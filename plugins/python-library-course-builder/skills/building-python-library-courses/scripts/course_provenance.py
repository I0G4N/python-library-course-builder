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

from assess_readiness import (
    ReadinessValidationError,
    validate_ready_plan,
    validate_route_contract,
)
from authoring_contract import AuthoringContractError, authoring_contract_sha256


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "course-template"
PLUGIN_MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
PROVENANCE_RELATIVE_PATH = "platform/coursekit-generation.json"
REGENERATION_RELATIVE_PATH = "platform/coursekit-regeneration.json"
CANONICAL_COURSE_RELATIVE_PATH = "platform/course/source/course.json"

PROVENANCE_SCHEMA_VERSION = 2
LEGACY_PROVENANCE_SCHEMA_VERSION = 1
REGENERATION_SCHEMA_VERSION = 1
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
    """A provenance or private regeneration document violated its contract."""


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


def _control_document_path(
    supplied: Path,
    relative: str,
    location: str,
) -> tuple[Path, Path]:
    """Resolve a course control document without following in-root symlinks."""

    candidate = Path(supplied).absolute()
    relative_path = Path(relative)
    if candidate.name == relative_path.name and (
        candidate.is_file() or candidate.is_symlink()
    ):
        root = candidate.parents[1]
        path = candidate
        if candidate.parent.name != relative_path.parent.name or path != root / relative_path:
            raise ProvenanceError(
                f"{location} direct path must use the canonical {relative} location"
            )
    else:
        root = candidate
        path = root / relative_path
    if root.is_symlink():
        raise ProvenanceError(f"{location} course root cannot be a symlink")
    current = root
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise ProvenanceError(f"{location} cannot contain symlinks")
    return root, path


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


_READINESS_PROJECTION_KEYS = (
    "status",
    "route_digest",
    "capability_dag",
    "required_capability_ids",
    "mastered_capability_ids",
    "missing_capability_ids",
    "capabilities",
    "preparatory_units",
    "preparatory_time",
    "readiness_summary",
    "plan_digest",
)


