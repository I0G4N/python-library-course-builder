from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from assess_readiness import assess_readiness  # noqa: E402
from tests.course_v2_fixture import make_assessed_spec  # noqa: E402


def make_readiness_route() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "route": {"id": "json-route", "title": "JSON fixture route"},
        "official_sources": [
            {
                "id": "python-docs",
                "title": "Python JSON documentation",
                "url": "https://docs.python.org/3.13/library/json.html",
                "kind": "documentation",
                "version": "3.13",
            }
        ],
        "capabilities": [
            _route_capability(
                "python-functions",
                "python",
                "Python 函数",
                "定义并调用 Python 函数",
                [],
                "lab01",
                "a",
            ),
            _route_capability(
                "json-data-model",
                "library",
                "JSON 数据模型",
                "把 JSON 值映射为 Python 值",
                ["python-functions"],
                "lab01",
                "b",
            ),
            _route_capability(
                "json-errors",
                "library",
                "JSON 解析失败",
                "诊断格式错误的 JSON 输入",
                ["json-data-model"],
                "lab03",
                "c",
            ),
            _route_capability(
                "domain-boundary",
                "domain",
                "序列化边界",
                "识别序列化输入与输出边界",
                ["json-data-model"],
                "lab02",
                "a",
                extended=True,
            ),
        ],
    }


def _route_capability(
    capability_id: str,
    kind: str,
    subject: str,
    title: str,
    requires: list[str],
    first_used_in: str,
    answer_id: str,
    *,
    extended: bool = False,
) -> dict[str, Any]:
    capability = {
        "id": capability_id,
        "kind": kind,
        "subject": subject,
        "title": title,
        "requires": requires,
        "source_ids": ["python-docs"],
        "first_used_in": first_used_in,
        "prep_tier": "extended" if extended else "standard",
        "diagnostic": {
            "id": f"diagnose-{capability_id}",
            "kind": "code_reading",
            "prompt": f"Choose the observable for {capability_id}.",
            "choices": [
                {"id": "a", "text": "first"},
                {"id": "b", "text": "second"},
                {"id": "c", "text": "third"},
            ],
            "answer_id": answer_id,
        },
    }
    if extended:
        capability["prep_reason"] = "该能力跨越完整的输入、失败与恢复生命周期。"
    return capability


def make_ready_plan(
    *,
    missing_ids: set[str] | None = None,
    raw_sentinel: str = "temporary raw learner evidence",
) -> dict[str, Any]:
    route = make_readiness_route()
    missing = set(missing_ids or set())
    evidence = []
    responses = []
    for capability in route["capabilities"]:
        capability_id = capability["id"]
        if capability_id in missing:
            responses.append(
                {
                    "question_id": capability["diagnostic"]["id"],
                    "answer": "不会",
                }
            )
        else:
            evidence.append(
                {
                    "capability_id": capability_id,
                    "kind": "code",
                    "verdict": "sufficient",
                    "content": f"{raw_sentinel}: {capability_id}",
                }
            )
    return assess_readiness(
        route,
        {"schema_version": 1, "evidence": evidence, "responses": responses},
    )


def _replace_unit_ids(value: Any, old: str, new: str) -> Any:
    if isinstance(value, dict):
        return {
            key: _replace_unit_ids(item, old, new) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_unit_ids(item, old, new) for item in value]
    if isinstance(value, str):
        return value.replace(f"{old}.", f"{new}.")
    return value


def _rotate_quiz_positions(quiz: list[dict[str, Any]], offset: int) -> None:
    for question in quiz:
        choices = question["choices"]
        shift = offset % len(choices)
        question["choices"] = choices[shift:] + choices[:shift]


def make_v3_spec(plan: dict[str, Any]) -> dict[str, Any]:
    spec = deepcopy(make_assessed_spec())
    spec["schema_version"] = 3
    foundation = spec.pop("foundation")
    capabilities_by_id = {
        capability["id"]: capability for capability in plan["capabilities"]
    }
    units = []
    for index, planned in enumerate(plan["preparatory_units"]):
        unit_id = planned["id"]
        lesson = _replace_unit_ids(deepcopy(foundation["lesson"]), "lab00", unit_id)
        quiz = _replace_unit_ids(deepcopy(foundation["quiz"]), "lab00", unit_id)
        _rotate_quiz_positions(quiz, index)
        units.append(
            {
                **deepcopy(planned),
                "title": (
                    "Lab 00：环境与学习流程导览"
                    if unit_id == "lab00"
                    else f"{unit_id}：证据匹配的先修讲义"
                ),
                "lesson": lesson,
                "quiz": quiz,
            }
        )
    unit_concepts = {
        unit["id"]: [concept["id"] for concept in unit["lesson"]["concepts"]]
        for unit in units
    }
    profile_capabilities = []
    for capability_id in plan["required_capability_ids"]:
        planned = capabilities_by_id[capability_id]
        prep_id = planned["preparatory_unit_id"]
        profile_capabilities.append(
            {
                **deepcopy(planned),
                "preparatory_concept_ids": (
                    list(unit_concepts[prep_id]) if prep_id is not None else []
                ),
            }
        )
    spec["course"]["audience"] = {
        "level": "assessed",
        "prerequisite_profile": {
            "assessment": "evidence-dialogue",
            "route_id": plan["route_id"],
            "readiness_summary": plan["readiness_summary"],
            "capabilities": profile_capabilities,
        },
    }
    spec["preparatory_units"] = units
    spec["labs"][0]["depends_on"] = units[-1]["id"]
    return spec


def make_v3_spec_and_plan(
    *,
    missing_ids: set[str] | None = None,
    raw_sentinel: str = "temporary raw learner evidence",
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = make_ready_plan(missing_ids=missing_ids, raw_sentinel=raw_sentinel)
    return make_v3_spec(plan), plan
