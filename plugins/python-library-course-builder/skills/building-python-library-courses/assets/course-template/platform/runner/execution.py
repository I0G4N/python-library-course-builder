"""Disposable, process-safe pytest execution for CourseKit grading."""

from __future__ import annotations

from dataclasses import dataclass
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
from typing import Any, BinaryIO


MAX_OUTPUT_BYTES = 200_000
MAX_EVIDENCE_BYTES = 1_000_000
MAX_WORKSPACE_COPY_BYTES = 64_000_000
COPY_CHUNK_BYTES = 65_536
_SKIP_DIRECTORIES = {
    ".coursekit",
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "tests",
}


class _CopyDeadlineExceeded(RuntimeError):
    """The disposable workspace could not be copied within its run budget."""


@dataclass(frozen=True)
class PytestRunResult:
    passed: bool
    output: str
    timed_out: bool
    output_limited: bool
    evidence_valid: bool
    returncode: int | None


def _copy_regular_tree(
    source: Path,
    destination: Path,
    *,
    deadline: float,
) -> None:
    if not source.is_dir() or source.is_symlink():
        raise ValueError("learner workspace must be a regular directory")
    destination.mkdir(parents=True, exist_ok=False)
    copied_bytes = 0

    def check_budget() -> None:
        if time.monotonic() >= deadline:
            raise _CopyDeadlineExceeded

    def copy_directory(current: Path, target: Path) -> None:
        nonlocal copied_bytes
        for child in current.iterdir():
            check_budget()
            if child.name in _SKIP_DIRECTORIES or child.is_symlink():
                continue
            try:
                if child.is_dir():
                    nested = target / child.name
                    nested.mkdir()
                    copy_directory(child, nested)
                elif child.is_file():
                    copied = target / child.name
                    with child.open("rb") as source_handle, copied.open("xb") as target_handle:
                        while True:
                            check_budget()
                            chunk = source_handle.read(COPY_CHUNK_BYTES)
                            if not chunk:
                                break
                            copied_bytes += len(chunk)
                            if copied_bytes > MAX_WORKSPACE_COPY_BYTES:
                                raise ValueError(
                                    "learner workspace exceeds the 64000000-byte grading copy limit"
                                )
                            target_handle.write(chunk)
                            check_budget()
            except _CopyDeadlineExceeded:
                raise
            except OSError:
                # FIFOs, sockets, disappearing files, and unreadable entries are
                # learner-owned input, never part of a trusted grading copy.
                continue

    copy_directory(source, destination)


def _group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - unexpected ownership boundary
        return True
    return True


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
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
    except subprocess.TimeoutExpired:  # pragma: no cover - SIGKILL is definitive
        process.kill()
        process.wait(timeout=1)


def _expected_targets(targets: list[str]) -> list[tuple[str, str]]:
    expected: list[tuple[str, str]] = []
    for target in targets:
        path, separator, node = target.partition("::")
        source = Path(path)
        if not separator or not node or not source.is_file() or source.is_symlink():
            raise ValueError(f"canonical pytest target must name one regular test: {target}")
        expected.append((str(source.resolve()), node))
    if not expected:
        raise ValueError("at least one canonical pytest target is required")
    return expected


