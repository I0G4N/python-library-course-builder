# 像刷 CS61A 一样，系统攻下一门 Python 库

[English](README.md) | 简体中文

[![CI](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml)

**Python Library Course Builder｜Python 库课程构建器** 是一个只包含 Skill 的 Codex 插件，可以把 Python 标准库模块、PyPI 包、框架或源码仓库变成一门使用简体中文或英语的累积项目课。

> 别再从 API 文档第一页开始硬啃。给 Skill 一个 Python 库，它会还你一条能学完、能验证、还能留下作品的路线。

一句话概括：先选择课程语言，再固定一条连贯路线，用可复核证据评估你已经掌握的内容，只为被判定缺失的路线能力生成先修，然后持续扩展同一个累积项目，直到你能使用、调试并解释目标库。

本项目不包含任何 CS61A 代码、作业、测试或教学文本；它是独立创作，与 UC Berkeley、CS61A 课程团队或 OpenAI 没有隶属、合作或背书关系。

0.3.0 版本仅支持两种课程语言：简体中文（`zh-CN`）和英语（`en`）。每次全新调用 Skill 时，即使请求已写明语言，第一个问题仍始终是课程语言选择。面向学员的讲义、readiness 问题、测验提示、反馈、生成文档和课程正文使用所选语言。代码、shell 命令、标识符、目标 API 名称以及官方来源标题和 URL 保持原文。

内置 Skill 名称为 `$building-python-library-courses`。

## 这不是“读文档”，而是“刷课程”

| 普通库教程 | Python Library Course Builder |
|---|---|
| 默认所有人从同一起点开始 | 先用可复核的代码与诊断证据评估路线能力 |
| 按 API 目录逐章浏览 | 围绕能力 DAG 和累积项目推进 |
| 看完示例就算学会 | 用 Quiz、测试、Runner 和解锁状态共同验证 |
| 基础不足时自己查资料 | 只为被判定缺失的能力生成 `prep01` 到 `prepNN` |
| 每章做一个孤立 Demo | 所有正式 Labs 持续扩展同一个 capstone |

这里的“CS61A-style”指累积练习、顺序解锁、机制理解和确定性反馈，不代表官方合作，也不复用 CS61A 的课程内容。面对大型框架或源码仓库，Skill 会先让学习者选择一条连贯路线，而不是假装一门课能覆盖所有 API。

每门新生成的 schema-v4 课程包含：

- 固定且不计分的 `lab00`，用于环境和学习流程；
- 从评估出的先修缺口生成的零个或多个纯知识 `prep01` 到 `prepNN`；
- 围绕同一个 capstone 扩展的 `lab01` 到 `labNN`；
- 可自由组织的 Markdown 讲义；深度来自一个讲透的机制、具体 walkthrough、接口与设计推理，以及可恢复的边界案例；
- 每个正式 Lab 在解锁编码工作区前的知识检查；
- 仅针对正式 Labs 的公开测试、hidden submit、私有解答和确定性本地评分；
- Web 和 Runner 共用的进度与知识状态；
- 知识关卡前的专注阅读布局，以及关卡后的可调讲义/代码工作区。

## 只学这条路线证明你需要的内容

每次全新调用首先提出一个阻塞选择：简体中文（`zh-CN`）或英语（`en`）。即使原始请求已指定语言，Skill 仍会询问；它不会根据对话语言或地区设置推断，且在学习者回答支持的选项前不会执行其他操作。

在创建任何课程规范或目标目录前，Skill 固定所选路线，从主要官方来源推导其先修能力 DAG，并运行确定性 **evidence-dialogue readiness preflight**。它复用具体代码和匹配的诊断回答，再为每个仍未知的能力一次只问一道预测题、读码题或微型代码题。声称掌握只是声称，不是证明；直接承认不会可以建立缺口。

原始回答和代码证据只保留在临时 readiness 报告中。完成的 readiness plan 记录每个已解决的路线能力；其先修单元仅按 DAG 层级、再按 `python -> library -> domain` 分组被判定缺失的能力。计划在创作前报告总先修时间，并把进度绑定到一个隔离的课程标识。

生成后的学员课程不会公开这份诊断。根 README、讲义、manifest、侧栏、内容载荷和公开 API 都不包含先修画像、能力判定、证据类型、诊断题 ID、route/readiness 摘要或已掌握/缺失列表。prep 会像普通章节一样直接把知识讲清楚，而不是告诉学习者“评估认为你缺少什么”。

`lab00` 始终是环境与学习循环导览。需要先修时，课程按依赖顺序添加 `prep01`、`prep02`、……；当所有必需能力都被评估为已掌握时，不会虚构任何 prep。

## 每个 Writer 一次生成完整章节包

父 Agent 先固定路线、官方事实、章节目标、任务 ID、公开接口、测试 selector、owned paths 和 capstone 增量。它为每章准备一个私有、精简的 Depth Brief，只围绕一个核心问题、一个 walkthrough、一个边界案例、当前设计和一个可信替代方案。

一个 clean-context Writer 只收到本章 brief、相关官方事实、锁定的任务契约和 owned paths。它在一次调用中完成规划、写作、静默检查和修订，并一次输出 `tutorial.md`、术语、quiz、starter、solution、公开测试、hidden tests 和可选 examples。

流程不再包含整课 Reviewer、replacement Writer、深度评分、字数门槛、语义完整性检查或结构化 lesson sidecar。`tutorial.md` 是唯一讲义真源，标题、顺序和篇幅都由主题决定。深度是 prompt 中的写作责任，不再由输出 schema 假装证明。

assembler 只检查运行必需条件：ID、必需文件和可解析性、quiz 答案引用、owned-path 安全、Python 语法、测试 selector、声明符号，以及 learner/author 隔离。机械失败只回给原 Writer 修复一次；再次失败就停止，不启动审核循环。

## 从 Lab 00 到 capstone，一路只造一个东西

路线在机制的小型教学等价实现和目标库官方 API 的计分 bridge 之间交替。后续 Labs 对已学能力使用官方 API，因此课程最终形成一个集成项目，而不是一组孤立练习。

`lab01` 仅在最后一个 prep 后解锁。如果没有评估出先修缺口，它直接依赖 `lab00`。现有 schema-v2/v3 课程保持兼容，新课程使用 schema v4。

每章只沿一条知识主线推进，讲义、quiz、代码和测试复用同一个具体案例与行为边界。integration 和 capstone 通过前章公开接口组合系统，不跨章依赖实现细节。

## Prep 只有知识区，这是有意的

每个 `prepNN` 都是使用所选课程语言的独立讲义，包含具体执行轨迹、诊断示例和知识测验，但没有代码工作区、分数或提交。Runner 拒绝 prep 的文件和执行 API，prep 也永远不计入课程总分。

Web 和 Runner 消费同一顺序和知识状态。初始只有 `lab00` 可导航；每个 prep 在前一单元掌握后解锁，正式 Labs 则在知识门之上增加编码验证。

## 环境要求

- 支持插件和 Skill 的 Codex。
- 用于 Skill 自动化和发布验证的 Python 3.13。
- 用于隔离 Python 环境的 [uv](https://docs.astral.sh/uv/)。
- Node.js 22.13 或更高版本（包含 npm）仅供插件贡献者重建或测试共享 Web runtime。
- 用于课程历史和仓库流程的 Git。

支持的本地环境是 macOS、Linux 和将项目放在 Linux 文件系统中的 WSL2。原生 Windows 不是已验证的执行路径。

创建课程需要 Codex 和网络访问，用于验证官方来源和安装依赖。完成 setup 后，必修示例和评分可以在 CPU/离线环境运行。不需要 GPU、API key、付费服务、云账号或外部数据库。

## 安装

### 从 GitHub 安装

将仓库添加为 Codex marketplace，然后安装插件：

```bash
codex plugin marketplace add I0G4N/python-library-course-builder --ref v0.3.0
codex plugin add python-library-course-builder@python-library-course-builder
```

最新 marketplace 流程请参阅 [Codex 插件创作与安装官方文档](https://learn.chatgpt.com/docs/build-plugins#add-a-marketplace-from-the-cli)。

### 从本地 checkout 安装

在将要容纳 checkout 的目录中克隆仓库，注册其相对 marketplace 路径，然后安装插件：

```bash
git clone --branch v0.3.0 --depth 1 https://github.com/I0G4N/python-library-course-builder.git
codex plugin marketplace add ./python-library-course-builder
codex plugin add python-library-course-builder@python-library-course-builder
```

安装后请启动一个新 Codex thread，以便发现新 Skill。

## 使用 Skill

请 Codex 调用 Skill，并给出 Python 目标和一个空目标目录。例如：

```text
Use $building-python-library-courses to create a beginner course for pathlib in ../pathlib-course.
```

Skill 总是先问课程语言。获得回答后，它才检查本地目标并用主要官方来源验证声明。小型和中型目标得到有界的累积路线；广泛目标则在创建任何课程文件前先让学习者选择一条连贯 track。

路线固定后，Skill 在创作 schema v4 或触碰目标目录前获得完整 readiness plan。父 Agent 锁定机械路线，然后每章由一个 Writer 生成完整章节包。

生成仍仅允许空目标目录。脚手架创建彼此分离的 learner 和同级 author 投影，直接复制预构建 Web runtime，不运行 npm，并只做最小机械检查。最终只做一次聚合验收：全部 starter 预期 RED、solution 对 public+hidden GREEN、三关可推进，以及真实 public-test/hidden-submit API 流程。

生成后，进入生成仓库、安装依赖并启动学习循环：

```bash
cd /path/to/generated-course
uv sync
uv run course
```

## 只重新生成发生变化的部分

向 Skill 明确提供一个现有课程路径，即可进入重生成模式：

```text
使用 $building-python-library-courses 重新生成 /path/to/course 中现有的生成课程。
```

现有课程固定语言、目标库版本、已选 track、任务 ID、接口和路线意图。schema-v2/v3 课程保持原样；显式重生成会创建完整的 v4 learner/author pair。

工作流先在课程目录外生成一份只读检查计划：

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/regenerate_course.py" check /path/to/course --json /tmp/course-regeneration-plan.json
```

schema v4 分别记录内容合同和 runtime 合同 digest。prompt 或 Depth Brief 合同变化才会重新调用章节 Writer；Web、Runner、exporter 或 verifier 变化只重新导出或验证已有内容。

若只有一章过浅，生成一个窄范围请求：

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/regenerate_course.py" chapter /path/to/course --chapter lab03 --reason "把 ownership boundary 讲到可预测" --json /tmp/chapter-regeneration.json
```

只有该章 Writer 会收到锁定路线、任务契约、selector 和 owned paths；其他章节保持不变。

候选 learner/author pair 通过一次聚合验收并拥有有效 receipt 后，再绑定替换计划：

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/regenerate_course.py" check /path/to/course --candidate-course /path/to/course-staging --json /tmp/course-regeneration-plan.json
```

审阅破坏性替换计划并停止课程服务后，接受整目录替换：

```bash
uv run --cache-dir "${TMPDIR:-/tmp}/coursekit-skill-uv-cache" --python 3.13 --no-project python "$SKILL_DIR/scripts/regenerate_course.py" apply /path/to/course --candidate-course /path/to/course-staging --plan /tmp/course-regeneration-plan.json --confirm-stopped --accept-replacement --json /tmp/course-regeneration-result.json
```

Apply 把 learner 与 author 目录作为一个事务替换。旧 pair 只在 apply 期间暂存于一个临时回滚目录；若绑定路径仍完整，清理前可捕获的失败会恢复原始 pair，路径受到外部干扰时则会 fail closed 并报告需要人工恢复。新 pair 落位且交换后校验成功后，CourseKit 会先把 `replacement_committed=true`、`cleanup_status=pending` 持久写入指定结果 JSON，再删除旧 pair；只有临时回滚目录已不存在且结果被原子升级为 `cleanup_status=complete` 后才报告成功。如果清理或最终结果升级失败，已验证的新 pair 会保持落位，较早的结果凭据仍能说明替换已经提交，命令以非零状态在 stderr 报告后续处理。成功替换不保留备份，因此不可撤销。

## 仓库结构

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

插件 bundle 只包含 Skill 及其本地 assets。它不声明 app、MCP server、云 connector 或直接 Codex capability。

## Learner/author 信任边界

v4 会生成 learner 项目和独立的同级 author 项目。learner tree 包含讲义、已去答案的 quiz、starter、公开测试、Web 和 Runner；author tree 包含 quiz 答案、solution、hidden tests 和验收 receipt。

author sibling 必须保持私有。hidden tests 是评测边界，不用于对抗可以直接读取该目录的人。

本地 Runner 是学习工具，不是操作系统安全沙箱。它会降低普通评分副作用并绑定 loopback，但提交的 Python 代码仍以当前用户权限执行。只运行可信本地课程代码，绝不将 Runner 暴露为公开评测服务；评估恶意提交时使用独立加固沙箱。

报告渠道和部署边界见 [SECURITY.md](SECURITY.md)。

## 独立实现声明

本项目独立创作。CS61A 和 CS336 启发了交互式知识检查与测试驱动作业的宏观想法，但本仓库不包含这些课程的代码、作业、测试或教学文本。本项目与 UC Berkeley、课程团队或 OpenAI 没有隶属、合作或背书关系。

## 贡献与发布

更改 Skill、模板或验证器前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。已发布变更见 [changelog](CHANGELOG.md)。维护者在创建发布标签前应完成 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)。

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。生成的课程模板获得相同的 `LICENSE` 和 `NOTICE` 文件。
