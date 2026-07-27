#!/usr/bin/env python3
"""Mechanical schema-v4 course-package validation and projection helpers.

Schema v4 deliberately treats tutorial depth as an authoring-prompt concern.
This module validates only data needed to assemble and run a course: identities,
paths, Python declarations, test selectors, quiz references, and public/private
projection boundaries.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping
from urllib.parse import urlparse


COURSE_SCHEMA_VERSION = 4
PACKAGE_SCHEMA_VERSION = 1
PUBLIC_BINDING_SCHEMA_VERSION = 1
AUTHOR_BINDING_SCHEMA_VERSION = 1

COURSE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
STABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
PREPARATORY_ID_PATTERN = re.compile(r"^prep(?:0[1-9]|[1-9][0-9]+)$")
LAB_ID_PATTERN = re.compile(r"^lab(?:0[0-9]|[1-9][0-9]+)$")
CHAPTER_KINDS = {
    "orientation",
    "preparatory",
    "lab",
    "integration",
    "capstone",
}
GRADED_CHAPTER_KINDS = {"lab", "integration", "capstone"}
COURSE_LANGUAGES = {"zh-CN", "en"}
TARGET_KINDS = {"stdlib", "pypi", "framework", "repository"}
FORBIDDEN_TREE_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

ROUTE_FIELDS = {"schema_version", "course", "target", "research", "chapters"}
COURSE_FIELDS = {
    "id",
    "curriculum_id",
    "title",
    "description",
    "language",
    "python_requires",
    "dependencies",
    "capstone",
}
TARGET_REQUIRED_FIELDS = {
    "name",
    "kind",
    "version",
    "official_sources",
}
TARGET_OPTIONAL_FIELDS = {"track", "import_roots"}
SOURCE_FIELDS = {"id", "title", "url"}
RESEARCH_FIELDS = {"status", "version_basis", "notes"}
CHAPTER_FIELDS = {
    "id",
    "title",
    "kind",
    "depends_on",
    "study_minutes",
    "sources",
    "owned_paths",
    "task_contracts",
}
STUDY_REQUIRED_FIELDS = {"min", "max"}
STUDY_OPTIONAL_FIELDS = {"reason"}
TASK_REQUIRED_FIELDS = {
    "id",
    "title",
    "file",
    "symbol",
    "prompt",
    "points",
    "timeout_seconds",
    "public_tests",
    "hidden_tests",
}
TASK_OPTIONAL_FIELDS = {"example"}
TASK_EXAMPLE_FIELDS = {"input", "output", "explanation"}
TERMS_FIELDS = {"terms"}
TERM_FIELDS = {"term", "definition"}
QUIZ_FIELDS = {"questions"}
QUIZ_QUESTION_REQUIRED_FIELDS = {
    "id",
    "prompt",
    "choices",
    "answer_id",
}
QUIZ_QUESTION_OPTIONAL_FIELDS = {
    "explanation",
}
QUIZ_CHOICE_REQUIRED_FIELDS = {"id", "text"}
QUIZ_CHOICE_OPTIONAL_FIELDS = {"feedback"}


class V4ContractError(ValueError):
    """A schema-v4 route or chapter package violates a mechanical contract."""


@dataclass(frozen=True)
class V4ChapterPackage:
    """One validated chapter package plus its normalized authored data."""

    chapter: dict[str, Any]
    root: Path
    tutorial: str
    terms: dict[str, Any]
    quiz: dict[str, Any]
    starter_files: dict[str, bytes]
    solution_files: dict[str, bytes]
    public_test_files: dict[str, bytes]
    hidden_test_files: dict[str, bytes]
    example_files: dict[str, bytes]

    @property
    def chapter_id(self) -> str:
        return str(self.chapter["id"])


@dataclass(frozen=True)
class V4AuthoringCourse:
    """A validated route and all corresponding chapter packages."""

    route: dict[str, Any]
    chapters: tuple[V4ChapterPackage, ...]


@dataclass(frozen=True)
class V4Projection:
    """Deterministic learner and author file projections."""

    learner_files: dict[str, bytes]
    author_files: dict[str, bytes]
    course_contract_sha256: str


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V4ContractError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise V4ContractError(f"{label} must be an array")
    return value


def _exact_fields(
    value: Mapping[str, Any],
    required: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise V4ContractError(f"{label} is missing field(s): {', '.join(missing)}")
    if unknown:
        raise V4ContractError(f"{label} has unknown field(s): {', '.join(unknown)}")


def _text(value: Mapping[str, Any], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise V4ContractError(f"{label}.{key} must be non-empty text")
    return result


def _stable_id(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or not STABLE_ID_PATTERN.fullmatch(value)
    ):
        raise V4ContractError(f"{label} must be a stable lowercase id")
    return value


def _string_array(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
) -> list[str]:
    items = _array(value, label)
    if len(items) < minimum or not all(
        isinstance(item, str) and item.strip() for item in items
    ):
        raise V4ContractError(
            f"{label} must contain at least {minimum} non-empty string(s)"
        )
    if len(items) != len(set(items)):
        raise V4ContractError(f"{label} must not contain duplicates")
    return [str(item) for item in items]


def _safe_relative_path(
    value: Any,
    label: str,
    *,
    suffix: str | None = None,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
    ):
        raise V4ContractError(f"{label} must be a safe POSIX relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(part in FORBIDDEN_TREE_NAMES for part in path.parts)
        or path.as_posix() != value
    ):
        raise V4ContractError(f"{label} must be a safe POSIX relative path")
    if suffix is not None and path.suffix != suffix:
        raise V4ContractError(f"{label} must end in {suffix}")
    return path.as_posix()


def _selector(value: Any, label: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise V4ContractError(f"{label} must be a pytest selector")
    path, separator, node = value.partition("::")
    if (
        not separator
        or not node
        or "::" in node
        or not node.startswith("test_")
    ):
        raise V4ContractError(
            f"{label} must use the form test_file.py::test_name"
        )
    relative = _safe_relative_path(path, label, suffix=".py")
    if not PurePosixPath(relative).name.startswith("test_"):
        raise V4ContractError(f"{label} must select a test_*.py file")
    return relative, node


def _parse_python(data: bytes, label: str) -> ast.Module:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise V4ContractError(f"{label} must be UTF-8 Python") from error
    try:
        return ast.parse(text, filename=label)
    except SyntaxError as error:
        raise V4ContractError(f"{label} is invalid Python: {error}") from error


def _declares(module: ast.Module, name: str) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == name
        for node in module.body
    )


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise V4ContractError(f"{label} is missing or is not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise V4ContractError(f"{label} is invalid JSON: {error}") from error
    return _object(value, label)


def _validate_regular_tree(root: Path, label: str) -> None:
    if root.is_symlink() or not root.is_dir():
        raise V4ContractError(f"{label} must be a regular directory")
    for current, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in [*directories, *files]:
            path = current_path / name
            if name in FORBIDDEN_TREE_NAMES:
                raise V4ContractError(f"{label} contains forbidden path {name}")
            if path.is_symlink():
                raise V4ContractError(f"{label} cannot contain symlinks: {path}")
            if path.is_file() or path.is_dir():
                continue
            raise V4ContractError(f"{label} contains a special file: {path}")


def _tree_files(
    root: Path,
    label: str,
    *,
    required: bool,
) -> dict[str, bytes]:
    if not root.exists():
        if required:
            raise V4ContractError(f"{label} directory is missing")
        return {}
    _validate_regular_tree(root, label)
    files: dict[str, bytes] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        _safe_relative_path(relative, f"{label} path")
        try:
            data = path.read_bytes()
        except OSError as error:
            raise V4ContractError(f"cannot read {label} file {relative}") from error
        if path.suffix == ".py":
            _parse_python(data, f"{label}/{relative}")
        files[relative] = data
    return files


def _validate_course(value: Any) -> dict[str, Any]:
    course = _object(value, "course")
    _exact_fields(course, COURSE_FIELDS, "course")
    course_id = _text(course, "id", "course")
    if not COURSE_ID_PATTERN.fullmatch(course_id):
        raise V4ContractError("course.id must be lowercase kebab-case")
    _stable_id(_text(course, "curriculum_id", "course"), "course.curriculum_id")
    for key in (
        "title",
        "description",
        "python_requires",
        "capstone",
    ):
        _text(course, key, "course")
    if course.get("language") not in COURSE_LANGUAGES:
        raise V4ContractError("course.language must be zh-CN or en")
    _string_array(course.get("dependencies"), "course.dependencies")
    return course


def _validate_target(value: Any) -> tuple[dict[str, Any], set[str]]:
    target = _object(value, "target")
    _exact_fields(
        target,
        TARGET_REQUIRED_FIELDS,
        "target",
        optional=TARGET_OPTIONAL_FIELDS,
    )
    for key in ("name", "version"):
        _text(target, key, "target")
    if target.get("kind") not in TARGET_KINDS:
        raise V4ContractError(
            "target.kind must be stdlib, pypi, framework, or repository"
        )
    if "track" in target:
        _text(target, "track", "target")
    if "import_roots" in target:
        roots = _string_array(
            target["import_roots"], "target.import_roots", minimum=1
        )
        if any("." in root or not root.isidentifier() for root in roots):
            raise V4ContractError(
                "target.import_roots must contain top-level Python identifiers"
            )
    sources = _array(target.get("official_sources"), "target.official_sources")
    if not sources:
        raise V4ContractError("target.official_sources must not be empty")
    source_ids: set[str] = set()
    for index, raw_source in enumerate(sources):
        label = f"target.official_sources[{index}]"
        source = _object(raw_source, label)
        _exact_fields(source, SOURCE_FIELDS, label)
        source_id = _stable_id(source.get("id"), f"{label}.id")
        if source_id in source_ids:
            raise V4ContractError(f"duplicate official source id: {source_id}")
        source_ids.add(source_id)
        _text(source, "title", label)
        parsed = urlparse(_text(source, "url", label))
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise V4ContractError(f"{label}.url must be an HTTPS URL")
    return target, source_ids


def _validate_research(value: Any) -> dict[str, Any]:
    research = _object(value, "research")
    _exact_fields(research, RESEARCH_FIELDS, "research")
    if research.get("status") != "complete":
        raise V4ContractError("research.status must be complete")
    _text(research, "version_basis", "research")
    _string_array(research.get("notes"), "research.notes", minimum=1)
    return research


def _validate_study_minutes(value: Any, label: str) -> dict[str, Any]:
    minutes = _object(value, label)
    _exact_fields(
        minutes,
        STUDY_REQUIRED_FIELDS,
        label,
        optional=STUDY_OPTIONAL_FIELDS,
    )
    minimum = minutes.get("min")
    maximum = minutes.get("max")
    if (
        type(minimum) is not int
        or type(maximum) is not int
        or minimum <= 0
        or maximum < minimum
    ):
        raise V4ContractError(
            f"{label}.min/max must be positive integers with min <= max"
        )
    if "reason" in minutes:
        _text(minutes, "reason", label)
    return minutes


def _validate_task(
    value: Any,
    *,
    label: str,
    chapter_id: str,
    owned_paths: set[str],
) -> dict[str, Any]:
    task = _object(value, label)
    _exact_fields(
        task,
        TASK_REQUIRED_FIELDS,
        label,
        optional=TASK_OPTIONAL_FIELDS,
    )
    task_id = _stable_id(task.get("id"), f"{label}.id")
    if not task_id.startswith(f"{chapter_id}."):
        raise V4ContractError(f"{label}.id must start with {chapter_id}.")
    for key in ("title", "prompt"):
        _text(task, key, label)
    file_path = _safe_relative_path(
        task.get("file"), f"{label}.file", suffix=".py"
    )
    if file_path not in owned_paths:
        raise V4ContractError(f"{label}.file must be one of the chapter owned_paths")
    symbol = _text(task, "symbol", label)
    if not symbol.isidentifier():
        raise V4ContractError(f"{label}.symbol must be a Python identifier")
    points = task.get("points")
    if type(points) is not int or points <= 0:
        raise V4ContractError(f"{label}.points must be a positive integer")
    timeout = task.get("timeout_seconds")
    if type(timeout) is not int or not 1 <= timeout <= 90:
        raise V4ContractError(
            f"{label}.timeout_seconds must be an integer from 1 to 90"
        )
    for kind in ("public_tests", "hidden_tests"):
        selectors = _string_array(task.get(kind), f"{label}.{kind}", minimum=1)
        for index, selector in enumerate(selectors):
            _selector(selector, f"{label}.{kind}[{index}]")
    if "example" in task:
        example = _object(task["example"], f"{label}.example")
        _exact_fields(example, TASK_EXAMPLE_FIELDS, f"{label}.example")
        for key in TASK_EXAMPLE_FIELDS:
            _text(example, key, f"{label}.example")
    return task


def _validate_chapters(
    value: Any,
    *,
    source_ids: set[str],
) -> list[dict[str, Any]]:
    raw_chapters = _array(value, "chapters")
    if len(raw_chapters) < 2:
        raise V4ContractError(
            "chapters must contain lab00 and at least one graded chapter"
        )
    chapters: list[dict[str, Any]] = []
    previous: str | None = None
    prep_number = 0
    lab_number = 0
    entered_graded_route = False
    task_ids: set[str] = set()
    owned_globally: set[str] = set()
    capstone_indexes: list[int] = []

    for index, raw_chapter in enumerate(raw_chapters):
        label = f"chapters[{index}]"
        chapter = _object(raw_chapter, label)
        _exact_fields(chapter, CHAPTER_FIELDS, label)
        chapter_id = _stable_id(chapter.get("id"), f"{label}.id")
        kind = chapter.get("kind")
        if kind not in CHAPTER_KINDS:
            raise V4ContractError(
                f"{label}.kind must be one of: {', '.join(sorted(CHAPTER_KINDS))}"
            )
        if index == 0:
            if (
                chapter_id != "lab00"
                or kind != "orientation"
                or chapter.get("depends_on") is not None
            ):
                raise V4ContractError(
                    "the first chapter must be orientation lab00 with null depends_on"
                )
        elif kind == "preparatory":
            if entered_graded_route:
                raise V4ContractError(
                    "preparatory chapters cannot follow graded chapters"
                )
            prep_number += 1
            expected = f"prep{prep_number:02d}"
            if chapter_id != expected:
                raise V4ContractError(f"{label}.id must be {expected}")
        else:
            entered_graded_route = True
            lab_number += 1
            expected = f"lab{lab_number:02d}"
            if chapter_id != expected or kind == "orientation":
                raise V4ContractError(
                    f"graded chapters must be ordered linearly as {expected}"
                )
        if index > 0 and chapter.get("depends_on") != previous:
            raise V4ContractError(f"{chapter_id}.depends_on must be {previous}")
        if kind == "capstone":
            capstone_indexes.append(index)
        _text(chapter, "title", label)
        _validate_study_minutes(chapter.get("study_minutes"), f"{label}.study_minutes")
        declared_sources = _string_array(
            chapter.get("sources"), f"{label}.sources", minimum=1
        )
        unknown_sources = sorted(set(declared_sources) - source_ids)
        if unknown_sources:
            raise V4ContractError(
                f"{label}.sources reference unknown source(s): "
                + ", ".join(unknown_sources)
            )
        owned_paths = {
            _safe_relative_path(path, f"{label}.owned_paths", suffix=".py")
            for path in _string_array(
                chapter.get("owned_paths"), f"{label}.owned_paths"
            )
        }
        if any(not path.startswith("src/") for path in owned_paths):
            raise V4ContractError(f"{label}.owned_paths must stay under src/")
        collisions = sorted(owned_paths & owned_globally)
        if collisions:
            raise V4ContractError(
                f"{label}.owned_paths collide with earlier chapters: "
                + ", ".join(collisions)
            )
        owned_globally.update(owned_paths)
        tasks = _array(chapter.get("task_contracts"), f"{label}.task_contracts")
        if kind in {"orientation", "preparatory"} and (owned_paths or tasks):
            raise V4ContractError(
                f"{chapter_id} is knowledge-only and cannot own code or tasks"
            )
        if kind in GRADED_CHAPTER_KINDS and (not owned_paths or not tasks):
            raise V4ContractError(
                f"{chapter_id} must own code and at least one task"
            )
        for task_index, raw_task in enumerate(tasks):
            task = _validate_task(
                raw_task,
                label=f"{label}.task_contracts[{task_index}]",
                chapter_id=chapter_id,
                owned_paths=owned_paths,
            )
            task_id = str(task["id"])
            if task_id in task_ids:
                raise V4ContractError(f"duplicate task id: {task_id}")
            task_ids.add(task_id)
        chapters.append(chapter)
        previous = chapter_id

    if lab_number == 0:
        raise V4ContractError("the route must contain at least one graded chapter")
    if len(capstone_indexes) > 1 or (
        capstone_indexes and capstone_indexes[0] != len(chapters) - 1
    ):
        raise V4ContractError("capstone, when present, must be the final chapter")
    return chapters


def validate_v4_route(value: Any) -> dict[str, Any]:
    """Validate and return a defensive copy of a schema-v4 route."""

    route = copy.deepcopy(_object(value, "route"))
    _exact_fields(route, ROUTE_FIELDS, "route")
    if route.get("schema_version") != COURSE_SCHEMA_VERSION:
        raise V4ContractError("route.schema_version must be 4")
    _validate_course(route.get("course"))
    _target, source_ids = _validate_target(route.get("target"))
    _validate_research(route.get("research"))
    _validate_chapters(route.get("chapters"), source_ids=source_ids)
    return route


def _validate_terms(value: Any, label: str) -> dict[str, Any]:
    terms = _object(value, label)
    _exact_fields(terms, TERMS_FIELDS, label)
    seen: set[str] = set()
    for index, raw_term in enumerate(_array(terms.get("terms"), f"{label}.terms")):
        item_label = f"{label}.terms[{index}]"
        item = _object(raw_term, item_label)
        _exact_fields(item, TERM_FIELDS, item_label)
        term = _text(item, "term", item_label)
        _text(item, "definition", item_label)
        if term in seen:
            raise V4ContractError(f"{label} contains duplicate term: {term}")
        seen.add(term)
    return terms


def _validate_quiz(
    value: Any,
    *,
    label: str,
    chapter_id: str,
    global_ids: set[str],
) -> dict[str, Any]:
    quiz = _object(value, label)
    _exact_fields(quiz, QUIZ_FIELDS, label)
    questions = _array(quiz.get("questions"), f"{label}.questions")
    if not questions:
        raise V4ContractError(f"{label}.questions must not be empty")
    for index, raw_question in enumerate(questions):
        item_label = f"{label}.questions[{index}]"
        question = _object(raw_question, item_label)
        _exact_fields(
            question,
            QUIZ_QUESTION_REQUIRED_FIELDS,
            item_label,
            optional=QUIZ_QUESTION_OPTIONAL_FIELDS,
        )
        question_id = _stable_id(question.get("id"), f"{item_label}.id")
        if not question_id.startswith(f"{chapter_id}."):
            raise V4ContractError(
                f"{item_label}.id must start with {chapter_id}."
            )
        if question_id in global_ids:
            raise V4ContractError(f"duplicate quiz question id: {question_id}")
        global_ids.add(question_id)
        _text(question, "prompt", item_label)
        if "explanation" in question:
            _text(question, "explanation", item_label)
        choices = _array(question.get("choices"), f"{item_label}.choices")
        if len(choices) < 2:
            raise V4ContractError(f"{item_label}.choices must contain at least two choices")
        choice_ids: set[str] = set()
        for choice_index, raw_choice in enumerate(choices):
            choice_label = f"{item_label}.choices[{choice_index}]"
            choice = _object(raw_choice, choice_label)
            _exact_fields(
                choice,
                QUIZ_CHOICE_REQUIRED_FIELDS,
                choice_label,
                optional=QUIZ_CHOICE_OPTIONAL_FIELDS,
            )
            choice_id = _stable_id(choice.get("id"), f"{choice_label}.id")
            if choice_id in choice_ids:
                raise V4ContractError(
                    f"{item_label} contains duplicate choice id: {choice_id}"
                )
            choice_ids.add(choice_id)
            _text(choice, "text", choice_label)
            if "feedback" in choice:
                _text(choice, "feedback", choice_label)
        if question.get("answer_id") not in choice_ids:
            raise V4ContractError(
                f"{item_label}.answer_id must reference one choice"
            )
    return quiz


def _validate_package_root(root: Path, chapter_id: str, *, graded: bool) -> None:
    _validate_regular_tree(root, f"{chapter_id} package")
    allowed = {
        "tutorial.md",
        "terms.json",
        "quiz.json",
        "starter",
        "solution",
        "tests",
        "examples",
    }
    actual = {path.name for path in root.iterdir()}
    required = {"tutorial.md", "terms.json", "quiz.json"}
    missing = sorted(required - actual)
    unknown = sorted(actual - allowed)
    if missing:
        raise V4ContractError(
            f"{chapter_id} package is missing: {', '.join(missing)}"
        )
    if unknown:
        raise V4ContractError(
            f"{chapter_id} package has unexpected entry: {', '.join(unknown)}"
        )
    code_entries = {"starter", "solution", "tests"}
    if graded and not code_entries <= actual:
        raise V4ContractError(
            f"{chapter_id} package requires starter, solution, and tests"
        )
    if not graded and actual & code_entries:
        raise V4ContractError(
            f"{chapter_id} is knowledge-only and cannot contain code or tests"
        )
    if graded:
        tests = root / "tests"
        children = {path.name for path in tests.iterdir()} if tests.is_dir() else set()
        if children != {"public", "hidden"}:
            raise V4ContractError(
                f"{chapter_id}/tests must contain exactly public and hidden"
            )


def _load_chapter_package(
    chapter: dict[str, Any],
    root: Path,
    *,
    quiz_ids: set[str],
) -> V4ChapterPackage:
    chapter_id = str(chapter["id"])
    graded = str(chapter["kind"]) in GRADED_CHAPTER_KINDS
    _validate_package_root(root, chapter_id, graded=graded)
    tutorial_path = root / "tutorial.md"
    if tutorial_path.is_symlink() or not tutorial_path.is_file():
        raise V4ContractError(f"{chapter_id}/tutorial.md must be a regular file")
    try:
        tutorial = tutorial_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise V4ContractError(
            f"{chapter_id}/tutorial.md must be UTF-8 Markdown"
        ) from error
    if not tutorial.strip():
        raise V4ContractError(f"{chapter_id}/tutorial.md must not be empty")
    terms = _validate_terms(
        _read_json(root / "terms.json", f"{chapter_id}/terms.json"),
        f"{chapter_id}/terms.json",
    )
    quiz = _validate_quiz(
        _read_json(root / "quiz.json", f"{chapter_id}/quiz.json"),
        label=f"{chapter_id}/quiz.json",
        chapter_id=chapter_id,
        global_ids=quiz_ids,
    )

    starter = _tree_files(
        root / "starter", f"{chapter_id}/starter", required=graded
    )
    solution = _tree_files(
        root / "solution", f"{chapter_id}/solution", required=graded
    )
    public_tests = _tree_files(
        root / "tests" / "public",
        f"{chapter_id}/tests/public",
        required=graded,
    )
    hidden_tests = _tree_files(
        root / "tests" / "hidden",
        f"{chapter_id}/tests/hidden",
        required=graded,
    )
    examples = _tree_files(
        root / "examples", f"{chapter_id}/examples", required=False
    )
    owned = set(str(path) for path in chapter["owned_paths"])
    if set(starter) != owned:
        raise V4ContractError(
            f"{chapter_id}/starter files must exactly match owned_paths"
        )
    if set(solution) != owned:
        raise V4ContractError(
            f"{chapter_id}/solution files must exactly match owned_paths"
        )

    starter_modules = {
        path: _parse_python(data, f"{chapter_id}/starter/{path}")
        for path, data in starter.items()
    }
    solution_modules = {
        path: _parse_python(data, f"{chapter_id}/solution/{path}")
        for path, data in solution.items()
    }
    public_modules = {
        path: _parse_python(data, f"{chapter_id}/tests/public/{path}")
        for path, data in public_tests.items()
        if path.endswith(".py")
    }
    hidden_modules = {
        path: _parse_python(data, f"{chapter_id}/tests/hidden/{path}")
        for path, data in hidden_tests.items()
        if path.endswith(".py")
    }
    for task_index, task in enumerate(chapter["task_contracts"]):
        label = f"{chapter_id}.task_contracts[{task_index}]"
        file_path = str(task["file"])
        symbol = str(task["symbol"])
        if not _declares(starter_modules[file_path], symbol):
            raise V4ContractError(
                f"{label}.symbol is not declared by the starter file"
            )
        if not _declares(solution_modules[file_path], symbol):
            raise V4ContractError(
                f"{label}.symbol is not declared by the solution file"
            )
        for field, registry in (
            ("public_tests", public_modules),
            ("hidden_tests", hidden_modules),
        ):
            for selector_index, raw_selector in enumerate(task[field]):
                selector_label = f"{label}.{field}[{selector_index}]"
                test_path, node = _selector(raw_selector, selector_label)
                module = registry.get(test_path)
                if module is None:
                    raise V4ContractError(
                        f"{selector_label} references a missing test file"
                    )
                if not _declares(module, node):
                    raise V4ContractError(
                        f"{selector_label} references a missing test function"
                    )

    return V4ChapterPackage(
        chapter=copy.deepcopy(chapter),
        root=root.resolve(),
        tutorial=tutorial,
        terms=copy.deepcopy(terms),
        quiz=copy.deepcopy(quiz),
        starter_files=starter,
        solution_files=solution,
        public_test_files=public_tests,
        hidden_test_files=hidden_tests,
        example_files=examples,
    )


def validate_v4_authoring(
    route: Mapping[str, Any],
    packages_root: Path | str,
) -> V4AuthoringCourse:
    """Validate one in-memory route and its package directory."""

    normalized = validate_v4_route(route)
    unresolved_root = Path(packages_root).absolute()
    _validate_regular_tree(unresolved_root, "chapter packages")
    expected_ids = [str(chapter["id"]) for chapter in normalized["chapters"]]
    actual_ids: list[str] = []
    for path in sorted(unresolved_root.iterdir(), key=lambda item: item.name):
        if path.is_symlink() or not path.is_dir():
            raise V4ContractError(
                "chapter packages root may contain only regular chapter directories"
            )
        actual_ids.append(path.name)
    if set(actual_ids) != set(expected_ids) or len(actual_ids) != len(expected_ids):
        missing = sorted(set(expected_ids) - set(actual_ids))
        unexpected = sorted(set(actual_ids) - set(expected_ids))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise V4ContractError(
            "chapter packages do not match route: " + "; ".join(details)
        )
    quiz_ids: set[str] = set()
    packages: list[V4ChapterPackage] = []
    errors: list[str] = []
    for chapter in normalized["chapters"]:
        chapter_id = str(chapter["id"])
        chapter_quiz_ids = set(quiz_ids)
        try:
            package = _load_chapter_package(
                chapter,
                unresolved_root / chapter_id,
                quiz_ids=chapter_quiz_ids,
            )
        except V4ContractError as error:
            errors.append(f"{chapter_id}: {error}")
            continue
        packages.append(package)
        quiz_ids = chapter_quiz_ids
    if errors:
        rendered = "\n".join(f"- {error}" for error in errors)
        raise V4ContractError(
            "chapter package mechanical validation failed:\n" + rendered
        )
    return V4AuthoringCourse(route=normalized, chapters=tuple(packages))


def load_v4_authoring(
    route_path: Path | str,
    packages_root: Path | str,
) -> V4AuthoringCourse:
    """Load and validate a route JSON file plus ``packages/<chapter-id>``."""

    route = _read_json(Path(route_path), "schema-v4 route")
    return validate_v4_authoring(route, packages_root)


def load_chapter_packages(
    route: Mapping[str, Any],
    packages_root: Path | str,
) -> tuple[V4ChapterPackage, ...]:
    """Return validated packages for callers that already hold a route."""

    return validate_v4_authoring(route, packages_root).chapters


def project_public_quiz(quiz: Mapping[str, Any]) -> dict[str, Any]:
    """Strip answer keys and all feedback from one validated authored quiz."""

    questions = []
    for raw_question in quiz["questions"]:
        question = _object(raw_question, "quiz question")
        questions.append(
            {
                "id": question["id"],
                "prompt": question["prompt"],
                "choices": [
                    {"id": choice["id"], "text": choice["text"]}
                    for choice in question["choices"]
                ],
            }
        )
    return {"questions": questions}


def project_quiz_answers(quiz: Mapping[str, Any]) -> dict[str, Any]:
    """Project answer, explanation, and per-choice feedback for author use."""

    answers: dict[str, Any] = {}
    for raw_question in quiz["questions"]:
        question = _object(raw_question, "quiz question")
        answers[str(question["id"])] = {
            "answer_id": question["answer_id"],
            "explanation": question.get("explanation", ""),
            "feedback": {
                str(choice["id"]): choice.get("feedback", "")
                for choice in question["choices"]
            },
        }
    return answers


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_strings(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _public_selector(chapter_id: str, selector: str) -> str:
    path, node = _selector(selector, "public test selector")
    return f"tests/{chapter_id}/{path}::{node}"


def _hidden_selector(chapter_id: str, selector: str) -> str:
    path, node = _selector(selector, "hidden test selector")
    return f"tests/hidden/{chapter_id}/{path}::{node}"


def render_course_toml(course: V4AuthoringCourse) -> str:
    """Render deterministic learner-visible course metadata."""

    route = course.route
    metadata = route["course"]
    target = route["target"]
    lines = [
        "schema_version = 4",
        f"course_id = {_toml_string(metadata['id'])}",
        f"curriculum_id = {_toml_string(metadata['curriculum_id'])}",
        f"title = {_toml_string(metadata['title'])}",
        f"description = {_toml_string(metadata['description'])}",
        f"language = {_toml_string(metadata['language'])}",
        f"python_requires = {_toml_string(metadata['python_requires'])}",
        f"dependencies = {_toml_strings(list(metadata['dependencies']))}",
        f"capstone = {_toml_string(metadata['capstone'])}",
        "",
        "[target]",
        f"name = {_toml_string(target['name'])}",
        f"kind = {_toml_string(target['kind'])}",
        f"version = {_toml_string(target['version'])}",
    ]
    if "track" in target:
        lines.append(f"track = {_toml_string(target['track'])}")
    if "import_roots" in target:
        lines.append(
            f"import_roots = {_toml_strings(list(target['import_roots']))}"
        )
    for source in target["official_sources"]:
        lines.extend(
            [
                "",
                "[[sources]]",
                f"id = {_toml_string(source['id'])}",
                f"title = {_toml_string(source['title'])}",
                f"url = {_toml_string(source['url'])}",
            ]
        )
    for chapter in route["chapters"]:
        chapter_id = str(chapter["id"])
        graded = str(chapter["kind"]) in GRADED_CHAPTER_KINDS
        lines.extend(
            [
                "",
                "[[chapters]]",
                f"id = {_toml_string(chapter_id)}",
                f"title = {_toml_string(chapter['title'])}",
                f"kind = {_toml_string(chapter['kind'])}",
                f"graded = {'true' if graded else 'false'}",
            ]
        )
        if chapter["depends_on"] is not None:
            lines.append(
                f"depends_on = {_toml_string(str(chapter['depends_on']))}"
            )
        lines.extend(
            [
                f"study_min = {chapter['study_minutes']['min']}",
                f"study_max = {chapter['study_minutes']['max']}",
                f"source_ids = {_toml_strings(list(chapter['sources']))}",
                f"owned_paths = {_toml_strings(list(chapter['owned_paths']))}",
                f"tutorial = {_toml_string(f'chapters/{chapter_id}/tutorial.md')}",
                f"terms = {_toml_string(f'chapters/{chapter_id}/terms.json')}",
                f"quiz = {_toml_string(f'chapters/{chapter_id}/quiz.json')}",
            ]
        )
        if "reason" in chapter["study_minutes"]:
            lines.append(
                f"study_reason = {_toml_string(chapter['study_minutes']['reason'])}"
            )
        for task in chapter["task_contracts"]:
            lines.extend(
                [
                    "",
                    "[[chapters.tasks]]",
                    f"id = {_toml_string(task['id'])}",
                    f"title = {_toml_string(task['title'])}",
                    f"file = {_toml_string(task['file'])}",
                    f"symbol = {_toml_string(task['symbol'])}",
                    f"prompt = {_toml_string(task['prompt'])}",
                    f"points = {task['points']}",
                    f"timeout_seconds = {task['timeout_seconds']}",
                    "public_tests = "
                    + _toml_strings(
                        [
                            _public_selector(chapter_id, selector)
                            for selector in task["public_tests"]
                        ]
                    ),
                ]
            )
            if "example" in task:
                for key in ("input", "output", "explanation"):
                    lines.append(
                        f"example_{key} = {_toml_string(task['example'][key])}"
                    )
    return "\n".join(lines) + "\n"


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contract_payload(
    course: V4AuthoringCourse,
    *,
    course_toml: bytes,
    public_quizzes: Mapping[str, bytes],
) -> dict[str, Any]:
    metadata = course.route["course"]
    return {
        "schema_version": PUBLIC_BINDING_SCHEMA_VERSION,
        "course_schema_version": COURSE_SCHEMA_VERSION,
        "course_id": metadata["id"],
        "curriculum_id": metadata["curriculum_id"],
        "course_toml_sha256": _digest(course_toml),
        "public_quiz_sha256": {
            chapter_id: _digest(value)
            for chapter_id, value in sorted(public_quizzes.items())
        },
    }


def _runtime_manifest(
    course: V4AuthoringCourse,
    *,
    contract_payload: Mapping[str, Any],
    contract_sha256: str,
) -> dict[str, Any]:
    route = course.route
    metadata = route["course"]
    sources = {
        str(source["id"]): copy.deepcopy(source)
        for source in route["target"]["official_sources"]
    }
    chapters: list[dict[str, Any]] = []
    for chapter in route["chapters"]:
        chapter_id = str(chapter["id"])
        tasks: list[dict[str, Any]] = []
        for task in chapter["task_contracts"]:
            projected = {
                key: copy.deepcopy(task[key])
                for key in (
                    "id",
                    "title",
                    "file",
                    "symbol",
                    "prompt",
                    "points",
                    "timeout_seconds",
                )
            }
            projected["tests"] = {
                "public": [
                    _public_selector(chapter_id, selector)
                    for selector in task["public_tests"]
                ]
            }
            if "example" in task:
                projected["example"] = copy.deepcopy(task["example"])
            tasks.append(projected)
        chapters.append(
            {
                "id": chapter_id,
                "title": chapter["title"],
                "kind": chapter["kind"],
                "unit_type": (
                    "coding"
                    if chapter["kind"] in GRADED_CHAPTER_KINDS
                    else chapter["kind"]
                ),
                "graded": chapter["kind"] in GRADED_CHAPTER_KINDS,
                "depends_on": chapter["depends_on"],
                "study_minutes": copy.deepcopy(chapter["study_minutes"]),
                "sources": [
                    copy.deepcopy(sources[source_id])
                    for source_id in chapter["sources"]
                ],
                "tasks": tasks,
                "questions": copy.deepcopy(tasks),
            }
        )
    return {
        **copy.deepcopy(dict(contract_payload)),
        "course_contract_sha256": contract_sha256,
        "course_id": metadata["id"],
        "curriculum_id": metadata["curriculum_id"],
        "title": metadata["title"],
        "description": metadata["description"],
        "language": metadata["language"],
        "python_requires": metadata["python_requires"],
        "capstone": metadata["capstone"],
        "target": copy.deepcopy(route["target"]),
        "chapters": chapters,
        "labs": copy.deepcopy(chapters),
        "total_points": sum(
            int(task["points"])
            for chapter in route["chapters"]
            for task in chapter["task_contracts"]
        ),
    }


def course_contract_sha256(course: V4AuthoringCourse) -> str:
    """Return the immutable public contract digest used for author binding."""

    course_toml = render_course_toml(course).encode("utf-8")
    quizzes = {
        chapter.chapter_id: _json_bytes(project_public_quiz(chapter.quiz))
        for chapter in course.chapters
    }
    return _digest(_json_bytes(_contract_payload(
        course,
        course_toml=course_toml,
        public_quizzes=quizzes,
    )))


def _add_file(
    files: dict[str, bytes],
    path: str,
    value: bytes,
    *,
    projection: str,
) -> None:
    _safe_relative_path(path, f"{projection} projection path")
    if path in files:
        raise V4ContractError(f"{projection} projection collision at {path}")
    files[path] = value


def project_v4_authoring(course: V4AuthoringCourse) -> V4Projection:
    """Build deterministic in-memory learner and author file maps."""

    learner: dict[str, bytes] = {}
    author: dict[str, bytes] = {}
    course_toml = render_course_toml(course).encode("utf-8")
    _add_file(learner, "course.toml", course_toml, projection="learner")
    public_quizzes: dict[str, bytes] = {}
    all_answers: dict[str, Any] = {}

    for chapter in course.chapters:
        chapter_id = chapter.chapter_id
        public_quiz = _json_bytes(project_public_quiz(chapter.quiz))
        public_quizzes[chapter_id] = public_quiz
        all_answers[chapter_id] = project_quiz_answers(chapter.quiz)
        _add_file(
            learner,
            f"chapters/{chapter_id}/tutorial.md",
            chapter.tutorial.encode("utf-8"),
            projection="learner",
        )
        _add_file(
            learner,
            f"chapters/{chapter_id}/terms.json",
            _json_bytes(chapter.terms),
            projection="learner",
        )
        _add_file(
            learner,
            f"chapters/{chapter_id}/quiz.json",
            public_quiz,
            projection="learner",
        )
        for path, value in chapter.starter_files.items():
            _add_file(learner, path, value, projection="learner")
        for path, value in chapter.public_test_files.items():
            _add_file(
                learner,
                f"tests/{chapter_id}/{path}",
                value,
                projection="learner",
            )
        for path, value in chapter.example_files.items():
            _add_file(
                learner,
                f"examples/{chapter_id}/{path}",
                value,
                projection="learner",
            )
        for path, value in chapter.solution_files.items():
            _add_file(author, f"solution/{path}", value, projection="author")
        for path, value in chapter.hidden_test_files.items():
            _add_file(
                author,
                f"tests/hidden/{chapter_id}/{path}",
                value,
                projection="author",
            )

    contract_payload = _contract_payload(
        course,
        course_toml=course_toml,
        public_quizzes=public_quizzes,
    )
    contract_sha256 = _digest(_json_bytes(contract_payload))
    public_binding = _runtime_manifest(
        course,
        contract_payload=contract_payload,
        contract_sha256=contract_sha256,
    )
    _add_file(
        learner,
        ".coursekit/course.json",
        _json_bytes(public_binding),
        projection="learner",
    )

    hidden_tasks: list[dict[str, Any]] = []
    for chapter in course.route["chapters"]:
        chapter_id = str(chapter["id"])
        for task in chapter["task_contracts"]:
            hidden_tasks.append(
                {
                    "chapter_id": chapter_id,
                    "task_id": task["id"],
                    "hidden_tests": [
                        _hidden_selector(chapter_id, selector)
                        for selector in task["hidden_tests"]
                    ],
                }
            )
    author_binding = {
        "schema_version": AUTHOR_BINDING_SCHEMA_VERSION,
        "course_schema_version": COURSE_SCHEMA_VERSION,
        "course_id": course.route["course"]["id"],
        "curriculum_id": course.route["course"]["curriculum_id"],
        "course_contract_sha256": contract_sha256,
        "tasks": hidden_tasks,
    }
    _add_file(
        author,
        "author.json",
        _json_bytes(author_binding),
        projection="author",
    )
    _add_file(
        author,
        "quiz-answers.json",
        _json_bytes(
            {
                "schema_version": 1,
                "course_id": course.route["course"]["id"],
                "chapters": all_answers,
            }
        ),
        projection="author",
    )
    return V4Projection(
        learner_files=learner,
        author_files=author,
        course_contract_sha256=contract_sha256,
    )


__all__ = [
    "AUTHOR_BINDING_SCHEMA_VERSION",
    "COURSE_SCHEMA_VERSION",
    "PACKAGE_SCHEMA_VERSION",
    "PUBLIC_BINDING_SCHEMA_VERSION",
    "V4AuthoringCourse",
    "V4ChapterPackage",
    "V4ContractError",
    "V4Projection",
    "course_contract_sha256",
    "load_chapter_packages",
    "load_v4_authoring",
    "project_public_quiz",
    "project_quiz_answers",
    "project_v4_authoring",
    "render_course_toml",
    "validate_v4_authoring",
    "validate_v4_route",
]
