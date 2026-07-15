from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "python-library-course-builder"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "building-python-library-courses"
TEMPLATE_README = SKILL_ROOT / "assets" / "course-template" / "README.md"
CHINESE_README = ROOT / "README.zh-CN.md"
RELEASE_VERSION = "0.2.0"

SKILL_DESCRIPTION = (
    "Use when a user asks to build, create, author, or learn through a "
    "structured, language-selectable hands-on course project for a Python "
    "standard-library module, PyPI package, framework, or repository instead "
    "of receiving a one-off explanation."
)
SHORT_DESCRIPTION = "Build Python courses in Chinese or English"
DEFAULT_PROMPT = (
    "Use $building-python-library-courses to create a source-backed "
    "course for a Python library or repository."
)
PLUGIN_DESCRIPTION = (
    "Build source-backed hands-on learning repositories for Python libraries "
    "in Simplified Chinese or English."
)
PLUGIN_LONG_DESCRIPTION = (
    "Turn a Python library into a cumulative beginner course in Simplified "
    "Chinese or English, with lessons, coding labs, CLI and Web grading."
)
MARKETPLACE_COMMAND = (
    "codex plugin marketplace add I0G4N/python-library-course-builder "
    f"--ref v{RELEASE_VERSION}"
)
PLUGIN_COMMAND = (
    "codex plugin add python-library-course-builder@python-library-course-builder"
)
CLONE_COMMAND = (
    f"git clone --branch v{RELEASE_VERSION} --depth 1 "
    "https://github.com/I0G4N/python-library-course-builder.git"
)
OFFICIAL_CODEX_DOCS = (
    "https://learn.chatgpt.com/docs/build-plugins#add-a-marketplace-from-the-cli"
)
NO_EXPORT_SENTENCE = (
    f"Version {RELEASE_VERSION} does not provide an automated learner-only export."
)
PRIVATE_REPOSITORY_SENTENCE = (
    "The supported secrecy path is to keep the complete teacher/authoring "
    "repository private."
)
SECURITY_ADVISORY_URL = (
    "https://github.com/I0G4N/python-library-course-builder/security/advisories/new"
)
CI_BADGE = (
    "[![CI](https://github.com/I0G4N/python-library-course-builder/actions/"
    "workflows/ci.yml/badge.svg?branch=main)](https://github.com/I0G4N/"
    "python-library-course-builder/actions/workflows/ci.yml)"
)
README_HERO = (
    "# Learn Any Python Library the Way You'd Work Through CS61A"
)
LANGUAGE_NAV = "English | [简体中文](README.zh-CN.md)"
EARLY_INDEPENDENCE_NOTICE = (
    "No CS61A code, assignments, tests, or instructional text are included, "
    "and this independently authored project is not affiliated with or "
    "endorsed by UC Berkeley, the CS61A course staff, or OpenAI."
)


def _text(path: Path) -> str:
    assert path.is_file(), f"required publication file is missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(_text(path))
    assert isinstance(payload, dict)
    return payload


def _skill_frontmatter_and_body() -> tuple[dict[str, Any], str]:
    match = re.fullmatch(
        r"---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)",
        _text(SKILL_ROOT / "SKILL.md"),
        re.DOTALL,
    )
    assert match is not None, "SKILL.md needs one YAML frontmatter block"
    frontmatter = yaml.safe_load(match.group("frontmatter"))
    assert isinstance(frontmatter, dict)
    return frontmatter, match.group("body")


def _fenced_shell_blocks(document: str) -> tuple[str, ...]:
    return tuple(
        match.group("body").strip()
        for match in re.finditer(
            r"^```(?:bash|sh)\s*$\n(?P<body>.*?)^```\s*$",
            document,
            re.MULTILINE | re.DOTALL,
        )
    )


def _advertises_learner_only_artifact(document: str) -> bool:
    remaining = document.replace(NO_EXPORT_SENTENCE, "")
    return bool(
        re.search(
            r"(?i)\blearner-only\s+(?:export|projection|distribution)\b",
            remaining,
        )
        or re.search(r"(?i)\bcourse\s+export\b", remaining)
    )


