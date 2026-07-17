from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import ModuleType
from typing import Callable

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = (
    ROOT
    / "plugins"
    / "python-library-course-builder"
    / "skills"
    / "building-python-library-courses"
)
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
UPDATE_PATH = SCRIPTS_ROOT / "update_course.py"
PROVENANCE_PATH = Path("platform/coursekit-generation.json")
OLD_VERSION = "0.2.0"
LEGACY_V2_VERSION = "0.1.1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")

sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "assets/course-template/platform"))

from course_provenance import hash_file  # noqa: E402
from tests.course_v2_fixture import make_spec  # noqa: E402
from tests.course_v3_fixture import make_v3_spec_and_plan  # noqa: E402
from validate_course import validate_spec  # noqa: E402
import scaffold_course  # noqa: E402


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _git(course: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=course,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _amend_baseline(course: Path, *, message: str | None = None) -> None:
    _git(course, "add", "-A")
    command = [
        "-c",
        "user.name=CourseKit",
        "-c",
        "user.email=coursekit@localhost",
        "commit",
        "-q",
        "--amend",
    ]
    if message is None:
        command.append("--no-edit")
    else:
        command.extend(["-m", message])
    _git(course, *command)


def _run_update(*arguments: object) -> subprocess.CompletedProcess[str]:
    assert UPDATE_PATH.is_file(), "the course updater CLI is missing"
    return subprocess.run(
        [sys.executable, str(UPDATE_PATH), *(str(value) for value in arguments)],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def _load_updater() -> ModuleType:
    assert UPDATE_PATH.is_file(), "the course updater CLI is missing"
    module_name = "course_update_contract_under_test"
    spec = importlib.util.spec_from_file_location(module_name, UPDATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _tree_snapshot(course: Path) -> dict[str, object]:
    files: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(course.rglob("*")):
        relative = path.relative_to(course)
        if relative.parts[0] == ".git":
            continue
        key = relative.as_posix()
        if path.is_symlink():
            files[key] = ("symlink", os.readlink(path))
        elif path.is_file():
            files[key] = ("file", path.read_bytes())
        elif path.is_dir():
            files[key] = ("directory", "")
    return {
        "files": files,
        "head": _git(course, "rev-parse", "HEAD"),
        "refs": _git(course, "for-each-ref", "--format=%(refname) %(objectname)"),
    }


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _plugin_version() -> str:
    manifest = _read_json(
        ROOT
        / "plugins"
        / "python-library-course-builder"
        / ".codex-plugin"
        / "plugin.json"
    )
    return str(manifest["version"])


def _make_old_provenance_course(
    seed: Path,
    destination: Path,
    *,
    version: str = OLD_VERSION,
) -> Path:
    shutil.copytree(seed, destination)
    provenance_path = destination / PROVENANCE_PATH
    provenance = _read_json(provenance_path)
    plugin = provenance["plugin"]
    skill = provenance["skill"]
    managed = provenance["managed_files"]
    assert isinstance(plugin, dict)
    assert isinstance(skill, dict)
    assert isinstance(managed, dict)
    plugin["version"] = version
    skill["version"] = version
    provenance["applied_migrations"] = []

    # Make one managed template byte-distinct from the current release. The
    # recorded baseline remains internally valid and gives the updater a small,
    # deterministic platform replacement to transact.
    readme = destination / "README.md"
    readme.write_text("# Legacy generated course\n", encoding="utf-8")
    readme_record = managed["README.md"]
    assert isinstance(readme_record, dict)
    readme_record["sha256"] = hash_file(readme)
    provenance["template"] = {
        "sha256": sha256(readme.read_bytes()).hexdigest()
    }
    _write_json(provenance_path, provenance)
    _amend_baseline(destination)
    assert _git(destination, "status", "--porcelain=v1", "--untracked-files=all") == ""
    return destination


def _make_legacy_course(
    seed: Path,
    destination: Path,
    *,
    trusted_baseline: bool,
) -> Path:
    shutil.copytree(seed, destination)
    (destination / PROVENANCE_PATH).unlink()
    _amend_baseline(
        destination,
        message=None if trusted_baseline else "manual initial import",
    )
    return destination


def _candidate_source(course: Path, destination: Path) -> Path:
    shutil.copytree(course / "platform/course/source", destination)
    tutorial = sorted(destination.rglob("tutorial.md"))[1]
    tutorial.write_text(
        tutorial.read_text(encoding="utf-8")
        + (
            "\n## 架构与接口\n\n"
            "调用方只依赖公开输入输出，课程实现负责验证边界并返回"
            "可观察结果。\n"
        ),
        encoding="utf-8",
    )
    return destination


def _check(
    course: Path,
    plan_path: Path,
    *,
    candidate_source: Path | None = None,
) -> dict[str, object]:
    arguments: list[object] = ["check", course]
    if candidate_source is not None:
        arguments.extend(["--candidate-source", candidate_source])
    arguments.extend(["--json", plan_path])
    completed = _run_update(*arguments)
    assert completed.returncode == 0, completed.stderr
    assert plan_path.is_file()
    return _read_json(plan_path)


def _apply(
    course: Path,
    plan_path: Path,
    result_path: Path,
    *,
    candidate_source: Path | None = None,
    accept_progress_reset: bool = False,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
    arguments: list[object] = [
        "apply",
        course,
        "--plan",
        plan_path,
    ]
    if candidate_source is not None:
        arguments.extend(["--candidate-source", candidate_source])
    arguments.append("--confirm-stopped")
    if accept_progress_reset:
        arguments.append("--accept-progress-reset")
    arguments.extend(["--json", result_path])
    completed = _run_update(*arguments)
    result = _read_json(result_path) if result_path.is_file() else None
    return completed, result


@pytest.fixture(scope="module")
def v3_seed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("course-update-v3-seed")
    spec, readiness = make_v3_spec_and_plan(language="zh-CN")
    spec_path = root / "spec.json"
    _write_json(spec_path, spec)
    course = root / "course"
    scaffold_course.scaffold(spec_path, course, readiness_plan=readiness)
    return course


@pytest.fixture(scope="module")
def v2_seed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("course-update-v2-seed")
    spec = make_spec()
    assert validate_spec(spec)["schema_version"] == 2
    spec_path = root / "spec.json"
    _write_json(spec_path, spec)
    course = root / "course"
    scaffold_course.scaffold(spec_path, course)
    return course


@pytest.fixture
def old_course(
    tmp_path: Path,
    v3_seed: Path,
) -> Path:
    return _make_old_provenance_course(v3_seed, tmp_path / "course")


def test_check_is_read_only_and_reports_pending_provenance_migrations(
    old_course: Path,
    tmp_path: Path,
) -> None:
    before = _tree_snapshot(old_course)

    plan = _check(old_course, tmp_path / "plan.json")

    assert _tree_snapshot(old_course) == before
    assert plan["schema_version"] == 1
    assert plan["command"] == "check"
    assert plan["status"] == "ready"
    assert plan["current_version"] == OLD_VERSION
    assert plan["target_version"] == _plugin_version()
    assert isinstance(plan["migrations"], list) and plan["migrations"]
    assert plan["identity_change"] is False
    assert plan["progress_reset_required"] is False
    assert SHA256_RE.fullmatch(str(plan["plan_digest"]))
    assert SHA256_RE.fullmatch(str(plan["target_snapshot_sha256"]))
    assert isinstance(plan["operations"], list)
    assert plan["conflicts"] == []


def test_version_and_bundle_drift_without_pending_migration_is_a_noop(
    v3_seed: Path,
    tmp_path: Path,
) -> None:
    course = tmp_path / "drift-only-course"
    shutil.copytree(v3_seed, course)
    provenance_path = course / PROVENANCE_PATH
    provenance = _read_json(provenance_path)
    plugin = provenance["plugin"]
    skill = provenance["skill"]
    bundle = provenance["bundle"]
    assert isinstance(plugin, dict)
    assert isinstance(skill, dict)
    assert isinstance(bundle, dict)
    plugin["version"] = LEGACY_V2_VERSION
    skill["version"] = LEGACY_V2_VERSION
    bundle["sha256"] = "0" * 64
    _write_json(provenance_path, provenance)
    before = _tree_snapshot(course)

    plan = _check(course, tmp_path / "drift-plan.json")

    assert plan["status"] == "up_to_date"
    assert plan["migrations"] == []
    assert _tree_snapshot(course) == before


def test_check_classifies_managed_protected_unknown_and_state_paths(
    old_course: Path,
    tmp_path: Path,
) -> None:
    protected = old_course / "labs/lab01/answer.py"
    protected.write_text(
        protected.read_text(encoding="utf-8") + "\n# learner answer\n",
        encoding="utf-8",
    )
    unknown = old_course / "labs/local_helper.py"
    unknown.write_text("LOCAL = True\n", encoding="utf-8")
    state = old_course / "labs/.coursekit/state.json"
    _write_json(state, {"curriculum_id": "learner-progress", "score": 7})

    plan = _check(old_course, tmp_path / "plan.json")
    operations = plan["operations"]
    assert isinstance(operations, list)
    by_path = {str(item["path"]): item for item in operations}
    assert len(by_path) == len(operations)
    assert by_path["README.md"]["classification"] == "template"
    assert by_path["platform/course/manifest.json"]["classification"] == "compiled"
    assert (
        by_path["labs/_course/coursekit/cli.py"]["classification"]
        == "workspace-runtime"
    )
    assert by_path["labs/lab01/answer.py"] == {
        "path": "labs/lab01/answer.py",
        "classification": "protected",
        "action": "preserve",
    }
    assert by_path["labs/local_helper.py"] == {
        "path": "labs/local_helper.py",
        "classification": "unknown",
        "action": "preserve",
    }
    assert by_path["labs/.coursekit/state.json"] == {
        "path": "labs/.coursekit/state.json",
        "classification": "state",
        "action": "preserve",
    }


def test_check_accepts_a_supported_legacy_generated_baseline(
    v3_seed: Path,
    tmp_path: Path,
) -> None:
    course = _make_legacy_course(
        v3_seed,
        tmp_path / "legacy-course",
        trusted_baseline=True,
    )
    before = _tree_snapshot(course)

    plan = _check(course, tmp_path / "legacy-plan.json")

    assert _tree_snapshot(course) == before
    assert plan["current_version"] in {"0.1.0", "0.1.1", "0.2.0"}
    assert plan["target_version"] == _plugin_version()
    assert plan["status"] in {"ready", "up_to_date"}


def test_check_rejects_a_course_without_provenance_or_a_trusted_baseline(
    v3_seed: Path,
    tmp_path: Path,
) -> None:
    course = _make_legacy_course(
        v3_seed,
        tmp_path / "manual-course",
        trusted_baseline=False,
    )
    before = _tree_snapshot(course)

    completed = _run_update(
        "check",
        course,
        "--json",
        tmp_path / "must-not-plan.json",
    )

    assert completed.returncode != 0
    assert completed.stderr.startswith("course update failed:")
    assert _tree_snapshot(course) == before


def test_check_rejects_a_symlink_in_canonical_source_without_writes(
    old_course: Path,
    tmp_path: Path,
) -> None:
    tutorial = sorted((old_course / "platform/course/source").rglob("tutorial.md"))[0]
    outside = tmp_path / "outside-tutorial.md"
    outside.write_text("# outside\n", encoding="utf-8")
    tutorial.unlink()
    try:
        tutorial.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks are unavailable: {error}")
    before = _tree_snapshot(old_course)

    completed = _run_update(
        "check",
        old_course,
        "--json",
        tmp_path / "symlink-plan.json",
    )

    assert completed.returncode != 0
    assert completed.stderr.startswith("course update failed:")
    assert _tree_snapshot(old_course) == before


def test_candidate_bound_plan_rejects_candidate_changes(
    old_course: Path,
    tmp_path: Path,
) -> None:
    candidate = _candidate_source(old_course, tmp_path / "candidate-source")
    plan_path = tmp_path / "candidate-plan.json"
    completed = _run_update(
        "check",
        old_course,
        "--candidate-source",
        candidate,
        "--json",
        plan_path,
    )
    assert completed.returncode == 0, completed.stderr
    changed = sorted(candidate.rglob("tutorial.md"))[0]
    changed.write_text(
        changed.read_text(encoding="utf-8") + "\nchanged after review\n",
        encoding="utf-8",
    )
    before = _tree_snapshot(old_course)

    applied, _ = _apply(
        old_course,
        plan_path,
        tmp_path / "stale-candidate-result.json",
        candidate_source=candidate,
    )

    assert applied.returncode != 0
    assert applied.stderr.startswith("course update failed:")
    assert _tree_snapshot(old_course) == before


def test_content_apply_rejects_a_candidate_not_bound_during_check(
    old_course: Path,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "unbound-plan.json"
    _check(old_course, plan_path)
    candidate = _candidate_source(old_course, tmp_path / "candidate-source")
    before = _tree_snapshot(old_course)

    applied, _ = _apply(
        old_course,
        plan_path,
        tmp_path / "unbound-result.json",
        candidate_source=candidate,
    )

    assert applied.returncode != 0
    assert "same --candidate-source" in applied.stderr
    assert _tree_snapshot(old_course) == before


def test_candidate_source_cannot_contain_the_live_course(
    old_course: Path,
    tmp_path: Path,
) -> None:
    ancestor = old_course.parent
    (ancestor / "course.json").write_text("{}\n", encoding="utf-8")
    before = _tree_snapshot(old_course)

    completed = _run_update(
        "check",
        old_course,
        "--candidate-source",
        ancestor,
        "--json",
        tmp_path / "ancestor-plan.json",
    )

    assert completed.returncode != 0
    assert completed.stderr.startswith("course update failed:")
    assert _tree_snapshot(old_course) == before


@pytest.mark.parametrize(
    "relative_path",
    ("README.md", "labs/lab01/answer.py"),
    ids=("managed", "protected"),
)
def test_plan_digest_detects_managed_and_protected_toctou_changes(
    old_course: Path,
    tmp_path: Path,
    relative_path: str,
) -> None:
    first_plan_path = tmp_path / "first-plan.json"
    first = _check(old_course, first_plan_path)
    changed = old_course / relative_path
    changed.write_text(
        changed.read_text(encoding="utf-8") + "\n# changed after check\n",
        encoding="utf-8",
    )
    after_user_change = _tree_snapshot(old_course)
    second = _check(old_course, tmp_path / "second-plan.json")
    assert second["plan_digest"] != first["plan_digest"]
    candidate = _candidate_source(old_course, tmp_path / "candidate-source")

    completed, _ = _apply(
        old_course,
        first_plan_path,
        tmp_path / "stale-result.json",
        candidate_source=candidate,
    )

    assert completed.returncode != 0
    assert completed.stderr.startswith("course update failed:")
    assert _tree_snapshot(old_course) == after_user_change


def test_managed_conflict_blocks_apply_without_writing_the_course(
    old_course: Path,
    tmp_path: Path,
) -> None:
    readme = old_course / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nLearner-local README note.\n",
        encoding="utf-8",
    )
    before = _tree_snapshot(old_course)
    plan_path = tmp_path / "blocked-plan.json"

    plan = _check(old_course, plan_path)

    assert _tree_snapshot(old_course) == before
    assert plan["status"] == "blocked"
    conflicts = plan["conflicts"]
    assert isinstance(conflicts, list)
    readme_conflict = next(item for item in conflicts if item["path"] == "README.md")
    assert str(readme_conflict["reason"]).strip()
    candidate = _candidate_source(old_course, tmp_path / "candidate-source")

    completed, _ = _apply(
        old_course,
        plan_path,
        tmp_path / "blocked-result.json",
        candidate_source=candidate,
    )

    assert completed.returncode != 0
    assert completed.stderr.startswith("course update failed:")
    assert _tree_snapshot(old_course) == before


def test_apply_preserves_learner_unknown_state_and_git_and_is_idempotent(
    old_course: Path,
    tmp_path: Path,
) -> None:
    protected = old_course / "labs/lab01/answer.py"
    protected.write_text("def answer_1():\n    return 41 + 1\n", encoding="utf-8")
    unknown = old_course / "labs/my_helper.py"
    unknown.write_text("ANSWER = 42\n", encoding="utf-8")
    state = old_course / "labs/.coursekit/state.json"
    _write_json(
        state,
        {
            "schema_version": 1,
            "curriculum_id": "learner-progress",
            "checkpoints": {"lab01": {"score": 10}},
        },
    )
    protected_bytes = protected.read_bytes()
    unknown_bytes = unknown.read_bytes()
    state_bytes = state.read_bytes()
    git_head = _git(old_course, "rev-parse", "HEAD")
    git_refs = _git(old_course, "for-each-ref", "--format=%(refname) %(objectname)")
    candidate = _candidate_source(old_course, tmp_path / "candidate-source")
    plan_path = tmp_path / "plan.json"
    plan = _check(old_course, plan_path, candidate_source=candidate)

    completed, result = _apply(
        old_course,
        plan_path,
        tmp_path / "result.json",
        candidate_source=candidate,
    )

    assert completed.returncode == 0, completed.stderr
    assert result is not None
    assert result["schema_version"] == 1
    assert result["status"] == "applied"
    assert isinstance(result["written"], list) and result["written"]
    assert isinstance(result["removed"], list)
    assert isinstance(result["preserved"], list)
    assert result["archived_state"] is None
    assert "labs/lab01/answer.py" in result["preserved"]
    assert "labs/my_helper.py" in result["preserved"]
    assert "labs/.coursekit/state.json" in result["preserved"]
    assert protected.read_bytes() == protected_bytes
    assert unknown.read_bytes() == unknown_bytes
    assert state.read_bytes() == state_bytes
    assert _git(old_course, "rev-parse", "HEAD") == git_head
    assert (
        _git(old_course, "for-each-ref", "--format=%(refname) %(objectname)")
        == git_refs
    )
    provenance = _read_json(old_course / PROVENANCE_PATH)
    assert provenance["plugin"]["version"] == _plugin_version()  # type: ignore[index]
    assert set(plan["migrations"]).issubset(set(provenance["applied_migrations"]))

    up_to_date_path = tmp_path / "up-to-date-plan.json"
    up_to_date = _check(old_course, up_to_date_path)
    assert up_to_date["status"] == "up_to_date"
    before_second_apply = _tree_snapshot(old_course)
    completed, second = _apply(
        old_course,
        up_to_date_path,
        tmp_path / "up-to-date-result.json",
    )
    assert completed.returncode == 0, completed.stderr
    assert second is not None and second["status"] == "up_to_date"
    assert second["written"] == []
    assert second["removed"] == []
    assert _tree_snapshot(old_course) == before_second_apply


def test_identity_change_requires_consent_and_archives_state_before_reset(
    v2_seed: Path,
    v3_seed: Path,
    tmp_path: Path,
) -> None:
    course = _make_old_provenance_course(
        v2_seed,
        tmp_path / "v2-course",
        version=LEGACY_V2_VERSION,
    )
    state = course / "labs/.coursekit/state.json"
    _write_json(
        state,
        {
            "schema_version": 1,
            "curriculum_id": "timeout-course-v2",
            "checkpoints": {"lab01": {"submitted": True, "score": 10}},
        },
    )
    state_bytes = state.read_bytes()
    candidate = tmp_path / "v3-candidate-source"
    shutil.copytree(v3_seed / "platform/course/source", candidate)
    plan_path = tmp_path / "identity-plan.json"
    plan = _check(course, plan_path, candidate_source=candidate)
    assert plan["identity_change"] is True
    assert plan["progress_reset_required"] is True
    before_rejected_apply = _tree_snapshot(course)

    rejected, _ = _apply(
        course,
        plan_path,
        tmp_path / "rejected-result.json",
        candidate_source=candidate,
    )
    assert rejected.returncode != 0
    assert rejected.stderr.startswith("course update failed:")
    assert _tree_snapshot(course) == before_rejected_apply

    completed, result = _apply(
        course,
        plan_path,
        tmp_path / "accepted-result.json",
        candidate_source=candidate,
        accept_progress_reset=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert result is not None and result["status"] == "applied"
    archive_value = result["archived_state"]
    assert isinstance(archive_value, str) and archive_value
    archive = Path(archive_value)
    if not archive.is_absolute():
        archive = course / archive
    assert archive.parent == course / "labs/.coursekit/archive"
    assert re.fullmatch(r"state-[0-9a-f]{12}\.json", archive.name)
    assert archive.read_bytes() == state_bytes
    assert not state.exists()
    provenance = _read_json(course / PROVENANCE_PATH)
    assert provenance["course"]["schema_version"] == 3  # type: ignore[index]


def test_apply_rolls_back_after_a_replacement_failure(
    old_course: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = _candidate_source(old_course, tmp_path / "candidate-source")
    plan_path = tmp_path / "plan.json"
    _check(old_course, plan_path, candidate_source=candidate)
    before = _tree_snapshot(old_course)
    updater = _load_updater()
    original_replace: Callable[..., object] = updater.os.replace
    injected = False
    course_root = old_course.resolve()

    def replace_then_fail_once(source: object, destination: object) -> object:
        nonlocal injected
        target = Path(destination).resolve()
        inside_course = target == course_root or course_root in target.parents
        if inside_course and not injected:
            injected = True
            result = original_replace(source, destination)
            raise OSError("injected replacement failure after mutation")
        return original_replace(source, destination)

    monkeypatch.setattr(updater.os, "replace", replace_then_fail_once)
    exit_code = updater.main(
        [
            "apply",
            str(old_course),
            "--plan",
            str(plan_path),
            "--candidate-source",
            str(candidate),
            "--confirm-stopped",
            "--json",
            str(tmp_path / "failed-result.json"),
        ]
    )
    captured = capsys.readouterr()

    assert injected is True
    assert exit_code != 0
    assert captured.err.startswith("course update failed:")
    assert _tree_snapshot(old_course) == before


def test_transaction_rollback_removes_new_ignored_named_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = _load_updater()
    root = tmp_path / "transaction-course"
    root.mkdir()
    existing = root / "sentinel.txt"
    existing.write_text("before\n", encoding="utf-8")
    original_replace: Callable[..., object] = updater.os.replace
    injected = False

    def replace_then_fail(source: object, destination: object) -> object:
        nonlocal injected
        result = original_replace(source, destination)
        if not injected:
            injected = True
            raise OSError("fail after creating ignored-name path")
        return result

    monkeypatch.setattr(updater.os, "replace", replace_then_fail)
    operations = [
        {
            "path": "platform/course/source/node_modules/generated.txt",
            "classification": "author-source",
            "action": "write",
        },
        {
            "path": "sentinel.txt",
            "classification": "template",
            "action": "write",
        },
    ]

    with pytest.raises(updater.CourseUpdateError, match="rolled back"):
        updater._apply_transaction(
            root,
            operations,
            {
                "platform/course/source/node_modules/generated.txt": b"new\n",
                "sentinel.txt": b"after\n",
            },
        )

    assert injected is True
    assert existing.read_text(encoding="utf-8") == "before\n"
    assert not (root / "platform").exists()
