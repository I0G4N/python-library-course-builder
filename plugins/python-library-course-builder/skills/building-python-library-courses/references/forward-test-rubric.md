# Forward-test rubric

This rubric separates the required generated-project acceptance matrix from optional instruction-transfer evaluation. Fresh-agent transfer evaluation is optional and is not a standard release gate.

## Contents

- [Optional fresh-agent transfer evaluation](#optional-fresh-agent-transfer-evaluation)
- [Paired Skill-output evaluation](#paired-skill-output-evaluation)
- [Optional small-target transfer test](#optional-small-target-transfer-test)
- [Optional large-target gate test](#optional-large-target-gate-test)
- [Required fail-closed negative tests](#required-fail-closed-negative-tests)
- [Required generated-project acceptance matrix](#required-generated-project-acceptance-matrix)
- [Repository quality](#repository-quality)
- [Optional RED/GREEN transfer comparison](#optional-redgreen-transfer-comparison)

## Optional fresh-agent transfer evaluation

Use this advisory evaluation when measuring whether the Skill transfers to a new target without replaying an existing course. When running it, use a fresh agent or context with only the user-style request, the Skill, a target name, and an empty destination. Do not provide an existing course specification, reference implementation, expected Lab titles, or prior verification report. Record the exact prompt, target version, output path, commands, exit codes, and failures.

Always generate outside the source repository. The destination must not exist or must be empty. Afterward, inspect for symlinks and absolute references back to the Skill or originating project.

The generated route must use a route-relevant prerequisite profile and gap decision, an evidence-based Lab 00, exact per-unit `study_minutes`, and the teaching-equivalent -> official bridge cycle. A reviewer must be able to trace that no downstream source or capstone imports a prior mini implementation.

## Paired Skill-output evaluation

This paired gate is **required for any change to readiness or teaching-depth Skill guidance**. Preserve one user-style prompt and target, score the **old output**, then give the same prompt and revised Skill to a fresh isolated agent that cannot see the old result, expected answer, or score. Save the exact prompt, Skill revision, output, source/version state, and scoring evidence for the **new output**. Fresh-agent transfer remains optional for ordinary course generation when the Skill guidance itself is unchanged.

Score six dimensions from 0-2. Every score needs an **evidence citation** to a concrete output section, value flow, mapping, or source decision:

1. **route-relevant readiness assessment and gap decision** — 0 absent; 1 useful prose but incomplete evidence/routing; 2 reuses evidence, asks only unresolved route capabilities, groups decisions, and stops a large gap before a spec.
2. **evidence-based two-layer foundation plan** — 0 generic prerequisites; 1 some gaps addressed; 2 separates evidenced general-Python gaps from route-specific library/domain foundations and gives mapped, justified Lab 00 work.
3. **precise operational contract** — 0 absent; 1 partially specifies behavior; 2 closes visible forms, constrained example inputs, example outputs, effects, and condition/observable/recovery failures around the tested convention.
4. **complete concrete-value worked trace** — 0 absent/generic; 1 concrete but incomplete or unmapped; 2 carries one real value/state through at least two named transitions with relevant intermediate shape/type/state/ownership and matches tests.
5. **concept-to-quiz/coding/capstone alignment** — 0 absent; 1 plausible narrative mapping; 2 gives inspectable concept/outcome mappings across the required activity surfaces and a real cumulative increment.
6. **natural Simplified-Chinese explanation with source/version discipline** — 0 unusable or unsupported; 1 understandable with gaps; 2 defines terms at first use, alternates explanation with values, uses primary official evidence, and resolves or explicitly blocks version uncertainty.

Pass only with **no zero**, at least **10/12**, and **exactly 2** on dimensions 3 and 4. If the new output misses any gate, strengthen the reusable Skill/reference wording and rerun with another fresh isolated agent; do not reinterpret the same evidence upward.

Record the result with this template:

```markdown
| Dimension | Old | New | Old evidence citation | New evidence citation |
|---|---:|---:|---|---|
| Readiness and gap decision | /2 | /2 | | |
| Two-layer foundation | /2 | /2 | | |
| Operational contract | /2 | /2 | | |
| Concrete worked trace | /2 | /2 | | |
| Activity/capstone alignment | /2 | /2 | | |
| Natural Chinese and sources | /2 | /2 | | |

Old total: /12
New total: /12
Gate: PASS/FAIL
Unresolved questions:
```

## Optional small-target transfer test

Use a bounded standard-library target such as `pathlib`:

1. Inspect the installed Python version.
2. Research the matching official Python documentation and CPython source.
3. Classify it as small unless the researched scope justifies otherwise.
4. Produce Lab 00 plus 3-5 graded Labs and one cumulative, local-filesystem capstone.
5. Run the complete project verifier and save its JSON report.

The route must cover a coherent progression rather than mechanically copying another library's Lab names. The generated prose, symbols, examples, tests, capstone, branding, and official links must all belong to the target.

## Optional large-target gate test

Invoke the Skill for a broad multi-product target such as Ray without naming a track. A passing response:

- uses official evidence to present 2-4 coherent choices such as Core, Data, Train/Tune, or Serve;
- explains the distinct capstone and environment implications of each choice;
- requests one selection;
- creates no specification, course directory, or partial template before selection.

After a track is selected, only that track is eligible for the 6-10 Lab route. A shallow all-products survey fails.

## Required fail-closed negative tests

Verify all of these separately:

- scaffolding to a non-empty directory preserves its sentinel file and writes nothing else;
- a file destination and symlink destination are rejected;
- an unresolved `{{TOKEN}}` is rejected;
- an unsafe relative path, missing source ID, duplicate ID, broken dependency, missing symbol/test, or non-positive points is rejected;
- an unselected large-target specification is rejected before destination creation;
- check/validation mode does not mutate source or output;
- an induced replacement failure leaves the prior generated output byte-for-byte intact.

## Required generated-project acceptance matrix

Run every check from fresh output.

### Source and structure

- canonical source validates and compiled artifacts have no drift;
- new Skill-authored output uses an `assessed` prerequisite profile whose capability titles, evidence basis, source IDs, first graded use, and `assume`/`foundation` gap decision resolve; legacy `basic-python` remains compatibility input;
- a completed specification contains no serialized large-gap state; a route needing multiple prerequisite layers stops before files are created;
- Lab 00 and every graded Lab preserve exact per-unit `study_minutes` through split source, parity snapshot, `content.json`, teacher and learner manifest, README, and learner projections;
- schema v2 split source contains structured `lesson.json` files, no editable source authoring snapshot, and emits a compiler-generated parity snapshot equal to the validated input;
- Lab IDs are contiguous and the count matches the adaptive range;
- all declared files, symbols, selectors, source IDs, and points resolve;
- no generated file is a symlink;
- `labs/` is learner-facing and `platform/` owns engine/private code;
- no unresolved token, generator absolute path, or foreign branding remains;
- scans reject legacy target-specific course branding, fixed `lab12`, and fixed score denominators in a course with a different subject or size.
- every lesson defines purpose, mechanism, mental model, design reasons, benefits, tradeoffs, invariants, boundaries, pitfalls, and source-backed claims for every concept;
- every assessed concept has a closed operational contract; every runnable example has a complete concrete-value trace of at least two steps; concept/outcome activity coverage satisfies the assessed Lab 00 versus graded-Lab surfaces;
- every lesson has at least two examples: a CPU/offline runnable example with exact command/output and a diagnostic wrong -> symptom -> cause -> fix example;
- every runnable command is exactly `python {path}` for its declared lesson-relative file;
- every quiz bank includes execution-trace and diagnostic questions, maps them to concepts/outcomes, gives feedback per stable choice ID, uses all answer positions, and keeps every position at or below 40%;
- every Lab after Lab 01 starts with a graded official bridge for the previous mechanism in the immediately next Lab, covers every prior target responsibility, then handwrites its next teaching-equivalent;
- AST/source-contract tests reject target imports in mini modules and any prior mini implementation import in downstream code or tests.
- review rejects prerequisite leakage and proves each exact graded formula has a visible worked numeric derivation or execution trace;
- `content.json` derives each concept's first practice link in authored concept/activity order, uses a knowledge check for Lab 00 and coding question for graded Labs, and adds no reverse `practice_links` to the authoring parity snapshot;
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

- Lab 01 cannot run before its prerequisite flow is satisfied;
- knowledge answers unlock the declared Lab;
- `test`, `grade`, `submit`, `checkpoint`, and `score` execute against manifest data;
- local `test` and `grade` use a disposable learner copy, bounded diagnostics, question-specific deadlines, isolated Ray environment variables, and complete descendant cleanup;
- public selectors that are absolute, traversing, missing, non-files, or symlinked fail closed, while command test outcomes return only 0 or 1;
- point totals equal the sum of exercise points;
- progress survives Runner restart and does not silently merge another curriculum ID;
- Git-unavailable behavior is recoverable and documented.

### Web and Runner

- production Web build and TypeScript checks pass;
- the rendered course uses manifest Lab titles/counts and compiled Markdown lessons;
- structured `lesson_outline` renders the assessed **open core** with exact time/reason, `先这样理解`, `输入和输出是什么`, `拿一个具体输入走一遍`, concrete trace, and first practice link before accessible disclosures for principles, design choices, sources, and diagnostics; the full Markdown fallback remains usable;
- manifest and README readiness projections group capability titles into assumed and foundation preparation without exposing internal IDs or enums; Web/Markdown use learner-safe labels rather than author terms;
- Python lesson fences and the editor have syntax highlighting and monospace alignment;
- Lab 00 has no code workspace, while each graded Lab hides the complete code/result area and makes no file request until foundation and current-Lab knowledge are complete;
- the desktop shell exposes two keyboard-accessible separators, respects declared minimum widths, lets the sidebar collapse, supports pointer drag plus Arrow keys/Home/End, and restores validated per-course localStorage preferences;
- widths from 760px through 1099px stack lesson and work, widths below 760px retain compact chapter navigation, and both ranges have no resize separators;
- the chapter navigation gate enables only Lab 00 and the first graded Lab initially, leaves later controls genuinely disabled, and unlocks the next Lab only after dependency completion;
- the knowledge gate renders a generic quiz from redacted `GET /api/knowledge/{lab_id}` data and persists correct answers through `POST /api/knowledge/answer` without disclosing answer keys;
- the coding verification gate keeps `POST /api/run` locked until foundation and current knowledge are mastered, then completes a Lab only after every coding question passes verified submission;
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

## Optional RED/GREEN transfer comparison

A no-Skill baseline is optional and applies only when measuring the effect of the Skill. If you run that comparison, keep the baseline and Skill-assisted result as separate reports. Compare at least:

- official evidence and version lock;
- adaptive curriculum and cumulative capstone;
- canonical source/compiler contract;
- starter/reference/hidden separation;
- starter RED and reference GREEN evidence;
- CLI completeness;
- pytest grading quality;
- Web editor and Runner behavior;
- progress and Git checkpoints;
- privacy, residue, path safety, and deployment documentation.

Do not mark an optional transfer evaluation GREEN if any Critical or Important issue remains. When a failure generalizes to other targets, patch the Skill, script, or template, regenerate from an empty directory, and rerun the required generated-project matrix.
