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
_DELETE = object()


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


def _mutate_path(
    root: Any, path: tuple[str | int, ...], value: object
) -> None:
    target = root
    for part in path[:-1]:
        target = target[part]
    leaf = path[-1]
    if value is _DELETE:
        target.pop(leaf)
    else:
        target[leaf] = value


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


@pytest.mark.parametrize(
    ("capability_id", "updates", "fragment"),
    (
        pytest.param(
            "json-data-model",
            {"status": "large-gap"},
            "status",
            id="large-gap-is-not-serialized",
        ),
        pytest.param(
            "python-functions",
            {
                "decision": "foundation",
                "foundation_concept_ids": ["lab00.c-mechanism"],
            },
            "decision",
            id="known-maps-to-assume",
        ),
        pytest.param(
            "json-data-model",
            {"first_used_in": "lab00"},
            "first_used_in",
            id="first-use-is-graded",
        ),
        pytest.param(
            "python-functions",
            {"kind": "tool"},
            "kind",
            id="kind-is-closed",
        ),
        pytest.param(
            "json-data-model",
            {"basis": "model-guess"},
            "basis",
            id="basis-is-closed",
        ),
        pytest.param(
            "json-data-model",
            {"source_ids": ["missing-source"]},
            "source_ids",
            id="sources-are-registered",
        ),
        pytest.param(
            "json-data-model",
            {"foundation_concept_ids": []},
            "foundation_concept_ids",
            id="foundation-decision-needs-concepts",
        ),
        pytest.param(
            "json-data-model",
            {"foundation_concept_ids": ["lab00.c-missing"]},
            "foundation_concept_ids",
            id="foundation-concepts-resolve",
        ),
    ),
)
def test_assessed_profile_rejects_inconsistent_capability_provenance(
    capability_id: str, updates: dict[str, object], fragment: str
) -> None:
    spec = make_assessed_spec()
    _capability(spec, capability_id).update(updates)

    _rejects(spec, fragment)


def test_foundation_capability_has_source_evidence_in_a_mapped_lab00_concept() -> None:
    spec = make_assessed_spec()
    spec["target"]["official_sources"].append(  # type: ignore[index]
        {
            "id": "python-language",
            "title": "Python language reference",
            "url": "https://docs.python.org/3.13/reference/",
            "kind": "documentation",
            "version": "3.13",
        }
    )
    _capability(spec, "json-data-model")["source_ids"] = ["python-language"]

    _rejects(spec, "json-data-model", "foundation_concept_ids", "source_ids")


@pytest.mark.parametrize(
    ("section_id", "payload"),
    (
        pytest.param(
            "lab00",
            {"tier": "foundation", "min": 30, "max": 60, "reason": "gap"},
            id="foundation-exact-range",
        ),
        pytest.param("lab02", None, id="every-graded-lab"),
        pytest.param(
            "lab01",
            {"tier": "foundation", "min": 30, "max": 45},
            id="graded-tier-is-closed",
        ),
        pytest.param(
            "lab01",
            {"tier": "standard", "min": 30, "max": 60},
            id="standard-exact-range",
        ),
        pytest.param(
            "lab01",
            {"tier": "standard", "min": 30, "max": 45, "reason": "extra"},
            id="standard-has-no-reason",
        ),
        pytest.param(
            "lab03",
            {"tier": "extended", "min": 45, "max": 60},
            id="extended-needs-reason",
        ),
        pytest.param(
            "lab03",
            {"tier": "extended", "min": 30, "max": 60, "reason": "extra work"},
            id="extended-exact-range",
        ),
        pytest.param(
            "lab00",
            {"tier": "foundation", "min": 45, "max": 60, "reason": ""},
            id="foundation-reason-is-nonempty",
        ),
        pytest.param(
            "lab03",
            {"tier": "extended", "min": 45, "max": 60, "reason": ""},
            id="extended-reason-is-nonempty",
        ),
    ),
)
def test_assessed_study_minutes_reject_noncanonical_shapes(
    section_id: str, payload: dict[str, object] | None
) -> None:
    spec = make_assessed_spec()
    section = _section(spec, section_id)
    if payload is None:
        section.pop("study_minutes")
    else:
        section["study_minutes"] = dict(payload)

    _rejects(spec, "study_minutes")


