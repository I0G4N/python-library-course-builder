"""Course-language catalogs for learner-facing CLI and Runner messages."""

from __future__ import annotations

import re
from typing import Any, Mapping


SUPPORTED_LANGUAGES = ("zh-CN", "en")


class CourseLanguageError(ValueError):
    """Raised when a v3 manifest does not declare a supported language."""


_ZH_CN = {
    "knowledge_check": "知识检查",
    "unknown_lab": "未知 Lab：{lab_id}",
    "unknown_lab_or_question": "未知 Lab 或题目：{item_id}",
    "unknown_knowledge_question": "未知知识题：{question_id}",
    "unknown_coding_question": "未知编码题：{question_id}",
    "invalid_choice": "无效选项：{choice_id}",
    "knowledge_unavailable": "{lab_id} 的知识检查尚未开放",
    "prep_knowledge_only": "{lab_id} 是仅包含知识学习的先修单元",
    "prep_use_unlock": "{lab_id} 是仅包含知识学习的先修单元；请使用 `course unlock {lab_id}`",
    "complete_first": "请先完成 {unit_id}",
    "unlock_first": "请先解锁 {unit_id}",
    "run_unlock_first": "请先运行 `course unlock {unit_id}`",
    "before_unlocking": "解锁 {lab_id} 前请先满足：{reasons}",
    "navigate_after_dependency": "完成依赖后才能进入 {lab_id}",
    "master_knowledge_first": "请先掌握 {lab_id} 的知识检查",
    "lab_locked": "{lab_id} 已锁定：{reasons}",
    "reason_separator": "；",
    "answer_prompt": "答案> ",
    "answers_retry": "{lab_id}：{count} 个答案需要再次尝试",
    "knowledge_unlocked": "{lab_id} 的知识检查已通过",
    "test_requires_question": "test 命令需要编码题 ID，例如 lab01.q1",
    "unknown_graded_lab": "未知的评分 Lab：{lab_id}",
    "cannot_run_public_tests": "[coursekit] 无法运行公开测试：{detail}",
    "public_exercises_passed": "{lab_id}：{passed}/{total} 个公开练习通过",
    "submit_heading": "提交 {question_id}",
    "verified": "已验证",
    "not_verified": "未验证",
    "runner_exercises_verified": "{lab_id}：Runner 已验证 {passed}/{total} 个练习",
    "runner_http": "Runner 返回 HTTP {status}",
    "runner_unreachable": "无法连接本地 Runner（{base_url}）：{detail}。请运行 `npm run learn` 后重试。",
    "runner_invalid_response": "Runner 返回的响应无效：{detail}",
    "runner_invalid_contract": "Runner 返回的响应契约无效",
    "invalid_checkpoint": "{lab_id} 的 checkpoint 配置无效",
    "submit_before_checkpoint": "checkpoint 前请先成功提交 {lab_id}",
    "git_unavailable": "Git 不可用或当前项目不是 Git 仓库；请初始化 Git 并创建基线提交后重试。",
    "git_baseline_missing": "学习进度中没有可用的 Git 基线；请恢复生成时的基线，或使用新的进度状态开始。",
    "git_baseline_not_ancestor": "保存的 Git 基线不是 HEAD 的祖先；请恢复生成时的历史后再创建 checkpoint。",
    "git_baseline_unavailable": "当前仓库中不存在保存的 Git 基线；请恢复其历史后再创建 checkpoint。",
    "commit_minimum": "请在学习基线后至少提交 {minimum} 个 {scope} 变更",
    "git_status_failed": "Git 状态检查失败；请修复 Git 后重试",
    "commit_scope": "创建 checkpoint 前请提交 {scope} 的变更",
    "checkpoint_accepted": "{lab_id} 的 checkpoint 已接受：{head}",
    "no_git_checkpoint": "无 Git checkpoint",
    "file_not_found": "文件不存在",
    "runner_busy": "Runner 正在处理另一个评分请求，请稍后重试",
    "file_locked": "{lab_id} 已锁定：{reasons}",
    "path_inside_workspace": "路径必须位于学习者工作区内",
    "question_file_path": "编码题文件必须指向工作区中的文件",
    "workspace_missing": "工作区目标不存在",
    "workspace_regular_file": "工作区目标必须是普通文件，且不能使用符号链接",
    "workspace_regular": "工作区目标必须是普通文件",
    "workspace_no_traverse": "工作区路径不能经过符号链接或非目录",
    "path_escapes_workspace": "路径越出了学习者工作区",
    "file_too_large": "文件过大",
    "content_too_large": "内容超过 {limit} 个 UTF-8 字节",
    "question_file_nonempty": "编码题文件必须是非空路径",
    "invalid_public_selector": "公开 pytest 选择器无效：{selector}",
    "public_target_symlink": "公开 pytest 目标不能使用符号链接：{selector}",
    "public_target_outside": "公开 pytest 目标位于学习者工作区之外：{selector}",
    "public_target_regular": "公开 pytest 目标必须是普通文件：{selector}",
    "no_public_selectors": "未声明公开 pytest 选择器",
    "timeout_range": "题目的 timeout_seconds 必须是 1 到 90 的整数",
    "invalid_knowledge_questions": "{lab_id} 的知识题无效",
    "knowledge_choices_list": "知识题选项必须是列表",
    "knowledge_choice_object": "知识题选项对象必须包含文本 ID 和标签",
    "knowledge_choice_type": "知识题选项必须是字符串或对象",
    "knowledge_choice_unique": "知识题选项 ID 必须唯一",
    "knowledge_answer_index": "知识题答案必须索引字符串选项",
    "knowledge_answer_object": "知识题答案必须标识一个对象选项",
    "knowledge_feedback_text": "知识题选项反馈必须是文本",
    "canonical_root": "标准测试根目录必须是普通目录",
    "canonical_selector_text": "标准 pytest 选择器必须是文本",
    "unsafe_canonical_selector": "不安全的标准 pytest 选择器：{selector}",
    "canonical_target_symlink": "标准 pytest 目标不能使用符号链接：{selector}",
    "canonical_target_escape": "标准 pytest 目标越出了根目录：{selector}",
    "canonical_target_regular": "标准 pytest 目标必须是普通文件：{selector}",
    "canonical_selector_required": "至少需要一个标准 pytest 选择器",
    "public_timeout": "[coursekit] 公开测试开始前 pytest 已超时",
    "hidden_timeout": "公开测试通过。隐藏验证失败（检查 {count} 个私有目标前已耗尽超时预算）。",
    "hidden_unavailable": "公开测试通过。隐藏验证失败（私有评分器不可用）。",
    "hidden_result": "公开测试通过。隐藏验证{result}（已检查 {count} 个私有目标）。",
    "hidden_passed": "通过",
    "hidden_failed": "失败",
    "source_policy_violation": "[coursekit] 源码策略违规：{detail}",
    "source_names_list": "{field} 必须是由非空模块名组成的列表",
    "source_invalid_python": "{filename} 不是有效的 Python：{detail}",
    "source_relative_import": "{filename} 使用了相对导入",
    "source_unsafe_path": "学习者源码路径不安全：{path}",
    "source_symlink": "学习者源码不能使用符号链接：{path}",
    "source_unavailable": "学习者源码不可用：{path}",
    "source_regular_file": "学习者源码必须是普通文件：{path}",
    "source_policy_missing": "题目的 source_policy 缺失或无效",
    "source_unknown_fields": "source_policy 包含未知字段：{fields}",
    "source_local_root": "source_policy.local_root 必须是一个顶层模块",
    "source_missing_imports": "题目文件缺少必需导入：{imports}",
    "source_forbidden_import": "{filename} 导入了禁止模块 {module}（边界 {boundary}）",
    "source_missing_helper": "{filename} 导入了未声明或缺失的本地 helper {module}",
    "local_runner": "本地 Runner",
    "artifacts_written": "{command}：生成 {count} 个文件",
}


