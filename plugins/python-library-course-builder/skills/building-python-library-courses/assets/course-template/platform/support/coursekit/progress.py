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

from .course import (
    ROOT,
    find_unit,
    formal_labs,
    foundation,
    is_preparatory_unit,
    load_manifest,
    ordered_units,
    preparatory_units,
    schema_version,
)


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
    manifest = load_manifest()
    compatible = {fresh["curriculum_id"]}
    if schema_version(manifest) < 3:
        compatible.update(manifest.get("compatible_curriculum_ids", []))
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


def prerequisite(lab_id: str, manifest: dict[str, Any] | None = None) -> str | None:
    current = manifest or load_manifest()
    if lab_id == str(foundation(current).get("id")):
        return None
    match = find_unit(lab_id, current)
    dependency = match.get("depends_on") if isinstance(match, dict) else None
    return str(dependency) if dependency is not None else None


def unit_complete(
    unit_id: str,
    state: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> bool:
    value = state if state is not None else read_state()
    current = manifest or load_manifest()
    if find_unit(unit_id, current) is None:
        return False
    if is_preparatory_unit(unit_id, current):
        return knowledge_complete(unit_id, value)
    return unit_id in {str(item) for item in value.get("completed_labs", [])}


def completed_preparatory_units(
    state: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    value = state if state is not None else read_state()
    current = manifest or load_manifest()
    return [
        str(item["id"])
        for item in preparatory_units(current)
        if unit_complete(str(item["id"]), value, current)
    ]


def unlocked_units(
    state: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    value = state if state is not None else read_state()
    current = manifest or load_manifest()
    return [
        str(item["id"])
        for item in ordered_units(current)
        if navigable(str(item["id"]), value, current)
    ]


def knowledge_gate_reasons(
    lab_id: str, state: dict[str, Any] | None = None
) -> list[str]:
    value = state if state is not None else read_state()
    manifest = load_manifest()
    base_id = str(foundation(manifest).get("id"))
    if lab_id == base_id:
        return []
    if schema_version(manifest) >= 3:
        dependency = prerequisite(lab_id, manifest)
        if dependency and not unit_complete(dependency, value, manifest):
            return [f"complete {dependency} first"]
        return []
    reasons = []
    if not knowledge_complete(base_id, value):
        reasons.append(f"unlock {base_id} first")
    dependency = prerequisite(lab_id)
    completed = {str(item) for item in value.get("completed_labs", [])}
    if dependency and dependency != base_id and dependency not in completed:
        reasons.append(f"complete {dependency} first")
    return reasons


def navigable(
    lab_id: str,
    state: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> bool:
    value = state if state is not None else read_state()
    current = manifest or load_manifest()
    if find_unit(lab_id, current) is None:
        return False
    base_id = str(foundation(current).get("id"))
    if lab_id == base_id:
        return True
    if schema_version(current) >= 3:
        if unit_complete(lab_id, value, current):
            return True
        dependency = prerequisite(lab_id, current)
        return bool(dependency) and unit_complete(dependency, value, current)
    completed = {str(item) for item in value.get("completed_labs", [])}
    if lab_id in completed:
        return True
    dependency = prerequisite(lab_id)
    return dependency == base_id or dependency in completed


def gate_reasons(lab_id: str, state: dict[str, Any] | None = None) -> list[str]:
    value = state if state is not None else read_state()
    manifest = load_manifest()
    if schema_version(manifest) >= 3 and is_preparatory_unit(lab_id, manifest):
        return [f"{lab_id} is a knowledge-only preparatory unit"]
    reasons = []
    dependency = prerequisite(lab_id, manifest)
    base_id = str(foundation(manifest).get("id"))
    if not navigable(lab_id, value, manifest) and dependency:
        reasons.append(f"complete {dependency} first")
    if schema_version(manifest) >= 3:
        if not knowledge_complete(lab_id, value):
            reasons.append(f"run `course unlock {lab_id}` first")
        return reasons
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
    current = load_manifest()
    if (
        lab is None
        and schema_version(current) >= 3
        and is_preparatory_unit(lab_id, current)
    ):
        raise ValueError(f"{lab_id} is not a graded Lab")
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
