from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import scaffold_course  # noqa: E402
import assess_readiness as readiness_module  # noqa: E402
from assess_readiness import (  # noqa: E402
    ReadinessValidationError,
    assess_readiness,
    build_route_contract,
    main as readiness_main,
    validate_ready_plan,
)
from authoring_contract import (  # noqa: E402
    authoring_contract_manifest,
    authoring_contract_sha256,
)
from course_provenance import (  # noqa: E402
    PROVENANCE_RELATIVE_PATH,
    REGENERATION_RELATIVE_PATH,
    ProvenanceError,
    build_regeneration_metadata,
    hash_file,
    hash_tree,
    load_generation_provenance,
    load_regeneration_metadata,
    regeneration_input_sha256,
    trusted_readiness_reuse,
    validate_generation_provenance,
)
from tests.course_v2_fixture import make_spec  # noqa: E402
from tests.course_v3_fixture import (  # noqa: E402
    make_readiness_route,
    make_v3_spec_and_plan,
)


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_hash_helpers_are_deterministic_and_ignore_selected_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "a.txt").write_text("alpha\n", encoding="utf-8")
    (root / "ignored").mkdir()
    (root / "ignored/b.txt").write_text("before\n", encoding="utf-8")

    digest = hash_tree(root, ignore={"ignored"})
    assert SHA256_PATTERN.fullmatch(hash_file(root / "a.txt"))
    assert SHA256_PATTERN.fullmatch(digest)

    (root / "ignored/b.txt").write_text("after\n", encoding="utf-8")
    assert hash_tree(root, ignore={"ignored"}) == digest
    (root / "a.txt").write_text("changed\n", encoding="utf-8")
    assert hash_tree(root, ignore={"ignored"}) != digest


@pytest.mark.parametrize(
    "course_name",
    ("coursekit-generation.json", "coursekit-regeneration.json"),
)
def test_control_document_basenames_are_valid_course_root_names(
    course_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, make_spec())
    target = tmp_path / course_name
    monkeypatch.setattr(scaffold_course, "initialize_git", lambda root: None)
    scaffold_course.scaffold(spec_path, target)

    assert load_generation_provenance(target, verify_hashes=True)[
        "schema_version"
    ] == 2
    assert load_regeneration_metadata(target)["schema_version"] == 1


