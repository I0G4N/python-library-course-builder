#!/usr/bin/env python3
"""Validate and assemble isolated chapter-writer fragments deterministically."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


UNIT_ID_RE = re.compile(r"^(?:lab|prep)\d{2}$")
FRAGMENT_KEYS = frozenset({"unit_id", "tutorial", "lesson", "quiz"})
MANIFEST_KEYS = frozenset({"schema_version", "expected_units"})
EXPECTED_UNIT_KEYS = frozenset({"unit_id", "locked"})


class AssemblyError(ValueError):
    """Raised when a writer fragment violates the parent-owned contract."""


def _load_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AssemblyError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AssemblyError(
            f"{label} {path} is not valid JSON: line {exc.lineno}, column {exc.colno}"
        ) from exc


def _object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssemblyError(f"{label} must be a JSON object")
    return value


def _exact_keys(value: dict[str, Any], expected: frozenset[str], *, label: str) -> None:
    actual = set(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append(f"missing {', '.join(missing)}")
    if extra:
        details.append(
            "parent-owned or unsupported field(s) " + ", ".join(extra)
        )
    raise AssemblyError(f"{label} has invalid fields: {'; '.join(details)}")


def _unit_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or UNIT_ID_RE.fullmatch(value) is None:
        raise AssemblyError(f"{label} must match labNN or prepNN")
    return value


def _decode_pointer_token(token: str) -> str:
    index = 0
    result: list[str] = []
    while index < len(token):
        if token[index] != "~":
            result.append(token[index])
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
            raise AssemblyError(f"invalid JSON Pointer escape in token {token!r}")
        result.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(result)


def _encode_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _pointer(tokens: tuple[str, ...]) -> str:
    return "/" + "/".join(_encode_pointer_token(token) for token in tokens)


def _is_lockable_contract_field(key: str) -> bool:
    """Return whether a writer-owned field carries identity or a mapping."""

    return key == "id" or key == "kind" or key.endswith("_id") or key.endswith("_ids")


def _required_lock_pointers(fragment: dict[str, Any]) -> frozenset[str]:
    """Derive the complete lock allowlist from this fragment's optional shape."""

    required: set[str] = set()

    def visit(value: Any, tokens: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_tokens = (*tokens, key)
                if _is_lockable_contract_field(key):
                    required.add(_pointer(child_tokens))
                visit(child, child_tokens)
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, (*tokens, str(index)))

    visit(fragment["lesson"], ("lesson",))
    visit(fragment["quiz"], ("quiz",))
    if not required:
        raise AssemblyError(
            f"{fragment['unit_id']} has no lockable lesson or quiz identity fields"
        )
    return frozenset(required)


