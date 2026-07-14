"use client";

import { useEffect, useId, useRef, useState } from "react";

import {
  createKnowledgeAnswerPost,
  createKnowledgeRefreshLifecycle,
  resolveKnowledgeAnswerFreshness,
  retryFailedPost,
  type KnowledgeAnswerPost,
} from "./progressionLifecycle.mjs";

const RUNNER_URL = "http://127.0.0.1:8765";

export type SharedCourseState = {
  course_id?: string;
  curriculum_id?: string;
  completed_labs?: string[];
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
          `Runner request failed (${response.status} ${response.statusText})`,
      );
    }
    return payload as T;
  } finally {
    window.clearTimeout(timeout);
    init?.signal?.removeEventListener("abort", abort);
  }
}

function runnerError(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "本地 Runner 响应超时。请确认学习服务仍在运行。";
  }
  const detail = error instanceof Error ? error.message : "发生未知错误。";
  return `本地 Runner 请求失败：${detail}`;
}

export function KnowledgeCheck({
  labId,
  refreshVersion,
  onProgressChange,
  onStateChange,
}: {
  labId: string;
  refreshVersion: number;
  onProgressChange: (labId: string, progress: KnowledgeProgress) => void;
  onStateChange: (state: SharedCourseState) => boolean;
}) {
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
        setLoadError(runnerError(requestError));
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
      setSubmitError(runnerError(requestError));
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
          <p className="eyebrow">CHECK</p>
          <h3 id={`knowledge-title-${groupPrefix}`}>知识检查</h3>
        </div>
        <span className="knowledge-status">
          {knowledge
            ? knowledge.completed
              ? `已完成 · ${knowledge.mastered}/${knowledge.total}`
              : `${knowledge.mastered}/${knowledge.total} 已掌握`
            : loading
              ? "正在加载…"
              : "尚未加载"}
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
            重新加载
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
            重试提交
          </button>
        </div>
      ) : null}

      {knowledge && !knowledge.available ? (
        <p className="knowledge-prerequisite">
          当前知识检查尚不可用。请先完成前置 Lab 的知识检查与学习要求。
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
                      {question.kind === "execution_trace" ? "执行推演" : "诊断分析"}
                    </small>
                  ) : null}
                  <span>{question.prompt}</span>
                  {question.mastered ? <small>已掌握</small> : null}
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
                    {submittingQuestionId === question.id ? "检查中…" : "检查答案"}
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
                      <strong>{feedback.correct ? "回答正确。" : "回答不正确。"}</strong>{" "}
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
        <p className="knowledge-loading">正在从本地 Runner 读取知识检查…</p>
      ) : null}
    </section>
  );
}
