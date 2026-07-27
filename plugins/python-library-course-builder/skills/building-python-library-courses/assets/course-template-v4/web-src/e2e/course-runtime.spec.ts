import { expect, test, type Page, type Route } from "@playwright/test";

type SharedState = {
  course_id: string;
  curriculum_id: string;
  completed_labs: string[];
  completed_preparatory_units: string[];
  unlocked_labs: string[];
  score: number;
  total_points: number;
  updated_at: string;
};

const courseId = "browser-conformance";
const curriculumId = "browser-conformance-v4";

const labs = [
  {
    id: "lab00",
    title: "Orientation",
    unit_type: "orientation",
    graded: false,
    description: "Learn the complete CourseKit loop.",
    questions: [],
    study_minutes: { tier: "orientation", min: 15, max: 30 },
  },
  {
    id: "lab01",
    title: "Boundary engine",
    unit_type: "lab",
    graded: true,
    description: "Carry one value through the boundary.",
    questions: [
      {
        id: "normalize",
        title: "Implement normalize",
        file: "src/browser_course/normalize.py",
        symbol: "normalize",
        prompt: "Preserve the boundary invariant.",
        points: 1,
      },
    ],
    study_minutes: { tier: "standard", min: 30, max: 45 },
  },
  {
    id: "lab02",
    title: "Composition",
    unit_type: "lab",
    graded: true,
    description: "Compose the public interfaces.",
    questions: [
      {
        id: "compose",
        title: "Compose interfaces",
        file: "src/browser_course/compose.py",
        symbol: "compose",
        points: 1,
      },
    ],
    study_minutes: { tier: "standard", min: 30, max: 45 },
  },
];

const content = {
  lab00: {
    id: "lab00",
    title: "Orientation",
    lesson: [
      "# A freely-shaped opening",
      "",
      "This prose deliberately follows the mechanism instead of a fixed outline.",
      "",
      "#### Failure / recovery?",
      "",
      "A concrete symptom leads to a concrete recovery.",
      "",
      "Inline formula: \\(x_i + 1\\) remains part of this sentence.",
      "",
      "Display formula:",
      "",
      "  \\[",
      "\\sum_{i=1}^{3} i = 6",
      "\\]",
      "",
      "\\[z=3\\]",
      "",
      "## Formula heading \\(E=mc^2\\)",
      "",
      "| Surface | Value |",
      "|---|---|",
      "| Table formula | \\(a^2+b^2=c^2\\) |",
      "",
      "- List formula \\(n+1\\)",
      "",
      "  Nested display formula:",
      "",
      "  \\[",
      "  m=5",
      "  \\]",
      "",
      "  List continuation stays in the same item.",
      "",
      "> Quote formula \\(q=42\\)",
      "",
      "```text",
      "Fenced literal \\(not_math\\), \\[not_display\\], and $fenced$.",
      "```",
      "",
      "Inline code literal `\\(inline_code\\)` stays code.",
      "",
      "    \\[four_space_literal\\]",
      "",
      "Dollar literals: shell $(), price $5, $x+1$, and $$y+1$$ stay unchanged.",
      "",
      "Invalid formula: \\(x^{\\) must not abort the lesson.",
      "",
      "Unclosed formula remains literal: \\(x + 1",
      "",
      "An unclosed formula does not consume a later one: \\(broken then \\(v=2\\).",
      "",
      "Nor does it consume inline code: \\(broken then `code \\)` remains code.",
      "",
      "Unclosed display remains literal:",
      "\\[",
      "x + 1",
      "",
      "\\[w=4\\]",
      "",
      "### Content after unclosed display",
      "",
      "The chapter still renders after an unmatched display delimiter.",
      "",
      "Untrusted formula: \\(\\href{https://evil.invalid/}{unsafe}\\).",
    ].join("\n"),
    terms: [
      {
        id: "control-token",
        name: "Control token",
        definition: "The value that crosses the teaching boundary.",
      },
    ],
    sources: [
      {
        id: "official",
        title: "Official reference",
        url: "https://docs.python.org/3/",
      },
    ],
    study_minutes: { tier: "orientation", min: 15, max: 30 },
  },
  lab01: {
    id: "lab01",
    title: "Boundary engine",
    lesson: [
      "# Follow value `17`",
      "",
      "The same value drives the explanation, quiz, and implementation.",
      "",
      "### Why this design wins here",
      "",
      "The alternative is credible, but moves recovery to the caller.",
    ].join("\n"),
    terms: [
      {
        id: "boundary",
        name: "Boundary",
        definition: "The caller-visible input and output contract.",
      },
    ],
    sources: [],
    study_minutes: { tier: "standard", min: 30, max: 45 },
    practice_links: [
      {
        kind: "coding-question",
        item_id: "normalize",
        title: "Implement normalize",
      },
    ],
  },
  lab02: {
    id: "lab02",
    title: "Composition",
    lesson: "# Compose public interfaces\n\nThe capstone uses only public boundaries.",
    terms: [],
    sources: [],
    study_minutes: { tier: "standard", min: 30, max: 45 },
  },
} as const;

