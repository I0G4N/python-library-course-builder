export type OperationContext = Readonly<{
  labId: string;
  questionId: string;
  path: string;
  source: string;
}>;

export type SelectionToken = Readonly<{
  selectionGeneration: number;
}>;

export type OperationToken = Readonly<
  OperationContext & {
    selectionGeneration: number;
    operationGeneration: number;
  }
>;

export type OperationLifecycle = Readonly<{
  captureSelection: () => SelectionToken;
  changeSelection: () => void;
  beginOperation: (context: OperationContext) => OperationToken;
  isSelectionCurrent: (token: SelectionToken) => boolean;
  isOperationCurrent: (token: OperationToken) => boolean;
}>;

export type SharedStateSnapshot = {
  course_id?: unknown;
  curriculum_id?: unknown;
  unlocked_labs?: unknown;
  updated_at?: unknown;
  [key: string]: unknown;
};

export type StateSnapshotDecision<T extends SharedStateSnapshot> = Readonly<{
  accepted: boolean;
  reason: "accepted" | "identity" | "invalid" | "stale";
  state?: T;
}>;

export type StateSnapshotArbiter = Readonly<{
  accept: <T extends SharedStateSnapshot>(snapshot: T) => StateSnapshotDecision<T>;
  current: () => SharedStateSnapshot | null;
}>;

export type KnowledgeAnswer = Readonly<{
  lab_id: string;
  question_id: string;
  choice_id: string;
}>;

export type KnowledgeAnswerPost = Readonly<{
  path: "/api/knowledge/answer";
  method: "POST";
  body: string;
  payload: KnowledgeAnswer;
}>;

export type KnowledgeRefreshLifecycle = Readonly<{
  isSubmitting: () => boolean;
  beginSubmit: () => boolean;
  requestRefresh: () => boolean;
  queueRefresh: () => void;
  finishSubmit: () => boolean;
}>;

export type KnowledgeAnswerFreshness = Readonly<{
  stateAccepted: boolean;
  feedback: Readonly<{
    correct: boolean;
    feedback: string;
    explanation: string;
  }>;
}>;

export type ProgressPollController = Readonly<{
  sync: (visibilityState: string) => void;
  cleanup: () => void;
  isActive: () => boolean;
}>;

export function createOperationLifecycle(): OperationLifecycle;
export function shouldChangeLab(
  currentLabId: string | null | undefined,
  nextLabId: string,
): boolean;
export function clearSavedDraftIfUnchanged(
  drafts: Record<string, string>,
  path: string,
  savedSource: string,
): boolean;
export function createKnowledgeRefreshLifecycle(): KnowledgeRefreshLifecycle;
export function resolveKnowledgeAnswerFreshness<TState>(
  answer: Readonly<{
    correct: boolean;
    feedback: string;
    explanation: string;
    state: TState;
  }>,
  acceptState: (state: TState) => boolean,
  refreshLifecycle: Pick<KnowledgeRefreshLifecycle, "queueRefresh">,
): KnowledgeAnswerFreshness;
export function createStateSnapshotArbiter(): StateSnapshotArbiter;
export function createKnowledgeAnswerPost(
  payload: KnowledgeAnswer,
): KnowledgeAnswerPost;
export function retryFailedPost(
  post: KnowledgeAnswerPost | null,
): KnowledgeAnswerPost | null;
export function shouldPollProgress(visibilityState: string): boolean;
export function createProgressPollController<TTimer>(options: Readonly<{
  schedule: (callback: () => void, intervalMs: number) => TTimer;
  cancel: (timer: TTimer) => void;
  onPoll: () => void;
  intervalMs: number;
}>): ProgressPollController;
