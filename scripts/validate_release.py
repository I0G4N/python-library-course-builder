#!/usr/bin/env python3
"""Run deterministic release checks from any working directory."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from typing import Iterable, Mapping, NamedTuple, Sequence
from urllib.parse import urlsplit


PLUGIN_NAME = "python-library-course-builder"
SKILL_NAME = "building-python-library-courses"
AUTHOR_NAME = "I0G4N"
AUTHOR_URL = "https://github.com/I0G4N"
REPOSITORY_URL = f"{AUTHOR_URL}/{PLUGIN_NAME}"
HOMEPAGE_URL = f"{REPOSITORY_URL}#readme"
DISPLAY_NAME = "Python Library Course Builder"
EXPECTED_UV_VERSION = "0.11.7"
MINIMUM_NODE_VERSION = (22, 13, 0)
FORWARD_ENVIRONMENT_NAMES = frozenset(
    {
        "COMSPEC",
        "LANG",
        "LANGUAGE",
        "LC_ADDRESS",
        "LC_ALL",
        "LC_COLLATE",
        "LC_CTYPE",
        "LC_IDENTIFICATION",
        "LC_MEASUREMENT",
        "LC_MESSAGES",
        "LC_MONETARY",
        "LC_NAME",
        "LC_NUMERIC",
        "LC_PAPER",
        "LC_TELEPHONE",
        "LC_TIME",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
    }
)

RESIDUE_PARTS = {
    ".mypy_cache",
    ".next",
    ".planning",
    ".pytest_cache",
    ".ruff_cache",
    ".superpowers",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
}
RESIDUE_SUFFIXES = {".log", ".pyc", ".pyo", ".tmp"}
EXPECTED_TEMPLATE_TOKENS = {
    "__COURSEKIT_CAPSTONE__",
    "__COURSEKIT_DESCRIPTION__",
    "__COURSEKIT_FIRST_QUESTION__",
    "__COURSEKIT_PREPARATION__",
    "__COURSEKIT_PYTHON_REQUIRES__",
    "__COURSEKIT_ROUTE__",
    "__COURSEKIT_SLUG__",
    "__COURSEKIT_TARGET__",
    "__COURSEKIT_TARGET_VERSION__",
    "__COURSEKIT_TITLE__",
}
SECRET_PATTERNS = (
    ("private key", re.compile(br"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(br"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(br"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("OpenAI API key", re.compile(br"\bsk-[A-Za-z0-9_-]{20,}\b")),
)
PRIVATE_HOST_PATTERNS = (
    re.compile(br"/Users/[A-Za-z0-9._-]+/"),
    re.compile(br"/home/[A-Za-z0-9._-]+/"),
    re.compile(br"/root/[A-Za-z0-9._/-]+"),
    re.compile(br"/private/(?:tmp|var/folders)/[A-Za-z0-9._/-]+"),
    re.compile(br"/var/folders/[A-Za-z0-9._/-]+"),
    re.compile(br"[A-Za-z]:/Users/[A-Za-z0-9._/-]+"),
    re.compile(br"[A-Za-z]:\\Users\\[^\\\s]+\\"),
)
TEMPLATE_TOKEN_RE = re.compile(r"__COURSEKIT_[A-Z0-9_]+__")
STRICT_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\."
    r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
PLUGIN_MANIFEST_FIELDS = frozenset(
    {
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "skills",
        "interface",
    }
)
PLUGIN_AUTHOR_FIELDS = frozenset({"name", "url"})
PLUGIN_INTERFACE_FIELDS = frozenset(
    {
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
        "websiteURL",
        "defaultPrompt",
    }
)
MARKETPLACE_FIELDS = frozenset({"name", "interface", "plugins"})
MARKETPLACE_INTERFACE_FIELDS = frozenset({"displayName"})
MARKETPLACE_PLUGIN_FIELDS = frozenset({"name", "source", "policy", "category"})
MARKETPLACE_SOURCE_FIELDS = frozenset({"source", "path"})
MARKETPLACE_POLICY_FIELDS = frozenset({"installation", "authentication"})


class CommandStep(NamedTuple):
    argv: tuple[str, ...]
    cwd: Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def git_inventory_command() -> list[str]:
    return [
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]


def decode_git_inventory(root: Path, payload: bytes) -> tuple[Path, ...]:
    base = root.resolve()
    paths: list[Path] = []
    for raw in payload.decode("utf-8", errors="surrogateescape").split("\0"):
        if not raw:
            continue
        relative = PurePosixPath(raw)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"git returned an unsafe repository path: {raw!r}")
        paths.append(base.joinpath(*relative.parts))
    return tuple(paths)


def repository_inventory(root: Path) -> tuple[Path, ...]:
    result = subprocess.run(
        git_inventory_command(),
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"unable to inventory repository files: {detail}")
    return decode_git_inventory(root, result.stdout)


def _relative_label(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _residue_reason(relative: Path) -> str | None:
    folded_parts = {part.casefold() for part in relative.parts}
    matching_parts = sorted(folded_parts & RESIDUE_PARTS)
    if matching_parts:
        return f"forbidden path segment {matching_parts[0]!r}"
    if relative.name in {
        ".DS_Store",
        ".coverage",
        "coverage.xml",
        "course-verification.json",
    }:
        return f"forbidden generated file {relative.name!r}"
    if relative.suffix.casefold() in RESIDUE_SUFFIXES:
        return f"forbidden generated suffix {relative.suffix!r}"
    return None


def scan_inventory(root: Path, files: Iterable[Path]) -> list[str]:
    errors: list[str] = []
    base = root.resolve()
    todo_marker = "[" + "TODO:"
    legacy_markers = (
        "ConcurrencyLab" + " baseline",
        "CS61A" + "-style",
        "CS336" + "-style",
    )
    for candidate in files:
        path = Path(candidate)
        label = _relative_label(base, path)
        if path.is_symlink():
            errors.append(f"symlink is not allowed in the release inventory: {label}")
            continue
        try:
            relative = path.relative_to(base)
        except ValueError:
            errors.append(f"inventory path escapes the repository: {path}")
            continue
        residue = _residue_reason(relative)
        if residue is not None:
            errors.append(f"release residue at {label}: {residue}")
        if not path.is_file():
            errors.append(f"inventory entry is not a regular file: {label}")
            continue
        try:
            raw = path.read_bytes()
        except OSError as error:
            errors.append(f"unable to read inventory entry {label}: {error}")
            continue
        for secret_name, pattern in SECRET_PATTERNS:
            if pattern.search(raw):
                errors.append(f"possible secret ({secret_name}) in {label}")
        if any(pattern.search(raw) for pattern in PRIVATE_HOST_PATTERNS):
            errors.append(f"private host path in {label}")
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        is_contract_fixture = bool(relative.parts and relative.parts[0] == "tests")
        if not is_contract_fixture and todo_marker in text:
            errors.append(f"unresolved TODO marker in {label}")
        if not is_contract_fixture:
            for marker in legacy_markers:
                if marker in text:
                    errors.append(f"legacy course branding {marker!r} in {label}")
            for token in TEMPLATE_TOKEN_RE.findall(text):
                if token not in EXPECTED_TEMPLATE_TOKENS:
                    errors.append(f"unexpected template token {token!r} in {label}")
    return errors


def _load_json_object(path: Path) -> tuple[dict[str, object] | None, list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, [f"unable to load {path.name}: {error}"]
    if not isinstance(payload, dict):
        return None, [f"{path.name} must contain a JSON object"]
    return payload, []


def _npm_dependency_parts(name: str) -> tuple[str, ...] | None:
    parts = tuple(name.split("/"))
    if name.startswith("@"):
        valid = (
            len(parts) == 2
            and parts[0].startswith("@")
            and len(parts[0]) > 1
            and bool(parts[1])
        )
    else:
        valid = len(parts) == 1 and bool(parts[0])
    if not valid or any(part in {".", ".."} for part in parts):
        return None
    return parts


def _npm_dependency_candidates(package_path: str, name: str) -> tuple[str, ...]:
    dependency_parts = _npm_dependency_parts(name)
    if dependency_parts is None:
        return ()
    prefix = PurePosixPath(package_path).parts if package_path else ()
    candidates: list[str] = []
    if prefix and "node_modules" not in prefix:
        while prefix:
            candidates.append(
                PurePosixPath(*prefix, "node_modules", *dependency_parts).as_posix()
            )
            prefix = prefix[:-1]
        candidates.append(
            PurePosixPath("node_modules", *dependency_parts).as_posix()
        )
        return tuple(candidates)
    while True:
        candidates.append(
            PurePosixPath(*prefix, "node_modules", *dependency_parts).as_posix()
        )
        node_modules = [
            index for index, part in enumerate(prefix) if part == "node_modules"
        ]
        if not node_modules:
            break
        prefix = prefix[: node_modules[-1]]
    return tuple(candidates)


def _npm_package_name(package_path: str) -> str | None:
    parts = PurePosixPath(package_path).parts
    node_modules = [index for index, part in enumerate(parts) if part == "node_modules"]
    if not node_modules:
        return None
    tail = parts[node_modules[-1] + 1 :]
    if len(tail) == 1 and tail[0]:
        return tail[0]
    if len(tail) == 2 and tail[0].startswith("@") and tail[1]:
        return f"{tail[0]}/{tail[1]}"
    return None


def _npm_parent_package_path(package_path: str) -> str | None:
    parts = PurePosixPath(package_path).parts
    node_modules = [index for index, part in enumerate(parts) if part == "node_modules"]
    if len(node_modules) < 2:
        return None
    return PurePosixPath(*parts[: node_modules[-1]]).as_posix()


def _npm_local_resolution_errors(
    resolved: object,
    package_path: str,
    *,
    link: bool,
) -> list[str]:
    if not isinstance(resolved, str) or not resolved:
        return [f"npm lock package {package_path!r} needs a local resolved path"]
    raw_path = resolved[5:] if resolved.startswith("file:") else resolved
    candidate = PurePosixPath(raw_path)
    portable_parts = tuple(part for part in re.split(r"[\\/]", raw_path) if part)
    windows_drive = re.match(r"^[A-Za-z]:", raw_path) is not None
    non_file_scheme = (
        not resolved.startswith("file:")
        and re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", resolved) is not None
    )
    if (
        not raw_path
        or candidate.is_absolute()
        or raw_path.startswith("\\")
        or windows_drive
        or non_file_scheme
        or "%" in raw_path
        or "\\" in raw_path
        or any(part in {".", ".."} for part in portable_parts)
        or "\0" in raw_path
        or (not link and not resolved.startswith("file:"))
    ):
        return [f"npm lock package {package_path!r} has an invalid local resolved path"]
    return []


def _npm_linked_local_targets(packages: Mapping[str, object]) -> frozenset[str]:
    targets: set[str] = set()
    for package_path, entry in packages.items():
        if not isinstance(package_path, str) or not isinstance(entry, dict):
            continue
        if entry.get("link") is not True:
            continue
        resolved = entry.get("resolved")
        if _npm_local_resolution_errors(resolved, package_path, link=True):
            continue
        assert isinstance(resolved, str)
        raw_path = resolved[5:] if resolved.startswith("file:") else resolved
        targets.add(PurePosixPath(raw_path).as_posix())
    return frozenset(targets)


def _npm_registry_metadata_errors(
    package_path: str,
    entry: Mapping[str, object],
    packages: Mapping[str, object],
) -> list[str]:
    errors: list[str] = []
    if entry.get("link") is True:
        # Lockfile v3 workspace links point at a local path and intentionally
        # omit registry version, tarball, and integrity metadata.
        errors.extend(
            _npm_local_resolution_errors(
                entry.get("resolved"),
                package_path,
                link=True,
            )
        )
        return errors

    version = entry.get("version")
    if not isinstance(version, str) or STRICT_SEMVER_RE.fullmatch(version) is None:
        errors.append(f"npm lock package {package_path!r} has an invalid version")

    if entry.get("inBundle") is True:
        # npm omits tarball metadata for the optional WASM packages bundled by
        # @tailwindcss/oxide-wasm32-wasi. Keep this exception structural: the
        # nearest parent must explicitly list the package as bundled.
        package_name = _npm_package_name(package_path)
        parent_path = _npm_parent_package_path(package_path)
        parent = packages.get(parent_path) if parent_path is not None else None
        bundled = parent.get("bundleDependencies") if isinstance(parent, dict) else None
        if (
            entry.get("optional") is not True
            or package_name is None
            or not isinstance(bundled, list)
            or package_name not in bundled
        ):
            errors.append(
                f"npm lock package {package_path!r} uses an invalid bundled-package metadata exception"
            )
        return errors

    resolved = entry.get("resolved")
    if isinstance(resolved, str) and resolved.startswith("file:"):
        # Local file dependencies are the other non-registry lockfile form.
        errors.extend(
            _npm_local_resolution_errors(resolved, package_path, link=False)
        )
        return errors

    if not isinstance(resolved, str):
        errors.append(
            f"npm lock registry package {package_path!r} is missing resolved metadata"
        )
    else:
        valid_registry_url = False
        try:
            parsed = urlsplit(resolved)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            pass
        else:
            valid_registry_url = (
                parsed.scheme == "https"
                and hostname == "registry.npmjs.org"
                and port in {None, 443}
                and parsed.username is None
                and parsed.password is None
                and parsed.path.endswith(".tgz")
                and not parsed.query
                and not parsed.fragment
            )
        if not valid_registry_url:
            errors.append(
                f"npm lock registry package {package_path!r} has an invalid resolved HTTPS registry URL"
            )

    integrity = entry.get("integrity")
    valid_integrity = False
    if isinstance(integrity, str) and integrity.startswith("sha512-"):
        try:
            digest = base64.b64decode(integrity.removeprefix("sha512-"), validate=True)
        except (binascii.Error, ValueError, TypeError):
            digest = b""
        valid_integrity = len(digest) == 64
    if not valid_integrity:
        errors.append(
            f"npm lock registry package {package_path!r} integrity must be one sha512 digest"
        )
    return errors


def _npm_dependency_graph_errors(packages: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    linked_local_targets = _npm_linked_local_targets(packages)
    for package_path, raw_entry in sorted(packages.items()):
        if not isinstance(package_path, str) or not isinstance(raw_entry, dict):
            continue
        if raw_entry.get("link") is not True:
            continue
        resolved = raw_entry.get("resolved")
        if _npm_local_resolution_errors(resolved, package_path, link=True):
            continue
        assert isinstance(resolved, str)
        raw_target = resolved[5:] if resolved.startswith("file:") else resolved
        target = PurePosixPath(raw_target).as_posix()
        if target not in packages:
            errors.append(
                f"npm lock link target {target!r} for package {package_path!r} is missing"
            )
    for package_path, raw_entry in sorted(packages.items()):
        if not isinstance(package_path, str) or not isinstance(raw_entry, dict):
            errors.append(f"npm lock package entry {package_path!r} must be an object")
            continue
        if package_path:
            parts = PurePosixPath(package_path).parts
            package_name = _npm_package_name(package_path)
            if (
                PurePosixPath(package_path).is_absolute()
                or ".." in parts
                or "\\" in package_path
                or "%" in package_path
            ):
                errors.append(f"npm lock package path {package_path!r} is invalid")
                continue
            if package_name is None:
                if package_path not in linked_local_targets:
                    errors.append(f"npm lock package path {package_path!r} is invalid")
                    continue
                version = raw_entry.get("version")
                if (
                    not isinstance(version, str)
                    or STRICT_SEMVER_RE.fullmatch(version) is None
                ):
                    errors.append(
                        f"npm lock workspace package {package_path!r} has an invalid version"
                    )
            else:
                errors.extend(
                    _npm_registry_metadata_errors(package_path, raw_entry, packages)
                )

        dependency_fields = ["dependencies", "optionalDependencies", "peerDependencies"]
        if package_path == "":
            dependency_fields.append("devDependencies")
        peer_meta = raw_entry.get("peerDependenciesMeta", {})
        for field in dependency_fields:
            dependencies = raw_entry.get(field, {})
            if not isinstance(dependencies, dict):
                errors.append(f"npm lock package {package_path!r} {field} must be an object")
                continue
            for dependency, requirement in sorted(dependencies.items()):
                label = f"npm lock package {package_path!r} {field} dependency {dependency!r}"
                if not isinstance(dependency, str) or not isinstance(requirement, str):
                    errors.append(f"{label} must use string name and requirement metadata")
                    continue
                if (
                    field == "peerDependencies"
                    and isinstance(peer_meta, dict)
                    and isinstance(peer_meta.get(dependency), dict)
                    and peer_meta[dependency].get("optional") is True
                ):
                    continue
                # Transitive requirements and versions come from the same lock
                # artifact, so this offline structural check proves Node-style
                # resolution and validates the resolved entry's own metadata;
                # it deliberately does not reimplement npm's range language.
                candidates = _npm_dependency_candidates(package_path, dependency)
                if not candidates:
                    errors.append(f"{label} has an invalid package name")
                elif not any(candidate in packages for candidate in candidates):
                    errors.append(
                        f"{label} does not resolve through the locked Node ancestor graph"
                    )
    return errors


def npm_lock_errors(package_path: Path, lock_path: Path) -> list[str]:
    package, errors = _load_json_object(package_path)
    lock, lock_errors = _load_json_object(lock_path)
    errors.extend(lock_errors)
    if package is None or lock is None:
        return errors
    if lock.get("lockfileVersion") != 3:
        errors.append("package-lock.json must use lockfileVersion 3")
    if lock.get("requires") is not True:
        errors.append("package-lock.json must declare requires=true")
    for field in ("name", "version"):
        if lock.get(field) != package.get(field):
            errors.append(f"package-lock top-level {field} does not match package.json")
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        return errors + ["package-lock.json packages must be an object"]
    lock_root = packages.get("")
    if not isinstance(lock_root, dict):
        return errors + ["package-lock.json is missing its root package entry"]
    for field in ("name", "version", "engines", "dependencies", "devDependencies"):
        expected = package.get(field, {})
        actual = lock_root.get(field, {})
        if actual != expected:
            errors.append(f"package-lock root {field} does not match package.json")
    for field in ("dependencies", "devDependencies"):
        declared = package.get(field, {})
        if not isinstance(declared, dict):
            errors.append(f"package.json {field} must be an object")
            continue
        for name, required_version in sorted(declared.items()):
            locked = packages.get(f"node_modules/{name}")
            if not isinstance(locked, dict):
                errors.append(f"package-lock is missing direct dependency {name}")
                continue
            if locked.get("link") is True:
                if not (
                    isinstance(required_version, str)
                    and required_version.startswith(("workspace:", "file:"))
                ):
                    errors.append(
                        f"package-lock direct dependency {name} uses a local override for non-local requirement {required_version!r}"
                    )
                continue
            if (
                isinstance(locked.get("resolved"), str)
                and locked["resolved"].startswith("file:")
            ):
                if not (
                    isinstance(required_version, str)
                    and required_version.startswith("file:")
                ):
                    errors.append(
                        f"package-lock direct dependency {name} uses a local override for non-local requirement {required_version!r}"
                    )
                continue
            if locked.get("version") != required_version:
                errors.append(
                    "package-lock direct dependency "
                    f"{name} version {locked.get('version')!r} does not match "
                    f"package.json {required_version!r}"
                )
    errors.extend(_npm_dependency_graph_errors(packages))
    return errors


def codex_validator_paths(codex_home: Path) -> dict[str, Path]:
    system_skills = codex_home.expanduser() / "skills" / ".system"
    return {
        "skill": (
            system_skills
            / "skill-creator"
            / "scripts"
            / "quick_validate.py"
        ),
        "plugin": (
            system_skills
            / "plugin-creator"
            / "scripts"
            / "validate_plugin.py"
        ),
    }


def codex_validator_errors(codex_home: Path) -> list[str]:
    errors: list[str] = []
    for kind, path in codex_validator_paths(codex_home).items():
        if not path.is_file():
            errors.append(f"official Codex {kind} validator not found under CODEX_HOME: {path}")
    return errors


def version_parity_errors(
    project_version: str,
    plugin_version: str,
    release_tag: str | None,
) -> list[str]:
    if project_version != plugin_version:
        return [
            "project version "
            f"{project_version} does not match plugin version {plugin_version}"
        ]
    if release_tag is not None and release_tag != f"v{project_version}":
        return [
            f"release tag {release_tag} does not match "
            f"project/plugin version {project_version}"
        ]
    return []


def _fixed_object_fields_errors(
    payload: Mapping[str, object],
    expected_fields: frozenset[str],
    label: str,
) -> list[str]:
    errors = [
        f"{label}.{field} is an unsupported field"
        for field in sorted(set(payload) - expected_fields)
    ]
    errors.extend(
        f"{label}.{field} is a required field"
        for field in sorted(expected_fields - set(payload))
    )
    return errors


def _non_empty_string_errors(value: object, field: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"{field} must be a non-empty string"]
    return []


def _https_url_errors(value: object, field: str) -> list[str]:
    if not isinstance(value, str):
        return [f"{field} must be an absolute HTTPS URL"]
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return [f"{field} must be a well-formed absolute HTTPS URL"]
    if (
        value != value.strip()
        or parsed.scheme != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        return [f"{field} must be an absolute HTTPS URL without credentials"]
    return []


def plugin_manifest_errors(manifest: Mapping[str, object]) -> list[str]:
    """Validate the repository's fixed, Skill-only plugin manifest schema."""

    errors = _fixed_object_fields_errors(
        manifest,
        PLUGIN_MANIFEST_FIELDS,
        "plugin manifest",
    )
    for field in ("name", "version", "description", "license", "skills"):
        errors.extend(_non_empty_string_errors(manifest.get(field), field))
    if manifest.get("name") != PLUGIN_NAME:
        errors.append(f"plugin manifest name must be {PLUGIN_NAME!r}")
    version = manifest.get("version")
    if not isinstance(version, str) or STRICT_SEMVER_RE.fullmatch(version) is None:
        errors.append("version must use strict semantic versioning")
    for field in ("homepage", "repository"):
        errors.extend(_https_url_errors(manifest.get(field), field))
    if manifest.get("license") != "Apache-2.0":
        errors.append("license must be 'Apache-2.0'")
    if manifest.get("skills") != "./skills/":
        errors.append("skills must be './skills/'")

    author = manifest.get("author")
    if not isinstance(author, dict):
        errors.append("author must be an object")
    else:
        errors.extend(
            _fixed_object_fields_errors(author, PLUGIN_AUTHOR_FIELDS, "author")
        )
        errors.extend(_non_empty_string_errors(author.get("name"), "author.name"))
        errors.extend(_https_url_errors(author.get("url"), "author.url"))
        if author.get("name") != AUTHOR_NAME:
            errors.append(f"author.name must be {AUTHOR_NAME!r}")
        if author.get("url") != AUTHOR_URL:
            errors.append(f"author.url must be {AUTHOR_URL!r}")

    if manifest.get("homepage") != HOMEPAGE_URL:
        errors.append(f"homepage must be {HOMEPAGE_URL!r}")
    if manifest.get("repository") != REPOSITORY_URL:
        errors.append(f"repository must be {REPOSITORY_URL!r}")

    keywords = manifest.get("keywords")
    if (
        not isinstance(keywords, list)
        or not keywords
        or not all(isinstance(value, str) and value.strip() for value in keywords)
        or len({value.casefold() for value in keywords if isinstance(value, str)})
        != len(keywords)
    ):
        errors.append("keywords must be a non-empty array of unique, non-empty strings")

    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        errors.append("interface must be an object")
        return errors
    errors.extend(
        _fixed_object_fields_errors(
            interface,
            PLUGIN_INTERFACE_FIELDS,
            "interface",
        )
    )
    for field in (
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
    ):
        errors.extend(
            _non_empty_string_errors(interface.get(field), f"interface.{field}")
        )
    if interface.get("category") != "Productivity":
        errors.append("interface.category must be 'Productivity'")
    if interface.get("displayName") != DISPLAY_NAME:
        errors.append(f"interface.displayName must be {DISPLAY_NAME!r}")
    if interface.get("developerName") != AUTHOR_NAME:
        errors.append(f"interface.developerName must be {AUTHOR_NAME!r}")
    if interface.get("capabilities") != []:
        errors.append("interface.capabilities must be an empty array for a Skill-only plugin")
    errors.extend(
        _https_url_errors(interface.get("websiteURL"), "interface.websiteURL")
    )
    if interface.get("websiteURL") != REPOSITORY_URL:
        errors.append(f"interface.websiteURL must be {REPOSITORY_URL!r}")
    prompts = interface.get("defaultPrompt")
    if (
        not isinstance(prompts, list)
        or not 1 <= len(prompts) <= 3
        or not all(
            isinstance(prompt, str) and prompt.strip() and len(prompt) <= 128
            for prompt in prompts
        )
    ):
        errors.append(
            "interface.defaultPrompt must contain one to three non-empty strings of at most 128 characters"
        )
    elif not any(f"${SKILL_NAME}" in prompt for prompt in prompts):
        errors.append(f"interface.defaultPrompt must invoke ${SKILL_NAME}")
    return errors


