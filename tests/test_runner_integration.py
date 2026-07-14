from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

from fastapi.testclient import TestClient
import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
PLATFORM_ROOT = SKILL_ROOT / "assets" / "course-template" / "platform"
sys.path.insert(0, str(PLATFORM_ROOT))

import runner.app as runner_app  # noqa: E402
from runner.execution import PytestRunResult  # noqa: E402


@dataclass(frozen=True)
class Runtime:
    client: TestClient
    workspace: Path
    course_root: Path
    request: dict[str, str]
    state: dict[str, Any]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Runtime:
    workspace = tmp_path / "labs"
    course_root = tmp_path / "course"
    learner_test = workspace / "lab01/tests/test_answer.py"
    canonical_test = course_root / "starter/lab01/tests/test_answer.py"
    hidden_test = course_root / "hidden/lab01/test_answer_hidden.py"

    (workspace / "lab01").mkdir(parents=True)
    (workspace / "lab01/answer.py").write_text(
        "def answer():\n    return 1\n",
        encoding="utf-8",
    )
    learner_test.parent.mkdir(parents=True)
    learner_test.write_text(
        "def test_answer():\n"
        "    # A learner-owned test must never replace the canonical test.\n"
        "    assert True\n",
        encoding="utf-8",
    )
    canonical_test.parent.mkdir(parents=True)
    canonical_test.write_text(
        "from lab01.answer import answer\n\n"
        "def test_answer():\n"
        "    assert answer() == 1\n",
        encoding="utf-8",
    )
    hidden_test.parent.mkdir(parents=True)
    hidden_test.write_text(
        "from lab01.answer import answer\n\n"
        "def test_answer_hidden():\n"
        "    assert answer() == 1\n",
        encoding="utf-8",
    )

    question = {
        "id": "lab01.q1",
        "title": "Answer",
        "file": "lab01/answer.py",
        "points": 2,
        "timeout_seconds": 3,
        "source_policy": {
            "local_root": "lab01",
            "required_imports": [],
            "forbidden_imports": [],
            "prior_mini_modules": [],
            "forbidden_course_roots": [],
        },
        "tests": {
            "public": ["lab01/tests/test_answer.py::test_answer"],
            "hidden": ["hidden/lab01/test_answer_hidden.py::test_answer_hidden"],
        },
    }
    course_manifest = {
        "course_id": "runner-contract-course",
        "curriculum_id": "runner-contract-v1",
        "title": "Runner contract course",
        "foundations": {"id": "lab00", "title": "Foundation"},
        "labs": [
            {
                "id": "lab01",
                "title": "Lab 01",
                "depends_on": "lab00",
                "questions": [question],
            },
            {
                "id": "lab02",
                "title": "Lab 02",
                "depends_on": "lab01",
                "questions": [
                    {
                        **question,
                        "id": "lab02.q1",
                        "title": "Another answer",
                        "file": "lab02/answer.py",
                        "source_policy": {
                            **question["source_policy"],
                            "local_root": "lab02",
                            "forbidden_course_roots": ["lab01"],
                        },
                    }
                ],
            },
        ],
    }
    _write_json(course_root / "manifest.json", course_manifest)
    _write_json(workspace / "manifest.json", course_manifest)
    _write_json(
        course_root / "knowledge.json",
        {
            "labs": {
                "lab00": {
                    "title": "Foundation",
                    "questions": [
                        {
                            "id": "lab00.k01",
                            "prompt": "Ready?",
                            "choices": ["Yes", "No"],
                            "answer": 0,
                            "explanation": "Yes is the readiness answer.",
                        }
                    ],
                },
                "lab01": {
                    "title": "Lab 01",
                    "questions": [
                        {
                            "id": "lab01.k01",
                            "kind": "execution_trace",
                            "prompt": "Choose one.",
                            "choices": [
                                {
                                    "id": "right",
                                    "text": "Right",
                                    "feedback": "This follows the execution trace.",
                                },
                                {
                                    "id": "wrong",
                                    "text": "Wrong",
                                    "feedback": "This skips the ownership boundary.",
                                },
                            ],
                            "answer_id": "right",
                            "explanation": "Right is correct.",
                        }
                    ],
                },
                "lab02": {
                    "title": "Lab 02",
                    "questions": [
                        {
                            "id": "lab02.k01",
                            "prompt": "Continue?",
                            "choices": ["Continue", "Stop"],
                            "answer": 0,
                            "explanation": "Continue is correct.",
                        }
                    ],
                },
            }
        },
    )
    _write_json(
        course_root / "content.json",
        {"foundations": {"id": "lab00"}, "labs": [{"id": "lab01"}]},
    )
    state = {
        "version": 1,
        "course_id": course_manifest["course_id"],
        "curriculum_id": course_manifest["curriculum_id"],
        "knowledge": {
            "lab00": {"lab00.k01": True},
            "lab01": {"lab01.k01": True},
        },
        "grades": {},
        "completed_labs": ["lab01"],
        "checkpoints": {},
        "updated_at": None,
    }
    _write_json(workspace / ".coursekit/state.json", state)

    monkeypatch.setattr(runner_app, "WORKSPACE_ROOT", workspace)
    monkeypatch.setattr(runner_app, "COURSE_ROOT", course_root)
    # Each test gets a fresh lock once the production Runner exposes it.
    monkeypatch.setattr(runner_app, "_RUN_LOCK", threading.Lock(), raising=False)
    app = runner_app.create_app()
    with TestClient(app) as client:
        yield Runtime(
            client=client,
            workspace=workspace,
            course_root=course_root,
            request={"lab_id": "lab01", "question_id": "lab01.q1"},
            state=state,
        )


