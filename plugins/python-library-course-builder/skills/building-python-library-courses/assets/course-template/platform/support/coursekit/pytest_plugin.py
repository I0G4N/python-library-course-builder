"""Prevent direct pytest runs from bypassing the knowledge unlock gate."""

from __future__ import annotations

import os
import re

import pytest

from .progress import gate_reasons


def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if os.environ.get("COURSEKIT_INTERNAL_RUN") == "1":
        return
    labs = sorted(
        {
            match.group(1)
            for item in items
            if (match := re.search(r"(?:^|/)(lab\d{2})/tests/", item.nodeid.replace("\\", "/")))
        }
    )
    reasons = list(dict.fromkeys(reason for lab_id in labs for reason in gate_reasons(lab_id)))
    if reasons:
        pytest.exit("CourseKit test gate:\n- " + "\n- ".join(reasons), returncode=4)
