from __future__ import annotations

from copy import deepcopy
from typing import Any


MISSING = object()


def _concept(lab_id: str, *, official: bool = False) -> dict[str, Any]:
    suffix = "official" if official else "mechanism"
    name = "Official JSON bridge" if official else "Teaching mechanism"
    return {
        "id": f"{lab_id}.c-{suffix}",
        "name": name,
        "definition": f"{name} is the precise behavior introduced in {lab_id}.",
        "purpose": "It gives one explicit responsibility to the cumulative fixture.",
        "mechanism": [
            "Validate the input at the caller boundary.",
            "Execute one deterministic operation.",
            "Return an observable result without hidden global state.",
        ],
        "mental_model": "Treat the operation as a box with owned input and output.",
        "design_reasons": ["A narrow interface is easy to test and replace."],
        "benefits": ["The mechanism can be compared with a public API."],
        "tradeoffs": ["The teaching version omits production optimizations."],
        "invariants": ["Equal inputs produce equal declared observables."],
        "boundaries": ["Only CPU and offline behavior is graded."],
        "pitfalls": ["A teaching equivalent is not upstream source code."],
        "source_claims": [
            {
                "source_id": "python-docs",
                "claim": "The bridge follows the pinned Python JSON contract.",
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
                "title": "Basic Python functions",
                "why": "The Lab exposes behavior through a small function interface.",
                "refresh": "Review parameters, return values, exceptions, and imports.",
            }
        ],
        "problem": {
            "context": "The cumulative fixture needs one new capability.",
            "naive_approach": "Hide work in global state and trust call order.",
            "failure": "Ownership and failure behavior become hard to reason about.",
        },
        "outcomes": [
            {"id": f"{lab_id}.o-trace", "text": "Trace input, execution, and output."},
            {
                "id": f"{lab_id}.o-diagnose",
                "text": "Diagnose a broken ownership boundary.",
            },
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
                "outcome_ids": [f"{lab_id}.o-trace"],
            },
            {
                "id": f"{lab_id}.e-diagnostic",
                "title": "Repair shared mutable state",
                "kind": "diagnostic",
                "wrong_code": "shared = []\ndef add(x):\n    shared.append(x)\n",
                "symptom": "A later call observes values left by an earlier call.",
                "cause": "The mutable list is process-global instead of call-owned.",
                "fix_code": "def add(items, x):\n    return [*items, x]\n",
                "explanation": "Returning state makes ownership explicit.",
                "concept_ids": [f"{lab_id}.c-mechanism"],
                "outcome_ids": [f"{lab_id}.o-diagnose"],
            },
        ],
        "capstone_bridge": {
            "input": "The previous official output contract.",
            "output": "One new capability with explicit ownership.",
            "increment": f"Add the {lab_id} capability.",
            "next": "Replace this mechanism with the pinned official API.",
        },
        "summary": [
            "A teaching implementation exposes the mechanism.",
            "The next Lab performs the graded official replacement.",
        ],
    }


def _quiz(lab_id: str, *, first_position: int) -> list[dict[str, Any]]:
    result = []
    for ordinal, (kind, answer_position) in enumerate(
        (("execution_trace", first_position), ("diagnostic", (first_position + 1) % 3)),
        start=1,
    ):
        choices = [
            {
                "id": choice_id,
                "text": f"Choice {choice_id.upper()} for {kind}",
                "feedback": f"Choice {choice_id.upper()} maps to one misconception.",
            }
            for choice_id in ("a", "b", "c")
        ]
        result.append(
            {
                "id": f"{lab_id}.k{ordinal:02d}",
                "kind": kind,
                "prompt": f"Which {kind.replace('_', ' ')} result follows?",
                "choices": choices,
                "answer_id": choices[answer_position]["id"],
                "explanation": "Trace ownership and execution order.",
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
        "title": f"Answer {number}",
        "file": path,
        "symbol": symbol,
        "points": 1,
        "prompt": "Return the expected value through the declared boundary.",
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
                    {"id": "return-value", "description": "The returned scalar."}
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
            "title": f"Lab {number}",
            "depends_on": "lab00" if number == 1 else f"lab{number - 1:02d}",
            "lesson": _lesson(lab_id, official=official),
            "sources": ["python-docs"],
            "files": files,
            "questions": questions,
            "quiz": _quiz(lab_id, first_position=quiz_positions[number - 1]),
            "module_cycle": {
                "reimplementation": {
                    "module_id": f"{lab_id}.mini-module",
                    "title": f"Teaching mechanism for {lab_id}",
                    "target_symbols": ["json.dumps"],
                    "lower_level_dependencies": ["plain Python values"],
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
            "title": "Timeout course",
            "description": "A focused timeout contract fixture.",
            "language": "en",
            "python_requires": ">=3.13,<3.14",
            "size": "small",
            "dependencies": [],
            "capstone": "A deterministic fixture",
            "audience": {
                "level": "basic-python",
                "assumes": ["variables", "functions", "classes", "imports"],
                "does_not_assume": ["JSON internals", "distributed systems"],
                "lab_minutes": {"min": 30, "max": 45},
            },
        },
        "target": {
            "name": "json",
            "kind": "stdlib",
            "version": "Python 3.13",
            "breadth": "focused",
            "track": "timeouts",
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
            "notes": ["The fixture is deterministic."],
        },
        "foundation": {
            "id": "lab00",
            "title": "Foundation",
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
                "meaning": "The JSON text or Python value crossing the API boundary.",
                "form": "str | JSON-compatible Python value",
                "example": '{"ready": true}',
                "constraints": ["The value must satisfy the documented JSON mapping."],
            }
        ],
        "outputs": [
            {
                "name": "result",
                "meaning": "The converted Python value or JSON text.",
                "form": "JSON-compatible Python value | str",
                "example": '{"ready": true}',
            }
        ],
        "effects": ["The operation does not mutate the caller-owned input."],
        "failure_modes": [
            {
                "condition": "The input violates the selected JSON operation's contract.",
                "observable": "The documented exception is raised at the API boundary.",
                "recovery": "Correct or normalize the input before retrying.",
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
                    "subject": "functions",
                    "title": "Define and call Python functions",
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
                    "subject": "json data model",
                    "title": "Map JSON values to Python values",
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
                    "subject": "serialization boundary",
                    "title": "Recognize a serialization boundary",
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
                    "subject": "json failures",
                    "title": "Diagnose malformed JSON input",
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
    foundation["study_minutes"] = {  # type: ignore[index]
        "tier": "foundation",
        "min": 45,
        "max": 60,
        "reason": "The self-assessment identified prerequisite gaps used by the route.",
    }

    operational_kinds = iter(
        ("api", "mechanism", "formula", "lifecycle", "data-model", "api")
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
                "input_state": 'text = \'{"ready": true}\'',
                "operation": "Pass the concrete input across the declared boundary.",
                "output_state": "The operation owns one validated input value.",
                "explanation": "This makes the input form and ownership visible.",
            },
            {
                "id": f"{section['id']}.t-result",
                "concept_ids": [concept_ids[-1]],
                "input_state": "The validated input is ready for conversion.",
                "operation": "Execute the selected JSON operation.",
                "output_state": "result = {'ready': True}",
                "explanation": "This makes the observable output state explicit.",
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
                "reason": "The final Lab combines conversion, diagnosis, and replacement.",
            }

    return spec
