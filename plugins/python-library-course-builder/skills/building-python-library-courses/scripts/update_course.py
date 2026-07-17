#!/usr/bin/env python3
"""Check and transactionally apply CourseKit generated-course migrations."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from course_provenance import (
    PROVENANCE_RELATIVE_PATH,
    ProvenanceError,
    build_generation_provenance,
    course_impacting_migrations,
    hash_file,
    hash_tree,
    load_generation_provenance,
)
import scaffold_course


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST_PATH = SKILL_ROOT.parents[1] / ".codex-plugin" / "plugin.json"
UPDATE_SCHEMA_VERSION = 1
GENERATED_BASELINE_MESSAGE = "coursekit: generated baseline"
STATE_RELATIVE_PATH = "labs/.coursekit/state.json"
SOURCE_RELATIVE_PATH = "platform/course/source"
MANAGED_ROLES = {"template", "compiled", "workspace-runtime"}
IGNORED_SNAPSHOT_NAMES = {
    ".DS_Store",
    ".coverage",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
}

# These are hashes of generated files shipped by the three supported releases.
# They are embedded so an installed Skill does not need its own Git repository.
LEGACY_RELEASE_SIGNATURES: dict[str, dict[str, str]] = {
    "0.1.0": {
        "platform/app/CourseKitApp.tsx": "fc078e8a1fd1c40ada87cd188df0495a9af9ec750a423d2efd3a1784f9e12c46",
        "platform/app/globals.css": "c3c1b6fcdcbadd87154992e1268c5a7db3e8ef0413e9abb26ced08522b0450db",
        "platform/coursekit/compiler.py": "84fb1850057eb218c65d8545da3c4bb8bfcaeaa84d99db3aecbafb08a7c9f4e6",
    },
    "0.1.1": {
        "platform/app/CourseKitApp.tsx": "b8b81cf9b98d88ee75f7273df5a7aa964aa616136db3179ed27f7ff27dbed451",
        "platform/app/globals.css": "acc93b84d422e940c8a1c95fd4039f9389a9e9155658593f38bad2badf08d8f9",
        "platform/coursekit/compiler.py": "84fb1850057eb218c65d8545da3c4bb8bfcaeaa84d99db3aecbafb08a7c9f4e6",
    },
    "0.2.0": {
        "platform/app/CourseKitApp.tsx": "5d46126c4b92a2b3dece8fc312696b6ec968a22c8b3ffe062f57a89b6a7b44c4",
        "platform/app/globals.css": "acc93b84d422e940c8a1c95fd4039f9389a9e9155658593f38bad2badf08d8f9",
        "platform/coursekit/compiler.py": "48d25f72ed1cab1e0af2b039376333e4722a9afcba59f9fae6da622265513bad",
    },
}
LEGACY_REQUIRED_PATHS = {
    "package.json",
    "platform/course/source/course.json",
    "platform/course/manifest.json",
    "platform/coursekit/compiler.py",
    "labs/manifest.json",
}
LEGACY_APPLIED_MIGRATIONS: dict[str, tuple[str, ...]] = {
    "0.1.0": (),
    "0.1.1": ("coursekit-0.1.1-responsive-workspace",),
    "0.2.0": (
        "coursekit-0.1.1-responsive-workspace",
        "coursekit-0.2.0-readiness-and-bilingual-runtime",
        "coursekit-0.2.0-tutorial-markdown-v1",
    ),
}


class CourseUpdateError(RuntimeError):
    """The requested update could not be proved safe."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _read_json_object(path: Path, location: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CourseUpdateError(f"cannot read {location}: {error}") from error
    if not isinstance(value, dict):
        raise CourseUpdateError(f"{location} must be a JSON object")
    return value


def _plugin_version() -> str:
    manifest = _read_json_object(PLUGIN_MANIFEST_PATH, "plugin manifest")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise CourseUpdateError("plugin manifest has no version")
    return version


