from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(SKILL_ROOT / "assets/course-template/platform"))

from assess_readiness import assess_readiness  # noqa: E402
from coursekit.compiler import SourceValidationError, compile_course, load_course_source  # noqa: E402
from scaffold_course import scaffold, write_canonical_source  # noqa: E402
from validate_course import SpecValidationError, validate_spec  # noqa: E402
from tests.course_v2_fixture import make_assessed_spec, make_spec  # noqa: E402
from tests.course_v3_fixture import (  # noqa: E402
    make_readiness_route,
    make_v3_spec,
    make_v3_spec_and_plan,
)


ALL_GAPS = {
    "python-functions",
    "json-data-model",
    "json-errors",
    "domain-boundary",
}


def test_v2_specs_remain_valid_without_a_readiness_plan() -> None:
    assert validate_spec(make_spec())["schema_version"] == 2
    assert validate_spec(make_assessed_spec())["schema_version"] == 2

    legacy_language = make_spec()
    legacy_language["course"]["language"] = "legacy-custom-language"
    assert validate_spec(legacy_language)["course"]["language"] == (
        "legacy-custom-language"
    )


@pytest.mark.parametrize("language", ["zh-CN", "en"])
def test_v3_course_language_matches_v2_readiness_plan(language: str) -> None:
    spec, plan = make_v3_spec_and_plan(language=language)

    validated = validate_spec(spec, readiness_plan=plan)

    assert validated["course"]["language"] == language
    assert plan["language"] == language


@pytest.mark.parametrize("language", ["zh", "en-US", "fr", ""])
def test_v3_course_language_is_closed(language: str) -> None:
    spec, plan = make_v3_spec_and_plan()
    spec["course"]["language"] = language

    with pytest.raises(SpecValidationError, match="course.language"):
        validate_spec(spec, readiness_plan=plan)


def test_v3_all_mastered_has_only_lab00_and_lab01_depends_on_it() -> None:
    spec, plan = make_v3_spec_and_plan()

    validated = validate_spec(spec, readiness_plan=plan)

    assert validated["schema_version"] == 3
    assert [unit["id"] for unit in validated["preparatory_units"]] == ["lab00"]
    assert validated["preparatory_units"][0]["study_minutes"] == {
        "tier": "orientation",
        "min": 15,
        "max": 30,
    }
    assert validated["labs"][0]["depends_on"] == "lab00"


def test_v3_multilevel_gaps_match_plan_order_and_last_dependency() -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids=ALL_GAPS)

    validated = validate_spec(spec, readiness_plan=plan)

    expected = [unit["id"] for unit in plan["preparatory_units"]]
    assert [unit["id"] for unit in validated["preparatory_units"]] == expected
    assert validated["labs"][0]["depends_on"] == expected[-1]
    assert all("files" not in unit and "questions" not in unit for unit in validated["preparatory_units"])


def test_v3_rejects_later_lab_dependency_bypass() -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids={"json-data-model"})
    spec["labs"][1]["depends_on"] = "lab99"

    with pytest.raises(SpecValidationError, match="lab02 must depend on lab01"):
        validate_spec(spec, readiness_plan=plan)


def test_v3_official_source_metadata_must_match_the_ready_plan() -> None:
    spec, plan = make_v3_spec_and_plan()
    spec["target"]["official_sources"][0]["url"] = "https://example.com/unrelated"

    with pytest.raises(SpecValidationError, match="official sources"):
        validate_spec(spec, readiness_plan=plan)


@pytest.mark.parametrize("case", ["missing", "incomplete", "summary", "route"])
def test_v3_readiness_plan_must_be_complete_and_match_spec(case: str) -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids={"json-data-model"})
    if case == "missing":
        plan = None
    elif case == "incomplete":
        plan = assess_readiness(
            make_readiness_route(),
            {
                "schema_version": 2,
                "language": "zh-CN",
                "evidence": [],
                "responses": [],
            },
        )
    elif case == "summary":
        spec["course"]["audience"]["prerequisite_profile"]["readiness_summary"] = "0" * 12
    else:
        spec["course"]["audience"]["prerequisite_profile"]["route_id"] = "other-route"

    with pytest.raises(SpecValidationError, match="readiness|route|summary|ready"):
        validate_spec(spec, readiness_plan=plan)


def test_v3_rejects_code_or_scoring_fields_on_prep_units() -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids={"json-data-model"})
    spec["preparatory_units"][1]["questions"] = []

    with pytest.raises(SpecValidationError, match="preparatory_units.*questions"):
        validate_spec(spec, readiness_plan=plan)


def test_mismatched_plan_fails_before_scaffolder_creates_destination(
    tmp_path: Path,
) -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids={"json-data-model"})
    spec["course"]["audience"]["prerequisite_profile"]["readiness_summary"] = "0" * 12
    spec_path = tmp_path / "spec.json"
    plan_path = tmp_path / "plan.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    destination = tmp_path / "must-not-exist"

    with pytest.raises((SpecValidationError, TypeError), match="readiness|summary|argument"):
        scaffold(spec_path, destination, readiness_plan=plan_path)

    assert not destination.exists()


