#!/usr/bin/env python3
"""Assemble one schema-v4 learner course and its sibling author projection."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from authoring_contract import (
    v4_content_contract_sha256,
    v4_runtime_contract_sha256,
)
from v4_contract import (
    V4ContractError,
    V4Projection,
    load_v4_authoring,
    project_v4_authoring,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
V4_TEMPLATE_ROOT = SKILL_ROOT / "assets" / "course-template-v4"
RUNTIME_ROOT = V4_TEMPLATE_ROOT / "coursekit_runtime"
LEGAL_ASSET_ROOT = SKILL_ROOT / "assets" / "course-template"
PLUGIN_MANIFEST = SKILL_ROOT.parents[1] / ".codex-plugin" / "plugin.json"
TEXT_SUFFIXES = {
    "",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".txt",
}


class V4ScaffoldError(RuntimeError):
    """A schema-v4 learner/author pair could not be assembled safely."""


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _ensure_empty_target(path: Path, *, label: str) -> bool:
    if path.is_symlink():
        raise V4ScaffoldError(f"{label} cannot be a symlink: {path}")
    if path.exists() and not path.is_dir():
        raise V4ScaffoldError(f"{label} must be an empty directory: {path}")
    existed = path.is_dir()
    if existed and any(path.iterdir()):
        raise V4ScaffoldError(f"{label} must be empty: {path}")
    return existed


def _validate_pair_paths(learner: Path, author: Path) -> tuple[bool, bool]:
    if learner == author:
        raise V4ScaffoldError("learner and author destinations must differ")
    if learner in author.parents or author in learner.parents:
        raise V4ScaffoldError("learner and author destinations cannot contain each other")
    learner_existed = _ensure_empty_target(learner, label="learner destination")
    author_existed = _ensure_empty_target(author, label="author destination")
    return learner_existed, author_existed


def _safe_destination(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*relative.split("/"))
    resolved_parent = candidate.parent.resolve()
    resolved_root = root.resolve()
    if resolved_parent != resolved_root and resolved_root not in resolved_parent.parents:
        raise V4ScaffoldError(f"projection path escapes destination: {relative}")
    return candidate


def _write_projection(root: Path, files: Mapping[str, bytes]) -> None:
    for relative, value in sorted(files.items()):
        destination = _safe_destination(root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise V4ScaffoldError(f"projection collision: {relative}")
        destination.write_bytes(value)


def _copy_runtime(destination: Path, *, language: str) -> None:
    if RUNTIME_ROOT.is_symlink() or not RUNTIME_ROOT.is_dir():
        raise V4ScaffoldError(f"schema-v4 runtime template is missing: {RUNTIME_ROOT}")
    for path in sorted(RUNTIME_ROOT.rglob("*")):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise V4ScaffoldError(f"schema-v4 runtime cannot contain symlinks: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise V4ScaffoldError(f"schema-v4 runtime contains a special file: {path}")
        relative = path.relative_to(RUNTIME_ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if target.suffix in TEXT_SUFFIXES:
            try:
                text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                raise V4ScaffoldError(
                    f"schema-v4 runtime text asset is not UTF-8: {relative}"
                ) from error
            if "__COURSEKIT_LANGUAGE__" in text:
                target.write_text(
                    text.replace("__COURSEKIT_LANGUAGE__", language),
                    encoding="utf-8",
                )
    static_index = destination / "static" / "index.html"
    if not static_index.is_file():
        raise V4ScaffoldError("schema-v4 runtime is missing static/index.html")


def _project_dependencies(route: Mapping[str, Any]) -> str:
    dependencies = [
        "fastapi>=0.115,<1",
        "httpx2>=2,<3",
        "pydantic>=2.10,<3",
        "pytest>=8.3,<9",
        "pytest-timeout>=2.3,<3",
        "uvicorn>=0.34,<1",
        *[str(value) for value in route["course"]["dependencies"]],
    ]
    lines = "\n".join(
        f"  {json.dumps(value)}," for value in dict.fromkeys(dependencies)
    )
    course_id = str(route["course"]["id"])
    python_requires = str(route["course"]["python_requires"])
    return f'''[project]
name = {json.dumps(course_id)}
version = "0.1.0"
requires-python = {json.dumps(python_requires)}
dependencies = [
{lines}
]

[project.scripts]
course = "coursekit_runtime.runner:main"

[build-system]
requires = ["setuptools==83.0.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["coursekit_runtime"]

[tool.pytest.ini_options]
addopts = "-ra"
pythonpath = ["src"]
testpaths = ["tests"]
'''


def _readme(route: Mapping[str, Any]) -> str:
    course = route["course"]
    if course["language"] == "en":
        return f"""# {course['title']}

{course['description']}

Start the single-port local course:

```bash
uv sync
uv run course
```

Open <http://127.0.0.1:8765>. The sibling author directory contains answers,
solutions, and hidden tests; keep it private.
"""
    return f"""# {course['title']}

{course['description']}

启动单端口本地课程：

```bash
uv sync
uv run course
```

