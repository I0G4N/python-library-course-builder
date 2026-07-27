import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = (path) =>
  readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("v4 lesson surface is free-form Markdown plus explicit terms", async () => {
  const [lesson, guide] = await Promise.all([
    source("CourseLesson.tsx"),
    source("lessonGuide.mjs"),
  ]);

  assert.match(lesson, /lesson: string/);
  assert.match(lesson, /terms\?: LessonTerm\[\]/);
  assert.match(lesson, /extractTutorialHeadings\(content\.lesson\)/);
  assert.match(lesson, /normalizeLessonTerms\(content\.terms\)/);
  assert.match(lesson, /markdownBlocks\(content\.lesson, t\)/);
  assert.match(lesson, /const practice = content\.practice_links\?\.\[0\]/);
  assert.match(lesson, /onClick=\{\(\) => onPractice\?\.\(practice\)\}/);
  assert.doesNotMatch(lesson, /lesson_outline|StructuredLesson|ConceptDeepDive/);
  assert.doesNotMatch(guide, /concepts|operational_contract|outcomes/);
});

test("v4 Vite shell reuses interaction components without a Node Web runtime", async () => {
  const [configuration, main, manifest, index] = await Promise.all([
    source("vite.config.ts"),
    source("main.tsx"),
    source("package.json"),
    source("index.html"),
  ]);
  const packageJson = JSON.parse(manifest);

  assert.match(main, /CourseKitApp/);
  assert.match(main, /@legacy\/globals\.css/);
  assert.match(configuration, /coursekit-v4-same-origin/);
  assert.match(configuration, /source === "\.\/CourseLesson"/);
  assert.match(configuration, /source === "\.\/courseLocale\.mjs"/);
  assert.match(configuration, /courseLocaleV4\.mjs/);
  assert.match(configuration, /const RUNNER_URL = ""/);
  assert.match(configuration, /document\.documentElement\.lang/);
  assert.match(configuration, /replaceAll\("npm run learn", "uv run course"\)/);
  assert.match(configuration, /coursekit_runtime\/static/);
  assert.equal(packageJson.dependencies.react, "19.2.6");
  assert.equal(packageJson.dependencies["@codemirror/view"], "6.43.6");
  assert.equal(packageJson.dependencies.next, undefined);
  assert.equal(packageJson.dependencies.vinext, undefined);
  assert.equal(packageJson.dependencies["drizzle-orm"], undefined);
  assert.match(index, /<html lang="__COURSEKIT_LANGUAGE__">/);
});

test("lesson math uses pinned local KaTeX with fail-soft untrusted rendering", async () => {
  const [lesson, main, manifest] = await Promise.all([
    source("CourseLesson.tsx"),
    source("main.tsx"),
    source("package.json"),
  ]);
  const packageJson = JSON.parse(manifest);

  assert.equal(packageJson.dependencies.katex, "0.18.1");
  assert.match(main, /import\s+["']katex\/dist\/katex\.min\.css["'];?/);
  assert.match(lesson, /from\s+["']katex["']/);
  assert.match(lesson, /katex\.renderToString\(/);
  assert.match(lesson, /displayMode/);
  assert.match(lesson, /throwOnError:\s*false/);
  assert.match(lesson, /trust:\s*false/);
  assert.match(lesson, /output:\s*["']htmlAndMathml["']/);
  assert.match(lesson, /dangerouslySetInnerHTML/);
  assert.doesNotMatch(
    `${main}\n${lesson}`,
    /(?:cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|unpkg\.com)/i,
  );
});

test("shared CI owns the real-browser matrix instead of generated courses", async () => {
  const [configuration, scenario, manifest] = await Promise.all([
    source("playwright.config.ts"),
    source("e2e/course-runtime.spec.ts"),
    source("package.json"),
  ]);
  const packageJson = JSON.parse(manifest);

  assert.match(configuration, /name: "chromium"/);
  assert.match(configuration, /name: "firefox"/);
  assert.match(configuration, /name: "webkit"/);
  assert.match(configuration, /npm run preview/);
  assert.equal(packageJson.devDependencies["@playwright/test"], "1.62.0");
  assert.equal(packageJson.scripts["test:browser"], "playwright test");

  assert.match(scenario, /page\.route\("\*\*\/api\/\*\*"/);
  assert.match(scenario, /A freely-shaped opening/);
  assert.match(scenario, /Control token/);
  assert.match(scenario, /Knowledge check/);
  assert.match(scenario, /Implement normalize code editor/);
  assert.match(scenario, /Run public tests/);
  assert.match(scenario, /Submit for grading/);
  assert.match(scenario, /server progress survives a real page reload/);
  assert.match(scenario, /three columns/);
});
