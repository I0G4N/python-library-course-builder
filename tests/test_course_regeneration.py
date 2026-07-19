from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from typing import Callable

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ROOT
    / "plugins/python-library-course-builder/skills/building-python-library-courses/scripts"
)
REGENERATION_PATH = SCRIPTS / "regenerate_course.py"
UPDATE_PATH = SCRIPTS / "update_course.py"
sys.path.insert(0, str(SCRIPTS))

import scaffold_course  # noqa: E402
from tests.course_v3_fixture import make_v3_spec_and_plan  # noqa: E402


def _load_regenerator() -> ModuleType:
    name = "course_regeneration_contract_under_test"
    spec = importlib.util.spec_from_file_location(name, REGENERATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def regenerator() -> ModuleType:
    return _load_regenerator()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _make_course(
    root: Path,
    *,
    tutorial: str,
    with_git: bool,
    progress: bool = False,
    locale: str = "zh-CN",
    track: str | None = "core",
    route_id: str = "json-route",
) -> Path:
    _write_json(
        root / "platform/course/source/course.json",
        {
            "schema_version": 3,
            "id": "json-course",
            "title": "JSON course",
            "language": locale,
            "audience": {
                "prerequisite_profile": {"route_id": route_id},
            },
            "manifest": {
                "target": {
                    "name": "json",
                    "kind": "stdlib",
                    "version": "3.13",
                    "track": track,
                },
            },
        },
    )
    (root / "platform/course/source/labs/lab01").mkdir(parents=True)
    (root / "platform/course/source/labs/lab01/tutorial.md").write_text(
        tutorial, encoding="utf-8"
    )
    _write_json(root / "platform/course/manifest.json", {"curriculum_id": tutorial})
    _write_json(root / "labs/manifest.json", {"course_id": "json-course"})
    (root / "labs/lab01").mkdir(parents=True)
    (root / "labs/lab01/README.md").write_text(tutorial, encoding="utf-8")
    _write_json(root / "platform/coursekit-generation.json", {"fixture": True})
    if progress:
        _write_json(root / "labs/.coursekit/state.json", {"completed_labs": ["lab01"]})
        (root / "learner-note.txt").write_text("keep me exactly\n", encoding="utf-8")
    if with_git:
        _git(root, "init", "-q")
        _git(root, "add", ".")
        _git(
            root,
            "-c",
            "user.name=CourseKit",
            "-c",
            "user.email=coursekit@localhost",
            "commit",
            "-q",
            "-m",
            "coursekit: generated baseline",
        )
    return root


def _install_contract_fakes(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    verification_passed: bool = True,
) -> None:
    current = "c" * 64
    old = "b" * 64
    runtime = regenerator.RuntimeContract("0.3.0", current)
    monkeypatch.setattr(regenerator, "_current_runtime", lambda: runtime)

    def baseline(root: Path, *, verify_hashes: bool = False) -> object:
        if (root / ".git").is_dir():
            assert verify_hashes is True
            return regenerator.CourseBaseline("provenance", 2, "0.3.0", current)
        assert verify_hashes is False
        return regenerator.CourseBaseline("provenance", 1, "0.2.0", old)

    monkeypatch.setattr(regenerator, "_load_course_baseline", baseline)
    monkeypatch.setattr(
        regenerator,
        "load_generation_provenance",
        lambda root, *, verify_hashes=False: {"schema_version": 2},
    )

    def regeneration_metadata(root: Path) -> dict[str, object]:
        source = json.loads(
            (root / "platform/course/source/course.json").read_text(encoding="utf-8")
        )
        profile = source["audience"]["prerequisite_profile"]
        route_id = profile.get("route_id")
        return {
            "route_intent": {
                "course_id": source["id"],
                "course_title": source["title"],
                "route_id": route_id,
                "route_title": f"{route_id}-title" if route_id is not None else None,
            }
        }

    monkeypatch.setattr(
        regenerator,
        "load_regeneration_metadata",
        regeneration_metadata,
    )
    monkeypatch.setattr(
        regenerator,
        "_run_full_verifier",
        lambda candidate: {
            "passed": verification_passed,
            "full_node_runner": verification_passed,
        },
    )


def test_check_uses_authoring_fingerprint_not_bundle_or_version(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(tmp_path / "course", tutorial="old tutorial\n", with_git=False)
    runtime = regenerator.RuntimeContract("0.3.0", "a" * 64)
    monkeypatch.setattr(regenerator, "_current_runtime", lambda: runtime)

    monkeypatch.setattr(
        regenerator,
        "_load_course_baseline",
        lambda root: regenerator.CourseBaseline(
            "provenance", 2, "0.2.0", "a" * 64
        ),
    )
    plan = regenerator.plan_regeneration(live)
    assert plan["status"] == "up_to_date"

    monkeypatch.setattr(
        regenerator,
        "_load_course_baseline",
        lambda root: regenerator.CourseBaseline(
            "provenance", 2, "0.2.0", "b" * 64
        ),
    )
    plan = regenerator.plan_regeneration(live)
    assert plan["status"] == "regeneration_required"
    assert plan["readiness_strategy"]["mode"] == "full_readiness"


def test_current_scaffold_has_a_hash_verified_v2_baseline(
    regenerator: ModuleType,
    tmp_path: Path,
) -> None:
    spec, readiness = make_v3_spec_and_plan(language="zh-CN")
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, spec)
    course = tmp_path / "course"
    scaffold_course.scaffold(spec_path, course, readiness_plan=readiness)

    runtime = regenerator._current_runtime()
    baseline = regenerator._load_course_baseline(course, verify_hashes=True)
    assert baseline.schema_version == 2
    assert baseline.plugin_version == runtime.plugin_version
    assert baseline.authoring_contract_sha256 == runtime.authoring_contract_sha256
    assert regenerator._regeneration_state(baseline, runtime)[0] == "up_to_date"


def test_same_version_collision_and_downgrade_fail_closed(
    regenerator: ModuleType,
) -> None:
    runtime = regenerator.RuntimeContract("0.3.0", "a" * 64)
    with pytest.raises(regenerator.CourseRegenerationError, match="collision"):
        regenerator._regeneration_state(
            regenerator.CourseBaseline("provenance", 2, "0.3.0", "b" * 64),
            runtime,
        )
    with pytest.raises(regenerator.CourseRegenerationError, match="downgrade"):
        regenerator._regeneration_state(
            regenerator.CourseBaseline("provenance", 2, "0.4.0", "a" * 64),
            runtime,
        )


def test_ready_plan_binds_full_diff_and_atomically_replaces_whole_course(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False, progress=True
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)
    old_snapshot = regenerator._snapshot(live)
    candidate_snapshot = regenerator._snapshot(candidate)
    plan_path = tmp_path / "plan.json"

    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)

    assert plan["status"] == "ready"
    assert plan["full_verification"]["passed"] is True
    assert plan["material_learner_facing_diff"]["changed"] is True
    assert plan["live_canonical_source_sha256"] != plan[
        "candidate_canonical_source_sha256"
    ]
    result = regenerator.apply_regeneration(
        live,
        candidate_course=candidate,
        plan_path=plan_path,
        confirm_stopped=True,
        accept_replacement=True,
    )

    backup = Path(result["backup_path"])
    assert result["status"] == "applied"
    assert backup.parent == live.parent
    assert backup.name.startswith("course.coursekit-backup-")
    assert regenerator._snapshot(backup) == old_snapshot
    assert (backup / "learner-note.txt").read_text(encoding="utf-8") == "keep me exactly\n"
    assert (backup / "labs/.coursekit/state.json").is_file()
    assert regenerator._snapshot(live) == candidate_snapshot
    assert not (live / "labs/.coursekit/state.json").exists()
    assert not candidate.exists()
    assert _git(live, "rev-list", "--count", "HEAD") == "1"


