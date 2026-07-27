import assert from "node:assert/strict";
import test from "node:test";

import {
  consumeMarkdownList,
  extractTutorialHeadings,
  headingSlug,
  normalizeLessonTerms,
} from "../lessonGuide.mjs";

test("free-form Markdown headings produce stable unicode navigation", () => {
  const markdown = [
    "# 为什么需要事件循环？",
    "## `Task` 的生命周期",
    "```python",
    "# code is not a chapter heading",
    "```",
    "## `Task` 的生命周期",
    "### Failure & recovery",
  ].join("\n");

  assert.deepEqual(extractTutorialHeadings(markdown), [
    {
      id: "section-为什么需要事件循环",
      title: "为什么需要事件循环？",
      level: 1,
    },
    {
      id: "section-task-的生命周期",
      title: "Task 的生命周期",
      level: 2,
    },
    {
      id: "section-task-的生命周期-2",
      title: "Task 的生命周期",
      level: 2,
    },
    {
      id: "section-failure-recovery",
      title: "Failure & recovery",
      level: 3,
    },
  ]);
  assert.equal(headingSlug("Crème brûlée"), "creme-brulee");
});

test("wrapped Markdown lists remain readable without a fixed chapter outline", () => {
  assert.deepEqual(
    consumeMarkdownList(
      [
        "- First item starts here",
        "  and continues naturally.",
        "- Second item",
        "",
      ],
      0,
    ),
    {
      ordered: false,
      start: undefined,
      items: [
        "First item starts here and continues naturally.",
        "Second item",
      ],
      nextIndex: 3,
    },
  );
});

test("terms come only from the explicit v4 terms payload", () => {
  assert.deepEqual(
    normalizeLessonTerms([
      { id: "task", name: " Task ", definition: " A scheduled coroutine. " },
      { id: "task", name: "Duplicate", definition: "Ignored." },
      { id: "", name: "Event loop", definition: "The scheduler." },
      { id: "bad", name: "", definition: "Not visible." },
    ]),
    [
      { id: "task", name: "Task", definition: "A scheduled coroutine." },
      {
        id: "event-loop",
        name: "Event loop",
        definition: "The scheduler.",
      },
    ],
  );

  assert.deepEqual(
    normalizeLessonTerms({
      concepts: [
        { id: "legacy", name: "Legacy", definition: "Must not be inferred." },
      ],
    }),
    [],
  );
});