function knowledgeView(labId: string, mastered: boolean) {
  const available = labId !== "lab02";
  return {
    lab_id: labId,
    title: `${labId} knowledge`,
    available,
    completed: mastered,
    mastered: mastered ? 1 : 0,
    total: 1,
    questions: available
      ? [
          {
            id: `${labId}-boundary`,
            kind: "diagnostic",
            prompt:
              labId === "lab01"
                ? "Which choice preserves the boundary invariant?"
                : "What completes the learning loop?",
            choices: [
              { id: "preserve", text: "Preserve the caller-visible contract." },
              { id: "guess", text: "Guess from an implementation detail." },
            ],
            mastered,
          },
        ]
      : [],
  };
}

async function installApi(page: Page) {
  let state: SharedState = {
    course_id: courseId,
    curriculum_id: curriculumId,
    completed_labs: ["lab00"],
    completed_preparatory_units: [],
    unlocked_labs: ["lab00", "lab01"],
    score: 1,
    total_points: 3,
    updated_at: "2026-07-26T01:00:00Z",
  };
  const mastered: Record<string, boolean> = {
    lab00: true,
    lab01: false,
    lab02: false,
  };
  const writes: string[] = [];
  const runModes: string[] = [];
  let revision = 0;

  function advanceState(changes: Partial<SharedState> = {}) {
    revision += 1;
    state = {
      ...state,
      ...changes,
      updated_at: `2026-07-26T01:00:0${revision}Z`,
    };
  }

  async function json(route: Route, body: unknown, status = 200) {
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  }

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (request.method() === "GET" && path === "/api/course") {
      await json(route, {
        manifest: {
          schema_version: 4,
          language: "en",
          course_id: courseId,
          curriculum_id: curriculumId,
          title: "Browser conformance course",
          description: "A mocked same-origin v4 course.",
          total_points: 3,
          labs,
        },
        state,
      });
      return;
    }
    if (request.method() === "GET" && path === "/api/state") {
      await json(route, state);
      return;
    }
    if (request.method() === "GET" && path.startsWith("/api/content/")) {
      const labId = decodeURIComponent(path.split("/").at(-1) ?? "");
      await json(route, content[labId as keyof typeof content] ?? {}, labId in content ? 200 : 404);
      return;
    }
    if (request.method() === "GET" && path.startsWith("/api/knowledge/")) {
      const labId = decodeURIComponent(path.split("/").at(-1) ?? "");
      await json(route, knowledgeView(labId, mastered[labId] === true));
      return;
    }
    if (request.method() === "POST" && path === "/api/knowledge/answer") {
      const answer = request.postDataJSON() as {
        lab_id: string;
        question_id: string;
        choice_id: string;
      };
      const correct = answer.choice_id === "preserve";
      if (correct) mastered[answer.lab_id] = true;
      advanceState();
      await json(route, {
        correct,
        feedback: correct ? "The public contract stays observable." : "Try the caller boundary.",
        explanation: "The caller must be able to predict the result.",
        knowledge: knowledgeView(answer.lab_id, mastered[answer.lab_id] === true),
        state,
      });
      return;
    }
    if (request.method() === "GET" && path === "/api/file") {
      await json(route, {
        path: "src/browser_course/normalize.py",
        content: "def normalize(value):\n    raise NotImplementedError\n",
      });
      return;
    }
    if (request.method() === "PUT" && path === "/api/file") {
      const payload = request.postDataJSON() as { content: string };
      writes.push(payload.content);
      await json(route, {
        path: "src/browser_course/normalize.py",
        status: "saved",
      });
      return;
    }
    if (request.method() === "POST" && path === "/api/run") {
      const payload = request.postDataJSON() as { mode: string };
      runModes.push(payload.mode);
      if (payload.mode === "submit") {
        advanceState({
          completed_labs: ["lab00", "lab01"],
          unlocked_labs: ["lab00", "lab01", "lab02"],
          score: 2,
        });
      } else {
        advanceState();
      }
      await json(route, {
        passed: true,
        output:
          payload.mode === "submit"
            ? "hidden submit passed"
            : "public tests passed",
        score: state.score,
        state,
      });
      return;
    }

    await json(route, { detail: `Unhandled mocked API route: ${request.method()} ${path}` }, 404);
  });

  return {
    writes,
    runModes,
    state: () => state,
  };
}

