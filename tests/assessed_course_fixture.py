"""Assessed-only cumulative JSON course content for the release fixture.

The generic timeout fixture intentionally lives in ``course_v2_fixture.py``.
This module owns the richer assessed coding tasks, lesson surfaces, and tests so
that strengthening release coverage cannot change the legacy fixture contract.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


def _route_contract(
    kind: str,
    *,
    forms: list[str],
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, str]],
    effects: list[str],
    failure_modes: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "forms": forms,
        "inputs": inputs,
        "outputs": outputs,
        "effects": effects,
        "failure_modes": failure_modes,
    }


def _json_shape_concept() -> dict[str, Any]:
    """Teach the selected route's JSON value model as its own foundation layer."""

    return {
        "id": "lab00.c-json-shape",
        "name": "JSON 值与 Python 值的递归映射",
        "definition": (
            "JSON 的 object、array、string、number、true、false 和 null 会按固定规则"
            "递归变成 Python 的 dict、list、str、int/float、True、False 和 None。"
        ),
        "purpose": (
            "在编写 ready 序列化与解析函数前，先明确每一类 JSON 值在 Python 中的"
            "对应形态，避免把 JSON 文本、解析后的容器和其中的标量混为一谈。"
        ),
        "mechanism": [
            "object 递归映射为 dict；每个对象键仍是 str，成员值继续按同一规则映射。",
            "array 递归映射为 list，并保持元素顺序；string 映射为 str。",
            "number 映射为 int 或 float，具体取决于文本是否需要小数表示。",
            "true 与 false 映射为 Python 的 True 与 False；null 映射为 None。",
        ],
        "mental_model": (
            "把 JSON 看成一棵有七类节点的值树：容器节点递归包含子节点，标量节点"
            "在边界处换成对应的 Python 类型。"
        ),
        "design_reasons": [
            "先固定数据模型，后续 Lab 才能分别讨论手写转换、官方 API 和业务形状校验。"
        ],
        "benefits": [
            "看到任意嵌套值时，可以逐层预测 json.loads 的 Python 结果和 json.dumps 的 JSON 表达。"
        ],
        "tradeoffs": [
            "反向序列化不是一一可逆：tuple 会编码成 JSON array，往返解析后得到 list。"
        ],
        "invariants": [
            "容器的嵌套关系与数组顺序保持不变，true/false/null 不会变成普通字符串。"
        ],
        "boundaries": [
            "顶层 JSON 值可以是 object、array 或标量，不保证解析结果一定是 dict。",
            "JSON 对象键必须是字符串；Python 的 set、bytes 和自定义对象默认会让 json.dumps 抛出 TypeError。",
        ],
        "pitfalls": [
            "JSON 文本写 true、false、null；Python 值写 True、False、None，大小写与含义都不能混用。",
            "合法 JSON 数字可能映射为 int 或 float；不要只凭显示形式假定具体 Python 类型。",
        ],
        "source_claims": [
            {
                "source_id": "python-docs",
                "claim": "Python json 文档定义了 JSON 值与 Python 值的双向转换表。",
                "status": "documented",
            }
        ],
        "operational_contract": _route_contract(
            "data-model",
            forms=[
                "JSON object -> Python dict",
                "JSON array -> Python list",
                "JSON string -> Python str",
                "JSON number -> Python int | float",
                "JSON true / false -> Python True / False",
                "JSON null -> Python None",
            ],
            inputs=[
                {
                    "name": "text",
                    "meaning": "包含任意合法顶层 JSON 值的文本。",
                    "form": "str containing a JSON value",
                    "example": "[1, true, null]",
                    "constraints": [
                        "对象键必须是字符串；顶层值可以是对象、数组或标量。"
                    ],
                }
            ],
            outputs=[
                {
                    "name": "value",
                    "meaning": "按 JSON 数据模型递归映射得到的 Python 值。",
                    "form": "dict | list | str | int | float | bool | None",
                    "example": "[1, True, None]",
                }
            ],
            effects=["转换会新建对应的 Python 值树，不修改调用者持有的 JSON 文本。"],
            failure_modes=[
                {
                    "condition": "输入文本不满足 JSON 语法，因而不存在可递归映射的 JSON 值。",
                    "observable": "json.loads 在建立 Python 值树前抛出 JSONDecodeError。",
                    "recovery": "修正引号、逗号或字面量拼写后重新解析。",
                }
            ],
        ),
    }


def _assessed_question(
    *,
    question_id: str,
    kind: str,
    title: str,
    file: str,
    symbol: str,
    prompt: str,
    concept_ids: list[str],
    outcome_ids: list[str],
    example: dict[str, str],
    public_code: str,
    hidden_code: str,
) -> dict[str, Any]:
    public_selector = f"test_{symbol}"
    hidden_selector = f"test_{symbol}_hidden"
    return {
        "id": question_id,
        "kind": kind,
        "title": title,
        "file": file,
        "symbol": symbol,
        "points": 1,
        "timeout_seconds": 30,
        "prompt": prompt,
        "concept_ids": concept_ids,
        "outcome_ids": outcome_ids,
        "example": example,
        "public_test": {
            "path": f"{public_selector}.py",
            "selector": public_selector,
            "code": public_code,
        },
        "hidden_test": {
            "path": f"{hidden_selector}.py",
            "selector": hidden_selector,
            "code": hidden_code,
        },
    }


def _rewrite_quiz(
    quiz: list[dict[str, Any]],
    *,
    trace_prompt: str,
    trace_correct: str,
    trace_feedback: str,
    trace_distractors: list[tuple[str, str]],
    trace_explanation: str,
    diagnostic_prompt: str,
    diagnostic_correct: str,
    diagnostic_feedback: str,
    diagnostic_distractors: list[tuple[str, str]],
    diagnostic_explanation: str,
) -> None:
    replacements = {
        "execution_trace": (
            trace_prompt,
            trace_correct,
            trace_feedback,
            trace_distractors,
            trace_explanation,
        ),
        "diagnostic": (
            diagnostic_prompt,
            diagnostic_correct,
            diagnostic_feedback,
            diagnostic_distractors,
            diagnostic_explanation,
        ),
    }
    for item in quiz:
        prompt, correct, feedback, distractors, explanation = replacements[item["kind"]]
        item["prompt"] = prompt
        item["explanation"] = explanation
        wrong = iter(distractors)
        for choice in item["choices"]:
            if choice["id"] == item["answer_id"]:
                choice.update({"text": correct, "feedback": feedback})
            else:
                text, wrong_feedback = next(wrong)
                choice.update({"text": text, "feedback": wrong_feedback})


def _diagnostic_quiz_item(
    *,
    quiz_id: str,
    prompt: str,
    answer: str,
    answer_feedback: str,
    distractors: list[tuple[str, str]],
    explanation: str,
    concept_ids: list[str],
    outcome_ids: list[str],
    answer_position: int,
) -> dict[str, Any]:
    options = list(distractors)
    options.insert(answer_position, (answer, answer_feedback))
    choices = [
        {"id": choice_id, "text": text, "feedback": feedback}
        for choice_id, (text, feedback) in zip(
            ("a", "b", "c"), options, strict=True
        )
    ]
    return {
        "id": quiz_id,
        "kind": "diagnostic",
        "prompt": prompt,
        "choices": choices,
        "answer_id": choices[answer_position]["id"],
        "explanation": explanation,
        "concept_ids": concept_ids,
        "outcome_ids": outcome_ids,
    }


