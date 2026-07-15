"""Manifest helpers shared by the CLI and pytest plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "manifest.json"


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or MANIFEST_PATH).read_text(encoding="utf-8"))


def schema_version(manifest: dict[str, Any] | None = None) -> int:
    value = manifest or load_manifest()
    configured = value.get("schema_version", 2)
    return configured if type(configured) is int else 2


def preparatory_units(
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return ordered, knowledge-only units for either curriculum schema."""

    value = manifest or load_manifest()
    if schema_version(value) >= 3:
        configured = value.get("preparatory_units", [])
        if not isinstance(configured, list):
            raise ValueError("manifest preparatory_units must be a list")
        return [item for item in configured if isinstance(item, dict)]
    item = value.get("foundations")
    return [item] if isinstance(item, dict) else []


def foundation(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    value = manifest or load_manifest()
    units = preparatory_units(value)
    item = units[0] if units else None
    if not isinstance(item, dict) or str(item.get("id")) != "lab00":
        raise ValueError("manifest has no foundation")
    return item


def formal_labs(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    value = manifest or load_manifest()
    return [item for item in value.get("labs", []) if isinstance(item, dict)]


def ordered_units(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    value = manifest or load_manifest()
    return [*preparatory_units(value), *formal_labs(value)]


def is_preparatory_unit(
    item_or_id: dict[str, Any] | str,
    manifest: dict[str, Any] | None = None,
) -> bool:
    value = manifest or load_manifest()
    item_id = (
        str(item_or_id.get("id"))
        if isinstance(item_or_id, dict)
        else str(item_or_id)
    )
    return item_id in {
        str(item.get("id")) for item in preparatory_units(value)
    }


def find_unit(
    unit_id: str, manifest: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    value = manifest or load_manifest()
    return next(
        (item for item in ordered_units(value) if str(item.get("id")) == unit_id),
        None,
    )


def find_lab(lab_id: str, manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Backward-compatible name for finding any navigable curriculum unit."""

    return find_unit(lab_id, manifest)


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