def test_failed_second_rename_restores_old_course_and_candidate(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False, progress=True
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    old_snapshot = regenerator._snapshot(live)
    candidate_snapshot = regenerator._snapshot(candidate)
    original_replace: Callable[..., object] = regenerator.os.replace
    injected = False

    def replace_then_fail(source: object, destination: object) -> object:
        nonlocal injected
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path == candidate and destination_path == live and not injected:
            injected = True
            original_replace(source, destination)
            raise OSError("injected second rename failure")
        return original_replace(source, destination)

    monkeypatch.setattr(regenerator.os, "replace", replace_then_fail)
    with pytest.raises(regenerator.CourseRegenerationError, match="rolled back"):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert injected is True
    assert regenerator._snapshot(live) == old_snapshot
    assert regenerator._snapshot(candidate) == candidate_snapshot
    assert not Path(plan["backup_path"]).exists()


def test_failed_first_rename_after_mutation_restores_old_course_and_candidate(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False, progress=True
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    old_snapshot = regenerator._snapshot(live)
    candidate_snapshot = regenerator._snapshot(candidate)
    backup = Path(plan["backup_path"])
    original_replace: Callable[..., object] = regenerator.os.replace
    injected = False

    def replace_then_fail(source: object, destination: object) -> object:
        nonlocal injected
        result = original_replace(source, destination)
        if Path(source) == live and Path(destination) == backup and not injected:
            injected = True
            raise OSError("injected first rename failure after mutation")
        return result

    monkeypatch.setattr(regenerator.os, "replace", replace_then_fail)
    with pytest.raises(regenerator.CourseRegenerationError, match="rolled back"):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert injected is True
    assert regenerator._snapshot(live) == old_snapshot
    assert regenerator._snapshot(candidate) == candidate_snapshot
    assert not backup.exists()


def test_stale_candidate_is_rejected_before_live_rename(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(tmp_path / "course", tutorial="old tutorial\n", with_git=False)
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    before = regenerator._snapshot(live)
    (candidate / "labs/lab01/README.md").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(regenerator.CourseRegenerationError, match="candidate"):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )
    assert regenerator._snapshot(live) == before
    assert not Path(plan["backup_path"]).exists()


def test_verifier_failure_blocks_and_candidate_must_be_a_sibling(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(tmp_path / "course", tutorial="old tutorial\n", with_git=False)
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch, verification_passed=False)

    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    assert plan["status"] == "blocked"
    assert "verification-failed" in {item["code"] for item in plan["blockers"]}

    outside = tmp_path / "other"
    outside.mkdir()
    non_sibling = _make_course(
        outside / "candidate", tutorial="new tutorial\n", with_git=True
    )
    with pytest.raises(regenerator.CourseRegenerationError, match="sibling"):
        regenerator.plan_regeneration(live, candidate_course=non_sibling)


def test_candidate_cannot_change_locked_route_intent(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course",
        tutorial="old tutorial\n",
        with_git=False,
        route_id="json-core",
    )
    candidate = _make_course(
        tmp_path / "candidate",
        tutorial="new tutorial\n",
        with_git=True,
        route_id="json-advanced",
    )
    _install_contract_fakes(regenerator, monkeypatch)

    plan = regenerator.plan_regeneration(live, candidate_course=candidate)

    assert plan["status"] == "blocked"
    assert "route-intent-mismatch" in {
        blocker["code"] for blocker in plan["blockers"]
    }


def test_route_intent_falls_back_for_live_but_is_strict_for_candidate(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    course = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False
    )

    def invalid_provenance(root: Path, *, verify_hashes: bool = False) -> object:
        assert verify_hashes is True
        raise regenerator.ProvenanceError("regeneration input hash mismatch")

    monkeypatch.setattr(regenerator, "load_generation_provenance", invalid_provenance)
    assert regenerator._route_intent(
        course,
        require_regeneration_metadata=False,
    ) == {
        "course_id": "json-course",
        "course_title": "JSON course",
        "route_id": "json-route",
        "route_title": None,
    }
    with pytest.raises(
        regenerator.CourseRegenerationError,
        match="invalid course regeneration metadata",
    ):
        regenerator._route_intent(
            course,
            require_regeneration_metadata=True,
        )


def test_legacy_provenance_cannot_authenticate_an_added_sidecar(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    course = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False
    )
    monkeypatch.setattr(
        regenerator,
        "load_generation_provenance",
        lambda root, *, verify_hashes=False: {"schema_version": 1},
    )

    def must_not_load_metadata(root: Path) -> object:
        raise AssertionError(f"legacy sidecar was trusted: {root}")

    monkeypatch.setattr(
        regenerator,
        "load_regeneration_metadata",
        must_not_load_metadata,
    )
    fallback = regenerator._route_intent(
        course,
        require_regeneration_metadata=False,
    )
    assert fallback["route_id"] == "json-route"
    assert fallback["route_title"] is None
    with pytest.raises(
        regenerator.CourseRegenerationError,
        match="legacy provenance cannot authenticate regeneration metadata",
    ):
        regenerator._route_intent(
            course,
            require_regeneration_metadata=True,
        )


def test_dirty_candidate_is_never_executed(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(tmp_path / "course", tutorial="old tutorial\n", with_git=False)
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    (candidate / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    _install_contract_fakes(regenerator, monkeypatch)

    def must_not_run(root: Path) -> dict[str, object]:
        raise AssertionError(f"dirty candidate was executed: {root}")

    monkeypatch.setattr(regenerator, "_run_full_verifier", must_not_run)
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)

    assert "candidate-not-fresh" in {
        blocker["code"] for blocker in plan["blockers"]
    }
    assert plan["full_verification"] == {
        "passed": False,
        "skipped": True,
        "reason": "candidate failed the pre-verification freshness gate",
    }


def test_whitespace_only_tutorial_change_is_not_material(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="same tutorial\n", with_git=False
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="  same   tutorial\n\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)

    diff = regenerator._material_diff(live, candidate)

    assert diff["changed"] is False, diff
    assert diff["changed_paths"] == []


def test_material_normalization_preserves_semantic_code_whitespace(
    regenerator: ModuleType,
) -> None:
    fenced_indented = b"Before\n\n```python\n    value = 1\n```\n"
    fenced_flat = b"Before\n\n```python\nvalue = 1\n```\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", fenced_indented
    ) != regenerator._normalized_learner_content("tutorial.md", fenced_flat)

    lower_language = b"```python\nprint(1)\n```\n"
    upper_language = b"```PYTHON\nprint(1)\n```   \n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", lower_language
    ) == regenerator._normalized_learner_content("tutorial.md", upper_language)
    short_language = b"```py\nprint(1)\n```\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", lower_language
    ) == regenerator._normalized_learner_content("tutorial.md", short_language)

    string_with_blank = b'value = """first\n\nsecond"""\n'
    string_without_blank = b'value = """first\nsecond"""\n'
    assert regenerator._normalized_learner_content(
        "starter/example.py", string_with_blank
    ) != regenerator._normalized_learner_content(
        "starter/example.py", string_without_blank
    )

    nested_list = b"- outer\n  - inner\n"
    flat_list = b"- outer\n- inner\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", nested_list
    ) != regenerator._normalized_learner_content("tutorial.md", flat_list)

    heading_and_paragraph = b"# Heading\nParagraph\n"
    single_heading = b"# Heading Paragraph\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", heading_and_paragraph
    ) != regenerator._normalized_learner_content("tutorial.md", single_heading)

    inline_spaced = b"Use `value  with  spaces`.\n"
    inline_flat = b"Use `value with spaces`.\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", inline_spaced
    ) != regenerator._normalized_learner_content("tutorial.md", inline_flat)

    outside_spaced = b"Use   `value`   now.\n"
    outside_flat = b"Use `value` now.\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", outside_spaced
    ) == regenerator._normalized_learner_content("tutorial.md", outside_flat)

    hard_break = b"first line  \nsecond line\n"
    soft_wrap = b"first line\nsecond line\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", hard_break
    ) != regenerator._normalized_learner_content("tutorial.md", soft_wrap)

    indented_blank = b"    first\n\n    second\n"
    indented_compact = b"    first\n    second\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", indented_blank
    ) != regenerator._normalized_learner_content("tutorial.md", indented_compact)

    thematic_break = b"before\n---\nafter\n"
    inline_dashes = b"before --- after\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", thematic_break
    ) != regenerator._normalized_learner_content("tutorial.md", inline_dashes)

    table = b"Name | Value\n--- | ---\nalpha | 1\n"
    inline_table_text = b"Name | Value --- | --- alpha | 1\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", table
    ) != regenerator._normalized_learner_content("tutorial.md", inline_table_text)

    paragraph_then_table_text = b"Intro\nName | Value\n--- | ---\nalpha | 1\n"
    paragraph_then_table = b"Intro\n\nName | Value\n--- | ---\nalpha | 1\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", paragraph_then_table_text
    ) != regenerator._normalized_learner_content(
        "tutorial.md", paragraph_then_table
    )

    heading_paragraph_table_text = (
        b"# Heading\nIntro\nName | Value\n--- | ---\nalpha | 1\n"
    )
    heading_paragraph_table = (
        b"# Heading\nIntro\n\nName | Value\n--- | ---\nalpha | 1\n"
    )
    assert regenerator._normalized_learner_content(
        "tutorial.md", heading_paragraph_table_text
    ) != regenerator._normalized_learner_content(
        "tutorial.md", heading_paragraph_table
    )

    formatted_table = b"| Name  | Value |\n| :--- | ---: |\n| alpha | 1 |\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", table
    ) == regenerator._normalized_learner_content("tutorial.md", formatted_table)

    one_ordered_list = b"1. first\n1. second\n"
    two_ordered_lists = b"1. first\n\n1. second\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", one_ordered_list
    ) != regenerator._normalized_learner_content("tutorial.md", two_ordered_lists)

    continued_list = b"1. first\n   continuation\n1. second\n"
    split_continued_list = b"1. first\n   continuation\n\n1. second\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", continued_list
    ) != regenerator._normalized_learner_content(
        "tutorial.md", split_continued_list
    )

    adjacent_mixed_lists = b"1. first\n- second\n"
    separated_mixed_lists = b"1. first\n\n- second\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", adjacent_mixed_lists
    ) == regenerator._normalized_learner_content(
        "tutorial.md", separated_mixed_lists
    )

    one_quote = b"> first\n> second\n"
    two_quotes = b"> first\n\n> second\n"
    assert regenerator._normalized_learner_content(
        "tutorial.md", one_quote
    ) != regenerator._normalized_learner_content("tutorial.md", two_quotes)


