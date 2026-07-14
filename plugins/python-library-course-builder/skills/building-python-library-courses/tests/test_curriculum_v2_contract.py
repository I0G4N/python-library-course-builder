from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
PLATFORM_ROOT = SKILL_ROOT / "assets" / "course-template" / "platform"
sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(PLATFORM_ROOT))

from scaffold_course import (  # noqa: E402
    ScaffoldError,
    compile_and_initialize,
    copy_template,
    render_course_route,
    write_canonical_source,
)
from validate_course import (  # noqa: E402
    TOKEN_PATTERN as AUTHOR_TOKEN_PATTERN,
    SpecValidationError,
    validate_spec,
)
from coursekit.compiler import (  # noqa: E402
    SourceValidationError,
    _manifest,
    compile_course,
    load_course_source,
)
from coursekit.io import TOKEN_PATTERN as SOURCE_TOKEN_PATTERN  # noqa: E402
from tests.test_timeout_contract import make_spec as make_v1_spec  # noqa: E402


CONCEPT_FIELDS = (
    "definition",
    "purpose",
    "mechanism",
    "mental_model",
    "design_reasons",
    "benefits",
    "tradeoffs",
    "invariants",
    "boundaries",
    "pitfalls",
    "source_claims",
)


def _concept(lab_id: str, *, official: bool = False) -> dict[str, object]:
    concept_id = f"{lab_id}.c-{'official' if official else 'mechanism'}"
    name = "Official fixture bridge" if official else "Teaching mechanism"
    return {
        "id": concept_id,
        "name": name,
        "definition": f"{name} is the precise object introduced in {lab_id}.",
        "purpose": "It gives one explicit responsibility to the cumulative project.",
        "mechanism": [
            "Validate the input at the caller boundary.",
            "Execute the operation and produce one observable result.",
            "Return ownership to the caller without hidden global state.",
        ],
        "mental_model": "Treat the operation as a box with owned input, state, and output.",
        "design_reasons": ["A narrow interface keeps behavior testable and replaceable."],
        "benefits": ["The learner can compare the mechanism with the official API."],
        "tradeoffs": ["The teaching version intentionally omits production optimizations."],
        "invariants": ["Equal inputs produce equal declared observables."],
        "boundaries": ["Only CPU and offline behavior is graded."],
        "pitfalls": ["Do not confuse a teaching equivalent with upstream source code."],
        "source_claims": [
            {
                "source_id": "python-docs",
                "claim": "The official bridge uses the pinned public contract.",
                "status": "documented",
            }
        ],
    }


def _lesson(lab_id: str, *, include_official: bool) -> dict[str, object]:
    concepts = []
    if include_official:
        concepts.append(_concept(lab_id, official=True))
    concepts.append(_concept(lab_id))
    outcome_ids = [f"{lab_id}.o-trace", f"{lab_id}.o-diagnose"]
    return {
        "prerequisites": [
            {
                "id": f"{lab_id}.p-python",
                "title": "Basic Python functions",
                "why": "The Lab exposes behavior through small function interfaces.",
                "refresh": "Review parameters, return values, exceptions, and imports.",
            }
        ],
        "problem": {
            "context": "The cumulative project needs one new capability.",
            "naive_approach": "Hide the work in a global helper and trust call order.",
            "failure": "Ownership and failure behavior then become impossible to reason about.",
        },
        "outcomes": [
            {"id": outcome_ids[0], "text": "Trace input, execution, and output."},
            {"id": outcome_ids[1], "text": "Diagnose a broken ownership boundary."},
        ],
        "concepts": concepts,
        "examples": [
            {
                "id": f"{lab_id}.e-runnable",
                "title": "Run the happy path",
                "kind": "runnable",
                "path": "examples/01_happy_path.py",
                "code": "value = 1 + 1\nprint(value)\n",
                "command": "python examples/01_happy_path.py",
                "expected_output": "2",
                "explanation": "The complete example runs offline on CPU.",
                "concept_ids": [f"{lab_id}.c-mechanism"],
                "outcome_ids": [outcome_ids[0]],
            },
            {
                "id": f"{lab_id}.e-diagnostic",
                "title": "See and repair the ownership bug",
                "kind": "diagnostic",
                "wrong_code": "shared = []\ndef add(x):\n    shared.append(x)\n",
                "symptom": "A later call observes values left by an earlier call.",
                "cause": "The mutable list is process-global instead of call-owned.",
                "fix_code": "def add(items, x):\n    return [*items, x]\n",
                "explanation": "Returning new state makes the ownership transfer explicit.",
                "concept_ids": [f"{lab_id}.c-mechanism"],
                "outcome_ids": [outcome_ids[1]],
            },
        ],
        "capstone_bridge": {
            "input": "The previous Lab's official output contract.",
            "output": "One new project capability with explicit ownership.",
            "increment": f"Add the {lab_id} capability to the cumulative fixture.",
            "next": "The next Lab replaces this mechanism with the pinned official API.",
        },
        "summary": [
            "A teaching implementation exposes the mechanism.",
            "The next Lab performs the graded official replacement.",
        ],
    }


