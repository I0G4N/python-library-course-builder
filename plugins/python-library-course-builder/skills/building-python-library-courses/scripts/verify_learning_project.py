#!/usr/bin/env python3
"""Verify the RED/GREEN, privacy, runtime, and standalone course contracts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request


RESIDUE_PATTERN = re.compile(
    r"Concurrency(?:Lab)|ThreadEval|threadeval|CONCURRENCY(?:LAB)|"
    r"completedCount\s*/\s*12|\blab12\b"
)
TOKEN_PATTERN = re.compile(r"\{\{[^{}]+\}\}|__COURSEKIT_[A-Z0-9_]+__")
RAY_UV_RUNTIME_ENV_FLAG = "RAY_ENABLE_UV_RUN_RUNTIME_ENV"
_SAFE_SUBPROCESS_ENVIRONMENT_NAMES = frozenset(
    {
        "COMSPEC",
        "LANG",
        "LANGUAGE",
        "LC_ADDRESS",
        "LC_ALL",
        "LC_COLLATE",
        "LC_CTYPE",
        "LC_IDENTIFICATION",
        "LC_MEASUREMENT",
        "LC_MESSAGES",
        "LC_MONETARY",
        "LC_NAME",
        "LC_NUMERIC",
        "LC_PAPER",
        "LC_TELEPHONE",
        "LC_TIME",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "VIRTUAL_ENV",
        "WINDIR",
    }
)
_TRUSTED_VERIFIER_ENVIRONMENT_NAMES = frozenset(
    {
        "COURSEKIT_COURSE_DIR",
        "COURSEKIT_INTERNAL_RUN",
        "COURSEKIT_RUNNER_URL",
        "COURSEKIT_WORKSPACE_DIR",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONPATH",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        RAY_UV_RUNTIME_ENV_FLAG,
    }
)


def verification_subprocess_env(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return an isolated verifier child environment.

    Only process-launch essentials and verifier-owned CourseKit controls cross
    this boundary; unrelated parent variables, including credentials, do not.
    The verifier can itself be bootstrapped with ``uv run --no-project`` while
    deliberately launching project-owned virtualenv interpreters. Ray 2.56
    otherwise discovers that unrelated ancestor ``uv run`` process and tries
    to reuse its dependency-free interpreter for workers.
    """
    inherited = os.environ if environment is None else environment
    allowed = _SAFE_SUBPROCESS_ENVIRONMENT_NAMES
    if environment is not None:
        allowed = allowed | _TRUSTED_VERIFIER_ENVIRONMENT_NAMES
    result = {
        name: value
        for name, value in inherited.items()
        if name.upper() in allowed
    }
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result[RAY_UV_RUNTIME_ENV_FLAG] = "0"
    return result


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=verification_subprocess_env(env),
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def python_env(project: Path, *, reference: bool = False) -> dict[str, str]:
    environment = verification_subprocess_env()
    paths = [project / "labs" / "_course", project / "labs"]
    if reference:
        paths.insert(0, project / "platform" / "course" / "reference")
    environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in paths)
    environment["COURSEKIT_INTERNAL_RUN"] = "1"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def environment_python(project: Path, environment: str) -> str:
    root = project / environment / ".venv"
    candidates = [root / "bin" / "python", root / "Scripts" / "python.exe"]
    return str(next((path for path in candidates if path.is_file()), Path(sys.executable)))


def learner_cli_command(project: Path) -> list[str]:
    root = project / "labs" / ".venv"
    candidates = [root / "bin" / "course", root / "Scripts" / "course.exe"]
    command = next((path for path in candidates if path.is_file()), None)
    if command is not None:
        return [str(command), "--help"]
    return [sys.executable, "-m", "coursekit.cli", "--help"]


def pytest_targets(project: Path) -> tuple[list[str], list[str]]:
    public = [
        str(path)
        for path in sorted((project / "labs").glob("lab*/tests"))
        if path.is_dir()
    ]
    hidden_root = project / "platform" / "course" / "tests" / "hidden"
    hidden = [str(hidden_root)] if hidden_root.is_dir() else []
    return public, hidden


def declared_public_targets(project: Path) -> list[tuple[str, list[str]]]:
    """Return one public pytest target set for every declared coding interface."""
    manifest = json.loads(
        (project / "labs" / "manifest.json").read_text(encoding="utf-8")
    )
    result: list[tuple[str, list[str]]] = []
    for lab in manifest.get("labs", []):
        if not isinstance(lab, dict):
            continue
        for question in lab.get("questions", []):
            if not isinstance(question, dict):
                continue
            tests = question.get("tests", {})
            targets: list[str] = []
            if isinstance(tests, dict):
                for key in ("public", "sample"):
                    configured = tests.get(key)
                    if isinstance(configured, list) and configured:
                        targets = [str(item) for item in configured]
                        break
            result.append((str(question.get("id", "")), list(dict.fromkeys(targets))))
    return result


