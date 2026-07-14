from __future__ import annotations

from copy import deepcopy
from typing import Any


MISSING = object()


def _concept(lab_id: str, *, official: bool = False) -> dict[str, Any]:
    suffix = "official" if official else "mechanism"
    name = "JSON 官方接口桥接" if official else "解析 JSON 文本"
    return {
        "id": f"{lab_id}.c-{suffix}",
        "name": name,
        "definition": (
            "输入合法 JSON 文本后，将它转换为可观察的 Python 字典输出。"
            if not official
            else "使用 json 官方接口完成 JSON 文本与 Python 字典之间的确定性转换。"
        ),
        "purpose": "让输入、转换动作、输出和失败方式都能被测试直接观察。",
        "mechanism": [
            "接收一段调用者提供的 JSON 文本输入。",
            "调用声明的解析或序列化操作。",
            "返回 Python 字典或 JSON 文本输出，不依赖隐藏的全局状态。",
        ],
        "mental_model": "把转换看成一条从具体输入到具体输出的可追踪管道。",
        "design_reasons": ["窄接口便于隔离解析、诊断和替换行为。"],
        "benefits": ["相同输入可以与官方 json API 的结果直接比较。"],
        "tradeoffs": ["教学实现只覆盖本课程声明的 JSON 子集。"],
        "invariants": ["相同合法输入产生相同的声明输出。"],
        "boundaries": ["必做示例只在 CPU 和离线环境运行。"],
        "pitfalls": ["JSON 的 true 会转换为 Python 的 True，而不是字符串。"],
        "source_claims": [
            {
                "source_id": "python-docs",
                "claim": "该转换遵循固定版本的 Python json 公共接口约定。",
                "status": "documented",
            }
        ],
    }


def _lesson(lab_id: str, *, official: bool = False) -> dict[str, Any]:
    concepts = [_concept(lab_id, official=True)] if official else []
    concepts.append(_concept(lab_id))
    return {
        "prerequisites": [
            {
                "id": f"{lab_id}.p-python",
                "title": "Python 函数与返回值",
                "why": "本 Lab 通过一个小函数暴露 JSON 转换行为。",
                "refresh": "复习参数、返回值、异常和 import 语句。",
            }
        ],
        "problem": {
            "context": "累积项目需要把 JSON 文本输入可靠地解析为 Python 字典输出。",
            "naive_approach": "把输入当作普通字符串直接传给后续代码。",
            "failure": "布尔值没有转换，格式错误也无法在明确边界被诊断。",
        },
        "outcomes": [
            {
                "id": f"{lab_id}.o-trace",
                "text": "追踪 JSON 文本输入、解析动作和 Python 字典输出。",
            },
            {
                "id": f"{lab_id}.o-diagnose",
                "text": "根据 JSONDecodeError 诊断并修复格式错误。",
            },
        ],
        "concepts": concepts,
        "examples": [
            {
                "id": f"{lab_id}.e-runnable",
                "title": "解析一个具体 JSON 输入",
                "kind": "runnable",
                "path": "examples/01_happy_path.py",
                "code": (
                    "import json\n\n"
                    "text = '{\"ready\": true}'\n"
                    "result = json.loads(text)\n"
                    "print(result)\n"
                ),
                "command": "python examples/01_happy_path.py",
                "expected_output": "{'ready': True}",
                "explanation": "示例在离线 CPU 环境中把 JSON 文本解析为 Python 字典。",
                "concept_ids": [f"{lab_id}.c-mechanism"],
                "outcome_ids": [f"{lab_id}.o-trace"],
                "trace": [
                    {
                        "id": f"{lab_id}.t-input",
                        "concept_ids": [f"{lab_id}.c-mechanism"],
                        "input_state": "JSON 文本输入：'{\"ready\": true}'",
                        "operation": "调用 json.loads(text) 解析 JSON 文本输入。",
                        "output_state": "解析得到一个 Python 字典。",
                        "explanation": "解析会把 JSON 的 true 转换为 Python 的 True。",
                    },
                    {
                        "id": f"{lab_id}.t-output",
                        "concept_ids": [f"{lab_id}.c-mechanism"],
                        "input_state": "Python 字典：{'ready': True}",
                        "operation": "将 result 作为函数边界的可观察输出。",
                        "output_state": "Python 字典输出：{'ready': True}",
                        "explanation": "输出保留 ready 字段，并使用 Python 布尔值。",
                    },
                ],
            },
            {
                "id": f"{lab_id}.e-diagnostic",
                "title": "修复尾随逗号导致的解析失败",
                "kind": "diagnostic",
                "wrong_code": "import json\njson.loads('{\"ready\": true,}')\n",
                "symptom": "调用抛出 json.JSONDecodeError，因而没有 Python 字典输出。",
                "cause": "JSON 对象最后一个成员后不能保留尾随逗号。",
                "fix_code": "import json\nresult = json.loads('{\"ready\": true}')\n",
                "explanation": "先修正 JSON 文本输入，再重新执行解析。",
                "concept_ids": [f"{lab_id}.c-mechanism"],
                "outcome_ids": [f"{lab_id}.o-diagnose"],
            },
        ],
        "capstone_bridge": {
            "input": "一段经过声明的 JSON 文本。",
            "output": "一个明确归调用者所有的 Python 值。",
            "increment": f"为累积项目加入 {lab_id} 的 JSON 转换能力。",
            "next": "下一 Lab 使用固定版本的官方 json API 完成替换。",
        },
        "summary": [
            "教学实现让 JSON 输入、转换动作和输出都可以被追踪。",
            "下一 Lab 将完成有评分的官方接口替换。",
        ],
    }