def test_authoring_contract_is_deterministic_and_excludes_update_runtime_plumbing(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "skill"
    shutil.copytree(
        SKILL_ROOT,
        copied,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    first = authoring_contract_manifest(copied)
    second = authoring_contract_manifest(copied)

    assert first == second
    assert SHA256_PATTERN.fullmatch(first["sha256"])
    paths = [record["path"] for record in first["files"]]
    assert paths == sorted(paths)
    assert "SKILL.md" in paths
    assert "references/architecture.md" in paths
    assert "scripts/assess_readiness.py" in paths
    assert "scripts/scaffold_course.py" in paths
    assert "assets/course-template/platform/coursekit/compiler.py" in paths
    assert "assets/course-template/platform/coursekit/models.py" in paths
    assert "scripts/authoring_contract.py" not in paths
    assert "scripts/course_provenance.py" not in paths
    assert "scripts/update_course.py" not in paths
    assert "scripts/regenerate_course.py" not in paths
    assert "assets/course-template/README.md" not in paths

    (copied / "scripts/update_course.py").write_text(
        "# excluded migration shim\n", encoding="utf-8"
    )
    (copied / "assets/course-template/README.md").write_text(
        "excluded runtime documentation\n", encoding="utf-8"
    )
    assert authoring_contract_manifest(copied) == first

    (copied / "references/new-teaching-contract.md").write_text(
        "new authoring behavior\n", encoding="utf-8"
    )
    changed = authoring_contract_manifest(copied)
    assert changed["sha256"] != first["sha256"]


def test_fresh_scaffold_writes_closed_provenance_before_git_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = make_spec()
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, spec)
    target = tmp_path / "generated-course"
    observed: dict[str, object] = {}

    def observe_baseline(root: Path) -> None:
        path = root / PROVENANCE_RELATIVE_PATH
        observed["exists"] = path.is_file()
        observed["provenance"] = json.loads(path.read_text(encoding="utf-8"))
        observed["regeneration"] = json.loads(
            (root / REGENERATION_RELATIVE_PATH).read_text(encoding="utf-8")
        )

    monkeypatch.setattr(scaffold_course, "initialize_git", observe_baseline)

    report = scaffold_course.scaffold(spec_path, target)

    assert observed["exists"] is True
    provenance = load_generation_provenance(target, verify_hashes=True)
    assert observed["provenance"] == provenance
    assert set(provenance) == {
        "schema_version",
        "plugin",
        "skill",
        "bundle",
        "template",
        "authoring",
        "authoring_contract",
        "regeneration_input",
        "course",
        "managed_files",
    }
    manifest = json.loads(
        (
            SKILL_ROOT.parents[1]
            / ".codex-plugin/plugin.json"
        ).read_text(encoding="utf-8")
    )
    assert provenance["schema_version"] == 2
    assert provenance["plugin"] == {
        "name": "python-library-course-builder",
        "version": manifest["version"],
    }
    assert provenance["skill"] == {
        "name": "building-python-library-courses",
        "version": manifest["version"],
    }
    assert set(provenance["bundle"]) == {"sha256"}
    assert set(provenance["template"]) == {"sha256"}
    assert set(provenance["authoring"]) == {"sha256"}
    assert provenance["authoring_contract"] == {
        "sha256": authoring_contract_sha256()
    }
    regeneration = load_regeneration_metadata(target)
    assert observed["regeneration"] == regeneration
    assert provenance["regeneration_input"] == {
        "sha256": regeneration_input_sha256(regeneration)
    }
    assert regeneration == {
        "schema_version": 1,
        "language": spec["course"]["language"],
        "target": {
            "name": spec["target"]["name"],
            "version": spec["target"]["version"],
            "track": spec["target"].get("track") or None,
        },
        "route_intent": {
            "course_id": spec["course"]["id"],
            "course_title": spec["course"]["title"],
            "route_id": None,
            "route_title": None,
        },
        "route_contract": None,
        "readiness_projection": None,
    }
    assert provenance["course"] == {
        "id": spec["course"]["id"],
        "schema_version": spec["schema_version"],
        "language": spec["course"]["language"],
        "target": {
            "name": spec["target"]["name"],
            "version": spec["target"]["version"],
        },
        "identity_sha256": provenance["course"]["identity_sha256"],
    }
    assert SHA256_PATTERN.fullmatch(provenance["course"]["identity_sha256"])

    managed = provenance["managed_files"]
    assert managed["package.json"]["role"] == "template"
    assert managed["platform/course/manifest.json"]["role"] == "compiled"
    assert managed["labs/_course/coursekit/cli.py"]["role"] == "workspace-runtime"
    assert managed["labs/manifest.json"]["role"] == "workspace-runtime"
    assert managed["labs/lab01/README.md"]["role"] == "workspace-runtime"
    assert (
        managed["labs/lab01/tests/test_answer_1.py"]["role"]
        == "workspace-runtime"
    )
    assert "labs/lab01/answer.py" not in managed
    assert "labs/lab02/mini.py" not in managed
    assert PROVENANCE_RELATIVE_PATH not in managed
    assert REGENERATION_RELATIVE_PATH not in managed
    assert all(
        set(record) == {"role", "sha256"}
        and record["role"] in {"template", "compiled", "workspace-runtime"}
        and SHA256_PATTERN.fullmatch(record["sha256"])
        and not PurePosixPath(path).is_absolute()
        and ".." not in PurePosixPath(path).parts
        and not path.startswith("labs/.coursekit/")
        and "/.git/" not in f"/{path}/"
        for path, record in managed.items()
    )
    assert managed["package.json"]["sha256"] == hash_file(target / "package.json")

    assert report["provenance"] == {
        "path": PROVENANCE_RELATIVE_PATH,
        "schema_version": 2,
        "plugin_version": manifest["version"],
        "skill_version": manifest["version"],
        "course_identity_sha256": provenance["course"]["identity_sha256"],
        "authoring_contract_sha256": provenance["authoring_contract"]["sha256"],
        "regeneration_input_sha256": provenance["regeneration_input"]["sha256"],
    }
    serialized = json.dumps(
        {"provenance": provenance, "regeneration": regeneration},
        ensure_ascii=False,
    )
    assert str(tmp_path) not in serialized
    assert "created_at" not in serialized
    assert "timestamp" not in serialized
    assert "responses" not in serialized
    assert "raw_evidence" not in serialized


def test_provenance_validation_rejects_open_or_unsafe_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, make_spec())
    target = tmp_path / "generated-course"
    monkeypatch.setattr(scaffold_course, "initialize_git", lambda root: None)
    scaffold_course.scaffold(spec_path, target)
    provenance = load_generation_provenance(target)

    extra = deepcopy(provenance)
    extra["unexpected"] = True
    with pytest.raises(ProvenanceError, match="unexpected|keys"):
        validate_generation_provenance(extra)

    nested_extra = deepcopy(provenance)
    nested_extra["plugin"]["source_path"] = str(tmp_path)
    with pytest.raises(ProvenanceError, match="plugin"):
        validate_generation_provenance(nested_extra)

    unsafe = deepcopy(provenance)
    unsafe["managed_files"]["../outside"] = {
        "role": "template",
        "sha256": "0" * 64,
    }
    with pytest.raises(ProvenanceError, match="managed_files|relative|unsafe"):
        validate_generation_provenance(unsafe)

    invalid_contract = deepcopy(provenance)
    invalid_contract["authoring_contract"]["sha256"] = "not-a-digest"
    with pytest.raises(ProvenanceError, match="authoring_contract"):
        validate_generation_provenance(invalid_contract)