def marketplace_contract_errors(marketplace: Mapping[str, object]) -> list[str]:
    """Validate the repository's fixed one-plugin marketplace schema."""

    errors = _fixed_object_fields_errors(
        marketplace,
        MARKETPLACE_FIELDS,
        "marketplace",
    )
    errors.extend(_non_empty_string_errors(marketplace.get("name"), "marketplace.name"))
    if marketplace.get("name") != PLUGIN_NAME:
        errors.append(f"marketplace.name must be {PLUGIN_NAME!r}")

    interface = marketplace.get("interface")
    if not isinstance(interface, dict):
        errors.append("marketplace.interface must be an object")
    else:
        errors.extend(
            _fixed_object_fields_errors(
                interface,
                MARKETPLACE_INTERFACE_FIELDS,
                "marketplace.interface",
            )
        )
        errors.extend(
            _non_empty_string_errors(
                interface.get("displayName"),
                "marketplace.interface.displayName",
            )
        )
        if interface.get("displayName") != DISPLAY_NAME:
            errors.append(
                f"marketplace.interface.displayName must be {DISPLAY_NAME!r}"
            )

    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        errors.append("marketplace.plugins must contain exactly one plugin entry")
        return errors
    entry = plugins[0]
    if not isinstance(entry, dict):
        errors.append("marketplace.plugins[0] must be an object")
        return errors
    errors.extend(
        _fixed_object_fields_errors(
            entry,
            MARKETPLACE_PLUGIN_FIELDS,
            "marketplace.plugins[0]",
        )
    )
    if entry.get("name") != PLUGIN_NAME:
        errors.append(f"marketplace.plugins[0].name must be {PLUGIN_NAME!r}")
    if entry.get("category") != "Productivity":
        errors.append("marketplace.plugins[0].category must be 'Productivity'")

    source = entry.get("source")
    if not isinstance(source, dict):
        errors.append("marketplace.plugins[0].source must be an object")
    else:
        errors.extend(
            _fixed_object_fields_errors(
                source,
                MARKETPLACE_SOURCE_FIELDS,
                "marketplace.plugins[0].source",
            )
        )
        if source.get("source") != "local":
            errors.append("marketplace.plugins[0].source.source must be 'local'")
        if source.get("path") != f"./plugins/{PLUGIN_NAME}":
            errors.append("marketplace.plugins[0].source.path is invalid")

    policy = entry.get("policy")
    if not isinstance(policy, dict):
        errors.append("marketplace.plugins[0].policy must be an object")
    else:
        errors.extend(
            _fixed_object_fields_errors(
                policy,
                MARKETPLACE_POLICY_FIELDS,
                "marketplace.plugins[0].policy",
            )
        )
        if policy.get("installation") != "AVAILABLE":
            errors.append(
                "marketplace.plugins[0].policy.installation must be 'AVAILABLE'"
            )
        if policy.get("authentication") != "ON_INSTALL":
            errors.append(
                "marketplace.plugins[0].policy.authentication must be 'ON_INSTALL'"
            )
    return errors


