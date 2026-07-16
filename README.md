# Learn Any Python Library the Way You'd Work Through CS61A

English | [简体中文](README.zh-CN.md)

[![CI](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml)

**Python Library Course Builder** is a Skill-only Codex plugin that turns a Python standard-library module, PyPI package, framework, or source repository into a cumulative project course in Simplified Chinese or English.

> Stop grinding through an API reference from page one. Give the Skill a Python library and receive a route you can finish, verify, and turn into a portfolio project.

In one sentence: choose a course language, fix one coherent route, use reviewable evidence to assess what you already know, receive prep only for route capabilities assessed as missing, and grow one cumulative project until you can use, debug, and explain the target library.

No CS61A code, assignments, tests, or instructional text are included, and this independently authored project is not affiliated with or endorsed by UC Berkeley, the CS61A course staff, or OpenAI.

Version 0.2.0 supports exactly two course languages: Simplified Chinese (`zh-CN`) and English (`en`). On every fresh Skill invocation, language choice is the first question even when the request already names a language. Learner-facing lessons, readiness questions, quiz prompts, feedback, generated documentation, and course prose use the selected language. Code, shell commands, identifiers, target API names, and official source titles and URLs retain their original spelling.

The bundled Skill is named `$building-python-library-courses`.

## Why this is a course, not a documentation tour

| Typical library tutorial | Python Library Course Builder |
|---|---|
| Gives everyone the same starting point | Assesses route capabilities from reviewable code and diagnostic evidence |
| Walks through an API index | Follows a capability DAG and one cumulative project |
| Treats reading an example as mastery | Uses quizzes, tests, Runner checks, and unlock state |
| Leaves prerequisite gaps to the learner | Generates `prep01` through `prepNN` only for assessed gaps |
| Ends each chapter with an isolated demo | Makes every formal Lab extend the same capstone |

Here, "CS61A-style" means cumulative practice, ordered progression, mechanism understanding, and deterministic feedback. It does not mean official cooperation or reuse of CS61A content. For a large framework or repository, the Skill asks the learner to select one coherent route instead of pretending one course can cover every API.

Each schema-v3 course contains:

- a fixed, ungraded `lab00` for environment setup and the learning workflow;
- zero or more knowledge-only `prep01` through `prepNN` units derived from assessed prerequisite gaps;
- a connected `lab01` through `labNN` route that grows one capstone;
- long-form tutorial chapters with progressive explanations, first-use definitions for technical terms, complete examples, boundaries, diagnosis, and execution traces;
- quiz-first progression before each formal Lab coding workspace unlocks;
- public tests, verified tests, reference implementations, and deterministic local grading for formal Labs only;
- one shared progression and knowledge state across the CLI, Web interface, and Runner; and
- a focus-reading layout before the knowledge gate and an adjustable lesson/code workspace afterward.

## Learn only what the route proves you need

Every fresh invocation begins with one blocking choice between Simplified Chinese (`zh-CN`) and English (`en`). The Skill asks even if the original request already specifies a language, never infers from the conversation language or locale, and does nothing else until the learner answers with one supported choice.

Before any course specification or destination is created, the Skill fixes the selected route, derives its prerequisite capability DAG from primary official sources, and runs a deterministic **evidence-dialogue readiness preflight**. It reuses concrete code and matching diagnostic responses, then asks exactly one prediction, code-reading, or micro-code question for each still-unknown capability. A claim of mastery is a claim rather than proof; a direct admission of not knowing can establish a gap.

Raw answers and code evidence stay in a temporary readiness report. A completed readiness plan records every resolved route capability; its preparatory units group only capabilities assessed as missing, by DAG level and then by `python -> library -> domain`. The plan reports total preparatory time before authoring and binds progress to an isolated curriculum identity.

The generated learner course does not publish that diagnosis. Its README, lessons, manifests, sidebar, content payloads, and public APIs omit the prerequisite profile, capability decisions, evidence classes, diagnostic IDs, route/readiness summaries, and assumed/missing lists. A prep unit teaches its subject as an ordinary, self-contained chapter rather than telling the learner what an assessment concluded about them.

`lab00` is always the environment and learning-loop orientation. When preparation is required, the course adds `prep01`, `prep02`, ... in prerequisite order. When every required capability is assessed as mastered, it invents no prep at all.

## One clean writer per chapter

The parent course author fixes the route, official sources, unit IDs, concept/outcome contracts, code interfaces, tests, mechanism cycle, official bridges, and capstone increments before prose authoring begins. It then launches one new clean-context subagent for each `lab00`, `prepNN`, and `labNN`; a writer is never reused for a second chapter and receives no readiness answers or learner-profile fields.

Each writer returns an isolated tutorial fragment. A deterministic assembler requires exactly one fragment for every expected unit and rejects missing, duplicate, unexpected, ID-mismatched, or contract-mutating output. A separate clean-context reviewer checks the complete course, and a rejected chapter is regenerated by a new writer. If clean subagents are unavailable, the Skill stops instead of silently writing every chapter in the parent context.

The result is authored Markdown whose structure follows the subject like a tutorial or textbook, while a structured lesson sidecar continues to carry source claims, operational contracts, traces, and activity mappings for deterministic validation. Quality is judged by explanatory continuity, concrete values, term definitions, boundary reasoning, and aligned practice—not by a rigid heading template or word-count quota.

## From Lab 00 to capstone, build one thing

The route alternates between a small teaching-equivalent of a mechanism and a graded bridge to the target library's official API. Later Labs use the official API for capabilities already learned, so the course becomes one integrated project rather than a collection of isolated exercises.

`lab01` unlocks only after the final prep. With no assessed prerequisite gaps, it depends directly on `lab00`. Existing schema v2 courses remain compatible, while the Skill authors new courses only as schema v3.

Each chapter turns its learning goals into operational contracts for inputs, outputs, state changes, errors, and recovery. Concrete execution traces follow real values through the target mechanism before implementation. Authored `tutorial.md` is the primary reading surface; the structured `lesson.json` remains a validation and navigation sidecar. Lessons keep task-linked practice beside the concept it checks, and every graded task points back to the chapter knowledge and capstone behavior it exercises.

## Prep is knowledge-only by design

Each `prepNN` is a standalone lecture in the selected course language with a concrete execution trace, diagnostic example, and knowledge quiz, but it has no code workspace, points, or submission. Prep file and execution APIs are denied by the Runner, and prep never contributes to the course score.

CLI, Web, and Runner consume the same order and knowledge state. Only `lab00` is initially navigable; each prep unlocks after the previous unit is mastered, and formal Labs add coding verification on top of the knowledge gate.

## Prerequisites

- Codex with plugin and Skill support.
- Python 3.13 for Skill automation and release verification.
- [uv](https://docs.astral.sh/uv/) for isolated Python environments.
- Node.js 22.13 or newer, including npm, for the generated Web workspace.
- Git for checkpoints and repository workflows.

The supported local environments are macOS, Linux, and WSL2 with the project stored in the Linux filesystem. Native Windows is not a verified execution path.

Course creation requires Codex plus network access to verify official sources and install dependencies. After setup, mandatory examples and grading are CPU/offline. No GPU, API key, paid service, cloud account, or external database is required.

## Install

### Install from GitHub

Add the repository as a Codex marketplace, then install the plugin:

```bash
codex plugin marketplace add I0G4N/python-library-course-builder --ref v0.2.0
codex plugin add python-library-course-builder@python-library-course-builder
```

See the [official Codex plugin authoring and installation documentation](https://learn.chatgpt.com/docs/build-plugins#add-a-marketplace-from-the-cli) for the current marketplace workflow.

### Install from a local checkout

From the directory that will contain the checkout, clone the repository, register its relative marketplace path, and install the plugin:

```bash
git clone --branch v0.2.0 --depth 1 https://github.com/I0G4N/python-library-course-builder.git
codex plugin marketplace add ./python-library-course-builder
codex plugin add python-library-course-builder@python-library-course-builder
```

Start a new Codex thread after installation so the new Skill is discovered.

## Use the Skill

Ask Codex to invoke the Skill and name the Python target plus an empty destination. For example:

```text
Use $building-python-library-courses to create a beginner course for pathlib in ../pathlib-course.
```

The Skill always asks the course-language question first. After that answer, it inspects the local target and verifies claims against primary official sources. Small and medium targets receive a bounded cumulative route. A broad target receives a choice of coherent tracks before any course files are created.

Once the route is fixed, the Skill must obtain a complete readiness plan before authoring a new schema-v3 specification or touching the destination. Validation and scaffolding reject a missing, incomplete, tampered, language-mismatched, or otherwise inconsistent plan before any destination write.

Generation remains empty-destination-only. With a matching ready plan, the Skill validates the course specification, copies the standalone CourseKit template, compiles the canonical source, proves the starter/reference RED-GREEN contract, and checks CLI, Web, Runner, progression, scoring, language, and privacy boundaries before handoff.

After generation, enter the generated repository, install its locked dependencies, and start the learning loop:

```bash
cd /path/to/generated-course
npm run setup
npm run learn
```

## Repository layout

```text
.
|-- .agents/plugins/marketplace.json
|-- plugins/python-library-course-builder/
|   |-- .codex-plugin/plugin.json
|   `-- skills/building-python-library-courses/
|       |-- SKILL.md
|       |-- agents/openai.yaml
|       |-- assets/course-template/
|       |-- references/
|       `-- scripts/
`-- tests/
```

The plugin bundle contains only the Skill and its local assets. It does not declare an app, MCP server, cloud connector, or direct Codex capability.

## Authoring and trust boundary

A generated project is an **authoring repository**: it contains the canonical course source, learner projection, reference implementations, and verified grader material needed to build and audit the course.

Hidden tests are not secret when the complete repository is available. They are hidden from the normal learner workspace to avoid accidental hints, but a user with filesystem access can inspect teacher artifacts. Version 0.2.0 does not provide an automated learner-only export. The supported secrecy path is to keep the complete teacher/authoring repository private.

The local Runner is a study tool, not an operating-system security sandbox. It reduces ordinary grading side effects and binds to loopback, but submitted Python executes with the current user's privileges. Run only trusted local course code, never expose the Runner as a public judge, and use a separate hardened sandbox for hostile submissions.

See [SECURITY.md](SECURITY.md) for reporting and deployment boundaries.

## Independent implementation

This project is independently authored. CS61A and CS336 influenced the broad idea of interactive knowledge checks and test-driven assignments, but no course code, assignments, tests, or instructional text from those courses is bundled here. This project is not affiliated with or endorsed by UC Berkeley, the course staff, or OpenAI.

## Contributing and releases

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing the Skill, template, or validators. Review the [changelog](CHANGELOG.md) for published changes. Maintainers should complete [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before tagging a release.

## License

Licensed under the [Apache License 2.0](LICENSE). Generated course templates receive the same `LICENSE` and `NOTICE` files.
