from __future__ import annotations

import pytest

from support.coursekit.locale import (
    CATALOGS,
    CourseLanguageError,
    copy_for_manifest,
    localize_detail,
    resolve_language,
)


def test_runtime_locale_resolution_preserves_v2_and_closes_v3() -> None:
    assert resolve_language({"schema_version": 2}) == "zh-CN"
    assert resolve_language({}) == "zh-CN"
    assert resolve_language(
        {"schema_version": 2, "language": "legacy-custom-language"}
    ) == "zh-CN"
    assert resolve_language({"schema_version": 3, "language": "zh-CN"}) == "zh-CN"
    assert resolve_language({"schema_version": 3, "language": "en"}) == "en"
    with pytest.raises(CourseLanguageError, match="language"):
        resolve_language({"schema_version": 3})
    with pytest.raises(CourseLanguageError, match="language"):
        resolve_language({"schema_version": 3, "language": "fr"})
    for invalid_schema in (None, True, "3", 1, 4):
        with pytest.raises(CourseLanguageError, match="schema_version"):
            resolve_language(
                {"schema_version": invalid_schema, "language": "en"}
            )


def test_python_runtime_catalogs_have_identical_keys() -> None:
    assert set(CATALOGS) == {"zh-CN", "en"}
    assert set(CATALOGS["zh-CN"]) == set(CATALOGS["en"])
    assert copy_for_manifest({"schema_version": 3, "language": "zh-CN"})[
        "knowledge_check"
    ] == "知识检查"
    assert copy_for_manifest({"schema_version": 3, "language": "en"})[
        "knowledge_check"
    ] == "Knowledge check"


def test_known_runner_and_cli_details_localize_without_changing_machine_values() -> None:
    zh = CATALOGS["zh-CN"]
    en = CATALOGS["en"]
    source_error = (
        "[coursekit] source policy violation: "
        "lab01/answer.py imports forbidden module 'json' ('json')"
    )
    assert "源码策略违规" in localize_detail(source_error, zh)
    assert "导入了禁止模块" in localize_detail(source_error, zh)
    assert localize_detail(source_error, en) == source_error
    locked = (
        "lab01 is locked: complete prep01 first; "
        "run `course unlock lab01` first"
    )
    assert localize_detail(locked, zh) == (
        "lab01 已锁定：请先完成 prep01；请先运行 `course unlock lab01`"
    )
    assert localize_detail(locked, en) == locked
