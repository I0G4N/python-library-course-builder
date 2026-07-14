from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import verify_learning_project as verifier  # noqa: E402
from scaffold_course import scaffold  # noqa: E402
from tests.test_timeout_contract import make_spec  # noqa: E402


def test_quiz_answer_script_supports_stable_schema_v2_choice_ids() -> None:
    knowledge = {
        "labs": {
            "lab00": {
                "questions": [
                    {
                        "choices": [
                            {"id": "a", "text": "A"},
                            {"id": "b", "text": "B"},
                            {"id": "c", "text": "C"},
                        ],
                        "answer_id": "b",
                    }
                ]
            }
        }
    }

    assert verifier._quiz_answers(knowledge, "lab00") == "2\n"


def test_verifier_executes_declared_runnable_lesson_examples(tmp_path: Path) -> None:
    source = tmp_path / "platform/course/source"
    compiled = tmp_path / "platform/course"
    example = source / "foundations/examples/01_value.py"
    example.parent.mkdir(parents=True)
    example.write_text("print(2)\n", encoding="utf-8")
    snapshot = {
        "foundation": {
            "id": "lab00",
            "lesson": {
                "examples": [
                    {
                        "id": "lab00.e-run",
                        "kind": "runnable",
                        "path": "examples/01_value.py",
                        "expected_output": "2",
                    }
                ]
            },
        },
        "labs": [],
    }
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / "authoring-spec.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )

    passed, evidence = verifier.runnable_lesson_examples(tmp_path, sys.executable)
    assert passed is True
    assert "lab00.e-run=0" in evidence

    snapshot["foundation"]["lesson"]["examples"][0]["expected_output"] = "3"
    (compiled / "authoring-spec.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )
    passed, evidence = verifier.runnable_lesson_examples(tmp_path, sys.executable)
    assert passed is False
    assert "expected '3'" in evidence


def test_runnable_lesson_example_can_import_the_generated_lab_package(
    tmp_path: Path,
) -> None:
    source = tmp_path / "platform/course/source/labs/lab01"
    compiled = tmp_path / "platform/course"
    example = source / "examples/01_import.py"
    example.parent.mkdir(parents=True)
    example.write_text(
        "from lab01.answer import value\n\nprint(value())\n",
        encoding="utf-8",
    )
    learner_lab = tmp_path / "labs/lab01"
    learner_lab.mkdir(parents=True)
    (learner_lab / "__init__.py").write_text("", encoding="utf-8")
    (learner_lab / "answer.py").write_text(
        "def value():\n    return 7\n",
        encoding="utf-8",
    )
    snapshot = {
        "foundation": None,
        "labs": [
            {
                "id": "lab01",
                "lesson": {
                    "examples": [
                        {
                            "id": "lab01.e-import",
                            "kind": "runnable",
                            "path": "examples/01_import.py",
                            "expected_output": "7",
                        }
                    ]
                },
            }
        ],
    }
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / "authoring-spec.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )

    passed, evidence = verifier.runnable_lesson_examples(
        tmp_path, sys.executable
    )

    assert passed is True, evidence
    assert "lab01.e-import=0" in evidence


@pytest.fixture()
def generated_course(tmp_path: Path) -> Path:
    spec_path = tmp_path / "spec.json"
    spec = make_spec()
    first_lab = spec["labs"][0]
    first_lab["files"].append(
        {
            "path": "lab01/second.py",
            "starter": (
                "def answer_second():\n"
                "    raise NotImplementedError\n"
            ),
            "reference": "def answer_second():\n    return 2\n",
        }
    )
    first_lab["questions"].append(
        {
            "id": "lab01.q2",
            "kind": "integration",
            "title": "Second answer",
            "file": "lab01/second.py",
            "symbol": "answer_second",
            "points": 2,
            "timeout_seconds": 30,
            "prompt": "Return the second value.",
            "concept_ids": ["lab01.c-mechanism"],
            "outcome_ids": ["lab01.o-diagnose"],
            "example": {
                "input": "answer_second()",
                "output": "2",
                "explanation": "The second interface returns 2.",
            },
            "public_test": {
                "path": "test_answer_second.py",
                "selector": "test_answer_second",
                "code": (
                    "from lab01.second import answer_second\n\n"
                    "def test_answer_second():\n"
                    "    assert answer_second() == 2\n"
                ),
            },
            "hidden_test": {
                "path": "test_answer_second_hidden.py",
                "selector": "test_answer_second_hidden",
                "code": (
                    "from lab01.second import answer_second\n\n"
                    "def test_answer_second_hidden():\n"
                    "    assert answer_second() == 2\n"
                ),
            },
        }
    )
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    target = tmp_path / "generated"
    scaffold(spec_path, target)
    for cache in target.rglob("__pycache__"):
        shutil.rmtree(cache)
    return target


def _source_digest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _replace_runner_source(course: Path, before: str, after: str) -> None:
    path = course / "platform/runner/app.py"
    source = path.read_text(encoding="utf-8")
    assert source.count(before) == 1
    path.write_text(source.replace(before, after), encoding="utf-8")


def _replace_runner_source_pattern(course: Path, pattern: str, after: str) -> None:
    path = course / "platform/runner/app.py"
    source = path.read_text(encoding="utf-8")
    source, count = re.subn(pattern, after, source, count=1, flags=re.MULTILINE)
    assert count == 1
    path.write_text(source, encoding="utf-8")


def test_web_progression_workflow_exercises_all_three_gates_without_mutating_source(
    generated_course: Path,
) -> None:
    source_state = generated_course / "labs/.coursekit/state.json"
    assert not source_state.exists()
    before = _source_digest(generated_course)

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["api_workflow"] is True, result["output"]
    assert result["chapter_navigation_gate"] is True
    assert result["knowledge_gate"] is True
    assert result["code_file_gate"] is True
    assert result["coding_verification_gate"] is True
    assert result["shared_progress_state"] is True
    for question_id in ("lab01.q1", "lab01.q2"):
        assert f"foundation-locked-file-{question_id}=409" in result["output"]
        assert f"foundation-locked-save-{question_id}=409" in result["output"]
        assert f"foundation-only-file-{question_id}=409" in result["output"]
        assert f"foundation-only-save-{question_id}=409" in result["output"]
        assert f"current-ready-file-{question_id}=200" in result["output"]
        assert f"current-ready-save-{question_id}=200" in result["output"]
        assert f"current-ready-reread-{question_id}=200" in result["output"]
    assert "foundation-only-run=409" in result["output"]
    assert "foundation-mastered=True,current-mastered=False" in result["output"]
    assert "intermediate-lab01.q1=locked" in result["output"]
    assert "final-lab01.q2=completed" in result["output"]
    assert source_state.exists() is False
    assert _source_digest(generated_course) == before


def test_web_progression_workflow_rejects_an_ungated_code_file_api(
    generated_course: Path,
) -> None:
    _replace_runner_source(
        generated_course,
        "    reasons = run_gate_reasons(lab_id, value)\n"
        "    if reasons:\n"
        "        raise CodeFileLockedError(\n"
        '            f"{lab_id} is locked: " + "; ".join(reasons)\n'
        "        )\n",
        "",
    )

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["code_file_gate"] is False, result["output"]
    assert result["api_workflow"] is False


def test_web_progression_workflow_rejects_a_file_api_that_only_gates_first_question(
    generated_course: Path,
) -> None:
    _replace_runner_source(
        generated_course,
        "    reasons = run_gate_reasons(lab_id, value)\n",
        "    reasons = run_gate_reasons(lab_id, value)\n"
        '    if question_id != "lab01.q1":\n'
        "        reasons = []\n",
    )

    result = verifier.web_progression_workflow(generated_course, sys.executable)

    assert result["code_file_gate"] is False, result["output"]
    assert result["api_workflow"] is False


def test_web_progression_workflow_rejects_a_noop_file_write(
    generated_course: Path,
) -> None:
    _replace_runner_source_pattern(
        generated_course,
        r"^\s+write_workspace_text\(destination_parts, request\.content\)$",
        "            _ = request.content  # deliberate mutation: report success without writing",
    )

    result = verifier.web_progression_workflow(generated_course, sys.executable)

    assert result["code_file_gate"] is False, result["output"]
    assert result["api_workflow"] is False


def test_web_progression_workflow_rejects_a_course_that_navigates_past_dependency(
    generated_course: Path,
) -> None:
    manifest_path = generated_course / "platform/course/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["labs"][1]["depends_on"] = manifest["foundations"]["id"]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["chapter_navigation_gate"] is False
    assert result["api_workflow"] is False


def test_web_progression_workflow_rejects_answer_keys_nested_in_post_response(
    generated_course: Path,
) -> None:
    _replace_runner_source(
        generated_course,
        'return {\n            "correct": correct,',
        'return {\n            "answer": {"choice_id": "leaked"},\n'
        '            "correct": correct,',
    )

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["knowledge_gate"] is False
    assert result["api_workflow"] is False


def test_web_progression_workflow_rejects_choice_feedback_leaked_by_get(
    generated_course: Path,
) -> None:
    _replace_runner_source(
        generated_course,
        'choices.append({"id": choice_id, "text": text})',
        'choices.append({\n'
        '            "id": choice_id,\n'
        '            "text": text,\n'
        '            "feedback": (\n'
        '                str(choice.get("feedback", ""))\n'
        '                if isinstance(choice, dict)\n'
        '                else ""\n'
        '            ),\n'
        '        })',
    )

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["knowledge_gate"] is False, result["output"]
    assert result["api_workflow"] is False


def test_privacy_boundary_rejects_private_authoring_snapshot_in_labs(
    generated_course: Path,
) -> None:
    assert verifier.privacy_boundary(generated_course) is True

    leaked = generated_course / "labs" / "_course" / "authoring-spec.json"
    leaked.parent.mkdir(parents=True, exist_ok=True)
    leaked.write_text("{}\n", encoding="utf-8")

    assert verifier.privacy_boundary(generated_course) is False


def test_web_progression_workflow_redacts_blocked_answer_post_response(
    generated_course: Path,
) -> None:
    _replace_runner_source(
        generated_course,
        'detail=f"{request.lab_id} knowledge is not available yet",',
        'detail={\n'
        '                    "message": f"{request.lab_id} knowledge is not available yet",\n'
        '                    "answer": {"choice_id": "leaked"},\n'
        '                },',
    )

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["knowledge_gate"] is False
    assert result["api_workflow"] is False


@pytest.mark.parametrize(
    "lab_id, condition",
    [
        ("lab01", 'lab_id == "lab01" and value.get("completed") is True'),
        ("lab02", 'lab_id == "lab02" and value.get("available") is True'),
    ],
)
def test_web_progression_workflow_redacts_mastered_and_newly_available_gets(
    generated_course: Path,
    lab_id: str,
    condition: str,
) -> None:
    original = 'return knowledge_view(lab_id, read_state())'
    replacement = (
        'value = knowledge_view(lab_id, read_state())\n'
        f'            if {condition}:\n'
        '                value["answer"] = {"choice_id": "leaked"}\n'
        '            return value'
    )
    _replace_runner_source(generated_course, original, replacement)

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["knowledge_gate"] is False, (lab_id, result["output"])
    assert result["api_workflow"] is False


def test_web_progression_workflow_rejects_state_that_omits_persisted_grades(
    generated_course: Path,
) -> None:
    _replace_runner_source(
        generated_course,
        'return {\n        **value,\n        "unlocked_labs":',
        'return {\n'
        '        **{key: item for key, item in value.items() if key != "grades"},\n'
        '        "unlocked_labs":',
    )

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["shared_progress_state"] is False
    assert result["coding_verification_gate"] is False
    assert result["api_workflow"] is False


def test_web_progression_workflow_checks_every_initially_locked_lab(
    generated_course: Path,
) -> None:
    manifest_path = generated_course / "platform/course/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["labs"]) >= 3
    manifest["labs"][2]["depends_on"] = manifest["foundations"]["id"]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["chapter_navigation_gate"] is False
    assert result["api_workflow"] is False


@pytest.mark.parametrize(
    "probe_result",
    [
        {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "output": "missing knowledge gate",
        },
        {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "output": "missing code file gate",
        },
        {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": 1,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "output": "non-boolean knowledge gate",
        },
        {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": True,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
        },
        {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": True,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "output": {"not": "text"},
        },
        {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": True,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "privacy_check": False,
            "output": "unknown false check",
        },
        {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": True,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "generated_project_tests": False,
            "output": "full-only key in workflow result",
        },
    ],
)
def test_web_progression_workflow_rejects_malformed_probe_schema(
    generated_course: Path,
    monkeypatch: pytest.MonkeyPatch,
    probe_result: dict[str, Any],
) -> None:
    marker = "COURSEKIT_WEB_PROGRESSION="
    completed = subprocess.CompletedProcess(
        [sys.executable],
        0,
        marker + json.dumps(probe_result) + "\n",
        "",
    )
    monkeypatch.setattr(verifier, "run", lambda *_args, **_kwargs: completed)

    result = verifier.web_progression_workflow(
        generated_course,
        sys.executable,
    )

    assert result["api_workflow"] is False
    assert isinstance(result["output"], str)
    assert "schema" in result["output"].lower()


def test_verify_reports_generated_tests_inside_web_progression_and_counts_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "platform").mkdir()
    (tmp_path / "labs").mkdir()
    run_calls: list[tuple[list[str], int]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
        timeout: int = 120,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, input_text
        run_calls.append((command, timeout))
        stdout = ""
        if "--help" in command:
            stdout = "unlock\n"
        elif command[:3] == ["git", "rev-list", "--count"]:
            stdout = "1\n"
        return subprocess.CompletedProcess(command, 0, stdout, "")

    healthy: dict[str, Any] = {
        "api_workflow": True,
        "chapter_navigation_gate": True,
        "knowledge_gate": True,
        "code_file_gate": True,
        "coding_verification_gate": True,
        "shared_progress_state": True,
        "output": "functional API workflow passed",
    }
    monkeypatch.setattr(verifier, "run", fake_run)
    monkeypatch.setattr(
        verifier, "pytest_targets", lambda _root: (["public"], ["hidden"])
    )
    monkeypatch.setattr(
        verifier, "reference_public_targets", lambda _root: ["public"]
    )
    monkeypatch.setattr(
        verifier, "starter_red_check", lambda _root, _python: (True, "red")
    )
    monkeypatch.setattr(
        verifier,
        "runnable_lesson_examples",
        lambda _root, _python: (True, "examples"),
    )
    monkeypatch.setattr(
        verifier, "cli_learning_workflow", lambda _root, _python: (True, "cli")
    )
    monkeypatch.setattr(
        verifier,
        "web_progression_workflow",
        lambda _root, _python: dict(healthy),
    )
    monkeypatch.setattr(verifier, "privacy_boundary", lambda _root: True)
    monkeypatch.setattr(verifier, "scan_residue", lambda _root: [])
    monkeypatch.setattr(verifier, "symlink_free", lambda _root: True)

    report = verifier.verify(tmp_path, full=True)

    assert report["web_progression"] == {
        **healthy,
        "generated_project_tests": True,
    }
    reference_timeout = next(
        timeout
        for command, timeout in run_calls
        if command[1:3] == ["-m", "pytest"]
    )
    assert reference_timeout == 300
    assert report["passed"] is True

    unhealthy = dict(healthy, knowledge_gate=False)
    monkeypatch.setattr(
        verifier,
        "web_progression_workflow",
        lambda _root, _python: unhealthy,
    )

    failed = verifier.verify(tmp_path, full=True)

    assert failed["web_progression"]["knowledge_gate"] is False
    assert failed["passed"] is False


def test_verifier_main_writes_requested_json_when_a_subprocess_times_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "verification.json"

    def timeout(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise subprocess.TimeoutExpired(["pytest"], 300)

    monkeypatch.setattr(verifier, "verify", timeout)

    exit_code = verifier.main([str(tmp_path), "--json", str(report_path)])

    assert exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert "timed out" in payload["error"]


@pytest.mark.parametrize(
    "full, malformed",
    [
        (True, {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "output": "missing key",
        }),
        (True, {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "output": "missing code file gate",
        }),
        (True, {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": "yes",
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "output": "wrong type",
        }),
        (True, {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": True,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
        }),
        (True, {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": True,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "privacy_check": False,
            "output": "unknown false check",
        }),
        (False, {
            "api_workflow": True,
            "chapter_navigation_gate": True,
            "knowledge_gate": True,
            "code_file_gate": True,
            "coding_verification_gate": True,
            "shared_progress_state": True,
            "generated_project_tests": False,
            "output": "full-only check in partial report",
        }),
    ],
)
def test_verify_fails_closed_for_malformed_web_progression_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full: bool,
    malformed: dict[str, Any],
) -> None:
    (tmp_path / "platform").mkdir()
    (tmp_path / "labs").mkdir()

    def fake_run(
        command: list[str],
        **_kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        stdout = ""
        if "--help" in command:
            stdout = "unlock\n"
        elif command[:3] == ["git", "rev-list", "--count"]:
            stdout = "1\n"
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(verifier, "run", fake_run)
    monkeypatch.setattr(
        verifier, "pytest_targets", lambda _root: (["public"], ["hidden"])
    )
    monkeypatch.setattr(
        verifier, "reference_public_targets", lambda _root: ["public"]
    )
    monkeypatch.setattr(
        verifier, "starter_red_check", lambda _root, _python: (True, "red")
    )
    monkeypatch.setattr(
        verifier, "cli_learning_workflow", lambda _root, _python: (True, "cli")
    )
    monkeypatch.setattr(
        verifier,
        "web_progression_workflow",
        lambda _root, _python: dict(malformed),
    )
    monkeypatch.setattr(verifier, "privacy_boundary", lambda _root: True)
    monkeypatch.setattr(verifier, "scan_residue", lambda _root: [])
    monkeypatch.setattr(verifier, "symlink_free", lambda _root: True)

    report = verifier.verify(tmp_path, full=full)

    assert report["passed"] is False