def apply_assessed_semantic_route(spec: dict[str, object]) -> None:
    """Replace the generic timeout fixture tasks with one cumulative JSON route."""

    lab01, lab02, lab03 = spec["labs"]  # type: ignore[index]

    # Lab 01: expose the serialization mechanism without the target library.
    lab01_answer_starter = (
        "def answer_1(ready: bool) -> str:\n"
        "    raise NotImplementedError\n"
    )
    lab01_answer_reference = (
        "def answer_1(ready: bool) -> str:\n"
        "    if type(ready) is not bool:\n"
        "        raise TypeError('ready must be bool')\n"
        "    return '{\"ready\":true}' if ready else '{\"ready\":false}'\n"
    )
    lab01["files"] = [
        {
            "path": "lab01/answer.py",
            "starter": lab01_answer_starter,
            "reference": lab01_answer_reference,
        }
    ]
    lab01["questions"] = [
        _assessed_question(
            question_id="lab01.q1",
            kind="reimplementation",
            title="手写 ready 布尔值的紧凑 JSON 序列化",
            file="lab01/answer.py",
            symbol="answer_1",
            prompt=(
                "实现 answer_1(ready: bool) -> str。只接受真正的 bool；"
                "不导入 json，分别返回紧凑文本 {\"ready\":true} 或 "
                "{\"ready\":false}，其他输入抛出 TypeError。"
            ),
            concept_ids=["lab01.c-mechanism"],
            outcome_ids=["lab01.o-trace", "lab01.o-diagnose"],
            example={
                "input": "answer_1(True)",
                "output": "{\"ready\":true}",
                "explanation": "布尔值 True 被手写为 JSON 的 true，并省略多余空格。",
            },
            public_code=(
                "import pytest\n"
                "from lab01.answer import answer_1\n\n"
                "def test_answer_1():\n"
                "    assert answer_1(True) == '{\"ready\":true}'\n"
                "    with pytest.raises(TypeError, match='ready'):\n"
                "        answer_1(1)\n"
            ),
            hidden_code=(
                "import pytest\n"
                "from lab01.answer import answer_1\n\n"
                "def test_answer_1_hidden():\n"
                "    assert answer_1(False) == '{\"ready\":false}'\n"
                "    with pytest.raises(TypeError, match='ready'):\n"
                "        answer_1('true')\n"
            ),
        )
    ]
    lab01["module_cycle"] = {
        "reimplementation": {
            "module_id": "lab01.mini-module",
            "title": "不用 json 手写 ready 布尔值的紧凑序列化",
            "target_symbols": ["json.dumps"],
            "lower_level_dependencies": ["bool 类型判断", "字符串选择"],
            "learner_file": "lab01/answer.py",
            "question_ids": ["lab01.q1"],
            "forbidden_imports": ["json"],
        }
    }

    # Lab 02: replace that serializer with json.dumps, then invert the direction.
    lab02_answer_starter = (
        "import json\n\n"
        "def answer_2(ready: bool) -> str:\n"
        "    raise NotImplementedError\n"
    )
    lab02_answer_reference = (
        "import json\n\n"
        "def answer_2(ready: bool) -> str:\n"
        "    if type(ready) is not bool:\n"
        "        raise TypeError('ready must be bool')\n"
        "    return json.dumps({'ready': ready}, separators=(',', ':'))\n"
    )
    lab02_mini_starter = (
        "def mini_2(text: str) -> dict[str, bool]:\n"
        "    raise NotImplementedError\n"
    )
    lab02_mini_reference = (
        "def mini_2(text: str) -> dict[str, bool]:\n"
        "    if type(text) is not str:\n"
        "        raise TypeError('text must be str')\n"
        "    if text == '{\"ready\":true}':\n"
        "        return {'ready': True}\n"
        "    if text == '{\"ready\":false}':\n"
        "        return {'ready': False}\n"
        "    raise ValueError('unsupported ready JSON text')\n"
    )
    lab02["files"] = [
        {
            "path": "lab02/answer.py",
            "starter": lab02_answer_starter,
            "reference": lab02_answer_reference,
        },
        {
            "path": "lab02/mini.py",
            "starter": lab02_mini_starter,
            "reference": lab02_mini_reference,
        },
    ]
    lab02["questions"] = [
        _assessed_question(
            question_id="lab02.q1",
            kind="official_bridge",
            title="用 json.dumps 替换手写紧凑序列化",
            file="lab02/answer.py",
            symbol="answer_2",
            prompt=(
                "实现 answer_2(ready: bool) -> str：保持 Lab 01 的 bool 边界，"
                "并实际调用 json.dumps(..., separators=(\",\", \":\")) 生成紧凑 JSON。"
            ),
            concept_ids=["lab02.c-official"],
            outcome_ids=["lab02.o-trace", "lab02.o-diagnose"],
            example={
                "input": "answer_2(False)",
                "output": "{\"ready\":false}",
                "explanation": "官方序列化接口产生与 Lab 01 相同的紧凑文本。",
            },
            public_code=(
                "import lab02.answer as answer_module\n"
                "from lab02.answer import answer_2\n\n"
                "def test_answer_2(monkeypatch):\n"
                "    calls = []\n"
                "    def fake_dumps(value, *, separators):\n"
                "        calls.append((value, separators))\n"
                "        return f'delegated-{len(calls)}'\n"
                "    monkeypatch.setattr(answer_module.json, 'dumps', fake_dumps)\n"
                "    assert answer_2(True) == 'delegated-1'\n"
                "    assert answer_2(False) == 'delegated-2'\n"
                "    assert calls == [\n"
                "        ({'ready': True}, (',', ':')),\n"
                "        ({'ready': False}, (',', ':')),\n"
                "    ]\n"
            ),
            hidden_code=(
                "import pytest\n"
                "from lab02.answer import answer_2\n\n"
                "def test_answer_2_hidden():\n"
                "    assert answer_2(True) == '{\"ready\":true}'\n"
                "    assert answer_2(False) == '{\"ready\":false}'\n"
                "    with pytest.raises(TypeError, match='ready'):\n"
                "        answer_2(1)\n"
            ),
        ),
        _assessed_question(
            question_id="lab02.q2",
            kind="reimplementation",
            title="手写紧凑 ready JSON 的窄解析器",
            file="lab02/mini.py",
            symbol="mini_2",
            prompt=(
                "实现 mini_2(text: str) -> dict[str, bool]。不用 json，只接受 "
                "{\"ready\":true} 与 {\"ready\":false} 两个已声明文本；"
                "非字符串抛出 TypeError，其他文本抛出 ValueError。"
            ),
            concept_ids=["lab02.c-mechanism"],
            outcome_ids=["lab02.o-trace", "lab02.o-diagnose"],
            example={
                "input": "mini_2('{\"ready\":true}')",
                "output": "{'ready': True}",
                "explanation": "窄解析器只把课程声明的紧凑文本映射回字典。",
            },
            public_code=(
                "import pytest\n"
                "from lab02.mini import mini_2\n\n"
                "def test_mini_2():\n"
                "    assert mini_2('{\"ready\":true}') == {'ready': True}\n"
                "    with pytest.raises(ValueError, match='unsupported'):\n"
                "        mini_2('{\"ready\": true}')\n"
                "    assert mini_2('{\"ready\":false}') == {'ready': False}\n"
            ),
            hidden_code=(
                "import pytest\n"
                "from lab02.mini import mini_2\n\n"
                "def test_mini_2_hidden():\n"
                "    assert mini_2('{\"ready\":false}') == {'ready': False}\n"
                "    with pytest.raises(TypeError, match='text'):\n"
                "        mini_2(b'{\"ready\":true}')\n"
                "    assert mini_2('{\"ready\":true}') == {'ready': True}\n"
            ),
        ),
    ]
    lab02["module_cycle"] = {
        "reimplementation": {
            "module_id": "lab02.mini-module",
            "title": "不用 json 手写紧凑 ready JSON 的窄解析器",
            "target_symbols": ["json.loads"],
            "lower_level_dependencies": ["字符串精确比较", "字典构造"],
            "learner_file": "lab02/mini.py",
            "question_ids": ["lab02.q2"],
            "forbidden_imports": ["json"],
        }
    }
    lab02["official_bridge"] = {
        "from_lab": "lab01",
        "mini_module": "lab01.answer",
        "official_symbols": ["json.dumps"],
        "required_imports": ["json"],
        "question_id": "lab02.q1",
        "observables": [
            {"id": "compact-text", "description": "紧凑 JSON 返回文本。"},
            {"id": "bool-boundary", "description": "非 bool 输入触发 TypeError。"},
        ],
        "comparison_cases": [
            {
                "input": "answer_2(True)",
                "expected": "{\"ready\":true}",
                "observable_ids": ["compact-text"],
            },
            {
                "input": "answer_2(False)",
                "expected": "{\"ready\":false}",
                "observable_ids": ["compact-text"],
            },
            {
                "input": "answer_2(1)",
                "expected": "TypeError",
                "observable_ids": ["bool-boundary"],
            },
        ],
    }

    # Lab 03: replace the narrow parser, then integrate the complete pipeline.
    lab03_answer_starter = (
        "import json\n\n"
        "def answer_3(text: str) -> object:\n"
        "    raise NotImplementedError\n"
    )
    lab03_answer_reference = (
        "import json\n\n"
        "def answer_3(text: str) -> object:\n"
        "    return json.loads(text)\n"
    )
    lab03_mini_starter = (
        "def mini_3(value: dict[str, bool]) -> str:\n"
        "    raise NotImplementedError\n"
    )
    lab03_mini_reference = (
        "def mini_3(value: dict[str, bool]) -> str:\n"
        "    if type(value) is not dict or set(value) != {'ready'}:\n"
        "        raise ValueError('value must contain only ready')\n"
        "    if type(value['ready']) is not bool:\n"
        "        raise ValueError('ready must be bool')\n"
        "    return '{\"ready\":true}' if value['ready'] else '{\"ready\":false}'\n"
    )
    lab03_project_starter = (
        "import json\n\n"
        "def normalize_ready_json(text: str, invert: bool = False) -> str:\n"
        "    raise NotImplementedError\n"
    )
    lab03_project_reference = (
        "import json\n\n"
        "def normalize_ready_json(text: str, invert: bool = False) -> str:\n"
        "    if type(text) is not str:\n"
        "        raise TypeError('text must be str')\n"
        "    if type(invert) is not bool:\n"
        "        raise TypeError('invert must be bool')\n"
        "    value = json.loads(text)\n"
        "    if type(value) is not dict or set(value) != {'ready'}:\n"
        "        raise ValueError('payload must contain only ready')\n"
        "    if type(value['ready']) is not bool:\n"
        "        raise ValueError('ready must be bool')\n"
        "    ready = not value['ready'] if invert else value['ready']\n"
        "    return json.dumps({'ready': ready}, separators=(',', ':'))\n"
    )
    lab03["files"] = [
        {
            "path": "lab03/answer.py",
            "starter": lab03_answer_starter,
            "reference": lab03_answer_reference,
        },
        {
            "path": "lab03/mini.py",
            "starter": lab03_mini_starter,
            "reference": lab03_mini_reference,
        },
        {
            "path": "lab03/project.py",
            "starter": lab03_project_starter,
            "reference": lab03_project_reference,
        },
    ]
    lab03["questions"] = [
        _assessed_question(
            question_id="lab03.q1",
            kind="official_bridge",
            title="用 json.loads 替换手写窄解析器",
            file="lab03/answer.py",
            symbol="answer_3",
            prompt=(
                "实现 answer_3(text: str) -> object，实际调用 json.loads(text)，"
                "并保留合法输入的返回值与格式错误时的 JSONDecodeError。"
            ),
            concept_ids=["lab03.c-official"],
            outcome_ids=["lab03.o-trace", "lab03.o-diagnose"],
            example={
                "input": "answer_3('{\"ready\":false}')",
                "output": "{'ready': False}",
                "explanation": "官方解析接口把 JSON 的 false 转换为 Python 的 False。",
            },
            public_code=(
                "import lab03.answer as answer_module\n"
                "from lab03.answer import answer_3\n\n"
                "def test_answer_3(monkeypatch):\n"
                "    calls = []\n"
                "    def fake_loads(text):\n"
                "        calls.append(text)\n"
                "        return {'seen': text}\n"
                "    monkeypatch.setattr(answer_module.json, 'loads', fake_loads)\n"
                "    assert answer_3('{\"ready\":true}') == {'seen': '{\"ready\":true}'}\n"
                "    assert answer_3('{\"ready\":false}') == {'seen': '{\"ready\":false}'}\n"
                "    assert calls == ['{\"ready\":true}', '{\"ready\":false}']\n"
            ),
            hidden_code=(
                "import json\n"
                "import pytest\n"
                "from lab03.answer import answer_3\n\n"
                "def test_answer_3_hidden():\n"
                "    assert answer_3('{\"ready\":true}') == {'ready': True}\n"
                "    assert answer_3('{\"ready\":false}') == {'ready': False}\n"
                "    with pytest.raises(json.JSONDecodeError):\n"
                "        answer_3('{\"ready\":true,}')\n"
            ),
        ),
        _assessed_question(
            question_id="lab03.q2",
            kind="reimplementation",
            title="手写精确 ready 字典的紧凑序列化",
            file="lab03/mini.py",
            symbol="mini_3",
            prompt=(
                "实现 mini_3(value: dict[str, bool]) -> str。不能导入 json；输入必须"
                "恰好包含 ready 字段，且值必须是 bool，否则抛出 ValueError。"
            ),
            concept_ids=["lab03.c-mechanism"],
            outcome_ids=["lab03.o-trace", "lab03.o-diagnose"],
            example={
                "input": "mini_3({'ready': True})",
                "output": "{\"ready\":true}",
                "explanation": "精确字典边界通过后，教学实现返回紧凑 JSON 文本。",
            },
            public_code=(
                "import pytest\n"
                "from lab03.mini import mini_3\n\n"
                "def test_mini_3():\n"
                "    assert mini_3({'ready': True}) == '{\"ready\":true}'\n"
                "    with pytest.raises(ValueError, match='only ready'):\n"
                "        mini_3({'ready': True, 'extra': 1})\n"
            ),
            hidden_code=(
                "import pytest\n"
                "from lab03.mini import mini_3\n\n"
                "def test_mini_3_hidden():\n"
                "    assert mini_3({'ready': False}) == '{\"ready\":false}'\n"
                "    with pytest.raises(ValueError, match='bool'):\n"
                "        mini_3({'ready': 1})\n"
            ),
        ),
        _assessed_question(
            question_id="lab03.q3",
            kind="integration",
            title="组合解析、精确校验、分支转换与紧凑序列化",
            file="lab03/project.py",
            symbol="normalize_ready_json",
            prompt=(
                "实现 normalize_ready_json(text: str, invert: bool = False) -> str。"
                "用 json.loads 解析；载荷必须恰好包含 ready 字段，且值必须是 bool；"
                "根据 invert 选择是否反转；最后用 json.dumps 和紧凑 separators 输出。"
            ),
            concept_ids=["lab03.c-official", "lab03.c-mechanism"],
            outcome_ids=["lab03.o-trace", "lab03.o-diagnose"],
            example={
                "input": "normalize_ready_json('{\"ready\":false}', invert=True)",
                "output": "{\"ready\":true}",
                "explanation": "解析后的 False 经 invert 分支变为 True，再被紧凑序列化。",
            },
            public_code=(
                "import json\n"
                "import pytest\n"
                "import lab03.project as project_module\n"
                "from lab03.project import normalize_ready_json\n\n"
                "def test_normalize_ready_json(monkeypatch):\n"
                "    real_loads = project_module.json.loads\n"
                "    real_dumps = project_module.json.dumps\n"
                "    loads_calls = []\n"
                "    dumps_calls = []\n"
                "    def tracked_loads(text):\n"
                "        loads_calls.append(text)\n"
                "        return real_loads(text)\n"
                "    def tracked_dumps(value, *, separators):\n"
                "        dumps_calls.append((value, separators))\n"
                "        return real_dumps(value, separators=separators)\n"
                "    monkeypatch.setattr(project_module.json, 'loads', tracked_loads)\n"
                "    monkeypatch.setattr(project_module.json, 'dumps', tracked_dumps)\n"
                "    assert normalize_ready_json(' { \"ready\" : true } ') == '{\"ready\":true}'\n"
                "    assert normalize_ready_json('{\"ready\":false}', invert=True) == '{\"ready\":true}'\n"
                "    with pytest.raises(TypeError, match='text'):\n"
                "        normalize_ready_json(b'{\"ready\":false}')\n"
                "    assert normalize_ready_json('{\"ready\":false}') == '{\"ready\":false}'\n"
                "    with pytest.raises(json.JSONDecodeError):\n"
                "        normalize_ready_json('{\"ready\":true,}')\n"
                "    assert normalize_ready_json('{\"ready\":true}') == '{\"ready\":true}'\n"
                "    with pytest.raises(ValueError, match='only ready'):\n"
                "        normalize_ready_json('{\"ready\":true,\"extra\":0}')\n"
                "    assert normalize_ready_json('{\"ready\":true}') == '{\"ready\":true}'\n"
                "    assert loads_calls == [\n"
                "        ' { \"ready\" : true } ',\n"
                "        '{\"ready\":false}',\n"
                "        '{\"ready\":false}',\n"
                "        '{\"ready\":true,}',\n"
                "        '{\"ready\":true}',\n"
                "        '{\"ready\":true,\"extra\":0}',\n"
                "        '{\"ready\":true}',\n"
                "    ]\n"
                "    assert dumps_calls == [\n"
                "        ({'ready': True}, (',', ':')),\n"
                "        ({'ready': True}, (',', ':')),\n"
                "        ({'ready': False}, (',', ':')),\n"
                "        ({'ready': True}, (',', ':')),\n"
                "        ({'ready': True}, (',', ':')),\n"
                "    ]\n"
            ),
            hidden_code=(
                "import pytest\n"
                "from lab03.project import normalize_ready_json\n\n"
                "def test_normalize_ready_json_hidden():\n"
                "    assert normalize_ready_json('{\"ready\":true}', invert=True) == '{\"ready\":false}'\n"
                "    assert normalize_ready_json('{\"ready\":false}', invert=False) == '{\"ready\":false}'\n"
                "    with pytest.raises(ValueError, match='bool'):\n"
                "        normalize_ready_json('{\"ready\":1}')\n"
                "    assert normalize_ready_json('{\"ready\":false}') == '{\"ready\":false}'\n"
                "    with pytest.raises(TypeError, match='invert'):\n"
                "        normalize_ready_json('{\"ready\":true}', invert=1)\n"
                "    assert normalize_ready_json('{\"ready\":true}', invert=True) == '{\"ready\":false}'\n"
            ),
        ),
    ]
    lab03["module_cycle"] = {
        "reimplementation": {
            "module_id": "lab03.mini-module",
            "title": "不用 json 手写精确 ready 字典的紧凑序列化",
            "target_symbols": ["json.dumps"],
            "lower_level_dependencies": ["字典形状校验", "bool 类型判断", "字符串选择"],
            "learner_file": "lab03/mini.py",
            "question_ids": ["lab03.q2"],
            "forbidden_imports": ["json"],
        }
    }
    lab03["official_bridge"] = {
        "from_lab": "lab02",
        "mini_module": "lab02.mini",
        "official_symbols": ["json.loads"],
        "required_imports": ["json"],
        "question_id": "lab03.q1",
        "observables": [
            {"id": "parsed-value", "description": "解析得到的 Python 值。"},
            {"id": "parse-failure", "description": "格式错误触发 JSONDecodeError。"},
        ],
        "comparison_cases": [
            {
                "input": "answer_3('{\"ready\":true}')",
                "expected": {"ready": True},
                "observable_ids": ["parsed-value"],
            },
            {
                "input": "answer_3('{\"ready\":false}')",
                "expected": {"ready": False},
                "observable_ids": ["parsed-value"],
            },
            {
                "input": "answer_3('{\"ready\":true,}')",
                "expected": "JSONDecodeError",
                "observable_ids": ["parse-failure"],
            },
        ],
    }

    # Keep every learner-facing surface aligned to the executable route above.
    lab01_lesson = lab01["lesson"]
    lab01_lesson["problem"] = {
        "context": "累积项目先把一个 ready 布尔值变成可传输的紧凑 JSON 文本。",
        "naive_approach": "直接把 Python 的 True 或 False 拼进字符串。",
        "failure": "Python 布尔拼写与 JSON 不同，非 bool 输入还会悄悄越过边界。",
    }
    lab01_lesson["outcomes"] = [
        {"id": "lab01.o-trace", "text": "追踪 bool 输入如何变成紧凑 ready JSON 文本。"},
        {"id": "lab01.o-diagnose", "text": "用 TypeError 阻止整数或字符串冒充 bool。"},
    ]
    lab01_concept = lab01_lesson["concepts"][0]
    lab01_concept.update(
        {
            "name": "手写紧凑 ready JSON 序列化",
            "definition": "教学函数把真正的 bool 映射成无多余空格的 ready JSON 文本。",
            "purpose": (
                "先看清序列化的输入、分支和输出，再在下一 Lab 用官方接口替换；"
                "解析 JSON 文本并得到 Python 字典属于后续的反向路线。"
            ),
            "mechanism": [
                "确认 ready 的实际类型恰好是 bool。",
                "True 选择 JSON 记号 true，False 选择 false。",
                "把记号放进固定的 ready 对象外壳并返回紧凑文本。",
            ],
            "mental_model": "把序列化看成从 Python 值到 JSON 文本的单向边界。",
            "design_reasons": ["窄输入让每个分支和失败都能被测试直接观察。"],
            "benefits": ["不依赖官方库也能看见 JSON 布尔拼写与紧凑格式。"],
            "tradeoffs": ["教学实现只支持一个 ready 布尔字段。"],
            "invariants": ["合法输入只会得到两种紧凑文本之一。"],
            "boundaries": ["ready 只接受 bool，不把 0、1 或字符串当成布尔值。"],
            "pitfalls": ["Python 使用 True/False，JSON 文本使用 true/false。"],
            "operational_contract": _route_contract(
                "mechanism",
                forms=["answer_1(ready: bool) -> str"],
                inputs=[
                    {
                        "name": "ready",
                        "meaning": "要序列化的 Python 布尔值。",
                        "form": "bool",
                        "example": "布尔输入示例：True",
                        "constraints": ["实际类型必须恰好是 bool。"],
                    }
                ],
                outputs=[
                    {
                        "name": "text",
                        "meaning": "只包含 ready 字段的紧凑 JSON 文本。",
                        "form": "str",
                        "example": "{\"ready\":true}",
                    }
                ],
                effects=["不修改调用者输入，也不导入 json。"],
                failure_modes=[
                    {
                        "condition": "ready 的实际类型不是 bool。",
                        "observable": "answer_1 抛出 TypeError。",
                        "recovery": "传入 True 或 False 后重新调用。",
                    }
                ],
            ),
        }
    )
    lab01_lesson["examples"] = [
        {
            "id": "lab01.e-runnable",
            "title": "让两个 bool 分支都走过序列化边界",
            "kind": "runnable",
            "path": "examples/01_happy_path.py",
            "code": lab01_answer_reference + "\nprint(answer_1(True))\nprint(answer_1(False))\n",
            "command": "python examples/01_happy_path.py",
            "expected_output": "{\"ready\":true}\n{\"ready\":false}",
            "explanation": "同一输入边界产生两种可观察的紧凑 JSON 文本。",
            "concept_ids": ["lab01.c-mechanism"],
            "outcome_ids": ["lab01.o-trace"],
            "trace": [
                {
                    "id": "lab01.t-input",
                    "concept_ids": ["lab01.c-mechanism"],
                    "input_state": "调用 answer_1(True)，输入是实际 bool。",
                    "operation": "先执行严格类型检查。",
                    "output_state": "输入通过 bool 边界。",
                    "explanation": "这一步阻止 1 或字符串冒充布尔值。",
                },
                {
                    "id": "lab01.t-select",
                    "concept_ids": ["lab01.c-mechanism"],
                    "input_state": "ready 为 True。",
                    "operation": "选择 JSON 布尔记号 true。",
                    "output_state": "准备好文本片段 true。",
                    "explanation": "这里显式区分 Python 与 JSON 的布尔拼写。",
                },
                {
                    "id": "lab01.t-output",
                    "concept_ids": ["lab01.c-mechanism"],
                    "input_state": "已有 JSON 布尔记号 true。",
                    "operation": "把记号放进固定 ready 对象外壳。",
                    "output_state": "返回 {\"ready\":true}。",
                    "explanation": "结果没有多余空格，可以直接比较。",
                },
            ],
        },
        {
            "id": "lab01.e-diagnostic",
            "title": "阻止整数冒充 bool",
            "kind": "diagnostic",
            "wrong_code": "from lab01.answer import answer_1\nanswer_1(1)\n",
            "symptom": "调用抛出 TypeError，而不是返回看似合理的 JSON。",
            "cause": "1 是 int；即使它在条件判断中为真，也不满足严格 bool 边界。",
            "fix_code": (
                "from lab01.answer import answer_1\n"
                "result = answer_1(True)\n"
                "print(result)\n"
            ),
            "explanation": (
                "把输入修正为真正的 bool 后重新调用并打印 recovered observable："
                "{\"ready\":true}。"
            ),
            "concept_ids": ["lab01.c-mechanism"],
            "outcome_ids": ["lab01.o-diagnose"],
        },
    ]
    lab01_lesson["capstone_bridge"] = {
        "input": "一个经过严格类型检查的 ready 布尔值。",
        "output": "紧凑的 ready JSON 文本。",
        "increment": "累积项目现在能手写序列化 true 与 false 两个分支。",
        "next": "下一 Lab 用 json.dumps 替换这段教学实现，并手写相反方向的窄解析器。",
    }
    lab01_lesson["summary"] = [
        "手写过程说明了 bool、JSON 布尔记号与紧凑文本之间的映射。",
        "TypeError 让输入边界可见；下一 Lab 将用 json.dumps 做等价替换。",
    ]
    _rewrite_quiz(
        lab01["quiz"],
        trace_prompt="answer_1(True) 依次经过类型检查和分支选择后返回什么？",
        trace_correct="返回 {\"ready\":true}",
        trace_feedback="正确：True 选择 JSON 的 true，并被放进紧凑 ready 对象。",
        trace_distractors=[
            ("返回 {'ready': True}", "这是 Python 字典，不是函数承诺的 JSON 文本。"),
            ("返回 {\"ready\":True}", "JSON 布尔记号必须是小写 true。"),
        ],
        trace_explanation="沿着 bool 输入、JSON 记号选择与紧凑文本输出逐步追踪。",
        diagnostic_prompt="answer_1(1) 为什么抛出 TypeError，应该怎样修复？",
        diagnostic_correct="把 1 改成真正的 bool，例如 True",
        diagnostic_feedback="正确：课程边界要求实际类型恰好是 bool。",
        diagnostic_distractors=[
            ("把 1 转成字符串 '1'", "字符串仍然不是 bool。"),
            ("删除类型检查", "这会让未声明输入悄悄越过边界。"),
        ],
        diagnostic_explanation="先保留严格边界，再把调用者输入修正为 True 或 False。",
    )

    lab02_lesson = lab02["lesson"]
    lab02_lesson["problem"] = {
        "context": "累积项目要用官方序列化接口替换 Lab 01，并开始学习反向解析。",
        "naive_approach": "只导入 json，却继续手写返回值；或者让窄解析器接受未声明格式。",
        "failure": "前者没有完成官方替换，后者掩盖了教学实现的明确边界。",
    }
    lab02_lesson["outcomes"] = [
        {"id": "lab02.o-trace", "text": "追踪 json.dumps 调用与窄解析器的反向映射。"},
        {"id": "lab02.o-diagnose", "text": "区分 bool 类型失败与未声明 JSON 文本失败。"},
    ]
    lab02_official, lab02_mechanism = lab02_lesson["concepts"]
    lab02_official.update(
        {
            "name": "用 json.dumps 完成等价替换",
            "definition": "官方桥接函数实际调用 json.dumps，把 ready 字典序列化为紧凑文本。",
            "purpose": "用官方接口替换 Lab 01 的手写实现，同时保留相同输入与输出。",
            "mechanism": [
                "先确认 ready 的实际类型是 bool。",
                "构造只含 ready 的 Python 字典。",
                "调用 json.dumps，并传入紧凑 separators。",
            ],
            "mental_model": "官方桥不是导入动作，而是把同一契约委托给 json.dumps。",
            "design_reasons": ["保持 Lab 01 的可观察结果，才能比较教学实现与官方实现。"],
            "benefits": ["官方接口可处理更广泛的 JSON 兼容值。"],
            "tradeoffs": ["为了延续课程边界，包装函数仍只接受 bool。"],
            "invariants": ["True 与 False 的输出和 Lab 01 完全一致。"],
            "boundaries": ["answer_2 仍拒绝非 bool，即使 json.dumps 本身能序列化整数。"],
            "pitfalls": ["只写 import json 不代表已经使用官方接口。"],
            "operational_contract": _route_contract(
                "api",
                forms=["answer_2(ready: bool) -> str", "json.dumps(value, separators=(\",\", \":\"))"],
                inputs=[
                    {
                        "name": "ready",
                        "meaning": "要放进 ready 字典的 Python 布尔值。",
                        "form": "bool",
                        "example": "布尔输入示例：False",
                        "constraints": ["实际类型必须恰好是 bool。"],
                    }
                ],
                outputs=[
                    {
                        "name": "text",
                        "meaning": "json.dumps 返回的紧凑 JSON 文本。",
                        "form": "str",
                        "example": "{\"ready\":false}",
                    }
                ],
                effects=["调用 json.dumps，但不修改 ready 输入。"],
                failure_modes=[
                    {
                        "condition": "ready 的实际类型不是 bool。",
                        "observable": "answer_2 在委托前抛出 TypeError。",
                        "recovery": "传入 True 或 False 后重新调用。",
                    }
                ],
            ),
        }
    )
    lab02_mechanism.update(
        {
            "name": "紧凑 ready JSON 的窄解析器",
            "definition": "mini_2(text: str) 只把两个已声明的紧凑 ready 文本映射回 Python 字典。",
            "purpose": "在使用 json.loads 前，先看清文本识别与 Python 值构造。",
            "mechanism": [
                "确认输入实际类型是 str。",
                "精确比较 true 与 false 两个紧凑文本。",
                "构造对应的 ready 布尔字典；其他文本明确失败。",
            ],
            "mental_model": "窄解析器是一张只有两行的文本到值映射表。",
            "design_reasons": ["显式拒绝未声明文本，让教学边界不会被误认为完整 JSON 语法。"],
            "benefits": ["两个合法分支和失败分支都能直接测试。"],
            "tradeoffs": ["空格、其他字段和其他 JSON 值都不在教学子集中。"],
            "invariants": ["两个合法文本分别得到 True 与 False。"],
            "boundaries": ["只接受两个完全匹配的紧凑字符串。"],
            "pitfalls": ["{\"ready\": true} 是合法 JSON，但不属于这个窄解析器。"],
            "operational_contract": _route_contract(
                "mechanism",
                forms=["mini_2(text: str) -> dict[str, bool]"],
                inputs=[
                    {
                        "name": "text",
                        "meaning": "课程声明的紧凑 ready JSON 文本。",
                        "form": "str",
                        "example": "窄解析输入：{\"ready\":true}",
                        "constraints": ["只能是 true 或 false 两个精确文本之一。"],
                    }
                ],
                outputs=[
                    {
                        "name": "value",
                        "meaning": "只含 ready 布尔字段的 Python 字典。",
                        "form": "dict[str, bool]",
                        "example": "{'ready': True}",
                    }
                ],
                effects=["不导入 json，也不修改输入文本。"],
                failure_modes=[
                    {
                        "condition": "text 的实际类型不是 str。",
                        "observable": "mini_2 在比较文本前抛出 TypeError('text must be str')。",
                        "recovery": "传入 str 类型的两个声明文本之一后重新调用。",
                    },
                    {
                        "condition": (
                            "text 是 str，但不等于 '{\"ready\":true}' 或 "
                            "'{\"ready\":false}'。"
                        ),
                        "observable": (
                            "mini_2 抛出 ValueError('unsupported ready JSON text')。"
                        ),
                        "recovery": (
                            "删除未声明空格或字段，改用两个精确文本之一后重新调用。"
                        ),
                    },
                ],
            ),
        }
    )
    lab02_lesson["examples"] = [
        {
            "id": "lab02.e-runnable",
            "title": "官方序列化后再走窄解析器",
            "kind": "runnable",
            "path": "examples/01_happy_path.py",
            "code": (
                lab02_answer_reference
                + "\n"
                + lab02_mini_reference
                + "\nprint(answer_2(True))\nprint(mini_2(answer_2(False)))\n"
            ),
            "command": "python examples/01_happy_path.py",
            "expected_output": "{\"ready\":true}\n{'ready': False}",
            "explanation": "同一示例先验证 json.dumps 委托，再展示反向教学实现。",
            "concept_ids": ["lab02.c-official", "lab02.c-mechanism"],
            "outcome_ids": ["lab02.o-trace"],
            "trace": [
                {
                    "id": "lab02.t-input",
                    "concept_ids": ["lab02.c-official"],
                    "input_state": "answer_2 收到 ready=False。",
                    "operation": "检查 bool 边界并构造 {'ready': False}。",
                    "output_state": "得到可交给官方接口的字典。",
                    "explanation": "包装函数保留了 Lab 01 的窄输入契约。",
                },
                {
                    "id": "lab02.t-dumps",
                    "concept_ids": ["lab02.c-official"],
                    "input_state": "已有 {'ready': False}。",
                    "operation": "调用 json.dumps 并设置紧凑 separators。",
                    "output_state": "得到 {\"ready\":false}。",
                    "explanation": "实际调用而不是只导入，才完成官方桥接。",
                },
                {
                    "id": "lab02.t-mini",
                    "concept_ids": ["lab02.c-mechanism"],
                    "input_state": "mini_2 收到 {\"ready\":false}。",
                    "operation": "精确匹配文本并构造 False 字典。",
                    "output_state": "返回 {'ready': False}。",
                    "explanation": "反向教学实现只覆盖声明的两个紧凑文本。",
                },
            ],
        },
        {
            "id": "lab02.e-diagnostic",
            "title": "识别合法 JSON 与窄解析器边界的差别",
            "kind": "diagnostic",
            "wrong_code": "from lab02.mini import mini_2\nmini_2('{\"ready\": true}')\n",
            "symptom": "调用抛出 ValueError。",
            "cause": "带空格文本虽然是合法 JSON，却不在 mini_2 声明的两个精确输入中。",
            "fix_code": (
                "from lab02.mini import mini_2\n"
                "result = mini_2('{\"ready\":true}')\n"
                "print(result)\n"
            ),
            "explanation": (
                "改用已声明的紧凑文本后重新调用并打印 recovered observable："
                "{'ready': True}。"
            ),
            "concept_ids": ["lab02.c-mechanism"],
            "outcome_ids": ["lab02.o-diagnose"],
        },
        {
            "id": "lab02.e-official-diagnostic",
            "title": "在委托 json.dumps 前守住 bool 边界",
            "kind": "diagnostic",
            "wrong_code": "from lab02.answer import answer_2\nanswer_2(1)\n",
            "symptom": "调用在进入 json.dumps 前抛出 TypeError。",
            "cause": (
                "json.dumps 虽能序列化整数，但 answer_2 延续了课程声明的严格 bool 输入契约；"
                "整数 1 不能冒充 True。"
            ),
            "fix_code": (
                "from lab02.answer import answer_2\n"
                "result = answer_2(True)\n"
                "print(result)\n"
            ),
            "explanation": (
                "保留包装函数的类型检查，把输入修正为真正的 bool，再重新委托官方接口并打印 "
                "recovered observable：{\"ready\":true}。"
            ),
            "concept_ids": ["lab02.c-official"],
            "outcome_ids": ["lab02.o-diagnose"],
        },
        {
            "id": "lab02.e-text-type-diagnostic",
            "title": "把 bytes 输入恢复为声明的 str 文本",
            "kind": "diagnostic",
            "wrong_code": (
                "from lab02.mini import mini_2\n"
                "mini_2(b'{\"ready\":false}')\n"
            ),
            "symptom": "函数在比较两个声明文本前抛出 TypeError: text must be str。",
            "cause": "bytes 与 str 是不同类型；窄解析器只声明了 str 输入边界。",
            "fix_code": (
                "from lab02.mini import mini_2\n"
                "result = mini_2('{\"ready\":false}')\n"
                "print(result)\n"
            ),
            "explanation": (
                "改用 str 类型的声明文本后重新调用并打印 recovered observable："
                "{'ready': False}。"
            ),
            "concept_ids": ["lab02.c-mechanism"],
            "outcome_ids": ["lab02.o-diagnose"],
        },
    ]
    lab02_lesson["capstone_bridge"] = {
        "input": "ready 布尔值或课程声明的紧凑 ready JSON 文本。",
        "output": "官方序列化文本或窄解析后的 ready 字典。",
        "increment": "累积项目已用 json.dumps 替换手写序列化，并拥有一个反向窄解析器。",
        "next": "下一 Lab 用 json.loads 替换窄解析器，再组合校验、invert 分支和紧凑输出。",
    }
    lab02_lesson["summary"] = [
        "官方桥接必须实际调用 json.dumps，并保持 Lab 01 的输入输出。",
        "mini_2 明确展示了窄解析边界；下一 Lab 将用 json.loads 做等价替换。",
    ]
    _rewrite_quiz(
        lab02["quiz"],
        trace_prompt="answer_2(False) 如何得到紧凑 JSON 文本？",
        trace_correct="构造 ready 字典并调用带紧凑 separators 的 json.dumps",
        trace_feedback="正确：官方桥保留 bool 边界，并把序列化委托给 json.dumps。",
        trace_distractors=[
            ("只需 import json 后手写字符串", "只导入没有完成官方接口替换。"),
            ("调用 json.loads(False)", "json.loads 是文本解析方向，不是序列化方向。"),
        ],
        trace_explanation="追踪 bool、ready 字典、json.dumps 调用与紧凑文本输出。",
        diagnostic_prompt="mini_2('{\"ready\": true}') 为什么失败，怎样恢复？",
        diagnostic_correct="改用声明的紧凑文本 {\"ready\":true}",
        diagnostic_feedback="正确：教学解析器只支持两个精确文本。",
        diagnostic_distractors=[
            ("把 true 改成 Python 的 True", "JSON 文本仍应使用小写 true。"),
            ("删除 ValueError 分支", "这会隐藏教学实现的边界。"),
        ],
        diagnostic_explanation="区分完整 JSON 语法与本 Lab 明确声明的窄教学子集。",
    )
    for quiz_item in lab02["quiz"]:
        quiz_item["concept_ids"] = [
            "lab02.c-official"
            if quiz_item["kind"] == "execution_trace"
            else "lab02.c-mechanism"
        ]
    lab02["quiz"].append(
        _diagnostic_quiz_item(
            quiz_id="lab02.k03",
            prompt="mini_2 收到 bytes 而不是 str 时为什么失败，怎样恢复？",
            answer="改用 str 类型的声明文本，例如 {\"ready\":false}",
            answer_feedback="正确：先恢复声明的输入类型，再重新走精确文本映射。",
            distractors=[
                ("继续传 bytes，只删除空格", "bytes 仍未满足 str 类型边界。"),
                ("删除 TypeError 分支", "这会隐藏课程声明的输入类型。"),
            ],
            explanation="先区分输入类型错误与字符串内容不受支持，再选择对应恢复动作。",
            concept_ids=["lab02.c-mechanism"],
            outcome_ids=["lab02.o-diagnose"],
            answer_position=2,
        )
    )

    lab03_lesson = lab03["lesson"]
    lab03_lesson["problem"] = {
        "context": "累积项目要用官方解析替换窄解析器，并把解析、校验、分支与输出串成一个入口。",
        "naive_approach": "解析后直接原样返回文本，或忽略 invert 与载荷形状。",
        "failure": "输出不再规范，额外字段和非 bool 值会越过边界，分支配置也可能失效。",
    }
    lab03_lesson["outcomes"] = [
        {"id": "lab03.o-trace", "text": "追踪 json.loads、精确载荷校验、invert 分支与 json.dumps。"},
        {"id": "lab03.o-diagnose", "text": "区分 JSON 语法错误、载荷形状错误和配置类型错误。"},
    ]
    lab03_official, lab03_mechanism = lab03_lesson["concepts"]
    lab03_official.update(
        {
            "name": "用 json.loads 完成等价解析替换",
            "definition": "answer_3(text: str) 直接调用 json.loads，把合法 JSON 文本转换为 Python 值。",
            "purpose": "用官方解析器替换 Lab 02 的窄文本映射，同时保留可比较输入。",
            "mechanism": [
                "接收调用者提供的 JSON 文本。",
                "把原始文本传给 json.loads。",
                "返回官方接口产生的 Python 值，格式错误则保留 JSONDecodeError。",
            ],
            "mental_model": "json.loads 是从 JSON 文本进入 Python 值世界的官方边界。",
            "design_reasons": ["直接委托能保留官方接口的合法输入范围和异常。"],
            "benefits": ["比窄解析器支持更多合法 JSON 空白和结构。"],
            "tradeoffs": ["语法合法不等于满足累积项目的 ready 载荷约束。"],
            "invariants": ["相同合法文本得到与 json.loads 相同的 Python 值。"],
            "boundaries": ["answer_3 只负责 JSON 语法解析，不负责业务形状校验。"],
            "pitfalls": ["json.loads('{\"ready\":1}') 会成功，但 1 不是项目需要的 bool。"],
            "operational_contract": _route_contract(
                "api",
                forms=["answer_3(text: str) -> object", "json.loads(text)"],
                inputs=[
                    {
                        "name": "text",
                        "meaning": "要交给官方解析器的 JSON 文本。",
                        "form": "str",
                        "example": "官方解析输入：{\"ready\":false}",
                        "constraints": ["必须满足 JSON 语法；业务形状由组合入口另行校验。"],
                    }
                ],
                outputs=[
                    {
                        "name": "value",
                        "meaning": "json.loads 返回的 Python 值。",
                        "form": "JSON 可表示的 Python 值",
                        "example": "{'ready': False}",
                    }
                ],
                effects=["调用 json.loads，但不修改输入文本。"],
                failure_modes=[
                    {
                        "condition": "text 不满足 JSON 语法。",
                        "observable": "json.loads 抛出 JSONDecodeError。",
                        "recovery": "修正 JSON 语法后重新调用。",
                    }
                ],
            ),
        }
    )
    lab03_mechanism.update(
        {
            "name": "ready 载荷的校验、分支与规范化",
            "definition": "normalize_ready_json 解析文本，要求载荷恰好包含 ready 字段，且值必须是 bool，再按 invert 分支转换并紧凑序列化。",
            "purpose": "把前两 Lab 的方向能力组合成一个有明确输入、配置和输出的累积项目入口。",
            "mechanism": [
                "检查 text 与 invert 的类型，再用 json.loads 解析。",
                "确认结果恰好是只含 ready 的字典，且 ready 的实际类型是 bool。",
                "invert 为 True 时反转 ready，否则保留原值。",
                "用 json.dumps 和紧凑 separators 输出规范文本。",
            ],
            "mental_model": "组合入口是一条解析、校验、转换、序列化的四段管道。",
            "design_reasons": ["把语法边界和业务边界分开，故障位置更清楚。"],
            "benefits": ["无论输入空白如何，合法载荷都会得到统一紧凑输出。"],
            "tradeoffs": ["精确形状会拒绝额外字段，即使它们是合法 JSON。"],
            "invariants": ["输出始终只含一个 ready 布尔值，并使用紧凑格式。"],
            "boundaries": ["text 必须是 str，invert 必须是 bool，载荷字典必须只含 ready 且其值为 bool。"],
            "pitfalls": ["恒定返回、原样返回或忽略 invert 都无法满足不同输入与分支。"],
            "operational_contract": _route_contract(
                "mechanism",
                forms=[
                    "mini_3(value: dict[str, bool]) -> str",
                    "normalize_ready_json(text: str, invert: bool = False) -> str",
                ],
                inputs=[
                    {
                        "name": "text",
                        "meaning": "待解析并规范化的 JSON 文本。",
                        "form": "str",
                        "example": "待规范化输入： { \"ready\" : true } ",
                        "constraints": ["解析结果必须是只含 ready 且其值为 bool 的字典。"],
                    },
                    {
                        "name": "invert",
                        "meaning": "是否反转解析后的 ready 布尔值。",
                        "form": "bool",
                        "example": "反转配置示例：True",
                        "constraints": ["实际类型必须恰好是 bool。"],
                    },
                ],
                outputs=[
                    {
                        "name": "normalized",
                        "meaning": "经过可选反转后的紧凑 ready JSON 文本。",
                        "form": "str",
                        "example": "{\"ready\":false}",
                    }
                ],
                effects=["调用 json.loads 与 json.dumps，但不修改调用者字符串。"],
                failure_modes=[
                    {
                        "condition": "text 的实际类型不是 str。",
                        "observable": (
                            "normalize_ready_json 在解析前抛出 "
                            "TypeError('text must be str')。"
                        ),
                        "recovery": (
                            "把输入转换为 str 类型的合法 ready JSON 文本后重新调用。"
                        ),
                    },
                    {
                        "condition": "invert 的实际类型不是 bool。",
                        "observable": (
                            "normalize_ready_json 在解析前抛出 "
                            "TypeError('invert must be bool')。"
                        ),
                        "recovery": "把 invert 改为 True 或 False 后重新调用。",
                    },
                    {
                        "condition": "text 是 str，但不满足 JSON 语法。",
                        "observable": "json.loads 抛出 JSONDecodeError，规范化流程停止。",
                        "recovery": "修正 JSON 语法后用相同 ready 值重新调用。",
                    },
                    {
                        "condition": (
                            "json.loads 的结果不是恰好只含 ready 字段的 dict。"
                        ),
                        "observable": (
                            "normalize_ready_json 抛出 "
                            "ValueError('payload must contain only ready')。"
                        ),
                        "recovery": (
                            "传入解析后恰好为 {'ready': <bool>} 的 JSON 文本后重新调用。"
                        ),
                    },
                    {
                        "condition": (
                            "载荷恰好只含 ready，但 ready 的实际类型不是 bool。"
                        ),
                        "observable": (
                            "normalize_ready_json 抛出 "
                            "ValueError('ready must be bool')。"
                        ),
                        "recovery": "把 ready 改为 JSON true 或 false 后重新调用。",
                    },
                ],
            ),
        }
    )
    lab03_lesson["examples"] = [
        {
            "id": "lab03.e-runnable",
            "title": "走完整的 ready JSON 规范化管道",
            "kind": "runnable",
            "path": "examples/01_happy_path.py",
            "code": lab03_project_reference + (
                "\nprint(normalize_ready_json(' { \"ready\" : true } '))\n"
                "print(normalize_ready_json('{\"ready\":false}', invert=True))\n"
            ),
            "command": "python examples/01_happy_path.py",
            "expected_output": "{\"ready\":true}\n{\"ready\":true}",
            "explanation": "第一个调用规范化空白，第二个调用还执行 invert 分支。",
            "concept_ids": ["lab03.c-official", "lab03.c-mechanism"],
            "outcome_ids": ["lab03.o-trace"],
            "trace": [
                {
                    "id": "lab03.t-input",
                    "concept_ids": ["lab03.c-official"],
                    "input_state": "收到 {\"ready\":false} 与 invert=True。",
                    "operation": "调用 json.loads 解析文本。",
                    "output_state": "得到 {'ready': False}。",
                    "explanation": "官方接口只处理 JSON 语法到 Python 值的转换。",
                },
                {
                    "id": "lab03.t-validate",
                    "concept_ids": ["lab03.c-mechanism"],
                    "input_state": "解析结果是 {'ready': False}。",
                    "operation": "检查字典只含 ready，且值的实际类型是 bool。",
                    "output_state": "载荷通过精确业务边界。",
                    "explanation": "这一步拒绝额外字段和 0/1。",
                },
                {
                    "id": "lab03.t-branch",
                    "concept_ids": ["lab03.c-mechanism"],
                    "input_state": "ready=False，invert=True。",
                    "operation": "执行反转分支，再调用紧凑 json.dumps。",
                    "output_state": "返回 {\"ready\":true}。",
                    "explanation": "配置分支和最终输出都有直接可观察结果。",
                },
            ],
        },
        {
            "id": "lab03.e-diagnostic",
            "title": "修复带额外字段的载荷",
            "kind": "diagnostic",
            "wrong_code": (
                "from lab03.project import normalize_ready_json\n"
                "normalize_ready_json('{\"ready\":true,\"extra\":0}')\n"
            ),
            "symptom": "JSON 语法解析成功，但精确载荷校验抛出 ValueError。",
            "cause": "项目边界要求字典只含 ready；extra 虽合法却未被声明。",
            "fix_code": (
                "from lab03.project import normalize_ready_json\n"
                "result = normalize_ready_json('{\"ready\":true}')\n"
                "print(result)\n"
            ),
            "explanation": (
                "删除未声明字段后重新调用并打印 recovered observable："
                "{\"ready\":true}。"
            ),
            "concept_ids": ["lab03.c-mechanism"],
            "outcome_ids": ["lab03.o-diagnose"],
        },
        {
            "id": "lab03.e-text-type-diagnostic",
            "title": "把 bytes 文本恢复为 str 输入",
            "kind": "diagnostic",
            "wrong_code": (
                "from lab03.project import normalize_ready_json\n"
                "normalize_ready_json(b'{\"ready\":false}')\n"
            ),
            "symptom": "入口在调用 json.loads 前抛出 TypeError: text must be str。",
            "cause": "text 输入是 bytes，不满足函数声明的 str 边界。",
            "fix_code": (
                "from lab03.project import normalize_ready_json\n"
                "result = normalize_ready_json('{\"ready\":false}')\n"
                "print(result)\n"
            ),
            "explanation": (
                "把输入恢复为 str 后重新调用并打印 recovered observable："
                "{\"ready\":false}。"
            ),
            "concept_ids": ["lab03.c-mechanism"],
            "outcome_ids": ["lab03.o-diagnose"],
        },
        {
            "id": "lab03.e-invert-type-diagnostic",
            "title": "把整数配置恢复为严格 bool",
            "kind": "diagnostic",
            "wrong_code": (
                "from lab03.project import normalize_ready_json\n"
                "normalize_ready_json('{\"ready\":true}', invert=1)\n"
            ),
            "symptom": "入口在解析前抛出 TypeError: invert must be bool。",
            "cause": "整数 1 虽然在条件判断中为真，却不满足严格 bool 配置边界。",
            "fix_code": (
                "from lab03.project import normalize_ready_json\n"
                "result = normalize_ready_json('{\"ready\":true}', invert=True)\n"
                "print(result)\n"
            ),
            "explanation": (
                "把配置改为真正的 bool 后重新调用并打印 recovered observable："
                "{\"ready\":false}。"
            ),
            "concept_ids": ["lab03.c-mechanism"],
            "outcome_ids": ["lab03.o-diagnose"],
        },
        {
            "id": "lab03.e-json-syntax-diagnostic",
            "title": "修复尾随逗号后重新规范化",
            "kind": "diagnostic",
            "wrong_code": (
                "from lab03.project import normalize_ready_json\n"
                "normalize_ready_json('{\"ready\":true,}')\n"
            ),
            "symptom": "json.loads 抛出 JSONDecodeError，后续载荷校验尚未执行。",
            "cause": "ready 成员后保留了 JSON 语法不允许的尾随逗号。",
            "fix_code": (
                "from lab03.project import normalize_ready_json\n"
                "result = normalize_ready_json('{\"ready\":true}')\n"
                "print(result)\n"
            ),
            "explanation": (
                "删除尾随逗号并保留相同 ready 值后重新调用，recovered observable："
                "{\"ready\":true}。"
            ),
            "concept_ids": ["lab03.c-official", "lab03.c-mechanism"],
            "outcome_ids": ["lab03.o-diagnose"],
        },
        {
            "id": "lab03.e-ready-type-diagnostic",
            "title": "把数字 ready 恢复为 JSON 布尔值",
            "kind": "diagnostic",
            "wrong_code": (
                "from lab03.project import normalize_ready_json\n"
                "normalize_ready_json('{\"ready\":1}')\n"
            ),
            "symptom": "载荷形状通过后，ready 类型检查抛出 ValueError: ready must be bool。",
            "cause": "JSON 数字 1 会解析为 int，不是项目声明的 bool。",
            "fix_code": (
                "from lab03.project import normalize_ready_json\n"
                "result = normalize_ready_json('{\"ready\":false}')\n"
                "print(result)\n"
            ),
            "explanation": (
                "把数字改为 JSON 布尔值后重新调用并打印 recovered observable："
                "{\"ready\":false}。"
            ),
            "concept_ids": ["lab03.c-mechanism"],
            "outcome_ids": ["lab03.o-diagnose"],
        },
    ]
    lab03_lesson["capstone_bridge"] = {
        "input": "一段 JSON 文本和一个严格 bool 类型的 invert 配置。",
        "output": "只含 ready 布尔值的规范化紧凑 JSON 文本。",
        "increment": "累积项目现在完成解析、精确校验、可选反转与紧凑序列化。",
        "next": "继续扩展时，应先为新字段声明形状、分支和失败测试，再放宽边界。",
    }
    lab03_lesson["summary"] = [
        "json.loads 完成窄解析器的官方替换，但业务形状仍需单独校验。",
        "最终入口用不同输入与 invert 分支证明它不是恒定返回、原样返回或忽略配置。",
    ]
    _rewrite_quiz(
        lab03["quiz"],
        trace_prompt="normalize_ready_json('{\"ready\":false}', invert=True) 返回什么？",
        trace_correct="返回 {\"ready\":true}",
        trace_feedback="正确：先解析 False，通过精确校验，再由 invert 分支反转并紧凑输出。",
        trace_distractors=[
            ("返回原始文本 {\"ready\":false}", "这忽略了 invert 分支。"),
            ("返回 {'ready': True}", "入口承诺的是 JSON 文本，不是 Python 字典。"),
        ],
        trace_explanation="沿着解析、精确校验、分支转换与紧凑序列化逐步追踪。",
        diagnostic_prompt="为什么带 extra 字段的合法 JSON 仍被 normalize_ready_json 拒绝？",
        diagnostic_correct="项目边界要求载荷恰好只包含 ready 字段",
        diagnostic_feedback="正确：JSON 语法合法与业务形状合法是两层不同检查。",
        diagnostic_distractors=[
            ("因为 json.loads 不支持多个字段", "json.loads 支持；失败来自后续精确形状校验。"),
            ("因为 ready 必须写成 Python 的 True", "JSON 文本仍应使用小写 true。"),
        ],
        diagnostic_explanation="先定位失败发生在解析后，再删除未声明字段并重试。",
    )
    for quiz_item in lab03["quiz"]:
        if quiz_item["kind"] == "diagnostic":
            quiz_item["concept_ids"] = ["lab03.c-mechanism"]
    lab03["quiz"].extend(
        [
            _diagnostic_quiz_item(
                quiz_id="lab03.k03",
                prompt="normalize_ready_json 收到 bytes 文本时怎样恢复？",
                answer="先转换为 str 类型的合法 ready JSON 文本",
                answer_feedback="正确：text 类型检查发生在 json.loads 之前。",
                distractors=[
                    ("直接把 bytes 交给 json.loads", "函数边界已明确要求 str。"),
                    ("把 invert 改成 False", "invert 不会修复 text 的类型。"),
                ],
                explanation="先恢复 text 的声明类型，再重新进入解析管道。",
                concept_ids=["lab03.c-mechanism"],
                outcome_ids=["lab03.o-diagnose"],
                answer_position=0,
            ),
            _diagnostic_quiz_item(
                quiz_id="lab03.k04",
                prompt="invert=1 为什么失败，怎样恢复？",
                answer="把 invert 改为真正的 bool，例如 True",
                answer_feedback="正确：整数 1 不能冒充严格 bool 配置。",
                distractors=[
                    ("把 JSON 的 true 改成 1", "这会再引入 ready 类型错误。"),
                    ("删除 invert 类型检查", "这会隐藏声明的配置边界。"),
                ],
                explanation="配置类型失败与 JSON 文本、载荷形状无关。",
                concept_ids=["lab03.c-mechanism"],
                outcome_ids=["lab03.o-diagnose"],
                answer_position=1,
            ),
            _diagnostic_quiz_item(
                quiz_id="lab03.k05",
                prompt="尾随逗号让规范化在哪一步失败，怎样恢复？",
                answer="先删除尾随逗号，再用相同 ready 值重新调用",
                answer_feedback="正确：JSONDecodeError 发生在业务形状校验之前。",
                distractors=[
                    ("先删除 ready 字段", "这会产生新的载荷形状错误。"),
                    ("把 invert 改成 True", "配置不会修复 JSON 语法。"),
                ],
                explanation="先修复 json.loads 的语法边界，后续校验才能执行。",
                concept_ids=["lab03.c-official", "lab03.c-mechanism"],
                outcome_ids=["lab03.o-diagnose"],
                answer_position=2,
            ),
            _diagnostic_quiz_item(
                quiz_id="lab03.k06",
                prompt="载荷是 {\"ready\":1} 时为什么失败，怎样恢复？",
                answer="把 1 改为 JSON 布尔值 true 或 false",
                answer_feedback="正确：形状通过后，ready 仍必须是严格 bool。",
                distractors=[
                    ("增加 extra 字段", "额外字段会触发更早的形状错误。"),
                    ("把 1 写成字符串", "字符串仍不是 bool。"),
                ],
                explanation="区分容器形状正确与字段值类型正确这两层边界。",
                concept_ids=["lab03.c-mechanism"],
                outcome_ids=["lab03.o-diagnose"],
                answer_position=0,
            ),
        ]
    )


