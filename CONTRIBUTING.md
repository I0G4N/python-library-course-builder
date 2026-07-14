# Contributing

Thank you for improving Python Library Course Builder. Changes should preserve its central contract: one source-backed, cumulative learning route for a beginner, with deterministic local examples and grading.

## Development prerequisites

- Python 3.13
- uv
- Node.js 22.13 or newer with npm
- Git

Development and generated-project verification are supported on macOS, Linux, and WSL2.

## Change workflow

1. Open an Issue or focused proposal for a substantial curriculum, schema, security, or runtime change.
2. Add or update a failing repository contract before changing behavior.
3. Make the smallest generator, template, or documentation change that satisfies the contract.
4. Run the focused test, the complete root suite, Node contract tests, and the official Skill and plugin validators.
5. For a generator or template change, generate a fresh bounded course into an empty directory and run its full verifier.
6. Keep commits scoped and explain any compatibility or curriculum-ID consequence.

Do not weaken a valid test simply to make a reference projection pass. Fix reusable defects in the Skill, compiler, or template rather than hand-editing one generated example.

## Validation

Install the exact locked development environment:

```bash
uv sync --locked
```

Run the base CI gate:

```bash
uv run python scripts/validate_release.py
```

This is the normal CI gate. It checks repository contracts and hygiene, Python and Node suites, lock files, the public Agent Skills validator, metadata, and worktree stability without requiring a local Codex installation.

Run the local Codex validator gate when Codex is installed and its official validators are available under `CODEX_HOME`:

```bash
uv run python scripts/validate_release.py --codex-validators
```

This runs the base gate plus the official Codex Skill quick validator and plugin validator. Normal CI does not depend on those installation-specific validator paths.

Run the complete release-candidate gate before publishing:

```bash
uv run python scripts/validate_release.py --codex-validators --forward
```

This runs both validation layers, then generates, sets up, and fully verifies a temporary standard-library course. CI also runs forward generation on its scheduled and tagged release path without depending on local `CODEX_HOME`. Run all three gates from the repository root with the prerequisite Python, uv, Node.js, and Git versions listed above.

## Documentation and evidence

Teach public behavior from primary official documentation and upstream source. Distinguish documented guarantees from implementation details, pin the taught version, and keep examples deterministic and CPU/offline runnable.

The bundled course design is independently authored. Contributions must not copy proprietary or course-restricted assignments, solutions, tests, or prose. Include attribution and license compatibility for any permitted third-party material.

## Security and privacy

Run only trusted code during local verification. Never include real credentials, personal information, or private vulnerability details in commits, fixtures, Issues, or pull requests. See [SECURITY.md](SECURITY.md) for the reporting channel and execution boundary.

Reference solutions and hidden tests are teacher artifacts, not a secrecy mechanism in a public authoring repository. Avoid claims that browser gating prevents filesystem inspection.

## Pull requests

A pull request should state:

- the learner or maintainer problem being solved;
- the failing contract that demonstrated it;
- exact verification commands and outcomes;
- generated-course evidence when template behavior changed;
- security, compatibility, and migration implications.

By contributing, you agree that your contribution is licensed under Apache-2.0.
