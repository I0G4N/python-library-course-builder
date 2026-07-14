from __future__ import annotations

from pathlib import Path
import sys

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import scaffold_course  # noqa: E402


def _read(relative: str) -> str:
    return (SKILL_ROOT / relative).read_text(encoding="utf-8")


def test_course_template_contains_no_runtime_generated_artifacts() -> None:
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


def test_template_copy_excludes_runtime_and_build_residue(
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


def test_template_copy_does_not_screen_symlinks_inside_ignored_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / "template"
    dependency = template / "platform/node_modules/package"
    dependency.mkdir(parents=True)
    (template / "README.md").write_text("course\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (dependency / "linked.js").symlink_to(outside)
    destination = tmp_path / "copied"
    monkeypatch.setattr(scaffold_course, "TEMPLATE_ROOT", template)

    scaffold_course.copy_template(destination)

    assert (destination / "README.md").read_text(encoding="utf-8") == "course\n"
    assert not (destination / "platform/node_modules").exists()


def test_template_copy_rejects_included_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / "template"
    template.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (template / "included-link.txt").symlink_to(outside)
    monkeypatch.setattr(scaffold_course, "TEMPLATE_ROOT", template)

    with pytest.raises(scaffold_course.ScaffoldError, match="cannot contain symlinks"):
        scaffold_course.copy_template(tmp_path / "copied")


def test_skill_and_rubrics_require_the_complete_three_gate_web_loop() -> None:
    skill = _read("SKILL.md")
    architecture = _read("references/architecture.md")
    authoring = _read("references/authoring-rubric.md")
    forward = _read("references/forward-test-rubric.md")

    for phrase in (
        "chapter navigation gate",
        "knowledge gate",
        "coding verification gate",
    ):
        assert phrase in skill
        assert phrase in authoring
        assert phrase in forward

    for endpoint in (
        "/api/state",
        "/api/knowledge/{lab_id}",
        "/api/knowledge/answer",
        "/api/run",
    ):
        assert endpoint in architecture
        assert endpoint in forward

    assert "fail closed" in architecture.lower()
    assert "generic Web quiz" in skill
    assert "functional API" in forward


def test_generated_readme_explains_the_shared_cli_and_web_progression() -> None:
    readme = _read("assets/course-template/README.md")

    assert "three gates" in readme
    assert "Web knowledge check" in readme
    assert "same progress state" in readme
    assert "Later Labs stay disabled" in readme
    assert "fails closed" in readme.lower()
    assert "initial `/api/state`" in readme
    assert "GET /api/knowledge/{lab_id}" in readme
    assert "POST /api/knowledge/answer" in readme
    assert "redacted" in readme
    assert "stale state snapshot" in readme
    assert "late save or run response" in readme
    assert "exact answer POST" in readme
    assert "background refresh" in readme


def test_author_contract_requires_quiz_first_code_and_question_scoped_files() -> None:
    skill = _read("SKILL.md")
    architecture = _read("references/architecture.md")
    forward = _read("references/forward-test-rubric.md")
    readme = _read("assets/course-template/README.md")

    for document in (skill, architecture, forward, readme):
        assert "Lab 00" in document
        assert "no code workspace" in document
        assert "workflow gate, not source secrecy" in document

    assert "GET /api/file?lab_id={lab_id}&question_id={question_id}" in architecture
    assert '"lab_id", "question_id", and "content"' in architecture
    assert "question-scoped file API" in skill
    assert "question-scoped file API" in forward
    assert "foundation and current-Lab knowledge" in readme


def test_generated_readme_names_the_supported_local_operating_systems() -> None:
    readme = _read("assets/course-template/README.md")

    assert "macOS" in readme
    assert "Linux" in readme
    assert "WSL2" in readme


def test_author_contract_documents_compiler_owned_source_preflight() -> None:
    skill = _read("SKILL.md")
    curriculum = _read("references/curriculum-contract.md")
    architecture = _read("references/architecture.md")
    forward = _read("references/forward-test-rubric.md")

    assert "source_policy" in skill
    assert "source_policy" in curriculum
    assert "source_policy" in architecture
    assert "source_policy" in forward
    assert "before pytest" in architecture
    assert "target_symbols" in curriculum and "official_symbols" in curriculum
    assert "python {path}" in curriculum
    assert "python {path}" in skill


def test_author_contract_requires_accessible_resizable_desktop_layout() -> None:
    skill = _read("SKILL.md")
    architecture = _read("references/architecture.md")
    forward = _read("references/forward-test-rubric.md")
    readme = _read("assets/course-template/README.md")

    for document in (skill, architecture, forward, readme):
        assert "two keyboard-accessible separators" in document
        assert "per-course localStorage" in document
        assert "no resize separators" in document

    assert "sidebar can collapse" in architecture
    assert "minimum widths" in architecture
    assert "Arrow keys" in forward


def test_skill_requires_the_mechanism_then_official_bridge_learning_cycle() -> None:
    skill = _read("SKILL.md")
    curriculum = _read("references/curriculum-contract.md")
    authoring = _read("references/authoring-rubric.md")
    forward = _read("references/forward-test-rubric.md")

    for document in (skill, curriculum, authoring, forward):
        assert "teaching-equivalent" in document
        assert "official bridge" in document
        assert "prior mini implementation" in document
        assert "wrong -> symptom -> cause -> fix" in document

    assert "schema_version\": 2" in curriculum
    assert "course.audience" in curriculum
    assert "lesson_outline" in curriculum
    assert "answer_id" in curriculum
    assert "official_bridge" in curriculum
    assert "module_cycle" in curriculum


def test_skill_requires_beginner_depth_and_executable_content_quality() -> None:
    skill = _read("SKILL.md")
    authoring = _read("references/authoring-rubric.md")
    forward = _read("references/forward-test-rubric.md")

    for document in (skill, authoring, forward):
        assert "30-45 minutes" in document
        assert "basic Python" in document
        assert "at least two examples" in document
        assert "execution-trace" in document
        assert "diagnostic" in document
        assert "40%" in document

    assert "CPU/offline runnable" in skill
    assert "compiler-generated parity snapshot" in skill


def test_skill_rejects_prerequisite_leakage_and_hollow_capstones() -> None:
    curriculum = _read("references/curriculum-contract.md")
    authoring = _read("references/authoring-rubric.md")
    forward = _read("references/forward-test-rubric.md")

    for document in (curriculum, authoring, forward):
        assert "prerequisite leakage" in document
        assert "worked numeric derivation" in document
        assert "stage-name-only" in document
        assert "immediately next Lab" in document

    assert "every declared target symbol" in authoring
    assert "mutation probe" in forward
    assert "untouched starter projection" in authoring
    assert "untouched starter projection" in forward
