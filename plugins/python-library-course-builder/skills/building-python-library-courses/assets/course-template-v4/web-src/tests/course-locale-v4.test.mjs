import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveCourseLanguage,
} from "../courseLocaleV4.mjs";

test("schema-v4 course payload resolves its boot locale", () => {
  const payload = {
    manifest: {
      schema_version: 4,
      language: "zh-CN",
    },
  };

  assert.equal(
    resolveCourseLanguage(
      payload.manifest.schema_version,
      payload.manifest.language,
    ),
    "zh-CN",
  );
  assert.equal(resolveCourseLanguage(4, "en"), "en");
});

test("schema-v4 locale remains explicit and legacy resolution is preserved", () => {
  assert.throws(
    () => resolveCourseLanguage(4, undefined),
    /schema v4 manifest\.language is required/,
  );
  assert.throws(
    () => resolveCourseLanguage(4, "fr"),
    /schema v4 manifest\.language is unsupported: fr/,
  );
  assert.equal(resolveCourseLanguage(2, undefined), "zh-CN");
  assert.equal(resolveCourseLanguage(3, "en"), "en");
});
