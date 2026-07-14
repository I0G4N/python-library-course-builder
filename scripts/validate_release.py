#!/usr/bin/env python3
"""Run deterministic release checks from any working directory."""

from __future__ import annotations

import argparse
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


PLUGIN_NAME = "python-library-course-builder"
SKILL_NAME = "building-python-library-courses"
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
    "__COURSEKIT_PYTHON_REQUIRES__",
    "__COURSEKIT_ROUTE__",
    "__COURSEKIT_SLUG__",
    "__COURSEKIT_TARGET__",
    "__COURSEKIT_TARGET_VERSION__",
    "__COURSEKIT_TITLE__",
}
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
)
PRIVATE_HOST_PATTERNS = (
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"/private/(?:tmp|var/folders)/[A-Za-z0-9._/-]+"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
)
TEMPLATE_TOKEN_RE = re.compile(r"__COURSEKIT_[A-Z0-9_]+__")


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
    if relative.name in {".DS_Store", "coverage.xml", "course-verification.json"}:
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
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        is_contract_fixture = bool(relative.parts and relative.parts[0] == "tests")
        for secret_name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"possible secret ({secret_name}) in {label}")
        if any(pattern.search(text) for pattern in PRIVATE_HOST_PATTERNS):
            errors.append(f"private host path in {label}")
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


def npm_lock_errors(package_path: Path, lock_path: Path) -> list[str]:
    package, errors = _load_json_object(package_path)
    lock, lock_errors = _load_json_object(lock_path)
    errors.extend(lock_errors)
    if package is None or lock is None:
        return errors
    if lock.get("lockfileVersion") != 3:
        errors.append("package-lock.json must use lockfileVersion 3")
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
            if locked.get("version") != required_version:
                errors.append(
                    "package-lock direct dependency "
                    f"{name} version {locked.get('version')!r} does not match "
                    f"package.json {required_version!r}"
                )
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
        expected_fields = {
            "name": PLUGIN_NAME,
            "license": "Apache-2.0",
            "skills": "./skills/",
        }
        for field, expected in expected_fields.items():
            if manifest.get(field) != expected:
                errors.append(f"plugin manifest {field} must be {expected!r}")
        if "apps" in manifest or "mcpServers" in manifest:
            errors.append("skill-only plugin must not declare apps or mcpServers")
        author = manifest.get("author")
        if not isinstance(author, dict) or "email" in author:
            errors.append("plugin author must be an object without email")
        interface = manifest.get("interface")
        if not isinstance(interface, dict) or interface.get("capabilities") != []:
            errors.append("plugin direct capabilities must be an empty array")
    if marketplace is not None:
        if marketplace.get("name") != PLUGIN_NAME:
            errors.append(f"marketplace name must be {PLUGIN_NAME!r}")
        entries = marketplace.get("plugins")
        matches = (
            [item for item in entries if isinstance(item, dict) and item.get("name") == PLUGIN_NAME]
            if isinstance(entries, list)
            else []
        )
        if len(matches) != 1:
            errors.append("marketplace must contain exactly one plugin entry")
        else:
            entry = matches[0]
            if entry.get("source") != {
                "source": "local",
                "path": f"./plugins/{PLUGIN_NAME}",
            }:
                errors.append("marketplace plugin source path is invalid")
            if entry.get("policy") != {
                "installation": "AVAILABLE",
                "authentication": "ON_INSTALL",
            }:
                errors.append("marketplace plugin policy is invalid")
            if entry.get("category") != "Productivity":
                errors.append("marketplace plugin category must be 'Productivity'")
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
    from tests.course_v2_fixture import make_spec

    with tempfile.TemporaryDirectory(prefix="course-builder-forward-") as raw:
        temporary = Path(raw)
        spec_path = temporary / "course.json"
        project_path = temporary / "generated-course"
        spec_path.write_text(
            json.dumps(make_spec(), ensure_ascii=False, indent=2) + "\n",
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
