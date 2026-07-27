#!/usr/bin/env python3
"""Plan and atomically replace an old generated course with a fresh one."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from typing import Any

from assess_readiness import ReadinessValidationError, build_route_contract
from authoring_contract import (
    v4_content_contract_sha256,
    v4_runtime_contract_sha256,
)
from course_provenance import (
    PROVENANCE_RELATIVE_PATH,
    ProvenanceError,
    load_generation_provenance,
    load_regeneration_metadata,
    trusted_readiness_reuse,
)
from verify_v4_course import (
    V4VerificationError,
    tree_sha256 as v4_tree_sha256,
    validate_v4_receipt,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST_PATH = SKILL_ROOT.parents[1] / ".codex-plugin" / "plugin.json"
VERIFIER_PATH = Path(__file__).with_name("verify_learning_project.py")
SOURCE_PATH = Path("platform/course/source")
STATE_PATH = Path("labs/.coursekit/state.json")
PLAN_SCHEMA_VERSION = 2
REPLACEMENT_POLICY = "delete-old-after-success"
ROLLBACK_LEARNER_NAME = "learner"
ROLLBACK_AUTHOR_NAME = "author"
GENERATED_BASELINE_MESSAGE = "coursekit: generated baseline"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
LOCAL_CACHEBUSTER_RE = re.compile(r"\+codex\.[0-9A-Za-z.-]+$")
V4_GENERATION_FIELDS = {
    "schema_version",
    "course_schema_version",
    "course_id",
    "curriculum_id",
    "plugin_version",
    "content_contract_sha256",
    "runtime_contract_sha256",
    "course_contract_sha256",
}
V4_DEPTH_BRIEF_FIELDS = (
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
)
V4_TARGETED_MUTABLE_PATHS = {
    ".coursekit/acceptance-progress.json",
    ".coursekit/acceptance-progress.json.lock",
    ".coursekit/progress.json",
    ".coursekit/progress.json.lock",
    ".coursekit/state.json",
    ".coursekit/state.json.lock",
}
V4_TARGETED_EPHEMERAL_NAMES = {
    ".DS_Store",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
MATERIAL_IGNORED_NAMES = {
    ".DS_Store",
    ".coverage",
    ".coursekit",
    ".coursekit-artifacts.json",
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "coverage.xml",
    "course-verification.json",
    "dist",
    "htmlcov",
    "node_modules",
}
MATERIAL_IGNORED_SUFFIXES = {
    ".log",
    ".pyc",
    ".pyd",
    ".pyo",
    ".tmp",
    ".tsbuildinfo",
}


class CourseRegenerationError(RuntimeError):
    """A course replacement could not be proven safe."""


@dataclass(frozen=True)
class RuntimeContract:
    plugin_version: str
    authoring_contract_sha256: str


@dataclass(frozen=True)
class CourseBaseline:
    kind: str
    schema_version: int
    plugin_version: str | None
    authoring_contract_sha256: str | None


@dataclass(frozen=True)
class _BoundRollbackEntry:
    """One inode-bound entry accepted for transient rollback deletion."""

    name: str
    kind: str
    fingerprint: tuple[int, int, int, int, int]
    mount_identity: tuple[int, ...] | None
    children: tuple[_BoundRollbackEntry, ...] = ()


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


def _read_json(path: Path, location: str) -> dict[str, Any]:
    if path.is_symlink():
        raise CourseRegenerationError(f"{location} cannot be a symlink")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CourseRegenerationError(f"cannot read {location}: {error}") from error
    if not isinstance(value, dict):
        raise CourseRegenerationError(f"{location} must be a JSON object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    destination = path.expanduser().absolute()
    if destination.is_symlink() or destination.exists() and destination.is_dir():
        raise CourseRegenerationError(f"JSON output path is unsafe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    rendered_bytes = rendered.encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        try:
            os.replace(temporary, destination)
        except OSError:
            # rename(2) wrappers can report an error after the directory entry
            # was already replaced. Treat the exact postcondition as success;
            # callers must never roll back an installed course while a matching
            # commit receipt is visible.
            if not _json_output_matches(destination, rendered_bytes):
                raise
        _fsync_directory(destination.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _json_output_matches(path: Path, expected: bytes) -> bool:
    try:
        return (
            not path.is_symlink()
            and path.is_file()
            and path.read_bytes() == expected
        )
    except OSError:
        return False


def _json_value_matches(path: Path, expected: Mapping[str, Any]) -> bool:
    rendered = (
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    return _json_output_matches(path, rendered)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _preflight_json_output(path: Path) -> Path:
    """Prove the result directory is writable before any course replacement."""

    destination = path.expanduser().absolute()
    if destination.is_symlink() or destination.exists() and destination.is_dir():
        raise CourseRegenerationError(f"JSON output path is unsafe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    probe: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.coursekit-write-probe-",
            dir=destination.parent,
            delete=False,
        ) as stream:
            probe = Path(stream.name)
    except OSError as error:
        raise CourseRegenerationError(
            f"JSON output directory is not writable: {destination.parent}: {error}"
        ) from error
    finally:
        if probe is not None:
            probe.unlink(missing_ok=True)
    return destination


def _plugin_version() -> str:
    manifest = _read_json(PLUGIN_MANIFEST_PATH, "plugin manifest")
    version = manifest.get("version")
    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
        raise CourseRegenerationError("plugin manifest has no valid semantic version")
    return version


def _contract_digest_from(value: object) -> str | None:
    if isinstance(value, str) and SHA256_RE.fullmatch(value):
        return value
    if isinstance(value, Mapping):
        digest = value.get("sha256")
        if isinstance(digest, str) and SHA256_RE.fullmatch(digest):
            return digest
    return None


def _current_authoring_contract_sha256() -> str:
    """Load the authoring fingerprint while tolerating the public helper names."""

    try:
        import authoring_contract
    except ImportError as error:
        raise CourseRegenerationError(
            "the installed Skill has no authoring-contract implementation"
        ) from error

    for name in (
        "authoring_contract_sha256",
        "current_authoring_contract",
        "authoring_contract_manifest",
    ):
        helper = getattr(authoring_contract, name, None)
        if callable(helper):
            digest = _contract_digest_from(helper())
            if digest is not None:
                return digest
    for name in ("AUTHORING_CONTRACT_SHA256", "sha256"):
        digest = _contract_digest_from(getattr(authoring_contract, name, None))
        if digest is not None:
            return digest
    raise CourseRegenerationError(
        "the installed Skill returned an invalid authoring-contract fingerprint"
    )


def _current_runtime() -> RuntimeContract:
    return RuntimeContract(
        plugin_version=_plugin_version(),
        authoring_contract_sha256=_current_authoring_contract_sha256(),
    )


def _version_core(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(version)
    if match is None:
        raise CourseRegenerationError(f"invalid plugin version in provenance: {version}")
    return tuple(int(match.group(index)) for index in range(1, 4))  # type: ignore[return-value]


def _control_path(root: Path, relative: Path, location: str) -> Path:
    path = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise CourseRegenerationError(f"{location} cannot contain symlinks")
    return path


def _course_root(path: Path, *, role: str) -> Path:
    supplied = path.expanduser()
    if supplied.is_symlink():
        raise CourseRegenerationError(f"{role} course path cannot be a symlink")
    try:
        root = supplied.resolve(strict=True)
    except OSError as error:
        raise CourseRegenerationError(f"{role} course path is unavailable: {error}") from error
    if not root.is_dir():
        raise CourseRegenerationError(f"{role} course path is not a directory: {root}")
    required = (
        SOURCE_PATH / "course.json",
        Path("platform/course/manifest.json"),
        Path("labs/manifest.json"),
    )
    missing = []
    for relative in required:
        candidate = _control_path(root, relative, f"{role} course")
        if not candidate.is_file():
            missing.append(relative.as_posix())
    if missing:
        raise CourseRegenerationError(
            f"{role} path is not a generated CourseKit course; missing "
            + ", ".join(missing)
        )
    return root


def _safe_output(path: Path, roots: tuple[Path, ...], *, location: str) -> Path:
    supplied = path.expanduser()
    if supplied.is_symlink():
        raise CourseRegenerationError(f"{location} cannot be a symlink")
    resolved = supplied.resolve(strict=False)
    for root in roots:
        if resolved == root or root in resolved.parents:
            raise CourseRegenerationError(
                f"{location} must be outside the live and candidate courses"
            )
    return resolved


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def _legacy_baseline(root: Path) -> CourseBaseline:
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    top_level = _git(root, "rev-parse", "--show-toplevel")
    roots = _git(root, "rev-list", "--max-parents=0", "HEAD")
    git_directory = root / ".git"
    try:
        owns_repository = (
            top_level.returncode == 0
            and Path(top_level.stdout.strip()).resolve(strict=True) == root
            and not git_directory.is_symlink()
            and git_directory.is_dir()
        )
    except OSError:
        owns_repository = False
    if inside.returncode or roots.returncode or not owns_repository:
        raise CourseRegenerationError(
            "course has no provenance and does not own a trustworthy generated Git baseline"
        )
    commits = [line for line in roots.stdout.splitlines() if line]
    if len(commits) != 1:
        raise CourseRegenerationError(
            "legacy course must have exactly one generated root commit"
        )
    message = _git(root, "show", "-s", "--format=%s", commits[0])
    if message.returncode or message.stdout.strip() != GENERATED_BASELINE_MESSAGE:
        raise CourseRegenerationError(
            "course has no provenance and its root commit is not a CourseKit baseline"
        )
    return CourseBaseline(
        kind="legacy-git",
        schema_version=0,
        plugin_version=None,
        authoring_contract_sha256=None,
    )


def _load_course_baseline(
    root: Path, *, verify_hashes: bool = False
) -> CourseBaseline:
    provenance_path = _control_path(
        root, Path(PROVENANCE_RELATIVE_PATH), "course provenance"
    )
    if not provenance_path.exists():
        return _legacy_baseline(root)
    if not provenance_path.is_file():
        raise CourseRegenerationError("course provenance is not a regular file")
    try:
        provenance = load_generation_provenance(root, verify_hashes=verify_hashes)
    except ProvenanceError as error:
        raise CourseRegenerationError(f"invalid course provenance: {error}") from error
    schema_version = provenance.get("schema_version")
    plugin = provenance.get("plugin")
    if not isinstance(schema_version, int) or not isinstance(plugin, Mapping):
        raise CourseRegenerationError("course provenance has no version metadata")
    version = plugin.get("version")
    if not isinstance(version, str):
        raise CourseRegenerationError("course provenance has no plugin version")
    contract = provenance.get("authoring_contract")
    digest = contract.get("sha256") if isinstance(contract, Mapping) else None
    return CourseBaseline(
        kind="provenance",
        schema_version=schema_version,
        plugin_version=version,
        authoring_contract_sha256=(
            digest if isinstance(digest, str) and SHA256_RE.fullmatch(digest) else None
        ),
    )


def _regeneration_state(
    baseline: CourseBaseline, runtime: RuntimeContract
) -> tuple[str, str]:
    if baseline.plugin_version is not None:
        current_core = _version_core(runtime.plugin_version)
        course_core = _version_core(baseline.plugin_version)
        if course_core > current_core:
            raise CourseRegenerationError(
                "course was generated by a newer plugin version; downgrade is refused"
            )
        if (
            course_core == current_core
            and baseline.authoring_contract_sha256 is not None
            and baseline.authoring_contract_sha256
            != runtime.authoring_contract_sha256
        ):
            is_local_iteration = (
                baseline.plugin_version != runtime.plugin_version
                and LOCAL_CACHEBUSTER_RE.search(runtime.plugin_version)
                is not None
            )
            if not is_local_iteration:
                raise CourseRegenerationError(
                    "plugin version collision: the same release version has a "
                    "different authoring-contract fingerprint"
                )
    if baseline.schema_version < 2 or baseline.authoring_contract_sha256 is None:
        return "regeneration_required", "legacy course has no authoring fingerprint"
    if baseline.authoring_contract_sha256 != runtime.authoring_contract_sha256:
        return "regeneration_required", "authoring contract changed"
    return "up_to_date", "authoring contract is unchanged"


def _identity(root: Path) -> dict[str, Any]:
    source = _read_json(
        _control_path(root, SOURCE_PATH / "course.json", "canonical source"),
        "canonical course source",
    )
    course = source
    manifest = source.get("manifest")
    target = manifest.get("target") if isinstance(manifest, Mapping) else None
    if not isinstance(course, Mapping) or not isinstance(target, Mapping):
        raise CourseRegenerationError("course identity has no course/target records")
    course_id = course.get("id")
    course_title = course.get("title")
    locale = course.get("language", course.get("locale"))
    name = target.get("name")
    version = target.get("version")
    kind = target.get("kind")
    if not all(
        isinstance(value, str) and value
        for value in (course_id, course_title, locale, name, version, kind)
    ):
        raise CourseRegenerationError("course identity is incomplete")
    if locale not in {"zh-CN", "en"}:
        raise CourseRegenerationError("course locale must be zh-CN or en")
    track = target.get("track")
    if track is not None and (not isinstance(track, str) or not track):
        raise CourseRegenerationError(
            "course target track must be a non-empty string or null"
        )
    return {
        "course_id": course_id,
        "locale": locale,
        "target": {
            "name": name,
            "kind": kind,
            "version": version,
            "track": track or None,
        },
    }


def _route_intent(
    root: Path, *, require_regeneration_metadata: bool = False
) -> dict[str, str | None]:
    """Recover locked route intent from trusted metadata or canonical source."""

    source = _read_json(
        _control_path(root, SOURCE_PATH / "course.json", "canonical source"),
        "canonical course source",
    )
    course_id = source.get("id")
    course_title = source.get("title")
    route_id: str | None = None
    audience = source.get("audience")
    if isinstance(audience, Mapping):
        profile = audience.get("prerequisite_profile")
        if isinstance(profile, Mapping) and isinstance(profile.get("route_id"), str):
            route_id = str(profile["route_id"])

    try:
        provenance = load_generation_provenance(root, verify_hashes=True)
        if provenance.get("schema_version") != 2:
            raise ProvenanceError(
                "legacy provenance cannot authenticate regeneration metadata"
            )
        metadata = load_regeneration_metadata(root)
    except ProvenanceError as error:
        if require_regeneration_metadata:
            raise CourseRegenerationError(
                f"invalid course regeneration metadata: {error}"
            ) from error
        metadata = None
    if metadata is not None:
        intent = metadata["route_intent"]
        metadata_course_id = str(intent["course_id"])
        if isinstance(course_id, str) and metadata_course_id != course_id:
            raise CourseRegenerationError(
                "regeneration sidecar course id does not match canonical source"
            )
        return {
            "course_id": metadata_course_id,
            "course_title": str(intent["course_title"]),
            "route_id": (
                str(intent["route_id"]) if intent["route_id"] is not None else None
            ),
            "route_title": (
                str(intent["route_title"])
                if intent["route_title"] is not None
                else None
            ),
        }

    return {
        "course_id": str(course_id) if isinstance(course_id, str) else None,
        "course_title": (
            str(course_title) if isinstance(course_title, str) else None
        ),
        "route_id": route_id,
        "route_title": None,
    }


def _route_intent_changed(
    locked: Mapping[str, str | None],
    candidate: Mapping[str, str | None],
) -> bool:
    """Treat every recoverable old route-intent field as immutable."""

    return any(
        value is not None and candidate.get(field) != value
        for field, value in locked.items()
    )


def _readiness_strategy(root: Path, baseline: CourseBaseline) -> dict[str, str]:
    if baseline.schema_version < 2:
        return {
            "mode": "full_readiness",
            "reason": "legacy provenance cannot prove reusable readiness evidence",
        }
    try:
        provenance = load_generation_provenance(root, verify_hashes=True)
        metadata = load_regeneration_metadata(root)
        if (
            provenance.get("schema_version") != 2
            or metadata.get("route_contract") is None
            or metadata.get("readiness_projection") is None
        ):
            raise ProvenanceError("trusted readiness route is unavailable")
    except ProvenanceError as error:
        return {
            "mode": "full_readiness",
            "reason": str(error),
        }
    return {
        "mode": "readiness_command_required",
        "reason": (
            "research the current route, then run the readiness subcommand to "
            "reuse only unchanged capability verdicts"
        ),
    }


def _finalize_scan_records(
    raw_records: list[
        tuple[str, str, bytes, tuple[int, int] | None, int]
    ],
) -> list[tuple[str, str, bytes]]:
    """Add hardlink topology to raw records using the canonical tree format."""

    hardlink_groups: dict[tuple[int, int], list[str]] = {}
    for relative, kind, _, inode, link_count in raw_records:
        if kind == "file" and inode is not None and link_count > 1:
            hardlink_groups.setdefault(inode, []).append(relative)
    records: list[tuple[str, str, bytes]] = []
    for relative, kind, value, inode, link_count in raw_records:
        if kind == "file" and inode is not None and link_count > 1:
            topology = json.dumps(
                {
                    "paths": sorted(hardlink_groups[inode]),
                    "link_count": link_count,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            value += b"\0hardlink\0" + hashlib.sha256(topology).digest()
        records.append((relative, kind, value))
    return records


def _scan_tree(root: Path) -> list[tuple[str, str, bytes]]:
    raw_records: list[
        tuple[str, str, bytes, tuple[int, int] | None, int]
    ] = []

    def visit(directory: Path, prefix: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise CourseRegenerationError(f"cannot scan course tree: {error}") from error
        for entry in entries:
            relative_path = prefix / entry.name
            relative = relative_path.as_posix()
            try:
                stat_result = entry.stat(follow_symlinks=False)
                mode = (stat_result.st_mode & 0o7777).to_bytes(2, "big")
                if entry.is_symlink():
                    raw_records.append(
                        (
                            relative,
                            "symlink",
                            mode
                            + os.readlink(entry.path).encode(
                                "utf-8",
                                errors="surrogateescape",
                            ),
                            None,
                            stat_result.st_nlink,
                        )
                    )
                elif entry.is_dir(follow_symlinks=False):
                    raw_records.append(
                        (
                            relative,
                            "directory",
                            mode,
                            None,
                            stat_result.st_nlink,
                        )
                    )
                    visit(Path(entry.path), relative_path)
                elif entry.is_file(follow_symlinks=False):
                    digest = hashlib.sha256()
                    with open(entry.path, "rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(chunk)
                    raw_records.append(
                        (
                            relative,
                            "file",
                            mode + digest.digest(),
                            (stat_result.st_dev, stat_result.st_ino),
                            stat_result.st_nlink,
                        )
                    )
                else:
                    raise CourseRegenerationError(
                        f"course tree contains a special file: {relative}"
                    )
            except OSError as error:
                raise CourseRegenerationError(
                    f"cannot inspect course path {relative}: {error}"
                ) from error

    visit(root, PurePosixPath())
    return _finalize_scan_records(raw_records)


def _snapshot_records(records: list[tuple[str, str, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative, kind, value in records:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(kind.encode("ascii"))
        digest.update(b"\0")
        digest.update(value)
        digest.update(b"\0")
    return digest.hexdigest()


def _snapshot(root: Path) -> str:
    return _snapshot_records(_scan_tree(root))


def _v4_course_root(path: Path) -> Path:
    supplied = path.expanduser()
    if supplied.is_symlink():
        raise CourseRegenerationError("v4 course path cannot be a symlink")
    try:
        root = supplied.resolve(strict=True)
    except OSError as error:
        raise CourseRegenerationError(f"v4 course path is unavailable: {error}") from error
    if not root.is_dir():
        raise CourseRegenerationError(f"v4 course path is not a directory: {root}")
    course_toml = _control_path(root, Path("course.toml"), "v4 course")
    public_binding = _control_path(
        root, Path(".coursekit/course.json"), "v4 course"
    )
    if not course_toml.is_file() or not public_binding.is_file():
        raise CourseRegenerationError(
            "v4 course is missing course.toml or .coursekit/course.json"
        )
    try:
        metadata = tomllib.loads(course_toml.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CourseRegenerationError(f"v4 course.toml is invalid: {error}") from error
    if metadata.get("schema_version") != 4:
        raise CourseRegenerationError("chapter regeneration requires schema v4")
    return root


def _sha256_file(path: Path, *, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise CourseRegenerationError(f"{label} is missing or unsafe")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v4_chapter_artifact_digest(
    learner: Path,
    author: Path,
    chapter: Mapping[str, Any],
) -> str:
    digest = hashlib.sha256()
    chapter_id = str(chapter["id"])
    roots: list[tuple[str, Path]] = [
        (
            f"learner/chapters/{chapter_id}",
            learner / "chapters" / chapter_id,
        ),
        (f"learner/tests/{chapter_id}", learner / "tests" / chapter_id),
        (f"learner/examples/{chapter_id}", learner / "examples" / chapter_id),
        (
            f"author/tests/hidden/{chapter_id}",
            author / "tests" / "hidden" / chapter_id,
        ),
    ]
    for owned in chapter.get("owned_paths", []):
        if not isinstance(owned, str):
            raise CourseRegenerationError(
                f"{chapter_id}.owned_paths must contain text paths"
            )
        roots.extend(
            (
                (f"learner/{owned}", learner / owned),
                (f"author/solution/{owned}", author / "solution" / owned),
            )
        )
    for logical_path, root in roots:
        digest.update(logical_path.encode("utf-8"))
        digest.update(b"\0")
        if not root.exists():
            digest.update(b"missing\0")
            continue
        if root.is_symlink():
            raise CourseRegenerationError(
                f"{chapter_id} artifact cannot be a symlink: {root}"
            )
        if root.is_file():
            records = [(root.name, "file", root.read_bytes())]
        elif root.is_dir():
            records = _scan_tree(root)
        else:
            raise CourseRegenerationError(
                f"{chapter_id} artifact is not a regular path: {root}"
            )
        for relative, kind, value in records:
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(kind.encode("ascii"))
            digest.update(b"\0")
            digest.update(value)
            digest.update(b"\0")
    return digest.hexdigest()


def _v4_package_selector(
    selector: Any,
    *,
    prefix: str,
    label: str,
) -> str:
    if not isinstance(selector, str):
        raise CourseRegenerationError(f"{label} must be text")
    path, separator, node = selector.partition("::")
    if not separator or not node or not path.startswith(prefix):
        raise CourseRegenerationError(
            f"{label} is not a projected schema-v4 selector"
        )
    package_path = path.removeprefix(prefix)
    if (
        not package_path
        or package_path.startswith("/")
        or ".." in PurePosixPath(package_path).parts
    ):
        raise CourseRegenerationError(f"{label} has an unsafe package path")
    return f"{package_path}::{node}"


def _v4_package_task_contract(
    chapter_id: str,
    task: Mapping[str, Any],
    hidden_selectors: list[Any],
) -> dict[str, Any]:
    required = (
        "id",
        "title",
        "file",
        "symbol",
        "prompt",
        "points",
        "timeout_seconds",
        "public_tests",
    )
    if any(key not in task for key in required):
        raise CourseRegenerationError(
            f"{chapter_id} contains an incomplete projected task contract"
        )
    public = task.get("public_tests")
    if not isinstance(public, list) or not public:
        raise CourseRegenerationError(
            f"{chapter_id}.{task.get('id')} has no public selectors"
        )
    if not hidden_selectors:
        raise CourseRegenerationError(
            f"{chapter_id}.{task.get('id')} has no hidden selectors"
        )
    result = {
        key: copy.deepcopy(task[key])
        for key in (
            "id",
            "title",
            "file",
            "symbol",
            "prompt",
            "points",
            "timeout_seconds",
        )
    }
    result["public_tests"] = [
        _v4_package_selector(
            selector,
            prefix=f"tests/{chapter_id}/",
            label=f"{chapter_id}.{task.get('id')} public selector",
        )
        for selector in public
    ]
    result["hidden_tests"] = [
        _v4_package_selector(
            selector,
            prefix=f"tests/hidden/{chapter_id}/",
            label=f"{chapter_id}.{task.get('id')} hidden selector",
        )
        for selector in hidden_selectors
    ]
    example_fields = {
        key: task.get(f"example_{key}")
        for key in ("input", "output", "explanation")
        if f"example_{key}" in task
    }
    if example_fields:
        if set(example_fields) != {"input", "output", "explanation"}:
            raise CourseRegenerationError(
                f"{chapter_id}.{task.get('id')} has an incomplete example"
            )
        result["example"] = example_fields
    return result


def _v4_locked_chapter(
    learner: Path,
    author: Path,
    chapters: list[Any],
    selected_index: int,
) -> dict[str, Any]:
    selected = chapters[selected_index]
    if not isinstance(selected, Mapping):
        raise CourseRegenerationError("schema-v4 chapter metadata is invalid")
    chapter_id = str(selected.get("id"))
    author_binding = _read_json(author / "author.json", "v4 author binding")
    hidden_by_task = {
        (str(task.get("chapter_id")), str(task.get("task_id"))): list(
            task.get("hidden_tests", [])
        )
        for task in author_binding.get("tasks", [])
        if isinstance(task, Mapping)
        and isinstance(task.get("hidden_tests"), list)
    }
    task_contracts: list[dict[str, Any]] = []
    tasks = selected.get("tasks", [])
    if not isinstance(tasks, list):
        raise CourseRegenerationError(
            f"{chapter_id} contains an invalid task collection"
        )
    for task in tasks:
        if not isinstance(task, Mapping):
            raise CourseRegenerationError(
                f"{chapter_id} contains an invalid task contract"
            )
        task_id = str(task.get("id"))
        hidden = hidden_by_task.get((chapter_id, task_id))
        if not hidden:
            raise CourseRegenerationError(
                f"author sibling has no hidden selectors for {task_id}"
            )
        task_contracts.append(
            _v4_package_task_contract(chapter_id, task, hidden)
        )
    sources = {
        str(source.get("id")): dict(source)
        for source in _v4_metadata(learner).get("sources", [])
        if isinstance(source, Mapping) and isinstance(source.get("id"), str)
    }
    source_ids = selected.get("source_ids", [])
    if not isinstance(source_ids, list):
        raise CourseRegenerationError(
            f"{chapter_id} contains invalid official source ids"
        )
    official_sources = [
        sources[source_id]
        for source_id in source_ids
        if isinstance(source_id, str) and source_id in sources
    ]
    if len(official_sources) != len(source_ids):
        raise CourseRegenerationError(
            f"{chapter_id} references an unavailable official source"
        )
    return {
        "id": selected.get("id"),
        "title": selected.get("title"),
        "kind": selected.get("kind"),
        "depends_on": selected.get("depends_on"),
        "study_minutes": {
            "min": selected.get("study_min"),
            "max": selected.get("study_max"),
            **(
                {"reason": selected["study_reason"]}
                if selected.get("study_reason") is not None
                else {}
            ),
        },
        "official_sources": official_sources,
        "task_contracts": task_contracts,
        "owned_paths": list(selected.get("owned_paths", [])),
        "previous_handoff": (
            {
                "id": chapters[selected_index - 1]["id"],
                "title": chapters[selected_index - 1]["title"],
            }
            if selected_index > 0
            else None
        ),
        "next_handoff": (
            {
                "id": chapters[selected_index + 1]["id"],
                "title": chapters[selected_index + 1]["title"],
            }
            if selected_index + 1 < len(chapters)
            else None
        ),
    }


def plan_v4_chapter_regeneration(
    course: Path,
    *,
    chapter_id: str,
    reason: str,
) -> dict[str, Any]:
    """Create a prompt-safe request that recalls only one schema-v4 Writer."""

    live = _v4_course_root(course)
    if not reason.strip():
        raise CourseRegenerationError("--reason must be non-empty")
    author = live.with_name(f"{live.name}-author")
    if author.is_symlink() or not author.is_dir():
        raise CourseRegenerationError("v4 author sibling is missing or unsafe")
    try:
        metadata = tomllib.loads(
            (live / "course.toml").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CourseRegenerationError(f"v4 course.toml is invalid: {error}") from error
    chapters = metadata.get("chapters")
    if not isinstance(chapters, list):
        raise CourseRegenerationError("v4 course.toml has no chapter route")
    selected_index = next(
        (
            index
            for index, chapter in enumerate(chapters)
            if isinstance(chapter, dict) and chapter.get("id") == chapter_id
        ),
        None,
    )
    if selected_index is None:
        raise CourseRegenerationError(f"unknown schema-v4 chapter: {chapter_id}")
    selected = chapters[selected_index]
    if not isinstance(selected, Mapping):
        raise CourseRegenerationError(f"invalid schema-v4 chapter: {chapter_id}")
    locked_chapter = _v4_locked_chapter(
        live,
        author,
        chapters,
        selected_index,
    )
    preserved = [
        {
            "chapter_id": str(chapter["id"]),
            "artifact_sha256": _v4_chapter_artifact_digest(
                live, author, chapter
            ),
        }
        for chapter in chapters
        if isinstance(chapter, Mapping) and chapter.get("id") != chapter_id
    ]
    return {
        "schema_version": 1,
        "mode": "chapter-regeneration-v4",
        "course": str(live),
        "author": str(author),
        "chapter_id": chapter_id,
        "reason": reason.strip(),
        "live_course_contract_sha256": _v4_generation(live)[
            "course_contract_sha256"
        ],
        "course_identity": {
            "course_id": metadata.get("course_id"),
            "curriculum_id": metadata.get("curriculum_id"),
            "language": metadata.get("language"),
            "target": metadata.get("target"),
            "capstone": metadata.get("capstone"),
        },
        "locked_chapter": locked_chapter,
        "depth_brief_requirement": {
            "required": True,
            "source": "new-parent-agent-prompt-context",
            "reuse_from_generated_course": False,
            "persist_in_generated_course": False,
            "fields": list(V4_DEPTH_BRIEF_FIELDS),
        },
        "preserve_chapters": preserved,
        "writer_calls": 1,
        "mechanical_repair_limit": 1,
        "include_previous_tutorial": False,
        "include_other_chapter_prose": False,
    }


def _looks_like_v4_course(path: Path) -> bool:
    """Route a generated root without weakening either version's validator."""

    supplied = path.expanduser()
    if supplied.is_symlink() or not supplied.is_dir():
        return False
    course_toml = supplied / "course.toml"
    return course_toml.exists() or course_toml.is_symlink()


