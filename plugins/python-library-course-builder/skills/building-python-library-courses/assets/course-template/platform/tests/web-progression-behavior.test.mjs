import assert from "node:assert/strict";
import test from "node:test";

let lifecycle = {};
try {
  lifecycle = await import("../app/progressionLifecycle.mjs");
} catch (error) {
  if (error?.code !== "ERR_MODULE_NOT_FOUND") throw error;
}

function requiredExport(name) {
  assert.equal(
    typeof lifecycle[name],
    "function",
    `progressionLifecycle.mjs must export ${name}()`,
  );
  return lifecycle[name];
}

function state(overrides = {}) {
  return {
    course_id: "course-generic",
    curriculum_id: "curriculum-v1",
    unlocked_labs: ["foundation"],
    completed_labs: [],
    score: 0,
    total_points: 10,
    updated_at: null,
    ...overrides,
  };
}

test("selection and operation generations reject late save/run UI work", () => {
  const createOperationLifecycle = requiredExport("createOperationLifecycle");
  const operations = createOperationLifecycle();
  const selectionA = operations.captureSelection();
  const runA = operations.beginOperation({
    labId: "lab-alpha",
    questionId: "question-alpha",
    path: "labs/alpha.py",
    source: "value = 'alpha'",
  });

  assert.equal(operations.isSelectionCurrent(selectionA), true);
  assert.equal(operations.isOperationCurrent(runA), true);

  operations.changeSelection();

  assert.equal(operations.isSelectionCurrent(selectionA), false);
  assert.equal(operations.isOperationCurrent(runA), false);
  assert.deepEqual(
    {
      labId: runA.labId,
      questionId: runA.questionId,
      path: runA.path,
      source: runA.source,
    },
    {
      labId: "lab-alpha",
      questionId: "question-alpha",
      path: "labs/alpha.py",
      source: "value = 'alpha'",
    },
    "an async operation keeps the context captured when it began",
  );

  const saveB = operations.beginOperation({
    labId: "lab-beta",
    questionId: "question-beta",
    path: "labs/beta.py",
    source: "value = 'beta'",
  });
  const runB = operations.beginOperation({
    labId: "lab-beta",
    questionId: "question-beta",
    path: "labs/beta.py",
    source: "value = 'beta changed'",
  });

  assert.equal(operations.isOperationCurrent(saveB), false);
  assert.equal(operations.isOperationCurrent(runB), true);
});

test("clicking the selected Lab does not begin a new selection lifecycle", () => {
  const shouldChangeLab = requiredExport("shouldChangeLab");

  assert.equal(shouldChangeLab("lab-alpha", "lab-alpha"), false);
  assert.equal(shouldChangeLab("lab-alpha", "lab-beta"), true);
  assert.equal(shouldChangeLab(null, "lab-alpha"), true);
});

test("shared state arbitration is monotonic and course-scoped", () => {
  const createStateSnapshotArbiter = requiredExport(
    "createStateSnapshotArbiter",
  );
  const arbiter = createStateSnapshotArbiter();
  const initial = state();
  const newer = state({
    unlocked_labs: ["foundation", "practice"],
    score: 6,
    updated_at: "2026-07-13T10:01:00.000Z",
  });
  const older = state({
    unlocked_labs: ["foundation"],
    score: 2,
    updated_at: "2026-07-13T10:00:00.000Z",
  });
  const equalTimestamp = state({
    unlocked_labs: ["foundation"],
    score: 1,
    updated_at: newer.updated_at,
  });

  assert.equal(arbiter.accept(initial).accepted, true);
  assert.equal(
    arbiter.accept(state({ score: 9 })).accepted,
    false,
    "two null timestamps cannot overwrite one another by arrival order",
  );
  assert.equal(arbiter.accept(newer).accepted, true);
  assert.equal(
    arbiter.accept(equalTimestamp).accepted,
    false,
    "equal timestamps cannot overwrite the accepted snapshot by arrival order",
  );
  assert.equal(arbiter.accept(older).accepted, false);
  assert.equal(arbiter.accept(initial).accepted, false, "null is older than ISO");
  assert.equal(arbiter.current(), newer);

  const otherCourse = state({
    course_id: "another-course",
    updated_at: "2026-07-13T10:02:00.000Z",
  });
  assert.equal(arbiter.accept(otherCourse).accepted, false);
  assert.equal(
    arbiter.accept(
      state({
        curriculum_id: "curriculum-v2",
        updated_at: "2026-07-13T10:03:00.000Z",
      }),
    ).accepted,
    false,
  );
  assert.equal(arbiter.current(), newer);
});

