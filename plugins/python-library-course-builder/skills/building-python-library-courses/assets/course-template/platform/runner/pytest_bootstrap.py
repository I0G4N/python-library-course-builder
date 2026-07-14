"""Trusted isolated pytest entrypoint used by the local CourseKit Runner."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest


class EvidencePlugin:
    def __init__(self) -> None:
        self.collected: list[dict[str, str]] = []
        self.outcomes: dict[str, str] = {}

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.collected = [
            {
                "nodeid": item.nodeid,
                "path": str(Path(str(item.path)).resolve()),
            }
            for item in session.items
        ]

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "call":
            self.outcomes[report.nodeid] = report.outcome


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--evidence-fd", required=True, type=int)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--target", action="append", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # Remove transport details from ordinary argv inspection before learner
    # code is imported. The parent validates the one-shot pipe payload.
    sys.argv = [sys.argv[0]]
    workspace = str(Path(args.workspace).resolve())
    if workspace not in sys.path:
        sys.path.insert(0, workspace)

    plugin = EvidencePlugin()
    exit_code = int(
        pytest.main(
            ["-q", "-s", "--noconftest", *args.target],
            plugins=[plugin],
        )
    )
    payload: dict[str, Any] = {
        "nonce": args.nonce,
        "exit_code": exit_code,
        "collected": plugin.collected,
        "outcomes": plugin.outcomes,
    }
    evidence = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    with os.fdopen(args.evidence_fd, "wb", closefd=True) as handle:
        handle.write(evidence)
        handle.flush()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
