# 像刷 CS61A 一样，系统攻下一门 Python 库

[English](README.md) | 简体中文

[![CI](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/I0G4N/python-library-course-builder/actions/workflows/ci.yml)

**Python Library Course Builder｜Python 库课程构建器** 是一个只包含 Skill 的 Codex 插件，可以把 Python 标准库模块、PyPI 包、框架或源码仓库变成一门使用简体中文或英语的累积项目课。

> 别再从 API 文档第一页开始硬啃。给 Skill 一个 Python 库，它会还你一条能学完、能验证、还能留下作品的路线。

一句话概括：先选择课程语言，再固定一条连贯路线，用可复核证据评估你已经掌握的内容，只为被判定缺失的路线能力生成先修，然后持续扩展同一个累积项目，直到你能使用、调试并解释目标库。

本项目不包含任何 CS61A 代码、作业、测试或教学文本；它是独立创作，与 UC Berkeley、CS61A 课程团队或 OpenAI 没有隶属、合作或背书关系。

0.2.0 版本仅支持两种课程语言：简体中文（`zh-CN`）和英语（`en`）。每次全新调用 Skill 时，即使请求已写明语言，第一个问题仍始终是课程语言选择。面向学员的讲义、readiness 问题、测验提示、反馈、生成文档和课程正文使用所选语言。代码、shell 命令、标识符、目标 API 名称以及官方来源标题和 URL 保持原文。

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

每门 schema-v3 课程包含：

- 固定且不计分的 `lab00`，用于环境和学习流程；
- 从评估出的先修缺口生成的零个或多个纯知识 `prep01` 到 `prepNN`；
- 围绕同一个 capstone 扩展的 `lab01` 到 `labNN`；
- 定义、机制、设计原因、权衡、例子、诊断和执行轨迹；
- 每个正式 Lab 在解锁编码工作区前的知识检查；
- 仅针对正式 Labs 的公开测试、验证测试、参考实现和确定性本地评分；
- CLI、Web 和 Runner 共用的进度与知识状态；
- 可调整三栏桌面工作区和响应式小屏布局。

## 只学这条路线证明你需要的内容

每次全新调用首先提出一个阻塞选择：简体中文（`zh-CN`）或英语（`en`）。即使原始请求已指定语言，Skill 仍会询问；它不会根据对话语言或地区设置推断，且在学习者回答支持的选项前不会执行其他操作。

在创建任何课程规范或目标目录前，Skill 固定所选路线，从主要官方来源推导其先修能力 DAG，并运行确定性 **evidence-dialogue readiness preflight**。它复用具体代码和匹配的诊断回答，再为每个仍未知的能力一次只问一道预测题、读码题或微型代码题。声称掌握只是声称，不是证明；直接承认不会可以建立缺口。

原始回答和代码证据只保留在临时 readiness 报告中，绝不复制进生成的课程仓库。完成的 readiness plan 记录每个已解决的路线能力；其先修单元仅按 DAG 层级、再按 `python -> library -> domain` 分组被判定缺失的能力。计划在创作前报告总先修时间，并将学习者画像绑定到 readiness-specific curriculum ID。

`lab00` 始终是环境与学习循环导览。需要先修时，课程按依赖顺序添加 `prep01`、`prep02`、……；当所有必需能力都被评估为已掌握时，不会虚构任何 prep。

## 从 Lab 00 到 capstone，一路只造一个东西

路线在机制的小型教学等价实现和目标库官方 API 的计分 bridge 之间交替。后续 Labs 对已学能力使用官方 API，因此课程最终形成一个集成项目，而不是一组孤立练习。

`lab01` 仅在最后一个 prep 后解锁。如果没有评估出先修缺口，它直接依赖 `lab00`。现有 schema v2 课程保持兼容，而 Skill 新创作的课程只使用 schema v3。

每章把学习目标转化为输入、输出、状态变化、错误和恢复的操作契约。具体执行轨迹在实现前先跟踪真实值穿过目标机制。讲义把与任务关联的练习放在所检查的概念旁，每个计分任务都指回本章知识和 capstone 行为。

## Prep 只有知识区，这是有意的

每个 `prepNN` 都是使用所选课程语言的独立讲义，包含具体执行轨迹、诊断示例和知识测验，但没有代码工作区、分数或提交。Runner 拒绝 prep 的文件和执行 API，prep 也永远不计入课程总分。

CLI、Web 和 Runner 消费同一顺序和知识状态。初始只有 `lab00` 可导航；每个 prep 在前一单元掌握后解锁，正式 Labs 则在知识门之上增加编码验证。

## 环境要求

- 支持插件和 Skill 的 Codex。
- 用于 Skill 自动化和发布验证的 Python 3.13。
- 用于隔离 Python 环境的 [uv](https://docs.astral.sh/uv/)。
- 用于生成 Web 工作区的 Node.js 22.13 或更高版本（包含 npm）。
- 用于 checkpoint 和仓库流程的 Git。

支持的本地环境是 macOS、Linux 和将项目放在 Linux 文件系统中的 WSL2。原生 Windows 不是已验证的执行路径。

创建课程需要 Codex 和网络访问，用于验证官方来源和安装依赖。完成 setup 后，必修示例和评分可以在 CPU/离线环境运行。不需要 GPU、API key、付费服务、云账号或外部数据库。

## 安装

### 从 GitHub 安装

将仓库添加为 Codex marketplace，然后安装插件：

```bash
codex plugin marketplace add I0G4N/python-library-course-builder --ref v0.2.0
codex plugin add python-library-course-builder@python-library-course-builder
```

最新 marketplace 流程请参阅 [Codex 插件创作与安装官方文档](https://learn.chatgpt.com/docs/build-plugins#add-a-marketplace-from-the-cli)。

### 从本地 checkout 安装

在将要容纳 checkout 的目录中克隆仓库，注册其相对 marketplace 路径，然后安装插件：

```bash
git clone --branch v0.2.0 --depth 1 https://github.com/I0G4N/python-library-course-builder.git
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

路线固定后，Skill 必须在创作新 schema-v3 规范或触碰目标目录前获得完整 readiness plan。验证和脚手架会在任何目标写入前拒绝缺失、未完成、被篡改、语言不匹配或其他不一致的计划。

生成仍仅允许空目标目录。匹配的 ready plan 存在时，Skill 会验证课程规范、复制独立 CourseKit 模板、编译规范源、证明 starter/reference RED-GREEN 契约，并在交付前检查 CLI、Web、Runner、进度、计分、语言和隐私边界。

生成后，进入生成仓库、安装锁定依赖并启动学习循环：

```bash
cd /path/to/generated-course
npm run setup
npm run learn
```

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
|       |-- references/
|       `-- scripts/
`-- tests/
```

插件 bundle 只包含 Skill 及其本地 assets。它不声明 app、MCP server、云 connector 或直接 Codex capability。

## 作者仓库与信任边界

生成项目是一个 **作者仓库**：它包含构建和审计课程所需的规范课程源、学员投影、参考实现和已验证评分材料。

当完整仓库可用时，隐藏测试不是秘密。它们从正常学员工作区分离以避免意外提示，但拥有文件系统访问权的用户仍可检查教师材料。0.2.0 版本不提供自动化的仅学员导出。唯一支持的保密路径是将完整的教师/作者仓库保持为私有仓库。

本地 Runner 是学习工具，不是操作系统安全沙箱。它会降低普通评分副作用并绑定 loopback，但提交的 Python 代码仍以当前用户权限执行。只运行可信本地课程代码，绝不将 Runner 暴露为公开评测服务；评估恶意提交时使用独立加固沙箱。

报告渠道和部署边界见 [SECURITY.md](SECURITY.md)。

## 独立实现声明

本项目独立创作。CS61A 和 CS336 启发了交互式知识检查与测试驱动作业的宏观想法，但本仓库不包含这些课程的代码、作业、测试或教学文本。本项目与 UC Berkeley、课程团队或 OpenAI 没有隶属、合作或背书关系。

## 贡献与发布

更改 Skill、模板或验证器前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。已发布变更见 [changelog](CHANGELOG.md)。维护者在创建发布标签前应完成 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)。

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。生成的课程模板获得相同的 `LICENSE` 和 `NOTICE` 文件。
