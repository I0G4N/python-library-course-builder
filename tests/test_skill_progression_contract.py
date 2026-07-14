from __future__ import annotations

import json
from pathlib import Path
import re
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


def _assert_in_order(document: str, phrases: tuple[str, ...]) -> None:
    missing = [phrase for phrase in phrases if phrase not in document]
    assert missing == [], f"missing ordered phrase(s): {missing}"
    positions = [document.index(phrase) for phrase in phrases]
    assert positions == sorted(positions), phrases


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

    assert "三个关卡" in readme
    assert "Web 知识检查" in readme
    assert "同一份进度状态" in readme
    assert "后续 Lab 保持禁用" in readme
    assert "默认拒绝" in readme
    assert "初次 `/api/state` 加载" in readme
    assert "GET /api/knowledge/{lab_id}" in readme
    assert "POST /api/knowledge/answer" in readme
    assert "脱敏" in readme
    assert "过期的状态快照" in readme
    assert "延迟返回的保存或运行响应" in readme
    assert "原样保留这次回答 POST" in readme
    assert "后台刷新" in readme
    assert "**重试提交**" in readme
    assert "**重试回答**" not in readme


def test_author_contract_requires_quiz_first_code_and_question_scoped_files() -> None:
    architecture = _read("references/architecture.md")
    forward = _read("references/forward-test-rubric.md")
    readme = _read("assets/course-template/README.md")

    for document in (architecture, forward):
        assert "Lab 00" in document
        assert "no code workspace" in document
        assert "workflow gate, not source secrecy" in document

    assert "Lab 00" in readme
    assert "没有代码工作区" in readme
    assert "流程关卡，而不是源码保密边界" in readme

    assert "GET /api/file?lab_id={lab_id}&question_id={question_id}" in architecture
    assert '"lab_id", "question_id", and "content"' in architecture
    assert "question-scoped file API" in forward
    assert "基础章节和当前 Lab 的知识检查" in readme


def test_generated_readme_names_the_supported_local_operating_systems() -> None:
    readme = _read("assets/course-template/README.md")

    assert "macOS" in readme
    assert "Linux" in readme
    assert "WSL2" in readme
    assert "Node.js 22.13 或更高版本" in readme
    assert "Node.js 22.13 or newer" not in readme


def test_author_contract_documents_compiler_owned_source_preflight() -> None:
    curriculum = _read("references/curriculum-contract.md")
    architecture = _read("references/architecture.md")
    forward = _read("references/forward-test-rubric.md")

    assert "source_policy" in curriculum
    assert "source_policy" in architecture
    assert "source_policy" in forward
    assert "before pytest" in architecture
    assert "target_symbols" in curriculum and "official_symbols" in curriculum
    assert "python {path}" in curriculum


def test_author_contract_requires_accessible_resizable_desktop_layout() -> None:
    architecture = _read("references/architecture.md")
    forward = _read("references/forward-test-rubric.md")
    readme = _read("assets/course-template/README.md")

    for document in (architecture, forward):
        assert "two keyboard-accessible separators" in document
        assert "per-course localStorage" in document
        assert "no resize separators" in document

    assert "两个可通过键盘操作的分隔条" in readme
    assert "每门课程的 localStorage" in readme
    assert "不显示调整大小的分隔条" in readme

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

    for document in (curriculum, authoring, forward):
        assert "wrong -> symptom -> cause -> fix" in document

    assert "schema_version\": 2" in curriculum
    assert "course.audience" in curriculum
    assert "lesson_outline" in curriculum
    assert "answer_id" in curriculum
    assert "official_bridge" in curriculum
    assert "module_cycle" in curriculum


