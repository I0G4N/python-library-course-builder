from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(SKILL_ROOT / "assets" / "course-template" / "platform"))

from coursekit.compiler import (  # noqa: E402
    SourceValidationError,
    _build_tree,
    _content,
    _knowledge,
    _manifest,
    load_course_source,
)
from scaffold_course import write_canonical_source  # noqa: E402
from validate_course import SpecValidationError, validate_spec  # noqa: E402
from tests.course_v2_fixture import make_assessed_spec, make_spec  # noqa: E402


SpecFactory = Callable[[], dict[str, object]]
PRIVATE_FIELD = "teacher_solution"
PRIVATE_SENTINEL = "PRIVATE-SENTINEL"
COMMON_LESSON_OBJECT_PATHS: tuple[tuple[str | int, ...], ...] = (
    (),
    ("prerequisites", 0),
    ("problem",),
    ("outcomes", 0),
    ("concepts", 0),
    ("concepts", 0, "source_claims", 0),
    ("examples", 0),
    ("examples", 1),
    ("capstone_bridge",),
)

PRIVATE_OBJECT = {PRIVATE_FIELD: PRIVATE_SENTINEL}

MANIFEST_VALUE_CASES = (
    pytest.param(
        "course", ("schema_version",), PRIVATE_OBJECT, id="course-schema-version"
    ),
    pytest.param(
        "course", ("layout_version",), PRIVATE_OBJECT, id="course-layout-version"
    ),
    pytest.param("course", ("course_id",), PRIVATE_OBJECT, id="course-id"),
    pytest.param(
        "course", ("curriculum_id",), PRIVATE_OBJECT, id="course-curriculum-id"
    ),
    pytest.param("course", ("title",), PRIVATE_OBJECT, id="course-title"),
    pytest.param("course", ("brand",), PRIVATE_OBJECT, id="course-brand"),
    pytest.param("course", ("project",), PRIVATE_OBJECT, id="course-project"),
    pytest.param("course", ("language",), PRIVATE_OBJECT, id="course-language"),
    pytest.param(
        "course", ("python_requires",), PRIVATE_OBJECT, id="course-python-requires"
    ),
    pytest.param("course", ("starter_root",), PRIVATE_OBJECT, id="course-starter-root"),
    pytest.param("course", ("source_root",), PRIVATE_OBJECT, id="course-source-root"),
    pytest.param(
        "course", ("reference_root",), PRIVATE_OBJECT, id="course-reference-root"
    ),
    pytest.param(
        "course", ("capstone", "name"), PRIVATE_OBJECT, id="course-capstone-name"
    ),
    pytest.param(
        "course",
        ("capstone", "description"),
        PRIVATE_OBJECT,
        id="course-capstone-description",
    ),
    pytest.param("course", ("target", "name"), PRIVATE_OBJECT, id="course-target-name"),
    pytest.param("course", ("target", "kind"), PRIVATE_OBJECT, id="course-target-kind"),
    pytest.param(
        "course", ("target", "version"), PRIVATE_OBJECT, id="course-target-version"
    ),
    pytest.param(
        "course", ("target", "track"), PRIVATE_OBJECT, id="course-target-track"
    ),
    pytest.param("course", ("adapter",), PRIVATE_OBJECT, id="course-adapter"),
    pytest.param("course", ("python",), PRIVATE_OBJECT, id="course-python"),
    pytest.param(
        "course",
        ("reference_components",),
        [PRIVATE_OBJECT],
        id="course-reference-components",
    ),
    pytest.param("foundation", ("id",), PRIVATE_OBJECT, id="foundation-id"),
    pytest.param("foundation", ("order",), PRIVATE_OBJECT, id="foundation-order"),
    pytest.param("foundation", ("title",), PRIVATE_OBJECT, id="foundation-title"),
    pytest.param(
        "foundation", ("description",), PRIVATE_OBJECT, id="foundation-description"
    ),
    pytest.param("foundation", ("graded",), PRIVATE_OBJECT, id="foundation-graded"),
    pytest.param(
        "foundation", ("directory",), PRIVATE_OBJECT, id="foundation-directory"
    ),
    pytest.param("foundation", ("readme",), PRIVATE_OBJECT, id="foundation-readme"),
    pytest.param(
        "foundation", ("git_scope",), PRIVATE_OBJECT, id="foundation-git-scope"
    ),
    pytest.param(
        "foundation",
        ("checkpoint", "require_submit"),
        PRIVATE_OBJECT,
        id="foundation-checkpoint-require-submit",
    ),
    pytest.param(
        "foundation",
        ("checkpoint", "git_initialized"),
        PRIVATE_OBJECT,
        id="foundation-checkpoint-git-initialized",
    ),
    pytest.param(
        "foundation",
        ("checkpoint", "git_clean"),
        PRIVATE_OBJECT,
        id="foundation-checkpoint-git-clean",
    ),
    pytest.param(
        "foundation",
        ("checkpoint", "min_commits"),
        PRIVATE_OBJECT,
        id="foundation-checkpoint-min-commits",
    ),
    pytest.param("foundation", ("demos",), [PRIVATE_OBJECT], id="foundation-demos"),
    pytest.param(
        "foundation", ("examples",), [PRIVATE_OBJECT], id="foundation-examples"
    ),
    pytest.param(
        "foundation",
        ("tests", "public"),
        [PRIVATE_OBJECT],
        id="foundation-tests-public",
    ),
    pytest.param(
        "foundation",
        ("tests", "sample"),
        [PRIVATE_OBJECT],
        id="foundation-tests-sample",
    ),
    pytest.param(
        "foundation",
        ("tests", "hidden"),
        [PRIVATE_OBJECT],
        id="foundation-tests-hidden",
    ),
    pytest.param(
        "foundation",
        ("tests", "submit"),
        [PRIVATE_OBJECT],
        id="foundation-tests-submit",
    ),
    pytest.param("lab", ("order",), PRIVATE_OBJECT, id="lab-order"),
    pytest.param("lab", ("description",), PRIVATE_OBJECT, id="lab-description"),
    pytest.param("lab", ("file",), PRIVATE_OBJECT, id="lab-file"),
    pytest.param("lab", ("directory",), PRIVATE_OBJECT, id="lab-directory"),
    pytest.param("lab", ("readme",), PRIVATE_OBJECT, id="lab-readme"),
    pytest.param("lab", ("git_scope",), PRIVATE_OBJECT, id="lab-git-scope"),
    pytest.param(
        "lab",
        ("checkpoint", "require_submit"),
        PRIVATE_OBJECT,
        id="lab-checkpoint-require-submit",
    ),
    pytest.param(
        "lab",
        ("checkpoint", "git_initialized"),
        PRIVATE_OBJECT,
        id="lab-checkpoint-git-initialized",
    ),
    pytest.param(
        "lab",
        ("checkpoint", "git_clean"),
        PRIVATE_OBJECT,
        id="lab-checkpoint-git-clean",
    ),
    pytest.param(
        "lab",
        ("checkpoint", "min_commits"),
        PRIVATE_OBJECT,
        id="lab-checkpoint-min-commits",
    ),
    pytest.param(
        "lab",
        ("git_checkpoint", "title"),
        PRIVATE_OBJECT,
        id="lab-git-checkpoint-title",
    ),
    pytest.param(
        "lab",
        ("git_checkpoint", "commands"),
        [PRIVATE_OBJECT],
        id="lab-git-checkpoint-commands",
    ),
    pytest.param("lab", ("tests", "public"), [PRIVATE_OBJECT], id="lab-tests-public"),
    pytest.param("lab", ("tests", "sample"), [PRIVATE_OBJECT], id="lab-tests-sample"),
    pytest.param("lab", ("tests", "hidden"), [PRIVATE_OBJECT], id="lab-tests-hidden"),
    pytest.param("lab", ("tests", "submit"), [PRIVATE_OBJECT], id="lab-tests-submit"),
)