def _quiz_question(
    lab_id: str,
    *,
    kind: str,
    ordinal: int,
    answer_position: int,
) -> dict[str, object]:
    choice_ids = ["a", "b", "c"]
    choices = [
        {
            "id": choice_id,
            "text": f"Choice {choice_id.upper()} for {kind}",
            "feedback": f"Choice {choice_id.upper()} maps to one concrete misconception.",
        }
        for choice_id in choice_ids
    ]
    return {
        "id": f"{lab_id}.k{ordinal:02d}",
        "kind": kind,
        "prompt": f"Which {kind.replace('_', ' ')} result follows?",
        "choices": choices,
        "answer_id": choice_ids[answer_position],
        "explanation": "Trace the declared ownership and execution order.",
        "concept_ids": [f"{lab_id}.c-mechanism"],
        "outcome_ids": [
            f"{lab_id}.o-{'trace' if kind == 'execution_trace' else 'diagnose'}"
        ],
    }


def _test_payload(symbol: str, *, hidden: bool = False) -> dict[str, str]:
    suffix = "_hidden" if hidden else ""
    selector = f"test_{symbol}{suffix}"
    return {
        "path": f"{selector}.py",
        "selector": selector,
        "code": f"def {selector}():\n    assert True\n",
    }


def make_v2_spec() -> dict[str, object]:
    spec = deepcopy(make_v1_spec())
    if spec.get("schema_version") == 2:
        return spec
    spec["schema_version"] = 2
    course = spec["course"]  # type: ignore[index]
    course["audience"] = {  # type: ignore[index]
        "level": "basic-python",
        "assumes": ["variables", "functions", "classes", "imports"],
        "does_not_assume": ["distributed systems", "the target library"],
        "lab_minutes": {"min": 30, "max": 45},
    }
    target = spec["target"]  # type: ignore[index]
    target["import_roots"] = ["fixture"]  # type: ignore[index]

    answer_positions = iter((0, 1, 2, 0, 1, 2, 0, 1))
    foundation = spec["foundation"]  # type: ignore[index]
    foundation.pop("examples")  # type: ignore[union-attr]
    foundation["lesson"] = _lesson("lab00", include_official=False)  # type: ignore[index]
    foundation["quiz"] = [  # type: ignore[index]
        _quiz_question(
            "lab00", kind="execution_trace", ordinal=1, answer_position=next(answer_positions)
        ),
        _quiz_question(
            "lab00", kind="diagnostic", ordinal=2, answer_position=next(answer_positions)
        ),
    ]

    labs = spec["labs"]  # type: ignore[index]
    for index, lab in enumerate(labs, start=1):  # type: ignore[union-attr]
        lab_id = str(lab["id"])
        include_official = index > 1
        lab.pop("concepts")
        lab.pop("capstone_increment")
        lab["lesson"] = _lesson(lab_id, include_official=include_official)

        original_file = lab["files"][0]
        original_question = lab["questions"][0]
        original_question["kind"] = "official_bridge" if include_official else "reimplementation"
        original_question["concept_ids"] = [
            f"{lab_id}.c-{'official' if include_official else 'mechanism'}"
        ]
        original_question["outcome_ids"] = [f"{lab_id}.o-trace"]
        if include_official:
            symbol = str(original_question["symbol"])
            original_file["starter"] = (
                f"import fixture\n\ndef {symbol}():\n    raise NotImplementedError\n"
            )
            original_file["reference"] = f"import fixture\n\ndef {symbol}():\n    return {index}\n"

            mini_symbol = f"mini_{index}"
            mini_path = f"{lab_id}/mini.py"
            mini_file = {
                "path": mini_path,
                "starter": f"def {mini_symbol}():\n    raise NotImplementedError\n",
                "reference": f"def {mini_symbol}():\n    return {index}\n",
            }
            mini_question = {
                "id": f"{lab_id}.q2",
                "kind": "reimplementation",
                "title": f"Implement teaching mechanism {index}",
                "file": mini_path,
                "symbol": mini_symbol,
                "points": 1,
                "timeout_seconds": 30,
                "prompt": "Implement the current teaching-equivalent mechanism.",
                "concept_ids": [f"{lab_id}.c-mechanism"],
                "outcome_ids": [f"{lab_id}.o-diagnose"],
                "example": {
                    "input": f"{mini_symbol}()",
                    "output": str(index),
                    "explanation": "The teaching mechanism matches the declared observable.",
                },
                "public_test": _test_payload(mini_symbol),
                "hidden_test": _test_payload(mini_symbol, hidden=True),
            }
            lab["files"].append(mini_file)
            lab["questions"].append(mini_question)
            lab["official_bridge"] = {
                "from_lab": f"lab{index - 1:02d}",
                "mini_module": f"lab{index - 1:02d}.answer",
                "official_symbols": ["fixture.answer"],
                "required_imports": ["fixture"],
                "question_id": original_question["id"],
                "observables": [
                    {"id": "return-value", "description": "The returned scalar value."}
                ],
                "comparison_cases": [
                    {
                        "input": f"{original_question['symbol']}()",
                        "expected": index,
                        "observable_ids": ["return-value"],
                    }
                ],
            }
            learner_file = mini_path
            question_ids = [mini_question["id"]]
        else:
            learner_file = str(original_file["path"])
            question_ids = [original_question["id"]]

        lab["module_cycle"] = {
            "reimplementation": {
                "module_id": f"{lab_id}.mini-module",
                "title": f"Teaching mechanism for {lab_id}",
                "target_symbols": ["fixture.answer"],
                "lower_level_dependencies": ["plain Python values"],
                "learner_file": learner_file,
                "question_ids": question_ids,
                "forbidden_imports": ["fixture"],
            }
        }
        lab["quiz"] = [
            _quiz_question(
                lab_id,
                kind="execution_trace",
                ordinal=1,
                answer_position=next(answer_positions),
            ),
            _quiz_question(
                lab_id,
                kind="diagnostic",
                ordinal=2,
                answer_position=next(answer_positions),
            ),
        ]
    return spec


