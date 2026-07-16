from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import sys

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from assemble_chapter_fragments import AssemblyError, assemble_fragments, write_assembly  # noqa: E402


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _fragment(unit_id: str) -> dict[str, object]:
    return {
        "unit_id": unit_id,
        "tutorial": f"# {unit_id}\n\nA connected tutorial chapter.",
        "lesson": {
            "concepts": [
                {
                    "id": f"{unit_id}.c1",
                    "name": "A locked concept identity",
                    "definition": "A concrete definition written by this chapter writer.",
                }
            ],
            "outcomes": [{"id": f"{unit_id}.o1", "description": "Trace a value."}],
        },
        "quiz": [
            {
                "id": f"{unit_id}.k1",
                "kind": "execution_trace",
                "prompt": "What happens next?",
                "choices": [{"id": "a", "text": "The declared result."}],
                "answer_id": "a",
                "concept_ids": [f"{unit_id}.c1"],
                "outcome_ids": [f"{unit_id}.o1"],
            }
        ],
    }


def _manifest(*unit_ids: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_units": [
            {
                "unit_id": unit_id,
                "locked": {
                    "/lesson/concepts/0/id": f"{unit_id}.c1",
                    "/lesson/outcomes/0/id": f"{unit_id}.o1",
                    "/quiz/0/id": f"{unit_id}.k1",
                    "/quiz/0/kind": "execution_trace",
                    "/quiz/0/choices/0/id": "a",
                    "/quiz/0/answer_id": "a",
                    "/quiz/0/concept_ids": [f"{unit_id}.c1"],
                    "/quiz/0/outcome_ids": [f"{unit_id}.o1"],
                },
            }
            for unit_id in unit_ids
        ],
    }


