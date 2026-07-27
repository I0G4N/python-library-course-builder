from __future__ import annotations

import json
import os
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

import scaffold_v4_course  # noqa: E402
from scaffold_course import main as scaffold_main  # noqa: E402
from scaffold_v4_course import V4ScaffoldError, scaffold_v4_pair  # noqa: E402
from validate_course import main as validate_main  # noqa: E402


def test_v4_scaffold_writes_learner_author_pair_without_node(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path / "source")
    learner = tmp_path / "tiny-parser"

    report = scaffold_v4_pair(route_path, packages, learner)
    author = tmp_path / "tiny-parser-author"

    assert report["schema_version"] == 4
    assert report["node_install"] is False
    assert report["author"] == str(author)
    assert tomllib.loads((learner / "course.toml").read_text())[
        "schema_version"
    ] == 4
    assert "httpx2>=2,<3" in tomllib.loads(
        (learner / "pyproject.toml").read_text()
    )["project"]["dependencies"]
    assert (learner / "coursekit_runtime/static/index.html").is_file()
    assert not list((learner / "coursekit_runtime").rglob("__pycache__"))
    assert not list((learner / "coursekit_runtime").rglob("*.pyc"))
    assert (learner / "LICENSE").is_file()
    assert (learner / "NOTICE").is_file()
    assert (learner / "src/tiny_parser/normalize.py").is_file()
    assert (learner / "tests/lab01/test_normalize.py").is_file()
    assert not (learner / "tests/hidden").exists()
    assert not (learner / "solution").exists()
    assert (author / "solution/src/tiny_parser/normalize.py").is_file()
    assert (author / "LICENSE").read_bytes() == (learner / "LICENSE").read_bytes()
    assert (author / "tests/hidden/lab01/test_normalize_hidden.py").is_file()
    assert json.loads((author / "verification.json").read_text())[
        "status"
    ] == "pending"
    generation = json.loads(
        (learner / ".coursekit/generation.json").read_text()
    )
    assert generation["course_schema_version"] == 4
    assert len(generation["content_contract_sha256"]) == 64
    assert len(generation["runtime_contract_sha256"]) == 64
    assert generation["course_contract_sha256"] == report[
        "course_contract_sha256"
    ]
    assert ".coursekit/state.json" in (learner / ".gitignore").read_text()
    assert ".coursekit/state.json.lock" in (learner / ".gitignore").read_text()
    assert "*.egg-info/" in (learner / ".gitignore").read_text()
    assert ".coursekit/progress.json" not in (learner / ".gitignore").read_text()
    serialized_learner = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in learner.rglob("*")
        if path.is_file() and "coursekit_runtime" not in path.parts
    )
    assert "hidden_tests" not in serialized_learner
    assert "answer_id" not in serialized_learner
    assert not (learner / "package.json").exists()


def test_v4_scaffold_rejects_nonempty_author_before_writing_learner(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path / "source")
    learner = tmp_path / "course"
    author = tmp_path / "course-author"
    author.mkdir()
    sentinel = author / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(V4ScaffoldError, match="author destination must be empty"):
        scaffold_v4_pair(route_path, packages, learner)

    assert not learner.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_v4_scaffold_rolls_back_first_rename_when_author_rename_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path / "source")
    learner = tmp_path / "course"
    author = tmp_path / "course-author"
    real_replace = os.replace
    calls = 0

    def fail_second(source: str | Path, destination: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected author rename failure")
        real_replace(source, destination)

    monkeypatch.setattr(scaffold_v4_course.os, "replace", fail_second)

    with pytest.raises(V4ScaffoldError, match="cannot expose learner/author pair"):
        scaffold_v4_pair(route_path, packages, learner)

    assert not learner.exists()
    assert not author.exists()


def test_public_cli_dispatches_v4_validation_and_scaffolding(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    route_path, packages, _route = write_v4_fixture(tmp_path / "source")
    learner = tmp_path / "course"

    assert validate_main(
        [str(route_path), "--chapter-packages", str(packages)]
    ) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation == {
        "valid": True,
        "course_id": "tiny-parser",
        "target": "json",
        "labs": 2,
    }

    assert scaffold_main(
        [
            str(route_path),
            str(learner),
            "--chapter-packages",
            str(packages),
        ]
    ) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == 4
    assert report["created"] == str(learner)
    assert (tmp_path / "course-author").is_dir()

    missing_packages = tmp_path / "missing-packages"
    assert scaffold_main([str(route_path), str(missing_packages)]) == 1
    error = capsys.readouterr().err
    assert "schema v4 scaffolding requires --chapter-packages" in error
    assert not missing_packages.exists()


def test_v4_scaffold_binds_the_selected_locale_into_first_paint(
    tmp_path: Path,
) -> None:
    route_path, packages, _route = write_v4_fixture(
        tmp_path / "source",
        language="en",
    )
    learner = tmp_path / "course"

    scaffold_v4_pair(route_path, packages, learner)

    index = (
        learner / "coursekit_runtime/static/index.html"
    ).read_text(encoding="utf-8")
    assert '<html lang="en">' in index
    assert "__COURSEKIT_LANGUAGE__" not in index
