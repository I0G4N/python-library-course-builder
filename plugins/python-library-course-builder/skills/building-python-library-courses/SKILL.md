---
name: building-python-library-courses
description: Use when a user asks to build, create, author, or learn through a structured, Chinese-first hands-on course project for a Python standard-library module, PyPI package, framework, or repository instead of receiving a one-off explanation.
---

# Build a Python Library Course

Create one standalone, source-backed authoring repository that teaches a Python target through a cumulative Lab sequence, incomplete learner code, public and hidden pytest suites, a CLI, and a browser. Follow the seven stages in order.

## requirements

Set `SKILL_DIR` to the absolute directory containing this `SKILL.md`:

```bash
export SKILL_DIR="/absolute/path/to/building-python-library-courses"
```

Run every bundled script with uv-managed Python 3.13. Require Python 3.13, `uv`, Node.js 22.13 or newer with npm, and Git. Support macOS, Linux, and WSL2; treat native Windows as unverified. Require no GPU, API key, cloud account, paid service, or external database for mandatory generation and grading.

Treat the generated project as an **authoring repository** containing learner and teacher projections. Explain that hidden tests are not secret from anyone who can inspect the complete repository; they only prevent accidental hints. Version 0.1.0 does not provide an automated learner-only export. The supported secrecy path is to keep the complete teacher/authoring repository private.

Run only trusted local code. Treat Runner and pytest isolation as protection from ordinary grading side effects, not as an operating-system sandbox for hostile submissions. Stop rather than execute an untrusted submission without an explicitly authorized operating-system sandbox. Keep the generated repository standalone: never link to or import from the Skill directory or another learning project.

Keep course requirements compatible with Python 3.13 and incompatible with Python 3.14. Stop and upgrade the template and lockfiles before teaching a target that requires Python 3.14 or newer.

## Language contract

Write learner-facing lessons, quiz prompts, feedback, generated documentation, and course prose in Simplified Chinese. Keep code, shell commands, identifiers, target API names, and official source titles and URLs in their original form. Version 0.1.0 has no language switch.

## Follow the seven-stage workflow

### 1. Inspect locally, then research officially

If the target is absent, ask for it and stop until known. Assess general Python readiness with short behavior/evidence questions rather than beginner/intermediate labels, and reuse evidence already supplied by the user instead of re-asking.