def _set_state(
    runtime: Runtime,
    *,
    knowledge: dict[str, dict[str, bool]] | None = None,
    completed_labs: list[str] | None = None,
) -> dict[str, Any]:
    value = {
        **runtime.state,
        "knowledge": knowledge or {},
        "grades": {},
        "completed_labs": completed_labs or [],
        "updated_at": None,
    }
    _write_json(runtime.workspace / ".coursekit/state.json", value)
    return value


def _workspace_files(root: Path) -> dict[str, str]:
    """Digest learner-visible files while excluding CourseKit's grade state."""

    result: dict[str, str] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".coursekit" in relative.parts or not path.is_file():
            continue
        result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _result(*, passed: bool, output: str = "") -> PytestRunResult:
    return PytestRunResult(
        passed=passed,
        output=output,
        timed_out=False,
        output_limited=False,
        evidence_valid=True,
        returncode=0 if passed else 1,
    )


def _file_read(runtime: Runtime):
    return runtime.client.get("/api/file", params=runtime.request)


def _file_write(runtime: Runtime, content: str):
    return runtime.client.put(
        "/api/file",
        json={**runtime.request, "content": content},
    )


def test_file_api_is_question_scoped_and_reuses_quiz_gate(runtime: Runtime) -> None:
    _set_state(runtime)

    before_foundation_read = _file_read(runtime)
    before_foundation_write = _file_write(runtime, "def answer():\n    return 2\n")

    _set_state(runtime, knowledge={"lab00": {"lab00.k01": True}})
    foundation_only_read = _file_read(runtime)
    foundation_only_write = _file_write(runtime, "def answer():\n    return 2\n")

    _set_state(
        runtime,
        knowledge={
            "lab00": {"lab00.k01": True},
            "lab01": {"lab01.k01": True},
        },
    )
    ready_read = _file_read(runtime)
    sentinel = "def answer():\n    return '集成写回验证'\n"
    ready_write = _file_write(runtime, sentinel)

    assert before_foundation_read.status_code == 409
    assert before_foundation_write.status_code == 409
    assert foundation_only_read.status_code == 409
    assert foundation_only_write.status_code == 409
    assert ready_read.status_code == 200
    assert ready_read.json() == {
        "path": "lab01/answer.py",
        "content": "def answer():\n    return 1\n",
    }
    assert ready_write.status_code == 200
    assert ready_write.json() == {"path": "lab01/answer.py", "status": "saved"}
    assert _file_read(runtime).json()["content"] == sentinel
    assert (runtime.workspace / "lab01/answer.py").read_bytes() == sentinel.encode("utf-8")


def test_file_api_rejects_path_addressing_and_unknown_questions(runtime: Runtime) -> None:
    legacy_read = runtime.client.get(
        "/api/file", params={"path": "lab01/answer.py"}
    )
    legacy_write = runtime.client.put(
        "/api/file",
        json={"path": "lab01/answer.py", "content": "pass\n"},
    )
    mixed_write = runtime.client.put(
        "/api/file",
        json={
            **runtime.request,
            "path": "lab01/answer.py",
            "content": "pass\n",
        },
    )

    assert legacy_read.status_code == 422
    assert legacy_write.status_code == 422
    assert mixed_write.status_code == 422
    assert runtime.client.get(
        "/api/file",
        params={"lab_id": "missing", "question_id": "missing.q1"},
    ).status_code == 404
    assert runtime.client.get(
        "/api/file",
        params={"lab_id": "lab01", "question_id": "missing.q1"},
    ).status_code == 404
    assert runtime.client.put(
        "/api/file",
        json={
            "lab_id": "lab01",
            "question_id": "missing.q1",
            "content": "pass\n",
        },
    ).status_code == 404