def _project_canonical_targets(
    expected: list[tuple[str, str]],
    destination: Path,
    *,
    deadline: float,
) -> list[str]:
    """Project target files and same-directory helpers into one trusted tree.

    A target's parent directory is the explicit helper boundary. Regular files
    and directories below it are copied; symlinks, special files, caches, and
    nested runtime/test roots are excluded. One shared byte limit and deadline
    cover every projected directory.
    """

    destination.mkdir(parents=True, exist_ok=False)
    copied_bytes = 0
    projected_directories: dict[Path, Path] = {}

    def check_budget() -> None:
        if time.monotonic() >= deadline:
            raise _CopyDeadlineExceeded

    def copy_directory(source: Path, target: Path) -> None:
        nonlocal copied_bytes
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            check_budget()
            if child.name in _SKIP_DIRECTORIES or child.is_symlink():
                continue
            try:
                if child.is_dir():
                    nested = target / child.name
                    nested.mkdir()
                    copy_directory(child, nested)
                elif child.is_file():
                    copied = target / child.name
                    with child.open("rb") as source_handle, copied.open(
                        "xb"
                    ) as target_handle:
                        while True:
                            check_budget()
                            chunk = source_handle.read(COPY_CHUNK_BYTES)
                            if not chunk:
                                break
                            copied_bytes += len(chunk)
                            if copied_bytes > MAX_WORKSPACE_COPY_BYTES:
                                raise ValueError(
                                    "canonical tests exceed the 64000000-byte "
                                    "projection limit"
                                )
                            target_handle.write(chunk)
                            check_budget()
            except (_CopyDeadlineExceeded, ValueError):
                raise
            except OSError:
                # The selected target is checked after projection. Other
                # unreadable or special helper entries are simply unavailable.
                continue

    projected_targets: list[str] = []
    for source_text, node in expected:
        source = Path(source_text)
        parent = source.parent
        projected_parent = projected_directories.get(parent)
        if projected_parent is None:
            check_budget()
            if not parent.is_dir() or parent.is_symlink():
                raise ValueError("canonical pytest target parent must be regular")
            slot = destination / f"{len(projected_directories):04d}"
            slot.mkdir()
            projected_parent = slot / parent.name
            projected_parent.mkdir()
            copy_directory(parent, projected_parent)
            projected_directories[parent] = projected_parent
        projected = projected_parent / source.name
        if not projected.is_file() or projected.is_symlink():
            raise ValueError(f"canonical pytest target could not be projected: {source}")
        projected_targets.append(f"{projected}::{node}")
    return projected_targets


def _read_evidence(
    raw: bytes,
    *,
    nonce: str,
    expected: list[tuple[str, str]],
    returncode: int | None,
) -> tuple[bool, bool]:
    try:
        payload: Any = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("nonce") != nonce:
            return False, False
        collected = payload.get("collected")
        outcomes = payload.get("outcomes")
        if not isinstance(collected, list) or not isinstance(outcomes, dict):
            return False, False
        if len(collected) != len(expected) or len(outcomes) != len(expected):
            return False, False
        remaining = list(expected)
        all_passed = True
        for item in collected:
            if not isinstance(item, dict):
                return False, False
            nodeid = item.get("nodeid")
            source = item.get("path")
            if not isinstance(nodeid, str) or not isinstance(source, str):
                return False, False
            match = next(
                (
                    candidate
                    for candidate in remaining
                    if candidate[0] == source and nodeid.endswith("::" + candidate[1])
                ),
                None,
            )
            outcome = outcomes.get(nodeid)
            if match is None or outcome not in {"passed", "failed", "skipped"}:
                return False, False
            all_passed = all_passed and outcome == "passed"
            remaining.remove(match)
        recorded_code = payload.get("exit_code")
        valid = (
            not remaining
            and isinstance(recorded_code, int)
            and not isinstance(recorded_code, bool)
            and recorded_code == returncode
        )
        return valid, valid and all_passed and recorded_code == 0
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return False, False


