#!/usr/bin/env python3
"""Reject the retired incremental course-migration workflow."""

from __future__ import annotations

import sys


MESSAGE = (
    "course update failed: incremental migrations are no longer supported; "
    "generate a complete candidate course with the current Skill, then run "
    "regenerate_course.py check COURSE --candidate-course STAGING --json PLAN"
)


def main(argv: list[str] | None = None) -> int:
    del argv
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
