import assert from "node:assert/strict";
import test from "node:test";

let layout = {};
try {
  layout = await import("../app/courseLayout.mjs");
} catch (error) {
  if (error?.code !== "ERR_MODULE_NOT_FOUND") throw error;
}

function requiredExport(name) {
  assert.equal(
    typeof layout[name],
    "function",
    `courseLayout.mjs must export ${name}()`,
  );
  return layout[name];
}

test("coding workspace is visible only for a navigable formal Lab with both quizzes complete", () => {
  const shouldShowCodingWorkspace = requiredExport(
    "shouldShowCodingWorkspace",
  );
  const ready = {
    formalLabSelected: true,
    selectedLabNavigable: true,
    foundationKnowledgeComplete: true,
    currentKnowledgeComplete: true,
  };

  assert.equal(shouldShowCodingWorkspace(ready), true);
  for (const key of Object.keys(ready)) {
    assert.equal(
      shouldShowCodingWorkspace({ ...ready, [key]: false }),
      false,
      `${key}=false must keep CODE and RESULT unmounted`,
    );
  }
});

test("layout preferences are course-scoped, validated, and clamped", () => {
  const layoutStorageKey = requiredExport("layoutStorageKey");
  const parseLayoutPreferences = requiredExport("parseLayoutPreferences");

  assert.equal(
    layoutStorageKey("ray-course"),
    "coursekit.layout.v1.ray-course",
  );
  assert.notEqual(layoutStorageKey("ray-course"), layoutStorageKey("verl-course"));
  assert.deepEqual(parseLayoutPreferences("not json"), {
    sidebarWidth: 208,
    sidebarCollapsed: false,
    lessonRatio: 0.42,
  });
  assert.deepEqual(
    parseLayoutPreferences(
      JSON.stringify({
        sidebarWidth: 999,
        sidebarCollapsed: "yes",
        lessonRatio: -4,
      }),
    ),
    {
      sidebarWidth: 320,
      sidebarCollapsed: false,
      lessonRatio: 0,
    },
  );
});

test("sidebar collapse preserves the expanded width for restoration", () => {
  const collapseSidebar = requiredExport("collapseSidebar");
  const expandSidebar = requiredExport("expandSidebar");

  const expanded = {
    sidebarWidth: 284,
    sidebarCollapsed: false,
    lessonRatio: 0.42,
  };
  const collapsed = collapseSidebar(expanded);
  assert.equal(collapsed.sidebarCollapsed, true);
  assert.equal(collapsed.sidebarWidth, 284);
  assert.deepEqual(expandSidebar(collapsed), expanded);
});

test("lesson width keeps the 320px and 440px panel minima", () => {
  const resolveLessonWidth = requiredExport("resolveLessonWidth");

  assert.equal(resolveLessonWidth(1_000, 0.42), 415);
  assert.equal(resolveLessonWidth(800, 0), 320);
  assert.equal(resolveLessonWidth(800, 1), 348);
});

test("separator keyboard behavior uses 16px arrows and Home/End bounds", () => {
  const nextSeparatorValue = requiredExport("nextSeparatorValue");

  assert.equal(nextSeparatorValue(208, "ArrowLeft", 160, 320), 192);
  assert.equal(nextSeparatorValue(208, "ArrowRight", 160, 320), 224);
  assert.equal(nextSeparatorValue(208, "Home", 160, 320), 160);
  assert.equal(nextSeparatorValue(208, "End", 160, 320), 320);
  assert.equal(nextSeparatorValue(208, "ArrowUp", 160, 320), null);
  assert.equal(nextSeparatorValue(160, "ArrowLeft", 160, 320), 160);
});
