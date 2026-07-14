from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_release.py"


def load_validator() -> ModuleType:
    assert VALIDATOR_PATH.is_file(), "scripts/validate_release.py is missing"
    spec = importlib.util.spec_from_file_location("release_validator", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inventory_scan_detects_secrets_private_paths_and_residue(
    tmp_path: Path,
) -> None:
    validator = load_validator()
    secret = tmp_path / "config.txt"
    secret.write_text("token=" + "ghp_" + "a" * 36 + "\n", encoding="utf-8")
    private_path = tmp_path / "notes.txt"
    private_path.write_text(
        "generated at " + "/" + "Users/alice/course/spec.json\n",
        encoding="utf-8",
    )
    residue = tmp_path / "platform" / "node_modules" / "package.js"
    residue.parent.mkdir(parents=True)
    residue.write_text("export default {};\n", encoding="utf-8")

    errors = validator.scan_inventory(
        tmp_path,
        (secret, private_path, residue),
    )

    rendered = "\n".join(errors).casefold()
    assert "secret" in rendered
    assert "private host path" in rendered
    assert "residue" in rendered


def test_inventory_scan_detects_symlinks(tmp_path: Path) -> None:
    validator = load_validator()
    target = tmp_path / "target.txt"
    target.write_text("safe\n", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(target.name)
    except OSError as error:
        pytest.skip(f"symlinks are unavailable: {error}")

    errors = validator.scan_inventory(tmp_path, (target, link))

    assert any("symlink" in error.casefold() for error in errors)


def test_inventory_scan_detects_windows_private_host_paths(tmp_path: Path) -> None:
    validator = load_validator()
    notes = tmp_path / "notes.txt"
    notes.write_text(
        "generated at " + "C:\\Users\\alice\\course\\spec.json\n",
        encoding="utf-8",
    )

    errors = validator.scan_inventory(tmp_path, (notes,))

    assert any("private host path" in error.casefold() for error in errors)


def test_inventory_scan_allows_contract_literals_under_tests(tmp_path: Path) -> None:
    validator = load_validator()
    contract = tmp_path / "tests" / "test_contract.py"
    contract.parent.mkdir()
    contract.write_text(
        "FORBIDDEN = "
        + repr(("CS61A" + "-style", "CS336" + "-style"))
        + "\n",
        encoding="utf-8",
    )

    assert validator.scan_inventory(tmp_path, (contract,)) == []


def test_npm_lock_validation_rejects_root_dependency_mismatch(tmp_path: Path) -> None:
    validator = load_validator()
    package_path = tmp_path / "package.json"
    lock_path = tmp_path / "package-lock.json"
    package_path.write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "0.1.0",
                "private": True,
                "engines": {"node": ">=22.13.0"},
                "dependencies": {"react": "19.2.6"},
                "devDependencies": {"typescript": "5.9.3"},
            }
        ),
        encoding="utf-8",
    )
    lock_path.write_text(
        json.dumps(
            {
                "name": "demo",
                "version": "0.1.0",
                "lockfileVersion": 3,
                "packages": {
                    "": {
                        "name": "demo",
                        "version": "0.1.0",
                        "engines": {"node": ">=22.13.0"},
                        "dependencies": {"react": "19.2.5"},
                        "devDependencies": {"typescript": "5.9.3"},
                    },
                    "node_modules/react": {"version": "19.2.5"},
                    "node_modules/typescript": {"version": "5.9.3"},
                },
            }
        ),
        encoding="utf-8",
    )

    errors = validator.npm_lock_errors(package_path, lock_path)

    assert any("dependencies" in error for error in errors)
    assert any("react" in error for error in errors)


def test_codex_validator_paths_are_derived_from_codex_home(tmp_path: Path) -> None:
    validator = load_validator()

    paths = validator.codex_validator_paths(tmp_path / "portable-codex-home")

    assert paths == {
        "skill": (
            tmp_path
            / "portable-codex-home"
            / "skills"
            / ".system"
            / "skill-creator"
            / "scripts"
            / "quick_validate.py"
        ),
        "plugin": (
            tmp_path
            / "portable-codex-home"
            / "skills"
            / ".system"
            / "plugin-creator"
            / "scripts"
            / "validate_plugin.py"
        ),
    }


def test_missing_official_codex_validators_fail_clearly(tmp_path: Path) -> None:
    validator = load_validator()

    errors = validator.codex_validator_errors(tmp_path / "missing-codex-home")

    assert len(errors) == 2
    assert all("official Codex" in error for error in errors)
    assert any("skill" in error.casefold() for error in errors)
    assert any("plugin" in error.casefold() for error in errors)


