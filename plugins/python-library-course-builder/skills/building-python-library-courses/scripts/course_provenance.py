#!/usr/bin/env python3
"""Build and validate deterministic provenance for generated CourseKit courses."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "course-template"
MIGRATION_REGISTRY_PATH = SKILL_ROOT / "references" / "course-migrations.json"
PLUGIN_MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
PROVENANCE_RELATIVE_PATH = "platform/coursekit-generation.json"

PROVENANCE_SCHEMA_VERSION = 1
MIGRATION_REGISTRY_SCHEMA_VERSION = 1
PLUGIN_NAME = "python-library-course-builder"
SKILL_NAME = "building-python-library-courses"
MANAGED_ROLES = {"template", "compiled", "workspace-runtime"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")

TREE_IGNORE_NAMES = {
    ".DS_Store",
    ".coverage",
    ".coursekit-artifacts.json",
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
}


class ProvenanceError(RuntimeError):
    """A provenance document or migration registry violated its contract."""


def hash_file(path: Path) -> str:
    """Return the SHA-256 digest for one regular, non-symlink file."""

    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ProvenanceError(f"cannot hash non-regular file: {candidate}")
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_ignores(ignore: Iterable[str] | None) -> tuple[str, ...]:
    values: list[str] = []
    for raw in ignore or ():
        value = str(raw).replace("\\", "/").strip("/")
        if not value or value == ".":
            continue
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ProvenanceError(f"unsafe hash-tree ignore path: {raw}")
        values.append(path.as_posix())
    return tuple(sorted(set(values)))


def _tree_path_is_ignored(relative: str, ignores: tuple[str, ...]) -> bool:
    parts = PurePosixPath(relative).parts
    for ignored in ignores:
        if "/" not in ignored and ignored in parts:
            return True
        if relative == ignored or relative.startswith(ignored + "/"):
            return True
    return False


def hash_tree(root: Path, ignore: Iterable[str] | None = None) -> str:
    """Hash relative paths and file digests in a tree deterministically."""

    directory = Path(root)
    if directory.is_symlink() or not directory.is_dir():
        raise ProvenanceError(f"cannot hash non-directory tree: {directory}")
    ignores = _normalized_ignores(ignore)
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if _tree_path_is_ignored(relative, ignores):
            continue
        if path.is_symlink():
            raise ProvenanceError(f"hash tree cannot contain symlinks: {relative}")
        if not path.is_file():
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hash_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _require_exact_keys(
    value: object,
    expected: set[str],
    location: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProvenanceError(f"{location} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ProvenanceError(f"{location} has invalid keys: {'; '.join(details)}")
    return value


def _require_nonempty_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProvenanceError(f"{location} must be a non-empty string")
    return value


def _require_sha256(value: object, location: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ProvenanceError(f"{location} must be a lowercase SHA-256 digest")
    return value


def _require_version(value: object, location: str) -> str:
    text = _require_nonempty_string(value, location)
    if VERSION_PATTERN.fullmatch(text) is None:
        raise ProvenanceError(f"{location} must be a semantic version")
    return text


def _require_relative_path(value: object, location: str) -> str:
    text = _require_nonempty_string(value, location)
    if "\\" in text:
        raise ProvenanceError(f"{location} must use POSIX separators")
    path = PurePosixPath(text)
    if path.is_absolute() or path.as_posix() != text or ".." in path.parts:
        raise ProvenanceError(f"{location} must be a safe relative POSIX path")
    return text


def _validate_migration_registry(value: object) -> dict[str, Any]:
    registry = _require_exact_keys(
        value,
        {"schema_version", "migrations"},
        "migration registry",
    )
    if registry["schema_version"] != MIGRATION_REGISTRY_SCHEMA_VERSION:
        raise ProvenanceError("unsupported migration registry schema_version")
    migrations = registry["migrations"]
    if not isinstance(migrations, list) or not migrations:
        raise ProvenanceError("migration registry migrations must be a non-empty list")
    expected_keys = {
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
    identifiers: set[str] = set()
    for index, raw_entry in enumerate(migrations):
        location = f"migration registry migrations[{index}]"
        entry = _require_exact_keys(raw_entry, expected_keys, location)
        identifier = _require_nonempty_string(entry["id"], f"{location}.id")
        if identifier in identifiers:
            raise ProvenanceError(f"duplicate migration id: {identifier}")
        identifiers.add(identifier)
        if entry["course_impacting"] is not True:
            raise ProvenanceError(f"{location}.course_impacting must be true")
        if entry["impact"] not in {"platform", "content"}:
            raise ProvenanceError(f"{location}.impact is unsupported")
        versions = entry["from_versions"]
        if not isinstance(versions, list) or not versions:
            raise ProvenanceError(f"{location}.from_versions must be non-empty")
        if len(versions) != len(set(versions)):
            raise ProvenanceError(f"{location}.from_versions contains duplicates")
        for version_index, version in enumerate(versions):
            _require_version(version, f"{location}.from_versions[{version_index}]")
        _require_version(entry["to_version"], f"{location}.to_version")
        for field in (
            "source_schema_change",
            "curriculum_identity_change",
            "progress_reset_required",
        ):
            if not isinstance(entry[field], bool):
                raise ProvenanceError(f"{location}.{field} must be boolean")
        source_paths = entry["source_paths"]
        if not isinstance(source_paths, list):
            raise ProvenanceError(f"{location}.source_paths must be a list")
        if len(source_paths) != len(set(source_paths)):
            raise ProvenanceError(f"{location}.source_paths contains duplicates")
        for path_index, path in enumerate(source_paths):
            _require_relative_path(path, f"{location}.source_paths[{path_index}]")
    return deepcopy(dict(registry))


def load_migration_registry(path: Path = MIGRATION_REGISTRY_PATH) -> dict[str, Any]:
    """Load and strictly validate the course-impacting migration registry."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"cannot load migration registry: {error}") from error
    return _validate_migration_registry(value)


