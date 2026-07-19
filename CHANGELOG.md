# Changelog

All notable changes to Python Library Course Builder are documented in this file.

## [Unreleased]

## [0.3.0] - 2026-07-18

### Added

- Added clean-context chapter authoring: every orientation, preparation, and graded Lab is written by a distinct non-reused subagent from a sanitized packet, assembled deterministically, and reviewed in a separate clean context.
- Added schema-v3 `tutorial-markdown-v1`, canonical `tutorial.md` chapter sources, exact Markdown compilation, stable heading navigation, and terminology guides while retaining structured lesson sidecars and legacy v2/v3 rendering.
- Added a focus-reading Web layout with a rich chapter/check rail on wide screens and responsive single-column reading before the coding workspace unlocks.
- Added deterministic schema-v2 generation provenance with an authoring-capability fingerprint and private regeneration-input digest.
- Added the private `platform/coursekit-regeneration.json` route/readiness sidecar without raw diagnostic answers or code evidence.
- Added two-phase `regenerate_course.py check/apply` replacement for explicitly located courses, with full sibling-course verification, permanent whole-root backup, stale-plan protection, and rollback.

### Changed

- Kept readiness diagnostics entirely author-side. Generated learner README files, manifests, content, sidebar copy, and public APIs no longer expose profiles, capability decisions, diagnostic summaries, or readiness-derived lists.
- Made tutorial quality depend on progressive explanation, first-use term definitions, concrete value flow, boundary recovery, and aligned practice instead of a rigid learner-facing field template or word-count target.
- Expanded future `prepNN` and graded `labNN` tutorials with a same-mainline architecture and interface lens covering component responsibilities, dependency and data/control flow, chosen versus credible alternative designs, benefits and tradeoffs, applicability, and revisit conditions; `lab00`, the schema, activities, scoring, and runtime remain unchanged.
- Routed an explicitly located course through its fixed language, target/version, track, and route intent instead of the fresh-course language gate.
- Made authoring-capability drift trigger complete research, readiness, clean-writer authoring, scaffold, RED/GREEN, and full verification. A valid v0.3+ sidecar reuses only readiness conclusions whose capability ID and definition hash are unchanged; legacy courses reassess the full route.
- Replaced the old course only after canonical source and substantive learner-facing content change. The replacement uses fresh progress and Git baseline; the old course, learner work, custom files, state, and Git history remain intact in the permanent backup.

### Removed

- Removed the course-impacting migration registry and incremental content-update semantics. `update_course.py` is retained only as a fail-closed pointer to full regeneration.

## [0.2.0] - 2026-07-15

### Added

- Added a mandatory first-question language choice on every fresh Skill invocation, with exactly `zh-CN` and `en` supported even when the original request already names a language.
- Made readiness questions, lessons, quizzes, feedback, generated documentation, CLI output, and Web presentation language-selectable without translating code, commands, identifiers, API names, or official source titles and URLs.
- Added complete, locale-specific positive teaching examples and fail-closed language parity from the readiness route through the generated course and handoff.
- Made the root README English-first and added a complete Simplified Chinese translation with reciprocal language navigation.

### Changed

- Repositioned plugin discovery metadata from Chinese-first to language-selectable while preserving Chinese and English as the only supported course locales.

## [0.1.1] - 2026-07-15

### Fixed

- Made the generated Web workspace fit short and resized browser windows with independently scrollable desktop panes, a stacked tablet layout from 760 through 1023 pixels, and natural document scrolling on mobile.
- Changed preparation-unit navigation badges from route-position numbers to stable `P01`, `P02`, ... labels while preserving `00`, `01`, ... for Labs.
- Kept `lab00` and every `prepNN` knowledge-only, and made each formal Lab reveal its Code and Result workspace only after that Lab's knowledge checks are complete.

## [0.1.0] - 2026-07-15

### Added

- A Chinese-first v0.1.0 authoring contract: learner-facing lessons, quiz prompts, feedback, generated documentation, and course prose use Simplified Chinese, while code and official-source identifiers stay in their original form; this release has no language switch.
- Initial release of the course builder for turning Python standard-library modules, packages, frameworks, and repositories into cumulative hands-on courses.
- A bilingual, CS61A-style public introduction grounded in cumulative projects, ordered progression, and deterministic feedback, with an explicit independent-implementation boundary.
- A standalone CourseKit template with lessons, knowledge checks, coding Labs, pytest grading, CLI and Web workflows, and shared learner progression.
- A deterministic `evidence-dialogue` readiness preflight that fixes the selected route, derives a prerequisite capability DAG from official sources, reuses concrete code and matching diagnostic evidence, asks one unresolved question at a time, and blocks specification or destination creation until the plan is `ready`.
- Schema v3 preparation with a fixed `lab00` orientation plus zero or more DAG-ordered `prepNN` knowledge units. Prep has no code workspaces, scores, or submissions; formal Labs are the only scored work and unlock only after required preparation is complete.
- Matching readiness-plan gates in validation and scaffolding, with missing, incomplete, tampered, or mismatched plans rejected before destination writes and raw learner answers kept out of generated repositories.
- Shared CLI, Web, and Runner progression and knowledge state, including prep workspace and file/run API denial, score isolation, restart persistence, and readiness-specific curriculum IDs.
- Schema-v2 compatibility across validation, compilation, generated artifacts, and runtime progression while all newly authored courses use schema v3.
- Detailed learner projections for exact study time, operational contracts, concrete execution traces, and task-linked practice across generated README, lesson, CLI, and Web views.
- Deterministic release validation for metadata, licenses, locks, Python and Node contracts, repository hygiene, and generated-template boundaries.
- Forward verification that generates a temporary standard-library course and proves its starter RED, reference GREEN, CLI, Web, Runner, progression, build, and shutdown contracts.

### Security and trust

- Direct URL dependencies must use immutable Git commits or SHA-256-pinned archives, and official-source URLs must not contain credentials or sensitive query parameters.
- Generated projects are authoring repositories: reference implementations and verified tests are teacher artifacts, not secrets from users with filesystem access.
- The local Runner reduces ordinary grading side effects but is not an operating-system sandbox; run only trusted course code and never expose it as a public judge.
