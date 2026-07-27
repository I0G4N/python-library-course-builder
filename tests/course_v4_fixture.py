from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _quiz(chapter_id: str, *, language: str) -> dict[str, Any]:
    if language == "en":
        prompt = f"Which observation matches {chapter_id}?"
        choices = (
            ("The declared behavior", "Correct: this follows the interface."),
            ("An unrelated side effect", "No: that effect is outside the interface."),
        )
        explanation = "The declared behavior is the observable course contract."
    else:
        prompt = f"哪个结果符合 {chapter_id} 的接口？"
        choices = (
            ("题目声明的行为", "正确：这个结果符合接口约定。"),
            ("无关的额外副作用", "不正确：该副作用不属于接口。"),
        )
        explanation = "题目声明的行为才是课程使用的可观察契约。"
    return {
        "questions": [
            {
                "id": f"{chapter_id}.k1",
                "prompt": prompt,
                "choices": [
                    {"id": "a", "text": choices[0][0], "feedback": choices[0][1]},
                    {"id": "b", "text": choices[1][0], "feedback": choices[1][1]},
                ],
                "answer_id": "a",
                "explanation": explanation,
            }
        ]
    }


def make_v4_route(*, language: str = "zh-CN") -> dict[str, Any]:
    if language == "en":
        title = "Small cumulative parser"
        description = "Build a parser through two cumulative chapters."
        capstone = "A small parser with an explicit normalization boundary."
        chapter_titles = (
            "Lab 00: learning loop",
            "Lab 01: normalize one value",
            "Lab 02: compose the parser",
        )
        prompts = ("Normalize one value.", "Compose the parser.")
    else:
        title = "累计式微型解析器"
        description = "通过两个累计章节构建一个微型解析器。"
        capstone = "具有明确归一化边界的微型解析器。"
        chapter_titles = (
            "Lab 00：学习循环",
            "Lab 01：归一化一个值",
            "Lab 02：组合解析器",
        )
        prompts = ("归一化一个值。", "组合解析器。")
    return {
        "schema_version": 4,
        "course": {
            "id": "tiny-parser",
            "curriculum_id": "tiny-parser-v4-fixture",
            "title": title,
            "description": description,
            "language": language,
            "python_requires": ">=3.13,<3.14",
            "dependencies": [],
            "capstone": capstone,
        },
        "target": {
            "name": "json",
            "kind": "stdlib",
            "version": "Python 3.13",
            "track": "value conversion",
            "import_roots": ["json"],
            "official_sources": [
                {
                    "id": "python-json",
                    "title": "Python json documentation",
                    "url": "https://docs.python.org/3.13/library/json.html",
                }
            ],
        },
        "research": {
            "status": "complete",
            "version_basis": "Pinned to the Python 3.13 documentation.",
            "notes": ["The fixture uses deterministic in-memory values."],
        },
        "chapters": [
            {
                "id": "lab00",
                "title": chapter_titles[0],
                "kind": "orientation",
                "depends_on": None,
                "study_minutes": {"min": 10, "max": 20},
                "sources": ["python-json"],
                "owned_paths": [],
                "task_contracts": [],
            },
            {
                "id": "lab01",
                "title": chapter_titles[1],
                "kind": "lab",
                "depends_on": "lab00",
                "study_minutes": {"min": 25, "max": 40},
                "sources": ["python-json"],
                "owned_paths": ["src/tiny_parser/normalize.py"],
                "task_contracts": [
                    {
                        "id": "lab01.q1",
                        "title": "normalize",
                        "file": "src/tiny_parser/normalize.py",
                        "symbol": "normalize",
                        "prompt": prompts[0],
                        "points": 1,
                        "timeout_seconds": 20,
                        "public_tests": [
                            "test_normalize.py::test_normalize"
                        ],
                        "hidden_tests": [
                            "test_normalize_hidden.py::test_normalize_hidden"
                        ],
                        "example": {
                            "input": "' ready '",
                            "output": "'ready'",
                            "explanation": "Whitespace is removed at the boundary.",
                        },
                    }
                ],
            },
            {
                "id": "lab02",
                "title": chapter_titles[2],
                "kind": "capstone",
                "depends_on": "lab01",
                "study_minutes": {
                    "min": 35,
                    "max": 50,
                    "reason": "The final chapter composes both public interfaces.",
                },
                "sources": ["python-json"],
                "owned_paths": ["src/tiny_parser/parser.py"],
                "task_contracts": [
                    {
                        "id": "lab02.q1",
                        "title": "parse",
                        "file": "src/tiny_parser/parser.py",
                        "symbol": "parse",
                        "prompt": prompts[1],
                        "points": 2,
                        "timeout_seconds": 30,
                        "public_tests": ["test_parser.py::test_parse"],
                        "hidden_tests": [
                            "test_parser_hidden.py::test_parse_hidden"
                        ],
                    }
                ],
            },
        ],
    }