test("shared v4 Web preserves the complete learning loop", async ({ page }) => {
  const api = await installApi(page);
  await page.goto("/");

  await test.step("restore progress and render free-form chapter tools", async () => {
    await expect(page.getByRole("heading", { name: "Browser conformance course" })).toBeVisible();
    await expect(page.locator(".score-line")).toContainText("1 / 3");
    await expect(page.locator(".lab-link", { hasText: "Orientation" }).locator(".lab-index")).toHaveText("✓");
    await expect(page.locator(".lab-link", { hasText: "Composition" })).toBeDisabled();

    const chapterGuide = page.getByRole("navigation", { name: "Chapter guide" });
    await expect(chapterGuide.getByRole("link", { name: "A freely-shaped opening" })).toHaveAttribute(
      "href",
      "#section-a-freely-shaped-opening",
    );
    await expect(chapterGuide.getByRole("link", { name: "Failure / recovery?" })).toHaveAttribute(
      "href",
      "#section-failure-recovery",
    );
    await expect(chapterGuide).toContainText("Control token");
    await expect(chapterGuide).toContainText("The value that crosses the teaching boundary.");
    await expect(page.getByRole("heading", { name: "Knowledge check" })).toBeVisible();
  });

  await test.step("render math across Markdown contexts without interpreting literals", async () => {
    const lesson = page.locator(".course-lesson");

    const inline = lesson.locator("p", { hasText: "Inline formula:" });
    await expect(inline.locator(".math-inline .katex")).toHaveCount(1);
    await expect(inline.locator(".katex-mathml math")).toHaveCount(1);
    await expect(inline.locator(".katex-html")).toHaveAttribute(
      "aria-hidden",
      "true",
    );

    const display = lesson.locator(".math-display .katex-display");
    await expect(display).toHaveCount(4);
    await expect(display.locator(".katex-mathml math")).toHaveCount(4);

    const heading = lesson.locator("h2", { hasText: "Formula heading" });
    await expect(heading.locator(".math-inline .katex")).toHaveCount(1);

    const tableRow = lesson.locator("tbody tr", { hasText: "Table formula" });
    await expect(tableRow.locator("td").nth(1).locator(".katex")).toHaveCount(1);

    const listItem = lesson.locator("li", { hasText: "List formula" });
    await expect(listItem.locator(".katex")).toHaveCount(2);
    await expect(listItem.locator(".math-display")).toHaveCount(1);
    await expect(listItem).toContainText(
      "List continuation stays in the same item.",
    );

    const quote = lesson.locator("blockquote", { hasText: "Quote formula" });
    await expect(quote.locator(".katex")).toHaveCount(1);

    const fenced = lesson.locator("pre.plain-code", {
      hasText: "Fenced literal",
    });
    await expect(fenced).toContainText(
      "Fenced literal \\(not_math\\), \\[not_display\\], and $fenced$.",
    );
    await expect(fenced.locator(".katex")).toHaveCount(0);

    const inlineCode = lesson.locator("code", {
      hasText: "\\(inline_code\\)",
    });
    await expect(inlineCode).toHaveText("\\(inline_code\\)");
    await expect(inlineCode.locator(".katex")).toHaveCount(0);

    const indentedLiteral = lesson.locator("p", {
      hasText: "\\[four_space_literal\\]",
    });
    await expect(indentedLiteral).toContainText("\\[four_space_literal\\]");
    await expect(indentedLiteral.locator(".katex")).toHaveCount(0);

    const dollars = lesson.locator("p", { hasText: "Dollar literals:" });
    await expect(dollars).toContainText(
      "Dollar literals: shell $(), price $5, $x+1$, and $$y+1$$ stay unchanged.",
    );
    await expect(dollars.locator(".katex")).toHaveCount(0);

    const invalid = lesson.locator("p", { hasText: "Invalid formula:" });
    await expect(invalid.locator(".katex-error")).toHaveCount(1);
    await expect(invalid).toContainText("x^{");

    const unclosed = lesson.locator("p", {
      hasText: "Unclosed formula remains literal:",
    });
    await expect(unclosed).toContainText("\\(x + 1");
    await expect(unclosed.locator(".katex")).toHaveCount(0);

    const laterInline = lesson.locator("p", {
      hasText: "does not consume a later one:",
    });
    await expect(laterInline).toContainText("\\(broken then");
    await expect(laterInline.locator(".katex")).toHaveCount(1);

    const protectedInlineCode = lesson.locator("p", {
      hasText: "Nor does it consume inline code:",
    });
    await expect(protectedInlineCode).toContainText("\\(broken then");
    await expect(protectedInlineCode.locator("code")).toHaveText("code \\)");
    await expect(protectedInlineCode.locator(".katex")).toHaveCount(0);

    const unclosedDisplay = lesson.locator("p", { hasText: "\\[ x + 1" });
    await expect(unclosedDisplay).toContainText("\\[ x + 1");
    await expect(unclosedDisplay.locator(".katex")).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "Content after unclosed display" }),
    ).toBeVisible();

    const untrusted = lesson.locator("p", {
      hasText: "Untrusted formula:",
    });
    await expect(
      untrusted.locator('a[href*="evil.invalid"]'),
    ).toHaveCount(0);
    await expect(untrusted.locator(".katex, .katex-error")).toHaveCount(1);
  });

  await page.locator(".lab-link", { hasText: "Boundary engine" }).click();
  await expect(page.getByRole("heading", { name: "Boundary engine" })).toBeVisible();

  await test.step("knowledge gate opens the coding workspace", async () => {
    await expect(page.locator(".work-column")).toHaveCount(0);
    await page.getByLabel("Preserve the caller-visible contract.").check();
    await page.getByRole("button", { name: "Check answer" }).click();
    await expect(page.locator(".knowledge-status")).toContainText("Complete");
    await expect(page.locator(".work-column")).toBeVisible();
  });

  await test.step("desktop keeps navigation, lesson, and coding as three columns", async () => {
    const sidebar = await page.locator(".course-sidebar").boundingBox();
    const lesson = await page.locator(".lesson-panel").boundingBox();
    const work = await page.locator(".work-column").boundingBox();
    expect(sidebar).not.toBeNull();
    expect(lesson).not.toBeNull();
    expect(work).not.toBeNull();
    expect(sidebar!.x + sidebar!.width).toBeLessThanOrEqual(lesson!.x);
    expect(lesson!.x + lesson!.width).toBeLessThanOrEqual(work!.x);
    await expect(page.locator(".learning-grid")).toHaveClass(/coding-visible/);
  });

  await test.step("CodeMirror saves before public and hidden execution", async () => {
    const editor = page.getByRole("textbox", { name: "Implement normalize code editor" });
    await expect(editor).toBeEditable();
    await editor.fill("def normalize(value):\n    return value\n");
    await expect(page.locator(".save-state")).toHaveText("Unsaved");

    await page.getByRole("button", { name: "Run public tests" }).click();
    await expect(page.locator(".test-output")).toHaveText("public tests passed");
    expect(api.writes).toEqual(["def normalize(value):\n    return value\n"]);
    expect(api.runModes).toEqual(["public"]);
    await expect(page.locator(".lab-link", { hasText: "Composition" })).toBeDisabled();

    await page.getByRole("button", { name: "Submit for grading" }).click();
    await expect(page.locator(".test-output")).toHaveText("hidden submit passed");
    expect(api.runModes).toEqual(["public", "submit"]);
    await expect(page.locator(".score-line")).toContainText("2 / 3");
    await expect(page.locator(".lab-link", { hasText: "Composition" })).toBeEnabled();
  });

  await test.step("server progress survives a real page reload", async () => {
    expect(api.state().completed_labs).toContain("lab01");
    await page.reload();
    await expect(page.locator(".score-line")).toContainText("2 / 3");
    await expect(page.locator(".lab-link", { hasText: "Boundary engine" }).locator(".lab-index")).toHaveText("✓");
    await expect(page.locator(".lab-link", { hasText: "Composition" })).toBeEnabled();
  });
});
