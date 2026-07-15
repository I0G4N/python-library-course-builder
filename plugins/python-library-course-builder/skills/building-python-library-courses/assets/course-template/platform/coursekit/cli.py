from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compiler import CourseKitError, compile_course, initialize_workspace
from support.coursekit.locale import CourseLanguageError, copy_for_manifest, render


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coursekit")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "check"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path)
        command.add_argument("output", type=Path)
    initialize = commands.add_parser("init-workspace")
    initialize.add_argument("compiled", type=Path)
    initialize.add_argument("target", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init-workspace":
            written = initialize_workspace(args.compiled, args.target)
        else:
            report = compile_course(
                args.source, args.output, check=args.command == "check"
            )
            written = list(report.written)
    except CourseKitError as error:
        print(error, file=sys.stderr)
        return 1
    manifest_path = (
        args.compiled / "manifest.json"
        if args.command == "init-workspace"
        else args.source / "course.json"
    )
    try:
        configured = json.loads(manifest_path.read_text(encoding="utf-8"))
        copy = copy_for_manifest(configured)
    except CourseLanguageError as error:
        print(error, file=sys.stderr)
        return 2
    except (OSError, ValueError, json.JSONDecodeError):
        copy = copy_for_manifest({"schema_version": 2})
    print(render(copy, "artifacts_written", command=args.command, count=len(written)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