def test_language_selectable_metadata_and_skill_language_contract_are_exact() -> None:
    frontmatter, skill_body = _skill_frontmatter_and_body()
    manifest = _json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    agent = yaml.safe_load(_text(SKILL_ROOT / "agents" / "openai.yaml"))

    assert frontmatter["description"] == SKILL_DESCRIPTION
    assert agent["interface"]["short_description"] == SHORT_DESCRIPTION
    assert agent["interface"]["default_prompt"] == DEFAULT_PROMPT
    assert manifest["description"] == PLUGIN_DESCRIPTION
    assert manifest["interface"]["shortDescription"] == SHORT_DESCRIPTION
    assert manifest["interface"]["longDescription"] == PLUGIN_LONG_DESCRIPTION
    assert manifest["interface"]["defaultPrompt"] == [DEFAULT_PROMPT]

    language_contract = (
        "On every fresh invocation, make the first question a course-language "
        "choice: ask the learner to choose exactly one course language before "
        "any other question or action",
        "Ask even when the request already names a language.",
        "Support exactly `zh-CN` and `en`.",
        "Write learner-facing lessons, readiness questions, quiz prompts, "
        "feedback, generated documentation, and course prose in the selected language.",
        "Keep code, shell commands, identifiers, target API names, and official "
        "source titles and URLs in their original form.",
    )
    for clause in language_contract:
        assert clause in skill_body
    assert len(skill_body.split()) <= 1_500

    readme = _text(ROOT / "README.md")
    chinese_readme = _text(CHINESE_README)
    changelog = _text(ROOT / "CHANGELOG.md")
    assert "Simplified Chinese or English" in readme[:1_200]
    assert "简体中文或英语" in chinese_readme[:1_200]
    assert "language-selectable" in changelog


def test_root_readme_is_english_canonical_and_cross_links_complete_chinese_readme() -> None:
    readme = _text(ROOT / "README.md")
    chinese_readme = _text(CHINESE_README)

    assert readme.startswith(f"{README_HERO}\n\n{LANGUAGE_NAV}\n\n{CI_BADGE}\n")
    english_body = readme.replace("简体中文", "")
    assert re.search(r"[\u3400-\u9fff]", english_body) is None
    assert chinese_readme.startswith(
        "# 像刷 CS61A 一样，系统攻下一门 Python 库\n\n"
        "[English](README.md) | 简体中文\n"
    )
    for required in (
        "evidence-dialogue readiness preflight",
        "`lab00`",
        "`prep01`",
        "`lab01`",
        "Codex",
        "Python 3.13",
        "Node.js 22.13",
        "authoring repository",
    ):
        assert required.casefold() in readme.casefold()
    for required in (
        "evidence-dialogue readiness preflight",
        "`lab00`",
        "`prep01`",
        "`lab01`",
        "Codex",
        "Python 3.13",
        "Node.js 22.13",
        "作者仓库",
    ):
        assert required.casefold() in chinese_readme.casefold()


def test_public_install_commands_pin_the_synchronized_release_version() -> None:
    readme = _text(ROOT / "README.md")
    chinese_readme = _text(CHINESE_README)
    command_sets = []
    for document in (readme, chinese_readme):
        command_sets.append(
            {
                line.strip()
                for block in _fenced_shell_blocks(document)
                for line in block.splitlines()
                if line.strip()
            }
        )
    commands = command_sets[0]
    project = tomllib.loads(_text(ROOT / "pyproject.toml"))
    manifest = _json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    changelog_match = re.search(
        r"^## \[(?P<version>[^]]+)] - \d{4}-\d{2}-\d{2}$",
        _text(ROOT / "CHANGELOG.md"),
        re.MULTILINE,
    )

    assert MARKETPLACE_COMMAND in commands
    assert CLONE_COMMAND in commands
    assert "codex plugin marketplace add I0G4N/python-library-course-builder" not in commands
    assert "git clone https://github.com/I0G4N/python-library-course-builder.git" not in commands
    assert changelog_match is not None
    versions = {
        project["project"]["version"],
        manifest["version"],
        changelog_match.group("version"),
        re.search(r"--ref v([^ ]+)$", MARKETPLACE_COMMAND).group(1),
        re.search(r"--branch v([^ ]+)", CLONE_COMMAND).group(1),
    }
    assert versions == {RELEASE_VERSION}
    assert command_sets[0] == command_sets[1]

    for template in ("bug.yml", "feature.yml"):
        issue_template = _text(ROOT / ".github" / "ISSUE_TEMPLATE" / template)
        assert f"placeholder: v{RELEASE_VERSION} or a full commit SHA" in issue_template
        assert "placeholder: v0.1.1 or a full commit SHA" not in issue_template