def _write_valid_split_source(root: Path) -> Path:
    platform = root / "platform"
    write_canonical_source(platform, validate_spec(make_v2_spec()))
    return platform / "course" / "source"


def test_v2_spec_validates_and_preserves_stable_quiz_choice_ids() -> None:
    validated = validate_spec(make_v2_spec())

    assert validated["schema_version"] == 2
    first = validated["foundation"]["quiz"][0]
    assert first["answer_id"] in {choice["id"] for choice in first["choices"]}
    assert all(choice["feedback"] for choice in first["choices"])


def test_author_and_split_question_schemas_reject_unknown_private_fields(
    tmp_path: Path,
) -> None:
    authored = make_v2_spec()
    authored["labs"][0]["questions"][0]["teacher_solution"] = "secret"
    with pytest.raises(SpecValidationError, match="unknown field.*teacher_solution"):
        validate_spec(authored)

    source = _write_valid_split_source(tmp_path)
    lab_path = source / "labs/lab01/lab.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    lab["questions"][0]["teacher_solution"] = "secret"
    lab_path.write_text(json.dumps(lab) + "\n", encoding="utf-8")
    with pytest.raises(SourceValidationError, match="unknown field.*teacher_solution"):
        load_course_source(source)


def test_author_and_split_question_examples_reject_unknown_private_fields(
    tmp_path: Path,
) -> None:
    authored = make_v2_spec()
    authored["labs"][0]["questions"][0]["example"]["teacher_note"] = "secret"
    with pytest.raises(SpecValidationError, match="example.*unknown field.*teacher_note"):
        validate_spec(authored)

    source = _write_valid_split_source(tmp_path)
    lab_path = source / "labs/lab01/lab.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    lab["questions"][0]["example"]["teacher_note"] = "secret"
    lab_path.write_text(json.dumps(lab) + "\n", encoding="utf-8")
    with pytest.raises(SourceValidationError, match="example.*unknown field.*teacher_note"):
        load_course_source(source)


