---
name: building-python-library-courses
description: Use when a user asks to build, create, author, or learn through a structured, language-selectable hands-on course project for a Python standard-library module, PyPI package, framework, or repository instead of receiving a one-off explanation.
---

# Build a Python Library Course

Create a standalone, source-backed course repository with cumulative Labs, learner code, pytest suites, a CLI, and a browser. Follow the seven stages in order.

## Choose the course language

On every fresh invocation, make the first question a course-language choice: ask the learner to choose exactly one course language before any other question or action. Ask even when the request already names a language. Support exactly `zh-CN` and `en`. Present Simplified Chinese (`zh-CN`) and English (`en`). Do not infer the choice from other context.

Ask only that question, then wait for the answer. Reject ambiguity. Keep the accepted locale fixed through research, readiness, generation, verification, and handoff; a language change starts a new route.

## requirements

Set `SKILL_DIR` to the absolute directory containing this `SKILL.md`:

```bash
export SKILL_DIR="/absolute/path/to/building-python-library-courses"
```

Use uv-managed Python 3.13, `uv`, Node.js 22.13+ with npm, and Git on macOS, Linux, or WSL2. Python 3.14 and native Windows are unverified. No GPU or external service is required.

The generated **authoring repository** contains learner and teacher projections. Hidden tests are not secret from repository readers. Version 0.2.0 does not provide an automated learner-only export. The supported secrecy path is to keep the complete teacher/authoring repository private. Run only trusted local code because Runner/pytest is not a hostile-code sandbox. Output must be standalone.

## Language contract

Write learner-facing lessons, readiness questions, quiz prompts, feedback, generated documentation, and course prose in the selected language. Ask readiness questions before authoring. Keep code, shell commands, identifiers, target API names, and official source titles and URLs in their original form. Use one locale without fallback. Readiness is private author-side routing input; learner material must not describe the learner's level, evidence, diagnostic result, profile, capability status, or preparation decision.

## Follow the seven-stage workflow

### 1. Inspect locally, then research officially

If the target is absent, ask after fixing language. Use behavior/evidence questions rather than beginner/intermediate labels, and reuse evidence already supplied by the learner. Claims of mastery are not evidence; direct admissions of not knowing may be.

Run the inspector before planning:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/inspect_python_target.py" TARGET --output /tmp/course-research.json
```

Treat the inspector as inventory. Research the public product surface from primary official sources, pin the taught version/range, record URLs, distinguish guarantees from implementation details, and report evidence gaps.

### 2. Apply the scope gate

Classify the public surface as **small** (3-5 graded Labs), **medium** (6-8), or **large**. For large targets, propose 2-4 tracks and wait until the user selects one track; then create 6-10 Labs. Require one environment, dependency chain, and cumulative capstone. Read [curriculum-contract.md](references/curriculum-contract.md) before writing the specification.

### 3. Design one cumulative route

Read [teaching-depth-contract.md](references/teaching-depth-contract.md) before route or specification design. After scope is fixed (and, for a large target, after the user selects one track), complete this readiness preflight before creating a specification or destination:

1. Research the selected route from primary official sources.
2. Build a learning-prerequisite DAG of capabilities, not package dependency metadata.
3. Create a UTF-8 route JSON with locale, selected route, sources, DAG, and one prediction, code-reading, or micro-code diagnostic per capability.
4. Create a temporary evidence JSON. Conversation evidence establishes mastery only with the matching diagnostic `question_id` and correct `answer_id`; free-form claims never do. Keep raw learner answers there only.
5. Run the assessor. On `needs_evidence`, ask its single `next_question`, append the response, and rerun; never repeat a resolved capability.
6. Continue only at `ready`. Confirm ordered prep and total preparatory time as an authoring decision; never copy diagnostic explanations into lessons.

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/assess_readiness.py" /path/to/route.json /path/to/evidence.json --output /tmp/readiness-plan.json
```

Author new specifications only as schema v3 with `course.audience.level: assessed`, `assessment: evidence-dialogue`, matching route/readiness data, per-unit `study_minutes`, `operational_contract`, runnable `trace`, and complete activity mappings. Schema v2 `basic-python` and `assessed/learner-self-report` remain compatibility inputs; never author new v2.