def test_all_secrecy_docs_publish_only_the_supported_private_repository_path() -> None:
    documents = {
        "README.md": _text(ROOT / "README.md"),
        "SECURITY.md": _text(ROOT / "SECURITY.md"),
        "SKILL.md": _text(SKILL_ROOT / "SKILL.md"),
        "template README.md": _text(TEMPLATE_README),
    }

    for label, document in documents.items():
        assert NO_EXPORT_SENTENCE in document, label
        assert PRIVATE_REPOSITORY_SENTENCE in document, label
        assert not _advertises_learner_only_artifact(document), label

    chinese_readme = _text(CHINESE_README)
    assert "0.2.0 版本不提供自动化的仅学员导出" in chinese_readme
    assert "完整的教师/作者仓库保持为私有仓库" in chinese_readme


@pytest.mark.parametrize(
    "advertisement",
    (
        "A learner-only export is available.",
        "Ship a learner-only export when answers must remain secret.",
        "A learner-only projection is supported.",
        "A learner-only distribution is available.",
        f"{NO_EXPORT_SENTENCE} A learner-only export is available.",
        "Run `course export` before publication.",
    ),
)
def test_secrecy_matcher_rejects_available_learner_only_artifacts(
    advertisement: str,
) -> None:
    assert _advertises_learner_only_artifact(advertisement)


@pytest.mark.parametrize(
    "supported_statement",
    (
        NO_EXPORT_SENTENCE,
        PRIVATE_REPOSITORY_SENTENCE,
        f"{NO_EXPORT_SENTENCE} {PRIVATE_REPOSITORY_SENTENCE}",
    ),
)
def test_secrecy_matcher_allows_the_supported_negative_boundary(
    supported_statement: str,
) -> None:
    assert not _advertises_learner_only_artifact(supported_statement)


