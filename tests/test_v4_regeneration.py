from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.course_v4_fixture import write_v4_fixture


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import regenerate_course as regeneration  # noqa: E402
import verify_v4_course as v4_verifier  # noqa: E402
from regenerate_course import (  # noqa: E402
    CourseRegenerationError,
    apply_v4_regeneration,
    main,
    plan_v4_chapter_regeneration,
    plan_v4_regeneration,
    plan_v4_targeted_regeneration,
)
from scaffold_v4_course import scaffold_v4_pair  # noqa: E402
from verify_v4_course import validate_v4_receipt, verify_v4_course  # noqa: E402


def _generation(learner: Path) -> dict[str, object]:
    return json.loads(
        (learner / ".coursekit/generation.json").read_text(encoding="utf-8")
    )


def _write_generation(learner: Path, value: dict[str, object]) -> None:
    (learner / ".coursekit/generation.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_plan(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _make_legacy_course(
    root: Path,
    *,
    schema_version: int = 3,
) -> Path:
    source = {
        "schema_version": schema_version,
        "id": "tiny-parser",
        "title": "Legacy tiny parser",
        "language": "zh-CN",
        "audience": {
            "prerequisite_profile": {"route_id": "value-conversion"},
        },
        "manifest": {
            "target": {
                "name": "json",
                "kind": "stdlib",
                "version": "Python 3.13",
                "track": "value conversion",
            }
        },
    }
    for path, value in (
        (root / "platform/course/source/course.json", source),
        (
            root / "platform/course/manifest.json",
            {"curriculum_id": "legacy-tiny-parser"},
        ),
        (root / "labs/manifest.json", {"course_id": "tiny-parser"}),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    tutorial = root / "platform/course/source/labs/lab01/tutorial.md"
    tutorial.parent.mkdir(parents=True, exist_ok=True)
    tutorial.write_text("# Legacy chapter\n", encoding="utf-8")
    learner_lab = root / "labs/lab01/README.md"
    learner_lab.parent.mkdir(parents=True, exist_ok=True)
    learner_lab.write_text("# Preserve this legacy root\n", encoding="utf-8")
    commands = (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=CourseKit",
            "-c",
            "user.email=coursekit@localhost",
            "commit",
            "-q",
            "-m",
            "coursekit: generated baseline",
        ),
    )
    for arguments in commands:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
    return root


def _verified_v4_candidate(root: Path) -> tuple[Path, Path, Path]:
    route_path, packages, _route = write_v4_fixture(root / "source")
    candidate = root / "candidate"
    scaffold_v4_pair(route_path, packages, candidate)
    candidate_author = root / "candidate-author"
    verify_v4_course(candidate, author_root=candidate_author)
    return route_path, candidate, candidate_author


def _targeted_v4_pair(
    root: Path,
    *,
    chapter_id: str = "lab01",
) -> tuple[Path, Path, Path, dict[str, object]]:
    route_path, packages, _route = write_v4_fixture(root / "source")
    learner = root / "course"
    scaffold_v4_pair(route_path, packages, learner)
    verify_v4_course(learner, author_root=root / "course-author")
    request = plan_v4_chapter_regeneration(
        learner,
        chapter_id=chapter_id,
        reason="Deepen the concrete boundary and recovery path.",
    )
    tutorial = packages / chapter_id / "tutorial.md"
    tutorial.write_text(
        tutorial.read_text(encoding="utf-8")
        + "\nA targeted chapter-only revision.\n",
        encoding="utf-8",
    )
    candidate = root / "candidate"
    scaffold_v4_pair(route_path, packages, candidate)
    candidate_author = root / "candidate-author"
    verify_v4_course(candidate, author_root=candidate_author)
    return learner, candidate, candidate_author, request


