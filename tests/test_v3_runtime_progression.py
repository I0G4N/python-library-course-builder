from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from typing import Any

from fastapi.testclient import TestClient
import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
PLATFORM_ROOT = SKILL_ROOT / "assets/course-template/platform"
sys.path.insert(0, str(PLATFORM_ROOT))

import runner.app as runner_app  # noqa: E402
from support.coursekit import course as course_helpers  # noqa: E402
from support.coursekit import progress  # noqa: E402


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _quiz(unit_id: str) -> dict[str, Any]:
    return {
        "id": f"{unit_id}.k01",
        "kind": "execution_trace",
        "prompt": f"Master {unit_id}?",
        "choices": [
            {"id": "yes", "text": "Yes", "feedback": "Correct."},
            {"id": "no", "text": "No", "feedback": "Try again."},
        ],
        "answer_id": "yes",
        "explanation": f"{unit_id} is mastered by the first choice.",
    }


def _formal_question(lab_id: str, points: int) -> dict[str, Any]:
    return {
        "id": f"{lab_id}.q1",
        "title": f"{lab_id} question",
        "file": f"{lab_id}/answer.py",
        "points": points,
        "timeout_seconds": 5,
        "source_policy": {
            "local_root": lab_id,
            "required_imports": [],
            "forbidden_imports": [],
            "prior_mini_modules": [],
            "forbidden_course_roots": [],
        },
        "tests": {"public": [], "hidden": []},
    }


def _v3_manifest(curriculum_id: str = "runtime-course-v3-aaaaaaaaaaaa") -> dict[str, Any]:
    return {
        "schema_version": 3,
        "course_id": "runtime-course",
        "curriculum_id": curriculum_id,
        "compatible_curriculum_ids": [],
        "title": "Runtime course",
        "preparatory_units": [
            {
                "id": "lab00",
                "title": "Orientation",
                "depends_on": None,
                "graded": False,
                "unit_type": "orientation",
                "category": "python",
            },
            {
                "id": "prep01",
                "title": "Python preparation",
                "depends_on": "lab00",
                "graded": False,
                "unit_type": "preparatory",
                "category": "python",
            },
            {
                "id": "prep02",
                "title": "Library preparation",
                "depends_on": "prep01",
                "graded": False,
                "unit_type": "preparatory",
                "category": "library",
            },
        ],
        "labs": [
            {
                "id": "lab01",
                "title": "Lab 01",
                "depends_on": "prep02",
                "questions": [_formal_question("lab01", 2)],
            },
            {
                "id": "lab02",
                "title": "Lab 02",
                "depends_on": "lab01",
                "questions": [_formal_question("lab02", 3)],
            },
        ],
    }


def _v2_manifest() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "course_id": "runtime-course",
        "curriculum_id": "runtime-course-v2",
        "compatible_curriculum_ids": [],
        "title": "Runtime course",
        "foundations": {"id": "lab00", "title": "Foundation", "graded": False},
        "labs": [
            {
                "id": "lab01",
                "title": "Lab 01",
                "depends_on": "lab00",
                "questions": [_formal_question("lab01", 2)],
            },
            {
                "id": "lab02",
                "title": "Lab 02",
                "depends_on": "lab01",
                "questions": [_formal_question("lab02", 3)],
            },
        ],
    }


def _knowledge(manifest: dict[str, Any]) -> dict[str, Any]:
    units = (
        manifest["preparatory_units"]
        if manifest["schema_version"] == 3
        else [manifest["foundations"]]
    )
    units = [*units, *manifest["labs"]]
    return {
        "schema_version": manifest["schema_version"],
        "curriculum_id": manifest["curriculum_id"],
        "labs": {
            str(unit["id"]): {
                "title": str(unit["title"]),
                "questions": [_quiz(str(unit["id"]))],
            }
            for unit in units
        },
    }