MANIFEST_RANGE_CASES = (
    pytest.param("course", ("schema_version",), 1, id="course-schema-version-value"),
    pytest.param("course", ("schema_version",), 2.0, id="course-schema-version-float"),
    pytest.param("course", ("layout_version",), 2, id="course-layout-version-value"),
    pytest.param("course", ("layout_version",), 3.0, id="course-layout-version-float"),
    pytest.param("foundation", ("order",), True, id="foundation-order-bool"),
    pytest.param("foundation", ("order",), -1, id="foundation-order-negative"),
    pytest.param("foundation", ("graded",), 0, id="foundation-graded-integer"),
    pytest.param(
        "foundation",
        ("checkpoint", "min_commits"),
        True,
        id="foundation-min-commits-bool",
    ),
    pytest.param(
        "foundation",
        ("checkpoint", "min_commits"),
        -1,
        id="foundation-min-commits-negative",
    ),
    pytest.param(
        "foundation",
        ("checkpoint", "require_submit"),
        1,
        id="foundation-checkpoint-flag-integer",
    ),
    pytest.param("lab", ("order",), True, id="lab-order-bool"),
    pytest.param("lab", ("order",), -1, id="lab-order-negative"),
    pytest.param(
        "lab", ("checkpoint", "min_commits"), True, id="lab-min-commits-bool"
    ),
    pytest.param(
        "lab", ("checkpoint", "min_commits"), -1, id="lab-min-commits-negative"
    ),
    pytest.param(
        "lab",
        ("checkpoint", "git_clean"),
        1,
        id="lab-checkpoint-flag-integer",
    ),
)

