#!/usr/bin/env python3
"""Run one aggregated schema-v4 course acceptance and write its receipt."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import tomllib
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from authoring_contract import v4_runtime_contract_sha256

SCRIPT_ROOT = Path(__file__).resolve().parent
TRUSTED_RUNTIME_ROOT = (
    SCRIPT_ROOT.parent / "assets/course-template-v4/coursekit_runtime"
)
TRUSTED_EXECUTION = TRUSTED_RUNTIME_ROOT / "execution.py"
TRUSTED_BOOTSTRAP = TRUSTED_RUNTIME_ROOT / "pytest_bootstrap.py"
IGNORED_TREE_NAMES = {
    ".DS_Store",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
MUTABLE_STATE_PATHS = {
    ".coursekit/acceptance-progress.json",
    ".coursekit/acceptance-progress.json.lock",
    ".coursekit/progress.json",
    ".coursekit/progress.json.lock",
    ".coursekit/state.json",
    ".coursekit/state.json.lock",
}
RUNTIME_TEXT_SUFFIXES = {
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
COURSEKIT_ENVIRONMENT_NAMES = (
    "COURSEKIT_LEARNER_ROOT",
    "COURSEKIT_ROOT",
    "COURSEKIT_COURSE_DIR",
    "COURSEKIT_AUTHOR_ROOT",
    "COURSEKIT_STATE_PATH",
)
GRADED_CHAPTER_KINDS = frozenset({"lab", "integration", "capstone"})
LEARNER_PRIVATE_ROOT_FILES = frozenset({"author.json", "quiz-answers.json"})


class V4VerificationError(ValueError):
    """A schema-v4 candidate cannot produce a trustworthy acceptance receipt."""


def _isolated_pytest_runner() -> Any:
    """Load the Skill-owned disposable pytest executor, never candidate code."""

    module_name = "_coursekit_v4_verifier_execution"
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded.run_isolated_pytest
    if TRUSTED_EXECUTION.is_symlink() or not TRUSTED_EXECUTION.is_file():
        raise V4VerificationError(
            "trusted schema-v4 pytest executor is unavailable"
        )
    spec = importlib.util.spec_from_file_location(module_name, TRUSTED_EXECUTION)
    if spec is None or spec.loader is None:
        raise V4VerificationError(
            "trusted schema-v4 pytest executor cannot be imported"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        sys.modules.pop(module_name, None)
        raise V4VerificationError(
            "trusted schema-v4 pytest executor cannot be imported"
        ) from error
    finally:
        sys.dont_write_bytecode = previous_bytecode
    runner = getattr(module, "run_isolated_pytest", None)
    if not callable(runner):
        raise V4VerificationError(
            "trusted schema-v4 pytest executor has no run entrypoint"
        )
    return runner


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise V4VerificationError(f"{label} is missing or is not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise V4VerificationError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise V4VerificationError(f"{label} must contain a JSON object")
    return value


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _preflight_tree(
    root: Path,
    *,
    label: str,
    reject_bytecode: bool = False,
) -> None:
    """Reject links and special files before any tree is read, copied, or run."""

    if root.is_symlink() or not root.is_dir():
        raise V4VerificationError(f"{label} tree is missing or unsafe: {root}")
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise V4VerificationError(f"{label} tree contains a symlink: {relative}")
        if reject_bytecode and (
            "__pycache__" in relative.parts
            or path.suffix in IGNORED_SUFFIXES
        ):
            raise V4VerificationError(
                f"{label} tree contains executable bytecode cache: {relative}"
            )
        if path.is_dir() or path.is_file():
            continue
        raise V4VerificationError(
            f"{label} tree contains a special file: {relative}"
        )


def _validate_learner_private_isolation(learner: Path) -> bool:
    """Reject author-only projections before learner code can be executed."""

    for path in sorted(learner.rglob("*")):
        relative = path.relative_to(learner)
        parts = tuple(part.casefold() for part in relative.parts)
        if not parts:
            continue
        private_root_file = (
            len(parts) == 1 and parts[0] in LEARNER_PRIVATE_ROOT_FILES
        )
        solution_projection = parts[0] == "solution"
        nested_hidden_tests = (
            parts[0] == "tests"
            and (
                "hidden" in parts[1:]
                or (
                    path.is_file()
                    and path.name.casefold().endswith("_hidden.py")
                )
            )
        )
        if private_root_file or solution_projection or nested_hidden_tests:
            raise V4VerificationError(
                f"learner tree contains private author material: {relative}"
            )
    return True


def _regular_files(
    root: Path,
    *,
    exclude_receipt: bool = False,
) -> Iterable[tuple[str, Path]]:
    _preflight_tree(root, label="course")
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        # Symlinks and special files were rejected for the entire tree before
        # ignored cache directories can hide them.
        if any(
            part in IGNORED_TREE_NAMES or part.endswith(".egg-info")
            for part in relative.parts
        ):
            continue
        if path.is_dir():
            continue
        if path.suffix in IGNORED_SUFFIXES:
            continue
        rendered = relative.as_posix()
        if rendered in MUTABLE_STATE_PATHS:
            continue
        if exclude_receipt and rendered == "verification.json":
            continue
        yield rendered, path


def tree_sha256(root: Path, *, exclude_receipt: bool = False) -> str:
    digest = hashlib.sha256()
    for relative, path in _regular_files(root, exclude_receipt=exclude_receipt):
        encoded = relative.encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _course_contract_digest(
    learner: Path,
    course_toml: Mapping[str, Any],
) -> str:
    quizzes: dict[str, str] = {}
    chapters = course_toml.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise V4VerificationError("course.toml has no chapters")
    seen: set[str] = set()
    for chapter in chapters:
        if not isinstance(chapter, dict) or not isinstance(chapter.get("id"), str):
            raise V4VerificationError("course.toml has an invalid chapter")
        chapter_id = str(chapter["id"])
        if (
            not chapter_id
            or chapter_id in {".", ".."}
            or "/" in chapter_id
            or "\\" in chapter_id
            or chapter_id in seen
        ):
            raise V4VerificationError("course.toml has an unsafe or duplicate chapter")
        seen.add(chapter_id)
        quiz_path = learner / "chapters" / chapter_id / "quiz.json"
        if quiz_path.is_symlink() or not quiz_path.is_file():
            raise V4VerificationError(
                f"{chapter_id} public quiz is missing or unsafe"
            )
        quizzes[chapter_id] = _sha256(quiz_path.read_bytes())
    payload = {
        "schema_version": 1,
        "course_schema_version": 4,
        "course_id": course_toml.get("course_id"),
        "curriculum_id": course_toml.get("curriculum_id"),
        "course_toml_sha256": _sha256((learner / "course.toml").read_bytes()),
        "public_quiz_sha256": dict(sorted(quizzes.items())),
    }
    return _sha256(_json_bytes(payload))


def _public_projection_from_toml(
    learner: Path,
    course_toml: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconstruct the exact learner runtime projection from bound TOML."""

    chapters = course_toml.get("chapters")
    sources = course_toml.get("sources")
    target = course_toml.get("target")
    if (
        not isinstance(chapters, list)
        or not chapters
        or not isinstance(sources, list)
        or not isinstance(target, dict)
    ):
        raise V4VerificationError("course.toml public metadata is invalid")

    source_by_id: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("id"), str):
            raise V4VerificationError("course.toml source is invalid")
        source_id = str(source["id"])
        if source_id in source_by_id:
            raise V4VerificationError("course.toml source IDs must be unique")
        source_by_id[source_id] = copy.deepcopy(source)

    projected_chapters: list[dict[str, Any]] = []
    seen_chapters: set[str] = set()
    total_points = 0
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise V4VerificationError("course.toml chapter is invalid")
        chapter_id = chapter.get("id")
        kind = chapter.get("kind")
        graded = chapter.get("graded")
        if (
            not isinstance(chapter_id, str)
            or not chapter_id
            or chapter_id in seen_chapters
            or chapter_id in {".", ".."}
            or "/" in chapter_id
            or "\\" in chapter_id
            or not isinstance(kind, str)
            or not isinstance(graded, bool)
        ):
            raise V4VerificationError("course.toml chapter identity is invalid")
        expected_graded = kind in GRADED_CHAPTER_KINDS
        if graded is not expected_graded:
            raise V4VerificationError(
                f"{chapter_id} graded flag does not match its chapter kind"
            )
        graded = expected_graded
        seen_chapters.add(chapter_id)

        source_ids = chapter.get("source_ids")
        tasks = chapter.get("tasks", [])
        if (
            not isinstance(source_ids, list)
            or not all(isinstance(item, str) for item in source_ids)
            or not isinstance(tasks, list)
        ):
            raise V4VerificationError(f"{chapter_id} public metadata is invalid")
        try:
            projected_sources = [
                copy.deepcopy(source_by_id[source_id]) for source_id in source_ids
            ]
        except KeyError as error:
            raise V4VerificationError(
                f"{chapter_id} references an unknown source"
            ) from error

        projected_tasks: list[dict[str, Any]] = []
        seen_tasks: set[str] = set()
        for task in tasks:
            if not isinstance(task, dict) or not isinstance(task.get("id"), str):
                raise V4VerificationError(f"{chapter_id} task is invalid")
            task_id = str(task["id"])
            public_tests = task.get("public_tests")
            if (
                not task_id
                or task_id in seen_tasks
                or not isinstance(public_tests, list)
                or not public_tests
                or not all(isinstance(item, str) and item for item in public_tests)
            ):
                raise V4VerificationError(f"{chapter_id} task contract is invalid")
            seen_tasks.add(task_id)
            try:
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
            except KeyError as error:
                raise V4VerificationError(
                    f"{chapter_id} task contract is incomplete"
                ) from error
            projected["tests"] = {"public": copy.deepcopy(public_tests)}
            example_keys = {
                key
                for key in ("example_input", "example_output", "example_explanation")
                if key in task
            }
            if example_keys:
                if example_keys != {
                    "example_input",
                    "example_output",
                    "example_explanation",
                }:
                    raise V4VerificationError(
                        f"{chapter_id} task example is incomplete"
                    )
                projected["example"] = {
                    "input": copy.deepcopy(task["example_input"]),
                    "output": copy.deepcopy(task["example_output"]),
                    "explanation": copy.deepcopy(task["example_explanation"]),
                }
            points = task.get("points")
            if isinstance(points, bool) or not isinstance(points, int):
                raise V4VerificationError(f"{chapter_id} task points are invalid")
            total_points += points
            projected_tasks.append(projected)

        study_minutes = {
            "min": chapter.get("study_min"),
            "max": chapter.get("study_max"),
        }
        if "study_reason" in chapter:
            study_minutes["reason"] = chapter["study_reason"]
        projected_chapters.append(
            {
                "id": chapter_id,
                "title": chapter.get("title"),
                "kind": kind,
                "unit_type": "coding" if graded else kind,
                "graded": graded,
                "depends_on": chapter.get("depends_on"),
                "study_minutes": study_minutes,
                "sources": projected_sources,
                "tasks": projected_tasks,
                "questions": copy.deepcopy(projected_tasks),
            }
        )

    quiz_hashes = {
        chapter_id: _sha256(
            (learner / "chapters" / chapter_id / "quiz.json").read_bytes()
        )
        for chapter_id in seen_chapters
    }
    contract_payload = {
        "schema_version": 1,
        "course_schema_version": 4,
        "course_id": course_toml.get("course_id"),
        "curriculum_id": course_toml.get("curriculum_id"),
        "course_toml_sha256": _sha256((learner / "course.toml").read_bytes()),
        "public_quiz_sha256": dict(sorted(quiz_hashes.items())),
    }
    contract_sha256 = _sha256(_json_bytes(contract_payload))
    projected_target = copy.deepcopy(target)
    projected_target["official_sources"] = copy.deepcopy(sources)
    return {
        **contract_payload,
        "course_contract_sha256": contract_sha256,
        "course_id": course_toml.get("course_id"),
        "curriculum_id": course_toml.get("curriculum_id"),
        "title": course_toml.get("title"),
        "description": course_toml.get("description"),
        "language": course_toml.get("language"),
        "python_requires": course_toml.get("python_requires"),
        "capstone": course_toml.get("capstone"),
        "target": projected_target,
        "chapters": projected_chapters,
        "labs": copy.deepcopy(projected_chapters),
        "total_points": total_points,
    }