def test_learner_manifest_question_allowlist_drops_private_raw_fields(
    tmp_path: Path,
) -> None:
    source = _write_valid_split_source(tmp_path)
    course = load_course_source(source)
    course.labs[0].questions[0].raw["teacher_solution"] = "do not publish"
    course.labs[0].questions[0].raw["example"]["teacher_note"] = "do not publish"

    learner_question = _manifest(course, learner=True)["labs"][0]["questions"][0]

    assert "teacher_solution" not in learner_question
    assert learner_question["example"] == {
        "input": "answer_1()",
        "output": "1",
        "explanation": "The function returns the Lab value.",
    }
    assert set(learner_question) == {
        "id",
        "kind",
        "title",
        "file",
        "symbol",
        "points",
        "timeout_seconds",
        "prompt",
        "concept_ids",
        "outcome_ids",
        "example",
        "tests",
        "source_policy",
    }
    assert learner_question["source_policy"] == {
        "local_root": "lab01",
        "required_imports": [],
        "forbidden_imports": ["json"],
        "prior_mini_modules": [],
        "forbidden_course_roots": [],
    }


def test_author_validator_rejects_unstable_quiz_ids() -> None:
    spec = make_v2_spec()
    spec["foundation"]["quiz"][0]["id"] = "Bad Quiz"

    with pytest.raises(SpecValidationError, match="stable lowercase id"):
        validate_spec(spec)


def test_author_validator_rejects_course_global_duplicate_quiz_ids() -> None:
    spec = make_v2_spec()
    spec["labs"][0]["quiz"][0]["id"] = spec["foundation"]["quiz"][0]["id"]

    with pytest.raises(SpecValidationError, match="duplicate quiz id"):
        validate_spec(spec)


def test_author_validator_rejects_unstable_coding_question_ids() -> None:
    spec = make_v2_spec()
    unstable_id = "lab01.q BAD"
    spec["labs"][0]["questions"][0]["id"] = unstable_id
    spec["labs"][0]["module_cycle"]["reimplementation"]["question_ids"] = [
        unstable_id
    ]

    with pytest.raises(SpecValidationError, match="stable lowercase id"):
        validate_spec(spec)


def test_course_requires_basic_python_audience_and_30_to_45_minute_labs() -> None:
    for mutation, message in (
        (lambda spec: spec["course"].pop("audience"), "course.audience"),
        (
            lambda spec: spec["course"]["audience"]["lab_minutes"].update({"max": 60}),
            "lab_minutes",
        ),
    ):
        spec = make_v2_spec()
        mutation(spec)
        with pytest.raises(SpecValidationError, match=message):
            validate_spec(spec)


@pytest.mark.parametrize("field", CONCEPT_FIELDS)
def test_every_concept_requires_the_full_beginner_explanation(field: str) -> None:
    spec = make_v2_spec()
    del spec["labs"][0]["lesson"]["concepts"][0][field]

    with pytest.raises(SpecValidationError, match=field):
        validate_spec(spec)


def test_concept_source_claims_resolve_to_primary_source_registry() -> None:
    spec = make_v2_spec()
    spec["labs"][0]["lesson"]["concepts"][0]["source_claims"][0][
        "source_id"
    ] = "missing-source"

    with pytest.raises(SpecValidationError, match="source_claims"):
        validate_spec(spec)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda examples: examples.pop(), "at least two"),
        (
            lambda examples: [item.update({"kind": "diagnostic"}) for item in examples],
            "runnable",
        ),
        (
            lambda examples: [item.update({"kind": "runnable"}) for item in examples],
            "diagnostic",
        ),
    ),
)
def test_each_lesson_has_runnable_and_wrong_symptom_cause_fix_examples(
    mutation: object, message: str
) -> None:
    spec = make_v2_spec()
    examples = spec["labs"][0]["lesson"]["examples"]
    mutation(examples)  # type: ignore[operator]

    with pytest.raises(SpecValidationError, match=message):
        validate_spec(spec)


def test_quizzes_require_trace_diagnostic_mappings_feedback_and_distributed_answers() -> None:
    mutations = (
        (
            lambda spec: spec["labs"][0]["quiz"][0]["choices"][0].pop("feedback"),
            "feedback",
        ),
        (
            lambda spec: spec["labs"][0]["quiz"][0].update({"answer_id": "missing"}),
            "answer_id",
        ),
        (
            lambda spec: spec["labs"][0]["quiz"][0].update({"concept_ids": ["missing"]}),
            "concept_ids",
        ),
        (
            lambda spec: spec["labs"][0].update(
                {"quiz": [spec["labs"][0]["quiz"][0]]}
            ),
            "diagnostic",
        ),
        (
            lambda spec: [
                question.update({"answer_id": "a"})
                for lab in [spec["foundation"], *spec["labs"]]
                for question in lab["quiz"]
            ],
            "answer position",
        ),
    )
    for mutation, message in mutations:
        spec = make_v2_spec()
        mutation(spec)
        with pytest.raises(SpecValidationError, match=message):
            validate_spec(spec)