def _safe_relative(value: str) -> str:
    if not value or "\\" in value:
        raise CourseUpdateError(f"unsafe generated path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or ".." in path.parts:
        raise CourseUpdateError(f"unsafe generated path: {value!r}")
    if path.parts and path.parts[0] == ".git":
        raise CourseUpdateError(f"update cannot manage Git internals: {value}")
    return value


def _course_root(path: Path) -> Path:
    supplied = path.expanduser()
    if supplied.is_symlink():
        raise CourseUpdateError(f"course path cannot be a symlink: {supplied}")
    try:
        root = supplied.resolve(strict=True)
    except OSError as error:
        raise CourseUpdateError(f"course path is unavailable: {error}") from error
    if not root.is_dir():
        raise CourseUpdateError(f"course path is not a directory: {root}")
    required = (
        root / "platform/course/source/course.json",
        root / "platform/course/manifest.json",
        root / "labs/manifest.json",
    )
    missing = [
        str(path.relative_to(root))
        for path in required
        if path.is_symlink() or not path.is_file()
    ]
    if missing:
        raise CourseUpdateError(
            "path is not a generated CourseKit course; missing " + ", ".join(missing)
        )
    return root


def _is_ignored(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return bool(parts and parts[0] == ".git") or any(
        name in IGNORED_SNAPSHOT_NAMES for name in parts
    )


def _snapshot(root: Path) -> str:
    """Hash all meaningful course bytes, including protected and state files."""

    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        in_canonical_source = relative == SOURCE_RELATIVE_PATH or relative.startswith(
            SOURCE_RELATIVE_PATH + "/"
        )
        if _is_ignored(relative) and not in_canonical_source:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"link\0")
            digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        elif path.is_file():
            digest.update(b"file\0")
            digest.update(hash_file(path).encode("ascii"))
        elif path.is_dir():
            digest.update(b"dir\0")
        else:
            digest.update(b"special\0")
        digest.update(b"\0")
    return digest.hexdigest()


def _run(
    command: list[str],
    *,
    cwd: Path,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_bytes,
        capture_output=True,
        check=False,
    )


def _git_text(root: Path, arguments: list[str]) -> str:
    completed = _run(["git", *arguments], cwd=root)
    if completed.returncode:
        detail = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
        raise CourseUpdateError(f"cannot inspect generated Git baseline: {detail.strip()}")
    try:
        return completed.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise CourseUpdateError("generated Git baseline has non-UTF-8 metadata") from error


def _baseline_commit(root: Path, *, required: bool) -> str | None:
    probe = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root)
    if probe.returncode:
        if required:
            raise CourseUpdateError(
                "course has no provenance and no generated Git baseline"
            )
        return None
    completed = _run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=root)
    if completed.returncode:
        if required:
            detail = (completed.stdout + completed.stderr).decode(
                "utf-8", errors="replace"
            )
            raise CourseUpdateError(
                f"cannot inspect generated Git baseline: {detail.strip()}"
            )
        return None
    try:
        commits = completed.stdout.decode("utf-8").strip().splitlines()
    except UnicodeDecodeError as error:
        if required:
            raise CourseUpdateError(
                "generated Git baseline has non-UTF-8 metadata"
            ) from error
        return None
    if len(commits) != 1:
        if required:
            raise CourseUpdateError("course does not have one trustworthy root baseline")
        return None
    return commits[0]


def _git_blob(root: Path, commit: str | None, relative: str) -> bytes | None:
    if commit is None:
        return None
    completed = _run(["git", "show", f"{commit}:{relative}"], cwd=root)
    if completed.returncode:
        return None
    return completed.stdout


def _git_tree_paths(root: Path, commit: str) -> tuple[str, ...]:
    completed = _run(["git", "ls-tree", "-r", "--name-only", "-z", commit], cwd=root)
    if completed.returncode:
        raise CourseUpdateError("cannot enumerate generated Git baseline")
    try:
        values = completed.stdout.decode("utf-8").split("\0")
    except UnicodeDecodeError as error:
        raise CourseUpdateError("generated Git baseline contains non-UTF-8 paths") from error
    return tuple(_safe_relative(value) for value in values if value)


def _detect_legacy_version(root: Path, commit: str, paths: set[str]) -> str:
    message = _git_text(root, ["show", "-s", "--format=%s", commit])
    if message != GENERATED_BASELINE_MESSAGE:
        raise CourseUpdateError(
            "course has no provenance and its root commit is not a generated CourseKit baseline"
        )
    if not LEGACY_REQUIRED_PATHS.issubset(paths):
        missing = sorted(LEGACY_REQUIRED_PATHS - paths)
        raise CourseUpdateError(
            "legacy generated baseline is missing structural anchors: " + ", ".join(missing)
        )
    for version, signature in LEGACY_RELEASE_SIGNATURES.items():
        if all(
            (blob := _git_blob(root, commit, relative)) is not None
            and _sha256_bytes(blob) == expected
            for relative, expected in signature.items()
        ):
            return version

    # A current generator baseline with its provenance deliberately removed is
    # still structurally trustworthy. Treat it as the newest supported legacy
    # shape; registry IDs, not this version label, decide whether work remains.
    current_anchors = (
        "platform/coursekit/compiler.py",
        "platform/app/CourseKitApp.tsx",
        "platform/app/globals.css",
    )
    if all(
        (blob := _git_blob(root, commit, relative)) is not None
        and (template := SKILL_ROOT / "assets/course-template" / relative).is_file()
        and _sha256_bytes(blob) == hash_file(template)
        for relative in current_anchors
    ):
        return "0.2.0"
    raise CourseUpdateError("generated baseline does not match a supported v0.1+ course")


def _current_course_spec(root: Path) -> dict[str, Any]:
    snapshot = root / "platform/course/authoring-spec.json"
    if snapshot.is_file():
        return _read_json_object(snapshot, "compiled authoring specification")
    course = _read_json_object(
        root / "platform/course/source/course.json", "canonical course source"
    )
    target = course.get("target")
    if not isinstance(target, dict):
        raise CourseUpdateError("canonical source has no target object")
    return {
        "schema_version": course.get("schema_version"),
        "course": course,
        "target": target,
        "labs": [],
    }