def forward_verification_plan(
    *,
    python_executable: str,
    repository: Path,
    scaffold_script: Path,
    verifier_script: Path,
    spec_path: Path,
    project_path: Path,
) -> tuple[CommandStep, ...]:
    return (
        CommandStep(
            (
                python_executable,
                str(scaffold_script),
                str(spec_path),
                str(project_path),
            ),
            repository,
        ),
        CommandStep(("npm", "run", "setup"), project_path),
        CommandStep(
            (
                python_executable,
                str(verifier_script),
                str(project_path),
                "--full",
            ),
            repository,
        ),
    )


def _plugin_paths(root: Path) -> dict[str, Path]:
    plugin = root / "plugins" / PLUGIN_NAME
    skill = plugin / "skills" / SKILL_NAME
    template = skill / "assets" / "course-template"
    return {
        "plugin": plugin,
        "skill": skill,
        "template": template,
        "platform": template / "platform",
        "scripts": skill / "scripts",
    }


def _read_project_version(root: Path) -> str:
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = payload.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise ValueError("pyproject.toml is missing project.version")
    return project["version"]


def _release_tag(root: Path, environment: Mapping[str, str]) -> str | None:
    if environment.get("GITHUB_REF_TYPE") == "tag":
        return environment.get("GITHUB_REF_NAME") or None
    result = subprocess.run(
        ["git", "describe", "--tags", "--exact-match", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def repository_contract_errors(
    root: Path,
    environment: Mapping[str, str],
) -> list[str]:
    paths = _plugin_paths(root)
    errors: list[str] = []
    manifest_path = paths["plugin"] / ".codex-plugin" / "plugin.json"
    marketplace_path = root / ".agents" / "plugins" / "marketplace.json"
    manifest, manifest_errors = _load_json_object(manifest_path)
    marketplace, marketplace_errors = _load_json_object(marketplace_path)
    errors.extend(manifest_errors)
    errors.extend(marketplace_errors)
    try:
        project_version = _read_project_version(root)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        errors.append(str(error))
        project_version = ""
    plugin_version = manifest.get("version") if manifest is not None else None
    if not isinstance(plugin_version, str):
        errors.append("plugin manifest is missing a string version")
    elif project_version:
        errors.extend(
            version_parity_errors(
                project_version,
                plugin_version,
                _release_tag(root, environment),
            )
        )
    if manifest is not None:
        errors.extend(plugin_manifest_errors(manifest))
    if marketplace is not None:
        errors.extend(marketplace_contract_errors(marketplace))
    for legal_name in ("LICENSE", "NOTICE"):
        root_file = root / legal_name
        template_file = paths["template"] / legal_name
        try:
            if root_file.read_bytes() != template_file.read_bytes():
                errors.append(f"root and template {legal_name} files differ")
        except OSError as error:
            errors.append(f"unable to compare {legal_name}: {error}")
    errors.extend(
        npm_lock_errors(
            paths["platform"] / "package.json",
            paths["platform"] / "package-lock.json",
        )
    )
    return errors


def _command_text(argv: Sequence[str]) -> str:
    return " ".join(argv)


def run_checked(
    argv: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
    timeout: int = 600,
) -> None:
    print(f"[release] $ {_command_text(argv)}")
    result = subprocess.run(
        list(argv),
        cwd=cwd,
        env=dict(environment) if environment is not None else None,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command exited {result.returncode}: {_command_text(argv)}"
        )


def _validation_environment(inherited: Mapping[str, str]) -> dict[str, str]:
    environment = dict(inherited)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def _forward_environment(inherited: Mapping[str, str], temporary: Path) -> dict[str, str]:
    environment = {
        key: value
        for key, value in inherited.items()
        if key in FORWARD_ENVIRONMENT_NAMES
    }
    home = temporary / "home"
    temp = temporary / "tmp"
    uv_cache = temporary / "uv-cache"
    npm_cache = temporary / "npm-cache"
    for directory in (home, temp, uv_cache, npm_cache):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "HOME": str(home),
            "TMPDIR": str(temp),
            "TEMP": str(temp),
            "TMP": str(temp),
            "UV_CACHE_DIR": str(uv_cache),
            "npm_config_cache": str(npm_cache),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
    )
    return environment


def _tool_errors() -> list[str]:
    errors: list[str] = []
    if sys.version_info[:2] != (3, 13):
        errors.append(
            "release validation requires Python 3.13, got "
            f"{sys.version_info.major}.{sys.version_info.minor}"
        )
    for executable in ("git", "node", "npm", "uv", "agentskills"):
        if shutil.which(executable) is None:
            errors.append(f"required executable is missing from PATH: {executable}")
    if shutil.which("node") is not None:
        result = subprocess.run(
            ["node", "--version"], text=True, capture_output=True, check=False
        )
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)\s*", result.stdout)
        if match is None or tuple(map(int, match.groups())) < MINIMUM_NODE_VERSION:
            errors.append("release validation requires Node.js >=22.13.0")
    if shutil.which("uv") is not None:
        result = subprocess.run(
            ["uv", "--version"], text=True, capture_output=True, check=False
        )
        actual = parse_uv_version(result.stdout)
        if actual != EXPECTED_UV_VERSION:
            errors.append(
                f"release validation requires uv {EXPECTED_UV_VERSION}, got {actual or 'unknown'}"
            )
    return errors