def test_file_api_rejects_unsafe_or_symlink_manifest_targets(
    runtime: Runtime,
    tmp_path: Path,
) -> None:
    manifest_path = runtime.course_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    question = manifest["labs"][0]["questions"][0]

    question["file"] = str((runtime.workspace / "lab01/answer.py").resolve())
    _write_json(manifest_path, manifest)
    assert _file_read(runtime).status_code == 400
    assert _file_write(runtime, "pass\n").status_code == 400

    question["file"] = "../outside.py"
    _write_json(manifest_path, manifest)
    assert _file_read(runtime).status_code == 400
    assert _file_write(runtime, "pass\n").status_code == 400

    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = True\n", encoding="utf-8")
    outside_directory = tmp_path / "outside-directory"
    outside_directory.mkdir()
    (outside_directory / "answer.py").write_text("SECRET = True\n", encoding="utf-8")
    intermediate_link = runtime.workspace / "linked-lab"
    try:
        intermediate_link.symlink_to(outside_directory, target_is_directory=True)
    except OSError as error:  # pragma: no cover - platform permission boundary
        pytest.skip(f"symlinks unavailable: {error}")
    question["file"] = "linked-lab/answer.py"
    _write_json(manifest_path, manifest)
    assert _file_read(runtime).status_code == 400
    assert _file_write(runtime, "SECRET = False\n").status_code == 400

    link = runtime.workspace / "lab01/escape.py"
    try:
        link.symlink_to(outside)
    except OSError as error:  # pragma: no cover - platform permission boundary
        pytest.skip(f"symlinks unavailable: {error}")
    question["file"] = "lab01/escape.py"
    _write_json(manifest_path, manifest)

    assert _file_read(runtime).status_code == 400
    assert _file_write(runtime, "SECRET = False\n").status_code == 400


def test_file_api_consistently_classifies_missing_and_non_regular_targets(
    runtime: Runtime,
) -> None:
    manifest_path = runtime.course_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    question = manifest["labs"][0]["questions"][0]

    question["file"] = "lab01/missing.py"
    _write_json(manifest_path, manifest)
    assert _file_read(runtime).status_code == 404
    assert _file_write(runtime, "pass\n").status_code == 404

    question["file"] = "lab01"
    _write_json(manifest_path, manifest)
    assert _file_read(runtime).status_code == 400
    assert _file_write(runtime, "pass\n").status_code == 400

    if hasattr(os, "mkfifo"):
        fifo = runtime.workspace / "lab01/blocked.fifo"
        try:
            os.mkfifo(fifo)
        except OSError as error:  # pragma: no cover - platform permission boundary
            pytest.skip(f"FIFO creation unavailable: {error}")
        question["file"] = "lab01/blocked.fifo"
        _write_json(manifest_path, manifest)
        assert _file_read(runtime).status_code == 400
        assert _file_write(runtime, "pass\n").status_code == 400