def make_assessed_course_spec(
    base_spec: dict[str, object],
    *,
    operational_contract: Callable[[str], dict[str, Any]],
) -> dict[str, object]:
    """Build assessed readiness, depth, and semantic route on a private copy."""
    spec = deepcopy(base_spec)
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
                    "foundation_concept_ids": ["lab00.c-json-shape"],
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
    foundation_lesson["concepts"].append(_json_shape_concept())
    foundation["study_minutes"] = {  # type: ignore[index]
        "tier": "foundation",
        "min": 45,
        "max": 60,
        "reason": "学习者自评发现本路线会用到的 JSON 前置知识缺口。",
    }

    operational_kind_by_concept = {
        "lab00.c-mechanism": "api",
        "lab00.c-json-shape": "data-model",
        "lab01.c-mechanism": "mechanism",
        "lab02.c-official": "api",
        "lab02.c-mechanism": "mechanism",
        "lab03.c-official": "api",
        "lab03.c-mechanism": "mechanism",
    }
    sections = [foundation, *spec["labs"]]  # type: ignore[index]
    for section in sections:
        lesson = section["lesson"]
        concept_ids = [concept["id"] for concept in lesson["concepts"]]
        for concept in lesson["concepts"]:
            if "operational_contract" not in concept:
                concept["operational_contract"] = operational_contract(
                    operational_kind_by_concept[concept["id"]]
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

    apply_assessed_semantic_route(spec)
    return spec