def test_language_mismatched_plan_fails_before_scaffolder_creates_destination(
    tmp_path: Path,
) -> None:
    spec, plan = make_v3_spec_and_plan(language="en")
    spec["course"]["language"] = "zh-CN"
    spec_path = tmp_path / "spec.json"
    plan_path = tmp_path / "plan.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    destination = tmp_path / "must-not-exist"

    with pytest.raises(SpecValidationError, match="course.language"):
        scaffold(spec_path, destination, readiness_plan=plan_path)

    assert not destination.exists()


def test_v3_split_source_compiles_independently_with_exact_parity_and_privacy(
    tmp_path: Path,
) -> None:
    sentinel = "PRIVATE-RAW-ANSWER-7f03d8"
    spec, plan = make_v3_spec_and_plan(
        missing_ids={"json-data-model", "domain-boundary"},
        raw_sentinel=sentinel,
    )
    validated = validate_spec(spec, readiness_plan=plan)
    platform = tmp_path / "platform"
    write_canonical_source(platform, validated)
    source = platform / "course/source"

    course = load_course_source(source)
    output = platform / "course/compiled"
    compile_course(source, output)

    snapshot = json.loads((output / "authoring-spec.json").read_text(encoding="utf-8"))
    learner_manifest = json.loads(
        (output / "starter/manifest.json").read_text(encoding="utf-8")
    )
    author_manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    content = json.loads((output / "content.json").read_text(encoding="utf-8"))
    assert snapshot == validated
    assert course.schema_version == 3
    assert course.lesson_format == "tutorial-markdown-v1"
    assert "readiness" not in learner_manifest
    assert "audience" not in learner_manifest
    assert "audience" not in author_manifest
    assert content["lesson_format"] == "tutorial-markdown-v1"
    assert all(
        item["lesson_format"] == "tutorial-markdown-v1"
        for item in [*content["preparatory_units"], *content["labs"]]
    )
    assert [
        (unit["id"], unit["unit_type"], unit["graded"])
        for unit in learner_manifest["preparatory_units"]
    ] == [
        ("lab00", "orientation", False),
        ("prep01", "preparatory", False),
        ("prep02", "preparatory", False),
    ]
    assert all(
        lab["unit_type"] == "lab" and lab["graded"] is True
        for lab in learner_manifest["labs"]
    )
    assert all(
        "capability_ids" not in unit
        for unit in learner_manifest["preparatory_units"]
    )
    assert all(
        "capability_ids" not in unit for unit in content["preparatory_units"]
    )
    assert sentinel not in "\n".join(
        path.read_text(encoding="utf-8")
        for root in (source, output)
        for path in root.rglob("*")
        if path.is_file()
    )


def test_v3_english_split_source_compiles_with_english_framework_copy(
    tmp_path: Path,
) -> None:
    spec, plan = make_v3_spec_and_plan(language="en")
    platform = tmp_path / "platform"
    write_canonical_source(platform, validate_spec(spec, readiness_plan=plan))
    output = platform / "course/compiled"

    compile_course(platform / "course/source", output)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    lesson = (output / "starter/lab00/README.md").read_text(encoding="utf-8")
    knowledge = json.loads((output / "knowledge.json").read_text(encoding="utf-8"))
    assert manifest["language"] == "en"
    assert "## Build the mental model" in lesson
    assert "## Trace one concrete value" in lesson
    assert "## 先修知识" not in lesson
    assert knowledge["title"].endswith("knowledge check")


def test_v3_tutorial_format_requires_markdown_for_every_unit() -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids={"json-data-model"})
    spec["preparatory_units"][1].pop("tutorial")

    with pytest.raises(SpecValidationError, match="tutorial"):
        validate_spec(spec, readiness_plan=plan)

    spec, plan = make_v3_spec_and_plan()
    spec["labs"][0]["tutorial"] = "   \n"
    with pytest.raises(SpecValidationError, match="tutorial"):
        validate_spec(spec, readiness_plan=plan)


def test_v3_without_lesson_format_keeps_legacy_renderer(tmp_path: Path) -> None:
    spec, plan = make_v3_spec_and_plan(language="en")
    spec["course"].pop("lesson_format")
    for unit in [*spec["preparatory_units"], *spec["labs"]]:
        unit.pop("tutorial")
    platform = tmp_path / "platform"
    write_canonical_source(platform, validate_spec(spec, readiness_plan=plan))
    output = platform / "course/compiled"

    compile_course(platform / "course/source", output)

    source = load_course_source(platform / "course/source")
    content = json.loads((output / "content.json").read_text(encoding="utf-8"))
    lesson = (output / "starter/lab00/README.md").read_text(encoding="utf-8")
    assert source.lesson_format is None
    assert "lesson_format" not in content
    assert "## Prerequisites" in lesson


