"""Single-port Web and grading runtime for schema-v4 CourseKit courses."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
import tomllib
from typing import Any, Callable, Iterator, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

try:  # Package import in tests and installed projects.
    from .execution import run_isolated_pytest
except ImportError:  # Direct ``python coursekit_runtime/runner.py`` execution.
    from execution import run_isolated_pytest


RUNTIME_ROOT = Path(__file__).resolve().parent
_DEFAULT_LEARNER_ROOT = RUNTIME_ROOT.parent
LEARNER_ROOT = Path(
    os.environ.get(
        "COURSEKIT_LEARNER_ROOT",
        os.environ.get(
            "COURSEKIT_ROOT",
            os.environ.get("COURSEKIT_COURSE_DIR", str(_DEFAULT_LEARNER_ROOT)),
        ),
    )
).absolute()
AUTHOR_ROOT = Path(
    os.environ.get(
        "COURSEKIT_AUTHOR_ROOT",
        str(LEARNER_ROOT.with_name(f"{LEARNER_ROOT.name}-author")),
    )
).absolute()
STATIC_ROOT = RUNTIME_ROOT / "static"
STATE_PATH_OVERRIDE = (
    Path(os.environ["COURSEKIT_STATE_PATH"]).absolute()
    if os.environ.get("COURSEKIT_STATE_PATH")
    else None
)

MAX_FILE_BYTES = 1_000_000
MAX_METADATA_BYTES = 4_000_000
_RUN_LOCK = threading.Lock()
_STATE_THREAD_LOCK = threading.RLock()


class CourseRuntimeError(RuntimeError):
    """A generated-course trust or runtime invariant failed."""


class AuthorPackageError(CourseRuntimeError):
    """The private sibling package is absent or does not bind to this course."""


class CodeFileLockedError(CourseRuntimeError):
    """The learner has not passed the navigation and knowledge gates."""


class CourseSPAStaticFiles(StaticFiles):
    """Serve static assets and fall back to the SPA shell for deep links."""

    async def get_response(self, path: str, scope: dict[str, Any]) -> Any:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            request_path = str(scope.get("path", ""))
            if (
                error.status_code != 404
                or request_path == "/api"
                or request_path.startswith("/api/")
            ):
                raise
            return await super().get_response("index.html", scope)


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
    model_config = ConfigDict(extra="forbid")

    lab_id: str
    question_id: str
    mode: Literal["public", "submit"] = "public"


class KnowledgeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_id: str
    question_id: str
    choice_id: str


def _regular_root(root: Path, label: str) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise CourseRuntimeError(f"{label} must be a regular directory")
    return root.resolve()


def _safe_parts(raw: str, label: str = "path") -> tuple[str, ...]:
    relative = Path(raw)
    if (
        not raw
        or "\\" in raw
        or relative.is_absolute()
        or ".." in relative.parts
    ):
        raise ValueError(f"{label} must stay inside its root")
    parts = tuple(part for part in relative.parts if part not in {"", "."})
    if not parts:
        raise ValueError(f"{label} must name a file")
    return parts


def _regular_file(root: Path, raw: str, *, label: str) -> Path:
    base = _regular_root(root, f"{label} root")
    parts = _safe_parts(raw, label)
    current = base
    for part in parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError as error:
            raise FileNotFoundError(f"{label} does not exist") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{label} cannot traverse a symlink")
    if not stat.S_ISREG(current.lstat().st_mode):
        raise ValueError(f"{label} must be a regular file")
    try:
        current.resolve(strict=True).relative_to(base)
    except ValueError as error:
        raise ValueError(f"{label} escapes its root") from error
    return current


def _read_bytes(
    root: Path,
    raw: str,
    *,
    label: str,
    limit: int = MAX_METADATA_BYTES,
) -> bytes:
    source = _regular_file(root, raw, label=label)
    if source.stat().st_size > limit:
        raise ValueError(f"{label} is too large")
    value = source.read_bytes()
    if len(value) > limit:
        raise ValueError(f"{label} is too large")
    return value


def _read_json(
    root: Path,
    raw: str,
    *,
    label: str,
) -> dict[str, Any]:
    try:
        value: Any = json.loads(_read_bytes(root, raw, label=label))
    except json.JSONDecodeError as error:
        raise CourseRuntimeError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CourseRuntimeError(f"{label} must contain a JSON object")
    return value


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _public_binding() -> dict[str, Any]:
    binding = _read_json(
        LEARNER_ROOT,
        ".coursekit/course.json",
        label="public course binding",
    )
    required = {
        "schema_version",
        "course_schema_version",
        "course_id",
        "curriculum_id",
        "course_toml_sha256",
        "public_quiz_sha256",
        "course_contract_sha256",
    }
    if not required.issubset(binding):
        raise CourseRuntimeError("public course binding is incomplete")
    if binding["schema_version"] != 1 or binding["course_schema_version"] != 4:
        raise CourseRuntimeError("unsupported public course binding")
    if not all(
        isinstance(binding[key], str) and binding[key]
        for key in (
            "course_id",
            "curriculum_id",
            "course_toml_sha256",
            "course_contract_sha256",
        )
    ):
        raise CourseRuntimeError("public course binding identities are invalid")
    quiz_hashes = binding["public_quiz_sha256"]
    if not isinstance(quiz_hashes, dict) or not all(
        isinstance(key, str)
        and key
        and isinstance(value, str)
        and value
        for key, value in quiz_hashes.items()
    ):
        raise CourseRuntimeError("public quiz bindings are invalid")

    course_toml = _read_bytes(
        LEARNER_ROOT,
        "course.toml",
        label="course.toml",
    )
    if _sha256(course_toml) != binding["course_toml_sha256"]:
        raise CourseRuntimeError("course.toml does not match its public binding")
    for chapter_id, expected in quiz_hashes.items():
        quiz = _read_bytes(
            LEARNER_ROOT,
            f"chapters/{chapter_id}/quiz.json",
            label=f"{chapter_id} public quiz",
        )
        if _sha256(quiz) != expected:
            raise CourseRuntimeError(
                f"{chapter_id} public quiz does not match its binding"
            )
    contract_payload = {
        "schema_version": binding["schema_version"],
        "course_schema_version": binding["course_schema_version"],
        "course_id": binding["course_id"],
        "curriculum_id": binding["curriculum_id"],
        "course_toml_sha256": binding["course_toml_sha256"],
        "public_quiz_sha256": binding["public_quiz_sha256"],
    }
    if (
        _sha256(_canonical_json_bytes(contract_payload))
        != binding["course_contract_sha256"]
    ):
        raise CourseRuntimeError("public course contract digest is invalid")
    return binding


def manifest() -> dict[str, Any]:
    """Load the public course manifest and verify its immutable bindings."""

    binding = _public_binding()
    try:
        value: Any = tomllib.loads(
            _read_bytes(
                LEARNER_ROOT,
                "course.toml",
                label="course.toml",
            ).decode("utf-8")
        )
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CourseRuntimeError("course.toml is not valid UTF-8 TOML") from error
    if not isinstance(value, dict) or value.get("schema_version") != 4:
        raise CourseRuntimeError("course.toml must use schema version 4")
    if (
        value.get("course_id") != binding["course_id"]
        or value.get("curriculum_id") != binding["curriculum_id"]
    ):
        raise CourseRuntimeError("course.toml identity does not match its binding")
    chapters = value.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise CourseRuntimeError("course.toml must declare chapters")
    seen: set[str] = set()
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise CourseRuntimeError("course.toml chapter entries must be tables")
        chapter_id = chapter.get("id")
        if not isinstance(chapter_id, str) or not chapter_id or chapter_id in seen:
            raise CourseRuntimeError("course.toml chapter IDs must be unique text")
        seen.add(chapter_id)
        if chapter_id not in binding["public_quiz_sha256"]:
            raise CourseRuntimeError(f"{chapter_id} has no bound public quiz")
        tasks = chapter.get("tasks", [])
        if not isinstance(tasks, list):
            raise CourseRuntimeError(f"{chapter_id} tasks must be an array")
    if set(binding["public_quiz_sha256"]) != seen:
        raise CourseRuntimeError("public quiz bindings do not match course chapters")
    return value


def _author_package() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load private task selectors and quiz answers after binding verification."""

    try:
        public = _public_binding()
        author = _read_json(AUTHOR_ROOT, "author.json", label="author binding")
        answers = _read_json(
            AUTHOR_ROOT,
            "quiz-answers.json",
            label="quiz answers",
        )
        expected = (
            public["course_id"],
            public["curriculum_id"],
            public["course_contract_sha256"],
        )
        actual = (
            author.get("course_id"),
            author.get("curriculum_id"),
            author.get("course_contract_sha256"),
        )
        if (
            author.get("schema_version") != 1
            or author.get("course_schema_version") != 4
            or actual != expected
            or not isinstance(author.get("tasks"), list)
            or answers.get("schema_version") != 1
            or answers.get("course_id") != public["course_id"]
            or not isinstance(answers.get("chapters"), dict)
        ):
            raise ValueError("binding mismatch")
        return author, answers
    except (
        CourseRuntimeError,
        FileNotFoundError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise AuthorPackageError(
            "author package is unavailable or does not match this course"
        ) from error


def _chapter(chapter_id: str, course: dict[str, Any] | None = None) -> dict[str, Any]:
    current = course or manifest()
    value = next(
        (
            item
            for item in current["chapters"]
            if isinstance(item, dict) and item.get("id") == chapter_id
        ),
        None,
    )
    if not isinstance(value, dict):
        raise LookupError(f"unknown chapter: {chapter_id}")
    return value


def _task(
    chapter_id: str,
    task_id: str,
    course: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    chapter = _chapter(chapter_id, course)
    value = next(
        (
            item
            for item in chapter.get("tasks", [])
            if isinstance(item, dict) and item.get("id") == task_id
        ),
        None,
    )
    if not isinstance(value, dict):
        raise LookupError(f"unknown coding question: {task_id}")
    return chapter, value


def _public_quiz(chapter_id: str) -> dict[str, Any]:
    _chapter(chapter_id)
    value = _read_json(
        LEARNER_ROOT,
        f"chapters/{chapter_id}/quiz.json",
        label=f"{chapter_id} public quiz",
    )
    questions = value.get("questions")
    if not isinstance(questions, list) or not all(
        isinstance(question, dict) for question in questions
    ):
        raise CourseRuntimeError(f"{chapter_id} public quiz is invalid")
    return value


def _quiz_question(
    chapter_id: str,
    question_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    quiz = _public_quiz(chapter_id)
    question = next(
        (
            item
            for item in quiz["questions"]
            if str(item.get("id")) == question_id
        ),
        None,
    )
    if not isinstance(question, dict):
        raise LookupError(f"unknown knowledge question: {question_id}")
    return quiz, question


def _state_path() -> Path:
    return STATE_PATH_OVERRIDE or LEARNER_ROOT / ".coursekit" / "state.json"


def _state_directory() -> Path:
    root = _regular_root(LEARNER_ROOT, "learner root")
    raw_destination = _state_path().absolute()
    destination = raw_destination.parent.resolve() / raw_destination.name
    try:
        relative = destination.relative_to(root)
    except ValueError as error:
        raise CourseRuntimeError("state path must stay inside the learner root") from error
    if (
        len(relative.parts) != 2
        or relative.parts[0] != ".coursekit"
        or relative.parts[1] in {"", ".", ".."}
    ):
        raise CourseRuntimeError("state path must name one file inside .coursekit")
    directory = destination.parent
    if directory.exists():
        metadata = directory.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise CourseRuntimeError(".coursekit must be a regular directory")
    else:
        directory.mkdir(mode=0o700)
    return directory


def _initial_state() -> dict[str, Any]:
    binding = _public_binding()
    return {
        "version": 1,
        "course_id": binding["course_id"],
        "curriculum_id": binding["curriculum_id"],
        "course_contract_sha256": binding["course_contract_sha256"],
        "knowledge": {},
        "grades": {},
        "completed_labs": [],
        "checkpoints": {},
        "updated_at": None,
    }


@contextmanager
def _state_file_lock() -> Iterator[None]:
    directory = _state_directory()
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        lock_path = _state_path().with_name(_state_path().name + ".lock")
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise CourseRuntimeError(
            "state lock must be a regular file without symlinks"
        ) from error
    handle = os.fdopen(descriptor, "a+b")
    try:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise CourseRuntimeError("state lock must be a regular file")
        if os.name == "nt":  # pragma: no cover - shared runtime CI
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


def _read_state_unlocked() -> dict[str, Any]:
    fresh = _initial_state()
    _state_directory()
    destination = _state_path()
    try:
        metadata = destination.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CourseRuntimeError("state must be a regular JSON file")
        if metadata.st_size > MAX_METADATA_BYTES:
            return fresh
        raw = destination.read_bytes()
        if len(raw) > MAX_METADATA_BYTES:
            return fresh
        value: Any = json.loads(raw)
    except FileNotFoundError:
        return fresh
    except json.JSONDecodeError:
        return fresh
    if not isinstance(value, dict):
        return fresh
    identity_keys = (
        "course_id",
        "curriculum_id",
        "course_contract_sha256",
    )
    if any(value.get(key) != fresh[key] for key in identity_keys):
        return fresh
    if (
        not isinstance(value.get("knowledge", {}), dict)
        or not isinstance(value.get("grades", {}), dict)
        or not isinstance(value.get("checkpoints", {}), dict)
        or not isinstance(value.get("completed_labs", []), list)
        or not all(
            isinstance(item, str) for item in value.get("completed_labs", [])
        )
        or (
            value.get("updated_at") is not None
            and not isinstance(value.get("updated_at"), str)
        )
    ):
        return fresh
    for key in (
        "knowledge",
        "grades",
        "completed_labs",
        "checkpoints",
        "updated_at",
    ):
        if key in value:
            fresh[key] = value[key]
    return fresh


def read_state() -> dict[str, Any]:
    with _STATE_THREAD_LOCK:
        return _read_state_unlocked()


def _write_state_unlocked(value: dict[str, Any]) -> dict[str, Any]:
    directory = _state_directory()
    destination = _state_path()
    if destination.is_symlink():
        raise CourseRuntimeError("state cannot be a symlink")
    value["updated_at"] = datetime.now(timezone.utc).isoformat()
    descriptor, raw = tempfile.mkstemp(
        prefix="state-",
        suffix=".json",
        dir=directory,
    )
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return value


def update_state(mutation: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    with _STATE_THREAD_LOCK, _state_file_lock():
        value = _read_state_unlocked()
        mutation(value)
        return _write_state_unlocked(value)


def _knowledge_complete(chapter_id: str, value: dict[str, Any]) -> bool:
    try:
        questions = _public_quiz(chapter_id)["questions"]
    except (CourseRuntimeError, LookupError):
        return False
    mastered = value.get("knowledge", {}).get(chapter_id, {})
    return bool(questions) and all(
        mastered.get(str(question.get("id"))) is True for question in questions
    )


def _unit_complete(
    chapter_id: str,
    value: dict[str, Any],
    course: dict[str, Any],
) -> bool:
    chapter = _chapter(chapter_id, course)
    if not bool(chapter.get("graded")):
        return _knowledge_complete(chapter_id, value)
    return chapter_id in {
        str(item) for item in value.get("completed_labs", []) if isinstance(item, str)
    }


def _navigable(
    chapter_id: str,
    value: dict[str, Any],
    course: dict[str, Any],
) -> bool:
    chapter = _chapter(chapter_id, course)
    if _unit_complete(chapter_id, value, course):
        return True
    dependency = chapter.get("depends_on")
    if dependency is None:
        return True
    return isinstance(dependency, str) and _unit_complete(dependency, value, course)


def exposed_state(value: dict[str, Any]) -> dict[str, Any]:
    course = manifest()
    unlocked = [
        str(chapter["id"])
        for chapter in course["chapters"]
        if _navigable(str(chapter["id"]), value, course)
    ]
    completed_preparatory = [
        str(chapter["id"])
        for chapter in course["chapters"]
        if not bool(chapter.get("graded"))
        and _knowledge_complete(str(chapter["id"]), value)
    ]
    summary = score(value, course)
    return {
        **value,
        "unlocked_labs": unlocked,
        "completed_preparatory_units": completed_preparatory,
        "score": summary["verified"],
        "total_points": summary["total"],
    }


def _run_gate_reasons(
    chapter_id: str,
    value: dict[str, Any],
    course: dict[str, Any] | None = None,
) -> list[str]:
    current = course or manifest()
    chapter = _chapter(chapter_id, current)
    reasons: list[str] = []
    if not bool(chapter.get("graded")):
        reasons.append(f"{chapter_id} is a knowledge-only chapter")
    if not _navigable(chapter_id, value, current):
        reasons.append(
            f"navigate to {chapter_id} only after completing its dependency"
        )
    if not _knowledge_complete(chapter_id, value):
        reasons.append(f"master {chapter_id} knowledge first")
    return reasons


def _knowledge_view(chapter_id: str, value: dict[str, Any]) -> dict[str, Any]:
    course = manifest()
    chapter = _chapter(chapter_id, course)
    questions = _public_quiz(chapter_id)["questions"]
    mastered = value.get("knowledge", {}).get(chapter_id, {})
    exposed_questions: list[dict[str, Any]] = []
    for question in questions:
        choices = question.get("choices", [])
        if not isinstance(choices, list):
            raise CourseRuntimeError(f"{chapter_id} quiz choices are invalid")
        exposed_questions.append(
            {
                "id": str(question.get("id")),
                "prompt": str(question.get("prompt", "")),
                "choices": [
                    {"id": str(choice.get("id")), "text": str(choice.get("text", ""))}
                    for choice in choices
                    if isinstance(choice, dict)
                ],
                "mastered": mastered.get(str(question.get("id"))) is True,
            }
        )
    mastered_count = sum(int(question["mastered"]) for question in exposed_questions)
    total = len(exposed_questions)
    return {
        "lab_id": chapter_id,
        "title": str(chapter.get("title", chapter_id)),
        "available": _navigable(chapter_id, value, course),
        "completed": bool(total) and mastered_count == total,
        "mastered": mastered_count,
        "total": total,
        "questions": exposed_questions,
    }


def _learner_manifest(course: dict[str, Any]) -> dict[str, Any]:
    labs: list[dict[str, Any]] = []
    for chapter in course["chapters"]:
        graded = bool(chapter.get("graded"))
        study: dict[str, Any] = {
            "min": chapter.get("study_min"),
            "max": chapter.get("study_max"),
        }
        if chapter.get("study_reason") is not None:
            study["reason"] = chapter["study_reason"]
        tasks: list[dict[str, Any]] = []
        for configured in chapter.get("tasks", []):
            task = dict(configured)
            example = {
                key: configured[f"example_{key}"]
                for key in ("input", "output", "explanation")
                if configured.get(f"example_{key}") is not None
            }
            if example:
                task["example"] = example
            tasks.append(task)
        labs.append(
            {
                "id": chapter["id"],
                "title": chapter.get("title", chapter["id"]),
                "graded": graded,
                # The retained Web contract uses ``lab`` for every coding unit;
                # preserve the more precise v4 kind alongside it.
                "unit_type": "lab" if graded else chapter.get("kind"),
                "kind": chapter.get("kind"),
                "depends_on": chapter.get("depends_on"),
                "study_minutes": study,
                "questions": tasks,
                "tasks": tasks,
            }
        )
    total_points = sum(
        int(task.get("points", 1))
        for chapter in course["chapters"]
        for task in chapter.get("tasks", [])
    )
    return {
        key: value
        for key, value in {
            **course,
            "language": course.get("language"),
            "labs": labs,
            "total_points": total_points,
        }.items()
        if key != "chapters"
    }


def _content(chapter_id: str) -> dict[str, Any]:
    course = manifest()
    chapter = _chapter(chapter_id, course)
    tutorial_path = str(chapter.get("tutorial", ""))
    terms_path = str(chapter.get("terms", ""))
    lesson = _read_bytes(
        LEARNER_ROOT,
        tutorial_path,
        label=f"{chapter_id} tutorial",
    ).decode("utf-8")
    terms_value = _read_json(
        LEARNER_ROOT,
        terms_path,
        label=f"{chapter_id} terms",
    )
    configured_terms = terms_value.get("terms", [])
    if not isinstance(configured_terms, list):
        raise CourseRuntimeError(f"{chapter_id} terms are invalid")
    terms: list[dict[str, str]] = []
    for index, term in enumerate(configured_terms):
        if not isinstance(term, dict):
            raise CourseRuntimeError(f"{chapter_id} terms are invalid")
        name = term.get("name", term.get("term"))
        definition = term.get("definition")
        if not isinstance(name, str) or not isinstance(definition, str):
            raise CourseRuntimeError(f"{chapter_id} terms are invalid")
        term_id = term.get("id")
        terms.append(
            {
                "id": str(term_id) if isinstance(term_id, str) else f"term-{index + 1}",
                "name": name,
                "definition": definition,
            }
        )
    source_ids = chapter.get("source_ids", [])
    sources = [
        source
        for source in course.get("sources", [])
        if isinstance(source, dict) and source.get("id") in source_ids
    ]
    study_minutes: dict[str, Any] = {
        "min": chapter.get("study_min"),
        "max": chapter.get("study_max"),
    }
    if chapter.get("study_reason") is not None:
        study_minutes["reason"] = chapter["study_reason"]
    tasks = chapter.get("tasks", [])
    practice_links = (
        [
            {
                "kind": "coding-question",
                "item_id": str(tasks[0]["id"]),
                "title": str(tasks[0].get("title", tasks[0]["id"])),
            }
        ]
        if tasks
        else []
    )
    return {
        "id": chapter_id,
        "title": str(chapter.get("title", chapter_id)),
        "lesson": lesson,
        "lesson_format": "tutorial-markdown-v1",
        "terms": terms,
        "sources": sources,
        "study_minutes": study_minutes,
        "practice_links": practice_links,
    }


def _workspace_parts(
    chapter_id: str,
    task_id: str,
    value: dict[str, Any],
) -> tuple[str, tuple[str, ...]]:
    course = manifest()
    _chapter_value, task = _task(chapter_id, task_id, course)
    reasons = _run_gate_reasons(chapter_id, value, course)
    if reasons:
        raise CodeFileLockedError(
            f"{chapter_id} is locked: " + "; ".join(reasons)
        )
    raw = task.get("file")
    if not isinstance(raw, str):
        raise ValueError("coding question file must be text")
    return raw, _safe_parts(raw, "coding question file")


def _open_workspace_file(parts: tuple[str, ...], flags: int) -> int:
    root = _regular_root(LEARNER_ROOT, "learner root")
    if os.name == "nt":  # pragma: no cover - shared runtime CI
        candidate = _regular_file(
            root,
            "/".join(parts),
            label="workspace target",
        )
        return os.open(candidate, flags | os.O_BINARY)

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd: int | None = None
    try:
        current_fd = os.open(root, directory_flags)
        for part in parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        descriptor = os.open(
            parts[-1],
            flags | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=current_fd,
        )
    except OSError as error:
        if error.errno == errno.ENOENT:
            raise FileNotFoundError("workspace target does not exist") from error
        raise ValueError(
            "workspace target must be a regular file without symlinks"
        ) from error
    finally:
        if current_fd is not None:
            os.close(current_fd)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError("workspace target must be a regular file")
    return descriptor


def read_workspace_text(parts: tuple[str, ...]) -> str:
    descriptor = _open_workspace_file(parts, os.O_RDONLY)
    try:
        if os.fstat(descriptor).st_size > MAX_FILE_BYTES:
            raise ValueError("file is too large")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(65_536, MAX_FILE_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ValueError("file is too large")
        return b"".join(chunks).decode("utf-8")
    finally:
        os.close(descriptor)


def write_workspace_text(parts: tuple[str, ...], content: str) -> None:
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"content exceeds {MAX_FILE_BYTES} UTF-8 bytes")
    descriptor = _open_workspace_file(parts, os.O_WRONLY)
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


def canonical_test_targets(root: Path, selectors: list[Any]) -> list[str]:
    base = _regular_root(root, "canonical test root")
    targets: list[str] = []
    for selector in selectors:
        if not isinstance(selector, str):
            raise ValueError("canonical pytest selector must be text")
        raw_path, separator, node = selector.partition("::")
        if not separator or not node:
            raise ValueError(f"unsafe canonical pytest selector: {selector}")
        source = _regular_file(base, raw_path, label="canonical pytest target")
        targets.append(f"{source.resolve()}::{node}")
    if not targets:
        raise ValueError("at least one canonical pytest selector is required")
    return targets


def _hidden_selectors(chapter_id: str, task_id: str) -> list[str]:
    author, _answers = _author_package()
    task = next(
        (
            item
            for item in author["tasks"]
            if isinstance(item, dict)
            and item.get("chapter_id") == chapter_id
            and item.get("task_id") == task_id
        ),
        None,
    )
    if not isinstance(task, dict) or not isinstance(task.get("hidden_tests"), list):
        raise AuthorPackageError(
            "author package is unavailable or does not match this course"
        )
    return [str(value) for value in task["hidden_tests"]]


def _run_tests(request: RunRequest) -> tuple[bool, bool, str]:
    course = manifest()
    _chapter_value, task = _task(request.lab_id, request.question_id, course)
    timeout_seconds = task.get("timeout_seconds")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 1 <= timeout_seconds <= 90
    ):
        raise ValueError("task timeout_seconds must be an integer from 1 to 90")
    public_selectors = task.get("public_tests")
    if not isinstance(public_selectors, list):
        raise ValueError("task public_tests must be a list")
    public_targets = canonical_test_targets(LEARNER_ROOT, public_selectors)
    deadline = time.monotonic() + timeout_seconds
    public_result = run_isolated_pytest(
        LEARNER_ROOT,
        public_targets,
        timeout_seconds=timeout_seconds,
    )
    if request.mode == "public" or not public_result.passed:
        return (
            public_result.passed,
            public_result.passed,
            public_result.output,
        )

    language = str(course.get("language", "en"))
    try:
        hidden_targets = canonical_test_targets(
            AUTHOR_ROOT,
            _hidden_selectors(request.lab_id, request.question_id),
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        hidden_result = run_isolated_pytest(
            LEARNER_ROOT,
            hidden_targets,
            timeout_seconds=remaining,
        )
    except AuthorPackageError:
        raise
    except Exception:
        message = (
            "隐藏测试暂时不可用。"
            if language == "zh-CN"
            else "Hidden tests are unavailable."
        )
        return False, True, message
    count = len(hidden_targets)
    if language == "zh-CN":
        result = "通过" if hidden_result.passed else "未通过"
        output = f"Hidden submit {result}（{count} 个私有测试目标）。"
    else:
        result = "passed" if hidden_result.passed else "failed"
        output = f"Hidden submit {result} ({count} private test targets)."
    return hidden_result.passed, True, output


def _record_result(
    request: RunRequest,
    passed: bool,
    public_passed: bool,
) -> dict[str, Any]:
    course = manifest()
    chapter, _task_value = _task(request.lab_id, request.question_id, course)

    def mutation(value: dict[str, Any]) -> None:
        grade = (
            value.setdefault("grades", {})
            .setdefault(request.lab_id, {})
            .setdefault(request.question_id, {})
        )
        grade["public"] = bool(public_passed)
        if request.mode == "submit":
            # Hidden verification is mastery, not a snapshot of the most recent
            # attempt. Once earned it remains available for progression even if
            # a later edit or submit fails.
            grade["verified"] = grade.get("verified") is True or bool(passed)
            complete = all(
                value["grades"]
                .get(request.lab_id, {})
                .get(str(task["id"]), {})
                .get("verified")
                is True
                for task in chapter.get("tasks", [])
            )
            if complete and request.lab_id not in value["completed_labs"]:
                value["completed_labs"].append(request.lab_id)

    return update_state(mutation)


def score(
    value: dict[str, Any],
    course: dict[str, Any] | None = None,
) -> dict[str, int]:
    current = course or manifest()
    total = public = verified = 0
    for chapter in current["chapters"]:
        for task in chapter.get("tasks", []):
            points = int(task.get("points", 1))
            total += points
            grade = (
                value.get("grades", {})
                .get(str(chapter["id"]), {})
                .get(str(task["id"]), {})
            )
            public += points if grade.get("public") else 0
            verified += points if grade.get("verified") else 0
    return {"public": public, "verified": verified, "total": total}


def create_app() -> FastAPI:
    application = FastAPI(title="CourseKit v4 Local Runner")

    @application.exception_handler(CourseRuntimeError)
    async def runtime_error(
        _request: Any,
        error: CourseRuntimeError,
    ) -> JSONResponse:
        status = 503 if isinstance(error, AuthorPackageError) else 500
        return JSONResponse(status_code=status, content={"detail": str(error)})

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/course")
    def get_course() -> dict[str, Any]:
        current = manifest()
        return {
            "manifest": _learner_manifest(current),
            "state": exposed_state(read_state()),
        }

    @application.get("/api/state")
    def get_state() -> dict[str, Any]:
        return exposed_state(read_state())

    @application.get("/api/content/{chapter_id}")
    def get_content(chapter_id: str) -> dict[str, Any]:
        try:
            return _content(chapter_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except UnicodeError as error:
            raise HTTPException(
                status_code=500,
                detail=f"{chapter_id} tutorial is not valid UTF-8",
            ) from error

    @application.get("/api/knowledge/{chapter_id}")
    def get_knowledge(chapter_id: str) -> dict[str, Any]:
        try:
            return _knowledge_view(chapter_id, read_state())
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @application.post("/api/knowledge/answer")
    def answer_knowledge(request: KnowledgeAnswer) -> dict[str, Any]:
        try:
            _quiz, question = _quiz_question(
                request.lab_id,
                request.question_id,
            )
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        current_state = read_state()
        course = manifest()
        if not _navigable(request.lab_id, current_state, course):
            raise HTTPException(
                status_code=409,
                detail=f"{request.lab_id} knowledge is not available yet",
            )
        choices = question.get("choices")
        if not isinstance(choices, list):
            raise HTTPException(status_code=400, detail="quiz choices are invalid")
        choice_ids = {
            str(choice.get("id"))
            for choice in choices
            if isinstance(choice, dict)
        }
        if request.choice_id not in choice_ids:
            raise HTTPException(status_code=400, detail="invalid choice")
        _author, answer_book = _author_package()
        try:
            answer = answer_book["chapters"][request.lab_id][request.question_id]
            answer_id = answer["answer_id"]
            feedback = answer.get("feedback", {}).get(request.choice_id, "")
            explanation = answer.get("explanation", "")
        except (KeyError, TypeError) as error:
            raise AuthorPackageError(
                "author package is unavailable or does not match this course"
            ) from error
        if not isinstance(answer_id, str) or answer_id not in choice_ids:
            raise AuthorPackageError(
                "author package is unavailable or does not match this course"
            )
        correct = request.choice_id == answer_id
        if correct:

            def mutation(value: dict[str, Any]) -> None:
                value.setdefault("knowledge", {}).setdefault(request.lab_id, {})[
                    request.question_id
                ] = True

            current_state = update_state(mutation)
        return {
            "correct": correct,
            "feedback": str(feedback),
            "explanation": str(explanation),
            "knowledge": _knowledge_view(request.lab_id, current_state),
            "state": exposed_state(current_state),
        }

    @application.get("/api/file")
    def get_file(lab_id: str, question_id: str) -> dict[str, str]:
        try:
            path, parts = _workspace_parts(lab_id, question_id, read_state())
            return {"path": path, "content": read_workspace_text(parts)}
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except CodeFileLockedError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="file not found") from error
        except (OSError, UnicodeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.put("/api/file")
    def put_file(request: FileWrite) -> dict[str, str]:
        try:
            path, parts = _workspace_parts(
                request.lab_id,
                request.question_id,
                read_state(),
            )
            write_workspace_text(parts, request.content)
            return {"path": path, "status": "saved"}
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except CodeFileLockedError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="file not found") from error
        except (OSError, UnicodeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.post("/api/run")
    def run(request: RunRequest) -> dict[str, Any]:
        if not _RUN_LOCK.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="Runner is busy with another grading request; try again shortly",
            )
        try:
            course = manifest()
            try:
                _task(request.lab_id, request.question_id, course)
            except LookupError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            current_state = read_state()
            reasons = _run_gate_reasons(request.lab_id, current_state, course)
            if reasons:
                raise HTTPException(
                    status_code=409,
                    detail=f"{request.lab_id} is locked: " + "; ".join(reasons),
                )
            passed, public_passed, output = _run_tests(request)
            value = _record_result(request, passed, public_passed)
            summary = score(value, course)
            return {
                "passed": passed,
                "output": output,
                "score": summary["verified"],
                "score_summary": summary,
                "state": exposed_state(value),
            }
        except AuthorPackageError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        finally:
            _RUN_LOCK.release()

    @application.api_route(
        "/api/{unknown_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    def unknown_api(unknown_path: str) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Unknown API route: /api/{unknown_path}"},
        )

    # Mount the prebuilt SPA last so it cannot shadow any API route. A missing
    # or symlinked static tree fails closed as ordinary 404 responses.
    if STATIC_ROOT.is_dir() and not STATIC_ROOT.is_symlink():
        application.mount(
            "/",
            CourseSPAStaticFiles(directory=STATIC_ROOT, html=True),
            name="coursekit-web",
        )
    return application


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("COURSEKIT_HOST", "127.0.0.1")
    raw_port = os.environ.get("COURSEKIT_PORT", "8765")
    try:
        port = int(raw_port)
    except ValueError as error:
        raise SystemExit("COURSEKIT_PORT must be an integer") from error
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
