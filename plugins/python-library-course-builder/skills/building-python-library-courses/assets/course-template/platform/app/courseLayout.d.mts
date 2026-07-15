export type LayoutPreferences = {
  sidebarWidth: number;
  sidebarCollapsed: boolean;
  lessonRatio: number;
};

export type CourseUnitType = "orientation" | "preparatory" | "lab";

export type CodingUnitMetadata = {
  unitType?: CourseUnitType;
  graded?: boolean;
  legacyFoundationSelected: boolean;
};

export type ReadinessProjection = {
  foundation?: unknown;
  preparatory?: unknown;
};

export type CompletionProjection = {
  completed_labs?: unknown;
  completed_preparatory_units?: unknown;
};

export type CodingWorkspaceGate = {
  codingUnitSelected: boolean;
  selectedLabNavigable: boolean;
  foundationKnowledgeComplete: boolean;
  currentKnowledgeComplete: boolean;
};

export const SIDEBAR_DEFAULT_WIDTH: number;
export const SIDEBAR_MIN_WIDTH: number;
export const SIDEBAR_MAX_WIDTH: number;
export const SIDEBAR_COLLAPSED_WIDTH: number;
export const LESSON_MIN_WIDTH: number;
export const WORK_MIN_WIDTH: number;
export const RESIZE_SEPARATOR_SIZE: number;
export const RESIZE_KEYBOARD_STEP: number;
export const DEFAULT_LESSON_RATIO: number;
export const DEFAULT_LAYOUT_PREFERENCES: Readonly<LayoutPreferences>;

export function normalizeLayoutPreferences(value: unknown): LayoutPreferences;
export function parseLayoutPreferences(serialized: unknown): LayoutPreferences;
export function serializeLayoutPreferences(preferences: unknown): string;
export function layoutStorageKey(courseId: string): string;
export function collapseSidebar(preferences: LayoutPreferences): LayoutPreferences;
export function expandSidebar(preferences: LayoutPreferences): LayoutPreferences;
export function resolveSidebarMaximum(viewportWidth: number): number;
export function resolveSidebarWidth(
  preferences: LayoutPreferences,
  viewportWidth: number,
): number;
export function resolveLessonWidth(
  containerWidth: number,
  lessonRatio: number,
): number;
export function lessonRatioFromWidth(
  containerWidth: number,
  lessonWidth: number,
): number;
export function nextSeparatorValue(
  value: number,
  key: string,
  min: number,
  max: number,
): number | null;
export function isCodingUnit(metadata: CodingUnitMetadata): boolean;
export function readinessPreparationTitles(
  readiness: ReadinessProjection | null | undefined,
): string[];
export function completedUnitIds(
  state: CompletionProjection | null | undefined,
): string[];
export function shouldShowCodingWorkspace(
  gate: CodingWorkspaceGate,
): boolean;
