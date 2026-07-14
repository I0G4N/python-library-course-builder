---
name: building-python-library-courses
description: Use when a user wants to learn a Python standard-library module, PyPI package, framework, or repository through a structured hands-on course project instead of a one-off explanation.
---

# Build a Python Library Course

Turn one Python target into a standalone, source-backed learning repository. The result must teach concepts, require the learner to complete code, grade that code through public and hidden pytest suites, and expose the same curriculum through a CLI and a browser.

In the commands below, set `SKILL_DIR` to the absolute directory that contains this `SKILL.md`.

## prerequisites

- Codex with Skill support for invoking this workflow.
- Python 3.13 for every bundled inspection, validation, scaffolding, and verification command.
- `uv` for reproducible, isolated Python execution.
- Node.js 22.13 or newer with npm for the generated Web workspace and its contract tests.
- Git for generated-project checkpoints and release verification.

The supported local environments are macOS, Linux, and WSL2; native Windows is not a verified path. No GPU, API key, cloud account, paid service, or external database is required for mandatory course generation and grading.

Every generated project is an **authoring repository** containing both learner and teacher projections. Hidden tests are not secret when that complete repository is distributed: they are withheld from the normal learner workspace to prevent accidental hints, not protected from a user who can inspect the filesystem. Use a learner-only export or private teacher repository when actual secrecy is required.

Run only trusted local code. The generated Runner and pytest isolation reduce ordinary grading side effects, but they are not an operating-system sandbox for hostile submissions.

## Non-negotiable outcome

Generate one repository that contains:

- `labs/lab00` as the ungraded foundations and environment check;
- a linear `lab01 -> labNN` sequence with adaptive depth and a cumulative capstone;
- a schema-v2 course for a learner who knows only basic Python, with every graded Lab sized for 30-45 minutes;
- definitions, purpose, step-by-step mechanisms, mental models, design reasons, benefits, tradeoffs, invariants, boundaries, pitfalls, and source-backed claims in every Lab;
- at least two examples per Lab: one CPU/offline runnable example and one diagnostic that teaches wrong -> symptom -> cause -> fix;
- a mechanism cycle in which Lab N handwrites a teaching-equivalent and Lab N+1 begins with a graded official bridge for that mechanism;
- import-boundary tests proving later work and the capstone do not depend on a prior mini implementation;
- compiler-owned `source_policy` metadata and a shared CLI/Runner AST preflight that rejects target delegation before pytest;
- incomplete learner code, public pytest tests, private reference code, and hidden grader tests;
- `unlock`, `test`, `grade`, `submit`, `checkpoint`, and `score` CLI operations;
- a CodeMirror Web editor, lesson renderer, Runner API, progress state, and Git checkpoints;
- one shared three-gate progression across CLI and Web: the chapter navigation gate, knowledge gate, and coding verification gate;
- a generic Web quiz generated from course data, with later Labs disabled until their declared dependency is completed;
- a quiz-first Web workspace: Lab 00 has no code workspace, and a graded Lab mounts its code workspace and question-scoped file API only after foundation and current-Lab knowledge are mastered;
- a desktop three-column shell with two keyboard-accessible separators, minimum widths, a collapsible sidebar, and validated per-course localStorage preferences; medium and small layouts have no resize separators;
- setup, launch, shutdown, and local deployment instructions.

The generated repository must be standalone. Never link or import files from the Skill directory or another learning project.

The bundled schema-v2 template targets Python `>=3.12,<3.14`, and all Skill automation runs on Python 3.13. A course specification must include Python 3.13 and exclude Python 3.14. If the target can only be taught on Python 3.14 or newer, stop and upgrade the template and its lockfiles before scaffolding; do not weaken this compatibility gate.

## Workflow

### 1. Inspect locally, then research officially

Run the bundled inspector before planning:

