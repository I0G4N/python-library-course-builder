"use client";

import { useEffect, useId, useRef, useState } from "react";

import {
  createKnowledgeAnswerPost,
  createKnowledgeRefreshLifecycle,
  resolveKnowledgeAnswerFreshness,
  retryFailedPost,
  type KnowledgeAnswerPost,
} from "./progressionLifecycle.mjs";
import {
  courseCopy,
  type CourseCopy,
  type CourseLanguage,
} from "./courseLocale.mjs";

const RUNNER_URL = "http://127.0.0.1:8765";

export type SharedCourseState = {
  course_id?: string;
  curriculum_id?: string;
  completed_labs?: string[];
  completed_preparatory_units?: string[];
  unlocked_labs?: string[];
  score?: number;
  total_points?: number;
  updated_at?: string | null;
  [key: string]: unknown;
};

export type KnowledgeProgress = {
  completed: boolean;
  mastered: number;
  total: number;
};

type KnowledgeChoice = {
  id: string;
  text: string;
};

type KnowledgeQuestion = {
  id: string;
  kind?: "execution_trace" | "diagnostic";
  prompt: string;
  choices: KnowledgeChoice[];
  mastered: boolean;
};

type KnowledgeView = KnowledgeProgress & {
  lab_id: string;
  title: string;
  available: boolean;
  questions: KnowledgeQuestion[];
};

type KnowledgeAnswerPayload = {
  correct: boolean;
  feedback: string;
  explanation: string;
  knowledge: KnowledgeView;
  state: SharedCourseState;
};

type QuestionFeedback = {
  correct: boolean;
  feedback: string;
  explanation: string;
};

function detailFromPayload(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  const message = (payload as { message?: unknown }).message;
  return typeof message === "string" ? message : null;
}

