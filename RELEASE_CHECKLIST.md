# Release checklist

Complete this checklist from a clean checkout before publishing a version.

## Metadata and legal

- [ ] The plugin version is valid semantic versioning and matches the intended Git tag.
- [ ] `plugin.json` and `marketplace.json` use the published plugin and marketplace names.
- [ ] Public author metadata contains no private email address or credential.
- [ ] Root and generated-template `LICENSE` and `NOTICE` files are byte-identical.
- [ ] `README.md` and `README.zh-CN.md` cross-link and publish matching installation, invocation, platform, language, and security instructions.

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
- [ ] Fresh `zh-CN` and `en` schema-v3 courses each pass split-source parity, README/Markdown, CLI, Web, Runner, privacy, and full verification.
- [ ] A real authoring trace shows exactly one non-reused `fork_turns="none"` writer per chapter, deterministic fragment assembly, and one separate clean-context whole-course review.
- [ ] Every new-format chapter has canonical `tutorial.md`, an intact structured `lesson.json` sidecar, byte-stable compiled Markdown, stable heading anchors, and a derived terminology guide; legacy v2/v3 lessons still render.
- [ ] Starter tests are RED only at declared learner interfaces.
- [ ] Reference implementations pass public and verified tests.
- [ ] CLI, Web, Runner, progression, build, and shutdown checks pass.
- [ ] Learner-visible output excludes reference code, verified-test bodies, readiness/profile metadata, diagnostic IDs, capability decisions, and readiness-derived lists.
- [ ] Browser checks at 1440x900, 1024x700, 900x700, and 390x844 confirm focus reading before the knowledge gate, no Code/Result or file request while locked, and the resizable workspace after unlock.
- [ ] A broad target stops at the track-selection gate before writing files.

## Existing-course regeneration

- [ ] Fresh scaffolding records closed schema-v2 generation provenance, the authoring fingerprint, and the private regeneration sidecar before its generated Git baseline; schema v2 contains no migration registry or `applied_migrations`.
- [ ] Fingerprint coverage includes Skill, teaching/architecture references, readiness, assembly, validation, scaffolding, verification, and canonical compiler/model, while README/release and runtime-only drift is excluded.
- [ ] A current matching fingerprint returns `up_to_date`; v0.1/v0.2 or invalid/missing sidecars require full readiness; same-version fingerprint collision and downgrade refuse to proceed.
- [ ] A valid v0.3+ sidecar reuses only readiness conclusions whose capability ID and definition hash are unchanged, and stores no raw answer, code evidence, or response text.
- [ ] `regenerate_course.py readiness COURSE --route CURRENT_ROUTE_JSON --json OUTPUT` produces `reuse_unchanged` only for verified, non-symlink input; `assess_readiness.py --trusted-course COURSE` rebinds it before use, while legacy/missing/tampered input yields `full_readiness`.
- [ ] Explicit-path regeneration locks locale, target/version, track, and route intent and never scans, upgrades the target, or uses old tutorial/code/test artifacts as writer input.
- [ ] Every candidate unit comes from a new clean writer, receives separate whole-course review, and the complete empty-only sibling candidate passes schema-v3, RED/GREEN, setup, and `verify_learning_project.py --full`.
- [ ] Candidate check blocks unchanged canonical source, provenance-only drift, learner-workspace-only drift, and absent authored learner-facing change; its digest detects every later old/candidate tree change.
- [ ] Legacy input must own its Git top level. Stale plan, symlink, containing roots, invalid result path, backup collision, failed verification, candidate drift, either rename failure, and post-swap snapshot failure leave or restore the old root byte-for-byte.
- [ ] Successful apply leaves the new path exactly equal to the verified candidate with fresh progress/Git baseline and preserves the complete old Git/state/code/custom/build tree in the permanent sibling backup.
- [ ] `update_course.py` fails closed with a regeneration pointer, the migration registry is absent, and Skill, architecture, curriculum, forward rubric, changelog, and bilingual README files describe one full-regeneration contract.

## Hosted GitHub settings and public verification

- [ ] The public repository exists at `https://github.com/I0G4N/python-library-course-builder`, and the repository, website, and `https://github.com/I0G4N/python-library-course-builder#readme` URLs resolve to it.
- [ ] GitHub Actions and Issues are enabled for the public repository.
- [ ] Private Vulnerability Reporting is enabled, and `https://github.com/I0G4N/python-library-course-builder/security/advisories/new` opens the private security report flow.
- [ ] The dependency graph, Dependabot alerts, and Dependabot security updates are enabled.
- [ ] A main branch ruleset and a v* tag ruleset protect the release branch and tags.
- [ ] The pinned public install command, `codex plugin marketplace add I0G4N/python-library-course-builder --ref v0.3.0`, succeeds from a clean Codex environment.
- [ ] Hosted main CI and the hosted v0.3.0 tag forward job pass for the release commit.

## Publication

- [ ] Git status is clean and the release commit has independent review approval.
- [ ] The local marketplace install succeeds without replacing the active standalone Skill prematurely.
- [ ] The development reinstall used a temporary `+codex.<timestamp>` cachebuster, and no cachebuster suffix appears in the release tag or manifest.
- [ ] The release tag points at the verified commit.
- [ ] The GitHub release links to the [changelog](CHANGELOG.md), license, security policy, and installation instructions.
- [ ] A clean temporary `CODEX_HOME` installs v0.3.0, and the local formal reinstall exposes the v0.3.0 Skill plus `regenerate_course.py` in a new Codex thread.
