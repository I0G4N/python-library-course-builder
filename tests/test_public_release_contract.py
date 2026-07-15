from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "python-library-course-builder"
SKILL_NAME = "building-python-library-courses"
SKILL_DESCRIPTION = (
    "Use when a user asks to build, create, author, or learn through a "
    "structured, Chinese-first hands-on course project for a Python "
    "standard-library module, PyPI package, framework, or repository instead "
    "of receiving a one-off explanation."
)
SKILL_SHORT_DESCRIPTION = "Build Chinese-first Python learning projects"
SKILL_DEFAULT_PROMPT = (
    "Use $building-python-library-courses to create a source-backed "
    "Chinese-first course for a Python library or repository."
)
PLUGIN_ROOT = ROOT / "plugins" / PLUGIN_NAME
SKILL_ROOT = PLUGIN_ROOT / "skills" / SKILL_NAME
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "course-template"
PLATFORM_ROOT = TEMPLATE_ROOT / "platform"
MARKETPLACE_PATH = ROOT / ".agents" / "plugins" / "marketplace.json"

sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(PLATFORM_ROOT))

import runner.execution as runner_execution  # noqa: E402
import verify_learning_project as verifier  # noqa: E402
from coursekit.compiler import SourceValidationError, load_course_source  # noqa: E402
from scaffold_course import copy_template, write_canonical_source  # noqa: E402
from validate_course import SpecValidationError, validate_spec  # noqa: E402

from tests.course_v2_fixture import make_spec  # noqa: E402


def _required_text(path: Path) -> str:
    try:
        label = path.relative_to(ROOT)
    except ValueError:
        label = path
    assert path.is_file(), f"required public file is missing: {label}"
    return path.read_text(encoding="utf-8")


def _required_json(path: Path) -> dict[str, Any]:
    return json.loads(_required_text(path))


def _skill_frontmatter_and_body() -> tuple[dict[str, Any], str]:
    document = _required_text(SKILL_ROOT / "SKILL.md")
    match = re.fullmatch(
        r"---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)",
        document,
        re.DOTALL,
    )
    assert match is not None, "SKILL.md needs one YAML frontmatter block"
    frontmatter = yaml.safe_load(match.group("frontmatter"))
    assert isinstance(frontmatter, dict), "SKILL.md frontmatter must be a mapping"
    return frontmatter, match.group("body")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _fenced_shell_commands(document: str) -> set[str]:
    blocks = re.findall(
        r"^```(?:bash|sh)\s*$\n(?P<body>.*?)^```\s*$",
        document,
        re.MULTILINE | re.DOTALL,
    )
    return {
        line.strip()
        for block in blocks
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _authoring_accepts(spec: dict[str, Any]) -> bool:
    try:
        validate_spec(spec)
    except SpecValidationError:
        return False
    return True


def _compiled_source_accepts(source: Path) -> bool:
    try:
        load_course_source(source)
    except SourceValidationError:
        return False
    return True


def _github_anchor(title: str) -> str:
    normalized = re.sub(r"[^\w\- ]", "", title.strip().casefold())
    return re.sub(r"[ ]+", "-", normalized)


def _permission_has_write(value: Any) -> bool:
    if isinstance(value, str):
        return value.casefold() == "write-all" or value.casefold() == "write"
    if isinstance(value, dict):
        return any(_permission_has_write(item) for item in value.values())
    if isinstance(value, list):
        return any(_permission_has_write(item) for item in value)
    return False


def test_plugin_manifest_and_marketplace_publish_exact_skill_only_metadata() -> None:
    manifest = _required_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")

    assert manifest["name"] == PLUGIN_NAME
    assert manifest["version"] == "0.1.0"
    assert manifest["author"]["name"] == "I0G4N"
    assert manifest["author"]["url"] == "https://github.com/I0G4N"
    assert "email" not in manifest["author"]
    assert manifest["license"] == "Apache-2.0"
    assert manifest["skills"] == "./skills/"
    assert "apps" not in manifest
    assert "mcpServers" not in manifest
    interface = manifest["interface"]
    assert interface["capabilities"] == []
    prompts = interface.get("defaultPrompt")
    assert isinstance(prompts, list) and all(
        isinstance(prompt, str) for prompt in prompts
    )
    assert any(
        "$building-python-library-courses" in prompt
        for prompt in prompts
    )

    marketplace = _required_json(MARKETPLACE_PATH)
    assert marketplace["name"] == PLUGIN_NAME
    matching_entries = [
        item for item in marketplace["plugins"] if item.get("name") == PLUGIN_NAME
    ]
    assert len(matching_entries) == 1
    entry = matching_entries[0]
    assert entry["source"] == {
        "source": "local",
        "path": f"./plugins/{PLUGIN_NAME}",
    }
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }


def test_skill_discovery_and_ui_metadata_are_synchronized() -> None:
    frontmatter, body = _skill_frontmatter_and_body()

    assert frontmatter == {
        "name": SKILL_NAME,
        "description": SKILL_DESCRIPTION,
    }
    assert SKILL_ROOT.name == frontmatter["name"]
    assert len(body.split()) <= 1_500, "SKILL.md must use progressive disclosure"

    reference_names = (
        "architecture.md",
        "authoring-rubric.md",
        "curriculum-contract.md",
        "forward-test-rubric.md",
    )
    for name in reference_names:
        assert f"](references/{name})" in body, f"SKILL.md must route readers to {name}"

    openai = yaml.safe_load(_required_text(SKILL_ROOT / "agents" / "openai.yaml"))
    assert openai == {
        "interface": {
            "display_name": "Python Library Course Builder",
            "short_description": SKILL_SHORT_DESCRIPTION,
            "default_prompt": SKILL_DEFAULT_PROMPT,
        }
    }
    assert 25 <= len(SKILL_SHORT_DESCRIPTION) <= 64
    assert f"${SKILL_NAME}" in SKILL_DEFAULT_PROMPT

    manifest = _required_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    assert manifest["interface"]["shortDescription"] == SKILL_SHORT_DESCRIPTION
    assert manifest["interface"]["defaultPrompt"] == [SKILL_DEFAULT_PROMPT]


def test_skill_routes_references_at_point_of_use() -> None:
    _, body = _skill_frontmatter_and_body()
    point_of_use_routes = (
        "Read [curriculum-contract.md](references/curriculum-contract.md) "
        "before writing the specification.",
        "Apply [authoring-rubric.md](references/authoring-rubric.md) while "
        "designing lessons, exercises, and tests.",
        "Read [architecture.md](references/architecture.md) before validating "
        "the generated runtime and ownership boundaries.",
        "Use [forward-test-rubric.md](references/forward-test-rubric.md) for "
        "the required local generated-project acceptance matrix.",
    )
    for route in point_of_use_routes:
        assert route in body, f"SKILL.md needs point-of-use routing: {route}"


def test_forward_acceptance_is_local_generated_project_only() -> None:
    forward = _required_text(SKILL_ROOT / "references" / "forward-test-rubric.md")

    assert "acceptance gate for a **local generated project**" in forward
    assert "scripts/verify_learning_project.py" in forward
    assert "## Required fail-closed negative tests" in forward
    assert "## Required generated-project acceptance matrix" in forward
    for removed_gate in (
        "fresh-agent",
        "fresh agent",
        "paired skill-output",
        "old output",
        "new output",
        "10/12",
        "transfer evaluation",
        "no-skill baseline",
    ):
        assert removed_gate not in forward.lower()


def test_skill_preserves_specification_to_split_source_boundary() -> None:
    _, body = _skill_frontmatter_and_body()
    authoring_contract = "Author one UTF-8 schema-v3 JSON specification"
    generation_contract = "The scaffolder creates the split canonical source"

    assert authoring_contract in body
    assert generation_contract in body
    assert body.index(authoring_contract) < body.index(generation_contract)


