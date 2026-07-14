from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compiler import CourseKitError, compile_course, initialize_workspace


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
    print(f"{args.command}: {len(written)} artifact(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
