"""Disposable, process-safe pytest execution for schema-v4 CourseKit."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from types import MappingProxyType
from typing import Any, BinaryIO, Mapping


MAX_OUTPUT_BYTES = 200_000
MAX_EVIDENCE_BYTES = 1_000_000
MAX_COPY_BYTES = 64_000_000
COPY_CHUNK_BYTES = 65_536
_SAFE_ENVIRONMENT_NAMES = frozenset(
    {
        "COMSPEC",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "VIRTUAL_ENV",
        "WINDIR",
    }
)
_SKIP_WORKSPACE_NAMES = {
    ".coursekit",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coursekit_runtime",
    "dist",
    "node_modules",
    "tests",
}
_SKIP_TEST_NAMES = _SKIP_WORKSPACE_NAMES | {"solution"}


@dataclass(frozen=True)
class PytestRunResult:
    passed: bool
    output: str
    timed_out: bool
    output_limited: bool
    evidence_valid: bool
    returncode: int | None
    collected: tuple[str, ...] = ()
    outcomes: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )


class _DeadlineExceeded(RuntimeError):
    """A trusted copy or execution step exhausted the shared run deadline."""


def safe_subprocess_environment(inherited: Mapping[str, str]) -> dict[str, str]:
    """Keep only OS, locale, path, and virtual-environment process settings."""

    if os.name != "nt":
        return {
            name: inherited[name]
            for name in _SAFE_ENVIRONMENT_NAMES
            if name in inherited
        }
    result: dict[str, str] = {}
    upper = {name.upper(): value for name, value in inherited.items()}
    for name in _SAFE_ENVIRONMENT_NAMES:
        if name in upper:
            result[name] = upper[name]
    return result


def _check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise _DeadlineExceeded


def _copy_tree(
    source: Path,
    destination: Path,
    *,
    deadline: float,
    skip_names: set[str],
    byte_budget: list[int],
) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("source must be a regular directory")
    destination.mkdir(parents=True, exist_ok=False)
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        _check_deadline(deadline)
        if child.name in skip_names or child.is_symlink():
            continue
        target = destination / child.name
        try:
            if child.is_dir():
                _copy_tree(
                    child,
                    target,
                    deadline=deadline,
                    skip_names=skip_names,
                    byte_budget=byte_budget,
                )
            elif child.is_file():
                with child.open("rb") as source_handle, target.open(
                    "xb"
                ) as target_handle:
                    while True:
                        _check_deadline(deadline)
                        chunk = source_handle.read(COPY_CHUNK_BYTES)
                        if not chunk:
                            break
                        byte_budget[0] += len(chunk)
                        if byte_budget[0] > MAX_COPY_BYTES:
                            raise ValueError(
                                "grading inputs exceed the 64000000-byte copy limit"
                            )
                        target_handle.write(chunk)
        except (_DeadlineExceeded, ValueError):
            raise
        except OSError:
            # FIFOs, sockets, unreadable entries, and disappearing learner files
            # never become part of the trusted disposable workspace.
            continue


def _expected_targets(targets: list[str]) -> list[tuple[str, str]]:
    expected: list[tuple[str, str]] = []
    for target in targets:
        path, separator, node = target.partition("::")
        source = Path(path)
        if (
            not separator
            or not node
            or source.is_symlink()
            or not source.is_file()
        ):
            raise ValueError(
                f"canonical pytest target must name one regular test: {target}"
            )
        expected.append((str(source.resolve()), node))
    if not expected:
        raise ValueError("at least one canonical pytest target is required")
    return expected


def _project_targets(
    expected: list[tuple[str, str]],
    destination: Path,
    *,
    deadline: float,
) -> list[str]:
    destination.mkdir(parents=True, exist_ok=False)
    projected_parents: dict[Path, Path] = {}
    budget = [0]
    result: list[str] = []
    for source_text, node in expected:
        _check_deadline(deadline)
        source = Path(source_text)
        parent = source.parent
        projected_parent = projected_parents.get(parent)
        if projected_parent is None:
            if parent.is_symlink() or not parent.is_dir():
                raise ValueError("canonical test parent must be a regular directory")
            projected_parent = destination / f"{len(projected_parents):04d}"
            _copy_tree(
                parent,
                projected_parent,
                deadline=deadline,
                skip_names=_SKIP_TEST_NAMES,
                byte_budget=budget,
            )
            projected_parents[parent] = projected_parent
        projected = projected_parent / source.name
        if projected.is_symlink() or not projected.is_file():
            raise ValueError(
                f"canonical pytest target could not be projected: {source}"
            )
        result.append(f"{projected.resolve()}::{node}")
    return result


def _group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - unexpected ownership boundary
        return True
    return True


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":  # pragma: no cover - exercised in shared runtime CI
        try:
            process.terminate()
            process.wait(timeout=0.75)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait(timeout=1)
        return
    process_group = process.pid
    try:
        os.killpg(process_group, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + 0.75
    while _group_exists(process_group) and time.monotonic() < deadline:
        time.sleep(0.02)
    if _group_exists(process_group):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:  # pragma: no cover
        process.kill()
        process.wait(timeout=1)


def _capture_output(
    stream: BinaryIO,
    destination: Path,
    *,
    limit: int,
    limited: threading.Event,
) -> None:
    stored = 0
    try:
        with stream, destination.open("wb") as handle:
            while True:
                chunk = stream.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break
                remaining = max(0, limit - stored)
                if remaining:
                    retained = chunk[:remaining]
                    handle.write(retained)
                    stored += len(retained)
                if len(chunk) > remaining:
                    limited.set()
    except (OSError, ValueError):
        limited.set()


def _bounded_output(
    path: Path,
    *,
    run_root: Path,
    workspace: Path,
    timed_out: bool,
    output_limited: bool,
    limit: int,
) -> str:
    try:
        raw = path.read_bytes()[-limit:]
    except OSError:
        raw = b""
    value = raw.decode("utf-8", errors="replace")
    value = value.replace(str(workspace), "<workspace>").replace(
        str(run_root), "<isolated-run>"
    )
    diagnostics: list[str] = []
    if timed_out:
        diagnostics.append("[coursekit] pytest timed out")
    if output_limited:
        diagnostics.append("[coursekit] pytest output limit exceeded")
    if diagnostics:
        value += ("\n" if value else "") + "\n".join(diagnostics)
    encoded = value.encode("utf-8")
    if len(encoded) > limit:
        value = encoded[-limit:].decode("utf-8", errors="ignore")
    return value


def _read_evidence_pipe(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    remaining = MAX_EVIDENCE_BYTES + 1
    while remaining > 0:
        chunk = os.read(descriptor, min(COPY_CHUNK_BYTES, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    value = b"".join(chunks)
    return value if len(value) <= MAX_EVIDENCE_BYTES else b""


def _matches_target(
    *,
    path: str,
    nodeid: str,
    expected_path: str,
    expected_node: str,
) -> bool:
    if path != expected_path:
        return False
    suffix = nodeid.rsplit("::", 1)[-1]
    return suffix == expected_node or suffix.startswith(expected_node + "[")


def _validate_evidence(
    raw: bytes,
    *,
    nonce: str,
    expected: list[tuple[str, str]],
    returncode: int | None,
) -> tuple[bool, bool, tuple[str, ...], Mapping[str, str]]:
    try:
        payload: Any = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("nonce") != nonce:
            raise ValueError
        collected = payload.get("collected")
        outcomes = payload.get("outcomes")
        recorded_code = payload.get("exit_code")
        if (
            not isinstance(collected, list)
            or not collected
            or not isinstance(outcomes, dict)
            or isinstance(recorded_code, bool)
            or not isinstance(recorded_code, int)
            or recorded_code != returncode
        ):
            raise ValueError
        matched = [False] * len(expected)
        normalized_outcomes: dict[str, str] = {}
        normalized_collected: list[str] = []
        all_passed = True
        for item in collected:
            if not isinstance(item, dict):
                raise ValueError
            nodeid = item.get("nodeid")
            source = item.get("path")
            if not isinstance(nodeid, str) or not isinstance(source, str):
                raise ValueError
            candidates = [
                index
                for index, (path, node) in enumerate(expected)
                if _matches_target(
                    path=source,
                    nodeid=nodeid,
                    expected_path=path,
                    expected_node=node,
                )
            ]
            if len(candidates) != 1:
                raise ValueError
            outcome = outcomes.get(nodeid)
            if outcome not in {"passed", "failed", "skipped"}:
                raise ValueError
            matched[candidates[0]] = True
            normalized_collected.append(nodeid)
            normalized_outcomes[nodeid] = outcome
            all_passed = all_passed and outcome == "passed"
        if not all(matched) or set(outcomes) != set(normalized_outcomes):
            raise ValueError
        valid = True
        passed = all_passed and recorded_code == 0
        return (
            valid,
            passed,
            tuple(normalized_collected),
            MappingProxyType(normalized_outcomes),
        )
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return False, False, (), MappingProxyType({})


def run_isolated_pytest(
    learner_workspace: Path | str,
    canonical_targets: list[str],
    *,
    timeout_seconds: float,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> PytestRunResult:
    """Run all selected tests once against a disposable learner workspace."""

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 90
    ):
        raise ValueError("timeout_seconds must be positive and no greater than 90")
    if (
        isinstance(max_output_bytes, bool)
        or not isinstance(max_output_bytes, int)
        or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES
    ):
        raise ValueError(
            f"max_output_bytes must be an integer from 1 to {MAX_OUTPUT_BYTES}"
        )
    source_input = Path(learner_workspace)
    if source_input.is_symlink() or not source_input.is_dir():
        raise ValueError("learner workspace must be a regular directory")
    source = source_input.resolve()
    source_expected = _expected_targets(canonical_targets)
    bootstrap = Path(__file__).with_name("pytest_bootstrap.py").resolve()
    if bootstrap.is_symlink() or not bootstrap.is_file():
        raise ValueError("trusted pytest bootstrap is unavailable")
    deadline = time.monotonic() + timeout_seconds

    with tempfile.TemporaryDirectory(prefix="coursekit-grade-") as raw_root:
        run_root = Path(raw_root)
        workspace = run_root / "workspace"
        output_path = run_root / "pytest-output.log"
        try:
            _copy_tree(
                source,
                workspace,
                deadline=deadline,
                skip_names=_SKIP_WORKSPACE_NAMES,
                byte_budget=[0],
            )
            projected = _project_targets(
                source_expected,
                run_root / "canonical-tests",
                deadline=deadline,
            )
        except _DeadlineExceeded:
            return PytestRunResult(
                False,
                "[coursekit] pytest timed out",
                True,
                False,
                False,
                None,
            )

        home = run_root / "home"
        temporary = run_root / "tmp"
        home.mkdir()
        temporary.mkdir()
        environment = safe_subprocess_environment(os.environ)
        environment.update(
            {
                "COURSEKIT_INTERNAL_RUN": "1",
                "HOME": str(home),
                "PWD": str(workspace),
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "RAY_ENABLE_UV_RUN_RUNTIME_ENV": "0",
                "RAY_USAGE_STATS_ENABLED": "0",
                "TEMP": str(temporary),
                "TMP": str(temporary),
                "TMPDIR": str(temporary),
            }
        )
        if time.monotonic() >= deadline:
            return PytestRunResult(
                False,
                "[coursekit] pytest timed out",
                True,
                False,
                False,
                None,
            )

        nonce = secrets.token_hex(32)
        evidence_read, evidence_write = os.pipe()
        command = [
            sys.executable,
            "-I",
            str(bootstrap),
            "--workspace",
            str(workspace),
            "--evidence-fd",
            str(evidence_write),
            "--nonce",
            nonce,
        ]
        for target in projected:
            command.extend(("--target", target))

        process: subprocess.Popen[bytes] | None = None
        evidence_write_open = True
        timed_out = False
        output_limited = False
        returncode: int | None = None
        try:
            try:
                process = subprocess.Popen(
                    command,
                    cwd=workspace,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    pass_fds=(evidence_write,),
                )
            finally:
                evidence_write_open = False
                os.close(evidence_write)
            if process.stdout is None:  # pragma: no cover - PIPE guarantees it
                raise RuntimeError("pytest output pipe was not created")
            limited = threading.Event()
            reader = threading.Thread(
                target=_capture_output,
                args=(process.stdout, output_path),
                kwargs={"limit": max_output_bytes, "limited": limited},
                daemon=True,
                name="coursekit-v4-output-capture",
            )
            reader.start()
            try:
                while process.poll() is None:
                    if limited.is_set():
                        output_limited = True
                        break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        break
                    time.sleep(0.02)
                returncode = process.poll()
            finally:
                _terminate_process_tree(process)
                if returncode is None:
                    returncode = process.returncode
                reader.join(timeout=1)
                if reader.is_alive():
                    process.stdout.close()
                    reader.join(timeout=1)
                    output_limited = True
                output_limited = output_limited or limited.is_set()
            evidence_raw = _read_evidence_pipe(evidence_read)
        finally:
            if process is not None and process.poll() is None:
                _terminate_process_tree(process)
            if evidence_write_open:
                os.close(evidence_write)
            os.close(evidence_read)

        projected_expected = _expected_targets(projected)
        evidence_valid, tests_passed, collected, outcomes = _validate_evidence(
            evidence_raw,
            nonce=nonce,
            expected=projected_expected,
            returncode=returncode,
        )
        output = _bounded_output(
            output_path,
            run_root=run_root,
            workspace=workspace,
            timed_out=timed_out,
            output_limited=output_limited,
            limit=max_output_bytes,
        )
        passed = bool(
            returncode == 0
            and evidence_valid
            and tests_passed
            and not timed_out
            and not output_limited
        )
        return PytestRunResult(
            passed=passed,
            output=output,
            timed_out=timed_out,
            output_limited=output_limited,
            evidence_valid=evidence_valid,
            returncode=returncode,
            collected=collected,
            outcomes=outcomes,
        )
