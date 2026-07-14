import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import test from "node:test";

const generatedManifestUrl = new URL("../course/starter/manifest.json", import.meta.url);

test("setup keeps every dependency cache inside the generated repository", async () => {
  const workspace = JSON.parse(
    await readFile(new URL("../../package.json", import.meta.url), "utf8"),
  );
  assert.match(
    workspace.scripts.setup,
    /uv sync --cache-dir \.\.\/platform\/\.uv-cache --directory labs --locked/,
  );
  assert.doesNotMatch(
    workspace.scripts.setup,
    /uv sync --cache-dir platform\/\.uv-cache --directory labs/,
  );
});

test("lint skips generated Python environments and build output", async () => {
  const platform = JSON.parse(
    await readFile(new URL("../package.json", import.meta.url), "utf8"),
  );
  assert.equal(
    platform.scripts.lint,
    "eslint . --ignore-pattern dist --ignore-pattern .next --ignore-pattern .venv --ignore-pattern .uv-cache",
  );
});

test("the Web shell is runtime-driven and keeps the Python editor", async () => {
  const app = await readFile(new URL("../app/CourseKitApp.tsx", import.meta.url), "utf8");
  assert.match(app, /\/api\/course/);
  assert.match(app, /\/api\/content/);
  assert.match(app, /PythonCode/);
  assert.doesNotMatch(app, /lab12|ThreadEval|Concurrency(?:Lab)/);
});

test(
  "the generated learner manifest excludes reference and hidden selectors",
  {
    skip: existsSync(generatedManifestUrl)
      ? false
      : "raw template has no compiled learner manifest",
  },
  async () => {
    const manifest = JSON.parse(await readFile(generatedManifestUrl, "utf8"));
    const serialized = JSON.stringify(manifest);
    assert.equal(manifest.student_workspace, true);
    assert.doesNotMatch(serialized, /reference_root|tests\/hidden|\"hidden\"/);
  },
);

test("grading clients allow exactly 105 seconds while ordinary Web requests stay at 8", async () => {
  const learnerCli = await readFile(
    new URL("../support/coursekit/cli.py", import.meta.url),
    "utf8",
  );
  const app = await readFile(new URL("../app/CourseKitApp.tsx", import.meta.url), "utf8");

  assert.match(learnerCli, /urlopen\(request, timeout=105\)/);
  assert.doesNotMatch(learnerCli, /urlopen\(request, timeout=60\)/);
  assert.match(app, /timeoutMs = 8_000/);
  assert.match(app, /runnerRequest<CoursePayload>\("\/api\/course"\)/);
  assert.match(
    app,
    /runnerRequest<CourseContentItem>\(\s*`\/api\/content\/\$\{encodeURIComponent\(selectedLab\.id\)\}`,\s*\)/,
  );
  assert.match(
    app,
    /runnerRequest<FileReadPayload>\(\s*`\/api\/file\?lab_id=\$\{encodeURIComponent\(selectedLab\.id\)\}&question_id=\$\{encodeURIComponent\(selectedQuestion\.id\)\}`,\s*\)/,
  );
  assert.match(
    app,
    /runnerRequest<FileWritePayload>\("\/api\/file", \{\s*method: "PUT",\s*body: JSON\.stringify\(\{\s*lab_id: captured\.labId,\s*question_id: captured\.questionId,\s*content: captured\.source,\s*\}\),\s*\}\);/,
  );
  assert.match(
    app,
    /clearSavedDraftIfUnchanged\(\s*draftsRef\.current,\s*captured\.path,\s*captured\.source,?\s*\)/,
  );
  assert.doesNotMatch(app, /delete draftsRef\.current\[captured\.path\]/);
  assert.match(
    app,
    /runnerRequest<RunPayload>\(\s*"\/api\/run",[\s\S]*?\n\s*105_000,\n\s*\);/,
  );
  assert.equal(app.match(/105_000/g)?.length, 1);
  assert.doesNotMatch(app, /70_000/);
});