def test_skill_stage_three_requires_readiness_before_route_design() -> None:
    skill = _read("SKILL.md")
    depth_link = "[teaching-depth-contract.md](references/teaching-depth-contract.md)"
    stage_one = skill.split("### 1. Inspect locally, then research officially", 1)[
        1
    ].split("### 2. Apply the scope gate", 1)[0]
    stage_two = skill.split("### 2. Apply the scope gate", 1)[1].split(
        "### 3. Design one cumulative route", 1
    )[0]
    stage_three = skill.split("### 3. Design one cumulative route", 1)[1].split(
        "### 4. Author the canonical specification", 1
    )[0]

    assert depth_link in stage_three
    load_references = skill.split("## Load detailed references only when needed", 1)[1]
    assert depth_link in load_references
    assert "After scope is fixed" in stage_three
    assert "for a large target" in stage_three
    _assert_in_order(
        stage_one,
        (
            "target is absent",
            "behavior/evidence questions",
            "rather than beginner/intermediate labels",
            "reuse evidence",
            "inspector",
            "primary official sources",
        ),
    )
    assert "user selects one track" in stage_two
    _assert_in_order(
        stage_three,
        (
            depth_link,
            "selected route",
            "primary official sources",
            "learning-prerequisite DAG",
            "package dependency metadata",
            "route-relevant",
            "safe to assume",
            "teach in Lab 00",
            "too large for this route",
            "45-60 minute Lab 00",
            "stop before writing the schema or destination file",
            "prerequisite course or a narrower track",
        ),
    )
    assert "Give each graded Lab one new knowledge mainline" in stage_three
    assert "Lab 02+ may also begin" in stage_three
    assert "does not justify a second unrelated mainline" in stage_three
    assert "Apply the exact adaptive time tiers" in stage_three


def test_skill_and_curriculum_document_assessed_authoring_contract() -> None:
    skill = _read("SKILL.md")
    curriculum = _read("references/curriculum-contract.md")

    for document in (skill, curriculum):
        for phrase in (
            "course.audience.level",
            "assessed",
            "learner-self-report",
            "study_minutes",
            "operational_contract",
            "trace",
            "basic-python",
            "compatibility",
        ):
            assert phrase in document

    assert (
        "Author new specifications with `course.audience.level: assessed`" in skill
    )
    assert (
        "Treat legacy `basic-python` as validator compatibility input, "
        "not the authoring default."
        in skill
    )

    json_blocks = re.findall(r"```json\n(.*?)\n```", curriculum, re.S)
    documented_default = json.loads(json_blocks[0])
    audience = documented_default["course"]["audience"]
    assert set(audience) == {"level", "prerequisite_profile"}
    assert audience["level"] == "assessed"
    profile = audience["prerequisite_profile"]
    assert set(profile) == {"assessment", "capabilities"}
    assert profile["assessment"] == "learner-self-report"
    assert profile["capabilities"]
    capability_fields = {
        "id",
        "kind",
        "subject",
        "title",
        "status",
        "decision",
        "basis",
        "source_ids",
        "first_used_in",
        "foundation_concept_ids",
    }
    assert all(
        set(capability) == capability_fields
        for capability in profile["capabilities"]
    )
    known = next(item for item in profile["capabilities"] if item["status"] == "known")
    gap = next(item for item in profile["capabilities"] if item["status"] != "known")
    assert (known["decision"], known["foundation_concept_ids"]) == ("assume", [])
    assert gap["decision"] == "foundation" and gap["foundation_concept_ids"]

    assessed_section = curriculum.split("## Assessed readiness and duration", 1)[
        1
    ].split("## Structured `lesson`", 1)[0]
    assert "`status` is `known`, `partial`, `missing`, or `unsure`" in assessed_section
    assert "`decision` is `assume` or `foundation`" in assessed_section
    assert (
        "A `known` capability uses `assume` and an empty "
        "`foundation_concept_ids`. Every other status uses `foundation`"
        in assessed_section
    )
    legacy_clause = assessed_section.split(
        "Legacy `course.audience.level: basic-python`", 1
    )[1]
    for legacy_field in ("assumes", "does_not_assume", "lab_minutes"):
        assert legacy_field in legacy_clause
    assert "readable **compatibility** input" in assessed_section
    assert "it is not the new authoring default" in assessed_section

    duration_payloads = [
        json.loads(payload)
        for payload in re.findall(r"`(\{\"tier\": .*?\})`", assessed_section)
    ]
    durations = {payload["tier"]: payload for payload in duration_payloads}
    assert durations["foundation"] == {
        "tier": "foundation",
        "min": 45,
        "max": 60,
        "reason": "...",
    }
    assert durations["standard"] == {"tier": "standard", "min": 30, "max": 45}
    assert durations["extended"] == {
        "tier": "extended",
        "min": 45,
        "max": 60,
        "reason": "...",
    }

    documented_lesson = json.loads(json_blocks[1])
    concept = documented_lesson["concepts"][0]
    contract = concept["operational_contract"]
    assert set(contract) == {
        "kind",
        "forms",
        "inputs",
        "outputs",
        "effects",
        "failure_modes",
    }
    assert contract["kind"] in {
        "api",
        "mechanism",
        "formula",
        "lifecycle",
        "data-model",
    }
    assert all(
        set(item) == {"name", "meaning", "form", "example", "constraints"}
        for item in contract["inputs"]
    )
    assert all(
        set(item) == {"name", "meaning", "form", "example"}
        for item in contract["outputs"]
    )
    assert all(
        set(item) == {"condition", "observable", "recovery"}
        for item in contract["failure_modes"]
    )
    runnable = next(
        item for item in documented_lesson["examples"] if item["kind"] == "runnable"
    )
    assert len(runnable["trace"]) >= 2
    assert all(
        set(step)
        == {
            "id",
            "concept_ids",
            "input_state",
            "operation",
            "output_state",
            "explanation",
        }
        for step in runnable["trace"]
    )
    assert all(
        set(step["concept_ids"]) <= set(runnable["concept_ids"])
        for step in runnable["trace"]
    )

    assert '"tier": "foundation"' in curriculum
    assert '"tier": "standard"' in curriculum
    assert '"tier": "extended"' in curriculum
    assert "45-60" in curriculum
    assert "30-45" in curriculum
    assert "large gap" in curriculum
    assert "before" in curriculum and "specification" in curriculum