def _identity(root: Path, spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    authoring = _current_course_spec(root) if spec is None else spec
    manifest = _read_json_object(root / "platform/course/manifest.json", "course manifest")
    course = authoring.get("course")
    target = authoring.get("target")
    if not isinstance(course, Mapping) or not isinstance(target, Mapping):
        raise CourseUpdateError("authoring specification has no course/target identity")
    labs = authoring.get("labs", [])
    lab_identity: list[dict[str, Any]] = []
    if isinstance(labs, list):
        for lab in labs:
            if not isinstance(lab, Mapping):
                continue
            questions = lab.get("questions", [])
            lab_identity.append(
                {
                    "id": str(lab.get("id", "")),
                    "questions": [
                        str(question.get("id", ""))
                        for question in questions
                        if isinstance(question, Mapping)
                    ],
                }
            )
    return {
        "course_id": str(course.get("id", "")),
        "curriculum_id": str(manifest.get("curriculum_id", "")),
        "schema_version": authoring.get("schema_version"),
        "language": str(course.get("language", "zh-CN")),
        "target": {
            "name": str(target.get("name", "")),
            "version": str(target.get("version", "")),
        },
        "labs": lab_identity,
    }


def _normalize_candidate_source(candidate: Path, course_root: Path) -> Path:
    supplied = candidate.expanduser()
    if supplied.is_symlink():
        raise CourseUpdateError("candidate source path cannot be a symlink")
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as error:
        raise CourseUpdateError(f"candidate source is unavailable: {error}") from error
    options = (
        resolved / SOURCE_RELATIVE_PATH,
        resolved / "course/source",
        resolved,
    )
    source = next((path for path in options if (path / "course.json").is_file()), None)
    if source is None or not source.is_dir():
        raise CourseUpdateError("candidate source must contain course.json")
    if (
        source == course_root
        or course_root in source.parents
        or source in course_root.parents
    ):
        raise CourseUpdateError(
            "candidate source and live course cannot contain one another"
        )
    _validate_source_tree(source)
    return source


def _validate_source_tree(source: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise CourseUpdateError("canonical source must be a regular directory")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise CourseUpdateError(
                "canonical source cannot contain symlinks: "
                + path.relative_to(source).as_posix()
            )
        if not path.is_dir() and not path.is_file():
            raise CourseUpdateError(
                "canonical source contains a special file: "
                + path.relative_to(source).as_posix()
            )


def _runtime_contract(spec: Mapping[str, Any]) -> dict[str, Any]:
    course = spec.get("course")
    if not isinstance(course, Mapping):
        raise CourseUpdateError("authoring specification has no course runtime contract")
    dependencies = course.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise CourseUpdateError("course dependencies must be a list")
    return {
        "python_requires": str(course.get("python_requires", "")),
        "dependencies": [str(value) for value in dependencies],
    }


def _materialize_locks_without_drift(
    shadow: Path, current: Path, spec: Mapping[str, Any]
) -> None:
    course = spec.get("course")
    dependencies = course.get("dependencies", []) if isinstance(course, Mapping) else []
    if not dependencies:
        scaffold_course.materialize_python_locks(shadow, dict(spec))
        return
    base = shadow / "platform/support/labs-stdlib.uv.lock"
    base.unlink(missing_ok=True)
    for relative in ("platform/uv.lock", "labs/uv.lock"):
        source = current / relative
        if not source.is_file() or source.is_symlink():
            raise CourseUpdateError(
                f"cannot preserve dependency lock during update: {relative}"
            )
        destination = shadow / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _verify_shadow(shadow: Path) -> None:
    completed = _run(
        [sys.executable, "-m", "coursekit.cli", "check", "course/source", "course"],
        cwd=shadow / "platform",
    )
    if completed.returncode:
        detail = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
        raise CourseUpdateError(f"shadow compiler verification failed: {detail.strip()}")
    scaffold_course.verify_no_tokens(shadow)
    try:
        load_generation_provenance(shadow, verify_hashes=True)
    except ProvenanceError as error:
        raise CourseUpdateError(f"shadow provenance verification failed: {error}") from error


def _build_shadow(
    current: Path,
    *,
    candidate_source: Path | None,
    parent: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    shadow = parent / "project"
    scaffold_course.copy_template(shadow)
    source = (
        current / SOURCE_RELATIVE_PATH
        if candidate_source is None
        else _normalize_candidate_source(candidate_source, current)
    )
    _validate_source_tree(source)
    target_source = shadow / SOURCE_RELATIVE_PATH
    if target_source == source or source in target_source.parents:
        raise CourseUpdateError("shadow destination cannot be inside canonical source")
    target_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target_source)
    try:
        scaffold_course.run_checked(
            [sys.executable, "-m", "coursekit.cli", "compile", "course/source", "course"],
            cwd=shadow / "platform",
        )
        spec = _read_json_object(
            shadow / "platform/course/authoring-spec.json",
            "shadow authoring specification",
        )
        scaffold_course.replace_template_tokens(shadow, spec)
        scaffold_course.configure_platform_dependencies(shadow / "platform", spec)
        scaffold_course.compile_and_initialize(shadow, spec)
        _materialize_locks_without_drift(shadow, current, spec)
        scaffold_course.verify_no_tokens(shadow)
        provenance = build_generation_provenance(shadow, spec)
        provenance_path = shadow / PROVENANCE_RELATIVE_PATH
        provenance_path.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _verify_shadow(shadow)
    except (OSError, ProvenanceError, scaffold_course.ScaffoldError) as error:
        if isinstance(error, CourseUpdateError):
            raise
        raise CourseUpdateError(f"cannot build verified shadow course: {error}") from error
    return shadow, spec, provenance


def _load_baseline(root: Path) -> dict[str, Any]:
    provenance_path = root / PROVENANCE_RELATIVE_PATH
    commit = _baseline_commit(root, required=not provenance_path.is_file())
    if provenance_path.is_file():
        try:
            provenance = load_generation_provenance(root)
        except ProvenanceError as error:
            raise CourseUpdateError(f"invalid course provenance: {error}") from error
        version = str(provenance["plugin"]["version"])
        return {
            "kind": "provenance",
            "version": version,
            "applied_migrations": tuple(provenance["applied_migrations"]),
            "managed_files": dict(provenance["managed_files"]),
            "commit": commit,
            "tree_paths": set(_git_tree_paths(root, commit)) if commit else set(),
        }

    if commit is None:  # Defensive: required=True above already rejects this.
        raise CourseUpdateError("legacy course has no generated Git baseline")
    paths = set(_git_tree_paths(root, commit))
    version = _detect_legacy_version(root, commit, paths)
    return {
        "kind": "legacy",
        "version": version,
        "applied_migrations": LEGACY_APPLIED_MIGRATIONS[version],
        "managed_files": {},
        "commit": commit,
        "tree_paths": paths,
    }


def _pending_migrations(baseline: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    version = str(baseline["version"])
    supported = set(LEGACY_RELEASE_SIGNATURES) | {_plugin_version()}
    if version not in supported:
        raise CourseUpdateError(
            f"course provenance version {version} is outside supported v0.1+ releases"
        )
    try:
        missing = course_impacting_migrations(baseline["applied_migrations"])
    except ProvenanceError as error:
        raise CourseUpdateError(f"cannot resolve migration chain: {error}") from error
    return tuple(entry for entry in missing if version in entry["from_versions"])


def _legacy_managed_role(relative: str, target: Mapping[str, Any]) -> str | None:
    target_record = target.get(relative)
    if isinstance(target_record, Mapping) and target_record.get("role") in MANAGED_ROLES:
        return str(target_record["role"])
    if relative == SOURCE_RELATIVE_PATH or relative.startswith(SOURCE_RELATIVE_PATH + "/"):
        return None
    if relative == "platform/course" or relative.startswith("platform/course/"):
        return "compiled"
    if relative.startswith("labs/_course/") or relative in {
        "labs/README.md",
        "labs/manifest.json",
        "labs/pyproject.toml",
        "labs/uv.lock",
    }:
        return "workspace-runtime"
    if re.fullmatch(r"labs/(?:lab|prep)\d+(?:/.*)?", relative):
        return None
    if relative.startswith("labs/"):
        return None
    return "template"


def _complete_legacy_managed(
    root: Path,
    baseline: dict[str, Any],
    target_managed: Mapping[str, Any],
) -> None:
    commit = str(baseline["commit"])
    managed: dict[str, dict[str, str]] = {}
    for relative in sorted(baseline["tree_paths"]):
        role = _legacy_managed_role(relative, target_managed)
        if role is None or relative == PROVENANCE_RELATIVE_PATH:
            continue
        blob = _git_blob(root, commit, relative)
        if blob is None:
            continue
        managed[relative] = {"role": role, "sha256": _sha256_bytes(blob)}
    baseline["managed_files"] = managed


def _current_bytes(root: Path, relative: str) -> bytes | None:
    path = root / _safe_relative(relative)
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise CourseUpdateError(f"managed path is not a regular file: {relative}")
    return path.read_bytes()


def _base_bytes(
    root: Path,
    baseline: Mapping[str, Any],
    relative: str,
    baseline_hash: str,
    current: bytes | None,
) -> bytes | None:
    blob = _git_blob(root, baseline.get("commit"), relative)
    if blob is not None and _sha256_bytes(blob) == baseline_hash:
        return blob
    if current is not None and _sha256_bytes(current) == baseline_hash:
        return current
    return None


def _merge_text(
    current: bytes,
    base: bytes,
    target: bytes,
) -> bytes | None:
    for value in (current, base, target):
        if b"\0" in value:
            return None
        try:
            value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    with tempfile.TemporaryDirectory(prefix="coursekit-merge-") as raw:
        directory = Path(raw)
        current_path = directory / "current"
        base_path = directory / "base"
        target_path = directory / "target"
        current_path.write_bytes(current)
        base_path.write_bytes(base)
        target_path.write_bytes(target)
        completed = _run(
            [
                "git",
                "merge-file",
                "-p",
                str(current_path),
                str(base_path),
                str(target_path),
            ],
            cwd=directory,
        )
        return completed.stdout if completed.returncode == 0 else None


def _classify_unmanaged(relative: str) -> str:
    if relative == STATE_RELATIVE_PATH or relative.startswith("labs/.coursekit/"):
        return "state"
    if relative == SOURCE_RELATIVE_PATH or relative.startswith(SOURCE_RELATIVE_PATH + "/"):
        return "author-source"
    if re.fullmatch(r"labs/(?:lab|prep)\d+(?:/.*)?", relative):
        return "protected"
    return "unknown"


def _all_live_files(root: Path) -> tuple[str, ...]:
    values: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if _is_ignored(relative) or path.is_dir() and not path.is_symlink():
            continue
        values.append(relative)
    return tuple(values)


def _managed_operations(
    root: Path,
    baseline: Mapping[str, Any],
    shadow: Path,
    target_provenance: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, bytes]]:
    baseline_managed = baseline["managed_files"]
    target_managed = target_provenance["managed_files"]
    if not isinstance(baseline_managed, Mapping) or not isinstance(target_managed, Mapping):
        raise CourseUpdateError("managed-file provenance is malformed")
    operations: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    payloads: dict[str, bytes] = {}
    handled: set[str] = set()

    for relative in sorted(set(baseline_managed) | set(target_managed)):
        _safe_relative(relative)
        handled.add(relative)
        base_record = baseline_managed.get(relative)
        target_record = target_managed.get(relative)
        role = str(
            (target_record or base_record or {}).get("role", "template")
        )
        if role not in MANAGED_ROLES:
            raise CourseUpdateError(f"unsupported managed role for {relative}: {role}")
        path = root / relative
        if path.is_symlink() or path.exists() and not path.is_file():
            conflicts.append(
                {"path": relative, "reason": "managed path is not a regular file"}
            )
            operations.append(
                {"path": relative, "classification": role, "action": "conflict"}
            )
            continue
        current = path.read_bytes() if path.is_file() else None
        target = (
            (shadow / relative).read_bytes()
            if target_record is not None
            else None
        )
        base_hash = str(base_record["sha256"]) if base_record is not None else None
        base = (
            _base_bytes(root, baseline, relative, base_hash, current)
            if base_hash is not None
            else None
        )
        current_hash = _sha256_bytes(current) if current is not None else None
        target_hash = _sha256_bytes(target) if target is not None else None

        if target is None:
            if current is None:
                action = "preserve"
            elif base_hash is not None and current_hash == base_hash:
                action = "remove"
            else:
                action = "preserve"
            operations.append(
                {"path": relative, "classification": role, "action": action}
            )
            continue

        if base_record is None:
            if current is None:
                action = "write"
                payloads[relative] = target
            elif current_hash == target_hash:
                action = "preserve"
            else:
                action = "conflict"
                conflicts.append(
                    {
                        "path": relative,
                        "reason": "new managed path collides with an existing local file",
                    }
                )
            operations.append(
                {"path": relative, "classification": role, "action": action}
            )
            continue

        if current is None:
            action = "conflict"
            conflicts.append(
                {"path": relative, "reason": "locally deleted managed file changed upstream"}
            )
        elif current_hash == target_hash:
            action = "preserve"
        elif current_hash == base_hash:
            action = "write"
            payloads[relative] = target
        elif target_hash == base_hash:
            action = "preserve"
        elif base is None:
            action = "conflict"
            conflicts.append(
                {
                    "path": relative,
                    "reason": "managed file changed locally and its baseline bytes are unavailable",
                }
            )
        else:
            merged = _merge_text(current, base, target)
            if merged is None:
                action = "conflict"
                conflicts.append(
                    {
                        "path": relative,
                        "reason": "managed file has unresolved local and migration changes",
                    }
                )
            else:
                action = "merge"
                payloads[relative] = merged
        operations.append(
            {"path": relative, "classification": role, "action": action}
        )

    for relative in _all_live_files(root):
        if relative in handled or relative == PROVENANCE_RELATIVE_PATH:
            continue
        operations.append(
            {
                "path": relative,
                "classification": _classify_unmanaged(relative),
                "action": "preserve",
            }
        )
    operations.sort(key=lambda item: item["path"])
    conflicts.sort(key=lambda item: item["path"])
    return operations, conflicts, payloads


def _source_operations(
    root: Path,
    shadow: Path,
) -> tuple[list[dict[str, str]], dict[str, bytes]]:
    current_root = root / SOURCE_RELATIVE_PATH
    target_root = shadow / SOURCE_RELATIVE_PATH
    current = {
        path.relative_to(current_root).as_posix(): path.read_bytes()
        for path in sorted(current_root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    target = {
        path.relative_to(target_root).as_posix(): path.read_bytes()
        for path in sorted(target_root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    operations: list[dict[str, str]] = []
    payloads: dict[str, bytes] = {}
    for local in sorted(set(current) | set(target)):
        relative = f"{SOURCE_RELATIVE_PATH}/{local}"
        if local not in target:
            action = "remove"
        elif local not in current or current[local] != target[local]:
            action = "write"
            payloads[relative] = target[local]
        else:
            action = "preserve"
        operations.append(
            {"path": relative, "classification": "author-source", "action": action}
        )
    return operations, payloads


def _preservation_operations(
    root: Path,
    managed: Mapping[str, Any],
) -> list[dict[str, str]]:
    operations: list[dict[str, str]] = []
    for relative in _all_live_files(root):
        if relative == PROVENANCE_RELATIVE_PATH:
            continue
        record = managed.get(relative)
        if isinstance(record, Mapping) and record.get("role") in MANAGED_ROLES:
            classification = str(record["role"])
        else:
            classification = _classify_unmanaged(relative)
        operations.append(
            {"path": relative, "classification": classification, "action": "preserve"}
        )
    return operations


def _plan_digest(plan: Mapping[str, Any]) -> str:
    return _canonical_digest(
        {key: value for key, value in plan.items() if key != "plan_digest"}
    )


def _target_snapshot(
    provenance: Mapping[str, Any], payloads: Mapping[str, bytes]
) -> str:
    return _canonical_digest(
        {
            "provenance": provenance,
            "payloads": {
                relative: _sha256_bytes(value)
                for relative, value in sorted(payloads.items())
            },
        }
    )


def _make_plan(
    root: Path,
    *,
    candidate_source: Path | None = None,
    keep_shadow: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    _validate_source_tree(root / SOURCE_RELATIVE_PATH)
    baseline = _load_baseline(root)
    migrations = _pending_migrations(baseline)
    migration_ids = [str(entry["id"]) for entry in migrations]
    current_spec = _current_course_spec(root)
    current_identity = _identity(root)
    snapshot = _snapshot(root)
    target_version = _plugin_version()

    if not migrations:
        plan: dict[str, Any] = {
            "schema_version": UPDATE_SCHEMA_VERSION,
            "command": "check",
            "status": "up_to_date",
            "current_version": str(baseline["version"]),
            "target_version": target_version,
            "migrations": [],
            "identity_change": False,
            "progress_reset_required": False,
            "operations": _preservation_operations(
                root, baseline.get("managed_files", {})
            ),
            "conflicts": [],
            "course_snapshot": snapshot,
            "candidate_source_sha256": None,
            "target_snapshot_sha256": None,
        }
        plan["plan_digest"] = _plan_digest(plan)
        return plan, None

    temporary = tempfile.TemporaryDirectory(
        prefix=f".{root.name}-coursekit-check-", dir=root.parent
    )
    try:
        shadow_parent = Path(temporary.name)
        shadow, target_spec, target_provenance = _build_shadow(
            root,
            candidate_source=candidate_source,
            parent=shadow_parent,
        )
        if baseline["kind"] == "legacy":
            _complete_legacy_managed(
                root, baseline, target_provenance["managed_files"]
            )
        operations, conflicts, target_payloads = _managed_operations(
            root, baseline, shadow, target_provenance
        )
        candidate_digest: str | None = None
        if candidate_source is not None:
            source_root = _normalize_candidate_source(candidate_source, root)
            candidate_digest = hash_tree(source_root)
            source_operations, source_payloads = _source_operations(root, shadow)
            target_payloads.update(source_payloads)
            replacements = {item["path"]: item for item in source_operations}
            operations = [
                replacements.get(item["path"], item)
                for item in operations
                if item["path"] not in replacements
                or item["classification"] == "author-source"
            ]
            existing = {item["path"] for item in operations}
            operations.extend(
                item for item in source_operations if item["path"] not in existing
            )
            operations.sort(key=lambda item: item["path"])

        target_identity = _identity(shadow, target_spec)
        if _runtime_contract(current_spec) != _runtime_contract(target_spec):
            raise CourseUpdateError(
                "update cannot change Python requirements or course dependencies"
            )
        if current_identity["language"] != target_identity["language"]:
            raise CourseUpdateError("update cannot change the course language")
        if current_identity["target"] != target_identity["target"]:
            raise CourseUpdateError("update cannot change the pinned target or version")
        identity_change = current_identity != target_identity
        if (
            current_identity.get("schema_version") == 2
            and any(
                entry["source_schema_change"]
                and entry["curriculum_identity_change"]
                for entry in migrations
            )
        ):
            identity_change = True
        progress_reset = identity_change and (root / STATE_RELATIVE_PATH).is_file()
        plan = {
            "schema_version": UPDATE_SCHEMA_VERSION,
            "command": "check",
            "status": "blocked" if conflicts else "ready",
            "current_version": str(baseline["version"]),
            "target_version": target_version,
            "migrations": migration_ids,
            "identity_change": identity_change,
            "progress_reset_required": progress_reset,
            "operations": operations,
            "conflicts": conflicts,
            "course_snapshot": snapshot,
            "candidate_source_sha256": candidate_digest,
            "target_snapshot_sha256": _target_snapshot(
                target_provenance, target_payloads
            ),
        }
        plan["plan_digest"] = _plan_digest(plan)
        context = {
            "baseline": baseline,
            "shadow": shadow,
            "target_spec": target_spec,
            "target_provenance": target_provenance,
            "operations": operations,
            "conflicts": conflicts,
            "target_payloads": target_payloads,
            "temporary": temporary,
        }
        if keep_shadow:
            return plan, context
        return plan, None
    finally:
        if not keep_shadow:
            temporary.cleanup()


def check_course(
    course: Path,
    *,
    candidate_source: Path | None = None,
) -> dict[str, Any]:
    root = _course_root(course)
    plan, _ = _make_plan(root, candidate_source=candidate_source)
    return plan


def _validate_output_path(path: Path, root: Path, label: str) -> Path:
    supplied = path.expanduser().absolute()
    resolved_parent = supplied.parent.resolve()
    resolved = resolved_parent / supplied.name
    if resolved == root or root in resolved.parents:
        raise CourseUpdateError(f"{label} path must be outside the course")
    resolved_parent.mkdir(parents=True, exist_ok=True)
    if resolved.is_symlink() or resolved.exists() and not resolved.is_file():
        raise CourseUpdateError(f"{label} path must be a regular JSON file")
    return resolved


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_plan(path: Path) -> dict[str, Any]:
    plan = _read_json_object(path, "course update plan")
    required = {
        "schema_version",
        "command",
        "status",
        "current_version",
        "target_version",
        "migrations",
        "identity_change",
        "progress_reset_required",
        "operations",
        "conflicts",
        "course_snapshot",
        "candidate_source_sha256",
        "target_snapshot_sha256",
        "plan_digest",
    }
    if set(plan) != required:
        raise CourseUpdateError("course update plan has unexpected or missing fields")
    if plan["schema_version"] != UPDATE_SCHEMA_VERSION or plan["command"] != "check":
        raise CourseUpdateError("unsupported course update plan")
    digest = plan.get("plan_digest")
    if not isinstance(digest, str) or digest != _plan_digest(plan):
        raise CourseUpdateError("course update plan digest is invalid")
    return plan


def _merge_operation_sets(
    managed: list[dict[str, str]],
    source: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    by_path = {item["path"]: item for item in managed}
    for item in source:
        by_path[item["path"]] = item
    return [by_path[path] for path in sorted(by_path)]


def _prepare_apply(
    root: Path,
    reviewed: Mapping[str, Any],
    candidate_source: Path | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    pending = _pending_migrations(_load_baseline(root))
    needs_candidate = any(entry["impact"] == "content" for entry in pending)
    candidate_in_plan = reviewed.get("candidate_source_sha256") is not None
    if needs_candidate and (candidate_source is None or not candidate_in_plan):
        raise CourseUpdateError(
            "content migrations require check and apply with the same --candidate-source"
        )
    if candidate_source is not None and not candidate_in_plan:
        raise CourseUpdateError(
            "candidate source was not bound by the reviewed plan; rerun check"
        )
    if (
        _identity(root).get("schema_version") == 2
        and any(entry["source_schema_change"] for entry in pending)
        and (candidate_source is None or not candidate_in_plan)
    ):
        raise CourseUpdateError(
            "schema-v2 migration requires a readiness-authored --candidate-source"
        )

    current, context = _make_plan(
        root,
        candidate_source=candidate_source if candidate_in_plan else None,
        keep_shadow=True,
    )
    if current["plan_digest"] != reviewed["plan_digest"]:
        if context is not None:
            context["temporary"].cleanup()
        raise CourseUpdateError(
            "course, candidate, or target bytes changed after check; rerun check"
        )
    if current["status"] == "blocked":
        if context is not None:
            context["temporary"].cleanup()
        raise CourseUpdateError("candidate update is blocked by conflicts")
    if current["status"] == "up_to_date":
        return current, None
    if context is None:
        raise CourseUpdateError("cannot prepare migration shadow")
    return current, context


def _safe_live_path(root: Path, relative: str) -> Path:
    path = root / _safe_relative(relative)
    current = root
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise CourseUpdateError(
                f"update destination has a symlink parent: {relative}"
            )
        if current.exists() and not current.is_dir():
            raise CourseUpdateError(
                f"update destination has a non-directory parent: {relative}"
            )
    return path


def _transaction_order(item: Mapping[str, str]) -> tuple[int, str]:
    relative = item["path"]
    if relative.startswith("labs/.coursekit/archive/"):
        priority = 0
    elif relative == STATE_RELATIVE_PATH:
        priority = 2
    elif relative == PROVENANCE_RELATIVE_PATH:
        priority = 3
    else:
        priority = 1
    return priority, relative


def _apply_transaction(
    root: Path,
    operations: list[dict[str, str]],
    payloads: Mapping[str, bytes],
) -> tuple[list[str], list[str], list[str]]:
    mutating = [
        item for item in operations if item["action"] in {"write", "merge", "remove"}
    ]
    for item in mutating:
        if item["action"] in {"write", "merge"} and item["path"] not in payloads:
            raise CourseUpdateError(f"missing staged payload for {item['path']}")
    originals: dict[str, tuple[bytes | None, int | None]] = {}
    rollback_directories: set[Path] = set()
    for item in mutating:
        relative = item["path"]
        destination = _safe_live_path(root, relative)
        if destination.is_symlink() or destination.exists() and not destination.is_file():
            raise CourseUpdateError(f"update target is not a regular file: {relative}")
        if destination.is_file():
            originals[relative] = (
                destination.read_bytes(),
                destination.stat().st_mode,
            )
        else:
            originals[relative] = (None, None)
        parent = destination.parent
        while parent != root:
            if not parent.exists():
                rollback_directories.add(parent)
            parent = parent.parent

    with tempfile.TemporaryDirectory(
        prefix=f".{root.name}-coursekit-transaction-", dir=root.parent
    ) as raw:
        transaction = Path(raw)
        staged = transaction / "staged"
        for relative, value in payloads.items():
            if relative not in originals:
                continue
            stage = staged / relative
            stage.parent.mkdir(parents=True, exist_ok=True)
            stage.write_bytes(value)
            _, mode = originals[relative]
            if mode is not None:
                stage.chmod(mode)

        attempted: list[str] = []
        try:
            for item in sorted(mutating, key=_transaction_order):
                relative = item["path"]
                destination = _safe_live_path(root, relative)
                action = item["action"]
                attempted.append(relative)
                if action == "remove":
                    destination.unlink(missing_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged / relative, destination)
        except Exception as error:
            rollback_errors: list[str] = []
            for relative in reversed(attempted):
                destination = root / relative
                original, mode = originals[relative]
                try:
                    if original is None:
                        if destination.is_symlink() or destination.is_file():
                            destination.unlink(missing_ok=True)
                    else:
                        restore = transaction / "restore" / relative
                        restore.parent.mkdir(parents=True, exist_ok=True)
                        restore.write_bytes(original)
                        if mode is not None:
                            restore.chmod(mode)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(restore, destination)
                except Exception as rollback_error:  # pragma: no cover - catastrophic
                    rollback_errors.append(f"{relative}: {rollback_error}")
            for directory in sorted(
                rollback_directories,
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if rollback_errors:
                raise CourseUpdateError(
                    "update failed and rollback was incomplete: "
                    + "; ".join(rollback_errors)
                ) from error
            raise CourseUpdateError(f"update transaction rolled back: {error}") from error

    written = sorted(
        item["path"] for item in mutating if item["action"] in {"write", "merge"}
    )
    removed = sorted(item["path"] for item in mutating if item["action"] == "remove")
    preserved = sorted(
        item["path"] for item in operations if item["action"] == "preserve"
    )
    return written, removed, preserved


def apply_course(
    course: Path,
    *,
    plan_path: Path,
    candidate_source: Path | None,
    confirm_stopped: bool,
    accept_progress_reset: bool,
) -> dict[str, Any]:
    if not confirm_stopped:
        raise CourseUpdateError("apply requires --confirm-stopped")
    root = _course_root(course)
    reviewed = _load_plan(plan_path)
    final_plan, context = _prepare_apply(root, reviewed, candidate_source)
    if context is None:
        preserved = [
            item["path"]
            for item in final_plan["operations"]
            if item["action"] == "preserve"
        ]
        return {
            "schema_version": UPDATE_SCHEMA_VERSION,
            "status": "up_to_date",
            "written": [],
            "removed": [],
            "preserved": sorted(preserved),
            "archived_state": None,
        }

    temporary = context["temporary"]
    try:
        target_provenance = context["target_provenance"]
        operations = [dict(item) for item in context["operations"]]
        conflicts = list(context["conflicts"])
        payloads = dict(context["target_payloads"])
        if conflicts:
            raise CourseUpdateError("candidate update has unresolved managed conflicts")
        if _snapshot(root) != reviewed["course_snapshot"]:
            raise CourseUpdateError("course changed while preparing the update")

        provenance_bytes = (
            json.dumps(target_provenance, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        operations = _merge_operation_sets(
            operations,
            [
                {
                    "path": PROVENANCE_RELATIVE_PATH,
                    "classification": "template",
                    "action": "write",
                }
            ],
        )
        payloads[PROVENANCE_RELATIVE_PATH] = provenance_bytes

        archived_state: str | None = None
        state = root / STATE_RELATIVE_PATH
        identity_change = bool(final_plan["identity_change"])
        if identity_change and state.is_file():
            if not accept_progress_reset:
                raise CourseUpdateError(
                    "curriculum identity changes; apply requires --accept-progress-reset"
                )
            state_bytes = state.read_bytes()
            archived_state = (
                "labs/.coursekit/archive/state-"
                + _sha256_bytes(state_bytes)[:12]
                + ".json"
            )
            archive_path = root / archived_state
            if archive_path.exists() and (
                archive_path.is_symlink()
                or not archive_path.is_file()
                or archive_path.read_bytes() != state_bytes
            ):
                raise CourseUpdateError("progress archive path already contains other data")
            operations = _merge_operation_sets(
                operations,
                [
                    {
                        "path": archived_state,
                        "classification": "state",
                        "action": "preserve" if archive_path.is_file() else "write",
                    },
                    {
                        "path": STATE_RELATIVE_PATH,
                        "classification": "state",
                        "action": "remove",
                    },
                ],
            )
            if not archive_path.is_file():
                payloads[archived_state] = state_bytes
        elif bool(reviewed["progress_reset_required"]):
            raise CourseUpdateError(
                "reviewed plan required a progress reset but active state changed"
            )

        written, removed, preserved = _apply_transaction(root, operations, payloads)
        return {
            "schema_version": UPDATE_SCHEMA_VERSION,
            "status": "applied",
            "written": written,
            "removed": removed,
            "preserved": preserved,
            "archived_state": archived_state,
        }
    finally:
        temporary.cleanup()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="plan an update without mutating COURSE")
    check.add_argument("course", type=Path)
    check.add_argument("--candidate-source", type=Path)
    check.add_argument("--json", dest="json_path", type=Path, required=True)

    apply = subparsers.add_parser("apply", help="apply a reviewed update plan")
    apply.add_argument("course", type=Path)
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--candidate-source", type=Path)
    apply.add_argument("--confirm-stopped", action="store_true")
    apply.add_argument("--accept-progress-reset", action="store_true")
    apply.add_argument("--json", dest="json_path", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        root = _course_root(args.course)
        json_path = _validate_output_path(args.json_path, root, "JSON output")
        if args.command == "check":
            result = check_course(
                root,
                candidate_source=args.candidate_source,
            )
        else:
            plan = args.plan.expanduser().resolve(strict=True)
            if plan == root or root in plan.parents:
                raise CourseUpdateError("reviewed plan must be stored outside the course")
            result = apply_course(
                root,
                plan_path=plan,
                candidate_source=args.candidate_source,
                confirm_stopped=args.confirm_stopped,
                accept_progress_reset=args.accept_progress_reset,
            )
        _write_json(json_path, result)
    except (
        CourseUpdateError,
        FileNotFoundError,
        OSError,
        ProvenanceError,
        json.JSONDecodeError,
    ) as error:
        print(f"course update failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
