from __future__ import annotations

from copy import deepcopy
import re
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


def make_readiness_route(*, language: str = "zh-CN") -> dict[str, Any]:
    if language == "en":
        capability_text = (
            ("Python functions", "Define and call Python functions"),
            ("JSON data model", "Map JSON values to Python values"),
            ("JSON parse failures", "Diagnose malformed JSON input"),
            ("Serialization boundary", "Identify serialization input and output boundaries"),
        )
        route_title = "JSON conversion fixture route"
    else:
        capability_text = (
            ("Python 函数", "定义并调用 Python 函数"),
            ("JSON 数据模型", "把 JSON 值映射为 Python 值"),
            ("JSON 解析失败", "诊断格式错误的 JSON 输入"),
            ("序列化边界", "识别序列化输入与输出边界"),
        )
        route_title = "JSON 测试路线"
    return {
        "schema_version": 2,
        "language": language,
        "route": {"id": "json-route", "title": route_title},
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
                *capability_text[0],
                [],
                "lab01",
                "a",
                language=language,
            ),
            _route_capability(
                "json-data-model",
                "library",
                *capability_text[1],
                ["python-functions"],
                "lab01",
                "b",
                language=language,
            ),
            _route_capability(
                "json-errors",
                "library",
                *capability_text[2],
                ["json-data-model"],
                "lab03",
                "c",
                language=language,
            ),
            _route_capability(
                "domain-boundary",
                "domain",
                *capability_text[3],
                ["json-data-model"],
                "lab02",
                "a",
                language=language,
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
    language: str,
    extended: bool = False,
) -> dict[str, Any]:
    if language == "en":
        prompt = f"Choose the observable for {capability_id}."
        choice_text = ("first observable", "second observable", "third observable")
    else:
        prompt = f"请选择 {capability_id} 的可观察结果。"
        choice_text = ("第一个结果", "第二个结果", "第三个结果")
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
            "prompt": prompt,
            "choices": [
                {"id": "a", "text": choice_text[0]},
                {"id": "b", "text": choice_text[1]},
                {"id": "c", "text": choice_text[2]},
            ],
            "answer_id": answer_id,
        },
    }
    if extended:
        capability["prep_reason"] = (
            "This capability spans the complete input, failure, and recovery lifecycle."
            if language == "en"
            else "该能力跨越完整的输入、失败与恢复生命周期。"
        )
    return capability