def test_module_cycle_requires_next_lab_official_bridge_as_first_question() -> None:
    missing = make_v2_spec()
    missing["labs"][1].pop("official_bridge")
    with pytest.raises(SpecValidationError, match="official_bridge"):
        validate_spec(missing)

    wrong_order = make_v2_spec()
    wrong_order["labs"][1]["questions"].reverse()
    with pytest.raises(SpecValidationError, match="first.*official_bridge"):
        validate_spec(wrong_order)


def test_bridge_declares_observable_comparison_and_current_lab_reimplementation() -> None:
    spec = make_v2_spec()
    spec["labs"][1]["official_bridge"]["comparison_cases"][0][
        "observable_ids"
    ] = ["missing"]
    with pytest.raises(SpecValidationError, match="observable"):
        validate_spec(spec)

    spec = make_v2_spec()
    spec["labs"][1]["questions"] = spec["labs"][1]["questions"][:1]
    with pytest.raises(SpecValidationError, match="reimplementation"):
        validate_spec(spec)


def test_mini_modules_forbid_target_imports_and_bridges_require_them() -> None:
    mini_imports_target = make_v2_spec()
    mini_imports_target["labs"][0]["files"][0]["reference"] = (
        "import json\n\ndef answer_1():\n    return 1\n"
    )
    with pytest.raises(SpecValidationError, match="forbidden import"):
        validate_spec(mini_imports_target)

    bridge_omits_target = make_v2_spec()
    bridge_omits_target["labs"][1]["files"][0]["starter"] = (
        "def answer_2():\n    raise NotImplementedError\n"
    )
    bridge_omits_target["labs"][1]["files"][0]["reference"] = (
        "def answer_2():\n    return 2\n"
    )
    with pytest.raises(SpecValidationError, match="required import"):
        validate_spec(bridge_omits_target)


def test_bridge_symbols_exactly_cover_the_previous_reimplementation() -> None:
    spec = make_v2_spec()
    spec["labs"][1]["official_bridge"]["official_symbols"] = ["json.loads"]

    with pytest.raises(SpecValidationError, match="target_symbols.*official_symbols"):
        validate_spec(spec)


def test_bridge_question_files_directly_import_every_required_root() -> None:
    spec = make_v2_spec()
    spec["target"]["import_roots"].append("pathlib")
    for lab in spec["labs"]:
        lab["module_cycle"]["reimplementation"]["forbidden_imports"].append(
            "pathlib"
        )
    spec["labs"][1]["official_bridge"]["required_imports"] = ["json", "pathlib"]

    with pytest.raises(SpecValidationError, match="missing required import.*pathlib"):
        validate_spec(spec)


def test_every_reimplementation_question_uses_the_declared_learner_file() -> None:
    spec = make_v2_spec()
    reimplementation = spec["labs"][1]["questions"][1]
    reimplementation["file"] = "lab02/answer.py"
    reimplementation["symbol"] = "answer_2"

    with pytest.raises(SpecValidationError, match="reimplementation.*learner_file"):
        validate_spec(spec)


@pytest.mark.parametrize(
    "source",
    (
        "import importlib\nimportlib.import_module('json')\n\ndef answer_1():\n    return 1\n",
        "from importlib import import_module as load\nload('json')\n\ndef answer_1():\n    return 1\n",
        "__import__('json')\n\ndef answer_1():\n    return 1\n",
    ),
)
def test_reimplementation_rejects_literal_dynamic_target_imports(source: str) -> None:
    spec = make_v2_spec()
    spec["labs"][0]["files"][0]["reference"] = source

    with pytest.raises(SpecValidationError, match="forbidden import"):
        validate_spec(spec)


def test_prior_mini_from_import_alias_cannot_bypass_the_boundary() -> None:
    spec = make_v2_spec()
    spec["labs"][2]["files"][0]["reference"] = (
        "import json\nfrom lab02 import mini as previous\n\n"
        "def answer_3():\n    return 3\n"
    )

    with pytest.raises(SpecValidationError, match="prior.*mini"):
        validate_spec(spec)