Make `preparatory_units[0]` the 15-30 minute `lab00`. Add only necessary `prep01`, `prep02`, ... in DAG-level and `python -> library -> domain` order. Prep takes 30-45 minutes, or 45-60 for derivation/lifecycle work. Invent none when mastered; do not impose a prep-count ceiling.

Before authoring learner-facing prose, read [chapter-writer-contract.md](references/chapter-writer-contract.md) and only the matching complete example: [Simplified Chinese](references/complete-teaching-example.zh-CN.md) or [English](references/complete-teaching-example.en.md). Prep chapters teach their subjects as ordinary course material, with no code, points, submissions, solutions, or hidden tests. Graded chapters connect concepts to quiz, code, and capstone. Neither may contain learner-gap, readiness, capability, evidence, or profile framing.

Give each graded Lab one new knowledge mainline and one usable increment to the same capstone. Lab 02+ may begin with the prior mechanism's graded official bridge, but that bridge does not justify a second unrelated mainline.

Enforce the teaching-equivalent -> official bridge cycle:

1. Make Lab 01 handwrite a small teaching-equivalent from lower-level CPU/offline primitives without importing the target API it explains.
2. Make Lab N+1 begin with a mandatory graded official bridge that calls the pinned API for Lab N's mechanism and compares declared observables.
3. Make that Lab handwrite the next conceptual layer without delegating to the official implementation.
4. Prevent every downstream learner file, reference, public or hidden test, and capstone from importing a prior mini implementation. Teach and use the official target API whenever later work needs an earlier capability.

CLI, Web, and Runner share the **chapter navigation gate**, **knowledge gate**, and **coding verification gate**, backed by a generic Web quiz and manifest CLI. V3 exposes only `lab00`, then each mastered prep, then `lab01`; no-gap courses go from `lab00` to `lab01`. Prep has no workspace, API access, or points. Formal Labs complete only after verified submissions. Apply [authoring-rubric.md](references/authoring-rubric.md) while designing lessons, exercises, and tests.

The parent locks IDs, sources, code/tests, module cycle, bridges, and handoffs, then creates one sanitized packet per `lab00`, `prepNN`, and `labNN` without diagnostic or learner-specific evidence. Use a distinct `fork_turns="none"` sub-agent per unit; never reuse a writer. Require exactly `unit_id`, natural textbook-style `tutorial`, structured `lesson`, and `quiz`, with connected explanations, first-use term definitions, concrete traces, boundaries, causes, and recovery—not repeated prose templates or word counts.

Run `scripts/assemble_chapter_fragments.py`; reject missing, duplicate, unexpected, extra-field, or locked-field drift. Use a new clean-context whole-course reviewer, and a new writer plus reviewer after any rejected unit. If the environment cannot create clean-context sub-agents, stop before learner-facing authoring.

### 4. Author the canonical specification

Author one UTF-8 schema-v3 JSON specification per [curriculum-contract.md](references/curriculum-contract.md). Set `course.lesson_format` to `tutorial-markdown-v1`; every unit contains assembled `tutorial` Markdown and a structured `lesson` sidecar. `preparatory_units` and private authoring profile must match `/tmp/readiness-plan.json`; raw evidence, profiles, and diagnostics never enter learner-facing manifests, content, docs, or APIs. Include pinned metadata, sources, deterministic examples, questions, code, and tests. The scaffolder creates the split canonical source.

Derive an opaque readiness-specific curriculum ID so routes never share progress; do not embed readable readiness data. Runtime schema versions remain independent.

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

- Read [curriculum-contract.md](references/curriculum-contract.md) for schema and mechanism-cycle contracts.
- Read [teaching-depth-contract.md](references/teaching-depth-contract.md) before readiness, route, or lesson design.
- Read [chapter-writer-contract.md](references/chapter-writer-contract.md) for sanitized clean-writer orchestration and review.
- Read only the example matching the selected course language before authoring learner-facing prose: [complete-teaching-example.zh-CN.md](references/complete-teaching-example.zh-CN.md) for `zh-CN`, or [complete-teaching-example.en.md](references/complete-teaching-example.en.md) for `en`. Use [complete-teaching-example.md](references/complete-teaching-example.md) only as the locale index.
- Read [authoring-rubric.md](references/authoring-rubric.md) for authoring quality.
- Read [architecture.md](references/architecture.md) for ownership, runtime, and UI contracts.
- Read [forward-test-rubric.md](references/forward-test-rubric.md) for local checks.