Run Skill automation with uv-managed Python 3.13 even when the host's `python3` is older:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/inspect_python_target.py" TARGET --output /tmp/course-research.json
```

Treat inspection as a local inventory, not as factual research. Verify the target and its version against primary official sources: the Python documentation and CPython source for standard-library modules; official project documentation, package metadata, release notes, and upstream source for third-party targets. Pin the version or version range taught, record source URLs, and distinguish documented guarantees from implementation details. Do not use generated tutorials, search snippets, or recollection as curriculum authority.

If official material is missing or contradictory, stop and report the evidence gap instead of inventing a contract.

### 2. Apply the scope gate

Classify the target from its public API and product surface, not name recognition alone:

- **small:** 3-5 graded Labs;
- **medium:** 6-8 graded Labs;
- **large:** propose 2-4 coherent product tracks and stop before creating files. After the user selects one track, generate 6-10 graded Labs for that track only.

Do not produce a shallow survey of a broad framework. A selected track must have one executable environment, one coherent dependency chain, and one capstone. Read [curriculum-contract.md](references/curriculum-contract.md) before writing the specification.

### 3. Design one cumulative route

Map official capabilities to prerequisites, then to observable learner outcomes. Present the proposed route and any material assumptions. Ask for a choice only when a track, environment, optional dependency, or destructive destination decision changes the course scope; otherwise proceed with the bounded route.

Treat the reader as a beginner who has basic Python but no target-library, distributed-systems, ML-systems, or framework knowledge. Budget 30-45 minutes per graded Lab. Each Lab must add a usable increment to the same capstone and must be understandable independently from its prerequisites through an explicit recap.

Use the mechanism-then-API cycle throughout the route:

1. Lab 01 handwrites a small teaching-equivalent from lower-level, CPU/offline primitives. It must not import the target API it is meant to explain.
2. Lab N, for N greater than 1, starts with a mandatory graded official bridge that calls the pinned official API corresponding to Lab N-1 and compares declared observables.
3. The same Lab then handwrites the next conceptual layer. Tests must distinguish understanding from delegating back to the official implementation.
4. No downstream code, public/hidden test, or capstone may import a prior mini implementation. When a prior capability is needed, teach and use the official target API directly in the current Lab.

A teaching-equivalent is a deliberately small model of a public mechanism, not a copy of upstream source and not a claim of production equivalence. Avoid isolated API drills, duplicated concepts, and Labs that cannot be graded deterministically offline. Apply [authoring-rubric.md](references/authoring-rubric.md) to lessons, exercises, and tests.

### 4. Author the canonical specification

Create a UTF-8 JSON specification that follows [curriculum-contract.md](references/curriculum-contract.md). Include:

- pinned target metadata and an explicit official-source registry;
- `schema_version: 2`, an explicit `course.audience` contract, foundations, ordered Labs, stable concept/outcome IDs, source IDs, and capstone increments;
- a structured lesson outline for every chapter containing prerequisites, the motivating problem, outcomes, full concept explanations, examples, capstone bridge, and summary;
- at least two examples in every outline, including runnable code with its command and expected output plus a diagnostic wrong -> symptom -> cause -> fix path;
- execution-trace and diagnostic quiz questions with 3-4 stable choice IDs, feedback for every choice, an `answer_id`, and concept/outcome mappings;
- answer positions distributed across all available positions, with no one position exceeding 40% of the course bank;
- `module_cycle.reimplementation` for every graded Lab and `official_bridge` for every Lab after Lab 01, including observables and comparison cases;
- quiz questions and 1-3 coding interfaces per graded Lab, each mapped to stable concept/outcome IDs and classified as `official_bridge`, `reimplementation`, or `integration`;
- starter, reference, public-test, and hidden-test content for every interface;
- points derived from declared exercises, never fixed totals.

For every runnable example, if its lesson-relative file is `{path}`, declare the command exactly as `python {path}`. For every Lab after Lab 01, require the bridge `official_symbols` set to equal the previous reimplementation `target_symbols`, require every `required_imports` root directly in both bridge projections, and require every reimplementation question to use its declared `learner_file`.

Question objects use a closed schema. The compiler emits, rather than accepts from authors, a learner-safe `source_policy` for every question: required roots, forbidden target roots, prior mini modules, prior course roots, and the current local root. CLI and Runner apply the same AST preflight before pytest, including aliased `from` imports, literal `importlib.import_module(...)`, literal `__import__(...)`, and reachable same-Lab helpers.

Keep examples and tests CPU/offline runnable, deterministic, and free of paid credentials. Use temporary directories and fakes at network, clock, process, GPU, and OS boundaries. Accelerator-only APIs may be taught only through config, metadata, source-backed traces, or fail-closed preflight objects; they are never a mandatory execution path.

The canonical source is split and human-reviewable: structured `lesson.json`, example files, Lab metadata, starter/reference code, and tests. Do not store a second editable authoring specification in the generated repository. The compiler reconstructs a private compiler-generated parity snapshot and must reject a direct split-source edit that violates the same v2 contract.

Encode progression as three separate gates. Lab 00 and the first graded Lab are initially navigable; each later Lab becomes navigable only after its dependency is completed. A Lab's knowledge check becomes answerable only after its knowledge prerequisites, while coding remains blocked until both foundation and current-Lab knowledge are mastered. Mark a Lab complete only after every declared coding question passes verified submission. CLI and Web/Runner mutations must persist one curriculum-scoped state, and direct pytest must read that same state rather than a parallel unlock system.

Keep Lab 00 lesson-and-quiz only: it has no code workspace at any viewport size. For every graded Lab, hide the complete code/result column and do not request workspace files until both foundation and current-Lab knowledge are complete. The Runner must repeat this rule for its question-scoped file API. This is a workflow gate, not source secrecy: learner files remain locally inspectable.

On desktop, render sidebar, lesson, and code/result as three columns with two keyboard-accessible separators. Preserve declared minimum widths, let the sidebar collapse, and store validated, clamped preferences in per-course localStorage. Medium and small layouts use their responsive navigation/stacking and have no resize separators.

### 5. Scaffold only into an empty destination

Run:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/validate_course.py" /path/to/spec.json
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/scaffold_course.py" /path/to/spec.json /path/to/empty-output
```