def _v4_metadata(root: Path) -> dict[str, Any]:
    course_toml = _control_path(root, Path("course.toml"), "v4 course")
    try:
        value = tomllib.loads(course_toml.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CourseRegenerationError(f"v4 course.toml is invalid: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 4:
        raise CourseRegenerationError("v4 course.toml schema_version must be 4")
    return value


def _v4_author_root(learner: Path, *, role: str) -> Path:
    supplied = learner.with_name(f"{learner.name}-author")
    if supplied.is_symlink():
        raise CourseRegenerationError(f"{role} v4 author path cannot be a symlink")
    try:
        root = supplied.resolve(strict=True)
    except OSError as error:
        raise CourseRegenerationError(
            f"{role} v4 author path is unavailable: {error}"
        ) from error
    if not root.is_dir() or root.parent != learner.parent:
        raise CourseRegenerationError(
            f"{role} v4 author must be a regular sibling directory"
        )
    for relative in ("author.json", "quiz-answers.json", "verification.json"):
        path = _control_path(root, Path(relative), f"{role} v4 author")
        if not path.is_file():
            raise CourseRegenerationError(
                f"{role} v4 author is missing {relative}"
            )
    return root


def _v4_pair(path: Path, *, role: str) -> tuple[Path, Path]:
    learner = _v4_course_root(path)
    return learner, _v4_author_root(learner, role=role)


def _v4_candidate_pair(
    candidate: Path,
    live: Path,
    live_author: Path,
) -> tuple[Path, Path]:
    learner, author = _v4_pair(candidate, role="candidate")
    roots = {live, live_author, learner, author}
    if (
        len(roots) != 4
        or learner.parent != live.parent
        or author.parent != live.parent
    ):
        raise CourseRegenerationError(
            "v4 candidate learner and author must be distinct siblings of the live pair"
        )
    return learner, author


def _v4_generation(root: Path) -> dict[str, Any]:
    generation = _read_json(
        _control_path(
            root,
            Path(".coursekit/generation.json"),
            "v4 generation metadata",
        ),
        "v4 generation metadata",
    )
    if set(generation) != V4_GENERATION_FIELDS:
        raise CourseRegenerationError(
            "v4 generation metadata has an invalid shape"
        )
    if (
        generation.get("schema_version") != 1
        or generation.get("course_schema_version") != 4
    ):
        raise CourseRegenerationError(
            "v4 generation metadata has an unsupported schema"
        )
    for field in (
        "content_contract_sha256",
        "runtime_contract_sha256",
        "course_contract_sha256",
    ):
        value = generation.get(field)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            raise CourseRegenerationError(
                f"v4 generation metadata has an invalid {field}"
            )
    version = generation.get("plugin_version")
    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
        raise CourseRegenerationError(
            "v4 generation metadata has an invalid plugin_version"
        )
    metadata = _v4_metadata(root)
    public = _read_json(
        _control_path(
            root,
            Path(".coursekit/course.json"),
            "v4 public binding",
        ),
        "v4 public binding",
    )
    if (
        generation.get("course_id") != metadata.get("course_id")
        or generation.get("curriculum_id") != metadata.get("curriculum_id")
        or generation.get("course_contract_sha256")
        != public.get("course_contract_sha256")
    ):
        raise CourseRegenerationError(
            "v4 generation metadata does not match the public course binding"
        )
    return generation


def _v4_identity(root: Path) -> dict[str, Any]:
    metadata = _v4_metadata(root)
    target = metadata.get("target")
    if not isinstance(target, Mapping):
        raise CourseRegenerationError("v4 course identity has no target")
    chapters = metadata.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise CourseRegenerationError("v4 course identity has no chapter route")
    route: list[dict[str, Any]] = []
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            raise CourseRegenerationError(
                "v4 course identity has an invalid chapter route"
            )
        chapter_id = chapter.get("id")
        kind = chapter.get("kind")
        depends_on = chapter.get("depends_on")
        if (
            not isinstance(chapter_id, str)
            or not isinstance(kind, str)
            or depends_on is not None
            and not isinstance(depends_on, str)
        ):
            raise CourseRegenerationError(
                "v4 course identity has an incomplete chapter route"
            )
        route.append(
            {
                "id": chapter_id,
                "kind": kind,
                "depends_on": depends_on,
            }
        )
    identity = {
        "course_id": metadata.get("course_id"),
        "curriculum_id": metadata.get("curriculum_id"),
        "language": metadata.get("language"),
        "target": dict(target),
        "route": route,
    }
    if (
        not isinstance(identity["course_id"], str)
        or not isinstance(identity["curriculum_id"], str)
        or identity["language"] not in {"zh-CN", "en"}
    ):
        raise CourseRegenerationError("v4 course identity is incomplete")
    return identity


def _legacy_course_schema_version(root: Path) -> int:
    source = _read_json(
        _control_path(root, SOURCE_PATH / "course.json", "legacy canonical source"),
        "legacy canonical course source",
    )
    schema_version = source.get("schema_version")
    if type(schema_version) is not int or schema_version not in {2, 3}:
        raise CourseRegenerationError(
            "explicit v4 migration requires a schema-v2 or schema-v3 course"
        )
    return schema_version


def _legacy_migration_identity(root: Path) -> dict[str, Any]:
    identity = _identity(root)
    return {
        "course_id": identity["course_id"],
        "language": identity["locale"],
        "target": dict(identity["target"]),
    }


def _v4_migration_identity(root: Path) -> dict[str, Any]:
    identity = _v4_identity(root)
    target = identity["target"]
    required = (
        identity["course_id"],
        identity["language"],
        target.get("name"),
        target.get("kind"),
        target.get("version"),
    )
    if not all(isinstance(value, str) and value for value in required):
        raise CourseRegenerationError(
            "v4 migration candidate has an incomplete course/target identity"
        )
    track = target.get("track")
    if track is not None and (not isinstance(track, str) or not track):
        raise CourseRegenerationError(
            "v4 migration candidate target track must be text or absent"
        )
    return {
        "course_id": identity["course_id"],
        "language": identity["language"],
        "target": {
            "name": target["name"],
            "kind": target["kind"],
            "version": target["version"],
            "track": track,
        },
    }


def _migration_identity_mismatches(
    legacy: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> list[str]:
    fields = (
        ("course_id", legacy.get("course_id"), candidate.get("course_id")),
        ("language", legacy.get("language"), candidate.get("language")),
    )
    mismatches = [
        field
        for field, old_value, new_value in fields
        if old_value != new_value
    ]
    legacy_target = legacy.get("target")
    candidate_target = candidate.get("target")
    if not isinstance(legacy_target, Mapping) or not isinstance(
        candidate_target, Mapping
    ):
        return [*mismatches, "target"]
    mismatches.extend(
        f"target.{field}"
        for field in ("name", "kind", "version", "track")
        if legacy_target.get(field) != candidate_target.get(field)
    )
    return mismatches


def _baseline_record(baseline: CourseBaseline) -> dict[str, Any]:
    return {
        "kind": baseline.kind,
        "schema_version": baseline.schema_version,
        "plugin_version": baseline.plugin_version,
        "authoring_contract_sha256": baseline.authoring_contract_sha256,
    }


def _v4_receipt_summary(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "receipt_sha256": receipt["receipt_sha256"],
        "learner_tree_sha256": receipt["learner_tree_sha256"],
        "author_tree_sha256": receipt["author_tree_sha256"],
        "runtime_sha256": receipt["runtime_sha256"],
        "verifier_sha256": receipt["verifier_sha256"],
    }


def _legacy_to_v4_migration_record(
    live: Path,
    candidate: Path,
) -> dict[str, Any]:
    candidate_identity = _v4_identity(candidate)
    return {
        "kind": "explicit-schema-v2-v3-to-v4",
        "source_schema_version": _legacy_course_schema_version(live),
        "target_schema_version": 4,
        "identity_lock": [
            "course_id",
            "language",
            "target.name",
            "target.kind",
            "target.version",
            "target.track",
        ],
        "legacy_route_intent": _route_intent(
            live,
            require_regeneration_metadata=False,
        ),
        "candidate_curriculum_id": candidate_identity["curriculum_id"],
        "candidate_route": candidate_identity["route"],
        "curriculum_id_policy": "new-v4-curriculum-id-allowed",
        "route_semantics": (
            "legacy route prose is not automatically comparable; course and "
            "target identity are locked and the new v4 route is receipt-bound"
        ),
    }


def _v4_content_metadata(root: Path) -> dict[str, Any]:
    """Project author-controlled semantics without exporter-only TOML details."""

    metadata = _v4_metadata(root)
    chapters: list[dict[str, Any]] = []
    for raw_chapter in metadata["chapters"]:
        chapter = dict(raw_chapter)
        tasks: list[dict[str, Any]] = []
        for raw_task in chapter.get("tasks", []):
            task = dict(raw_task)
            tasks.append(
                {
                    key: task[key]
                    for key in (
                        "id",
                        "title",
                        "file",
                        "symbol",
                        "prompt",
                        "points",
                        "timeout_seconds",
                        "example_input",
                        "example_output",
                        "example_explanation",
                    )
                    if key in task
                }
            )
        chapters.append(
            {
                key: chapter[key]
                for key in (
                    "id",
                    "title",
                    "kind",
                    "depends_on",
                    "study_min",
                    "study_max",
                    "study_reason",
                    "source_ids",
                )
                if key in chapter
            }
            | {"tasks": tasks}
        )
    return {
        key: metadata[key]
        for key in (
            "course_id",
            "curriculum_id",
            "title",
            "description",
            "language",
            "capstone",
            "target",
            "sources",
        )
        if key in metadata
    } | {"chapters": chapters}


def _v4_digest_selected_tree(
    learner: Path,
    author: Path,
) -> str:
    digest = hashlib.sha256()
    metadata = _canonical_digest(_v4_content_metadata(learner)).encode("ascii")
    digest.update(b"course-metadata\0")
    digest.update(metadata)
    digest.update(b"\0")
    selected = (
        ("learner", learner, ("chapters", "src", "tests", "examples")),
        (
            "author",
            author,
            ("quiz-answers.json", "solution", "tests/hidden"),
        ),
    )
    for role, root, relatives in selected:
        for raw_relative in relatives:
            relative = Path(raw_relative)
            path = _control_path(root, relative, f"v4 {role} content")
            if not path.exists():
                continue
            if path.is_symlink():
                raise CourseRegenerationError(
                    f"v4 {role} content cannot be a symlink: {raw_relative}"
                )
            records = (
                [(path.name, "file", path.read_bytes())]
                if path.is_file()
                else _scan_tree(path)
                if path.is_dir()
                else []
            )
            if not records:
                if not path.is_dir():
                    raise CourseRegenerationError(
                        f"v4 {role} content is not regular: {raw_relative}"
                    )
                records = [(".", "directory", b"")]
            digest.update(role.encode("ascii"))
            digest.update(b"\0")
            digest.update(raw_relative.encode("utf-8"))
            digest.update(b"\0")
            for item, kind, value in records:
                digest.update(item.encode("utf-8"))
                digest.update(b"\0")
                digest.update(kind.encode("ascii"))
                digest.update(b"\0")
                digest.update(value)
                digest.update(b"\0")
    return digest.hexdigest()


def _v4_current_contracts() -> dict[str, str]:
    content = v4_content_contract_sha256()
    runtime = v4_runtime_contract_sha256()
    if (
        SHA256_RE.fullmatch(content) is None
        or SHA256_RE.fullmatch(runtime) is None
    ):
        raise CourseRegenerationError(
            "the installed Skill returned invalid v4 contract fingerprints"
        )
    return {
        "plugin_version": _plugin_version(),
        "content_contract_sha256": content,
        "runtime_contract_sha256": runtime,
    }


def _v4_regeneration_state(
    learner: Path,
    author: Path,
    generation: Mapping[str, Any],
    current: Mapping[str, str],
) -> tuple[str, str, str, int, list[str]]:
    generated_version = str(generation["plugin_version"])
    if _version_core(generated_version) > _version_core(current["plugin_version"]):
        raise CourseRegenerationError(
            "v4 course was generated by a newer plugin version; downgrade is refused"
        )
    if (
        generation["content_contract_sha256"]
        != current["content_contract_sha256"]
    ):
        chapter_ids = [
            str(chapter["id"])
            for chapter in _v4_metadata(learner)["chapters"]
            if isinstance(chapter, Mapping)
            and isinstance(chapter.get("id"), str)
        ]
        if not chapter_ids:
            raise CourseRegenerationError(
                "v4 content regeneration has no chapter Writers to recall"
            )
        return (
            "needs_content_regeneration",
            "content contract changed",
            "regenerate-content",
            len(chapter_ids),
            chapter_ids,
        )
    if (
        generation["runtime_contract_sha256"]
        != current["runtime_contract_sha256"]
        or generated_version != current["plugin_version"]
    ):
        return (
            "needs_reexport_revalidation",
            "runtime, exporter, verifier, or plugin version changed",
            "re-export/revalidate",
            0,
            [],
        )
    try:
        validate_v4_receipt(learner, author_root=author)
    except V4VerificationError as error:
        return (
            "needs_revalidation",
            f"verification receipt is stale or missing: {error}",
            "revalidate",
            0,
            [],
        )
    return (
        "up_to_date",
        "v4 contracts and receipt are current",
        "none",
        0,
        [],
    )


def _rollback_path(live: Path, *snapshots: str) -> Path:
    if not snapshots or any(SHA256_RE.fullmatch(value) is None for value in snapshots):
        raise CourseRegenerationError(
            "cannot reserve a rollback path without valid snapshots"
        )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = "-".join(snapshot[:8] for snapshot in snapshots)
    return live.with_name(
        f".{live.name}.coursekit-rollback-{timestamp}-{suffix}"
    )


def _tree_state(root: Path) -> dict[str, tuple[str, bytes]]:
    return {
        relative: (kind, value)
        for relative, kind, value in _scan_tree(root)
    }


def _externally_hardlinked_files(
    root: Path,
    records: list[tuple[str, str, bytes]] | None = None,
) -> list[str]:
    groups: dict[tuple[int, int], list[str]] = {}
    link_counts: dict[tuple[int, int], int] = {}
    for relative, kind, _ in records if records is not None else _scan_tree(root):
        if kind != "file":
            continue
        try:
            stat_result = (root / relative).stat(follow_symlinks=False)
        except OSError as error:
            raise CourseRegenerationError(
                f"cannot inspect candidate hard links at {relative}: {error}"
            ) from error
        if stat_result.st_nlink <= 1:
            continue
        inode = (stat_result.st_dev, stat_result.st_ino)
        groups.setdefault(inode, []).append(relative)
        link_counts[inode] = stat_result.st_nlink
    return sorted(
        relative
        for inode, paths in groups.items()
        if len(paths) != link_counts[inode]
        for relative in paths
    )


def _unexpected_verifier_changes(
    before: Mapping[str, tuple[str, bytes]],
    after: Mapping[str, tuple[str, bytes]],
) -> list[str]:
    changed = sorted(
        relative
        for relative in set(before) | set(after)
        if before.get(relative) != after.get(relative)
    )
    return [
        relative
        for relative in changed
        if not (
            relative == ".git/index"
            or (
                ".git" not in PurePosixPath(relative).parts
                and _material_artifact_ignored(PurePosixPath(relative))
            )
        )
    ]


def _hash_source(root: Path) -> str:
    source = root / SOURCE_PATH
    digest = hashlib.sha256()
    for relative, kind, value in _scan_tree(source):
        if kind == "symlink":
            raise CourseRegenerationError(
                f"canonical source cannot contain symlinks: {relative}"
            )
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(kind.encode("ascii"))
        digest.update(b"\0")
        digest.update(value)
        digest.update(b"\0")
    return digest.hexdigest()


def _material_artifact_ignored(path: PurePosixPath) -> bool:
    return (
        any(
            part in MATERIAL_IGNORED_NAMES or part.endswith(".egg-info")
            for part in path.parts
        )
        or path.suffix in MATERIAL_IGNORED_SUFFIXES
    )


def _learner_facing(relative: str) -> bool:
    path = PurePosixPath(relative)
    parts = path.parts
    if _material_artifact_ignored(path):
        return False
    if len(parts) >= 5 and parts[:4] == ("platform", "course", "source", "labs"):
        if path.name in {"tutorial.md", "lesson.json", "quiz.json"}:
            return True
        return bool(
            len(parts) >= 7
            and (
                parts[5] == "starter"
                or parts[5:7] == ("tests", "public")
            )
        )
    if len(parts) >= 5 and parts[:4] == (
        "platform",
        "course",
        "source",
        "preparatory_units",
    ):
        return path.name in {"tutorial.md", "lesson.json", "quiz.json"}
    prefixes = (
        ("platform", "course", "starter"),
        ("platform", "course", "tests", "public"),
    )
    if any(parts[: len(prefix)] == prefix for prefix in prefixes):
        return True
    # The live labs/ tree is learner-editable. It cannot prove that the current
    # authoring capability produced different course content.
    return False


def _learner_projection(root: Path) -> dict[str, str]:
    projection: dict[str, str] = {}
    for relative, kind, _ in _scan_tree(root):
        if kind == "file" and _learner_facing(relative):
            try:
                value = (root / relative).read_bytes()
            except OSError as error:
                raise CourseRegenerationError(
                    f"cannot read learner-facing course path {relative}: {error}"
                ) from error
            projection[relative] = _normalized_learner_content(relative, value).hex()
    return projection


def _normalized_learner_content(relative: str, value: bytes) -> bytes:
    """Ignore formatting-only churn while retaining authored semantic changes."""

    suffix = PurePosixPath(relative).suffix.casefold()
    if suffix == ".json":
        try:
            parsed = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return value
        return json.dumps(
            parsed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    try:
        text = value.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        return value
    if suffix == ".md":
        segments: list[Any] = []
        prose: list[str] = []
        fenced: list[str] = []
        fence_marker: str | None = None

        def normalize_inline_lines(lines: list[str]) -> list[list[str]]:
            tokens: list[list[str]] = []
            for index, raw_line in enumerate(lines):
                trailing = re.search(r"[ \t]+$", raw_line)
                trailing_text = trailing.group(0) if trailing is not None else ""
                hard_break = len(trailing_text.replace("\t", "  ")) >= 2
                line = (
                    raw_line[: -len(trailing_text)]
                    if trailing_text
                    else raw_line
                )
                position = 0
                while position < len(line):
                    opening = re.search(r"`+", line[position:])
                    if opening is None:
                        tokens.append(["text", line[position:]])
                        position = len(line)
                        break
                    start = position + opening.start()
                    delimiter = opening.group(0)
                    if start > position:
                        tokens.append(["text", line[position:start]])
                    closing = line.find(delimiter, start + len(delimiter))
                    if closing < 0:
                        tokens.append(["text", line[start:]])
                        position = len(line)
                        break
                    end = closing + len(delimiter)
                    tokens.append(["inline-code", line[start:end]])
                    position = end
                if not line:
                    tokens.append(["text", ""])
                if hard_break:
                    tokens.append(["hard-break", ""])
                elif index + 1 < len(lines):
                    tokens.append(["text", " "])

            canonical: list[list[str]] = []
            for kind, token in tokens:
                if kind == "text":
                    token = re.sub(r"[ \t]+", " ", token)
                    if canonical and canonical[-1][0] == "text":
                        canonical[-1][1] += token
                    else:
                        canonical.append([kind, token])
                else:
                    canonical.append([kind, token])
            if canonical and canonical[0][0] == "text":
                canonical[0][1] = canonical[0][1].lstrip()
            if canonical and canonical[-1][0] == "text":
                canonical[-1][1] = canonical[-1][1].rstrip()
            return [token for token in canonical if token[0] != "text" or token[1]]

        def flush_prose() -> None:
            paragraph: list[str] = []
            indented_code: list[str] = []

            def flush_paragraph() -> None:
                if not paragraph:
                    return
                normalized = normalize_inline_lines(paragraph)
                if normalized:
                    segments.append(["paragraph", normalized])
                paragraph.clear()

            def flush_indented_code() -> None:
                while indented_code and not indented_code[-1]:
                    indented_code.pop()
                if indented_code:
                    segments.append(["indented-code", "\n".join(indented_code)])
                indented_code.clear()

            heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
            quote_pattern = re.compile(r"^>\s?(.*)$")
            quote_blocks: dict[int, list[list[str]]] = {}
            quote_members: set[int] = set()
            quote_index = 0
            while quote_index < len(prose):
                first_quote = quote_pattern.match(prose[quote_index])
                if first_quote is None:
                    quote_index += 1
                    continue
                end = quote_index
                content: list[str] = []
                while end < len(prose):
                    quote = quote_pattern.match(prose[end])
                    if quote is None:
                        break
                    content.append(quote.group(1))
                    end += 1
                quote_blocks[quote_index] = normalize_inline_lines(
                    [" ".join(content)]
                )
                quote_members.update(range(quote_index, end))
                quote_index = end

            table_row = re.compile(r"^\s*\|?.+\|.+\|?\s*$")
            table_separator = re.compile(r"^\s*\|?\s*:?-{3,}")
            list_item_pattern = re.compile(
                r"^( {0,3})([-+*]|\d+[.)])[ \t]+(.*)$"
            )

            def thematic_break(line: str) -> bool:
                return re.fullmatch(
                    r"\s{0,3}(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})",
                    line,
                ) is not None

            def table_is_block_start(index: int) -> bool:
                if index == 0 or not prose[index - 1].strip():
                    return True
                previous = prose[index - 1]
                if (
                    heading_pattern.match(previous)
                    or quote_pattern.match(previous)
                    or thematic_break(previous)
                    or list_item_pattern.match(previous)
                ):
                    return True
                cursor = index - 2
                while cursor >= 0 and prose[cursor].strip():
                    line = prose[cursor]
                    if (
                        heading_pattern.match(line)
                        or quote_pattern.match(line)
                        or thematic_break(line)
                    ):
                        return False
                    if list_item_pattern.match(line):
                        return True
                    cursor -= 1
                return False

            table_blocks: dict[int, list[Any]] = {}
            table_members: set[int] = set()
            table_index = 0
            while table_index + 1 < len(prose):
                if not (
                    table_index not in quote_members
                    and heading_pattern.match(prose[table_index]) is None
                    and table_is_block_start(table_index)
                    and table_row.match(prose[table_index])
                    and table_separator.match(prose[table_index + 1])
                ):
                    table_index += 1
                    continue
                end = table_index + 2
                while end < len(prose) and table_row.match(prose[end]):
                    end += 1

                def table_cells(line: str) -> list[list[list[str]]]:
                    rendered = line.strip().removeprefix("|").removesuffix("|")
                    return [
                        normalize_inline_lines([cell.strip()])
                        for cell in rendered.split("|")
                    ]

                table_blocks[table_index] = [
                    table_cells(prose[table_index]),
                    [table_cells(line) for line in prose[table_index + 2 : end]],
                ]
                table_members.update(range(table_index, end))
                table_index = end

            list_blocks: dict[int, list[Any]] = {}
            list_members: set[int] = set()
            list_index = 0
            while list_index < len(prose):
                if list_index in quote_members or list_index in table_members:
                    list_index += 1
                    continue
                first_item = list_item_pattern.match(prose[list_index])
                if first_item is None:
                    list_index += 1
                    continue
                first_marker = first_item.group(2)
                ordered = first_marker[0].isdigit()
                start_number = (
                    int(re.match(r"\d+", first_marker).group(0))
                    if ordered
                    else None
                )
                items = [
                    {
                        "indent": len(first_item.group(1)),
                        "text": first_item.group(3).strip(),
                    }
                ]
                end = list_index + 1
                while end < len(prose) and prose[end].strip():
                    if end in quote_blocks or end in table_blocks:
                        break
                    if heading_pattern.match(prose[end]) or thematic_break(prose[end]):
                        break
                    next_item = list_item_pattern.match(prose[end])
                    if next_item is not None:
                        next_ordered = next_item.group(2)[0].isdigit()
                        if next_ordered != ordered:
                            break
                        items.append(
                            {
                                "indent": len(next_item.group(1)),
                                "text": next_item.group(3).strip(),
                            }
                        )
                        end += 1
                        continue
                    items[-1]["text"] = (
                        f"{items[-1]['text']} {prose[end].strip()}".strip()
                    )
                    end += 1
                list_blocks[list_index] = [
                    "ordered-list" if ordered else "unordered-list",
                    start_number,
                    [
                        [item["indent"], normalize_inline_lines([item["text"]])]
                        for item in items
                    ],
                ]
                list_members.update(range(list_index, end))
                list_index = end

            for prose_index, prose_line in enumerate(prose):
                if prose_index in quote_blocks:
                    flush_paragraph()
                    flush_indented_code()
                    segments.append(["quote", quote_blocks[prose_index]])
                    continue
                if prose_index in quote_members:
                    continue
                if prose_index in table_blocks:
                    flush_paragraph()
                    flush_indented_code()
                    segments.append(["table", table_blocks[prose_index]])
                    continue
                if prose_index in table_members:
                    continue
                if prose_index in list_blocks:
                    flush_paragraph()
                    flush_indented_code()
                    segments.append(list_blocks[prose_index])
                    continue
                if prose_index in list_members:
                    continue
                if prose_line.startswith("    ") or prose_line.startswith("\t"):
                    flush_paragraph()
                    indented_code.append(prose_line)
                    continue
                if not prose_line.strip():
                    if indented_code:
                        indented_code.append("")
                    else:
                        flush_paragraph()
                    continue
                flush_indented_code()
                if thematic_break(prose_line):
                    flush_paragraph()
                    segments.append(["thematic-break"])
                    continue
                heading = heading_pattern.match(prose_line)
                if heading is not None:
                    flush_paragraph()
                    prefix = heading.group(1)
                    content = heading.group(2)
                    normalized = normalize_inline_lines([content])
                    segments.append(["heading", prefix, normalized])
                    continue
                if prose_line.lstrip().startswith(("|", "<")):
                    flush_paragraph()
                    segments.append(["structural-line", prose_line])
                    continue
                paragraph.append(prose_line)
            flush_paragraph()
            flush_indented_code()
            prose.clear()

        for line in text.split("\n"):
            marker = re.match(r"^\s*(`{3,}|~{3,})", line)
            if fence_marker is None:
                if marker is None:
                    prose.append(line)
                    continue
                flush_prose()
                fence_marker = marker.group(1)[0]
                renderer_fence = re.fullmatch(r"```([\w+-]*)\s*", line)
                renderer_language = (
                    renderer_fence.group(1).lower()
                    if renderer_fence is not None
                    else ""
                )
                if renderer_language in {"py", "python"}:
                    renderer_language = "python"
                fenced = [
                    f"```{renderer_language}"
                    if renderer_fence is not None
                    else line.rstrip()
                ]
                continue
            fenced.append(line)
            if re.match(rf"^\s*{re.escape(fence_marker)}{{3,}}\s*$", line):
                if re.fullmatch(r"```\s*", line):
                    fenced[-1] = "```"
                segments.append(["fenced-code", "\n".join(fenced)])
                fenced = []
                fence_marker = None
        if fenced:
            segments.append(["fenced-code", "\n".join(fenced)])
        flush_prose()
        return json.dumps(
            segments,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    return text.rstrip("\n").encode("utf-8")


def _material_diff(live: Path, candidate: Path) -> dict[str, Any]:
    old = _learner_projection(live)
    new = _learner_projection(candidate)
    changed = sorted(
        relative for relative in set(old) | set(new) if old.get(relative) != new.get(relative)
    )
    return {
        "changed": bool(changed),
        "changed_paths": changed,
        "old_projection_sha256": _canonical_digest(old),
        "candidate_projection_sha256": _canonical_digest(new),
    }


def _require_canonical_git_index(root: Path) -> None:
    index = _git(root, "ls-files", "--stage", "-v", "-z")
    if index.returncode:
        raise CourseRegenerationError("candidate Git index cannot be inspected")
    invalid: list[str] = []
    for entry in index.stdout.split("\0"):
        if not entry:
            continue
        metadata, separator, path = entry.partition("\t")
        fields = metadata.split()
        if (
            not separator
            or not path
            or len(fields) != 4
            or fields[0] != "H"
            or re.fullmatch(r"[0-7]{6}", fields[1]) is None
            or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", fields[2]) is None
            or fields[3] != "0"
        ):
            invalid.append(path or entry)
    if invalid:
        raise CourseRegenerationError(
            "candidate Git index contains noncanonical flags or stages: "
            + ", ".join(invalid[:5])
        )


def _require_fresh_candidate(root: Path) -> None:
    git_dir = root / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        raise CourseRegenerationError("candidate has no fresh Git baseline")
    roots = _git(root, "rev-list", "--max-parents=0", "HEAD")
    count = _git(root, "rev-list", "--count", "HEAD")
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if roots.returncode or count.returncode or status.returncode:
        raise CourseRegenerationError("candidate Git baseline cannot be inspected")
    root_commits = [line for line in roots.stdout.splitlines() if line]
    if len(root_commits) != 1 or count.stdout.strip() != "1":
        raise CourseRegenerationError(
            "candidate must contain exactly one fresh generated commit"
        )
    message = _git(root, "show", "-s", "--format=%s", "HEAD")
    if message.returncode or message.stdout.strip() != GENERATED_BASELINE_MESSAGE:
        raise CourseRegenerationError("candidate HEAD is not a generated baseline")
    if status.stdout.strip():
        raise CourseRegenerationError("candidate Git baseline is not clean")
    _require_canonical_git_index(root)
    ignored = _git(
        root,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
    )
    if ignored.returncode:
        raise CourseRegenerationError(
            "candidate Git-ignored files cannot be inspected"
        )
    unexpected_ignored: list[str] = []
    for raw in ignored.stdout.split("\0"):
        if not raw:
            continue
        relative = PurePosixPath(raw)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not _material_artifact_ignored(relative)
        ):
            unexpected_ignored.append(raw)
    if unexpected_ignored:
        raise CourseRegenerationError(
            "candidate contains unexpected Git-ignored files: "
            + ", ".join(unexpected_ignored[:5])
        )
    progress_root = root / STATE_PATH.parent
    if progress_root.is_symlink() or progress_root.exists():
        raise CourseRegenerationError("candidate contains learner progress state")
    records = _scan_tree(root)
    hardlinked_files = _externally_hardlinked_files(root, records)
    if hardlinked_files:
        raise CourseRegenerationError(
            "candidate contains externally hard-linked files: "
            + ", ".join(hardlinked_files[:5])
        )
    ignored_symlink_roots = {".git", "node_modules", ".venv", ".uv-cache", ".next"}
    unsafe_links = [
        relative
        for relative, kind, _ in records
        if kind == "symlink"
        and not any(
            part in ignored_symlink_roots
            for part in PurePosixPath(relative).parts
        )
    ]
    if unsafe_links:
        raise CourseRegenerationError(
            "candidate contains unsafe symlinks: " + ", ".join(unsafe_links[:5])
        )


def _run_full_verifier(candidate: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix=f".{candidate.name}-coursekit-verification-", dir=candidate.parent
    ) as raw:
        report_path = Path(raw) / "report.json"
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER_PATH),
                    str(candidate),
                    "--full",
                    "--json",
                    str(report_path),
                ],
                cwd=SKILL_ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=1200,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"passed": False, "error": str(error)}
        try:
            report = _read_json(report_path, "full verification report")
        except CourseRegenerationError as error:
            return {
                "passed": False,
                "error": str(error),
                "exit_code": completed.returncode,
                "output": (completed.stdout + completed.stderr)[-4000:],
            }
        report["exit_code"] = completed.returncode
        if completed.returncode != 0:
            report["passed"] = False
        return report


def _candidate_baseline(
    candidate: Path, runtime: RuntimeContract
) -> CourseBaseline:
    baseline = _load_course_baseline(candidate, verify_hashes=True)
    if baseline.schema_version != 2:
        raise CourseRegenerationError("candidate must use provenance schema v2")
    if baseline.plugin_version != runtime.plugin_version:
        raise CourseRegenerationError(
            "candidate plugin version does not match the current Skill"
        )
    if baseline.authoring_contract_sha256 != runtime.authoring_contract_sha256:
        raise CourseRegenerationError(
            "candidate authoring fingerprint does not match the current Skill"
        )
    return baseline


def _candidate_root(candidate: Path, live: Path) -> Path:
    root = _course_root(candidate, role="candidate")
    if root == live or root.parent != live.parent:
        raise CourseRegenerationError(
            "candidate must be a distinct sibling of the live course"
        )
    return root


def _finish_plan(plan: dict[str, Any]) -> dict[str, Any]:
    result = dict(plan)
    result["plan_digest"] = _canonical_digest(plan)
    return result


def _base_plan(
    live: Path,
    baseline: CourseBaseline,
    runtime: RuntimeContract,
    status: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "command": "check",
        "status": status,
        "reason": reason,
        "course": str(live),
        "current_plugin_version": runtime.plugin_version,
        "course_plugin_version": baseline.plugin_version,
        "current_authoring_contract_sha256": runtime.authoring_contract_sha256,
        "course_authoring_contract_sha256": baseline.authoring_contract_sha256,
        "identity": _identity(live),
        "readiness_strategy": _readiness_strategy(live, baseline),
    }


def plan_readiness_reuse(course: Path, route_path: Path) -> dict[str, Any]:
    """Bind the newly researched route to reusable private readiness decisions."""

    live = _course_root(course, role="live")
    runtime = _current_runtime()
    baseline = _load_course_baseline(live)
    status, _ = _regeneration_state(baseline, runtime)
    if status != "regeneration_required":
        raise CourseRegenerationError("live course does not require regeneration")
    route = _read_json(route_path.expanduser().resolve(strict=True), "current route")
    try:
        route_contract = build_route_contract(route)
    except ReadinessValidationError as error:
        raise CourseRegenerationError(f"invalid current readiness route: {error}") from error
    if baseline.schema_version < 2 or baseline.authoring_contract_sha256 is None:
        return {
            "schema_version": 1,
            "mode": "full_readiness",
            "reason": "legacy course cannot establish trusted prior decisions",
            "route_contract_sha256": _canonical_digest(route_contract),
        }
    try:
        return trusted_readiness_reuse(live, route_contract)
    except ProvenanceError as error:
        # Missing, invalid, locally modified, or digest-mismatched private
        # metadata never becomes evidence. The safe fallback is a full fresh
        # diagnostic, surfaced as a structured mode for the Skill workflow.
        return {
            "schema_version": 1,
            "mode": "full_readiness",
            "reason": str(error),
            "route_contract_sha256": _canonical_digest(route_contract),
        }


def plan_regeneration(
    course: Path,
    *,
    candidate_course: Path | None = None,
) -> dict[str, Any]:
    live = _course_root(course, role="live")
    if candidate_course is not None and _looks_like_v4_course(candidate_course):
        return plan_legacy_to_v4_regeneration(
            live,
            candidate_course=candidate_course,
        )
    runtime = _current_runtime()
    baseline = _load_course_baseline(live)
    status, reason = _regeneration_state(baseline, runtime)
    plan = _base_plan(live, baseline, runtime, status, reason)
    if candidate_course is None:
        return _finish_plan(plan)

    candidate = _candidate_root(candidate_course, live)
    candidate_baseline = _candidate_baseline(candidate, runtime)
    live_identity = plan["identity"]
    candidate_identity = _identity(candidate)
    live_route_intent = _route_intent(
        live,
        require_regeneration_metadata=False,
    )
    candidate_route_intent = _route_intent(
        candidate,
        require_regeneration_metadata=candidate_baseline.schema_version >= 2,
    )
    live_source = _hash_source(live)
    candidate_source = _hash_source(candidate)
    material_diff = _material_diff(live, candidate)
    blockers: list[dict[str, str]] = []
    if status != "regeneration_required":
        blockers.append(
            {"code": "not-required", "message": "live course is already up to date"}
        )
    if candidate_identity != live_identity:
        blockers.append(
            {
                "code": "identity-mismatch",
                "message": "candidate changed the course locale, target, track, or course id",
            }
        )
    if _route_intent_changed(live_route_intent, candidate_route_intent):
        blockers.append(
            {
                "code": "route-intent-mismatch",
                "message": "candidate changed the locked course or route intent",
            }
        )
    if candidate_source == live_source:
        blockers.append(
            {
                "code": "canonical-source-unchanged",
                "message": "candidate canonical course source did not change",
            }
        )
    if not material_diff["changed"]:
        blockers.append(
            {
                "code": "learner-content-unchanged",
                "message": "candidate has no material learner-facing content change",
            }
        )

    candidate_was_fresh = True
    try:
        _require_fresh_candidate(candidate)
    except CourseRegenerationError as error:
        candidate_was_fresh = False
        blockers.append({"code": "candidate-not-fresh", "message": str(error)})

    if candidate_was_fresh:
        pre_verification_tree = _tree_state(candidate)
        verification = _run_full_verifier(candidate)
        if verification.get("passed") is not True:
            blockers.append(
                {
                    "code": "verification-failed",
                    "message": "candidate failed verify_learning_project.py --full",
                }
            )
        # Verification may exercise the repository but cannot leave it dirty,
        # progressed, or without its one-commit generated baseline.
        try:
            _require_fresh_candidate(candidate)
            unexpected_changes = _unexpected_verifier_changes(
                pre_verification_tree,
                _tree_state(candidate),
            )
            if unexpected_changes:
                raise CourseRegenerationError(
                    "verification created or changed non-runtime files: "
                    + ", ".join(unexpected_changes[:5])
                )
        except CourseRegenerationError as error:
            blockers.append(
                {"code": "verification-mutated-candidate", "message": str(error)}
            )
    else:
        verification = {
            "passed": False,
            "skipped": True,
            "reason": "candidate failed the pre-verification freshness gate",
        }

    live_snapshot = _snapshot(live)
    candidate_snapshot = _snapshot(candidate)
    rollback = _rollback_path(live, live_snapshot)
    if rollback.exists() or rollback.is_symlink():
        raise CourseRegenerationError(
            f"planned rollback path already exists: {rollback}"
        )
    plan.update(
        {
            "status": "blocked" if blockers else "ready",
            "candidate_course": str(candidate),
            "candidate_identity": candidate_identity,
            "route_intent": live_route_intent,
            "candidate_route_intent": candidate_route_intent,
            "live_snapshot_sha256": live_snapshot,
            "candidate_snapshot_sha256": candidate_snapshot,
            "live_canonical_source_sha256": live_source,
            "candidate_canonical_source_sha256": candidate_source,
            "material_learner_facing_diff": material_diff,
            "full_verification": verification,
            "replacement_policy": REPLACEMENT_POLICY,
            "rollback_path": str(rollback),
            "blockers": blockers,
        }
    )
    return _finish_plan(plan)


def plan_v4_regeneration(
    course: Path,
    *,
    candidate_course: Path | None = None,
) -> dict[str, Any]:
    """Classify or bind a schema-v4 learner/author replacement pair."""

    live, live_author = _v4_pair(course, role="live")
    generation = _v4_generation(live)
    current = _v4_current_contracts()
    status, reason, action, writer_calls, chapter_ids = _v4_regeneration_state(
        live,
        live_author,
        generation,
        current,
    )
    live_identity = _v4_identity(live)
    live_content = _v4_digest_selected_tree(live, live_author)
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "course_schema_version": 4,
        "command": "check",
        "status": status,
        "reason": reason,
        "required_action": action,
        "writer_calls": writer_calls,
        "chapter_ids": chapter_ids,
        "course": str(live),
        "author": str(live_author),
        "current_plugin_version": current["plugin_version"],
        "course_plugin_version": generation["plugin_version"],
        "current_content_contract_sha256": current[
            "content_contract_sha256"
        ],
        "course_content_contract_sha256": generation[
            "content_contract_sha256"
        ],
        "current_runtime_contract_sha256": current[
            "runtime_contract_sha256"
        ],
        "course_runtime_contract_sha256": generation[
            "runtime_contract_sha256"
        ],
        "identity": live_identity,
        "live_content_projection_sha256": live_content,
    }
    if candidate_course is None:
        return _finish_plan(plan)

    candidate, candidate_author = _v4_candidate_pair(
        candidate_course,
        live,
        live_author,
    )
    candidate_generation = _v4_generation(candidate)
    candidate_identity = _v4_identity(candidate)
    candidate_content = _v4_digest_selected_tree(candidate, candidate_author)
    blockers: list[dict[str, str]] = []
    if status == "up_to_date":
        blockers.append(
            {
                "code": "not-required",
                "message": "live v4 course is already up to date",
            }
        )
    if candidate_identity != live_identity:
        blockers.append(
            {
                "code": "identity-mismatch",
                "message": (
                    "candidate changed the course id, curriculum, language, "
                    "target, or chapter route"
                ),
            }
        )
    expected_generation = {
        "plugin_version": current["plugin_version"],
        "content_contract_sha256": current["content_contract_sha256"],
        "runtime_contract_sha256": current["runtime_contract_sha256"],
    }
    stale_generation = sorted(
        key
        for key, value in expected_generation.items()
        if candidate_generation.get(key) != value
    )
    if stale_generation:
        blockers.append(
            {
                "code": "candidate-contract-stale",
                "message": (
                    "candidate was not exported by the current v4 contracts: "
                    + ", ".join(stale_generation)
                ),
            }
        )
    if (
        status == "needs_content_regeneration"
        and candidate_content == live_content
    ):
        blockers.append(
            {
                "code": "content-unchanged",
                "message": (
                    "content-contract regeneration must produce a material "
                    "author-controlled content change"
                ),
            }
        )
    if status in {"needs_reexport_revalidation", "needs_revalidation"} and (
        candidate_content != live_content
    ):
        blockers.append(
            {
                "code": "unexpected-content-change",
                "message": (
                    "runtime export or revalidation cannot change Writer-owned "
                    "course content"
                ),
            }
        )

    receipt: dict[str, Any] | None
    try:
        receipt = validate_v4_receipt(
            candidate,
            author_root=candidate_author,
        )
    except V4VerificationError as error:
        receipt = None
        blockers.append(
            {
                "code": "receipt-invalid",
                "message": (
                    "candidate acceptance receipt failed offline binding "
                    f"validation: {error}"
                ),
            }
        )
    for root, label in (
        (candidate, "candidate learner"),
        (candidate_author, "candidate author"),
    ):
        external = _externally_hardlinked_files(root)
        if external:
            blockers.append(
                {
                    "code": "candidate-hardlink",
                    "message": (
                        f"{label} contains externally hard-linked files: "
                        + ", ".join(external[:5])
                    ),
                }
            )

    live_snapshot = _snapshot(live)
    live_author_snapshot = _snapshot(live_author)
    candidate_snapshot = _snapshot(candidate)
    candidate_author_snapshot = _snapshot(candidate_author)
    rollback = _rollback_path(
        live,
        live_snapshot,
        live_author_snapshot,
    )
    if rollback.exists() or rollback.is_symlink():
        raise CourseRegenerationError(
            f"planned v4 rollback path already exists: {rollback}"
        )
    plan.update(
        {
            "status": "blocked" if blockers else "ready",
            "regeneration_kind": status,
            "candidate_course": str(candidate),
            "candidate_author": str(candidate_author),
            "candidate_identity": candidate_identity,
            "candidate_content_projection_sha256": candidate_content,
            "candidate_generation": candidate_generation,
            "candidate_receipt": (
                {
                    "receipt_sha256": receipt["receipt_sha256"],
                    "learner_tree_sha256": receipt["learner_tree_sha256"],
                    "author_tree_sha256": receipt["author_tree_sha256"],
                    "runtime_sha256": receipt["runtime_sha256"],
                    "verifier_sha256": receipt["verifier_sha256"],
                }
                if receipt is not None
                else None
            ),
            "live_snapshot_sha256": live_snapshot,
            "live_author_snapshot_sha256": live_author_snapshot,
            "candidate_snapshot_sha256": candidate_snapshot,
            "candidate_author_snapshot_sha256": candidate_author_snapshot,
            "replacement_policy": REPLACEMENT_POLICY,
            "rollback_path": str(rollback),
            "blockers": blockers,
        }
    )
    return _finish_plan(plan)


