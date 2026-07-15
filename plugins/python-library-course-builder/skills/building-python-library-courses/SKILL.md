---
name: building-python-library-courses
description: Use when a user asks to build, create, author, or learn through a structured, language-selectable hands-on course project for a Python standard-library module, PyPI package, framework, or repository instead of receiving a one-off explanation.
---

# Build a Python Library Course

Create a standalone, source-backed course repository with cumulative Labs, learner code, pytest suites, a CLI, and a browser. Follow the seven stages in order.

## Choose the course language

On every fresh invocation, make the first question a course-language choice: ask the learner to choose exactly one course language before any other question or action. Ask even when the request already names a language. Support exactly `zh-CN` and `en`. Present them as Simplified Chinese (`zh-CN`) and English (`en`). Do not infer the choice from the request language, prior threads, locale, target, or destination.

Ask only the language question, then wait for the answer. If the answer is unsupported or ambiguous, ask the learner to choose `zh-CN` or `en` again and do nothing else. Treat the accepted locale as immutable input to route research, readiness, specification, generation, verification, and handoff. A later language change starts a new route/readiness cycle; never relabel an existing plan or course.

## requirements

Set `SKILL_DIR` to the absolute directory containing this `SKILL.md`:

```bash
export SKILL_DIR="/absolute/path/to/building-python-library-courses"
```

Run bundled scripts with uv-managed Python 3.13. Require `uv`, Node.js 22.13+ with npm, and Git. Support macOS, Linux, and WSL2; native Windows is unverified. Mandatory generation and grading need no GPU or external service.

The generated **authoring repository** contains learner and teacher projections. Hidden tests are not secret from anyone who can inspect it. Version 0.2.0 does not provide an automated learner-only export. The supported secrecy path is to keep the complete teacher/authoring repository private.

Run only trusted local code: Runner/pytest isolation is not a hostile-code sandbox. Keep output standalone; never link to or import from the Skill or another course.

Require Python 3.13 and exclude Python 3.14. Upgrade the template and lockfiles before teaching a newer-only target.

## Language contract

Write learner-facing lessons, readiness questions, quiz prompts, feedback, generated documentation, and course prose in the selected language. Keep code, shell commands, identifiers, target API names, and official source titles and URLs in their original form. Use one locale consistently; do not mix locales or silently fall back. Language choice is not readiness evidence and raw answers remain temporary.

## Follow the seven-stage workflow

### 1. Inspect locally, then research officially

If the target is absent, ask for it after the language choice is fixed and stop until known. Use short behavior/evidence questions rather than beginner/intermediate labels, and reuse evidence from code and conversation already supplied by the learner. A claim of mastery is not evidence; a direct admission of not knowing may establish a missing capability.

Run the inspector before planning:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/inspect_python_target.py" TARGET --output /tmp/course-research.json
```

Treat the report as inventory, not research. Use primary official sources for the target's public and product surface, pin the taught version/range, record URLs, and distinguish documented guarantees from implementation details. Report missing or contradictory evidence.

### 2. Apply the scope gate

Classify the target from its public API and product surface:

- Select **small** for 3-5 graded Labs.
- Select **medium** for 6-8 graded Labs.
- For **large**, propose 2-4 coherent tracks and wait until the user selects one track; then create 6-10 graded Labs for it.

Require one environment, dependency chain, and cumulative capstone. Read [curriculum-contract.md](references/curriculum-contract.md) before writing the specification.

### 3. Design one cumulative route

Read [teaching-depth-contract.md](references/teaching-depth-contract.md) before route or specification design. After scope is fixed (and, for a large target, after the user selects one track), complete this readiness preflight before creating a specification or destination:

1. Research the selected route from primary official sources as needed beyond the target-surface evidence from Stage 1.
2. Build a learning-prerequisite DAG of learner capabilities, not package dependency metadata.
3. Create a UTF-8 route JSON containing the selected locale, selected route, fixed official sources, the capability DAG, and one prediction, code-reading, or micro-code diagnostic per capability in that locale.
4. Create a temporary evidence JSON containing reusable code evidence and prior diagnostic responses. Conversation evidence establishes mastery only when its item carries the matching route diagnostic `question_id` and correct `answer_id`; free-form claims never do. Keep raw learner answers and code evidence in this temporary report only.
5. Run the deterministic assessor. If it returns `needs_evidence`, ask exactly its single `next_question`, append the response to the temporary evidence JSON, and rerun. Never ask a resolved capability again.
6. Continue only when it returns `ready`. Present the ordered preparatory units and total preparatory time before authoring.

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/assess_readiness.py" /path/to/route.json /path/to/evidence.json --output /tmp/readiness-plan.json
```

Author new specifications only as schema v3 with `course.audience.level: assessed`, `assessment: evidence-dialogue`, matching route/readiness data, per-unit `study_minutes`, `operational_contract`, runnable `trace`, and complete activity mappings. Schema v2 `basic-python` and `assessed/learner-self-report` remain compatibility inputs; never author new v2.

