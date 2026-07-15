from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import verify_learning_project as verifier  # noqa: E402
from scaffold_course import scaffold  # noqa: E402
from tests.course_v3_fixture import make_v3_spec_and_plan  # noqa: E402


@pytest.fixture()
def generated_v3_course(tmp_path: Path) -> Path:
    spec, plan = make_v3_spec_and_plan(
        missing_ids={"json-data-model", "domain-boundary"}
    )
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    target = tmp_path / "generated"
    scaffold(spec_path, target, readiness_plan=plan)
    for cache in target.rglob("__pycache__"):
        shutil.rmtree(cache)
    return target


def _replace_runner_source(course: Path, before: str, after: str) -> None:
    path = course / "platform/runner/app.py"
    source = path.read_text(encoding="utf-8")
    assert source.count(before) == 1
    path.write_text(source.replace(before, after), encoding="utf-8")


def test_v3_web_probe_verifies_ordered_prep_isolation_and_formal_score(
    generated_v3_course: Path,
) -> None:
    manifest = json.loads(
        (generated_v3_course / "platform/course/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    prep_ids = [str(unit["id"]) for unit in manifest["preparatory_units"]]
    assert prep_ids == ["lab00", "prep01", "prep02"]
    learner_readme = (generated_v3_course / "labs/README.md").read_text(
        encoding="utf-8"
    )
    assert "uv run course unlock prep01" in learner_readme
    assert "uv run course unlock lab01" not in learner_readme

    result = verifier.web_progression_workflow(
        generated_v3_course,
        sys.executable,
    )

    assert result["api_workflow"] is True, result["output"]
    assert result["chapter_navigation_gate"] is True
    assert result["knowledge_gate"] is True
    assert result["code_file_gate"] is True
    assert result["coding_verification_gate"] is True
    assert result["shared_progress_state"] is True
    for index, unit_id in enumerate(prep_ids):
        expected = ",".join([*prep_ids[: index + 1], *prep_ids[index + 1 : index + 2]])
        if index == len(prep_ids) - 1:
            expected = ",".join([*prep_ids, "lab01"])
        assert f"prep-file-{unit_id}=409" in result["output"]
        assert f"prep-save-{unit_id}=409" in result["output"]
        assert f"prep-run-{unit_id}=409" in result["output"]
        assert f"prep-score-{unit_id}=0" in result["output"]
        assert f"prep-unlocked-{unit_id}={expected}" in result["output"]


def test_v3_web_probe_fails_when_prep_file_guard_is_removed(
    generated_v3_course: Path,
) -> None:
    _replace_runner_source(
        generated_v3_course,
        "    if is_preparatory_unit(lab_id):\n"
        "        raise CodeFileLockedError(\n"
        '            f"{lab_id} is a knowledge-only preparatory unit"\n'
        "        )\n",
        "",
    )

    result = verifier.web_progression_workflow(
        generated_v3_course,
        sys.executable,
    )

    assert result["code_file_gate"] is False, result["output"]
    assert result["api_workflow"] is False


def test_v3_web_probe_fails_when_prep_run_guard_is_removed(
    generated_v3_course: Path,
) -> None:
    _replace_runner_source(
        generated_v3_course,
        "            if is_preparatory_unit(request.lab_id):\n"
        "                raise HTTPException(\n"
        "                    status_code=409,\n"
        '                    detail=f"{request.lab_id} is a knowledge-only preparatory unit",\n'
        "                )\n",
        "",
    )

    result = verifier.web_progression_workflow(
        generated_v3_course,
        sys.executable,
    )

    assert result["code_file_gate"] is False, result["output"]
    assert result["api_workflow"] is False


def test_v3_web_probe_rejects_a_skipped_preparatory_dependency(
    generated_v3_course: Path,
) -> None:
    manifest_path = generated_v3_course / "platform/course/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["preparatory_units"][2]["depends_on"] = "lab00"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = verifier.web_progression_workflow(
        generated_v3_course,
        sys.executable,
    )

    assert result["chapter_navigation_gate"] is False, result["output"]
    assert result["api_workflow"] is False


def test_v3_web_probe_rejects_a_formal_lab_that_skips_lab01(
    generated_v3_course: Path,
) -> None:
    manifest_path = generated_v3_course / "platform/course/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["labs"][1]["depends_on"] = manifest["preparatory_units"][-1]["id"]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = verifier.web_progression_workflow(
        generated_v3_course,
        sys.executable,
    )

    assert result["chapter_navigation_gate"] is False, result["output"]
    assert result["api_workflow"] is False


def test_v3_web_probe_fails_when_prep_answers_create_grades(
    generated_v3_course: Path,
) -> None:
    _replace_runner_source(
        generated_v3_course,
        "                value.setdefault(\"knowledge\", {}).setdefault(request.lab_id, {})[\n"
        "                    request.question_id\n"
        "                ] = True\n",
        "                value.setdefault(\"knowledge\", {}).setdefault(request.lab_id, {})[\n"
        "                    request.question_id\n"
        "                ] = True\n"
        "                value.setdefault(\"grades\", {}).setdefault(request.lab_id, {})[\n"
        "                    request.question_id\n"
        "                ] = {\"public\": True, \"verified\": True}\n",
    )

    result = verifier.web_progression_workflow(
        generated_v3_course,
        sys.executable,
    )

    assert result["knowledge_gate"] is False, result["output"]
    assert result["shared_progress_state"] is False
    assert result["api_workflow"] is False


def test_v3_cli_probe_unlocks_every_prep_before_lab01(
    generated_v3_course: Path,
) -> None:
    environment = dict(os.environ)
    environment["UV_CACHE_DIR"] = "/tmp/course-builder-readiness-uv-cache"
    for directory in ("platform", "labs"):
        synced = subprocess.run(
            ["uv", "sync", "--frozen", "--directory", directory],
            cwd=generated_v3_course,
            env=environment,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        assert synced.returncode == 0, synced.stdout + synced.stderr
    passed, evidence = verifier.cli_learning_workflow(
        generated_v3_course,
        verifier.environment_python(generated_v3_course, "labs"),
    )

    assert passed is True, evidence
    assert "prep-skip=3" in evidence
    for unit_id in ("lab00", "prep01", "prep02", "lab01"):
        assert f"unlock-{unit_id}=0" in evidence
    for operation in ("test", "grade", "submit", "checkpoint"):
        assert f"prep-{operation}=2" in evidence


def test_v3_runnable_examples_include_preparatory_units(tmp_path: Path) -> None:
    source = tmp_path / "platform/course/source/preparatory_units/prep01"
    compiled = tmp_path / "platform/course"
    example = source / "examples/trace.py"
    example.parent.mkdir(parents=True)
    example.write_text("print('prep')\n", encoding="utf-8")
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / "authoring-spec.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "preparatory_units": [
                    {
                        "id": "prep01",
                        "lesson": {
                            "examples": [
                                {
                                    "id": "prep01.e-trace",
                                    "kind": "runnable",
                                    "path": "examples/trace.py",
                                    "expected_output": "prep",
                                }
                            ]
                        },
                    }
                ],
                "labs": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    passed, evidence = verifier.runnable_lesson_examples(
        tmp_path,
        sys.executable,
    )

    assert passed is True, evidence
    assert "prep01.e-trace=0" in evidence
