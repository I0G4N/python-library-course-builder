# __COURSEKIT_TITLE__

__COURSEKIT_DESCRIPTION__

Target: `__COURSEKIT_TARGET__` (__COURSEKIT_TARGET_VERSION__). The course is built from fixed-version official sources recorded in `platform/course/source/sources.json`.

This course selected English (`en`) when it was created. Lessons, quiz prompts, feedback, generated documentation, and the learning interface use English. Code, shell commands, identifiers, target API names, and official-source titles and URLs remain in their original form. A generated course has no runtime language switch.

## Prerequisites

- Python __COURSEKIT_PYTHON_REQUIRES__
- [uv](https://docs.astral.sh/uv/)
- Node.js 22.13 or newer
- Git

Supported local platforms are macOS, Linux, and WSL2 with the project stored in the Linux filesystem. Native Windows is not a verified CourseKit execution path.

No API key, cloud account, database, GPU, or paid service is required. Mandatory examples and grading run deterministically and locally.

__COURSEKIT_PREPARATION__

## Course route

__COURSEKIT_ROUTE__

## Start learning

```bash
npm run setup
npm run learn
```

Open the Web URL printed by the terminal. The local Runner listens only on `127.0.0.1:8765`; press `Ctrl+C` in the launching terminal to stop both processes.

Use the browser for lessons, examples, editing, and fast feedback. Use a local IDE for formal Lab implementation and debugging; both surfaces edit the same formal-Lab files under `labs/`. Preparatory units provide lessons, examples, and knowledge checks, never an editable coding workspace.

The Runner is a local study tool, not a hostile-code sandbox. It reduces ordinary grading side effects, but submitted Python still executes with the current OS account's privileges. Keep it on loopback and never expose it as a public judge.

## Learning progression

CLI, Web, and Runner share one progression state, course order, and knowledge state. Restarts load the same `labs/.coursekit/state.json`.

Schema v3 follows `lab00 -> prep01 -> prep02 -> ... -> lab01`:

1. Initially, only `lab00` is navigable. It is a 15–30 minute environment and learning-workflow orientation.
2. Completing the `lab00` knowledge check unlocks the first `prepNN`; completing each prep knowledge check unlocks the next unit in dependency order.
3. The final prep unlocks `lab01`. A route with no prep chapters proceeds directly from `lab00` to `lab01`.
4. Formal Labs enforce the chapter navigation gate, knowledge gate, and coding verification gate. The current Lab's knowledge check precedes coding, and every verified submission precedes the next formal Lab.

Every `prepNN` is an independent knowledge-only lesson and quiz with no coding question, workspace, points, submission, or checkpoint. Runner file, write, and execution APIs reject prep units; only formal Labs contribute to the score.

Schema v2 remains compatible: it has no `prepNN`; `lab00` is its single foundation unit; `lab00` and `lab01` start navigable; later Labs unlock after the preceding formal Lab completes.

To restart from Lab 00, stop `npm run learn`, archive the progress file, and restart:

```bash
mv labs/.coursekit/state.json labs/.coursekit/state.json.bak
```

This resets progression only; it does not modify formal-Lab implementations under `labs/labNN/`.

The coding route alternates between a deliberately small teaching-equivalent and a graded bridge to the pinned official API. Later Labs and the capstone call the official library rather than importing earlier mini implementations.

`lab00` and every `prepNN` have no code workspace. Until the preparation chain and current formal Lab knowledge check are complete, the browser does not mount Code/Result or call question-scoped file APIs. This is a workflow gate, not source secrecy: the starter files remain visible from an IDE or terminal.

Before the knowledge check is complete, Web uses a focus-reading layout: wide screens show the tutorial at a comfortable line length with a chapter outline, terminology index, and knowledge check in a right rail; narrower screens stack those surfaces. After a formal Lab's knowledge check, the resizable lesson and Code/Result workspace returns. On desktop, two keyboard-accessible separators resize the sidebar, lesson pane, and work pane; the sidebar can collapse and validated preferences live in per-course localStorage. Medium and small layouts show no resize separators, and the knowledge check remains available for review after unlock.

Web interactions fail closed during the initial `/api/state` load. Navigation, quizzes, editing, tests, and submission stay disabled until authoritative progression arrives; a transient request failure never unlocks a Lab.

The generic Web knowledge check reads redacted questions from `GET /api/knowledge/{lab_id}` and submits one choice to `POST /api/knowledge/answer`. Neither response exposes answer keys or feedback for unselected choices. A failed POST preserves the selected answer and original request so **Retry submission** resends the same answer; background refreshes do not erase the error.

Progress responses are ordered by curriculum identity and `updated_at`. Web rejects stale state snapshots and ignores delayed save or run responses after the learner changes Lab or question.

## CLI learning loop

```bash
cd labs
uv run course status
uv run course unlock lab00
```

If the route contains `prepNN`, unlock each one in table order. Each command completes its knowledge check without running code or producing points. After the last prep:

```bash
uv run course unlock lab01
uv run course test __COURSEKIT_FIRST_QUESTION__
uv run course grade lab01
uv run course submit lab01
git add lab01 && git commit -m "finish lab01"
uv run course checkpoint lab01
uv run course score
```

Direct `pytest` runs use the same knowledge gate. Public tests sit beside starter code; verified tests and reference implementations remain under `platform/course/` and are never copied into the normal learner workspace.

This separation reduces accidental hints but is not a secrecy boundary after publication. Anyone with the complete repository can inspect `platform/course/reference/` and `platform/course/tests/hidden/`. Version 0.2.0 does not provide an automated learner-only export. The supported secrecy path is to keep the complete teacher/authoring repository private.

## Authoring and integrity

`platform/course/source/` is the only canonical source. In the new tutorial format, each chapter stores textbook-style prose in `tutorial.md` and concept, source, and activity mappings in the `lesson.json` sidecar, alongside runnable examples, Lab metadata, code, and tests. `platform/course/authoring-spec.json` is a private compiler-generated verification view, not a parallel editable source.

```bash
npm --prefix platform run course:compile
npm --prefix platform run course:check
npm test
npm run test:reference
```

Every Lab extends one capstone: __COURSEKIT_CAPSTONE__