def parse_uv_version(output: str) -> str:
    match = re.match(r"^uv\s+(\d+\.\d+\.\d+)(?:\s|$)", output.strip())
    return match.group(1) if match is not None else ""


def _worktree_snapshot(root: Path) -> bytes:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("unable to snapshot git worktree")
    return result.stdout


def worktree_clean_errors(porcelain: bytes) -> list[str]:
    errors: list[str] = []
    for raw_entry in porcelain.decode("utf-8", errors="surrogateescape").split("\0"):
        if not raw_entry:
            continue
        if len(raw_entry) < 3:
            errors.append(f"release worktree is not clean: unknown {raw_entry!r}")
            continue
        status = raw_entry[:2]
        path = raw_entry[3:] if raw_entry[2:3] == " " else raw_entry[2:]
        if status == "??":
            errors.append(f"release worktree is not clean: untracked {path}")
            continue
        if status[0] != " ":
            errors.append(f"release worktree is not clean: staged {path}")
        if status[1] != " ":
            errors.append(f"release worktree is not clean: unstaged {path}")
    return errors


def run_official_codex_validators(root: Path, codex_home: Path) -> None:
    errors = codex_validator_errors(codex_home)
    if errors:
        raise RuntimeError("; ".join(errors))
    paths = _plugin_paths(root)
    validators = codex_validator_paths(codex_home)
    environment = _validation_environment(os.environ)
    run_checked(
        [sys.executable, str(validators["skill"]), str(paths["skill"])],
        cwd=root,
        environment=environment,
    )
    run_checked(
        [sys.executable, str(validators["plugin"]), str(paths["plugin"])],
        cwd=root,
        environment=environment,
    )


