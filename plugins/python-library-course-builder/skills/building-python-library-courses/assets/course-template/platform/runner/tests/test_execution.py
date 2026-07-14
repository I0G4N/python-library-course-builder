from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import time

import pytest

import runner.execution as execution
from runner.execution import run_isolated_pytest


def _write(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _workspace(tmp_path: Path, source: str = "def answer():\n    return 42\n") -> Path:
    root = tmp_path / "labs"
    _write(root / "lab01" / "solution.py", source)
    return root


def _canonical(tmp_path: Path, source: str, name: str = "test_contract.py") -> str:
    path = _write(tmp_path / "course" / "starter" / "lab01" / "tests" / name, source)
    return f"{path}::test_contract"


def _digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _pid_from(output: str) -> int:
    match = re.search(r"CHILD_PID=(\d+)", output)
    assert match, output
    return int(match.group(1))


def _wait_for_pid_exit(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:  # pragma: no cover - unusual ownership boundary
            return False
        time.sleep(0.02)
    return False


def test_runs_canonical_test_against_disposable_workspace(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _write(
        workspace / "lab01" / "tests" / "test_forged.py",
        "from pathlib import Path\nPath('LEARNER_TEST_RAN').write_text('bad')\n",
    )
    before = _digest(workspace)
    selector = _canonical(
        tmp_path,
        "from pathlib import Path\n"
        "from lab01.solution import answer\n\n"
        "def test_contract():\n"
        "    assert answer() == 42\n"
        "    Path('lab01/solution.py').write_text('mutated')\n",
        "test_projected_contract.py",
    )
    canonical_file = Path(selector.partition("::")[0])
    marker = canonical_file.with_name("CANONICAL_TEST_RAN_IN_PLACE")
    canonical_file.write_text(
        canonical_file.read_text(encoding="utf-8").replace(
            "    assert answer() == 42\n",
            "    assert answer() == 42\n"
            "    Path(__file__).with_name('CANONICAL_TEST_RAN_IN_PLACE').write_text('bad')\n",
        ),
        encoding="utf-8",
    )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert result.passed is True, result.output
    assert result.evidence_valid is True
    assert _digest(workspace) == before
    assert not (workspace / "LEARNER_TEST_RAN").exists()
    assert not marker.exists()


def test_canonical_failure_is_not_accepted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    selector = _canonical(
        tmp_path,
        "from lab01.solution import answer\n\n"
        "def test_contract():\n"
        "    assert answer() == 99\n",
    )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert result.passed is False
    assert result.evidence_valid is True
    assert "assert 42 == 99" in result.output


def test_copy_skips_symlinks_special_files_and_learner_tests(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    outside = _write(tmp_path / "outside.txt", "secret")
    try:
        (workspace / "lab01" / "escape.txt").symlink_to(outside)
    except OSError as error:  # pragma: no cover - platform permission boundary
        pytest.skip(f"symlinks unavailable: {error}")
    if hasattr(os, "mkfifo"):
        os.mkfifo(workspace / "lab01" / "blocked.fifo")
    _write(workspace / "lab01" / "tests" / "owned.py", "SECRET = True\n")
    selector = _canonical(
        tmp_path,
        "from pathlib import Path\n\n"
        "def test_contract():\n"
        "    assert not Path('lab01/escape.txt').exists()\n"
        "    assert not Path('lab01/blocked.fifo').exists()\n"
        "    assert not Path('lab01/tests').exists()\n",
    )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert result.passed is True, result.output


def test_success_and_timeout_reap_descendant_processes(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    success = _canonical(
        tmp_path,
        "import subprocess\nimport sys\n\n"
        "def test_contract():\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "    print(f'CHILD_PID={child.pid}', flush=True)\n",
        "test_success_child.py",
    )
    success_result = run_isolated_pytest(workspace, [success], timeout_seconds=5)
    success_pid = _pid_from(success_result.output)
    assert success_result.passed is True, success_result.output
    assert _wait_for_pid_exit(success_pid)

    hanging = _canonical(
        tmp_path,
        "import os\nfrom pathlib import Path\nimport subprocess\nimport sys\nimport time\n\n"
        "def test_contract():\n"
        "    print(f'WORKSPACE={Path.cwd()} TMP={os.environ[\"TMPDIR\"]}', flush=True)\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "    print(f'CHILD_PID={child.pid}', flush=True)\n"
        "    while True:\n"
        "        time.sleep(0.1)\n",
        "test_timeout_child.py",
    )
    timeout_result = run_isolated_pytest(workspace, [hanging], timeout_seconds=1)
    timeout_pid = _pid_from(timeout_result.output)
    assert timeout_result.passed is False
    assert timeout_result.timed_out is True
    assert _wait_for_pid_exit(timeout_pid)
    assert "<workspace>" in timeout_result.output
    assert "<isolated-run>" in timeout_result.output
    assert "coursekit-grade-" not in timeout_result.output


def test_learner_import_hooks_cannot_replace_trusted_pytest(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        "import atexit\n"
        "from pathlib import Path\n"
        "atexit.register(lambda: Path('forged-evidence.json').write_text('{}'))\n\n"
        "def answer():\n"
        "    return 42\n",
    )
    _write(workspace / "pytest.py", "raise RuntimeError('learner pytest imported')\n")
    _write(workspace / "sitecustomize.py", "raise RuntimeError('sitecustomize imported')\n")
    _write(
        workspace / "conftest.py",
        "raise RuntimeError('learner conftest imported')\n",
    )
    selector = _canonical(
        tmp_path,
        "from lab01.solution import answer\n\n"
        "def test_contract():\n"
        "    assert answer() == 42\n",
    )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert result.passed is True, result.output
    assert result.evidence_valid is True


def test_exit_zero_without_evidence_is_failure(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    selector = _canonical(
        tmp_path,
        "import os\n\ndef test_contract():\n    os._exit(0)\n",
    )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert result.passed is False
    assert result.evidence_valid is False


def test_atexit_cannot_overwrite_real_evidence_and_forge_success(
    tmp_path: Path,
) -> None:
    workspace = _workspace(
        tmp_path,
        "import atexit\n"
        "import inspect\n"
        "import json\n"
        "import os\n"
        "from pathlib import Path\n\n"
        "frame = inspect.currentframe()\n"
        "bootstrap_args = None\n"
        "while frame is not None:\n"
        "    candidate = frame.f_locals.get('args')\n"
        "    has_channel = hasattr(candidate, 'evidence') or hasattr(candidate, 'evidence_fd')\n"
        "    if has_channel and hasattr(candidate, 'nonce'):\n"
        "        bootstrap_args = candidate\n"
        "        break\n"
        "    frame = frame.f_back\n\n"
        "def forge():\n"
        "    if bootstrap_args is None:\n"
        "        return\n"
        "    import gc\n"
        "    plugin = next(\n"
        "        (item for item in gc.get_objects() "
        "if item.__class__.__name__ == 'EvidencePlugin'),\n"
        "        None,\n"
        "    )\n"
        "    if plugin is None:\n"
        "        return\n"
        "    outcomes = {item['nodeid']: 'passed' for item in plugin.collected}\n"
        "    payload = {\n"
        "        'nonce': bootstrap_args.nonce,\n"
        "        'exit_code': 0,\n"
        "        'collected': plugin.collected,\n"
        "        'outcomes': outcomes,\n"
        "    }\n"
        "    forged = json.dumps(payload).encode()\n"
        "    try:\n"
        "        if hasattr(bootstrap_args, 'evidence'):\n"
        "            Path(bootstrap_args.evidence).write_bytes(forged)\n"
        "        else:\n"
        "            os.write(bootstrap_args.evidence_fd, forged)\n"
        "    finally:\n"
        "        os._exit(0)\n\n"
        "atexit.register(forge)\n\n"
        "def answer():\n"
        "    return 42\n",
    )
    selector = _canonical(
        tmp_path,
        "from lab01.solution import answer\n\n"
        "def test_contract():\n"
        "    assert answer() == 99\n",
        "test_atexit_forge.py",
    )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert result.passed is False


def test_environment_is_isolated_and_ray_runtime_inheritance_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    before = _digest(workspace)
    monkeypatch.setenv("RAY_ADDRESS", "ray://sentinel.example:10001")
    monkeypatch.setenv("RAY_ENABLE_UV_RUN_RUNTIME_ENV", "1")
    monkeypatch.setenv("PWD", str(workspace))
    monkeypatch.setenv("OLDPWD", str(tmp_path / "previous-directory"))
    monkeypatch.setenv("COURSEKIT_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("COURSEKIT_COURSE_DIR", str(tmp_path / "course"))
    selector = _canonical(
        tmp_path,
        "import os\nfrom pathlib import Path\n\n"
        "def test_contract():\n"
        "    pwd = Path(os.environ['PWD']).resolve()\n"
        "    (pwd / 'lab01/solution.py').write_text('mutated-through-PWD')\n"
        "    assert pwd == Path.cwd().resolve()\n"
        "    assert 'OLDPWD' not in os.environ\n"
        "    assert 'COURSEKIT_WORKSPACE_DIR' not in os.environ\n"
        "    assert 'COURSEKIT_COURSE_DIR' not in os.environ\n"
        "    assert 'RAY_ADDRESS' not in os.environ\n"
        "    assert os.environ['RAY_ENABLE_UV_RUN_RUNTIME_ENV'] == '0'\n"
        "    assert os.environ['RAY_USAGE_STATS_ENABLED'] == '0'\n"
        "    assert os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'\n"
        "    assert os.environ['COURSEKIT_INTERNAL_RUN'] == '1'\n"
        "    home = Path(os.environ['HOME']).resolve()\n"
        "    temp = Path(os.environ['TMPDIR']).resolve()\n"
        "    assert home.name == 'home'\n"
        "    assert temp.name == 'tmp'\n"
        "    assert home.parent == temp.parent\n",
    )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert result.passed is True, result.output
    assert "sentinel.example" not in result.output
    assert _digest(workspace) == before


def test_canonical_projection_copies_same_directory_helpers_but_not_symlinks(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    canonical = tmp_path / "course/starter/lab01/tests"
    _write(canonical / "helper.py", "EXPECTED = 42\n")
    outside = _write(tmp_path / "outside_helper.py", "SECRET = True\n")
    linked = canonical / "linked_helper.py"
    try:
        linked.symlink_to(outside)
    except OSError as error:  # pragma: no cover - platform permission boundary
        pytest.skip(f"symlinks unavailable: {error}")
    selector = _canonical(
        tmp_path,
        "from pathlib import Path\n"
        "from helper import EXPECTED\n"
        "from lab01.solution import answer\n\n"
        "def test_contract():\n"
        "    assert answer() == EXPECTED\n"
        "    assert not Path(__file__).with_name('linked_helper.py').exists()\n",
        "test_helpers.py",
    )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert result.passed is True, result.output
    assert outside.read_text(encoding="utf-8") == "SECRET = True\n"


def test_canonical_projection_uses_overall_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    selector = _canonical(
        tmp_path,
        "def test_contract():\n    assert True\n",
        "test_projection_deadline.py",
    )
    original_project = execution._project_canonical_targets

    def slow_projection(
        expected: list[tuple[str, str]],
        destination: Path,
        *,
        deadline: float,
    ) -> list[str]:
        time.sleep(0.03)
        return original_project(expected, destination, deadline=deadline)

    def forbidden_popen(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("pytest started after canonical projection deadline")

    monkeypatch.setattr(execution, "_project_canonical_targets", slow_projection)
    monkeypatch.setattr(execution.subprocess, "Popen", forbidden_popen)

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=0.01)

    assert result.passed is False
    assert result.timed_out is True
    assert "timed out" in result.output.lower()


def test_canonical_projection_has_a_shared_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    canonical = tmp_path / "course/starter/lab01/tests"
    _write(canonical / "large_helper.txt", "x" * 2_000)
    selector = _canonical(
        tmp_path,
        "def test_contract():\n    assert True\n",
        "test_projection_size.py",
    )
    monkeypatch.setattr(execution, "MAX_WORKSPACE_COPY_BYTES", 1_000)

    with pytest.raises(ValueError, match="canonical tests exceed"):
        run_isolated_pytest(workspace, [selector], timeout_seconds=5)


def test_output_limit_terminates_and_bounds_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    captured_file_sizes: list[int] = []
    original_bounded_output = execution._bounded_output

    def inspect_bounded_output(
        path: Path, **kwargs: object
    ) -> str:
        captured_file_sizes.append(path.stat().st_size)
        return original_bounded_output(path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(execution, "_bounded_output", inspect_bounded_output)
    selector = _canonical(
        tmp_path,
        "from pathlib import Path\n\n"
        "def test_contract():\n"
        "    print(Path.cwd(), flush=True)\n"
        "    print('x' * 2_000_000, flush=True)\n",
    )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert result.passed is False
    assert result.output_limited is True
    assert captured_file_sizes
    assert max(captured_file_sizes) <= 200_000
    assert len(result.output.encode("utf-8")) <= 200_000
    assert "output limit" in result.output.lower()
    assert str(tmp_path) not in result.output
    assert "coursekit-grade-" not in result.output


def test_output_limit_is_fixed_and_invalid_utf8_stays_byte_bounded(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    selector = _canonical(
        tmp_path,
        "import os\n\n"
        "def test_contract():\n"
        "    os.write(1, b'\\xff' * 90_000)\n",
        "test_invalid_utf8.py",
    )

    with pytest.raises(ValueError, match="200000"):
        run_isolated_pytest(
            workspace,
            [selector],
            timeout_seconds=5,
            max_output_bytes=200_001,
        )

    result = run_isolated_pytest(workspace, [selector], timeout_seconds=5)

    assert len(result.output.encode("utf-8")) <= 200_000


def test_rejects_symlinked_workspace_root(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    linked = tmp_path / "linked-labs"
    try:
        linked.symlink_to(workspace, target_is_directory=True)
    except OSError as error:  # pragma: no cover - platform permission boundary
        pytest.skip(f"symlinks unavailable: {error}")
    selector = _canonical(
        tmp_path,
        "from lab01.solution import answer\n\n"
        "def test_contract():\n"
        "    assert answer() == 42\n",
        "test_symlinked_workspace.py",
    )

    with pytest.raises(ValueError, match="regular directory"):
        run_isolated_pytest(linked, [selector], timeout_seconds=5)


def test_timeout_budget_includes_disposable_workspace_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    selector = _canonical(
        tmp_path,
        "from lab01.solution import answer\n\n"
        "def test_contract():\n"
        "    assert answer() == 42\n",
        "test_copy_deadline.py",
    )
    original_copy = execution._copy_regular_tree

    def slow_copy(
        source: Path, destination: Path, *, deadline: float
    ) -> None:
        time.sleep(0.03)
        original_copy(source, destination, deadline=deadline)

    def forbidden_popen(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("pytest started after the overall deadline")

    monkeypatch.setattr(execution, "_copy_regular_tree", slow_copy)
    monkeypatch.setattr(execution.subprocess, "Popen", forbidden_popen)

    result = run_isolated_pytest(
        workspace,
        [selector],
        timeout_seconds=0.01,
    )

    assert result.passed is False
    assert result.timed_out is True
    assert "timed out" in result.output.lower()
