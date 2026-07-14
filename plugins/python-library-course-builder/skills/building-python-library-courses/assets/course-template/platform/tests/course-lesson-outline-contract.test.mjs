import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const lessonUrl = new URL("../app/CourseLesson.tsx", import.meta.url);
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
  assert.match(openCore, /example\.trace/);
  assert.match(openCore, /step\.input_state/);
  assert.match(openCore, /step\.operation/);
  assert.match(openCore, /step\.output_state/);

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
});