MANIFEST_UNSAFE_PATH_CASES = (
    pytest.param("course", ("starter_root",), "../private", id="course-starter-root"),
    pytest.param("course", ("source_root",), "../private", id="course-source-root"),
    pytest.param(
        "course", ("reference_root",), "../private", id="course-reference-root"
    ),
    pytest.param("course", ("adapter",), "../private.py", id="course-adapter"),
    pytest.param(
        "course",
        ("reference_components",),
        ["../private.json"],
        id="course-reference-components",
    ),
    pytest.param("foundation", ("directory",), "../private", id="foundation-directory"),
    pytest.param("foundation", ("readme",), "../private.md", id="foundation-readme"),
    pytest.param("foundation", ("git_scope",), "../private", id="foundation-git-scope"),
    pytest.param(
        "foundation", ("demos",), ["../private.py"], id="foundation-demos"
    ),
    pytest.param(
        "foundation", ("examples",), ["../private.py"], id="foundation-examples"
    ),
    pytest.param("lab", ("file",), "../private.py", id="lab-file"),
    pytest.param("lab", ("directory",), "../private", id="lab-directory"),
    pytest.param("lab", ("readme",), "../private.md", id="lab-readme"),
    pytest.param("lab", ("git_scope",), "../private", id="lab-git-scope"),
)


def _lesson(spec: dict[str, object]) -> dict[str, Any]:
    return spec["labs"][0]["lesson"]  # type: ignore[index,return-value]


def _object_at(
    root: dict[str, Any], path: tuple[str | int, ...]
) -> dict[str, Any]:
    value: Any = root
    for part in path:
        value = value[part]
    assert isinstance(value, dict)
    return value


def _replace_at(
    root: dict[str, Any], path: tuple[str, ...], value: Any
) -> None:
    parent = _object_at(root, path[:-1])
    parent[path[-1]] = value


def _split_manifest(
    source: Path, surface: str
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    if surface in {"course", "foundation"}:
        path = source / "course.json"
        payload = _read_json(path)
        manifest = (
            payload["manifest"]
            if surface == "course"
            else payload["foundations"]["manifest"]
        )
    else:
        path = source / "labs/lab01/lab.json"
        payload = _read_json(path)
        manifest = payload["manifest"]
    assert isinstance(manifest, dict)
    return path, payload, manifest


def _loaded_manifest(course: Any, surface: str) -> dict[str, Any]:
    if surface == "course":
        return course.course["manifest"]
    if surface == "foundation":
        return course.foundation["manifest"]
    return course.labs[0].raw["manifest"]


def _write_split_source(root: Path, factory: SpecFactory) -> Path:
    platform = root / "platform"
    write_canonical_source(platform, validate_spec(factory()))
    return platform / "course" / "source"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "factory",
    (
        pytest.param(make_spec, id="legacy-basic-python"),
        pytest.param(make_assessed_spec, id="assessed"),
    ),
)
@pytest.mark.parametrize("path", COMMON_LESSON_OBJECT_PATHS)
def test_author_schema_rejects_private_fields_at_every_lesson_object_boundary(
    factory: SpecFactory, path: tuple[str | int, ...]
) -> None:
    spec = factory()
    _object_at(_lesson(spec), path)[PRIVATE_FIELD] = PRIVATE_SENTINEL

    with pytest.raises(
        SpecValidationError,
        match=rf"unknown field.*{PRIVATE_FIELD}",
    ):
        validate_spec(spec)