def test_reimplementation_cannot_delegate_through_missing_or_target_helpers() -> None:
    missing = make_v2_spec()
    missing["labs"][0]["files"][0]["starter"] = (
        "from lab01.helper import build\n\ndef answer_1():\n    raise NotImplementedError\n"
    )
    missing["labs"][0]["files"][0]["reference"] = (
        "from lab01.helper import build\n\ndef answer_1():\n    return build()\n"
    )
    with pytest.raises(SpecValidationError, match="undeclared.*helper"):
        validate_spec(missing)

    indirect = make_v2_spec()
    indirect["labs"][0]["files"][0]["starter"] = (
        "from lab01.helper import build\n\ndef answer_1():\n    raise NotImplementedError\n"
    )
    indirect["labs"][0]["files"][0]["reference"] = (
        "from lab01.helper import build\n\ndef answer_1():\n    return build()\n"
    )
    indirect["labs"][0]["files"].append(
        {
            "path": "lab01/helper.py",
            "starter": "import json\n\ndef build():\n    return 1\n",
            "reference": "import json\n\ndef build():\n    return 1\n",
        }
    )
    with pytest.raises(SpecValidationError, match="forbidden import"):
        validate_spec(indirect)


def test_package_root_init_cannot_hide_a_target_import() -> None:
    spec = make_v2_spec()
    spec["labs"][0]["files"][0]["starter"] = (
        "import lab01\n\ndef answer_1():\n    raise NotImplementedError\n"
    )
    spec["labs"][0]["files"][0]["reference"] = (
        "import lab01\n\ndef answer_1():\n    return 1\n"
    )
    spec["labs"][0]["files"].append(
        {
            "path": "lab01/__init__.py",
            "starter": "import json\n",
            "reference": "import json\n",
        }
    )

    with pytest.raises(SpecValidationError, match="forbidden import"):
        validate_spec(spec)


def test_author_and_split_reject_relative_import_from_in_coding_files(
    tmp_path: Path,
) -> None:
    authored = make_v2_spec()
    authored["labs"][0]["files"][0]["reference"] = (
        "from .helper import build\n\ndef answer_1():\n    return build()\n"
    )
    with pytest.raises(SpecValidationError, match="relative ImportFrom"):
        validate_spec(authored)

    source = _write_valid_split_source(tmp_path)
    answer = source / "labs/lab01/reference/lab01/answer.py"
    answer.write_text(
        "from .helper import build\n\ndef answer_1():\n    return build()\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceValidationError, match="relative ImportFrom"):
        load_course_source(source)


def test_downstream_code_cannot_import_a_prior_teaching_module() -> None:
    spec = make_v2_spec()
    spec["labs"][2]["files"][0]["reference"] = (
        "import json\nfrom lab02.mini import mini_2\n\n"
        "def answer_3():\n    return mini_2() + 1\n"
    )

    with pytest.raises(SpecValidationError, match="prior mini implementation"):
        validate_spec(spec)


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("symbols", "target_symbols.*official_symbols"),
        ("required-imports", "missing required import.*pathlib"),
        ("question-file", "reimplementation.*learner_file"),
        ("dynamic-import", "forbidden import"),
        ("prior-alias", "prior.*mini"),
    ),
)
def test_split_compiler_enforces_the_complete_mechanism_bridge_boundary(
    tmp_path: Path, case: str, message: str
) -> None:
    source = _write_valid_split_source(tmp_path)
    if case == "symbols":
        lab_path = source / "labs/lab02/lab.json"
        lab = json.loads(lab_path.read_text(encoding="utf-8"))
        lab["official_bridge"]["official_symbols"] = ["json.loads"]
        lab_path.write_text(json.dumps(lab) + "\n", encoding="utf-8")
    elif case == "required-imports":
        sources_path = source / "sources.json"
        sources = json.loads(sources_path.read_text(encoding="utf-8"))
        sources["target"]["import_roots"].append("pathlib")
        sources_path.write_text(json.dumps(sources) + "\n", encoding="utf-8")
        for lab_id in ("lab01", "lab02", "lab03"):
            lab_path = source / f"labs/{lab_id}/lab.json"
            lab = json.loads(lab_path.read_text(encoding="utf-8"))
            lab["module_cycle"]["reimplementation"]["forbidden_imports"].append(
                "pathlib"
            )
            if lab_id == "lab02":
                lab["official_bridge"]["required_imports"] = ["json", "pathlib"]
            lab_path.write_text(json.dumps(lab) + "\n", encoding="utf-8")
    elif case == "question-file":
        lab_path = source / "labs/lab02/lab.json"
        lab = json.loads(lab_path.read_text(encoding="utf-8"))
        lab["questions"][1]["file"] = "lab02/answer.py"
        lab["questions"][1]["symbol"] = "answer_2"
        lab_path.write_text(json.dumps(lab) + "\n", encoding="utf-8")
    elif case == "dynamic-import":
        (source / "labs/lab01/reference/lab01/answer.py").write_text(
            "import importlib\nimportlib.import_module('json')\n\n"
            "def answer_1():\n    return 1\n",
            encoding="utf-8",
        )
    elif case == "prior-alias":
        (source / "labs/lab03/reference/lab03/answer.py").write_text(
            "import json\nfrom lab02 import mini as previous\n\n"
            "def answer_3():\n    return 3\n",
            encoding="utf-8",
        )
    else:  # pragma: no cover
        raise AssertionError(case)

    with pytest.raises(SourceValidationError, match=message):
        load_course_source(source)


