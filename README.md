# 像刷 CS61A 一样，系统攻下一门 Python 库
## Turn Any Python Library into a CS61A-Style Course

[![CI](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml)

**Python Library Course Builder｜Python 库课程构建器** 是一个 Chinese-first、只包含 Skill 的 Codex 插件。给它一个 Python 标准库模块、PyPI 包、框架或源码仓库，它会把目标变成一门真正可以“刷”的中文项目课。

> 别再从 API 文档第一页开始硬啃。给它一个 Python 库，它会还你一条能学完、能验证、还能留下作品的路线。

In one sentence: choose a coherent route, use reviewable evidence to assess what you already know, receive prep only for route capabilities assessed as missing, and build one cumulative project until you can use, debug, and explain the target library.

No CS61A code, assignments, tests, or instructional text are included, and this independently authored project is not affiliated with or endorsed by UC Berkeley, the CS61A course staff, or OpenAI.

Version 0.1.1 uses Simplified Chinese for learner-facing lessons, quiz prompts, feedback, generated documentation, and course prose. Code, shell commands, identifiers, target API names, and official source titles and URLs remain in their original form; this release has no language switch.

The bundled Skill is named `$building-python-library-courses`.

## 不是“读文档”，而是“刷课程”

| 普通库教程 | Python Library Course Builder |
|---|---|
| 默认所有人从同一起点开始 | 先用可复核的代码与诊断证据评估路线能力 |
| 按 API 目录逐章浏览 | 围绕一条能力 DAG 和累积项目推进 |
| 看完示例就算学会 | Quiz、测试、Runner 和解锁状态共同验证 |
| 基础不足时自己查资料 | 只为被判定缺失的路线能力生成 `prep01` 到 `prepNN` |
| 每章完成一个孤立 Demo | 所有正式 Labs 持续扩展同一个作品 |

“CS61A-style”在这里指累积练习、顺序解锁、机制理解和确定性反馈，不代表官方合作，也不复用 CS61A 的课程内容。面对大型框架或源码仓库，Skill 会先让学习者选择一条连贯路线，而不是假装一门课能覆盖所有 API。

Each schema v3 course contains:

- a fixed, ungraded `lab00` for the environment and learning workflow;
- zero or more knowledge-only `prep01` through `prepNN` units derived from assessed prerequisite gaps;
- a connected `lab01` through `labNN` route that grows one capstone;
- detailed definitions, mechanisms, design reasons, tradeoffs, examples, diagnostics, and execution traces;
- quiz-first progression before each formal Lab's coding workspace unlocks;
- public tests, verified tests, reference implementations, and deterministic local grading for formal Labs only;
- one shared progression and knowledge state across the CLI, Web interface, and Runner;
- an adjustable three-column desktop workspace and responsive smaller layouts.

## 评估为已掌握的，不让你重学；判定缺失的，不让你跳过

Before any course specification or destination is created, the Skill fixes the selected route, derives its prerequisite capability DAG from primary official sources, and runs a deterministic **evidence-dialogue readiness preflight**. It reuses concrete code and matching diagnostic responses, then asks exactly one prediction, code-reading, or micro-code question for each still-unknown capability. A claim of mastery is treated as a claim rather than proof; “I don't know” can directly establish a gap.

Raw answers and code evidence stay in a temporary readiness report. They are never copied into the generated course repository. A completed readiness plan records every resolved route capability; its preparatory units group only capabilities assessed as missing, by DAG level and then by `python -> library -> domain`. The plan reports total preparatory time before authoring and binds the learner profile to a readiness-specific curriculum ID.

`lab00` is always the environment and learning-loop orientation. When preparation is required, the course adds `prep01`, `prep02`, ... in prerequisite order; when every required capability is assessed as mastered, it invents no prep at all.

## 从 lab00 到 Capstone，一路只造一个东西

The route alternates between a small teaching-equivalent of a mechanism and a graded bridge to the target library's official API. Later Labs use the official API for capabilities already learned, so the course becomes one integrated project rather than a set of isolated exercises.

`lab01` unlocks only after the final prep. With no assessed prerequisite gaps, it depends directly on `lab00`. Existing schema v2 courses remain compatible, while the Skill authors new courses only as schema v3.

Each chapter turns its learning goals into operational contracts for inputs, outputs, state changes, errors, and recovery. Concrete execution traces follow real values through the target mechanism before the learner has to implement it. Lessons keep task-linked practice beside the concept it checks, and every graded task points back to the chapter knowledge and capstone behavior it exercises.

## 没有代码区的 Prep，反而更难混过去

Each `prepNN` is a standalone Chinese lecture with a concrete execution trace, diagnostic example, and knowledge quiz, but it has no code workspace, points, or submission. Prep file and execution APIs are denied by the Runner, and prep never contributes to the course score.

CLI, Web, and Runner consume the same order and knowledge state. Only `lab00` is initially navigable; each prep unlocks after the previous unit is mastered, and formal Labs add coding verification on top of the knowledge gate.

## prerequisites

- Codex with plugin and Skill support.
- Python 3.13 for Skill automation and release verification.
- [uv](https://docs.astral.sh/uv/) for isolated Python environments.
- Node.js 22.13 or newer, including npm, for the generated Web workspace.
- Git for checkpoints and repository workflows.

The supported local environments are macOS, Linux, and WSL2 with the project stored in the Linux filesystem. Native Windows is not a verified execution path.

Course creation requires Codex plus network access to verify official sources and install dependencies. After setup, mandatory examples and grading are CPU/offline. No GPU, API key, paid service, cloud account, or external database is required.

## 两条命令开始你的第一门库课程｜Install

### Install from GitHub

Add the repository as a Codex marketplace, then install the plugin:

```bash
codex plugin marketplace add I0G4N/python-library-course-builder --ref v0.1.1
codex plugin add python-library-course-builder@python-library-course-builder
```

See the [official Codex plugin authoring and installation documentation](https://learn.chatgpt.com/docs/build-plugins#add-a-marketplace-from-the-cli) for the current marketplace workflow.

### Install from a local checkout

From the directory that will contain the checkout, clone the repository, register its relative marketplace path, and install the plugin:

```bash
git clone --branch v0.1.1 --depth 1 https://github.com/I0G4N/python-library-course-builder.git
codex plugin marketplace add ./python-library-course-builder
codex plugin add python-library-course-builder@python-library-course-builder
```

Start a new Codex thread after installation so the new Skill is discovered.

## 给它一个目标，它还你一门课｜Use the Skill

Ask Codex to invoke the Skill and name the Python target plus an empty destination. For example:

```text
Use $building-python-library-courses to create a beginner course for pathlib in ../pathlib-course.
```

The Skill first inspects the local target and verifies claims against primary official sources. Small and medium targets receive a bounded cumulative route. A broad target receives a choice of coherent tracks before any course files are created.

Once the route is fixed, the Skill must obtain a complete readiness plan before authoring a new schema v3 specification or touching the destination. Validation and scaffolding reject a missing, incomplete, tampered, or mismatched plan before any destination write.

Generation remains empty-destination-only. With a matching ready plan, the Skill validates the course specification, copies the standalone CourseKit template, compiles the canonical source, proves the starter/reference RED-GREEN contract, and checks CLI, Web, Runner, progression, scoring, and privacy boundaries before handoff.

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

Hidden tests are not secret when the complete repository is available. They are hidden from the normal learner workspace to avoid accidental hints, but a user with filesystem access can inspect teacher artifacts. Version 0.1.1 does not provide an automated learner-only export. The supported secrecy path is to keep the complete teacher/authoring repository private.

The local Runner is a study tool, not an operating-system security sandbox. It reduces ordinary grading side effects and binds to loopback, but submitted Python executes with the current user's privileges. Run only trusted local course code, never expose the Runner as a public judge, and use a separate hardened sandbox for hostile submissions.

See [SECURITY.md](SECURITY.md) for reporting and deployment boundaries.

## Independent implementation

This project is independently authored. CS61A and CS336 influenced the broad idea of interactive knowledge checks and test-driven assignments, but no course code, assignments, tests, or instructional text from those courses is bundled here. This project is not affiliated with or endorsed by UC Berkeley, the course staff, or OpenAI.

## Contributing and releases

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing the Skill, template, or validators. Review the [changelog](CHANGELOG.md) for published changes. Maintainers should complete [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before tagging a release.

## License

Licensed under the [Apache License 2.0](LICENSE). Generated course templates receive the same `LICENSE` and `NOTICE` files.