def test_teaching_depth_reference_defines_positive_chapter_recipe() -> None:
    depth_path = SKILL_ROOT / "references/teaching-depth-contract.md"
    assert depth_path.is_file(), (
        "Stage 3 needs the directly linked teaching-depth reference"
    )
    depth = depth_path.read_text(encoding="utf-8")
    depth_lower = depth.lower()

    _assert_in_order(
        depth,
        (
            "concrete capstone problem",
            "plain-language understanding",
            "exact operational contract",
            "complete real-value execution trace",
            "boundary and error reasoning",
            "runnable and diagnostic examples",
            "knowledge check",
            "coding or capstone increment",
        ),
    )
    for phrase in (
        "two-layer Lab 00",
        "general-Python gaps",
        "route-specific library and domain foundations",
        "api",
        "mechanism",
        "formula",
        "lifecycle",
        "data-model",
        "forms",
        "inputs",
        "outputs",
        "effects",
        "condition",
        "observable",
        "recovery",
        "same concrete value or state",
        "at least two named transitions",
        "shapes, types, state, or ownership",
        "numeric formula",
        "data or shape transformation",
        "state or lifecycle flow",
        "public API boundary",
        "先这样理解",
        "输入和输出是什么",
        "拿一个具体输入走一遍",
        "first practice link",
        "word count",
    ):
        assert phrase.lower() in depth_lower

    natural = depth.split("## Write natural learner-facing Chinese", 1)[1].split(
        "## Adapt the recipe to the concept kind", 1
    )[0]
    assert "Define a term at first use" in natural
    assert "Use short transitions" in natural
    assert "这在这里重要，因为" in natural
    assert "Alternate explanation with concrete values" in natural
    assert "schema-field dump" in natural
    assert "stiff glossary" in natural
    assert "explain jargon before using it" in natural

    time_contract = depth.split("## Choose time from the work", 1)[1].split(
        "## Review semantically", 1
    )[0]
    assert "Lab 00 uses the `foundation` tier" in time_contract
    assert "An ordinary graded Lab uses the `standard` tier" in time_contract
    assert "may use the `extended` tier" in time_contract
    assert time_contract.count("**45-60 minutes**") == 2
    assert time_contract.count("**30-45 minutes**") == 1
    assert "specific reason tied to the assessed gaps" in time_contract
    assert (
        "A genuinely combined, derivation-heavy, or lifecycle-heavy Lab"
        in time_contract
    )
    assert "with a specific reason naming that work" in time_contract


