from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import verify_learning_project as verifier  # noqa: E402


RAY_UV_FLAG = "RAY_ENABLE_UV_RUN_RUNTIME_ENV"


@pytest.mark.parametrize("provide_environment", [False, True])
def test_verifier_run_disables_ray_uv_propagation_for_every_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provide_environment: bool,
) -> None:
    monkeypatch.setenv(RAY_UV_FLAG, "1")
    provided = dict(os.environ) if provide_environment else None

    completed = verifier.run(
        [sys.executable, "-c", f"import os; print(os.environ[{RAY_UV_FLAG!r}])"],
        cwd=tmp_path,
        env=provided,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "0"
    if provided is not None:
        assert provided[RAY_UV_FLAG] == "1"


def test_python_test_environment_disables_ray_uv_propagation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(RAY_UV_FLAG, "1")

    environment = verifier.python_env(tmp_path)

    assert environment[RAY_UV_FLAG] == "0"