async function runnerRequest<T>(
  path: string,
  t: CourseCopy,
  init?: RequestInit,
  timeoutMs = 8_000,
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (init?.signal?.aborted) abort();
  init?.signal?.addEventListener("abort", abort, { once: true });
  const timeout = window.setTimeout(abort, timeoutMs);
  try {
    const response = await fetch(`${RUNNER_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(
        detailFromPayload(payload) ??
          t.runnerRequestStatus(response.status, response.statusText),
      );
    }
    return payload as T;
  } finally {
    window.clearTimeout(timeout);
    init?.signal?.removeEventListener("abort", abort);
  }
}

function runnerError(error: unknown, t: CourseCopy): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return t.runnerTimeout;
  }
  const detail = error instanceof Error ? error.message : t.unknownError;
  return t.runnerRequestFailed(detail);
}

export function KnowledgeCheck({
  labId,
  language,
  refreshVersion,
  onProgressChange,
  onStateChange,
}: {
  labId: string;
  language: CourseLanguage;
  refreshVersion: number;
  onProgressChange: (labId: string, progress: KnowledgeProgress) => void;
  onStateChange: (state: SharedCourseState) => boolean;
}) {
  const t = courseCopy(language);
  const groupPrefix = useId();
  const requestGenerationRef = useRef(0);
  const fetchRequestRef = useRef(0);
  const knowledgeRefreshLifecycleRef = useRef(
    createKnowledgeRefreshLifecycle(),
  );
  const submitControllerRef = useRef<AbortController | null>(null);
  const [retryVersion, setRetryVersion] = useState(0);
  const [queuedRefreshVersion, setQueuedRefreshVersion] = useState(0);
  const [knowledge, setKnowledge] = useState<KnowledgeView | null>(null);
  const [selectedChoices, setSelectedChoices] = useState<Record<string, string>>(
    {},
  );
  const [feedbackByQuestion, setFeedbackByQuestion] = useState<
    Record<string, QuestionFeedback>
  >({});
  const [loading, setLoading] = useState(true);
  const [submittingQuestionId, setSubmittingQuestionId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [failedSubmission, setFailedSubmission] =
    useState<KnowledgeAnswerPost | null>(null);

  useEffect(() => {
    requestGenerationRef.current += 1;
    return () => {
      requestGenerationRef.current += 1;
      submitControllerRef.current?.abort();
    };
  }, [labId]);

  useEffect(() => {
    if (!knowledgeRefreshLifecycleRef.current.requestRefresh()) return;
    const generation = requestGenerationRef.current;
    const requestId = ++fetchRequestRef.current;
    const controller = new AbortController();
    void runnerRequest<KnowledgeView>(
      `/api/knowledge/${encodeURIComponent(labId)}`,
      t,
      { signal: controller.signal },
    )
      .then((payload) => {
        if (
          generation !== requestGenerationRef.current ||
          requestId !== fetchRequestRef.current
        ) return;
        setKnowledge(payload);
        setLoadError(null);
        onProgressChange(payload.lab_id, {
          completed: payload.completed,
          mastered: payload.mastered,
          total: payload.total,
        });
      })
      .catch((requestError: unknown) => {
        if (
          controller.signal.aborted ||
          generation !== requestGenerationRef.current ||
          requestId !== fetchRequestRef.current
        ) return;
        setLoadError(runnerError(requestError, t));
      })
      .finally(() => {
        if (
          generation === requestGenerationRef.current &&
          requestId === fetchRequestRef.current
        ) setLoading(false);
      });
    return () => {
      controller.abort();
    };
  }, [
    labId,
    language,
    onProgressChange,
    queuedRefreshVersion,
    refreshVersion,
    retryVersion,
  ]);

  async function submitAnswer(submission: KnowledgeAnswerPost) {
    const questionId = submission.payload.question_id;
    if (
      submission.payload.lab_id !== labId ||
      !knowledge?.available ||
      !knowledgeRefreshLifecycleRef.current.beginSubmit()
    ) return;
    const generation = requestGenerationRef.current;
    const controller = new AbortController();
    fetchRequestRef.current += 1;
    submitControllerRef.current?.abort();
    submitControllerRef.current = controller;
    setSubmittingQuestionId(questionId);
    setLoading(false);
    setSubmitError(null);
    setFailedSubmission(null);
    try {
      const payload = await runnerRequest<KnowledgeAnswerPayload>(
        submission.path,
        t,
        {
          method: submission.method,
          signal: controller.signal,
          body: submission.body,
        },
      );
      if (generation !== requestGenerationRef.current) return;
      const freshness = resolveKnowledgeAnswerFreshness(
        payload,
        onStateChange,
        knowledgeRefreshLifecycleRef.current,
      );
      setFeedbackByQuestion((current) => ({
        ...current,
        [questionId]: freshness.feedback,
      }));
      if (!freshness.stateAccepted) return;
      setKnowledge(payload.knowledge);
      onProgressChange(payload.knowledge.lab_id, {
        completed: payload.knowledge.completed,
        mastered: payload.knowledge.mastered,
        total: payload.knowledge.total,
      });
    } catch (requestError) {
      if (
        controller.signal.aborted ||
        generation !== requestGenerationRef.current
      ) return;
      setFailedSubmission(submission);
      setSubmitError(runnerError(requestError, t));
    } finally {
      if (submitControllerRef.current === controller) {
        const shouldReplayRefresh =
          knowledgeRefreshLifecycleRef.current.finishSubmit();
        submitControllerRef.current = null;
        if (generation === requestGenerationRef.current) {
          setSubmittingQuestionId(null);
          if (shouldReplayRefresh) {
            setQueuedRefreshVersion((value) => value + 1);
          }
        }
      }
    }
  }

  function submitSelectedAnswer(questionId: string) {
    const selectedChoice = selectedChoices[questionId];
    if (
      !selectedChoice ||
      !knowledge?.available ||
      knowledgeRefreshLifecycleRef.current.isSubmitting()
    ) {
      return;
    }
    void submitAnswer(
      createKnowledgeAnswerPost({
        lab_id: labId,
        question_id: questionId,
        choice_id: selectedChoice,
      }),
    );
  }

  return (
    <section
      className="knowledge-check"
      aria-labelledby={`knowledge-title-${groupPrefix}`}
    >
      <header className="knowledge-heading">
        <div>
          <p className="eyebrow">{t.checkLabel}</p>
          <h3 id={`knowledge-title-${groupPrefix}`}>{t.knowledgeCheck}</h3>
        </div>
        <span className="knowledge-status">
          {knowledge
            ? knowledge.completed
              ? t.knowledgeCompleted(knowledge.mastered, knowledge.total)
              : t.knowledgeMastered(knowledge.mastered, knowledge.total)
            : loading
              ? t.loading
              : t.notLoaded}
        </span>
      </header>

      {loadError ? (
        <div className="knowledge-error" role="alert">
          <p>{loadError}</p>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              setLoadError(null);
              setRetryVersion((value) => value + 1);
            }}
          >
            {t.reload}
          </button>
        </div>
      ) : null}

      {submitError && failedSubmission ? (
        <div className="knowledge-error" role="alert">
          <p>{submitError}</p>
          <button
            type="button"
            disabled={submittingQuestionId !== null}
            onClick={() => {
              const retry = retryFailedPost(failedSubmission);
              if (retry) void submitAnswer(retry);
            }}
          >
            {t.retrySubmit}
          </button>
        </div>
      ) : null}

      {knowledge && !knowledge.available ? (
        <p className="knowledge-prerequisite">
          {t.knowledgeUnavailable}
        </p>
      ) : null}

      {knowledge?.available ? (
        <div className="knowledge-questions" aria-busy={loading}>
          {knowledge.questions.map((question, questionIndex) => {
            const selectedChoice = selectedChoices[question.id] ?? "";
            const feedback = feedbackByQuestion[question.id];
            const fieldsetId = `${groupPrefix}-${questionIndex}`;
            return (
              <fieldset
                className={
                  question.mastered
                    ? "knowledge-question mastered"
                    : "knowledge-question"
                }
                key={question.id}
                disabled={submittingQuestionId === question.id}
              >
                <legend>
                  {question.kind ? (
                    <small className="knowledge-kind">
                      {question.kind === "execution_trace" ? t.executionTrace : t.diagnosticAnalysis}
                    </small>
                  ) : null}
                  <span>{question.prompt}</span>
                  {question.mastered ? <small>{t.mastered}</small> : null}
                </legend>
                <div className="knowledge-choices">
                  {question.choices.map((choice, choiceIndex) => {
                    const inputId = `${fieldsetId}-${choiceIndex}`;
                    return (
                      <label htmlFor={inputId} key={choice.id}>
                        <input
                          id={inputId}
                          type="radio"
                          name={fieldsetId}
                          value={choice.id}
                          checked={selectedChoice === choice.id}
                          onChange={() => {
                            setSelectedChoices((current) => ({
                              ...current,
                              [question.id]: choice.id,
                            }));
                          }}
                        />
                        <span>{choice.text}</span>
                      </label>
                    );
                  })}
                </div>
                <div className="knowledge-answer-row">
                  <button
                    type="button"
                    className="knowledge-submit"
                    onClick={() => submitSelectedAnswer(question.id)}
                    disabled={!selectedChoice || submittingQuestionId !== null}
                  >
                    {submittingQuestionId === question.id ? t.checking : t.checkAnswer}
                  </button>
                  {feedback ? (
                    <p
                      className={
                        feedback.correct
                          ? "knowledge-feedback correct"
                          : "knowledge-feedback incorrect"
                      }
                      aria-live="polite"
                    >
                      <strong>{feedback.correct ? t.correctAnswer : t.incorrectAnswer}</strong>{" "}
                      <span>{feedback.feedback}</span>{" "}
                      <span>{feedback.explanation}</span>
                    </p>
                  ) : null}
                </div>
              </fieldset>
            );
          })}
        </div>
      ) : loading && !knowledge ? (
        <p className="knowledge-loading">{t.loadingKnowledge}</p>
      ) : null}
    </section>
  );
}
