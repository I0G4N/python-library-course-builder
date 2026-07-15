from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
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


@pytest.mark.parametrize(
    "private_path",
    (
        "/" + "root/private-course/spec.json",
        "C:/" + "Users/alice/private-course/spec.json",
        "/" + "var/folders/ab/private-course/spec.json",
    ),
)
def test_inventory_scan_detects_additional_private_host_paths(
    tmp_path: Path,
    private_path: str,
) -> None:
    validator = load_validator()
    notes = tmp_path / "notes.txt"
    notes.write_text(f"generated at {private_path}\n", encoding="utf-8")

    errors = validator.scan_inventory(tmp_path, (notes,))

    assert any("private host path" in error.casefold() for error in errors)


def test_inventory_scan_rejects_tracked_nul_binary_with_secret(tmp_path: Path) -> None:
    validator = load_validator()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    binary = tmp_path / "tracked.bin"
    binary.write_bytes(b"header\0token=" + b"ghp_" + b"a" * 36 + b"\0tail")
    subprocess.run(["git", "add", binary.name], cwd=tmp_path, check=True)

    inventory = validator.repository_inventory(tmp_path)
    errors = validator.scan_inventory(tmp_path, inventory)

    assert binary in inventory
    assert any("secret" in error.casefold() for error in errors)


def test_inventory_scan_rejects_coverage_database_residue(tmp_path: Path) -> None:
    validator = load_validator()
    coverage = tmp_path / ".coverage"
    coverage.write_bytes(b"SQLite format 3\0")

    errors = validator.scan_inventory(tmp_path, (coverage,))

    assert any("residue" in error.casefold() for error in errors)


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


@pytest.mark.parametrize(
    "filename", ("README.md", "README.zh-CN.md", "CHANGELOG.md")
)
@pytest.mark.parametrize("spelling", ("CS61A-style", "CS61A-Style", "cs61a-style"))
def test_inventory_scan_allows_cs61a_style_only_in_root_marketing_docs(
    tmp_path: Path,
    filename: str,
    spelling: str,
) -> None:
    validator = load_validator()
    document = tmp_path / filename
    document.write_text(f"A {spelling} course builder.\n", encoding="utf-8")

    assert validator.scan_inventory(tmp_path, (document,)) == []


@pytest.mark.parametrize(
    "relative_name",
    (
        "SECURITY.md",
        "docs/README.md",
        "plugins/example/skills/example/SKILL.md",
    ),
)
@pytest.mark.parametrize("spelling", ("CS61A-style", "CS61A-Style", "cs61a-style"))
def test_inventory_scan_rejects_cs61a_style_outside_root_marketing_docs(
    tmp_path: Path,
    relative_name: str,
    spelling: str,
) -> None:
    validator = load_validator()
    document = tmp_path / relative_name
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(f"A {spelling} course builder.\n", encoding="utf-8")

    errors = validator.scan_inventory(tmp_path, (document,))

    assert any("legacy course branding" in error for error in errors)


def test_release_template_token_allowlist_matches_the_shipped_template() -> None:
    validator = load_validator()
    template_root = (
        ROOT
        / "plugins"
        / "python-library-course-builder"
        / "skills"
        / "building-python-library-courses"
        / "assets"
        / "course-template"
    )
    shipped_tokens = {
        token
        for path in template_root.rglob("*")
        if path.is_file()
        for token in validator.TEMPLATE_TOKEN_RE.findall(
            path.read_text(encoding="utf-8")
        )
    }

    assert validator.EXPECTED_TEMPLATE_TOKENS == shipped_tokens


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


def test_npm_lock_validation_accepts_complete_platform_graph() -> None:
    validator = load_validator()
    platform = (
        ROOT
        / "plugins"
        / "python-library-course-builder"
        / "skills"
        / "building-python-library-courses"
        / "assets"
        / "course-template"
        / "platform"
    )

    assert (
        validator.npm_lock_errors(
            platform / "package.json",
            platform / "package-lock.json",
        )
        == []
    )


