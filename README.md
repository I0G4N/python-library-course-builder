# Learn Any Python Library the Way You'd Work Through CS61A

English | [简体中文](README.zh-CN.md)

[![CI](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml)

**Python Library Course Builder** is a Skill-only Codex plugin that turns a Python standard-library module, PyPI package, framework, or source repository into a cumulative project course in Simplified Chinese or English.

> Stop grinding through an API reference from page one. Give the Skill a Python library and receive a route you can finish, verify, and turn into a portfolio project.

In one sentence: choose a course language, fix one coherent route, use reviewable evidence to assess what you already know, receive prep only for route capabilities assessed as missing, and grow one cumulative project until you can use, debug, and explain the target library.

No CS61A code, assignments, tests, or instructional text are included, and this independently authored project is not affiliated with or endorsed by UC Berkeley, the CS61A course staff, or OpenAI.

Version 0.3.0 supports exactly two course languages: Simplified Chinese (`zh-CN`) and English (`en`). On every fresh Skill invocation, language choice is the first question even when the request already names a language. Learner-facing lessons, readiness questions, quiz prompts, feedback, generated documentation, and course prose use the selected language. Code, shell commands, identifiers, target API names, and official source titles and URLs retain their original spelling.

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

Each new schema-v4 course contains:

- a fixed, ungraded `lab00` for environment setup and the learning workflow;
- zero or more knowledge-only `prep01` through `prepNN` units derived from assessed prerequisite gaps;
- a connected `lab01` through `labNN` route that grows one capstone;
- free-form Markdown chapters whose depth comes from one focused mechanism, a concrete walkthrough, interface and design reasoning, and a recoverable boundary case;
- quiz-first progression before each formal Lab coding workspace unlocks;
- public tests, hidden submissions, private solutions, and deterministic local grading for formal Labs only;
- one shared progression and knowledge state across the Web interface and Runner; and
- a focus-reading layout before the knowledge gate and an adjustable lesson/code workspace afterward.

## Learn only what the route proves you need

Every fresh invocation begins with one blocking choice between Simplified Chinese (`zh-CN`) and English (`en`). The Skill asks even if the original request already specifies a language, never infers from the conversation language or locale, and does nothing else until the learner answers with one supported choice.

Before any course specification or destination is created, the Skill fixes the selected route, derives its prerequisite capability DAG from primary official sources, and runs a deterministic **evidence-dialogue readiness preflight**. It reuses concrete code and matching diagnostic responses, then asks exactly one prediction, code-reading, or micro-code question for each still-unknown capability. A claim of mastery is a claim rather than proof; a direct admission of not knowing can establish a gap.

Raw answers and code evidence stay in a temporary readiness report. A completed readiness plan records every resolved route capability; its preparatory units group only capabilities assessed as missing, by DAG level and then by `python -> library -> domain`. The plan reports total preparatory time before authoring and binds progress to an isolated curriculum identity.

The generated learner course does not publish that diagnosis. Its README, lessons, manifests, sidebar, content payloads, and public APIs omit the prerequisite profile, capability decisions, evidence classes, diagnostic IDs, route/readiness summaries, and assumed/missing lists. A prep unit teaches its subject as an ordinary, self-contained chapter rather than telling the learner what an assessment concluded about them.

`lab00` is always the environment and learning-loop orientation. When preparation is required, the course adds `prep01`, `prep02`, ... in prerequisite order. When every required capability is assessed as mastered, it invents no prep at all.

## One complete package per chapter Writer

The parent course author fixes the route, official facts, chapter goals, task IDs, public interfaces, test selectors, owned paths, and capstone increments. For each chapter it creates a private, compact Depth Brief centered on one core question, one walkthrough case, one boundary case, the chosen design, and one credible alternative.

One clean-context Writer receives only that chapter's brief, relevant official facts, locked task contracts, and owned paths. In one call it plans, writes, silently checks, and revises a complete package: `tutorial.md`, terms, quiz, starter, solution, public tests, hidden tests, and optional examples. It outputs only the finished package.

There is no whole-course Reviewer, replacement Writer, depth score, word-count gate, semantic completeness check, or structured lesson sidecar. `tutorial.md` is the only prose source of truth and may use any headings, order, and length. Depth is a writing obligation in the prompt, not a property the output schema pretends to prove.

The assembler checks only what execution requires: IDs, required files and parseability, quiz answer references, owned-path safety, Python syntax, test selectors, declared symbols, and learner/author isolation. A mechanical failure is returned to the same Writer once. If it still fails, generation stops instead of starting a review loop.

## From Lab 00 to capstone, build one thing

The route alternates between a small teaching-equivalent of a mechanism and a graded bridge to the target library's official API. Later Labs use the official API for capabilities already learned, so the course becomes one integrated project rather than a collection of isolated exercises.

`lab01` unlocks only after the final prep. With no assessed prerequisite gaps, it depends directly on `lab00`. Existing schema-v2/v3 courses remain compatible, while new authoring uses schema v4.

Each chapter follows one knowledge mainline. Its tutorial, quiz, code, and tests share the same concrete case and behavior boundary. Integration and capstone chapters compose the public interfaces introduced earlier rather than reaching into another chapter's implementation.

## Prep is knowledge-only by design

Each `prepNN` is a standalone lecture in the selected course language with a concrete execution trace, diagnostic example, and knowledge quiz, but it has no code workspace, points, or submission. Prep file and execution APIs are denied by the Runner, and prep never contributes to the course score.

The Web interface and Runner consume the same order and knowledge state. Only `lab00` is initially navigable; each prep unlocks after the previous unit is mastered, and formal Labs add coding verification on top of the knowledge gate.

## Prerequisites

- Codex with plugin and Skill support.
- Python 3.13 for Skill automation and release verification.
- [uv](https://docs.astral.sh/uv/) for isolated Python environments.
- Node.js 22.13 or newer, including npm, only for plugin contributors who rebuild or test the shared Web runtime.
- Git for course history and repository workflows.

The supported local environments are macOS, Linux, and WSL2 with the project stored in the Linux filesystem. Native Windows is not a verified execution path.

Course creation requires Codex plus network access to verify official sources and install dependencies. After setup, mandatory examples and grading are CPU/offline. No GPU, API key, paid service, cloud account, or external database is required.

## Install

### Install from GitHub

Add the repository as a Codex marketplace, then install the plugin:

```bash
codex plugin marketplace add I0G4N/python-library-course-builder --ref v0.3.0
codex plugin add python-library-course-builder@python-library-course-builder
```

See the [official Codex plugin authoring and installation documentation](https://learn.chatgpt.com/docs/build-plugins#add-a-marketplace-from-the-cli) for the current marketplace workflow.

### Install from a local checkout

From the directory that will contain the checkout, clone the repository, register its relative marketplace path, and install the plugin:

```bash
git clone --branch v0.3.0 --depth 1 https://github.com/I0G4N/python-library-course-builder.git
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

Once the route is fixed, the Skill obtains a complete readiness plan before authoring schema v4 or touching the destination. The parent locks the mechanical route, then one Writer creates each complete chapter package.

Generation remains empty-destination-only. The scaffolder creates separate learner and sibling author projections, copies the prebuilt Web runtime without running npm, and performs minimal mechanical checks. One final acceptance proves aggregate starter RED, solution public+hidden GREEN, the three progression gates, and a real public-test/hidden-submit API flow.

After generation, enter the generated repository, install its dependencies, and start the learning loop:

```bash
cd /path/to/generated-course
uv sync
uv run course
```

## Regenerate only what changed

Give the Skill one explicit existing-course path to enter regeneration mode:

```text
Use $building-python-library-courses to regenerate the existing generated course at /path/to/course.
```

The existing course fixes its language, pinned target version, selected track, task IDs, interfaces, and route intent. Schema-v2/v3 courses stay unchanged; explicit regeneration produces a complete v4 learner/author pair.

The workflow first creates a read-only plan outside the course:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/regenerate_course.py" check /path/to/course --json /tmp/course-regeneration-plan.json
```

Schema v4 stores separate content and runtime contract digests. A prompt or Depth-Brief contract change recalls chapter Writers. A Web, Runner, exporter, or verifier change only re-exports or revalidates existing content.

If one chapter is shallow, generate a narrowly scoped request:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/regenerate_course.py" chapter /path/to/course --chapter lab03 --reason "make the ownership boundary predictable" --json /tmp/chapter-regeneration.json
```

Only that chapter Writer is recalled with locked route metadata, task contracts, selectors, and owned paths; other chapters remain unchanged.

After a rebuilt learner/author candidate has one valid acceptance receipt, bind it to the replacement plan:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/regenerate_course.py" check /path/to/course --candidate-course /path/to/course-staging --json /tmp/course-regeneration-plan.json
```

After reviewing the destructive replacement plan and stopping course services, accept whole-root replacement:

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/regenerate_course.py" apply /path/to/course --candidate-course /path/to/course-staging --plan /tmp/course-regeneration-plan.json --confirm-stopped --accept-replacement --json /tmp/course-regeneration-result.json
```

Apply replaces the learner and author directories as one transaction. The old pair exists only in a transient rollback directory during apply. A handled failure before cleanup restores the originals when the bound paths remain intact; path interference fails closed and reports manual recovery. After the new pair is installed and post-swap validation succeeds, CourseKit durably writes `replacement_committed=true` and `cleanup_status=pending` to the requested result JSON before deleting the old pair. It reports success only after the rollback directory is absent and the result has been atomically upgraded to `cleanup_status=complete`. If cleanup or that final upgrade fails, the verified new pair stays installed and the earlier result still identifies a committed replacement; the nonzero command reports the remaining action on stderr. No backup is retained after success, so a successful replacement is irreversible.

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
|       |-- assets/course-template-v4/
|       |-- references/
|       `-- scripts/
`-- tests/
```

The plugin bundle contains only the Skill and its local assets. It does not declare an app, MCP server, cloud connector, or direct Codex capability.

## Learner/author trust boundary

A v4 generation creates a learner project and a separate sibling author project. The learner tree contains tutorials, redacted quizzes, starter code, public tests, the Web app, and the Runner. The author tree contains quiz answers, solutions, hidden tests, and the verification receipt.

Keep the author sibling private. Hidden tests are an assessment boundary rather than a defense against a user who can read that directory.

The local Runner is a study tool, not an operating-system security sandbox. It reduces ordinary grading side effects and binds to loopback, but submitted Python executes with the current user's privileges. Run only trusted local course code, never expose the Runner as a public judge, and use a separate hardened sandbox for hostile submissions.

See [SECURITY.md](SECURITY.md) for reporting and deployment boundaries.

## Independent implementation

This project is independently authored. CS61A and CS336 influenced the broad idea of interactive knowledge checks and test-driven assignments, but no course code, assignments, tests, or instructional text from those courses is bundled here. This project is not affiliated with or endorsed by UC Berkeley, the course staff, or OpenAI.

## Contributing and releases

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing the Skill, template, or validators. Review the [changelog](CHANGELOG.md) for published changes. Maintainers should complete [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before tagging a release.

## License

Licensed under the [Apache License 2.0](LICENSE). Generated course templates receive the same `LICENSE` and `NOTICE` files.
