# Verification profiles v4

Validation is split so every course proves its own content once while shared runtime behavior is proved once in Skill CI.

## Chapter-package mechanical validation

Run during assembly only:

- route chapter/task IDs match package IDs;
- required files exist and JSON/TOML parses;
- quiz `answer_id` resolves to a declared choice;
- owned paths are relative, conflict-free, in bounds, and not symlinks;
- Python files parse;
- declared starter/solution symbols exist;
- public and hidden selectors resolve; and
- learner projection contains no answers, solution, hidden tests/selectors, or author paths.

Do not inspect tutorial headings, length, keywords, semantic completeness, padding, repetition, definitions, design explanation, alternatives, benefits, or tradeoffs.

One failure list may be returned to the original chapter Writer once. A second failure stops generation.

## Per-course acceptance

Run once for the final learner/author candidate:

- collect every starter selector and prove each declared task has at least one
  failing selector (other selectors for that task may already pass);
- overlay the solution and prove every public+hidden selector is GREEN;
- inventory optional examples without executing or gating on them;
- exercise one real HTTP/API path through navigation, quiz, file save, public test, hidden submit, persisted completion, and next-chapter unlock;
- confirm content returns exact Markdown, explicit terms, sources, study time, first-task practice link, and no `lesson_outline`;
- confirm learner/author isolation; and
- write a receipt binding learner, author, runtime, verifier, and course-contract digests.

The course acceptance must not invoke npm, a Web build, lint, TypeScript, the browser matrix, dual-locale matrix, or the full Runner security suite.

## Shared engine conformance

Run when the Skill template, Web, Runner, or verifier changes:

- build the static SPA once;
- run TypeScript/lint and both locales;
- run the same mocked same-origin API journey in Chromium, Firefox, and WebKit;
- preserve Markdown heading navigation, terms, quiz, CodeMirror, save, public tests, hidden submit, progress, three gates, and responsive three-column behavior;
- run path traversal, absolute path, symlink, output limit, timeout, concurrency, descendant cleanup, and process-restart matrices;
- test static `/`, hashed assets, same-origin APIs, and JSON 404 for unknown `/api/*`;
- test learner/author contract mismatch and private-data redaction; and
- run compatibility fixtures for existing v2/v3 courses.

Generated v4 courses copy the certified static/runtime assets and record their digest. They do not repeat this matrix.

## Regeneration

- v2/v3 input remains byte-identical until explicit replacement.
- A targeted chapter request changes only that chapter package and derived projections.
- Content-prompt/Depth-Brief drift may call Writers; runtime/Web/verifier drift only re-exports or revalidates.
- Candidate acceptance runs once.
- `check` and `apply` recompute receipt bindings without rerunning the verifier.
- A changed candidate, receipt, route identity, runtime/verifier digest, unsafe path, symlink, or partial pair blocks replacement.
- Pair replacement uses one transient rollback directory. Handled pre-cleanup failures restore the original pair while bound paths remain intact; path interference fails closed. Before destructive cleanup, apply durably records `replacement_committed=true` and `cleanup_status=pending`; verified success deletes the previous learner/author trees and rollback directory, upgrades that receipt to `cleanup_status=complete`, retains no backup, and is irreversible. Partial cleanup or final receipt failure keeps the verified new pair installed and leaves a result that distinguishes committed replacement from rollback.
