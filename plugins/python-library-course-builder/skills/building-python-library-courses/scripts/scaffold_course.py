#!/usr/bin/env python3
"""Generate a standalone CourseKit learning project from a validated JSON spec."""

from __future__ import annotations

import argparse
import copy
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from validate_course import TOKEN_PATTERN, SpecValidationError, load_and_validate


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "course-template"
TEXT_SUFFIXES = {
    "",
    ".css",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
TEMPLATE_IGNORE = shutil.ignore_patterns(
    ".DS_Store",
    ".coverage",
    ".coursekit",
    ".coursekit-artifacts.json",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "*.egg-info",
    "*.log",
    "*.py[cod]",
    "*.tmp",
    "*.tsbuildinfo",
    "__pycache__",
    "build",
    "coverage",
    "coverage.xml",
    "course-verification.json",
    "dist",
    "htmlcov",
    "node_modules",
)


class ScaffoldError(RuntimeError):
    """The standalone project could not be created safely."""


def json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def text_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def source_text_write(path: Path, value: str) -> None:
    """Write authored source bytes without normalizing their trailing newlines."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def ensure_empty_target(target: Path) -> None:
    if target.is_symlink():
        raise ScaffoldError(f"output target cannot be a symlink: {target}")
    if target.exists() and not target.is_dir():
        raise ScaffoldError(f"output target must be an empty directory: {target}")
    if target.exists() and any(target.iterdir()):
        raise ScaffoldError(f"output target must be empty: {target}")


def copy_template(destination: Path) -> None:
    if not TEMPLATE_ROOT.is_dir():
        raise ScaffoldError(f"Skill template is missing: {TEMPLATE_ROOT}")
    for root, directory_names, file_names in os.walk(TEMPLATE_ROOT):
        names = [*directory_names, *file_names]
        ignored = TEMPLATE_IGNORE(root, names)
        directory_names[:] = [name for name in directory_names if name not in ignored]
        for name in names:
            if name in ignored:
                continue
            source = Path(root, name)
            if source.is_symlink():
                raise ScaffoldError(f"Skill template cannot contain symlinks: {source}")
    shutil.copytree(
        TEMPLATE_ROOT,
        destination,
        dirs_exist_ok=True,
        ignore=TEMPLATE_IGNORE,
    )


def render_course_route(spec: dict[str, Any]) -> str:
    """Render the learner-visible chapter order from the validated course spec."""

    def table_cell(value: object) -> str:
        text = html.escape(str(value), quote=False)
        return text.replace("\\", "&#92;").replace("|", "&#124;").replace(
            "\r\n", "\n"
        ).replace("\r", "\n").replace("\n", "<br>")

    rows = [("lab00", str(spec["foundation"]["title"]))]
    rows.extend((str(lab["id"]), str(lab["title"])) for lab in spec["labs"])
    lines = ["| 顺序 | 本章主题 |", "| --- | --- |"]
    lines.extend(
        f"| `{table_cell(lab_id)}` | {table_cell(title)} |" for lab_id, title in rows
    )
    return "\n".join(lines)


def replace_template_tokens(root: Path, spec: dict[str, Any]) -> None:
    course = spec["course"]
    target = spec["target"]
    replacements = {
        "__COURSEKIT_SLUG__": course["id"],
        "__COURSEKIT_TITLE__": course["title"],
        "__COURSEKIT_DESCRIPTION__": course["description"],
        "__COURSEKIT_TARGET__": target["name"],
        "__COURSEKIT_TARGET_VERSION__": target["version"],
        "__COURSEKIT_PYTHON_REQUIRES__": course["python_requires"],
        "__COURSEKIT_CAPSTONE__": course["capstone"],
        "__COURSEKIT_FIRST_QUESTION__": spec["labs"][0]["questions"][0]["id"],
        "__COURSEKIT_ROUTE__": render_course_route(spec),
    }
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = value
        for token, replacement in replacements.items():
            updated = updated.replace(token, replacement)
        if updated != value:
            path.write_text(updated, encoding="utf-8")


def _quiz(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"questions": items}


def _test_selector(lab_id: str, test: dict[str, Any], *, hidden: bool) -> str:
    prefix = "tests/hidden" if hidden else f"{lab_id}/tests"
    return f"{prefix}/{test['path']}::{test['selector']}"


def _write_lesson(root: Path, lesson: dict[str, Any]) -> None:
    """Split runnable example code out of the structured lesson metadata."""

    payload = copy.deepcopy(lesson)
    for example in payload["examples"]:
        if example["kind"] != "runnable":
            continue
        code = example.pop("code")
        relative = Path(*str(example["path"]).split("/"))
        source_text_write(root / relative, code)
    json_write(root / "lesson.json", payload)


def write_canonical_source(platform: Path, spec: dict[str, Any]) -> None:
    source = platform / "course" / "source"
    course = spec["course"]
    target = spec["target"]
    foundation = spec["foundation"]
    curriculum_id = f"{course['id']}-v2"
    lab_order = [lab["id"] for lab in spec["labs"]]
    course_payload = {
        "schema_version": 2,
        "id": course["id"],
        "title": course["title"],
        "description": course["description"],
        "audience": course["audience"],
        "curriculum_id": curriculum_id,
        "compatible_curriculum_ids": [curriculum_id],
        "language": course["language"],
        "python_requires": course["python_requires"],
        "size": course["size"],
        "dependencies": course.get("dependencies", []),
        "capstone": course["capstone"],
        "lab_order": lab_order,
        "extensions": [],
        "knowledge_title": f"{course['title']} 知识检查",
        "manifest": {
            "schema_version": 2,
            "layout_version": 3,
            "course_id": course["id"],
            "curriculum_id": curriculum_id,
            "title": course["title"],
            "brand": course["title"],
            "project": target["name"],
            "language": course["language"],
            "audience": course["audience"],
            "python_requires": course["python_requires"],
            "starter_root": "starter",
            "source_root": "starter",
            "reference_root": "reference",
            "capstone": {
                "name": target["name"],
                "description": course["capstone"],
            },
            "target": {
                "name": target["name"],
                "kind": target["kind"],
                "version": target["version"],
                "track": target.get("track") or None,
            },
        },
        "foundations": {
            "id": "lab00",
            "title": foundation["title"],
            "lesson": "foundations/lesson.json",
            "quiz": "foundations/quiz.json",
            "manifest": {
                "id": "lab00",
                "order": 0,
                "title": foundation["title"],
                "description": "心智模型、环境检查和官方来源导览。",
                "graded": False,
                "directory": "lab00",
                "readme": "lab00/README.md",
                "git_scope": "lab00",
                "checkpoint": {
                    "require_submit": False,
                    "git_initialized": False,
                    "git_clean": False,
                    "min_commits": 0,
                },
            },
        },
        "research": spec["research"],
    }
    if "study_minutes" in foundation:
        course_payload["foundations"]["study_minutes"] = copy.deepcopy(
            foundation["study_minutes"]
        )
    json_write(source / "course.json", course_payload)
    json_write(
        source / "sources.json",
        {"target": target, "sources": target["official_sources"]},
    )
    _write_lesson(source / "foundations", foundation["lesson"])
    json_write(source / "foundations" / "quiz.json", _quiz(foundation["quiz"]))

    for order, lab in enumerate(spec["labs"], start=1):
        lab_id = lab["id"]
        lab_root = source / "labs" / lab_id
        rendered_questions = []
        public_files: dict[str, str] = {}
        hidden_files: dict[str, str] = {}
        for question in lab["questions"]:
            public = question["public_test"]
            hidden = question["hidden_test"]
            public_files.setdefault(public["path"], public["code"])
            hidden_files.setdefault(hidden["path"], hidden["code"])
            rendered_question = copy.deepcopy(question)
            rendered_question.pop("public_test")
            rendered_question.pop("hidden_test")
            rendered_question["tests"] = {
                "public": [_test_selector(lab_id, public, hidden=False)],
                "hidden": [_test_selector(lab_id, hidden, hidden=True)],
            }
            rendered_questions.append(rendered_question)
        public_selectors = [
            selector
            for question in rendered_questions
            for selector in question["tests"]["public"]
        ]
        hidden_selectors = [
            selector
            for question in rendered_questions
            for selector in question["tests"]["hidden"]
        ]
        lab_payload = {
            "id": lab_id,
            "title": lab["title"],
            "depends_on": lab["depends_on"],
            "sources": lab["sources"],
            "lesson": "lesson.json",
            "module_cycle": lab["module_cycle"],
            "files": [{"path": item["path"]} for item in lab["files"]],
            "questions": rendered_questions,
            "quiz": lab["quiz"],
            "manifest": {
                "order": order,
                "description": lab["lesson"]["capstone_bridge"]["increment"],
                "file": lab["questions"][0]["file"],
                "directory": lab_id,
                "readme": f"{lab_id}/README.md",
                "git_scope": lab_id,
                "checkpoint": {
                    "require_submit": True,
                    "git_initialized": True,
                    "git_clean": True,
                    "min_commits": 1,
                },
                "git_checkpoint": {
                    "title": f"完成 {lab_id}",
                    "commands": [
                        f"git status --short -- {lab_id}",
                        f"git add -- {lab_id}",
                        f"git commit -m finish-{lab_id} -- {lab_id}",
                    ],
                },
                "tests": {
                    "public": public_selectors,
                    "sample": public_selectors,
                    "hidden": hidden_selectors,
                    "submit": public_selectors + hidden_selectors,
                },
            },
        }
        if "study_minutes" in lab:
            lab_payload["study_minutes"] = copy.deepcopy(lab["study_minutes"])
        if "official_bridge" in lab:
            lab_payload["official_bridge"] = copy.deepcopy(lab["official_bridge"])
        json_write(lab_root / "lab.json", lab_payload)
        _write_lesson(lab_root, lab["lesson"])
        for file_spec in lab["files"]:
            relative = Path(*file_spec["path"].split("/"))
            source_text_write(lab_root / "starter" / relative, file_spec["starter"])
            source_text_write(lab_root / "reference" / relative, file_spec["reference"])
        for name, code in public_files.items():
            source_text_write(lab_root / "tests" / "public" / name, code)
        for name, code in hidden_files.items():
            source_text_write(lab_root / "tests" / "hidden" / name, code)


def configure_platform_dependencies(platform: Path, spec: dict[str, Any]) -> None:
    dependencies = [str(value) for value in spec["course"].get("dependencies", [])]
    if not dependencies:
        return
    path = platform / "pyproject.toml"
    value = path.read_text(encoding="utf-8")
    marker = "dependencies = [\n"
    if marker not in value:
        raise ScaffoldError("platform pyproject dependency marker is missing")
    rendered = "".join(f"  {json.dumps(requirement)},\n" for requirement in dependencies)
    path.write_text(value.replace(marker, marker + rendered, 1), encoding="utf-8")


def run_checked(
    command: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        message = (completed.stdout + completed.stderr).strip()
        raise ScaffoldError(f"command failed ({' '.join(command)}):\n{message}")


def verify_authoring_snapshot(platform: Path, spec: dict[str, Any]) -> None:
    snapshot_path = platform / "course" / "authoring-spec.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ScaffoldError(
            f"compiled authoring snapshot is missing: {snapshot_path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ScaffoldError(
            f"compiled authoring snapshot is invalid JSON: {snapshot_path}"
        ) from error
    if snapshot != spec:
        raise ScaffoldError(
            "compiled authoring snapshot does not match the validated input specification"
        )


def compile_and_initialize(root: Path, spec: dict[str, Any]) -> None:
    platform = root / "platform"
    run_checked(
        [sys.executable, "-m", "coursekit.cli", "compile", "course/source", "course"],
        cwd=platform,
    )
    verify_authoring_snapshot(platform, spec)
    support = platform / "support" / "coursekit"
    learner_support = platform / "course" / "starter" / "_course" / "coursekit"
    shutil.copytree(support, learner_support, dirs_exist_ok=True)
    runner = platform / "runner"
    for name in ("execution.py", "pytest_bootstrap.py"):
        source = runner / name
        if not source.is_file() or source.is_symlink():
            raise ScaffoldError(f"Runner execution support is missing: {source}")
        shutil.copy2(source, learner_support / name)
    labs = root / "labs"
    if labs.exists():
        labs.rmdir()
    run_checked(
        [sys.executable, "-m", "coursekit.cli", "init-workspace", "course", str(labs)],
        cwd=platform,
    )
    course = spec["course"]
    course_dependencies = [str(value) for value in course.get("dependencies", [])]
    first_question_id = str(spec["labs"][0]["questions"][0]["id"])
    dependency_lines = "".join(
        f"  {json.dumps(requirement)},\n" for requirement in course_dependencies
    )
    labs_pyproject = f'''[project]
name = "{course['id']}-labs"
version = "0.1.0"
requires-python = "{course['python_requires']}"
dependencies = [
{dependency_lines}  "pytest>=8.3,<9",
  "pytest-timeout>=2.3,<3",
]

[project.scripts]
course = "coursekit.cli:main"

[project.entry-points.pytest11]
coursekit = "coursekit.pytest_plugin"

[build-system]
requires = ["setuptools==83.0.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
package-dir = {{"" = "_course"}}

[tool.setuptools.packages.find]
where = ["_course"]
include = ["coursekit*"]

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["."]
pythonpath = [".", "_course"]
'''
    text_write(labs / "pyproject.toml", labs_pyproject)
    text_write(
        labs / "README.md",
        f'''# {course['title']} 学员工作区

从 `lab00/README.md` 开始，然后按编号顺序完成各个 Lab。只编辑 `labNN/` 下的文件；`_course/` 包含共享的 CLI 和进度支持。

```bash
uv run course status
uv run course unlock lab00
uv run course unlock lab01
uv run course test {first_question_id}
```

公开测试位于起始代码旁边。完整实现和验证测试保留在 `../platform/course/` 中，不会出现在正常的学员工作流程里。
''',
    )


def verify_no_tokens(root: Path) -> None:
    unresolved = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if TOKEN_PATTERN.search(text):
            unresolved.append(path.relative_to(root).as_posix())
    if unresolved:
        raise ScaffoldError("unresolved template tokens: " + ", ".join(unresolved))


def initialize_git(root: Path) -> None:
    run_checked(["git", "init", "-q"], cwd=root)
    run_checked(["git", "add", "."], cwd=root)
    run_checked(
        [
            "git",
            "-c",
            "user.name=CourseKit",
            "-c",
            "user.email=coursekit@localhost",
            "commit",
            "-q",
            "-m",
            "coursekit: generated baseline",
        ],
        cwd=root,
    )


def materialize_python_locks(root: Path, spec: dict[str, Any]) -> None:
    course = spec["course"]
    base = root / "platform" / "support" / "labs-stdlib.uv.lock"
    if not base.is_file():
        raise ScaffoldError("learner lockfile template is missing")
    value = base.read_text(encoding="utf-8")
    value = value.replace(
        'requires-python = ">=3.12"',
        f"requires-python = {json.dumps(course['python_requires'])}",
        1,
    ).replace(
        'name = "sample-course-labs"',
        f"name = {json.dumps(course['id'] + '-labs')}",
        1,
    )
    text_write(root / "labs" / "uv.lock", value)
    base.unlink()

    if course.get("dependencies"):
        if shutil.which("uv") is None:
            raise ScaffoldError("uv is required to lock third-party course dependencies")
        cache = root / ".coursekit-lock-cache"
        environment = {**os.environ, "UV_CACHE_DIR": str(cache)}
        try:
            run_checked(["uv", "lock", "--directory", "platform"], cwd=root, env=environment)
            run_checked(["uv", "lock", "--directory", "labs"], cwd=root, env=environment)
        finally:
            shutil.rmtree(cache, ignore_errors=True)


def scaffold(spec_path: Path, output: Path) -> dict[str, Any]:
    spec = load_and_validate(spec_path)
    destination = output.absolute()
    ensure_empty_target(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-coursekit-", dir=destination.parent) as raw:
        workspace = Path(raw) / "project"
        copy_template(workspace)
        replace_template_tokens(workspace, spec)
        configure_platform_dependencies(workspace / "platform", spec)
        write_canonical_source(workspace / "platform", spec)
        compile_and_initialize(workspace, spec)
        materialize_python_locks(workspace, spec)
        verify_no_tokens(workspace)
        initialize_git(workspace)
        if destination.exists():
            destination.rmdir()
        os.replace(workspace, destination)
    return {
        "created": str(destination),
        "course_id": spec["course"]["id"],
        "target": spec["target"]["name"],
        "labs": len(spec["labs"]),
        "git_baseline": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = scaffold(args.spec, args.output)
    except (OSError, SpecValidationError, ScaffoldError) as error:
        print(f"scaffold failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