def starter_red_check(project: Path, learner_python: str) -> tuple[bool, str]:
    """Prove each declared interface has an ordinary public-test failure.

    Pytest exit code 1 means tests were collected and failed. Collection,
    usage, interruption, no-test, and infrastructure failures use other exit
    codes and are never accepted as learner RED evidence.
    """
    interfaces = declared_public_targets(project)
    if not interfaces:
        return False, "learner manifest declares no coding interfaces"
    evidence: list[str] = []
    for question_id, targets in interfaces:
        if not question_id or not targets:
            return False, f"{question_id or '<unknown>'}: no declared public selector"
        completed = run(
            [learner_python, "-m", "pytest", "-q", *targets],
            cwd=project / "labs",
            env=python_env(project),
        )
        evidence.append(f"{question_id}={completed.returncode}")
        if completed.returncode != 1:
            detail = (completed.stdout + completed.stderr)[-2000:]
            return (
                False,
                f"{question_id}: expected pytest exit 1, got {completed.returncode}\n{detail}",
            )
    return True, ", ".join(evidence)


def reference_public_targets(project: Path) -> list[str]:
    return [
        str(path)
        for path in sorted((project / "platform" / "course" / "starter").glob("lab*/tests"))
        if path.is_dir()
    ]


def runnable_lesson_examples(
    project: Path, python: str
) -> tuple[bool, str]:
    """Execute every schema-v2 runnable example from canonical split source."""
    snapshot_path = project / "platform" / "course" / "authoring-spec.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        return False, f"authoring snapshot unavailable: {error}"

    sections: list[tuple[str, Path, dict[str, Any]]] = []
    foundation = snapshot.get("foundation")
    if isinstance(foundation, dict):
        sections.append(
            (
                str(foundation.get("id", "lab00")),
                project / "platform" / "course" / "source" / "foundations",
                foundation,
            )
        )
    for lab in snapshot.get("labs", []):
        if isinstance(lab, dict):
            lab_id = str(lab.get("id", ""))
            sections.append(
                (
                    lab_id,
                    project
                    / "platform"
                    / "course"
                    / "source"
                    / "labs"
                    / lab_id,
                    lab,
                )
            )

    evidence: list[str] = []
    found = 0
    for lab_id, base, section in sections:
        lesson = section.get("lesson")
        examples = lesson.get("examples") if isinstance(lesson, dict) else None
        if not isinstance(examples, list):
            return False, f"{lab_id} has no structured lesson examples"
        for example in examples:
            if not isinstance(example, dict) or example.get("kind") != "runnable":
                continue
            found += 1
            example_id = str(example.get("id", f"{lab_id}.example"))
            raw_path = example.get("path")
            if not isinstance(raw_path, str):
                return False, f"{example_id} has no runnable path"
            relative = PurePosixPath(raw_path)
            if relative.is_absolute() or any(
                part in {"", ".", ".."} for part in relative.parts
            ):
                return False, f"{example_id} has an unsafe runnable path"
            source = base.joinpath(*relative.parts)
            if source.is_symlink() or not source.is_file():
                return False, f"{example_id} runnable source is missing or unsafe"
            completed = run(
                [python, str(source)],
                cwd=base,
                env=python_env(project),
                timeout=90,
            )
            evidence.append(f"{example_id}={completed.returncode}")
            if completed.returncode:
                detail = (completed.stdout + completed.stderr)[-2000:]
                return False, f"{example_id} failed with {completed.returncode}:\n{detail}"
            expected = example.get("expected_output")
            if not isinstance(expected, str):
                return False, f"{example_id} has no expected output"
            actual = completed.stdout.rstrip()
            if actual != expected.rstrip():
                return (
                    False,
                    f"{example_id} expected {expected.rstrip()!r}, got {actual!r}",
                )
    if not found:
        return False, "course declares no runnable lesson examples"
    return True, ", ".join(evidence)


def scan_residue(project: Path) -> list[str]:
    findings = []
    for path in project.rglob("*"):
        if not path.is_file() or any(part in {".git", "node_modules", ".venv", ".uv-cache", ".next"} for part in path.parts):
            continue
        relative = path.relative_to(project)
        # Contract tests intentionally name forbidden legacy strings in negative
        # assertions; residue means shipped runtime/content, not the guard itself.
        if relative.parts[:2] == ("platform", "tests"):
            continue
        try:
            value = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if RESIDUE_PATTERN.search(value) or TOKEN_PATTERN.search(value):
            findings.append(relative.as_posix())
    return findings


def privacy_boundary(project: Path) -> bool:
    labs = project / "labs"
    if (labs / "reference").exists() or (labs / "tests" / "hidden").exists():
        return False
    if any(
        path.is_file() and path.name == "authoring-spec.json"
        for path in labs.rglob("*")
    ):
        return False
    manifest_path = labs / "manifest.json"
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    if "reference_root" in manifest or "reference_components" in manifest:
        return False
    return "tests/hidden" not in manifest_text and '"hidden"' not in manifest_text


def symlink_free(project: Path) -> bool:
    ignored = {".git", "node_modules", ".venv", ".uv-cache", ".next"}
    return not project.is_symlink() and not any(
        path.is_symlink() and not any(part in ignored for part in path.relative_to(project).parts)
        for path in project.rglob("*")
    )


def _quiz_answers(knowledge: dict[str, Any], lab_id: str) -> str:
    answers: list[str] = []
    for question in knowledge["labs"][lab_id]["questions"]:
        answer_id = question.get("answer_id")
        if isinstance(answer_id, str):
            choices = question.get("choices")
            if not isinstance(choices, list):
                raise ValueError(f"{lab_id} quiz choices must be a list")
            choice_ids = [
                choice.get("id") if isinstance(choice, dict) else str(index)
                for index, choice in enumerate(choices)
            ]
            if answer_id not in choice_ids:
                raise ValueError(f"{lab_id} quiz answer_id is not a choice")
            position = choice_ids.index(answer_id)
        else:
            answer = question.get("answer")
            if isinstance(answer, bool) or not isinstance(answer, int):
                raise ValueError(f"{lab_id} quiz has no valid answer")
            position = answer
        answers.append(f"{position + 1}\n")
    return "".join(answers)


