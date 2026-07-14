from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
PLATFORM_ROOT = SKILL_ROOT / "assets" / "course-template" / "platform"
sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(PLATFORM_ROOT))

from scaffold_course import (  # noqa: E402
    copy_template,
    render_course_route,
    replace_template_tokens,
    write_canonical_source,
)
from validate_course import validate_spec  # noqa: E402
from coursekit.compiler import compile_course  # noqa: E402
from tests.course_v2_fixture import make_assessed_spec, make_spec  # noqa: E402


def _compile_assessed(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    spec = validate_spec(make_assessed_spec())
    platform = tmp_path / "platform"
    write_canonical_source(platform, spec)
    output = tmp_path / "compiled"
    compile_course(platform / "course/source", output)
    return spec, output


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _keys_named(value: object, name: str) -> list[object]:
    matches: list[object] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == name:
                matches.append(child)
            matches.extend(_keys_named(child, name))
    elif isinstance(value, list):
        for child in value:
            matches.extend(_keys_named(child, name))
    return matches


def _expected_practice_links(
    concepts: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    *,
    kind: str,
    title_key: str,
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for concept in concepts:
        activity = next(
            item for item in activities if concept["id"] in item["concept_ids"]
        )
        result.append(
            {
                "concept_id": concept["id"],
                "kind": kind,
                "item_id": activity["id"],
                "title": activity[title_key],
            }
        )
    return result


def test_assessed_content_projects_study_time_and_first_practice_in_concept_order(
    tmp_path: Path,
) -> None:
    spec, output = _compile_assessed(tmp_path)
    content = _read_json(output / "content.json")

    units = [
        (spec["foundation"], content["foundations"], "knowledge-check", "quiz", "prompt"),
        *[
            (authored, compiled, "coding-question", "questions", "title")
            for authored, compiled in zip(spec["labs"], content["labs"], strict=True)
        ],
    ]
    for authored, compiled, kind, activity_key, title_key in units:
        assert compiled["study_minutes"] == authored["study_minutes"]
        expected = _expected_practice_links(
            authored["lesson"]["concepts"],
            authored[activity_key],
            kind=kind,
            title_key=title_key,
        )
        assert compiled["practice_links"] == expected
        assert [link["concept_id"] for link in compiled["practice_links"]] == [
            concept["id"] for concept in authored["lesson"]["concepts"]
        ]
        assert all(
            set(link) == {"concept_id", "kind", "item_id", "title"}
            for link in compiled["practice_links"]
        )

    authoring = _read_json(output / "authoring-spec.json")
    assert _keys_named(authoring, "practice_links") == []


def test_assessed_manifests_project_safe_readiness_and_unit_study_time(
    tmp_path: Path,
) -> None:
    spec, output = _compile_assessed(tmp_path)
    profile = spec["course"]["audience"]["prerequisite_profile"]
    expected_readiness = {
        "assumed": [
            item["title"]
            for item in profile["capabilities"]
            if item["decision"] == "assume"
        ],
        "foundation": [
            item["title"]
            for item in profile["capabilities"]
            if item["decision"] == "foundation"
        ],
    }

    for relative in (Path("manifest.json"), Path("starter/manifest.json")):
        manifest = _read_json(output / relative)
        assert manifest["audience"] == spec["course"]["audience"]
        assert manifest["readiness"] == expected_readiness
        assert set(manifest["readiness"]) == {"assumed", "foundation"}
        assert manifest["foundations"]["study_minutes"] == spec["foundation"][
            "study_minutes"
        ]
        for authored, compiled in zip(spec["labs"], manifest["labs"], strict=True):
            assert compiled["study_minutes"] == authored["study_minutes"]

    learner = _read_json(output / "starter/manifest.json")
    assert "reference_root" not in learner
    assert "hidden" not in json.dumps(learner, ensure_ascii=False)


def test_assessed_markdown_renders_open_learning_path_before_deep_dives(
    tmp_path: Path,
) -> None:
    spec, output = _compile_assessed(tmp_path)
    content = _read_json(output / "content.json")
    units = [
        (spec["foundation"], content["foundations"]),
        *zip(spec["labs"], content["labs"], strict=True),
    ]

    for authored, compiled in units:
        markdown = compiled["lesson"]
        study = authored["study_minutes"]
        time_text = f"{study['min']}–{study['max']} 分钟"
        assert time_text in markdown
        if study.get("reason"):
            assert study["reason"] in markdown

        first_concept = authored["lesson"]["concepts"][0]
        contract = first_concept["operational_contract"]
        runnable = next(
            item for item in authored["lesson"]["examples"] if item["kind"] == "runnable"
        )
        first_practice = compiled["practice_links"][0]
        visible_markers = [
            "## 先修知识",
            "## 问题",
            "## 学习目标",
            first_concept["definition"],
            "先这样理解",
            first_concept["mental_model"],
            "输入和输出是什么",
            contract["forms"][0],
            contract["inputs"][0]["meaning"],
            contract["inputs"][0]["example"],
            contract["inputs"][0]["constraints"][0],
            contract["outputs"][0]["meaning"],
            contract["effects"][0],
            contract["failure_modes"][0]["condition"],
            runnable["code"].rstrip(),
            "拿一个具体输入走一遍",
            runnable["trace"][0]["input_state"],
            runnable["trace"][0]["operation"],
            runnable["trace"][0]["output_state"],
            runnable["trace"][0]["explanation"],
            first_practice["title"],
            "## 结课项目衔接",
            "## 总结",
        ]
        positions = [markdown.index(marker) for marker in visible_markers]
        assert positions == sorted(positions)
        assert markdown.index("<details>") > markdown.index(first_practice["title"])
        assert "<summary>运行细节</summary>" in markdown
        assert "<summary>需要保持的条件</summary>" in markdown
        assert "<summary>依据与延伸</summary>" in markdown
        assert "心智模型：" not in markdown
        assert "机制：一步一步发生什么" not in markdown
        assert "始终成立的约束" not in markdown
        assert "`data-model`" not in markdown
        assert "`mechanism`" not in markdown
        assert "（documented）" not in markdown
        assert "（implementation）" not in markdown
        for outcome in authored["lesson"]["outcomes"]:
            assert outcome["id"] not in markdown
        for concept in authored["lesson"]["concepts"]:
            assert concept["id"] not in markdown


def test_assessed_root_readme_summarizes_readiness_and_exact_route_times(
    tmp_path: Path,
) -> None:
    spec = validate_spec(make_assessed_spec())
    copy_template(tmp_path)
    replace_template_tokens(tmp_path, spec)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")

    assert "## 学习准备" in readme
    capabilities = spec["course"]["audience"]["prerequisite_profile"][
        "capabilities"
    ]
    for capability in capabilities:
        assert capability["title"] in readme
        assert capability["id"] not in readme
    assert "课程路线只假设学员掌握 Python 基础" not in readme

    route = render_course_route(spec)
    assert route.startswith("| 顺序 | 本章主题 | 预计用时 |")
    assert "<br>" in route
    assert "&lt;br&gt;" not in route
    for unit in [spec["foundation"], *spec["labs"]]:
        study = unit["study_minutes"]
        expected = f"{study['min']}–{study['max']} 分钟"
        assert expected in route
        if study.get("reason"):
            assert study["reason"] in route
    assert route in readme


def test_legacy_root_readme_keeps_basic_python_copy_and_two_column_route(
    tmp_path: Path,
) -> None:
    spec = validate_spec(make_spec())
    copy_template(tmp_path)
    replace_template_tokens(tmp_path, spec)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    route = render_course_route(spec)

    assert route.startswith("| 顺序 | 本章主题 |\n| --- | --- |")
    assert "预计用时" not in route
    assert "课程路线只假设学员掌握 Python 基础" in readme
    assert "## 学习准备" not in readme