Run the inspector before planning:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/inspect_python_target.py" TARGET --output /tmp/course-research.json
```

Treat the report as a local inventory, not as factual research. Research the target's public and product surface from primary official sources so Stage 2 can classify it: use Python documentation and CPython source for standard-library modules; use official documentation, package metadata, release notes, and upstream source for third-party targets. Pin the taught version or range, record source URLs, and distinguish documented guarantees from implementation details. Stop and report an evidence gap when official sources are missing or contradictory.

### 2. Apply the scope gate

Classify the target from its public API and product surface:

- Select **small** for 3-5 graded Labs.
- Select **medium** for 6-8 graded Labs.
- Select **large** by proposing 2-4 coherent product tracks, then stop before writing any specification or destination file. After the user selects one track, create 6-10 graded Labs for that track only.

Require one executable environment, one dependency chain, and one cumulative capstone. Read [curriculum-contract.md](references/curriculum-contract.md) before writing the specification.

### 3. Design one cumulative route

Read [teaching-depth-contract.md](references/teaching-depth-contract.md) before route or specification design. After scope is fixed (and, for a large target, after the user selects one track), complete this selected-route readiness sequence before authoring:

1. Research the selected route from primary official sources as needed beyond the target-surface evidence from Stage 1.
2. Build a learning-prerequisite DAG of learner capabilities, not package dependency metadata.
3. Ask only about route-relevant Python, library, and domain capabilities not already evidenced.
4. Summarize capability titles as **safe to assume**, **teach in Lab 00**, or **too large for this route**.
5. If multiple prerequisite layers cannot fit a focused 45-60 minute Lab 00, stop before writing the schema or destination file and offer a prerequisite course or a narrower track. Never serialize a large-gap state as a completed target specification.

Author new specifications with `course.audience.level: assessed`, a `learner-self-report` prerequisite profile, exact per-unit `study_minutes`, a concept `operational_contract`, a runnable `trace`, and complete concept/outcome activity mappings. Treat legacy `basic-python` as validator compatibility input, not the authoring default.

Use Lab 00 only for evidenced foundations. Give each graded Lab one new knowledge mainline and one usable increment to the same capstone. Lab 02+ may also begin with the prior mechanism's graded official bridge; that bridge does not justify a second unrelated mainline. Apply the exact adaptive time tiers and positive chapter recipe from the teaching-depth contract.

Before authoring learner-facing prose, read [complete-teaching-example.md](references/complete-teaching-example.md) as the positive depth model. For every evidenced Lab 00 gap, connect the learner's existing cognitive anchor to a definition, current-route need, complete concrete value flow, misconception or boundary, and a recovery check. For every graded chapter, move from its project problem and plain-language prediction through the exact contract and one complete value flow into valid/boundary cases, diagnosis, quiz, coding, and the capstone increment. Keep the two Lab 00 layers explicit and keep one new knowledge mainline per graded chapter.

Enforce the teaching-equivalent -> official bridge cycle:

1. Make Lab 01 handwrite a small teaching-equivalent from lower-level CPU/offline primitives without importing the target API it explains.
2. Make Lab N+1 begin with a mandatory graded official bridge that calls the pinned API for Lab N's mechanism and compares declared observables.
3. Make that Lab handwrite the next conceptual layer without delegating to the official implementation.
4. Prevent every downstream learner file, reference, public or hidden test, and capstone from importing a prior mini implementation. Teach and use the official target API whenever later work needs an earlier capability.

Apply one shared progression model across CLI and Web: the **chapter navigation gate**, **knowledge gate**, and **coding verification gate**. Drive the knowledge gate with a generic Web quiz and mark a Lab complete only after every declared coding question passes verified submission. Apply [authoring-rubric.md](references/authoring-rubric.md) while designing lessons, exercises, and tests.

### 4. Author the canonical specification

Author one UTF-8 schema-v2 JSON specification exactly as [curriculum-contract.md](references/curriculum-contract.md) defines it. Include pinned target metadata, an official-source registry, source-backed lessons, deterministic CPU/offline examples, questions, incomplete starter code, private reference code, public tests, and hidden tests. Keep Lab and outcome identifiers stable and derive points from declared exercises. Treat this JSON as authoring input. Let the scaffolder create the split canonical source inside the generated repository.

Use [architecture.md](references/architecture.md) for compiler ownership, source preflight, progression state, CLI, Web, Runner, layout, and privacy boundaries. Do not invent parallel schemas, editable parity snapshots, or alternate unlock state. Keep network, clock, process, GPU, and operating-system boundaries deterministic through temporary directories and fakes.

### 5. Scaffold only into an empty destination

Run validation before scaffolding:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/validate_course.py" /path/to/spec.json
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/scaffold_course.py" /path/to/spec.json /path/to/empty-output
```

Write only to a missing or empty real directory. Require the scaffolder to reject a file, symlink, or non-empty directory before its first write. Never bypass the empty destination guard or add an overwrite flag.

### 6. Prove RED, then GREEN

Read [architecture.md](references/architecture.md) before validating the generated runtime and ownership boundaries.

Set up and verify the generated project:

```bash
cd /path/to/project
npm run setup
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/verify_learning_project.py" . --full --json /tmp/course-verification.json
```

Require fresh completion evidence that:

- the untouched learner starter is RED only at declared incomplete interfaces, never because of collection, syntax, dependency, or timeout failures;
- the private reference projection is GREEN for every public and hidden test; and
- CLI, Web, Runner, the three progression gates, learner-artifact privacy, path safety, and residue checks are GREEN.

Use [forward-test-rubric.md](references/forward-test-rubric.md) for the required local generated-project acceptance matrix. Fix systematic failures in the Skill, generator, or template; regenerate into an empty destination and rerun the full verifier instead of hand-editing one generated course.

### 7. Hand off the learning loop

Copy the exact setup, launch, first-Lab, test, score, and shutdown commands from the generated README. Report the pinned target version, graded Lab count, capstone, verification report path, and platform limitations. Repeat the authoring-repository and hidden-test warning before any public hosting handoff.

## Load detailed references only when needed

- Read [curriculum-contract.md](references/curriculum-contract.md) for the schema, sizing, lesson, question, source-policy, and mechanism-cycle contracts.
- Read [teaching-depth-contract.md](references/teaching-depth-contract.md) before readiness, route, or lesson design for adaptive foundations, operational depth, concrete traces, activity alignment, and time tiers.
- Read [complete-teaching-example.md](references/complete-teaching-example.md) before authoring learner-facing prose for a complete Lab 00 and graded-JSON positive example.
- Read [authoring-rubric.md](references/authoring-rubric.md) for teaching depth, exercise quality, and grader quality.
- Read [architecture.md](references/architecture.md) for generated-project ownership, runtime, security, progression, and UI contracts.
- Read [forward-test-rubric.md](references/forward-test-rubric.md) for required local generated-project checks.