def run_forward_verification(root: Path) -> None:
    paths = _plugin_paths(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tests.course_v2_fixture import make_assessed_spec

    with tempfile.TemporaryDirectory(prefix="course-builder-forward-") as raw:
        temporary = Path(raw)
        spec_path = temporary / "course.json"
        project_path = temporary / "generated-course"
        spec_path.write_text(
            json.dumps(make_assessed_spec(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        plan = forward_verification_plan(
            python_executable=sys.executable,
            repository=root,
            scaffold_script=paths["scripts"] / "scaffold_course.py",
            verifier_script=paths["scripts"] / "verify_learning_project.py",
            spec_path=spec_path,
            project_path=project_path,
        )
        environment = _forward_environment(os.environ, temporary)
        for step in plan:
            run_checked(
                step.argv,
                cwd=step.cwd,
                environment=environment,
                timeout=1800,
            )


def validate_release(*, codex_validators: bool, forward: bool) -> None:
    root = repository_root()
    paths = _plugin_paths(root)
    before = _worktree_snapshot(root)
    errors = worktree_clean_errors(before)
    errors.extend(_tool_errors())
    errors.extend(repository_contract_errors(root, os.environ))
    errors.extend(scan_inventory(root, repository_inventory(root)))
    if errors:
        raise RuntimeError("\n".join(errors))

    environment = _validation_environment(os.environ)
    run_checked(["uv", "lock", "--check"], cwd=root, environment=environment)
    run_checked(
        ["uv", "lock", "--check", "--directory", str(paths["platform"])],
        cwd=root,
        environment=environment,
    )
    run_checked(
        ["agentskills", "validate", str(paths["skill"])],
        cwd=root,
        environment=environment,
    )
    run_checked(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        cwd=root,
        environment=environment,
        timeout=1200,
    )
    node_tests = sorted((paths["platform"] / "tests").glob("*.test.mjs"))
    if not node_tests:
        raise RuntimeError("no bundled Node contract tests were found")
    run_checked(
        ["node", "--test", *(str(path) for path in node_tests)],
        cwd=root,
        environment=environment,
    )
    run_checked(["git", "diff", "--check"], cwd=root, environment=environment)
    run_checked(
        ["git", "diff", "--cached", "--check"],
        cwd=root,
        environment=environment,
    )
    if codex_validators:
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        run_official_codex_validators(root, codex_home)
    if forward:
        run_forward_verification(root)
    after = _worktree_snapshot(root)
    if after != before:
        raise RuntimeError("release validation changed the Git worktree")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-validators",
        action="store_true",
        help="also run the official validators discovered under CODEX_HOME",
    )
    parser.add_argument(
        "--forward",
        action="store_true",
        help="generate, set up, and fully verify a temporary stdlib course",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_release(
            codex_validators=args.codex_validators,
            forward=args.forward,
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
        print(f"[release] FAILED\n{error}", file=sys.stderr)
        return 1
    print("[release] all requested checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