def _quiz(lab_id: str, *, first_position: int) -> list[dict[str, Any]]:
    result = []
    for ordinal, (kind, answer_position) in enumerate(
        (("execution_trace", first_position), ("diagnostic", (first_position + 1) % 3)),
        start=1,
    ):
        if kind == "execution_trace":
            prompt = "json.loads('{\"ready\": true}') 会产生什么结果？"
            correct = (
                "返回 {'ready': True}",
                "正确：JSON 对象变成 Python 字典，true 变成 True。",
            )
            distractors = [
                (
                    "返回原始字符串 '{\"ready\": true}'",
                    "json.loads 会解析文本，而不是原样返回输入。",
                ),
                (
                    "返回 {'ready': 'true'}",
                    "JSON 布尔值会变成 Python 的 True，不会变成字符串。",
                ),
            ]
            explanation = "沿着具体输入、json.loads 调用和 Python 字典输出逐步追踪。"
        else:
            prompt = "json.loads('{\"ready\": true,}') 为什么失败，应该怎样修复？"
            correct = (
                "删除 true 后面的尾随逗号",
                "正确：合法 JSON 对象的最后一个成员后没有尾随逗号。",
            )
            distractors = [
                (
                    "把 true 改成 Python 的 True",
                    "JSON 文本使用小写 true；改成 True 反而不是合法 JSON。",
                ),
                (
                    "改用 eval 解析字符串",
                    "eval 不是 JSON 解析器，也会扩大不必要的执行边界。",
                ),
            ]
            explanation = "根据 JSONDecodeError 回到输入文本边界，修正语法后重试。"
        options = list(distractors)
        options.insert(answer_position, correct)
        choices = [
            {
                "id": choice_id,
                "text": option[0],
                "feedback": option[1],
            }
            for choice_id, option in zip(("a", "b", "c"), options, strict=True)
        ]
        result.append(
            {
                "id": f"{lab_id}.k{ordinal:02d}",
                "kind": kind,
                "prompt": prompt,
                "choices": choices,
                "answer_id": choices[answer_position]["id"],
                "explanation": explanation,
                "concept_ids": [f"{lab_id}.c-mechanism"],
                "outcome_ids": [
                    f"{lab_id}.o-{'trace' if kind == 'execution_trace' else 'diagnose'}"
                ],
            }
        )
    return result


