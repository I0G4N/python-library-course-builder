from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import sys

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import authoring_contract  # noqa: E402
import scaffold_course  # noqa: E402
from v4_contract import validate_v4_route  # noqa: E402


def _read(relative: str) -> str:
    return (SKILL_ROOT / relative).read_text(encoding="utf-8")


def _first_fenced_block(document: str, language: str) -> str:
    match = re.search(
        rf"```{re.escape(language)}[ \t]*\n(?P<body>.*?)\n```",
        document,
        flags=re.S,
    )
    assert match is not None, f"missing {language} fenced block"
    return match.group("body")


def test_legacy_course_template_contains_no_runtime_generated_artifacts() -> None:
    """The unchanged v2/v3 template must remain safe to copy."""

    template = SKILL_ROOT / "assets" / "course-template"
    forbidden_names = {
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
    forbidden_files = {".coverage", "coverage.xml", "course-verification.json"}
    forbidden_suffixes = {".log", ".pyc", ".pyd", ".pyo", ".tmp", ".tsbuildinfo"}

    polluted = sorted(
        path.relative_to(template).as_posix()
        for path in template.rglob("*")
        if (
            path.is_symlink()
            or path.name in forbidden_names
            or path.name in forbidden_files
            or path.name.endswith(".egg-info")
            or path.suffix in forbidden_suffixes
        )
    )

    assert polluted == []


def test_legacy_template_copy_excludes_runtime_and_build_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / "template"
    (template / "pkg/__pycache__").mkdir(parents=True)
    (template / "platform/app").mkdir(parents=True)
    (template / "README.md").write_text("course\n", encoding="utf-8")
    (template / "pkg/module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (template / "platform/app/page.tsx").write_text(
        "export default 1\n", encoding="utf-8"
    )
    (template / "pkg/__pycache__/module.cpython-313.pyc").write_bytes(b"cache")
    (template / "stray.pyc").write_bytes(b"cache")
    residue = {
        ".mypy_cache/state.json": "{}\n",
        ".pytest_cache/CACHEDIR.TAG": "cache\n",
        ".ruff_cache/state.json": "{}\n",
        ".uv-cache/archive-v0/file": "cache\n",
        ".venv/bin/python": "binary\n",
        "build/output.js": "compiled\n",
        "coverage/lcov.info": "coverage\n",
        "coverage.xml": "<coverage />\n",
        "course-verification.json": "{}\n",
        "htmlcov/index.html": "coverage\n",
        "platform/.next/server/page.js": "compiled\n",
        "platform/dist/bundle.js": "compiled\n",
        "platform/node_modules/package/index.js": "dependency\n",
        "platform/tsconfig.tsbuildinfo": "{}\n",
        "pytest.log": "test output\n",
        "scratch.tmp": "temporary\n",
    }
    for relative, content in residue.items():
        path = template / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    (template / ".coverage").write_bytes(b"SQLite format 3\0")
    destination = tmp_path / "copied"
    monkeypatch.setattr(scaffold_course, "TEMPLATE_ROOT", template)

    scaffold_course.copy_template(destination)

    copied_files = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert copied_files == {"README.md", "pkg/module.py", "platform/app/page.tsx"}


def test_legacy_template_copy_ignores_dependency_symlinks_but_rejects_copied_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / "template"
    dependency = template / "platform/node_modules/package"
    dependency.mkdir(parents=True)
    (template / "README.md").write_text("course\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (dependency / "ignored-link.js").symlink_to(outside)
    monkeypatch.setattr(scaffold_course, "TEMPLATE_ROOT", template)

    destination = tmp_path / "copied"
    scaffold_course.copy_template(destination)
    assert (destination / "README.md").read_text(encoding="utf-8") == "course\n"
    assert not (destination / "platform/node_modules").exists()

    included = template / "included-link.txt"
    included.symlink_to(outside)
    with pytest.raises(scaffold_course.ScaffoldError, match="cannot contain symlinks"):
        scaffold_course.copy_template(tmp_path / "rejected")


def test_legacy_readme_keeps_web_progression_and_schema_v2_compatibility() -> None:
    readme = _read("assets/course-template/README.md")

    for phrase in (
        "三个关卡",
        "Web 知识检查",
        "CLI、Web 和本地 Runner 使用同一份进度状态",
        "GET /api/knowledge/{lab_id}",
        "POST /api/knowledge/answer",
        "Schema v2 课程继续使用兼容流程",
        "`lab00` 和 `lab01` 初始均可导航",
        "macOS",
        "Linux",
        "WSL2",
    ):
        assert phrase in readme


def test_v4_fresh_courses_choose_and_lock_one_supported_language() -> None:
    skill = _read("SKILL.md")
    curriculum = _read("references/curriculum-contract.md")

    assert "ask exactly one question before any other action" in skill
    assert "Simplified Chinese (`zh-CN`) or English (`en`)" in skill
    assert "Keep the accepted locale fixed" in skill
    assert "Do not ask again or silently change" in skill
    assert "exactly `zh-CN` or `en`" in curriculum


def test_v4_depth_brief_is_small_exact_and_ephemeral() -> None:
    skill = _read("SKILL.md")
    writer = _read("references/chapter-writer-contract.md")
    curriculum = _read("references/curriculum-contract.md")
    expected = [
        "chapter_id",
        "chapter_kind",
        "core_question",
        "project_increment",
        "required_facts",
        "interface_boundary",
        "walkthrough_case",
        "boundary_case",
        "design_choice",
        "credible_alternative",
        "previous_handoff",
        "next_handoff",
        "official_sources",
        "task_contracts",
        "owned_paths",
    ]

    assert _first_fenced_block(skill, "text").splitlines() == expected
    assert _first_fenced_block(writer, "text").splitlines() == expected
    assert "prompt context, not a course schema or generated artifact" in skill
    assert "`required_facts` contains 3–6" in skill
    assert "not part of schema v4" in writer
    assert "3–6 required official facts" in writer

    route = json.loads(_first_fenced_block(curriculum, "json"))
    assert validate_v4_route(route) == route
    serialized_route = json.dumps(route)
    for private_field in (
        "core_question",
        "project_increment",
        "required_facts",
        "interface_boundary",
        "walkthrough_case",
        "boundary_case",
        "design_choice",
        "credible_alternative",
        "previous_handoff",
        "next_handoff",
    ):
        assert private_field not in serialized_route
    assert (
        "The route does not contain `core_question`, required facts, walkthrough"
        in curriculum
    )


def test_v4_free_markdown_depth_is_prompt_guidance_not_output_scoring() -> None:
    skill = _read("SKILL.md")
    writer = _read("references/chapter-writer-contract.md")
    depth = _read("references/teaching-depth-contract.md")
    authoring = _read("references/authoring-rubric.md")
    curriculum = _read("references/curriculum-contract.md")
    forward = _read("references/forward-test-rubric.md")

    assert "`tutorial.md` is arbitrary nonempty UTF-8 Markdown" in curriculum
    assert "No title, section, keyword, or length is required" in curriculum
    assert "any Markdown headings, narrative order, and chapter length" in writer
    assert "not a machine-scored rubric" in authoring
    assert "Writer instructions, not JSON fields" in depth
    assert "No downstream script tries to prove semantic completeness" in writer
    assert (
        "Do not inspect tutorial headings, length, keywords, semantic completeness"
        in forward
    )

    prompt = writer.split("## Writer prompt", 1)[1].split(
        "## Silent single-call self-review", 1
    )[0]
    for depth_input in (
        "core question",
        "walkthrough case",
        "essential definitions",
        "component responsibilities",
        "caller/implementer interface",
        "data or control flow",
        "selected design",
        "credible alternative",
        "benefits and costs",
        "symptom, cause, and recovery",
    ):
        assert depth_input in prompt

    assert not (SKILL_ROOT / "references/tutorial-depth-policy.md").exists()
    assert not (SKILL_ROOT / "scripts/tutorial_depth.py").exists()
    assert "depth evaluator" in skill
    assert "word-count check" in skill
    assert "concept/outcome/trace validator" in skill


def test_v4_uses_one_writer_and_at_most_one_mechanical_repair() -> None:
    skill = _read("SKILL.md")
    writer = _read("references/chapter-writer-contract.md")
    forward = _read("references/forward-test-rubric.md")

    assert "Launch exactly one Writer per chapter" in skill
    assert skill.count('fork_turns="none"') == 1
    assert "In the same call, the Writer silently plans, writes, checks, and revises" in skill
    assert "outputs only final package files" in skill
    assert "Send the concise error list to the same Writer once" in writer
    assert "If the second mechanical check fails, stop and report it" in writer
    assert "One failure list may be returned to the original chapter Writer once" in forward
    assert "A second failure stops generation" in forward
    assert "do not launch a new Writer" in skill
    assert "Do not launch a replacement Writer" in writer
    assert "Do not run a whole-course Reviewer" in skill


def test_v4_acceptance_runs_inside_the_generated_python_environment() -> None:
    skill = _read("SKILL.md")

    assert "uv lock --cache-dir" in skill
    assert "--project /path/to/course" in skill
    assert "--isolated" in skill
    assert "--locked --no-editable" in skill
    assert "target-library dependencies participate in the real tests" in skill
    assert "`uv.lock`" in skill
    acceptance = skill.split("### 5. Run one course acceptance", 1)[1].split(
        "### 6. Hand off", 1
    )[0]
    assert "--no-project" not in acceptance
    assert "npm install" in acceptance


def test_v4_validator_contract_is_mechanical_only() -> None:
    skill = _read("SKILL.md")
    writer = _read("references/chapter-writer-contract.md")
    forward = _read("references/forward-test-rubric.md")

    for phrase in (
        "IDs",
        "required files",
        "JSON/TOML parsing",
        "quiz option references",
        "owned-path safety/conflicts/symlinks",
        "Python syntax",
        "selectors",
        "declared symbols",
        "learner/author isolation",
    ):
        assert phrase in skill

    for failure in (
        "mismatched chapter/task IDs",
        "missing or unparseable required files",
        "invalid quiz answer reference",
        "invalid Python syntax",
        "missing test selector or declared symbol",
        "leakage into the learner projection",
    ):
        assert failure in writer

    assert "does not inspect implementation strategy or prose semantics" in _read(
        "references/curriculum-contract.md"
    )
    assert "definitions, design explanation, alternatives, benefits, or tradeoffs" in forward


def test_v4_chapter_package_and_learner_author_projections_are_stable() -> None:
    skill = _read("SKILL.md")
    curriculum = _read("references/curriculum-contract.md")

    for path in (
        "tutorial.md",
        "terms.json",
        "quiz.json",
        "starter/src/...",
        "solution/src/...",
        "tests/public/...",
        "tests/hidden/...",
    ):
        assert path in skill

    assert "`tutorial.md` is the only prose source of truth" in _read(
        "references/chapter-writer-contract.md"
    )
    assert "terms.json` is a presentation-only object" in curriculum
    assert "Learner quiz files omit answers" in curriculum
    assert "<slug>-author/" in curriculum
    assert "solution/src/<package>/" in curriculum
    assert "tests/hidden/<chapter-id>/..." in curriculum


def test_v4_preserves_the_full_web_loop_and_three_gates() -> None:
    skill = _read("SKILL.md")
    architecture = _read("references/architecture.md")
    forward = _read("references/forward-test-rubric.md")

    for gate in ("Navigation gate", "Knowledge gate", "Coding verification gate"):
        assert gate in architecture
    for endpoint in (
        "GET /api/content/{id}",
        "GET /api/course",
        "GET /api/state",
        "GET /api/knowledge/{id}",
        "POST /api/knowledge/answer",
        "GET/PUT /api/file",
        "POST /api/run",
    ):
        assert endpoint in architecture
    for feature in (
        "Markdown navigation",
        "terms",
        "quiz",
        "CodeMirror",
        "save",
        "public tests",
        "hidden submit",
        "progress restoration",
        "three gates",
        "three-column desktop layout",
    ):
        assert feature in skill

    assert "exact `tutorial.md` Markdown" in architecture
    assert "It never returns `lesson_outline`" in architecture
    assert "first-task practice link, and no `lesson_outline`" in forward
    assert "one real HTTP/API path" in forward

    static_root = (
        SKILL_ROOT / "assets/course-template-v4/coursekit_runtime/static"
    )
    index = (static_root / "index.html").read_text(encoding="utf-8")
    asset_paths = re.findall(r'(?:src|href)="(/assets/[^"]+)"', index)
    assert asset_paths
    assert all((static_root / path.removeprefix("/")).is_file() for path in asset_paths)


def test_v4_runs_one_course_acceptance_and_keeps_shared_checks_in_ci() -> None:
    skill = _read("SKILL.md")
    architecture = _read("references/architecture.md")
    forward = _read("references/forward-test-rubric.md")

    assert "one Python environment and one local port" in skill
    assert "One Python process on one port" in architecture
    assert "does not install Node" in architecture
    assert "Run exactly one aggregated course-specific verification" in skill
    assert "starter tasks to be RED" in skill
    assert "public+hidden tests to be GREEN" in skill
    assert "## Shared engine conformance" in forward
    assert "Generated v4 courses copy the certified static/runtime assets" in forward
    assert "They do not repeat this matrix" in forward
    assert "must not invoke npm" in forward


def test_v4_content_and_runtime_digests_drive_different_regeneration_paths() -> None:
    content = authoring_contract.v4_content_contract_manifest(SKILL_ROOT)
    runtime = authoring_contract.v4_runtime_contract_manifest(SKILL_ROOT)
    content_paths = {item["path"] for item in content["files"]}
    runtime_paths = {item["path"] for item in runtime["files"]}

    assert re.fullmatch(r"[0-9a-f]{64}", content["sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", runtime["sha256"])
    assert content_paths.isdisjoint(runtime_paths)
    assert "SKILL.md" not in content_paths
    assert "references/curriculum-contract.md" not in content_paths
    assert "references/chapter-writer-contract.md" in content_paths
    assert any(
        path.startswith("assets/course-template-v4/coursekit_runtime/")
        for path in runtime_paths
    )

    skill = _read("SKILL.md")
    curriculum = _read("references/curriculum-contract.md")
    regeneration = _read("scripts/regenerate_course.py")
    for document in (skill, curriculum):
        assert "Content-prompt or Depth-Brief contract" in document
        assert "runtime" in document and "revalidat" in document
    assert (
        "regenerate_course.py chapter COURSE --chapter <id> --reason ... --json REQUEST"
        in curriculum
    )
    assert "All other chapter packages remain byte-identical" in curriculum
    assert "v4_content_contract_sha256" in regeneration
    assert "v4_runtime_contract_sha256" in regeneration
    assert "plan_v4_chapter_regeneration" in regeneration
    assert '"mechanical_repair_limit": 1' in regeneration


def test_v4_contract_digests_follow_real_content_and_runtime_file_changes(
    tmp_path: Path,
) -> None:
    skill_copy = tmp_path / "skill"
    paths = {
        *authoring_contract.V4_CONTENT_CONTRACT_PATHS,
        *authoring_contract.V4_RUNTIME_SCRIPT_PATHS,
    }
    for relative in sorted(paths):
        source = SKILL_ROOT / relative
        destination = skill_copy / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    shutil.copytree(
        SKILL_ROOT / authoring_contract.V4_RUNTIME_ROOT,
        skill_copy / authoring_contract.V4_RUNTIME_ROOT,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    content_before = authoring_contract.v4_content_contract_sha256(skill_copy)
    runtime_before = authoring_contract.v4_runtime_contract_sha256(skill_copy)

    runtime_file = (
        skill_copy / authoring_contract.V4_RUNTIME_ROOT / "runner.py"
    )
    runtime_file.write_text(
        runtime_file.read_text(encoding="utf-8") + "\n# runtime-only change\n",
        encoding="utf-8",
    )
    assert authoring_contract.v4_content_contract_sha256(skill_copy) == (
        content_before
    )
    runtime_after = authoring_contract.v4_runtime_contract_sha256(skill_copy)
    assert runtime_after != runtime_before

    writer_contract = (
        skill_copy / "references/chapter-writer-contract.md"
    )
    writer_contract.write_text(
        writer_contract.read_text(encoding="utf-8")
        + "\n<!-- content-prompt change -->\n",
        encoding="utf-8",
    )
    assert authoring_contract.v4_content_contract_sha256(skill_copy) != (
        content_before
    )
    assert authoring_contract.v4_runtime_contract_sha256(skill_copy) == (
        runtime_after
    )


def test_v4_keeps_legacy_courses_unchanged_until_explicit_regeneration() -> None:
    skill = _read("SKILL.md")
    architecture = _read("references/architecture.md")
    curriculum = _read("references/curriculum-contract.md")
    forward = _read("references/forward-test-rubric.md")

    assert "Existing schema-v2/v3 courses remain readable and unchanged" in skill
    assert "Existing schema-v2/v3 source, compiler, Web, and generated layout" in architecture
    assert "Do not rewrite or migrate them in place" in curriculum
    assert "v2/v3 input remains byte-identical until explicit replacement" in forward
