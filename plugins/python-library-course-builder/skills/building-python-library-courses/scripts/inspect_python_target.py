#!/usr/bin/env python3
"""Inspect a Python target locally and emit the official-research gate skeleton."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys
import sysconfig
from typing import Any


BROAD_TARGETS = {
    "django",
    "fastapi",
    "flask",
    "numpy",
    "pandas",
    "pytorch",
    "ray",
    "scipy",
    "sqlalchemy",
    "tensorflow",
    "torch",
}


def stdlib_module_names() -> set[str]:
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return set(names)
    # Python 3.9 has no sys.stdlib_module_names. A local filesystem inventory
    # is sufficient for classification; official research remains a later gate.
    result = set(sys.builtin_module_names)
    stdlib = Path(sysconfig.get_paths()["stdlib"])
    try:
        entries = list(stdlib.iterdir())
    except OSError:
        return result
    for entry in entries:
        if entry.name in {"site-packages", "dist-packages", "__pycache__"}:
            continue
        if entry.is_dir() and (entry / "__init__.py").is_file():
            result.add(entry.name)
        elif entry.is_file() and entry.suffix in {".py", ".so", ".pyd"}:
            result.add(entry.stem.split(".", 1)[0])
    return result


def inspect_target(name: str) -> dict[str, Any]:
    module_name = name.replace("-", "_")
    kind = "stdlib" if module_name in stdlib_module_names() else "pypi"
    installed_version = None
    distribution = None
    if kind != "stdlib":
        packages = importlib.metadata.packages_distributions()
        candidates = packages.get(module_name, [name])
        for candidate in candidates:
            try:
                installed_version = importlib.metadata.version(candidate)
                distribution = candidate
                break
            except importlib.metadata.PackageNotFoundError:
                continue
    spec = importlib.util.find_spec(module_name)
    location = spec.origin if spec is not None else None
    breadth = "broad" if module_name.lower() in BROAD_TARGETS else "focused"
    return {
        "name": name,
        "module": module_name,
        "kind": kind,
        "importable": spec is not None,
        "installed_distribution": distribution,
        "installed_version": installed_version,
        "location": location,
        "breadth_hint": breadth,
        "track_required": breadth == "broad",
        "host_python": ".".join(str(value) for value in sys.version_info[:3]),
        "generator_python_supported": (3, 12) <= sys.version_info[:2] < (3, 14),
        "recommended_generator": "uv run --python 3.13 --no-project python",
        "research_gate": {
            "status": "required",
            "instructions": [
                "Confirm the learner's goal and, for broad targets, choose one track.",
                "Browse primary official documentation and the official repository or release notes.",
                "Pin the documented version and record direct URLs before authoring exercises.",
                "Separate stable offline contracts from optional integrations and credentials.",
            ],
            "required_artifacts": [
                "target version basis",
                "official API URLs",
                "concept dependency route",
                "offline deterministic grading boundary",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = inspect_target(args.target)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
