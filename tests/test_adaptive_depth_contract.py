from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(SKILL_ROOT / "assets" / "course-template" / "platform"))

from coursekit.compiler import load_course_source  # noqa: E402
from scaffold_course import write_canonical_source  # noqa: E402
from validate_course import SpecValidationError, validate_spec  # noqa: E402
from tests.course_v2_fixture import make_assessed_spec, make_spec  # noqa: E402


Spec = dict[str, object]
Mutation = Callable[[Spec], None]


def _audience(spec: Spec) -> dict[str, Any]:
    return spec["course"]["audience"]  # type: ignore[index,return-value]


def _capability(spec: Spec, capability_id: str) -> dict[str, Any]:
    capabilities = _audience(spec)["prerequisite_profile"]["capabilities"]
    return next(item for item in capabilities if item["id"] == capability_id)


def _section(spec: Spec, section_id: str) -> dict[str, Any]:
    if section_id == "lab00":
        return spec["foundation"]  # type: ignore[return-value]
    return next(lab for lab in spec["labs"] if lab["id"] == section_id)  # type: ignore[index,return-value]


def _concept(spec: Spec, section_id: str) -> dict[str, Any]:
    return _section(spec, section_id)["lesson"]["concepts"][0]


def _example(spec: Spec, section_id: str, kind: str) -> dict[str, Any]:
    examples = _section(spec, section_id)["lesson"]["examples"]
    return next(item for item in examples if item["kind"] == kind)


def _rejects(spec: Spec, *fragments: str) -> None:
    with pytest.raises(SpecValidationError) as caught:
        validate_spec(spec)
    message = str(caught.value)
    for fragment in fragments:
        assert fragment in message, message


def test_legacy_basic_python_audience_remains_accepted_unchanged() -> None:
    spec = make_spec()

    validated = validate_spec(spec)

    assert validated["course"]["audience"] == spec["course"]["audience"]
    assert validated["course"]["audience"]["level"] == "basic-python"


def test_complete_assessed_spec_preserves_depth_and_trace_contracts() -> None:
    spec = make_assessed_spec()

    validated = validate_spec(spec)

    audience = validated["course"]["audience"]
    profile = audience["prerequisite_profile"]
    assert audience["level"] == "assessed"
    assert profile["assessment"] == "learner-self-report"
    assert {item["status"] for item in profile["capabilities"]} == {
        "known",
        "partial",
        "missing",
        "unsure",
    }
    assert {item["kind"] for item in profile["capabilities"]} == {
        "python",
        "library",
        "domain",
    }
    known = next(item for item in profile["capabilities"] if item["status"] == "known")
    assert known["decision"] == "assume"
    assert known["foundation_concept_ids"] == []
    for gap in (item for item in profile["capabilities"] if item["status"] != "known"):
        assert gap["decision"] == "foundation"
        assert gap["foundation_concept_ids"]

    assert validated["foundation"]["study_minutes"] == {
        "tier": "foundation",
        "min": 45,
        "max": 60,
        "reason": spec["foundation"]["study_minutes"]["reason"],
    }
    assert validated["labs"][0]["study_minutes"] == {
        "tier": "standard",
        "min": 30,
        "max": 45,
    }
    assert validated["labs"][2]["study_minutes"]["tier"] == "extended"
    assert validated["labs"][2]["study_minutes"]["reason"]

    sections = [validated["foundation"], *validated["labs"]]
    contracts = [
        concept["operational_contract"]
        for section in sections
        for concept in section["lesson"]["concepts"]
    ]
    assert {contract["kind"] for contract in contracts} == {
        "api",
        "mechanism",
        "formula",
        "lifecycle",
        "data-model",
    }
    assert all(
        all(contract[field] for field in ("forms", "inputs", "outputs", "effects", "failure_modes"))
        for contract in contracts
    )
    for section in sections:
        runnable = next(
            item for item in section["lesson"]["examples"] if item["kind"] == "runnable"
        )
        assert len(runnable["trace"]) >= 2
        assert len({step["id"] for step in runnable["trace"]}) == len(runnable["trace"])
        assert all(
            set(step["concept_ids"]) <= set(runnable["concept_ids"])
            for step in runnable["trace"]
        )


