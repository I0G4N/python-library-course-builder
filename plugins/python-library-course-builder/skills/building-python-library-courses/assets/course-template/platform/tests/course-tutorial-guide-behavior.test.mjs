import assert from "node:assert/strict";
import test from "node:test";

import {
  consumeMarkdownList,
  extractLessonTerms,
  extractTutorialHeadings,
  headingSlug,
} from "../app/lessonGuide.mjs";

test("tutorial headings receive stable unicode anchors with deterministic duplicates", () => {
  const markdown = [
    "# 为什么需要事件循环？",
    "## `Task` 的生命周期",
    "```python",
    "# this is code, not navigation",
    "```",
    "## `Task` 的生命周期",
    "### Failure & recovery",
    "##### Implementation note",
    "###### Edge condition",
  ].join("\n");

  assert.deepEqual(extractTutorialHeadings(markdown), [
    { id: "section-为什么需要事件循环", title: "为什么需要事件循环？", level: 1 },
    { id: "section-task-的生命周期", title: "Task 的生命周期", level: 2 },
    { id: "section-task-的生命周期-2", title: "Task 的生命周期", level: 2 },
    { id: "section-failure-recovery", title: "Failure & recovery", level: 3 },
    { id: "section-implementation-note", title: "Implementation note", level: 5 },
    { id: "section-edge-condition", title: "Edge condition", level: 6 },
  ]);
  assert.equal(headingSlug("Crème brûlée"), "creme-brulee");
  assert.equal(headingSlug("***"), "section");
});

test("ordered and unordered lists preserve wrapped continuation lines", () => {
  const unordered = [
    "- First item starts here",
    "  and continues on the next physical line.",
    "- Second item",
    "with a lazy continuation.",
    "",
    "After the list.",
  ];
  assert.deepEqual(consumeMarkdownList(unordered, 0), {
    ordered: false,
    start: undefined,
    items: [
      "First item starts here and continues on the next physical line.",
      "Second item with a lazy continuation.",
    ],
    nextIndex: 4,
  });

  const ordered = [
    "3. Inspect the input",
    "   before changing state.",
    "4) Return the result",
    "## Next section",
  ];
  assert.deepEqual(consumeMarkdownList(ordered, 0), {
    ordered: true,
    start: 3,
    items: ["Inspect the input before changing state.", "Return the result"],
    nextIndex: 3,
  });
});

test("terminology is derived from the structured sidecar without duplicate concepts", () => {
  assert.deepEqual(
    extractLessonTerms({
      concepts: [
        { id: "task", name: "Task", definition: "A scheduled coroutine." },
        { id: "task", name: "Task again", definition: "Duplicate id." },
        { id: "loop", name: "Event loop", definition: "The cooperative scheduler." },
        { id: "missing", name: "", definition: "Not learner visible." },
      ],
    }),
    [
      { id: "task", name: "Task", definition: "A scheduled coroutine." },
      { id: "loop", name: "Event loop", definition: "The cooperative scheduler." },
    ],
  );
});