def _loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _wait_for_runner(process: subprocess.Popen[str], url: str, timeout: float = 15) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib_request.urlopen(f"{url}/api/health", timeout=1) as response:
                value = json.loads(response.read().decode("utf-8"))
            if value.get("status") == "ok":
                return True
        except (
            urllib_error.URLError,
            TimeoutError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            time.sleep(0.1)
    return False


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


WEB_PROGRESSION_BOOLEAN_CHECKS = (
    "api_workflow",
    "chapter_navigation_gate",
    "knowledge_gate",
    "code_file_gate",
    "coding_verification_gate",
    "shared_progress_state",
)


def web_progression_schema_error(
    result: Any,
    *,
    require_generated_tests: bool = False,
) -> str | None:
    if not isinstance(result, dict):
        return "web_progression schema must be an object"
    required = list(WEB_PROGRESSION_BOOLEAN_CHECKS)
    if require_generated_tests:
        required.append("generated_project_tests")
    missing = [key for key in required if key not in result]
    if missing:
        return "web_progression schema is missing: " + ", ".join(missing)
    allowed = {*required, "output"}
    unknown = sorted(str(key) for key in result if key not in allowed)
    if unknown:
        return "web_progression schema has unknown keys: " + ", ".join(unknown)
    non_boolean = [key for key in required if type(result[key]) is not bool]
    if non_boolean:
        return "web_progression schema requires booleans for: " + ", ".join(
            non_boolean
        )
    if "output" not in result:
        return "web_progression schema is missing: output"
    if not isinstance(result["output"], str):
        return "web_progression schema requires text output"
    return None


_WEB_PROGRESSION_PROBE = r"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from fastapi.testclient import TestClient

import runner.app as runner_app


ANSWER_KEY_FIELDS = {
    "answer",
    "answer_id",
    "correct_answer",
    "correct_choice_id",
}

PUBLIC_KNOWLEDGE_FIELDS = {
    "lab_id",
    "title",
    "available",
    "completed",
    "mastered",
    "total",
    "questions",
}
PUBLIC_QUESTION_FIELDS = {"id", "kind", "prompt", "choices", "mastered"}
PUBLIC_CHOICE_FIELDS = {"id", "text"}


def contains_answer_key(value):
    if isinstance(value, dict):
        return any(
            str(key).lower() in ANSWER_KEY_FIELDS
            or contains_answer_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_answer_key(item) for item in value)
    return False


def is_public_knowledge_view(value):
    if not isinstance(value, dict):
        return False
    if not set(value).issubset(PUBLIC_KNOWLEDGE_FIELDS):
        return False
    questions = value.get("questions")
    if not isinstance(questions, list):
        return False
    for question in questions:
        if not isinstance(question, dict):
            return False
        if not set(question).issubset(PUBLIC_QUESTION_FIELDS):
            return False
        choices = question.get("choices")
        if not isinstance(choices, list):
            return False
        for choice in choices:
            if not isinstance(choice, dict):
                return False
            if set(choice) != PUBLIC_CHOICE_FIELDS:
                return False
            if not all(isinstance(choice[field], str) for field in PUBLIC_CHOICE_FIELDS):
                return False
    return not contains_answer_key(value)


def correct_choice_id(question):
    choices = question.get("choices")
    answer_id = question.get("answer_id")
    answer = question.get("answer")
    if not isinstance(choices, list):
        raise ValueError("knowledge choices must be a list")
    if choices and all(isinstance(choice, str) for choice in choices):
        if isinstance(answer, bool) or not isinstance(answer, int):
            raise ValueError("string knowledge choices require an answer index")
        if answer < 0 or answer >= len(choices):
            raise ValueError("knowledge answer index is out of range")
        return str(answer)
    if choices and all(isinstance(choice, dict) for choice in choices):
        configured = answer_id if isinstance(answer_id, str) else answer
        if not isinstance(configured, str):
            raise ValueError("object knowledge choices require an answer id")
        if configured not in {choice.get("id") for choice in choices}:
            raise ValueError("object knowledge answer id is out of range")
        return configured
    raise ValueError("knowledge choices must use one supported representation")


def post_answer(client, lab_id, question):
    return client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": lab_id,
            "question_id": str(question["id"]),
            "choice_id": correct_choice_id(question),
        },
    )


checks = {
    "api_workflow": False,
    "chapter_navigation_gate": False,
    "knowledge_gate": False,
    "code_file_gate": False,
    "coding_verification_gate": False,
    "shared_progress_state": False,
    "output": "",
}
evidence = []
course_root = Path(os.environ["COURSEKIT_COURSE_DIR"])
workspace = Path(os.environ["COURSEKIT_WORKSPACE_DIR"])
manifest = json.loads((course_root / "manifest.json").read_text(encoding="utf-8"))
knowledge = json.loads((course_root / "knowledge.json").read_text(encoding="utf-8"))
foundation = manifest["foundations"]
labs = [lab for lab in manifest["labs"] if isinstance(lab, dict)]
if len(labs) < 2:
    raise ValueError(
        "functional Web progression requires one foundation and at least two graded Labs"
    )
