# Changelog

All notable changes to Python Library Course Builder are documented in this file.

## [0.1.0] - 2026-07-14

### Added

- Initial release of the course builder for turning Python standard-library modules, packages, frameworks, and repositories into cumulative hands-on courses.
- A standalone CourseKit template with lessons, knowledge checks, coding Labs, pytest grading, CLI and Web workflows, and shared learner progression.
- Deterministic release validation for metadata, licenses, locks, Python and Node contracts, repository hygiene, and generated-template boundaries.
- Forward verification that generates a temporary standard-library course and proves its starter RED, reference GREEN, CLI, Web, Runner, progression, build, and shutdown contracts.

### Security and trust

- Direct URL dependencies must use immutable Git commits or SHA-256-pinned archives, and official-source URLs must not contain credentials or sensitive query parameters.
- Generated projects are authoring repositories: reference implementations and verified tests are teacher artifacts, not secrets from users with filesystem access.
- The local Runner reduces ordinary grading side effects but is not an operating-system sandbox; run only trusted course code and never expose it as a public judge.