def build_regeneration_metadata(
    spec: Mapping[str, Any],
    *,
    readiness_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build private, evidence-free inputs for a future full regeneration."""

    course = spec["course"]
    target = spec["target"]
    language = course.get("language", "zh-CN")
    route_contract: dict[str, Any] | None = None
    readiness_projection: dict[str, Any] | None = None
    route_id: str | None = None
    route_title: str | None = None
    if spec["schema_version"] == 3:
        if readiness_plan is None:
            raise ProvenanceError(
                "schema-v3 regeneration metadata requires a readiness plan"
            )
        try:
            plan = validate_ready_plan(readiness_plan)
        except ReadinessValidationError as error:
            raise ProvenanceError(f"invalid readiness plan: {error}") from error
        route_contract = deepcopy(plan["route_contract"])
        route_id = str(plan["route_id"])
        route_title = str(route_contract["route"]["title"])
        readiness_projection = {
            key: deepcopy(plan[key]) for key in _READINESS_PROJECTION_KEYS
        }
    metadata = {
        "schema_version": REGENERATION_SCHEMA_VERSION,
        "language": language,
        "target": {
            "name": target["name"],
            "version": target["version"],
            "track": target.get("track") or None,
        },
        "route_intent": {
            "course_id": course["id"],
            "course_title": course["title"],
            "route_id": route_id,
            "route_title": route_title,
        },
        "route_contract": route_contract,
        "readiness_projection": readiness_projection,
    }
    return validate_regeneration_metadata(metadata)


def _reconstructed_ready_plan(
    metadata: Mapping[str, Any],
) -> dict[str, Any] | None:
    route_contract = metadata["route_contract"]
    projection = metadata["readiness_projection"]
    if route_contract is None or projection is None:
        return None
    plan = {
        "schema_version": route_contract["schema_version"],
        "status": projection["status"],
        "route_id": metadata["route_intent"]["route_id"],
        "route_digest": projection["route_digest"],
        "route_contract": deepcopy(route_contract),
        "official_sources": deepcopy(route_contract["official_sources"]),
        "official_source_ids": [
            str(source["id"]) for source in route_contract["official_sources"]
        ],
        "capability_dag": deepcopy(projection["capability_dag"]),
        "required_capability_ids": deepcopy(
            projection["required_capability_ids"]
        ),
        "mastered_capability_ids": deepcopy(
            projection["mastered_capability_ids"]
        ),
        "missing_capability_ids": deepcopy(
            projection["missing_capability_ids"]
        ),
        "capabilities": deepcopy(projection["capabilities"]),
        "preparatory_units": deepcopy(projection["preparatory_units"]),
        "preparatory_time": deepcopy(projection["preparatory_time"]),
        "readiness_summary": projection["readiness_summary"],
        "plan_digest": projection["plan_digest"],
    }
    if route_contract["schema_version"] == 2:
        plan["language"] = metadata["language"]
    return plan


def validate_regeneration_metadata(value: object) -> dict[str, Any]:
    """Strictly validate private regeneration inputs and readiness integrity."""

    metadata = _require_exact_keys(
        value,
        {
            "schema_version",
            "language",
            "target",
            "route_intent",
            "route_contract",
            "readiness_projection",
        },
        "regeneration metadata",
    )
    if metadata["schema_version"] != REGENERATION_SCHEMA_VERSION:
        raise ProvenanceError("unsupported regeneration metadata schema_version")
    language = _require_nonempty_string(
        metadata["language"], "regeneration metadata.language"
    )
    if language not in {"zh-CN", "en"}:
        raise ProvenanceError("regeneration metadata.language is unsupported")
    target = _require_exact_keys(
        metadata["target"],
        {"name", "version", "track"},
        "regeneration metadata.target",
    )
    _require_nonempty_string(target["name"], "regeneration metadata.target.name")
    _require_nonempty_string(
        target["version"], "regeneration metadata.target.version"
    )
    if target["track"] is not None:
        _require_nonempty_string(
            target["track"], "regeneration metadata.target.track"
        )
    intent = _require_exact_keys(
        metadata["route_intent"],
        {"course_id", "course_title", "route_id", "route_title"},
        "regeneration metadata.route_intent",
    )
    _require_nonempty_string(
        intent["course_id"], "regeneration metadata.route_intent.course_id"
    )
    _require_nonempty_string(
        intent["course_title"], "regeneration metadata.route_intent.course_title"
    )
    route_values = (intent["route_id"], intent["route_title"])
    if (route_values[0] is None) != (route_values[1] is None):
        raise ProvenanceError(
            "regeneration metadata route id and title must both be present or null"
        )
    if route_values[0] is not None:
        _require_nonempty_string(
            route_values[0], "regeneration metadata.route_intent.route_id"
        )
        _require_nonempty_string(
            route_values[1], "regeneration metadata.route_intent.route_title"
        )

    route_contract = metadata["route_contract"]
    projection = metadata["readiness_projection"]
    if (route_contract is None) != (projection is None):
        raise ProvenanceError(
            "regeneration metadata route contract and readiness projection must pair"
        )
    if route_contract is None:
        if route_values != (None, None):
            raise ProvenanceError(
                "legacy regeneration metadata cannot retain a readiness route"
            )
    else:
        projection_mapping = _require_exact_keys(
            projection,
            set(_READINESS_PROJECTION_KEYS),
            "regeneration metadata.readiness_projection",
        )
        candidate = dict(metadata)
        candidate["readiness_projection"] = projection_mapping
        try:
            plan = validate_ready_plan(_reconstructed_ready_plan(candidate))
        except ReadinessValidationError as error:
            raise ProvenanceError(
                f"invalid regeneration readiness projection: {error}"
            ) from error
        if plan["route_id"] != route_values[0]:
            raise ProvenanceError(
                "regeneration metadata route intent does not match readiness route"
            )
        if plan["route_contract"]["route"]["title"] != route_values[1]:
            raise ProvenanceError(
                "regeneration metadata route title does not match readiness route"
            )
        if plan.get("language", "zh-CN") != language:
            raise ProvenanceError(
                "regeneration metadata language does not match readiness route"
            )
    return deepcopy(dict(metadata))


def regeneration_input_sha256(value: object) -> str:
    """Hash the canonical, validated private regeneration inputs."""

    return _canonical_json_digest(validate_regeneration_metadata(value))


def write_regeneration_metadata(
    course_root: Path,
    spec: Mapping[str, Any],
    *,
    readiness_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write private regeneration inputs before provenance and the Git baseline."""

    root = Path(course_root)
    metadata = build_regeneration_metadata(spec, readiness_plan=readiness_plan)
    path = root / REGENERATION_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return metadata


def load_regeneration_metadata(course_root: Path) -> dict[str, Any]:
    """Load and validate private regeneration inputs from a generated course."""

    root, path = _control_document_path(
        Path(course_root),
        REGENERATION_RELATIVE_PATH,
        "course regeneration metadata",
    )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProvenanceError(
            f"cannot load course regeneration metadata: {error}"
        ) from error
    metadata = validate_regeneration_metadata(value)
    _validate_regeneration_course_binding(root, metadata)
    return metadata


def _canonical_course_contract(course_root: Path) -> dict[str, Any]:
    _, path = _control_document_path(
        course_root,
        CANONICAL_COURSE_RELATIVE_PATH,
        "canonical course source",
    )
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"cannot load canonical course source: {error}") from error
    if not isinstance(source, Mapping):
        raise ProvenanceError("canonical course source must be an object")
    schema_version = source.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ProvenanceError("canonical course schema_version must be an integer")
    course_id = _require_nonempty_string(source.get("id"), "canonical course id")
    title = _require_nonempty_string(source.get("title"), "canonical course title")
    language = _require_nonempty_string(
        source.get("language"), "canonical course language"
    )
    if language not in {"zh-CN", "en"}:
        raise ProvenanceError("canonical course language is unsupported")
    manifest = source.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ProvenanceError("canonical course manifest must be an object")
    target = manifest.get("target")
    if not isinstance(target, Mapping):
        raise ProvenanceError("canonical course target must be an object")
    target_name = _require_nonempty_string(
        target.get("name"), "canonical course target.name"
    )
    target_version = _require_nonempty_string(
        target.get("version"), "canonical course target.version"
    )
    track = target.get("track")
    if track is not None:
        track = _require_nonempty_string(track, "canonical course target.track")
    route_id: str | None = None
    audience = source.get("audience")
    if isinstance(audience, Mapping):
        profile = audience.get("prerequisite_profile")
        if isinstance(profile, Mapping) and profile.get("route_id") is not None:
            route_id = _require_nonempty_string(
                profile.get("route_id"),
                "canonical course audience.prerequisite_profile.route_id",
            )
    return {
        "schema_version": schema_version,
        "course_id": course_id,
        "course_title": title,
        "language": language,
        "target": {
            "name": target_name,
            "version": target_version,
            "track": track,
        },
        "route_id": route_id,
    }