def test_v4_targeted_regeneration_locks_only_one_chapter(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path / "source")
    learner = tmp_path / "course"
    scaffold_v4_pair(route_path, packages, learner)

    request = plan_v4_chapter_regeneration(
        learner,
        chapter_id="lab01",
        reason="Make ownership and recovery concrete.",
    )

    assert request["mode"] == "chapter-regeneration-v4"
    assert request["chapter_id"] == "lab01"
    assert request["writer_calls"] == 1
    assert request["mechanical_repair_limit"] == 1
    assert request["include_previous_tutorial"] is False
    assert request["include_other_chapter_prose"] is False
    assert request["locked_chapter"]["owned_paths"] == [
        "src/tiny_parser/normalize.py"
    ]
    assert request["locked_chapter"]["task_contracts"][0][
        "hidden_tests"
    ] == ["test_normalize_hidden.py::test_normalize_hidden"]
    assert request["locked_chapter"]["task_contracts"][0][
        "public_tests"
    ] == ["test_normalize.py::test_normalize"]
    assert request["locked_chapter"]["task_contracts"][0]["example"] == {
        "input": "' ready '",
        "output": "'ready'",
        "explanation": "Whitespace is removed at the boundary.",
    }
    assert not any(
        key.startswith("example_")
        for key in request["locked_chapter"]["task_contracts"][0]
    )
    assert request["depth_brief_requirement"] == {
        "required": True,
        "source": "new-parent-agent-prompt-context",
        "reuse_from_generated_course": False,
        "persist_in_generated_course": False,
        "fields": [
            "chapter_id",
            "chapter_kind",
            "core_question",
            "project_increment",
            "required_facts",
            "interface_boundary",
            "walkthrough_case",
            "boundary_case",
            "design_choice",
            "credible_alternative",
            "previous_handoff",
            "next_handoff",
            "official_sources",
            "task_contracts",
            "owned_paths",
        ],
    }
    assert {
        chapter["chapter_id"] for chapter in request["preserve_chapters"]
    } == {"lab00", "lab02"}
    serialized = json.dumps(request, ensure_ascii=False)
    assert "This prose intentionally" not in serialized
    assert "answer_id" not in serialized


