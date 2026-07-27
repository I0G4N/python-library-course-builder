from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Iterator

from fastapi.testclient import TestClient
import pytest

from tests.course_v4_fixture import write_v4_fixture


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = (
    ROOT
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(SKILL_ROOT / "assets/course-template-v4"))

from v4_contract import load_v4_authoring, project_v4_authoring  # noqa: E402
import coursekit_runtime.execution as execution  # noqa: E402
import coursekit_runtime.runner as runner  # noqa: E402


def _write_projection(root: Path) -> tuple[Path, Path]:
    route_path, packages, _route = write_v4_fixture(root / "authoring")
    projection = project_v4_authoring(load_v4_authoring(route_path, packages))
    learner = root / "tiny-parser"
    author = root / "tiny-parser-author"
    for relative, value in projection.learner_files.items():
        destination = learner / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(value)
    for relative, value in projection.author_files.items():
        destination = author / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(value)
    static = learner / "coursekit_runtime" / "static"
    static.mkdir(parents=True)
    (static / "index.html").write_text(
        "<!doctype html><title>CourseKit v4</title><main>single port</main>",
        encoding="utf-8",
    )
    return learner, author


@pytest.fixture()
def runtime_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Path, Path]]:
    learner, author = _write_projection(tmp_path)
    monkeypatch.setattr(runner, "LEARNER_ROOT", learner)
    monkeypatch.setattr(runner, "AUTHOR_ROOT", author)
    monkeypatch.setattr(
        runner,
        "STATIC_ROOT",
        learner / "coursekit_runtime" / "static",
    )
    with TestClient(runner.create_app()) as client:
        yield client, learner, author


def _answer(
    client: TestClient,
    chapter_id: str,
    choice_id: str = "a",
) -> dict[str, object]:
    response = client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": chapter_id,
            "question_id": f"{chapter_id}.k1",
            "choice_id": choice_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_v4_single_port_content_course_and_unknown_api(
    runtime_client: tuple[TestClient, Path, Path],
) -> None:
    client, _learner, _author = runtime_client

    assert client.get("/api/health").json() == {"status": "ok"}
    course = client.get("/api/course")
    assert course.status_code == 200
    assert [item["id"] for item in course.json()["manifest"]["labs"]] == [
        "lab00",
        "lab01",
        "lab02",
    ]
    assert course.json()["manifest"]["labs"][2]["unit_type"] == "lab"
    assert course.json()["manifest"]["labs"][2]["kind"] == "capstone"
    assert course.json()["state"]["unlocked_labs"] == ["lab00"]

    content = client.get("/api/content/lab01")
    assert content.status_code == 200
    payload = content.json()
    assert payload["lesson_format"] == "tutorial-markdown-v1"
    assert payload["lesson"].startswith("# Lab 01")
    assert payload["terms"][0] == {
        "id": "term-1",
        "name": "boundary",
        "definition": "The caller-visible input and output edge.",
    }
    assert payload["sources"][0]["id"] == "python-json"
    assert payload["study_minutes"] == {"min": 25, "max": 40}
    assert payload["practice_links"] == [
        {
            "kind": "coding-question",
            "item_id": "lab01.q1",
            "title": "normalize",
        }
    ]
    assert "lesson_outline" not in payload

    index = client.get("/")
    assert index.status_code == 200
    assert "single port" in index.text
    deep_link = client.get("/chapters/lab01")
    assert deep_link.status_code == 200
    assert deep_link.headers["content-type"].startswith("text/html")
    assert "single port" in deep_link.text
    missing_api = client.get("/api/not-a-real-route")
    assert missing_api.status_code == 404
    assert missing_api.headers["content-type"].startswith("application/json")
    assert "CourseKit v4" not in missing_api.text


def test_v4_three_gates_save_public_tests_hidden_submit_and_progress(
    runtime_client: tuple[TestClient, Path, Path],
) -> None:
    client, learner, author = runtime_client
    request = {"lab_id": "lab01", "question_id": "lab01.q1"}

    assert client.get("/api/file", params=request).status_code == 409
    first = _answer(client, "lab00")
    assert first["correct"] is True
    assert "lab01" in first["state"]["unlocked_labs"]
    assert first["state"]["completed_preparatory_units"] == ["lab00"]
    assert client.get("/api/file", params=request).status_code == 409

    second = _answer(client, "lab01")
    assert second["correct"] is True
    current = client.get("/api/file", params=request)
    assert current.status_code == 200
    assert "NotImplementedError" in current.json()["content"]

    solution = (
        "def normalize(value: str) -> str:\n"
        "    return value.strip()\n"
    )
    saved = client.put("/api/file", json={**request, "content": solution})
    assert saved.status_code == 200
    assert (
        learner / "src/tiny_parser/normalize.py"
    ).read_text(encoding="utf-8") == solution

    public = client.post("/api/run", json={**request, "mode": "public"})
    assert public.status_code == 200, public.text
    assert public.json()["passed"] is True
    assert public.json()["score_summary"] == {
        "public": 1,
        "verified": 0,
        "total": 3,
    }
    assert "lab02" not in public.json()["state"]["unlocked_labs"]

    submitted = client.post("/api/run", json={**request, "mode": "submit"})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["passed"] is True
    assert submitted.json()["score_summary"] == {
        "public": 1,
        "verified": 1,
        "total": 3,
    }
    assert "lab01" in submitted.json()["state"]["completed_labs"]
    assert "lab02" in submitted.json()["state"]["unlocked_labs"]

    restored = client.get("/api/state").json()
    assert restored["grades"]["lab01"]["lab01.q1"] == {
        "public": True,
        "verified": True,
    }
    assert restored["course_contract_sha256"]

    hidden = author / "tests/hidden/lab01/test_normalize_hidden.py"
    hidden.write_text(
        "from tiny_parser.normalize import normalize\n\n"
        "def test_normalize_hidden():\n"
        "    assert normalize(' value ') == 'NEW_PRIVATE_EXPECTATION'\n",
        encoding="utf-8",
    )
    failed_retry = client.post(
        "/api/run",
        json={**request, "mode": "submit"},
    )
    assert failed_retry.status_code == 200, failed_retry.text
    assert failed_retry.json()["passed"] is False
    assert failed_retry.json()["score_summary"] == {
        "public": 1,
        "verified": 1,
        "total": 3,
    }
    assert failed_retry.json()["state"]["grades"]["lab01"]["lab01.q1"] == {
        "public": True,
        "verified": True,
    }
    assert "lab01" in failed_retry.json()["state"]["completed_labs"]
    assert "lab02" in failed_retry.json()["state"]["unlocked_labs"]