def make_ready_plan(
    *,
    missing_ids: set[str] | None = None,
    raw_sentinel: str = "temporary raw learner evidence",
    language: str = "zh-CN",
) -> dict[str, Any]:
    route = make_readiness_route(language=language)
    missing = set(missing_ids or set())
    evidence = []
    responses = []
    for capability in route["capabilities"]:
        capability_id = capability["id"]
        if capability_id in missing:
            responses.append(
                {
                    "question_id": capability["diagnostic"]["id"],
                    "answer": "I don't know" if language == "en" else "不会",
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
        {
            "schema_version": 2,
            "language": language,
            "evidence": evidence,
            "responses": responses,
        },
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


_HAN_RE = re.compile(r"[\u3400-\u9fff]")


def _tutorial_markdown(
    unit_id: str,
    title: str,
    lesson: dict[str, Any],
    *,
    language: str,
) -> str:
    concept = lesson["concepts"][0]
    problem = lesson["problem"]
    example = next(
        item for item in lesson["examples"] if item["kind"] == "runnable"
    )
    if language == "en":
        return (
            f"# {title}\n\n"
            f"This chapter begins with a concrete problem: {problem['context']} "
            "We will follow one value through the complete boundary before naming "
            "the reusable idea.\n\n"
            f"## Build the mental model\n\n"
            f"**{concept['name']}** means {concept['definition']} "
            f"In this course, it matters because {concept['purpose']}\n\n"
            f"## Trace one concrete value\n\n"
            f"{example['explanation']} Run `{example['command']}` and compare the "
            "observable output with the contract, then explain where a malformed "
            "input would stop the flow.\n\n"
            f"## Connect it to the project\n\n"
            f"{lesson['capstone_bridge']['increment']}\n\n"
            f"<!-- fixture-unit: {unit_id} -->\n\n"
        )
    return (
        f"# {title}\n\n"
        f"本章从一个具体问题开始：{problem['context']}。我们先让一个值完整地穿过边界，"
        "观察每一步发生了什么，再为可复用的机制命名。\n\n"
        "## 建立心智模型\n\n"
        f"**{concept['name']}** 指的是：{concept['definition']}。它在本课程中的作用是："
        f"{concept['purpose']}\n\n"
        "## 追踪一个具体值\n\n"
        f"{example['explanation']}。运行 `{example['command']}`，将可观察输出与契约逐项对照，"
        "然后说明格式错误的输入会在哪一步停止。\n\n"
        "## 接入课程项目\n\n"
        f"{lesson['capstone_bridge']['increment']}\n\n"
        f"<!-- fixture-unit: {unit_id} -->\n\n"
    )


def _fixture_context(path: tuple[str | int, ...]) -> str:
    for collection, prefix in (("labs", "Lab"), ("preparatory_units", "Prep")):
        if collection in path:
            index = path.index(collection)
            if index + 1 < len(path) and isinstance(path[index + 1], int):
                ordinal = int(path[index + 1])
                if collection == "preparatory_units" and ordinal == 0:
                    return "Lab 00 orientation"
                return f"{prefix} {ordinal + (1 if collection == 'labs' else 0):02d}"
    return "the JSON conversion course"


def _english_fixture_text(text: str, path: tuple[str | int, ...]) -> str:
    field = next(
        (str(part) for part in reversed(path) if isinstance(part, str)),
        "content",
    )
    context = _fixture_context(path)
    position = next(
        (int(part) + 1 for part in reversed(path) if isinstance(part, int)),
        1,
    )
    if path == ("course", "title"):
        return "Reliable JSON Conversion Course"
    if path == ("course", "description"):
        return "Verify JSON conversion contracts with concrete inputs and observable outputs."
    if path == ("course", "capstone"):
        return "A deterministic JSON conversion project"
    templates = {
        "subject": "JSON conversion foundations",
        "title": f"{context}: JSON conversion and observable boundaries",
        "track": "JSON conversion and error boundaries",
        "notes": "Every required JSON example runs deterministically on an offline CPU.",
        "assumes": "Python variables, functions, classes, and import statements",
        "does_not_assume": "JSON implementation internals or distributed systems",
        "reason": "This capability spans the complete input, failure, and recovery lifecycle.",
        "why": f"{context} exposes JSON conversion behavior through one small function.",
        "refresh": "Review parameters, return values, exceptions, and import statements.",
        "context": f"{context} must convert a concrete JSON value across a testable boundary.",
        "naive_approach": "Pass the input through unchanged and assume its representation is already correct.",
        "failure": "That shortcut hides type differences, malformed input, and the documented failure boundary.",
        "name": f"{context} JSON conversion mechanism",
        "definition": "A declared conversion maps one concrete JSON or Python value to an observable result.",
        "purpose": "Make the input, conversion step, output, failure, and recovery directly testable.",
        "mechanism": f"Step {position}: apply the declared JSON mapping and record the observable value.",
        "mental_model": "Treat conversion as a traceable pipeline from one owned input to one declared output.",
        "design_reasons": "A narrow interface isolates conversion, diagnosis, and replacement behavior.",
        "benefits": "The same input can be compared directly with the official json API result.",
        "tradeoffs": "The teaching implementation intentionally covers only the declared JSON subset.",
        "invariants": "The same valid input always produces the same declared observable output.",
        "boundaries": "Required examples run offline on CPU and reject inputs outside the declared subset.",
        "pitfalls": "JSON true, false, and null are not Python source spellings or ordinary strings.",
        "claim": "The conversion follows the pinned public contract in the Python json documentation.",
        "meaning": "A concrete JSON text or Python value crossing the declared API boundary.",
        "example": "Concrete boundary example: a ready boolean and its compact JSON representation.",
        "constraints": "The value must satisfy the documented JSON mapping and the unit's narrow contract.",
        "effects": "The operation returns a new observable value without mutating caller-owned input.",
        "condition": "The input type or text violates the declared JSON conversion contract.",
        "observable": "The boundary raises the documented exception before returning a value.",
        "recovery": "Repair the input type or JSON spelling, then call the same boundary again.",
        "input_state": f"Trace step {position} input: one concrete JSON text or Python value.",
        "operation": f"Trace step {position} operation: apply the declared conversion or validation.",
        "output_state": f"Trace step {position} output: the expected observable value or exception.",
        "input": "One declared JSON text or Python value owned by the caller.",
        "output": "One deterministic converted value returned across the course boundary.",
        "increment": f"{context} adds one tested JSON conversion capability to the capstone.",
        "next": "The next unit replaces the teaching mechanism with the pinned official json API.",
        "summary": f"{context} makes the JSON input, conversion, output, and failure path observable.",
        "prompt": "What observable result follows from this concrete JSON conversion, and how is a failure repaired?",
        "text": f"Choice {position}: preserve the declared JSON mapping and boundary behavior.",
        "feedback": (
            "Correct: this choice preserves the declared JSON mapping and observable boundary."
            if "正确" in text
            else "Not quite: this choice bypasses or changes the declared JSON boundary."
        ),
        "explanation": "Follow the concrete input through the declared conversion and compare the observable output.",
        "lower_level_dependencies": "Python type checks, values, branches, and string construction",
    }
    return templates.get(
        field,
        f"{context} explains {field.replace('_', ' ')} with a concrete JSON input and observable output.",
    )


def _englishize_fixture_prose(
    value: Any,
    path: tuple[str | int, ...] = (),
) -> Any:
    if isinstance(value, dict):
        return {
            key: _englishize_fixture_prose(item, (*path, key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _englishize_fixture_prose(item, (*path, index))
            for index, item in enumerate(value)
        ]
    if isinstance(value, str) and _HAN_RE.search(value):
        return _english_fixture_text(value, path)
    return value


def make_v3_spec(plan: dict[str, Any]) -> dict[str, Any]:
    spec = deepcopy(make_assessed_spec())
    spec["schema_version"] = 3
    spec["course"]["language"] = plan.get("language", "zh-CN")
    spec["course"]["lesson_format"] = "tutorial-markdown-v1"
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
                    (
                        "Lab 00: Environment and learning workflow"
                        if plan.get("language") == "en"
                        else "Lab 00：环境与学习流程导览"
                    )
                    if unit_id == "lab00"
                    else (
                        f"{unit_id}: JSON conversion foundations"
                        if plan.get("language") == "en"
                        else f"{unit_id}：JSON 转换基础"
                    )
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
    if plan.get("language") == "en":
        spec = _englishize_fixture_prose(spec)
    language = str(plan.get("language", "zh-CN"))
    for unit in [*spec["preparatory_units"], *spec["labs"]]:
        unit["tutorial"] = _tutorial_markdown(
            str(unit["id"]),
            str(unit["title"]),
            unit["lesson"],
            language=language,
        )
    return spec


def make_v3_spec_and_plan(
    *,
    missing_ids: set[str] | None = None,
    raw_sentinel: str = "temporary raw learner evidence",
    language: str = "zh-CN",
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = make_ready_plan(
        missing_ids=missing_ids,
        raw_sentinel=raw_sentinel,
        language=language,
    )
    return make_v3_spec(plan), plan