def test_assembler_orders_one_fragment_per_expected_unit_and_is_byte_stable(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    _write_json(manifest_path, _manifest("lab00", "prep01", "lab01"))
    _write_json(fragments / "z-lab01.json", _fragment("lab01"))
    _write_json(fragments / "a-lab00.json", _fragment("lab00"))
    _write_json(fragments / "m-prep01.json", _fragment("prep01"))

    assembled = assemble_fragments(manifest_path, fragments)

    assert [unit["unit_id"] for unit in assembled["units"]] == [
        "lab00",
        "prep01",
        "lab01",
    ]
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_assembly(assembled, first)
    write_assembly(assemble_fragments(manifest_path, fragments), second)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().endswith(b"\n")


@pytest.mark.parametrize(
    ("fragments_by_name", "expected_message"),
    [
        ({"lab00.json": _fragment("lab00")}, "missing fragment(s): lab01"),
        (
            {
                "lab00.json": _fragment("lab00"),
                "lab01-a.json": _fragment("lab01"),
                "lab01-b.json": _fragment("lab01"),
            },
            "duplicate fragment for lab01",
        ),
        (
            {
                "lab00.json": _fragment("lab00"),
                "lab01.json": _fragment("lab01"),
                "lab02.json": _fragment("lab02"),
            },
            "unexpected fragment(s): lab02",
        ),
    ],
)
def test_assembler_rejects_missing_duplicate_and_unexpected_fragments(
    tmp_path: Path,
    fragments_by_name: dict[str, dict[str, object]],
    expected_message: str,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    _write_json(manifest_path, _manifest("lab00", "lab01"))
    for filename, fragment in fragments_by_name.items():
        _write_json(fragments / filename, fragment)

    with pytest.raises(AssemblyError, match=re.escape(expected_message)):
        assemble_fragments(manifest_path, fragments)


def test_assembler_rejects_parent_owned_top_level_and_locked_field_mutation(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, _manifest("lab00"))

    fragments = tmp_path / "extra-field"
    fragments.mkdir()
    extra_field = _fragment("lab00")
    extra_field["official_sources"] = ["writer-must-not-change-this"]
    _write_json(fragments / "lab00.json", extra_field)
    with pytest.raises(AssemblyError, match="parent-owned or unsupported field"):
        assemble_fragments(manifest_path, fragments)

    mutated_fragments = tmp_path / "locked-mutation"
    mutated_fragments.mkdir()
    mutation = deepcopy(_fragment("lab00"))
    mutation["lesson"]["concepts"][0]["id"] = "lab00.writer-changed-id"  # type: ignore[index]
    _write_json(mutated_fragments / "lab00.json", mutation)
    with pytest.raises(AssemblyError, match="changes parent-owned field"):
        assemble_fragments(manifest_path, mutated_fragments)


def test_assembler_rejects_empty_lock_map(tmp_path: Path) -> None:
    manifest = _manifest("lab00")
    manifest["expected_units"][0]["locked"] = {}  # type: ignore[index]
    manifest_path = tmp_path / "manifest.json"
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    _write_json(manifest_path, manifest)
    _write_json(fragments / "lab00.json", _fragment("lab00"))

    with pytest.raises(
        AssemblyError,
        match=r"manifest\.expected_units\[0\]\.locked must not be empty",
    ):
        assemble_fragments(manifest_path, fragments)


def test_assembler_rejects_incomplete_lock_map_for_each_unit(tmp_path: Path) -> None:
    manifest = _manifest("lab00", "lab01")
    del manifest["expected_units"][1]["locked"]["/quiz/0/answer_id"]  # type: ignore[index]
    manifest_path = tmp_path / "manifest.json"
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    _write_json(manifest_path, manifest)
    _write_json(fragments / "lab00.json", _fragment("lab00"))
    _write_json(fragments / "lab01.json", _fragment("lab01"))

    with pytest.raises(
        AssemblyError,
        match=(
            r"lab01 lock set is incomplete: missing required locked pointer\(s\): "
            r"/quiz/0/answer_id"
        ),
    ):
        assemble_fragments(manifest_path, fragments)


def test_assembler_rejects_unknown_lock_pointer(tmp_path: Path) -> None:
    manifest = _manifest("lab00")
    manifest["expected_units"][0]["locked"][  # type: ignore[index]
        "/lesson/concepts/0/name"
    ] = "A locked concept identity"
    manifest_path = tmp_path / "manifest.json"
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    _write_json(manifest_path, manifest)
    _write_json(fragments / "lab00.json", _fragment("lab00"))

    with pytest.raises(
        AssemblyError,
        match=r"unknown locked pointer\(s\): /lesson/concepts/0/name",
    ):
        assemble_fragments(manifest_path, fragments)


def test_optional_fragment_collections_contribute_required_locks_when_present(
    tmp_path: Path,
) -> None:
    fragment = _fragment("lab00")
    fragment["lesson"]["examples"] = [  # type: ignore[index]
        {
            "id": "lab00.e1",
            "kind": "runnable",
            "concept_ids": ["lab00.c1"],
            "outcome_ids": ["lab00.o1"],
            "trace": [{"id": "lab00.t1", "concept_ids": ["lab00.c1"]}],
        }
    ]
    manifest_path = tmp_path / "manifest.json"
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    _write_json(manifest_path, _manifest("lab00"))
    _write_json(fragments / "lab00.json", fragment)

    with pytest.raises(AssemblyError) as exc_info:
        assemble_fragments(manifest_path, fragments)

    message = str(exc_info.value)
    for pointer in (
        "/lesson/examples/0/id",
        "/lesson/examples/0/kind",
        "/lesson/examples/0/concept_ids",
        "/lesson/examples/0/outcome_ids",
        "/lesson/examples/0/trace/0/id",
        "/lesson/examples/0/trace/0/concept_ids",
    ):
        assert pointer in message


def test_skill_requires_one_clean_context_writer_per_unit_and_clean_replacements() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    contract = (SKILL_ROOT / "references/chapter-writer-contract.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        'fork_turns="none"',
        "Never reuse a writer for another unit",
        "one-writer/one-unit boundary",
        "exactly `unit_id`, `tutorial`, `lesson`, and `quiz`",
        "replacement sanitized packet",
        "whole-course reviewer",
        "If the environment cannot create clean-context sub-agents, stop",
    ):
        assert phrase in contract
    assert "one sanitized packet per `lab00`, `prepNN`, and `labNN`" in skill
    assert "assemble_chapter_fragments.py" in skill


def test_examples_model_subject_driven_tutorials_without_diagnostic_framing() -> None:
    examples = {
        "zh-CN": (
            SKILL_ROOT / "references/complete-teaching-example.zh-CN.md"
        ).read_text(encoding="utf-8"),
        "en": (
            SKILL_ROOT / "references/complete-teaching-example.en.md"
        ).read_text(encoding="utf-8"),
    }

    for forbidden in (
        "已有证据与本章边界",
        "只补证据指向的缺口",
        "你已经会什么",
        "Existing evidence and chapter boundary",
        "teach only evidence-backed gaps",
        "What you already know",
        "#### Define the term",
        "#### 先把术语说清楚",
    ):
        assert all(forbidden not in example for example in examples.values())

    assert "#### 缺键并不等于返回 `None`" in examples["zh-CN"]
    assert "### 跟着 `enabled` 走过两扇门" in examples["zh-CN"]
    assert "#### A missing key is not `None`" in examples["en"]
    assert "### Follow `enabled` through both gates" in examples["en"]