The scaffolder must fail before writing when the destination is a file, symlink, or non-empty directory. It must also fail on unknown template tokens, unsafe paths, missing references, unresolved source IDs, invalid Lab dependencies, or an unresolved large-target track gate. Never add an overwrite flag to bypass these checks.

Schema-v2 generation gives the course a new, incompatible curriculum ID so stale v1 progress cannot unlock semantically different work. Preserve the progress-state, artifact-index, engine, and layout schema versions unless their own contracts actually change; curriculum schema and runtime-state schema are separate concerns.

The template architecture and ownership boundaries are documented in [architecture.md](references/architecture.md).

### 6. Prove RED, then GREEN

Verify the generated project:

```bash
cd /path/to/project
npm run setup
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/verify_learning_project.py" . --full --json /tmp/course-verification.json
```

Do not call the course complete unless fresh evidence shows all of the following:

1. learner starter tests fail only at declared incomplete interfaces;
2. the private reference projection passes public and hidden pytest suites;
3. CLI unlock/test/grade/submit/checkpoint/score behavior works;
4. Web builds and its generic Web quiz proves the chapter navigation gate, knowledge gate, quiz-first code visibility, accessible desktop resizing, responsive stacking, coding verification gate, fail-closed loading, retry, and stale-response behavior;
5. the Runner functionally proves state, redacted knowledge, answer, locked question-scoped file access, locked run, verified completion, and next-Lab unlock APIs against a disposable learner copy;
6. learner-visible files exclude reference implementations and hidden tests;
7. no template token, foreign branding, fixed Lab count, fixed score denominator, unsafe symlink, or absolute source path remains.

Also inspect the compiled `lesson_outline` and Markdown fallback for every chapter, run every declared runnable example, verify each diagnostic contains wrong code, symptom, cause, and fixed code, and prove the official-bridge/no-prior-mini import boundaries from generated source rather than prose alone.

Use [forward-test-rubric.md](references/forward-test-rubric.md) for fresh-agent and broad-target checks. Fix the generator or template when a forward test exposes a systematic defect; do not hand-edit only the generated example.

### 7. Hand off the learning loop

Give the user the exact setup, launch, first-Lab, test, score, and shutdown commands from the generated README. Explain that repository-contained hidden tests are only separated from the learner workspace, not secret after public hosting. Report the pinned target version, Lab count, capstone, verification report path, and any platform limitations.

The scaffolder initializes Git only inside the generated repository and creates a clean baseline checkpoint. If the user publishes the complete repository, warn that reference implementations and hidden tests under `platform/course/` become inspectable; use a private teacher distribution when actual secrecy matters.

## Resource map

- [architecture.md](references/architecture.md): engine, content, learner, and privacy boundaries.
- [curriculum-contract.md](references/curriculum-contract.md): specification shape and adaptive sizing rules.
- [authoring-rubric.md](references/authoring-rubric.md): lesson, exercise, and grader quality criteria.
- [forward-test-rubric.md](references/forward-test-rubric.md): end-to-end acceptance and regression checks.
- `assets/course-template/`: standalone CourseKit project template; copy through the scaffolder, not manually.
- `scripts/inspect_python_target.py`: local target inventory and initial size signal.
- `scripts/scaffold_course.py`: fail-closed deterministic renderer.
- `scripts/validate_course.py`: specification and source-contract validator.
- `scripts/verify_learning_project.py`: RED/GREEN, CLI, Web, Runner, privacy, and residue verifier.