test("shared state arbitration preserves sub-millisecond ISO ordering", () => {
  const createStateSnapshotArbiter = requiredExport(
    "createStateSnapshotArbiter",
  );
  const arbiter = createStateSnapshotArbiter();
  const newer = state({
    score: 8,
    updated_at: "2026-07-13T10:01:00.000002+00:00",
  });
  const older = state({
    score: 7,
    updated_at: "2026-07-13T10:01:00.000001Z",
  });

  assert.equal(arbiter.accept(newer).accepted, true);
  assert.equal(arbiter.accept(older).accepted, false);
  assert.equal(arbiter.current(), newer);
});

test("shared state arbitration rejects malformed identity, timestamps, and unlock data", () => {
  const createStateSnapshotArbiter = requiredExport(
    "createStateSnapshotArbiter",
  );
  const invalidStates = [
    state({ course_id: "" }),
    state({ curriculum_id: "" }),
    state({ unlocked_labs: null }),
    state({ updated_at: "not-an-iso-timestamp" }),
    state({ updated_at: "2026-07-13" }),
  ];

  for (const invalidState of invalidStates) {
    const arbiter = createStateSnapshotArbiter();
    assert.equal(arbiter.accept(invalidState).accepted, false);
    assert.equal(arbiter.current(), null);
  }
});

test("failed knowledge answers retain the exact POST for retry", async () => {
  const createKnowledgeAnswerPost = requiredExport(
    "createKnowledgeAnswerPost",
  );
  const retryFailedPost = requiredExport("retryFailedPost");
  const post = createKnowledgeAnswerPost({
    lab_id: "lab-generic",
    question_id: "question-generic",
    choice_id: "choice-b",
  });
  const calls = [];

  async function execute(request) {
    calls.push({ path: request.path, method: request.method, body: request.body });
    if (calls.length === 1) throw new Error("temporary Runner failure");
  }

  let failedPost = null;
  try {
    await execute(post);
  } catch {
    failedPost = post;
  }
  const retry = retryFailedPost(failedPost);
  assert.equal(retry, post, "retry reuses the exact immutable request descriptor");
  await execute(retry);

  assert.deepEqual(calls, [
    { path: "/api/knowledge/answer", method: "POST", body: post.body },
    { path: "/api/knowledge/answer", method: "POST", body: post.body },
  ]);
  assert.equal(Object.isFrozen(post), true);
  assert.equal(Object.isFrozen(post.payload), true);
});

test("knowledge refreshes queue during submit and replay once afterward", () => {
  const createKnowledgeRefreshLifecycle = requiredExport(
    "createKnowledgeRefreshLifecycle",
  );
  const refreshes = createKnowledgeRefreshLifecycle();

  assert.equal(refreshes.requestRefresh(), true);
  assert.equal(refreshes.beginSubmit(), true);
  assert.equal(refreshes.beginSubmit(), false);
  assert.equal(refreshes.isSubmitting(), true);
  assert.equal(refreshes.requestRefresh(), false);
  assert.equal(refreshes.requestRefresh(), false, "multiple refreshes coalesce");
  assert.equal(refreshes.finishSubmit(), true, "successful submit replays once");
  assert.equal(refreshes.isSubmitting(), false);
  assert.equal(refreshes.finishSubmit(), false, "replay intent is consumed");

  assert.equal(refreshes.beginSubmit(), true);
  assert.equal(refreshes.requestRefresh(), false);
  assert.equal(refreshes.finishSubmit(), true, "failed submit also replays once");
  assert.equal(refreshes.requestRefresh(), true);
});

