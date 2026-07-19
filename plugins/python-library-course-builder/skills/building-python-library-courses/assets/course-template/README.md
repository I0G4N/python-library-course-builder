# __COURSEKIT_TITLE__

__COURSEKIT_DESCRIPTION__

目标：`__COURSEKIT_TARGET__`（__COURSEKIT_TARGET_VERSION__）。课程依据固定版本的官方来源构建。生成完成后，已固定版本的官方来源注册表会写入 `platform/course/source/sources.json`.

本课程在创建时选择了简体中文（`zh-CN`）。课程、测验提示、反馈、生成文档和界面均使用该语言；代码、shell 命令、标识符、目标 API 名称以及官方来源标题和 URL 保持原文。课程创建后不提供运行时语言切换。

## 环境要求

- Python __COURSEKIT_PYTHON_REQUIRES__
- [uv](https://docs.astral.sh/uv/)
- Node.js 22.13 或更高版本
- Git

支持的本地平台为 macOS 和 Linux。在 Windows 上，请使用 WSL2，并将项目存放在
Linux 文件系统内；原生 Windows 不属于 CourseKit 已验证的执行路径。

无需 API key、云账户、数据库或 GPU。计分测试具有确定性，并在本地运行。

__COURSEKIT_PREPARATION__

## 课程路线

__COURSEKIT_ROUTE__

## 开始学习

```bash
npm run setup
npm run learn
```

打开终端输出的 Web URL。本地 Runner 只监听 `127.0.0.1:8765`。在启动进程的终端中按 `Ctrl+C` 即可停止两个进程。

浏览器适合阅读、运行示例、编辑和获取快速反馈。进行正式 Lab 的实现和调试时请使用本地 IDE；两个界面编辑的都是 `labs/` 下正式 Lab 的同一组文件。准备单元只提供讲义、示例和知识检查，不提供可编辑的编程工作区。

Runner 是本地学习工具，不是用于恶意代码的安全沙箱。它会隔离常规评分副作用并回收 pytest 进程组，但在当前 OS 账户下运行的代码仍拥有该账户的权限。服务必须保持在 loopback 上，绝不能将其作为面向不可信提交的公开评测器。

## 学习进度

CLI、Web 和本地 Runner 使用同一份进度状态，并共享相同的课程顺序与知识状态。重新启动任一界面时，都会从 `labs/.coursekit/state.json` 载入同一份进度。

Schema v3 课程严格按 `lab00 -> prep01 -> prep02 -> ... -> lab01` 推进：

1. 初始只有 `lab00` 可导航。它是 15–30 分钟的环境与学习流程导览。
2. 完成 `lab00` 的知识检查后，才会开放第一个 `prepNN`；完成当前 `prepNN` 的知识检查后，才会按课程路线开放下一个准备单元。
3. 完成最后一个 `prepNN` 后，才会开放 `lab01`。不包含 prep 章节的路线会从 `lab00` 直接进入 `lab01`。
4. 进入正式 Lab 后，三个关卡依次是章节导航关卡、知识关卡和编程验证关卡：运行代码前必须先完成当前 Lab 的知识检查，每个编程问题都通过验证提交后，才会解锁下一个正式 Lab。

每个 `prepNN` 都是独立的知识型先修讲义与测验：没有编程题、代码工作区、分数、提交或 checkpoint。Runner 会拒绝准备单元的文件读取、文件写入和执行 API；课程总分只统计正式 Labs。

Schema v2 课程继续使用兼容流程：它没有 `prepNN`，`lab00` 是单一基础章节，`lab00` 和 `lab01` 初始均可导航，后续 Labs 仍在前一个正式 Lab 完成后开放。无论课程使用 v2 还是 v3，打开课程都不会绕过知识关卡或编程关卡，禁用章节也无法点击。

如需从 Lab 00 重新开始，请先停止 `npm run learn`，归档进度文件后再启动：

```bash
mv labs/.coursekit/state.json labs/.coursekit/state.json.bak
```

此操作只会重置学习进度，不会修改 `labs/labNN/` 下的实现。

编程路线在机制实现和官方 API 之间交替推进。你会在一个 Lab 中基于更底层的原语手写一个刻意缩小的教学等价实现；下一个 Lab 首先使用固定版本的官方 API 替换该机制并比较可观察行为，然后再手写下一层。后续 Lab 和结课项目调用官方库，不会导入先前的小型实现。

`lab00` 和所有 `prepNN` 都没有代码工作区。在整条准备链以及当前正式 Lab 的知识检查完成之前，浏览器不会挂载代码/结果区域，也不会调用问题级文件 API。这是流程关卡，而不是源码保密边界：你仍可通过 IDE 或终端查看 `labs/` 下正式 Lab 的起始文件。

完成知识检查前，Web 使用专注阅读模式：宽屏以舒适行长显示教程正文，并在右侧提供本章目录、术语索引和知识检查；较窄屏幕会按顺序堆叠这些内容。完成正式 Lab 的知识检查后，界面恢复讲义与代码/结果分栏。桌面端的侧边栏、课程区和代码/结果区之间有两个可通过键盘操作的分隔条；拖动后可调整布局，聚焦时可使用 Arrow 键、Home 或 End。侧边栏可以折叠，验证后的偏好设置按课程保存在 localStorage 中。中小屏幕不显示调整大小的分隔条，知识检查在解锁后仍可回看。

Web 在初次 `/api/state` 加载期间默认拒绝交互：在权威进度返回前，章节导航、测验、编辑器以及测试/提交操作都保持禁用。临时请求失败绝不会让已锁定的 Lab 变为可点击状态。

每个 Web 知识检查都来自通用课程数据。界面从 `GET /api/knowledge/{lab_id}` 读取脱敏后的问题和选项载荷，并将所选答案发送到 `POST /api/knowledge/answer`；两个响应都不会包含答案键或未选选项的反馈。回答响应只解释所选误区和对应推理过程。如果该 POST 失败，界面会保留所选答案并原样保留这次回答 POST，使 **重试提交** 能重新发送同一请求。后台刷新不会清除这次提交错误。

进度响应按课程标识和 `updated_at` 排序。Web 会拒绝过期的状态快照，也会忽略切换 Lab 或问题后延迟返回的保存或运行响应，因此旧操作无法重新锁定导航或覆盖新选择的编辑器。

## CLI 学习循环

```bash
cd labs
uv run course status
uv run course unlock lab00
```

如果课程路线列出 `prepNN`，请严格按表格顺序逐一运行 `uv run course unlock prepNN`；每次命令都会完成该准备单元的知识检查，而不会运行代码或产生分数。完成最后一个准备单元后继续：

```bash
uv run course unlock lab01
uv run course test __COURSEKIT_FIRST_QUESTION__
uv run course grade lab01
uv run course submit lab01
git add lab01 && git commit -m "finish lab01"
uv run course checkpoint lab01
uv run course score
```

直接运行 `pytest` 时会使用同一个知识关卡。公开测试位于你的代码旁边。验证测试和参考实现保留在 `platform/course/` 下，绝不会复制到学员工作区。

这种隔离可以避免本地学习时意外看到提示，但发布后不构成保密边界。如果将完整仓库推送到公开 Git 主机，任何人都可以查看 `platform/course/reference/` 和 `platform/course/tests/hidden/`。Version 0.3.0 does not provide an automated learner-only export. The supported secrecy path is to keep the complete teacher/authoring repository private.

## 作者与完整性

`platform/course/source/` 是唯一规范来源。新教程格式的每章以 `tutorial.md` 保存教材式正文，以 `lesson.json` 保存概念、来源和活动映射 sidecar，并同时包含可运行示例、Lab 元数据、代码和测试。`platform/course/authoring-spec.json` 是编译器生成的私有校验视图，不是可并行编辑的来源。使用以下命令重新生成或检查产物：

```bash
npm --prefix platform run course:compile
npm --prefix platform run course:check
npm test
npm run test:reference
```

每个 Lab 都会扩展结课项目：__COURSEKIT_CAPSTONE__
