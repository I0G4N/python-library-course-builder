#!/usr/bin/env python3
"""Plan and atomically replace an old generated course with a fresh one."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any

from assess_readiness import ReadinessValidationError, build_route_contract
from course_provenance import (
    PROVENANCE_RELATIVE_PATH,
    ProvenanceError,
    load_generation_provenance,
    load_regeneration_metadata,
    trusted_readiness_reuse,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST_PATH = SKILL_ROOT.parents[1] / ".codex-plugin" / "plugin.json"
VERIFIER_PATH = Path(__file__).with_name("verify_learning_project.py")
SOURCE_PATH = Path("platform/course/source")
STATE_PATH = Path("labs/.coursekit/state.json")
PLAN_SCHEMA_VERSION = 1
GENERATED_BASELINE_MESSAGE = "coursekit: generated baseline"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
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
            temporary = Path(stream.name)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
            raise CourseRegenerationError(
                "plugin version collision: the same version has a different "
                "authoring-contract fingerprint"
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


def _snapshot(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, kind, value in _scan_tree(root):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(kind.encode("ascii"))
        digest.update(b"\0")
        digest.update(value)
        digest.update(b"\0")
    return digest.hexdigest()


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


def _backup_path(live: Path, live_snapshot: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return live.with_name(
        f"{live.name}.coursekit-backup-{timestamp}-{live_snapshot[:8]}"
    )


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
    backup = _backup_path(live, live_snapshot)
    if backup.exists() or backup.is_symlink():
        raise CourseRegenerationError(f"planned backup path already exists: {backup}")
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
            "backup_path": str(backup),
            "blockers": blockers,
        }
    )
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
    backup_raw = plan.get("backup_path")
    if not isinstance(backup_raw, str):
        raise CourseRegenerationError("plan has no backup path")
    backup = Path(backup_raw)
    expected_name = re.compile(
        re.escape(live.name)
        + r"\.coursekit-backup-\d{8}T\d{6}Z-"
        + re.escape(str(plan["live_snapshot_sha256"])[:8])
    )
    if (
        not backup.is_absolute()
        or backup.parent != live.parent
        or expected_name.fullmatch(backup.name) is None
        or backup.exists()
        or backup.is_symlink()
    ):
        raise CourseRegenerationError("planned backup path is unsafe or already exists")
    return backup, post_verification_snapshot


def _restore_after_failed_swap(
    live: Path, candidate: Path, backup: Path, old_snapshot: str
) -> str:
    recovery_errors: list[str] = []
    if live.exists() or live.is_symlink():
        if candidate.exists() or candidate.is_symlink():
            recovery_errors.append("candidate path is occupied")
        else:
            try:
                os.replace(live, candidate)
            except OSError as error:
                recovery_errors.append(f"cannot move failed candidate back: {error}")
    if not live.exists() and not live.is_symlink():
        try:
            os.replace(backup, live)
        except OSError as error:
            recovery_errors.append(f"cannot restore backup: {error}")
    if live.is_dir() and _snapshot(live) == old_snapshot:
        return "rolled back"
    detail = "; ".join(recovery_errors) or "restored tree did not match snapshot"
    return f"manual recovery required ({detail}); backup remains at {backup}"


def apply_regeneration(
    course: Path,
    *,
    candidate_course: Path,
    plan_path: Path,
    confirm_stopped: bool,
    accept_replacement: bool,
) -> dict[str, Any]:
    if not confirm_stopped:
        raise CourseRegenerationError("--confirm-stopped is required")
    if not accept_replacement:
        raise CourseRegenerationError("--accept-replacement is required")
    live = _course_root(course, role="live")
    candidate = _candidate_root(candidate_course, live)
    plan_file = _safe_output(plan_path, (live, candidate), location="plan path")
    plan = _load_plan(plan_file)
    runtime = _current_runtime()
    live_baseline = _load_course_baseline(live)
    status, _ = _regeneration_state(live_baseline, runtime)
    if status != "regeneration_required":
        raise CourseRegenerationError("live course no longer requires regeneration")
    candidate_baseline = _candidate_baseline(candidate, runtime)
    backup, candidate_snapshot = _validate_ready_plan(
        plan,
        live,
        candidate,
        runtime,
        live_baseline,
        candidate_baseline,
    )
    old_snapshot = str(plan["live_snapshot_sha256"])

    try:
        os.replace(live, backup)
    except OSError as error:
        recovery = _restore_after_failed_swap(
            live, candidate, backup, old_snapshot
        )
        raise CourseRegenerationError(
            f"cannot create complete course backup: {error}; {recovery}"
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
            live, candidate, backup, old_snapshot
        )
        raise CourseRegenerationError(
            f"candidate changed before replacement: {error}; {recovery}"
        ) from error
    try:
        os.replace(candidate, live)
    except OSError as error:
        recovery = _restore_after_failed_swap(live, candidate, backup, old_snapshot)
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
            _snapshot(backup) == old_snapshot
            and _snapshot(live) == candidate_snapshot
        )
    except CourseRegenerationError as error:
        recovery = _restore_after_failed_swap(
            live, candidate, backup, old_snapshot
        )
        raise CourseRegenerationError(
            f"post-swap snapshot verification failed: {error}; {recovery}"
        ) from error
    if not snapshots_match:
        recovery = _restore_after_failed_swap(
            live, candidate, backup, old_snapshot
        )
        raise CourseRegenerationError(
            f"post-swap snapshot verification failed; {recovery}"
        )
    return {
        "schema_version": 1,
        "status": "applied",
        "course": str(live),
        "backup_path": str(backup),
        "old_snapshot_sha256": old_snapshot,
        "new_snapshot_sha256": candidate_snapshot,
        "plan_digest": plan["plan_digest"],
        "fresh_baseline": True,
        "progress_state": "empty",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check whether full regeneration is required")
    check.add_argument("course", type=Path)
    check.add_argument("--candidate-course", type=Path)
    check.add_argument("--json", dest="json_path", type=Path, required=True)
    readiness = commands.add_parser(
        "readiness", help="reuse only unchanged trusted readiness decisions"
    )
    readiness.add_argument("course", type=Path)
    readiness.add_argument("--route", type=Path, required=True)
    readiness.add_argument("--json", dest="json_path", type=Path, required=True)
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
            live = _course_root(args.course, role="live")
            candidate = (
                _candidate_root(args.candidate_course, live)
                if args.candidate_course is not None
                else None
            )
            output = _safe_output(
                args.json_path,
                (live,) if candidate is None else (live, candidate),
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
        else:
            live = _course_root(args.course, role="live")
            candidate = _candidate_root(args.candidate_course, live)
            output = _safe_output(
                args.json_path, (live, candidate), location="result output"
            )
            plan_preview = _load_plan(
                _safe_output(args.plan, (live, candidate), location="plan path")
            )
            backup_raw = plan_preview.get("backup_path")
            if isinstance(backup_raw, str):
                planned_backup = Path(backup_raw)
                if output == planned_backup or planned_backup in output.parents:
                    raise CourseRegenerationError(
                        "result output must be outside the permanent course backup"
                    )
            output = _preflight_json_output(output)
            report = apply_regeneration(
                live,
                candidate_course=candidate,
                plan_path=args.plan,
                confirm_stopped=args.confirm_stopped,
                accept_replacement=args.accept_replacement,
            )
        _write_json(output, report)
    except (CourseRegenerationError, OSError) as error:
        print(f"course regeneration failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
