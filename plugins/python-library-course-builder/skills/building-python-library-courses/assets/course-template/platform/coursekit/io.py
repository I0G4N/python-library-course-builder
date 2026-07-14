from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


TOKEN_PATTERN = re.compile(
    r"\{\{[^{}\r\n]+\}\}|__COURSEKIT_[A-Z0-9_]+__"
)
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path}: {error}") from error


def json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()


def safe_relative_path(value: str, *, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or "" in path.parts
    ):
        raise ValueError(f"unsafe {label}: {value!r}")
    for part in path.parts:
        reserved_stem = part.split(".", 1)[0].upper()
        if (
            ":" in part
            or part.endswith((" ", "."))
            or reserved_stem in WINDOWS_RESERVED_NAMES
        ):
            raise ValueError(f"unsafe {label}: {value!r}")
    return path


def unresolved_tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in TOKEN_PATTERN.finditer(text))
