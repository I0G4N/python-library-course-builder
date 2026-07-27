import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import test from "node:test";

const staticRoot = new URL("../../coursekit_runtime/static/", import.meta.url);

test("prebuilt v4 static bundle is same-origin and self-contained", async () => {
  const index = await readFile(new URL("index.html", staticRoot), "utf8");
  const assets = await readdir(new URL("assets/", staticRoot));
  const javascript = assets.filter((name) => name.endsWith(".js"));
  const stylesheets = assets.filter((name) => name.endsWith(".css"));
  const katexFonts = assets.filter(
    (name) => /^KaTeX_.+\.(?:woff2?|ttf)$/.test(name),
  );

  assert.ok(javascript.length >= 1, "Vite must emit a hashed JavaScript asset");
  assert.ok(stylesheets.length >= 1, "Vite must emit a hashed stylesheet");
  assert.ok(
    katexFonts.length >= 1,
    "Vite must emit local KaTeX font assets",
  );
  assert.match(index, /<html lang="__COURSEKIT_LANGUAGE__">/);
  assert.match(index, /\/assets\/[^"]+\.js/);
  assert.match(index, /\/assets\/[^"]+\.css/);

  const bundledSource = (
    await Promise.all(
      javascript.map((name) =>
        readFile(new URL(`assets/${name}`, staticRoot), "utf8"),
      ),
    )
  ).join("\n");
  const bundledStyles = (
    await Promise.all(
      stylesheets.map((name) =>
        readFile(new URL(`assets/${name}`, staticRoot), "utf8"),
      ),
    )
  ).join("\n");
  assert.doesNotMatch(bundledSource, /http:\/\/127\.0\.0\.1:8765/);
  assert.doesNotMatch(bundledSource, /lesson_outline/);
  assert.doesNotMatch(bundledSource, /npm run learn/);
  assert.doesNotMatch(bundledSource, /uv run coursekit serve/);
  assert.match(bundledSource, /uv run course/);
  assert.match(bundledStyles, /@font-face/);
  assert.match(bundledStyles, /KaTeX_Main/);
  assert.match(bundledStyles, /\.katex/);
  assert.match(
    bundledStyles,
    /url\([^)]*KaTeX_[^)]*\.(?:woff2?|ttf)[^)]*\)/,
  );
  assert.doesNotMatch(bundledStyles, /https?:\/\//i);
  assert.doesNotMatch(
    `${index}\n${bundledStyles}`,
    /(?:cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|unpkg\.com)/i,
  );
});