def test_v4_targeted_regeneration_cli_and_unknown_chapter(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path / "source")
    learner = tmp_path / "course"
    scaffold_v4_pair(route_path, packages, learner)
    output = tmp_path / "chapter-request.json"

    assert (
        main(
            [
                "chapter",
                str(learner),
                "--chapter",
                "lab02",
                "--reason",
                "Deepen failure propagation.",
                "--json",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text())["chapter_id"] == "lab02"

    with pytest.raises(CourseRegenerationError, match="unknown schema-v4 chapter"):
        plan_v4_chapter_regeneration(
            learner,
            chapter_id="lab99",
            reason="Not present.",
        )


def test_v4_targeted_request_candidate_check_and_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path / "source")
    learner = tmp_path / "course"
    scaffold_v4_pair(route_path, packages, learner)
    learner_author = tmp_path / "course-author"
    verify_v4_course(learner, author_root=learner_author)

    request_path = tmp_path / "chapter-request.json"
    assert main(
        [
            "chapter",
            str(learner),
            "--chapter",
            "lab01",
            "--reason",
            "Use a more concrete failure and recovery.",
            "--json",
            str(request_path),
        ]
    ) == 0
    tutorial = packages / "lab01/tutorial.md"
    tutorial.write_text(
        tutorial.read_text(encoding="utf-8")
        + "\nThe revised boundary now uses a concrete failing value.\n",
        encoding="utf-8",
    )
    candidate = tmp_path / "candidate"
    scaffold_v4_pair(route_path, packages, candidate)
    candidate_author = tmp_path / "candidate-author"
    verify_v4_course(candidate, author_root=candidate_author)

    before_other = regeneration._v4_chapter_artifact_digest(
        learner,
        learner_author,
        regeneration._v4_metadata(learner)["chapters"][2],
    )
    before_readme = (learner / "README.md").read_bytes()
    plan_path = tmp_path / "targeted-plan.json"
    assert main(
        [
            "check",
            str(learner),
            "--candidate-course",
            str(candidate),
            "--chapter-request",
            str(request_path),
            "--json",
            str(plan_path),
        ]
    ) == 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["status"] == "ready"
    assert plan["regeneration_kind"] == "targeted-chapter"
    assert plan["chapter_ids"] == ["lab01"]
    assert plan["writer_calls"] == 1
    assert plan["mechanical_repair_limit"] == 1
    assert plan["candidate_receipt"]["receipt_sha256"]
    assert plan["targeted_scope"]["unauthorized_learner_paths"] == []
    assert plan["targeted_scope"]["unauthorized_author_paths"] == []

    def no_full_verifier(_candidate: Path) -> dict[str, object]:
        raise AssertionError("targeted check/apply must use the offline receipt")

    monkeypatch.setattr(regeneration, "_run_full_verifier", no_full_verifier)
    result_path = tmp_path / "targeted-result.json"
    assert main(
        [
            "apply",
            str(learner),
            "--candidate-course",
            str(candidate),
            "--plan",
            str(plan_path),
            "--confirm-stopped",
            "--accept-replacement",
            "--json",
            str(result_path),
        ]
    ) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "applied"
    assert result["regeneration_kind"] == "targeted-chapter"
    assert result["chapter_ids"] == ["lab01"]
    assert result["writer_calls_during_apply"] == 0
    assert result["receipt_validation"] == "offline"
    assert "concrete failing value" in (
        learner / "chapters/lab01/tutorial.md"
    ).read_text(encoding="utf-8")
    assert (learner / "README.md").read_bytes() == before_readme
    assert regeneration._v4_chapter_artifact_digest(
        learner,
        learner_author,
        regeneration._v4_metadata(learner)["chapters"][2],
    ) == before_other
    assert not candidate.exists()
    assert not candidate_author.exists()
    assert result["replacement_policy"] == "delete-old-after-success"
    assert result["rollback_retained"] is False
    assert result["backup_retained"] is False
    assert result["old_project_deleted"] is True
    assert result["replacement_irreversible"] is True
    assert not Path(result["rollback_path"]).exists()
    validate_v4_receipt(learner, author_root=learner_author)


@pytest.mark.parametrize("tamper", ("other-chapter", "target-contract"))
def test_v4_targeted_check_rejects_out_of_scope_candidate_changes(
    tmp_path: Path,
    tamper: str,
) -> None:
    case = tmp_path / tamper
    route_path, packages, route = write_v4_fixture(case / "source")
    learner = case / "course"
    scaffold_v4_pair(route_path, packages, learner)
    verify_v4_course(learner, author_root=case / "course-author")
    request = plan_v4_chapter_regeneration(
        learner,
        chapter_id="lab01",
        reason="Deepen only lab01.",
    )
    target = packages / "lab01/tutorial.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nTarget revision.\n",
        encoding="utf-8",
    )
    if tamper == "other-chapter":
        outside = packages / "lab02/tutorial.md"
        outside.write_text(
            outside.read_text(encoding="utf-8")
            + "\nUnauthorized other-chapter revision.\n",
            encoding="utf-8",
        )
    else:
        route["chapters"][1]["task_contracts"][0]["prompt"] = (
            "Unauthorized task contract change."
        )
        _write_plan(route_path, route)
    candidate = case / "candidate"
    scaffold_v4_pair(route_path, packages, candidate)
    verify_v4_course(candidate, author_root=case / "candidate-author")

    plan = plan_v4_targeted_regeneration(
        learner,
        candidate_course=candidate,
        chapter_request=request,
    )
    assert plan["status"] == "blocked"
    assert "targeted-scope-violation" in {
        blocker["code"] for blocker in plan["blockers"]
    }
    if tamper == "other-chapter":
        assert (
            "chapters/lab02/tutorial.md"
            in plan["targeted_scope"]["unauthorized_learner_paths"]
        )
    else:
        assert "course.toml" in plan["targeted_scope"][
            "unauthorized_learner_paths"
        ]