def _test(
    path: str,
    symbol: str,
    expected: int,
    *,
    hidden: bool = False,
) -> dict[str, str]:
    module = path.removesuffix(".py").replace("/", ".")
    suffix = "_hidden" if hidden else ""
    selector = f"test_{symbol}{suffix}"
    return {
        "path": f"{selector}.py",
        "selector": selector,
        "code": (
            f"from {module} import {symbol}\n\n"
            f"def {selector}():\n"
            f"    assert {symbol}() == {expected}\n"
        ),
    }


def _question(
    lab_id: str,
    number: int,
    *,
    symbol: str,
    path: str,
    kind: str,
    question_number: int,
    timeout_seconds: object = MISSING,
) -> dict[str, Any]:
    concept = "official" if kind == "official_bridge" else "mechanism"
    question: dict[str, Any] = {
        "id": f"{lab_id}.q{question_number}",
        "kind": kind,
        "title": f"完成 {lab_id} 的 JSON 转换边界",
        "file": path,
        "symbol": symbol,
        "points": 1,
        "prompt": "通过声明的函数边界返回测试要求的确定性结果。",
        "concept_ids": [f"{lab_id}.c-{concept}"],
        "outcome_ids": [f"{lab_id}.o-trace"],
        "example": {
            "input": f"{symbol}()",
            "output": str(number),
            "explanation": "The function returns the Lab value.",
        },
        "public_test": _test(path, symbol, number),
        "hidden_test": _test(path, symbol, number, hidden=True),
    }
    if timeout_seconds is not MISSING:
        question["timeout_seconds"] = timeout_seconds
    return question


def make_spec(timeout_seconds: object = MISSING) -> dict[str, object]:
    labs: list[dict[str, Any]] = []
    quiz_positions = (0, 2, 1)
    for number in range(1, 4):
        lab_id = f"lab{number:02d}"
        symbol = f"answer_{number}"
        answer_path = f"{lab_id}/answer.py"
        official = number > 1
        first_question = _question(
            lab_id,
            number,
            symbol=symbol,
            path=answer_path,
            kind="official_bridge" if official else "reimplementation",
            question_number=1,
            timeout_seconds=timeout_seconds if number == 1 else MISSING,
        )
        answer_import = "import json\n\n" if official else ""
        files = [
            {
                "path": answer_path,
                "starter": f"{answer_import}def {symbol}():\n    raise NotImplementedError\n",
                "reference": f"{answer_import}def {symbol}():\n    return {number}\n",
            }
        ]
        questions = [first_question]
        if official:
            mini_symbol = f"mini_{number}"
            mini_path = f"{lab_id}/mini.py"
            files.append(
                {
                    "path": mini_path,
                    "starter": f"def {mini_symbol}():\n    raise NotImplementedError\n",
                    "reference": f"def {mini_symbol}():\n    return {number}\n",
                }
            )
            questions.append(
                _question(
                    lab_id,
                    number,
                    symbol=mini_symbol,
                    path=mini_path,
                    kind="reimplementation",
                    question_number=2,
                )
            )
            official_bridge: dict[str, Any] | None = {
                "from_lab": f"lab{number - 1:02d}",
                "mini_module": (
                    "lab01.answer"
                    if number == 2
                    else f"lab{number - 1:02d}.mini"
                ),
                "official_symbols": ["json.dumps"],
                "required_imports": ["json"],
                "question_id": first_question["id"],
                "observables": [
                    {"id": "return-value", "description": "函数返回的标量值。"}
                ],
                "comparison_cases": [
                    {
                        "input": f"{symbol}()",
                        "expected": number,
                        "observable_ids": ["return-value"],
                    }
                ],
            }
            learner_file = mini_path
            reimplementation_ids = [f"{lab_id}.q2"]
        else:
            official_bridge = None
            learner_file = answer_path
            reimplementation_ids = [f"{lab_id}.q1"]

        lab: dict[str, Any] = {
            "id": lab_id,
            "title": f"Lab {number}: JSON 转换",
            "depends_on": "lab00" if number == 1 else f"lab{number - 1:02d}",
            "lesson": _lesson(lab_id, official=official),
            "sources": ["python-docs"],
            "files": files,
            "questions": questions,
            "quiz": _quiz(lab_id, first_position=quiz_positions[number - 1]),
            "module_cycle": {
                "reimplementation": {
                    "module_id": f"{lab_id}.mini-module",
                    "title": f"{lab_id} 的 JSON 转换教学实现",
                    "target_symbols": ["json.dumps"],
                    "lower_level_dependencies": ["普通 Python 值"],
                    "learner_file": learner_file,
                    "question_ids": reimplementation_ids,
                    "forbidden_imports": ["json"],
                }
            },
        }
        if official_bridge is not None:
            lab["official_bridge"] = official_bridge
        labs.append(lab)

    return {
        "schema_version": 2,
        "course": {
            "id": "timeout-course",
            "title": "JSON 转换练习课程",
            "description": "通过具体 JSON 输入和输出验证课程契约。",
            "language": "zh-CN",
            "python_requires": ">=3.13,<3.14",
            "size": "small",
            "dependencies": [],
            "capstone": "一个可确定复现的 JSON 转换小项目",
            "audience": {
                "level": "basic-python",
                "assumes": ["变量", "函数", "类", "import 语句"],
                "does_not_assume": ["JSON 内部实现", "分布式系统"],
                "lab_minutes": {"min": 30, "max": 45},
            },
        },
        "target": {
            "name": "json",
            "kind": "stdlib",
            "version": "Python 3.13",
            "breadth": "focused",
            "track": "JSON 转换与错误边界",
            "import_roots": ["json"],
            "official_sources": [
                {
                    "id": "python-docs",
                    "title": "Python JSON documentation",
                    "url": "https://docs.python.org/3.13/library/json.html",
                    "kind": "documentation",
                    "version": "3.13",
                }
            ],
        },
        "research": {
            "status": "complete",
            "version_basis": "Python 3.13",
            "notes": ["所有 JSON 示例均在离线 CPU 环境确定性运行。"],
        },
        "foundation": {
            "id": "lab00",
            "title": "Lab 00: JSON 输入与输出基础",
            "lesson": _lesson("lab00"),
            "quiz": _quiz("lab00", first_position=0),
        },
        "labs": labs,
    }


