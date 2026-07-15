import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  COURSE_COPY,
  STATIC_COURSE_LANGUAGE,
  SUPPORTED_COURSE_LANGUAGES,
  courseCopy,
  resolveCourseLanguage,
} from "../app/courseLocale.mjs";

test("runtime locale resolution preserves legacy courses and closes v3", () => {
  assert.deepEqual(SUPPORTED_COURSE_LANGUAGES, ["zh-CN", "en"]);
  const expectedStaticLanguage =
    "__COURSEKIT_LANGUAGE__" === "en" ? "en" : "zh-CN";
  assert.equal(STATIC_COURSE_LANGUAGE, expectedStaticLanguage);
  assert.equal(resolveCourseLanguage(2, undefined), "zh-CN");
  assert.equal(resolveCourseLanguage(undefined, undefined), "zh-CN");
  assert.equal(resolveCourseLanguage(2, "legacy-custom-language"), "zh-CN");
  assert.equal(resolveCourseLanguage(3, "zh-CN"), "zh-CN");
  assert.equal(resolveCourseLanguage(3, "en"), "en");
  assert.throws(() => resolveCourseLanguage(3, undefined), /language/);
  assert.throws(() => resolveCourseLanguage(3, "fr"), /language/);
  for (const invalidSchema of [null, true, "3", 1, 4]) {
    assert.throws(
      () => resolveCourseLanguage(invalidSchema, "en"),
      /schema_version/,
    );
  }
});

test("zh-CN and en expose the same complete runtime catalog", () => {
  assert.deepEqual(
    Object.keys(COURSE_COPY.en).sort(),
    Object.keys(COURSE_COPY["zh-CN"]).sort(),
  );
  assert.equal(courseCopy("zh-CN").knowledgeCheck, "知识检查");
  assert.equal(courseCopy("en").knowledgeCheck, "Knowledge check");
  assert.equal(courseCopy("zh-CN").studyMinutes(15, 30), "15–30 分钟");
  assert.equal(courseCopy("en").studyMinutes(15, 30), "15–30 minutes");
  assert.equal(courseCopy("en").lockedLab("lab01"), "lab01 is locked");
  assert.equal(courseCopy("zh-CN").lockedLab("lab01"), "lab01，未解锁");
});

test("the generated static locale drives the first paint and html lang", async () => {
  const [app, layout, locale] = await Promise.all([
    readFile(new URL("../app/CourseKitApp.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/courseLocale.mjs", import.meta.url), "utf8"),
  ]);

  assert.match(locale, /"__COURSEKIT_LANGUAGE__"/);
  assert.match(app, /useState<CourseLanguage>\(STATIC_COURSE_LANGUAGE\)/);
  assert.match(app, /courseCopy\(STATIC_COURSE_LANGUAGE\)\.connectingRunner/);
  assert.match(layout, /<html lang=\{STATIC_COURSE_LANGUAGE\}/);
  assert.match(app, /document\.documentElement\.lang = courseLanguage/);
});

test("learner-visible Web chrome comes from the locale catalog", async () => {
  const [app, knowledge, lesson] = await Promise.all([
    readFile(new URL("../app/CourseKitApp.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/KnowledgeCheck.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/CourseLesson.tsx", import.meta.url), "utf8"),
  ]);

  for (const key of [
    "localCourseLabel",
    "pythonCourseLabel",
    "learnLabel",
    "codeLabel",
    "resultLabel",
    "passedLabel",
    "failedLabel",
  ]) {
    assert.match(app, new RegExp(`t\\.${key}`));
  }
  assert.match(knowledge, /t\.checkLabel/);
  assert.match(lesson, /t\.capstoneLabel/);
  assert.doesNotMatch(app, />LEARN<|>CODE<|>RESULT<|"PASSED"|"FAILED"/);
  assert.doesNotMatch(knowledge, />CHECK</);
  assert.doesNotMatch(lesson, />CAPSTONE</);
});
