# __COURSEKIT_TITLE__

__COURSEKIT_DESCRIPTION__

Target: `__COURSEKIT_TARGET__` (__COURSEKIT_TARGET_VERSION__). The curriculum is built from pinned official sources listed in [`platform/course/source/sources.json`](platform/course/source/sources.json).

## Requirements

- Python __COURSEKIT_PYTHON_REQUIRES__
- [uv](https://docs.astral.sh/uv/)
- Node.js 22.13 or newer
- Git

Supported local platforms are macOS and Linux. On Windows, use WSL2 with the
project stored inside the Linux filesystem; native Windows is not a verified
CourseKit execution path.

No API key, cloud account, database, or GPU is required. Graded tests are deterministic and run locally.

The route assumes basic Python only. A graded Lab is designed for roughly 30-45 minutes and begins with prerequisites, the concrete problem, traceable outcomes, and complete runnable examples. Deeper mechanism/design tradeoffs and wrong-code diagnostics are available as expandable sections instead of crowding the first reading pass.

## 课程路线

__COURSEKIT_ROUTE__

## Start learning

```bash
npm run setup
npm run learn
```

Open the printed Web URL. The local Runner listens only on `127.0.0.1:8765`. Stop both processes with `Ctrl+C` in the terminal that started them.

The browser is useful for reading, examples, editing, and quick feedback. Use your local IDE for serious implementation and debugging; both surfaces edit the same files under `labs/`.

The Runner is a local study tool, not a hostile-code sandbox. It isolates ordinary grading side effects and reclaims the pytest process group, but code running under your OS account has that account's privileges. Keep the service on loopback and never expose it as a public judge for untrusted submissions.

## Learning progression

The CLI and Web use the same progress state and enforce the same three gates:

1. Read Lab 00 and the first graded Lab through the chapter list. Later Labs stay disabled until the preceding Lab is completed.
2. Complete each Web knowledge check (or `course unlock LAB` in the CLI) before running that Lab's code.
3. Pass verified submission for every coding question in the Lab before the next Lab unlocks.

Opening a lesson does not bypass its knowledge or coding gate. A disabled Lab is not clickable, and restarting either interface reloads the same progress from `labs/.coursekit/state.json`.

To restart this curriculum from Lab 00, stop `npm run learn` and archive the progress file before starting again:

```bash
mv labs/.coursekit/state.json labs/.coursekit/state.json.bak
```

This resets learning progress only. Your implementations under `labs/labNN/` remain untouched.

The coding route alternates between mechanism and official API. In one Lab you handwrite a deliberately small teaching-equivalent from lower-level primitives. The next Lab starts by replacing that mechanism through the pinned official API and comparing observable behavior, then you handwrite the next layer. Later Labs and the capstone call the official library rather than importing an earlier mini implementation.

Lab 00 is for foundations and has no code workspace. In a graded Lab, the browser does not mount the code/result area or call the question-scoped file API until foundation and current-Lab knowledge are complete. This is a workflow gate, not source secrecy: you can still inspect your own starter files under `labs/` from an IDE or terminal.

On desktop, the sidebar, lesson, and code/result columns use two keyboard-accessible separators. Drag them to adjust the layout; focus a separator and use the Arrow keys, Home, or End. The sidebar can collapse, minimum widths keep every pane usable, and validated preferences are stored in per-course localStorage. Medium and small screens stack or switch navigation and have no resize separators.

The Web fails closed during the initial `/api/state` load: chapter navigation, the quiz, the editor, and test/submit actions remain disabled until authoritative progress arrives. A temporary request failure never turns locked Labs into clickable Labs.

Each Web knowledge check is generic course data. It reads redacted question and choice payloads from `GET /api/knowledge/{lab_id}` and sends the selected choice to `POST /api/knowledge/answer`; neither response includes an answer key or unselected-choice feedback. The answer response explains only the selected misconception and the underlying trace. If that POST fails, the selected choice and exact answer POST remain on screen so **Retry answer** resends the same request. A background refresh cannot erase that submission error.

Progress responses are ordered by curriculum identity and `updated_at`. The Web rejects a stale state snapshot, and it ignores a late save or run response after you switch Labs or questions, so older work cannot relock navigation or overwrite the newly selected editor.

## CLI loop

```bash
cd labs
uv run course status
uv run course unlock lab00
uv run course unlock lab01
uv run course test __COURSEKIT_FIRST_QUESTION__
uv run course grade lab01
uv run course submit lab01
git add lab01 && git commit -m "finish lab01"
uv run course checkpoint lab01
uv run course score
```

Direct `pytest` uses the same knowledge gate. Public tests live beside your code. Verified tests and reference implementations remain under `platform/course/` and are never copied into the learner workspace.

This separation prevents accidental hints during local study; it is not a secrecy boundary after publication. If you push the complete repository to a public Git host, anyone can inspect `platform/course/reference/` and `platform/course/tests/hidden/`. Keep the teacher projection private or publish a learner-only distribution when answers and verified tests must remain secret.

## Authoring and integrity

`platform/course/source/` is canonical: structured `lesson.json`, runnable example files, Lab metadata, code, and tests. Markdown lessons and `platform/course/authoring-spec.json` are compiler-generated views, not parallel editable sources. Regenerate or check artifacts with:

```bash
npm --prefix platform run course:compile
npm --prefix platform run course:check
npm test
npm run test:reference
```

The capstone grows in every Lab: __COURSEKIT_CAPSTONE__
