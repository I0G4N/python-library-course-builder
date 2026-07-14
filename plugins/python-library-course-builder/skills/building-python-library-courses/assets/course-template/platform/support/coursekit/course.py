"""Manifest helpers shared by the CLI and pytest plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "manifest.json"


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or MANIFEST_PATH).read_text(encoding="utf-8"))


def foundation(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    value = manifest or load_manifest()
    item = value.get("foundations")
    if not isinstance(item, dict):
        raise ValueError("manifest has no foundation")
    return item


def formal_labs(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    value = manifest or load_manifest()
    return [item for item in value.get("labs", []) if isinstance(item, dict)]


def find_lab(lab_id: str, manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
    value = manifest or load_manifest()
    base = foundation(value)
    if str(base.get("id")) == lab_id:
        return base
    return next((lab for lab in formal_labs(value) if str(lab.get("id")) == lab_id), None)


def select_item(
    item_id: str, manifest: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    value = manifest or load_manifest()
    lab = find_lab(item_id, value)
    if lab is not None:
        return lab, None
    for candidate in formal_labs(value):
        for question in candidate.get("questions", []):
            if isinstance(question, dict) and str(question.get("id")) == item_id:
                return candidate, question
    raise LookupError(f"unknown Lab or question: {item_id}")


def public_targets(configured: dict[str, Any]) -> list[str]:
    tests = configured.get("tests", {})
    if not isinstance(tests, dict):
        return []
    for key in ("public", "sample", "submit"):
        values = tests.get(key)
        if isinstance(values, list) and values:
            return [str(value) for value in values]
    return []


def targets_for_item(lab: dict[str, Any], question: dict[str, Any] | None) -> list[str]:
    if question is not None:
        return public_targets(question)
    values: list[str] = []
    for configured in lab.get("questions", []):
        if isinstance(configured, dict):
            values.extend(public_targets(configured))
    return deduplicate(values or public_targets(lab))


def deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def all_questions(
    manifest: dict[str, Any] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    result = []
    for lab in formal_labs(manifest):
        result.extend(
            (lab, question)
            for question in lab.get("questions", [])
            if isinstance(question, dict)
        )
    return result
