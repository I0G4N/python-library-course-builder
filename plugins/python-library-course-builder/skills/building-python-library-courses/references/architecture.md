# CourseKit v4 architecture

CourseKit v4 follows the shape of hand-built teaching repositories: readable chapter files, one cumulative `src/` tree, ordinary tests, and a small shared runtime. The legacy v2/v3 compiler remains available only for existing projects.

## Authoring flow

```text
parent route + official facts + task/path locks
                 |
                 +--> ephemeral Depth Brief per chapter
                              |
                              +--> one Writer, one complete package
                                           |
                                           +--> mechanical v4 assembly
                                                      |
                           +--------------------------+------------------+
                           |                                             |
                    learner project                               author sibling
```

The parent never writes chapter prose. A Writer never changes route order, task IDs, public interfaces, selectors, or owned paths. The assembler never rewrites prose or judges its depth.

## Ownership

The learner root owns:

- `course.toml`;
- `chapters/<id>/tutorial.md`, public terms, and redacted quiz questions;
- cumulative starter `src/`;
- public tests and examples;
- the prebuilt static Web and Python runtime; and
- local progress under ignored `.coursekit/` state.

The sibling author root owns:

- quiz answers and explanations;
- the complete solution `src/`;
- hidden tests and private selectors; and
- the acceptance receipt.

No learner file contains an answer key, solution byte, hidden selector, hidden test body, or private author path. The author root is not a security sandbox; publishing it publishes those materials.

## Runtime contract

One Python process on one port serves both:

- the prebuilt React/CodeMirror application; and
- all `/api/*` routes.

The static application uses same-origin API requests. The Runner registers API routes before the SPA fallback; an unknown `/api/*` returns JSON 404 rather than `index.html`.

The generated course does not install Node. Shared engine CI builds the static application and runs the same mocked same-origin API journey in Chromium, Firefox, and WebKit. That matrix proves both locales, free-form Markdown navigation, terms, quiz gates, CodeMirror/save, public and hidden execution controls, restored progress, responsive three-column layout, Runner safety, timeouts, concurrency, and process cleanup.

## Content API

`GET /api/content/{id}` resolves the ID through the manifest and returns:

- `id`, `title`, and the exact `tutorial.md` Markdown;
- explicit `terms.json` records;
- official sources referenced by the chapter;
- study time; and
- at most one practice link derived from the first task.

It never returns `lesson_outline`. Markdown headings drive the chapter navigation rail; explicit terms drive the terminology rail.

The remaining routes keep their existing behavior:

- `GET /api/course` and `GET /api/state`;
- `GET /api/knowledge/{id}` and `POST /api/knowledge/answer`;
- `GET/PUT /api/file`; and
- `POST /api/run` with `public` or `submit`.

## Three gates

1. **Navigation gate** — only `lab00` is initially open; completing a chapter opens its declared successor.
2. **Knowledge gate** — all quiz questions in the current chapter must be answered correctly before code becomes editable. A knowledge-only chapter completes here.
3. **Coding verification gate** — a graded chapter completes only when all task hidden submissions pass.

Public tests give immediate diagnostics but do not complete the chapter. Progress persists locally and is scoped by course/curriculum identity.

## Test execution

The Runner accepts only a manifest chapter/task pair and the exact task file. It rejects absolute paths, traversal, path/symlink escapes, unknown selectors, and requests before the gates are satisfied.

Public mode executes public selectors. Submit mode executes public plus private hidden selectors against the learner's current `src/`. The solution tree is used only by course acceptance, never to grade the learner.

One bounded execution owns a declared timeout and output limit. Concurrent grading returns 409. The shared runtime CI—not each generated course—proves descendant cleanup and the full adversarial matrix.

## Transactional generation

The scaffolder validates and stages learner and author trees under one temporary parent. It exposes neither destination until both are complete. A failed second rename rolls the first back; it never leaves a half pair.

Existing destination files, non-empty directories, symlinks, containing paths, or a collision between learner and author targets fail before writes.

## Acceptance receipt

One course-specific acceptance binds:

- immutable course contract digest;
- learner tree digest, excluding progress/caches;
- author tree digest, excluding the receipt itself;
- runtime digest;
- verifier digest;
- RED/GREEN and API-flow results; and
- course/curriculum identity.

Regeneration check/apply recomputes these bindings instead of rerunning acceptance. Any material change fails closed.

## Existing-course replacement

Apply reserves one validated, inode-bound sibling directory as transient
rollback storage. It stages the old learner and author there, installs the
receipt-bound candidate pair, and rechecks both old and new snapshots. Any
handled failure before cleanup restores the original pair and removes the
empty rollback directory while the bound paths remain intact. Path
interference fails closed and reports manual recovery instead of deleting
unverified trees.

After post-swap validation, apply atomically writes and filesystem-syncs a
result JSON with `replacement_committed=true` and
`cleanup_status=pending`. Only then may it recursively delete the old pair.
Once the rollback directory is absent, apply atomically upgrades the result to
`cleanup_status=complete` and reports success. If that final result write
fails, the earlier durable commit receipt remains, so the caller does not
confuse the installed replacement with a rollback. An `os.replace` error
raised after the result entry changed is accepted only when the exact expected
JSON is present, followed by a successful directory sync.

Apply retains no backup after success, so a successful replacement is
irreversible. If cleanup partially fails, apply keeps the verified new pair
installed, records `cleanup_status=failed` when possible, and reports the
residue rather than trying to restore an incomplete old pair.

This transaction handles in-process errors; it is not a crash journal.
Termination or power loss between filesystem operations can leave the
rollback directory for manual inspection.

## Compatibility

Existing schema-v2/v3 source, compiler, Web, and generated layout remain readable and unchanged. New authoring defaults to v4. Explicit regeneration is a complete new learner/author pair, not an in-place migration.