def _read_evidence_pipe(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    remaining = MAX_EVIDENCE_BYTES + 1
    while remaining > 0:
        chunk = os.read(descriptor, min(65_536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    value = b"".join(chunks)
    return value if len(value) <= MAX_EVIDENCE_BYTES else b""


def _capture_bounded_output(
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
                chunk = stream.read(65_536)
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
        # A broken capture channel cannot be accepted as a successful grade.
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
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > limit:
                handle.seek(size - limit)
            raw = handle.read(limit)
    except OSError:
        raw = b""
    diagnostics = []
    if timed_out:
        diagnostics.append("[coursekit] pytest timed out")
    if output_limited:
        diagnostics.append("[coursekit] pytest output limit exceeded")
    value = raw.decode("utf-8", errors="replace")
    sanitized = value.replace(str(workspace), "<workspace>").replace(
        str(run_root), "<isolated-run>"
    )
    if diagnostics:
        sanitized += ("\n" if sanitized else "") + "\n".join(diagnostics)
    encoded = sanitized.encode("utf-8")
    if len(encoded) <= limit:
        return sanitized
    # ``sanitized`` was valid Unicode, so ignoring a possible partial leading
    # code point after tail slicing cannot discard any interior diagnostics.
    return encoded[-limit:].decode("utf-8", errors="ignore")


def run_isolated_pytest(
    learner_workspace: Path | str,
    canonical_targets: list[str],
    *,
    timeout_seconds: float,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> PytestRunResult:
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
    deadline = time.monotonic() + timeout_seconds

    source_input = Path(learner_workspace)
    if source_input.is_symlink() or not source_input.is_dir():
        raise ValueError("learner workspace must be a regular directory")
    source = source_input.resolve()
    source_expected = _expected_targets(canonical_targets)
    bootstrap = Path(__file__).with_name("pytest_bootstrap.py").resolve()
    nonce = secrets.token_hex(32)

    with tempfile.TemporaryDirectory(prefix="coursekit-grade-") as raw_root:
        run_root = Path(raw_root)
        workspace = run_root / "workspace"
        home = run_root / "home"
        temporary = run_root / "tmp"
        output_file = run_root / "pytest-output.log"
        try:
            _copy_regular_tree(source, workspace, deadline=deadline)
            projected_targets = _project_canonical_targets(
                source_expected,
                run_root / "canonical-tests",
                deadline=deadline,
            )
        except _CopyDeadlineExceeded:
            return PytestRunResult(
                passed=False,
                output=_bounded_output(
                    output_file,
                    run_root=run_root,
                    workspace=workspace,
                    timed_out=True,
                    output_limited=False,
                    limit=max_output_bytes,
                ),
                timed_out=True,
                output_limited=False,
                evidence_valid=False,
                returncode=None,
            )
        home.mkdir()
        temporary.mkdir()

        environment = dict(os.environ)
        for inherited_name in (
            "COURSEKIT_COURSE_DIR",
            "COURSEKIT_WORKSPACE_DIR",
            "OLDPWD",
            "PYTHONPATH",
            "RAY_ADDRESS",
        ):
            environment.pop(inherited_name, None)
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
                passed=False,
                output=_bounded_output(
                    output_file,
                    run_root=run_root,
                    workspace=workspace,
                    timed_out=True,
                    output_limited=False,
                    limit=max_output_bytes,
                ),
                timed_out=True,
                output_limited=False,
                evidence_valid=False,
                returncode=None,
            )
        timed_out = False
        output_limited = False
        returncode: int | None = None
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
        for target in projected_targets:
            command.extend(("--target", target))

        evidence_write_open = True
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
            if process.stdout is None:  # pragma: no cover - PIPE guarantees this
                raise RuntimeError("pytest output pipe was not created")
            output_event = threading.Event()
            output_reader = threading.Thread(
                target=_capture_bounded_output,
                args=(process.stdout, output_file),
                kwargs={"limit": max_output_bytes, "limited": output_event},
                name="coursekit-output-capture",
                daemon=True,
            )
            output_reader_started = False
            try:
                output_reader.start()
                output_reader_started = True
                while process.poll() is None:
                    output_limited = output_event.is_set()
                    if output_limited:
                        break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        break
                    time.sleep(0.02)
                returncode = process.poll()
            finally:
                _terminate_group(process)
                if returncode is None:
                    returncode = process.returncode
                if output_reader_started:
                    output_reader.join(timeout=1)
                if output_reader_started and output_reader.is_alive():
                    process.stdout.close()
                    output_reader.join(timeout=1)
                elif not output_reader_started:
                    process.stdout.close()
                output_limited = output_limited or output_event.is_set()
                if output_reader_started and output_reader.is_alive():  # pragma: no cover
                    output_limited = True
            evidence_raw = _read_evidence_pipe(evidence_read)
        finally:
            if evidence_write_open:
                os.close(evidence_write)
            os.close(evidence_read)

        expected = _expected_targets(projected_targets)
        evidence_valid, tests_passed = _read_evidence(
            evidence_raw,
            nonce=nonce,
            expected=expected,
            returncode=returncode,
        )
        output = _bounded_output(
            output_file,
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
        )