def test_version_parity_rejects_a_tag_mismatch() -> None:
    validator = load_validator()

    errors = validator.version_parity_errors("0.1.0", "0.1.0", "v0.2.0")

    assert errors == [
        "release tag v0.2.0 does not match project/plugin version 0.1.0"
    ]


def test_uv_version_parser_ignores_packager_metadata() -> None:
    validator = load_validator()

    assert (
        validator.parse_uv_version(
            "uv 0.11.7 (Homebrew 2026-04-15 aarch64-apple-darwin)\n"
        )
        == "0.11.7"
    )


def test_git_inventory_is_portable_and_includes_untracked_nonignored_files(
    tmp_path: Path,
) -> None:
    validator = load_validator()
    payload = (
        b"README.md\0"
        b"docs/file with spaces.md\0"
        + "docs/\u5b66\u4e60.md".encode()
        + b"\0untracked-release.txt\0"
    )

    inventory = validator.decode_git_inventory(tmp_path, payload)

    assert validator.git_inventory_command() == [
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    assert inventory == (
        tmp_path / "README.md",
        tmp_path / "docs" / "file with spaces.md",
        tmp_path / "docs" / "\u5b66\u4e60.md",
        tmp_path / "untracked-release.txt",
    )
    assert all(path.is_absolute() for path in inventory)


def test_repository_root_does_not_depend_on_current_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = load_validator()
    monkeypatch.chdir(tmp_path)

    assert validator.repository_root() == ROOT


def test_release_worktree_rejects_tracked_staged_and_untracked_changes() -> None:
    validator = load_validator()
    porcelain = (
        b" M tracked-change.txt\0"
        b"M  staged-change.txt\0"
        b"?? untracked-release.txt\0"
    )

    errors = validator.worktree_clean_errors(porcelain)

    assert errors == [
        "release worktree is not clean: unstaged tracked-change.txt",
        "release worktree is not clean: staged staged-change.txt",
        "release worktree is not clean: untracked untracked-release.txt",
    ]
    assert validator.worktree_clean_errors(b"") == []


def test_forward_plan_runs_scaffold_setup_and_full_verifier(tmp_path: Path) -> None:
    validator = load_validator()
    repository = tmp_path / "checkout"
    scripts = repository / "plugins" / "course-builder" / "skill" / "scripts"
    scaffold = scripts / "scaffold_course.py"
    verifier = scripts / "verify_learning_project.py"
    spec = tmp_path / "forward" / "course.json"
    project = tmp_path / "forward" / "generated-course"

    plan = validator.forward_verification_plan(
        python_executable="python3.13",
        repository=repository,
        scaffold_script=scaffold,
        verifier_script=verifier,
        spec_path=spec,
        project_path=project,
    )

    assert [(step.argv, step.cwd) for step in plan] == [
        (("python3.13", str(scaffold), str(spec), str(project)), repository),
        (("npm", "run", "setup"), project),
        (
            ("python3.13", str(verifier), str(project), "--full"),
            repository,
        ),
    ]


def test_forward_environment_is_a_closed_secret_free_allowlist(tmp_path: Path) -> None:
    validator = load_validator()
    inherited = {
        "PATH": "/portable/bin",
        "LANG": "en_US.UTF-8",
        "LC_TIME": "C",
        "LC_SECRET_TOKEN": "do-not-leak",
        "VIRTUAL_ENV": "/ambient/venv",
        "GITHUB_TOKEN": "do-not-leak",
        "AWS_SECRET_ACCESS_KEY": "do-not-leak",
        "COURSEKIT_INJECTED": "do-not-leak",
    }

    environment = validator._forward_environment(inherited, tmp_path / "isolated")

    assert environment["PATH"] == "/portable/bin"
    assert environment["LANG"] == "en_US.UTF-8"
    assert environment["LC_TIME"] == "C"
    assert "LC_SECRET_TOKEN" not in environment
    assert "VIRTUAL_ENV" not in environment
    assert "GITHUB_TOKEN" not in environment
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert "COURSEKIT_INJECTED" not in environment
    assert set(environment) == {
        "PATH",
        "LANG",
        "LC_TIME",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "UV_CACHE_DIR",
        "npm_config_cache",
        "PYTHONDONTWRITEBYTECODE",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    }