foundation_id = str(foundation["id"])
first = labs[0]
later = labs[1]
first_id = str(first["id"])
later_id = str(later["id"])
first_questions = [
    question for question in first.get("questions", []) if isinstance(question, dict)
]
if not first_questions:
    raise ValueError(f"{first_id} declares no coding questions")
file_probes = []
for index, question in enumerate(first_questions):
    question_id = str(question["id"])
    relative_file = str(question["file"])
    learner_file = workspace / relative_file
    original_bytes = learner_file.read_bytes()
    original_text = original_bytes.decode("utf-8")
    file_probes.append(
        {
            "question_id": question_id,
            "relative_file": relative_file,
            "learner_file": learner_file,
            "original_bytes": original_bytes,
            "original_text": original_text,
            "request": {"lab_id": first_id, "question_id": question_id},
            "locked_sentinel": f"LOCKED_WRITE_MUST_NOT_APPLY:{index}:{question_id}\n",
            "ready_sentinel": f"# COURSEKIT_WRITE_SENTINEL:{index}:{question_id}\n",
        }
    )


def expected_unlocked(completed):
    unlocked = [foundation_id]
    for lab in labs:
        lab_id = str(lab["id"])
        dependency = str(lab.get("depends_on", foundation_id))
        if (
            lab_id in completed
            or dependency == foundation_id
            or dependency in completed
        ):
            unlocked.append(lab_id)
    return list(dict.fromkeys(unlocked))


initial_expected = expected_unlocked(set())
initial_route_valid = initial_expected == [foundation_id, first_id]