def test_v3_tutorial_markdown_is_byte_stable_across_split_and_compile(
    tmp_path: Path,
) -> None:
    spec, plan = make_v3_spec_and_plan()
    tutorial = "# Exact bytes\n\nParagraph with  two spaces.  \n\n"
    spec["preparatory_units"][0]["tutorial"] = tutorial
    validated = validate_spec(spec, readiness_plan=plan)
    platform = tmp_path / "platform"
    write_canonical_source(platform, validated)
    source = platform / "course/source"
    output = platform / "course/compiled"

    loaded = load_course_source(source)
    compile_course(source, output)

    split = source / "preparatory_units/lab00/tutorial.md"
    content = json.loads((output / "content.json").read_text(encoding="utf-8"))
    snapshot = json.loads(
        (output / "authoring-spec.json").read_text(encoding="utf-8")
    )
    assert split.read_bytes() == tutorial.encode("utf-8")
    assert loaded.preparatory_units[0].lesson == tutorial
    assert content["preparatory_units"][0]["lesson"] == tutorial
    assert (output / "starter/lab00/README.md").read_bytes() == tutorial.encode(
        "utf-8"
    )
    assert snapshot["preparatory_units"][0]["tutorial"] == tutorial


def test_v3_runtime_projections_do_not_publish_readiness_metadata(
    tmp_path: Path,
) -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids={"json-data-model"})
    platform = tmp_path / "platform"
    write_canonical_source(platform, validate_spec(spec, readiness_plan=plan))
    output = platform / "course/compiled"
    compile_course(platform / "course/source", output)

    public_paths = [
        output / "manifest.json",
        output / "content.json",
        output / "starter/manifest.json",
        output / "starter/_course/content.json",
    ]
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in public_paths)
    for private_key in (
        '"readiness"',
        '"audience"',
        '"route_id"',
        '"readiness_summary"',
        '"prerequisite_profile"',
        '"capability_ids"',
        '"decision"',
        '"basis"',
    ):
        assert private_key not in public_text


def test_v3_split_source_rejects_course_manifest_language_mismatch(
    tmp_path: Path,
) -> None:
    spec, plan = make_v3_spec_and_plan(language="en")
    platform = tmp_path / "platform"
    write_canonical_source(platform, validate_spec(spec, readiness_plan=plan))
    course_path = platform / "course/source/course.json"
    course = json.loads(course_path.read_text(encoding="utf-8"))
    course["manifest"]["language"] = "zh-CN"
    course_path.write_text(json.dumps(course) + "\n", encoding="utf-8")

    with pytest.raises(SourceValidationError, match="manifest.language"):
        load_course_source(platform / "course/source")


def test_v3_split_source_rejects_readiness_summary_tampering(tmp_path: Path) -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids={"json-data-model"})
    platform = tmp_path / "platform"
    write_canonical_source(platform, validate_spec(spec, readiness_plan=plan))
    course_path = platform / "course/source/course.json"
    course = json.loads(course_path.read_text(encoding="utf-8"))
    course["audience"]["prerequisite_profile"]["readiness_summary"] = "0" * 12
    course_path.write_text(json.dumps(course) + "\n", encoding="utf-8")

    with pytest.raises(SourceValidationError, match="readiness|summary|curriculum"):
        load_course_source(platform / "course/source")


def test_v3_split_source_rejects_unmapped_prep_concepts(tmp_path: Path) -> None:
    spec, plan = make_v3_spec_and_plan(missing_ids={"json-data-model"})
    platform = tmp_path / "platform"
    write_canonical_source(platform, validate_spec(spec, readiness_plan=plan))
    course_path = platform / "course/source/course.json"
    course = json.loads(course_path.read_text(encoding="utf-8"))
    for audience in (course["audience"], course["manifest"]["audience"]):
        capability = next(
            item
            for item in audience["prerequisite_profile"]["capabilities"]
            if item["preparatory_unit_id"] == "prep01"
        )
        capability["preparatory_concept_ids"] = capability[
            "preparatory_concept_ids"
        ][:1]
    course_path.write_text(json.dumps(course) + "\n", encoding="utf-8")

    with pytest.raises(SourceValidationError, match="lack preparatory capability coverage"):
        load_course_source(platform / "course/source")


def test_v3_authoring_spec_rejects_temporary_evidence_fields() -> None:
    spec, plan = make_v3_spec_and_plan()
    spec["temporary_evidence"] = deepcopy(plan["temporary_evidence"])

    with pytest.raises(SpecValidationError, match="unknown.*temporary_evidence"):
        validate_spec(spec, readiness_plan=plan)


def test_v3_split_source_rejects_temporary_evidence_fields(tmp_path: Path) -> None:
    spec, plan = make_v3_spec_and_plan()
    platform = tmp_path / "platform"
    write_canonical_source(platform, validate_spec(spec, readiness_plan=plan))
    course_path = platform / "course/source/course.json"
    course = json.loads(course_path.read_text(encoding="utf-8"))
    course["temporary_evidence"] = deepcopy(plan["temporary_evidence"])
    course_path.write_text(json.dumps(course) + "\n", encoding="utf-8")

    with pytest.raises(SourceValidationError, match="unknown.*temporary_evidence"):
        load_course_source(platform / "course/source")
