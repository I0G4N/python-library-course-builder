"""Shared knowledge gates and pytest grading for generated courses."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import PurePosixPath
import subprocess
import sys
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from .course import ROOT, find_lab, select_item, targets_for_item
from .execution import run_isolated_pytest
from .source_policy import SourcePolicyError, preflight_question_source
from .progress import (
    gate_reasons,
    knowledge_gate_reasons,
    load_knowledge,
    read_state,
    record_answer,
    record_grade,
    score,
    update_state,
    utc_now,
)


DEFAULT_RUNNER_URL = "http://127.0.0.1:8765"


def _questions(lab_id: str) -> list[dict[str, Any]]:
    return load_knowledge()["labs"][lab_id]["questions"]


def _choice_text(choice: Any) -> str:
    if isinstance(choice, dict) and isinstance(choice.get("text"), str):
        return choice["text"]
    return str(choice)


def _choice_is_correct(question: dict[str, Any], selected_index: int) -> bool:
    choices = question.get("choices", [])
    if not isinstance(choices, list) or not 0 <= selected_index < len(choices):
        return False
    selected = choices[selected_index]
    answer_id = question.get("answer_id")
    answer = question.get("answer")
    if isinstance(selected, str):
        return (
            isinstance(answer, int)
            and not isinstance(answer, bool)
            and selected_index == answer
        )
    if isinstance(selected, dict):
        configured = answer_id if isinstance(answer_id, str) else answer
        return isinstance(configured, str) and selected.get("id") == configured
    return False


def _choice_feedback(question: dict[str, Any], selected_index: int) -> str:
    choices = question.get("choices", [])
    if not isinstance(choices, list) or not 0 <= selected_index < len(choices):
        return ""
    selected = choices[selected_index]
    if not isinstance(selected, dict):
        return ""
    feedback = selected.get("feedback", "")
    return feedback if isinstance(feedback, str) else ""


def unlock(lab_id: str) -> int:
    lab = find_lab(lab_id)
    if lab is None:
        print(f"unknown Lab: {lab_id}", file=sys.stderr)
        return 2
    state = read_state()
    reasons = knowledge_gate_reasons(lab_id, state)
    if reasons:
        print(
            f"{'; '.join(reasons)} before unlocking {lab_id}",
            file=sys.stderr,
        )
        return 3
    wrong = 0
    for question in _questions(lab_id):
        print(f"\n{question['prompt']}")
        for index, choice in enumerate(question["choices"], start=1):
            print(f"  {index}. {_choice_text(choice)}")
        try:
            selected_index = int(input("answer> ").strip()) - 1
        except (EOFError, ValueError):
            selected_index = -1
        correct = _choice_is_correct(question, selected_index)
        record_answer(lab_id, str(question["id"]), correct)
        feedback = _choice_feedback(question, selected_index)
        explanation = str(question["explanation"])
        detail = " ".join(part for part in (feedback, explanation) if part)
        print(("✓ " if correct else "✗ ") + detail)
        wrong += 0 if correct else 1
    if wrong:
        print(f"{lab_id}: {wrong} answer(s) need another attempt")
        return 1
    print(f"{lab_id} knowledge unlocked")
    return 0


def _canonical_public_targets(targets: list[str]) -> list[str]:
    """Resolve manifest-declared public selectors without following symlinks."""

    root = ROOT.resolve()
    canonical: list[str] = []
    for selector in targets:
        raw_path, separator, node = selector.partition("::")
        relative = PurePosixPath(raw_path)
        if (
            not separator
            or not node
            or not raw_path
            or "\\" in raw_path
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ValueError(f"invalid public pytest selector: {selector}")
        candidate = ROOT.joinpath(*relative.parts)
        current = ROOT
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"public pytest target cannot use symlinks: {selector}")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (FileNotFoundError, OSError, ValueError) as error:
            raise ValueError(
                f"public pytest target is outside the learner workspace: {selector}"
            ) from error
        if not resolved.is_file():
            raise ValueError(f"public pytest target must be a regular file: {selector}")
        canonical.append(f"{resolved}::{node}")
    if not canonical:
        raise ValueError("no public pytest selectors were declared")
    return list(dict.fromkeys(canonical))


def _question_timeout(question: dict[str, Any]) -> int:
    value = question.get("timeout_seconds", 30)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 90:
        raise ValueError("question timeout_seconds must be an integer from 1 to 90")
    return value


def _run_pytest(targets: list[str], *, timeout_seconds: int) -> bool:
    try:
        result = run_isolated_pytest(
            ROOT,
            _canonical_public_targets(targets),
            timeout_seconds=timeout_seconds,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"[coursekit] cannot run public tests: {error}", file=sys.stderr)
        return False
    if result.output:
        print(result.output.rstrip())
    return bool(result.passed)


def _source_preflight(question: dict[str, Any]) -> bool:
    try:
        preflight_question_source(
            ROOT,
            str(question.get("file", "")),
            question.get("source_policy"),
        )
    except (OSError, UnicodeError, SourcePolicyError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return False
    return True


def test_exercise(item_id: str) -> int:
    try:
        lab, question = select_item(item_id)
    except LookupError as error:
        print(error, file=sys.stderr)
        return 2
    if question is None:
        print("test expects a coding question id such as lab01.q1", file=sys.stderr)
        return 2
    lab_id = str(lab["id"])
    reasons = gate_reasons(lab_id)
    if reasons:
        print("Lab is locked:\n- " + "\n- ".join(reasons), file=sys.stderr)
        return 4
    public = targets_for_item(lab, question)
    try:
        timeout_seconds = _question_timeout(question)
    except ValueError as error:
        print(f"[coursekit] cannot run public tests: {error}", file=sys.stderr)
        return 1
    if not _source_preflight(question):
        return 1
    success = _run_pytest(public, timeout_seconds=timeout_seconds)
    record_grade(
        lab_id,
        [str(question["id"])],
        verified=False,
        passed=success,
    )
    return 0 if success else 1


def grade_lab(lab_id: str) -> int:
    lab = find_lab(lab_id)
    questions = lab.get("questions", []) if isinstance(lab, dict) else []
    if lab is None or not questions:
        print(f"unknown graded Lab: {lab_id}", file=sys.stderr)
        return 2
    reasons = gate_reasons(lab_id)
    if reasons:
        print("Lab is locked:\n- " + "\n- ".join(reasons), file=sys.stderr)
        return 4
    passed = 0
    for question in questions:
        if not isinstance(question, dict):
            continue
        question_id = str(question["id"])
        print(f"\n== {question_id}: {question.get('title', question_id)} ==")
        try:
            timeout_seconds = _question_timeout(question)
        except ValueError as error:
            print(f"[coursekit] cannot run public tests: {error}", file=sys.stderr)
            success = False
        else:
            success = _source_preflight(question) and _run_pytest(
                targets_for_item(lab, question), timeout_seconds=timeout_seconds
            )
        record_grade(lab_id, [question_id], verified=False, passed=success)
        passed += int(success)
    total = len([item for item in questions if isinstance(item, dict)])
    print(f"\n{lab_id}: {passed}/{total} public exercises passed")
    return 0 if total and passed == total else 1


def _runner_submit(lab_id: str, question_id: str) -> tuple[bool, str]:
    base_url = os.environ.get("COURSEKIT_RUNNER_URL", DEFAULT_RUNNER_URL).rstrip("/")
    payload = json.dumps(
        {"lab_id": lab_id, "question_id": question_id, "mode": "submit"}
    ).encode("utf-8")
    request = urllib_request.Request(
        f"{base_url}/api/run",
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=105) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("detail")
        except (UnicodeError, json.JSONDecodeError, AttributeError):
            detail = None
        return False, str(detail or f"Runner returned HTTP {error.code}")
    except (urllib_error.URLError, TimeoutError, OSError) as error:
        return False, (
            f"cannot reach the local Runner at {base_url}: {error}. "
            "Start it with `npm run learn` and retry."
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        return False, f"Runner returned an invalid response: {error}"
    if not isinstance(value, dict) or not isinstance(value.get("passed"), bool):
        return False, "Runner returned an invalid response contract"
    output = str(value.get("output", ""))
    return bool(value["passed"]), output


def submit_lab(lab_id: str) -> int:
    lab = find_lab(lab_id)
    questions = lab.get("questions", []) if isinstance(lab, dict) else []
    if lab is None or not questions:
        print(f"unknown graded Lab: {lab_id}", file=sys.stderr)
        return 2
    reasons = gate_reasons(lab_id)
    if reasons:
        print("Lab is locked:\n- " + "\n- ".join(reasons), file=sys.stderr)
        return 4
    passed = 0
    for question in questions:
        if not isinstance(question, dict):
            continue
        question_id = str(question["id"])
        print(f"\n== submit {question_id} ==")
        success, output = _runner_submit(lab_id, question_id)
        if output:
            print(output.rstrip())
        print("verified" if success else "not verified")
        passed += int(success)
    total = len([item for item in questions if isinstance(item, dict)])
    print(f"\n{lab_id}: {passed}/{total} exercises verified by the Runner")
    return 0 if total and passed == total else 1


def _git(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None


def _git_value(args: list[str]) -> str | None:
    result = _git(args)
    if result is None or result.returncode:
        return None
    value = result.stdout.strip()
    return value or None


def checkpoint(lab_id: str) -> int:
    lab = find_lab(lab_id)
    questions = lab.get("questions", []) if isinstance(lab, dict) else []
    if lab is None or not questions:
        print(f"unknown graded Lab: {lab_id}", file=sys.stderr)
        return 2
    configured = lab.get("checkpoint", {})
    if not isinstance(configured, dict):
        print(f"{lab_id} has an invalid checkpoint configuration", file=sys.stderr)
        return 2
    state = read_state()
    if configured.get("require_submit", True) and lab_id not in state.get("completed_labs", []):
        print(f"submit {lab_id} successfully before checkpoint", file=sys.stderr)
        return 4
    verified_questions = [
        str(question["id"])
        for question in questions
        if isinstance(question, dict)
        and state.get("grades", {})
        .get(lab_id, {})
        .get(str(question["id"]), {})
        .get("verified")
        is True
    ]
    expected_questions = [
        str(question["id"]) for question in questions if isinstance(question, dict)
    ]
    if configured.get("require_submit", True) and set(verified_questions) != set(
        expected_questions
    ):
        print(f"submit {lab_id} successfully before checkpoint", file=sys.stderr)
        return 4
    scope = str(lab.get("git_scope") or lab.get("directory") or lab_id)
    baseline = state.get("git_baseline_commit")
    head: str | None = None
    commits_after_baseline = 0
    if configured.get("git_initialized", True):
        inside = _git_value(["rev-parse", "--is-inside-work-tree"])
        if inside != "true":
            print(
                "Git is unavailable or this project is not a Git repository; "
                "initialize Git and create a baseline commit, then retry.",
                file=sys.stderr,
            )
            return 5
        head = _git_value(["rev-parse", "--verify", "HEAD"])
        if not head or not isinstance(baseline, str) or not baseline:
            print(
                "the learning state has no usable Git baseline; restore the generated "
                "baseline or start with a fresh progress state",
                file=sys.stderr,
            )
            return 5
        ancestry = _git(["merge-base", "--is-ancestor", baseline, head])
        if ancestry is None or ancestry.returncode:
            print(
                "the saved Git baseline is not an ancestor of HEAD; restore the "
                "generated history before checkpointing",
                file=sys.stderr,
            )
            return 5
        count = _git_value(["rev-list", "--count", f"{baseline}..{head}", "--", scope])
        try:
            commits_after_baseline = int(count or "")
        except ValueError:
            print(
                "the saved Git baseline is not available in this repository; "
                "restore its history before checkpointing",
                file=sys.stderr,
            )
            return 5
        minimum = int(configured.get("min_commits", 1))
        if commits_after_baseline < minimum:
            print(
                f"commit at least {minimum} {scope} change(s) after the learning baseline",
                file=sys.stderr,
            )
            return 5
        if configured.get("git_clean", True):
            status = _git(["status", "--porcelain", "--", scope])
            if status is None or status.returncode:
                print("Git status failed; repair Git and retry", file=sys.stderr)
                return 5
            if status.stdout.strip():
                print(f"commit the {scope} changes before checkpoint", file=sys.stderr)
                return 5
    test_identity = {
        str(question["id"]): list(question.get("tests", {}).get("submit", []))
        for question in questions
        if isinstance(question, dict)
    }
    checkpoint_value = {
        "commit": head,
        "baseline_commit": baseline,
        "git_scope": scope,
        "commits_after_baseline": commits_after_baseline,
        "verified_questions": verified_questions,
        "test_identity": test_identity,
        "created_at": utc_now(),
    }

    def mutation(current: dict[str, Any]) -> None:
        current.setdefault("checkpoints", {})[lab_id] = {
            **checkpoint_value,
            "score": score(current),
        }

    update_state(mutation)
    print(f"{lab_id} checkpoint accepted at {head or 'no-git checkpoint'}")
    return 0


def status() -> int:
    state = read_state()
    current = score(state)
    print(json.dumps({"completed_labs": state["completed_labs"], "score": current}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="course")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("unlock", "test", "grade", "submit", "checkpoint"):
        command = commands.add_parser(name)
        command.add_argument("item")
    commands.add_parser("score")
    commands.add_parser("status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "unlock":
        return unlock(args.item)
    if args.command == "test":
        return test_exercise(args.item)
    if args.command == "grade":
        return grade_lab(args.item)
    if args.command == "submit":
        return submit_lab(args.item)
    if args.command == "checkpoint":
        return checkpoint(args.item)
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