def test_legacy_v1_provenance_remains_loadable_without_a_migration_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, make_spec())
    target = tmp_path / "generated-course"
    monkeypatch.setattr(scaffold_course, "initialize_git", lambda root: None)
    scaffold_course.scaffold(spec_path, target)
    provenance = load_generation_provenance(target)
    legacy = deepcopy(provenance)
    legacy["schema_version"] = 1
    legacy.pop("authoring_contract")
    legacy.pop("regeneration_input")
    legacy["applied_migrations"] = ["historical-id-not-in-current-skill"]
    _write_json(target / PROVENANCE_RELATIVE_PATH, legacy)

    loaded = load_generation_provenance(target, verify_hashes=True)
    assert loaded["schema_version"] == 1
    assert loaded["applied_migrations"] == ["historical-id-not-in-current-skill"]

    duplicated = deepcopy(loaded)
    duplicated["applied_migrations"] *= 2
    with pytest.raises(ProvenanceError, match="duplicates"):
        validate_generation_provenance(duplicated)


def test_v3_sidecar_preserves_safe_route_contract_without_raw_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_sentinel = "RAW-LEARNER-EVIDENCE-MUST-NOT-PERSIST"
    spec, plan = make_v3_spec_and_plan(
        missing_ids={"json-errors"}, raw_sentinel=raw_sentinel
    )
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, spec)
    target = tmp_path / "generated-course"
    monkeypatch.setattr(scaffold_course, "initialize_git", lambda root: None)

    scaffold_course.scaffold(spec_path, target, readiness_plan=plan)

    metadata = load_regeneration_metadata(target)
    provenance = load_generation_provenance(target, verify_hashes=True)
    assert metadata["route_contract"] == plan["route_contract"]
    assert metadata["route_intent"]["route_id"] == plan["route_id"]
    assert metadata["readiness_projection"]["mastered_capability_ids"] == plan[
        "mastered_capability_ids"
    ]
    assert metadata["readiness_projection"]["missing_capability_ids"] == [
        "json-errors"
    ]
    assert provenance["regeneration_input"]["sha256"] == (
        regeneration_input_sha256(metadata)
    )
    serialized = (target / REGENERATION_RELATIVE_PATH).read_text(encoding="utf-8")
    assert raw_sentinel not in serialized
    assert "temporary_evidence" not in serialized
    assert '"responses"' not in serialized
    assert '"diagnostic"' in serialized
    assert all(
        SHA256_PATTERN.fullmatch(record["sha256"])
        for record in metadata["route_contract"]["capability_contracts"]
    )