def test_split_source_preserves_the_complete_assessed_contract(tmp_path: Path) -> None:
    spec = make_assessed_spec()
    platform = tmp_path / "platform"
    write_canonical_source(platform, spec)

    course = load_course_source(platform / "course" / "source")

    assert course.course["audience"] == spec["course"]["audience"]
    assert course.foundation["study_minutes"] == spec["foundation"]["study_minutes"]
    assert course.foundation_lesson_outline["concepts"][0][
        "operational_contract"
    ] == spec["foundation"]["lesson"]["concepts"][0]["operational_contract"]
    assert course.labs[0].raw["study_minutes"] == spec["labs"][0]["study_minutes"]
    assert course.labs[0].lesson_outline["examples"][0]["trace"] == spec["labs"][
        0
    ]["lesson"]["examples"][0]["trace"]


def _large_gap(spec: Spec) -> None:
    _capability(spec, "json-data-model")["status"] = "large-gap"


def _known_with_foundation(spec: Spec) -> None:
    capability = _capability(spec, "python-functions")
    capability["decision"] = "foundation"
    capability["foundation_concept_ids"] = ["lab00.c-mechanism"]


def _foundation_first_use(spec: Spec) -> None:
    _capability(spec, "json-data-model")["first_used_in"] = "lab00"


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    (
        pytest.param(_large_gap, "status", id="large-gap-is-not-serialized"),
        pytest.param(_known_with_foundation, "decision", id="known-maps-to-assume"),
        pytest.param(_foundation_first_use, "first_used_in", id="first-use-is-graded"),
    ),
)
def test_assessed_profile_rejects_inconsistent_capability_provenance(
    mutation: Mutation, fragment: str
) -> None:
    spec = make_assessed_spec()
    mutation(spec)

    _rejects(spec, fragment)


def _wrong_foundation_range(spec: Spec) -> None:
    _section(spec, "lab00")["study_minutes"]["min"] = 30


def _missing_graded_minutes(spec: Spec) -> None:
    _section(spec, "lab02").pop("study_minutes")


def _standard_reason(spec: Spec) -> None:
    _section(spec, "lab01")["study_minutes"]["reason"] = "not allowed"


def _extended_without_reason(spec: Spec) -> None:
    _section(spec, "lab03")["study_minutes"].pop("reason")


@pytest.mark.parametrize(
    "mutation",
    (
        pytest.param(_wrong_foundation_range, id="foundation-exact-range"),
        pytest.param(_missing_graded_minutes, id="every-graded-lab"),
        pytest.param(_standard_reason, id="standard-has-no-reason"),
        pytest.param(_extended_without_reason, id="extended-needs-reason"),
    ),
)
def test_assessed_study_minutes_reject_noncanonical_shapes(mutation: Mutation) -> None:
    spec = make_assessed_spec()
    mutation(spec)

    _rejects(spec, "study_minutes")


def _missing_operational_contract(spec: Spec) -> None:
    _concept(spec, "lab01").pop("operational_contract")


def _empty_operational_forms(spec: Spec) -> None:
    _concept(spec, "lab01")["operational_contract"]["forms"] = []


def _unknown_operational_input_field(spec: Spec) -> None:
    contract = _concept(spec, "lab01")["operational_contract"]
    contract["inputs"][0]["teacher_note"] = "private"


@pytest.mark.parametrize(
    "mutation",
    (
        pytest.param(_missing_operational_contract, id="contract-required"),
        pytest.param(_empty_operational_forms, id="collections-non-empty"),
        pytest.param(_unknown_operational_input_field, id="nested-fields-closed"),
    ),
)
def test_operational_contract_rejects_incomplete_or_open_shapes(
    mutation: Mutation,
) -> None:
    spec = make_assessed_spec()
    mutation(spec)

    _rejects(spec, "operational_contract")


def _missing_trace(spec: Spec) -> None:
    _example(spec, "lab01", "runnable").pop("trace")


def _one_trace_step(spec: Spec) -> None:
    runnable = _example(spec, "lab01", "runnable")
    runnable["trace"] = runnable["trace"][:1]


def _duplicate_trace_id(spec: Spec) -> None:
    steps = _example(spec, "lab01", "runnable")["trace"]
    steps[1]["id"] = steps[0]["id"]


def _trace_outside_example(spec: Spec) -> None:
    runnable = _example(spec, "lab02", "runnable")
    runnable["concept_ids"] = ["lab02.c-mechanism"]
    runnable["trace"][0]["concept_ids"] = ["lab02.c-official"]


