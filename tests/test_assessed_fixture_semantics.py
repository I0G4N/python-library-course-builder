from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = (
    ROOT
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(SKILL_ROOT / "assets/course-template/platform"))

from coursekit.compiler import compile_course, load_course_source  # noqa: E402
from scaffold_course import write_canonical_source  # noqa: E402
from validate_course import validate_spec  # noqa: E402
from tests.course_v2_fixture import make_assessed_spec, make_spec  # noqa: E402


Spec = dict[str, Any]


def _questions(spec: Spec) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    for lab in spec["labs"]:
        for question in lab["questions"]:
            yield lab, question


def _declared_file(lab: dict[str, Any], path: str) -> dict[str, str]:
    return next(item for item in lab["files"] if item["path"] == path)


def _concept(spec: Spec, section_id: str, concept_id: str) -> dict[str, Any]:
    section = (
        spec["foundation"]
        if section_id == "lab00"
        else next(item for item in spec["labs"] if item["id"] == section_id)
    )
    return next(
        item for item in section["lesson"]["concepts"] if item["id"] == concept_id
    )


def _function(code: str, symbol: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    module = ast.parse(code)
    return next(
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == symbol
    )


def _tested_calls(question: dict[str, Any]) -> set[str]:
    calls: set[str] = set()
    for field in ("public_test", "hidden_test"):
        module = ast.parse(question[field]["code"])
        for node in ast.walk(module):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != question["symbol"]:
                continue
            calls.add(
                ast.dump(
                    ast.Tuple(
                        elts=[
                            *node.args,
                            *[
                                ast.Tuple(
                                    elts=[ast.Constant(keyword.arg), keyword.value],
                                    ctx=ast.Load(),
                                )
                                for keyword in node.keywords
                            ],
                        ],
                        ctx=ast.Load(),
                    ),
                    include_attributes=False,
                )
            )
    return calls


def _calls_api(code: str, module: str, name: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == module
        and node.func.attr == name
        for node in ast.walk(ast.parse(code))
    )


def _lesson_text(lab: dict[str, Any]) -> str:
    def flatten(value: object) -> Iterable[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from flatten(child)
        elif isinstance(value, list):
            for child in value:
                yield from flatten(child)

    return "\n".join(flatten(lab["lesson"]))


def _has_pytest_raises(code: str) -> bool:
    return any(
        isinstance(node, ast.With)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and isinstance(item.context_expr.func.value, ast.Name)
            and item.context_expr.func.value.id == "pytest"
            and item.context_expr.func.attr == "raises"
            for item in node.items
        )
        for node in ast.walk(ast.parse(code))
    )


def _normalized_expression(source: str) -> str:
    return ast.unparse(ast.parse(source, mode="eval").body)


def _pytest_raises_calls(code: str) -> set[tuple[str, str]]:
    covered: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(code)):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            context = item.context_expr
            if not (
                isinstance(context, ast.Call)
                and isinstance(context.func, ast.Attribute)
                and isinstance(context.func.value, ast.Name)
                and context.func.value.id == "pytest"
                and context.func.attr == "raises"
                and context.args
            ):
                continue
            exception = ast.unparse(context.args[0])
            for statement in node.body:
                for child in ast.walk(statement):
                    if isinstance(child, ast.Call):
                        covered.add((exception, ast.unparse(child)))
    return covered


def _asserted_call_results(code: str) -> set[tuple[str, str]]:
    covered: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(code)):
        if not (
            isinstance(node, ast.Assert)
            and isinstance(node.test, ast.Compare)
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Eq)
            and len(node.test.comparators) == 1
            and isinstance(node.test.left, ast.Call)
        ):
            continue
        covered.add(
            (ast.unparse(node.test.left), ast.unparse(node.test.comparators[0]))
        )
    return covered


