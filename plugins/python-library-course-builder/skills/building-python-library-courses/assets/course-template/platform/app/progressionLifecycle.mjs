const KNOWLEDGE_ANSWER_PATH = "/api/knowledge/answer";
const ISO_TIMESTAMP =
  /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$/;

function parseIsoTimestamp(value) {
  if (value === null) return null;
  if (typeof value !== "string") return undefined;
  const match = ISO_TIMESTAMP.exec(value);
  if (!match) return undefined;
  const fraction = match[2] ?? "";
  const milliseconds = fraction.padEnd(3, "0").slice(0, 3);
  const epochMilliseconds = Date.parse(`${match[1]}.${milliseconds}${match[3]}`);
  if (!Number.isFinite(epochMilliseconds)) return undefined;
  return Object.freeze({
    epochMilliseconds,
    submillisecond: fraction.slice(3),
  });
}

function timestampIsNotNewer(candidate, current) {
  if (current === null) return candidate === null;
  if (candidate === null) return true;
  if (candidate.epochMilliseconds !== current.epochMilliseconds) {
    return candidate.epochMilliseconds < current.epochMilliseconds;
  }
  const precision = Math.max(
    candidate.submillisecond.length,
    current.submillisecond.length,
  );
  return (
    candidate.submillisecond.padEnd(precision, "0") <=
    current.submillisecond.padEnd(precision, "0")
  );
}

function snapshotMetadata(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  const { course_id: courseId, curriculum_id: curriculumId, updated_at: updatedAt } =
    snapshot;
  if (
    typeof courseId !== "string" ||
    courseId.length === 0 ||
    typeof curriculumId !== "string" ||
    curriculumId.length === 0 ||
    !Array.isArray(snapshot.unlocked_labs)
  ) {
    return null;
  }
  const timestamp = parseIsoTimestamp(updatedAt);
  if (timestamp === undefined) return null;
  return {
    identity: `${courseId}\u0000${curriculumId}`,
    timestamp,
  };
}

export function createOperationLifecycle() {
  let selectionGeneration = 0;
  let operationGeneration = 0;

  return Object.freeze({
    captureSelection() {
      return Object.freeze({ selectionGeneration });
    },
    changeSelection() {
      selectionGeneration += 1;
    },
    beginOperation(context) {
      operationGeneration += 1;
      return Object.freeze({
        labId: context.labId,
        questionId: context.questionId,
        path: context.path,
        source: context.source,
        selectionGeneration,
        operationGeneration,
      });
    },
    isSelectionCurrent(token) {
      return token?.selectionGeneration === selectionGeneration;
    },
    isOperationCurrent(token) {
      return (
        token?.selectionGeneration === selectionGeneration &&
        token?.operationGeneration === operationGeneration
      );
    },
  });
}

export function shouldChangeLab(currentLabId, nextLabId) {
  return currentLabId !== nextLabId;
}

export function clearSavedDraftIfUnchanged(drafts, path, savedSource) {
  if (drafts[path] !== savedSource) return false;
  delete drafts[path];
  return true;
}

export function createKnowledgeRefreshLifecycle() {
  let submitting = false;
  let refreshQueued = false;

  return Object.freeze({
    isSubmitting() {
      return submitting;
    },
    beginSubmit() {
      if (submitting) return false;
      submitting = true;
      return true;
    },
    requestRefresh() {
      if (!submitting) return true;
      refreshQueued = true;
      return false;
    },
    queueRefresh() {
      refreshQueued = true;
    },
    finishSubmit() {
      if (!submitting) return false;
      submitting = false;
      const shouldReplay = refreshQueued;
      refreshQueued = false;
      return shouldReplay;
    },
  });
}

export function resolveKnowledgeAnswerFreshness(
  answer,
  acceptState,
  refreshLifecycle,
) {
  const stateAccepted = acceptState(answer.state) === true;
  if (!stateAccepted) refreshLifecycle.queueRefresh();
  return Object.freeze({
    stateAccepted,
    feedback: Object.freeze({
      correct: answer.correct,
      feedback: answer.feedback,
      explanation: answer.explanation,
    }),
  });
}

export function createStateSnapshotArbiter() {
  let acceptedSnapshot = null;
  let acceptedMetadata = null;

  return Object.freeze({
    accept(snapshot) {
      const metadata = snapshotMetadata(snapshot);
      if (!metadata) {
        return Object.freeze({ accepted: false, reason: "invalid" });
      }
      if (acceptedMetadata) {
        if (metadata.identity !== acceptedMetadata.identity) {
          return Object.freeze({ accepted: false, reason: "identity" });
        }
        if (timestampIsNotNewer(metadata.timestamp, acceptedMetadata.timestamp)) {
          return Object.freeze({ accepted: false, reason: "stale" });
        }
      }
      acceptedSnapshot = snapshot;
      acceptedMetadata = metadata;
      return Object.freeze({ accepted: true, reason: "accepted", state: snapshot });
    },
    current() {
      return acceptedSnapshot;
    },
  });
}

export function createKnowledgeAnswerPost(payload) {
  const capturedPayload = Object.freeze({
    lab_id: payload.lab_id,
    question_id: payload.question_id,
    choice_id: payload.choice_id,
  });
  return Object.freeze({
    path: KNOWLEDGE_ANSWER_PATH,
    method: "POST",
    body: JSON.stringify(capturedPayload),
    payload: capturedPayload,
  });
}

export function retryFailedPost(post) {
  if (
    !post ||
    post.path !== KNOWLEDGE_ANSWER_PATH ||
    post.method !== "POST" ||
    typeof post.body !== "string"
  ) {
    return null;
  }
  return post;
}

export function shouldPollProgress(visibilityState) {
  return visibilityState === "visible";
}

export function createProgressPollController({
  schedule,
  cancel,
  onPoll,
  intervalMs,
}) {
  let timer;
  let disposed = false;

  function stop() {
    if (timer === undefined) return;
    cancel(timer);
    timer = undefined;
  }

  return Object.freeze({
    sync(visibilityState) {
      if (disposed) return;
      if (!shouldPollProgress(visibilityState)) {
        stop();
        return;
      }
      if (timer === undefined) timer = schedule(onPoll, intervalMs);
    },
    cleanup() {
      disposed = true;
      stop();
    },
    isActive() {
      return timer !== undefined;
    },
  });
}
