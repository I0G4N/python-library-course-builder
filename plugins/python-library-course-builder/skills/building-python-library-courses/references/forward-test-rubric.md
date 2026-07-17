# Forward-test rubric

This rubric is the required acceptance gate for a **local generated project**. Generate into an empty destination, run `scripts/verify_learning_project.py`, inspect the resulting learner and teacher projections, and accept only current local evidence from the generated repository.

## Contents

- [Required fail-closed negative tests](#required-fail-closed-negative-tests)
- [Required authoring workflow evidence](#required-authoring-workflow-evidence)
- [Required existing-course update matrix](#required-existing-course-update-matrix)
- [Required generated-project acceptance matrix](#required-generated-project-acceptance-matrix)
- [Repository quality](#repository-quality)

## Required fail-closed negative tests

Verify all of these separately:

- scaffolding to a non-empty directory preserves its sentinel file and writes nothing else;
- a file destination and symlink destination are rejected;
- an unresolved `{{TOKEN}}` is rejected;
- an unsafe relative path, missing source ID, duplicate ID, broken dependency, missing symbol/test, or non-positive points is rejected;
- an unselected large-target specification is rejected before destination creation;
- check/validation mode does not mutate source or output;
- an induced replacement failure leaves the prior generated output byte-for-byte intact.
- generated-course `check` changes no course byte, Git ref, or progress state;
- version/hash drift without an unapplied `course_impacting` migration is a no-op;
- a tampered plan digest or any managed, learner, unknown, source, or state change after `check` blocks `apply`;
- a missing/forged legacy baseline, managed hash collision, unsafe path, symlink, missing stop confirmation, unresolved merge, or shadow verification failure blocks all course writes; and
- an identity-changing update without explicit reset acceptance leaves active progress and its course byte-for-byte intact.

## Required authoring workflow evidence

For a real Skill-authored course, retain an author-side orchestration trace until acceptance and verify it without copying that trace into the generated learner course:

- the expected unit set is exactly `lab00`, every selected `prepNN`, and every formal `labNN`;
- each unit is written by one distinct clean-context writer launched with `fork_turns="none"`, and no writer is reused for another chapter;
- every writer receives only its sanitized chapter packet and locked cross-course contracts, never readiness answers, profile fields, capability status/decision/basis, or another chapter's prose;
- deterministic assembly rejects missing, duplicate, unexpected, or unit-ID-mismatched fragments and rejects mutation of parent-owned route, code, tests, module-cycle, bridge, and source contracts;
- one separate clean-context reviewer checks the assembled whole course; a rejected chapter is replaced by a newly launched writer rather than repaired by reusing the original writer; and
- if clean subagents cannot be launched, authoring stops instead of silently composing all chapters in the parent context.

This is an observed workflow contract, not comparative scoring between agents or outputs. Generated-project tests validate the assembled artifacts; they cannot prove which context authored them.

## Required existing-course update matrix

Exercise the updater against copied fixtures; never use a learner's only course artifact.

- fresh scaffolding records closed, deterministic `platform/coursekit-generation.json` before its generated Git baseline, with correct plugin/Skill/course identity, applied migration IDs, managed roles, and hashes;
- an explicit existing-course path reads and locks its canonical language and pinned target without asking the fresh-course language question;
- provenance-backed courses and real v0.1.0, v0.1.1, and v0.2.0 generated-root fixtures select only applicable unapplied registry IDs; unverifiable origins stop;
- `check` reports managed `template`, `compiled`, and `workspace-runtime` operations plus `protected`, `author-source`, `unknown`, and `state` preservation without mutating the course;
- apply rebinds the reviewed digest, rebuilds the candidate in a sibling shadow, passes compiler/provenance integrity plus the complete `scripts/verify_learning_project.py` acceptance flow on a pristine prepared snapshot, and only then starts the transaction;
- unchanged managed files advance, clean three-way text merges retain compatible local edits, and unresolved conflicts produce zero target writes;
- learner-editable code, canonical source unless explicitly supplied, unknown files, unchanged progress, Git HEAD, and every ref remain byte-for-byte unchanged;
- content migrations supply reviewed canonical source; legacy structured v3 lessons gain `tutorial-markdown-v1` and the architecture/interface lens without changing locale, target, or formal identity;
- v2-to-v3 uses current evidence readiness, retains formal Lab code/IDs where possible, reports identity change, archives exact state before reset, and requires `--accept-progress-reset`;
- an injected failure after a real replacement restores the entire pre-apply tree, including empty-directory shape, while leaving Git refs untouched;
- successful provenance lists the applied IDs, and repeated `check` plus `apply` returns `up_to_date` with no writes; and
- no step scans for other courses, changes the empty-only scaffolder, commits/tags Git, or installs/upgrades a Skill, plugin, target, or course locale.

## Required generated-project acceptance matrix

Run every check from fresh output.

### Source and structure

- canonical source validates and compiled artifacts have no drift;
- new Skill-authored output uses a private schema v3 `evidence-dialogue` prerequisite profile; capability titles, evidence class, source IDs, first graded use, and each gap decision (`assume`/`preparatory`) exactly match the ready plan in canonical authoring data and the private parity snapshot;
- learner/runtime manifests, `content.json`, generated README files, sidebar copy, Web/CLI/Runner payloads, and public APIs contain no `audience`, `prerequisite_profile`, `readiness`, route/readiness summary, assumed/preparatory capability list, capability status/decision/basis, diagnostic question/answer IDs, or prep `capability_ids`; the curriculum suffix remains opaque;
- zero gaps produce only lab00; multi-layer gaps produce the minimum ordered prep chain without a hard count ceiling;
- lab00, every prep, and every graded Lab preserve exact per-unit `study_minutes` through split source, parity snapshot, content, manifest, README, and learner projections;
- new tutorial-format schema v3 split source has `tutorial.md` plus `lesson.json` for every `preparatory_units/{lab00,prepNN}` and formal Lab, no editable source snapshot, preserves authored tutorial Markdown byte-for-byte through `content.json`, and emits a parity snapshot equal to the validated input; schema v2 and schema v3 without `lesson_format` remain compatible through the legacy renderer;
- Lab IDs are contiguous and the count matches the adaptive range;
- all declared files, symbols, selectors, source IDs, and points resolve;
- no generated file is a symlink;
- `labs/` is learner-facing and `platform/` owns engine/private code;
- no unresolved token, generator absolute path, or foreign branding remains;
- scans reject legacy target-specific course branding, fixed `lab12`, and fixed score denominators in a course with a different subject or size.
- every lesson defines purpose, mechanism, mental model, design reasons, benefits, tradeoffs, invariants, boundaries, pitfalls, and source-backed claims for every concept;
- every assessed concept has a closed operational contract; every runnable example has a complete concrete-value trace of at least two steps; concept/outcome activity coverage satisfies the assessed Lab 00 versus graded-Lab surfaces;
- every prep gap connects an existing cognitive anchor, term definition, current-route need, complete value flow, misconception or boundary, and recovery check;
- every graded chapter satisfies `teaching-depth-contract.md` as a naturally structured tutorial rather than a repeated author-field inventory; it defines jargon at first use, keeps one new knowledge mainline, and connects its project problem, plain-language predictive model, precise contract, one same-value complete flow, valid/boundary cases, diagnosis/recovery, quiz, coding question, and capstone increment in the selected `zh-CN` or `en` locale, with no mixed-language, diagnostic-profile narration, or fallback text;
- a boundary witness for every declared failure and every independently stated boundary must execute one representative counterexample, apply its recovery, re-execute the corrected path, record the recovered observable, and prove its prose contract, runnable or diagnostic code, expected output, diagnostic quiz and, for graded concepts, coding prompt plus public and hidden tests agree on the condition, observable, and recovery;
- every lesson has at least two examples: a CPU/offline runnable example with exact command/output and a diagnostic wrong -> symptom -> cause -> fix example;
- every runnable command is exactly `python {path}` for its declared lesson-relative file;
- every quiz bank includes execution-trace and diagnostic questions, maps them to concepts/outcomes, gives feedback per stable choice ID, uses all answer positions, and keeps every position at or below 40%;
- every Lab after Lab 01 starts with a graded official bridge for the previous mechanism in the immediately next Lab, covers every prior target responsibility, then handwrites its next teaching-equivalent;
- AST/source-contract tests reject target imports in mini modules and any prior mini implementation import in downstream code or tests.
- review rejects prerequisite leakage and proves each exact graded formula has a visible worked numeric derivation or execution trace;
- `content.json` derives each concept's first practice link in authored activity order, uses a knowledge check for prep and a coding question for graded Labs, and adds no reverse links to the parity snapshot;
- a capstone mutation probe replaces real payload transformations with stage-name-only callbacks, reorders identities, changes masks, and bypasses a selected config branch; each mutation must fail.

### TDD projections

- learner starter imports and pytest collects normally;
- starter is RED only for declared incomplete interfaces;
- reference is GREEN for every public selector;
- reference is GREEN for all hidden tests;
- repeated runs are deterministic and CPU/offline;
- runnable lesson examples execute with their declared expected output against the untouched starter projection before coding is unlocked and never require a learner TODO;
- every compiled coding question has a learner-safe `source_policy`, and both CLI and Runner reject missing required roots, forbidden target roots, prior mini/prior-Lab imports, literal dynamic imports, and indirect same-Lab helper delegation before pytest;
- exercises whose tests spawn processes declare an explicit `timeout_seconds` budget within 1-90 seconds and verify bounded shutdown without orphaned children; other omissions normalize to 30 seconds;
- learner projection and public API payloads contain no reference code, hidden-test body, hidden selector, or private path.

### CLI and progress

- Lab 01 cannot run before the complete prep flow is satisfied;
- prep test/grade/submit/checkpoint commands fail closed and score remains unchanged;
- knowledge answers unlock the declared Lab;
- `test`, `grade`, `submit`, `checkpoint`, and `score` execute against manifest data;
- local `test` and `grade` use a disposable learner copy, bounded diagnostics, question-specific deadlines, isolated Ray environment variables, and complete descendant cleanup;
- public selectors that are absolute, traversing, missing, non-files, or symlinked fail closed, while command test outcomes return only 0 or 1;
- point totals equal the sum of exercise points;
- progress survives Runner restart and does not silently merge another curriculum ID;
- Git-unavailable behavior is recoverable and documented.

### Web and Runner

- The **chapter navigation gate**, **knowledge gate**, and **coding verification gate** use the same manifest order and persisted knowledge state across CLI, Web, and Runner.
- production Web build and TypeScript checks pass;
- the rendered course uses manifest Lab titles/counts and compiled Markdown lessons;
- `tutorial-markdown-v1` renders authored Markdown as the primary lesson with stable heading anchors, accessible semantic markup, syntax-highlighted code, and a chapter guide derived from headings plus structured concepts; `lesson_outline` remains a non-primary semantic sidecar, while legacy inputs retain the complete structured Markdown fallback;
- generated course prose presents prep as ordinary route chapters and never explains that a profile, answer, status, or assessed deficiency selected them;
- Python lesson fences and the editor have syntax highlighting and monospace alignment;
- no orientation/prep unit has a code workspace; in short, prep has no code workspace. Each graded Lab hides code/results and makes no file request until the prep chain and current knowledge are complete;
- before coding unlock, widths of at least 1280px use a roughly 80-character tutorial column plus a 300-360px rail containing the heading guide, terminology index, and knowledge check; widths from 1024px through 1279px use a centered single column with the rail after it; body text is 15-16px at about 1.75 line height;
- after coding unlock, widths of 1024px and above restore the desktop shell with two keyboard-accessible separators, declared minimum widths, sidebar collapse, pointer drag plus Arrow keys/Home/End, validated per-course localStorage preferences, and a reviewable knowledge check;
- a short or resized desktop viewport keeps the complete interface reachable through independent lesson and code/result vertical scrolling, with no fixed shell minimum height or implicit toolbar row clipping the learning surface;
- widths from 760px through 1023px stack lesson, guide/check rail, and unlocked work without blocking scroll chaining; widths below 760px keep chapter navigation in explicit grid areas plus natural document scrolling without a capped or sticky lesson surface; both ranges have no resize separators;
- schema v3 initially enables only Lab 00, unlocks one prep at a time by knowledge mastery, then Lab 01; schema v2 preserves its original initial pair;
- the knowledge gate renders a generic quiz from redacted `GET /api/knowledge/{lab_id}` data and persists correct answers through `POST /api/knowledge/answer` without disclosing answer keys;
- the Runner rejects prep file/write/run APIs explicitly; formal `POST /api/run` stays locked until prep and current knowledge are mastered;
- the question-scoped file API rejects reads and writes with 409 before the same knowledge gates, accepts only a manifest Lab/question pair after unlock, returns 404 for unknown pairs, and retains traversal, absolute-path, and symlink rejection;
- a functional API workflow calls `GET /api/state`, `GET /api/knowledge/{lab_id}`, `POST /api/knowledge/answer`, and `POST /api/run` in a disposable learner copy and proves the next Lab stays locked before coding verification and unlocks afterward;
- initial state and refreshes fail closed; out-of-order snapshots, late save/run responses after navigation, hidden-document polling, listener cleanup, and failed-answer retry are covered by generated project tests rather than source-token checks alone;
- Runner health, course, lesson, safe file read/write, public test, hidden grade, and score APIs pass smoke tests;
- traversal, absolute paths, and symlink reads/writes are rejected;
- grading projects canonical teacher tests plus same-directory helpers against a disposable learner copy, leaves learner and teacher source files unchanged, and never exposes hidden diagnostics;
- public and hidden phases share one declared deadline; concurrent grading returns 409 and the lock releases after success and failure;
- process-spawning exercises leave no descendant process after success, failure, timeout, or output overflow;
- launch, Ctrl+C shutdown, restart, and final shutdown leave no orphaned service.

These controls are a workflow gate, not source secrecy. Acceptance must not claim that hiding the Web workspace prevents a local learner from opening starter files directly.

### Repository quality

- root, platform, and learner tests pass;
- lint, build, compile checks, and course drift checks pass;
- README commands work in a clean environment and state required Python/Node tooling;
- a clean Git baseline checkpoint excludes runtime state and caches; if it includes the author projection, the README clearly states that public hosting exposes reference answers and hidden tests.