_EN = {
    "knowledge_check": "Knowledge check",
    "unknown_lab": "unknown Lab: {lab_id}",
    "unknown_lab_or_question": "unknown Lab or question: {item_id}",
    "unknown_knowledge_question": "unknown knowledge question: {question_id}",
    "unknown_coding_question": "unknown coding question: {question_id}",
    "invalid_choice": "invalid choice: {choice_id}",
    "knowledge_unavailable": "{lab_id} knowledge is not available yet",
    "prep_knowledge_only": "{lab_id} is a knowledge-only preparatory unit",
    "prep_use_unlock": "{lab_id} is a knowledge-only preparatory unit; use `course unlock {lab_id}`",
    "complete_first": "complete {unit_id} first",
    "unlock_first": "unlock {unit_id} first",
    "run_unlock_first": "run `course unlock {unit_id}` first",
    "before_unlocking": "{reasons} before unlocking {lab_id}",
    "navigate_after_dependency": "navigate to {lab_id} only after completing its dependency",
    "master_knowledge_first": "master {lab_id} knowledge first",
    "lab_locked": "{lab_id} is locked: {reasons}",
    "reason_separator": "; ",
    "answer_prompt": "answer> ",
    "answers_retry": "{lab_id}: {count} answer(s) need another attempt",
    "knowledge_unlocked": "{lab_id} knowledge unlocked",
    "test_requires_question": "test expects a coding question id such as lab01.q1",
    "unknown_graded_lab": "unknown graded Lab: {lab_id}",
    "cannot_run_public_tests": "[coursekit] cannot run public tests: {detail}",
    "public_exercises_passed": "{lab_id}: {passed}/{total} public exercises passed",
    "submit_heading": "submit {question_id}",
    "verified": "verified",
    "not_verified": "not verified",
    "runner_exercises_verified": "{lab_id}: {passed}/{total} exercises verified by the Runner",
    "runner_http": "Runner returned HTTP {status}",
    "runner_unreachable": "cannot reach the local Runner at {base_url}: {detail}. Start it with `npm run learn` and retry.",
    "runner_invalid_response": "Runner returned an invalid response: {detail}",
    "runner_invalid_contract": "Runner returned an invalid response contract",
    "invalid_checkpoint": "{lab_id} has an invalid checkpoint configuration",
    "submit_before_checkpoint": "submit {lab_id} successfully before checkpoint",
    "git_unavailable": "Git is unavailable or this project is not a Git repository; initialize Git and create a baseline commit, then retry.",
    "git_baseline_missing": "the learning state has no usable Git baseline; restore the generated baseline or start with a fresh progress state",
    "git_baseline_not_ancestor": "the saved Git baseline is not an ancestor of HEAD; restore the generated history before checkpointing",
    "git_baseline_unavailable": "the saved Git baseline is not available in this repository; restore its history before checkpointing",
    "commit_minimum": "commit at least {minimum} {scope} change(s) after the learning baseline",
    "git_status_failed": "Git status failed; repair Git and retry",
    "commit_scope": "commit the {scope} changes before checkpoint",
    "checkpoint_accepted": "{lab_id} checkpoint accepted at {head}",
    "no_git_checkpoint": "no-git checkpoint",
    "file_not_found": "file not found",
    "runner_busy": "Runner is busy with another grading request; try again shortly",
    "file_locked": "{lab_id} is locked: {reasons}",
    "path_inside_workspace": "path must stay inside the learner workspace",
    "question_file_path": "coding question file must name a workspace file",
    "workspace_missing": "workspace target does not exist",
    "workspace_regular_file": "workspace target must be a regular file without symlinks",
    "workspace_regular": "workspace target must be a regular file",
    "workspace_no_traverse": "workspace path cannot traverse a symlink or non-directory",
    "path_escapes_workspace": "path escapes the learner workspace",
    "file_too_large": "file is too large",
    "content_too_large": "content exceeds {limit} UTF-8 bytes",
    "question_file_nonempty": "coding question file must be a non-empty path",
    "invalid_public_selector": "invalid public pytest selector: {selector}",
    "public_target_symlink": "public pytest target cannot use symlinks: {selector}",
    "public_target_outside": "public pytest target is outside the learner workspace: {selector}",
    "public_target_regular": "public pytest target must be a regular file: {selector}",
    "no_public_selectors": "no public pytest selectors were declared",
    "timeout_range": "question timeout_seconds must be an integer from 1 to 90",
    "invalid_knowledge_questions": "invalid knowledge questions for {lab_id}",
    "knowledge_choices_list": "knowledge choices must be a list",
    "knowledge_choice_object": "knowledge choice objects require text ids and labels",
    "knowledge_choice_type": "knowledge choices must be strings or objects",
    "knowledge_choice_unique": "knowledge choice ids must be unique",
    "knowledge_answer_index": "knowledge answer must index string choices",
    "knowledge_answer_object": "knowledge answer must identify an object choice",
    "knowledge_feedback_text": "knowledge choice feedback must be text",
    "canonical_root": "canonical test root must be a regular directory",
    "canonical_selector_text": "canonical pytest selector must be text",
    "unsafe_canonical_selector": "unsafe canonical pytest selector: {selector}",
    "canonical_target_symlink": "canonical pytest target cannot use symlinks: {selector}",
    "canonical_target_escape": "canonical pytest target escapes its root: {selector}",
    "canonical_target_regular": "canonical pytest target must be a regular file: {selector}",
    "canonical_selector_required": "at least one canonical pytest selector is required",
    "public_timeout": "[coursekit] pytest timed out before public tests started",
    "hidden_timeout": "Public tests passed. Hidden verification failed (timeout budget exhausted before {count} private target(s) could be checked).",
    "hidden_unavailable": "Public tests passed. Hidden verification failed (private grader unavailable).",
    "hidden_result": "Public tests passed. Hidden verification {result} ({count} private target(s) checked).",
    "hidden_passed": "passed",
    "hidden_failed": "failed",
    "source_policy_violation": "[coursekit] source policy violation: {detail}",
    "source_names_list": "{field} must be a list of non-empty module names",
    "source_invalid_python": "{filename} is not valid Python: {detail}",
    "source_relative_import": "{filename} uses a relative import",
    "source_unsafe_path": "unsafe learner source path: {path}",
    "source_symlink": "learner source cannot use symlinks: {path}",
    "source_unavailable": "learner source is unavailable: {path}",
    "source_regular_file": "learner source is not a regular file: {path}",
    "source_policy_missing": "question source_policy is missing or invalid",
    "source_unknown_fields": "source_policy has unknown field(s): {fields}",
    "source_local_root": "source_policy.local_root must be one top-level module",
    "source_missing_imports": "question file is missing required import(s): {imports}",
    "source_forbidden_import": "{filename} imports forbidden module {module} ({boundary})",
    "source_missing_helper": "{filename} imports undeclared or missing local helper {module}",
    "local_runner": "Local Runner",
    "artifacts_written": "{command}: {count} artifact(s)",
}