def _validate_public_projection(
    learner: Path,
    course_toml: Mapping[str, Any],
    public: Mapping[str, Any],
) -> str:
    expected = _public_projection_from_toml(learner, course_toml)
    if dict(public) != expected:
        raise V4VerificationError(
            "runtime course public projection does not match course.toml"
        )
    return str(expected["course_contract_sha256"])


def _tasks(course_toml: Mapping[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for chapter in course_toml["chapters"]:
        raw = chapter.get("tasks", [])
        if not isinstance(raw, list):
            raise V4VerificationError(
                f"{chapter.get('id', 'chapter')} tasks must be an array"
            )
        for task in raw:
            if not isinstance(task, dict):
                raise V4VerificationError("task must be an object")
            tasks.append({"chapter_id": chapter["id"], **copy.deepcopy(task)})
    return tasks


def _private_tasks(author: Mapping[str, Any]) -> dict[tuple[str, str], list[str]]:
    result: dict[tuple[str, str], list[str]] = {}
    raw_tasks = author.get("tasks")
    if not isinstance(raw_tasks, list):
        raise V4VerificationError("author.json tasks must be an array")
    for task in raw_tasks:
        if not isinstance(task, dict):
            raise V4VerificationError("author.json task must be an object")
        key = (str(task.get("chapter_id")), str(task.get("task_id")))
        selectors = task.get("hidden_tests")
        if (
            key in result
            or not isinstance(selectors, list)
            or not selectors
            or not all(isinstance(item, str) and item for item in selectors)
        ):
            raise V4VerificationError("author.json contains an invalid private task")
        result[key] = [str(item) for item in selectors]
    return result


def _public_selector_groups(
    tasks: Iterable[Mapping[str, Any]],
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    owners: dict[str, str] = {}
    for task in tasks:
        public = task.get("public_tests")
        if (
            not isinstance(public, list)
            or not public
            or not all(isinstance(item, str) and item for item in public)
        ):
            raise V4VerificationError(
                f"task {task.get('id')} has no valid public selectors"
            )
        key = f"{task.get('chapter_id')}/{task.get('id')}"
        if key in groups:
            raise V4VerificationError(f"duplicate public task identity: {key}")
        selected = [str(item) for item in public]
        for selector in selected:
            previous = owners.get(selector)
            if previous is not None:
                raise V4VerificationError(
                    f"public selector is shared by {previous} and {key}"
                )
            owners[selector] = key
        groups[key] = selected
    return groups


def _hidden_selectors(
    tasks: Iterable[Mapping[str, Any]],
    private: Mapping[tuple[str, str], list[str]],
) -> list[str]:
    selectors: list[str] = []
    for task in tasks:
        key = (str(task["chapter_id"]), str(task.get("id")))
        selected = private.get(key)
        if selected is None:
            raise V4VerificationError(
                f"author projection has no hidden selectors for {key[1]}"
            )
        selectors.extend(selected)
    return list(dict.fromkeys(selectors))


def _run_pytest_batch(
    workspace: Path,
    selectors: list[str],
    *,
    expected: str,
    timeout_seconds: int,
    selector_groups: Mapping[str, list[str]] | None = None,
) -> dict[str, Any]:
    if not selectors:
        raise V4VerificationError(f"{expected} pytest batch has no selectors")
    if expected not in {"red", "green"}:
        raise V4VerificationError(f"unknown pytest expectation: {expected}")
    if expected == "red":
        grouped = [
            selector
            for group in (selector_groups or {}).values()
            for selector in group
        ]
        if not selector_groups or grouped != selectors:
            raise V4VerificationError(
                "red pytest batch must preserve task-to-selector groups"
            )
    elif selector_groups is not None:
        raise V4VerificationError(
            "green pytest batch does not accept starter selector groups"
        )
    if workspace.is_symlink() or not workspace.is_dir():
        raise V4VerificationError(
            f"{expected} pytest workspace is missing or unsafe"
        )
    root = workspace.resolve()
    canonical: list[str] = []
    for selector in selectors:
        raw_path, separator, node = selector.partition("::")
        relative = Path(raw_path)
        if (
            not separator
            or not node
            or not raw_path
            or "\\" in raw_path
            or relative.is_absolute()
            or ".." in relative.parts
        ):
            raise V4VerificationError(
                f"{expected} pytest selector is unsafe: {selector}"
            )
        candidate = workspace.joinpath(*relative.parts)
        current = workspace
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise V4VerificationError(
                    f"{expected} pytest selector uses a symlink: {selector}"
                )
        if not candidate.is_file():
            raise V4VerificationError(
                f"{expected} pytest selector is missing: {selector}"
            )
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError) as error:
            raise V4VerificationError(
                f"{expected} pytest selector escapes its workspace: {selector}"
            ) from error
        canonical.append(f"{resolved}::{node}")

    before = tree_sha256(workspace)
    try:
        result = _isolated_pytest_runner()(
            workspace,
            canonical,
            timeout_seconds=min(float(timeout_seconds), 90.0),
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise V4VerificationError(
            f"{expected} isolated pytest batch could not run: {error}"
        ) from error
    after = tree_sha256(workspace)
    if after != before:
        raise V4VerificationError(
            f"{expected} pytest batch modified its source workspace"
        )

    outcomes = dict(result.outcomes)
    collected = list(result.collected)
    if (
        not isinstance(outcomes, dict)
        or not isinstance(collected, list)
        or len(collected) < len(selectors)
        or not outcomes
        or result.evidence_valid is not True
        or result.timed_out is True
        or result.output_limited is True
    ):
        raise V4VerificationError(
            f"{expected} pytest batch did not collect every selector\n"
            + result.output[-4000:]
        )
    observed = {str(value) for value in outcomes.values()}
    task_outcomes: dict[str, list[str]] | None = None
    if expected == "red":
        parent_indices: dict[Path, int] = {}
        selector_outcomes: dict[str, list[str]] = {}
        for selector, canonical_selector in zip(selectors, canonical, strict=True):
            source_text, _, node = canonical_selector.partition("::")
            source = Path(source_text)
            if source.parent not in parent_indices:
                parent_indices[source.parent] = len(parent_indices)
            projected = (
                "canonical-tests/"
                f"{parent_indices[source.parent]:04d}/"
                f"{source.name}::{node}"
            )
            matched = [
                str(outcome)
                for nodeid, outcome in outcomes.items()
                if str(nodeid) == projected
                or str(nodeid).startswith(projected + "[")
            ]
            if not matched:
                raise V4VerificationError(
                    f"red pytest batch lost selector evidence: {selector}"
                )
            selector_outcomes[selector] = matched

        task_outcomes = {}
        for task_key, task_selectors in (selector_groups or {}).items():
            task_observed = [
                outcome
                for selector in task_selectors
                for outcome in selector_outcomes[selector]
            ]
            if (
                not task_observed
                or any(
                    outcome not in {"passed", "failed"}
                    for outcome in task_observed
                )
                or "failed" not in task_observed
            ):
                raise V4VerificationError(
                    f"starter task {task_key} did not start RED"
                )
            task_outcomes[task_key] = sorted(set(task_observed))
        passed = (
            result.returncode not in {None, 0}
            and result.passed is False
            and observed <= {"passed", "failed"}
            and bool(task_outcomes)
        )
    else:
        passed = result.passed is True and observed == {"passed"}
    if not passed:
        raise V4VerificationError(
            f"{expected} pytest batch had outcomes {sorted(observed)} "
            f"and exit {result.returncode}\n"
            + result.output[-4000:]
        )
    evidence = {
        "selectors": len(selectors),
        "collected": sorted(str(nodeid) for nodeid in collected),
        "collected_count": len(collected),
        "outcomes": dict(sorted((str(key), str(value)) for key, value in outcomes.items())),
        "isolated": True,
        "batches": 1,
    }
    if task_outcomes is not None:
        evidence["task_outcomes"] = task_outcomes
    return evidence


def _solution_workspace(learner: Path, author: Path, destination: Path) -> Path:
    _preflight_tree(learner, label="learner", reject_bytecode=True)
    _preflight_tree(author, label="author", reject_bytecode=True)
    workspace = destination / "solution-workspace"
    shutil.copytree(
        learner,
        workspace,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            ".git",
            ".pytest_cache",
            ".venv",
            "__pycache__",
            "*.egg-info",
            "*.pyc",
        ),
    )
    solution = author / "solution" / "src"
    hidden = author / "tests" / "hidden"
    if solution.is_symlink() or not solution.is_dir():
        raise V4VerificationError("author solution/src is missing")
    if hidden.is_symlink() or not hidden.is_dir():
        raise V4VerificationError("author hidden tests are missing")
    shutil.copytree(
        solution,
        workspace / "src",
        dirs_exist_ok=True,
        symlinks=True,
    )
    shutil.copytree(
        hidden,
        workspace / "tests" / "hidden",
        symlinks=True,
    )
    _preflight_tree(
        workspace,
        label="solution workspace",
        reject_bytecode=True,
    )
    return workspace


def _example_inventory(workspace: Path) -> dict[str, Any]:
    examples = sorted((workspace / "examples").rglob("*.py")) if (
        workspace / "examples"
    ).is_dir() else []
    return {
        "count": len(examples),
        "executed": False,
        "required": False,
    }


@contextmanager
def _load_runner_module(
    learner: Path,
    author: Path,
    *,
    state_path: Path | None = None,
) -> Iterator[Any]:
    runtime_root = learner / "coursekit_runtime"
    _preflight_tree(runtime_root, label="candidate runtime", reject_bytecode=True)
    runner_path = runtime_root / "runner.py"
    init_path = runtime_root / "__init__.py"
    if runner_path.is_symlink() or not runner_path.is_file():
        raise V4VerificationError("schema-v4 Runner is missing")
    if init_path.is_symlink() or not init_path.is_file():
        raise V4VerificationError("schema-v4 runtime package is missing")
    previous = {name: os.environ.get(name) for name in COURSEKIT_ENVIRONMENT_NAMES}
    os.environ["COURSEKIT_LEARNER_ROOT"] = str(learner)
    os.environ["COURSEKIT_ROOT"] = str(learner)
    os.environ["COURSEKIT_COURSE_DIR"] = str(learner)
    os.environ["COURSEKIT_AUTHOR_ROOT"] = str(author)
    os.environ["COURSEKIT_STATE_PATH"] = str(
        state_path or learner / ".coursekit" / "acceptance-progress.json"
    )
    suffix = hashlib.sha256(
        str(learner).encode() + os.urandom(16)
    ).hexdigest()[:16]
    package_name = f"_coursekit_v4_runtime_{suffix}"
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        package_spec = importlib.util.spec_from_file_location(
            package_name,
            init_path,
            submodule_search_locations=[str(runtime_root)],
        )
        if package_spec is None or package_spec.loader is None:
            raise V4VerificationError("cannot import schema-v4 runtime package")
        package = importlib.util.module_from_spec(package_spec)
        sys.modules[package_name] = package
        package_spec.loader.exec_module(package)

        module_name = f"{package_name}.runner"
        runner_spec = importlib.util.spec_from_file_location(module_name, runner_path)
        if runner_spec is None or runner_spec.loader is None:
            raise V4VerificationError("cannot import schema-v4 Runner")
        module = importlib.util.module_from_spec(runner_spec)
        sys.modules[module_name] = module
        runner_spec.loader.exec_module(module)
        yield module
    finally:
        sys.dont_write_bytecode = previous_bytecode
        for name in tuple(sys.modules):
            if name == package_name or name.startswith(f"{package_name}."):
                sys.modules.pop(name, None)
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _api_flow(
    learner: Path,
    author: Path,
    course_toml: Mapping[str, Any],
    answers: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        from fastapi.testclient import TestClient
    except ImportError as error:  # pragma: no cover - setup contract
        raise V4VerificationError("FastAPI TestClient is unavailable") from error

    calls = 0
    navigation_checks = 0
    coding_smoke: dict[str, Any] | None = None
    with _load_runner_module(learner, author) as module:
        create_app = getattr(module, "create_app", None)
        app = create_app() if callable(create_app) else getattr(module, "app", None)
        update_state = getattr(module, "update_state", None)
        if app is None or not callable(update_state):
            raise V4VerificationError("schema-v4 Runner exposes no acceptance API")
        with TestClient(app) as client:
            health = client.get("/api/health")
            calls += 1
            if health.status_code != 200 or health.json().get("status") != "ok":
                raise V4VerificationError("Runner health endpoint failed")
            static = client.get("/")
            calls += 1
            if static.status_code != 200 or "<!doctype html" not in static.text.lower():
                raise V4VerificationError("Runner did not serve the static Web")
            unknown_api = client.get("/api/not-a-real-route")
            calls += 1
            if unknown_api.status_code != 404 or "application/json" not in (
                unknown_api.headers.get("content-type", "")
            ):
                raise V4VerificationError("unknown /api route did not return JSON 404")

            payload = client.get("/api/course")
            calls += 1
            if payload.status_code != 200:
                raise V4VerificationError("Runner course endpoint failed")
            chapters = list(course_toml["chapters"])
            finished: set[str] = set()

            def expected_unlocked() -> set[str]:
                return {
                    str(item["id"])
                    for item in chapters
                    if str(item["id"]) in finished
                    or item.get("depends_on") is None
                    or str(item.get("depends_on")) in finished
                }

            def assert_navigation_state(
                state: Mapping[str, Any],
                *,
                stage: str,
            ) -> None:
                nonlocal navigation_checks
                unlocked = state.get("unlocked_labs")
                if not isinstance(unlocked, list) or {
                    str(item) for item in unlocked
                } != expected_unlocked():
                    raise V4VerificationError(
                        f"navigation gate state is invalid {stage}"
                    )
                navigation_checks += 1

            assert_navigation_state(
                payload.json().get("state", {}),
                stage="before the first chapter",
            )

            for chapter in chapters:
                chapter_id = str(chapter["id"])
                state_response = client.get("/api/state")
                calls += 1
                if state_response.status_code != 200:
                    raise V4VerificationError(
                        f"navigation gate did not unlock {chapter_id}"
                    )
                assert_navigation_state(
                    state_response.json(),
                    stage=f"before {chapter_id}",
                )
                if chapter_id not in expected_unlocked():
                    raise V4VerificationError(
                        f"course.toml orders locked chapter {chapter_id}"
                    )

                content_response = client.get(f"/api/content/{chapter_id}")
                calls += 1
                if content_response.status_code != 200:
                    raise V4VerificationError(
                        f"content endpoint failed for {chapter_id}"
                    )
                content = content_response.json()
                expected_tutorial = (
                    learner / "chapters" / chapter_id / "tutorial.md"
                ).read_text(encoding="utf-8")
                if (
                    content.get("lesson") != expected_tutorial
                    or "lesson_outline" in content
                    or not isinstance(content.get("terms"), list)
                ):
                    raise V4VerificationError(
                        f"content projection is invalid for {chapter_id}"
                    )

                knowledge_response = client.get(f"/api/knowledge/{chapter_id}")
                calls += 1
                if knowledge_response.status_code != 200:
                    raise V4VerificationError(
                        f"knowledge endpoint failed for {chapter_id}"
                    )
                knowledge = knowledge_response.json()
                chapter_answers = answers.get("chapters", {}).get(chapter_id, {})
                for question in knowledge.get("questions", []):
                    question_id = str(question["id"])
                    answer_id = chapter_answers.get(question_id, {}).get("answer_id")
                    response = client.post(
                        "/api/knowledge/answer",
                        json={
                            "lab_id": chapter_id,
                            "question_id": question_id,
                            "choice_id": answer_id,
                        },
                    )
                    calls += 1
                    if (
                        response.status_code != 200
                        or response.json().get("correct") is not True
                    ):
                        raise V4VerificationError(
                            f"knowledge answer failed for {question_id}"
                        )

                tasks = chapter.get("tasks", [])
                if chapter.get("graded"):
                    if not isinstance(tasks, list) or not tasks:
                        raise V4VerificationError(
                            f"graded chapter {chapter_id} has no tasks"
                        )
                    if coding_smoke is None:
                        task = tasks[0]
                        task_id = str(task["id"])
                        file_response = client.get(
                            "/api/file",
                            params={
                                "lab_id": chapter_id,
                                "question_id": task_id,
                            },
                        )
                        calls += 1
                        if file_response.status_code != 200:
                            raise V4VerificationError(
                                f"file read failed for {task_id}"
                            )
                        saved = client.put(
                            "/api/file",
                            json={
                                "lab_id": chapter_id,
                                "question_id": task_id,
                                "content": file_response.json()["content"],
                            },
                        )
                        calls += 1
                        if saved.status_code != 200:
                            raise V4VerificationError(
                                f"file save failed for {task_id}"
                            )
                        for mode in ("public", "submit"):
                            result = client.post(
                                "/api/run",
                                json={
                                    "lab_id": chapter_id,
                                    "question_id": task_id,
                                    "mode": mode,
                                },
                            )
                            calls += 1
                            if (
                                result.status_code != 200
                                or result.json().get("passed") is not True
                            ):
                                raise V4VerificationError(
                                    f"{mode} run failed for {task_id}: "
                                    + result.text[-1000:]
                                )
                        coding_smoke = {
                            "chapter_id": chapter_id,
                            "task_id": task_id,
                            "runs": 2,
                        }

                    def mark_aggregate_verified(
                        value: dict[str, Any],
                        *,
                        current_chapter: Mapping[str, Any] = chapter,
                        current_id: str = chapter_id,
                    ) -> None:
                        chapter_grades = value.setdefault("grades", {}).setdefault(
                            current_id,
                            {},
                        )
                        for declared in current_chapter.get("tasks", []):
                            chapter_grades[str(declared["id"])] = {
                                "public": True,
                                "verified": True,
                            }
                        completed = value.setdefault("completed_labs", [])
                        if current_id not in completed:
                            completed.append(current_id)

                    update_state(mark_aggregate_verified)

                finished.add(chapter_id)
                advanced_state = client.get("/api/state")
                calls += 1
                if advanced_state.status_code != 200:
                    raise V4VerificationError(
                        f"navigation state failed after {chapter_id}"
                    )
                assert_navigation_state(
                    advanced_state.json(),
                    stage=f"after {chapter_id}",
                )

            final_state = client.get("/api/state")
            calls += 1
            if final_state.status_code != 200:
                raise V4VerificationError("final progress endpoint failed")
            state = final_state.json()
            completed = set(state.get("completed_labs", []))
            expected_graded = {
                str(chapter["id"]) for chapter in chapters if chapter.get("graded")
            }
            mastered = state.get("knowledge", {})
            if (
                coding_smoke is None
                or not expected_graded <= completed
                or any(
                    not mastered.get(str(chapter["id"]))
                    or not all(mastered[str(chapter["id"])].values())
                    for chapter in chapters
                )
            ):
                raise V4VerificationError(
                    "three-gate flow did not complete every chapter"
                )
    return {
        "passed": True,
        "requests": calls,
        "chapters": len(course_toml["chapters"]),
        "coding_smoke": coding_smoke,
        "navigation_checks": navigation_checks,
    }


def _file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise V4VerificationError(f"verification input is missing: {path}")
    return _sha256(path.read_bytes())


def _verifier_sha256() -> str:
    engine = {
        "schema_version": 1,
        "files": [
            {
                "path": "scripts/verify_v4_course.py",
                "sha256": _file_sha256(Path(__file__).resolve()),
            },
            {
                "path": "coursekit_runtime/execution.py",
                "sha256": _file_sha256(TRUSTED_EXECUTION),
            },
            {
                "path": "coursekit_runtime/pytest_bootstrap.py",
                "sha256": _file_sha256(TRUSTED_BOOTSTRAP),
            },
        ],
    }
    return _sha256(_json_bytes(engine))


def _expected_runtime_sha256(language: str) -> str:
    _preflight_tree(TRUSTED_RUNTIME_ROOT, label="trusted runtime")
    digest = hashlib.sha256()
    for path in sorted(TRUSTED_RUNTIME_ROOT.rglob("*")):
        relative = path.relative_to(TRUSTED_RUNTIME_ROOT)
        if any(part in IGNORED_TREE_NAMES for part in relative.parts):
            continue
        if path.is_dir() or path.suffix in IGNORED_SUFFIXES:
            continue
        payload = path.read_bytes()
        if path.suffix in RUNTIME_TEXT_SUFFIXES:
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError as error:
                raise V4VerificationError(
                    f"trusted runtime text asset is invalid: {relative}"
                ) from error
            payload = text.replace("__COURSEKIT_LANGUAGE__", language).encode(
                "utf-8"
            )
        encoded = relative.as_posix().encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _validate_generation_contract(
    learner: Path,
    course_toml: Mapping[str, Any],
    contract_sha256: str,
) -> None:
    generation = _load_json(
        learner / ".coursekit" / "generation.json",
        "generation metadata",
    )
    try:
        current_runtime_contract = v4_runtime_contract_sha256()
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise V4VerificationError(
            "current schema-v4 runtime contract is unavailable"
        ) from error
    if (
        generation.get("schema_version") != 1
        or generation.get("course_schema_version") != 4
        or generation.get("course_id") != course_toml.get("course_id")
        or generation.get("curriculum_id") != course_toml.get("curriculum_id")
        or generation.get("course_contract_sha256") != contract_sha256
        or generation.get("runtime_contract_sha256") != current_runtime_contract
    ):
        raise V4VerificationError(
            "generation metadata does not match the current runtime contract"
        )
    language = course_toml.get("language")
    if not isinstance(language, str):
        raise V4VerificationError("course.toml language is invalid")
    actual_runtime = tree_sha256(learner / "coursekit_runtime")
    expected_runtime = _expected_runtime_sha256(language)
    if actual_runtime != expected_runtime:
        raise V4VerificationError(
            "candidate runtime does not match the current trusted projection"
        )


def _resolved_root(
    value: Path | str,
    *,
    label: str,
    reject_bytecode: bool = False,
) -> Path:
    raw = Path(value).absolute()
    if raw.is_symlink() or not raw.is_dir():
        raise V4VerificationError(f"{label} root is missing or unsafe: {raw}")
    resolved = raw.resolve()
    _preflight_tree(
        resolved,
        label=label,
        reject_bytecode=reject_bytecode,
    )
    return resolved


def verify_v4_course(
    project: Path | str,
    *,
    author_root: Path | str | None = None,
) -> dict[str, Any]:
    learner = _resolved_root(
        project,
        label="learner",
        reject_bytecode=True,
    )
    author = (
        _resolved_root(
            author_root,
            label="author",
            reject_bytecode=True,
        )
        if author_root is not None
        else _resolved_root(
            learner.with_name(f"{learner.name}-author"),
            label="author",
            reject_bytecode=True,
        )
    )
    learner_private_isolation = _validate_learner_private_isolation(learner)
    try:
        course_toml = tomllib.loads((learner / "course.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise V4VerificationError(f"course.toml is invalid: {error}") from error
    if course_toml.get("schema_version") != 4:
        raise V4VerificationError("course.toml schema_version must be 4")

    course = _load_json(learner / ".coursekit" / "course.json", "runtime course")
    author_binding = _load_json(author / "author.json", "author binding")
    answers = _load_json(author / "quiz-answers.json", "quiz answers")
    contract_sha256 = _validate_public_projection(
        learner,
        course_toml,
        course,
    )
    _validate_generation_contract(learner, course_toml, contract_sha256)
    for label, value in (
        ("runtime course", course),
        ("author binding", author_binding),
    ):
        if (
            value.get("course_id") != course_toml.get("course_id")
            or value.get("curriculum_id") != course_toml.get("curriculum_id")
            or value.get("course_contract_sha256") != contract_sha256
        ):
            raise V4VerificationError(f"{label} does not match the course contract")

    tasks = _tasks(course_toml)
    if not tasks:
        raise V4VerificationError("schema-v4 course has no graded tasks")
    private = _private_tasks(author_binding)
    public_groups = _public_selector_groups(tasks)
    public = [
        selector
        for group in public_groups.values()
        for selector in group
    ]
    hidden = _hidden_selectors(tasks, private)
    timeout = min(
        300,
        max(30, sum(int(task.get("timeout_seconds", 30)) for task in tasks)),
    )
    starter_evidence = _run_pytest_batch(
        learner,
        public,
        expected="red",
        timeout_seconds=timeout,
        selector_groups=public_groups,
    )

    with tempfile.TemporaryDirectory(prefix=".coursekit-v4-acceptance-") as raw:
        solution = _solution_workspace(learner, author, Path(raw))
        solution_evidence = _run_pytest_batch(
            solution,
            [*public, *hidden],
            expected="green",
            timeout_seconds=timeout,
        )
        examples = _example_inventory(solution)
        api_flow = _api_flow(
            solution,
            author,
            course_toml,
            answers,
        )

    checks = {
        "starter_red": starter_evidence,
        "solution_green": solution_evidence,
        "examples": examples,
        "api_flow": api_flow,
        "learner_private_isolation": learner_private_isolation,
        "node_install": False,
    }
    receipt_base = {
        "schema_version": 1,
        "course_schema_version": 4,
        "profile": "course-acceptance-v1",
        "passed": True,
        "course_id": course_toml["course_id"],
        "curriculum_id": course_toml["curriculum_id"],
        "course_contract_sha256": contract_sha256,
        "learner_tree_sha256": tree_sha256(learner),
        "author_tree_sha256": tree_sha256(author, exclude_receipt=True),
        "runtime_sha256": tree_sha256(learner / "coursekit_runtime"),
        "verifier_sha256": _verifier_sha256(),
        "checks": checks,
    }
    receipt = {
        **receipt_base,
        "receipt_sha256": _sha256(_json_bytes(receipt_base)),
    }
    (author / "verification.json").write_bytes(_json_bytes(receipt))
    return receipt


def validate_v4_receipt(
    project: Path | str,
    *,
    author_root: Path | str | None = None,
) -> dict[str, Any]:
    """Recompute receipt bindings without executing tests or starting Runner."""

    learner = _resolved_root(
        project,
        label="learner",
        reject_bytecode=True,
    )
    author = (
        _resolved_root(
            author_root,
            label="author",
            reject_bytecode=True,
        )
        if author_root is not None
        else _resolved_root(
            learner.with_name(f"{learner.name}-author"),
            label="author",
            reject_bytecode=True,
        )
    )
    _validate_learner_private_isolation(learner)
    receipt = _load_json(author / "verification.json", "verification receipt")
    required = {
        "schema_version",
        "course_schema_version",
        "profile",
        "passed",
        "course_id",
        "curriculum_id",
        "course_contract_sha256",
        "learner_tree_sha256",
        "author_tree_sha256",
        "runtime_sha256",
        "verifier_sha256",
        "checks",
        "receipt_sha256",
    }
    if set(receipt) != required:
        raise V4VerificationError("verification receipt has an invalid shape")
    if (
        receipt["schema_version"] != 1
        or receipt["course_schema_version"] != 4
        or receipt["profile"] != "course-acceptance-v1"
        or receipt["passed"] is not True
    ):
        raise V4VerificationError("verification receipt is not a passed v4 acceptance")
    try:
        course_toml = tomllib.loads(
            (learner / "course.toml").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise V4VerificationError(f"course.toml is invalid: {error}") from error
    if course_toml.get("schema_version") != 4:
        raise V4VerificationError("course.toml schema_version must be 4")
    public = _load_json(learner / ".coursekit/course.json", "runtime course")
    contract_sha256 = _validate_public_projection(
        learner,
        course_toml,
        public,
    )
    _validate_generation_contract(learner, course_toml, contract_sha256)
    expected = {
        "course_id": course_toml.get("course_id"),
        "curriculum_id": course_toml.get("curriculum_id"),
        "course_contract_sha256": contract_sha256,
        "learner_tree_sha256": tree_sha256(learner),
        "author_tree_sha256": tree_sha256(author, exclude_receipt=True),
        "runtime_sha256": tree_sha256(learner / "coursekit_runtime"),
        "verifier_sha256": _verifier_sha256(),
    }
    mismatches = [
        key for key, value in expected.items() if receipt.get(key) != value
    ]
    base = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt.get("receipt_sha256") != _sha256(_json_bytes(base)):
        mismatches.append("receipt_sha256")
    if mismatches:
        raise V4VerificationError(
            "verification receipt binding mismatch: "
            + ", ".join(sorted(set(mismatches)))
        )
    return receipt


__all__ = [
    "V4VerificationError",
    "tree_sha256",
    "validate_v4_receipt",
    "verify_v4_course",
]