test("stale answer state keeps feedback but queues authoritative knowledge", () => {
  const createKnowledgeRefreshLifecycle = requiredExport(
    "createKnowledgeRefreshLifecycle",
  );
  const resolveKnowledgeAnswerFreshness = requiredExport(
    "resolveKnowledgeAnswerFreshness",
  );
  const createStateSnapshotArbiter = requiredExport(
    "createStateSnapshotArbiter",
  );
  const arbiter = createStateSnapshotArbiter();
  const refreshes = createKnowledgeRefreshLifecycle();
  const current = state({
    score: 4,
    updated_at: "2026-07-13T11:00:00.000Z",
  });
  assert.equal(arbiter.accept(current).accepted, true);
  assert.equal(refreshes.beginSubmit(), true);

  const staleAnswer = resolveKnowledgeAnswerFreshness(
    {
      correct: false,
      feedback: "This choice skips the ownership boundary.",
      explanation: "The submitted choice is not correct.",
      state: state({
        score: 1,
        updated_at: "2026-07-13T10:59:59.000Z",
      }),
    },
    (candidate) => arbiter.accept(candidate).accepted,
    refreshes,
  );

  assert.equal(staleAnswer.stateAccepted, false);
  assert.deepEqual(staleAnswer.feedback, {
    correct: false,
    feedback: "This choice skips the ownership boundary.",
    explanation: "The submitted choice is not correct.",
  });
  assert.equal(arbiter.current(), current);
  assert.equal(refreshes.finishSubmit(), true);

  assert.equal(refreshes.beginSubmit(), true);
  const freshAnswer = resolveKnowledgeAnswerFreshness(
    {
      correct: true,
      feedback: "This choice follows the execution trace.",
      explanation: "The submitted choice is correct.",
      state: state({
        score: 5,
        updated_at: "2026-07-13T11:00:01.000Z",
      }),
    },
    (candidate) => arbiter.accept(candidate).accepted,
    refreshes,
  );
  assert.equal(freshAnswer.stateAccepted, true);
  assert.deepEqual(freshAnswer.feedback, {
    correct: true,
    feedback: "This choice follows the execution trace.",
    explanation: "The submitted choice is correct.",
  });
  assert.equal(refreshes.finishSubmit(), false);
});

test("a completed PUT clears only the exact draft it saved", () => {
  const clearSavedDraftIfUnchanged = requiredExport(
    "clearSavedDraftIfUnchanged",
  );
  const path = "labs/generic.py";
  const capturedSource = "value = 'captured'";
  const drafts = { [path]: capturedSource };

  assert.equal(
    clearSavedDraftIfUnchanged(drafts, path, capturedSource),
    true,
  );
  assert.equal(path in drafts, false);

  drafts[path] = capturedSource;
  drafts[path] = "value = 'typed while PUT was pending'";
  assert.equal(
    clearSavedDraftIfUnchanged(drafts, path, capturedSource),
    false,
  );
  assert.equal(drafts[path], "value = 'typed while PUT was pending'");
});

test("progress polling starts, stops, restarts, and cleans up exactly once", () => {
  const createProgressPollController = requiredExport(
    "createProgressPollController",
  );
  const callbacks = new Map();
  const scheduled = [];
  const canceled = [];
  const polls = [];
  let nextTimer = 0;
  const polling = createProgressPollController({
    schedule(callback, intervalMs) {
      nextTimer += 1;
      callbacks.set(nextTimer, callback);
      scheduled.push({ timer: nextTimer, intervalMs });
      return nextTimer;
    },
    cancel(timer) {
      canceled.push(timer);
      callbacks.delete(timer);
    },
    onPoll() {
      polls.push("poll");
    },
    intervalMs: 5_000,
  });

  assert.equal(polling.isActive(), false);
  polling.sync("visible");
  polling.sync("visible");
  assert.equal(polling.isActive(), true);
  assert.deepEqual(scheduled, [{ timer: 1, intervalMs: 5_000 }]);

  callbacks.get(1)();
  assert.deepEqual(polls, ["poll"]);

  polling.sync("hidden");
  polling.sync("prerender");
  assert.equal(polling.isActive(), false);
  assert.deepEqual(canceled, [1]);

  polling.sync("visible");
  assert.equal(polling.isActive(), true);
  assert.deepEqual(scheduled, [
    { timer: 1, intervalMs: 5_000 },
    { timer: 2, intervalMs: 5_000 },
  ]);

  polling.cleanup();
  polling.cleanup();
  polling.sync("visible");
  assert.equal(polling.isActive(), false);
  assert.deepEqual(canceled, [1, 2]);
  assert.equal(scheduled.length, 2, "a cleaned-up controller stays inert");
});