def _write_knowledge_package(
    root: Path,
    chapter_id: str,
    title: str,
    *,
    language: str,
) -> None:
    chapter = root / chapter_id
    chapter.mkdir(parents=True)
    (chapter / "tutorial.md").write_text(
        f"# {title}\n\n"
        "A free-form chapter may choose any natural narrative and heading order.\n",
        encoding="utf-8",
    )
    _write_json(
        chapter / "terms.json",
        {
            "terms": [
                {
                    "term": "learning loop",
                    "definition": "Read, predict, implement, test, and reflect.",
                }
            ]
        },
    )
    _write_json(chapter / "quiz.json", _quiz(chapter_id, language=language))


def _write_graded_package(
    root: Path,
    chapter: dict[str, Any],
    *,
    language: str,
) -> None:
    chapter_id = str(chapter["id"])
    package = root / chapter_id
    package.mkdir(parents=True)
    (package / "tutorial.md").write_text(
        (
            f"# {chapter['title']}\n\n"
            "This prose intentionally does not follow a required heading template.\n\n"
            "## One concrete walk-through\n\n"
            "A value crosses one caller-visible interface and produces one observable.\n"
        ),
        encoding="utf-8",
    )
    _write_json(
        package / "terms.json",
        {
            "terms": [
                {
                    "term": "boundary",
                    "definition": "The caller-visible input and output edge.",
                }
            ]
        },
    )
    _write_json(package / "quiz.json", _quiz(chapter_id, language=language))

    task = chapter["task_contracts"][0]
    owned_path = str(task["file"])
    symbol = str(task["symbol"])
    starter = (
        f"def {symbol}(value: str) -> str:\n"
        "    raise NotImplementedError\n"
    )
    solution = (
        f"def {symbol}(value: str) -> str:\n"
        "    return value.strip()\n"
    )
    starter_path = package / "starter" / owned_path
    solution_path = package / "solution" / owned_path
    starter_path.parent.mkdir(parents=True, exist_ok=True)
    solution_path.parent.mkdir(parents=True, exist_ok=True)
    starter_path.write_text(starter, encoding="utf-8")
    solution_path.write_text(solution, encoding="utf-8")

    public_selector = str(task["public_tests"][0])
    public_name, _, public_node = public_selector.partition("::")
    hidden_selector = str(task["hidden_tests"][0])
    hidden_name, _, hidden_node = hidden_selector.partition("::")
    public = package / "tests" / "public" / public_name
    hidden = package / "tests" / "hidden" / hidden_name
    public.parent.mkdir(parents=True, exist_ok=True)
    hidden.parent.mkdir(parents=True, exist_ok=True)
    import_path = owned_path.removeprefix("src/").removesuffix(".py").replace("/", ".")
    public.write_text(
        f"from {import_path} import {symbol}\n\n"
        f"def {public_node}():\n"
        f"    assert {symbol}(' ready ') == 'ready'\n",
        encoding="utf-8",
    )
    hidden.write_text(
        f"from {import_path} import {symbol}\n\n"
        f"def {hidden_node}():\n"
        f"    assert {symbol}(' value ') == 'value'\n",
        encoding="utf-8",
    )
    example = package / "examples" / "walkthrough.py"
    example.parent.mkdir(parents=True)
    example.write_text(
        f"from {import_path} import {symbol}\n"
        f"print({symbol}(' example '))\n",
        encoding="utf-8",
    )


def write_v4_fixture(
    root: Path,
    *,
    language: str = "zh-CN",
) -> tuple[Path, Path, dict[str, Any]]:
    route = make_v4_route(language=language)
    route_path = root / "route.json"
    packages = root / "packages"
    packages.mkdir(parents=True)
    _write_json(route_path, route)
    _write_knowledge_package(
        packages,
        "lab00",
        route["chapters"][0]["title"],
        language=language,
    )
    for chapter in route["chapters"][1:]:
        _write_graded_package(packages, chapter, language=language)
    return route_path, packages, deepcopy(route)