打开 <http://127.0.0.1:8765>。相邻的 author 目录包含答案、解答和 hidden
tests，请保持私有。
"""


def _add_generated_files(
    projection: V4Projection,
    *,
    route: Mapping[str, Any],
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    learner = dict(projection.learner_files)
    author = dict(projection.author_files)
    learner["pyproject.toml"] = _project_dependencies(route).encode("utf-8")
    learner["README.md"] = _readme(route).encode("utf-8")
    for legal_name in ("LICENSE", "NOTICE"):
        legal_path = LEGAL_ASSET_ROOT / legal_name
        if legal_path.is_symlink() or not legal_path.is_file():
            raise V4ScaffoldError(
                f"schema-v4 legal asset is missing or unsafe: {legal_name}"
            )
        legal_bytes = legal_path.read_bytes()
        learner[legal_name] = legal_bytes
        author[legal_name] = legal_bytes
    learner[".gitignore"] = (
        ".coursekit/state.json\n"
        ".coursekit/state.json.lock\n"
        ".pytest_cache/\n"
        ".ruff_cache/\n"
        ".venv/\n"
        "__pycache__/\n"
        "*.egg-info/\n"
        "*.py[cod]\n"
    ).encode("utf-8")
    try:
        plugin = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
        plugin_version = plugin["version"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise V4ScaffoldError(f"plugin manifest is invalid: {error}") from error
    learner[".coursekit/generation.json"] = _json_bytes(
        {
            "schema_version": 1,
            "course_schema_version": 4,
            "course_id": route["course"]["id"],
            "curriculum_id": route["course"]["curriculum_id"],
            "plugin_version": plugin_version,
            "content_contract_sha256": v4_content_contract_sha256(),
            "runtime_contract_sha256": v4_runtime_contract_sha256(),
            "course_contract_sha256": projection.course_contract_sha256,
        }
    )
    author["verification.json"] = _json_bytes(
        {
            "schema_version": 1,
            "course_schema_version": 4,
            "course_id": route["course"]["id"],
            "course_contract_sha256": projection.course_contract_sha256,
            "passed": False,
            "status": "pending",
        }
    )
    return learner, author


def _expose_pair(
    staged_learner: Path,
    staged_author: Path,
    learner: Path,
    author: Path,
    *,
    learner_existed: bool,
    author_existed: bool,
) -> None:
    if learner_existed:
        learner.rmdir()
    if author_existed:
        author.rmdir()
    learner_exposed = False
    try:
        os.replace(staged_learner, learner)
        learner_exposed = True
        os.replace(staged_author, author)
    except OSError as error:
        if learner_exposed and learner.exists() and not staged_learner.exists():
            try:
                os.replace(learner, staged_learner)
            except OSError as rollback_error:
                raise V4ScaffoldError(
                    "author projection swap failed and learner rollback failed: "
                    f"{rollback_error}"
                ) from error
        if learner_existed and not learner.exists():
            learner.mkdir()
        if author_existed and not author.exists():
            author.mkdir()
        raise V4ScaffoldError(f"cannot expose learner/author pair: {error}") from error


def scaffold_v4_pair(
    route_path: Path | str,
    packages_root: Path | str,
    learner_output: Path | str,
    *,
    author_output: Path | str | None = None,
) -> dict[str, Any]:
    """Validate, stage, and atomically expose a learner/author sibling pair."""

    authoring = load_v4_authoring(route_path, packages_root)
    projection = project_v4_authoring(authoring)
    learner_files, author_files = _add_generated_files(
        projection,
        route=authoring.route,
    )
    learner = Path(learner_output).absolute()
    author = (
        Path(author_output).absolute()
        if author_output is not None
        else learner.with_name(f"{learner.name}-author")
    )
    learner_existed, author_existed = _validate_pair_paths(learner, author)
    if learner.parent != author.parent:
        raise V4ScaffoldError(
            "learner and author destinations must share one parent for atomic staging"
        )
    learner.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{learner.name}-v4-",
        dir=learner.parent,
    ) as raw:
        staging = Path(raw)
        staged_learner = staging / "learner"
        staged_author = staging / "author"
        staged_learner.mkdir()
        staged_author.mkdir()
        _write_projection(staged_learner, learner_files)
        _write_projection(staged_author, author_files)
        _copy_runtime(
            staged_learner / "coursekit_runtime",
            language=str(authoring.route["course"]["language"]),
        )
        _expose_pair(
            staged_learner,
            staged_author,
            learner,
            author,
            learner_existed=learner_existed,
            author_existed=author_existed,
        )
    return {
        "created": str(learner),
        "author": str(author),
        "schema_version": 4,
        "course_id": authoring.route["course"]["id"],
        "chapters": len(authoring.chapters),
        "graded_chapters": sum(
            chapter.chapter["kind"] in {"lab", "integration", "capstone"}
            for chapter in authoring.chapters
        ),
        "course_contract_sha256": projection.course_contract_sha256,
        "verification": "pending",
        "node_install": False,
    }


__all__ = ["V4ScaffoldError", "scaffold_v4_pair"]