def _validate_regeneration_course_binding(
    course_root: Path,
    metadata: Mapping[str, Any],
) -> None:
    canonical = _canonical_course_contract(course_root)
    intent = metadata["route_intent"]
    if metadata["language"] != canonical["language"]:
        raise ProvenanceError(
            "regeneration metadata language does not match canonical source"
        )
    if metadata["target"] != canonical["target"]:
        raise ProvenanceError(
            "regeneration metadata target does not match canonical source"
        )
    if intent["course_id"] != canonical["course_id"]:
        raise ProvenanceError(
            "regeneration metadata course id does not match canonical source"
        )
    if intent["course_title"] != canonical["course_title"]:
        raise ProvenanceError(
            "regeneration metadata course title does not match canonical source"
        )
    if intent["route_id"] != canonical["route_id"]:
        raise ProvenanceError(
            "regeneration metadata route id does not match canonical source"
        )


def trusted_readiness_reuse(
    course_root: Path,
    route_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Reuse only unchanged capability decisions from verified v2 metadata."""

    provenance = load_generation_provenance(course_root, verify_hashes=True)
    if provenance["schema_version"] != PROVENANCE_SCHEMA_VERSION:
        raise ProvenanceError(
            "legacy provenance cannot establish trusted readiness reuse"
        )
    metadata = load_regeneration_metadata(course_root)
    old_contract = metadata["route_contract"]
    old_projection = metadata["readiness_projection"]
    if old_contract is None or old_projection is None:
        raise ProvenanceError(
            "course requires full readiness reassessment"
        )
    try:
        current_contract = validate_route_contract(route_contract)
    except ReadinessValidationError as error:
        raise ProvenanceError(f"invalid current route contract: {error}") from error
    if current_contract.get("language", "zh-CN") != metadata["language"]:
        raise ProvenanceError(
            "current readiness route language does not match the generated course"
        )
    route_intent = metadata["route_intent"]
    if current_contract["route"]["id"] != route_intent["route_id"]:
        raise ProvenanceError(
            "current readiness route id does not match the locked route intent"
        )
    if current_contract["route"]["title"] != route_intent["route_title"]:
        raise ProvenanceError(
            "current readiness route title does not match the locked route intent"
        )

    old_hashes = {
        str(record["id"]): str(record["sha256"])
        for record in old_contract["capability_contracts"]
    }
    current_records = current_contract["capability_contracts"]
    current_hashes = {
        str(record["id"]): str(record["sha256"])
        for record in current_records
    }
    old_decisions = {
        str(capability["id"]): str(capability["status"])
        for capability in old_projection["capabilities"]
    }
    reusable: list[dict[str, str]] = []
    needs_evidence: list[str] = []
    new_ids: list[str] = []
    changed_ids: list[str] = []
    for record in current_records:
        capability_id = str(record["id"])
        if capability_id not in old_hashes:
            new_ids.append(capability_id)
            needs_evidence.append(capability_id)
        elif old_hashes[capability_id] != record["sha256"]:
            changed_ids.append(capability_id)
            needs_evidence.append(capability_id)
        else:
            status = old_decisions.get(capability_id)
            if status not in {"known", "missing"}:
                raise ProvenanceError(
                    f"trusted readiness decision is missing: {capability_id}"
                )
            reusable.append(
                {
                    "capability_id": capability_id,
                    "contract_sha256": str(record["sha256"]),
                    "status": status,
                }
            )
    removed_ids = [
        capability_id
        for capability_id in old_hashes
        if capability_id not in current_hashes
    ]
    return {
        "schema_version": 1,
        "mode": "reuse_unchanged",
        "source": {
            "course_identity_sha256": provenance["course"]["identity_sha256"],
            "authoring_contract_sha256": provenance["authoring_contract"]["sha256"],
            "regeneration_input_sha256": provenance["regeneration_input"]["sha256"],
        },
        "route_contract_sha256": _canonical_json_digest(current_contract),
        "reusable_decisions": reusable,
        "reusable_capability_ids": [
            decision["capability_id"] for decision in reusable
        ],
        "needs_evidence_capability_ids": needs_evidence,
        "missing_capability_ids": [
            decision["capability_id"]
            for decision in reusable
            if decision["status"] == "missing"
        ],
        "new_capability_ids": new_ids,
        "changed_capability_ids": changed_ids,
        "removed_capability_ids": removed_ids,
    }


def _managed_path_is_excluded(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    if relative in {PROVENANCE_RELATIVE_PATH, REGENERATION_RELATIVE_PATH}:
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
    regeneration_metadata = load_regeneration_metadata(root)
    identity = _course_identity(spec)
    identity["identity_sha256"] = course_identity_sha256(identity)
    try:
        contract_sha256 = authoring_contract_sha256()
    except AuthoringContractError as error:
        raise ProvenanceError(f"cannot build authoring contract: {error}") from error
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
        "authoring_contract": {
            "sha256": contract_sha256,
        },
        "regeneration_input": {
            "sha256": regeneration_input_sha256(regeneration_metadata),
        },
        "course": identity,
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
    canonical = _canonical_course_contract(root)
    canonical_identity = {
        "id": canonical["course_id"],
        "schema_version": canonical["schema_version"],
        "language": canonical["language"],
        "target": {
            "name": canonical["target"]["name"],
            "version": canonical["target"]["version"],
        },
    }
    canonical_identity["identity_sha256"] = course_identity_sha256(
        canonical_identity
    )
    if provenance["course"] != canonical_identity:
        raise ProvenanceError(
            "provenance course identity does not match canonical source"
        )
    if provenance["schema_version"] == PROVENANCE_SCHEMA_VERSION:
        metadata = load_regeneration_metadata(root)
        if (
            regeneration_input_sha256(metadata)
            != provenance["regeneration_input"]["sha256"]
        ):
            raise ProvenanceError("regeneration input hash mismatch")


def validate_generation_provenance(
    value: object,
    *,
    course_root: Path | None = None,
    verify_hashes: bool = False,
) -> dict[str, Any]:
    """Strictly validate provenance and optionally bind it to current file bytes."""

    if not isinstance(value, Mapping):
        raise ProvenanceError("provenance must be an object")
    schema_version = value.get("schema_version")
    if schema_version == LEGACY_PROVENANCE_SCHEMA_VERSION:
        expected_keys = {
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
    elif schema_version == PROVENANCE_SCHEMA_VERSION:
        expected_keys = {
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
    else:
        raise ProvenanceError("unsupported provenance schema_version")
    provenance = _require_exact_keys(value, expected_keys, "provenance")
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
    if schema_version == PROVENANCE_SCHEMA_VERSION:
        for field in ("authoring_contract", "regeneration_input"):
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

    if schema_version == LEGACY_PROVENANCE_SCHEMA_VERSION:
        migrations = provenance["applied_migrations"]
        if not isinstance(migrations, list) or not all(
            isinstance(identifier, str) and identifier for identifier in migrations
        ):
            raise ProvenanceError(
                "provenance.applied_migrations must be a string list"
            )
        if len(migrations) != len(set(migrations)):
            raise ProvenanceError(
                "provenance.applied_migrations contains duplicates"
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

    root, path = _control_document_path(
        Path(course_root),
        PROVENANCE_RELATIVE_PATH,
        "course provenance",
    )
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
    report = {
        "path": PROVENANCE_RELATIVE_PATH,
        "schema_version": validated["schema_version"],
        "plugin_version": validated["plugin"]["version"],
        "skill_version": validated["skill"]["version"],
        "course_identity_sha256": validated["course"]["identity_sha256"],
    }
    if validated["schema_version"] == PROVENANCE_SCHEMA_VERSION:
        report["authoring_contract_sha256"] = validated["authoring_contract"][
            "sha256"
        ]
        report["regeneration_input_sha256"] = validated["regeneration_input"][
            "sha256"
        ]
    return report
