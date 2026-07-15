export const SIDEBAR_DEFAULT_WIDTH = 208;
export const SIDEBAR_MIN_WIDTH = 160;
export const SIDEBAR_MAX_WIDTH = 320;
export const SIDEBAR_COLLAPSED_WIDTH = 64;
export const LESSON_MIN_WIDTH = 320;
export const WORK_MIN_WIDTH = 440;
export const RESIZE_SEPARATOR_SIZE = 12;
export const RESIZE_KEYBOARD_STEP = 16;
export const DEFAULT_LESSON_RATIO = 0.42;

export const DEFAULT_LAYOUT_PREFERENCES = Object.freeze({
  sidebarWidth: SIDEBAR_DEFAULT_WIDTH,
  sidebarCollapsed: false,
  lessonRatio: DEFAULT_LESSON_RATIO,
});

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function finiteNumber(value, fallback) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function normalizeLayoutPreferences(value) {
  const candidate = value && typeof value === "object" ? value : {};
  return {
    sidebarWidth: clamp(
      finiteNumber(candidate.sidebarWidth, SIDEBAR_DEFAULT_WIDTH),
      SIDEBAR_MIN_WIDTH,
      SIDEBAR_MAX_WIDTH,
    ),
    sidebarCollapsed:
      typeof candidate.sidebarCollapsed === "boolean"
        ? candidate.sidebarCollapsed
        : false,
    lessonRatio: clamp(
      finiteNumber(candidate.lessonRatio, DEFAULT_LESSON_RATIO),
      0,
      1,
    ),
  };
}

export function parseLayoutPreferences(serialized) {
  if (typeof serialized !== "string") {
    return { ...DEFAULT_LAYOUT_PREFERENCES };
  }
  try {
    return normalizeLayoutPreferences(JSON.parse(serialized));
  } catch {
    return { ...DEFAULT_LAYOUT_PREFERENCES };
  }
}

export function serializeLayoutPreferences(preferences) {
  return JSON.stringify(normalizeLayoutPreferences(preferences));
}

export function layoutStorageKey(courseId) {
  const normalizedId = String(courseId || "course").trim() || "course";
  return `coursekit.layout.v1.${normalizedId}`;
}

export function collapseSidebar(preferences) {
  return {
    ...normalizeLayoutPreferences(preferences),
    sidebarCollapsed: true,
  };
}

export function expandSidebar(preferences) {
  return {
    ...normalizeLayoutPreferences(preferences),
    sidebarCollapsed: false,
  };
}

export function resolveSidebarMaximum(viewportWidth) {
  const width = finiteNumber(viewportWidth, Number.POSITIVE_INFINITY);
  const spaceForMain =
    LESSON_MIN_WIDTH +
    WORK_MIN_WIDTH +
    RESIZE_SEPARATOR_SIZE * 2 +
    24;
  return Math.max(
    SIDEBAR_MIN_WIDTH,
    Math.min(SIDEBAR_MAX_WIDTH, width - spaceForMain),
  );
}

export function resolveSidebarWidth(preferences, viewportWidth) {
  const normalized = normalizeLayoutPreferences(preferences);
  if (normalized.sidebarCollapsed) return SIDEBAR_COLLAPSED_WIDTH;
  return clamp(
    normalized.sidebarWidth,
    SIDEBAR_MIN_WIDTH,
    resolveSidebarMaximum(viewportWidth),
  );
}

export function resolveLessonWidth(containerWidth, lessonRatio) {
  const width = Math.max(0, finiteNumber(containerWidth, 0));
  const available = Math.max(0, width - RESIZE_SEPARATOR_SIZE);
  const maximum = Math.max(LESSON_MIN_WIDTH, available - WORK_MIN_WIDTH);
  return clamp(
    Math.round(available * clamp(finiteNumber(lessonRatio, DEFAULT_LESSON_RATIO), 0, 1)),
    LESSON_MIN_WIDTH,
    maximum,
  );
}

export function lessonRatioFromWidth(containerWidth, lessonWidth) {
  const available = Math.max(
    1,
    finiteNumber(containerWidth, 0) - RESIZE_SEPARATOR_SIZE,
  );
  const resolvedWidth = resolveLessonWidth(containerWidth, lessonWidth / available);
  return clamp(resolvedWidth / available, 0, 1);
}

export function nextSeparatorValue(value, key, min, max) {
  const current = clamp(finiteNumber(value, min), min, max);
  if (key === "ArrowLeft") {
    return clamp(current - RESIZE_KEYBOARD_STEP, min, max);
  }
  if (key === "ArrowRight") {
    return clamp(current + RESIZE_KEYBOARD_STEP, min, max);
  }
  if (key === "Home") return min;
  if (key === "End") return max;
  return null;
}

export function isCodingUnit({
  unitType,
  graded,
  legacyFoundationSelected,
}) {
  if (unitType !== undefined) {
    return unitType === "lab" && graded === true;
  }
  if (legacyFoundationSelected) return false;
  return graded !== false;
}

export function readinessPreparationTitles(readiness) {
  if (!readiness || typeof readiness !== "object") return [];
  const configured = readiness.preparatory ?? readiness.foundation ?? [];
  return Array.isArray(configured)
    ? configured.filter((value) => typeof value === "string")
    : [];
}

export function completedUnitIds(state) {
  if (!state || typeof state !== "object") return [];
  const formal = Array.isArray(state.completed_labs) ? state.completed_labs : [];
  const preparatory = Array.isArray(state.completed_preparatory_units)
    ? state.completed_preparatory_units
    : [];
  return [...new Set([...formal, ...preparatory].filter((value) => typeof value === "string"))];
}

export function shouldShowCodingWorkspace({
  codingUnitSelected,
  selectedLabNavigable,
  foundationKnowledgeComplete,
  currentKnowledgeComplete,
}) {
  return Boolean(
    codingUnitSelected &&
      selectedLabNavigable &&
      foundationKnowledgeComplete &&
      currentKnowledgeComplete,
  );
}
