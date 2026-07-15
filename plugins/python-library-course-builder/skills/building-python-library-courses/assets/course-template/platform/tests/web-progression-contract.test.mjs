import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appUrl = new URL("../app/CourseKitApp.tsx", import.meta.url);
const knowledgeUrl = new URL("../app/KnowledgeCheck.tsx", import.meta.url);
const lifecycleUrl = new URL("../app/progressionLifecycle.mjs", import.meta.url);
const cssUrl = new URL("../app/globals.css", import.meta.url);

async function readSource(url) {
  try {
    return await readFile(url, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") return "";
    throw error;
  }
}

test("knowledge checks use learner-safe APIs and accessible, retryable controls", async () => {
  const [knowledge, lifecycle] = await Promise.all([
    readSource(knowledgeUrl),
    readSource(lifecycleUrl),
  ]);

  assert.match(knowledge, /\/api\/knowledge\/\$\{encodeURIComponent\(labId\)\}/);
  assert.match(lifecycle, /"\/api\/knowledge\/answer"/);
  assert.match(knowledge, /<fieldset/);
  assert.match(knowledge, /<legend/);
  assert.match(knowledge, /type="radio"/);
  assert.match(knowledge, /choice_id: selectedChoice/);
  assert.match(knowledge, /feedback\.explanation/);
  assert.match(knowledge, /question\.kind === "execution_trace"/);
  assert.match(knowledge, /t\.executionTrace/);
  assert.match(knowledge, /t\.diagnosticAnalysis/);
  assert.match(knowledge, /knowledge\.available/);
  assert.match(knowledge, /knowledge\.completed/);
  assert.match(knowledge, /knowledge\.mastered/);
  assert.match(knowledge, /knowledge\.total/);
  assert.match(knowledge, /requestGenerationRef/);
  assert.match(knowledge, /controller\.abort\(\)/);
  assert.match(knowledge, /knowledgeRefreshLifecycleRef/);
  assert.match(
    knowledge,
    /\[\s*labId,\s*language,\s*onProgressChange,\s*queuedRefreshVersion,\s*refreshVersion,\s*retryVersion,?\s*\]/,
  );
  assert.doesNotMatch(
    knowledge,
    /\[labId, onProgressChange, refreshVersion, retryVersion, submittingQuestionId\]/,
  );
  assert.match(knowledge, /const \[loadError, setLoadError\]/);
  assert.match(knowledge, /const \[submitError, setSubmitError\]/);
  assert.match(knowledge, /const \[failedSubmission, setFailedSubmission\]/);
  assert.match(knowledge, /createKnowledgeAnswerPost/);
  assert.match(knowledge, /createKnowledgeRefreshLifecycle/);
  assert.match(knowledge, /resolveKnowledgeAnswerFreshness/);
  assert.match(knowledge, /retryFailedPost\(failedSubmission\)/);
  assert.match(
    knowledge,
    /runnerRequest<KnowledgeAnswerPayload>\(\s*submission\.path,\s*t,\s*\{\s*method: submission\.method,[\s\S]*?body: submission\.body/,
  );
  assert.match(lifecycle, /KNOWLEDGE_ANSWER_PATH = "\/api\/knowledge\/answer"/);
  assert.match(lifecycle, /path: KNOWLEDGE_ANSWER_PATH/);
  assert.match(lifecycle, /method: "POST"/);
  assert.match(knowledge, /t\.runnerRequestFailed/);
  assert.match(knowledge, /\{t\.reload\}/);
  assert.match(knowledge, /\{t\.retrySubmit\}/);
  assert.match(knowledge, /onProgressChange/);
  assert.match(
    knowledge,
    /onStateChange: \(state: SharedCourseState\) => boolean/,
  );

  const submitStart = knowledge.indexOf(
    "const payload = await runnerRequest<KnowledgeAnswerPayload>",
  );
  const submitEnd = knowledge.indexOf("} catch (requestError)", submitStart);
  assert.notEqual(submitStart, -1, "answer submit block must exist");
  assert.notEqual(submitEnd, -1, "answer submit block must be bounded");
  const submitSuccess = knowledge.slice(submitStart, submitEnd);
  const resolveFreshness = submitSuccess.indexOf(
    "resolveKnowledgeAnswerFreshness",
  );
  const setFeedback = submitSuccess.indexOf("setFeedbackByQuestion");
  const freshnessGate = submitSuccess.indexOf(
    "if (!freshness.stateAccepted) return;",
  );
  const setKnowledge = submitSuccess.indexOf("setKnowledge(payload.knowledge)");
  const setProgress = submitSuccess.indexOf("onProgressChange(");
  assert.ok(resolveFreshness >= 0, "answer state must be arbitrated first");
  assert.ok(
    setFeedback > resolveFreshness && setFeedback < freshnessGate,
    "current answer feedback must render outside the shared-state gate",
  );
  assert.ok(
    freshnessGate > setFeedback &&
      setKnowledge > freshnessGate &&
      setProgress > freshnessGate,
    "rejected answer state must block knowledge and mastery mutation",
  );
  assert.match(knowledge, /knowledgeRefreshLifecycleRef\.current\.finishSubmit\(\)/);
  assert.match(knowledge, /setQueuedRefreshVersion\(\(value\) => value \+ 1\)/);
});

test("course navigation and coding controls fail closed around shared progression", async () => {
  const [app, css] = await Promise.all([
    readFile(appUrl, "utf8"),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(app, /Array\.isArray\(payload\.state\?\.unlocked_labs\)/);
  assert.match(app, /new Set\(courseState\.unlocked_labs \?\? \[\]\)/);
  assert.doesNotMatch(app, /courseState\.unlocked_labs \?\? labs\.map/);
  assert.match(app, /const foundationLabId = labs\[0\]\?\.id \?\? ""/);
  assert.match(app, /unit_type\?: CourseUnitType/);
  assert.match(app, /graded\?: boolean/);
  assert.match(app, /isCodingUnit\(\{/);
  assert.match(app, /unitType: selectedLab\.unit_type/);
  assert.match(app, /graded: selectedLab\.graded/);
  assert.doesNotMatch(app, /selectedLab && selectedLab\.id !== foundationLabId/);
  assert.match(app, /disabled=\{!isUnlocked\}/);
  assert.match(app, /t\.lockedLab/);
  assert.match(app, /aria-label=\{isUnlocked \? lab\.title : t\.lockedLab\(lab\.title\)\}/);
  assert.match(app, /title=\{isUnlocked \? lab\.title : t\.lockedLabTitle\(lab\.title\)\}/);
  assert.match(css, /\.lab-link:disabled small\s*\{[^}]*display: block/);
  assert.match(css, /\.coding-lock-reason\s*\{[^}]*white-space: normal/);
  assert.doesNotMatch(css, /\.coding-lock-reason\s*\{[^}]*white-space: nowrap/);
  assert.match(
    app,
    /const codingReady =[\s\S]*codingUnitSelected[\s\S]*selectedLabNavigable[\s\S]*foundationKnowledgeComplete[\s\S]*currentKnowledgeComplete/,
  );
  assert.match(app, /editable=\{[\s\S]*codingReady[\s\S]*\}/);
  assert.match(app, /aria-describedby=\{codingReady \? undefined : codingLockReasonId\}/);
  assert.match(app, /async function saveSource\([^)]*\): Promise<boolean> \{\s*if \(!codingReady\) return false/);
  assert.match(app, /async function run\(mode: RunMode\) \{\s*if \(!codingReady/);
  assert.match(app, /<KnowledgeCheck[\s\S]*labId=\{selectedLab\.id\}/);
  assert.match(app, /operationLifecycleRef/);
  assert.match(app, /changeSelection\(\)/);
  assert.match(app, /isSelectionCurrent/);
  assert.match(app, /isOperationCurrent/);

  const labClickStart = app.indexOf("onClick={() => {", app.indexOf("lab-nav"));
  const labClickEnd = app.indexOf("}}", labClickStart);
  assert.notEqual(labClickStart, -1, "Lab navigation must define a click handler");
  assert.notEqual(labClickEnd, -1, "Lab navigation click handler must be bounded");
  const labClick = app.slice(labClickStart, labClickEnd);
  const noOpGuard = labClick.indexOf(
    "if (!isUnlocked || !shouldChangeLab(selectedLab?.id, lab.id)) return;",
  );
  const invalidateSelection = labClick.indexOf(
    "operationLifecycleRef.current.changeSelection()",
  );
  assert.notEqual(noOpGuard, -1, "selected-Lab clicks must return without mutation");
  assert.ok(
    noOpGuard < invalidateSelection,
    "selected-Lab no-op guard must precede lifecycle invalidation and loading resets",
  );
});

test("shared state refresh is visible-only and does not replace learner workspace state", async () => {
  const app = await readFile(appUrl, "utf8");
  const acceptStart = app.indexOf("const acceptCourseState");
  const acceptEnd = app.indexOf("\n\n  const recordKnowledgeProgress", acceptStart);
  const refreshStart = app.indexOf("async function refreshCourseState");
  const refreshEnd = app.indexOf("\n  useEffect", refreshStart);
  assert.notEqual(refreshStart, -1, "CourseKitApp must define refreshCourseState");
  assert.notEqual(refreshEnd, -1, "refreshCourseState must remain a focused helper");
  assert.notEqual(acceptStart, -1, "CourseKitApp must validate shared state");
  assert.notEqual(acceptEnd, -1, "shared-state validation must remain focused");
  const acceptBody = app.slice(acceptStart, acceptEnd);
  const refreshBody = app.slice(refreshStart, refreshEnd);

  assert.match(acceptBody, /stateArbiterRef\.current\.accept\(state\)/);
  assert.doesNotMatch(acceptBody, /stateRefreshRequestRef\.current \+= 1/);
  assert.match(refreshBody, /runnerRequest<CourseState>\("\/api\/state", t\)/);
  assert.match(refreshBody, /acceptCourseState\(payload\)/);
  assert.match(refreshBody, /setKnowledgeRefreshVersion/);
  assert.doesNotMatch(
    refreshBody,
    /setSelectedLabId|setSelectedQuestionId|setSource|setLoadedSource|setResult|draftsRef/,
  );
  assert.match(app, /shouldPollProgress\(document\.visibilityState\)/);
  assert.match(app, /createProgressPollController/);
  assert.match(app, /polling\.sync\(document\.visibilityState\)/);
  assert.match(app, /polling\.cleanup\(\)/);
  assert.match(app, /window\.setInterval\([\s\S]*5_000/);
  assert.match(app, /window\.addEventListener\("focus"/);
  assert.match(app, /document\.addEventListener\("visibilitychange"/);
  assert.match(app, /refreshVersion=\{knowledgeRefreshVersion\}/);
  assert.match(
    app,
    /runnerRequest<FoundationKnowledgePayload>\(\s*`\/api\/knowledge\/\$\{encodeURIComponent\(foundationLabId\)\}`/,
  );
  assert.match(app, /if \(payload\.state\) acceptCourseState\(payload\.state\)/);
});

test("Web progression stays generic across generated course sizes and subjects", async () => {
  const [app, knowledge] = await Promise.all([
    readFile(appUrl, "utf8"),
    readSource(knowledgeUrl),
  ]);
  const source = `${app}\n${knowledge}`;

  assert.doesNotMatch(source, /lab00|lab12|ThreadEval|Concurrency(?:Lab)/);
  assert.doesNotMatch(source, /labs\.length\s*[!=<>]=?\s*\d+/);
});