def test_v4_public_knowledge_never_leaks_answers_and_author_mismatch_fails_closed(
    runtime_client: tuple[TestClient, Path, Path],
) -> None:
    client, _learner, author = runtime_client
    public = client.get("/api/knowledge/lab00")
    assert public.status_code == 200
    serialized = json.dumps(public.json(), ensure_ascii=False)
    assert "answer_id" not in serialized
    assert "explanation" not in serialized
    assert "feedback" not in serialized

    binding_path = author / "author.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    binding["course_contract_sha256"] = "0" * 64
    binding_path.write_text(
        json.dumps(binding, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    response = client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab00",
            "question_id": "lab00.k1",
            "choice_id": "a",
        },
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "author package is unavailable or does not match this course"
    }


def test_v4_hidden_failures_do_not_leak_private_output(
    runtime_client: tuple[TestClient, Path, Path],
) -> None:
    client, _learner, author = runtime_client
    _answer(client, "lab00")
    _answer(client, "lab01")
    request = {"lab_id": "lab01", "question_id": "lab01.q1"}
    client.put(
        "/api/file",
        json={
            **request,
            "content": (
                "def normalize(value: str) -> str:\n"
                "    return value.strip()\n"
            ),
        },
    )
    hidden = author / "tests/hidden/lab01/test_normalize_hidden.py"
    hidden.write_text(
        "from tiny_parser.normalize import normalize\n\n"
        "def test_normalize_hidden():\n"
        "    assert normalize(' value ') == 'SECRET_PRIVATE_EXPECTATION'\n",
        encoding="utf-8",
    )

    response = client.post(
        "/api/run",
        json={**request, "mode": "submit"},
    )
    assert response.status_code == 200
    assert response.json()["passed"] is False
    assert response.json()["state"]["grades"]["lab01"]["lab01.q1"] == {
        "public": True,
        "verified": False,
    }
    assert "lab01" not in response.json()["state"]["completed_labs"]
    assert "SECRET_PRIVATE_EXPECTATION" not in response.text
    assert "test_normalize_hidden" not in response.text


def test_v4_file_api_rejects_symlink_and_runner_rejects_concurrency(
    runtime_client: tuple[TestClient, Path, Path],
    tmp_path: Path,
) -> None:
    client, learner, _author = runtime_client
    _answer(client, "lab00")
    _answer(client, "lab01")
    request = {"lab_id": "lab01", "question_id": "lab01.q1"}

    target = learner / "src/tiny_parser/normalize.py"
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = True\n", encoding="utf-8")
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError as error:  # pragma: no cover - platform boundary
        pytest.skip(f"symlinks unavailable: {error}")
    assert client.get("/api/file", params=request).status_code == 400
    assert (
        client.put(
            "/api/file",
            json={**request, "content": "SECRET = False\n"},
        ).status_code
        == 400
    )
    assert outside.read_text(encoding="utf-8") == "SECRET = True\n"

    assert runner._RUN_LOCK.acquire(blocking=False)
    try:
        busy = client.post("/api/run", json={**request, "mode": "public"})
    finally:
        runner._RUN_LOCK.release()
    assert busy.status_code == 409


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_v4_isolated_pytest_runs_one_aggregate_collection_and_times_out(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "learner"
    _write(
        workspace / "src/example.py",
        "def answer():\n    return 42\n",
    )
    tests = tmp_path / "trusted"
    first = _write(
        tests / "test_contract.py",
        "from example import answer\n\n"
        "def test_first():\n"
        "    assert answer() == 42\n\n"
        "def test_second():\n"
        "    assert answer() > 0\n",
    )
    result = execution.run_isolated_pytest(
        workspace,
        [
            f"{first}::test_first",
            f"{first}::test_second",
        ],
        timeout_seconds=5,
    )
    assert result.passed is True, result.output
    assert result.evidence_valid is True
    assert len(result.collected) == 2
    assert set(result.outcomes.values()) == {"passed"}

    hanging = _write(
        tests / "test_hanging.py",
        "import time\n\n"
        "def test_hanging():\n"
        "    while True:\n"
        "        time.sleep(0.05)\n",
    )
    timeout = execution.run_isolated_pytest(
        workspace,
        [f"{hanging}::test_hanging"],
        timeout_seconds=0.25,
    )
    assert timeout.passed is False
    assert timeout.timed_out is True
    assert "timed out" in timeout.output