def test_readiness_basis_cannot_persist_raw_learner_evidence() -> None:
    _, plan = make_v3_spec_and_plan()
    tampered = deepcopy(plan)
    tampered["capabilities"][0]["basis"] = (
        "RAW learner answer: here is my private source code"
    )
    tampered["plan_digest"] = readiness_module._digest(
        readiness_module._safe_plan_projection(tampered)
    )

    with pytest.raises(ReadinessValidationError, match="privacy-safe readiness basis"):
        validate_ready_plan(tampered)


def test_regeneration_metadata_symlink_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, plan = make_v3_spec_and_plan()
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, spec)
    target = tmp_path / "generated-course"
    monkeypatch.setattr(scaffold_course, "initialize_git", lambda root: None)
    scaffold_course.scaffold(spec_path, target, readiness_plan=plan)
    metadata_path = target / REGENERATION_RELATIVE_PATH
    outside = tmp_path / "outside-regeneration.json"
    outside.write_bytes(metadata_path.read_bytes())
    metadata_path.unlink()
    try:
        metadata_path.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks are unavailable: {error}")

    with pytest.raises(ProvenanceError, match="symlink"):
        load_regeneration_metadata(target)
    with pytest.raises(ProvenanceError, match="symlink"):
        load_generation_provenance(target, verify_hashes=True)


def test_regeneration_metadata_is_bound_to_canonical_course_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, plan = make_v3_spec_and_plan()
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, spec)
    target = tmp_path / "generated-course"
    monkeypatch.setattr(scaffold_course, "initialize_git", lambda root: None)
    scaffold_course.scaffold(spec_path, target, readiness_plan=plan)
    metadata_path = target / REGENERATION_RELATIVE_PATH
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["route_intent"]["course_title"] += " stale"
    _write_json(metadata_path, metadata)

    with pytest.raises(ProvenanceError, match="title does not match canonical source"):
        load_regeneration_metadata(target)


def test_noncanonical_direct_control_file_paths_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, make_spec())
    target = tmp_path / "generated-course"
    monkeypatch.setattr(scaffold_course, "initialize_git", lambda root: None)
    scaffold_course.scaffold(spec_path, target)
    arbitrary = tmp_path / "arbitrary"
    arbitrary.mkdir()
    direct = arbitrary / Path(PROVENANCE_RELATIVE_PATH).name
    direct.write_bytes((target / PROVENANCE_RELATIVE_PATH).read_bytes())

    with pytest.raises(ProvenanceError, match="canonical"):
        load_generation_provenance(direct)

    direct.unlink()
    try:
        direct.symlink_to(target / PROVENANCE_RELATIVE_PATH)
    except OSError as error:
        pytest.skip(f"symlinks are unavailable: {error}")
    with pytest.raises(ProvenanceError, match="canonical"):
        load_generation_provenance(direct)


