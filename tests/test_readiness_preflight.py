from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
ASSESSOR_PATH = (
    ROOT
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
    / "scripts/assess_readiness.py"
)
FIXTURES = ROOT / "tests/fixtures/readiness"


def _assessor() -> ModuleType:
    assert ASSESSOR_PATH.is_file(), "assess_readiness.py is missing"
    spec = importlib.util.spec_from_file_location("assess_readiness", ASSESSOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _route(name: str = "numpy") -> dict[str, object]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _evidence(
    *items: dict[str, object],
    responses: list[dict[str, object]] | None = None,
    language: str = "zh-CN",
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "language": language,
        "evidence": list(items),
        "responses": list(responses or []),
    }


def test_readiness_v2_requires_matching_supported_language_and_binds_identity() -> None:
    module = _assessor()
    route_en = _route()
    route_en["language"] = "en"
    responses = [
        {"question_id": capability["diagnostic"]["id"], "answer": "不会"}
        for capability in route_en["capabilities"]
    ]

    plan_en = module.assess_readiness(
        route_en,
        _evidence(responses=responses, language="en"),
    )
    plan_zh = module.assess_readiness(
        _route(),
        _evidence(responses=responses),
    )

    assert plan_en["schema_version"] == 2
    assert plan_en["language"] == "en"
    assert plan_en["route_digest"] != plan_zh["route_digest"]
    assert plan_en["readiness_summary"] != plan_zh["readiness_summary"]
    assert plan_en["plan_digest"] != plan_zh["plan_digest"]
    validated = module.validate_ready_plan(plan_en)
    assert validated["schema_version"] == 2
    assert validated["language"] == "en"
    assert validated["readiness_summary"] == plan_en["readiness_summary"]
    assert validated["plan_digest"] == plan_en["plan_digest"]


@pytest.mark.parametrize(
    ("target", "mutation", "message"),
    [
        ("route", lambda value: value.pop("language"), "language"),
        ("route", lambda value: value.update({"language": "fr"}), "language"),
        ("evidence", lambda value: value.pop("language"), "language"),
        ("evidence", lambda value: value.update({"language": "fr"}), "language"),
        ("evidence", lambda value: value.update({"language": "en"}), "language"),
    ],
)
def test_readiness_v2_rejects_missing_unsupported_or_mismatched_language(
    target: str,
    mutation: object,
    message: str,
) -> None:
    module = _assessor()
    route = _route()
    evidence = _evidence()
    mutation(route if target == "route" else evidence)

    with pytest.raises(module.ReadinessValidationError, match=message):
        module.assess_readiness(route, evidence)


def test_readiness_v1_remains_an_implicit_zh_cn_compatibility_contract() -> None:
    module = _assessor()
    route = _route()
    route["schema_version"] = 1
    route.pop("language")
    evidence = _evidence()
    evidence["schema_version"] = 1
    evidence.pop("language")
    for capability in route["capabilities"]:
        evidence["responses"].append(
            {"question_id": capability["diagnostic"]["id"], "answer": "不会"}
        )

    plan = module.assess_readiness(route, evidence)

    assert plan["schema_version"] == 1
    assert "language" not in plan
    assert module.validate_ready_plan(plan)["readiness_summary"] == plan[
        "readiness_summary"
    ]

    forged = deepcopy(plan)
    forged["language"] = "en"
    with pytest.raises(module.ReadinessValidationError, match="language"):
        module.validate_ready_plan(forged)


@pytest.mark.parametrize("fixture_name", ["numpy", "pytorch", "verl"])
def test_pending_set_is_required_capabilities_minus_sufficient_evidence(
    fixture_name: str,
) -> None:
    module = _assessor()
    route = _route(fixture_name)
    report = module.assess_readiness(
        route,
        _evidence(
            {
                "capability_id": "python-base",
                "kind": "code",
                "verdict": "sufficient",
                "content": "raw code evidence must remain temporary",
            }
        ),
    )

    assert report["status"] == "needs_evidence"
    assert report["required_capability_ids"] == [
        "python-base",
        "library-core",
        "domain-loop",
    ]
    assert report["needs_evidence_capability_ids"] == [
        "library-core",
        "domain-loop",
    ]
    assert report["next_question"]["capability_id"] == "library-core"
    assert isinstance(report["next_question"], dict)


def test_self_claim_is_not_mastery_evidence_and_only_one_question_is_emitted() -> None:
    module = _assessor()
    report = module.assess_readiness(
        _route(),
        _evidence(
            {
                "capability_id": "python-base",
                "kind": "self_report",
                "verdict": "sufficient",
                "content": "我会",
            }
        ),
    )

    assert report["mastered_capability_ids"] == []
    assert report["needs_evidence_capability_ids"][0] == "python-base"
    assert report["next_question"]["id"] == "numpy-python-base"
    assert "questions" not in report


@pytest.mark.parametrize(
    "claim",
    [
        "我会",
        "我会 NumPy 数组",
        "我已经掌握",
        "yes, I know this",
        "I know NumPy arrays",
        "我很熟悉 NumPy",
        "本人掌握 NumPy",
        "当然会 NumPy",
        "熟练使用 NumPy",
        "sure, I understand it",
    ],
)
def test_claim_only_conversation_is_not_accepted_as_mastery_evidence(
    claim: str,
) -> None:
    module = _assessor()
    report = module.assess_readiness(
        _route(),
        _evidence(
            {
                "capability_id": "python-base",
                "kind": "conversation",
                "verdict": "sufficient",
                "content": claim,
            }
        ),
    )

    assert report["mastered_capability_ids"] == []
    assert report["next_question"]["capability_id"] == "python-base"


def test_structured_prior_conversation_diagnostic_is_reused() -> None:
    module = _assessor()
    report = module.assess_readiness(
        _route(),
        _evidence(
            {
                "capability_id": "python-base",
                "kind": "conversation",
                "verdict": "sufficient",
                "question_id": "numpy-python-base",
                "answer_id": "a",
                "content": "raw prior dialogue remains temporary",
            }
        ),
    )

    assert report["mastered_capability_ids"] == ["python-base"]
    assert report["next_question"]["capability_id"] == "library-core"


def test_preparatory_unit_numbering_has_no_two_digit_ceiling() -> None:
    module = _assessor()
    route = _route()
    prototype = route["capabilities"][0]
    capabilities = []
    responses = []
    previous_id = None
    for index in range(1, 101):
        capability_id = f"cap-{index:03d}"
        question_id = f"question-{index:03d}"
        capability = deepcopy(prototype)
        capability.update(
            {
                "id": capability_id,
                "title": f"Capability {index}",
                "requires": [previous_id] if previous_id is not None else [],
                "diagnostic": {
                    **deepcopy(prototype["diagnostic"]),
                    "id": question_id,
                },
            }
        )
        capabilities.append(capability)
        responses.append({"question_id": question_id, "answer": "不会"})
        previous_id = capability_id
    route["capabilities"] = capabilities

    report = module.assess_readiness(route, _evidence(responses=responses))

    assert report["status"] == "ready"
    assert len(report["preparatory_units"]) == 101
    assert report["preparatory_units"][-1]["id"] == "prep100"
    assert report["preparatory_units"][-1]["depends_on"] == "prep99"
    assert module.validate_ready_plan(report)["readiness_summary"] == report[
        "readiness_summary"
    ]


def test_declared_unknown_marks_missing_and_is_never_asked_again() -> None:
    module = _assessor()
    report = module.assess_readiness(
        _route(),
        _evidence(
            responses=[
                {"question_id": "numpy-python-base", "answer": "不会"},
            ]
        ),
    )

    assert report["missing_capability_ids"] == ["python-base"]
    assert "python-base" not in report["needs_evidence_capability_ids"]
    assert report["next_question"]["capability_id"] == "library-core"
    assert report["asked_question_ids"] == ["numpy-python-base"]


def test_diagnostic_answers_advance_once_without_reasking_resolved_capabilities() -> None:
    module = _assessor()
    responses = [
        {"question_id": "numpy-python-base", "answer": "a"},
        {"question_id": "numpy-library-core", "answer": "not-b"},
    ]
    report = module.assess_readiness(_route(), _evidence(responses=responses))

    assert report["mastered_capability_ids"] == ["python-base"]
    assert report["missing_capability_ids"] == ["library-core"]
    assert report["needs_evidence_capability_ids"] == ["domain-loop"]
    assert report["next_question"]["capability_id"] == "domain-loop"
    assert report["asked_question_ids"] == [
        "numpy-python-base",
        "numpy-library-core",
    ]


def test_diagnostic_responses_must_follow_the_single_question_prefix() -> None:
    module = _assessor()

    with pytest.raises(module.ReadinessValidationError, match="next_question"):
        module.assess_readiness(
            _route(),
            _evidence(
                responses=[
                    {"question_id": "numpy-domain-loop", "answer": "c"},
                ]
            ),
        )


def test_all_mastered_yields_only_lab00_and_stable_summary() -> None:
    module = _assessor()
    route = _route()
    evidence = _evidence(
        *[
            {
                "capability_id": capability["id"],
                "kind": "conversation",
                "verdict": "sufficient",
                "question_id": capability["diagnostic"]["id"],
                "answer_id": capability["diagnostic"]["answer_id"],
                "content": f"raw evidence for {capability['id']}",
            }
            for capability in route["capabilities"]
        ]
    )

    first = module.assess_readiness(route, evidence)
    second = module.assess_readiness(route, deepcopy(evidence))

    assert first["status"] == "ready"
    assert first["preparatory_units"] == [
        {
            "id": "lab00",
            "category": "orientation",
            "dag_level": 0,
            "depends_on": None,
            "capability_ids": [],
            "study_minutes": {"tier": "orientation", "min": 15, "max": 30},
        }
    ]
    assert first["preparatory_time"] == {"min": 15, "max": 30}
    assert first["readiness_summary"] == second["readiness_summary"]
    assert len(first["readiness_summary"]) == 12


def test_ready_plan_recomputes_summary_and_closed_prep_structure() -> None:
    module = _assessor()
    responses = [
        {"question_id": capability["diagnostic"]["id"], "answer": "不会"}
        for capability in _route()["capabilities"]
    ]
    plan = module.assess_readiness(_route(), _evidence(responses=responses))

    forged_summary = deepcopy(plan)
    forged_summary["readiness_summary"] = "0" * 12
    forged_summary["plan_digest"] = module._digest(
        module._safe_plan_projection(forged_summary)
    )
    with pytest.raises(module.ReadinessValidationError, match="readiness_summary"):
        module.validate_ready_plan(forged_summary)

    forged_chain = deepcopy(plan)
    forged_chain["preparatory_units"][1]["depends_on"] = "prep99"
    forged_chain["readiness_summary"] = module._readiness_summary(forged_chain)
    forged_chain["plan_digest"] = module._digest(
        module._safe_plan_projection(forged_chain)
    )
    with pytest.raises(module.ReadinessValidationError, match="capability DAG"):
        module.validate_ready_plan(forged_chain)


def test_multilevel_gaps_group_by_dag_level_then_python_library_domain() -> None:
    module = _assessor()
    route = _route()
    route["capabilities"].insert(
        1,
        {
            **deepcopy(route["capabilities"][0]),
            "id": "domain-base",
            "kind": "domain",
            "title": "A same-level domain prerequisite",
            "diagnostic": {
                **deepcopy(route["capabilities"][0]["diagnostic"]),
                "id": "numpy-domain-base",
            },
        },
    )
    responses = [
        {"question_id": capability["diagnostic"]["id"], "answer": "不会"}
        for capability in route["capabilities"]
    ]

    report = module.assess_readiness(route, _evidence(responses=responses))

    assert report["status"] == "ready"
    units = report["preparatory_units"]
    assert [(item["dag_level"], item["category"]) for item in units[1:]] == [
        (1, "python"),
        (1, "domain"),
        (2, "library"),
        (3, "domain"),
    ]
    assert [item["id"] for item in units] == [
        "lab00",
        "prep01",
        "prep02",
        "prep03",
        "prep04",
    ]
    assert units[-1]["study_minutes"] == {
        "tier": "extended",
        "min": 45,
        "max": 60,
        "reason": "This fixture capability spans a complete lifecycle.",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda route: route["capabilities"][0].update({"requires": ["missing"]}), "unknown"),
        (lambda route: route["capabilities"][0].update({"requires": ["domain-loop"]}), "cycle"),
    ],
)
def test_invalid_capability_dag_fails_closed(mutation: object, message: str) -> None:
    module = _assessor()
    route = _route()
    mutation(route)

    with pytest.raises(module.ReadinessValidationError, match=message):
        module.assess_readiness(route, _evidence())
