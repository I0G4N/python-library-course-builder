from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import verify_learning_project as verifier  # noqa: E402


RAY_UV_FLAG = "RAY_ENABLE_UV_RUN_RUNTIME_ENV"


def test_verifier_child_environment_keeps_trusted_overrides_and_drops_secrets(
    tmp_path: Path,
) -> None:
    trusted = {
        "PATH": os.environ["PATH"],
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C.UTF-8",
        "VIRTUAL_ENV": str(tmp_path / ".venv"),
        "PYTHONPATH": str(tmp_path / "support"),
        "COURSEKIT_INTERNAL_RUN": "1",
        "COURSEKIT_RUNNER_URL": "http://127.0.0.1:8123",
        "COURSEKIT_COURSE_DIR": str(tmp_path / "course"),
        "COURSEKIT_WORKSPACE_DIR": str(tmp_path / "labs"),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    inherited = {
        **trusted,
        RAY_UV_FLAG: "1",
        "OPENAI_API_KEY": "openai-secret",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "HF_TOKEN": "hf-secret",
        "UNRELATED_CUSTOM_VALUE": "must-not-leak",
    }
    names = [
        *trusted,
        RAY_UV_FLAG,
        "OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "HF_TOKEN",
        "UNRELATED_CUSTOM_VALUE",
    ]

    completed = verifier.run(
        [
            sys.executable,
            "-c",
            (
                "import json, os; "
                f"print(json.dumps({{name: os.environ.get(name) for name in {names!r}}}))"
            ),
        ],
        cwd=tmp_path,
        env=inherited,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    child = json.loads(completed.stdout)
    assert {name: child[name] for name in trusted} == trusted
    assert child[RAY_UV_FLAG] == "0"
    assert child["OPENAI_API_KEY"] is None
    assert child["AWS_SECRET_ACCESS_KEY"] is None
    assert child["HF_TOKEN"] is None
    assert child["UNRELATED_CUSTOM_VALUE"] is None
    assert inherited[RAY_UV_FLAG] == "1"


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