def _runtime_tree(
    tmp_path: Path,
    manifest: dict[str, Any],
    *,
    copy_cli: bool = False,
) -> tuple[Path, Path]:
    workspace = tmp_path / "labs"
    course_root = tmp_path / "course"
    workspace.mkdir()
    course_root.mkdir()
    _write_json(workspace / "manifest.json", manifest)
    _write_json(course_root / "manifest.json", manifest)
    knowledge = _knowledge(manifest)
    _write_json(workspace / "_course/knowledge.json", knowledge)
    _write_json(course_root / "knowledge.json", knowledge)
    preparatory = manifest.get("preparatory_units", [])
    _write_json(
        course_root / "content.json",
        {
            "schema_version": manifest["schema_version"],
            "preparatory_units": [
                {"id": unit["id"], "title": unit["title"], "lesson": "prep"}
                for unit in preparatory
            ],
            "foundations": manifest.get("foundations"),
            "labs": [
                {"id": lab["id"], "title": lab["title"], "lesson": "lab"}
                for lab in manifest["labs"]
            ],
        },
    )
    for lab in manifest["labs"]:
        path = workspace / str(lab["questions"][0]["file"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def answer():\n    return 1\n", encoding="utf-8")
    if copy_cli:
        package = workspace / "_course/coursekit"
        shutil.copytree(PLATFORM_ROOT / "support/coursekit", package)
        for name in ("execution.py", "pytest_bootstrap.py"):
            shutil.copy2(PLATFORM_ROOT / "runner" / name, package / name)
    return workspace, course_root


def _configure_progress(
    monkeypatch: pytest.MonkeyPatch,
    workspace: Path,
) -> None:
    monkeypatch.setattr(course_helpers, "MANIFEST_PATH", workspace / "manifest.json")
    monkeypatch.setattr(progress, "STATE_PATH", workspace / ".coursekit/state.json")
    monkeypatch.setattr(progress, "KNOWLEDGE_PATH", workspace / "_course/knowledge.json")
    monkeypatch.setattr(progress, "git_head", lambda: None)


def _master(state: dict[str, Any], unit_id: str) -> None:
    state.setdefault("knowledge", {})[unit_id] = {f"{unit_id}.k01": True}


def test_v3_progression_unlocks_one_knowledge_dependency_at_a_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, _course_root = _runtime_tree(tmp_path, _v3_manifest())
    _configure_progress(monkeypatch, workspace)
    state = progress.initial_state()

    assert [
        unit_id
        for unit_id in ("lab00", "prep01", "prep02", "lab01", "lab02")
        if progress.navigable(unit_id, state)
    ] == ["lab00"]

    _master(state, "lab00")
    assert progress.navigable("prep01", state) is True
    assert progress.navigable("prep02", state) is False
    assert progress.navigable("lab01", state) is False

    _master(state, "prep01")
    assert progress.navigable("prep02", state) is True
    assert progress.navigable("lab01", state) is False

    _master(state, "prep02")
    assert progress.navigable("lab01", state) is True
    assert progress.navigable("lab02", state) is False
    with pytest.raises(ValueError, match="prep01 is not a graded Lab"):
        progress.record_grade(
            "prep01", ["prep01.q1"], verified=True, passed=True
        )

    _master(state, "lab01")
    assert progress.navigable("lab02", state) is False
    progress.write_state(state)
    progress.record_grade("lab01", ["lab01.q1"], verified=True, passed=True)
    assert progress.navigable("lab02") is True
    assert progress.score() == {"public": 0, "verified": 2, "total": 5}


def test_v2_keeps_lab01_initially_navigable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, course_root = _runtime_tree(
        tmp_path, _v2_manifest(), copy_cli=True
    )
    _configure_progress(monkeypatch, workspace)
    state = progress.initial_state()

    assert progress.navigable("lab00", state) is True
    assert progress.navigable("lab01", state) is True
    assert progress.navigable("lab02", state) is False
    assert progress.gate_reasons("lab00", state) == [
        "run `course unlock lab00` first"
    ]

    grade = _run_cli(workspace, "grade", "lab00")
    assert grade.returncode == 2
    assert "unknown graded Lab: lab00" in grade.stderr
    assert "knowledge-only" not in grade.stderr

    with _runner_client(monkeypatch, workspace, course_root) as client:
        request = {"lab_id": "lab00", "question_id": "lab00.q1"}
        assert client.get("/api/file", params=request).status_code == 404
        assert client.put(
            "/api/file", json={**request, "content": "unchanged\n"}
        ).status_code == 404
        assert client.post(
            "/api/run", json={**request, "mode": "public"}
        ).status_code == 404


def _answer(client: TestClient, unit_id: str) -> Any:
    return client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": unit_id,
            "question_id": f"{unit_id}.k01",
            "choice_id": "yes",
        },
    )


def _runner_client(
    monkeypatch: pytest.MonkeyPatch,
    workspace: Path,
    course_root: Path,
) -> TestClient:
    monkeypatch.setattr(runner_app, "WORKSPACE_ROOT", workspace)
    monkeypatch.setattr(runner_app, "COURSE_ROOT", course_root)
    monkeypatch.setattr(runner_app, "_RUN_LOCK", threading.Lock())
    monkeypatch.setattr(runner_app, "git_head", lambda: None)
    return TestClient(runner_app.create_app())


