#!/usr/bin/env python3
"""Compute the deterministic contract for course-authoring capability."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
AUTHORING_CONTRACT_SCHEMA_VERSION = 1

# Keep this allowlist narrow. Changes to generated-course runtime presentation,
# release documentation, migration/regeneration plumbing, or provenance itself
# must not claim that the Skill learned how to author different course content.
AUTHORING_SCRIPT_PATHS = (
    "scripts/assemble_chapter_fragments.py",
    "scripts/assess_readiness.py",
    "scripts/inspect_python_target.py",
    "scripts/scaffold_course.py",
    "scripts/validate_course.py",
    "scripts/verify_learning_project.py",
)
CANONICAL_SOURCE_PATHS = (
    "assets/course-template/platform/coursekit/compiler.py",
    "assets/course-template/platform/coursekit/models.py",
)
V4_CONTENT_CONTRACT_PATHS = (
    "references/authoring-rubric.md",
    "references/chapter-writer-contract.md",
    "references/teaching-depth-contract.md",
)
V4_RUNTIME_SCRIPT_PATHS = (
    "assets/course-template/LICENSE",
    "assets/course-template/NOTICE",
    "scripts/scaffold_course.py",
    "scripts/scaffold_v4_course.py",
    "scripts/v4_contract.py",
    "scripts/validate_course.py",
    "scripts/verify_learning_project.py",
    "scripts/verify_v4_course.py",
)
V4_RUNTIME_ROOT = "assets/course-template-v4/coursekit_runtime"


class AuthoringContractError(RuntimeError):
    """The installed Skill cannot produce a trustworthy capability contract."""


def _hash_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise AuthoringContractError(
            f"authoring contract path is not a regular file: {path}"
        )
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _checked_paths(
    paths: tuple[str, ...],
    skill_root: Path,
) -> tuple[str, ...]:
    normalized = tuple(sorted(set(paths)))
    for relative in normalized:
        candidate = PurePosixPath(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise AuthoringContractError(
                f"unsafe authoring contract path: {relative}"
            )
        path = skill_root / relative
        if path.is_symlink() or not path.is_file():
            raise AuthoringContractError(
                f"authoring contract input is missing: {relative}"
            )
    return normalized


def _manifest_for_paths(
    paths: tuple[str, ...],
    skill_root: Path,
) -> dict[str, Any]:
    root = Path(skill_root)
    files = [
        {"path": relative, "sha256": _hash_file(root / relative)}
        for relative in _checked_paths(paths, root)
    ]
    contract = {
        "schema_version": AUTHORING_CONTRACT_SCHEMA_VERSION,
        "files": files,
    }
    return {**contract, "sha256": _canonical_digest(contract)}


def authoring_contract_paths(
    skill_root: Path = SKILL_ROOT,
) -> tuple[str, ...]:
    """Return the closed, sorted set of inputs that define authoring ability."""

    root = Path(skill_root)
    references = root / "references"
    if references.is_symlink() or not references.is_dir():
        raise AuthoringContractError(
            f"authoring reference directory is missing: {references}"
        )
    reference_paths = tuple(
        path.relative_to(root).as_posix()
        for path in sorted(references.rglob("*.md"))
        if path.is_file()
    )
    paths = (
        "SKILL.md",
        *reference_paths,
        *AUTHORING_SCRIPT_PATHS,
        *CANONICAL_SOURCE_PATHS,
    )
    return _checked_paths(tuple(paths), root)


def authoring_contract_manifest(
    skill_root: Path = SKILL_ROOT,
) -> dict[str, Any]:
    """Return per-file digests plus their deterministic aggregate SHA-256."""

    root = Path(skill_root)
    return _manifest_for_paths(authoring_contract_paths(root), root)


def current_authoring_contract() -> dict[str, Any]:
    """Return the installed Skill's current authoring capability contract."""

    return authoring_contract_manifest()


def authoring_contract_sha256(skill_root: Path = SKILL_ROOT) -> str:
    """Return only the aggregate authoring capability digest."""

    return str(authoring_contract_manifest(skill_root)["sha256"])


def v4_content_contract_manifest(
    skill_root: Path = SKILL_ROOT,
) -> dict[str, Any]:
    """Hash only canonical Depth-Brief and Writer-prompt inputs.

    The top-level Skill and curriculum reference intentionally stay outside
    this digest because they also document runtime, Web, export, and migration
    behavior. Those changes must not recall chapter Writers.
    """

    return _manifest_for_paths(V4_CONTENT_CONTRACT_PATHS, Path(skill_root))


def v4_content_contract_sha256(skill_root: Path = SKILL_ROOT) -> str:
    return str(v4_content_contract_manifest(skill_root)["sha256"])


def v4_runtime_contract_manifest(
    skill_root: Path = SKILL_ROOT,
) -> dict[str, Any]:
    """Hash exporter/verifier/runtime bytes without changing content prompts."""

    root = Path(skill_root)
    runtime = root / V4_RUNTIME_ROOT
    if runtime.is_symlink() or not runtime.is_dir():
        raise AuthoringContractError(
            f"schema-v4 runtime directory is missing: {runtime}"
        )
    runtime_paths = tuple(
        path.relative_to(root).as_posix()
        for path in sorted(runtime.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )
    return _manifest_for_paths(
        (*V4_RUNTIME_SCRIPT_PATHS, *runtime_paths),
        root,
    )


def v4_runtime_contract_sha256(skill_root: Path = SKILL_ROOT) -> str:
    return str(v4_runtime_contract_manifest(skill_root)["sha256"])