def test_changelog_publishes_the_release_version_from_project_metadata() -> None:
    changelog = _required_text(ROOT / "CHANGELOG.md")
    release = re.search(
        r"^## \[(?P<version>[^]]+)] - (?P<date>\d{4}-\d{2}-\d{2})$",
        changelog,
        re.MULTILINE,
    )
    assert release is not None, "CHANGELOG.md needs a versioned release heading"

    project = tomllib.loads(_required_text(ROOT / "pyproject.toml"))
    manifest = _required_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    changelog_version = release.group("version")

    assert changelog_version == "0.1.0"
    assert release.group("date") == "2026-07-15"
    assert project["project"]["version"] == changelog_version
    assert manifest["version"] == changelog_version


def test_release_docs_link_the_changelog_and_publish_exact_validation_commands() -> None:
    readme = _required_text(ROOT / "README.md")
    contributing = _required_text(ROOT / "CONTRIBUTING.md")
    checklist = _required_text(ROOT / "RELEASE_CHECKLIST.md")
    changelog_link = re.compile(
        r"\[[^]\n]*changelog[^]\n]*]\(CHANGELOG\.md\)",
        re.IGNORECASE,
    )

    assert changelog_link.search(readme), "README.md must link CHANGELOG.md"
    assert changelog_link.search(checklist), (
        "RELEASE_CHECKLIST.md must link CHANGELOG.md"
    )

    commands = _fenced_shell_commands(contributing)
    required_commands = {
        "uv sync --locked",
        "uv run python scripts/validate_release.py",
        "uv run python scripts/validate_release.py --codex-validators",
        (
            "uv run python scripts/validate_release.py "
            "--codex-validators --forward"
        ),
    }
    assert required_commands <= commands, (
        "CONTRIBUTING.md must publish copyable locked deterministic and "
        f"forward validation commands; missing {sorted(required_commands - commands)}"
    )
    assert re.search(r"^- \[ \] ", checklist, re.MULTILINE)
    assert not re.search(r"^- \[[xX]\] ", checklist, re.MULTILINE)


def test_readme_publishes_a_generic_local_marketplace_install_flow() -> None:
    commands = _fenced_shell_commands(_required_text(ROOT / "README.md"))

    assert "codex plugin marketplace add ./python-library-course-builder" in commands
    assert (
        "codex plugin add "
        "python-library-course-builder@python-library-course-builder"
    ) in commands


def test_public_repository_files_and_generated_template_license_are_present(
    tmp_path: Path,
) -> None:
    required = (
        "README.md",
        "LICENSE",
        "NOTICE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        ".gitignore",
    )
    missing = [name for name in required if not (ROOT / name).is_file()]
    assert not missing, f"missing public repository files: {missing}"

    root_license = _required_text(ROOT / "LICENSE")
    root_notice = _required_text(ROOT / "NOTICE")
    assert "Apache License" in root_license
    assert "Version 2.0" in root_license

    generated = tmp_path / "generated-course"
    copy_template(generated)
    assert _required_text(generated / "LICENSE") == root_license
    assert _required_text(generated / "NOTICE") == root_notice


