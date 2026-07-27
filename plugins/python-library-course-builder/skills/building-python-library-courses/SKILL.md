---
name: building-python-library-courses
description: Use when a user asks to build, create, author, regenerate, update, upgrade, or learn through a structured, language-selectable hands-on course project for a Python standard-library module, PyPI package, framework, or repository, including fully regenerating an explicitly located course after the Skill's authoring capability changes.
---

# Build a Python Library Course

## Choose the course language

For a fresh course, ask exactly one question before any other action: choose Simplified Chinese (`zh-CN`) or English (`en`). Ask even when the request already suggests a language. Keep the accepted locale fixed through research, authoring, verification, and handoff.

For an explicit existing course, read and lock its locale, target/version, track, and route intent. Do not ask again or silently change them.

## Requirements and privacy

Set `SKILL_DIR` to this Skill's absolute directory. Require `uv`, Python 3.13, and Git on macOS, Linux, or WSL2. A generated v4 course uses one Python environment and one local port; it does not install Node. Node/Web build, browser, dual-locale, timeout, cleanup, and Runner security matrices belong to the shared Skill/runtime CI.

The learner and sibling author directories are separate projections. The author directory contains answers, solutions, and hidden tests and must remain private. Hidden tests are an assessment boundary, not a hostile-code secrecy guarantee.

## Build a v4 course

### 1. Inspect, research, and decide the route

Inspect the target locally, then verify facts against primary official sources:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project \
  python "$SKILL_DIR/scripts/inspect_python_target.py" TARGET \
  --output /tmp/course-research.json
```

Pin the taught version/range. Separate documented guarantees from version-pinned implementation facts. Classify scope as small, medium, or large; for a large target propose 2–4 coherent tracks and wait for the learner's selection.

Run the evidence-based readiness flow in [curriculum-contract.md](references/curriculum-contract.md). Use it only to decide which ordinary `prepNN` chapters are needed. Never expose raw answers, capability labels, or diagnostic framing in the generated course.

The parent Agent owns the one cumulative route, chapter order, official facts, task IDs, public interfaces, dependency direction, test selectors, and non-overlapping owned paths. Keep one knowledge mainline per chapter and one runnable project increment per graded chapter.

### 2. Create one private Depth Brief per chapter

Read [teaching-depth-contract.md](references/teaching-depth-contract.md) and [chapter-writer-contract.md](references/chapter-writer-contract.md). Build an ephemeral brief with exactly the information needed by that chapter:

```text
chapter_id
chapter_kind
core_question
project_increment
required_facts
interface_boundary
walkthrough_case
boundary_case
design_choice
credible_alternative
previous_handoff
next_handoff
official_sources
task_contracts
owned_paths
```

`required_facts` contains 3–6 chapter-relevant facts grounded in the listed official sources. The brief is prompt context, not a course schema or generated artifact. Do not add scores, depth bands, word ranges, concept/outcome mappings, readiness evidence, other chapters' prose, or a complete teaching example.

Apply chapter-kind depth:

- `lab00` explains setup, course use, and demonstrates the complete learn–quiz–code–test–submit loop without owning a coding task; do not force architecture analysis.
- `prepNN` makes one prerequisite mechanism predictable for the next Lab.
- ordinary `labNN` makes one implementable mechanism predictable through its value/control flow, interface, design choice, credible alternative, boundary, and engineering tradeoffs.
- integration/capstone uses one end-to-end case to compose prior public interfaces and explain dependencies, failure propagation, and system tradeoffs.

### 3. Launch exactly one Writer per chapter

Use one fresh `fork_turns="none"` sub-Agent per chapter. Each Writer receives only its Depth Brief, relevant official facts, locked task contracts, and owned paths. It produces one complete package:

```text
packages/<chapter-id>/
├── tutorial.md
├── terms.json
├── quiz.json
├── starter/src/...       # graded chapters only
├── solution/src/...      # graded chapters only
├── tests/public/...      # graded chapters only
├── tests/hidden/...      # graded chapters only
└── examples/...          # optional
```

Give every Writer this instruction:

> Write a natural, connected textbook chapter rather than a field manual. Organize it around the core question and carry the walkthrough case through the complete mechanism. Naturally explain the essential definitions, component responsibilities, caller/implementer interface, data or control flow, selected design, one credible alternative, benefits and costs, and the boundary case's symptom, cause, and recovery. Choose headings and length for the subject. Keep the quiz, code, and tests on the same case and behavior boundary.

In the same call, the Writer silently plans, writes, checks, and revises until the learner can define the mechanism, predict the walkthrough, see responsibilities and interfaces, compare the design and alternative, state benefits/costs/invariants, recover from the boundary case, and complete the coding task. It outputs only final package files—never its checklist or reasoning.

Do not run a whole-course Reviewer, replacement Writer, depth evaluator, word-count check, semantic completeness check, padding/repetition detector, or concept/outcome/trace validator.

### 4. Scaffold learner and author projections

Read [architecture.md](references/architecture.md). Author a temporary schema-v4 `route.json` containing only runtime/mechanical metadata and locked task/path contracts described by [curriculum-contract.md](references/curriculum-contract.md).

Scaffold once; its internal validation makes a separate pre-validation call unnecessary:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project \
  python "$SKILL_DIR/scripts/scaffold_course.py" /tmp/route.json /path/to/course \
  --chapter-packages /tmp/packages
```