def test_file_api_limits_utf8_encoded_bytes(runtime: Runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    target = runtime.workspace / "lab01/answer.py"
    before = target.read_bytes()
    monkeypatch.setattr(runner_app, "MAX_FILE_BYTES", 8)

    response = _file_write(runtime, "你你你")

    assert response.status_code == 422
    assert target.read_bytes() == before

    accepted = _file_write(runtime, "你你")
    assert accepted.status_code == 200
    assert target.read_bytes() == "你你".encode("utf-8")


def test_public_run_uses_canonical_test_not_learner_owned_test(runtime: Runtime) -> None:
    canonical_test = runtime.course_root / "starter/lab01/tests/test_answer.py"
    canonical_test.write_text(
        "from lab01.answer import answer\n\n"
        "def test_answer():\n"
        "    assert answer() == 99, 'CANONICAL_TEST_WAS_USED'\n",
        encoding="utf-8",
    )

    response = runtime.client.post(
        "/api/run", json={**runtime.request, "mode": "public"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["passed"] is False
    assert "CANONICAL_TEST_WAS_USED" in response.json()["output"]


@pytest.mark.parametrize(
    ("forbidden_source", "policy_field", "policy_values"),
    (
        ("import json\n\ndef answer():\n    return 1\n", "forbidden_imports", ["json"]),
        ("from json import dumps as encode\n\ndef answer():\n    return 1\n", "forbidden_imports", ["json"]),
        ("import importlib\nimportlib.import_module('json')\n\ndef answer():\n    return 1\n", "forbidden_imports", ["json"]),
        ("__import__('json')\n\ndef answer():\n    return 1\n", "forbidden_imports", ["json"]),
        ("import json\n\ndef answer():\n    return 1\n", "required_imports", ["json", "pathlib"]),
        ("from lab00 import mini as previous\n\ndef answer():\n    return 1\n", "prior_mini_modules", ["lab00.mini"]),
    ),
)
def test_runner_source_policy_preflight_blocks_import_bypasses_before_pytest(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
    forbidden_source: str,
    policy_field: str,
    policy_values: list[str],
) -> None:
    manifest_path = runtime.course_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["labs"][0]["questions"][0]["source_policy"][policy_field] = policy_values
    _write_json(manifest_path, manifest)
    (runtime.workspace / "lab01/answer.py").write_text(
        forbidden_source, encoding="utf-8"
    )
    called = False

    def should_not_run(*_args: object, **_kwargs: object) -> PytestRunResult:
        nonlocal called
        called = True
        return _result(passed=True)

    monkeypatch.setattr(runner_app, "run_isolated_pytest", should_not_run)

    response = runtime.client.post("/api/run", json=runtime.request)

    assert response.status_code == 400
    assert "source policy" in response.json()["detail"]
    assert called is False


def test_runner_source_policy_follows_same_lab_helpers_before_pytest(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = runtime.course_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["labs"][0]["questions"][0]["source_policy"]["forbidden_imports"] = [
        "json"
    ]
    _write_json(manifest_path, manifest)
    (runtime.workspace / "lab01/answer.py").write_text(
        "from lab01.helper import build\n\ndef answer():\n    return build()\n",
        encoding="utf-8",
    )
    (runtime.workspace / "lab01/helper.py").write_text(
        "import json\n\ndef build():\n    return 1\n", encoding="utf-8"
    )
    called = False

    def should_not_run(*_args: object, **_kwargs: object) -> PytestRunResult:
        nonlocal called
        called = True
        return _result(passed=True)

    monkeypatch.setattr(runner_app, "run_isolated_pytest", should_not_run)

    response = runtime.client.post("/api/run", json=runtime.request)

    assert response.status_code == 400
    assert "lab01/helper.py imports forbidden module" in response.json()["detail"]
    assert called is False


def test_runner_source_policy_follows_package_root_init_before_pytest(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = runtime.course_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["labs"][0]["questions"][0]["source_policy"]["forbidden_imports"] = [
        "json"
    ]
    _write_json(manifest_path, manifest)
    (runtime.workspace / "lab01/answer.py").write_text(
        "import lab01\n\ndef answer():\n    return 1\n", encoding="utf-8"
    )
    (runtime.workspace / "lab01/__init__.py").write_text(
        "import json\n", encoding="utf-8"
    )
    called = False

    def should_not_run(*_args: object, **_kwargs: object) -> PytestRunResult:
        nonlocal called
        called = True
        return _result(passed=True)

    monkeypatch.setattr(runner_app, "run_isolated_pytest", should_not_run)

    response = runtime.client.post("/api/run", json=runtime.request)

    assert response.status_code == 400
    assert "lab01/__init__.py imports forbidden module" in response.json()["detail"]
    assert called is False


def test_run_does_not_mutate_learner_visible_workspace(runtime: Runtime) -> None:
    before = _workspace_files(runtime.workspace)

    response = runtime.client.post(
        "/api/run", json={**runtime.request, "mode": "public"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["passed"] is True
    assert _workspace_files(runtime.workspace) == before


def test_submit_does_not_execute_hidden_test_in_teacher_tree(runtime: Runtime) -> None:
    hidden = runtime.course_root / "hidden/lab01/test_answer_hidden.py"
    hidden.write_text(
        "from pathlib import Path\n"
        "from lab01.answer import answer\n\n"
        "def test_answer_hidden():\n"
        "    Path(__file__).write_text('TEACHER_TEST_MUTATED\\n')\n"
        "    assert answer() == 1\n",
        encoding="utf-8",
    )
    before = hidden.read_bytes()

    response = runtime.client.post(
        "/api/run", json={**runtime.request, "mode": "submit"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["passed"] is True
    assert hidden.read_bytes() == before


def test_public_and_hidden_tests_share_one_decreasing_deadline(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, list[str], float]] = []

    def fake_isolated_pytest(
        learner_workspace: Path,
        canonical_targets: list[str],
        *,
        timeout_seconds: float,
        **_kwargs: Any,
    ) -> PytestRunResult:
        calls.append(
            (Path(learner_workspace), list(canonical_targets), timeout_seconds)
        )
        if len(calls) == 1:
            time.sleep(0.04)
        return _result(passed=True)

    monkeypatch.setattr(
        runner_app, "run_isolated_pytest", fake_isolated_pytest, raising=False
    )
    monkeypatch.setattr(
        runner_app,
        "run_pytest",
        lambda _targets: (True, "legacy runner"),
        raising=False,
    )

    passed, public_passed, _output = runner_app.run_tests(
        runner_app.RunRequest(**runtime.request, mode="submit")
    )

    assert (passed, public_passed) == (True, True)
    assert len(calls) == 2
    public_call, hidden_call = calls
    assert public_call[0] == runtime.workspace
    assert hidden_call[0] == runtime.workspace
    assert public_call[1] == [
        str(
            (
                runtime.course_root / "starter/lab01/tests/test_answer.py"
            ).resolve()
        )
        + "::test_answer"
    ]
    assert hidden_call[1] == [
        str(
            (
                runtime.course_root / "hidden/lab01/test_answer_hidden.py"
            ).resolve()
        )
        + "::test_answer_hidden"
    ]
    assert 0 < hidden_call[2] < public_call[2] <= 3
    assert public_call[2] - hidden_call[2] >= 0.03


def test_submit_never_exposes_hidden_runner_diagnostics(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def fake_isolated_pytest(
        _learner_workspace: Path,
        _canonical_targets: list[str],
        *,
        timeout_seconds: float,
        **_kwargs: Any,
    ) -> PytestRunResult:
        nonlocal calls
        assert timeout_seconds > 0
        calls += 1
        if calls == 1:
            return _result(passed=True, output="public diagnostics are allowed")
        return _result(
            passed=False,
            output="PRIVATE_TEST_PATH::test_secret PRIVATE_ASSERTION_BODY",
        )

    monkeypatch.setattr(
        runner_app, "run_isolated_pytest", fake_isolated_pytest, raising=False
    )
    monkeypatch.setattr(
        runner_app,
        "run_pytest",
        lambda _targets: (True, "legacy runner"),
        raising=False,
    )

    passed, public_passed, output = runner_app.run_tests(
        runner_app.RunRequest(**runtime.request, mode="submit")
    )

    assert calls == 2
    assert (passed, public_passed) == (False, True)
    assert output == (
        "Public tests passed. "
        "Hidden verification failed (1 private target(s) checked)."
    )
    assert "PRIVATE_TEST_PATH" not in output
    assert "test_secret" not in output
    assert "PRIVATE_ASSERTION_BODY" not in output


def test_submit_hides_hidden_runner_exceptions(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def exploding_hidden_runner(
        _learner_workspace: Path,
        _canonical_targets: list[str],
        *,
        timeout_seconds: float,
        **_kwargs: Any,
    ) -> PytestRunResult:
        nonlocal calls
        assert timeout_seconds > 0
        calls += 1
        if calls == 1:
            return _result(passed=True)
        raise RuntimeError(
            "PRIVATE_TEST_PATH::test_secret PRIVATE_ASSERTION_BODY"
        )

    monkeypatch.setattr(
        runner_app, "run_isolated_pytest", exploding_hidden_runner
    )

    passed, public_passed, output = runner_app.run_tests(
        runner_app.RunRequest(**runtime.request, mode="submit")
    )

    assert calls == 2
    assert (passed, public_passed) == (False, True)
    assert output == (
        "Public tests passed. "
        "Hidden verification failed (private grader unavailable)."
    )
    assert "PRIVATE_TEST_PATH" not in output
    assert "test_secret" not in output
    assert "PRIVATE_ASSERTION_BODY" not in output


def test_concurrent_run_returns_409_then_lock_releases_after_completion(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = threading.Event()
    release = threading.Event()
    call_lock = threading.Lock()
    call_count = 0

    def blocking_run_tests(
        _request: runner_app.RunRequest,
    ) -> tuple[bool, bool, str]:
        nonlocal call_count
        with call_lock:
            call_count += 1
            current = call_count
        if current == 1:
            entered.set()
            assert release.wait(timeout=3), "test did not release the first run"
        return True, True, "ok"

    monkeypatch.setattr(runner_app, "run_tests", blocking_run_tests)
    monkeypatch.setattr(
        runner_app,
        "record_result",
        lambda _request, _passed, _public_passed: runtime.state,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(
            runtime.client.post,
            "/api/run",
            json={**runtime.request, "mode": "public"},
        )
        assert entered.wait(timeout=2), "first run never entered the Runner"
        try:
            concurrent = runtime.client.post(
                "/api/run", json={**runtime.request, "mode": "public"}
            )
        finally:
            release.set()
        first = first_future.result(timeout=3)

    assert first.status_code == 200, first.text
    assert concurrent.status_code == 409, concurrent.text
    assert "busy" in concurrent.text.lower()

    after_completion = runtime.client.post(
        "/api/run", json={**runtime.request, "mode": "public"}
    )
    assert after_completion.status_code == 200, after_completion.text


def test_run_lock_releases_when_grading_raises(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_count = 0

    def flaky_run_tests(
        _request: runner_app.RunRequest,
    ) -> tuple[bool, bool, str]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("expected grading failure")
        return True, True, "ok"

    monkeypatch.setattr(runner_app, "run_tests", flaky_run_tests)
    monkeypatch.setattr(
        runner_app,
        "record_result",
        lambda _request, _passed, _public_passed: runtime.state,
    )

    failed = runtime.client.post(
        "/api/run", json={**runtime.request, "mode": "public"}
    )
    recovered = runtime.client.post(
        "/api/run", json={**runtime.request, "mode": "public"}
    )

    assert failed.status_code == 400, failed.text
    assert recovered.status_code == 200, recovered.text


def test_progression_state_exposes_navigable_labs(runtime: Runtime) -> None:
    _set_state(runtime)

    initial = runtime.client.get("/api/state")

    assert initial.status_code == 200, initial.text
    assert initial.json()["unlocked_labs"] == ["lab00", "lab01"]

    _set_state(runtime, completed_labs=["lab01"])
    after_completion = runtime.client.get("/api/state")

    assert after_completion.status_code == 200, after_completion.text
    assert after_completion.json()["unlocked_labs"] == [
        "lab00",
        "lab01",
        "lab02",
    ]


def test_progression_knowledge_view_redacts_answers_and_tracks_availability(
    runtime: Runtime,
) -> None:
    _set_state(runtime)

    foundation = runtime.client.get("/api/knowledge/lab00")
    first_lab = runtime.client.get("/api/knowledge/lab01")
    unknown = runtime.client.get("/api/knowledge/missing")

    assert foundation.status_code == 200, foundation.text
    assert foundation.json() == {
        "lab_id": "lab00",
        "title": "Foundation",
        "available": True,
        "completed": False,
        "mastered": 0,
        "total": 1,
        "questions": [
            {
                "id": "lab00.k01",
                "prompt": "Ready?",
                "choices": [
                    {"id": "0", "text": "Yes"},
                    {"id": "1", "text": "No"},
                ],
                "mastered": False,
            }
        ],
    }
    assert "answer" not in json.dumps(foundation.json())
    assert first_lab.status_code == 200, first_lab.text
    assert first_lab.json()["available"] is False
    assert first_lab.json()["questions"][0]["kind"] == "execution_trace"
    assert first_lab.json()["questions"][0]["choices"] == [
        {"id": "right", "text": "Right"},
        {"id": "wrong", "text": "Wrong"},
    ]
    assert "answer" not in json.dumps(first_lab.json())
    assert unknown.status_code == 404, unknown.text


def test_progression_answer_api_persists_only_correct_mastery_and_validates_requests(
    runtime: Runtime,
) -> None:
    initial = _set_state(runtime)
    state_file = runtime.workspace / ".coursekit/state.json"
    before_wrong = state_file.read_bytes()

    unknown_lab = runtime.client.post(
        "/api/knowledge/answer",
        json={"lab_id": "missing", "question_id": "q", "choice_id": "0"},
    )
    unknown_question = runtime.client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab00",
            "question_id": "missing",
            "choice_id": "0",
        },
    )
    invalid_choice = runtime.client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab00",
            "question_id": "lab00.k01",
            "choice_id": "missing",
        },
    )
    wrong = runtime.client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab00",
            "question_id": "lab00.k01",
            "choice_id": "1",
        },
    )

    assert unknown_lab.status_code == 404, unknown_lab.text
    assert unknown_question.status_code == 404, unknown_question.text
    assert invalid_choice.status_code == 400, invalid_choice.text
    assert wrong.status_code == 200, wrong.text
    assert wrong.json()["correct"] is False
    assert wrong.json()["explanation"] == "Yes is the readiness answer."
    assert wrong.json()["knowledge"]["mastered"] == 0
    assert wrong.json()["state"]["knowledge"] == initial["knowledge"]
    assert state_file.read_bytes() == before_wrong

    correct = runtime.client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab00",
            "question_id": "lab00.k01",
            "choice_id": "0",
        },
    )

    assert correct.status_code == 200, correct.text
    assert correct.json()["correct"] is True
    assert correct.json()["knowledge"]["completed"] is True
    assert correct.json()["knowledge"]["mastered"] == 1
    assert correct.json()["state"]["knowledge"]["lab00"]["lab00.k01"] is True
    assert isinstance(correct.json()["state"]["updated_at"], str)


def test_progression_answer_api_enforces_knowledge_prerequisites(
    runtime: Runtime,
) -> None:
    _set_state(runtime)

    first_lab = runtime.client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab01",
            "question_id": "lab01.k01",
            "choice_id": "right",
        },
    )

    assert first_lab.status_code == 409, first_lab.text

    foundation = runtime.client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab00",
            "question_id": "lab00.k01",
            "choice_id": "0",
        },
    )
    assert foundation.status_code == 200, foundation.text

    later_lab = runtime.client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab02",
            "question_id": "lab02.k01",
            "choice_id": "0",
        },
    )

    assert later_lab.status_code == 409, later_lab.text
    view = runtime.client.get("/api/knowledge/lab02")
    assert view.status_code == 200, view.text
    assert view.json()["available"] is False