def test_split_compiler_follows_package_root_init_for_target_imports(
    tmp_path: Path,
) -> None:
    source = _write_valid_split_source(tmp_path)
    lab_path = source / "labs/lab01/lab.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    lab["files"].append({"path": "lab01/__init__.py"})
    lab_path.write_text(json.dumps(lab) + "\n", encoding="utf-8")
    for projection in ("starter", "reference"):
        (source / f"labs/lab01/{projection}/lab01/__init__.py").write_text(
            "import json\n", encoding="utf-8"
        )
        answer = source / f"labs/lab01/{projection}/lab01/answer.py"
        original = answer.read_text(encoding="utf-8")
        answer.write_text("import lab01\n" + original, encoding="utf-8")

    with pytest.raises(SourceValidationError, match="forbidden import"):
        load_course_source(source)


def test_scaffolder_uses_structured_split_source_and_compiler_generates_snapshot() -> None:
    spec = validate_spec(make_v2_spec())
    with tempfile.TemporaryDirectory() as temporary:
        platform = Path(temporary) / "platform"
        write_canonical_source(platform, spec)
        source = platform / "course/source"

        assert (source / "foundations/lesson.json").is_file()
        assert (source / "labs/lab01/lesson.json").is_file()
        assert not (source / "foundations/lesson.md").exists()
        assert not (source / "authoring-spec.json").exists()

        course = load_course_source(source)
        output = platform / "course/compiled"
        compile_course(source, output)

        content = json.loads((output / "content.json").read_text(encoding="utf-8"))
        lab = content["labs"][0]
        assert lab["lesson"].startswith("# Lab 01")
        assert lab["lesson_outline"] == spec["labs"][0]["lesson"]
        assert "<details" not in lab["lesson"]

        snapshot = json.loads(
            (output / "authoring-spec.json").read_text(encoding="utf-8")
        )
        assert snapshot == spec
        assert course.schema_version == 2


def test_generated_root_readme_route_lists_foundation_and_every_lab() -> None:
    spec = make_v2_spec()

    route = render_course_route(spec)

    expected_rows = [
        ("lab00", spec["foundation"]["title"]),
        *[(lab["id"], lab["title"]) for lab in spec["labs"]],
    ]
    assert route.startswith("| 顺序 | 本章主题 |")
    for lab_id, title in expected_rows:
        assert f"| `{lab_id}` | {title} |" in route


def test_generated_root_readme_route_escapes_table_pipes_and_newlines() -> None:
    spec = make_v2_spec()
    spec["foundation"]["title"] = "Setup \\ path | mental model\nCPU only"

    route = render_course_route(spec)

    assert "| `lab00` | Setup &#92; path &#124; mental model<br>CPU only |" in route
    assert "mental model\nCPU only" not in route


def test_runnable_commands_must_exactly_execute_the_declared_path(
    tmp_path: Path,
) -> None:
    spec = make_v2_spec()
    spec["foundation"]["lesson"]["examples"][0]["command"] = (
        "python -m examples.01_happy_path"
    )
    with pytest.raises(SpecValidationError, match="command must be exactly"):
        validate_spec(spec)

    source = _write_valid_split_source(tmp_path)
    lesson_path = source / "foundations/lesson.json"
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    lesson["examples"][0]["command"] = "python -m examples.01_happy_path"
    lesson_path.write_text(json.dumps(lesson) + "\n", encoding="utf-8")
    with pytest.raises(SourceValidationError, match="command must be exactly"):
        load_course_source(source)


