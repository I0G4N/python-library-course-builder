from __future__ import annotations

import ast
from copy import deepcopy
import inspect
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "python-library-course-builder"
PLUGIN_ROOT = ROOT / "plugins" / PLUGIN_NAME
SKILL_ROOT = PLUGIN_ROOT / "skills" / "building-python-library-courses"
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "course-template"
PLATFORM_ROOT = TEMPLATE_ROOT / "platform"
MARKETPLACE_PATH = ROOT / ".agents" / "plugins" / "marketplace.json"
REPOSITORY_URL = "https://github.com/I0G4N/python-library-course-builder"
DEFAULT_PROMPT = (
    "Use $building-python-library-courses to turn a Python library into a "
    "structured, testable learning project."
)

sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(PLATFORM_ROOT))

import runner.execution as runner_execution  # noqa: E402
from coursekit.compiler import SourceValidationError, load_course_source  # noqa: E402
from scaffold_course import write_canonical_source  # noqa: E402
from validate_course import SpecValidationError, validate_spec  # noqa: E402

from tests.course_v2_fixture import make_spec  # noqa: E402


def _required_text(path: Path) -> str:
    assert path.is_file(), f"required public file is missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _required_json(path: Path) -> dict[str, Any]:
    return json.loads(_required_text(path))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


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


def test_plugin_manifest_and_marketplace_publish_exact_skill_only_metadata() -> None:
    manifest = _required_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")

    assert manifest["name"] == PLUGIN_NAME
    assert manifest["version"] == "0.1.0"
    assert manifest["author"] == {
        "name": "I0G4N",
        "url": "https://github.com/I0G4N",
    }
    assert "email" not in manifest["author"]
    assert manifest["homepage"] == f"{REPOSITORY_URL}#readme"
    assert manifest["repository"] == REPOSITORY_URL
    assert manifest["license"] == "Apache-2.0"
    assert manifest["skills"] == "./skills/"
    assert "apps" not in manifest
    assert "mcpServers" not in manifest
    assert manifest["interface"] == {
        "displayName": "Python Library Course Builder",
        "shortDescription": "Build testable Python library learning projects",
        "longDescription": (
            "Turn a Python library into a beginner-first cumulative course with "
            "concept checks, coding exercises, and pytest grading."
        ),
        "developerName": "I0G4N",
        "category": "Productivity",
        "capabilities": [],
        "websiteURL": REPOSITORY_URL,
        "defaultPrompt": [DEFAULT_PROMPT],
    }

    marketplace = _required_json(MARKETPLACE_PATH)
    assert marketplace == {
        "name": PLUGIN_NAME,
        "interface": {"displayName": "Python Library Course Builder"},
        "plugins": [
            {
                "name": PLUGIN_NAME,
                "source": {
                    "source": "local",
                    "path": f"./plugins/{PLUGIN_NAME}",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            }
        ],
    }


def test_public_repository_files_and_generated_template_license_are_present() -> None:
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
    assert _required_text(TEMPLATE_ROOT / "LICENSE") == root_license
    assert _required_text(TEMPLATE_ROOT / "NOTICE") == root_notice


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

    missing_contents: list[str] = []
    for path in sorted((SKILL_ROOT / "references").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if len(text.splitlines()) > 100 and re.search(
            r"^## (?:Table of contents|Contents)$", text, re.IGNORECASE | re.MULTILINE
        ) is None:
            missing_contents.append(path.name)
    assert not missing_contents, f"long references lack a table of contents: {missing_contents}"

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
        "mutable git reference": "demo @ git+https://github.com/example/demo.git@main",
        "artifact without sha256": "demo @ https://example.com/demo-1.0.0.whl",
    }
    invalid_sources = {
        "official source userinfo": "https://reader:secret@docs.example.com/guide",
        "official source sensitive query": "https://docs.example.com/guide?api_key=secret",
    }
    valid_dependencies = {
        "full git commit": f"demo @ git+https://github.com/example/demo.git@{commit}",
        "sha256 artifact": f"demo @ https://example.com/demo-1.0.0.whl#sha256={sha256}",
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

    for index, (label, dependency) in enumerate(valid_dependencies.items()):
        spec = make_spec()
        spec["course"]["dependencies"] = [dependency]
        validated_direct = validate_spec(spec)
        platform = tmp_path / f"valid-{index}" / "platform"
        write_canonical_source(platform, validated_direct)
        if not _compiled_source_accepts(platform / "course" / "source"):
            violations.append(f"compiled source rejected {label}")

    assert not violations, "\n".join(violations)


def test_runner_subprocess_environment_uses_a_safe_allowlist() -> None:
    builder = getattr(runner_execution, "safe_subprocess_environment", None)
    assert callable(builder), "runner.execution.safe_subprocess_environment is missing"

    inherited = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OPENAI_API_KEY": "openai-secret",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "HF_TOKEN": "hf-secret",
        "UNRELATED_CUSTOM_VALUE": "must-not-leak",
    }
    environment = builder(inherited)

    assert environment["PATH"] == inherited["PATH"]
    assert environment["LANG"] == inherited["LANG"]
    assert environment["LC_ALL"] == inherited["LC_ALL"]
    assert {
        "OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "HF_TOKEN",
        "UNRELATED_CUSTOM_VALUE",
    }.isdisjoint(environment)
    run_source = inspect.getsource(runner_execution.run_isolated_pytest)
    assert "safe_subprocess_environment(" in run_source
    assert "dict(os.environ)" not in run_source


def test_full_verifier_uses_locked_offline_typescript_execution() -> None:
    verifier_path = SCRIPTS_ROOT / "verify_learning_project.py"
    source = _required_text(verifier_path)
    tree = ast.parse(source, filename=str(verifier_path))
    string_lists = [
        [item.value for item in node.elts]
        for node in ast.walk(tree)
        if isinstance(node, (ast.List, ast.Tuple))
        and all(
            isinstance(item, ast.Constant) and isinstance(item.value, str)
            for item in node.elts
        )
    ]

    assert ["npm", "exec", "--offline", "--", "tsc", "--noEmit"] in string_lists
    assert all(not command or command[0] != "npx" for command in string_lists)
    assert "npx tsc" not in source


def test_ci_is_read_only_pinned_and_runs_the_root_release_validator() -> None:
    workflow = _required_text(ROOT / ".github" / "workflows" / "ci.yml")
    validator = ROOT / "scripts" / "validate_release.py"

    assert validator.is_file(), "root scripts/validate_release.py is missing"
    assert re.search(r"^permissions:\s*$", workflow, re.MULTILINE)
    assert re.search(r"^\s+contents:\s*read\s*$", workflow, re.MULTILINE)
    assert "pull_request_target" not in workflow
    assert re.search(r"python-version:\s*['\"]?3\.13['\"]?", workflow)
    assert re.search(r"node-version:\s*['\"]?22(?:\.\d+)*['\"]?", workflow)
    assert "uv run python scripts/validate_release.py" in workflow