Make `preparatory_units[0]` the 15-30 minute `lab00` orientation. Add only necessary `prep01`, `prep02`, ... units in DAG-level and `python -> library -> domain` order. Prep takes 30-45 minutes, or 45-60 with a derivation/lifecycle reason. Invent none when all capabilities are mastered; do not impose a prep-count ceiling.

Before authoring learner-facing prose, read only the complete example matching the selected course language: [Simplified Chinese](references/complete-teaching-example.zh-CN.md) for `zh-CN` or [English](references/complete-teaching-example.en.md) for `en`. Each `prepNN` connects a cognitive anchor, definition, route need, concrete value flow, boundary, recovery, trace, diagnosis, and quiz, but has no code, points, submission, solution, or hidden test. Graded chapters connect problem, prediction, contract, value flow, boundaries, diagnosis, quiz, code, and capstone.

Give each graded Lab one new knowledge mainline and one usable increment to the same capstone. Lab 02+ may begin with the prior mechanism's graded official bridge, but that bridge does not justify a second unrelated mainline.

Enforce the teaching-equivalent -> official bridge cycle:

1. Make Lab 01 handwrite a small teaching-equivalent from lower-level CPU/offline primitives without importing the target API it explains.
2. Make Lab N+1 begin with a mandatory graded official bridge that calls the pinned API for Lab N's mechanism and compares declared observables.
3. Make that Lab handwrite the next conceptual layer without delegating to the official implementation.
4. Prevent every downstream learner file, reference, public or hidden test, and capstone from importing a prior mini implementation. Teach and use the official target API whenever later work needs an earlier capability.

CLI, Web, and Runner share the **chapter navigation gate**, **knowledge gate**, and **coding verification gate**, backed by a generic Web quiz and manifest CLI. V3 exposes only `lab00`, then each mastered prep, then `lab01`; no-gap courses go from `lab00` to `lab01`. Prep has no workspace, API access, or points. Formal Labs complete only after verified submissions. Apply [authoring-rubric.md](references/authoring-rubric.md) while designing lessons, exercises, and tests.

### 4. Author the canonical specification

Author one UTF-8 schema-v3 JSON specification per [curriculum-contract.md](references/curriculum-contract.md). `preparatory_units` and the profile must match `/tmp/readiness-plan.json`; exclude raw evidence. Include pinned metadata, official sources, lessons, deterministic examples, Lab questions, starter/reference code, and public/hidden tests. The scaffolder creates the split canonical source.

Use `<course-id>-v3-<readiness_summary>` so learner profiles never share progress. Other runtime schema versions remain independent.

Use [architecture.md](references/architecture.md) for ownership, runtime, layout, and privacy. Do not invent parallel schemas, editable parity snapshots, or unlock state; fake nondeterministic boundaries.

### 5. Scaffold only into an empty destination

Run validation before scaffolding:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/validate_course.py" /path/to/spec.json --readiness-plan /tmp/readiness-plan.json
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/scaffold_course.py" /path/to/spec.json /path/to/empty-output --readiness-plan /tmp/readiness-plan.json
```

V2 retains no-plan commands. V3 rejects a missing, incomplete, tampered, or mismatched plan before writes. Use only a missing/empty real destination; never add overwrite.

### 6. Prove RED, then GREEN

Read [architecture.md](references/architecture.md) before validating the generated runtime and ownership boundaries.

Set up and verify the generated project:

```bash
cd /path/to/project
npm run setup
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/verify_learning_project.py" . --full --json /tmp/course-verification.json
```

Require fresh evidence that:

- the untouched learner starter is RED only at declared incomplete interfaces, never because of collection, syntax, dependency, or timeout failures;
- the private reference projection is GREEN for every public and hidden test; and
- CLI, Web, Runner, progression, privacy, path safety, and residue checks are GREEN.

Use [forward-test-rubric.md](references/forward-test-rubric.md) for the required local generated-project acceptance matrix. Fix generator-level failures, regenerate, and rerun instead of patching output.

### 7. Hand off the learning loop

Copy setup, launch, first-Lab, test, score, and shutdown commands from the generated README. Report target version, Lab count, capstone, verification path, and limitations; repeat the privacy warning before hosting.

## Load detailed references only when needed

- Read [curriculum-contract.md](references/curriculum-contract.md) for the schema, sizing, lesson, question, source-policy, and mechanism-cycle contracts.
- Read [teaching-depth-contract.md](references/teaching-depth-contract.md) before readiness, route, or lesson design for adaptive foundations, operational depth, concrete traces, activity alignment, and time tiers.
- Read only the example matching the selected course language before authoring learner-facing prose: [complete-teaching-example.zh-CN.md](references/complete-teaching-example.zh-CN.md) for `zh-CN`, or [complete-teaching-example.en.md](references/complete-teaching-example.en.md) for `en`. Use [complete-teaching-example.md](references/complete-teaching-example.md) only as the locale index.
- Read [authoring-rubric.md](references/authoring-rubric.md) for teaching depth, exercise quality, and grader quality.
- Read [architecture.md](references/architecture.md) for generated-project ownership, runtime, security, progression, and UI contracts.
- Read [forward-test-rubric.md](references/forward-test-rubric.md) for required local generated-project checks.