def test_trusted_delta_readiness_reuses_only_unchanged_capability_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids={"json-errors"})
    spec_path = tmp_path / "spec.json"
    _write_json(spec_path, spec)
    target = tmp_path / "generated-course"
    monkeypatch.setattr(scaffold_course, "initialize_git", lambda root: None)
    scaffold_course.scaffold(spec_path, target, readiness_plan=plan)

    route = make_readiness_route()
    route["capabilities"][1]["diagnostic"]["prompt"] += " changed"
    new_capability = deepcopy(route["capabilities"][-1])
    new_capability.update(
        {
            "id": "new-boundary",
            "title": "新增边界能力",
            "requires": ["domain-boundary"],
            "first_used_in": "lab03",
            "diagnostic": {
                **new_capability["diagnostic"],
                "id": "diagnose-new-boundary",
            },
        }
    )
    route["capabilities"].append(new_capability)
    current_contract = build_route_contract(route)

    trusted = trusted_readiness_reuse(target, current_contract)

    assert trusted["mode"] == "reuse_unchanged"
    assert trusted["changed_capability_ids"] == ["json-data-model"]
    assert trusted["new_capability_ids"] == ["new-boundary"]
    assert trusted["needs_evidence_capability_ids"] == [
        "json-data-model",
        "new-boundary",
    ]
    assert trusted["missing_capability_ids"] == ["json-errors"]
    assert trusted["reusable_capability_ids"] == [
        "python-functions",
        "json-errors",
        "domain-boundary",
    ]

    report = assess_readiness(
        route,
        {
            "schema_version": 2,
            "language": "zh-CN",
            "evidence": [],
            "responses": [],
        },
        trusted_prior_decisions=trusted,
    )
    assert report["status"] == "needs_evidence"
    assert report["next_question"]["capability_id"] == "json-data-model"
    assert report["mastered_capability_ids"] == [
        "python-functions",
        "domain-boundary",
    ]
    assert report["missing_capability_ids"] == ["json-errors"]

    route_path = tmp_path / "current-route.json"
    evidence_path = tmp_path / "current-evidence.json"
    trusted_path = tmp_path / "trusted-prior.json"
    output_path = tmp_path / "readiness-output.json"
    _write_json(route_path, route)
    _write_json(
        evidence_path,
        {
            "schema_version": 2,
            "language": "zh-CN",
            "evidence": [],
            "responses": [],
        },
    )
    _write_json(trusted_path, trusted)
    assert readiness_main(
        [
            str(route_path),
            str(evidence_path),
            "--trusted-prior-decisions",
            str(trusted_path),
            "--trusted-course",
            str(target),
            "--output",
            str(output_path),
        ]
    ) == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == (
        "needs_evidence"
    )

    forged = deepcopy(trusted)
    forged["source"]["course_identity_sha256"] = "0" * 64
    _write_json(trusted_path, forged)
    assert readiness_main(
        [
            str(route_path),
            str(evidence_path),
            "--trusted-prior-decisions",
            str(trusted_path),
            "--trusted-course",
            str(target),
            "--output",
            str(tmp_path / "forged-output.json"),
        ]
    ) == 1

    wrong_route_id = deepcopy(current_contract)
    wrong_route_id["route"]["id"] = "different-route"
    with pytest.raises(ProvenanceError, match="route id"):
        trusted_readiness_reuse(target, wrong_route_id)

    wrong_route_title = deepcopy(current_contract)
    wrong_route_title["route"]["title"] = "Different route"
    with pytest.raises(ProvenanceError, match="route title"):
        trusted_readiness_reuse(target, wrong_route_title)

    replacement_route = make_readiness_route()
    replacement_route["route"]["title"] += " changed"
    replacement_plan = assess_readiness(
        replacement_route,
        {
            "schema_version": 2,
            "language": "zh-CN",
            "evidence": [
                {
                    "capability_id": capability["id"],
                    "kind": "code",
                    "verdict": "sufficient",
                    "content": "privacy-safe test evidence",
                }
                for capability in replacement_route["capabilities"]
                if capability["id"] != "json-errors"
            ],
            "responses": [
                {
                    "question_id": "diagnose-json-errors",
                    "answer": "不会",
                }
            ],
        },
    )
    replacement_metadata = build_regeneration_metadata(
        spec,
        readiness_plan=replacement_plan,
    )
    metadata_path = target / REGENERATION_RELATIVE_PATH
    _write_json(metadata_path, replacement_metadata)
    assert load_regeneration_metadata(target)["route_intent"]["route_title"].endswith(
        " changed"
    )
    with pytest.raises(ProvenanceError, match="regeneration input hash mismatch"):
        trusted_readiness_reuse(target, current_contract)