def test_runner_persists_prep_progress_and_isolates_readiness_curricula(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, course_root = _runtime_tree(tmp_path, _v3_manifest())
    with _runner_client(monkeypatch, workspace, course_root) as client:
        initial = client.get("/api/state")
        assert initial.json()["unlocked_labs"] == ["lab00"]
        assert initial.json()["completed_preparatory_units"] == []
        for unit_id, expected in (
            ("lab00", ["lab00", "prep01"]),
            ("prep01", ["lab00", "prep01", "prep02"]),
            ("prep02", ["lab00", "prep01", "prep02", "lab01"]),
        ):
            response = _answer(client, unit_id)
            assert response.status_code == 200, response.text
            assert response.json()["state"]["unlocked_labs"] == expected
        state = client.get("/api/state").json()
        assert state["completed_preparatory_units"] == [
            "lab00",
            "prep01",
            "prep02",
        ]
        assert state["completed_labs"] == []
        assert state["score"] == 0
        assert state["total_points"] == 5

    with _runner_client(monkeypatch, workspace, course_root) as restarted:
        persisted = restarted.get("/api/state").json()
        assert persisted["unlocked_labs"] == [
            "lab00",
            "prep01",
            "prep02",
            "lab01",
        ]
        assert persisted["knowledge"]["prep02"]["prep02.k01"] is True

        replacement = _v3_manifest("runtime-course-v3-bbbbbbbbbbbb")
        _write_json(workspace / "manifest.json", replacement)
        _write_json(course_root / "manifest.json", replacement)
        isolated = restarted.get("/api/state").json()
        assert isolated["curriculum_id"] == "runtime-course-v3-bbbbbbbbbbbb"
        assert isolated["knowledge"] == {}
        assert isolated["grades"] == {}
        assert isolated["completed_labs"] == []
        assert isolated["unlocked_labs"] == ["lab00"]


def test_runner_refuses_all_prep_file_and_execution_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, course_root = _runtime_tree(tmp_path, _v3_manifest())
    monkeypatch.setattr(
        runner_app,
        "read_workspace_text",
        lambda _parts: pytest.fail("prep attempted a workspace read"),
    )
    monkeypatch.setattr(
        runner_app,
        "write_workspace_text",
        lambda _parts, _content: pytest.fail("prep attempted a workspace write"),
    )
    monkeypatch.setattr(
        runner_app,
        "run_tests",
        lambda _request: pytest.fail("prep attempted to run pytest"),
    )
    with _runner_client(monkeypatch, workspace, course_root) as client:
        assert _answer(client, "lab00").status_code == 200
        request = {"lab_id": "prep01", "question_id": "prep01.q1"}
        assert client.get("/api/file", params=request).status_code == 409
        assert client.put(
            "/api/file", json={**request, "content": "forbidden\n"}
        ).status_code == 409
        assert client.post(
            "/api/run", json={**request, "mode": "public"}
        ).status_code == 409
        state = client.get("/api/state").json()
        assert state["grades"] == {}
        assert state["score"] == 0


def _run_cli(
    workspace: Path,
    *arguments: str,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(workspace / "_course"), str(workspace))
    )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "coursekit.cli", *arguments],
        cwd=workspace,
        env=environment,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_cli_orders_prep_unlocks_and_rejects_coding_commands(
    tmp_path: Path,
) -> None:
    workspace, _course_root = _runtime_tree(
        tmp_path, _v3_manifest(), copy_cli=True
    )

    blocked = _run_cli(workspace, "unlock", "prep01", input_text="1\n")
    assert blocked.returncode == 3
    assert "answer>" not in blocked.stdout

    for unit_id in ("lab00", "prep01", "prep02"):
        unlocked = _run_cli(workspace, "unlock", unit_id, input_text="1\n")
        assert unlocked.returncode == 0, unlocked.stdout + unlocked.stderr

    for command in ("test", "grade", "submit", "checkpoint"):
        refused = _run_cli(workspace, command, "prep01")
        assert refused.returncode == 2, refused.stdout + refused.stderr
        assert "knowledge-only" in refused.stderr

    scored = _run_cli(workspace, "score")
    assert scored.returncode == 0, scored.stdout + scored.stderr
    payload = json.loads(scored.stdout)
    assert payload["score"] == {"public": 0, "verified": 0, "total": 5}
    state = json.loads(
        (workspace / ".coursekit/state.json").read_text(encoding="utf-8")
    )
    assert state["completed_labs"] == []
    assert state["grades"] == {}