def test_v4_targeted_second_rename_failure_rolls_back_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learner, candidate, candidate_author, request = _targeted_v4_pair(tmp_path)
    learner_author = tmp_path / "course-author"
    plan = plan_v4_targeted_regeneration(
        learner,
        candidate_course=candidate,
        chapter_request=request,
    )
    assert plan["status"] == "ready"
    plan_path = tmp_path / "targeted-rollback-plan.json"
    _write_plan(plan_path, plan)
    old_learner = regeneration._snapshot(learner)
    old_author = regeneration._snapshot(learner_author)
    candidate_learner = regeneration._snapshot(candidate)
    candidate_author_snapshot = regeneration._snapshot(candidate_author)
    real_replace = os.replace
    failed = False

    def fail_author_install(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
    ) -> None:
        nonlocal failed
        if (
            not failed
            and Path(source) == candidate_author
            and Path(destination) == learner_author
        ):
            failed = True
            raise OSError("injected targeted author rename failure")
        real_replace(source, destination)

    monkeypatch.setattr(regeneration.os, "replace", fail_author_install)
    with pytest.raises(
        CourseRegenerationError,
        match="rolled back learner and author",
    ):
        apply_v4_regeneration(
            learner,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert failed is True
    assert regeneration._snapshot(learner) == old_learner
    assert regeneration._snapshot(learner_author) == old_author
    assert regeneration._snapshot(candidate) == candidate_learner
    assert regeneration._snapshot(candidate_author) == candidate_author_snapshot
    assert not Path(plan["rollback_path"]).exists()


def test_v4_old_author_stage_failure_after_rename_restores_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learner, candidate, candidate_author, request = _targeted_v4_pair(tmp_path)
    learner_author = tmp_path / "course-author"
    plan = plan_v4_targeted_regeneration(
        learner,
        candidate_course=candidate,
        chapter_request=request,
    )
    plan_path = tmp_path / "old-author-stage-plan.json"
    _write_plan(plan_path, plan)
    rollback = Path(plan["rollback_path"])
    staged_author = rollback / regeneration.ROLLBACK_AUTHOR_NAME
    old_learner = regeneration._snapshot(learner)
    old_author = regeneration._snapshot(learner_author)
    candidate_learner = regeneration._snapshot(candidate)
    candidate_author_snapshot = regeneration._snapshot(candidate_author)
    real_replace = os.replace
    failed = False

    def rename_then_fail(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
    ) -> None:
        nonlocal failed
        real_replace(source, destination)
        if (
            not failed
            and Path(source) == learner_author
            and Path(destination) == staged_author
        ):
            failed = True
            raise OSError("injected old-author stage failure after rename")

    monkeypatch.setattr(regeneration.os, "replace", rename_then_fail)
    with pytest.raises(
        CourseRegenerationError,
        match="rolled back learner and author",
    ):
        apply_v4_regeneration(
            learner,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert failed is True
    assert regeneration._snapshot(learner) == old_learner
    assert regeneration._snapshot(learner_author) == old_author
    assert regeneration._snapshot(candidate) == candidate_learner
    assert regeneration._snapshot(candidate_author) == candidate_author_snapshot
    assert not rollback.exists()


def test_v4_cleanup_failure_keeps_verified_new_pair_and_reports_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learner, candidate, candidate_author, request = _targeted_v4_pair(tmp_path)
    learner_author = tmp_path / "course-author"
    plan = plan_v4_targeted_regeneration(
        learner,
        candidate_course=candidate,
        chapter_request=request,
    )
    plan_path = tmp_path / "cleanup-failure-plan.json"
    result_path = tmp_path / "cleanup-failure-result.json"
    _write_plan(plan_path, plan)
    rollback = Path(plan["rollback_path"])
    old_learner = regeneration._snapshot(learner)
    old_author = regeneration._snapshot(learner_author)
    candidate_learner = regeneration._snapshot(candidate)
    candidate_author_snapshot = regeneration._snapshot(candidate_author)

    def fail_cleanup(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected v4 cleanup failure")

    monkeypatch.setattr(
        regeneration,
        "_delete_bound_rollback_contents",
        fail_cleanup,
    )
    with pytest.raises(
        CourseRegenerationError,
        match="new pair remains installed",
    ):
        apply_v4_regeneration(
            learner,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
            result_path=result_path,
        )

    assert regeneration._snapshot(learner) == candidate_learner
    assert regeneration._snapshot(learner_author) == candidate_author_snapshot
    assert not candidate.exists()
    assert not candidate_author.exists()
    assert regeneration._snapshot(
        rollback / regeneration.ROLLBACK_LEARNER_NAME
    ) == old_learner
    assert regeneration._snapshot(
        rollback / regeneration.ROLLBACK_AUTHOR_NAME
    ) == old_author
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "applied"
    assert result["replacement_committed"] is True
    assert result["transaction_state"] == "cleanup_failed"
    assert result["cleanup_status"] == "failed"
    assert result["cleanup_residue_possible"] is True
    assert "rollback_retained" not in result
    assert "old_project_deleted" not in result
    assert "replacement_irreversible" not in result


def test_v4_cleanup_root_swap_preserves_foreign_tree_and_old_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learner, candidate, candidate_author, request = _targeted_v4_pair(tmp_path)
    learner_author = tmp_path / "course-author"
    plan = plan_v4_targeted_regeneration(
        learner,
        candidate_course=candidate,
        chapter_request=request,
    )
    plan_path = tmp_path / "cleanup-root-swap-plan.json"
    _write_plan(plan_path, plan)
    rollback = Path(plan["rollback_path"])
    captured_rollback = tmp_path / "captured-v4-old-pair"
    old_learner = regeneration._snapshot(learner)
    old_author = regeneration._snapshot(learner_author)
    candidate_learner = regeneration._snapshot(candidate)
    candidate_author_snapshot = regeneration._snapshot(candidate_author)
    real_validate = regeneration._validate_rollback_root

    def swap_root_after_validation(*args: object, **kwargs: object) -> object:
        bound = real_validate(*args, **kwargs)
        os.replace(rollback, captured_rollback)
        rollback.mkdir()
        (rollback / "foreign-marker.txt").write_text(
            "must survive\n",
            encoding="utf-8",
        )
        return bound

    monkeypatch.setattr(
        regeneration,
        "_validate_rollback_root",
        swap_root_after_validation,
    )
    with pytest.raises(
        CourseRegenerationError,
        match="new pair remains installed",
    ):
        apply_v4_regeneration(
            learner,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert regeneration._snapshot(learner) == candidate_learner
    assert regeneration._snapshot(learner_author) == candidate_author_snapshot
    assert not candidate.exists()
    assert not candidate_author.exists()
    assert (rollback / "foreign-marker.txt").read_text(
        encoding="utf-8"
    ) == "must survive\n"
    assert regeneration._snapshot(
        captured_rollback / regeneration.ROLLBACK_LEARNER_NAME
    ) == old_learner
    assert regeneration._snapshot(
        captured_rollback / regeneration.ROLLBACK_AUTHOR_NAME
    ) == old_author


def test_v4_partial_cleanup_never_restores_an_incomplete_old_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learner, candidate, candidate_author, request = _targeted_v4_pair(tmp_path)
    learner_author = tmp_path / "course-author"
    plan = plan_v4_targeted_regeneration(
        learner,
        candidate_course=candidate,
        chapter_request=request,
    )
    plan_path = tmp_path / "partial-cleanup-plan.json"
    _write_plan(plan_path, plan)
    rollback = Path(plan["rollback_path"])
    candidate_learner = regeneration._snapshot(candidate)
    candidate_author_snapshot = regeneration._snapshot(candidate_author)
    real_rmtree = regeneration.shutil.rmtree

    def partially_delete_then_fail(
        *_args: object,
        **_kwargs: object,
    ) -> None:
        assert rollback.is_dir()
        real_rmtree(rollback / regeneration.ROLLBACK_LEARNER_NAME)
        raise OSError("injected partial cleanup failure")

    monkeypatch.setattr(
        regeneration,
        "_delete_bound_rollback_contents",
        partially_delete_then_fail,
    )
    with pytest.raises(
        CourseRegenerationError,
        match="new pair remains installed",
    ):
        apply_v4_regeneration(
            learner,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert regeneration._snapshot(learner) == candidate_learner
    assert regeneration._snapshot(learner_author) == candidate_author_snapshot
    assert not candidate.exists()
    assert not candidate_author.exists()
    assert rollback.is_dir()
    assert not (rollback / regeneration.ROLLBACK_LEARNER_NAME).exists()
    assert (rollback / regeneration.ROLLBACK_AUTHOR_NAME).is_dir()


def test_v4_check_separates_content_from_runtime_contract_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path / "source")
    learner = tmp_path / "course"
    scaffold_v4_pair(route_path, packages, learner)
    generated = _generation(learner)

    changed_content = "a" * 64
    assert changed_content != generated["content_contract_sha256"]
    monkeypatch.setattr(
        regeneration,
        "v4_content_contract_sha256",
        lambda: changed_content,
    )
    content_plan = plan_v4_regeneration(learner)
    assert content_plan["status"] == "needs_content_regeneration"
    assert content_plan["required_action"] == "regenerate-content"
    assert content_plan["writer_calls"] == 3
    assert content_plan["chapter_ids"] == ["lab00", "lab01", "lab02"]

    monkeypatch.setattr(
        regeneration,
        "v4_content_contract_sha256",
        lambda: str(generated["content_contract_sha256"]),
    )
    changed_runtime = "b" * 64
    assert changed_runtime != generated["runtime_contract_sha256"]
    monkeypatch.setattr(
        regeneration,
        "v4_runtime_contract_sha256",
        lambda: changed_runtime,
    )
    monkeypatch.setattr(
        v4_verifier,
        "v4_runtime_contract_sha256",
        lambda: changed_runtime,
    )
    runtime_plan = plan_v4_regeneration(learner)
    assert runtime_plan["status"] == "needs_reexport_revalidation"
    assert runtime_plan["required_action"] == "re-export/revalidate"
    assert runtime_plan["writer_calls"] == 0
    assert runtime_plan["chapter_ids"] == []


def test_v4_check_and_apply_use_offline_receipt_without_recalling_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    route_path, packages, _route = write_v4_fixture(source)
    learner = tmp_path / "course"
    candidate = tmp_path / "candidate"
    scaffold_v4_pair(route_path, packages, learner)
    scaffold_v4_pair(route_path, packages, candidate)
    learner_author = tmp_path / "course-author"
    candidate_author = tmp_path / "candidate-author"

    generated = _generation(learner)
    changed_runtime = "c" * 64
    assert changed_runtime != generated["runtime_contract_sha256"]
    monkeypatch.setattr(
        regeneration,
        "v4_runtime_contract_sha256",
        lambda: changed_runtime,
    )
    monkeypatch.setattr(
        v4_verifier,
        "v4_runtime_contract_sha256",
        lambda: changed_runtime,
    )
    candidate_generation = _generation(candidate)
    candidate_generation["runtime_contract_sha256"] = changed_runtime
    _write_generation(candidate, candidate_generation)
    (candidate / "README.md").write_text(
        "# Refreshed v4 runtime export\n",
        encoding="utf-8",
    )
    verify_v4_course(candidate, author_root=candidate_author)

    def no_full_verifier(_candidate: Path) -> dict[str, object]:
        raise AssertionError("v4 check/apply must not rerun the full verifier")

    monkeypatch.setattr(regeneration, "_run_full_verifier", no_full_verifier)
    plan = plan_v4_regeneration(
        learner,
        candidate_course=candidate,
    )
    assert plan["status"] == "ready"
    assert plan["regeneration_kind"] == "needs_reexport_revalidation"
    assert plan["writer_calls"] == 0
    assert plan["chapter_ids"] == []
    assert plan["candidate_receipt"]["receipt_sha256"]

    plan_path = tmp_path / "v4-plan.json"
    _write_plan(plan_path, plan)
    result_path = tmp_path / "v4-result.json"
    assert main(
        [
            "apply",
            str(learner),
            "--candidate-course",
            str(candidate),
            "--plan",
            str(plan_path),
            "--confirm-stopped",
            "--accept-replacement",
            "--json",
            str(result_path),
        ]
    ) == 0
    result = json.loads(
        result_path.read_text(encoding="utf-8")
    )

    assert result["status"] == "applied"
    assert result["receipt_validation"] == "offline"
    assert result["writer_calls_during_apply"] == 0
    assert (learner / "README.md").read_text(encoding="utf-8") == (
        "# Refreshed v4 runtime export\n"
    )
    assert learner_author.is_dir()
    assert not candidate.exists()
    assert not candidate_author.exists()
    assert result["replacement_policy"] == "delete-old-after-success"
    assert result["rollback_retained"] is False
    assert result["backup_retained"] is False
    assert result["old_project_deleted"] is True
    assert result["replacement_irreversible"] is True
    assert not Path(result["rollback_path"]).exists()


def test_v4_second_candidate_rename_failure_rolls_back_both_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path / "source")
    learner = tmp_path / "course"
    candidate = tmp_path / "candidate"
    scaffold_v4_pair(route_path, packages, learner)
    scaffold_v4_pair(route_path, packages, candidate)
    learner_author = tmp_path / "course-author"
    candidate_author = tmp_path / "candidate-author"

    generated = _generation(learner)
    changed_runtime = "d" * 64
    monkeypatch.setattr(
        regeneration,
        "v4_runtime_contract_sha256",
        lambda: changed_runtime,
    )
    monkeypatch.setattr(
        v4_verifier,
        "v4_runtime_contract_sha256",
        lambda: changed_runtime,
    )
    candidate_generation = _generation(candidate)
    candidate_generation["runtime_contract_sha256"] = changed_runtime
    _write_generation(candidate, candidate_generation)
    verify_v4_course(candidate, author_root=candidate_author)
    plan = plan_v4_regeneration(
        learner,
        candidate_course=candidate,
    )
    assert plan["status"] == "ready"
    plan_path = tmp_path / "rollback-plan.json"
    _write_plan(plan_path, plan)

    old_learner = regeneration._snapshot(learner)
    old_author = regeneration._snapshot(learner_author)
    candidate_learner = regeneration._snapshot(candidate)
    candidate_author_snapshot = regeneration._snapshot(candidate_author)
    real_replace = os.replace
    failed = False

    def fail_second_candidate_rename(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
    ) -> None:
        nonlocal failed
        if (
            not failed
            and Path(source) == candidate_author
            and Path(destination) == learner_author
        ):
            failed = True
            raise OSError("injected author candidate rename failure")
        real_replace(source, destination)

    monkeypatch.setattr(regeneration.os, "replace", fail_second_candidate_rename)
    with pytest.raises(
        CourseRegenerationError,
        match="rolled back learner and author",
    ):
        apply_v4_regeneration(
            learner,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert failed is True
    assert regeneration._snapshot(learner) == old_learner
    assert regeneration._snapshot(learner_author) == old_author
    assert regeneration._snapshot(candidate) == candidate_learner
    assert regeneration._snapshot(candidate_author) == candidate_author_snapshot
    assert not Path(plan["rollback_path"]).exists()


@pytest.mark.parametrize("legacy_schema_version", (2, 3))
def test_explicit_legacy_to_v4_check_and_apply_installs_verified_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    legacy_schema_version: int,
) -> None:
    legacy = _make_legacy_course(
        tmp_path / "course",
        schema_version=legacy_schema_version,
    )
    _route_path, candidate, candidate_author = _verified_v4_candidate(
        tmp_path
    )
    author_destination = tmp_path / "course-author"
    old_snapshot = regeneration._snapshot(legacy)

    def no_full_verifier(_candidate: Path) -> dict[str, object]:
        raise AssertionError("legacy-to-v4 migration must use the offline receipt")

    monkeypatch.setattr(regeneration, "_run_full_verifier", no_full_verifier)
    plan_path = tmp_path / "migration-plan.json"
    assert main(
        [
            "check",
            str(legacy),
            "--candidate-course",
            str(candidate),
            "--json",
            str(plan_path),
        ]
    ) == 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["status"] == "ready"
    assert plan["migration_kind"] == "legacy-to-v4"
    assert plan["writer_calls"] == 0
    assert plan["chapter_ids"] == []
    assert plan["source_course_schema_version"] == legacy_schema_version
    assert plan["target_course_schema_version"] == 4
    assert plan["identity"] == {
        "course_id": "tiny-parser",
        "language": "zh-CN",
        "target": {
            "name": "json",
            "kind": "stdlib",
            "version": "Python 3.13",
            "track": "value conversion",
        },
    }
    assert plan["migration"]["curriculum_id_policy"] == (
        "new-v4-curriculum-id-allowed"
    )
    assert plan["migration"]["candidate_curriculum_id"] == (
        "tiny-parser-v4-fixture"
    )
    assert plan["candidate_receipt"]["receipt_sha256"]

    result_path = tmp_path / "migration-result.json"
    assert main(
        [
            "apply",
            str(legacy),
            "--candidate-course",
            str(candidate),
            "--plan",
            str(plan_path),
            "--confirm-stopped",
            "--accept-replacement",
            "--json",
            str(result_path),
        ]
    ) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "applied"
    assert result["migration_kind"] == "legacy-to-v4"
    assert result["receipt_validation"] == "offline"
    assert result["writer_calls_during_apply"] == 0
    assert regeneration._looks_like_v4_course(legacy)
    assert author_destination.is_dir()
    validate = regeneration.validate_v4_receipt(
        legacy,
        author_root=author_destination,
    )
    assert validate["receipt_sha256"] == plan["candidate_receipt"]["receipt_sha256"]
    assert result["old_snapshot_sha256"] == old_snapshot
    assert result["replacement_policy"] == "delete-old-after-success"
    assert result["rollback_retained"] is False
    assert result["backup_retained"] is False
    assert result["old_project_deleted"] is True
    assert result["replacement_irreversible"] is True
    assert not Path(result["rollback_path"]).exists()
    assert not candidate.exists()
    assert not candidate_author.exists()


@pytest.mark.parametrize(
    ("field", "replacement", "expected_mismatch"),
    (
        ("course_id", "different-course", "course_id"),
        ("language", "en", "language"),
        ("name", "pathlib", "target.name"),
        ("kind", "pypi", "target.kind"),
        ("version", "Python 3.14", "target.version"),
        ("track", "different track", "target.track"),
    ),
)
def test_explicit_legacy_to_v4_blocks_locked_identity_changes(
    tmp_path: Path,
    field: str,
    replacement: str,
    expected_mismatch: str,
) -> None:
    case = tmp_path / field
    legacy = _make_legacy_course(case / "course")
    route_path, packages, route = write_v4_fixture(case / "source")
    if field == "course_id":
        route["course"]["id"] = replacement
    elif field == "language":
        route["course"]["language"] = replacement
    else:
        route["target"][field] = replacement
    route_path.write_text(
        json.dumps(route, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    candidate = case / "candidate"
    scaffold_v4_pair(route_path, packages, candidate)
    candidate_author = case / "candidate-author"
    verify_v4_course(candidate, author_root=candidate_author)

    plan = regeneration.plan_regeneration(
        legacy,
        candidate_course=candidate,
    )
    assert plan["status"] == "blocked"
    assert expected_mismatch in plan["identity_mismatches"]
    assert {
        blocker["code"] for blocker in plan["blockers"]
    } == {"migration-identity-mismatch"}


def test_legacy_to_v4_second_rename_failure_restores_single_legacy_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _make_legacy_course(tmp_path / "course")
    _route_path, candidate, candidate_author = _verified_v4_candidate(
        tmp_path
    )
    author_destination = tmp_path / "course-author"
    plan = regeneration.plan_regeneration(
        legacy,
        candidate_course=candidate,
    )
    assert plan["status"] == "ready"
    plan_path = tmp_path / "migration-rollback-plan.json"
    _write_plan(plan_path, plan)

    old_snapshot = regeneration._snapshot(legacy)
    candidate_snapshot = regeneration._snapshot(candidate)
    candidate_author_snapshot = regeneration._snapshot(candidate_author)
    real_replace = os.replace
    failed = False

    def fail_author_install(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
    ) -> None:
        nonlocal failed
        if (
            not failed
            and Path(source) == candidate_author
            and Path(destination) == author_destination
        ):
            failed = True
            raise OSError("injected migration author rename failure")
        real_replace(source, destination)

    monkeypatch.setattr(regeneration.os, "replace", fail_author_install)
    monkeypatch.setattr(
        regeneration,
        "_run_full_verifier",
        lambda _candidate: (_ for _ in ()).throw(
            AssertionError("migration cannot invoke full verifier")
        ),
    )
    with pytest.raises(
        CourseRegenerationError,
        match="rolled back legacy root with no author destination",
    ):
        regeneration.apply_regeneration(
            legacy,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert failed is True
    assert regeneration._snapshot(legacy) == old_snapshot
    assert not author_destination.exists()
    assert regeneration._snapshot(candidate) == candidate_snapshot
    assert regeneration._snapshot(candidate_author) == candidate_author_snapshot
    assert not Path(plan["rollback_path"]).exists()


def test_legacy_to_v4_author_destination_race_still_restores_legacy_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _make_legacy_course(tmp_path / "course")
    _route_path, candidate, candidate_author = _verified_v4_candidate(
        tmp_path
    )
    author_destination = tmp_path / "course-author"
    plan = regeneration.plan_regeneration(
        legacy,
        candidate_course=candidate,
    )
    plan_path = tmp_path / "migration-author-race-plan.json"
    _write_plan(plan_path, plan)
    rollback = Path(plan["rollback_path"])
    staged_learner = rollback / regeneration.ROLLBACK_LEARNER_NAME
    old_snapshot = regeneration._snapshot(legacy)
    candidate_snapshot = regeneration._snapshot(candidate)
    candidate_author_snapshot = regeneration._snapshot(candidate_author)
    real_replace = os.replace
    injected = False

    def create_foreign_author_after_staging(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
    ) -> None:
        nonlocal injected
        real_replace(source, destination)
        if (
            not injected
            and Path(source) == legacy
            and Path(destination) == staged_learner
        ):
            injected = True
            author_destination.mkdir()
            (author_destination / "foreign.txt").write_text(
                "do not overwrite\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(
        regeneration.os,
        "replace",
        create_foreign_author_after_staging,
    )
    with pytest.raises(
        CourseRegenerationError,
        match="manual recovery required",
    ):
        regeneration.apply_regeneration(
            legacy,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert injected is True
    assert regeneration._snapshot(legacy) == old_snapshot
    assert regeneration._snapshot(candidate) == candidate_snapshot
    assert regeneration._snapshot(candidate_author) == candidate_author_snapshot
    assert (author_destination / "foreign.txt").read_text(
        encoding="utf-8"
    ) == "do not overwrite\n"
    assert not rollback.exists()
