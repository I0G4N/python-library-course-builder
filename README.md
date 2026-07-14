# Python Library Course Builder

[![CI](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml)

Python Library Course Builder is a skill-only Codex plugin that turns a Python standard-library module, package, framework, or repository into a Chinese-first structured learning project. It produces one cumulative course with beginner-oriented lessons, knowledge checks, coding Labs, pytest grading, a CLI, and a local Web workspace.

Version 0.1.0 uses Simplified Chinese for learner-facing lessons, quiz prompts, feedback, generated documentation, and course prose. Code, shell commands, identifiers, target API names, and official source titles and URLs remain in their original form; this release has no language switch.

The bundled Skill is named `$building-python-library-courses`.

## What it builds

Each generated course contains:

- an ungraded Lab 00 for foundations and environment checks;
- a connected `lab01` through `labNN` route that grows one capstone;
- detailed definitions, mechanisms, design reasons, tradeoffs, examples, and diagnostics;
- quiz-first progression before each coding workspace unlocks;
- public tests, verified tests, reference implementations, and deterministic local grading;
- one shared progress model across the CLI and Web interface;
- an adjustable three-column desktop workspace and responsive smaller layouts.

The route alternates between a small teaching-equivalent of a mechanism and a graded bridge to the target library's official API. Later Labs use the official API for capabilities already learned, so the course becomes one integrated project rather than a set of isolated exercises.

## prerequisites

- Codex with plugin and Skill support.
- Python 3.13 for Skill automation and release verification.
- [uv](https://docs.astral.sh/uv/) for isolated Python environments.
- Node.js 22.13 or newer, including npm, for the generated Web workspace.
- Git for checkpoints and repository workflows.

The supported local environments are macOS, Linux, and WSL2 with the project stored in the Linux filesystem. Native Windows is not a verified execution path.

Course creation requires Codex plus network access to verify official sources and install dependencies. After setup, mandatory examples and grading are CPU/offline. No GPU, API key, paid service, cloud account, or external database is required.

## Install from GitHub

Add the repository as a Codex marketplace, then install the plugin:

```bash
codex plugin marketplace add I0G4N/python-library-course-builder --ref v0.1.0
codex plugin add python-library-course-builder@python-library-course-builder
```

See the [official Codex plugin authoring and installation documentation](https://learn.chatgpt.com/docs/build-plugins#add-a-marketplace-from-the-cli) for the current marketplace workflow.

## Install from a local checkout

From the directory that will contain the checkout, clone the repository, register its relative marketplace path, and install the plugin:

```bash
git clone --branch v0.1.0 --depth 1 https://github.com/I0G4N/python-library-course-builder.git
codex plugin marketplace add ./python-library-course-builder
codex plugin add python-library-course-builder@python-library-course-builder
```

Start a new Codex thread after installation so the new Skill is discovered.

## Use the Skill

Ask Codex to invoke the Skill and name the Python target plus an empty destination. For example:

```text
Use $building-python-library-courses to create a beginner course for pathlib in ../pathlib-course.
```

The Skill first inspects the local target and verifies claims against primary official sources. Small and medium targets receive a bounded cumulative route. A broad target receives a choice of coherent tracks before any course files are created.

Generation is empty-destination-only. The Skill validates the course specification, copies the standalone CourseKit template, compiles the canonical source, proves the starter/reference RED-GREEN contract, and checks CLI, Web, Runner, progression, and privacy boundaries before handoff.

After generation, enter the generated repository, install its locked dependencies, and start the learning loop:

```bash
cd /path/to/generated-course
npm run setup
npm run learn
```

## Repository layout

```text
.
├── .agents/plugins/marketplace.json
├── plugins/python-library-course-builder/
│   ├── .codex-plugin/plugin.json
│   └── skills/building-python-library-courses/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       ├── assets/course-template/
│       ├── references/
│       └── scripts/
└── tests/
```

The plugin bundle contains only the Skill and its local assets. It does not declare an app, MCP server, cloud connector, or direct Codex capability.

## Authoring and trust boundary

A generated project is an **authoring repository**: it contains the canonical course source, learner projection, reference implementations, and verified grader material needed to build and audit the course.

Hidden tests are not secret when the complete repository is available. They are hidden from the normal learner workspace to avoid accidental hints, but a user with filesystem access can inspect teacher artifacts. Version 0.1.0 does not provide an automated learner-only export. The supported secrecy path is to keep the complete teacher/authoring repository private.

The local Runner is a study tool, not an operating-system security sandbox. It reduces ordinary grading side effects and binds to loopback, but submitted Python executes with the current user's privileges. Run only trusted local course code, never expose the Runner as a public judge, and use a separate hardened sandbox for hostile submissions.

See [SECURITY.md](SECURITY.md) for reporting and deployment boundaries.

## Independent implementation

This project is independently authored. CS61A and CS336 influenced the broad idea of interactive knowledge checks and test-driven assignments, but no course code, assignments, tests, or instructional text from those courses is bundled here. This project is not affiliated with or endorsed by UC Berkeley, the course staff, or OpenAI.

## Contributing and releases

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing the Skill, template, or validators. Review the [changelog](CHANGELOG.md) for published changes. Maintainers should complete [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before tagging a release.

## License

Licensed under the [Apache License 2.0](LICENSE). Generated course templates receive the same `LICENSE` and `NOTICE` files.
