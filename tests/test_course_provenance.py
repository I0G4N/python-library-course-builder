from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
import re
import sys

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import scaffold_course  # noqa: E402
from course_provenance import (  # noqa: E402
    PROVENANCE_RELATIVE_PATH,
    ProvenanceError,
    course_impacting_migrations,
    current_migration_ids,
    hash_file,
    hash_tree,
    load_generation_provenance,
    load_migration_registry,
    validate_generation_provenance,
)
from tests.course_v2_fixture import make_spec  # noqa: E402


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


def test_migration_registry_is_closed_unique_and_drives_current_ids() -> None:
    registry = load_migration_registry()

    assert set(registry) == {"schema_version", "migrations"}
    assert registry["schema_version"] == 1
    ids = [entry["id"] for entry in registry["migrations"]]
    assert ids
    assert len(ids) == len(set(ids))
    assert current_migration_ids() == tuple(ids)
    assert tuple(entry["id"] for entry in course_impacting_migrations()) == tuple(
        entry["id"]
        for entry in registry["migrations"]
        if entry["course_impacting"]
    )
    for entry in registry["migrations"]:
        assert set(entry) == {
            "id",
            "course_impacting",
            "impact",
            "from_versions",
            "to_version",
            "source_schema_change",
            "curriculum_identity_change",
            "progress_reset_required",
            "source_paths",
        }
        assert entry["impact"] in {"platform", "content"}
        assert entry["course_impacting"] is True
        assert entry["from_versions"]
        assert all(not Path(path).is_absolute() for path in entry["source_paths"])


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
        "course",
        "applied_migrations",
        "managed_files",
    }
    assert provenance["schema_version"] == 1
    assert provenance["plugin"] == {
        "name": "python-library-course-builder",
        "version": "0.2.0",
    }
    assert provenance["skill"] == {
        "name": "building-python-library-courses",
        "version": "0.2.0",
    }
    assert set(provenance["bundle"]) == {"sha256"}
    assert set(provenance["template"]) == {"sha256"}
    assert set(provenance["authoring"]) == {"sha256"}
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
    assert tuple(provenance["applied_migrations"]) == current_migration_ids()

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
        "schema_version": 1,
        "plugin_version": "0.2.0",
        "skill_version": "0.2.0",
        "course_identity_sha256": provenance["course"]["identity_sha256"],
        "applied_migrations": list(current_migration_ids()),
    }
    serialized = json.dumps(provenance, ensure_ascii=False)
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

    unknown_migration = deepcopy(provenance)
    unknown_migration["applied_migrations"].append("unknown-migration")
    with pytest.raises(ProvenanceError, match="migration"):
        validate_generation_provenance(unknown_migration)

    non_prefix = deepcopy(provenance)
    non_prefix["applied_migrations"] = non_prefix["applied_migrations"][1:]
    with pytest.raises(ProvenanceError, match="prefix"):
        validate_generation_provenance(non_prefix)