@pytest.mark.parametrize(
    ("path", "value"),
    (
        pytest.param(None, _DELETE, id="contract-required"),
        pytest.param(("kind",), "analogy", id="kind-is-closed"),
        pytest.param(("forms",), [], id="forms-nonempty"),
        pytest.param(("inputs",), [], id="inputs-nonempty"),
        pytest.param(("outputs",), [], id="outputs-nonempty"),
        pytest.param(("effects",), [], id="effects-nonempty"),
        pytest.param(("failure_modes",), [], id="failure-modes-nonempty"),
        pytest.param(
            ("inputs", 0, "meaning"), _DELETE, id="input-required-field"
        ),
        pytest.param(
            ("inputs", 0, "teacher_note"), "private", id="input-fields-closed"
        ),
        pytest.param(
            ("outputs", 0, "form"), _DELETE, id="output-required-field"
        ),
        pytest.param(
            ("outputs", 0, "teacher_note"), "private", id="output-fields-closed"
        ),
        pytest.param(
            ("failure_modes", 0, "recovery"),
            _DELETE,
            id="failure-required-field",
        ),
        pytest.param(
            ("failure_modes", 0, "teacher_note"),
            "private",
            id="failure-fields-closed",
        ),
    ),
)
def test_operational_contract_rejects_incomplete_or_open_shapes(
    path: tuple[str | int, ...] | None, value: object
) -> None:
    spec = make_assessed_spec()
    concept = _concept(spec, "lab01")
    if path is None:
        concept.pop("operational_contract")
    else:
        _mutate_path(concept["operational_contract"], path, value)

    _rejects(spec, "operational_contract")


@pytest.mark.parametrize(
    "case",
    (
        "trace-required",
        "at-least-two-steps",
        "stable-unique-step-ids",
        "stable-step-id-format",
        "concept-subset",
        "concept-ids-nonempty",
        "step-fields-required",
    ),
)
def test_runnable_trace_rejects_incomplete_or_unlinked_steps(
    case: str,
) -> None:
    spec = make_assessed_spec()
    runnable = _example(spec, "lab01", "runnable")
    if case == "trace-required":
        runnable.pop("trace")
    elif case == "at-least-two-steps":
        runnable["trace"] = runnable["trace"][:1]
    elif case == "stable-unique-step-ids":
        runnable["trace"][1]["id"] = runnable["trace"][0]["id"]
    elif case == "stable-step-id-format":
        runnable["trace"][0]["id"] = "Bad Step"
    elif case == "concept-subset":
        runnable = _example(spec, "lab02", "runnable")
        runnable["concept_ids"] = ["lab02.c-mechanism"]
        runnable["trace"][0]["concept_ids"] = ["lab02.c-official"]
    elif case == "concept-ids-nonempty":
        runnable["trace"][0]["concept_ids"] = []
    else:
        runnable["trace"][0].pop("operation")

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


@pytest.mark.parametrize("surface", ("runnable trace", "quiz", "diagnostic"))
def test_every_lab00_concept_has_required_non_coding_coverage(surface: str) -> None:
    spec = make_assessed_spec()
    foundation = _section(spec, "lab00")
    target_id = "lab00.c-json-shape"
    fallback_id = "lab00.c-mechanism"

    if surface == "runnable trace":
        for step in _example(spec, "lab00", "runnable")["trace"]:
            if target_id in step["concept_ids"]:
                step["concept_ids"] = [fallback_id]
    elif surface == "quiz":
        for quiz in foundation["quiz"]:
            quiz["concept_ids"] = [fallback_id]
    else:
        _example(spec, "lab00", "diagnostic")["concept_ids"] = [fallback_id]
        for quiz in foundation["quiz"]:
            if quiz["kind"] == "diagnostic":
                quiz["concept_ids"] = [fallback_id]

    _rejects(spec, "lab00", target_id, surface.split()[0])


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


def test_forward_fixture_uses_chinese_json_prose_and_a_concrete_main_trace() -> None:
    spec = make_spec()
    lab = _section(spec, "lab01")
    lesson = lab["lesson"]
    runnable = _example(spec, "lab01", "runnable")
    trace = runnable.get("trace")

    learner_prose = json.dumps(
        {
            "title": lab["title"],
            "problem": lesson["problem"],
            "outcomes": lesson["outcomes"],
            "concept": lesson["concepts"][0],
            "example_title": runnable["title"],
            "example_explanation": runnable["explanation"],
        },
        ensure_ascii=False,
    )
    for expected_phrase in ("解析 JSON 文本", "Python 字典", "输入", "输出"):
        assert expected_phrase in learner_prose

    representative = json.dumps(spec, ensure_ascii=False)
    for generic_english in (
        "Teaching mechanism",
        "Execute one deterministic operation",
        "value = 1 + 1",
        "plain Python values",
        "The returned scalar.",
    ):
        assert generic_english not in representative

    assert "import json" in runnable["code"]
    assert re.search(r"json\.(loads|dumps)\(", runnable["code"])
    assert isinstance(trace, list) and len(trace) >= 2
    trace_text = json.dumps(trace, ensure_ascii=False)
    for expected_phrase in ("JSON 文本", "Python 字典", "解析", "输入", "输出"):
        assert expected_phrase in trace_text
    assert any(
        re.search(r"json\.(loads|dumps)\(", step["operation"])
        for step in trace
    )
    assert any(
        "{" in step["input_state"] and ":" in step["input_state"]
        for step in trace
    )
    assert any(step["output_state"].strip() for step in trace)