def test_npm_lock_validation_rejects_missing_transitive_dependency(
    tmp_path: Path,
) -> None:
    validator = load_validator()
    platform = (
        ROOT
        / "plugins"
        / "python-library-course-builder"
        / "skills"
        / "building-python-library-courses"
        / "assets"
        / "course-template"
        / "platform"
    )
    package_path = tmp_path / "package.json"
    lock_path = tmp_path / "package-lock.json"
    package_path.write_bytes((platform / "package.json").read_bytes())
    lock = json.loads((platform / "package-lock.json").read_text(encoding="utf-8"))
    lock["packages"].pop("node_modules/scheduler")
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    errors = validator.npm_lock_errors(package_path, lock_path)

    rendered = "\n".join(errors)
    assert "scheduler" in rendered
    assert "dependency" in rendered


def test_npm_lock_validation_rejects_corrupt_registry_metadata(tmp_path: Path) -> None:
    validator = load_validator()
    platform = (
        ROOT
        / "plugins"
        / "python-library-course-builder"
        / "skills"
        / "building-python-library-courses"
        / "assets"
        / "course-template"
        / "platform"
    )
    package_path = tmp_path / "package.json"
    lock_path = tmp_path / "package-lock.json"
    package_path.write_bytes((platform / "package.json").read_bytes())
    lock = json.loads((platform / "package-lock.json").read_text(encoding="utf-8"))
    scheduler = lock["packages"]["node_modules/scheduler"]
    scheduler["resolved"] = "http://registry.npmjs.org/scheduler/-/scheduler.tgz"
    scheduler["integrity"] = "sha256-not-a-sha512-digest"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    errors = validator.npm_lock_errors(package_path, lock_path)

    rendered = "\n".join(errors)
    assert "scheduler" in rendered
    assert "resolved" in rendered
    assert "integrity" in rendered
    assert "sha512" in rendered


def test_npm_lock_metadata_allows_only_local_link_and_file_exceptions() -> None:
    validator = load_validator()
    packages = {
        "node_modules/workspace": {
            "link": True,
            "resolved": "packages/workspace",
        },
        "node_modules/local-archive": {
            "version": "1.2.3",
            "resolved": "file:vendor/local-archive.tgz",
        },
    }

    assert (
        validator._npm_registry_metadata_errors(
            "node_modules/workspace",
            packages["node_modules/workspace"],
            packages,
        )
        == []
    )
    assert (
        validator._npm_registry_metadata_errors(
            "node_modules/local-archive",
            packages["node_modules/local-archive"],
            packages,
        )
        == []
    )

    remote_link = {"link": True, "resolved": "https://example.invalid/package"}
    errors = validator._npm_registry_metadata_errors(
        "node_modules/remote-link",
        remote_link,
        {"node_modules/remote-link": remote_link},
    )

    assert any("local resolved path" in error for error in errors)

    for resolved in (
        "file:../../outside.tgz",
        "file:%2e%2e/outside.tgz",
        "../outside-workspace",
        "..\\outside-workspace",
    ):
        traversal = {"link": True, "resolved": resolved}
        traversal_errors = validator._npm_registry_metadata_errors(
            "node_modules/traversal-link",
            traversal,
            {"node_modules/traversal-link": traversal},
        )
        assert any("local resolved path" in error for error in traversal_errors)


def test_npm_lock_graph_accepts_contained_workspace_link(tmp_path: Path) -> None:
    validator = load_validator()
    package = {
        "name": "demo",
        "version": "0.1.0",
        "engines": {"node": ">=22.13.0"},
        "dependencies": {"workspace": "workspace:*"},
        "devDependencies": {},
    }
    lock = {
        "name": "demo",
        "version": "0.1.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": {
            "": dict(package),
            "node_modules/workspace": {
                "resolved": "packages/workspace",
                "link": True,
            },
            "packages/workspace": {
                "name": "workspace",
                "version": "1.0.0",
            },
        },
    }
    package_path = tmp_path / "package.json"
    lock_path = tmp_path / "package-lock.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    assert validator.npm_lock_errors(package_path, lock_path) == []

    lock["packages"].pop("packages/workspace")
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    missing_target_errors = validator.npm_lock_errors(package_path, lock_path)

    assert any("link target" in error for error in missing_target_errors)

    lock["packages"]["packages/workspace"] = {
        "name": "workspace",
        "version": "1.0.0",
    }
    package["dependencies"]["workspace"] = "1.0.0"
    lock["packages"][""]["dependencies"]["workspace"] = "1.0.0"
    package_path.write_text(json.dumps(package), encoding="utf-8")
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    override_errors = validator.npm_lock_errors(package_path, lock_path)

    assert any("local override" in error for error in override_errors)