def _import_roots(code: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _compile_assessed(tmp_path: Path) -> tuple[Spec, Path]:
    spec = validate_spec(make_assessed_spec())
    platform = tmp_path / "platform"
    write_canonical_source(platform, spec)
    output = tmp_path / "compiled"
    compile_course(platform / "course/source", output)
    return spec, output


def _selector_targets(
    output: Path,
    lab: dict[str, Any],
    question: dict[str, Any],
) -> list[str]:
    public = question["public_test"]
    hidden = question["hidden_test"]
    return [
        str(
            output
            / "starter"
            / lab["id"]
            / "tests"
            / public["path"]
        )
        + f"::{public['selector']}",
        str(output / "tests" / "hidden" / hidden["path"])
        + f"::{hidden['selector']}",
    ]


def _run_selectors(
    output: Path,
    implementation_root: Path,
    targets: list[str],
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(implementation_root), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *targets],
        cwd=output,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_python_code(
    code: str,
    *,
    cwd: Path,
    implementation_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if implementation_root is not None:
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(implementation_root), environment.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_every_assessed_question_is_parameterized_and_tests_distinct_inputs() -> None:
    spec = make_assessed_spec()
    questions = list(_questions(spec))

    assert {question["id"] for _lab, question in questions} == {
        "lab01.q1",
        "lab02.q1",
        "lab02.q2",
        "lab03.q1",
        "lab03.q2",
        "lab03.q3",
    }
    for lab, question in questions:
        declared = _declared_file(lab, question["file"])
        for projection in ("starter", "reference"):
            function = _function(declared[projection], question["symbol"])
            parameters = [
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
            ]
            assert parameters, (
                f"{question['id']} {projection} {question['symbol']} must accept "
                "caller-provided input"
            )

        example = ast.parse(question["example"]["input"], mode="eval").body
        assert isinstance(example, ast.Call) and (example.args or example.keywords), (
            f"{question['id']} example must declare a concrete input"
        )
        assert len(_tested_calls(question)) >= 2, (
            f"{question['id']} public and hidden tests must exercise at least two "
            "materially different calls"
        )


def test_generic_legacy_fixture_keeps_the_head_runnable_trace(
    tmp_path: Path,
) -> None:
    legacy = make_spec()
    expected_trace = [
        {
            "id": "lab01.t-input",
            "concept_ids": ["lab01.c-mechanism"],
            "input_state": "JSON 文本输入：'{\"ready\": true}'",
            "operation": "调用 json.loads(text) 解析 JSON 文本输入。",
            "output_state": "解析得到一个 Python 字典。",
            "explanation": "解析会把 JSON 的 true 转换为 Python 的 True。",
        },
        {
            "id": "lab01.t-output",
            "concept_ids": ["lab01.c-mechanism"],
            "input_state": "Python 字典：{'ready': True}",
            "operation": "将 result 作为函数边界的可观察输出。",
            "output_state": "Python 字典输出：{'ready': True}",
            "explanation": "输出保留 ready 字段，并使用 Python 布尔值。",
        },
    ]

    assert legacy["labs"][0]["lesson"]["examples"][0]["trace"] == expected_trace
    make_assessed_spec()

    assert make_spec() == legacy
    assert [len(lab["questions"]) for lab in legacy["labs"]] == [1, 2, 2]
    assert "def answer_1():\n    return 1\n" in legacy["labs"][0]["files"][0][
        "reference"
    ]
    validated = validate_spec(make_spec())
    platform = tmp_path / "platform"
    write_canonical_source(platform, validated)
    split_source = load_course_source(platform / "course" / "source")
    assert split_source.labs[0].lesson_outline["examples"][0]["trace"] == expected_trace


def test_foundation_json_shape_is_a_distinct_concrete_data_model_lesson() -> None:
    spec = make_assessed_spec()
    parser = _concept(spec, "lab00", "lab00.c-mechanism")
    shape = _concept(spec, "lab00", "lab00.c-json-shape")

    for field in (
        "purpose",
        "mechanism",
        "mental_model",
        "design_reasons",
        "benefits",
        "tradeoffs",
        "invariants",
        "boundaries",
        "pitfalls",
        "operational_contract",
    ):
        assert shape[field] != parser[field], (
            f"lab00.c-json-shape must teach JSON value shapes rather than clone "
            f"the generic parser concept's {field}"
        )

    contract = shape["operational_contract"]
    assert contract["kind"] == "data-model"
    assert contract["forms"] == [
        "JSON object -> Python dict",
        "JSON array -> Python list",
        "JSON string -> Python str",
        "JSON number -> Python int | float",
        "JSON true / false -> Python True / False",
        "JSON null -> Python None",
    ]
    assert contract["inputs"] == [
        {
            "name": "text",
            "meaning": "包含任意合法顶层 JSON 值的文本。",
            "form": "str containing a JSON value",
            "example": "[1, true, null]",
            "constraints": [
                "对象键必须是字符串；顶层值可以是对象、数组或标量。"
            ],
        }
    ]
    assert contract["outputs"] == [
        {
            "name": "value",
            "meaning": "按 JSON 数据模型递归映射得到的 Python 值。",
            "form": "dict | list | str | int | float | bool | None",
            "example": "[1, True, None]",
        }
    ]
    assert any("不修改" in effect and "新" in effect for effect in contract["effects"])

    mechanism = "\n".join(shape["mechanism"])
    tradeoffs = "\n".join(shape["tradeoffs"])
    boundaries = "\n".join(shape["boundaries"])
    pitfalls = "\n".join(shape["pitfalls"])
    assert all(
        marker in mechanism
        for marker in ("object", "dict", "array", "list", "true", "True", "null", "None")
    )
    assert all(marker in tradeoffs for marker in ("tuple", "array", "list", "往返"))
    assert "顶层" in boundaries and "对象键" in boundaries
    assert all(marker in boundaries for marker in ("set", "bytes", "TypeError"))
    assert all(marker in pitfalls for marker in ("true", "True", "null", "None"))


def test_lab02_lesson_activities_map_only_the_concepts_they_exercise() -> None:
    spec = make_assessed_spec()
    lab02 = spec["labs"][1]
    examples = {item["id"]: item for item in lab02["lesson"]["examples"]}
    quiz = {item["kind"]: item for item in lab02["quiz"]}

    assert examples["lab02.e-runnable"]["concept_ids"] == [
        "lab02.c-official",
        "lab02.c-mechanism",
    ]
    assert examples["lab02.e-diagnostic"]["concept_ids"] == [
        "lab02.c-mechanism"
    ]
    assert examples["lab02.e-official-diagnostic"]["concept_ids"] == [
        "lab02.c-official"
    ]
    assert "answer_2(1)" in examples["lab02.e-official-diagnostic"]["wrong_code"]
    assert quiz["execution_trace"]["concept_ids"] == ["lab02.c-official"]
    assert quiz["diagnostic"]["concept_ids"] == ["lab02.c-mechanism"]
    validate_spec(spec)


def test_mechanism_failure_modes_have_one_to_one_executable_witnesses(
    tmp_path: Path,
) -> None:
    spec, output = _compile_assessed(tmp_path)
    expected = {
        ("lab02", "lab02.c-mechanism"): [
            {
                "contract": {
                    "condition": "text 的实际类型不是 str。",
                    "observable": "mini_2 在比较文本前抛出 TypeError('text must be str')。",
                    "recovery": "传入 str 类型的两个声明文本之一后重新调用。",
                },
                "diagnostic_id": "lab02.e-text-type-diagnostic",
                "quiz_id": "lab02.k03",
                "concept_ids": ["lab02.c-mechanism"],
                "error": "TypeError: text must be str",
                "recovered": "{'ready': False}",
                "quiz_prompt": "mini_2 收到 bytes 而不是 str 时为什么失败，怎样恢复？",
                "quiz_answer": "改用 str 类型的声明文本，例如 {\"ready\":false}",
                "coding": (
                    "lab02.q2",
                    "TypeError",
                    "mini_2(b'{\"ready\":true}')",
                    "mini_2('{\"ready\":true}')",
                    "{'ready': True}",
                ),
            },
            {
                "contract": {
                    "condition": (
                        "text 是 str，但不等于 '{\"ready\":true}' 或 "
                        "'{\"ready\":false}'。"
                    ),
                    "observable": (
                        "mini_2 抛出 ValueError('unsupported ready JSON text')。"
                    ),
                    "recovery": "删除未声明空格或字段，改用两个精确文本之一后重新调用。",
                },
                "diagnostic_id": "lab02.e-diagnostic",
                "quiz_id": "lab02.k02",
                "concept_ids": ["lab02.c-mechanism"],
                "error": "ValueError: unsupported ready JSON text",
                "recovered": "{'ready': True}",
                "quiz_prompt": "mini_2('{\"ready\": true}') 为什么失败，怎样恢复？",
                "quiz_answer": "改用声明的紧凑文本 {\"ready\":true}",
                "coding": (
                    "lab02.q2",
                    "ValueError",
                    "mini_2('{\"ready\": true}')",
                    "mini_2('{\"ready\":false}')",
                    "{'ready': False}",
                ),
            },
        ],
        ("lab03", "lab03.c-mechanism"): [
            {
                "contract": {
                    "condition": "text 的实际类型不是 str。",
                    "observable": (
                        "normalize_ready_json 在解析前抛出 "
                        "TypeError('text must be str')。"
                    ),
                    "recovery": "把输入转换为 str 类型的合法 ready JSON 文本后重新调用。",
                },
                "diagnostic_id": "lab03.e-text-type-diagnostic",
                "quiz_id": "lab03.k03",
                "concept_ids": ["lab03.c-mechanism"],
                "error": "TypeError: text must be str",
                "recovered": '{"ready":false}',
                "quiz_prompt": "normalize_ready_json 收到 bytes 文本时怎样恢复？",
                "quiz_answer": "先转换为 str 类型的合法 ready JSON 文本",
                "coding": (
                    "lab03.q3",
                    "TypeError",
                    "normalize_ready_json(b'{\"ready\":false}')",
                    "normalize_ready_json('{\"ready\":false}')",
                    "'{\"ready\":false}'",
                ),
            },
            {
                "contract": {
                    "condition": "invert 的实际类型不是 bool。",
                    "observable": (
                        "normalize_ready_json 在解析前抛出 "
                        "TypeError('invert must be bool')。"
                    ),
                    "recovery": "把 invert 改为 True 或 False 后重新调用。",
                },
                "diagnostic_id": "lab03.e-invert-type-diagnostic",
                "quiz_id": "lab03.k04",
                "concept_ids": ["lab03.c-mechanism"],
                "error": "TypeError: invert must be bool",
                "recovered": '{"ready":false}',
                "quiz_prompt": "invert=1 为什么失败，怎样恢复？",
                "quiz_answer": "把 invert 改为真正的 bool，例如 True",
                "coding": (
                    "lab03.q3",
                    "TypeError",
                    "normalize_ready_json('{\"ready\":true}', invert=1)",
                    "normalize_ready_json('{\"ready\":true}', invert=True)",
                    "'{\"ready\":false}'",
                ),
            },
            {
                "contract": {
                    "condition": "text 是 str，但不满足 JSON 语法。",
                    "observable": "json.loads 抛出 JSONDecodeError，规范化流程停止。",
                    "recovery": "修正 JSON 语法后用相同 ready 值重新调用。",
                },
                "diagnostic_id": "lab03.e-json-syntax-diagnostic",
                "quiz_id": "lab03.k05",
                "concept_ids": ["lab03.c-official", "lab03.c-mechanism"],
                "error": "json.decoder.JSONDecodeError:",
                "recovered": '{"ready":true}',
                "quiz_prompt": "尾随逗号让规范化在哪一步失败，怎样恢复？",
                "quiz_answer": "先删除尾随逗号，再用相同 ready 值重新调用",
                "coding": (
                    "lab03.q3",
                    "json.JSONDecodeError",
                    "normalize_ready_json('{\"ready\":true,}')",
                    "normalize_ready_json('{\"ready\":true}')",
                    "'{\"ready\":true}'",
                ),
            },
            {
                "contract": {
                    "condition": "json.loads 的结果不是恰好只含 ready 字段的 dict。",
                    "observable": (
                        "normalize_ready_json 抛出 "
                        "ValueError('payload must contain only ready')。"
                    ),
                    "recovery": (
                        "传入解析后恰好为 {'ready': <bool>} 的 JSON 文本后重新调用。"
                    ),
                },
                "diagnostic_id": "lab03.e-diagnostic",
                "quiz_id": "lab03.k02",
                "concept_ids": ["lab03.c-mechanism"],
                "error": "ValueError: payload must contain only ready",
                "recovered": '{"ready":true}',
                "quiz_prompt": (
                    "为什么带 extra 字段的合法 JSON 仍被 "
                    "normalize_ready_json 拒绝？"
                ),
                "quiz_answer": "项目边界要求载荷恰好只包含 ready 字段",
                "coding": (
                    "lab03.q3",
                    "ValueError",
                    "normalize_ready_json('{\"ready\":true,\"extra\":0}')",
                    "normalize_ready_json('{\"ready\":true}')",
                    "'{\"ready\":true}'",
                ),
            },
            {
                "contract": {
                    "condition": "载荷恰好只含 ready，但 ready 的实际类型不是 bool。",
                    "observable": (
                        "normalize_ready_json 抛出 ValueError('ready must be bool')。"
                    ),
                    "recovery": "把 ready 改为 JSON true 或 false 后重新调用。",
                },
                "diagnostic_id": "lab03.e-ready-type-diagnostic",
                "quiz_id": "lab03.k06",
                "concept_ids": ["lab03.c-mechanism"],
                "error": "ValueError: ready must be bool",
                "recovered": '{"ready":false}',
                "quiz_prompt": "载荷是 {\"ready\":1} 时为什么失败，怎样恢复？",
                "quiz_answer": "把 1 改为 JSON 布尔值 true 或 false",
                "coding": (
                    "lab03.q3",
                    "ValueError",
                    "normalize_ready_json('{\"ready\":1}')",
                    "normalize_ready_json('{\"ready\":false}')",
                    "'{\"ready\":false}'",
                ),
            },
        ],
    }

    for (section_id, concept_id), witnesses in expected.items():
        section = next(item for item in spec["labs"] if item["id"] == section_id)
        contract = _concept(spec, section_id, concept_id)["operational_contract"]
        assert contract["failure_modes"] == [
            witness["contract"] for witness in witnesses
        ]

        diagnostics = {
            item["id"]: item
            for item in section["lesson"]["examples"]
            if item["kind"] == "diagnostic"
            and concept_id in item["concept_ids"]
        }
        quizzes = {item["id"]: item for item in section["quiz"]}
        questions = {item["id"]: item for item in section["questions"]}
        assert set(diagnostics) >= {
            witness["diagnostic_id"] for witness in witnesses
        }

        for witness in witnesses:
            diagnostic = diagnostics[witness["diagnostic_id"]]
            assert diagnostic["concept_ids"] == witness["concept_ids"]
            failed = _run_python_code(
                diagnostic["wrong_code"],
                cwd=output,
                implementation_root=output / "reference",
            )
            assert failed.returncode != 0
            assert witness["error"] in failed.stderr

            recovered = _run_python_code(
                diagnostic["fix_code"],
                cwd=output,
                implementation_root=output / "reference",
            )
            assert recovered.returncode == 0, recovered.stdout + recovered.stderr
            assert recovered.stdout.strip() == witness["recovered"]
            assert witness["recovered"] in diagnostic["explanation"]

            quiz = quizzes[witness["quiz_id"]]
            assert quiz["kind"] == "diagnostic"
            assert quiz["concept_ids"] == witness["concept_ids"]
            assert quiz["prompt"] == witness["quiz_prompt"]
            answer = next(
                choice for choice in quiz["choices"] if choice["id"] == quiz["answer_id"]
            )
            assert answer["text"] == witness["quiz_answer"]

            (
                question_id,
                exception,
                failure_call,
                recovery_call,
                recovery_result,
            ) = witness["coding"]
            question = questions[question_id]
            test_codes = [
                question["public_test"]["code"],
                question["hidden_test"]["code"],
            ]
            raise_coverage = {
                pair for code in test_codes for pair in _pytest_raises_calls(code)
            }
            recovery_coverage = {
                pair for code in test_codes for pair in _asserted_call_results(code)
            }
            assert (
                exception,
                _normalized_expression(failure_call),
            ) in raise_coverage
            assert (
                _normalized_expression(recovery_call),
                _normalized_expression(recovery_result),
            ) in recovery_coverage

    selectors = [
        target
        for lab, question in _questions(spec)
        for target in _selector_targets(output, lab, question)
    ]
    result = _run_selectors(output, output / "reference", selectors)
    assert result.returncode == 0, result.stdout + result.stderr


def test_assessed_bridge_references_call_the_declared_json_apis() -> None:
    spec = make_assessed_spec()
    lab02, lab03 = spec["labs"][1:]
    answer_2 = _declared_file(lab02, "lab02/answer.py")["reference"]
    answer_3 = _declared_file(lab03, "lab03/answer.py")["reference"]

    assert lab02["official_bridge"]["official_symbols"] == ["json.dumps"]
    assert _calls_api(answer_2, "json", "dumps"), (
        "lab02 official bridge must call json.dumps"
    )
    assert lab03["official_bridge"]["official_symbols"] == ["json.loads"]
    assert _calls_api(answer_3, "json", "loads"), (
        "lab03 official bridge must call json.loads"
    )
    for projection in ("starter", "reference"):
        function = _function(
            _declared_file(lab03, "lab03/answer.py")[projection],
            "answer_3",
        )
        assert function.returns is not None
        assert ast.unparse(function.returns) == "object"
    official_contract = lab03["lesson"]["concepts"][0]["operational_contract"]
    assert official_contract["outputs"][0]["form"] == "JSON 可表示的 Python 值"


def test_assessed_lesson_surfaces_follow_the_same_cumulative_json_route() -> None:
    spec = make_assessed_spec()
    lab01, lab02, lab03 = spec["labs"]

    lab01_text = _lesson_text(lab01)
    lab01_runnable = next(
        item for item in lab01["lesson"]["examples"] if item["kind"] == "runnable"
    )
    assert "answer_1(ready: bool) -> str" in lab01_text
    assert "紧凑" in lab01_text and "序列化" in lab01_text
    assert '{"ready":true}' in lab01_text and "TypeError" in lab01_text
    assert "import json" not in lab01_runnable["code"]
    assert "answer_1(True)" in lab01_runnable["code"]

    lab02_text = _lesson_text(lab02)
    lab02_runnable = next(
        item for item in lab02["lesson"]["examples"] if item["kind"] == "runnable"
    )
    assert "answer_2(ready: bool) -> str" in lab02_text
    assert "mini_2(text: str)" in lab02_text
    assert "json.dumps" in lab02_text and "窄解析器" in lab02_text
    assert _calls_api(lab02_runnable["code"], "json", "dumps")

    lab03_text = _lesson_text(lab03)
    lab03_runnable = next(
        item for item in lab03["lesson"]["examples"] if item["kind"] == "runnable"
    )
    assert "answer_3(text: str)" in lab03_text
    assert "normalize_ready_json" in lab03_text and "invert" in lab03_text
    assert "恰好包含 ready 字段，且值必须是 bool" in lab03_text
    assert _calls_api(lab03_runnable["code"], "json", "loads")
    assert _calls_api(lab03_runnable["code"], "json", "dumps")

    lab03_questions = {item["id"]: item for item in lab03["questions"]}
    reimplementation = lab03["module_cycle"]["reimplementation"]
    assert reimplementation["target_symbols"] == ["json.dumps"]
    assert reimplementation["question_ids"] == ["lab03.q2"]
    assert lab03_questions["lab03.q2"]["kind"] == "reimplementation"
    assert lab03_questions["lab03.q2"]["concept_ids"] == ["lab03.c-mechanism"]
    assert lab03_questions["lab03.q3"]["kind"] == "integration"
    assert set(lab03_questions["lab03.q3"]["concept_ids"]) == {
        "lab03.c-official",
        "lab03.c-mechanism",
    }
    mini_3 = _declared_file(lab03, "lab03/mini.py")["reference"]
    project = _declared_file(lab03, "lab03/project.py")["reference"]
    assert "json" not in _import_roots(mini_3)
    assert _calls_api(project, "json", "loads")
    assert _calls_api(project, "json", "dumps")

    for lab in (lab01, lab02, lab03):
        concepts = {item["id"]: item for item in lab["lesson"]["concepts"]}
        for concept_id in concepts:
            mapped = [
                question
                for question in lab["questions"]
                if concept_id in question["concept_ids"]
            ]
            assert mapped, f"{concept_id} needs a coding witness"
            assert any(
                _has_pytest_raises(question["public_test"]["code"])
                or _has_pytest_raises(question["hidden_test"]["code"])
                for question in mapped
            ), f"{concept_id} declared failure needs an executed counterexample"
            assert any(
                len(_tested_calls(question)) >= 2 for question in mapped
            ), f"{concept_id} failure needs an executed recovery/valid case"


def test_downstream_assessed_code_never_imports_a_prior_lab() -> None:
    spec = make_assessed_spec()

    for index, lab in enumerate(spec["labs"]):
        prior_roots = {item["id"] for item in spec["labs"][:index]}
        snippets = [
            projection
            for file_spec in lab["files"]
            for projection in (file_spec["starter"], file_spec["reference"])
        ]
        snippets.extend(
            question[test_kind]["code"]
            for question in lab["questions"]
            for test_kind in ("public_test", "hidden_test")
        )
        assert all(not (_import_roots(code) & prior_roots) for code in snippets), (
            f"{lab['id']} must not import prior Lab implementations or tests"
        )


def test_generated_reference_passes_all_declared_selectors_and_starter_is_todo_red(
    tmp_path: Path,
) -> None:
    spec, output = _compile_assessed(tmp_path)
    targets: list[str] = []
    for lab, question in _questions(spec):
        targets.extend(_selector_targets(output, lab, question))
        starter = _declared_file(lab, question["file"])["starter"]
        function = _function(starter, question["symbol"])
        assert any(
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Name)
            and node.exc.id == "NotImplementedError"
            for node in function.body
        ), f"{question['id']} starter must stay RED at its TODO interface"

    reference = _run_selectors(output, output / "reference", targets)
    assert reference.returncode == 0, reference.stdout + reference.stderr

    starter = _run_selectors(output, output / "starter", targets)
    assert starter.returncode != 0
    starter_output = starter.stdout + starter.stderr
    assert "NotImplementedError" in starter_output
    assert "ERROR collecting" not in starter_output


def test_runnable_and_diagnostic_examples_execute_the_declared_failure_and_recovery(
    tmp_path: Path,
) -> None:
    spec, output = _compile_assessed(tmp_path)
    expected_diagnostics = {
        "lab01.e-diagnostic": ("TypeError", '{"ready":true}'),
        "lab02.e-diagnostic": ("ValueError", "{'ready': True}"),
        "lab02.e-text-type-diagnostic": ("TypeError", "{'ready': False}"),
        "lab02.e-official-diagnostic": ("TypeError", '{"ready":true}'),
        "lab03.e-diagnostic": ("ValueError", '{"ready":true}'),
        "lab03.e-text-type-diagnostic": ("TypeError", '{"ready":false}'),
        "lab03.e-invert-type-diagnostic": ("TypeError", '{"ready":false}'),
        "lab03.e-json-syntax-diagnostic": ("JSONDecodeError", '{"ready":true}'),
        "lab03.e-ready-type-diagnostic": ("ValueError", '{"ready":false}'),
    }
    seen_diagnostics: set[str] = set()

    for lab in spec["labs"]:
        runnable = next(
            item for item in lab["lesson"]["examples"] if item["kind"] == "runnable"
        )
        ran = _run_python_code(runnable["code"], cwd=output)
        assert ran.returncode == 0, ran.stdout + ran.stderr
        assert ran.stdout.strip() == runnable["expected_output"]

        diagnostics = [
            item
            for item in lab["lesson"]["examples"]
            if item["kind"] == "diagnostic"
        ]
        for diagnostic in diagnostics:
            diagnostic_id = diagnostic["id"]
            seen_diagnostics.add(diagnostic_id)
            expected_failure, expected_recovery = expected_diagnostics[diagnostic_id]

            failed = _run_python_code(
                diagnostic["wrong_code"],
                cwd=output,
                implementation_root=output / "reference",
            )
            assert failed.returncode != 0, diagnostic_id
            assert expected_failure in failed.stderr, diagnostic_id

            recovered = _run_python_code(
                diagnostic["fix_code"],
                cwd=output,
                implementation_root=output / "reference",
            )
            assert recovered.returncode == 0, (
                diagnostic_id + recovered.stdout + recovered.stderr
            )
            assert recovered.stdout.strip() == expected_recovery, diagnostic_id
            assert expected_recovery in diagnostic["explanation"], diagnostic_id

    assert seen_diagnostics == set(expected_diagnostics)


def test_generated_selectors_reject_the_old_zero_argument_constants(
    tmp_path: Path,
) -> None:
    spec, output = _compile_assessed(tmp_path)

    for lab, question in _questions(spec):
        reference_path = output / "reference" / question["file"]
        original = reference_path.read_text(encoding="utf-8")
        old_value = int(lab["id"].removeprefix("lab"))
        reference_path.write_text(
            f"def {question['symbol']}():\n    return {old_value}\n",
            encoding="utf-8",
        )
        try:
            result = _run_selectors(
                output,
                output / "reference",
                _selector_targets(output, lab, question),
            )
        finally:
            reference_path.write_text(original, encoding="utf-8")
        assert result.returncode != 0, (
            f"{question['id']} selectors accepted the old zero-argument constant"
        )


def test_generated_selectors_reject_parameterized_constant_implementations(
    tmp_path: Path,
) -> None:
    spec, output = _compile_assessed(tmp_path)
    mutations = {
        "lab01.q1": (
            "def answer_1(ready: bool) -> str:\n"
            "    return '{\"ready\":true}'\n"
        ),
        "lab02.q1": (
            "import json\n\n"
            "def answer_2(ready: bool) -> str:\n"
            "    return '{\"ready\":true}'\n"
        ),
        "lab02.q2": (
            "def mini_2(text: str) -> dict[str, bool]:\n"
            "    return {'ready': True}\n"
        ),
        "lab03.q1": (
            "import json\n\n"
            "def answer_3(text: str) -> object:\n"
            "    return {'ready': True}\n"
        ),
        "lab03.q2": (
            "def mini_3(value: dict[str, bool]) -> str:\n"
            "    return '{\"ready\":true}'\n"
        ),
        "lab03.q3": (
            "import json\n\n"
            "def normalize_ready_json(text: str, invert: bool = False) -> str:\n"
            "    return '{\"ready\":true}'\n"
        ),
    }

    for lab, question in _questions(spec):
        reference_path = output / "reference" / question["file"]
        original = reference_path.read_text(encoding="utf-8")
        reference_path.write_text(mutations[question["id"]], encoding="utf-8")
        try:
            result = _run_selectors(
                output,
                output / "reference",
                _selector_targets(output, lab, question),
            )
        finally:
            reference_path.write_text(original, encoding="utf-8")
        assert result.returncode != 0, (
            f"{question['id']} selectors accepted a parameterized constant"
        )


def test_bridge_selectors_reject_equivalent_non_delegating_implementations(
    tmp_path: Path,
) -> None:
    spec, output = _compile_assessed(tmp_path)
    mutations = {
        "lab02.q1": (
            "import json\n\n"
            "def answer_2(ready: bool) -> str:\n"
            "    if type(ready) is not bool:\n"
            "        raise TypeError('ready must be bool')\n"
            "    return '{\"ready\":true}' if ready else '{\"ready\":false}'\n"
        ),
        "lab03.q1": (
            "import json\n\n"
            "def answer_3(text: str) -> dict[str, bool]:\n"
            "    if text == '{\"ready\":true}':\n"
            "        return {'ready': True}\n"
            "    if text == '{\"ready\":false}':\n"
            "        return {'ready': False}\n"
            "    raise ValueError('unsupported JSON text')\n"
        ),
    }

    for lab, question in _questions(spec):
        mutation = mutations.get(question["id"])
        if mutation is None:
            continue
        reference_path = output / "reference" / question["file"]
        original = reference_path.read_text(encoding="utf-8")
        reference_path.write_text(mutation, encoding="utf-8")
        try:
            result = _run_selectors(
                output,
                output / "reference",
                _selector_targets(output, lab, question),
            )
        finally:
            reference_path.write_text(original, encoding="utf-8")
        assert result.returncode != 0, (
            f"{question['id']} selectors accepted an implementation that bypasses "
            "the official json API"
        )


def test_final_integration_selectors_kill_semantic_mutations(tmp_path: Path) -> None:
    spec, output = _compile_assessed(tmp_path)
    lab = spec["labs"][2]
    question = next(item for item in lab["questions"] if item["kind"] == "integration")
    reference_path = output / "reference" / question["file"]
    original = reference_path.read_text(encoding="utf-8")
    mutations = {
        "constant": (
            "import json\n\n"
            "def normalize_ready_json(text: str, invert: bool = False) -> str:\n"
            "    return '{\"ready\":true}'\n"
        ),
        "identity": (
            "import json\n\n"
            "def normalize_ready_json(text: str, invert: bool = False) -> str:\n"
            "    return text\n"
        ),
        "ignored-input": (
            "import json\n\n"
            "def normalize_ready_json(text: str, invert: bool = False) -> str:\n"
            "    return '{\"ready\":false}' if invert else '{\"ready\":true}'\n"
        ),
        "ignored-config": (
            "import json\n\n"
            "def normalize_ready_json(text: str, invert: bool = False) -> str:\n"
            "    value = json.loads(text)\n"
            "    return json.dumps(value, separators=(',', ':'))\n"
        ),
    }

    for name, mutation in mutations.items():
        reference_path.write_text(mutation, encoding="utf-8")
        try:
            result = _run_selectors(
                output,
                output / "reference",
                _selector_targets(output, lab, question),
            )
            assert result.returncode != 0, (
                f"integration selectors accepted the {name} mutation"
            )
        finally:
            reference_path.write_text(original, encoding="utf-8")
