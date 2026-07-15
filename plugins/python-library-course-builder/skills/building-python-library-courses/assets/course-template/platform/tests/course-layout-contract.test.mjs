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

function mediaSection(css, start, end) {
  const startIndex = css.indexOf(start);
  assert.notEqual(startIndex, -1, `missing media query: ${start}`);
  const endIndex = end ? css.indexOf(end, startIndex + start.length) : css.length;
  assert.notEqual(endIndex, -1, `missing following media query: ${end}`);
  return css.slice(startIndex, endIndex);
}

test("orientation, prep, and quiz-locked units do not mount or preload coding", async () => {
  const app = await readFile(appUrl, "utf8");

  assert.match(app, /graded\?: boolean/);
  assert.match(app, /unit_type\?: CourseUnitType/);
  assert.match(
    app,
    /const codingUnitSelected = Boolean\([\s\S]*?isCodingUnit\(\{[\s\S]*?unitType: selectedLab\.unit_type,[\s\S]*?graded: selectedLab\.graded,[\s\S]*?legacyFoundationSelected: selectedLab\.id === foundationLabId/,
  );
  assert.doesNotMatch(
    app,
    /selectedLab && selectedLab\.id !== foundationLabId/,
  );
  assert.match(app, /selectedLab\?\.unit_type === "preparatory"/);
  assert.match(app, /const codingReady = shouldShowCodingWorkspace\(/);
  assert.match(app, /codingUnitSelected,/);
  assert.match(
    app,
    /const codingReady = shouldShowCodingWorkspace\(\{[\s\S]*?codingUnitSelected,[\s\S]*?selectedLabNavigable,[\s\S]*?foundationKnowledgeComplete,[\s\S]*?currentKnowledgeComplete,[\s\S]*?\}\);/,
  );
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
  assert.match(css, /@media \(min-width: 1024px\)/);
  assert.match(css, /@media \(min-width: 760px\) and \(max-width: 1023px\)/);
  assert.match(css, /@media \(max-width: 759px\)/);
  assert.match(app, /disabled=\{layoutPreferences\.sidebarCollapsed\}/);
});

test("short desktop windows keep lesson and work columns independently scrollable", async () => {
  const css = await readFile(cssUrl, "utf8");

  assert.match(
    css,
    /\.course-shell\s*\{[\s\S]*?height:\s*100vh;[\s\S]*?height:\s*100dvh;[\s\S]*?min-height:\s*0;[\s\S]*?overflow:\s*hidden;[\s\S]*?\}/,
  );
  assert.match(css, /\.course-sidebar\s*\{[\s\S]*?min-height:\s*0;[\s\S]*?\}/);
  assert.match(css, /\.course-main\s*\{[\s\S]*?overflow:\s*hidden;[\s\S]*?\}/);
  assert.match(
    css,
    /\.lesson-scroll\s*\{[\s\S]*?overflow-y:\s*auto;[\s\S]*?overscroll-behavior:\s*contain;[\s\S]*?\}/,
  );
  assert.match(
    css,
    /\.work-column\s*\{[\s\S]*?overflow-y:\s*auto;[\s\S]*?overscroll-behavior:\s*contain;[\s\S]*?\}/,
  );
});

test("tablet stacks the learning surfaces and mobile uses natural document scrolling", async () => {
  const css = await readFile(cssUrl, "utf8");
  const tablet = mediaSection(
    css,
    "@media (min-width: 760px) and (max-width: 1023px)",
    "@media (max-width: 759px)",
  );
  const mobile = mediaSection(
    css,
    "@media (max-width: 759px)",
    "@media (max-width: 480px)",
  );

  assert.match(tablet, /\.learning-grid\s*\{[\s\S]*?overflow-y:\s*auto;[\s\S]*?\}/);
  assert.match(
    tablet,
    /\.lesson-scroll\s*\{[\s\S]*?overscroll-behavior:\s*auto;[\s\S]*?\}/,
  );
  assert.match(
    tablet,
    /\.learning-grid\.coding-visible\s*\{[\s\S]*?grid-template-rows:[\s\S]*?\}/,
  );
  assert.doesNotMatch(tablet, /\.learning-grid\.coding-visible\s*\{[^}]*grid-template-columns:/s);

  assert.match(
    mobile,
    /\.course-shell\s*\{[\s\S]*?height:\s*auto;[\s\S]*?min-height:\s*100dvh;[\s\S]*?overflow:\s*visible;[\s\S]*?\}/,
  );
  assert.match(
    mobile,
    /\.course-sidebar\s*\{[\s\S]*?position:\s*static;[\s\S]*?grid-template-areas:\s*"brand nav"\s*"readiness readiness";[\s\S]*?\}/,
  );
  assert.match(mobile, /\.brand-block\s*\{[\s\S]*?grid-area:\s*brand;[\s\S]*?\}/);
  assert.match(
    mobile,
    /\.readiness-summary\s*\{[\s\S]*?grid-area:\s*readiness;[\s\S]*?overflow:\s*visible;[\s\S]*?\}/,
  );
  assert.match(mobile, /\.lab-nav\s*\{[\s\S]*?grid-area:\s*nav;[\s\S]*?\}/);
  assert.match(mobile, /\.course-main\s*\{[\s\S]*?display:\s*block;[\s\S]*?\}/);
  assert.match(mobile, /\.learning-grid\s*\{[\s\S]*?overflow:\s*visible;[\s\S]*?\}/);
  assert.match(
    mobile,
    /\.lesson-scroll\s*\{[\s\S]*?max-height:\s*none;[\s\S]*?overflow:\s*visible;[\s\S]*?\}/,
  );
  assert.match(mobile, /\.work-column\s*\{[\s\S]*?overflow:\s*visible;[\s\S]*?\}/);
});

test("toolbar metadata shares one grid cell instead of creating an implicit row", async () => {
  const app = await readFile(appUrl, "utf8");

  assert.match(
    app,
    /<header className="course-toolbar">[\s\S]*?<div className="course-toolbar-meta">[\s\S]*?className="course-summary"[\s\S]*?className="selected-study-time"[\s\S]*?<\/div>[\s\S]*?<\/header>/,
  );
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

test("zero-gap v3 readiness reports no extra prep instead of an empty prep list", async () => {
  const app = await readFile(appUrl, "utf8");

  assert.match(app, /preparationTitles\.length > 0/);
  assert.match(app, /无需额外先修/);
  assert.match(app, /完成 Lab 00 导览后即可进入正式 Lab/);
});

test("chapter navigation uses the shared Lab and Prep badge formatter", async () => {
  const app = await readFile(appUrl, "utf8");

  assert.match(app, /unitBadgeLabel,/);
  assert.match(
    app,
    /className="lab-index">\s*\{isComplete\s*\?\s*"✓"\s*:\s*unitBadgeLabel\(lab\.id, index\)\}/,
  );
  assert.doesNotMatch(app, /\^lab\\d\+\$/);
});