def _operational_contract(kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "forms": ["json.loads(text)", "json.dumps(value)"],
        "inputs": [
            {
                "name": "value",
                "meaning": "跨越 API 边界的 JSON 文本或 Python 值输入。",
                "form": "str | JSON-compatible Python value",
                "example": '{"ready": true}',
                "constraints": ["该值必须满足文档声明的 JSON 映射规则。"],
            }
        ],
        "outputs": [
            {
                "name": "result",
                "meaning": "转换后得到的 Python 值或 JSON 文本输出。",
                "form": "JSON-compatible Python value | str",
                "example": '{"ready": true}',
            }
        ],
        "effects": ["操作不会修改调用者拥有的输入。"],
        "failure_modes": [
            {
                "condition": "输入违反所选 JSON 操作的接口约定。",
                "observable": "API 边界抛出文档声明的异常。",
                "recovery": "修正或规范化输入后重新调用。",
            }
        ],
    }


def make_assessed_spec() -> dict[str, object]:
    """Return the complete assessed-mode contract fixture used by RED tests."""
    spec = deepcopy(make_spec())
    lab00_concept_id = "lab00.c-mechanism"
    spec["course"]["audience"] = {  # type: ignore[index]
        "level": "assessed",
        "prerequisite_profile": {
            "assessment": "learner-self-report",
            "capabilities": [
                {
                    "id": "python-functions",
                    "kind": "python",
                    "subject": "Python 函数",
                    "title": "定义并调用 Python 函数",
                    "status": "known",
                    "decision": "assume",
                    "basis": "explicit-prerequisite",
                    "source_ids": ["python-docs"],
                    "first_used_in": "lab01",
                    "foundation_concept_ids": [],
                },
                {
                    "id": "json-data-model",
                    "kind": "library",
                    "subject": "JSON 数据模型",
                    "title": "把 JSON 值映射为 Python 值",
                    "status": "partial",
                    "decision": "foundation",
                    "basis": "selected-route-usage",
                    "source_ids": ["python-docs"],
                    "first_used_in": "lab01",
                    "foundation_concept_ids": [lab00_concept_id],
                },
                {
                    "id": "domain-boundary",
                    "kind": "domain",
                    "subject": "序列化边界",
                    "title": "识别序列化输入与输出边界",
                    "status": "missing",
                    "decision": "foundation",
                    "basis": "selected-route-usage",
                    "source_ids": ["python-docs"],
                    "first_used_in": "lab02",
                    "foundation_concept_ids": [lab00_concept_id],
                },
                {
                    "id": "json-errors",
                    "kind": "library",
                    "subject": "JSON 解析失败",
                    "title": "诊断格式错误的 JSON 输入",
                    "status": "unsure",
                    "decision": "foundation",
                    "basis": "explicit-prerequisite",
                    "source_ids": ["python-docs"],
                    "first_used_in": "lab03",
                    "foundation_concept_ids": [lab00_concept_id],
                },
            ],
        },
    }

    foundation = spec["foundation"]  # type: ignore[index]
    foundation_lesson = foundation["lesson"]  # type: ignore[index]
    json_shape = deepcopy(foundation_lesson["concepts"][0])
    json_shape.update(
        {
            "id": "lab00.c-json-shape",
            "name": "JSON 值的 Python 形态",
            "definition": "JSON 值只会映射到一组明确的 Python 值形态。",
        }
    )
    foundation_lesson["concepts"].append(json_shape)
    foundation["study_minutes"] = {  # type: ignore[index]
        "tier": "foundation",
        "min": 45,
        "max": 60,
        "reason": "学习者自评发现本路线会用到的 JSON 前置知识缺口。",
    }

    operational_kinds = iter(
        (
            "api",
            "data-model",
            "mechanism",
            "formula",
            "lifecycle",
            "data-model",
            "api",
        )
    )
    sections = [foundation, *spec["labs"]]  # type: ignore[index]
    for section in sections:
        lesson = section["lesson"]
        concept_ids = [concept["id"] for concept in lesson["concepts"]]
        for concept in lesson["concepts"]:
            concept["operational_contract"] = _operational_contract(
                next(operational_kinds)
            )

        runnable = next(
            example for example in lesson["examples"] if example["kind"] == "runnable"
        )
        runnable["concept_ids"] = list(concept_ids)
        runnable["trace"] = [
            {
                "id": f"{section['id']}.t-input",
                "concept_ids": [concept_ids[0]],
                "input_state": 'JSON 文本输入：text = \'{"ready": true}\'',
                "operation": "把具体输入传入声明的 JSON 转换边界。",
                "output_state": "转换操作收到一段已验证的 JSON 文本。",
                "explanation": "这一步明确输入形式以及调用者对输入的所有权。",
            },
            {
                "id": f"{section['id']}.t-result",
                "concept_ids": [concept_ids[-1]],
                "input_state": "经过验证的 JSON 文本已经可以解析。",
                "operation": "调用 json.loads(text) 解析 JSON 文本。",
                "output_state": "Python 字典输出：result = {'ready': True}",
                "explanation": "这一步明确解析后的可观察 Python 字典输出。",
            },
        ]

        diagnostic = next(
            example
            for example in lesson["examples"]
            if example["kind"] == "diagnostic"
        )
        diagnostic["concept_ids"] = list(concept_ids)
        for quiz in section["quiz"]:
            quiz["concept_ids"] = list(concept_ids)

    for index, lab in enumerate(spec["labs"]):  # type: ignore[index]
        if index < 2:
            lab["study_minutes"] = {"tier": "standard", "min": 30, "max": 45}
        else:
            lab["study_minutes"] = {
                "tier": "extended",
                "min": 45,
                "max": 60,
                "reason": "最终 Lab 同时组合 JSON 转换、错误诊断和官方接口替换。",
            }

    return spec
