from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

import runner.app as runner_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    workspace = tmp_path / "labs"
    course_root = tmp_path / "course"
    shutil.copytree(
        runner_app.WORKSPACE_ROOT,
        workspace,
        ignore=shutil.ignore_patterns(".venv", ".coursekit", ".pytest_cache", "__pycache__", "*.egg-info"),
    )
    shutil.copytree(
        runner_app.COURSE_ROOT,
        course_root,
        ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"),
    )
    monkeypatch.setattr(runner_app, "WORKSPACE_ROOT", workspace)
    monkeypatch.setattr(runner_app, "COURSE_ROOT", course_root)
    return TestClient(runner_app.app)


def test_health_and_runtime_course(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    payload = client.get("/api/course").json()
    assert payload["manifest"]["labs"]
    assert "reference_root" not in payload["manifest"]


def _coding_request() -> tuple[dict[str, str], dict[str, object]]:
    course = runner_app.manifest(internal=True)
    lab = course["labs"][0]
    question = lab["questions"][0]
    return {
        "lab_id": str(lab["id"]),
        "question_id": str(question["id"]),
    }, question


def _preparatory_unit_ids(course: dict[str, object]) -> tuple[str, ...]:
    units = course.get("preparatory_units")
    if isinstance(units, list):
        return tuple(
            str(unit["id"])
            for unit in units
            if isinstance(unit, dict) and unit.get("id")
        )
    foundation = course.get("foundations")
    if isinstance(foundation, dict) and foundation.get("id"):
        return (str(foundation["id"]),)
    raise AssertionError("manifest must declare preparatory_units or foundations")


def _write_mastered_state(*lab_ids: str) -> None:
    knowledge = json.loads(
        (runner_app.COURSE_ROOT / "knowledge.json").read_text(encoding="utf-8")
    )
    state = runner_app.initial_state()
    for lab_id in lab_ids:
        state["knowledge"][lab_id] = {
            str(item["id"]): True for item in knowledge["labs"][lab_id]["questions"]
        }
    runner_app.write_state(state)


def _set_question_file(path: str) -> None:
    course = runner_app.manifest(internal=True)
    course["labs"][0]["questions"][0]["file"] = path
    (runner_app.COURSE_ROOT / "manifest.json").write_text(
        json.dumps(course, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_content_and_question_scoped_file_gate(client: TestClient) -> None:
    assert client.get("/api/content/lab01").status_code == 200
    request, question = _coding_request()
    preparatory_ids = _preparatory_unit_ids(runner_app.manifest(internal=True))

    assert client.get("/api/file", params=request).status_code == 409
    assert client.put(
        "/api/file", json={**request, "content": "pass\n"}
    ).status_code == 409

    _write_mastered_state(*preparatory_ids)
    assert client.get("/api/file", params=request).status_code == 409
    assert client.put(
        "/api/file", json={**request, "content": "pass\n"}
    ).status_code == 409

    _write_mastered_state(*preparatory_ids, request["lab_id"])
    current = client.get("/api/file", params=request)
    assert current.status_code == 200
    assert set(current.json()) == {"path", "content"}
    sentinel = "COURSEKIT_SENTINEL = '模板写回验证'\n"
    saved = client.put(
        "/api/file", json={**request, "content": sentinel}
    )
    assert saved.status_code == 200
    assert saved.json() == {"path": str(question["file"]), "status": "saved"}
    assert client.get("/api/file", params=request).json()["content"] == sentinel
    assert (runner_app.WORKSPACE_ROOT / str(question["file"])).read_bytes() == sentinel.encode(
        "utf-8"
    )


def test_file_api_rejects_legacy_paths_and_unknown_questions(client: TestClient) -> None:
    request, _question = _coding_request()
    assert client.get(
        "/api/file", params={"path": "lab01/solution.py"}
    ).status_code == 422
    assert client.put(
        "/api/file", json={"path": "lab01/solution.py", "content": "pass\n"}
    ).status_code == 422
    assert client.put(
        "/api/file",
        json={**request, "path": "lab01/solution.py", "content": "pass\n"},
    ).status_code == 422
    assert client.get(
        "/api/file", params={"lab_id": "missing", "question_id": "missing.q1"}
    ).status_code == 404
    assert client.get(
        "/api/file", params={"lab_id": "lab01", "question_id": "missing.q1"}
    ).status_code == 404
    assert client.put(
        "/api/file",
        json={
            "lab_id": "lab01",
            "question_id": "missing.q1",
            "content": "pass\n",
        },
    ).status_code == 404


def test_file_api_rejects_unsafe_manifest_path(client: TestClient) -> None:
    request, _question = _coding_request()
    course = runner_app.manifest(internal=True)
    _write_mastered_state(*_preparatory_unit_ids(course), request["lab_id"])
    _set_question_file("../README.md")

    assert client.get("/api/file", params=request).status_code == 400
    assert client.put(
        "/api/file", json={**request, "content": "pass\n"}
    ).status_code == 400

    _set_question_file(str((runner_app.WORKSPACE_ROOT / "lab01/solution.py").resolve()))
    assert client.get("/api/file", params=request).status_code == 400
    assert client.put(
        "/api/file", json={**request, "content": "pass\n"}
    ).status_code == 400


def test_file_api_distinguishes_missing_and_existing_non_regular_targets(
    client: TestClient,
) -> None:
    request, _question = _coding_request()
    course = runner_app.manifest(internal=True)
    _write_mastered_state(*_preparatory_unit_ids(course), request["lab_id"])

    _set_question_file("lab01/does-not-exist.py")
    assert client.get("/api/file", params=request).status_code == 404
    assert client.put(
        "/api/file", json={**request, "content": "pass\n"}
    ).status_code == 404

    _set_question_file("lab01")
    assert client.get("/api/file", params=request).status_code == 400
    assert client.put(
        "/api/file", json={**request, "content": "pass\n"}
    ).status_code == 400


def test_file_api_rejects_final_symlink(client: TestClient, tmp_path: Path) -> None:
    request, _question = _coding_request()
    course = runner_app.manifest(internal=True)
    _write_mastered_state(*_preparatory_unit_ids(course), request["lab_id"])
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = True\n", encoding="utf-8")
    target = runner_app.WORKSPACE_ROOT / "lab01" / "escape.py"
    try:
        target.symlink_to(outside)
    except OSError as error:  # pragma: no cover - platform permission boundary
        pytest.skip(f"symlinks unavailable: {error}")
    _set_question_file("lab01/escape.py")
    assert client.get("/api/file", params=request).status_code == 400
    assert client.put(
        "/api/file", json={**request, "content": "SECRET = False\n"}
    ).status_code == 400


def test_file_api_rejects_intermediate_symlink(client: TestClient, tmp_path: Path) -> None:
    request, _question = _coding_request()
    course = runner_app.manifest(internal=True)
    _write_mastered_state(*_preparatory_unit_ids(course), request["lab_id"])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "solution.py").write_text("SECRET = True\n", encoding="utf-8")
    link = runner_app.WORKSPACE_ROOT / "linked-lab"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:  # pragma: no cover - platform permission boundary
        pytest.skip(f"symlinks unavailable: {error}")
    _set_question_file("linked-lab/solution.py")

    assert client.get("/api/file", params=request).status_code == 400
    assert client.put(
        "/api/file", json={**request, "content": "SECRET = False\n"}
    ).status_code == 400


def test_file_api_rejects_non_regular_targets(client: TestClient) -> None:
    request, _question = _coding_request()
    course = runner_app.manifest(internal=True)
    _write_mastered_state(*_preparatory_unit_ids(course), request["lab_id"])
    if not hasattr(os, "mkfifo"):  # pragma: no cover - Windows
        pytest.skip("FIFO creation is unavailable")
    target = runner_app.WORKSPACE_ROOT / "lab01" / "blocked.fifo"
    try:
        os.mkfifo(target)
    except OSError as error:  # pragma: no cover - platform permission boundary
        pytest.skip(f"FIFO creation unavailable: {error}")
    _set_question_file("lab01/blocked.fifo")
    response = client.get("/api/file", params=request)
    assert response.status_code == 400
    assert "regular file" in response.text
    written = client.put(
        "/api/file", json={**request, "content": "pass\n"}
    )
    assert written.status_code == 400
    assert "regular file" in written.text


def test_file_api_limits_utf8_bytes_not_python_characters(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, question = _coding_request()
    course = runner_app.manifest(internal=True)
    _write_mastered_state(*_preparatory_unit_ids(course), request["lab_id"])
    target = runner_app.WORKSPACE_ROOT / str(question["file"])
    before = target.read_bytes()
    monkeypatch.setattr(runner_app, "MAX_FILE_BYTES", 8)

    response = client.put(
        "/api/file", json={**request, "content": "你你你"}
    )

    assert response.status_code == 422
    assert target.read_bytes() == before


    accepted = client.put(
        "/api/file", json={**request, "content": "你你"}
    )
    assert accepted.status_code == 200
    assert target.read_bytes() == "你你".encode("utf-8")


def test_runner_enforces_unlock_then_runs_public_and_verified_tests(client: TestClient) -> None:
    course = runner_app.manifest(internal=True)
    lab = course["labs"][0]
    question = lab["questions"][0]
    request = {"lab_id": lab["id"], "question_id": question["id"]}

    assert client.post("/api/run", json={**request, "mode": "public"}).status_code == 409

    knowledge = json.loads((runner_app.COURSE_ROOT / "knowledge.json").read_text(encoding="utf-8"))
    state = runner_app.initial_state()
    for lab_id in (*_preparatory_unit_ids(course), lab["id"]):
        state["knowledge"][lab_id] = {
            str(item["id"]): True for item in knowledge["labs"][lab_id]["questions"]
        }
    runner_app.write_state(state)

    learner_file = runner_app.WORKSPACE_ROOT / question["file"]
    reference_file = runner_app.COURSE_ROOT / "reference" / question["file"]
    learner_file.write_bytes(reference_file.read_bytes())

    public = client.post("/api/run", json={**request, "mode": "public"})
    assert public.status_code == 200, public.text
    assert public.json()["passed"] is True
    verified = client.post("/api/run", json={**request, "mode": "submit"})
    assert verified.status_code == 200, verified.text
    assert verified.json()["passed"] is True
    assert verified.json()["score_summary"]["verified"] == int(question["points"])


def test_submit_hides_all_private_test_diagnostics(client: TestClient) -> None:
    course = runner_app.manifest(internal=True)
    lab = course["labs"][0]
    question = lab["questions"][0]
    request = {"lab_id": lab["id"], "question_id": question["id"]}

    knowledge = json.loads((runner_app.COURSE_ROOT / "knowledge.json").read_text(encoding="utf-8"))
    state = runner_app.initial_state()
    for lab_id in (*_preparatory_unit_ids(course), lab["id"]):
        state["knowledge"][lab_id] = {
            str(item["id"]): True for item in knowledge["labs"][lab_id]["questions"]
        }
    runner_app.write_state(state)

    learner_file = runner_app.WORKSPACE_ROOT / question["file"]
    reference_file = runner_app.COURSE_ROOT / "reference" / question["file"]
    learner_file.write_bytes(reference_file.read_bytes())

    hidden_relative = "hidden/private_contract_test.py"
    hidden_selector = f"{hidden_relative}::test_secret_contract"
    question["tests"]["hidden"] = [hidden_selector]
    (runner_app.COURSE_ROOT / "manifest.json").write_text(
        json.dumps(course, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    hidden_file = runner_app.COURSE_ROOT / hidden_relative
    hidden_file.parent.mkdir(parents=True, exist_ok=True)
    hidden_file.write_text(
        "def test_secret_contract():\n"
        "    assert False, 'PRIVATE_ASSERTION_BODY'\n",
        encoding="utf-8",
    )

    response = client.post("/api/run", json={**request, "mode": "submit"})
    assert response.status_code == 200, response.text
    assert response.json()["passed"] is False
    assert "Hidden verification failed (1 private target(s) checked)." in response.json()["output"]
    for private_detail in (
        str(runner_app.COURSE_ROOT),
        "private_contract_test.py",
        "test_secret_contract",
        "PRIVATE_ASSERTION_BODY",
        "assert False",
    ):
        assert private_detail not in response.text
    assert response.json()["state"]["grades"][lab["id"]][question["id"]]["public"] is True