with TestClient(runner_app.app) as client:
    initial_response = client.get("/api/state")
    foundation_response = client.get(f"/api/knowledge/{foundation_id}")
    first_response = client.get(f"/api/knowledge/{first_id}")
    locked_run = client.post(
        "/api/run",
        json={
            "lab_id": first_id,
            "question_id": str(first_questions[0]["id"]),
            "mode": "public",
        },
    )
    foundation_locked_results = []
    for probe in file_probes:
        locked_file = client.get("/api/file", params=probe["request"])
        locked_save = client.put(
            "/api/file",
            json={
                **probe["request"],
                "content": probe["locked_sentinel"],
            },
        )
        unchanged = probe["learner_file"].read_bytes() == probe["original_bytes"]
        foundation_locked_results.append(
            locked_file.status_code == 409
            and locked_save.status_code == 409
            and unchanged
        )
        evidence.extend(
            (
                f"foundation-locked-file-{probe['question_id']}={locked_file.status_code}",
                f"foundation-locked-save-{probe['question_id']}={locked_save.status_code}",
            )
        )
    later_knowledge = knowledge["labs"][later_id]["questions"]
    blocked_later = post_answer(client, later_id, later_knowledge[0])
    blocked_later_payload = blocked_later.json()

    initial_state = initial_response.json()
    foundation_view = foundation_response.json()
    first_view = first_response.json()
    initial_unlocked = initial_state.get("unlocked_labs", [])
    initial_navigation = (
        initial_response.status_code == 200
        and initial_route_valid
        and initial_unlocked == initial_expected
    )
    redacted = (
        foundation_response.status_code == 200
        and is_public_knowledge_view(foundation_view)
        and first_response.status_code == 200
        and is_public_knowledge_view(first_view)
    )
    initial_knowledge_gate = (
        foundation_view.get("available") is True
        and first_view.get("available") is False
        and locked_run.status_code == 409
        and blocked_later.status_code == 409
        and not contains_answer_key(blocked_later_payload)
    )
    evidence.extend(
        (
            f"state={initial_response.status_code}",
            f"initial-unlocked={','.join(initial_unlocked)}",
            f"expected-initial={','.join(initial_expected)}",
            f"locked-run={locked_run.status_code}",
            f"blocked-later-knowledge={blocked_later.status_code}",
        )
    )

    correct_answers = True
    answer_payloads_redacted = True
    for question in knowledge["labs"][foundation_id]["questions"]:
        response = post_answer(client, foundation_id, question)
        payload = response.json()
        evidence.append(
            f"answer-{question['id']}={response.status_code}:{payload.get('correct')}"
        )
        correct_answers = (
            correct_answers
            and response.status_code == 200
            and payload.get("correct") is True
        )
        answer_payloads_redacted = (
            answer_payloads_redacted and not contains_answer_key(payload)
        )

    foundation_mastered_response = client.get(
        f"/api/knowledge/{foundation_id}"
    )
    current_unmastered_response = client.get(f"/api/knowledge/{first_id}")
    foundation_mastered = foundation_mastered_response.json()
    current_unmastered = current_unmastered_response.json()
    independent_knowledge_gates = (
        foundation_mastered_response.status_code == 200
        and foundation_mastered.get("completed") is True
        and current_unmastered_response.status_code == 200
        and current_unmastered.get("available") is True
        and current_unmastered.get("completed") is False
        and is_public_knowledge_view(foundation_mastered)
        and is_public_knowledge_view(current_unmastered)
    )
    evidence.append(
        "foundation-mastered="
        f"{foundation_mastered.get('completed') is True},"
        "current-mastered="
        f"{current_unmastered.get('completed') is True}"
    )

    foundation_only_run = client.post(
        "/api/run",
        json={
            "lab_id": first_id,
            "question_id": str(first_questions[0]["id"]),
            "mode": "public",
        },
    )
    evidence.append(f"foundation-only-run={foundation_only_run.status_code}")
    foundation_only_results = []
    for probe in file_probes:
        locked_file = client.get("/api/file", params=probe["request"])
        locked_save = client.put(
            "/api/file",
            json={
                **probe["request"],
                "content": probe["locked_sentinel"],
            },
        )
        unchanged = probe["learner_file"].read_bytes() == probe["original_bytes"]
        foundation_only_results.append(
            locked_file.status_code == 409
            and locked_save.status_code == 409
            and unchanged
        )
        evidence.extend(
            (
                f"foundation-only-file-{probe['question_id']}={locked_file.status_code}",
                f"foundation-only-save-{probe['question_id']}={locked_save.status_code}",
            )
        )

    for question in knowledge["labs"][first_id]["questions"]:
        response = post_answer(client, first_id, question)
        payload = response.json()
        evidence.append(
            f"answer-{question['id']}={response.status_code}:{payload.get('correct')}"
        )
        correct_answers = (
            correct_answers
            and response.status_code == 200
            and payload.get("correct") is True
        )
        answer_payloads_redacted = (
            answer_payloads_redacted and not contains_answer_key(payload)
        )

    available_response = client.get(f"/api/knowledge/{first_id}")
    before_code_response = client.get("/api/state")
    available_first = available_response.json()
    before_code_state = before_code_response.json()
    before_code_unlocked = before_code_state.get("unlocked_labs", [])
    knowledge_passed = (
        redacted
        and initial_knowledge_gate
        and independent_knowledge_gates
        and foundation_only_run.status_code == 409
        and correct_answers
        and answer_payloads_redacted
        and available_response.status_code == 200
        and available_first.get("completed") is True
        and is_public_knowledge_view(available_first)
    )

    current_ready_results = []
    for probe in file_probes:
        ready_file = client.get("/api/file", params=probe["request"])
        ready_payload = ready_file.json()
        ready_save = client.put(
            "/api/file",
            json={
                **probe["request"],
                "content": probe["ready_sentinel"],
            },
        )
        ready_save_payload = ready_save.json()
        ready_reread = client.get("/api/file", params=probe["request"])
        ready_reread_payload = ready_reread.json()
        sentinel_bytes = probe["ready_sentinel"].encode("utf-8")
        disk_has_sentinel = probe["learner_file"].read_bytes() == sentinel_bytes
        restore = client.put(
            "/api/file",
            json={
                **probe["request"],
                "content": probe["original_text"],
            },
        )
        restored_reread = client.get("/api/file", params=probe["request"])
        restored_payload = restored_reread.json()
        restored = (
            restore.status_code == 200
            and restored_reread.status_code == 200
            and restored_payload.get("content") == probe["original_text"]
            and probe["learner_file"].read_bytes() == probe["original_bytes"]
        )
        current_ready_results.append(
            ready_file.status_code == 200
            and ready_payload.get("path") == probe["relative_file"]
            and ready_payload.get("content") == probe["original_text"]
            and ready_save.status_code == 200
            and ready_save_payload
            == {"path": probe["relative_file"], "status": "saved"}
            and ready_reread.status_code == 200
            and ready_reread_payload.get("path") == probe["relative_file"]
            and ready_reread_payload.get("content") == probe["ready_sentinel"]
            and disk_has_sentinel
            and restored
        )
        evidence.extend(
            (
                f"current-ready-file-{probe['question_id']}={ready_file.status_code}",
                f"current-ready-save-{probe['question_id']}={ready_save.status_code}",
                f"current-ready-reread-{probe['question_id']}={ready_reread.status_code}",
                f"current-ready-restore-{probe['question_id']}={restore.status_code}",
            )
        )
    checks["code_file_gate"] = (
        len(foundation_locked_results) == len(file_probes)
        and all(foundation_locked_results)
        and len(foundation_only_results) == len(file_probes)
        and all(foundation_only_results)
        and len(current_ready_results) == len(file_probes)
        and all(current_ready_results)
    )

    shutil.copytree(
        course_root / "reference" / first_id,
        workspace / first_id,
        dirs_exist_ok=True,
    )
    submit_passed = True
    intermediate_locked = True
    intermediate_navigation = True
    for index, question in enumerate(first_questions):
        response = client.post(
            "/api/run",
            json={
                "lab_id": first_id,
                "question_id": str(question["id"]),
                "mode": "submit",
            },
        )
        payload = response.json()
        evidence.append(
            f"submit-{question['id']}={response.status_code}:{payload.get('passed')}"
        )
        submit_passed = (
            submit_passed
            and response.status_code == 200
            and payload.get("passed") is True
        )
        step_state_response = client.get("/api/state")
        step_state = step_state_response.json()
        is_final = index == len(first_questions) - 1
        if is_final:
            final_label = (
                "completed"
                if first_id in step_state.get("completed_labs", [])
                else "locked"
            )
            evidence.append(f"final-{question['id']}={final_label}")
        else:
            still_locked = (
                step_state_response.status_code == 200
                and first_id not in step_state.get("completed_labs", [])
                and step_state.get("unlocked_labs", []) == initial_expected
            )
            intermediate_locked = intermediate_locked and still_locked
            intermediate_navigation = (
                intermediate_navigation
                and step_state.get("unlocked_labs", []) == initial_expected
            )
            evidence.append(
                f"intermediate-{question['id']}="
                + ("locked" if still_locked else "unlocked")
            )

    final_response = client.get("/api/state")
    later_response = client.get(f"/api/knowledge/{later_id}")
    final_state = final_response.json()
    later_view = later_response.json()
    final_unlocked = final_state.get("unlocked_labs", [])
    completed = final_state.get("completed_labs", [])
    expected_after_first = expected_unlocked({first_id})
    persisted = json.loads(
        (workspace / ".coursekit" / "state.json").read_text(encoding="utf-8")
    )
    final_navigation = (
        final_response.status_code == 200
        and final_unlocked == expected_after_first
        and all(
            str(lab["id"]) not in final_unlocked
            for lab in labs
            if str(lab["id"]) not in expected_after_first
        )
    )
    checks["chapter_navigation_gate"] = (
        initial_navigation
        and before_code_response.status_code == 200
        and before_code_unlocked == initial_expected
        and intermediate_navigation
        and final_navigation
    )
    checks["knowledge_gate"] = knowledge_passed and is_public_knowledge_view(
        later_view
    )
    first_grades = final_state.get("grades", {}).get(first_id, {})
    verified_questions = all(
        first_grades.get(str(question["id"]), {}).get("public") is True
        and first_grades.get(str(question["id"]), {}).get("verified") is True
        for question in first_questions
    )
    first_points = sum(int(question.get("points", 1)) for question in first_questions)
    total_points = sum(
        int(question.get("points", 1))
        for lab in labs
        for question in lab.get("questions", [])
        if isinstance(question, dict)
    )
    checks["coding_verification_gate"] = (
        submit_passed
        and intermediate_locked
        and first_id not in before_code_state.get("completed_labs", [])
        and first_id in completed
        and later_response.status_code == 200
        and later_view.get("available") is True
        and verified_questions
        and final_state.get("score") == first_points
        and final_state.get("total_points") == total_points
    )
    persisted_fields = (
        "version",
        "course_id",
        "curriculum_id",
        "knowledge",
        "grades",
        "completed_labs",
        "checkpoints",
        "git_baseline_commit",
        "updated_at",
    )
    checks["shared_progress_state"] = (
        all(persisted.get(key) == final_state.get(key) for key in persisted_fields)
        and persisted.get("grades") == final_state.get("grades")
        and verified_questions
        and final_state.get("score") == first_points
    )
    checks["api_workflow"] = all(
        checks[key] is True
        for key in (
            "chapter_navigation_gate",
            "knowledge_gate",
            "code_file_gate",
            "coding_verification_gate",
            "shared_progress_state",
        )
    )

