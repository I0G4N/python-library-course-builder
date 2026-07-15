# Changelog

All notable changes to Python Library Course Builder are documented in this file.

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