CATALOGS: dict[str, dict[str, str]] = {"zh-CN": _ZH_CN, "en": _EN}


def resolve_language(manifest: Mapping[str, Any]) -> str:
    """Resolve language with v2 compatibility and v3 fail-closed semantics."""

    schema_version = manifest.get("schema_version", 2)
    language = manifest.get("language")
    if type(schema_version) is not int or schema_version not in {2, 3}:
        raise CourseLanguageError("manifest.schema_version must be 2 or 3")
    if schema_version == 2:
        return str(language) if language in SUPPORTED_LANGUAGES else "zh-CN"
    if schema_version == 3:
        if language is None or language == "":
            raise CourseLanguageError("schema v3 manifest.language is required")
        if language in SUPPORTED_LANGUAGES:
            return str(language)
        raise CourseLanguageError(
            f"schema v3 manifest.language is unsupported: {language}"
        )
    raise AssertionError("unreachable course schema version")


def copy_for_manifest(manifest: Mapping[str, Any]) -> dict[str, str]:
    return CATALOGS[resolve_language(manifest)]


def render(copy: Mapping[str, str], key: str, **values: Any) -> str:
    return copy[key].format(**values)


_DETAIL_PATTERNS: tuple[tuple[re.Pattern[str], str, tuple[str, ...]], ...] = (
    (re.compile(r"^unknown Lab: (.+)$"), "unknown_lab", ("lab_id",)),
    (re.compile(r"^unknown Lab or question: (.+)$"), "unknown_lab_or_question", ("item_id",)),
    (re.compile(r"^unknown knowledge question: (.+)$"), "unknown_knowledge_question", ("question_id",)),
    (re.compile(r"^unknown coding question: (.+)$"), "unknown_coding_question", ("question_id",)),
    (re.compile(r"^invalid choice: (.+)$"), "invalid_choice", ("choice_id",)),
    (re.compile(r"^(.+) knowledge is not available yet$"), "knowledge_unavailable", ("lab_id",)),
    (re.compile(r"^(.+) is a knowledge-only preparatory unit$"), "prep_knowledge_only", ("lab_id",)),
    (re.compile(r"^complete (.+) first$"), "complete_first", ("unit_id",)),
    (re.compile(r"^unlock (.+) first$"), "unlock_first", ("unit_id",)),
    (re.compile(r"^run `course unlock (.+)` first$"), "run_unlock_first", ("unit_id",)),
    (re.compile(r"^navigate to (.+) only after completing its dependency$"), "navigate_after_dependency", ("lab_id",)),
    (re.compile(r"^master (.+) knowledge first$"), "master_knowledge_first", ("lab_id",)),
    (re.compile(r"^invalid knowledge questions for (.+)$"), "invalid_knowledge_questions", ("lab_id",)),
    (re.compile(r"^content exceeds (\d+) UTF-8 bytes$"), "content_too_large", ("limit",)),
    (re.compile(r"^unsafe canonical pytest selector: (.+)$"), "unsafe_canonical_selector", ("selector",)),
    (re.compile(r"^canonical pytest target cannot use symlinks: (.+)$"), "canonical_target_symlink", ("selector",)),
    (re.compile(r"^canonical pytest target escapes its root: (.+)$"), "canonical_target_escape", ("selector",)),
    (re.compile(r"^canonical pytest target must be a regular file: (.+)$"), "canonical_target_regular", ("selector",)),
)