def test_progression_answer_returns_only_selected_choice_feedback(
    runtime: Runtime,
) -> None:
    _set_state(runtime, knowledge={"lab00": {"lab00.k01": True}})

    response = runtime.client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab01",
            "question_id": "lab01.k01",
            "choice_id": "wrong",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["correct"] is False
    assert payload["feedback"] == "This skips the ownership boundary."
    serialized = json.dumps(payload)
    assert "This follows the execution trace." not in serialized
    assert "answer_id" not in serialized


def test_progression_run_api_enforces_navigation_and_knowledge_gates(
    runtime: Runtime,
) -> None:
    _set_state(runtime)

    state = runtime.client.get("/api/state")
    missing_foundation = runtime.client.post(
        "/api/run", json={**runtime.request, "mode": "public"}
    )

    assert state.status_code == 200, state.text
    assert "lab01" in state.json()["unlocked_labs"]
    assert missing_foundation.status_code == 409, missing_foundation.text

    _set_state(runtime, knowledge={"lab00": {"lab00.k01": True}})
    missing_current = runtime.client.post(
        "/api/run", json={**runtime.request, "mode": "public"}
    )
    assert missing_current.status_code == 409, missing_current.text

    _set_state(
        runtime,
        knowledge={
            "lab00": {"lab00.k01": True},
            "lab01": {"lab01.k01": True},
        },
    )
    allowed = runtime.client.post(
        "/api/run", json={**runtime.request, "mode": "public"}
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["passed"] is True


def test_progression_state_updates_are_locked_atomic_and_lossless(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_state(runtime)
    replacements: list[tuple[Path, Path]] = []
    real_replace = runner_app.os.replace

    def tracking_replace(source: str | Path, destination: str | Path) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(runner_app.os, "replace", tracking_replace)

    def remember(question_id: str) -> dict[str, Any]:
        def mutation(value: dict[str, Any]) -> None:
            time.sleep(0.04)
            value.setdefault("knowledge", {}).setdefault("lab00", {})[
                question_id
            ] = True

        return runner_app.update_state(mutation)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(remember, ["one", "two"]))

    saved = json.loads(
        (runtime.workspace / ".coursekit/state.json").read_text(encoding="utf-8")
    )
    assert saved["knowledge"]["lab00"] == {"one": True, "two": True}
    assert isinstance(saved["updated_at"], str)
    assert all(isinstance(value["updated_at"], str) for value in results)
    assert (runtime.workspace / ".coursekit/state.json.lock").is_file()
    assert len(replacements) == 2
    assert all(
        destination == runtime.workspace / ".coursekit/state.json"
        and source.parent == destination.parent
        for source, destination in replacements
    )


def test_review_trusted_manifest_controls_progression_when_learner_copy_diverges(
    runtime: Runtime,
) -> None:
    _set_state(
        runtime,
        knowledge={
            "lab00": {"lab00.k01": True},
            "lab02": {"lab02.k01": True},
        },
    )
    learner_path = runtime.workspace / "manifest.json"
    learner = json.loads(learner_path.read_text(encoding="utf-8"))
    learner["curriculum_id"] = "learner-tampered"
    learner["labs"][1]["depends_on"] = "lab00"
    learner["labs"][1]["questions"][0]["points"] = 999
    _write_json(learner_path, learner)

    course = runtime.client.get("/api/course")
    state = runtime.client.get("/api/state")
    knowledge = runtime.client.get("/api/knowledge/lab02")
    run = runtime.client.post(
        "/api/run",
        json={"lab_id": "lab02", "question_id": "lab02.q1", "mode": "public"},
    )

    assert course.status_code == 200, course.text
    assert course.json()["manifest"]["curriculum_id"] == "learner-tampered"
    assert state.status_code == 200, state.text
    assert state.json()["curriculum_id"] == runtime.state["curriculum_id"]
    assert state.json()["knowledge"]["lab02"]["lab02.k01"] is True
    assert state.json()["unlocked_labs"] == ["lab00", "lab01"]
    assert state.json()["total_points"] == 4
    assert knowledge.status_code == 200, knowledge.text
    assert knowledge.json()["available"] is False
    assert run.status_code == 409, run.text


def test_review_first_web_answer_persists_the_shared_git_baseline(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = "a" * 40
    (runtime.workspace / ".coursekit/state.json").unlink()
    monkeypatch.setattr(runner_app, "git_head", lambda: baseline, raising=False)

    response = runtime.client.post(
        "/api/knowledge/answer",
        json={
            "lab_id": "lab00",
            "question_id": "lab00.k01",
            "choice_id": "0",
        },
    )

    assert response.status_code == 200, response.text
    persisted = json.loads(
        (runtime.workspace / ".coursekit/state.json").read_text(encoding="utf-8")
    )
    assert set(persisted) == {
        "version",
        "course_id",
        "curriculum_id",
        "knowledge",
        "grades",
        "completed_labs",
        "checkpoints",
        "git_baseline_commit",
        "updated_at",
    }
    assert persisted["git_baseline_commit"] == baseline
    assert response.json()["state"]["git_baseline_commit"] == baseline


def test_review_runner_and_copied_cli_progress_updates_survive_process_contention(
    runtime: Runtime,
) -> None:
    _set_state(runtime)
    copied_support = runtime.workspace / "_course/coursekit"
    shutil.copytree(
        SKILL_ROOT / "assets/course-template/platform/support/coursekit",
        copied_support,
    )
    runner_entered = runtime.workspace / "runner-entered"
    cli_started = runtime.workspace / "cli-started"

    def runner_mutation(value: dict[str, Any]) -> None:
        runner_entered.write_text("entered\n", encoding="utf-8")
        deadline = time.monotonic() + 3
        while not cli_started.exists():
            if time.monotonic() >= deadline:
                raise AssertionError("CLI subprocess never attempted its update")
            time.sleep(0.01)
        time.sleep(0.1)
        value.setdefault("knowledge", {}).setdefault("lab00", {})[
            "runner-process-race"
        ] = True

    script = r'''
from pathlib import Path
import sys

from coursekit.progress import update_state

Path(sys.argv[1]).write_text("started\n", encoding="utf-8")

def mutation(state):
    state.setdefault("knowledge", {}).setdefault("lab00", {})["cli-process-race"] = True

update_state(mutation)
'''
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(runtime.workspace / "_course")

    with ThreadPoolExecutor(max_workers=1) as pool:
        runner_future = pool.submit(runner_app.update_state, runner_mutation)
        deadline = time.monotonic() + 3
        while not runner_entered.exists():
            if time.monotonic() >= deadline:
                raise AssertionError("Runner never acquired the shared state lock")
            time.sleep(0.01)
        completed = subprocess.run(
            [sys.executable, "-c", script, str(cli_started)],
            cwd=runtime.workspace,
            env=environment,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        runner_future.result(timeout=5)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    saved = json.loads(
        (runtime.workspace / ".coursekit/state.json").read_text(encoding="utf-8")
    )
    assert saved["knowledge"]["lab00"]["runner-process-race"] is True
    assert saved["knowledge"]["lab00"]["cli-process-race"] is True
    assert (runtime.workspace / ".coursekit/state.json.lock").is_file()


def test_review_lab02_run_stays_locked_until_lab01_is_complete(
    runtime: Runtime,
) -> None:
    _set_state(
        runtime,
        knowledge={
            "lab00": {"lab00.k01": True},
            "lab02": {"lab02.k01": True},
        },
    )

    response = runtime.client.post(
        "/api/run",
        json={"lab_id": "lab02", "question_id": "lab02.q1", "mode": "public"},
    )

    assert response.status_code == 409, response.text


def test_review_completed_later_lab_remains_navigable(runtime: Runtime) -> None:
    _set_state(runtime, completed_labs=["lab02"])

    response = runtime.client.get("/api/state")

    assert response.status_code == 200, response.text
    assert response.json()["unlocked_labs"] == ["lab00", "lab01", "lab02"]