def test_public_docs_are_neutral_navigable_and_state_runtime_boundaries() -> None:
    forbidden = ("ConcurrencyLab", "CS61A-style", "CS336-style")
    text_suffixes = {
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".mjs",
        ".py",
        ".toml",
        ".ts",
        ".tsx",
        ".yaml",
        ".yml",
    }
    occurrences: list[str] = []
    for path in sorted(SKILL_ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        for term in forbidden:
            if term.casefold() in text.casefold():
                occurrences.append(f"{path.relative_to(SKILL_ROOT)}: {term}")
    assert not occurrences, "internal/runtime labels remain:\n" + "\n".join(occurrences)

    invalid_contents: list[str] = []
    for path in sorted((SKILL_ROOT / "references").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if len(text.splitlines()) <= 100:
            continue
        contents = re.search(
            r"^## (?:Table of contents|Contents)\s*$\n(?P<body>.*?)(?=^## |\Z)",
            text,
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        headings = {
            _github_anchor(match.group(1))
            for match in re.finditer(r"^#{2,6}\s+(.+?)\s*$", text, re.MULTILINE)
            if match.group(1).casefold() not in {"table of contents", "contents"}
        }
        links = (
            re.findall(r"\[[^\]]+\]\(#([^)]+)\)", contents.group("body"))
            if contents is not None
            else []
        )
        if not links or not any(link.casefold() in headings for link in links):
            invalid_contents.append(path.name)
    assert not invalid_contents, (
        "long references need a TOC with a real heading anchor: "
        f"{invalid_contents}"
    )

    documents = {
        "README.md": _required_text(ROOT / "README.md"),
        "SKILL.md": _required_text(SKILL_ROOT / "SKILL.md"),
    }
    for name, document in documents.items():
        lowered = document.casefold()
        assert re.search(r"^## (?:prerequisites|requirements)$", document, re.MULTILINE), name
        for prerequisite in ("python 3.13", "uv", "node.js 22.13", "git"):
            assert prerequisite in lowered, f"{name} does not state {prerequisite}"
        assert "authoring repository" in lowered, name
        assert "hidden tests are not secret" in lowered, name


def test_direct_dependencies_and_official_sources_require_safe_immutable_urls(
    tmp_path: Path,
) -> None:
    sha256 = "a" * 64
    commit = "b" * 40
    invalid_dependencies = {
        "dependency userinfo": (
            f"demo @ https://user:password@example.com/demo.whl#sha256={sha256}"
        ),
        "dependency sensitive query": (
            f"demo @ https://example.com/demo.whl?token=secret#sha256={sha256}"
        ),
        "git reference missing": "demo @ git+https://github.com/example/demo.git",
        "git tag": "demo @ git+https://github.com/example/demo.git@v1.2.3",
        "git branch": "demo @ git+https://github.com/example/demo.git@main",
        "git short sha": "demo @ git+https://github.com/example/demo.git@deadbeef",
        "wheel without sha256": "demo @ https://example.com/demo-1.0.0-py3-none-any.whl",
        "archive without sha256": "demo @ https://example.com/demo-1.0.0.tar.gz",
        "wheel with short sha256": (
            "demo @ https://example.com/demo-1.0.0-py3-none-any.whl#sha256=abc123"
        ),
        "archive with non-hex sha256": (
            f"demo @ https://example.com/demo-1.0.0.tar.gz#sha256={'g' * 64}"
        ),
        "wheel with wrong hash algorithm": (
            f"demo @ https://example.com/demo-1.0.0-py3-none-any.whl#sha512={sha256}"
        ),
        "wheel with uppercase sha256 key": (
            f"demo @ https://example.com/demo-1.0.0-py3-none-any.whl#SHA256={sha256}"
        ),
        "wheel with mixed-case sha256 key": (
            f"demo @ https://example.com/demo-1.0.0-py3-none-any.whl#Sha256={sha256}"
        ),
        "wheel with encoded sha256 key": (
            f"demo @ https://example.com/demo-1.0.0-py3-none-any.whl#%73ha256={sha256}"
        ),
        "wheel with encoded sha256 value": (
            "demo @ https://example.com/demo-1.0.0-py3-none-any.whl"
            f"#sha256=%61{'a' * 63}"
        ),
        "wheel with uppercase sha256 value": (
            f"demo @ https://example.com/demo-1.0.0-py3-none-any.whl#sha256={'A' * 64}"
        ),
        "wheel with mixed-case sha256 value": (
            "demo @ https://example.com/demo-1.0.0-py3-none-any.whl"
            f"#sha256={'a' * 63}F"
        ),
        "wheel with duplicate sha256": (
            "demo @ https://example.com/demo-1.0.0-py3-none-any.whl"
            f"#sha256={sha256}&SHA256={sha256}"
        ),
    }
    invalid_sources = {
        "official source userinfo": "https://reader:secret@docs.example.com/guide",
        "official source sensitive query": "https://docs.example.com/guide?api_key=secret",
        "official source nonnumeric port": "https://docs.example.com:notaport/guide",
        "official source unbalanced ipv6": "https://[2001:db8::1/guide",
    }
    valid_sources = {
        "official source anchor": "https://docs.example.com/guide#worker-lifecycle",
    }
    valid_dependencies = {
        "full git commit": f"demo @ git+https://github.com/example/demo.git@{commit}",
        "sha256 wheel": (
            f"demo @ https://example.com/demo-1.0.0-py3-none-any.whl#sha256={sha256}"
        ),
        "sha256 archive": (
            f"demo @ https://example.com/demo-1.0.0.tar.gz#sha256={sha256}"
        ),
        "sha256 archive with metadata": (
            "demo @ https://example.com/demo-1.0.0.tar.gz"
            f"#sha256={sha256}&subdirectory=python"
        ),
    }
    violations: list[str] = []

    for label, dependency in invalid_dependencies.items():
        spec = make_spec()
        spec["course"]["dependencies"] = [dependency]
        if _authoring_accepts(spec):
            violations.append(f"authoring accepted {label}")

    for label, url in invalid_sources.items():
        spec = make_spec()
        spec["target"]["official_sources"][0]["url"] = url
        if _authoring_accepts(spec):
            violations.append(f"authoring accepted {label}")

    for label, url in valid_sources.items():
        spec = make_spec()
        spec["target"]["official_sources"][0]["url"] = url
        if not _authoring_accepts(spec):
            violations.append(f"authoring rejected {label}")

    for label, dependency in valid_dependencies.items():
        spec = make_spec()
        spec["course"]["dependencies"] = [dependency]
        if not _authoring_accepts(spec):
            violations.append(f"authoring rejected {label}")

    validated = validate_spec(make_spec())
    for index, (label, dependency) in enumerate(invalid_dependencies.items()):
        platform = tmp_path / f"dependency-{index}" / "platform"
        write_canonical_source(platform, deepcopy(validated))
        source = platform / "course" / "source"
        course = _required_json(source / "course.json")
        course["dependencies"] = [dependency]
        _write_json(source / "course.json", course)
        if _compiled_source_accepts(source):
            violations.append(f"compiled source accepted {label}")

    for index, (label, url) in enumerate(invalid_sources.items()):
        platform = tmp_path / f"source-{index}" / "platform"
        write_canonical_source(platform, deepcopy(validated))
        source = platform / "course" / "source"
        sources = _required_json(source / "sources.json")
        sources["sources"][0]["url"] = url
        sources["target"]["official_sources"][0]["url"] = url
        _write_json(source / "sources.json", sources)
        if _compiled_source_accepts(source):
            violations.append(f"compiled source accepted {label}")

    for index, (label, url) in enumerate(valid_sources.items()):
        spec = make_spec()
        spec["target"]["official_sources"][0]["url"] = url
        validated_source = validate_spec(spec)
        platform = tmp_path / f"valid-source-{index}" / "platform"
        write_canonical_source(platform, validated_source)
        if not _compiled_source_accepts(platform / "course" / "source"):
            violations.append(f"compiled source rejected {label}")

    for index, (label, dependency) in enumerate(valid_dependencies.items()):
        spec = make_spec()
        spec["course"]["dependencies"] = [dependency]
        validated_direct = validate_spec(spec)
        platform = tmp_path / f"valid-{index}" / "platform"
        write_canonical_source(platform, validated_direct)
        if not _compiled_source_accepts(platform / "course" / "source"):
            violations.append(f"compiled source rejected {label}")

    assert not violations, "\n".join(violations)


def test_runner_subprocess_environment_uses_a_safe_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = getattr(runner_execution, "safe_subprocess_environment", None)
    assert callable(builder), "runner.execution.safe_subprocess_environment is missing"

    inherited = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "Path": "/attacker/mixed-case-bin",
        "path": "/attacker/lowercase-bin",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OPENAI_API_KEY": "openai-secret",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "HF_TOKEN": "hf-secret",
        "UNRELATED_CUSTOM_VALUE": "must-not-leak",
    }
    monkeypatch.setattr(
        runner_execution, "_WINDOWS_ENVIRONMENT", False, raising=False
    )
    environment = builder(inherited)

    assert environment["PATH"] == inherited["PATH"]
    assert environment["LANG"] == inherited["LANG"]
    assert environment["LC_ALL"] == inherited["LC_ALL"]
    assert {
        "Path",
        "path",
        "OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "HF_TOKEN",
        "UNRELATED_CUSTOM_VALUE",
    }.isdisjoint(environment)

    monkeypatch.setattr(
        runner_execution, "_WINDOWS_ENVIRONMENT", True, raising=False
    )
    windows_environment = builder(
        {
            "Path": "/windows/mixed-case-bin",
            "PATH": "/windows/canonical-bin",
            "path": "/windows/lowercase-bin",
            "SystemRoot": "C:\\Windows-from-mixed-case",
            "SYSTEMROOT": "C:\\Windows",
        }
    )
    assert windows_environment == {
        "PATH": "/windows/canonical-bin",
        "SYSTEMROOT": "C:\\Windows",
    }
    monkeypatch.setattr(
        runner_execution, "_WINDOWS_ENVIRONMENT", False, raising=False
    )

    monkeypatch.setenv("PATH", inherited["PATH"])
    monkeypatch.setenv("LANG", inherited["LANG"])
    monkeypatch.setenv("LC_ALL", inherited["LC_ALL"])
    monkeypatch.setenv("OPENAI_API_KEY", inherited["OPENAI_API_KEY"])
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", inherited["AWS_SECRET_ACCESS_KEY"])
    monkeypatch.setenv("HF_TOKEN", inherited["HF_TOKEN"])
    monkeypatch.setenv("UNRELATED_CUSTOM_VALUE", inherited["UNRELATED_CUSTOM_VALUE"])

    workspace = tmp_path / "labs"
    solution = workspace / "lab01" / "solution.py"
    solution.parent.mkdir(parents=True)
    solution.write_text("VALUE = 42\n", encoding="utf-8")
    canonical = tmp_path / "course" / "starter" / "lab01" / "tests" / "test_env.py"
    canonical.parent.mkdir(parents=True)
    canonical.write_text(
        "import os\n\n"
        "def test_environment_contract():\n"
        "    assert os.environ['PATH'] == " + repr(inherited["PATH"]) + "\n"
        "    assert os.environ['LANG'] == " + repr(inherited["LANG"]) + "\n"
        "    assert os.environ['LC_ALL'] == " + repr(inherited["LC_ALL"]) + "\n"
        "    for name in (\n"
        "        'OPENAI_API_KEY', 'AWS_SECRET_ACCESS_KEY', 'HF_TOKEN',\n"
        "        'UNRELATED_CUSTOM_VALUE',\n"
        "    ):\n"
        "        assert name not in os.environ\n",
        encoding="utf-8",
    )

    result = runner_execution.run_isolated_pytest(
        workspace,
        [f"{canonical}::test_environment_contract"],
        timeout_seconds=5,
    )

    assert result.passed is True, result.output


def test_full_verifier_uses_locked_local_typescript_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "platform").mkdir()
    (tmp_path / "labs").mkdir()
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        **_kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        stdout = ""
        if "--help" in command:
            stdout = "unlock\n"
        elif command[:3] == ["git", "rev-list", "--count"]:
            stdout = "1\n"
        return subprocess.CompletedProcess(command, 0, stdout, "")

    healthy_progression = {
        key: True for key in verifier.WEB_PROGRESSION_BOOLEAN_CHECKS
    }
    healthy_progression["output"] = "functional API workflow passed"
    monkeypatch.setattr(verifier, "run", fake_run)
    monkeypatch.setattr(
        verifier, "pytest_targets", lambda _root: (["public"], ["hidden"])
    )
    monkeypatch.setattr(
        verifier, "reference_public_targets", lambda _root: ["public"]
    )
    monkeypatch.setattr(
        verifier, "starter_red_check", lambda _root, _python: (True, "red")
    )
    monkeypatch.setattr(
        verifier,
        "runnable_lesson_examples",
        lambda _root, _python: (True, "examples"),
    )
    monkeypatch.setattr(
        verifier, "cli_learning_workflow", lambda _root, _python: (True, "cli")
    )
    monkeypatch.setattr(
        verifier,
        "web_progression_workflow",
        lambda _root, _python: dict(healthy_progression),
    )
    monkeypatch.setattr(verifier, "privacy_boundary", lambda _root: True)
    monkeypatch.setattr(verifier, "scan_residue", lambda _root: [])
    monkeypatch.setattr(verifier, "symlink_free", lambda _root: True)

    verifier.verify(tmp_path, full=True)

    expected = ["npm", "run", "typecheck"]
    assert expected in commands, commands
    assert all(not command or command[0] != "npx" for command in commands)
    assert all(command[:2] != ["npm", "exec"] for command in commands)

    package = _required_json(PLATFORM_ROOT / "package.json")
    assert package["scripts"]["typecheck"] == (
        "node ./node_modules/typescript/bin/tsc --noEmit"
    )

    missing_local = tmp_path / "missing-local-typescript"
    missing_local.mkdir()
    _write_json(
        missing_local / "package.json",
        {
            "name": "missing-local-typescript",
            "private": True,
            "scripts": {"typecheck": package["scripts"]["typecheck"]},
        },
    )
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    marker = tmp_path / "global-tsc-ran"
    fake_tsc = fake_bin / "tsc"
    fake_tsc.write_text(
        "#!/bin/sh\n: > \"$FAKE_TSC_MARKER\"\nexit 0\n", encoding="utf-8"
    )
    fake_tsc.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = os.pathsep.join((str(fake_bin), environment["PATH"]))
    environment["FAKE_TSC_MARKER"] = str(marker)

    missing_result = subprocess.run(
        ["npm", "run", "typecheck"],
        cwd=missing_local,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert missing_result.returncode != 0
    assert not marker.exists(), missing_result.stdout + missing_result.stderr


def test_ci_is_read_only_pinned_and_runs_the_root_release_validator() -> None:
    workflow = _required_text(ROOT / ".github" / "workflows" / "ci.yml")
    validator = ROOT / "scripts" / "validate_release.py"

    assert validator.is_file(), "root scripts/validate_release.py is missing"
    assert re.search(r"\bsecrets\s*(?:\.|\[)", workflow, re.IGNORECASE) is None
    payload = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert isinstance(payload, dict), "CI workflow must be a YAML mapping"

    def assert_no_secret_context(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                assert not (
                    isinstance(key, str) and key.casefold() == "secrets"
                ), "CI must not declare or inherit a secrets mapping"
                assert_no_secret_context(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_secret_context(nested)
        elif isinstance(value, str):
            assert re.search(r"\bsecrets\b", value, re.IGNORECASE) is None

    assert_no_secret_context(payload)

    root_permissions = payload.get("permissions")
    assert isinstance(root_permissions, dict)
    assert root_permissions.get("contents") == "read"
    assert not _permission_has_write(root_permissions)

    events = payload.get("on")
    event_names = {events} if isinstance(events, str) else set(events or {})
    assert "pull_request_target" not in event_names

    jobs = payload.get("jobs")
    assert isinstance(jobs, dict) and jobs
    steps: list[dict[str, Any]] = []
    for job in jobs.values():
        assert isinstance(job, dict)
        assert not _permission_has_write(job.get("permissions", {}))
        job_steps = job.get("steps", [])
        assert isinstance(job_steps, list)
        typed_steps = [step for step in job_steps if isinstance(step, dict)]
        steps.extend(typed_steps)
        job_checkouts = [
            step
            for step in typed_steps
            if isinstance(step.get("uses"), str)
            and step["uses"].startswith("actions/checkout@")
        ]
        job_uv_setups = [
            step
            for step in typed_steps
            if isinstance(step.get("uses"), str)
            and step["uses"].startswith("astral-sh/setup-uv@")
        ]
        assert len(job_checkouts) == 1
        assert len(job_uv_setups) == 1
        checkout_options = job_checkouts[0].get("with")
        uv_options = job_uv_setups[0].get("with")
        assert isinstance(checkout_options, dict)
        assert isinstance(uv_options, dict)
        assert checkout_options.get("persist-credentials") == "false"
        assert uv_options.get("version") == "0.11.7"
        assert any(step.get("run") == "uv sync --locked" for step in typed_steps)

    uses = [step["uses"] for step in steps if isinstance(step.get("uses"), str)]
    assert uses, "CI must use pinned setup actions"
    for action in uses:
        assert re.fullmatch(r"[^/\s]+/[^@\s]+@[0-9a-fA-F]{40}", action), action

    uv_steps = [
        step
        for step in steps
        if isinstance(step.get("uses"), str)
        and step["uses"].startswith("astral-sh/setup-uv@")
    ]
    checkout_steps = [
        step
        for step in steps
        if isinstance(step.get("uses"), str)
        and step["uses"].startswith("actions/checkout@")
    ]

    def version(step: dict[str, Any], key: str) -> Any:
        options = step.get("with", {})
        return options.get(key) if isinstance(options, dict) else None

    for job in jobs.values():
        assert isinstance(job, dict)
        job_steps = job.get("steps")
        assert isinstance(job_steps, list)
        typed_steps = [step for step in job_steps if isinstance(step, dict)]
        job_python = [
            step
            for step in typed_steps
            if isinstance(step.get("uses"), str)
            and step["uses"].startswith("actions/setup-python@")
        ]
        job_node = [
            step
            for step in typed_steps
            if isinstance(step.get("uses"), str)
            and step["uses"].startswith("actions/setup-node@")
        ]
        assert len(job_python) == 1
        assert len(job_node) == 1
        assert version(job_python[0], "python-version") == "3.13"
        assert version(job_node[0], "node-version") == "22"

    assert len(uv_steps) == len(jobs)
    assert all(version(step, "version") == "0.11.7" for step in uv_steps)
    assert len(checkout_steps) == len(jobs)
    assert all(
        version(step, "persist-credentials") == "false"
        for step in checkout_steps
    )

    run_steps = [step["run"] for step in steps if isinstance(step.get("run"), str)]
    assert run_steps.count("uv sync --locked") == len(jobs)

    forward = jobs.get("forward")
    assert isinstance(forward, dict)
    assert forward.get("needs") == "validate"
    assert forward.get("if") == (
        "github.event_name == 'schedule' || startsWith(github.ref, 'refs/tags/v')"
    )
    forward_steps = forward.get("steps")
    assert isinstance(forward_steps, list)
    forward_runs = [
        step.get("run") for step in forward_steps if isinstance(step, dict)
    ]
    assert "uv run python scripts/validate_release.py --forward" in forward_runs

    validate = jobs.get("validate")
    assert isinstance(validate, dict)
    assert validate.get("if") is None
    validate_steps = validate.get("steps")
    assert isinstance(validate_steps, list)
    validate_runs = [
        step.get("run") for step in validate_steps if isinstance(step, dict)
    ]
    assert validate_runs.count("uv run python scripts/validate_release.py") == 1

    assert isinstance(events, dict)
    assert "schedule" in events
    push = events.get("push")
    assert isinstance(push, dict)
    assert push.get("tags") == ["v*"]


def test_dependabot_covers_every_release_lock_ecosystem_and_path() -> None:
    dependabot = yaml.load(
        _required_text(ROOT / ".github" / "dependabot.yml"),
        Loader=yaml.BaseLoader,
    )
    assert isinstance(dependabot, dict)
    assert dependabot.get("version") == "2"
    updates = dependabot.get("updates")
    assert isinstance(updates, list) and len(updates) == 4

    matrix = {
        (update.get("package-ecosystem"), update.get("directory"))
        for update in updates
        if isinstance(update, dict)
    }
    platform = (
        "/plugins/python-library-course-builder/skills/"
        "building-python-library-courses/assets/course-template/platform"
    )
    assert matrix == {
        ("uv", "/"),
        ("uv", platform),
        ("npm", platform),
        ("github-actions", "/"),
    }
    intervals = {
        (update.get("package-ecosystem"), update.get("directory")): (
            update.get("schedule", {}).get("interval")
            if isinstance(update.get("schedule"), dict)
            else None
        )
        for update in updates
        if isinstance(update, dict)
    }
    assert intervals == {
        ("uv", "/"): "weekly",
        ("uv", platform): "weekly",
        ("npm", platform): "weekly",
        ("github-actions", "/"): "monthly",
    }