def test_forged_failed_verification_plan_is_rechecked_during_apply(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(tmp_path / "course", tutorial="old tutorial\n", with_git=False)
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(
        regenerator,
        monkeypatch,
        verification_passed=False,
    )
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    assert plan["status"] == "blocked"
    forged = dict(plan)
    forged.pop("plan_digest")
    forged["status"] = "ready"
    forged["blockers"] = []
    forged["full_verification"] = {"passed": True}
    forged = regenerator._finish_plan(forged)
    plan_path = tmp_path / "forged-plan.json"
    regenerator._write_json(plan_path, forged)

    with pytest.raises(
        regenerator.CourseRegenerationError,
        match="failed full verification during apply",
    ):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert not Path(plan["backup_path"]).exists()


def test_forged_nonmaterial_plan_is_rejected_during_apply(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(tmp_path / "course", tutorial="same tutorial\n", with_git=False)
    candidate = _make_course(
        tmp_path / "candidate", tutorial="same tutorial\n", with_git=True
    )
    source_path = candidate / "platform/course/source/course.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["research_marker"] = "new authoring metadata only"
    _write_json(source_path, source)
    _git(candidate, "add", ".")
    _git(
        candidate,
        "-c",
        "user.name=CourseKit",
        "-c",
        "user.email=coursekit@localhost",
        "commit",
        "-q",
        "--amend",
        "--no-edit",
    )
    _install_contract_fakes(regenerator, monkeypatch)
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    assert "learner-content-unchanged" in {
        blocker["code"] for blocker in plan["blockers"]
    }
    forged = dict(plan)
    forged.pop("plan_digest")
    forged["status"] = "ready"
    forged["blockers"] = []
    forged = regenerator._finish_plan(forged)
    plan_path = tmp_path / "forged-nonmaterial-plan.json"
    regenerator._write_json(plan_path, forged)

    with pytest.raises(
        regenerator.CourseRegenerationError,
        match="no material learner-facing change",
    ):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert not Path(plan["backup_path"]).exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("language", "fr", "locale must be zh-CN or en"),
        ("title", "", "identity is incomplete"),
    ),
)
def test_invalid_canonical_identity_fails_closed(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    live = _make_course(tmp_path / "course", tutorial="old tutorial\n", with_git=False)
    source_path = live / "platform/course/source/course.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source[field] = value
    _write_json(source_path, source)
    _install_contract_fakes(regenerator, monkeypatch)

    with pytest.raises(regenerator.CourseRegenerationError, match=message):
        regenerator.plan_regeneration(live)


def test_progress_or_provenance_alone_cannot_satisfy_material_diff(
    regenerator: ModuleType,
    tmp_path: Path,
) -> None:
    live = _make_course(tmp_path / "course", tutorial="same\n", with_git=False)
    candidate = _make_course(tmp_path / "candidate", tutorial="same\n", with_git=True)
    _write_json(live / "labs/.coursekit/state.json", {"score": 10})
    (live / "labs/lab01/answer.py").write_text(
        "# learner-authored work must not count as new course content\n",
        encoding="utf-8",
    )
    _write_json(candidate / "platform/coursekit-generation.json", {"different": True})
    (live / "README.md").write_text("old template\n", encoding="utf-8")
    (candidate / "README.md").write_text("new template\n", encoding="utf-8")
    cache = candidate / "platform/course/starter/_course/coursekit/__pycache__"
    cache.mkdir(parents=True)
    (cache / "locale.cpython-313.pyc").write_bytes(b"runtime cache only")
    _write_json(
        candidate / "platform/course/source/course.json",
        {"schema_version": 3, "research_only_change": True},
    )

    diff = regenerator._material_diff(live, candidate)
    assert diff["changed"] is False


@pytest.mark.parametrize(
    "artifact",
    (
        "platform/course/starter/.pytest_cache/v/cache/nodeids",
        "platform/course/starter/.mypy_cache/3.13/cache.json",
        "platform/course/starter/.ruff_cache/0.12.0/cache",
        "platform/course/starter/.tox/py313/bin/python",
        "platform/course/starter/example.egg-info/PKG-INFO",
        "platform/course/starter/.DS_Store",
        "platform/course/starter/tsconfig.tsbuildinfo",
    ),
)
def test_ignored_runtime_artifact_cannot_satisfy_material_diff(
    regenerator: ModuleType,
    tmp_path: Path,
    artifact: str,
) -> None:
    live = _make_course(tmp_path / "course", tutorial="same\n", with_git=False)
    candidate = _make_course(
        tmp_path / "candidate", tutorial="same\n", with_git=True
    )
    artifact_path = candidate / artifact
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("runtime cache only\n", encoding="utf-8")

    diff = regenerator._material_diff(live, candidate)

    assert diff["changed"] is False
    assert diff["changed_paths"] == []


def test_apply_accepts_verifier_refresh_of_ignored_runtime_artifacts(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    (candidate / ".gitignore").write_text(".pytest_cache/\n", encoding="utf-8")
    _git(candidate, "add", ".gitignore")
    _git(
        candidate,
        "-c",
        "user.name=CourseKit",
        "-c",
        "user.email=coursekit@localhost",
        "commit",
        "-q",
        "--amend",
        "--no-edit",
    )
    _install_contract_fakes(regenerator, monkeypatch)
    verifier_calls = 0
    cache = candidate / "platform/course/.pytest_cache/v/cache/nodeids"

    def verifier(root: Path) -> dict[str, object]:
        nonlocal verifier_calls
        assert root == candidate
        verifier_calls += 1
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(f"verification {verifier_calls}\n", encoding="utf-8")
        return {"passed": True, "full_node_runner": True}

    monkeypatch.setattr(regenerator, "_run_full_verifier", verifier)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)

    result = regenerator.apply_regeneration(
        live,
        candidate_course=candidate,
        plan_path=plan_path,
        confirm_stopped=True,
        accept_replacement=True,
    )

    installed_cache = live / cache.relative_to(candidate)
    assert verifier_calls == 2
    assert installed_cache.read_text(encoding="utf-8") == "verification 2\n"
    assert result["new_snapshot_sha256"] == regenerator._snapshot(live)
    assert not candidate.exists()


def test_candidate_hardlink_cannot_couple_new_course_to_permanent_backup(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    live_manifest = live / "labs/manifest.json"
    candidate_manifest = candidate / "labs/manifest.json"
    candidate_manifest.unlink()
    os.link(live_manifest, candidate_manifest)
    assert live_manifest.stat().st_ino == candidate_manifest.stat().st_ino
    assert _git(candidate, "status", "--short") == ""
    _install_contract_fakes(regenerator, monkeypatch)

    plan = regenerator.plan_regeneration(live, candidate_course=candidate)

    assert plan["status"] == "blocked"
    blocker = next(
        item for item in plan["blockers"] if item["code"] == "candidate-not-fresh"
    )
    assert "hard-linked files" in blocker["message"]
    assert not Path(plan["backup_path"]).exists()


def test_candidate_allows_hardlinks_fully_contained_in_runtime_artifacts(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    (candidate / ".gitignore").write_text(
        ".uv-cache/\n.venv/\n",
        encoding="utf-8",
    )
    _git(candidate, "add", ".gitignore")
    _git(
        candidate,
        "-c",
        "user.name=CourseKit",
        "-c",
        "user.email=coursekit@localhost",
        "commit",
        "-q",
        "--amend",
        "--no-edit",
    )
    cache_file = candidate / "platform/.uv-cache/archive/package.py"
    environment_file = candidate / "platform/.venv/lib/package.py"
    cache_file.parent.mkdir(parents=True)
    environment_file.parent.mkdir(parents=True)
    cache_file.write_text("value = 1\n", encoding="utf-8")
    os.link(cache_file, environment_file)
    assert cache_file.stat().st_ino == environment_file.stat().st_ino
    _install_contract_fakes(regenerator, monkeypatch)

    plan = regenerator.plan_regeneration(live, candidate_course=candidate)

    assert plan["status"] == "ready", plan["blockers"]


def test_apply_rejects_mode_change_hidden_by_git_configuration(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    script = candidate / "run.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o644)
    _git(candidate, "add", "run.sh")
    _git(
        candidate,
        "-c",
        "user.name=CourseKit",
        "-c",
        "user.email=coursekit@localhost",
        "commit",
        "-q",
        "--amend",
        "--no-edit",
    )
    _git(candidate, "config", "core.filemode", "false")
    _install_contract_fakes(regenerator, monkeypatch)
    verifier_calls = 0

    def verifier(root: Path) -> dict[str, object]:
        nonlocal verifier_calls
        verifier_calls += 1
        if verifier_calls == 2:
            (root / "run.sh").chmod(0o755)
        return {"passed": True, "full_node_runner": True}

    monkeypatch.setattr(regenerator, "_run_full_verifier", verifier)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    old_snapshot = regenerator._snapshot(live)

    with pytest.raises(
        regenerator.CourseRegenerationError,
        match="non-runtime files",
    ):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert verifier_calls == 2
    assert regenerator._snapshot(live) == old_snapshot
    assert not Path(plan["backup_path"]).exists()


def test_apply_rejects_arbitrary_git_ignored_file_created_by_verifier(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    (candidate / ".gitignore").write_text("sitecustomize.py\n", encoding="utf-8")
    _git(candidate, "add", ".gitignore")
    _git(
        candidate,
        "-c",
        "user.name=CourseKit",
        "-c",
        "user.email=coursekit@localhost",
        "commit",
        "-q",
        "--amend",
        "--no-edit",
    )
    _install_contract_fakes(regenerator, monkeypatch)
    verifier_calls = 0

    def verifier(root: Path) -> dict[str, object]:
        nonlocal verifier_calls
        verifier_calls += 1
        if verifier_calls == 2:
            (root / "sitecustomize.py").write_text(
                "raise RuntimeError('must not be installed')\n",
                encoding="utf-8",
            )
        return {"passed": True, "full_node_runner": True}

    monkeypatch.setattr(regenerator, "_run_full_verifier", verifier)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    old_snapshot = regenerator._snapshot(live)

    with pytest.raises(
        regenerator.CourseRegenerationError,
        match="unexpected Git-ignored files|non-runtime files",
    ):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert verifier_calls == 2
    assert regenerator._snapshot(live) == old_snapshot
    assert not Path(plan["backup_path"]).exists()


def test_apply_rejects_git_hook_created_by_verifier(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)
    verifier_calls = 0

    def verifier(root: Path) -> dict[str, object]:
        nonlocal verifier_calls
        verifier_calls += 1
        if verifier_calls == 2:
            hook = root / ".git/hooks/post-commit"
            hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        return {"passed": True, "full_node_runner": True}

    monkeypatch.setattr(regenerator, "_run_full_verifier", verifier)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    old_snapshot = regenerator._snapshot(live)

    with pytest.raises(
        regenerator.CourseRegenerationError,
        match="non-runtime files",
    ):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert verifier_calls == 2
    assert regenerator._snapshot(live) == old_snapshot
    assert not Path(plan["backup_path"]).exists()


def test_apply_rejects_semantic_git_index_flags_created_by_verifier(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)
    verifier_calls = 0

    def verifier(root: Path) -> dict[str, object]:
        nonlocal verifier_calls
        verifier_calls += 1
        if verifier_calls == 2:
            updated = regenerator._git(
                root,
                "update-index",
                "--skip-worktree",
                "labs/manifest.json",
            )
            assert updated.returncode == 0, updated.stderr
        return {"passed": True, "full_node_runner": True}

    monkeypatch.setattr(regenerator, "_run_full_verifier", verifier)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    old_snapshot = regenerator._snapshot(live)

    with pytest.raises(
        regenerator.CourseRegenerationError,
        match="noncanonical flags or stages",
    ):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert verifier_calls == 2
    assert regenerator._snapshot(live) == old_snapshot
    assert not Path(plan["backup_path"]).exists()


def test_legacy_course_must_own_its_git_repository(
    regenerator: ModuleType,
    tmp_path: Path,
) -> None:
    parent = tmp_path / "outer"
    course = _make_course(
        parent / "course", tutorial="legacy tutorial\n", with_git=False
    )
    (course / "platform/coursekit-generation.json").unlink()
    _git(parent, "init", "-q")
    _git(parent, "add", ".")
    _git(
        parent,
        "-c",
        "user.name=CourseKit",
        "-c",
        "user.email=coursekit@localhost",
        "commit",
        "-q",
        "-m",
        "coursekit: generated baseline",
    )

    with pytest.raises(regenerator.CourseRegenerationError, match="does not own"):
        regenerator._load_course_baseline(course)


def test_post_swap_snapshot_error_rolls_back_both_roots(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False, progress=True
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    backup = Path(plan["backup_path"])
    old_snapshot = regenerator._snapshot(live)
    candidate_snapshot = regenerator._snapshot(candidate)
    original_snapshot = regenerator._snapshot
    injected = False

    def fail_once_after_swap(root: Path) -> str:
        nonlocal injected
        if Path(root) == backup and backup.exists() and not injected:
            injected = True
            raise regenerator.CourseRegenerationError("injected snapshot read failure")
        return original_snapshot(root)

    monkeypatch.setattr(regenerator, "_snapshot", fail_once_after_swap)
    with pytest.raises(regenerator.CourseRegenerationError, match="rolled back"):
        regenerator.apply_regeneration(
            live,
            candidate_course=candidate,
            plan_path=plan_path,
            confirm_stopped=True,
            accept_replacement=True,
        )

    assert injected is True
    assert original_snapshot(live) == old_snapshot
    assert original_snapshot(candidate) == candidate_snapshot
    assert not backup.exists()


def test_invalid_result_output_is_rejected_before_swap(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False, progress=True
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    old_snapshot = regenerator._snapshot(live)
    candidate_snapshot = regenerator._snapshot(candidate)
    output_directory = tmp_path / "result-directory"
    output_directory.mkdir()

    exit_code = regenerator.main(
        [
            "apply",
            str(live),
            "--candidate-course",
            str(candidate),
            "--plan",
            str(plan_path),
            "--confirm-stopped",
            "--accept-replacement",
            "--json",
            str(output_directory),
        ]
    )

    assert exit_code == 1
    assert regenerator._snapshot(live) == old_snapshot
    assert regenerator._snapshot(candidate) == candidate_snapshot
    assert not Path(plan["backup_path"]).exists()


def test_result_under_planned_backup_is_rejected_without_creating_backup(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live = _make_course(
        tmp_path / "course", tutorial="old tutorial\n", with_git=False, progress=True
    )
    candidate = _make_course(
        tmp_path / "candidate", tutorial="new tutorial\n", with_git=True
    )
    _install_contract_fakes(regenerator, monkeypatch)
    plan_path = tmp_path / "plan.json"
    plan = regenerator.plan_regeneration(live, candidate_course=candidate)
    regenerator._write_json(plan_path, plan)
    backup = Path(plan["backup_path"])
    old_snapshot = regenerator._snapshot(live)
    candidate_snapshot = regenerator._snapshot(candidate)

    exit_code = regenerator.main(
        [
            "apply",
            str(live),
            "--candidate-course",
            str(candidate),
            "--plan",
            str(plan_path),
            "--confirm-stopped",
            "--accept-replacement",
            "--json",
            str(backup / "result.json"),
        ]
    )

    assert exit_code == 1
    assert not backup.exists()
    assert regenerator._snapshot(live) == old_snapshot
    assert regenerator._snapshot(candidate) == candidate_snapshot


def test_incremental_updater_is_a_fail_closed_deprecation_wrapper() -> None:
    completed = subprocess.run(
        [sys.executable, str(UPDATE_PATH), "check", "/tmp/old-course"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "incremental migrations are no longer supported" in completed.stderr
    assert "regenerate_course.py" in completed.stderr


def test_readiness_builds_current_contract_and_emits_assessor_input(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live = _make_course(tmp_path / "course", tutorial="old tutorial\n", with_git=False)
    current = "c" * 64
    monkeypatch.setattr(
        regenerator,
        "_current_runtime",
        lambda: regenerator.RuntimeContract("0.3.0", current),
    )
    monkeypatch.setattr(
        regenerator,
        "_load_course_baseline",
        lambda root: regenerator.CourseBaseline(
            "provenance", 2, "0.2.0", "b" * 64
        ),
    )
    route = {"schema_version": 2, "language": "zh-CN", "route": {"id": "new"}}
    route_path = tmp_path / "route.json"
    _write_json(route_path, route)
    contract = {"schema_version": 2, "capability_contracts": []}
    expected = {
        "schema_version": 1,
        "mode": "reuse_unchanged",
        "reusable_decisions": [],
    }
    monkeypatch.setattr(regenerator, "build_route_contract", lambda value: contract)

    def reuse(root: Path, value: object) -> dict[str, object]:
        assert root == live.resolve()
        assert value == contract
        return expected

    monkeypatch.setattr(regenerator, "trusted_readiness_reuse", reuse)
    assert regenerator.plan_readiness_reuse(live, route_path) == expected
    output = tmp_path / "trusted-prior.json"
    assert (
        regenerator.main(
            [
                "readiness",
                str(live),
                "--route",
                str(route_path),
                "--json",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8")) == expected
    assert json.loads(capsys.readouterr().out)["mode"] == "reuse_unchanged"


def test_legacy_readiness_falls_back_to_full_diagnostic(
    regenerator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live = _make_course(tmp_path / "course", tutorial="old tutorial\n", with_git=False)
    monkeypatch.setattr(
        regenerator,
        "_current_runtime",
        lambda: regenerator.RuntimeContract("0.3.0", "c" * 64),
    )
    monkeypatch.setattr(
        regenerator,
        "_load_course_baseline",
        lambda root: regenerator.CourseBaseline("provenance", 1, "0.2.0", None),
    )
    monkeypatch.setattr(
        regenerator,
        "build_route_contract",
        lambda value: {"schema_version": 2, "capability_contracts": []},
    )
    route_path = tmp_path / "route.json"
    _write_json(route_path, {"schema_version": 2})

    result = regenerator.plan_readiness_reuse(live, route_path)
    assert result["mode"] == "full_readiness"
    assert "legacy" in result["reason"]
    output = tmp_path / "full-readiness.json"
    assert (
        regenerator.main(
            [
                "readiness",
                str(live),
                "--route",
                str(route_path),
                "--json",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["mode"] == "full_readiness"
    assert json.loads(capsys.readouterr().out)["mode"] == "full_readiness"
