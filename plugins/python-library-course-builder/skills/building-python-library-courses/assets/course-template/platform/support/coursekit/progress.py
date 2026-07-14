"""Atomic, manifest-driven learner progress storage."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Iterator

from .course import ROOT, formal_labs, foundation, load_manifest


STATE_VERSION = 1
STATE_PATH = ROOT / ".coursekit" / "state.json"
KNOWLEDGE_PATH = ROOT / "_course" / "knowledge.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_head() -> str | None:
    """Return the repository HEAD used as the learner's progress baseline."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def initial_state() -> dict[str, Any]:
    manifest = load_manifest()
    return {
        "version": STATE_VERSION,
        "course_id": manifest["course_id"],
        "curriculum_id": manifest["curriculum_id"],
        "knowledge": {},
        "grades": {},
        "completed_labs": [],
        "checkpoints": {},
        "git_baseline_commit": git_head(),
        "updated_at": None,
    }


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


def _compatible(value: Any, fresh: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return fresh
    if value.get("course_id") != fresh["course_id"]:
        return fresh
    compatible = {fresh["curriculum_id"]}
    compatible.update(load_manifest().get("compatible_curriculum_ids", []))
    if value.get("curriculum_id") not in compatible:
        return fresh
    result = dict(fresh)
    for key in (
        "knowledge",
        "grades",
        "completed_labs",
        "checkpoints",
        "git_baseline_commit",
        "updated_at",
    ):
        if key in value:
            result[key] = value[key]
    result["curriculum_id"] = fresh["curriculum_id"]
    return result


def read_state() -> dict[str, Any]:
    fresh = initial_state()
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fresh
    return _compatible(value, fresh)


def _write_state_unlocked(state: dict[str, Any]) -> dict[str, Any]:
    state["updated_at"] = utc_now()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(
        prefix="state-", suffix=".json", dir=STATE_PATH.parent
    )
    temp = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp, STATE_PATH)
    finally:
        temp.unlink(missing_ok=True)
    return state


def write_state(state: dict[str, Any]) -> dict[str, Any]:
    with _lock(STATE_PATH):
        return _write_state_unlocked(state)


def update_state(mutation: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    with _lock(STATE_PATH):
        state = read_state()
        mutation(state)
        return _write_state_unlocked(state)


def load_knowledge() -> dict[str, Any]:
    return json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))


def knowledge_complete(lab_id: str, state: dict[str, Any] | None = None) -> bool:
    value = state or read_state()
    bank = load_knowledge()
    required = [str(question["id"]) for question in bank["labs"][lab_id]["questions"]]
    mastered = value.get("knowledge", {}).get(lab_id, {})
    return bool(required) and all(mastered.get(question_id) is True for question_id in required)


def record_answer(lab_id: str, question_id: str, correct: bool) -> dict[str, Any]:
    if not correct:
        return read_state()

    def mutation(state: dict[str, Any]) -> None:
        state.setdefault("knowledge", {}).setdefault(lab_id, {})[question_id] = True

    return update_state(mutation)


def prerequisite(lab_id: str) -> str | None:
    if lab_id == str(foundation().get("id")):
        return None
    labs = formal_labs()
    match = next((lab for lab in labs if str(lab.get("id")) == lab_id), None)
    return str(match.get("depends_on")) if match else None


def knowledge_gate_reasons(
    lab_id: str, state: dict[str, Any] | None = None
) -> list[str]:
    value = state or read_state()
    base_id = str(foundation().get("id"))
    if lab_id == base_id:
        return []
    reasons = []
    if not knowledge_complete(base_id, value):
        reasons.append(f"unlock {base_id} first")
    dependency = prerequisite(lab_id)
    completed = {str(item) for item in value.get("completed_labs", [])}
    if dependency and dependency != base_id and dependency not in completed:
        reasons.append(f"complete {dependency} first")
    return reasons


def navigable(lab_id: str, state: dict[str, Any] | None = None) -> bool:
    value = state or read_state()
    base_id = str(foundation().get("id"))
    if lab_id == base_id:
        return True
    completed = {str(item) for item in value.get("completed_labs", [])}
    if lab_id in completed:
        return True
    dependency = prerequisite(lab_id)
    return dependency == base_id or dependency in completed


def gate_reasons(lab_id: str, state: dict[str, Any] | None = None) -> list[str]:
    value = state or read_state()
    reasons = []
    dependency = prerequisite(lab_id)
    base_id = str(foundation().get("id"))
    if not navigable(lab_id, value) and dependency:
        reasons.append(f"complete {dependency} first")
    if lab_id != base_id and not knowledge_complete(base_id, value):
        reasons.append(f"unlock {base_id} first")
    if not knowledge_complete(lab_id, value):
        reasons.append(f"run `course unlock {lab_id}` first")
    return reasons


def record_grade(
    lab_id: str,
    question_ids: list[str],
    *,
    verified: bool,
    passed: bool,
) -> dict[str, Any]:
    kind = "verified" if verified else "public"
    lab = next(
        (item for item in formal_labs() if str(item.get("id")) == lab_id),
        None,
    )
    declared = (
        [
            str(question["id"])
            for question in lab.get("questions", [])
            if isinstance(question, dict)
        ]
        if isinstance(lab, dict)
        else []
    )

    def mutation(state: dict[str, Any]) -> None:
        for question_id in question_ids:
            state.setdefault("grades", {}).setdefault(lab_id, {}).setdefault(
                question_id, {}
            )[kind] = bool(passed)
        complete = bool(declared) and all(
            state.get("grades", {})
            .get(lab_id, {})
            .get(question_id, {})
            .get("verified")
            is True
            for question_id in declared
        )
        if verified and complete and lab_id not in state["completed_labs"]:
            state["completed_labs"].append(lab_id)

    return update_state(mutation)


def score(state: dict[str, Any] | None = None) -> dict[str, int]:
    value = state or read_state()
    manifest = load_manifest()
    total = 0
    public = 0
    verified = 0
    for lab in formal_labs(manifest):
        for question in lab.get("questions", []):
            points = int(question.get("points", 1))
            total += points
            grade = value.get("grades", {}).get(str(lab["id"]), {}).get(str(question["id"]), {})
            public += points if grade.get("public") else 0
            verified += points if grade.get("verified") else 0
    return {"public": public, "verified": verified, "total": total}
