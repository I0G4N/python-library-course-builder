import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const lessonUrl = new URL("../app/CourseLesson.tsx", import.meta.url);
const appUrl = new URL("../app/CourseKitApp.tsx", import.meta.url);
const cssUrl = new URL("../app/globals.css", import.meta.url);

test("structured lessons keep a Markdown fallback and render the beginner core first", async () => {
  const lesson = await readFile(lessonUrl, "utf8");

  assert.match(lesson, /lesson_outline\?: LessonOutline/);
  assert.match(lesson, /content\.lesson_outline/);
  assert.match(lesson, /学习前先确认/);
  assert.match(lesson, /本章要解决的问题/);
  assert.match(lesson, /学完你将能够/);
  assert.match(lesson, /content\.lesson\)/);
});

test("principles, design choices, and troubleshooting use accessible native disclosure", async () => {
  const [lesson, css] = await Promise.all([
    readFile(lessonUrl, "utf8"),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(lesson, /<details[^>]*className="lesson-deep-dive"/);
  assert.match(lesson, /<summary>/);
  assert.match(lesson, /深入原理与设计取舍/);
  assert.match(lesson, /错误现象、原因与修复/);
  assert.match(lesson, /<PythonCodeBlock[\s\S]*wrong_code/);
  assert.match(lesson, /<PythonCodeBlock[\s\S]*fix_code/);
  assert.match(css, /\.lesson-deep-dive/);
  assert.match(css, /\.lesson-diagnostic/);
});

test("runnable lesson examples expose commands and expected output before coding unlock", async () => {
  const lesson = await readFile(lessonUrl, "utf8");

  assert.match(lesson, /example\.kind === "runnable"/);
  assert.match(lesson, /example\.command/);
  assert.match(lesson, /example\.expected_output/);
  assert.match(lesson, /讲义可运行示例/);
});

test("core concept definitions stay visible before the closed deep dive", async () => {
  const lesson = await readFile(lessonUrl, "utf8");

  const overview = lesson.indexOf('className="lesson-concept-overview"');
  const deepDive = lesson.indexOf('<details className="lesson-deep-dive">');
  assert.ok(overview >= 0, "the open beginner core must render concept definitions");
  assert.ok(deepDive >= 0, "the lesson must retain a native deep-dive disclosure");
  assert.ok(overview < deepDive, "definitions must appear before the closed disclosure");
  assert.match(lesson.slice(overview, deepDive), /concept\.definition/);
  assert.match(lesson.slice(overview, deepDive), /concept\.purpose/);
});

test("plain contract and concrete trace precede the closed deep dive with learner labels", async () => {
  const lesson = await readFile(lessonUrl, "utf8");

  const deepDive = lesson.indexOf('<details className="lesson-deep-dive">');
  assert.ok(deepDive >= 0, "the lesson must retain a native deep-dive disclosure");

  const openCore = lesson.slice(0, deepDive);
  for (const label of [
    "先这样理解",
    "输入和输出是什么",
    "拿一个具体输入走一遍",
  ]) {
    const position = lesson.indexOf(label);
    assert.ok(position >= 0, `missing learner-visible label: ${label}`);
    assert.ok(position < deepDive, `${label} must appear before the closed disclosure`);
  }

  assert.match(openCore, /concept\.mental_model/);
  assert.match(openCore, /concept\.operational_contract/);
  assert.match(openCore, /operational_contract\.inputs/);
  assert.match(openCore, /operational_contract\.outputs/);
  assert.match(openCore, /operational_contract\.forms/);
  assert.match(openCore, /operational_contract\.effects/);
  assert.match(openCore, /operational_contract\.failure_modes/);
  assert.match(openCore, /input\.form/);
  assert.match(openCore, /input\.example/);
  assert.match(openCore, /input\.constraints/);
  assert.match(openCore, /output\.form/);
  assert.match(openCore, /output\.example/);
  assert.match(openCore, /failure\.condition/);
  assert.match(openCore, /failure\.observable/);
  assert.match(openCore, /failure\.recovery/);
  assert.match(openCore, /example\.trace/);
  assert.match(openCore, /step\.input_state/);
  assert.match(openCore, /step\.operation/);
  assert.match(openCore, /step\.output_state/);
  assert.match(openCore, /step\.explanation/);

  assert.doesNotMatch(lesson, /心智模型：/);
  assert.doesNotMatch(lesson, /机制：一步一步发生什么/);
  assert.doesNotMatch(lesson, /始终成立的约束/);
});

test("structured foundation source payloads render as safe official links", async () => {
  const lesson = await readFile(lessonUrl, "utf8");

  assert.match(lesson, /sources\?: Array<\{ id: string; title: string; url: string \}>/);
  assert.match(lesson, /content\.sources\?\.length/);
  assert.match(lesson, /href=\{source\.url\}/);
  assert.match(lesson, /target="_blank" rel="noopener noreferrer"/);
  assert.match(lesson, /<details[^>]*className="source-list"/);
});

test("content types and concept cards expose study time and first-practice actions", async () => {
  const lesson = await readFile(lessonUrl, "utf8");

  assert.match(lesson, /type OperationalContractKind =\s*[\s\S]*"api"[\s\S]*"mechanism"[\s\S]*"formula"[\s\S]*"lifecycle"[\s\S]*"data-model"/);
  const inputType = lesson.slice(
    lesson.indexOf("type OperationalInput ="),
    lesson.indexOf("type OperationalOutput ="),
  );
  const outputType = lesson.slice(
    lesson.indexOf("type OperationalOutput ="),
    lesson.indexOf("type OperationalFailure ="),
  );
  assert.match(inputType, /constraints: string\[\]/);
  assert.doesNotMatch(inputType, /constraints\?:/);
  assert.doesNotMatch(outputType, /constraints/);
  assert.match(lesson, /kind: OperationalContractKind/);
  assert.match(lesson, /export type StudyMinutes/);
  assert.match(lesson, /tier: "standard"; min: 30; max: 45; reason\?: never/);
  assert.match(lesson, /tier: "foundation" \| "extended"; min: 45; max: 60; reason: string/);
  assert.match(lesson, /export type PracticeLink/);
  assert.match(lesson, /study_minutes\?: StudyMinutes/);
  assert.match(lesson, /practice_links\?: PracticeLink\[\]/);
  assert.match(lesson, /onPractice\?: \(link: PracticeLink\) => void/);
  assert.match(lesson, /practiceLinksByConcept/);
  assert.match(lesson, /type="button"[\s\S]*onClick=\{\(\) => onPractice\?\.\(practice\)\}/);
  assert.match(lesson, /先做这个练习/);
  assert.match(lesson, /预计学习时间/);
});

test("course shell renders readiness and routes practice to stable targets", async () => {
  const [app, css] = await Promise.all([
    readFile(appUrl, "utf8"),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(app, /readiness\?: \{\s*assumed: string\[\];\s*foundation: string\[\]/);
  assert.match(app, /study_minutes\?: StudyMinutes/);
  assert.match(app, /manifest\.readiness/);
  assert.match(app, /readiness\.assumed\.map/);
  assert.match(app, /readiness\.foundation\.map/);
  assert.match(app, /lab\.study_minutes/);
  assert.match(app, /selectedLab\?\.study_minutes/);
  assert.match(app, /handlePractice/);
  assert.match(app, /link\.kind === "coding-question"/);
  assert.match(app, /setSelectedQuestionId\(link\.item_id\)/);
  assert.match(app, /codingReady \? "work-column"/);
  assert.match(app, /scrollIntoView/);
  assert.match(app, /id=\{`knowledge-check-\$\{selectedLab\.id\}`\}/);
  assert.match(app, /className="work-column"[\s\S]*id="work-column"[\s\S]*tabIndex=\{-1\}/);
  assert.match(app, /<CourseLesson content=\{lesson\} onPractice=\{handlePractice\}/);
  const practiceStart = app.indexOf("const handlePractice");
  const practiceEnd = app.indexOf("const dirty", practiceStart);
  const practiceHandler = app.slice(practiceStart, practiceEnd);
  assert.match(practiceHandler, /setFileLoading\(codingReady\)/);
  assert.match(practiceHandler, /setFileLoadFailed\(false\)/);
  assert.match(practiceHandler, /setFileLoadRetryVersion/);
  assert.match(app, /readiness\.assumed\.map\(\(title, index\)/);
  assert.match(app, /readiness\.foundation\.map\(\(title, index\)/);
  assert.match(css, /\.readiness-summary/);
  assert.match(css, /\.sidebar-collapsed \.readiness-summary/);
  assert.match(css, /\.practice-action/);
});