def _resolve_pointer(document: Any, pointer: str, *, label: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise AssemblyError(f"{label} must be a non-empty JSON Pointer")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = _decode_pointer_token(raw_token)
        if isinstance(current, dict):
            if token not in current:
                raise AssemblyError(f"{label} does not resolve: missing object key {token!r}")
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdigit():
                raise AssemblyError(f"{label} does not resolve: {token!r} is not an array index")
            index = int(token)
            if index >= len(current):
                raise AssemblyError(f"{label} does not resolve: array index {index} is out of range")
            current = current[index]
            continue
        raise AssemblyError(f"{label} does not resolve through a scalar value")
    return current


def _json_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return bool(left == right)


def _read_manifest(path: Path) -> tuple[list[str], dict[str, dict[str, Any]]]:
    manifest = _object(_load_json(path, label="manifest"), label="manifest")
    _exact_keys(manifest, MANIFEST_KEYS, label="manifest")
    if manifest["schema_version"] != 1:
        raise AssemblyError("manifest.schema_version must be 1")
    raw_units = manifest["expected_units"]
    if not isinstance(raw_units, list) or not raw_units:
        raise AssemblyError("manifest.expected_units must be a non-empty array")

    ordered_ids: list[str] = []
    locks_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_unit in enumerate(raw_units):
        label = f"manifest.expected_units[{index}]"
        unit = _object(raw_unit, label=label)
        _exact_keys(unit, EXPECTED_UNIT_KEYS, label=label)
        unit_id = _unit_id(unit["unit_id"], label=f"{label}.unit_id")
        if unit_id in locks_by_id:
            raise AssemblyError(f"manifest repeats expected unit {unit_id}")
        locked = _object(unit["locked"], label=f"{label}.locked")
        if not locked:
            raise AssemblyError(f"{label}.locked must not be empty")
        for pointer in locked:
            if not isinstance(pointer, str) or not pointer.startswith("/"):
                raise AssemblyError(
                    f"{label}.locked key {pointer!r} must be a non-empty JSON Pointer"
                )
        ordered_ids.append(unit_id)
        locks_by_id[unit_id] = locked
    return ordered_ids, locks_by_id


def _read_fragment(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise AssemblyError(f"fragment must not be a symlink: {path}")
    fragment = _object(_load_json(path, label="fragment"), label=f"fragment {path}")
    _exact_keys(fragment, FRAGMENT_KEYS, label=f"fragment {path}")
    _unit_id(fragment["unit_id"], label=f"fragment {path}.unit_id")
    tutorial = fragment["tutorial"]
    if not isinstance(tutorial, str) or not tutorial.strip():
        raise AssemblyError(f"fragment {path}.tutorial must be non-empty Markdown")
    lesson = fragment["lesson"]
    if not isinstance(lesson, dict) or not lesson:
        raise AssemblyError(f"fragment {path}.lesson must be a non-empty object")
    quiz = fragment["quiz"]
    if not isinstance(quiz, list) or not quiz:
        raise AssemblyError(f"fragment {path}.quiz must be a non-empty array")
    return fragment


def assemble_fragments(manifest_path: Path, fragments_dir: Path) -> dict[str, Any]:
    """Return a validated assembly ordered exactly like the parent manifest."""

    expected_ids, locks_by_id = _read_manifest(manifest_path)
    try:
        candidates = sorted(
            (path for path in fragments_dir.iterdir() if path.suffix == ".json"),
            key=lambda path: path.name,
        )
    except OSError as exc:
        raise AssemblyError(f"cannot scan fragment directory {fragments_dir}: {exc}") from exc
    if not candidates:
        raise AssemblyError(f"fragment directory contains no JSON fragments: {fragments_dir}")

    fragments_by_id: dict[str, dict[str, Any]] = {}
    sources_by_id: dict[str, Path] = {}
    for path in candidates:
        fragment = _read_fragment(path)
        unit_id = fragment["unit_id"]
        if unit_id in fragments_by_id:
            raise AssemblyError(
                f"duplicate fragment for {unit_id}: {sources_by_id[unit_id]} and {path}"
            )
        fragments_by_id[unit_id] = fragment
        sources_by_id[unit_id] = path

    expected = set(expected_ids)
    actual = set(fragments_by_id)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append(f"missing fragment(s): {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected fragment(s): {', '.join(unexpected)}")
        raise AssemblyError("; ".join(details))

    ordered_fragments: list[dict[str, Any]] = []
    for unit_id in expected_ids:
        fragment = fragments_by_id[unit_id]
        locked = locks_by_id[unit_id]
        required = _required_lock_pointers(fragment)
        supplied = set(locked)
        missing_locks = sorted(required - supplied)
        unknown_locks = sorted(supplied - required)
        if missing_locks or unknown_locks:
            details: list[str] = []
            if missing_locks:
                details.append(
                    "missing required locked pointer(s): " + ", ".join(missing_locks)
                )
            if unknown_locks:
                details.append(
                    "unknown locked pointer(s): " + ", ".join(unknown_locks)
                )
            raise AssemblyError(f"{unit_id} lock set is incomplete: {'; '.join(details)}")
        for pointer, expected_value in locked.items():
            actual_value = _resolve_pointer(
                fragment,
                pointer,
                label=f"{unit_id} locked field {pointer}",
            )
            if not _json_equal(actual_value, expected_value):
                raise AssemblyError(
                    f"{unit_id} changes parent-owned field {pointer}: "
                    f"expected {expected_value!r}, got {actual_value!r}"
                )
        ordered_fragments.append(fragment)

    return {"schema_version": 1, "units": ordered_fragments}


def write_assembly(value: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one clean-context writer fragment per expected course unit."
    )
    parser.add_argument("manifest", type=Path, help="parent-owned unit and lock manifest")
    parser.add_argument("fragments_dir", type=Path, help="directory containing fragment JSON files")
    parser.add_argument("--output", required=True, type=Path, help="assembled JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        assembly = assemble_fragments(args.manifest, args.fragments_dir)
        write_assembly(assembly, args.output)
    except AssemblyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
