import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appUrl = new URL("../app/CourseKitApp.tsx", import.meta.url);
const separatorUrl = new URL("../app/ResizeSeparator.tsx", import.meta.url);
const cssUrl = new URL("../app/globals.css", import.meta.url);

async function readSource(url) {
  try {
    return await readFile(url, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") return "";
    throw error;
  }
}

test("Lab00 and quiz-locked Labs do not mount or preload the coding workspace", async () => {
  const app = await readFile(appUrl, "utf8");

  assert.match(app, /const codingReady = shouldShowCodingWorkspace\(/);
  assert.match(app, /\{codingReady \? \([\s\S]*className="work-column"[\s\S]*\) : null\}/);
  assert.match(
    app,
    /useEffect\(\(\) => \{\s*if \(!codingReady \|\| !selectedLab \|\| !selectedQuestion\) \{[\s\S]*return;[\s\S]*?runnerRequest<FileReadPayload>/,
  );
  assert.match(
    app,
    /`\/api\/file\?lab_id=\$\{encodeURIComponent\(selectedLab\.id\)\}&question_id=\$\{encodeURIComponent\(selectedQuestion\.id\)\}`/,
  );
  assert.match(
    app,
    /\}, \[codingReady, fileLoadRetryVersion, selectedLab, selectedQuestion\]\);/,
  );
});

test("desktop columns use two native accessible vertical separators", async () => {
  const [app, separator, css] = await Promise.all([
    readFile(appUrl, "utf8"),
    readSource(separatorUrl),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(app, /<ResizeSeparator[\s\S]*label="调整章节导航宽度"/);
  assert.match(app, /<ResizeSeparator[\s\S]*label="调整讲义与编码区宽度"/);
  assert.match(separator, /role="separator"/);
  assert.match(separator, /aria-orientation="vertical"/);
  assert.match(separator, /aria-valuemin=\{min\}/);
  assert.match(separator, /aria-valuemax=\{max\}/);
  assert.match(separator, /aria-valuenow=\{Math\.round\(value\)\}/);
  assert.match(separator, /aria-disabled=\{disabled \|\| undefined\}/);
  assert.match(separator, /tabIndex=\{disabled \? -1 : 0\}/);
  assert.match(separator, /onPointerDown/);
  assert.match(separator, /setPointerCapture/);
  assert.match(separator, /onKeyDown/);
  assert.match(css, /@media \(min-width: 1100px\)/);
  assert.match(css, /@media \(min-width: 760px\) and \(max-width: 1099px\)/);
  assert.match(css, /@media \(max-width: 759px\)/);
  assert.match(app, /disabled=\{layoutPreferences\.sidebarCollapsed\}/);
});

test("the coding workspace stays inert until its selected file is loaded", async () => {
  const app = await readFile(appUrl, "utf8");

  assert.match(app, /const selectedFileReady = Boolean\([\s\S]*filePath === selectedQuestion\.file[\s\S]*!fileLoading/);
  assert.match(app, /filePath === selectedQuestion\.file &&\s*!fileLoadFailed/);
  assert.match(app, /const selectedFileLoading = selectedFilePending && !fileLoadFailed/);
  assert.match(app, /aria-busy=\{selectedFileLoading\}/);
  assert.match(app, /Boolean\(selectedQuestion\) &&\s*selectedFileReady/);
  assert.match(app, /running !== null \|\|\s*!selectedFileReady/);
  assert.match(app, /setFilePath\(""\);\s*setFileLoadFailed\(true\)/);
  assert.match(app, /setFileLoadRetryVersion\(\(value\) => value \+ 1\)/);
});

test("layout state loads with the course and persists under its manifest id", async () => {
  const app = await readFile(appUrl, "utf8");

  assert.match(app, /layoutStorageKey\(courseId\)/);
  assert.match(app, /window\.localStorage\.getItem/);
  assert.match(app, /window\.localStorage\.setItem/);
  assert.match(app, /const loadedCourseId = manifestCourseId\(payload\.manifest\)/);
  assert.match(app, /parseLayoutPreferences/);
  assert.match(app, /serializeLayoutPreferences/);
  assert.match(
    app,
    /const \[layoutPreferences, setLayoutPreferences\] =[\s\S]*?useState<LayoutPreferences>\(\{ \.\.\.DEFAULT_LAYOUT_PREFERENCES \}\)/,
  );
});