checks["output"] = ", ".join(evidence)
print("COURSEKIT_WEB_PROGRESSION=" + json.dumps(checks, ensure_ascii=False))
"""


def web_progression_workflow(
    project: Path,
    platform_python: str,
) -> dict[str, Any]:
    """Exercise Web progression through the generated Runner's public APIs.

    The verifier works in a disposable learner copy so proving progression does
    not unlock, grade, or dirty the generated repository being audited.
    """

    failed: dict[str, Any] = {
        "api_workflow": False,
        "chapter_navigation_gate": False,
        "knowledge_gate": False,
        "code_file_gate": False,
        "coding_verification_gate": False,
        "shared_progress_state": False,
        "output": "",
    }
    with tempfile.TemporaryDirectory(prefix="coursekit-web-progression-") as raw:
        root = Path(raw)
        workspace = root / "labs"
        course_root = root / "platform" / "course"
        shutil.copytree(
            project / "labs",
            workspace,
            ignore=shutil.ignore_patterns(
                ".venv",
                ".coursekit",
                ".pytest_cache",
                "__pycache__",
                "*.egg-info",
            ),
        )
        shutil.copytree(project / "platform" / "course", course_root)
        runner_environment = verification_subprocess_env()
        runner_environment.update(
            {
                "PYTHONPATH": str(project / "platform"),
                "COURSEKIT_COURSE_DIR": str(course_root),
                "COURSEKIT_WORKSPACE_DIR": str(workspace),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            }
        )
        completed = run(
            [platform_python, "-c", _WEB_PROGRESSION_PROBE],
            cwd=project / "platform",
            env=runner_environment,
            timeout=300,
        )
    marker = "COURSEKIT_WEB_PROGRESSION="
    if completed.returncode:
        failed["output"] = (completed.stdout + completed.stderr)[-8000:]
        return failed
    rendered = next(
        (
            line.removeprefix(marker)
            for line in reversed(completed.stdout.splitlines())
            if line.startswith(marker)
        ),
        None,
    )
    if rendered is None:
        failed["output"] = (
            "functional API probe returned no result marker:\n"
            + (completed.stdout + completed.stderr)[-8000:]
        )
        return failed
    try:
        result = json.loads(rendered)
    except json.JSONDecodeError as error:
        failed["output"] = f"invalid functional API result: {error}"
        return failed
    if not isinstance(result, dict):
        failed["output"] = "functional API result must be an object"
        return failed
    schema_error = web_progression_schema_error(result)
    if schema_error is not None:
        failed["output"] = schema_error
        return failed
    return result


def cli_learning_workflow(project: Path, learner_python: str) -> tuple[bool, str]:
    manifest = json.loads((project / "labs" / "manifest.json").read_text(encoding="utf-8"))
    labs = [item for item in manifest.get("labs", []) if isinstance(item, dict)]
    if not labs:
        return False, "learner manifest has no graded Labs"
    first = labs[0]
    lab_id = str(first["id"])
    question_id = str(first["questions"][0]["id"])
    with tempfile.TemporaryDirectory(prefix="coursekit-cli-workflow-") as raw:
        root = Path(raw)
        shutil.copytree(
            project / "labs",
            root / "labs",
            ignore=shutil.ignore_patterns(".venv", ".coursekit", ".pytest_cache", "__pycache__", "*.egg-info"),
        )
        shutil.copytree(project / "platform" / "course", root / "platform" / "course")
        environment = python_env(root)
        command = [learner_python, "-m", "coursekit.cli"]
        evidence: list[str] = []

        for git_command in (
            ["git", "init", "-q"],
            ["git", "add", "."],
            [
                "git",
                "-c",
                "user.name=CourseKit",
                "-c",
                "user.email=coursekit@localhost",
                "commit",
                "-q",
                "-m",
                "baseline",
            ],
        ):
            completed = run(git_command, cwd=root)
            if completed.returncode:
                return False, completed.stdout + completed.stderr
        port = _loopback_port()
        runner_url = f"http://127.0.0.1:{port}"
        environment["COURSEKIT_RUNNER_URL"] = runner_url
        runner_environment = verification_subprocess_env()
        runner_environment.update(
            {
                "PYTHONPATH": str(project / "platform"),
                "COURSEKIT_COURSE_DIR": str(root / "platform" / "course"),
                "COURSEKIT_WORKSPACE_DIR": str(root / "labs"),
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            }
        )
        runner_log = (root / "runner.log").open("w+", encoding="utf-8")
        runner = subprocess.Popen(
            [
                environment_python(project, "platform"),
                "-m",
                "uvicorn",
                "runner.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=project / "platform",
            env=runner_environment,
            text=True,
            stdout=runner_log,
            stderr=subprocess.STDOUT,
        )
        try:
            if not _wait_for_runner(runner, runner_url):
                runner_log.flush()
                runner_log.seek(0)
                return False, "temporary Runner failed to start:\n" + runner_log.read()

            locked = run([*command, "test", question_id], cwd=root / "labs", env=environment)
            evidence.append(f"locked={locked.returncode}")
            if locked.returncode != 4:
                return False, "expected locked test return code 4; " + ", ".join(evidence)

            knowledge = json.loads(
                (root / "labs" / "_course" / "knowledge.json").read_text(encoding="utf-8")
            )
            for unlock_id in ("lab00", lab_id):
                unlocked = run(
                    [*command, "unlock", unlock_id],
                    cwd=root / "labs",
                    env=environment,
                    input_text=_quiz_answers(knowledge, unlock_id),
                )
                evidence.append(f"unlock-{unlock_id}={unlocked.returncode}")
                if unlocked.returncode:
                    return False, unlocked.stdout + unlocked.stderr + "\n" + ", ".join(evidence)

            wrong_test_target = run(
                [*command, "test", lab_id], cwd=root / "labs", env=environment
            )
            evidence.append(f"test-lab-rejected={wrong_test_target.returncode}")
            if wrong_test_target.returncode != 2:
                return False, "course test must reject a Lab id; " + ", ".join(evidence)

            reference_lab = root / "platform" / "course" / "reference" / lab_id
            shutil.copytree(reference_lab, root / "labs" / lab_id, dirs_exist_ok=True)
            for operation, item in (("test", question_id), ("grade", lab_id), ("submit", lab_id)):
                completed = run([*command, operation, item], cwd=root / "labs", env=environment)
                evidence.append(f"{operation}={completed.returncode}")
                if completed.returncode:
                    return False, completed.stdout + completed.stderr + "\n" + ", ".join(evidence)

            early_checkpoint = run(
                [*command, "checkpoint", lab_id], cwd=root / "labs", env=environment
            )
            evidence.append(f"checkpoint-before-commit={early_checkpoint.returncode}")
            if early_checkpoint.returncode != 5:
                return False, "checkpoint accepted an uncommitted Lab; " + ", ".join(evidence)

            for git_command in (
                ["git", "add", "--", f"labs/{lab_id}"],
                [
                    "git",
                    "-c",
                    "user.name=CourseKit",
                    "-c",
                    "user.email=coursekit@localhost",
                    "commit",
                    "-q",
                    "-m",
                    f"finish-{lab_id}",
                    "--",
                    f"labs/{lab_id}",
                ],
            ):
                completed = run(git_command, cwd=root)
                if completed.returncode:
                    return False, completed.stdout + completed.stderr
            checkpoint = run([*command, "checkpoint", lab_id], cwd=root / "labs", env=environment)
            scored = run([*command, "score"], cwd=root / "labs", env=environment)
            evidence.extend((f"checkpoint={checkpoint.returncode}", f"score={scored.returncode}"))
            if checkpoint.returncode or scored.returncode:
                return False, checkpoint.stdout + checkpoint.stderr + scored.stdout + scored.stderr
            state = json.loads(
                (root / "labs" / ".coursekit" / "state.json").read_text(encoding="utf-8")
            )
            head = run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
            snapshot = state.get("checkpoints", {}).get(lab_id)
            passed = (
                lab_id in state.get("completed_labs", [])
                and isinstance(snapshot, dict)
                and snapshot.get("commit") == head
                and question_id in snapshot.get("verified_questions", [])
                and question_id in snapshot.get("test_identity", {})
                and isinstance(snapshot.get("score"), dict)
                and bool(snapshot.get("created_at"))
            )
            return passed, ", ".join(evidence)
        finally:
            _stop_process(runner)
            runner_log.close()


def verify(project: Path, *, full: bool = False) -> dict[str, Any]:
    root = project.resolve()
    platform = root / "platform"
    platform_python = environment_python(root, "platform")
    learner_python = environment_python(root, "labs")
    public, hidden = pytest_targets(root)
    reference_public = reference_public_targets(root)
    compiler = run(
        [platform_python, "-m", "coursekit.cli", "check", "course/source", "course"],
        cwd=platform,
    )
    starter_red, starter_red_output = starter_red_check(root, learner_python)
    examples_green, examples_output = runnable_lesson_examples(
        root, platform_python
    )
    reference = run(
        [platform_python, "-m", "pytest", "-q", *reference_public, *hidden],
        cwd=platform,
        env=python_env(root, reference=True),
        timeout=300,
    )
    cli = run(
        learner_cli_command(root),
        cwd=root / "labs",
        env=python_env(root),
    )
    runner = run(
        [
            platform_python,
            "-c",
            (
                "from fastapi.testclient import TestClient; "
                "from runner.app import app; "
                "r=TestClient(app).get('/api/health'); "
                "assert r.status_code == 200 and r.json()['status'] == 'ok'"
            ),
        ],
        cwd=platform,
        env={**os.environ, "PYTHONPATH": str(platform)},
    )
    commits = run(["git", "rev-list", "--count", "HEAD"], cwd=root)
    cli_workflow, cli_workflow_output = cli_learning_workflow(root, learner_python)
    web_progression_result = web_progression_workflow(root, platform_python)
    if isinstance(web_progression_result, dict):
        web_progression = web_progression_result
    else:
        web_progression = {
            key: False for key in WEB_PROGRESSION_BOOLEAN_CHECKS
        }
        web_progression["output"] = (
            web_progression_schema_error(web_progression_result)
            or "invalid web_progression result"
        )
    report: dict[str, Any] = {
        "compiler_check": compiler.returncode == 0,
        "starter_red": starter_red and bool(public),
        "reference_green": reference.returncode == 0 and bool(reference_public) and bool(hidden),
        "lesson_examples_green": examples_green,
        "cli_smoke": cli.returncode == 0 and "unlock" in cli.stdout,
        "cli_workflow": cli_workflow,
        "runner_smoke": runner.returncode == 0,
        "web_progression": web_progression,
        "privacy_boundary": privacy_boundary(root),
        "starter_red_output": starter_red_output,
        "lesson_examples_output": examples_output,
        "cli_workflow_output": cli_workflow_output,
    }
    if full:
        node = run(["npm", "test"], cwd=root, timeout=300)
        lint = run(["npm", "run", "lint"], cwd=root, timeout=180)
        typescript = run(
            ["npm", "exec", "--offline", "--", "tsc", "--noEmit"],
            cwd=platform,
            timeout=180,
        )
        report["full_node_runner"] = node.returncode == 0
        web_progression["generated_project_tests"] = node.returncode == 0
        report["lint"] = lint.returncode == 0
        report["typescript"] = typescript.returncode == 0
        report["full_output"] = (
            node.stdout
            + node.stderr
            + lint.stdout
            + lint.stderr
            + typescript.stdout
            + typescript.stderr
        )[-8000:]
    # Audit the final filesystem only after build, lint, and TypeScript have
    # had a chance to reveal unignored caches or other mutations.
    residue = scan_residue(root)
    git_status = run(["git", "status", "--porcelain"], cwd=root)
    report["residue_free"] = not residue
    report["symlink_free"] = symlink_free(root)
    report["git_baseline"] = (
        commits.returncode == 0
        and int(commits.stdout.strip() or 0) >= 1
        and git_status.returncode == 0
        and not git_status.stdout.strip()
    )
    report["residue_files"] = residue
    report["git_status"] = git_status.stdout.splitlines()
    detail_keys = {
        "residue_files",
        "git_status",
        "cli_workflow_output",
        "starter_red_output",
        "lesson_examples_output",
        "full_output",
        "passed",
    }
    top_level_passed = all(
        value is True
        for key, value in report.items()
        if key not in detail_keys and key != "web_progression"
    )
    progression_schema_error = web_progression_schema_error(
        web_progression,
        require_generated_tests=full,
    )
    web_progression_passed = (
        progression_schema_error is None
        and all(
            web_progression[key] is True
            for key in WEB_PROGRESSION_BOOLEAN_CHECKS
        )
        and (
            not full
            or web_progression["generated_project_tests"] is True
        )
    )
    report["passed"] = top_level_passed and web_progression_passed
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args(argv)
    try:
        report = verify(args.project, full=args.full)
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        rendered = json.dumps(
            {"passed": False, "error": str(error)},
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        if args.json_path:
            args.json_path.parent.mkdir(parents=True, exist_ok=True)
            args.json_path.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
