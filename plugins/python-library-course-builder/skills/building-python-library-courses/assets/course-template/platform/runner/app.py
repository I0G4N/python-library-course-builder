"""Manifest-driven local Runner for generated CourseKit projects."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Iterator, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from runner.execution import run_isolated_pytest
from support.coursekit.course import (
    find_unit as find_manifest_unit,
    formal_labs as manifest_formal_labs,
    foundation as manifest_foundation,
    is_preparatory_unit as manifest_is_preparatory_unit,
    ordered_units as manifest_ordered_units,
    preparatory_units as manifest_preparatory_units,
    schema_version as manifest_schema_version,
)
from support.coursekit.source_policy import preflight_question_source
from support.coursekit.locale import (
    CourseLanguageError,
    copy_for_manifest,
    localize_detail,
)


PLATFORM_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PLATFORM_ROOT.parent
COURSE_ROOT = Path(os.environ.get("COURSEKIT_COURSE_DIR", PLATFORM_ROOT / "course")).resolve()
WORKSPACE_ROOT = Path(os.environ.get("COURSEKIT_WORKSPACE_DIR", PROJECT_ROOT / "labs")).resolve()
MAX_FILE_BYTES = 1_000_000
_RUN_LOCK = threading.Lock()


class FileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: str
    question_id: str
    content: str = Field(max_length=MAX_FILE_BYTES)

    @field_validator("content")
    @classmethod
    def validate_utf8_size(cls, content: str) -> str:
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError(f"content exceeds {MAX_FILE_BYTES} UTF-8 bytes")
        return content


class RunRequest(BaseModel):
    lab_id: str
    question_id: str
    mode: Literal["public", "submit"] = "public"


class KnowledgeAnswer(BaseModel):
    lab_id: str
    question_id: str
    choice_id: str


class CodeFileLockedError(RuntimeError):
    """The learner has not completed the quizzes required for a code file."""


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def manifest(*, internal: bool = False) -> dict[str, Any]:
    path = COURSE_ROOT / "manifest.json" if internal else WORKSPACE_ROOT / "manifest.json"
    return load_json(path)


def state_path() -> Path:
    return WORKSPACE_ROOT / ".coursekit" / "state.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_head() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=WORKSPACE_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def initial_state() -> dict[str, Any]:
    current = manifest(internal=True)
    return {
        "version": 1,
        "course_id": current["course_id"],
        "curriculum_id": current["curriculum_id"],
        "knowledge": {},
        "grades": {},
        "completed_labs": [],
        "checkpoints": {},
        "git_baseline_commit": git_head(),
        "updated_at": None,
    }


def read_state() -> dict[str, Any]:
    fresh = initial_state()
    try:
        value = load_json(state_path())
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return fresh
    if value.get("course_id") != fresh["course_id"]:
        return fresh
    internal = manifest(internal=True)
    compatible = {fresh["curriculum_id"]}
    if manifest_schema_version(internal) < 3:
        compatible.update(internal.get("compatible_curriculum_ids", []))
    if value.get("curriculum_id") not in compatible:
        return fresh
    merged = dict(fresh)
    if manifest_schema_version(internal) < 3:
        merged.update(value)
    else:
        for key in (
            "knowledge",
            "grades",
            "completed_labs",
            "checkpoints",
            "git_baseline_commit",
            "updated_at",
        ):
            if key in value:
                merged[key] = value[key]
    merged["curriculum_id"] = fresh["curriculum_id"]
    return merged


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.with_suffix(path.suffix + ".lock").open("a+b")
    try:
        if os.name == "nt":  # pragma: no cover
            import msvcrt

            if handle.read(1) == b"":
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":  # pragma: no cover
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _write_state_unlocked(value: dict[str, Any]) -> dict[str, Any]:
    destination = state_path()
    value["updated_at"] = utc_now()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix="state-", suffix=".json", dir=destination.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return value


def write_state(value: dict[str, Any]) -> dict[str, Any]:
    destination = state_path()
    with _lock(destination):
        return _write_state_unlocked(value)


def update_state(mutation: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    destination = state_path()
    with _lock(destination):
        value = read_state()
        mutation(value)
        return _write_state_unlocked(value)


def learner_manifest() -> dict[str, Any]:
    value = manifest(internal=False)
    value.pop("reference_root", None)
    value.pop("reference_components", None)
    if manifest_schema_version(value) >= 3:
        value["labs"] = [
            *manifest_preparatory_units(value),
            *manifest_formal_labs(value),
        ]
    else:
        base = value.get("foundations")
        if isinstance(base, dict):
            value["labs"] = [base, *value.get("labs", [])]
    return value


def curriculum_lab(lab_id: str) -> dict[str, Any]:
    current = manifest(internal=True)
    unit = find_manifest_unit(lab_id, current)
    if isinstance(unit, dict):
        return unit
    raise LookupError(f"unknown Lab: {lab_id}")


def knowledge_lab(lab_id: str) -> dict[str, Any]:
    curriculum_lab(lab_id)
    try:
        lab = load_json(COURSE_ROOT / "knowledge.json")["labs"][lab_id]
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise LookupError(f"unknown Lab: {lab_id}") from error
    if not isinstance(lab, dict):
        raise LookupError(f"unknown Lab: {lab_id}")
    return lab


def knowledge_questions(lab_id: str) -> list[dict[str, Any]]:
    questions = knowledge_lab(lab_id).get("questions", [])
    if not isinstance(questions, list) or not all(
        isinstance(question, dict) for question in questions
    ):
        raise ValueError(f"invalid knowledge questions for {lab_id}")
    return questions


def knowledge_complete(lab_id: str, value: dict[str, Any]) -> bool:
    try:
        questions = knowledge_questions(lab_id)
    except (LookupError, ValueError):
        return False
    mastered = value.get("knowledge", {}).get(lab_id, {})
    return bool(questions) and all(
        mastered.get(str(item["id"])) is True for item in questions
    )


def is_preparatory_unit(lab_id: str) -> bool:
    current = manifest(internal=True)
    return (
        manifest_schema_version(current) >= 3
        and manifest_is_preparatory_unit(lab_id, current)
    )


def prerequisite(lab_id: str, current: dict[str, Any]) -> str | None:
    unit = find_manifest_unit(lab_id, current)
    if not isinstance(unit, dict):
        return None
    dependency = unit.get("depends_on")
    return str(dependency) if dependency is not None else None


def unit_complete(
    lab_id: str,
    value: dict[str, Any],
    current: dict[str, Any] | None = None,
) -> bool:
    course = current or manifest(internal=True)
    if find_manifest_unit(lab_id, course) is None:
        return False
    if manifest_is_preparatory_unit(lab_id, course):
        return knowledge_complete(lab_id, value)
    return lab_id in {str(item) for item in value.get("completed_labs", [])}


def navigable(
    lab_id: str,
    value: dict[str, Any],
    current: dict[str, Any] | None = None,
) -> bool:
    course = current or manifest(internal=True)
    if find_manifest_unit(lab_id, course) is None:
        return False
    base_id = str(manifest_foundation(course).get("id", "lab00"))
    if lab_id == base_id:
        return True
    if manifest_schema_version(course) >= 3:
        if unit_complete(lab_id, value, course):
            return True
        dependency = prerequisite(lab_id, course)
        return bool(dependency) and unit_complete(dependency, value, course)
    completed = {str(item) for item in value.get("completed_labs", [])}
    if lab_id in completed:
        return True
    dependency = prerequisite(lab_id, course)
    return dependency == base_id or dependency in completed


def knowledge_available(lab_id: str, value: dict[str, Any]) -> bool:
    lab = curriculum_lab(lab_id)
    current = manifest(internal=True)
    base_id = str(manifest_foundation(current).get("id", "lab00"))
    if lab_id == base_id:
        return True
    if manifest_schema_version(current) >= 3:
        return navigable(lab_id, value, current)
    if not knowledge_complete(base_id, value):
        return False
    dependency = str(lab.get("depends_on", base_id))
    completed = {str(item) for item in value.get("completed_labs", [])}
    return dependency == base_id or dependency in completed


def choice_payloads(question: dict[str, Any]) -> list[dict[str, str]]:
    configured = question.get("choices")
    if not isinstance(configured, list):
        raise ValueError("knowledge choices must be a list")
    choices: list[dict[str, str]] = []
    for index, choice in enumerate(configured):
        if isinstance(choice, str):
            choice_id, text = str(index), choice
        elif isinstance(choice, dict):
            choice_id = choice.get("id")
            text = choice.get("text")
            if not isinstance(choice_id, str) or not isinstance(text, str):
                raise ValueError("knowledge choice objects require text ids and labels")
        else:
            raise ValueError("knowledge choices must be strings or objects")
        choices.append({"id": choice_id, "text": text})
    if len({choice["id"] for choice in choices}) != len(choices):
        raise ValueError("knowledge choice ids must be unique")
    return choices


def correct_choice_id(question: dict[str, Any]) -> str:
    configured = question.get("choices")
    answer_id = question.get("answer_id")
    if isinstance(answer_id, str):
        return answer_id
    answer = question.get("answer")
    if isinstance(configured, list) and all(
        isinstance(choice, str) for choice in configured
    ):
        if isinstance(answer, bool) or not isinstance(answer, int):
            raise ValueError("knowledge answer must index string choices")
        return str(answer)
    if isinstance(answer, str):
        return answer
    raise ValueError("knowledge answer must identify an object choice")


def selected_choice_feedback(question: dict[str, Any], choice_id: str) -> str:
    configured = question.get("choices")
    if not isinstance(configured, list):
        raise ValueError("knowledge choices must be a list")
    for index, choice in enumerate(configured):
        if isinstance(choice, str) and str(index) == choice_id:
            return ""
        if isinstance(choice, dict) and choice.get("id") == choice_id:
            feedback = choice.get("feedback", "")
            if not isinstance(feedback, str):
                raise ValueError("knowledge choice feedback must be text")
            return feedback
    raise ValueError(f"invalid choice: {choice_id}")


def find_knowledge_question(
    lab_id: str, question_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    lab = knowledge_lab(lab_id)
    question = next(
        (
            item
            for item in knowledge_questions(lab_id)
            if str(item.get("id")) == question_id
        ),
        None,
    )
    if not isinstance(question, dict):
        raise LookupError(f"unknown knowledge question: {question_id}")
    return lab, question


def knowledge_view(lab_id: str, value: dict[str, Any]) -> dict[str, Any]:
    lab = knowledge_lab(lab_id)
    questions = knowledge_questions(lab_id)
    mastered = value.get("knowledge", {}).get(lab_id, {})
    exposed_questions = [
        {
            "id": str(question["id"]),
            **(
                {"kind": question["kind"]}
                if isinstance(question.get("kind"), str)
                else {}
            ),
            "prompt": str(question["prompt"]),
            "choices": choice_payloads(question),
            "mastered": mastered.get(str(question["id"])) is True,
        }
        for question in questions
    ]
    mastered_count = sum(int(question["mastered"]) for question in exposed_questions)
    total = len(exposed_questions)
    return {
        "lab_id": lab_id,
        "title": str(lab.get("title", curriculum_lab(lab_id).get("title", lab_id))),
        "available": knowledge_available(lab_id, value),
        "completed": bool(total) and mastered_count == total,
        "mastered": mastered_count,
        "total": total,
        "questions": exposed_questions,
    }


def exposed_state(value: dict[str, Any]) -> dict[str, Any]:
    current = manifest(internal=True)
    unlocked = [
        str(unit["id"])
        for unit in manifest_ordered_units(current)
        if navigable(str(unit["id"]), value, current)
    ]
    summary = score(value)
    exposed = {
        **value,
        "unlocked_labs": list(dict.fromkeys(unlocked)),
        "score": summary["verified"],
        "total_points": summary["total"],
    }
    if manifest_schema_version(current) >= 3:
        exposed["completed_preparatory_units"] = [
            str(unit["id"])
            for unit in manifest_preparatory_units(current)
            if unit_complete(str(unit["id"]), value, current)
        ]
    return exposed


def run_gate_reasons(lab_id: str, value: dict[str, Any]) -> list[str]:
    current = manifest(internal=True)
    if is_preparatory_unit(lab_id):
        return [f"{lab_id} is a knowledge-only preparatory unit"]
    base_id = str(manifest_foundation(current).get("id", "lab00"))
    reasons = []
    if lab_id not in set(exposed_state(value)["unlocked_labs"]):
        reasons.append(f"navigate to {lab_id} only after completing its dependency")
    if not knowledge_complete(base_id, value):
        reasons.append(f"master {base_id} knowledge first")
    if not knowledge_complete(lab_id, value):
        reasons.append(f"master {lab_id} knowledge first")
    return reasons


def find_content(lab_id: str) -> dict[str, Any]:
    content = load_json(COURSE_ROOT / "content.json")
    foundation = content.get("foundations")
    if isinstance(foundation, dict) and str(foundation.get("id")) == lab_id:
        return foundation
    for group in ("preparatory_units", "labs"):
        for lab in content.get(group, []):
            if isinstance(lab, dict) and str(lab.get("id")) == lab_id:
                return lab
    raise LookupError(f"unknown Lab: {lab_id}")


def safe_workspace_path(raw: str) -> tuple[str, ...]:
    """Validate a manifest path lexically without following filesystem links."""

    relative = Path(raw)
    if not raw or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("path must stay inside the learner workspace")
    parts = tuple(part for part in relative.parts if part not in {"", "."})
    if not parts:
        raise ValueError("coding question file must name a workspace file")
    return parts


def _workspace_open_error(error: OSError) -> None:
    if error.errno == errno.ENOENT:
        raise FileNotFoundError("workspace target does not exist") from error
    raise ValueError("workspace target must be a regular file without symlinks") from error


@contextmanager
def _posix_parent_fd(parts: tuple[str, ...]) -> Iterator[int]:
    """Open every parent through directory fds so link swaps cannot redirect I/O."""

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd: int | None = None
    try:
        try:
            current_fd = os.open(WORKSPACE_ROOT, directory_flags)
            for part in parts[:-1]:
                next_fd = os.open(part, directory_flags, dir_fd=current_fd)
                os.close(current_fd)
                current_fd = next_fd
        except OSError as error:
            _workspace_open_error(error)
        assert current_fd is not None
        yield current_fd
    finally:
        if current_fd is not None:
            os.close(current_fd)


def _open_posix_workspace_file(parts: tuple[str, ...], flags: int) -> int:
    with _posix_parent_fd(parts) as parent_fd:
        try:
            descriptor = os.open(
                parts[-1],
                flags | os.O_NONBLOCK | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
        except OSError as error:
            _workspace_open_error(error)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("workspace target must be a regular file")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _windows_workspace_path(parts: tuple[str, ...]) -> Path:  # pragma: no cover
    """Best-effort Windows fallback where dir_fd/O_NOFOLLOW are unavailable.

    Every component is checked with lstat and the resolved final target must
    remain below the configured workspace. POSIX uses the race-resistant fd
    implementation above; Python does not expose an equivalent portable
    Windows reparse-point API.
    """

    root = WORKSPACE_ROOT.resolve(strict=True)
    current = root
    for part in parts[:-1]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            raise
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("workspace path cannot traverse a symlink or non-directory")
    candidate = current / parts[-1]
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("workspace target must be a regular file without symlinks")
    try:
        candidate.resolve(strict=True).relative_to(root)
    except ValueError as error:
        raise ValueError("path escapes the learner workspace") from error
    return candidate


def read_workspace_text(parts: tuple[str, ...]) -> str:
    if os.name == "nt":  # pragma: no cover
        source = _windows_workspace_path(parts)
        if source.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("file is too large")
        data = source.read_bytes()
    else:
        descriptor = _open_posix_workspace_file(parts, os.O_RDONLY)
        try:
            if os.fstat(descriptor).st_size > MAX_FILE_BYTES:
                raise ValueError("file is too large")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(64 * 1024, MAX_FILE_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise ValueError("file is too large")
            data = b"".join(chunks)
        finally:
            os.close(descriptor)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("file is too large")
    return data.decode("utf-8")


def write_workspace_text(parts: tuple[str, ...], content: str) -> None:
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"content exceeds {MAX_FILE_BYTES} UTF-8 bytes")
    if os.name == "nt":  # pragma: no cover
        destination = _windows_workspace_path(parts)
        with destination.open("r+b") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("workspace target must be a regular file")
            handle.seek(0)
            handle.truncate()
            handle.write(data)
        return
    descriptor = _open_posix_workspace_file(parts, os.O_WRONLY)
    try:
        os.ftruncate(descriptor, 0)
        written = 0
        while written < len(data):
            count = os.write(descriptor, data[written:])
            if count <= 0:  # pragma: no cover - defensive OS contract guard
                raise OSError("workspace write made no progress")
            written += count
    finally:
        os.close(descriptor)


def question_workspace_path(
    lab_id: str,
    question_id: str,
    value: dict[str, Any],
) -> tuple[str, tuple[str, ...]]:
    """Resolve one trusted manifest question to its gated learner file."""

    if is_preparatory_unit(lab_id):
        raise CodeFileLockedError(
            f"{lab_id} is a knowledge-only preparatory unit"
        )
    _lab, question = find_question(manifest(internal=True), lab_id, question_id)
    reasons = run_gate_reasons(lab_id, value)
    if reasons:
        raise CodeFileLockedError(
            f"{lab_id} is locked: " + "; ".join(reasons)
        )
    raw = question.get("file")
    if not isinstance(raw, str) or not raw:
        raise ValueError("coding question file must be a non-empty path")
    return raw, safe_workspace_path(raw)


def find_question(course: dict[str, Any], lab_id: str, question_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    lab = next((item for item in course.get("labs", []) if item.get("id") == lab_id), None)
    if not isinstance(lab, dict):
        raise LookupError(f"unknown Lab: {lab_id}")
    question = next(
        (item for item in lab.get("questions", []) if item.get("id") == question_id),
        None,
    )
    if not isinstance(question, dict):
        raise LookupError(f"unknown coding question: {question_id}")
    return lab, question


def canonical_test_targets(root: Path, selectors: list[Any]) -> list[str]:
    """Resolve manifest selectors against one trusted teacher projection."""

    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("canonical test root must be a regular directory")
    resolved_base = base.resolve()
    targets: list[str] = []
    for value in selectors:
        if not isinstance(value, str):
            raise ValueError("canonical pytest selector must be text")
        path, separator, node = value.partition("::")
        relative = Path(path)
        if (
            not separator
            or not node
            or not path
            or "\\" in path
            or relative.is_absolute()
            or ".." in relative.parts
        ):
            raise ValueError(f"unsafe canonical pytest selector: {value}")

        candidate = base.joinpath(*relative.parts)
        current = base
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"canonical pytest target cannot use symlinks: {value}")
        try:
            resolved = candidate.resolve()
            resolved.relative_to(resolved_base)
        except (OSError, ValueError) as error:
            raise ValueError(f"canonical pytest target escapes its root: {value}") from error
        if not candidate.is_file():
            raise ValueError(f"canonical pytest target must be a regular file: {value}")
        targets.append(f"{resolved}::{node}")
    if not targets:
        raise ValueError("at least one canonical pytest selector is required")
    return targets


def run_tests(request: RunRequest) -> tuple[bool, bool, str]:
    internal = manifest(internal=True)
    copy = copy_for_manifest(internal)
    _, question = find_question(internal, request.lab_id, request.question_id)
    timeout_seconds = question.get("timeout_seconds", 30)
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 90
    ):
        raise ValueError("question timeout_seconds must be an integer from 1 to 90")
    deadline = time.monotonic() + timeout_seconds

    public_targets = canonical_test_targets(
        COURSE_ROOT / "starter", list(question["tests"]["public"])
    )
    public_remaining = deadline - time.monotonic()
    if public_remaining <= 0:
        return False, False, copy["public_timeout"]
    public_result = run_isolated_pytest(
        WORKSPACE_ROOT,
        public_targets,
        timeout_seconds=public_remaining,
    )
    if request.mode == "public" or not public_result.passed:
        return public_result.passed, public_result.passed, public_result.output

    try:
        hidden_targets = canonical_test_targets(
            COURSE_ROOT, list(question["tests"]["hidden"])
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return (
                False,
                True,
                copy["hidden_timeout"].format(count=len(hidden_targets)),
            )
        hidden_result = run_isolated_pytest(
            WORKSPACE_ROOT,
            hidden_targets,
            timeout_seconds=remaining,
        )
    except Exception:
        # Hidden selectors, paths, assertion text, and infrastructure details
        # are a privacy boundary. They may be logged by an operator, but never
        # returned through the learner-facing API.
        return (
            False,
            True,
            copy["hidden_unavailable"],
        )
    target_count = len(hidden_targets)
    result = copy["hidden_passed"] if hidden_result.passed else copy["hidden_failed"]
    output = copy["hidden_result"].format(
        result=result,
        count=target_count,
    )
    return hidden_result.passed, True, output


def preflight_request_source(request: RunRequest) -> None:
    """Apply the compiler-owned source policy before starting any pytest process."""

    _lab, question = find_question(
        manifest(internal=True), request.lab_id, request.question_id
    )
    preflight_question_source(
        WORKSPACE_ROOT,
        str(question.get("file", "")),
        question.get("source_policy"),
    )


def record_result(request: RunRequest, passed: bool, public_passed: bool) -> dict[str, Any]:
    internal_lab = next(
        item
        for item in manifest(internal=True)["labs"]
        if item["id"] == request.lab_id
    )

    def mutation(value: dict[str, Any]) -> None:
        grade = (
            value.setdefault("grades", {})
            .setdefault(request.lab_id, {})
            .setdefault(request.question_id, {})
        )
        grade["public"] = bool(public_passed)
        if request.mode == "submit":
            grade["verified"] = bool(passed)
            complete = all(
                value["grades"]
                .get(request.lab_id, {})
                .get(str(item["id"]), {})
                .get("verified")
                is True
                for item in internal_lab["questions"]
            )
            if complete and request.lab_id not in value["completed_labs"]:
                value["completed_labs"].append(request.lab_id)

    return update_state(mutation)


def score(value: dict[str, Any]) -> dict[str, int]:
    total = public = verified = 0
    for lab in manifest(internal=True)["labs"]:
        for question in lab["questions"]:
            points = int(question.get("points", 1))
            total += points
            grade = value.get("grades", {}).get(str(lab["id"]), {}).get(str(question["id"]), {})
            public += points if grade.get("public") else 0
            verified += points if grade.get("verified") else 0
    return {"public": public, "verified": verified, "total": total}


def create_app() -> FastAPI:
    title = "CourseKit Local Runner"
    try:
        current_manifest = manifest(internal=True)
        copy = copy_for_manifest(current_manifest)
        title = f"{current_manifest['title']} {copy['local_runner']}"
    except (OSError, ValueError, KeyError, json.JSONDecodeError, CourseLanguageError):
        pass
    app = FastAPI(title=title)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
        allow_methods=["GET", "PUT", "POST"],
        allow_headers=["content-type"],
    )

    @app.middleware("http")
    async def require_supported_course_language(
        request: Any, call_next: Callable[[Any], Any]
    ) -> Any:
        if request.url.path != "/api/health":
            try:
                copy_for_manifest(manifest(internal=True))
            except CourseLanguageError as error:
                return JSONResponse(
                    status_code=500,
                    content={"detail": str(error)},
                )
        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def localized_http_error(_request: Any, error: HTTPException) -> JSONResponse:
        try:
            copy = copy_for_manifest(manifest(internal=True))
            detail = localize_detail(error.detail, copy)
            status_code = error.status_code
        except CourseLanguageError as language_error:
            detail = str(language_error)
            status_code = 500
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers=error.headers,
        )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/course")
    def course() -> dict[str, Any]:
        learner = learner_manifest()
        copy_for_manifest(learner)
        return {"manifest": learner, "state": exposed_state(read_state())}

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return exposed_state(read_state())

    @app.post("/api/knowledge/answer")
    def answer_knowledge(request: KnowledgeAnswer) -> dict[str, Any]:
        try:
            _lab, question = find_knowledge_question(
                request.lab_id, request.question_id
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        current_state = read_state()
        if not knowledge_available(request.lab_id, current_state):
            raise HTTPException(
                status_code=409,
                detail=f"{request.lab_id} knowledge is not available yet",
            )
        try:
            choices = choice_payloads(question)
            if request.choice_id not in {choice["id"] for choice in choices}:
                raise ValueError(f"invalid choice: {request.choice_id}")
            correct = request.choice_id == correct_choice_id(question)
            feedback = selected_choice_feedback(question, request.choice_id)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if correct:
            def mutation(value: dict[str, Any]) -> None:
                value.setdefault("knowledge", {}).setdefault(request.lab_id, {})[
                    request.question_id
                ] = True

            current_state = update_state(mutation)
        return {
            "correct": correct,
            "feedback": feedback,
            "explanation": str(question.get("explanation", "")),
            "knowledge": knowledge_view(request.lab_id, current_state),
            "state": exposed_state(current_state),
        }

    @app.get("/api/knowledge/{lab_id}")
    def get_knowledge(lab_id: str) -> dict[str, Any]:
        try:
            return knowledge_view(lab_id, read_state())
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/content/{lab_id}")
    def content(lab_id: str) -> dict[str, Any]:
        try:
            return find_content(lab_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/file")
    def read_file(lab_id: str, question_id: str) -> dict[str, str]:
        try:
            path, source_parts = question_workspace_path(
                lab_id,
                question_id,
                read_state(),
            )
            return {"path": path, "content": read_workspace_text(source_parts)}
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except CodeFileLockedError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="file not found") from error
        except (OSError, UnicodeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.put("/api/file")
    def write_file(request: FileWrite) -> dict[str, str]:
        try:
            path, destination_parts = question_workspace_path(
                request.lab_id,
                request.question_id,
                read_state(),
            )
            write_workspace_text(destination_parts, request.content)
            return {"path": path, "status": "saved"}
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except CodeFileLockedError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="file not found") from error
        except (OSError, UnicodeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/run")
    def run(request: RunRequest) -> dict[str, Any]:
        if not _RUN_LOCK.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="Runner is busy with another grading request; try again shortly",
            )
        try:
            current_manifest = manifest(internal=True)
            if is_preparatory_unit(request.lab_id):
                raise HTTPException(
                    status_code=409,
                    detail=f"{request.lab_id} is a knowledge-only preparatory unit",
                )
            try:
                find_question(
                    current_manifest, request.lab_id, request.question_id
                )
            except LookupError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            except (KeyError, ValueError) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            current_state = read_state()
            reasons = run_gate_reasons(request.lab_id, current_state)
            if reasons:
                raise HTTPException(
                    status_code=409,
                    detail=f"{request.lab_id} is locked: " + "; ".join(reasons),
                )
            try:
                preflight_request_source(request)
                passed, public_passed, output = run_tests(request)
                value = record_result(request, passed, public_passed)
            except (KeyError, LookupError, ValueError) as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            return {
                "passed": passed,
                "output": output,
                "score": score(value)["verified"],
                "score_summary": score(value),
                "state": exposed_state(value),
            }
        finally:
            _RUN_LOCK.release()

    return app


app = create_app()