def test_authoring_contract_requires_adaptive_depth_and_activity_alignment() -> None:
    authoring = _read("references/authoring-rubric.md")
    authoring_lower = authoring.lower()

    for phrase in (
        "evidence-based readiness",
        "two-layer Lab 00",
        "general-Python gaps",
        "route-specific library and domain foundations",
        "new material",
        "review",
        "one new knowledge mainline",
        "Lab 02+",
        "second unrelated mainline",
        "operational contract",
        "complete real-value execution trace",
        "first practice link",
        "compiler",
        "45-60 minutes",
        "30-45 minutes",
        "specific reason",
    ):
        assert phrase.lower() in authoring_lower

    exercise_contract = authoring.split("## 4. Exercise design", 1)[1].split(
        "## 5. Test and grading quality", 1
    )[0]
    assert (
        "Every assessed concept reaches trace, quiz, and diagnosis; "
        "every graded-Lab concept also reaches coding."
        in exercise_contract
    )
    assert (
        "Every outcome reaches an example plus a quiz or coding assessment."
        in exercise_contract
    )
    assert (
        "The compiler derives the concept-ordered **first practice link** from "
        "authored activity order; authors do not maintain reverse mappings."
        in exercise_contract
    )

    curriculum = _read("references/curriculum-contract.md")
    assert (
        "every Lab 00 concept maps to a runnable trace, quiz, and diagnosis"
        in curriculum
    )
    assert (
        "every graded-Lab concept maps to a runnable trace, quiz, coding question, "
        "and diagnosis"
        in curriculum
    )
    assert "every outcome maps to an example and to an assessment" in curriculum


def test_forward_rubric_defines_projection_and_paired_skill_score_gates() -> None:
    forward = _read("references/forward-test-rubric.md")
    paired = forward.split("## Paired Skill-output evaluation", 1)[1].split(
        "## Optional small-target transfer test", 1
    )[0]

    assert (
        "required for any change to readiness or teaching-depth Skill guidance"
        in paired
    )
    assert "Preserve one user-style prompt and target" in paired
    assert (
        "the same prompt and revised Skill to a fresh isolated agent that cannot "
        "see the old result, expected answer, or score"
        in paired
    )
    assert "Every score needs an **evidence citation**" in paired
    assert (
        "Pass only with **no zero**, at least **10/12**, and **exactly 2** on "
        "dimensions 3 and 4."
        in paired
    )
    assert (
        "If the new output misses any gate, strengthen the reusable Skill/reference "
        "wording and rerun with another fresh isolated agent; do not reinterpret "
        "the same evidence upward."
        in paired
    )
    for phrase in (
        "prerequisite profile",
        "gap decision",
        "per-unit",
        "study_minutes",
        "manifest",
        "README",
        "open core",
        "先这样理解",
        "输入和输出是什么",
        "拿一个具体输入走一遍",
        "first practice link",
        "learner-safe labels",
    ):
        assert phrase in forward

    for phrase in (
        "old output",
        "new output",
        "route-relevant readiness assessment",
        "evidence-based two-layer foundation plan",
        "precise operational contract",
        "complete concrete-value worked trace",
        "concept-to-quiz/coding/capstone alignment",
        "natural Simplified-Chinese explanation",
        "evidence citation",
    ):
        assert phrase in paired


def test_skill_requires_executable_content_quality() -> None:
    authoring = _read("references/authoring-rubric.md")
    forward = _read("references/forward-test-rubric.md")

    curriculum = _read("references/curriculum-contract.md")
    for document in (curriculum, authoring, forward):
        assert "at least two examples" in document
        assert "execution-trace" in document
        assert "diagnostic" in document
        assert "40%" in document

    assert "CPU/offline runnable" in curriculum
    assert "compiler-generated parity snapshot" in curriculum


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