def current_migration_ids() -> tuple[str, ...]:
    """Return all migration IDs represented by the current generated format."""

    return tuple(entry["id"] for entry in load_migration_registry()["migrations"])


def course_impacting_migrations(
    applied_migrations: Iterable[str] = (),
    *,
    registry: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return registered course-impacting migrations not already applied."""

    validated = (
        load_migration_registry()
        if registry is None
        else _validate_migration_registry(registry)
    )
    applied = tuple(applied_migrations)
    if len(applied) != len(set(applied)):
        raise ProvenanceError("applied_migrations contains duplicates")
    known = {entry["id"] for entry in validated["migrations"]}
    unknown = sorted(set(applied) - known)
    if unknown:
        raise ProvenanceError("unknown migration ids: " + ", ".join(unknown))
    return tuple(
        deepcopy(entry)
        for entry in validated["migrations"]
        if entry["course_impacting"] and entry["id"] not in applied
    )


def _canonical_json_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _course_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    if "course" in value:
        course = value["course"]
        target = value["target"]
        schema_version = value["schema_version"]
        language = course.get("language", "zh-CN")
        if schema_version == 2 and language not in {"zh-CN", "en"}:
            language = "zh-CN"
        return {
            "id": course["id"],
            "schema_version": schema_version,
            "language": language,
            "target": {
                "name": target["name"],
                "version": target["version"],
            },
        }
    return {
        "id": value["id"],
        "schema_version": value["schema_version"],
        "language": value["language"],
        "target": {
            "name": value["target"]["name"],
            "version": value["target"]["version"],
        },
    }


def course_identity_sha256(value: Mapping[str, Any]) -> str:
    """Hash the stable fields that distinguish one generated curriculum."""

    return _canonical_json_digest(_course_identity(value))


def _plugin_metadata() -> dict[str, str]:
    try:
        manifest = json.loads(PLUGIN_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"cannot load plugin manifest: {error}") from error
    if not isinstance(manifest, Mapping):
        raise ProvenanceError("plugin manifest must be an object")
    name = _require_nonempty_string(manifest.get("name"), "plugin manifest name")
    version = _require_version(manifest.get("version"), "plugin manifest version")
    if name != PLUGIN_NAME:
        raise ProvenanceError(f"unexpected plugin name: {name}")
    return {"name": name, "version": version}


def _managed_path_is_excluded(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    if relative == PROVENANCE_RELATIVE_PATH:
        return True
    if ".git" in parts or any(name in parts for name in TREE_IGNORE_NAMES):
        return True
    return relative == "labs/.coursekit" or relative.startswith("labs/.coursekit/")


def _iter_regular_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if _managed_path_is_excluded(relative):
            continue
        if path.is_symlink():
            raise ProvenanceError(f"generated course cannot contain managed symlink: {relative}")
        if path.is_file():
            yield path


def _learner_editable_paths(course_root: Path) -> set[str]:
    manifest_path = course_root / "labs" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"cannot load learner manifest: {error}") from error
    if not isinstance(manifest, Mapping):
        raise ProvenanceError("learner manifest must be an object")
    editable: set[str] = set()

    def add(value: object, location: str) -> None:
        relative = _require_relative_path(value, location)
        if relative.startswith("_course/") or relative == "manifest.json":
            raise ProvenanceError(f"{location} cannot name CourseKit runtime data")
        editable.add(relative)

    labs = manifest.get("labs")
    if not isinstance(labs, list):
        raise ProvenanceError("learner manifest labs must be a list")
    for lab_index, raw_lab in enumerate(labs):
        if not isinstance(raw_lab, Mapping):
            raise ProvenanceError(
                f"learner manifest labs[{lab_index}] must be an object"
            )
        if "file" in raw_lab:
            add(raw_lab["file"], f"learner manifest labs[{lab_index}].file")
        questions = raw_lab.get("questions")
        if not isinstance(questions, list):
            raise ProvenanceError(
                f"learner manifest labs[{lab_index}].questions must be a list"
            )
        for question_index, raw_question in enumerate(questions):
            if not isinstance(raw_question, Mapping) or "file" not in raw_question:
                raise ProvenanceError(
                    "learner manifest question must be an object with file"
                )
            add(
                raw_question["file"],
                (
                    f"learner manifest labs[{lab_index}]"
                    f".questions[{question_index}].file"
                ),
            )

    def collect_explicit(value: object, location: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_location = f"{location}.{key}"
                if key in {"editable_paths", "learner_editable_paths"}:
                    if not isinstance(child, list):
                        raise ProvenanceError(f"{child_location} must be a list")
                    for index, path in enumerate(child):
                        add(path, f"{child_location}[{index}]")
                else:
                    collect_explicit(child, child_location)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                collect_explicit(child, f"{location}[{index}]")

    collect_explicit(manifest, "learner manifest")
    return editable


def _managed_files(course_root: Path) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}

    def add(relative: str, role: str) -> None:
        if _managed_path_is_excluded(relative):
            return
        path = course_root / relative
        if not path.exists():
            return
        if path.is_symlink() or not path.is_file():
            raise ProvenanceError(f"managed path is not a regular file: {relative}")
        existing = records.get(relative)
        if existing is not None and existing["role"] != role:
            raise ProvenanceError(f"managed path has conflicting roles: {relative}")
        records[relative] = {"role": role, "sha256": hash_file(path)}

    for template_path in _iter_regular_files(TEMPLATE_ROOT):
        add(template_path.relative_to(TEMPLATE_ROOT).as_posix(), "template")

    compiled_root = course_root / "platform" / "course"
    if not compiled_root.is_dir():
        raise ProvenanceError("generated course is missing platform/course")
    for path in _iter_regular_files(compiled_root):
        local = path.relative_to(compiled_root).as_posix()
        if local == "source" or local.startswith("source/"):
            continue
        add(path.relative_to(course_root).as_posix(), "compiled")

    editable_paths = _learner_editable_paths(course_root)
    starter_root = compiled_root / "starter"
    if not starter_root.is_dir():
        raise ProvenanceError("generated course is missing platform/course/starter")
    for path in _iter_regular_files(starter_root):
        local = path.relative_to(starter_root).as_posix()
        if local in editable_paths:
            continue
        add(f"labs/{local}", "workspace-runtime")

    workspace_root = course_root / "labs" / "_course"
    if not workspace_root.is_dir():
        raise ProvenanceError("generated course is missing labs/_course")
    for path in _iter_regular_files(workspace_root):
        add(path.relative_to(course_root).as_posix(), "workspace-runtime")
    for relative in ("labs/README.md", "labs/pyproject.toml", "labs/uv.lock"):
        add(relative, "workspace-runtime")

    return {path: records[path] for path in sorted(records)}


def build_generation_provenance(
    course_root: Path,
    spec: Mapping[str, Any],
) -> dict[str, Any]:
    """Build provenance after generation and before the baseline Git commit."""

    root = Path(course_root)
    source_root = root / "platform" / "course" / "source"
    if not source_root.is_dir():
        raise ProvenanceError("generated course is missing canonical source")
    plugin = _plugin_metadata()
    identity = _course_identity(spec)
    identity["identity_sha256"] = course_identity_sha256(identity)
    provenance = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "plugin": plugin,
        "skill": {"name": SKILL_NAME, "version": plugin["version"]},
        "bundle": {
            "sha256": hash_tree(SKILL_ROOT, ignore=TREE_IGNORE_NAMES),
        },
        "template": {
            "sha256": hash_tree(TEMPLATE_ROOT, ignore=TREE_IGNORE_NAMES),
        },
        "authoring": {
            "sha256": hash_tree(source_root, ignore=TREE_IGNORE_NAMES),
        },
        "course": identity,
        "applied_migrations": list(current_migration_ids()),
        "managed_files": _managed_files(root),
    }
    return validate_generation_provenance(provenance)


def _validate_name_version(value: object, location: str) -> Mapping[str, Any]:
    record = _require_exact_keys(value, {"name", "version"}, location)
    _require_nonempty_string(record["name"], f"{location}.name")
    _require_version(record["version"], f"{location}.version")
    return record


def _verify_course_hashes(root: Path, provenance: Mapping[str, Any]) -> None:
    resolved_root = root.resolve()
    for relative, record in provenance["managed_files"].items():
        path = root / relative
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise ProvenanceError(f"managed file is missing: {relative}") from error
        if not resolved.is_relative_to(resolved_root):
            raise ProvenanceError(f"managed file escapes course root: {relative}")
        if path.is_symlink() or not path.is_file():
            raise ProvenanceError(f"managed file is not regular: {relative}")
        if hash_file(path) != record["sha256"]:
            raise ProvenanceError(f"managed file hash mismatch: {relative}")
    source_root = root / "platform" / "course" / "source"
    if hash_tree(source_root, ignore=TREE_IGNORE_NAMES) != provenance["authoring"]["sha256"]:
        raise ProvenanceError("canonical authoring source hash mismatch")


def validate_generation_provenance(
    value: object,
    *,
    course_root: Path | None = None,
    verify_hashes: bool = False,
) -> dict[str, Any]:
    """Strictly validate provenance and optionally bind it to current file bytes."""

    provenance = _require_exact_keys(
        value,
        {
            "schema_version",
            "plugin",
            "skill",
            "bundle",
            "template",
            "authoring",
            "course",
            "applied_migrations",
            "managed_files",
        },
        "provenance",
    )
    if provenance["schema_version"] != PROVENANCE_SCHEMA_VERSION:
        raise ProvenanceError("unsupported provenance schema_version")
    plugin = _validate_name_version(provenance["plugin"], "provenance.plugin")
    skill = _validate_name_version(provenance["skill"], "provenance.skill")
    if plugin["name"] != PLUGIN_NAME:
        raise ProvenanceError("provenance.plugin.name is unsupported")
    if skill["name"] != SKILL_NAME:
        raise ProvenanceError("provenance.skill.name is unsupported")
    for field in ("bundle", "template", "authoring"):
        digest = _require_exact_keys(
            provenance[field],
            {"sha256"},
            f"provenance.{field}",
        )
        _require_sha256(digest["sha256"], f"provenance.{field}.sha256")

    course = _require_exact_keys(
        provenance["course"],
        {"id", "schema_version", "language", "target", "identity_sha256"},
        "provenance.course",
    )
    _require_nonempty_string(course["id"], "provenance.course.id")
    if (
        not isinstance(course["schema_version"], int)
        or isinstance(course["schema_version"], bool)
        or course["schema_version"] < 2
    ):
        raise ProvenanceError("provenance.course.schema_version is unsupported")
    _require_nonempty_string(course["language"], "provenance.course.language")
    target = _require_exact_keys(
        course["target"],
        {"name", "version"},
        "provenance.course.target",
    )
    _require_nonempty_string(target["name"], "provenance.course.target.name")
    _require_nonempty_string(target["version"], "provenance.course.target.version")
    identity_digest = _require_sha256(
        course["identity_sha256"],
        "provenance.course.identity_sha256",
    )
    if identity_digest != course_identity_sha256(course):
        raise ProvenanceError("provenance.course.identity_sha256 does not match identity")

    migrations = provenance["applied_migrations"]
    if not isinstance(migrations, list) or not all(
        isinstance(identifier, str) and identifier for identifier in migrations
    ):
        raise ProvenanceError("provenance.applied_migrations must be a string list")
    if len(migrations) != len(set(migrations)):
        raise ProvenanceError("provenance.applied_migrations contains duplicates")
    registered = current_migration_ids()
    unknown = sorted(set(migrations) - set(registered))
    if unknown:
        raise ProvenanceError("provenance references unknown migration ids: " + ", ".join(unknown))
    if tuple(migrations) != registered[: len(migrations)]:
        raise ProvenanceError(
            "provenance.applied_migrations must be a registry-order prefix"
        )

    managed = provenance["managed_files"]
    if not isinstance(managed, Mapping):
        raise ProvenanceError("provenance.managed_files must be an object")
    for raw_path, raw_record in managed.items():
        relative = _require_relative_path(raw_path, "provenance.managed_files path")
        if _managed_path_is_excluded(relative):
            raise ProvenanceError(f"provenance.managed_files contains excluded path: {relative}")
        record = _require_exact_keys(
            raw_record,
            {"role", "sha256"},
            f"provenance.managed_files[{relative}]",
        )
        if record["role"] not in MANAGED_ROLES:
            raise ProvenanceError(f"provenance.managed_files[{relative}].role is unsupported")
        _require_sha256(
            record["sha256"],
            f"provenance.managed_files[{relative}].sha256",
        )

    result = deepcopy(dict(provenance))
    if verify_hashes:
        if course_root is None:
            raise ProvenanceError("course_root is required when verify_hashes is true")
        _verify_course_hashes(Path(course_root), result)
    return result


def write_generation_provenance(
    course_root: Path,
    spec: Mapping[str, Any],
) -> dict[str, Any]:
    """Write fresh provenance atomically and return the validated document."""

    root = Path(course_root)
    provenance = build_generation_provenance(root, spec)
    path = root / PROVENANCE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return provenance


def load_generation_provenance(
    course_root: Path,
    *,
    verify_hashes: bool = False,
) -> dict[str, Any]:
    """Load provenance from a course root (or from the provenance file itself)."""

    supplied = Path(course_root)
    if supplied.name == Path(PROVENANCE_RELATIVE_PATH).name and supplied.is_file():
        path = supplied
        root = supplied.parents[1]
    else:
        root = supplied
        path = root / PROVENANCE_RELATIVE_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"cannot load course provenance: {error}") from error
    return validate_generation_provenance(
        value,
        course_root=root,
        verify_hashes=verify_hashes,
    )


def provenance_report(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable, compact scaffold-report projection."""

    validated = validate_generation_provenance(provenance)
    return {
        "path": PROVENANCE_RELATIVE_PATH,
        "schema_version": validated["schema_version"],
        "plugin_version": validated["plugin"]["version"],
        "skill_version": validated["skill"]["version"],
        "course_identity_sha256": validated["course"]["identity_sha256"],
        "applied_migrations": list(validated["applied_migrations"]),
    }
