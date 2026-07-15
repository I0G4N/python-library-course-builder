"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";

import {
  CourseLesson,
  type CourseContentItem,
  type PracticeLink,
  type StudyMinutes,
} from "./CourseLesson";
import {
  KnowledgeCheck,
  type KnowledgeProgress,
  type SharedCourseState,
} from "./KnowledgeCheck";
import { PythonCodeEditor } from "./PythonCode";
import { ResizeSeparator } from "./ResizeSeparator";
import {
  DEFAULT_LAYOUT_PREFERENCES,
  LESSON_MIN_WIDTH,
  RESIZE_SEPARATOR_SIZE,
  SIDEBAR_COLLAPSED_WIDTH,
  SIDEBAR_MIN_WIDTH,
  WORK_MIN_WIDTH,
  collapseSidebar,
  completedUnitIds,
  expandSidebar,
  isCodingUnit,
  layoutStorageKey,
  lessonRatioFromWidth,
  normalizeLayoutPreferences,
  parseLayoutPreferences,
  resolveLessonWidth,
  resolveSidebarMaximum,
  resolveSidebarWidth,
  readinessPreparationTitles,
  serializeLayoutPreferences,
  shouldShowCodingWorkspace,
  type CourseUnitType,
  type LayoutPreferences,
} from "./courseLayout.mjs";
import {
  clearSavedDraftIfUnchanged,
  createOperationLifecycle,
  createProgressPollController,
  createStateSnapshotArbiter,
  shouldChangeLab,
  shouldPollProgress,
  type OperationToken,
} from "./progressionLifecycle.mjs";

const RUNNER_URL = "http://127.0.0.1:8765";

type CourseQuestion = {
  id: string;
  title: string;
  file: string;
  symbol?: string;
  prompt?: string;
  points?: number;
  example?: {
    input?: string;
    output?: string;
    explanation?: string;
  };
};

type CourseLab = {
  id: string;
  title: string;
  graded?: boolean;
  unit_type?: CourseUnitType;
  description?: string;
  concepts?: string[];
  questions?: CourseQuestion[];
  study_minutes?: StudyMinutes;
};

type CourseManifest = {
  course_id?: string;
  title: string;
  description?: string;
  project?: string;
  total_points?: number;
  capstone?: string | { title?: string; description?: string };
  readiness?: {
    assumed: string[];
    foundation?: string[];
    preparatory?: string[];
    route_id?: string;
    summary?: string;
  };
  labs: CourseLab[];
};

type CourseState = SharedCourseState;

type CoursePayload = {
  manifest: CourseManifest;
  state?: CourseState;
};

type FileReadPayload = {
  path: string;
  content: string;
};

type FileWritePayload = {
  path: string;
  status: "saved";
};

type RunPayload = {
  passed: boolean;
  output?: string;
  score?: number;
  state?: CourseState;
};

type FoundationKnowledgePayload = KnowledgeProgress & {
  lab_id: string;
};

type ConnectionState = "loading" | "online" | "error";
type RunMode = "public" | "submit";

function studyTimeLabel(study: StudyMinutes): string {
  return `${study.min}–${study.max} 分钟`;
}

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
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
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
  }
}

function capstoneSummary(capstone: CourseManifest["capstone"]): string | null {
  if (typeof capstone === "string") return capstone;
  if (!capstone) return null;
  return capstone.description ?? capstone.title ?? null;
}

function manifestCourseId(value: CourseManifest): string {
  return value.course_id?.trim() || value.title || "course";
}

function displayError(error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "本地 Runner 响应超时。请确认学习服务仍在运行。";
  }
  return error instanceof Error ? error.message : "发生未知错误。";
}