def _validated_v4_chapter_request(
    live: Path,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    chapter_id = request.get("chapter_id")
    reason = request.get("reason")
    if not isinstance(chapter_id, str) or not isinstance(reason, str):
        raise CourseRegenerationError(
            "targeted regeneration request has no chapter_id or reason"
        )
    expected = plan_v4_chapter_regeneration(
        live,
        chapter_id=chapter_id,
        reason=reason,
    )
    if dict(request) != expected:
        raise CourseRegenerationError(
            "targeted regeneration request is stale, forged, or for another course"
        )
    return expected


def _v4_targeted_ephemeral(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (
        relative in V4_TARGETED_MUTABLE_PATHS
        or any(part in V4_TARGETED_EPHEMERAL_NAMES for part in path.parts)
        or path.suffix in {".pyc", ".pyo"}
    )


def _v4_targeted_allowed_path(
    relative: str,
    *,
    role: str,
    chapter_id: str,
    owned_paths: set[str],
) -> bool:
    if _v4_targeted_ephemeral(relative):
        return True
    if role == "learner":
        if relative in {
            ".coursekit/course.json",
            ".coursekit/generation.json",
            f"chapters/{chapter_id}",
            f"chapters/{chapter_id}/tutorial.md",
            f"chapters/{chapter_id}/terms.json",
            f"chapters/{chapter_id}/quiz.json",
            "examples",
            f"examples/{chapter_id}",
            f"tests/{chapter_id}",
        }:
            return True
        if relative in owned_paths:
            return True
        return (
            relative.startswith(f"examples/{chapter_id}/")
            or relative.startswith(f"tests/{chapter_id}/")
        )
    if relative in {
        "author.json",
        "quiz-answers.json",
        "verification.json",
        f"tests/hidden/{chapter_id}",
    }:
        return True
    if relative.startswith(f"tests/hidden/{chapter_id}/"):
        return True
    return relative.removeprefix("solution/") in owned_paths and relative.startswith(
        "solution/"
    )


def _v4_targeted_tree_diff(
    live: Path,
    candidate: Path,
    *,
    role: str,
    chapter_id: str,
    owned_paths: set[str],
) -> dict[str, Any]:
    before = _tree_state(live)
    after = _tree_state(candidate)
    changed = sorted(
        relative
        for relative in set(before) | set(after)
        if before.get(relative) != after.get(relative)
    )
    material = [
        relative for relative in changed if not _v4_targeted_ephemeral(relative)
    ]
    unauthorized = [
        relative
        for relative in material
        if not _v4_targeted_allowed_path(
            relative,
            role=role,
            chapter_id=chapter_id,
            owned_paths=owned_paths,
        )
    ]
    return {
        "changed": material,
        "unauthorized": unauthorized,
    }


def _v4_targeted_normalized_control(
    root: Path,
    *,
    role: str,
    relative: str,
    chapter_id: str,
) -> dict[str, Any]:
    value = copy.deepcopy(
        _read_json(
            _control_path(root, Path(relative), f"v4 {role} targeted control"),
            f"v4 {role} targeted control",
        )
    )
    if relative == ".coursekit/course.json":
        value.pop("course_contract_sha256", None)
        quiz_hashes = value.get("public_quiz_sha256")
        if not isinstance(quiz_hashes, dict) or chapter_id not in quiz_hashes:
            raise CourseRegenerationError(
                "targeted runtime course has no target chapter quiz binding"
            )
        quiz_hashes[chapter_id] = "<target-chapter-quiz>"
    elif relative == ".coursekit/generation.json":
        value.pop("course_contract_sha256", None)
    elif relative == "author.json":
        value.pop("course_contract_sha256", None)
    elif relative == "quiz-answers.json":
        chapters = value.get("chapters")
        if not isinstance(chapters, dict) or chapter_id not in chapters:
            raise CourseRegenerationError(
                "targeted quiz answer book has no target chapter"
            )
        chapters.pop(chapter_id)
    else:  # pragma: no cover - internal call contract
        raise CourseRegenerationError(
            f"unsupported targeted control comparison: {relative}"
        )
    return value


def _v4_targeted_control_mismatches(
    live: Path,
    live_author: Path,
    candidate: Path,
    candidate_author: Path,
    *,
    chapter_id: str,
) -> list[str]:
    mismatches: list[str] = []
    for role, first, second, relative in (
        ("learner", live, candidate, ".coursekit/course.json"),
        ("learner", live, candidate, ".coursekit/generation.json"),
        ("author", live_author, candidate_author, "author.json"),
        ("author", live_author, candidate_author, "quiz-answers.json"),
    ):
        if _v4_targeted_normalized_control(
            first,
            role=role,
            relative=relative,
            chapter_id=chapter_id,
        ) != _v4_targeted_normalized_control(
            second,
            role=role,
            relative=relative,
            chapter_id=chapter_id,
        ):
            mismatches.append(f"{role}/{relative}")
    return mismatches


def _v4_targeted_chapter_digest(
    learner: Path,
    author: Path,
    chapter: Mapping[str, Any],
) -> str:
    chapter_id = str(chapter["id"])
    answers = _read_json(author / "quiz-answers.json", "v4 quiz answers")
    chapters = answers.get("chapters")
    if not isinstance(chapters, Mapping) or chapter_id not in chapters:
        raise CourseRegenerationError(
            f"v4 quiz answers have no chapter {chapter_id}"
        )
    return _canonical_digest(
        {
            "artifacts": _v4_chapter_artifact_digest(
                learner,
                author,
                chapter,
            ),
            "quiz_answers": chapters[chapter_id],
        }
    )


def _v4_targeted_scope_report(
    live: Path,
    live_author: Path,
    candidate: Path,
    candidate_author: Path,
    *,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    chapter_id = str(request["chapter_id"])
    locked = request["locked_chapter"]
    if not isinstance(locked, Mapping):
        raise CourseRegenerationError(
            "targeted regeneration request has no locked chapter"
        )
    owned_raw = locked.get("owned_paths")
    if not isinstance(owned_raw, list) or not all(
        isinstance(path, str) for path in owned_raw
    ):
        raise CourseRegenerationError(
            "targeted regeneration request has invalid owned paths"
        )
    owned = set(owned_raw)
    learner_diff = _v4_targeted_tree_diff(
        live,
        candidate,
        role="learner",
        chapter_id=chapter_id,
        owned_paths=owned,
    )
    author_diff = _v4_targeted_tree_diff(
        live_author,
        candidate_author,
        role="author",
        chapter_id=chapter_id,
        owned_paths=owned,
    )
    controls = _v4_targeted_control_mismatches(
        live,
        live_author,
        candidate,
        candidate_author,
        chapter_id=chapter_id,
    )
    return {
        "chapter_id": chapter_id,
        "learner_changed_paths": learner_diff["changed"],
        "author_changed_paths": author_diff["changed"],
        "unauthorized_learner_paths": learner_diff["unauthorized"],
        "unauthorized_author_paths": author_diff["unauthorized"],
        "derived_control_mismatches": controls,
    }


def plan_v4_targeted_regeneration(
    course: Path,
    *,
    candidate_course: Path,
    chapter_request: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one explicit chapter request to a receipt-valid replacement pair."""

    live, live_author = _v4_pair(course, role="live")
    candidate, candidate_author = _v4_candidate_pair(
        candidate_course,
        live,
        live_author,
    )
    request = _validated_v4_chapter_request(live, chapter_request)
    chapter_id = str(request["chapter_id"])
    current = _v4_current_contracts()
    live_generation = _v4_generation(live)
    candidate_generation = _v4_generation(candidate)
    live_status, live_reason, _action, _calls, _chapters = (
        _v4_regeneration_state(
            live,
            live_author,
            live_generation,
            current,
        )
    )
    live_identity = _v4_identity(live)
    candidate_identity = _v4_identity(candidate)
    blockers: list[dict[str, str]] = []
    if live_status != "up_to_date":
        blockers.append(
            {
                "code": "global-regeneration-required",
                "message": (
                    "targeted chapter regeneration requires current global "
                    f"contracts and receipt: {live_reason}"
                ),
            }
        )
    if candidate_identity != live_identity:
        blockers.append(
            {
                "code": "identity-mismatch",
                "message": "targeted candidate changed the locked course route",
            }
        )
    expected_generation = {
        "plugin_version": current["plugin_version"],
        "content_contract_sha256": current["content_contract_sha256"],
        "runtime_contract_sha256": current["runtime_contract_sha256"],
    }
    stale = sorted(
        key
        for key, value in expected_generation.items()
        if candidate_generation.get(key) != value
    )
    if stale:
        blockers.append(
            {
                "code": "candidate-contract-stale",
                "message": (
                    "targeted candidate was not exported by current contracts: "
                    + ", ".join(stale)
                ),
            }
        )
    scope = _v4_targeted_scope_report(
        live,
        live_author,
        candidate,
        candidate_author,
        request=request,
    )
    unauthorized = [
        *scope["unauthorized_learner_paths"],
        *scope["unauthorized_author_paths"],
        *scope["derived_control_mismatches"],
    ]
    if unauthorized:
        blockers.append(
            {
                "code": "targeted-scope-violation",
                "message": (
                    "targeted candidate changed files or controls outside "
                    f"{chapter_id}: " + ", ".join(unauthorized[:8])
                ),
            }
        )

    metadata = _v4_metadata(live)
    selected = next(
        (
            chapter
            for chapter in metadata["chapters"]
            if isinstance(chapter, Mapping) and chapter.get("id") == chapter_id
        ),
        None,
    )
    if not isinstance(selected, Mapping):
        raise CourseRegenerationError(
            f"targeted chapter disappeared from live route: {chapter_id}"
        )
    live_target = _v4_targeted_chapter_digest(live, live_author, selected)
    candidate_target = _v4_targeted_chapter_digest(
        candidate,
        candidate_author,
        selected,
    )
    if live_target == candidate_target:
        blockers.append(
            {
                "code": "targeted-content-unchanged",
                "message": f"targeted candidate did not change {chapter_id}",
            }
        )

    receipt: dict[str, Any] | None
    try:
        receipt = validate_v4_receipt(
            candidate,
            author_root=candidate_author,
        )
    except V4VerificationError as error:
        receipt = None
        blockers.append(
            {
                "code": "receipt-invalid",
                "message": (
                    "targeted candidate acceptance receipt failed offline "
                    f"binding validation: {error}"
                ),
            }
        )
    for root, label in (
        (candidate, "candidate learner"),
        (candidate_author, "candidate author"),
    ):
        external = _externally_hardlinked_files(root)
        if external:
            blockers.append(
                {
                    "code": "candidate-hardlink",
                    "message": (
                        f"{label} contains externally hard-linked files: "
                        + ", ".join(external[:5])
                    ),
                }
            )

    live_snapshot = _snapshot(live)
    live_author_snapshot = _snapshot(live_author)
    candidate_snapshot = _snapshot(candidate)
    candidate_author_snapshot = _snapshot(candidate_author)
    rollback = _rollback_path(
        live,
        live_snapshot,
        live_author_snapshot,
    )
    if rollback.exists() or rollback.is_symlink():
        raise CourseRegenerationError(
            f"planned targeted v4 rollback path already exists: {rollback}"
        )
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "course_schema_version": 4,
        "command": "check",
        "status": "blocked" if blockers else "ready",
        "reason": f"explicit targeted regeneration for {chapter_id}",
        "required_action": "replace-targeted-chapter",
        "regeneration_kind": "targeted-chapter",
        "writer_calls": 1,
        "mechanical_repair_limit": 1,
        "chapter_ids": [chapter_id],
        "course": str(live),
        "author": str(live_author),
        "candidate_course": str(candidate),
        "candidate_author": str(candidate_author),
        "chapter_request": request,
        "chapter_request_sha256": _canonical_digest(request),
        "current_plugin_version": current["plugin_version"],
        "current_content_contract_sha256": current[
            "content_contract_sha256"
        ],
        "current_runtime_contract_sha256": current[
            "runtime_contract_sha256"
        ],
        "course_generation": live_generation,
        "candidate_generation": candidate_generation,
        "identity": live_identity,
        "candidate_identity": candidate_identity,
        "target_live_projection_sha256": live_target,
        "target_candidate_projection_sha256": candidate_target,
        "targeted_scope": scope,
        "candidate_receipt": (
            _v4_receipt_summary(receipt) if receipt is not None else None
        ),
        "live_snapshot_sha256": live_snapshot,
        "live_author_snapshot_sha256": live_author_snapshot,
        "candidate_snapshot_sha256": candidate_snapshot,
        "candidate_author_snapshot_sha256": candidate_author_snapshot,
        "replacement_policy": REPLACEMENT_POLICY,
        "rollback_path": str(rollback),
        "blockers": blockers,
    }
    return _finish_plan(plan)


def plan_legacy_to_v4_regeneration(
    course: Path,
    *,
    candidate_course: Path,
) -> dict[str, Any]:
    """Bind an explicit schema-v2/v3 course migration to a verified v4 pair."""

    live = _course_root(course, role="live")
    author_destination = live.with_name(f"{live.name}-author")
    candidate, candidate_author = _v4_candidate_pair(
        candidate_course,
        live,
        author_destination,
    )
    source_schema_version = _legacy_course_schema_version(live)
    legacy_baseline = _load_course_baseline(live)
    locked_identity = _legacy_migration_identity(live)
    candidate_identity = _v4_migration_identity(candidate)
    identity_mismatches = _migration_identity_mismatches(
        locked_identity,
        candidate_identity,
    )
    migration = _legacy_to_v4_migration_record(live, candidate)
    current = _v4_current_contracts()
    candidate_generation = _v4_generation(candidate)
    blockers: list[dict[str, str]] = []

    if author_destination.exists() or author_destination.is_symlink():
        blockers.append(
            {
                "code": "author-destination-occupied",
                "message": (
                    "legacy-to-v4 migration requires an unused sibling author "
                    f"path: {author_destination}"
                ),
            }
        )
    if identity_mismatches:
        blockers.append(
            {
                "code": "migration-identity-mismatch",
                "message": (
                    "v4 candidate changed locked legacy identity fields: "
                    + ", ".join(identity_mismatches)
                ),
            }
        )
    expected_generation = {
        "plugin_version": current["plugin_version"],
        "content_contract_sha256": current["content_contract_sha256"],
        "runtime_contract_sha256": current["runtime_contract_sha256"],
    }
    stale_generation = sorted(
        key
        for key, value in expected_generation.items()
        if candidate_generation.get(key) != value
    )
    if stale_generation:
        blockers.append(
            {
                "code": "candidate-contract-stale",
                "message": (
                    "v4 migration candidate was not exported by the current "
                    "contracts: " + ", ".join(stale_generation)
                ),
            }
        )

    receipt: dict[str, Any] | None
    try:
        receipt = validate_v4_receipt(
            candidate,
            author_root=candidate_author,
        )
    except V4VerificationError as error:
        receipt = None
        blockers.append(
            {
                "code": "receipt-invalid",
                "message": (
                    "v4 migration candidate receipt failed offline binding "
                    f"validation: {error}"
                ),
            }
        )
    for root, label in (
        (candidate, "candidate learner"),
        (candidate_author, "candidate author"),
    ):
        external = _externally_hardlinked_files(root)
        if external:
            blockers.append(
                {
                    "code": "candidate-hardlink",
                    "message": (
                        f"{label} contains externally hard-linked files: "
                        + ", ".join(external[:5])
                    ),
                }
            )

    live_snapshot = _snapshot(live)
    candidate_snapshot = _snapshot(candidate)
    candidate_author_snapshot = _snapshot(candidate_author)
    rollback = _rollback_path(live, live_snapshot)
    if rollback.exists() or rollback.is_symlink():
        raise CourseRegenerationError(
            f"planned legacy migration rollback path already exists: {rollback}"
        )
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "course_schema_version": 4,
        "command": "check",
        "status": "blocked" if blockers else "ready",
        "reason": "explicit schema-v2/v3 to schema-v4 migration",
        "required_action": "install-v4-learner-author-pair",
        "migration_kind": "legacy-to-v4",
        "writer_calls": 0,
        "chapter_ids": [],
        "course": str(live),
        "author": str(author_destination),
        "candidate_course": str(candidate),
        "candidate_author": str(candidate_author),
        "source_course_schema_version": source_schema_version,
        "target_course_schema_version": 4,
        "legacy_baseline": _baseline_record(legacy_baseline),
        "identity": locked_identity,
        "candidate_identity": candidate_identity,
        "identity_mismatches": identity_mismatches,
        "migration": migration,
        "current_plugin_version": current["plugin_version"],
        "current_content_contract_sha256": current[
            "content_contract_sha256"
        ],
        "current_runtime_contract_sha256": current[
            "runtime_contract_sha256"
        ],
        "candidate_generation": candidate_generation,
        "candidate_receipt": (
            _v4_receipt_summary(receipt) if receipt is not None else None
        ),
        "live_snapshot_sha256": live_snapshot,
        "candidate_snapshot_sha256": candidate_snapshot,
        "candidate_author_snapshot_sha256": candidate_author_snapshot,
        "replacement_policy": REPLACEMENT_POLICY,
        "rollback_path": str(rollback),
        "blockers": blockers,
    }
    return _finish_plan(plan)


def _load_plan(path: Path) -> dict[str, Any]:
    plan = _read_json(path.expanduser().resolve(strict=True), "regeneration plan")
    digest = plan.pop("plan_digest", None)
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise CourseRegenerationError("regeneration plan has no valid digest")
    if _canonical_digest(plan) != digest:
        raise CourseRegenerationError("regeneration plan digest does not match")
    plan["plan_digest"] = digest
    return plan


def _validated_rollback_path(
    raw: Any,
    *,
    root: Path,
    snapshots: tuple[str, ...],
    label: str,
) -> Path:
    if not isinstance(raw, str):
        raise CourseRegenerationError(f"regeneration plan has no {label}")
    if not snapshots or any(
        SHA256_RE.fullmatch(value) is None for value in snapshots
    ):
        raise CourseRegenerationError(
            f"regeneration plan has invalid snapshots for {label}"
        )
    path = Path(raw)
    suffix = "-".join(re.escape(snapshot[:8]) for snapshot in snapshots)
    expected = re.compile(
        re.escape(f".{root.name}.coursekit-rollback-")
        + r"\d{8}T\d{6}Z-"
        + suffix
    )
    if (
        not path.is_absolute()
        or path.parent != root.parent
        or expected.fullmatch(path.name) is None
        or path.exists()
        or path.is_symlink()
    ):
        raise CourseRegenerationError(
            f"planned {label} is unsafe or already exists"
        )
    return path


def _create_rollback_root(path: Path) -> tuple[int, int]:
    try:
        path.mkdir(mode=0o700)
    except OSError as error:
        raise CourseRegenerationError(
            f"cannot create transient rollback path {path}: {error}"
        ) from error
    if path.is_symlink() or not path.is_dir():
        raise CourseRegenerationError(
            f"transient rollback path is not a regular directory: {path}"
        )
    try:
        stat_result = path.stat(follow_symlinks=False)
    except OSError as error:
        try:
            path.rmdir()
        except OSError:
            pass
        raise CourseRegenerationError(
            f"cannot bind transient rollback path {path}: {error}"
        ) from error
    return stat_result.st_dev, stat_result.st_ino


def _matches_snapshot(path: Path, expected: str) -> bool:
    return (
        not path.is_symlink()
        and path.is_dir()
        and _snapshot(path) == expected
    )


def _directory_open_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise CourseRegenerationError(
            "fd-bound rollback cleanup is unsupported on this platform"
        )
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _file_open_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise CourseRegenerationError(
            "fd-bound rollback cleanup is unsupported on this platform"
        )
    return os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _entry_fingerprint(
    stat_result: os.stat_result,
) -> tuple[int, int, int, int, int]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_mode,
        stat_result.st_size,
        stat_result.st_mtime_ns,
    )


def _fd_mount_identity(fd: int) -> tuple[int, ...]:
    """Return an fd-bound mount identity or fail closed."""

    stat_result = os.fstat(fd)
    if sys.platform.startswith("linux"):
        try:
            fd_info = Path(f"/proc/self/fdinfo/{fd}").read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeError) as error:
            raise CourseRegenerationError(
                "cannot inspect Linux mount identity for rollback cleanup"
            ) from error
        match = re.search(r"^mnt_id:\s*(\d+)\s*$", fd_info, re.MULTILINE)
        if match is None:
            raise CourseRegenerationError(
                "Linux mount identity is unavailable for rollback cleanup"
            )
        return stat_result.st_dev, int(match.group(1))
    if sys.platform == "darwin":
        # macOS has no same-filesystem bind mount. st_dev changes at a
        # mounted filesystem boundary and is available through the bound fd.
        return (stat_result.st_dev,)
    raise CourseRegenerationError(
        "fd-bound rollback cleanup supports only macOS, Linux, and WSL2"
    )


def _open_directory_at(parent_fd: int, name: str) -> int:
    try:
        return os.open(name, _directory_open_flags(), dir_fd=parent_fd)
    except OSError as error:
        raise CourseRegenerationError(
            f"cannot bind rollback directory entry {name}: {error}"
        ) from error


def _assert_same_mount(
    fd: int,
    root_mount_identity: tuple[int, ...],
    *,
    relative: str,
) -> tuple[int, ...]:
    mount_identity = _fd_mount_identity(fd)
    if mount_identity != root_mount_identity:
        raise CourseRegenerationError(
            f"rollback tree crosses a nested mountpoint at {relative}"
        )
    return mount_identity


def _scan_bound_rollback_directory(
    directory_fd: int,
    *,
    root_mount_identity: tuple[int, ...],
) -> tuple[
    list[tuple[str, str, bytes]],
    tuple[_BoundRollbackEntry, ...],
]:
    """Snapshot a directory through fds and bind every deletable inode."""

    raw_records: list[
        tuple[str, str, bytes, tuple[int, int] | None, int]
    ] = []

    def visit(
        current_fd: int,
        prefix: PurePosixPath,
    ) -> tuple[_BoundRollbackEntry, ...]:
        try:
            with os.scandir(current_fd) as iterator:
                names = sorted(entry.name for entry in iterator)
        except OSError as error:
            raise CourseRegenerationError(
                f"cannot scan bound rollback tree: {error}"
            ) from error

        bound_entries: list[_BoundRollbackEntry] = []
        for name in names:
            relative_path = prefix / name
            relative = relative_path.as_posix()
            try:
                stat_result = os.stat(
                    name,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise CourseRegenerationError(
                    f"cannot inspect bound rollback path {relative}: {error}"
                ) from error
            mode = (stat_result.st_mode & 0o7777).to_bytes(2, "big")
            fingerprint = _entry_fingerprint(stat_result)

            if stat.S_ISLNK(stat_result.st_mode):
                try:
                    target = os.readlink(name, dir_fd=current_fd)
                except OSError as error:
                    raise CourseRegenerationError(
                        f"cannot read rollback symlink {relative}: {error}"
                    ) from error
                raw_records.append(
                    (
                        relative,
                        "symlink",
                        mode
                        + target.encode(
                            "utf-8",
                            errors="surrogateescape",
                        ),
                        None,
                        stat_result.st_nlink,
                    )
                )
                bound_entries.append(
                    _BoundRollbackEntry(
                        name=name,
                        kind="symlink",
                        fingerprint=fingerprint,
                        mount_identity=None,
                    )
                )
                continue

            if stat.S_ISDIR(stat_result.st_mode):
                child_fd = _open_directory_at(current_fd, name)
                try:
                    opened_stat = os.fstat(child_fd)
                    if _entry_fingerprint(opened_stat) != fingerprint:
                        raise CourseRegenerationError(
                            f"rollback directory changed while binding: {relative}"
                        )
                    mount_identity = _assert_same_mount(
                        child_fd,
                        root_mount_identity,
                        relative=relative,
                    )
                    raw_records.append(
                        (
                            relative,
                            "directory",
                            mode,
                            None,
                            stat_result.st_nlink,
                        )
                    )
                    children = visit(child_fd, relative_path)
                    if _entry_fingerprint(os.fstat(child_fd)) != fingerprint:
                        raise CourseRegenerationError(
                            f"rollback directory changed while scanning: {relative}"
                        )
                finally:
                    os.close(child_fd)
                bound_entries.append(
                    _BoundRollbackEntry(
                        name=name,
                        kind="directory",
                        fingerprint=fingerprint,
                        mount_identity=mount_identity,
                        children=children,
                    )
                )
                continue

            if stat.S_ISREG(stat_result.st_mode):
                try:
                    file_fd = os.open(
                        name,
                        _file_open_flags(),
                        dir_fd=current_fd,
                    )
                except OSError as error:
                    raise CourseRegenerationError(
                        f"cannot bind rollback file {relative}: {error}"
                    ) from error
                try:
                    opened_stat = os.fstat(file_fd)
                    if _entry_fingerprint(opened_stat) != fingerprint:
                        raise CourseRegenerationError(
                            f"rollback file changed while binding: {relative}"
                        )
                    mount_identity = _assert_same_mount(
                        file_fd,
                        root_mount_identity,
                        relative=relative,
                    )
                    digest = hashlib.sha256()
                    while chunk := os.read(file_fd, 1024 * 1024):
                        digest.update(chunk)
                    if _entry_fingerprint(os.fstat(file_fd)) != fingerprint:
                        raise CourseRegenerationError(
                            f"rollback file changed while scanning: {relative}"
                        )
                finally:
                    os.close(file_fd)
                raw_records.append(
                    (
                        relative,
                        "file",
                        mode + digest.digest(),
                        (stat_result.st_dev, stat_result.st_ino),
                        stat_result.st_nlink,
                    )
                )
                bound_entries.append(
                    _BoundRollbackEntry(
                        name=name,
                        kind="file",
                        fingerprint=fingerprint,
                        mount_identity=mount_identity,
                    )
                )
                continue

            raise CourseRegenerationError(
                f"rollback tree contains a special file: {relative}"
            )

        return tuple(bound_entries)

    bound_entries = visit(directory_fd, PurePosixPath())
    return _finalize_scan_records(raw_records), bound_entries


def _assert_named_directory_identity(
    parent_fd: int,
    name: str,
    identity: tuple[int, int],
) -> None:
    try:
        stat_result = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as error:
        raise CourseRegenerationError(
            "transient rollback path identity changed during cleanup"
        ) from error
    if (
        not stat.S_ISDIR(stat_result.st_mode)
        or (stat_result.st_dev, stat_result.st_ino) != identity
    ):
        raise CourseRegenerationError(
            "transient rollback path identity changed during cleanup"
        )


def _preflight_rollback_deletion(path: Path, expected_snapshot: str) -> None:
    """Reject mounted or unstable old trees before the first live rename."""

    parent_fd: int | None = None
    root_fd: int | None = None
    try:
        parent_fd = os.open(path.parent, _directory_open_flags())
        root_fd = _open_directory_at(parent_fd, path.name)
        root_stat = os.fstat(root_fd)
        identity = (root_stat.st_dev, root_stat.st_ino)
        parent_mount_identity = _fd_mount_identity(parent_fd)
        root_mount_identity = _assert_same_mount(
            root_fd,
            parent_mount_identity,
            relative=".",
        )
        records, _ = _scan_bound_rollback_directory(
            root_fd,
            root_mount_identity=root_mount_identity,
        )
        if _snapshot_records(records) != expected_snapshot:
            raise CourseRegenerationError(
                f"old project changed during rollback cleanup preflight: {path}"
            )
        _assert_named_directory_identity(parent_fd, path.name, identity)
    except OSError as error:
        raise CourseRegenerationError(
            f"cannot preflight rollback cleanup for {path}: {error}"
        ) from error
    finally:
        if root_fd is not None:
            os.close(root_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _validate_rollback_root(
    rollback: Path,
    expected: Mapping[str, str],
    *,
    identity: tuple[int, int],
    rollback_fd: int,
    parent_mount_identity: tuple[int, ...],
) -> tuple[tuple[_BoundRollbackEntry, ...], tuple[int, ...]]:
    stat_result = os.fstat(rollback_fd)
    if (
        not stat.S_ISDIR(stat_result.st_mode)
        or (stat_result.st_dev, stat_result.st_ino) != identity
    ):
        raise CourseRegenerationError(
            "transient rollback path identity changed during replacement"
        )
    root_mount_identity = _assert_same_mount(
        rollback_fd,
        parent_mount_identity,
        relative=".",
    )
    try:
        with os.scandir(rollback_fd) as iterator:
            names = sorted(entry.name for entry in iterator)
    except OSError as error:
        raise CourseRegenerationError(
            f"cannot inspect transient rollback path {rollback}: {error}"
        ) from error
    if set(names) != set(expected):
        raise CourseRegenerationError(
            "transient rollback path contains unexpected or missing roots"
        )

    bound_entries: list[_BoundRollbackEntry] = []
    for name, snapshot in expected.items():
        try:
            entry_stat = os.stat(
                name,
                dir_fd=rollback_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            raise CourseRegenerationError(
                f"cannot inspect transient rollback member {name}: {error}"
            ) from error
        if not stat.S_ISDIR(entry_stat.st_mode):
            raise CourseRegenerationError(
                f"transient rollback member is unsafe: {name}"
            )
        member_fd = _open_directory_at(rollback_fd, name)
        try:
            opened_stat = os.fstat(member_fd)
            fingerprint = _entry_fingerprint(entry_stat)
            if _entry_fingerprint(opened_stat) != fingerprint:
                raise CourseRegenerationError(
                    f"transient rollback member changed: {name}"
                )
            mount_identity = _assert_same_mount(
                member_fd,
                root_mount_identity,
                relative=name,
            )
            records, children = _scan_bound_rollback_directory(
                member_fd,
                root_mount_identity=root_mount_identity,
            )
            if _snapshot_records(records) != snapshot:
                raise CourseRegenerationError(
                    f"transient rollback member changed: {name}"
                )
            if _entry_fingerprint(os.fstat(member_fd)) != fingerprint:
                raise CourseRegenerationError(
                    f"transient rollback member changed while scanning: {name}"
                )
        finally:
            os.close(member_fd)
        bound_entries.append(
            _BoundRollbackEntry(
                name=name,
                kind="directory",
                fingerprint=fingerprint,
                mount_identity=mount_identity,
                children=children,
            )
        )
    return tuple(bound_entries), root_mount_identity


def _assert_bound_entry(
    parent_fd: int,
    entry: _BoundRollbackEntry,
) -> os.stat_result:
    try:
        stat_result = os.stat(
            entry.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except OSError as error:
        raise CourseRegenerationError(
            f"validated rollback entry disappeared: {entry.name}"
        ) from error
    if _entry_fingerprint(stat_result) != entry.fingerprint:
        raise CourseRegenerationError(
            f"validated rollback entry changed before deletion: {entry.name}"
        )
    return stat_result


def _delete_bound_rollback_contents(
    directory_fd: int,
    entries: tuple[_BoundRollbackEntry, ...],
    *,
    root_mount_identity: tuple[int, ...],
) -> None:
    """Recursively unlink only the inode manifest bound during validation."""

    try:
        current_names = set(os.listdir(directory_fd))
    except OSError as error:
        raise CourseRegenerationError(
            f"cannot inspect bound rollback directory: {error}"
        ) from error
    expected_names = {entry.name for entry in entries}
    if current_names != expected_names:
        raise CourseRegenerationError(
            "validated rollback directory changed before deletion"
        )

    for entry in entries:
        stat_result = _assert_bound_entry(directory_fd, entry)
        if entry.kind == "directory":
            if not stat.S_ISDIR(stat_result.st_mode):
                raise CourseRegenerationError(
                    f"validated rollback directory became unsafe: {entry.name}"
                )
            child_fd = _open_directory_at(directory_fd, entry.name)
            try:
                if _entry_fingerprint(os.fstat(child_fd)) != entry.fingerprint:
                    raise CourseRegenerationError(
                        "validated rollback directory changed before deletion: "
                        f"{entry.name}"
                    )
                mount_identity = _assert_same_mount(
                    child_fd,
                    root_mount_identity,
                    relative=entry.name,
                )
                if mount_identity != entry.mount_identity:
                    raise CourseRegenerationError(
                        "validated rollback mount identity changed before deletion: "
                        f"{entry.name}"
                    )
                _delete_bound_rollback_contents(
                    child_fd,
                    entry.children,
                    root_mount_identity=root_mount_identity,
                )
                if os.listdir(child_fd):
                    raise CourseRegenerationError(
                        f"validated rollback directory is not empty: {entry.name}"
                    )
            finally:
                os.close(child_fd)
            current_stat = os.stat(
                entry.name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(current_stat.st_mode)
                or (
                    current_stat.st_dev,
                    current_stat.st_ino,
                )
                != entry.fingerprint[:2]
            ):
                raise CourseRegenerationError(
                    "validated rollback directory was replaced during deletion: "
                    f"{entry.name}"
                )
            os.rmdir(entry.name, dir_fd=directory_fd)
            continue

        if entry.kind == "file":
            if not stat.S_ISREG(stat_result.st_mode):
                raise CourseRegenerationError(
                    f"validated rollback file became unsafe: {entry.name}"
                )
            try:
                file_fd = os.open(
                    entry.name,
                    _file_open_flags(),
                    dir_fd=directory_fd,
                )
            except OSError as error:
                raise CourseRegenerationError(
                    f"cannot rebind rollback file {entry.name}: {error}"
                ) from error
            try:
                if _entry_fingerprint(os.fstat(file_fd)) != entry.fingerprint:
                    raise CourseRegenerationError(
                        f"validated rollback file changed: {entry.name}"
                    )
                mount_identity = _assert_same_mount(
                    file_fd,
                    root_mount_identity,
                    relative=entry.name,
                )
                if mount_identity != entry.mount_identity:
                    raise CourseRegenerationError(
                        "validated rollback mount identity changed before deletion: "
                        f"{entry.name}"
                    )
            finally:
                os.close(file_fd)
            os.unlink(entry.name, dir_fd=directory_fd)
            continue

        if entry.kind != "symlink" or not stat.S_ISLNK(stat_result.st_mode):
            raise CourseRegenerationError(
                f"validated rollback entry became unsafe: {entry.name}"
            )
        os.unlink(entry.name, dir_fd=directory_fd)


def _delete_rollback_root(
    rollback: Path,
    expected: Mapping[str, str],
    *,
    identity: tuple[int, int],
) -> None:
    """Delete only the fully validated old project tree after commit checks."""

    parent_fd: int | None = None
    rollback_fd: int | None = None
    try:
        parent_fd = os.open(rollback.parent, _directory_open_flags())
        rollback_fd = _open_directory_at(parent_fd, rollback.name)
        parent_mount_identity = _fd_mount_identity(parent_fd)
        bound_entries, root_mount_identity = _validate_rollback_root(
            rollback,
            expected,
            identity=identity,
            rollback_fd=rollback_fd,
            parent_mount_identity=parent_mount_identity,
        )
        # This check intentionally occurs after validation. If the pathname was
        # swapped, the foreign tree is left untouched and cleanup fails closed.
        _assert_named_directory_identity(parent_fd, rollback.name, identity)
        _delete_bound_rollback_contents(
            rollback_fd,
            bound_entries,
            root_mount_identity=root_mount_identity,
        )
        _assert_named_directory_identity(parent_fd, rollback.name, identity)
        os.rmdir(rollback.name, dir_fd=parent_fd)
    except OSError as error:
        raise CourseRegenerationError(
            f"cannot delete transient rollback path {rollback}: {error}"
        ) from error
    finally:
        if rollback_fd is not None:
            os.close(rollback_fd)
        if parent_fd is not None:
            os.close(parent_fd)
    if rollback.exists() or rollback.is_symlink():
        raise CourseRegenerationError(
            f"transient rollback path still exists after deletion: {rollback}"
        )


def _prepare_apply_result_output(
    result_path: Path | None,
    *,
    roots: tuple[Path, ...],
    rollback: Path,
    location: str,
) -> Path | None:
    if result_path is None:
        return None
    output = _safe_output(result_path, roots, location=location)
    if output == rollback or rollback in output.parents:
        raise CourseRegenerationError(
            f"{location} must be outside the transient rollback path"
        )
    return _preflight_json_output(output)


def _replacement_report(
    base: Mapping[str, Any],
    *,
    rollback: Path,
    cleanup_status: str,
) -> dict[str, Any]:
    if cleanup_status not in {"pending", "complete", "failed"}:
        raise CourseRegenerationError(
            f"invalid replacement cleanup status: {cleanup_status}"
        )
    if cleanup_status == "pending":
        transaction_state = "replacement_committed"
    elif cleanup_status == "complete":
        rollback_retained = False
        old_project_deleted = True
        replacement_irreversible = True
        residue_possible = False
        transaction_state = "complete"
    else:
        transaction_state = "cleanup_failed"
    report = {
        **base,
        "status": "applied",
        "replacement_committed": True,
        "transaction_state": transaction_state,
        "cleanup_status": cleanup_status,
        "backup_retained": False,
    }
    if cleanup_status == "complete":
        report.update(
            {
                "rollback_retained": rollback_retained,
                "old_project_deleted": old_project_deleted,
                "replacement_irreversible": replacement_irreversible,
                "cleanup_residue_possible": residue_possible,
            }
        )
    elif cleanup_status == "failed":
        # Recursive cleanup may have removed all, some, or none of the old
        # tree, and pathname interference can leave an unrelated directory at
        # rollback_path. Do not turn that uncertain residue into a backup or
        # deletion claim.
        report["cleanup_residue_possible"] = True
    return report


def _remove_empty_rollback_root(
    rollback: Path,
    errors: list[str],
    *,
    identity: tuple[int, int],
) -> None:
    if not rollback.exists() and not rollback.is_symlink():
        return
    if rollback.is_symlink() or not rollback.is_dir():
        errors.append("transient rollback path became unsafe")
        return
    try:
        stat_result = rollback.stat(follow_symlinks=False)
        if (stat_result.st_dev, stat_result.st_ino) != identity:
            errors.append("transient rollback path identity changed")
            return
        rollback.rmdir()
    except OSError as error:
        errors.append(f"cannot remove empty transient rollback path: {error}")


def _validate_v4_targeted_ready_plan(
    plan: Mapping[str, Any],
    *,
    live: Path,
    live_author: Path,
    candidate: Path,
    candidate_author: Path,
) -> tuple[Path, str, str]:
    if (
        plan.get("schema_version") != PLAN_SCHEMA_VERSION
        or plan.get("course_schema_version") != 4
        or plan.get("command") != "check"
        or plan.get("status") != "ready"
        or plan.get("regeneration_kind") != "targeted-chapter"
        or plan.get("required_action") != "replace-targeted-chapter"
        or plan.get("writer_calls") != 1
        or plan.get("mechanical_repair_limit") != 1
        or plan.get("replacement_policy") != REPLACEMENT_POLICY
        or plan.get("blockers") != []
    ):
        raise CourseRegenerationError(
            "targeted v4 apply requires a ready, blocker-free chapter plan"
        )
    if (
        plan.get("course") != str(live)
        or plan.get("author") != str(live_author)
        or plan.get("candidate_course") != str(candidate)
        or plan.get("candidate_author") != str(candidate_author)
    ):
        raise CourseRegenerationError(
            "targeted v4 plan is for different learner/author paths"
        )
    request_raw = plan.get("chapter_request")
    if not isinstance(request_raw, Mapping):
        raise CourseRegenerationError(
            "targeted v4 plan has no chapter request"
        )
    request = _validated_v4_chapter_request(live, request_raw)
    if (
        plan.get("chapter_request_sha256") != _canonical_digest(request)
        or plan.get("chapter_ids") != [request["chapter_id"]]
    ):
        raise CourseRegenerationError(
            "targeted v4 chapter request binding changed after check"
        )

    current = _v4_current_contracts()
    if (
        plan.get("current_plugin_version") != current["plugin_version"]
        or plan.get("current_content_contract_sha256")
        != current["content_contract_sha256"]
        or plan.get("current_runtime_contract_sha256")
        != current["runtime_contract_sha256"]
    ):
        raise CourseRegenerationError(
            "the installed v4 Skill changed after targeted check"
        )
    live_generation = _v4_generation(live)
    candidate_generation = _v4_generation(candidate)
    status, _reason, _action, _calls, _chapters = _v4_regeneration_state(
        live,
        live_author,
        live_generation,
        current,
    )
    if (
        status != "up_to_date"
        or plan.get("course_generation") != live_generation
        or plan.get("candidate_generation") != candidate_generation
    ):
        raise CourseRegenerationError(
            "targeted v4 generation contracts changed after check"
        )
    expected_generation = {
        "plugin_version": current["plugin_version"],
        "content_contract_sha256": current["content_contract_sha256"],
        "runtime_contract_sha256": current["runtime_contract_sha256"],
    }
    if any(
        candidate_generation.get(key) != value
        for key, value in expected_generation.items()
    ):
        raise CourseRegenerationError(
            "targeted v4 candidate no longer uses current contracts"
        )
    live_identity = _v4_identity(live)
    candidate_identity = _v4_identity(candidate)
    if (
        plan.get("identity") != live_identity
        or plan.get("candidate_identity") != candidate_identity
        or candidate_identity != live_identity
    ):
        raise CourseRegenerationError(
            "targeted v4 course identity or route changed after check"
        )

    live_snapshot = _snapshot(live)
    live_author_snapshot = _snapshot(live_author)
    candidate_snapshot = _snapshot(candidate)
    candidate_author_snapshot = _snapshot(candidate_author)
    if (
        plan.get("live_snapshot_sha256") != live_snapshot
        or plan.get("live_author_snapshot_sha256") != live_author_snapshot
    ):
        raise CourseRegenerationError(
            "live v4 pair changed after targeted check"
        )
    if (
        plan.get("candidate_snapshot_sha256") != candidate_snapshot
        or plan.get("candidate_author_snapshot_sha256")
        != candidate_author_snapshot
    ):
        raise CourseRegenerationError(
            "candidate v4 pair changed after targeted check"
        )

    scope = _v4_targeted_scope_report(
        live,
        live_author,
        candidate,
        candidate_author,
        request=request,
    )
    if (
        plan.get("targeted_scope") != scope
        or scope["unauthorized_learner_paths"]
        or scope["unauthorized_author_paths"]
        or scope["derived_control_mismatches"]
    ):
        raise CourseRegenerationError(
            "targeted v4 candidate escaped its chapter-owned scope"
        )
    metadata = _v4_metadata(live)
    selected = next(
        (
            chapter
            for chapter in metadata["chapters"]
            if isinstance(chapter, Mapping)
            and chapter.get("id") == request["chapter_id"]
        ),
        None,
    )
    if not isinstance(selected, Mapping):
        raise CourseRegenerationError(
            "targeted v4 chapter disappeared after check"
        )
    live_target = _v4_targeted_chapter_digest(
        live,
        live_author,
        selected,
    )
    candidate_target = _v4_targeted_chapter_digest(
        candidate,
        candidate_author,
        selected,
    )
    if (
        live_target == candidate_target
        or plan.get("target_live_projection_sha256") != live_target
        or plan.get("target_candidate_projection_sha256") != candidate_target
    ):
        raise CourseRegenerationError(
            "targeted v4 chapter change no longer matches the plan"
        )

    try:
        receipt = validate_v4_receipt(
            candidate,
            author_root=candidate_author,
        )
    except V4VerificationError as error:
        raise CourseRegenerationError(
            f"targeted v4 candidate receipt changed or is invalid: {error}"
        ) from error
    if plan.get("candidate_receipt") != _v4_receipt_summary(receipt):
        raise CourseRegenerationError(
            "targeted v4 candidate receipt binding changed after check"
        )
    for root, label in (
        (candidate, "candidate learner"),
        (candidate_author, "candidate author"),
    ):
        external = _externally_hardlinked_files(root)
        if external:
            raise CourseRegenerationError(
                f"{label} contains externally hard-linked files: "
                + ", ".join(external[:5])
            )

    rollback = _validated_rollback_path(
        plan.get("rollback_path"),
        root=live,
        snapshots=(live_snapshot, live_author_snapshot),
        label="targeted v4 rollback path",
    )
    return rollback, candidate_snapshot, candidate_author_snapshot


def _validate_v4_ready_plan(
    plan: Mapping[str, Any],
    *,
    live: Path,
    live_author: Path,
    candidate: Path,
    candidate_author: Path,
) -> tuple[Path, str, str]:
    if (
        plan.get("schema_version") != PLAN_SCHEMA_VERSION
        or plan.get("course_schema_version") != 4
        or plan.get("command") != "check"
        or plan.get("status") != "ready"
        or plan.get("replacement_policy") != REPLACEMENT_POLICY
        or plan.get("blockers") != []
    ):
        raise CourseRegenerationError(
            "v4 apply requires a ready, blocker-free regeneration plan"
        )
    if (
        plan.get("course") != str(live)
        or plan.get("author") != str(live_author)
        or plan.get("candidate_course") != str(candidate)
        or plan.get("candidate_author") != str(candidate_author)
    ):
        raise CourseRegenerationError(
            "v4 regeneration plan is for different learner/author paths"
        )

    current = _v4_current_contracts()
    if (
        plan.get("current_plugin_version") != current["plugin_version"]
        or plan.get("current_content_contract_sha256")
        != current["content_contract_sha256"]
        or plan.get("current_runtime_contract_sha256")
        != current["runtime_contract_sha256"]
    ):
        raise CourseRegenerationError("the installed v4 Skill changed after check")
    live_generation = _v4_generation(live)
    status, _reason, action, writer_calls, chapter_ids = _v4_regeneration_state(
        live,
        live_author,
        live_generation,
        current,
    )
    if (
        plan.get("regeneration_kind") != status
        or plan.get("required_action") != action
        or plan.get("writer_calls") != writer_calls
        or plan.get("chapter_ids") != chapter_ids
        or status == "up_to_date"
    ):
        raise CourseRegenerationError(
            "live v4 regeneration requirement changed after check"
        )
    if (
        plan.get("course_plugin_version") != live_generation["plugin_version"]
        or plan.get("course_content_contract_sha256")
        != live_generation["content_contract_sha256"]
        or plan.get("course_runtime_contract_sha256")
        != live_generation["runtime_contract_sha256"]
    ):
        raise CourseRegenerationError(
            "live v4 generation metadata changed after check"
        )

    live_identity = _v4_identity(live)
    candidate_identity = _v4_identity(candidate)
    if (
        plan.get("identity") != live_identity
        or plan.get("candidate_identity") != candidate_identity
        or candidate_identity != live_identity
    ):
        raise CourseRegenerationError(
            "v4 course identity or chapter route changed after check"
        )
    candidate_generation = _v4_generation(candidate)
    if (
        plan.get("candidate_generation") != candidate_generation
        or candidate_generation["plugin_version"] != current["plugin_version"]
        or candidate_generation["content_contract_sha256"]
        != current["content_contract_sha256"]
        or candidate_generation["runtime_contract_sha256"]
        != current["runtime_contract_sha256"]
    ):
        raise CourseRegenerationError(
            "v4 candidate generation contract changed after check"
        )

    live_snapshot = _snapshot(live)
    live_author_snapshot = _snapshot(live_author)
    candidate_snapshot = _snapshot(candidate)
    candidate_author_snapshot = _snapshot(candidate_author)
    if (
        plan.get("live_snapshot_sha256") != live_snapshot
        or plan.get("live_author_snapshot_sha256") != live_author_snapshot
    ):
        raise CourseRegenerationError("live v4 pair changed after check")
    if (
        plan.get("candidate_snapshot_sha256") != candidate_snapshot
        or plan.get("candidate_author_snapshot_sha256")
        != candidate_author_snapshot
    ):
        raise CourseRegenerationError("candidate v4 pair changed after check")

    live_content = _v4_digest_selected_tree(live, live_author)
    candidate_content = _v4_digest_selected_tree(candidate, candidate_author)
    if (
        plan.get("live_content_projection_sha256") != live_content
        or plan.get("candidate_content_projection_sha256") != candidate_content
    ):
        raise CourseRegenerationError(
            "v4 author-controlled content projection changed after check"
        )
    if status == "needs_content_regeneration":
        if candidate_content == live_content:
            raise CourseRegenerationError(
                "v4 content regeneration produced no material content change"
            )
    elif candidate_content != live_content:
        raise CourseRegenerationError(
            "v4 runtime refresh or revalidation changed Writer-owned content"
        )

    try:
        receipt = validate_v4_receipt(
            candidate,
            author_root=candidate_author,
        )
    except V4VerificationError as error:
        raise CourseRegenerationError(
            f"v4 candidate receipt changed or is invalid: {error}"
        ) from error
    receipt_summary = {
        "receipt_sha256": receipt["receipt_sha256"],
        "learner_tree_sha256": receipt["learner_tree_sha256"],
        "author_tree_sha256": receipt["author_tree_sha256"],
        "runtime_sha256": receipt["runtime_sha256"],
        "verifier_sha256": receipt["verifier_sha256"],
    }
    if plan.get("candidate_receipt") != receipt_summary:
        raise CourseRegenerationError(
            "v4 candidate receipt binding changed after check"
        )
    for root, label in (
        (candidate, "candidate learner"),
        (candidate_author, "candidate author"),
    ):
        external = _externally_hardlinked_files(root)
        if external:
            raise CourseRegenerationError(
                f"{label} contains externally hard-linked files: "
                + ", ".join(external[:5])
            )

    rollback = _validated_rollback_path(
        plan.get("rollback_path"),
        root=live,
        snapshots=(live_snapshot, live_author_snapshot),
        label="v4 rollback path",
    )
    return rollback, candidate_snapshot, candidate_author_snapshot


def _restore_v4_pair(
    *,
    live: Path,
    live_author: Path,
    candidate: Path,
    candidate_author: Path,
    rollback: Path,
    rollback_identity: tuple[int, int],
    old_snapshot: str,
    old_author_snapshot: str,
    candidate_snapshot: str,
    candidate_author_snapshot: str,
) -> str:
    errors: list[str] = []
    learner_rollback = rollback / ROLLBACK_LEARNER_NAME
    author_rollback = rollback / ROLLBACK_AUTHOR_NAME

    def matches(path: Path, expected: str, label: str) -> bool:
        try:
            return _matches_snapshot(path, expected)
        except CourseRegenerationError as error:
            errors.append(f"cannot inspect {label}: {error}")
            return False

    def location(
        current: Path,
        staged: Path,
        expected: str,
        label: str,
    ) -> str | None:
        if matches(staged, expected, f"staged {label}"):
            return "rollback"
        if matches(current, expected, f"current {label}"):
            return "live"
        errors.append(f"original {label} is not recoverable")
        return None

    learner_location = location(
        live,
        learner_rollback,
        old_snapshot,
        "learner",
    )
    author_location = location(
        live_author,
        author_rollback,
        old_author_snapshot,
        "author",
    )
    restore_specs = (
        (
            "learner",
            learner_location,
            live,
            candidate,
            learner_rollback,
            candidate_snapshot,
        ),
        (
            "author",
            author_location,
            live_author,
            candidate_author,
            author_rollback,
            candidate_author_snapshot,
        ),
    )
    for label, source, current, candidate_path, _staged, expected in restore_specs:
        if source != "rollback" or (
            not current.exists() and not current.is_symlink()
        ):
            continue
        if candidate_path.exists() or candidate_path.is_symlink():
            errors.append(f"candidate {label} path is occupied")
        elif not matches(current, expected, f"installed candidate {label}"):
            errors.append(f"installed candidate {label} changed")
    if errors:
        return (
            "manual recovery required ("
            + "; ".join(errors)
            + f"); installed paths were preserved and rollback is {rollback}"
        )

    def move(source: Path, destination: Path, message: str) -> bool:
        try:
            os.replace(source, destination)
            return True
        except OSError as error:
            if (
                not source.exists()
                and not source.is_symlink()
                and (destination.exists() or destination.is_symlink())
            ):
                return True
            errors.append(f"{message}: {error}")
            return False

    moved_candidates: dict[str, bool] = {}
    for label, source, current, candidate_path, staged, _expected in reversed(
        restore_specs
    ):
        if source != "rollback":
            continue
        current_occupied = current.exists() or current.is_symlink()
        moved = True
        if current_occupied:
            moved = move(
                current,
                candidate_path,
                f"cannot move failed candidate {label} back",
            )
            moved_candidates[label] = moved
        if moved and not current.exists() and not current.is_symlink():
            move(staged, current, f"cannot restore original {label}")

    try:
        restored = (
            live.is_dir()
            and not live.is_symlink()
            and live_author.is_dir()
            and not live_author.is_symlink()
            and _snapshot(live) == old_snapshot
            and _snapshot(live_author) == old_author_snapshot
        )
    except CourseRegenerationError as error:
        errors.append(f"cannot verify restored pair: {error}")
        restored = False
    for label, moved in moved_candidates.items():
        if not moved:
            continue
        candidate_path = candidate if label == "learner" else candidate_author
        expected = (
            candidate_snapshot
            if label == "learner"
            else candidate_author_snapshot
        )
        try:
            if not _matches_snapshot(candidate_path, expected):
                errors.append(f"restored candidate {label} changed")
        except CourseRegenerationError as error:
            errors.append(f"cannot verify restored candidate {label}: {error}")
    _remove_empty_rollback_root(
        rollback,
        errors,
        identity=rollback_identity,
    )
    if restored and not errors:
        return "rolled back learner and author with no retained rollback"
    detail = "; ".join(errors) or "restored pair did not match snapshots"
    return f"manual recovery required ({detail}); rollback is {rollback}"


def apply_v4_regeneration(
    course: Path,
    *,
    candidate_course: Path,
    plan_path: Path,
    confirm_stopped: bool,
    accept_replacement: bool,
    result_path: Path | None = None,
) -> dict[str, Any]:
    """Install a receipt-bound v4 learner/author pair without rerunning tests."""

    if not confirm_stopped:
        raise CourseRegenerationError("--confirm-stopped is required")
    if not accept_replacement:
        raise CourseRegenerationError("--accept-replacement is required")
    live, live_author = _v4_pair(course, role="live")
    candidate, candidate_author = _v4_candidate_pair(
        candidate_course,
        live,
        live_author,
    )
    plan_file = _safe_output(
        plan_path,
        (live, live_author, candidate, candidate_author),
        location="v4 plan path",
    )
    plan = _load_plan(plan_file)
    validator = (
        _validate_v4_targeted_ready_plan
        if plan.get("regeneration_kind") == "targeted-chapter"
        else _validate_v4_ready_plan
    )
    rollback, candidate_snapshot, candidate_author_snapshot = validator(
        plan,
        live=live,
        live_author=live_author,
        candidate=candidate,
        candidate_author=candidate_author,
    )
    old_snapshot = str(plan["live_snapshot_sha256"])
    old_author_snapshot = str(plan["live_author_snapshot_sha256"])
    output = _prepare_apply_result_output(
        result_path,
        roots=(live, live_author, candidate, candidate_author),
        rollback=rollback,
        location="v4 result output",
    )
    result_base = {
        "schema_version": 2,
        "course_schema_version": 4,
        "course": str(live),
        "author": str(live_author),
        "replacement_policy": REPLACEMENT_POLICY,
        "rollback_path": str(rollback),
        "old_snapshot_sha256": old_snapshot,
        "old_author_snapshot_sha256": old_author_snapshot,
        "new_snapshot_sha256": candidate_snapshot,
        "new_author_snapshot_sha256": candidate_author_snapshot,
        "plan_digest": plan["plan_digest"],
        "receipt_validation": "offline",
        "writer_calls_during_apply": 0,
        **(
            {
                "regeneration_kind": "targeted-chapter",
                "chapter_ids": list(plan["chapter_ids"]),
            }
            if plan.get("regeneration_kind") == "targeted-chapter"
            else {}
        ),
    }
    learner_rollback = rollback / ROLLBACK_LEARNER_NAME
    author_rollback = rollback / ROLLBACK_AUTHOR_NAME
    _preflight_rollback_deletion(live, old_snapshot)
    _preflight_rollback_deletion(live_author, old_author_snapshot)
    rollback_identity = _create_rollback_root(rollback)
    try:
        os.replace(live, learner_rollback)
        os.replace(live_author, author_rollback)
        for root, expected, label in (
            (candidate, candidate_snapshot, "candidate learner"),
            (
                candidate_author,
                candidate_author_snapshot,
                "candidate author",
            ),
        ):
            external = _externally_hardlinked_files(root)
            if external or _snapshot(root) != expected:
                detail = (
                    "externally hard-linked files: " + ", ".join(external[:5])
                    if external
                    else "snapshot changed"
                )
                raise CourseRegenerationError(f"{label} {detail}")
        os.replace(candidate, live)
        os.replace(candidate_author, live_author)
        if (
            _snapshot(learner_rollback) != old_snapshot
            or _snapshot(author_rollback) != old_author_snapshot
            or _snapshot(live) != candidate_snapshot
            or _snapshot(live_author) != candidate_author_snapshot
        ):
            raise CourseRegenerationError(
                "post-swap v4 learner/author snapshots do not match"
            )
        validate_v4_receipt(live, author_root=live_author)
    except (OSError, CourseRegenerationError, V4VerificationError) as error:
        recovery = _restore_v4_pair(
            live=live,
            live_author=live_author,
            candidate=candidate,
            candidate_author=candidate_author,
            rollback=rollback,
            rollback_identity=rollback_identity,
            old_snapshot=old_snapshot,
            old_author_snapshot=old_author_snapshot,
            candidate_snapshot=candidate_snapshot,
            candidate_author_snapshot=candidate_author_snapshot,
        )
        raise CourseRegenerationError(
            f"v4 pair replacement failed: {error}; {recovery}"
        ) from error
    pending_report = _replacement_report(
        result_base,
        rollback=rollback,
        cleanup_status="pending",
    )
    if output is not None:
        try:
            _write_json(output, pending_report)
        except (CourseRegenerationError, OSError) as error:
            if _json_value_matches(output, pending_report):
                raise CourseRegenerationError(
                    "v4 pair was installed and verified and its commit receipt "
                    "is visible, but receipt durability could not be confirmed; "
                    f"cleanup was not started and rollback remains at {rollback}: "
                    f"{error}"
                ) from error
            recovery = _restore_v4_pair(
                live=live,
                live_author=live_author,
                candidate=candidate,
                candidate_author=candidate_author,
                rollback=rollback,
                rollback_identity=rollback_identity,
                old_snapshot=old_snapshot,
                old_author_snapshot=old_author_snapshot,
                candidate_snapshot=candidate_snapshot,
                candidate_author_snapshot=candidate_author_snapshot,
            )
            raise CourseRegenerationError(
                "cannot persist the v4 replacement commit receipt before "
                f"cleanup: {error}; {recovery}"
            ) from error
    try:
        _delete_rollback_root(
            rollback,
            {
                ROLLBACK_LEARNER_NAME: old_snapshot,
                ROLLBACK_AUTHOR_NAME: old_author_snapshot,
            },
            identity=rollback_identity,
        )
    except CourseRegenerationError as error:
        receipt_note = ""
        if output is not None:
            failure_report = _replacement_report(
                result_base,
                rollback=rollback,
                cleanup_status="failed",
            )
            try:
                _write_json(output, failure_report)
                receipt_note = (
                    f"; result output {output} records cleanup_status=failed"
                )
            except (CourseRegenerationError, OSError) as receipt_error:
                receipt_note = (
                    "; the durable pending commit receipt remains"
                    if _json_value_matches(output, pending_report)
                    else "; no matching result receipt could be confirmed"
                ) + (
                    " because recording cleanup failure also failed: "
                    f"{receipt_error}"
                )
        raise CourseRegenerationError(
            "v4 pair was installed and verified, but deleting the old project "
            f"failed: {error}; the new pair remains installed and cleanup "
            f"residue may remain at {rollback}{receipt_note}"
        ) from error
    complete_report = _replacement_report(
        result_base,
        rollback=rollback,
        cleanup_status="complete",
    )
    if output is not None:
        try:
            _write_json(output, complete_report)
        except (CourseRegenerationError, OSError) as error:
            durable_state = (
                "the complete result is visible but its directory sync failed"
                if _json_value_matches(output, complete_report)
                else "the durable pending commit receipt remains"
            )
            raise CourseRegenerationError(
                "v4 pair was installed and verified and the old project was "
                f"deleted, but finalizing result output failed: {error}; "
                f"{durable_state} at {output}"
            ) from error
    return complete_report


def _validate_legacy_to_v4_ready_plan(
    plan: Mapping[str, Any],
    *,
    live: Path,
    author_destination: Path,
    candidate: Path,
    candidate_author: Path,
) -> tuple[Path, str, str]:
    if (
        plan.get("schema_version") != PLAN_SCHEMA_VERSION
        or plan.get("course_schema_version") != 4
        or plan.get("command") != "check"
        or plan.get("status") != "ready"
        or plan.get("migration_kind") != "legacy-to-v4"
        or plan.get("required_action") != "install-v4-learner-author-pair"
        or plan.get("writer_calls") != 0
        or plan.get("chapter_ids") != []
        or plan.get("replacement_policy") != REPLACEMENT_POLICY
        or plan.get("blockers") != []
    ):
        raise CourseRegenerationError(
            "legacy-to-v4 apply requires a ready, blocker-free migration plan"
        )
    if (
        plan.get("course") != str(live)
        or plan.get("author") != str(author_destination)
        or plan.get("candidate_course") != str(candidate)
        or plan.get("candidate_author") != str(candidate_author)
    ):
        raise CourseRegenerationError(
            "legacy-to-v4 plan is for different learner/author paths"
        )
    if author_destination.exists() or author_destination.is_symlink():
        raise CourseRegenerationError(
            "legacy-to-v4 author destination became occupied after check"
        )

    source_schema_version = _legacy_course_schema_version(live)
    baseline = _load_course_baseline(live)
    locked_identity = _legacy_migration_identity(live)
    candidate_identity = _v4_migration_identity(candidate)
    mismatches = _migration_identity_mismatches(
        locked_identity,
        candidate_identity,
    )
    if (
        plan.get("source_course_schema_version") != source_schema_version
        or plan.get("target_course_schema_version") != 4
        or plan.get("legacy_baseline") != _baseline_record(baseline)
        or plan.get("identity") != locked_identity
        or plan.get("candidate_identity") != candidate_identity
        or plan.get("identity_mismatches") != []
        or mismatches
    ):
        raise CourseRegenerationError(
            "legacy or v4 migration identity changed after check"
        )
    migration = _legacy_to_v4_migration_record(live, candidate)
    if plan.get("migration") != migration:
        raise CourseRegenerationError(
            "legacy-to-v4 route migration record changed after check"
        )

    current = _v4_current_contracts()
    if (
        plan.get("current_plugin_version") != current["plugin_version"]
        or plan.get("current_content_contract_sha256")
        != current["content_contract_sha256"]
        or plan.get("current_runtime_contract_sha256")
        != current["runtime_contract_sha256"]
    ):
        raise CourseRegenerationError(
            "the installed v4 Skill changed after migration check"
        )
    candidate_generation = _v4_generation(candidate)
    if (
        plan.get("candidate_generation") != candidate_generation
        or candidate_generation["plugin_version"] != current["plugin_version"]
        or candidate_generation["content_contract_sha256"]
        != current["content_contract_sha256"]
        or candidate_generation["runtime_contract_sha256"]
        != current["runtime_contract_sha256"]
    ):
        raise CourseRegenerationError(
            "v4 migration candidate contracts changed after check"
        )

    live_snapshot = _snapshot(live)
    candidate_snapshot = _snapshot(candidate)
    candidate_author_snapshot = _snapshot(candidate_author)
    if plan.get("live_snapshot_sha256") != live_snapshot:
        raise CourseRegenerationError("legacy course changed after migration check")
    if (
        plan.get("candidate_snapshot_sha256") != candidate_snapshot
        or plan.get("candidate_author_snapshot_sha256")
        != candidate_author_snapshot
    ):
        raise CourseRegenerationError(
            "v4 migration candidate pair changed after check"
        )

    try:
        receipt = validate_v4_receipt(
            candidate,
            author_root=candidate_author,
        )
    except V4VerificationError as error:
        raise CourseRegenerationError(
            f"v4 migration receipt changed or is invalid: {error}"
        ) from error
    if plan.get("candidate_receipt") != _v4_receipt_summary(receipt):
        raise CourseRegenerationError(
            "v4 migration receipt binding changed after check"
        )
    for root, label in (
        (candidate, "candidate learner"),
        (candidate_author, "candidate author"),
    ):
        external = _externally_hardlinked_files(root)
        if external:
            raise CourseRegenerationError(
                f"{label} contains externally hard-linked files: "
                + ", ".join(external[:5])
            )

    rollback = _validated_rollback_path(
        plan.get("rollback_path"),
        root=live,
        snapshots=(live_snapshot,),
        label="legacy migration rollback path",
    )
    return rollback, candidate_snapshot, candidate_author_snapshot


def _restore_failed_legacy_to_v4(
    *,
    live: Path,
    author_destination: Path,
    candidate: Path,
    candidate_author: Path,
    rollback: Path,
    rollback_identity: tuple[int, int],
    old_snapshot: str,
    candidate_snapshot: str,
    candidate_author_snapshot: str,
) -> str:
    errors: list[str] = []
    learner_rollback = rollback / ROLLBACK_LEARNER_NAME

    def matches(path: Path, expected: str, label: str) -> bool:
        try:
            return _matches_snapshot(path, expected)
        except CourseRegenerationError as error:
            errors.append(f"cannot inspect {label}: {error}")
            return False

    old_is_staged = matches(
        learner_rollback,
        old_snapshot,
        "staged legacy learner",
    )
    old_is_live = matches(live, old_snapshot, "current legacy learner")
    if not old_is_staged and not old_is_live:
        errors.append("original legacy learner is not recoverable")

    learner_installed = (
        old_is_staged and (live.exists() or live.is_symlink())
    )
    author_destination_occupied = (
        author_destination.exists() or author_destination.is_symlink()
    )
    author_installed = (
        author_destination_occupied
        and not candidate_author.exists()
        and not candidate_author.is_symlink()
        and matches(
            author_destination,
            candidate_author_snapshot,
            "installed candidate author",
        )
    )
    if learner_installed:
        if candidate.exists() or candidate.is_symlink():
            errors.append("candidate learner path is occupied")
        elif not matches(
            live,
            candidate_snapshot,
            "installed candidate learner",
        ):
            errors.append("installed candidate learner changed")
    if errors:
        return (
            "manual recovery required ("
            + "; ".join(errors)
            + f"); installed paths were preserved and rollback is {rollback}"
        )

    def move(source: Path, destination: Path, message: str) -> bool:
        try:
            os.replace(source, destination)
            return True
        except OSError as error:
            if (
                not source.exists()
                and not source.is_symlink()
                and (destination.exists() or destination.is_symlink())
            ):
                return True
            errors.append(f"{message}: {error}")
            return False

    if author_installed:
        move(
            author_destination,
            candidate_author,
            "cannot move failed author installation back",
        )
    if learner_installed:
        move(
            live,
            candidate,
            "cannot move failed learner installation back",
        )
    if old_is_staged and not live.exists() and not live.is_symlink():
        move(
            learner_rollback,
            live,
            "cannot restore original legacy learner",
        )

    try:
        restored = (
            not live.is_symlink()
            and live.is_dir()
            and _snapshot(live) == old_snapshot
            and not author_destination.exists()
            and not author_destination.is_symlink()
            and candidate.is_dir()
            and _snapshot(candidate) == candidate_snapshot
            and candidate_author.is_dir()
            and _snapshot(candidate_author) == candidate_author_snapshot
        )
    except CourseRegenerationError as error:
        errors.append(f"cannot verify restored migration inputs: {error}")
        restored = False
    _remove_empty_rollback_root(
        rollback,
        errors,
        identity=rollback_identity,
    )
    if restored and not errors:
        return (
            "rolled back legacy root with no author destination or retained "
            "rollback"
        )
    detail = "; ".join(errors) or "restored paths did not match snapshots"
    return f"manual recovery required ({detail}); rollback is {rollback}"


def apply_legacy_to_v4_regeneration(
    course: Path,
    *,
    candidate_course: Path,
    plan_path: Path,
    confirm_stopped: bool,
    accept_replacement: bool,
    result_path: Path | None = None,
) -> dict[str, Any]:
    """Install a receipt-bound v4 pair over one legacy course root."""

    if not confirm_stopped:
        raise CourseRegenerationError("--confirm-stopped is required")
    if not accept_replacement:
        raise CourseRegenerationError("--accept-replacement is required")
    live = _course_root(course, role="live")
    author_destination = live.with_name(f"{live.name}-author")
    candidate, candidate_author = _v4_candidate_pair(
        candidate_course,
        live,
        author_destination,
    )
    plan_file = _safe_output(
        plan_path,
        (live, author_destination, candidate, candidate_author),
        location="legacy-to-v4 plan path",
    )
    plan = _load_plan(plan_file)
    (
        rollback,
        candidate_snapshot,
        candidate_author_snapshot,
    ) = _validate_legacy_to_v4_ready_plan(
        plan,
        live=live,
        author_destination=author_destination,
        candidate=candidate,
        candidate_author=candidate_author,
    )
    old_snapshot = str(plan["live_snapshot_sha256"])
    output = _prepare_apply_result_output(
        result_path,
        roots=(live, author_destination, candidate, candidate_author),
        rollback=rollback,
        location="legacy-to-v4 result output",
    )
    result_base = {
        "schema_version": 2,
        "course_schema_version": 4,
        "migration_kind": "legacy-to-v4",
        "source_course_schema_version": plan[
            "source_course_schema_version"
        ],
        "course": str(live),
        "author": str(author_destination),
        "replacement_policy": REPLACEMENT_POLICY,
        "rollback_path": str(rollback),
        "old_snapshot_sha256": old_snapshot,
        "new_snapshot_sha256": candidate_snapshot,
        "new_author_snapshot_sha256": candidate_author_snapshot,
        "plan_digest": plan["plan_digest"],
        "receipt_validation": "offline",
        "writer_calls_during_apply": 0,
    }
    learner_rollback = rollback / ROLLBACK_LEARNER_NAME
    _preflight_rollback_deletion(live, old_snapshot)
    rollback_identity = _create_rollback_root(rollback)
    try:
        os.replace(live, learner_rollback)
        for root, expected, label in (
            (candidate, candidate_snapshot, "candidate learner"),
            (
                candidate_author,
                candidate_author_snapshot,
                "candidate author",
            ),
        ):
            external = _externally_hardlinked_files(root)
            if external or _snapshot(root) != expected:
                detail = (
                    "externally hard-linked files: " + ", ".join(external[:5])
                    if external
                    else "snapshot changed"
                )
                raise CourseRegenerationError(f"{label} {detail}")
        if author_destination.exists() or author_destination.is_symlink():
            raise CourseRegenerationError(
                "author destination was occupied during migration"
            )
        os.replace(candidate, live)
        os.replace(candidate_author, author_destination)
        if (
            _snapshot(learner_rollback) != old_snapshot
            or _snapshot(live) != candidate_snapshot
            or _snapshot(author_destination) != candidate_author_snapshot
        ):
            raise CourseRegenerationError(
                "post-swap legacy-to-v4 snapshots do not match"
            )
        validate_v4_receipt(live, author_root=author_destination)
    except (OSError, CourseRegenerationError, V4VerificationError) as error:
        recovery = _restore_failed_legacy_to_v4(
            live=live,
            author_destination=author_destination,
            candidate=candidate,
            candidate_author=candidate_author,
            rollback=rollback,
            rollback_identity=rollback_identity,
            old_snapshot=old_snapshot,
            candidate_snapshot=candidate_snapshot,
            candidate_author_snapshot=candidate_author_snapshot,
        )
        raise CourseRegenerationError(
            f"legacy-to-v4 pair replacement failed: {error}; {recovery}"
        ) from error
    pending_report = _replacement_report(
        result_base,
        rollback=rollback,
        cleanup_status="pending",
    )
    if output is not None:
        try:
            _write_json(output, pending_report)
        except (CourseRegenerationError, OSError) as error:
            if _json_value_matches(output, pending_report):
                raise CourseRegenerationError(
                    "the v4 pair was installed over the legacy course and its "
                    "commit receipt is visible, but receipt durability could "
                    "not be confirmed; cleanup was not started and rollback "
                    f"remains at {rollback}: {error}"
                ) from error
            recovery = _restore_failed_legacy_to_v4(
                live=live,
                author_destination=author_destination,
                candidate=candidate,
                candidate_author=candidate_author,
                rollback=rollback,
                rollback_identity=rollback_identity,
                old_snapshot=old_snapshot,
                candidate_snapshot=candidate_snapshot,
                candidate_author_snapshot=candidate_author_snapshot,
            )
            raise CourseRegenerationError(
                "cannot persist the legacy-to-v4 replacement commit receipt "
                f"before cleanup: {error}; {recovery}"
            ) from error
    try:
        _delete_rollback_root(
            rollback,
            {ROLLBACK_LEARNER_NAME: old_snapshot},
            identity=rollback_identity,
        )
    except CourseRegenerationError as error:
        receipt_note = ""
        if output is not None:
            failure_report = _replacement_report(
                result_base,
                rollback=rollback,
                cleanup_status="failed",
            )
            try:
                _write_json(output, failure_report)
                receipt_note = (
                    f"; result output {output} records cleanup_status=failed"
                )
            except (CourseRegenerationError, OSError) as receipt_error:
                receipt_note = (
                    "; the durable pending commit receipt remains"
                    if _json_value_matches(output, pending_report)
                    else "; no matching result receipt could be confirmed"
                ) + (
                    " because recording cleanup failure also failed: "
                    f"{receipt_error}"
                )
        raise CourseRegenerationError(
            "v4 pair was installed and verified, but deleting the old legacy "
            f"project failed: {error}; the new pair remains installed and "
            f"cleanup residue may remain at {rollback}{receipt_note}"
        ) from error
    complete_report = _replacement_report(
        result_base,
        rollback=rollback,
        cleanup_status="complete",
    )
    if output is not None:
        try:
            _write_json(output, complete_report)
        except (CourseRegenerationError, OSError) as error:
            durable_state = (
                "the complete result is visible but its directory sync failed"
                if _json_value_matches(output, complete_report)
                else "the durable pending commit receipt remains"
            )
            raise CourseRegenerationError(
                "the v4 pair was installed over the legacy course and the old "
                f"project was deleted, but finalizing result output failed: "
                f"{error}; {durable_state} at {output}"
            ) from error
    return complete_report


def _validate_ready_plan(
    plan: Mapping[str, Any],
    live: Path,
    candidate: Path,
    runtime: RuntimeContract,
    live_baseline: CourseBaseline,
    candidate_baseline: CourseBaseline,
) -> tuple[Path, str]:
    if (
        plan.get("schema_version") != PLAN_SCHEMA_VERSION
        or plan.get("command") != "check"
        or plan.get("status") != "ready"
        or plan.get("replacement_policy") != REPLACEMENT_POLICY
    ):
        raise CourseRegenerationError("apply requires a ready regeneration plan")
    if plan.get("course") != str(live) or plan.get("candidate_course") != str(candidate):
        raise CourseRegenerationError("regeneration plan is for different course paths")
    if plan.get("blockers") != []:
        raise CourseRegenerationError("ready regeneration plan must have no blockers")
    if (
        plan.get("current_plugin_version") != runtime.plugin_version
        or plan.get("current_authoring_contract_sha256")
        != runtime.authoring_contract_sha256
    ):
        raise CourseRegenerationError("the installed Skill changed after check")
    live_identity = _identity(live)
    candidate_identity = _identity(candidate)
    if plan.get("identity") != live_identity:
        raise CourseRegenerationError("live course identity changed after check")
    if plan.get("candidate_identity") != candidate_identity:
        raise CourseRegenerationError("candidate identity changed after check")
    if candidate_identity != live_identity:
        raise CourseRegenerationError("candidate changed the locked course identity")
    live_route_intent = _route_intent(
        live,
        require_regeneration_metadata=False,
    )
    candidate_route_intent = _route_intent(
        candidate,
        require_regeneration_metadata=candidate_baseline.schema_version >= 2,
    )
    if plan.get("route_intent") != live_route_intent:
        raise CourseRegenerationError("live course route intent changed after check")
    if plan.get("candidate_route_intent") != candidate_route_intent:
        raise CourseRegenerationError("candidate route intent changed after check")
    locked_intent = plan["route_intent"]
    candidate_intent = plan["candidate_route_intent"]
    if not isinstance(locked_intent, Mapping) or not isinstance(
        candidate_intent, Mapping
    ):
        raise CourseRegenerationError("regeneration plan has invalid route intent")
    if _route_intent_changed(locked_intent, candidate_intent):
        raise CourseRegenerationError("candidate changed the locked route intent")
    # Git may refresh index stat metadata while proving cleanliness. Do that
    # before comparing the byte-for-byte candidate snapshot.
    _require_fresh_candidate(candidate)
    if plan.get("live_snapshot_sha256") != _snapshot(live):
        raise CourseRegenerationError("live course changed after check")
    if plan.get("candidate_snapshot_sha256") != _snapshot(candidate):
        raise CourseRegenerationError("candidate course changed after check")
    live_source = _hash_source(live)
    candidate_source = _hash_source(candidate)
    if plan.get("live_canonical_source_sha256") != live_source:
        raise CourseRegenerationError("live canonical source changed after check")
    if plan.get("candidate_canonical_source_sha256") != candidate_source:
        raise CourseRegenerationError("candidate canonical source changed after check")
    if candidate_source == live_source:
        raise CourseRegenerationError("candidate canonical source is unchanged")
    material_diff = _material_diff(live, candidate)
    if plan.get("material_learner_facing_diff") != material_diff:
        raise CourseRegenerationError("learner-facing diff changed after check")
    if material_diff.get("changed") is not True:
        raise CourseRegenerationError("candidate has no material learner-facing change")
    verification = plan.get("full_verification")
    if not isinstance(verification, Mapping) or verification.get("passed") is not True:
        raise CourseRegenerationError("plan does not contain a passing full verification")
    pre_verification_tree = _tree_state(candidate)
    current_verification = _run_full_verifier(candidate)
    if current_verification.get("passed") is not True:
        raise CourseRegenerationError("candidate failed full verification during apply")
    _require_fresh_candidate(candidate)
    unexpected_changes = _unexpected_verifier_changes(
        pre_verification_tree,
        _tree_state(candidate),
    )
    if unexpected_changes:
        raise CourseRegenerationError(
            "verification created or changed non-runtime files during apply: "
            + ", ".join(unexpected_changes[:5])
        )
    if plan.get("live_snapshot_sha256") != _snapshot(live):
        raise CourseRegenerationError("live course changed during apply validation")
    # Full verification is allowed to refresh Git-ignored runtime artifacts.
    # Revalidate every authored contract after it runs, then bind the atomic
    # replacement to the exact post-verification tree that will be moved.
    post_verification_baseline = _candidate_baseline(candidate, runtime)
    if post_verification_baseline != candidate_baseline:
        raise CourseRegenerationError(
            "candidate provenance changed during apply verification"
        )
    if _identity(candidate) != candidate_identity:
        raise CourseRegenerationError(
            "candidate identity changed during apply verification"
        )
    if _route_intent(
        candidate,
        require_regeneration_metadata=post_verification_baseline.schema_version >= 2,
    ) != candidate_route_intent:
        raise CourseRegenerationError(
            "candidate route intent changed during apply verification"
        )
    if _material_diff(live, candidate) != material_diff:
        raise CourseRegenerationError(
            "learner-facing diff changed during apply verification"
        )
    post_verification_snapshot = _snapshot(candidate)
    rollback = _validated_rollback_path(
        plan.get("rollback_path"),
        root=live,
        snapshots=(str(plan["live_snapshot_sha256"]),),
        label="course rollback path",
    )
    return rollback, post_verification_snapshot


def _restore_after_failed_swap(
    live: Path,
    candidate: Path,
    rollback: Path,
    rollback_identity: tuple[int, int],
    old_snapshot: str,
    candidate_snapshot: str,
) -> str:
    recovery_errors: list[str] = []
    learner_rollback = rollback / ROLLBACK_LEARNER_NAME

    def matches(path: Path, expected: str, label: str) -> bool:
        try:
            return _matches_snapshot(path, expected)
        except CourseRegenerationError as error:
            recovery_errors.append(f"cannot inspect {label}: {error}")
            return False

    old_is_staged = matches(
        learner_rollback,
        old_snapshot,
        "staged original course",
    )
    old_is_live = matches(live, old_snapshot, "current original course")
    if not old_is_staged and not old_is_live:
        recovery_errors.append("original course is not recoverable")

    candidate_installed = old_is_staged and (
        live.exists() or live.is_symlink()
    )
    if candidate_installed:
        if candidate.exists() or candidate.is_symlink():
            recovery_errors.append("candidate path is occupied")
        elif not matches(live, candidate_snapshot, "installed candidate"):
            recovery_errors.append("installed candidate changed")
    if recovery_errors:
        return (
            "manual recovery required ("
            + "; ".join(recovery_errors)
            + f"); installed paths were preserved and rollback is {rollback}"
        )

    if candidate_installed:
        try:
            os.replace(live, candidate)
        except OSError as error:
            if (
                live.exists()
                or live.is_symlink()
                or (
                    not candidate.exists()
                    and not candidate.is_symlink()
                )
            ):
                recovery_errors.append(
                    f"cannot move failed candidate back: {error}"
                )
    if (
        old_is_staged
        and not live.exists()
        and not live.is_symlink()
    ):
        try:
            os.replace(learner_rollback, live)
        except OSError as error:
            if (
                learner_rollback.exists()
                or learner_rollback.is_symlink()
                or (
                    not live.exists()
                    and not live.is_symlink()
                )
            ):
                recovery_errors.append(
                    f"cannot restore original course: {error}"
                )
    try:
        restored = _matches_snapshot(live, old_snapshot)
        if candidate_installed and not _matches_snapshot(
            candidate,
            candidate_snapshot,
        ):
            recovery_errors.append("restored candidate changed")
    except CourseRegenerationError as error:
        recovery_errors.append(f"cannot verify restored paths: {error}")
        restored = False
    _remove_empty_rollback_root(
        rollback,
        recovery_errors,
        identity=rollback_identity,
    )
    if restored and not recovery_errors:
        return "rolled back with no retained rollback"
    detail = "; ".join(recovery_errors) or "restored tree did not match snapshot"
    return f"manual recovery required ({detail}); rollback is {rollback}"


def apply_regeneration(
    course: Path,
    *,
    candidate_course: Path,
    plan_path: Path,
    confirm_stopped: bool,
    accept_replacement: bool,
    result_path: Path | None = None,
) -> dict[str, Any]:
    if not confirm_stopped:
        raise CourseRegenerationError("--confirm-stopped is required")
    if not accept_replacement:
        raise CourseRegenerationError("--accept-replacement is required")
    live = _course_root(course, role="live")
    if _looks_like_v4_course(candidate_course):
        return apply_legacy_to_v4_regeneration(
            live,
            candidate_course=candidate_course,
            plan_path=plan_path,
            confirm_stopped=confirm_stopped,
            accept_replacement=accept_replacement,
            result_path=result_path,
        )
    candidate = _candidate_root(candidate_course, live)
    plan_file = _safe_output(plan_path, (live, candidate), location="plan path")
    plan = _load_plan(plan_file)
    runtime = _current_runtime()
    live_baseline = _load_course_baseline(live)
    status, _ = _regeneration_state(live_baseline, runtime)
    if status != "regeneration_required":
        raise CourseRegenerationError("live course no longer requires regeneration")
    candidate_baseline = _candidate_baseline(candidate, runtime)
    rollback, candidate_snapshot = _validate_ready_plan(
        plan,
        live,
        candidate,
        runtime,
        live_baseline,
        candidate_baseline,
    )
    old_snapshot = str(plan["live_snapshot_sha256"])
    output = _prepare_apply_result_output(
        result_path,
        roots=(live, candidate),
        rollback=rollback,
        location="result output",
    )
    result_base = {
        "schema_version": 2,
        "course": str(live),
        "replacement_policy": REPLACEMENT_POLICY,
        "rollback_path": str(rollback),
        "old_snapshot_sha256": old_snapshot,
        "new_snapshot_sha256": candidate_snapshot,
        "plan_digest": plan["plan_digest"],
        "fresh_baseline": True,
        "progress_state": "empty",
    }
    learner_rollback = rollback / ROLLBACK_LEARNER_NAME
    _preflight_rollback_deletion(live, old_snapshot)
    rollback_identity = _create_rollback_root(rollback)

    try:
        os.replace(live, learner_rollback)
    except OSError as error:
        recovery = _restore_after_failed_swap(
            live,
            candidate,
            rollback,
            rollback_identity,
            old_snapshot,
            candidate_snapshot,
        )
        raise CourseRegenerationError(
            f"cannot stage the old course for replacement: {error}; {recovery}"
        ) from error
    try:
        hardlinked_files = _externally_hardlinked_files(candidate)
        if hardlinked_files or _snapshot(candidate) != candidate_snapshot:
            detail = (
                "hard-linked files: " + ", ".join(hardlinked_files[:5])
                if hardlinked_files
                else "candidate snapshot changed"
            )
            raise CourseRegenerationError(detail)
    except CourseRegenerationError as error:
        recovery = _restore_after_failed_swap(
            live,
            candidate,
            rollback,
            rollback_identity,
            old_snapshot,
            candidate_snapshot,
        )
        raise CourseRegenerationError(
            f"candidate changed before replacement: {error}; {recovery}"
        ) from error
    try:
        os.replace(candidate, live)
    except OSError as error:
        recovery = _restore_after_failed_swap(
            live,
            candidate,
            rollback,
            rollback_identity,
            old_snapshot,
            candidate_snapshot,
        )
        raise CourseRegenerationError(
            f"candidate replacement failed: {error}; {recovery}"
        ) from error

    try:
        hardlinked_files = _externally_hardlinked_files(live)
        if hardlinked_files:
            raise CourseRegenerationError(
                "installed candidate contains hard-linked files: "
                + ", ".join(hardlinked_files[:5])
            )
        snapshots_match = (
            _snapshot(learner_rollback) == old_snapshot
            and _snapshot(live) == candidate_snapshot
        )
    except CourseRegenerationError as error:
        recovery = _restore_after_failed_swap(
            live,
            candidate,
            rollback,
            rollback_identity,
            old_snapshot,
            candidate_snapshot,
        )
        raise CourseRegenerationError(
            f"post-swap snapshot verification failed: {error}; {recovery}"
        ) from error
    if not snapshots_match:
        recovery = _restore_after_failed_swap(
            live,
            candidate,
            rollback,
            rollback_identity,
            old_snapshot,
            candidate_snapshot,
        )
        raise CourseRegenerationError(
            f"post-swap snapshot verification failed; {recovery}"
        )
    pending_report = _replacement_report(
        result_base,
        rollback=rollback,
        cleanup_status="pending",
    )
    if output is not None:
        try:
            _write_json(output, pending_report)
        except (CourseRegenerationError, OSError) as error:
            if _json_value_matches(output, pending_report):
                raise CourseRegenerationError(
                    "replacement was installed and verified and its commit "
                    "receipt is visible, but receipt durability could not be "
                    "confirmed; cleanup was not started and rollback remains "
                    f"at {rollback}: {error}"
                ) from error
            recovery = _restore_after_failed_swap(
                live,
                candidate,
                rollback,
                rollback_identity,
                old_snapshot,
                candidate_snapshot,
            )
            raise CourseRegenerationError(
                "cannot persist the replacement commit receipt before "
                f"cleanup: {error}; {recovery}"
            ) from error
    try:
        _delete_rollback_root(
            rollback,
            {ROLLBACK_LEARNER_NAME: old_snapshot},
            identity=rollback_identity,
        )
    except CourseRegenerationError as error:
        receipt_note = ""
        if output is not None:
            failure_report = _replacement_report(
                result_base,
                rollback=rollback,
                cleanup_status="failed",
            )
            try:
                _write_json(output, failure_report)
                receipt_note = (
                    f"; result output {output} records cleanup_status=failed"
                )
            except (CourseRegenerationError, OSError) as receipt_error:
                receipt_note = (
                    "; the durable pending commit receipt remains"
                    if _json_value_matches(output, pending_report)
                    else "; no matching result receipt could be confirmed"
                ) + (
                    " because recording cleanup failure also failed: "
                    f"{receipt_error}"
                )
        raise CourseRegenerationError(
            "replacement was installed and verified, but deleting the old "
            f"course failed: {error}; the new course remains installed and "
            f"cleanup residue may remain at {rollback}{receipt_note}"
        ) from error
    complete_report = _replacement_report(
        result_base,
        rollback=rollback,
        cleanup_status="complete",
    )
    if output is not None:
        try:
            _write_json(output, complete_report)
        except (CourseRegenerationError, OSError) as error:
            durable_state = (
                "the complete result is visible but its directory sync failed"
                if _json_value_matches(output, complete_report)
                else "the durable pending commit receipt remains"
            )
            raise CourseRegenerationError(
                "replacement was installed and verified and the old course was "
                f"deleted, but finalizing result output failed: {error}; "
                f"{durable_state} at {output}"
            ) from error
    return complete_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check whether full regeneration is required")
    check.add_argument("course", type=Path)
    check.add_argument("--candidate-course", type=Path)
    check.add_argument(
        "--chapter-request",
        type=Path,
        help="bind a chapter command request to one targeted v4 candidate",
    )
    check.add_argument("--json", dest="json_path", type=Path, required=True)
    readiness = commands.add_parser(
        "readiness", help="reuse only unchanged trusted readiness decisions"
    )
    readiness.add_argument("course", type=Path)
    readiness.add_argument("--route", type=Path, required=True)
    readiness.add_argument("--json", dest="json_path", type=Path, required=True)
    chapter = commands.add_parser(
        "chapter",
        help="prepare one schema-v4 chapter-only regeneration request",
    )
    chapter.add_argument("course", type=Path)
    chapter.add_argument("--chapter", dest="chapter_id", required=True)
    chapter.add_argument("--reason", required=True)
    chapter.add_argument("--json", dest="json_path", type=Path, required=True)
    apply = commands.add_parser("apply", help="atomically install a verified replacement")
    apply.add_argument("course", type=Path)
    apply.add_argument("--candidate-course", type=Path, required=True)
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--confirm-stopped", action="store_true")
    apply.add_argument("--accept-replacement", action="store_true")
    apply.add_argument("--json", dest="json_path", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "check":
            if (
                args.chapter_request is not None
                and args.candidate_course is None
            ):
                raise CourseRegenerationError(
                    "--chapter-request requires --candidate-course"
                )
            if _looks_like_v4_course(args.course):
                live, live_author = _v4_pair(args.course, role="live")
                if args.candidate_course is None:
                    candidate = None
                    roots = (live, live_author)
                else:
                    candidate, candidate_author = _v4_candidate_pair(
                        args.candidate_course,
                        live,
                        live_author,
                    )
                    roots = (
                        live,
                        live_author,
                        candidate,
                        candidate_author,
                    )
                output = _safe_output(
                    args.json_path,
                    roots,
                    location="v4 plan output",
                )
                chapter_request: dict[str, Any] | None = None
                if args.chapter_request is not None:
                    request_path = _safe_output(
                        args.chapter_request,
                        roots,
                        location="chapter request path",
                    )
                    if request_path == output:
                        raise CourseRegenerationError(
                            "chapter request and plan output must differ"
                        )
                    chapter_request = _read_json(
                        request_path,
                        "chapter regeneration request",
                    )
                output = _preflight_json_output(output)
                report = (
                    plan_v4_targeted_regeneration(
                        live,
                        candidate_course=candidate,
                        chapter_request=chapter_request,
                    )
                    if chapter_request is not None and candidate is not None
                    else plan_v4_regeneration(
                        live,
                        candidate_course=candidate,
                    )
                )
            else:
                if args.chapter_request is not None:
                    raise CourseRegenerationError(
                        "--chapter-request is available only for schema-v4 courses"
                    )
                live = _course_root(args.course, role="live")
                if (
                    args.candidate_course is not None
                    and _looks_like_v4_course(args.candidate_course)
                ):
                    author_destination = live.with_name(f"{live.name}-author")
                    candidate, candidate_author = _v4_candidate_pair(
                        args.candidate_course,
                        live,
                        author_destination,
                    )
                    roots = (
                        live,
                        author_destination,
                        candidate,
                        candidate_author,
                    )
                else:
                    candidate = (
                        _candidate_root(args.candidate_course, live)
                        if args.candidate_course is not None
                        else None
                    )
                    roots = (live,) if candidate is None else (live, candidate)
                output = _safe_output(
                    args.json_path,
                    roots,
                    location="plan output",
                )
                output = _preflight_json_output(output)
                report = plan_regeneration(live, candidate_course=candidate)
        elif args.command == "readiness":
            live = _course_root(args.course, role="live")
            output = _safe_output(
                args.json_path, (live,), location="trusted readiness output"
            )
            output = _preflight_json_output(output)
            report = plan_readiness_reuse(live, args.route)
        elif args.command == "chapter":
            live = _v4_course_root(args.course)
            author = live.with_name(f"{live.name}-author")
            output = _safe_output(
                args.json_path,
                (live, author),
                location="chapter regeneration output",
            )
            output = _preflight_json_output(output)
            report = plan_v4_chapter_regeneration(
                live,
                chapter_id=args.chapter_id,
                reason=args.reason,
            )
        else:
            if _looks_like_v4_course(args.course):
                live, live_author = _v4_pair(args.course, role="live")
                candidate, candidate_author = _v4_candidate_pair(
                    args.candidate_course,
                    live,
                    live_author,
                )
                roots = (live, live_author, candidate, candidate_author)
                output = _safe_output(
                    args.json_path,
                    roots,
                    location="v4 result output",
                )
                plan_preview = _load_plan(
                    _safe_output(
                        args.plan,
                        roots,
                        location="v4 plan path",
                    )
                )
                rollback_raw = plan_preview.get("rollback_path")
                if isinstance(rollback_raw, str):
                    planned_rollback = Path(rollback_raw)
                    if (
                        output == planned_rollback
                        or planned_rollback in output.parents
                    ):
                        raise CourseRegenerationError(
                            "result output must be outside the transient v4 "
                            "rollback path"
                        )
                output = _preflight_json_output(output)
                report = apply_v4_regeneration(
                    live,
                    candidate_course=candidate,
                    plan_path=args.plan,
                    confirm_stopped=args.confirm_stopped,
                    accept_replacement=args.accept_replacement,
                    result_path=output,
                )
            else:
                live = _course_root(args.course, role="live")
                if _looks_like_v4_course(args.candidate_course):
                    author_destination = live.with_name(f"{live.name}-author")
                    candidate, candidate_author = _v4_candidate_pair(
                        args.candidate_course,
                        live,
                        author_destination,
                    )
                    roots = (
                        live,
                        author_destination,
                        candidate,
                        candidate_author,
                    )
                else:
                    candidate = _candidate_root(args.candidate_course, live)
                    roots = (live, candidate)
                output = _safe_output(
                    args.json_path, roots, location="result output"
                )
                plan_preview = _load_plan(
                    _safe_output(args.plan, roots, location="plan path")
                )
                rollback_raw = plan_preview.get("rollback_path")
                if isinstance(rollback_raw, str):
                    planned_rollback = Path(rollback_raw)
                    if (
                        output == planned_rollback
                        or planned_rollback in output.parents
                    ):
                        raise CourseRegenerationError(
                            "result output must be outside the transient course "
                            "rollback path"
                        )
                output = _preflight_json_output(output)
                report = apply_regeneration(
                    live,
                    candidate_course=candidate,
                    plan_path=args.plan,
                    confirm_stopped=args.confirm_stopped,
                    accept_replacement=args.accept_replacement,
                    result_path=output,
                )
        if args.command != "apply":
            _write_json(output, report)
    except (CourseRegenerationError, OSError) as error:
        print(f"course regeneration failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