@pytest.mark.parametrize(
    "mutation",
    (
        pytest.param(_missing_trace, id="trace-required"),
        pytest.param(_one_trace_step, id="at-least-two-steps"),
        pytest.param(_duplicate_trace_id, id="stable-unique-step-ids"),
        pytest.param(_trace_outside_example, id="concept-subset"),
    ),
)
def test_runnable_trace_rejects_incomplete_or_unlinked_steps(
    mutation: Mutation,
) -> None:
    spec = make_assessed_spec()
    mutation(spec)

    _rejects(spec, "trace")


@pytest.mark.parametrize(
    "surface", ("runnable trace", "quiz", "coding question", "diagnostic")
)
def test_every_graded_concept_is_covered_by_each_learning_surface(
    surface: str,
) -> None:
    spec = make_assessed_spec()
    lab = _section(spec, "lab02")
    official_id = "lab02.c-official"
    mechanism_id = "lab02.c-mechanism"

    if surface == "runnable trace":
        for step in _example(spec, "lab02", "runnable")["trace"]:
            if official_id in step["concept_ids"]:
                step["concept_ids"] = [mechanism_id]
    elif surface == "quiz":
        for quiz in lab["quiz"]:
            quiz["concept_ids"] = [mechanism_id]
    elif surface == "coding question":
        for question in lab["questions"]:
            question["concept_ids"] = [mechanism_id]
    else:
        _example(spec, "lab02", "diagnostic")["concept_ids"] = [mechanism_id]
        for quiz in lab["quiz"]:
            if quiz["kind"] == "diagnostic":
                quiz["concept_ids"] = [mechanism_id]

    _rejects(spec, official_id, surface.split()[0])


def _outcome_without_example(spec: Spec) -> None:
    _example(spec, "lab01", "runnable")["outcome_ids"] = ["lab01.o-diagnose"]


def _outcome_without_assessment(spec: Spec) -> None:
    lab = _section(spec, "lab01")
    for item in [*lab["quiz"], *lab["questions"]]:
        item["outcome_ids"] = ["lab01.o-trace"]


@pytest.mark.parametrize(
    "mutation",
    (
        pytest.param(_outcome_without_example, id="example-mapping"),
        pytest.param(_outcome_without_assessment, id="quiz-or-coding-mapping"),
    ),
)
def test_every_outcome_has_example_and_assessment_mapping(mutation: Mutation) -> None:
    spec = make_assessed_spec()
    mutation(spec)

    _rejects(spec, "outcome")


def test_lab00_has_trace_quiz_and_diagnostic_coverage_without_coding() -> None:
    spec = make_assessed_spec()
    foundation = _section(spec, "lab00")
    assert "questions" not in foundation

    validated = validate_spec(spec)

    assert "questions" not in validated["foundation"]


def _is_simplified_chinese(text: object) -> bool:
    if not isinstance(text, str) or re.search(r"[\u4e00-\u9fff]", text) is None:
        return False
    return re.search(r"[這學輸轉錯為發實應個從]", text) is None


def test_forward_fixture_uses_chinese_json_prose_and_a_concrete_main_trace() -> None:
    spec = make_spec()
    lab = _section(spec, "lab01")
    lesson = lab["lesson"]
    runnable = _example(spec, "lab01", "runnable")
    trace = runnable.get("trace")

    representative_prose = [
        lab["title"],
        lesson["problem"]["context"],
        lesson["outcomes"][0]["text"],
        lesson["concepts"][0]["name"],
        lesson["concepts"][0]["definition"],
        runnable["title"],
        runnable["explanation"],
    ]
    assert all(_is_simplified_chinese(text) for text in representative_prose)

    representative = json.dumps(
        {"lesson": lesson, "runnable": runnable}, ensure_ascii=False
    )
    for placeholder in (
        "Teaching mechanism",
        "Execute one deterministic operation",
        "value = 1 + 1",
    ):
        assert placeholder not in representative

    assert "import json" in runnable["code"]
    assert re.search(r"json\.(loads|dumps)\(", runnable["code"])
    assert isinstance(trace, list) and len(trace) >= 2
    assert all(_is_simplified_chinese(step["explanation"]) for step in trace)
    assert any(
        re.search(r"json\.(loads|dumps)\(", step["operation"])
        for step in trace
    )
    assert any(
        "{" in step["input_state"] and ":" in step["input_state"]
        for step in trace
    )
    assert any(step["output_state"].strip() for step in trace)