_DETAIL_EXACT = {
    "knowledge choices must be a list": "knowledge_choices_list",
    "knowledge choice objects require text ids and labels": "knowledge_choice_object",
    "knowledge choices must be strings or objects": "knowledge_choice_type",
    "knowledge choice ids must be unique": "knowledge_choice_unique",
    "knowledge answer must index string choices": "knowledge_answer_index",
    "knowledge answer must identify an object choice": "knowledge_answer_object",
    "knowledge choice feedback must be text": "knowledge_feedback_text",
    "path must stay inside the learner workspace": "path_inside_workspace",
    "coding question file must name a workspace file": "question_file_path",
    "workspace target does not exist": "workspace_missing",
    "workspace target must be a regular file without symlinks": "workspace_regular_file",
    "workspace target must be a regular file": "workspace_regular",
    "workspace path cannot traverse a symlink or non-directory": "workspace_no_traverse",
    "path escapes the learner workspace": "path_escapes_workspace",
    "file is too large": "file_too_large",
    "coding question file must be a non-empty path": "question_file_nonempty",
    "canonical test root must be a regular directory": "canonical_root",
    "canonical pytest selector must be text": "canonical_selector_text",
    "at least one canonical pytest selector is required": "canonical_selector_required",
    "question timeout_seconds must be an integer from 1 to 90": "timeout_range",
    "file not found": "file_not_found",
    "Runner is busy with another grading request; try again shortly": "runner_busy",
}


