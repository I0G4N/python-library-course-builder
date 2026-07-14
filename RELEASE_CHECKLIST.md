# Release checklist

Complete this checklist from a clean checkout before publishing a version.

## Metadata and legal

- [ ] The plugin version is valid semantic versioning and matches the intended Git tag.
- [ ] `plugin.json` and `marketplace.json` use the published plugin and marketplace names.
- [ ] Public author metadata contains no private email address or credential.
- [ ] Root and generated-template `LICENSE` and `NOTICE` files are byte-identical.
- [ ] README installation, invocation, platform, and security instructions match verified behavior.

## Base and local validation

- [ ] The base CI gate, `uv run python scripts/validate_release.py`, passes under Python 3.13.
- [ ] The complete root Python suite passes under Python 3.13.
- [ ] All bundled Node contract tests pass under Node.js 22.13 or newer.
- [ ] The public Agent Skills validator passes as part of the base gate.
- [ ] The local Codex gate, `uv run python scripts/validate_release.py --codex-validators`, passes the official Skill quick validator and plugin validator from `CODEX_HOME`.
- [ ] Lock files are current and install in locked/offline verification modes.
- [ ] Repository scans find no secret, symlink, unresolved token, absolute generator path, or legacy course branding.

## Forward verification

- [ ] The release-candidate gate, `uv run python scripts/validate_release.py --codex-validators --forward`, passes.
- [ ] A small standard-library target generates into an empty directory.
- [ ] Starter tests are RED only at declared learner interfaces.
- [ ] Reference implementations pass public and verified tests.
- [ ] CLI, Web, Runner, progression, build, and shutdown checks pass.
- [ ] Learner-visible output excludes reference code and verified-test bodies.
- [ ] A broad target stops at the track-selection gate before writing files.

## Publication

- [ ] Git status is clean and the release commit has independent review approval.
- [ ] The local marketplace install succeeds without replacing the active standalone Skill prematurely.
- [ ] The release tag points at the verified commit.
- [ ] The GitHub release links to the [changelog](CHANGELOG.md), license, security policy, and installation instructions.