@pytest.mark.parametrize(
    "factory",
    (
        pytest.param(make_spec, id="legacy-basic-python"),
        pytest.param(make_assessed_spec, id="assessed"),
    ),
)
@pytest.mark.parametrize("path", COMMON_LESSON_OBJECT_PATHS)
def test_split_schema_rejects_private_fields_at_every_lesson_object_boundary(
    tmp_path: Path,
    factory: SpecFactory,
    path: tuple[str | int, ...],
) -> None:
    source = _write_split_source(tmp_path, factory)
    lesson_path = source / "labs/lab01/lesson.json"
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    _object_at(lesson, path)[PRIVATE_FIELD] = PRIVATE_SENTINEL
    lesson_path.write_text(
        json.dumps(lesson, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SourceValidationError,
        match=rf"unknown field.*{PRIVATE_FIELD}",
    ):
        load_course_source(source)


def test_learner_json_projections_allowlist_nested_lesson_fields(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_assessed_spec)
    course = load_course_source(source)
    expected = {
        "manifest": _manifest(course, learner=True),
        "knowledge": _knowledge(course),
        "content": _content(course),
    }

    lesson = course.labs[0].lesson_outline
    private_paths = (
        *COMMON_LESSON_OBJECT_PATHS,
        ("concepts", 0, "operational_contract"),
        ("concepts", 0, "operational_contract", "inputs", 0),
        ("concepts", 0, "operational_contract", "outputs", 0),
        ("concepts", 0, "operational_contract", "failure_modes", 0),
        ("examples", 0, "trace", 0),
    )
    for path in private_paths:
        _object_at(lesson, path)[PRIVATE_FIELD] = PRIVATE_SENTINEL

    actual = {
        "manifest": _manifest(course, learner=True),
        "knowledge": _knowledge(course),
        "content": _content(course),
    }

    assert actual == expected
    assert PRIVATE_SENTINEL not in json.dumps(actual, ensure_ascii=False)


@pytest.mark.parametrize(
    "path",
    (
        pytest.param(("course",), id="course"),
        pytest.param(("foundation",), id="foundation"),
        pytest.param(("labs", 0), id="lab"),
    ),
)
def test_author_schema_rejects_raw_manifest_at_every_author_boundary(
    path: tuple[str | int, ...],
) -> None:
    spec = make_spec()
    _object_at(spec, path)["manifest"] = {
        "author_notes": {PRIVATE_FIELD: PRIVATE_SENTINEL}
    }

    with pytest.raises(SpecValidationError, match=r"unknown field.*manifest"):
        validate_spec(spec)


@pytest.mark.parametrize(
    ("path", "manifest"),
    (
        pytest.param(
            ("course",),
            {"target": {"track": PRIVATE_OBJECT}},
            id="course-target-track",
        ),
        pytest.param(
            ("foundation",),
            {"demos": [PRIVATE_OBJECT]},
            id="foundation-demos",
        ),
        pytest.param(
            ("labs", 0),
            {"tests": {"public": [PRIVATE_OBJECT]}},
            id="lab-tests",
        ),
    ),
)
def test_author_schema_rejects_known_manifest_value_tunnels(
    path: tuple[str | int, ...], manifest: dict[str, Any]
) -> None:
    spec = make_spec()
    _object_at(spec, path)["manifest"] = manifest

    with pytest.raises(SpecValidationError, match=r"unknown field.*manifest"):
        validate_spec(spec)


@pytest.mark.parametrize(
    "surface",
    (
        pytest.param("course", id="course"),
        pytest.param("foundation", id="foundation"),
        pytest.param("lab", id="lab"),
    ),
)
def test_split_schema_rejects_unknown_nested_manifest_fields(
    tmp_path: Path, surface: str
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    if surface in {"course", "foundation"}:
        path = source / "course.json"
        payload = _read_json(path)
        manifest = (
            payload["manifest"]
            if surface == "course"
            else payload["foundations"]["manifest"]
        )
        nested = manifest["capstone"] if surface == "course" else manifest["checkpoint"]
    else:
        path = source / "labs/lab01/lab.json"
        payload = _read_json(path)
        nested = payload["manifest"]["checkpoint"]
    nested["author_notes"] = {PRIVATE_FIELD: PRIVATE_SENTINEL}
    _write_json(path, payload)

    with pytest.raises(SourceValidationError, match=r"unknown field.*author_notes"):
        load_course_source(source)


@pytest.mark.parametrize(
    ("surface", "field_path", "invalid"),
    (*MANIFEST_VALUE_CASES, *MANIFEST_RANGE_CASES, *MANIFEST_UNSAFE_PATH_CASES),
)
def test_split_schema_rejects_malformed_known_manifest_values(
    tmp_path: Path,
    surface: str,
    field_path: tuple[str, ...],
    invalid: Any,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    path, payload, manifest = _split_manifest(source, surface)
    if field_path[0] == "tests" and "tests" not in manifest:
        manifest["tests"] = {
            "public": [],
            "sample": [],
            "hidden": [],
            "submit": [],
        }
    _replace_at(manifest, field_path, invalid)
    _write_json(path, payload)

    with pytest.raises(SourceValidationError):
        load_course_source(source)


@pytest.mark.parametrize(
    ("surface", "field_path", "invalid"),
    (*MANIFEST_VALUE_CASES, *MANIFEST_RANGE_CASES, *MANIFEST_UNSAFE_PATH_CASES),
)
def test_learner_projection_rejects_malformed_known_manifest_values(
    tmp_path: Path,
    surface: str,
    field_path: tuple[str, ...],
    invalid: Any,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    course = load_course_source(source)
    manifest = _loaded_manifest(course, surface)
    if field_path[0] == "tests" and "tests" not in manifest:
        manifest["tests"] = {
            "public": [],
            "sample": [],
            "hidden": [],
            "submit": [],
        }
    _replace_at(manifest, field_path, invalid)

    with pytest.raises(SourceValidationError):
        _manifest(course, learner=True)


def test_split_schema_rejects_outer_foundation_demos_value_tunnel(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    course_path = source / "course.json"
    payload = _read_json(course_path)
    payload["foundations"]["demos"] = [PRIVATE_OBJECT]
    _write_json(course_path, payload)

    with pytest.raises(SourceValidationError):
        load_course_source(source)


def test_learner_projection_rejects_outer_foundation_demos_value_tunnel(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    course = load_course_source(source)
    course.foundation["demos"] = [PRIVATE_OBJECT]

    with pytest.raises(SourceValidationError):
        _manifest(course, learner=True)


def test_split_and_projection_accept_safe_optional_manifest_shapes(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    course_path, course_payload, course_manifest = _split_manifest(source, "course")
    course_manifest.update(
        {
            "adapter": "starter/tools/adapter.py",
            "python": "python3",
            "reference_components": ["reference/components.json"],
        }
    )
    course_manifest["target"]["track"] = None
    foundation_manifest = course_payload["foundations"]["manifest"]
    foundation_manifest.update(
        {
            "demos": ["lab00/examples/demo.py"],
            "examples": ["lab00/examples/example.py"],
            "tests": {
                "public": [],
                "sample": [],
                "hidden": [],
                "submit": [],
            },
        }
    )
    _write_json(course_path, course_payload)

    course = load_course_source(source)
    learner = _manifest(course, learner=True)

    assert learner["adapter"] == "tools/adapter.py"
    assert learner["python"] == "python3"
    assert "reference_components" not in learner
    assert learner["target"]["track"] is None
    assert learner["foundations"]["demos"] == ["lab00/examples/demo.py"]
    assert learner["foundations"]["examples"] == ["lab00/examples/example.py"]


def test_learner_manifest_recursively_allowlists_raw_manifest_fields(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    course = load_course_source(source)
    expected = _manifest(course, learner=True)

    course.course["manifest"]["capstone"]["author_notes"] = {
        PRIVATE_FIELD: PRIVATE_SENTINEL
    }
    course.foundation["manifest"]["checkpoint"]["author_notes"] = {
        PRIVATE_FIELD: PRIVATE_SENTINEL
    }
    course.labs[0].raw["manifest"]["checkpoint"]["author_notes"] = {
        PRIVATE_FIELD: PRIVATE_SENTINEL
    }

    actual = _manifest(course, learner=True)
    compiled = tmp_path / "compiled-manifest-projection"
    _build_tree(course, compiled)
    artifact = _read_json(compiled / "starter/manifest.json")

    assert actual == expected
    assert artifact == expected
    assert PRIVATE_SENTINEL not in json.dumps(actual, ensure_ascii=False)
    assert PRIVATE_SENTINEL not in json.dumps(artifact, ensure_ascii=False)


def test_basic_python_author_rejects_unknown_audience_fields() -> None:
    spec = make_spec()
    spec["course"]["audience"][PRIVATE_FIELD] = PRIVATE_SENTINEL  # type: ignore[index]

    with pytest.raises(
        SpecValidationError,
        match=rf"unknown field.*{PRIVATE_FIELD}",
    ):
        validate_spec(spec)


def test_basic_python_split_source_rejects_unknown_audience_fields(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    course_path = source / "course.json"
    course = _read_json(course_path)
    course["audience"][PRIVATE_FIELD] = PRIVATE_SENTINEL
    course["manifest"]["audience"][PRIVATE_FIELD] = PRIVATE_SENTINEL
    _write_json(course_path, course)

    with pytest.raises(
        SourceValidationError,
        match=rf"unknown field.*{PRIVATE_FIELD}",
    ):
        load_course_source(source)


def test_learner_manifest_recursively_allowlists_basic_python_audience(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    course = load_course_source(source)
    expected = _manifest(course, learner=True)
    course.audience[PRIVATE_FIELD] = PRIVATE_SENTINEL

    actual = _manifest(course, learner=True)

    assert actual == expected
    assert PRIVATE_SENTINEL not in json.dumps(actual, ensure_ascii=False)


@pytest.mark.parametrize(
    "path",
    (
        pytest.param(("labs", 0, "quiz", 0), id="question"),
        pytest.param(("labs", 0, "quiz", 0, "choices", 0), id="choice"),
    ),
)
def test_author_schema_rejects_unknown_quiz_fields(
    path: tuple[str | int, ...],
) -> None:
    spec = make_spec()
    _object_at(spec, path)[PRIVATE_FIELD] = PRIVATE_SENTINEL

    with pytest.raises(
        SpecValidationError,
        match=rf"unknown field.*{PRIVATE_FIELD}",
    ):
        validate_spec(spec)


@pytest.mark.parametrize(
    "path",
    (
        pytest.param(("quiz", 0), id="question"),
        pytest.param(("quiz", 0, "choices", 0), id="choice"),
    ),
)
def test_split_schema_rejects_unknown_quiz_fields(
    tmp_path: Path, path: tuple[str | int, ...]
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    lab_path = source / "labs/lab01/lab.json"
    lab = _read_json(lab_path)
    _object_at(lab, path)[PRIVATE_FIELD] = PRIVATE_SENTINEL
    _write_json(lab_path, lab)

    with pytest.raises(
        SourceValidationError,
        match=rf"unknown field.*{PRIVATE_FIELD}",
    ):
        load_course_source(source)


def test_compiled_learner_knowledge_recursively_allowlists_quiz_fields(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    course = load_course_source(source)
    question = course.labs[0].quiz[0]
    question[PRIVATE_FIELD] = PRIVATE_SENTINEL
    question["choices"][0][PRIVATE_FIELD] = PRIVATE_SENTINEL

    compiled = tmp_path / "compiled"
    _build_tree(course, compiled)
    learner_knowledge = _read_json(compiled / "starter/_course/knowledge.json")

    assert PRIVATE_SENTINEL not in json.dumps(learner_knowledge, ensure_ascii=False)


def test_basic_python_author_rejects_unknown_study_minutes_fields() -> None:
    spec = make_spec()
    spec["labs"][0]["study_minutes"] = {  # type: ignore[index]
        "tier": "standard",
        "min": 30,
        "max": 45,
        PRIVATE_FIELD: PRIVATE_SENTINEL,
    }

    with pytest.raises(
        SpecValidationError,
        match=rf"unknown field.*{PRIVATE_FIELD}",
    ):
        validate_spec(spec)


def test_basic_python_split_source_rejects_unknown_study_minutes_fields(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    lab_path = source / "labs/lab01/lab.json"
    lab = _read_json(lab_path)
    lab["study_minutes"] = {
        "tier": "standard",
        "min": 30,
        "max": 45,
        PRIVATE_FIELD: PRIVATE_SENTINEL,
    }
    _write_json(lab_path, lab)

    with pytest.raises(
        SourceValidationError,
        match=rf"unknown field.*{PRIVATE_FIELD}",
    ):
        load_course_source(source)


def test_learner_content_and_manifest_allowlist_study_minutes(
    tmp_path: Path,
) -> None:
    source = _write_split_source(tmp_path, make_spec)
    course = load_course_source(source)
    course.labs[0].raw["study_minutes"] = {
        "tier": "standard",
        "min": 30,
        "max": 45,
        PRIVATE_FIELD: PRIVATE_SENTINEL,
    }

    learner = {
        "manifest": _manifest(course, learner=True),
        "content": _content(course),
    }

    assert learner["manifest"]["labs"][0]["study_minutes"] == {
        "tier": "standard",
        "min": 30,
        "max": 45,
    }
    assert learner["content"]["labs"][0]["study_minutes"] == {
        "tier": "standard",
        "min": 30,
        "max": 45,
    }
    assert PRIVATE_SENTINEL not in json.dumps(learner, ensure_ascii=False)