def test_github_community_files_publish_structured_issue_and_pr_contracts() -> None:
    issue_root = ROOT / ".github" / "ISSUE_TEMPLATE"
    required_field_ids = {
        "target_area",
        "version_or_commit",
        "environment",
        "reproducible_evidence",
        "expected_behavior",
        "actual_behavior",
        "context",
    }
    for filename in ("bug.yml", "feature.yml"):
        payload = yaml.safe_load(_text(issue_root / filename))
        assert isinstance(payload, dict), filename
        body = payload.get("body")
        assert isinstance(body, list) and body, filename
        field_ids = {
            item.get("id")
            for item in body
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        assert required_field_ids <= field_ids, filename
        warning_text = "\n".join(
            str(item.get("attributes", {}).get("value", ""))
            for item in body
            if isinstance(item, dict) and item.get("type") == "markdown"
        ).casefold()
        assert "security vulnerabilit" in warning_text, filename
        assert "not" in warning_text and "public" in warning_text, filename
        assert SECURITY_ADVISORY_URL.casefold() in warning_text, filename

    config = yaml.safe_load(_text(issue_root / "config.yml"))
    assert isinstance(config, dict)
    assert config["blank_issues_enabled"] is False
    security_links = [
        link
        for link in config.get("contact_links", [])
        if isinstance(link, dict) and link.get("url") == SECURITY_ADVISORY_URL
    ]
    assert len(security_links) == 1

    pull_request_template = _text(ROOT / ".github" / "pull_request_template.md")
    headings = {
        heading.strip().casefold()
        for heading in re.findall(r"^##\s+(.+?)\s*$", pull_request_template, re.MULTILINE)
    }
    assert {
        "problem",
        "failing contract or evidence",
        "change",
        "verification commands and results",
        "generated-course evidence",
        "security, compatibility, and migration implications",
    } <= headings


def test_readme_publishes_badge_official_docs_boundaries_and_first_use_loop() -> None:
    readme = _text(ROOT / "README.md")
    assert readme.startswith(f"{README_HERO}\n\n{LANGUAGE_NAV}\n\n{CI_BADGE}\n")
    assert EARLY_INDEPENDENCE_NOTICE in readme.split("## Why", 1)[0]

    github_installation = readme.split("### Install from GitHub", 1)[1].split(
        "### Install from a local checkout", 1
    )[0]
    local_installation = readme.split("### Install from a local checkout", 1)[1].split(
        "Start a new Codex thread", 1
    )[0]
    assert OFFICIAL_CODEX_DOCS in github_installation
    assert MARKETPLACE_COMMAND in github_installation
    assert PLUGIN_COMMAND in github_installation
    assert CLONE_COMMAND in local_installation
    assert PLUGIN_COMMAND in local_installation
    assert (
        "Course creation requires Codex plus network access to verify official "
        "sources and install dependencies."
    ) in readme
    assert (
        "After setup, mandatory examples and grading are CPU/offline."
    ) in readme
    assert "cd /path/to/generated-course\nnpm run setup\nnpm run learn" in _fenced_shell_blocks(
        readme
    )


def test_readme_publishes_the_v3_readiness_and_course_learning_contract() -> None:
    readme = _text(ROOT / "README.md").casefold()

    for promise in (
        "evidence-dialogue readiness preflight",
        "`lab00` is always the environment and learning-loop orientation",
        "`prep01`, `prep02`, ...",
        "no code workspace, points, or submission",
        "`lab01` unlocks only after the final prep",
        "schema v2 courses remain compatible",
        "operational contracts",
        "concrete execution traces",
        "task-linked practice",
    ):
        assert promise in readme
    assert "lab 00 adapts to the prerequisite gaps" not in readme


def test_changelog_records_v3_readiness_and_detailed_learner_projections() -> None:
    release = _text(ROOT / "CHANGELOG.md").split(
        "## [0.1.0] - 2026-07-15", 1
    )[1].casefold()

    for promise in (
        "`evidence-dialogue` readiness preflight",
        "fixed `lab00` orientation",
        "dag-ordered `prepnn`",
        "no code workspaces, scores, or submissions",
        "shared cli, web, and runner progression",
        "schema-v2 compatibility",
        "detailed learner projections",
        "operational contracts",
        "concrete execution traces",
        "task-linked practice",
    ):
        assert promise in release
    assert "adaptive lab 00" not in release


def test_raw_template_readme_describes_generated_sources_without_a_broken_link() -> None:
    readme = _text(TEMPLATE_README)
    assert "[platform/course/source/sources.json]" not in readme
    assert "](platform/course/source/sources.json)" not in readme
    assert (
        "生成完成后，已固定版本的官方来源注册表会写入 "
        "`platform/course/source/sources.json`."
    ) in readme


def test_release_checklist_keeps_all_hosted_publication_gates_unchecked() -> None:
    checklist = _text(ROOT / "RELEASE_CHECKLIST.md")
    folded = checklist.casefold()
    required_fragments = (
        "https://github.com/i0g4n/python-library-course-builder",
        "github actions and issues",
        "private vulnerability reporting",
        SECURITY_ADVISORY_URL,
        "dependency graph",
        "dependabot alerts",
        "dependabot security updates",
        "main branch ruleset",
        "v* tag ruleset",
        MARKETPLACE_COMMAND,
        "hosted main ci",
        f"hosted v{RELEASE_VERSION} tag forward job",
    )
    for fragment in required_fragments:
        assert fragment.casefold() in folded

    checkbox_marks = re.findall(r"^- \[(?P<mark>.)] ", checklist, re.MULTILINE)
    assert checkbox_marks, "release checklist must contain reusable checkboxes"
    assert set(checkbox_marks) == {" "}, "release checklist must remain unchecked"