def localize_detail(detail: Any, copy: Mapping[str, str]) -> Any:
    """Translate known learner-facing error details without changing their shape."""

    if not isinstance(detail, str):
        return detail
    policy_prefix = "[coursekit] source policy violation: "
    if detail.startswith(policy_prefix):
        source_detail = detail[len(policy_prefix) :]
        source_patterns = (
            (re.compile(r"^(.+) must be a list of non-empty module names$"), "source_names_list", ("field",)),
            (re.compile(r"^(.+) is not valid Python: (.+)$", re.DOTALL), "source_invalid_python", ("filename", "detail")),
            (re.compile(r"^(.+) uses a relative import$"), "source_relative_import", ("filename",)),
            (re.compile(r"^unsafe learner source path: (.+)$"), "source_unsafe_path", ("path",)),
            (re.compile(r"^learner source cannot use symlinks: (.+)$"), "source_symlink", ("path",)),
            (re.compile(r"^learner source is unavailable: (.+)$"), "source_unavailable", ("path",)),
            (re.compile(r"^learner source is not a regular file: (.+)$"), "source_regular_file", ("path",)),
            (re.compile(r"^source_policy has unknown field\(s\): (.+)$"), "source_unknown_fields", ("fields",)),
            (re.compile(r"^question file is missing required import\(s\): (.+)$"), "source_missing_imports", ("imports",)),
            (re.compile(r"^(.+) imports forbidden module (.+) \((.+)\)$"), "source_forbidden_import", ("filename", "module", "boundary")),
            (re.compile(r"^(.+) imports undeclared or missing local helper (.+)$"), "source_missing_helper", ("filename", "module")),
        )
        source_exact = {
            "question source_policy is missing or invalid": "source_policy_missing",
            "source_policy.local_root must be one top-level module": "source_local_root",
        }
        key = source_exact.get(source_detail)
        if key:
            return render(copy, "source_policy_violation", detail=copy[key])
        for pattern, source_key, names in source_patterns:
            match = pattern.fullmatch(source_detail)
            if match:
                localized_source = render(
                    copy,
                    source_key,
                    **dict(zip(names, match.groups(), strict=True)),
                )
                return render(copy, "source_policy_violation", detail=localized_source)
    locked = re.fullmatch(r"^(.+) is locked: (.+)$", detail, flags=re.DOTALL)
    if locked:
        lab_id, reasons = locked.groups()
        input_separator = "\n- " if "\n- " in reasons else "; "
        output_separator = (
            input_separator if input_separator == "\n- " else copy["reason_separator"]
        )
        localized = output_separator.join(
            str(localize_detail(reason, copy))
            for reason in reasons.split(input_separator)
        )
        return render(copy, "lab_locked", lab_id=lab_id, reasons=localized)
    exact = _DETAIL_EXACT.get(detail)
    if exact:
        return copy[exact]
    for pattern, key, names in _DETAIL_PATTERNS:
        match = pattern.fullmatch(detail)
        if match:
            return render(copy, key, **dict(zip(names, match.groups(), strict=True)))
    return detail