def test_repository_owned_plugin_and_marketplace_schemas_accept_release_metadata() -> None:
    validator = load_validator()
    manifest = json.loads(
        (
            ROOT
            / "plugins"
            / "python-library-course-builder"
            / ".codex-plugin"
            / "plugin.json"
        ).read_text(encoding="utf-8")
    )
    marketplace = json.loads(
        (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
            encoding="utf-8"
        )
    )

    assert validator.plugin_manifest_errors(manifest) == []
    assert validator.marketplace_contract_errors(marketplace) == []


def test_plugin_schema_rejects_missing_unknown_and_malformed_metadata() -> None:
    validator = load_validator()
    manifest_path = (
        ROOT
        / "plugins"
        / "python-library-course-builder"
        / ".codex-plugin"
        / "plugin.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    missing_description = deepcopy(manifest)
    missing_description.pop("description")
    unknown_field = deepcopy(manifest)
    unknown_field["unexpected"] = True
    unsafe_fields = deepcopy(manifest)
    unsafe_fields.update(
        {
            "version": "01.2.3",
            "homepage": "http://example.invalid/plugin",
            "keywords": ["python", ""],
            "apps": "./.app.json",
            "mcpServers": "./.mcp.json",
        }
    )
    unsafe_fields["author"]["email"] = "private@example.invalid"
    unsafe_fields["interface"]["capabilities"] = ["Write"]
    unsafe_fields["interface"]["defaultPrompt"] = "not-a-list"

    missing_errors = validator.plugin_manifest_errors(missing_description)
    unknown_errors = validator.plugin_manifest_errors(unknown_field)
    unsafe_errors = validator.plugin_manifest_errors(unsafe_fields)

    assert any("description" in error for error in missing_errors)
    assert any("unexpected" in error for error in unknown_errors)
    rendered = "\n".join(unsafe_errors)
    for field in (
        "version",
        "homepage",
        "keywords",
        "apps",
        "mcpServers",
        "author.email",
        "capabilities",
        "defaultPrompt",
    ):
        assert field in rendered


@pytest.mark.parametrize(
    ("field_path", "invalid_value"),
    (
        (("author", "name"), "Someone Else"),
        (("author", "url"), "https://example.invalid/author"),
        (("author", "url"), "https://[::1"),
        (("homepage",), "https://example.invalid/readme"),
        (("repository",), "https://example.invalid/repository"),
        (("repository",), "https://example.invalid:notaport/repository"),
        (("interface", "displayName"), "Different Plugin"),
        (("interface", "developerName"), "Someone Else"),
        (("interface", "websiteURL"), "https://example.invalid/plugin"),
    ),
)
def test_plugin_schema_rejects_wrong_identity_and_malformed_urls(
    field_path: tuple[str, ...],
    invalid_value: str,
) -> None:
    validator = load_validator()
    manifest = json.loads(
        (
            ROOT
            / "plugins"
            / "python-library-course-builder"
            / ".codex-plugin"
            / "plugin.json"
        ).read_text(encoding="utf-8")
    )
    target = manifest
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = invalid_value

    errors = validator.plugin_manifest_errors(manifest)

    assert any(".".join(field_path) in error for error in errors)


def test_marketplace_schema_rejects_missing_display_name_and_unknown_fields() -> None:
    validator = load_validator()
    marketplace = json.loads(
        (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
            encoding="utf-8"
        )
    )
    missing_display_name = deepcopy(marketplace)
    missing_display_name["interface"].pop("displayName")
    unknown_fields = deepcopy(marketplace)
    unknown_fields["unexpected"] = True
    unknown_fields["plugins"][0]["source"]["branch"] = "main"
    unknown_fields["plugins"][0]["policy"]["products"] = ["codex"]

    missing_errors = validator.marketplace_contract_errors(missing_display_name)
    unknown_errors = validator.marketplace_contract_errors(unknown_fields)

    assert any("interface.displayName" in error for error in missing_errors)
    rendered = "\n".join(unknown_errors)
    assert "unexpected" in rendered
    assert "source.branch" in rendered
    assert "policy.products" in rendered


def test_marketplace_schema_rejects_wrong_identity_and_extra_entries() -> None:
    validator = load_validator()
    marketplace = json.loads(
        (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
            encoding="utf-8"
        )
    )
    wrong_display_name = deepcopy(marketplace)
    wrong_display_name["interface"]["displayName"] = "Different Marketplace"
    extra_entry = deepcopy(marketplace)
    extra_entry["plugins"].append(deepcopy(extra_entry["plugins"][0]))

    identity_errors = validator.marketplace_contract_errors(wrong_display_name)
    entry_errors = validator.marketplace_contract_errors(extra_entry)

    assert any("interface.displayName" in error for error in identity_errors)
    assert any("exactly one" in error for error in entry_errors)


def test_repository_contract_runs_owned_manifest_and_marketplace_validators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = load_validator()
    monkeypatch.setattr(
        validator,
        "plugin_manifest_errors",
        lambda manifest: ["owned plugin schema sentinel"],
    )
    monkeypatch.setattr(
        validator,
        "marketplace_contract_errors",
        lambda marketplace: ["owned marketplace schema sentinel"],
    )

    errors = validator.repository_contract_errors(ROOT, {})

    assert "owned plugin schema sentinel" in errors
    assert "owned marketplace schema sentinel" in errors


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
    readiness_plan = tmp_path / "forward" / "readiness-plan.json"
    project = tmp_path / "forward" / "generated-course"

    plan = validator.forward_verification_plan(
        python_executable="python3.13",
        repository=repository,
        scaffold_script=scaffold,
        verifier_script=verifier,
        spec_path=spec,
        readiness_plan_path=readiness_plan,
        project_path=project,
    )

    assert [(step.argv, step.cwd) for step in plan] == [
        (
            (
                "python3.13",
                str(scaffold),
                str(spec),
                str(project),
                "--readiness-plan",
                str(readiness_plan),
            ),
            repository,
        ),
        (("npm", "run", "setup"), project),
        (
            ("python3.13", str(verifier), str(project), "--full"),
            repository,
        ),
    ]


def test_forward_verification_writes_the_v3_course_and_readiness_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.course_v3_fixture import make_v3_spec_and_plan

    validator = load_validator()
    captured: dict[str, dict[str, object]] = {}

    def capture_plan(**kwargs: object) -> tuple[()]:
        spec_path = kwargs["spec_path"]
        readiness_plan_path = kwargs["readiness_plan_path"]
        assert isinstance(spec_path, Path)
        assert isinstance(readiness_plan_path, Path)
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        readiness_plan = json.loads(
            readiness_plan_path.read_text(encoding="utf-8")
        )
        language = str(spec["course"]["language"])
        captured[language] = {
            "spec": spec,
            "readiness_plan": readiness_plan,
        }
        return ()

    monkeypatch.setattr(validator, "forward_verification_plan", capture_plan)

    validator.run_forward_verification(ROOT)

    expected: dict[str, dict[str, object]] = {}
    for language in ("zh-CN", "en"):
        spec, readiness_plan = make_v3_spec_and_plan(
            missing_ids={"json-data-model", "domain-boundary"},
            language=language,
        )
        expected[language] = {
            "spec": spec,
            "readiness_plan": readiness_plan,
        }
    assert captured == expected


def test_forward_fixtures_contain_real_learner_prose_in_each_locale() -> None:
    from tests.course_v3_fixture import make_v3_spec_and_plan

    validator = load_validator()
    for language in ("zh-CN", "en"):
        spec, readiness_plan = make_v3_spec_and_plan(
            missing_ids={"json-data-model", "domain-boundary"},
            language=language,
        )
        assert validator.forward_fixture_locale_errors(
            language,
            spec,
            readiness_plan,
        ) == []

    english_spec, english_plan = make_v3_spec_and_plan(language="en")
    english_spec["course"]["title"] = "混合语言课程"
    assert "English forward fixture contains Han learner-facing text" in (
        validator.forward_fixture_locale_errors(
            "en",
            english_spec,
            english_plan,
        )
    )

    chinese_spec, chinese_plan = make_v3_spec_and_plan(language="zh-CN")
    chinese_spec["course"]["description"] = "An otherwise English course description."
    assert (
        "zh-CN learner-facing field must contain Chinese text: "
        "spec.course.description"
    ) in validator.forward_fixture_locale_errors(
        "zh-CN",
        chinese_spec,
        chinese_plan,
    )


def test_generated_forward_locale_gate_checks_prose_and_first_paint(
    tmp_path: Path,
) -> None:
    validator = load_validator()
    project = tmp_path / "generated"
    surfaces = {
        "README.md": "# English JSON course\n\n## Prerequisites\n",
        "labs/README.md": "# Learner workspace\n",
        "platform/course/content.json": '{"lesson":"English lesson"}\n',
        "platform/course/manifest.json": '{"language":"en"}\n',
        "platform/app/courseLocale.mjs": (
            'const GENERATED_COURSE_LANGUAGE = "en";\n'
        ),
    }
    for relative, content in surfaces.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    assert validator.forward_generated_locale_errors(project, "en") == []

    (project / "platform/course/content.json").write_text(
        '{"lesson":"混合语言"}\n',
        encoding="utf-8",
    )
    assert any(
        "contains Han text" in error
        for error in validator.forward_generated_locale_errors(project, "en")
    )


def test_zh_cn_generated_locale_gate_requires_framework_and_lesson_anchors(
    tmp_path: Path,
) -> None:
    validator = load_validator()
    project = tmp_path / "generated-zh-cn"
    unit = {
        "title": "Lab 00：学习导览",
        "lesson_outline": {
            "problem": {"context": "使用具体输入理解课程边界。"},
            "outcomes": [{"text": "追踪输入与输出。"}],
            "concepts": [{"definition": "课程边界是一条可观察的约定。"}],
        },
    }
    surfaces = {
        "README.md": "# 中文课程\n\n## 课程路线\n\n## 开始学习\n\n完成知识检查。\n",
        "labs/README.md": (
            "# 中文课程学员工作区\n\n从 `lab00/README.md` 开始。\n\n"
            "公开测试位于起始代码旁边。\n"
        ),
        "platform/course/content.json": json.dumps(
            {"preparatory_units": [unit], "labs": [unit]},
            ensure_ascii=False,
        ),
        "platform/course/manifest.json": json.dumps(
            {
                "language": "zh-CN",
                "title": "中文课程",
                "preparatory_units": [{"title": "Lab 00：学习导览"}],
                "labs": [{"title": "Lab 01：正式练习"}],
            },
            ensure_ascii=False,
        ),
        "platform/app/courseLocale.mjs": (
            'const GENERATED_COURSE_LANGUAGE = "zh-CN";\n'
        ),
    }
    for relative, content in surfaces.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    assert validator.forward_generated_locale_errors(project, "zh-CN") == []

    (project / "README.md").write_text(
        "# 中文课程\n\n## Course route\n\n## 开始学习\n\n完成知识检查。\n",
        encoding="utf-8",
    )
    errors = validator.forward_generated_locale_errors(project, "zh-CN")
    assert any("missing anchor '## 课程路线'" in error for error in errors)

    content = json.loads(
        (project / "platform/course/content.json").read_text(encoding="utf-8")
    )
    content["labs"][0]["lesson_outline"]["problem"]["context"] = (
        "An English-only lesson context."
    )
    (project / "platform/course/content.json").write_text(
        json.dumps(content, ensure_ascii=False),
        encoding="utf-8",
    )
    errors = validator.forward_generated_locale_errors(project, "zh-CN")
    assert any(
        "generated content.labs[0].lesson_outline.problem.context" in error
        for error in errors
    )


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