The scaffolder checks only IDs, required files, JSON/TOML parsing, quiz option references, owned-path safety/conflicts/symlinks, Python syntax, selectors, declared symbols, and learner/author isolation. On failure, send the short mechanical error list to the original chapter Writer once. If it still fails, stop and report; do not launch a new Writer.

Existing schema-v2/v3 courses remain readable and unchanged. Explicit regeneration creates a complete v4 learner/author pair; it never patches old prose or migrates the old tree in place.

### 5. Run one course acceptance

Run exactly one aggregated course-specific verification:

```bash
uv lock --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" \
  --project /path/to/course
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --isolated \
  --locked --no-editable --project /path/to/course \
  python "$SKILL_DIR/scripts/verify_learning_project.py" /path/to/course \
  --json /tmp/course-verification.json
```

Require all declared starter tasks to be RED, the solution against public+hidden tests to be GREEN, quiz/navigation/coding gates to advance, one real API flow to cover public test and hidden submit, and a receipt that binds learner, author, runtime, and verifier digests. Do not run per-course npm install, Web build, browser matrix, dual-language matrix, or the full Runner safety suite.

Locking first and then running through the generated project creates one disposable Python environment before the receipt is computed, so target-library dependencies participate in the real tests and `uv.lock` is bound by acceptance. `--isolated` prevents a pre-existing project `.venv` from becoming part of the trust boundary; `--locked` prevents dependency drift during verification.

Use [forward-test-rubric.md](references/forward-test-rubric.md) for the split between per-course acceptance and shared engine conformance.

### 6. Hand off

Report the locale, target version, chapter count, capstone, acceptance receipt, learning command, and privacy limitation. The Python Runner serves the prebuilt Web and `/api/*` from one port and preserves Markdown navigation, terms, quiz, CodeMirror, save, public tests, hidden submit, progress restoration, three gates, and the three-column desktop layout.

## Regenerate only what changed

For an explicit course, inspect its provenance first:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project \
  python "$SKILL_DIR/scripts/regenerate_course.py" check COURSE \
  --json /tmp/course-regeneration-plan.json
```

Content-prompt or Depth-Brief contract drift regenerates chapter packages. Web/runtime/verifier drift re-exports or revalidates without recalling Writers.

When the learner identifies one shallow chapter, create a targeted request:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project \
  python "$SKILL_DIR/scripts/regenerate_course.py" chapter COURSE \
  --chapter lab03 --reason "explain the ownership boundary with a concrete failure" \
  --json /tmp/chapter-regeneration.json
```

Recall only that chapter's original role with the locked route, task IDs, interfaces, and owned paths; leave all other packages unchanged. Verify the rebuilt pair once before transactional replacement. During apply, stage the old learner/author pair only in one transient rollback directory. On a handled pre-cleanup failure, restore both originals when their bound snapshots and destinations remain intact; otherwise fail closed and report manual recovery without deleting unverified paths. After the new pair is installed and post-swap validation succeeds, durably write the result JSON with `replacement_committed=true` and `cleanup_status=pending` before deleting anything. Then delete the old trees and rollback directory and atomically upgrade the result to `cleanup_status=complete`; report success only after that directory is absent and the final result is durable. If recursive cleanup or final result upgrade fails, keep the verified new pair installed and preserve or update the earlier commit receipt so the caller can distinguish a committed replacement from a rollback. Retain no backup after success and warn that successful replacement is irreversible. Never commit, push, or publish unless the user separately asks.

The request intentionally contains no recovered semantic brief. The parent
Agent must create a new chapter-local Depth Brief, then give the original
Writer role that brief plus the request's package-relative task contracts.
After scaffolding and accepting a candidate pair, bind and install it with:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project \
  python "$SKILL_DIR/scripts/regenerate_course.py" check COURSE \
  --candidate-course CANDIDATE --chapter-request /tmp/chapter-regeneration.json \
  --json /tmp/chapter-replacement-plan.json

uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project \
  python "$SKILL_DIR/scripts/regenerate_course.py" apply COURSE \
  --candidate-course CANDIDATE --plan /tmp/chapter-replacement-plan.json \
  --confirm-stopped --accept-replacement \
  --json /tmp/chapter-replacement-result.json
```

Targeted check permits changes only in the named chapter's prose, terms, quiz,
owned source files, public/hidden tests, examples, and receipt-bound derived
manifests. It requires every other chapter and unrelated material file to
remain byte-identical. Apply performs offline receipt validation and never
calls a Writer.
