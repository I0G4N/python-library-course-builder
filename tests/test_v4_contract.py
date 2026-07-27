from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tomllib

import pytest

from tests.course_v4_fixture import write_v4_fixture


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from v4_contract import (  # noqa: E402
    V4ContractError,
    course_contract_sha256,
    load_v4_authoring,
    project_v4_authoring,
    validate_v4_authoring,
    validate_v4_route,
)


def _write_route(path: Path, route: dict[str, object]) -> None:
    path.write_text(
        json.dumps(route, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_v4_route_packages_and_projections_are_deterministic(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path)

    first = load_v4_authoring(route_path, packages)
    second = load_v4_authoring(route_path, packages)
    first_projection = project_v4_authoring(first)
    second_projection = project_v4_authoring(second)

    assert first_projection == second_projection
    assert first_projection.course_contract_sha256 == course_contract_sha256(first)
    parsed = tomllib.loads(
        first_projection.learner_files["course.toml"].decode("utf-8")
    )
    assert parsed["schema_version"] == 4
    assert [chapter["id"] for chapter in parsed["chapters"]] == [
        "lab00",
        "lab01",
        "lab02",
    ]
    assert (
        parsed["chapters"][1]["tasks"][0]["public_tests"]
        == ["tests/lab01/test_normalize.py::test_normalize"]
    )
    assert "hidden_tests" not in parsed["chapters"][1]["tasks"][0]
    assert "src/tiny_parser/normalize.py" in first_projection.learner_files
    assert (
        "tests/lab01/test_normalize.py"
        in first_projection.learner_files
    )
    assert (
        "solution/src/tiny_parser/normalize.py"
        in first_projection.author_files
    )
    assert (
        "tests/hidden/lab01/test_normalize_hidden.py"
        in first_projection.author_files
    )


def test_v4_public_quiz_and_course_manifest_do_not_expose_private_answers(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path)
    projection = project_v4_authoring(load_v4_authoring(route_path, packages))

    learner_quiz = json.loads(
        projection.learner_files["chapters/lab01/quiz.json"]
    )
    serialized_learner = json.dumps(
        {
            path: value.decode("utf-8")
            for path, value in projection.learner_files.items()
        },
        ensure_ascii=False,
    )
    assert learner_quiz == {
        "questions": [
            {
                "id": "lab01.k1",
                "prompt": "哪个结果符合 lab01 的接口？",
                "choices": [
                    {"id": "a", "text": "题目声明的行为"},
                    {"id": "b", "text": "无关的额外副作用"},
                ],
            }
        ]
    }
    assert '"answer_id"' not in serialized_learner
    assert '"feedback"' not in serialized_learner
    assert '"explanation"' not in serialized_learner

    author_answers = json.loads(
        projection.author_files["quiz-answers.json"]
    )
    assert (
        author_answers["chapters"]["lab01"]["lab01.k1"]["answer_id"]
        == "a"
    )
    assert (
        author_answers["chapters"]["lab01"]["lab01.k1"]["feedback"]["b"]
        == "不正确：该副作用不属于接口。"
    )
    author_binding = json.loads(projection.author_files["author.json"])
    public_binding = json.loads(
        projection.learner_files[".coursekit/course.json"]
    )
    assert (
        author_binding["course_contract_sha256"]
        == public_binding["course_contract_sha256"]
        == projection.course_contract_sha256
    )


def test_v4_accepts_free_markdown_but_rejects_depth_brief_schema_fields(
    tmp_path: Path,
) -> None:
    route_path, packages, route = write_v4_fixture(tmp_path)
    tutorial = packages / "lab01" / "tutorial.md"
    tutorial.write_text(
        "A chapter may begin without a heading.\n\n"
        "Then use an unusual transition.\n\n"
        "##### A deliberately nonstandard section\n\n"
        "There is no required vocabulary or prose length here.\n",
        encoding="utf-8",
    )
    assert load_v4_authoring(route_path, packages).chapters[1].tutorial.startswith(
        "A chapter may begin"
    )

    route_with_depth_brief = deepcopy(route)
    route_with_depth_brief["chapters"][1]["core_question"] = (
        "This belongs only in the writer prompt."
    )
    with pytest.raises(V4ContractError, match="unknown field.*core_question"):
        validate_v4_route(route_with_depth_brief)


def test_v4_contract_digest_changes_with_public_quiz_not_tutorial(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path)
    initial = load_v4_authoring(route_path, packages)
    initial_digest = course_contract_sha256(initial)

    tutorial = packages / "lab01" / "tutorial.md"
    tutorial.write_text(
        tutorial.read_text(encoding="utf-8") + "\nA prose-only revision.\n",
        encoding="utf-8",
    )
    prose_revision = load_v4_authoring(route_path, packages)
    assert course_contract_sha256(prose_revision) == initial_digest

    quiz_path = packages / "lab01" / "quiz.json"
    quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
    quiz["questions"][0]["prompt"] += "（修订）"
    quiz_path.write_text(
        json.dumps(quiz, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    quiz_revision = load_v4_authoring(route_path, packages)
    assert course_contract_sha256(quiz_revision) != initial_digest


def test_v4_quiz_explanation_and_feedback_are_optional(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path)
    quiz_path = packages / "lab01" / "quiz.json"
    quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
    question = quiz["questions"][0]
    question.pop("explanation")
    for choice in question["choices"]:
        choice.pop("feedback")
    quiz_path.write_text(
        json.dumps(quiz, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    projection = project_v4_authoring(
        load_v4_authoring(route_path, packages)
    )
    answers = json.loads(projection.author_files["quiz-answers.json"])
    assert answers["chapters"]["lab01"]["lab01.k1"] == {
        "answer_id": "a",
        "explanation": "",
        "feedback": {"a": "", "b": ""},
    }


def test_v4_rejects_missing_solution_and_missing_test_selector(
    tmp_path: Path,
) -> None:
    route_path, packages, route = write_v4_fixture(tmp_path)
    missing_solution = (
        packages / "lab01" / "solution" / "src/tiny_parser/normalize.py"
    )
    missing_solution.unlink()
    with pytest.raises(V4ContractError, match="solution files must exactly match"):
        load_v4_authoring(route_path, packages)

    _route_path, second_packages, second_route = write_v4_fixture(
        tmp_path / "second"
    )
    second_route["chapters"][1]["task_contracts"][0]["public_tests"] = [
        "test_normalize.py::test_not_declared"
    ]
    with pytest.raises(V4ContractError, match="missing test function"):
        validate_v4_authoring(second_route, second_packages)


def test_v4_reports_one_mechanical_error_per_invalid_chapter(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path)
    (packages / "lab01/tutorial.md").write_text("", encoding="utf-8")
    (packages / "lab02/tutorial.md").write_text("", encoding="utf-8")

    with pytest.raises(V4ContractError) as captured:
        load_v4_authoring(route_path, packages)

    message = str(captured.value)
    assert "chapter package mechanical validation failed" in message
    assert "- lab01: lab01/tutorial.md must not be empty" in message
    assert "- lab02: lab02/tutorial.md must not be empty" in message


def test_v4_rejects_owned_path_collisions_and_package_symlinks(
    tmp_path: Path,
) -> None:
    _route_path, packages, route = write_v4_fixture(tmp_path)
    route["chapters"][2]["owned_paths"] = ["src/tiny_parser/normalize.py"]
    route["chapters"][2]["task_contracts"][0]["file"] = (
        "src/tiny_parser/normalize.py"
    )
    with pytest.raises(V4ContractError, match="collide with earlier chapters"):
        validate_v4_authoring(route, packages)

    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlinks are unavailable")
    link = packages / "lab01" / "examples" / "linked.py"
    link.symlink_to(packages / "lab01" / "tutorial.md")
    with pytest.raises(V4ContractError, match="cannot contain symlinks"):
        load_v4_authoring(tmp_path / "route.json", packages)