export function CourseKitApp() {
  const draftsRef = useRef<Record<string, string>>({});
  const learningGridRef = useRef<HTMLDivElement | null>(null);
  const stateRefreshRequestRef = useRef(0);
  const operationLifecycleRef = useRef(createOperationLifecycle());
  const stateArbiterRef = useRef(createStateSnapshotArbiter());
  const [connection, setConnection] = useState<ConnectionState>("loading");
  const [manifest, setManifest] = useState<CourseManifest | null>(null);
  const [courseState, setCourseState] = useState<CourseState>({
    unlocked_labs: [],
  });
  const [knowledgeProgress, setKnowledgeProgress] = useState<
    Record<string, KnowledgeProgress>
  >({});
  const [knowledgeRefreshVersion, setKnowledgeRefreshVersion] = useState(0);
  const [selectedLabId, setSelectedLabId] = useState("");
  const [selectedQuestionId, setSelectedQuestionId] = useState("");
  const [lesson, setLesson] = useState<CourseContentItem | null>(null);
  const [source, setSource] = useState("");
  const [loadedSource, setLoadedSource] = useState("");
  const [filePath, setFilePath] = useState("");
  const [lessonLoading, setLessonLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileLoadFailed, setFileLoadFailed] = useState(false);
  const [fileLoadRetryVersion, setFileLoadRetryVersion] = useState(0);
  const [running, setRunning] = useState<RunMode | null>(null);
  const [result, setResult] = useState<RunPayload | null>(null);
  const [notice, setNotice] = useState("正在连接本地 Runner…");
  const [layoutPreferences, setLayoutPreferences] =
    useState<LayoutPreferences>({ ...DEFAULT_LAYOUT_PREFERENCES });
  const [layoutReadyCourseId, setLayoutReadyCourseId] = useState("");
  const [viewportWidth, setViewportWidth] = useState(1_440);
  const [learningGridWidth, setLearningGridWidth] = useState(1_000);

  const labs = useMemo(() => manifest?.labs ?? [], [manifest]);
  const selectedLab = useMemo(
    () => labs.find((lab) => lab.id === selectedLabId) ?? labs[0] ?? null,
    [labs, selectedLabId],
  );
  const questions = useMemo(
    () => selectedLab?.questions ?? [],
    [selectedLab],
  );
  const selectedQuestion = useMemo(
    () =>
      questions.find((question) => question.id === selectedQuestionId) ??
      questions[0] ??
      null,
    [questions, selectedQuestionId],
  );
  const completed = useMemo(
    () => new Set(completedUnitIds(courseState)),
    [courseState],
  );
  const unlocked = useMemo(
    () => new Set(courseState.unlocked_labs ?? []),
    [courseState.unlocked_labs],
  );
  const foundationLabId = labs[0]?.id ?? "";
  const selectedLabNavigable = Boolean(
    selectedLab && unlocked.has(selectedLab.id),
  );
  const foundationKnowledgeComplete =
    knowledgeProgress[foundationLabId]?.completed === true;
  const currentKnowledgeComplete = selectedLab
    ? knowledgeProgress[selectedLab.id]?.completed === true
    : false;
  const codingUnitSelected = Boolean(
    selectedLab &&
      isCodingUnit({
        unitType: selectedLab.unit_type,
        graded: selectedLab.graded,
        legacyFoundationSelected: selectedLab.id === foundationLabId,
      }),
  );
  const codingReady = shouldShowCodingWorkspace({
    codingUnitSelected,
    selectedLabNavigable,
    foundationKnowledgeComplete,
    currentKnowledgeComplete,
  });
  const codingLockReasonId = "coding-lock-reason";
  const codingLockReason = !codingUnitSelected
    ? selectedLab?.unit_type === "preparatory"
      ? "先修单元不包含编码练习；完成知识检查后继续下一单元。"
      : "基础章节不包含编码练习；完成知识检查后进入正式 Lab。"
    : !selectedLabNavigable
      ? "此 Lab 尚未解锁，完成前置 Lab 后才能编码。"
      : !foundationKnowledgeComplete
        ? "请先完成基础章节的知识检查，之后才能编辑和运行代码。"
        : !currentKnowledgeComplete
          ? "请先完成当前 Lab 的知识检查，之后才能编辑和运行代码。"
          : null;
  const handlePractice = useCallback((link: PracticeLink) => {
    if (!selectedLab) return;
    let targetId = `knowledge-check-${selectedLab.id}`;
    if (link.kind === "coding-question") {
      operationLifecycleRef.current.changeSelection();
      setSelectedQuestionId(link.item_id);
      setFileLoadFailed(false);
      setFileLoading(codingReady);
      if (codingReady) {
        setFileLoadRetryVersion((value) => value + 1);
      }
      setResult(null);
      setRunning(null);
      setNotice(
        codingReady
          ? "正在载入所选练习…"
          : "完成本章知识检查后即可进入这道编码练习。",
      );
      targetId = codingReady ? "work-column" : targetId;
    }
    window.requestAnimationFrame(() => {
      const target = document.getElementById(targetId);
      target?.focus({ preventScroll: true });
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [codingReady, selectedLab]);
  const dirty = source !== loadedSource;
  const earned = courseState.score ?? result?.score;
  const total = courseState.total_points ?? manifest?.total_points;
  const courseId = manifest ? manifestCourseId(manifest) : "course";
  const sidebarMaximum = resolveSidebarMaximum(viewportWidth);
  const sidebarWidth = resolveSidebarWidth(layoutPreferences, viewportWidth);
  const lessonWidth = resolveLessonWidth(
    learningGridWidth,
    layoutPreferences.lessonRatio,
  );
  const lessonMaximum = Math.max(
    LESSON_MIN_WIDTH,
    learningGridWidth - RESIZE_SEPARATOR_SIZE - WORK_MIN_WIDTH,
  );
  const shellStyle = {
    "--sidebar-width": `${sidebarWidth}px`,
  } as CSSProperties;
  const learningGridStyle = {
    "--lesson-width": `${lessonWidth}px`,
  } as CSSProperties;
  const selectedFileReady = Boolean(
    codingReady &&
      selectedQuestion &&
      filePath === selectedQuestion.file &&
      !fileLoadFailed &&
      !fileLoading,
  );
  const selectedFilePending = Boolean(
    codingReady && selectedQuestion && !selectedFileReady,
  );
  const selectedFileLoading = selectedFilePending && !fileLoadFailed;

  const acceptCourseState = useCallback((state: CourseState): boolean => {
    const decision = stateArbiterRef.current.accept(state);
    if (!decision.accepted || !decision.state) return false;
    setCourseState(decision.state as CourseState);
    return true;
  }, []);

  const recordKnowledgeProgress = useCallback(
    (labId: string, progress: KnowledgeProgress) => {
      setKnowledgeProgress((current) => ({ ...current, [labId]: progress }));
    },
    [],
  );

  useEffect(() => {
    function measureViewport() {
      setViewportWidth(window.innerWidth);
    }
    measureViewport();
    window.addEventListener("resize", measureViewport);
    return () => window.removeEventListener("resize", measureViewport);
  }, []);

  useEffect(() => {
    if (!manifest || layoutReadyCourseId !== courseId) return;
    try {
      window.localStorage.setItem(
        layoutStorageKey(courseId),
        serializeLayoutPreferences(layoutPreferences),
      );
    } catch {
      // Resizing remains functional even when the browser rejects persistence.
    }
  }, [courseId, layoutPreferences, layoutReadyCourseId, manifest]);

  useEffect(() => {
    if (!manifest) return;
    const grid = learningGridRef.current;
    if (!grid) return;
    const gridElement = grid;

    function measureGrid() {
      const styles = window.getComputedStyle(gridElement);
      const horizontalPadding =
        Number.parseFloat(styles.paddingLeft) +
        Number.parseFloat(styles.paddingRight);
      setLearningGridWidth(
        Math.max(0, gridElement.clientWidth - horizontalPadding),
      );
    }

    measureGrid();
    const observer = new ResizeObserver(measureGrid);
    observer.observe(gridElement);
    window.addEventListener("resize", measureGrid);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measureGrid);
    };
  }, [manifest]);

  function resizeSidebar(nextWidth: number) {
    setLayoutPreferences((current) => {
      if (current.sidebarCollapsed) return current;
      return normalizeLayoutPreferences({
        ...current,
        sidebarCollapsed: false,
        sidebarWidth: nextWidth,
      });
    });
  }

  function resizeLesson(nextWidth: number) {
    setLayoutPreferences((current) => ({
      ...current,
      lessonRatio: lessonRatioFromWidth(learningGridWidth, nextWidth),
    }));
  }

  const refreshCourseState = useCallback(
    async function refreshCourseState() {
      const requestId = ++stateRefreshRequestRef.current;
      try {
        const payload = await runnerRequest<CourseState>("/api/state");
        if (requestId !== stateRefreshRequestRef.current) return;
        if (!acceptCourseState(payload)) return;
        setKnowledgeRefreshVersion((value) => value + 1);
      } catch (error) {
        if (requestId !== stateRefreshRequestRef.current) return;
        setNotice(`进度同步失败：${displayError(error)}`);
      }
    },
    [acceptCourseState],
  );

  useEffect(() => {
    let active = true;
    void runnerRequest<CoursePayload>("/api/course")
      .then((payload) => {
        if (!active) return;
        if (
          !payload.manifest ||
          !Array.isArray(payload.manifest.labs) ||
          !Array.isArray(payload.state?.unlocked_labs)
        ) {
          throw new Error(
            "Runner 返回的课程清单缺少 labs 或 state.unlocked_labs；课程已保持锁定。",
          );
        }
        if (!acceptCourseState(payload.state)) {
          throw new Error(
            "Runner 返回的共享进度身份或更新时间无效；课程已保持锁定。",
          );
        }
        const loadedCourseId = manifestCourseId(payload.manifest);
        let restoredLayout = { ...DEFAULT_LAYOUT_PREFERENCES };
        try {
          restoredLayout = parseLayoutPreferences(
            window.localStorage.getItem(layoutStorageKey(loadedCourseId)),
          );
        } catch {
          // Storage can be unavailable in privacy-restricted browser contexts.
        }
        operationLifecycleRef.current.changeSelection();
        setLayoutPreferences(restoredLayout);
        setLayoutReadyCourseId(loadedCourseId);
        setManifest(payload.manifest);
        setSelectedLabId(payload.manifest.labs[0]?.id ?? "");
        setSelectedQuestionId(payload.manifest.labs[0]?.questions?.[0]?.id ?? "");
        setFileLoading(false);
        setFileLoadFailed(false);
        setConnection("online");
        setNotice("已连接本地 Runner。代码只保存在你的本地工作区。");
      })
      .catch((error) => {
        if (!active) return;
        setConnection("error");
        setNotice(displayError(error));
      });
    return () => {
      active = false;
    };
  }, [acceptCourseState]);

  useEffect(() => {
    if (!manifest) return;
    const polling = createProgressPollController({
      schedule(callback, intervalMs) {
        return window.setInterval(callback, intervalMs);
      },
      cancel(timer) {
        window.clearInterval(timer);
      },
      onPoll() {
        void refreshCourseState();
      },
      intervalMs: 5_000,
    });
    const handleFocus = () => {
      if (shouldPollProgress(document.visibilityState)) {
        void refreshCourseState();
      }
    };
    const handleVisibilityChange = () => {
      if (shouldPollProgress(document.visibilityState)) {
        void refreshCourseState();
      }
      polling.sync(document.visibilityState);
    };
    polling.sync(document.visibilityState);
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      polling.cleanup();
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      stateRefreshRequestRef.current += 1;
    };
  }, [manifest, refreshCourseState]);

  useEffect(() => {
    if (!foundationLabId || selectedLab?.id === foundationLabId) return;
    let active = true;
    void runnerRequest<FoundationKnowledgePayload>(
      `/api/knowledge/${encodeURIComponent(foundationLabId)}`,
    )
      .then((payload) => {
        if (!active) return;
        recordKnowledgeProgress(payload.lab_id, {
          completed: payload.completed,
          mastered: payload.mastered,
          total: payload.total,
        });
      })
      .catch(() => {
        // Keep the gate closed; polling or visiting the foundation retries.
      });
    return () => {
      active = false;
    };
  }, [
    foundationLabId,
    knowledgeRefreshVersion,
    recordKnowledgeProgress,
    selectedLab?.id,
  ]);

  useEffect(() => {
    if (!selectedLab) return;
    let active = true;
    void runnerRequest<CourseContentItem>(
      `/api/content/${encodeURIComponent(selectedLab.id)}`,
    )
      .then((payload) => {
        if (active) setLesson(payload);
      })
      .catch((error) => {
        if (active) {
          setLesson(null);
          setNotice(`讲义加载失败：${displayError(error)}`);
        }
      })
      .finally(() => {
        if (active) setLessonLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedLab]);

  useEffect(() => {
    if (!codingReady || !selectedLab || !selectedQuestion) {
      return;
    }
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setFileLoadFailed(false);
      setFileLoading(true);
    });
    const selection = operationLifecycleRef.current.captureSelection();
    void runnerRequest<FileReadPayload>(
      `/api/file?lab_id=${encodeURIComponent(selectedLab.id)}&question_id=${encodeURIComponent(selectedQuestion.id)}`,
    )
      .then((payload) => {
        if (
          !active ||
          !operationLifecycleRef.current.isSelectionCurrent(selection)
        ) return;
        setFilePath(payload.path);
        setFileLoadFailed(false);
        setSource(draftsRef.current[payload.path] ?? payload.content);
        setLoadedSource(payload.content);
      })
      .catch((error) => {
        if (
          !active ||
          !operationLifecycleRef.current.isSelectionCurrent(selection)
        ) return;
        setFilePath("");
        setFileLoadFailed(true);
        setSource("");
        setLoadedSource("");
        setNotice(`代码加载失败：${displayError(error)}`);
      })
      .finally(() => {
        if (
          active &&
          operationLifecycleRef.current.isSelectionCurrent(selection)
        ) setFileLoading(false);
      });
    return () => {
      active = false;
    };
  }, [codingReady, fileLoadRetryVersion, selectedLab, selectedQuestion]);

  async function saveSource(operation?: OperationToken): Promise<boolean> {
    if (!codingReady) return false;
    if (!selectedLab || !selectedQuestion || !filePath) return false;
    const captured =
      operation ??
      operationLifecycleRef.current.beginOperation({
        labId: selectedLab.id,
        questionId: selectedQuestion.id,
        path: filePath,
        source,
      });
    if (!operationLifecycleRef.current.isOperationCurrent(captured)) return false;
    const needsSave = captured.source !== loadedSource;
    if (!needsSave) return true;
    try {
      const payload = await runnerRequest<FileWritePayload>("/api/file", {
        method: "PUT",
        body: JSON.stringify({
          lab_id: captured.labId,
          question_id: captured.questionId,
          content: captured.source,
        }),
      });
      if (payload.status !== "saved") {
        throw new Error("Runner 没有确认文件已保存。");
      }
      if (!operationLifecycleRef.current.isOperationCurrent(captured)) {
        return false;
      }
      setFilePath(payload.path || captured.path);
      setLoadedSource(captured.source);
      clearSavedDraftIfUnchanged(
        draftsRef.current,
        captured.path,
        captured.source,
      );
      setNotice("代码已保存到本地工作区。");
      return true;
    } catch (error) {
      if (operationLifecycleRef.current.isOperationCurrent(captured)) {
        setNotice(`保存失败：${displayError(error)}`);
      }
      return false;
    }
  }

  async function run(mode: RunMode) {
    if (!codingReady || !selectedLab || !selectedQuestion) return;
    const operation = operationLifecycleRef.current.beginOperation({
      labId: selectedLab.id,
      questionId: selectedQuestion.id,
      path: filePath,
      source,
    });
    setRunning(mode);
    setResult(null);
    setNotice(mode === "public" ? "正在运行公开测试…" : "正在运行提交测试…");
    try {
      if (!(await saveSource(operation))) return;
      if (!operationLifecycleRef.current.isOperationCurrent(operation)) return;
      const payload = await runnerRequest<RunPayload>(
        "/api/run",
        {
          method: "POST",
          body: JSON.stringify({
            lab_id: operation.labId,
            question_id: operation.questionId,
            mode,
          }),
        },
        105_000,
      );
      if (payload.state) acceptCourseState(payload.state);
      if (!operationLifecycleRef.current.isOperationCurrent(operation)) return;
      setResult(payload);
      setNotice(
        payload.passed
          ? mode === "submit"
            ? "提交测试通过，进度已记录。"
            : "公开测试通过。继续检查边界条件后再提交。"
          : "测试未通过；根据输出定位第一个失败。",
      );
    } catch (error) {
      if (operationLifecycleRef.current.isOperationCurrent(operation)) {
        setResult({ passed: false, output: displayError(error) });
        setNotice("Runner 执行失败。");
      }
    } finally {
      if (operationLifecycleRef.current.isOperationCurrent(operation)) {
        setRunning(null);
      }
    }
  }

  if (!manifest) {
    return (
      <main className="boot-screen">
        <div className="boot-card">
          <span className={`status-dot ${connection}`} aria-hidden="true" />
          <p className="eyebrow">COURSEKIT LOCAL</p>
          <h1>{connection === "error" ? "无法连接课程" : "正在载入课程"}</h1>
          <p>{notice}</p>
          {connection === "error" ? (
            <p className="boot-command">
              请在项目根目录运行 <code>npm run learn</code>，然后刷新页面。
            </p>
          ) : null}
        </div>
      </main>
    );
  }

  const readiness = manifest.readiness;
  const preparationTitles = readinessPreparationTitles(readiness);
  const hasAdditionalPreparation = preparationTitles.length > 0;

  return (
    <main
      className={`course-shell${layoutPreferences.sidebarCollapsed ? " sidebar-collapsed" : ""}`}
      style={shellStyle}
    >
      <aside className="course-sidebar" id="course-sidebar">
        <header className="brand-block">
          <span className="brand-mark" aria-hidden="true">CK</span>
          <div className="brand-copy">
            <p className="eyebrow">PYTHON COURSE</p>
            <h1>{manifest.title}</h1>
          </div>
          <button
            type="button"
            className="sidebar-toggle"
            aria-label={layoutPreferences.sidebarCollapsed ? "展开章节导航" : "折叠章节导航"}
            aria-expanded={!layoutPreferences.sidebarCollapsed}
            aria-controls="course-sidebar"
            title={layoutPreferences.sidebarCollapsed ? "展开章节导航" : "折叠章节导航"}
            onClick={() =>
              setLayoutPreferences((current) =>
                current.sidebarCollapsed
                  ? expandSidebar(current)
                  : collapseSidebar(current),
              )
            }
          >
            <span aria-hidden="true">
              {layoutPreferences.sidebarCollapsed ? "›" : "‹"}
            </span>
          </button>
        </header>

        {readiness ? (
          <section className="readiness-summary" aria-labelledby="readiness-title">
            <h2 id="readiness-title">学习准备</h2>
            <h3>课程直接使用</h3>
            <ul>{readiness.assumed.map((title, index) => <li key={`assumed-${index}-${title}`}>{title}</li>)}</ul>
            <h3>
              {hasAdditionalPreparation
                ? readiness.preparatory
                  ? "正式 Lab 前会先讲"
                  : "Lab 00 会先讲"
                : "无需额外先修"}
            </h3>
            {hasAdditionalPreparation ? (
              <ul>{preparationTitles.map((title, index) => <li key={`preparation-${index}-${title}`}>{title}</li>)}</ul>
            ) : (
              <p>完成 Lab 00 导览后即可进入正式 Lab。</p>
            )}
          </section>
        ) : null}

        <nav className="lab-nav" aria-label="课程章节">
          {labs.map((lab, index) => {
            const isSelected = lab.id === selectedLab?.id;
            const isComplete = completed.has(lab.id);
            const isUnlocked = unlocked.has(lab.id);
            return (
              <button
                type="button"
                key={lab.id}
                className={isSelected ? "lab-link selected" : "lab-link"}
                disabled={!isUnlocked}
                aria-label={isUnlocked ? lab.title : `${lab.title}，未解锁`}
                title={isUnlocked ? lab.title : `${lab.title} · 未解锁`}
                onClick={() => {
                  if (!isUnlocked || !shouldChangeLab(selectedLab?.id, lab.id)) return;
                  const firstQuestion = lab.questions?.[0];
                  operationLifecycleRef.current.changeSelection();
                  setSelectedLabId(lab.id);
                  setSelectedQuestionId(firstQuestion?.id ?? "");
                  setFilePath("");
                  setSource("");
                  setLoadedSource("");
                  setResult(null);
                  setRunning(null);
                  setNotice("正在载入所选学习内容…");
                  setLessonLoading(true);
                  setFileLoading(false);
                  setFileLoadFailed(false);
                }}
                aria-current={isSelected ? "page" : undefined}
              >
                <span className="lab-index">
                  {isComplete
                    ? "✓"
                    : /^lab\d+$/.test(lab.id)
                      ? lab.id.slice(3)
                      : String(index + 1).padStart(2, "0")}
                </span>
                <span>
                  <strong>{lab.title}</strong>
                  <small>{isUnlocked ? lab.id : `${lab.id} · 未解锁`}</small>
                  {lab.study_minutes ? (
                    <small>{studyTimeLabel(lab.study_minutes)}</small>
                  ) : null}
                </span>
              </button>
            );
          })}
        </nav>

        <footer className="sidebar-footer">
          {typeof earned === "number" && typeof total === "number" ? (
            <div className="score-line">
              <span>已验证</span>
              <strong>{earned} / {total}</strong>
            </div>
          ) : null}
          <span className="runner-state"><i /> Runner online</span>
        </footer>
      </aside>

      <ResizeSeparator
        className="sidebar-separator"
        label="调整章节导航宽度"
        controls="course-sidebar course-main"
        value={sidebarWidth}
        min={
          layoutPreferences.sidebarCollapsed
            ? SIDEBAR_COLLAPSED_WIDTH
            : SIDEBAR_MIN_WIDTH
        }
        max={
          layoutPreferences.sidebarCollapsed
            ? SIDEBAR_COLLAPSED_WIDTH
            : sidebarMaximum
        }
        disabled={layoutPreferences.sidebarCollapsed}
        onChange={resizeSidebar}
      />

      <section className="course-main" id="course-main">
        <header className="course-toolbar">
          <div>
            <p className="eyebrow">{selectedLab?.id ?? "LAB"}</p>
            <h2>{selectedLab?.title ?? "选择一个 Lab"}</h2>
          </div>
          <p className="course-summary">
            {selectedLab?.description ?? manifest.description ?? manifest.project ?? capstoneSummary(manifest.capstone)}
          </p>
          {selectedLab?.study_minutes ? (
            <p className="selected-study-time">
              <strong>预计学习时间：{studyTimeLabel(selectedLab.study_minutes)}</strong>
              {selectedLab.study_minutes.reason ? ` · ${selectedLab.study_minutes.reason}` : null}
            </p>
          ) : null}
        </header>

        <div
          className={`learning-grid${codingReady ? " coding-visible" : " lesson-only"}`}
          ref={learningGridRef}
          style={learningGridStyle}
        >
          <section
            className="panel lesson-panel"
            id="lesson-panel"
            aria-label="课程讲义"
          >
            <div className="panel-heading">
              <span>LEARN</span>
              <small>{lessonLoading ? "正在加载…" : "定义 · 原理 · 示例"}</small>
            </div>
            <div className="panel-scroll lesson-scroll">
              {lesson ? (
                <CourseLesson content={lesson} onPractice={handlePractice} />
              ) : (
                <p className="empty-copy">这个 Lab 暂时没有可用讲义。</p>
              )}
              {selectedLab ? (
                <div
                  id={`knowledge-check-${selectedLab.id}`}
                  className="knowledge-check-target"
                  tabIndex={-1}
                >
                  <KnowledgeCheck
                    key={selectedLab.id}
                    labId={selectedLab.id}
                    refreshVersion={knowledgeRefreshVersion}
                    onProgressChange={recordKnowledgeProgress}
                    onStateChange={acceptCourseState}
                  />
                </div>
              ) : null}
            </div>
          </section>

          {codingReady ? (
            <>
              <ResizeSeparator
                className="workspace-separator"
                label="调整讲义与编码区宽度"
                controls="lesson-panel work-column"
                value={lessonWidth}
                min={LESSON_MIN_WIDTH}
                max={lessonMaximum}
                onChange={resizeLesson}
              />
              <section
                className="work-column"
                id="work-column"
                tabIndex={-1}
                aria-label="编码与测试"
              >
            <div className="panel code-panel">
              <div className="panel-heading code-heading">
                <div>
                  <span>CODE</span>
                  <small>{filePath || "未选择文件"}</small>
                </div>
                <label>
                  <span className="sr-only">选择练习</span>
                  <select
                    value={selectedQuestion?.id ?? ""}
                    onChange={(event) => {
                      operationLifecycleRef.current.changeSelection();
                      setSelectedQuestionId(event.target.value);
                      setResult(null);
                      setRunning(null);
                      setNotice("正在载入所选练习…");
                      setFileLoading(true);
                      setFileLoadFailed(false);
                    }}
                    disabled={
                      !codingReady ||
                      !questions.length ||
                      running !== null ||
                      selectedFileLoading
                    }
                    aria-describedby={codingReady ? undefined : codingLockReasonId}
                  >
                    {questions.map((question) => (
                      <option value={question.id} key={question.id}>
                        {question.title}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {selectedQuestion ? (
                <div className="question-brief">
                  <div>
                    <strong>{selectedQuestion.title}</strong>
                    <p>{selectedQuestion.prompt ?? `补全 ${selectedQuestion.symbol ?? selectedQuestion.id}。`}</p>
                  </div>
                  {typeof selectedQuestion.points === "number" ? (
                    <span>{selectedQuestion.points} pts</span>
                  ) : null}
                </div>
              ) : (
                <p className="empty-copy question-empty">本章没有编码题。</p>
              )}

              {selectedQuestion?.example ? (
                <details className="example-disclosure">
                  <summary>查看示例与解释</summary>
                  <dl>
                    {selectedQuestion.example.input ? (
                      <><dt>输入</dt><dd><code>{selectedQuestion.example.input}</code></dd></>
                    ) : null}
                    {selectedQuestion.example.output ? (
                      <><dt>输出</dt><dd><code>{selectedQuestion.example.output}</code></dd></>
                    ) : null}
                    {selectedQuestion.example.explanation ? (
                      <><dt>解释</dt><dd>{selectedQuestion.example.explanation}</dd></>
                    ) : null}
                  </dl>
                </details>
              ) : null}

              <div className="editor-frame" aria-busy={selectedFileLoading}>
                {selectedFilePending ? (
                  <div className="editor-loading">
                    <span>
                      {fileLoadFailed
                        ? "代码读取失败，编辑器保持锁定。"
                        : "正在读取本地文件…"}
                    </span>
                    {fileLoadFailed ? (
                      <button
                        type="button"
                        onClick={() => {
                          setNotice("正在重新读取代码文件…");
                          setFileLoadRetryVersion((value) => value + 1);
                        }}
                      >
                        重试读取
                      </button>
                    ) : null}
                  </div>
                ) : null}
                <PythonCodeEditor
                  value={source}
                  documentKey={filePath || selectedQuestion?.id || "empty"}
                  editable={
                    connection === "online" &&
                    Boolean(selectedQuestion) &&
                    selectedFileReady
                  }
                  onChange={(value) => {
                    setSource(value);
                    if (filePath) draftsRef.current[filePath] = value;
                  }}
                  ariaLabel={`${selectedQuestion?.title ?? "Python"} 代码编辑器`}
                />
              </div>

              <div className="action-bar">
                <div className="action-meta">
                  <span className={dirty ? "save-state dirty" : "save-state"}>
                    {dirty ? "未保存" : "已同步"}
                  </span>
                  {codingLockReason ? (
                    <span className="coding-lock-reason" id={codingLockReasonId}>
                      {codingLockReason}
                    </span>
                  ) : null}
                </div>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => void run("public")}
                  disabled={
                    !codingReady ||
                    !selectedQuestion ||
                    running !== null ||
                    !selectedFileReady
                  }
                  aria-describedby={codingReady ? undefined : codingLockReasonId}
                >
                  {running === "public" ? "运行中…" : "运行公开测试"}
                </button>
                <button
                  type="button"
                  className="button primary"
                  onClick={() => void run("submit")}
                  disabled={
                    !codingReady ||
                    !selectedQuestion ||
                    running !== null ||
                    !selectedFileReady
                  }
                  aria-describedby={codingReady ? undefined : codingLockReasonId}
                >
                  {running === "submit" ? "提交中…" : "提交评分"}
                </button>
              </div>
            </div>

            <div className="panel result-panel" aria-live="polite">
              <div className="panel-heading">
                <span>RESULT</span>
                <small className={result?.passed ? "result-pass" : result ? "result-fail" : ""}>
                  {result ? (result.passed ? "PASSED" : "FAILED") : "等待运行"}
                </small>
              </div>
              <div className="result-body">
                <p className="notice">{notice}</p>
                {result?.output ? <pre className="test-output">{result.output}</pre> : null}
              </div>
            </div>
              </section>
            </>
          ) : null}
        </div>
      </section>
    </main>
  );
}
