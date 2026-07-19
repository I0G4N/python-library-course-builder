# CourseKit project architecture

Use this reference when designing or reviewing the generated repository. The objective is a content-driven learning product, not a bespoke demo for one library.

The generic template and bundled course infrastructure are independently authored for this project. Generated projects copy the engine files and retain no import, symlink, or runtime path back to the Skill or an originating course repository.

## Contents

- [Ownership map](#ownership-map)
- [Data flow](#data-flow)
- [Three-gate progression](#three-gate-progression)
- [Responsive workspace layout](#responsive-workspace-layout)
- [Course language ownership](#course-language-ownership)
- [Runtime boundaries](#runtime-boundaries)
- [Compilation and workspace rules](#compilation-and-workspace-rules)
- [Generated-course provenance and regeneration](#generated-course-provenance-and-regeneration)
- [Privacy model](#privacy-model)
- [Git checkpoints](#git-checkpoints)

## Ownership map

```text
project/
├── README.md                       learner setup, start, stop, and course route
├── package.json                    root setup/learn/test/build commands
├── labs/                           the learner's obvious starting point
│   ├── README.md
│   ├── pyproject.toml
│   ├── lab00/                      environment and learning-loop orientation
│   ├── prep01/ ... prepNN/         knowledge-only preparatory units when needed
│   ├── lab01/ ... labNN/           learner code plus public tests
│   └── _course/coursekit/          generic CLI, progress, and pytest support
└── platform/                       all non-learner engine and private artifacts
    ├── coursekit-generation.json  generator provenance and authoring fingerprint
    ├── coursekit-regeneration.json private route/readiness regeneration input
    ├── app/                        content-driven Web shell and CodeMirror editor
    ├── runner/                     FastAPI workspace and grading service
    ├── coursekit/                  source loader, validator, and compiler
    ├── course/
    │   ├── source/                 canonical authored course inputs
    │   ├── manifest.json           compiled navigation and grading metadata
    │   ├── knowledge.json          compiled knowledge checks
    │   ├── content.json            compiled Markdown lessons
    │   ├── starter/                workspace projection
    │   ├── reference/              private complete implementations
    │   └── tests/hidden/           private grader tests
    └── tests/                      engine, contract, Web, and Runner tests
```

`labs/` is the only directory learners need to edit. Configuration, services, generated metadata, reference answers, and hidden tests stay under `platform/`.

## Data flow

```text
official sources
      |
      v
private readiness plan -> course specification + canonical source tree
      |
      v
CourseKit validation and deterministic compilation
      |
      +--> sanitized manifest/content/knowledge --> Web + CLI + Runner
      +--> starter projection ---------> labs/
      +--> reference + hidden tests ---> private verification/grader
      +--> regeneration sidecar ------> future author-side regeneration
```

There is one split authoring source of truth. New schema-v3 chapters store primary tutorial prose in `tutorial.md` and deterministic concept/activity metadata in `lesson.json`. Prep lessons live under `course/source/preparatory_units/`; formal Lab metadata, code, and tests stay under `course/source/labs/`. Schema-v2 `foundations/` and schema-v3 sources without tutorial Markdown remain compatibility inputs. Do not keep an editable source `authoring-spec.json`. Consumers traverse the sanitized compiled manifest; unit order, titles, dependencies, score totals, questions, and lesson paths are data.

The readiness plan, audience prerequisite profile, capability mappings, readiness summary, and regeneration sidecar are author-side inputs. Validation and private authoring artifacts may inspect them; learner/runtime manifests, content payloads, generated README files, sidebar copy, and public APIs do not contain them. The curriculum ID may retain the readiness-derived suffix only as an opaque progress-isolation token.

Each coding question carries normalized `timeout_seconds` metadata in both internal and learner manifests. It must be an integer from 1 through 90 and defaults to 30 when omitted.

Each compiled question also carries compiler-owned `source_policy` metadata: its same-Lab root, all directly required official import roots, forbidden target roots, prior mini modules, and prior course roots. Both the copied CLI and the Runner call the same AST preflight before pytest. The preflight recognizes `import`, aliased `from ... import ...`, literal `importlib.import_module(...)`, and literal `__import__(...)`, follows reachable same-Lab helpers, and fails closed on missing policy, syntax errors, undeclared helpers, forbidden imports, or missing required imports.

## Three-gate progression

Progression has three independent, cumulative decisions:

1. In schema v3 the **chapter navigation gate** makes only Lab 00 navigable initially. Each prep becomes navigable when its predecessor's knowledge is complete; Lab 01 follows the final prep or Lab 00. Formal-Lab dependencies still require verified completion. Schema v2 retains its original Lab 00 plus Lab 01 initial navigation.
2. The **knowledge gate** makes each navigable unit's quiz answerable in order. Prep completion is derived from knowledge mastery and never enters `completed_labs`.
3. The **coding verification gate** marks a Lab complete only after every declared coding question has passed verified submission. Passing one public test or one question cannot unlock the next Lab.

CLI and Web/Runner mutations update the same curriculum-scoped state under `labs/.coursekit/state.json`; direct pytest reads that state to enforce its gate. The Runner is the authority for Web progression and exposes `GET /api/state`, `GET /api/knowledge/{lab_id}`, `POST /api/knowledge/answer`, and `POST /api/run`. Knowledge GET responses normalize choices and redact answer keys plus unselected choice feedback. An answer POST returns only correctness, the selected choice feedback, and the explanation permitted after that attempt. The generic Web quiz renders only this public payload; it never imports course-specific question logic.

The Web must fail closed while initial state is unavailable. Every orientation/prep unit is lesson-and-quiz only and has no code workspace; it never mounts or requests one. A graded Lab mounts code/results only after the complete prep chain and current-Lab knowledge are mastered. The Runner explicitly rejects prep file and execution APIs before path resolution. This is a workflow gate, not source secrecy: formal starter files remain locally inspectable.

## Responsive workspace layout

Before `codingReady`, use a focus-reading layout and never mount a disabled or empty editor. At widths of 1280px and above, the learning area contains a roughly 80-character narrative column plus a 300-360px rail. The rail derives stable heading links and a terminology index from the tutorial and structured concepts, then contains the still-reviewable knowledge check. Body prose is 15-16px with approximately 1.75 line height. From 1024px through 1279px, center the narrative as one column and place the rail after it. From 760px through 1023px, use the existing stacked learning surface. Below 760px, use natural document scrolling with no sticky or capped nested lesson surface.

After a graded chapter reaches `codingReady`, restore the IDE workspace at widths of 1024px and above: sidebar, lesson, and code/result columns with two keyboard-accessible separators. The sidebar defaults to 208px, remains between 160px and 320px while expanded, and can collapse to 64px. The lesson and work areas preserve minimum widths of 320px and 440px. Pointer drag adjusts widths; a focused separator supports Arrow keys in 16px steps plus Home and End, exposes `role="separator"` and current/min/max values, and keeps a usable focus target. The desktop shell is clamped to the dynamic viewport with no fixed minimum height; the lesson and code/result columns scroll vertically and independently so a short or resized browser window cannot hide their lower content. The knowledge check remains reachable for review rather than disappearing after unlock.

Validated, clamped preferences live in per-course localStorage under `coursekit.layout.v1.<course_id>` so unrelated courses never share layout state. Invalid or stale values fall back safely. From 760px through 1023px the unlocked lesson and work areas stack inside the learning surface, and the inner lesson scroller permits scroll chaining to the outer stacked surface so a newly unlocked workspace remains reachable. Below 760px the compact chapter navigation uses explicit grid areas and the page returns to natural document scrolling. Medium and small layouts have no resize separators.

## Course language ownership

Every fresh Skill invocation asks for exactly one course locale before target discovery or readiness. The supported set is closed to `zh-CN` and `en`; an already worded language preference does not skip this first question. The accepted locale is immutable input to the route, readiness plan, schema-v3 source, compiled manifest, generated README and Markdown, Web catalog, CLI output, and handoff. Unknown, missing, mixed, or mismatched locale state fails closed instead of falling back.

Author-side readiness questions and all learner-facing prose, labels, feedback, and generated documentation use the selected locale. Code, shell commands, identifiers, target API names, and official source titles and URLs retain their original spelling. Locale selection is not capability evidence. Raw answers and completed diagnostic/profile metadata are not copied into learner-facing projections or prose.

## Runtime boundaries

The Web application owns presentation and editor state. It fetches course content and workspace files from the Runner; it does not execute arbitrary Python in the browser. Frontend guards are feedback, not authority: the Runner repeats every progression check for direct requests. Workspace access is question-scoped: read with `GET /api/file?lab_id={lab_id}&question_id={question_id}` and write with `PUT /api/file`, whose JSON fields are `"lab_id", "question_id", and "content"`. The server derives the target path from the internal manifest instead of trusting a client path. Unknown Lab/question pairs return 404, unmet knowledge gates return 409, and unsafe or symlink targets return 400.

The Runner owns safe file access, pytest subprocesses, progress persistence, and grading APIs. Resolve every workspace path against the learner root and reject traversal, absolute paths, symlinks, and non-regular target files. Grading copies regular learner files into a disposable workspace, excludes learner tests and runtime artifacts, and projects each canonical public or hidden target plus regular same-directory helpers into the isolated run before invoking the trusted bootstrap. The target's parent directory is the explicit helper boundary; symlinks, special files, caches, and nested runtime/test roots are excluded. One monotonic deadline covers learner and canonical projection, and both projections have fixed size limits. Public and hidden phases share the question deadline; only one grading request runs per Runner process at a time.

Every grading subprocess starts in its own POSIX session with isolated home and temporary directories, `PWD` set to the disposable workspace, `OLDPWD` removed, bounded combined output, pytest plugin and `conftest.py` loading disabled, and trusted collection/outcome evidence for the projected targets. Reclaim the complete process group after success, failure, timeout, or output overflow. Never construct shell command strings from learner input and never use a machine-global cleanup command such as `ray stop --force`.

This is defense-in-depth for a local learner workflow, not an OS security sandbox. Deliberately hostile code running as the same user can introspect its Python process or detach from its process group. Keep the Runner bound to loopback; do not use it to execute untrusted remote submissions without a separate container or operating-system sandbox.

The CLI reads the same manifest and state model. Its local `test` and `grade` commands resolve only relative, regular, symlink-free public selectors under `labs/`, then use the same copied isolation engine as the Runner. The engine projects the selected visible tests because test code can derive paths from `__file__`; copying only learner source is not enough to preserve the real workspace. Each question receives one deadline covering canonical projection and execution, diagnostics stay bounded, inherited `RAY_ADDRESS` is removed, and every outcome maps to a stable command exit code of 0 or 1. It must support:

- `unlock LAB` for prerequisite knowledge checks;
- `test EXERCISE` for the declared public selector;
- `grade LAB` for local Lab scoring;
- `submit LAB` for Runner-backed hidden grading;
- `checkpoint LAB` for the declared Git milestone;
- `score` for manifest-derived totals and completion state.

Optional library-specific capabilities are declared extensions. A course without an extension must render no empty extension panel and expose no dead command.

## Compilation and workspace rules

Compilation is deterministic: the same canonical input yields byte-identical declared artifacts. Check mode performs no writes and reports drift. Compile mode updates only artifacts recorded by its artifact index, preserves unrelated files, and rolls back on replacement failure.

Curriculum schema is independent from runtime schemas. Schema v3 uses `<course-id>-v3-<readiness_summary>` and declares no compatibility across different summaries; public consumers treat the suffix as opaque. This does not itself bump progress-state, artifact-index, engine, or layout versions. The compiled authoring snapshot is private verification material and never appears in the learner starter projection or public APIs.

Workspace initialization is empty-target-only and transactional. Reject files, symlinks, and non-empty destinations before the first write. Generated projects contain copied files, never symlinks or imports back to the Skill, template, or originating repository.

Only allowlisted template tokens may be substituted. After rendering, scan every text file for unresolved tokens and every path for traversal or absolute source references.

## Generated-course provenance and regeneration

Fresh scaffolds write tracked schema-v2 `platform/coursekit-generation.json` and private `platform/coursekit-regeneration.json` before the generated Git baseline. Generation provenance retains plugin/Skill versions, bundle/template/source digests, stable course identity, and managed-file hashes, and adds `authoring_contract.sha256` plus `regeneration_input.sha256`. Schema v1 is accepted only to recognize a legacy course and require regeneration; it never enables incremental migration. The retired migration registry and `applied_migrations` do not exist in schema v2.

The authoring-contract fingerprint is deterministic and changes when course-writing capability changes. It covers `SKILL.md`, every teaching/architecture reference, readiness assessment, chapter assembly, validation, scaffolding, full verification, and the canonical-source compiler/model. Release prose, README files, and generic front-end/runtime-only files are excluded. Bundle, template, or runtime drift alone therefore does not trigger new course content. A recorded plugin version newer than the running plugin refuses downgrade; equal plugin versions with unequal fingerprints are a version collision rather than a silent rewrite.

The regeneration sidecar is a closed author-only document containing `schema_version`, `language`, `target`, `route_intent`, `route_contract`, and `readiness_projection`. `target` locks name, version, and selected track. `route_intent` preserves course and route IDs/titles. `route_contract` retains validated `schema_version`, `language`, route, official sources, capabilities, and `capability_contracts` entries with exactly `id` plus definition `sha256`. `readiness_projection` retains only `status`, `route_digest`, `capability_dag`, required/mastered/missing IDs, privacy-safe capability decisions, preparatory-unit mapping/time, readiness summary, and plan digest. It never stores raw answers, code evidence, diagnostic responses, or learner-facing prose.

Regeneration mode accepts only an explicit course root and never scans. It locks locale, target/version, track, and route intent; it does not automatically upgrade the target. A matching current authoring fingerprint returns `up_to_date`. A changed or legacy fingerprint returns `regeneration_required`. For a valid v0.3+ sidecar, readiness conclusions may be reused only when both capability ID and definition hash are unchanged; new or changed capabilities receive current diagnostics. Missing, invalid, v0.1, or v0.2 sidecars require complete reassessment.

After current-route research, `regenerate_course.py readiness COURSE --route CURRENT_ROUTE_JSON --json OUTPUT` materializes the boundary. Trusted v0.3+ input writes `mode: reuse_unchanged` and a closed decision set consumable by `assess_readiness.py --trusted-prior-decisions OUTPUT --trusted-course COURSE`; the assessor rebinds it to verified course bytes. Legacy, missing, or tampered input writes `mode: full_readiness`, for which the assessor omits both flags and diagnoses the entire current DAG.

The old course supplies only those locked route inputs and eligible readiness conclusions. Its tutorials, lesson prose, quizzes, learner code, tests, and reference implementation are not writer inputs. Research official sources again, build the current route, use a distinct clean writer for every unit, run a separate whole-course review, scaffold into an empty sibling directory, and pass normal schema-v3 validation, RED/GREEN checks, and `verify_learning_project.py --full` before candidate review.

`regenerate_course.py check COURSE --candidate-course STAGING` binds the old and candidate snapshots. A `ready` plan requires a changed canonical-source hash and at least one substantive authored change among canonical tutorial, lesson, quiz, starter, compiled starter, or public-test paths; provenance-only changes and edits found only in the live learner workspace are `blocked`. Its digest binds the complete old tree, candidate tree, current fingerprint, verification report, course identity, route intent, and reserved backup path. Candidate validation failures are reported as `blocked`; unsafe roots, control-file symlinks, path containment, unrecognized formats, downgrade, or version collision fail closed. A provenance-free legacy course must own its Git top level rather than inherit an enclosing repository.

`apply` accepts only that reviewed `ready` plan plus `--confirm-stopped` and `--accept-replacement`. It preflights the external result path, renames the complete old root to `<course>.coursekit-backup-<UTC>-<snapshot8>`, then renames the verified sibling candidate to the original path. Both roots must share a parent/filesystem. A first-rename error after mutation, failed second rename, or post-swap snapshot error immediately restores the old root. Stale bytes, candidate drift, backup collision, or replacement failure leaves or restores the old course byte-for-byte.

Success means the new root is exactly the verified candidate with fresh progress and a new generated Git baseline. The old `.git`, state, learner code, custom files, and build residue remain intact only in the permanent backup; nothing is merged forward or automatically deleted. A repeated check against the new fingerprint is `up_to_date`. Regeneration does not install a Skill/plugin, commit the surrounding repository, or publish a release.

## Privacy model

Learner-visible `labs/` includes starter code, tutorials or links to tutorials, and public tests. It excludes reference implementations, hidden-test source, hidden selectors, private artifact paths, readiness/profile objects, capability decisions, and author-side diagnostic metadata. Generated README, manifest, content, Web, CLI, Runner, sidebar, and public API responses must not disclose them either.

This separation prevents accidental hints during local study; it is not a secrecy guarantee when the full repository is published. State that limitation in the README and handoff.

## Git checkpoints

Git checkpoints are learning milestones, not a replacement for grading. The initial generated repository should have a clean verified baseline before learner changes. A checkpoint records the current Lab, test state, and commit identity when a Git repository is available. Missing Git must produce a clear recoverable message rather than corrupt progress.