def test_author_and_split_compiler_use_the_same_unresolved_token_language(
    tmp_path: Path,
) -> None:
    samples = (
        "{{UPPER_TOKEN}}",
        "{{ lower-token }}",
        "__COURSEKIT_PRIVATE__",
        "ordinary { braces }",
    )
    assert [bool(AUTHOR_TOKEN_PATTERN.search(item)) for item in samples] == [
        bool(SOURCE_TOKEN_PATTERN.search(item)) for item in samples
    ]

    for token in samples[:3]:
        source = _write_valid_split_source(tmp_path / token.replace("/", "_"))
        answer = source / "labs/lab01/reference/lab01/answer.py"
        answer.write_text(
            f"# {token}\n\ndef answer_1():\n    return 1\n", encoding="utf-8"
        )
        with pytest.raises(SourceValidationError, match="unresolved template token"):
            load_course_source(source)


def test_foundation_structured_content_includes_resolved_source_links(
    tmp_path: Path,
) -> None:
    source = _write_valid_split_source(tmp_path)
    output = tmp_path / "compiled"
    compile_course(source, output)
    content = json.loads((output / "content.json").read_text(encoding="utf-8"))

    assert content["foundations"]["sources"] == [
        {
            "id": "python-docs",
            "title": "Python JSON documentation",
            "url": "https://docs.python.org/3.13/library/json.html",
        }
    ]


def test_scaffolder_rejects_snapshot_that_differs_from_validated_input() -> None:
    authored = make_v2_spec()
    authored["author_extension"] = {"preserve": True}
    spec = validate_spec(authored)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "project"
        copy_template(root)
        write_canonical_source(root / "platform", spec)

        with pytest.raises(ScaffoldError, match="authoring snapshot"):
            compile_and_initialize(root, spec)

        assert not (root / "labs" / "manifest.json").exists()


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("dependency", "PEP 508"),
        ("target-kind", "target.kind"),
        ("target-breadth", "target.breadth"),
        ("third-party-without-dependency", "dependencies"),
        ("broad-without-track", "target.track"),
        ("broad-small-course", "course.size large"),
        ("target-name", "target.name"),
        ("target-version", "target.version"),
        ("official-sources", "official sources"),
        ("source-url", "HTTPS URL"),
        ("research-status", "research.status"),
        ("research-version-basis", "version_basis"),
        ("research-notes", "research.notes"),
    ),
)
def test_split_source_rejects_invalid_authoring_metadata(
    tmp_path: Path, case: str, message: str
) -> None:
    source = _write_valid_split_source(tmp_path)
    course_path = source / "course.json"
    sources_path = source / "sources.json"
    course = json.loads(course_path.read_text(encoding="utf-8"))
    sources = json.loads(sources_path.read_text(encoding="utf-8"))

    if case == "dependency":
        course["dependencies"] = ["not a valid PEP 508 requirement ???"]
    elif case == "target-kind":
        sources["target"]["kind"] = "invented"
    elif case == "target-breadth":
        sources["target"]["breadth"] = "infinite"
    elif case == "third-party-without-dependency":
        sources["target"]["kind"] = "pypi"
        course["dependencies"] = []
    elif case == "broad-without-track":
        sources["target"]["breadth"] = "broad"
        sources["target"]["track"] = ""
    elif case == "broad-small-course":
        sources["target"]["breadth"] = "broad"
    elif case == "target-name":
        sources["target"]["name"] = ""
    elif case == "target-version":
        sources["target"]["version"] = ""
    elif case == "official-sources":
        sources["target"]["official_sources"] = []
        sources["sources"] = []
    elif case == "source-url":
        sources["target"]["official_sources"][0]["url"] = "https://"
        sources["sources"][0]["url"] = "https://"
    elif case == "research-status":
        course["research"]["status"] = "incomplete"
    elif case == "research-version-basis":
        course["research"]["version_basis"] = ""
    elif case == "research-notes":
        course["research"]["notes"] = []
    else:  # pragma: no cover - the parameter table is exhaustive.
        raise AssertionError(case)

    course_path.write_text(json.dumps(course) + "\n", encoding="utf-8")
    sources_path.write_text(json.dumps(sources) + "\n", encoding="utf-8")

    with pytest.raises(SourceValidationError, match=message):
        load_course_source(source)


def test_split_source_rejects_selector_for_missing_test_node(tmp_path: Path) -> None:
    source = _write_valid_split_source(tmp_path)
    lab_path = source / "labs" / "lab01" / "lab.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    selector = lab["questions"][0]["tests"]["public"][0]
    test_path, separator, _node = selector.partition("::")
    assert separator
    lab["questions"][0]["tests"]["public"][0] = (
        f"{test_path}::test_does_not_exist"
    )
    lab_path.write_text(json.dumps(lab) + "\n", encoding="utf-8")

    with pytest.raises(SourceValidationError, match="does not declare"):
        load_course_source(source)
