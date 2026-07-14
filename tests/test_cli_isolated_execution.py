from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import pytest


SKILL_ROOT = (
    Path(__file__).resolve().parents[1]
    / "plugins/python-library-course-builder/skills/building-python-library-courses"
)
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from scaffold_course import scaffold  # noqa: E402
from tests.test_timeout_contract import make_spec  # noqa: E402


def _write_spec(path: Path, *, timeout_seconds: int = 5) -> None:
    spec = make_spec(timeout_seconds)
    question = spec["labs"][0]["questions"][0]
    question["public_test"]["code"] = (
        "from pathlib import Path\n"
        "import os\n"
        "from lab01.answer import answer_1\n\n"
        "def test_answer_1():\n"
        "    assert answer_1() == 1\n"
        "    Path('lab01/answer.py').write_text('mutated\\n')\n"
        "    real_answer = Path(__file__).resolve().parents[1] / 'answer.py'\n"
        "    real_answer.write_text('mutated-via-test-file\\n')\n"
        "    assert 'RAY_ADDRESS' not in os.environ\n"
        "    assert os.environ['RAY_ENABLE_UV_RUN_RUNTIME_ENV'] == '0'\n"
    )
    path.write_text(json.dumps(spec), encoding="utf-8")


@pytest.fixture()
def generated_course(tmp_path: Path) -> Path:
    spec_path = tmp_path / "spec.json"
    _write_spec(spec_path)
    target = tmp_path / "generated"
    scaffold(spec_path, target)
    return target


def _learner_environment(course: Path) -> dict[str, str]:
    root = course / "labs"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(root / "_course"), str(root))
    )
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def _unlock_first_lab(course: Path) -> None:
    root = course / "labs"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    knowledge = json.loads(
        (root / "_course/knowledge.json").read_text(encoding="utf-8")
    )

    def mastered(lab_id: str) -> dict[str, bool]:
        return {
            str(question["id"]): True
            for question in knowledge["labs"][lab_id]["questions"]
        }

    state = {
        "version": 1,
        "course_id": manifest["course_id"],
        "curriculum_id": manifest["curriculum_id"],
        "knowledge": {
            "lab00": mastered("lab00"),
            "lab01": mastered("lab01"),
        },
        "grades": {},
        "completed_labs": [],
        "checkpoints": {},
        "git_baseline_commit": None,
        "updated_at": None,
    }
    destination = root / ".coursekit" / "state.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(state), encoding="utf-8")


def _quiz_input(course: Path, lab_id: str) -> str:
    knowledge = json.loads(
        (course / "labs/_course/knowledge.json").read_text(encoding="utf-8")
    )
    answers: list[str] = []
    for question in knowledge["labs"][lab_id]["questions"]:
        choice_ids = [choice["id"] for choice in question["choices"]]
        answers.append(str(choice_ids.index(question["answer_id"]) + 1))
    return "\n".join(answers) + "\n"


def _run_cli(
    course: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: float = 10,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "coursekit.cli", *arguments],
        cwd=course / "labs",
        env=environment or _learner_environment(course),
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - unusual ownership boundary
        return True
    return True


def _wait_for_pid_exit(pid: int, timeout: float = 4) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.02)
    return False


def test_scaffold_copies_standalone_execution_engine(generated_course: Path) -> None:
    support = generated_course / "labs" / "_course" / "coursekit"
    template_runner = SKILL_ROOT / "assets/course-template/platform/runner"

    for name in ("execution.py", "pytest_bootstrap.py"):
        assert (support / name).read_bytes() == (template_runner / name).read_bytes()


def test_scaffolded_readmes_use_simplified_chinese_for_fixed_guidance(
    generated_course: Path,
) -> None:
    root_readme = (generated_course / "README.md").read_text(encoding="utf-8")
    labs_readme = (generated_course / "labs" / "README.md").read_text(
        encoding="utf-8"
    )

    for heading in (
        "## 环境要求",
        "## 开始学习",
        "## 学习进度",
        "## CLI 学习循环",
        "## 作者与完整性",
    ):
        assert heading in root_readme
    for stale_heading in (
        "## Requirements",
        "## Start learning",
        "## Learning progression",
        "## CLI loop",
        "## Authoring and integrity",
    ):
        assert stale_heading not in root_readme

    assert "学员工作区" in labs_readme
    assert "从 `lab00/README.md` 开始" in labs_readme
    assert "公开测试位于起始代码旁边" in labs_readme
    for stale_prose in ("learner workspace", "Start with", "Public tests"):
        assert stale_prose not in labs_readme

    assert "npm run setup\nnpm run learn" in root_readme
    assert "uv run course status" in labs_readme


def test_cli_runs_only_canonical_public_test_in_disposable_workspace(
    generated_course: Path,
) -> None:
    root = generated_course / "labs"
    _unlock_first_lab(generated_course)
    solution = root / "lab01" / "answer.py"
    solution.write_text("def answer_1():\n    return 1\n", encoding="utf-8")
    before = solution.read_bytes()
    (root / "lab01" / "tests" / "test_unlisted.py").write_text(
        "from pathlib import Path\n"
        "Path('UNLISTED_TEST_RAN').write_text('bad')\n"
        "def test_unlisted():\n"
        "    assert False\n",
        encoding="utf-8",
    )
    environment = _learner_environment(generated_course)
    environment["RAY_ADDRESS"] = "ray://sentinel.example:10001"
    environment["RAY_ENABLE_UV_RUN_RUNTIME_ENV"] = "1"

    completed = _run_cli(
        generated_course,
        "test",
        "lab01.q1",
        environment=environment,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert solution.read_bytes() == before
    assert not (root / "UNLISTED_TEST_RAN").exists()
    assert "sentinel.example" not in completed.stdout + completed.stderr


@pytest.mark.parametrize(
    ("source_text", "policy_field", "policy_values"),
    (
        (
            "import importlib\nimportlib.import_module('json')\n\n"
            "def answer_1():\n    return 1\n",
            "forbidden_imports",
            ["json"],
        ),
        (
            "import json\n\ndef answer_1():\n    return 1\n",
            "required_imports",
            ["json", "pathlib"],
        ),
        (
            "from lab00 import mini as previous\n\ndef answer_1():\n    return 1\n",
            "prior_mini_modules",
            ["lab00.mini"],
        ),
    ),
)
def test_cli_source_policy_preflight_blocks_before_pytest(
    generated_course: Path,
    source_text: str,
    policy_field: str,
    policy_values: list[str],
) -> None:
    _unlock_first_lab(generated_course)
    manifest_path = generated_course / "labs/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    question = manifest["labs"][0]["questions"][0]
    question["source_policy"][policy_field] = policy_values
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    source = generated_course / "labs" / question["file"]
    source.write_text(source_text, encoding="utf-8")

    result = _run_cli(generated_course, "test", str(question["id"]))

    assert result.returncode == 1
    assert "source policy" in result.stdout + result.stderr


def test_cli_rejects_unsafe_manifest_public_selectors(
    generated_course: Path,
) -> None:
    root = generated_course / "labs"
    linked = root / "lab01" / "tests" / "linked.py"
    try:
        linked.symlink_to(root / "lab01" / "tests" / "test_answer_1.py")
    except OSError as error:  # pragma: no cover - platform permission boundary
        pytest.skip(f"symlinks unavailable: {error}")
    script = r'''
from coursekit.cli import _canonical_public_targets

valid = _canonical_public_targets(["lab01/tests/test_answer_1.py::test_answer_1"])
assert len(valid) == 1 and valid[0].endswith("test_answer_1.py::test_answer_1")
invalid = [
    "/tmp/test_bad.py::test_bad",
    "../test_bad.py::test_bad",
    "lab01::test_bad",
    "lab01/tests/missing.py::test_bad",
    "lab01/tests/linked.py::test_answer_1",
]
for selector in invalid:
    try:
        _canonical_public_targets([selector])
    except ValueError:
        pass
    else:
        raise AssertionError(f"accepted unsafe selector: {selector}")
'''

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=_learner_environment(generated_course),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_question_timeout_is_passed_and_grade_uses_a_fresh_budget_per_question(
    generated_course: Path,
) -> None:
    root = generated_course / "labs"
    script = r'''
from types import SimpleNamespace
import coursekit.cli as cli

calls = []
def fake_run(workspace, targets, *, timeout_seconds):
    calls.append(timeout_seconds)
    return SimpleNamespace(passed=True, output="", returncode=0)

cli.run_isolated_pytest = fake_run
cli.gate_reasons = lambda _lab_id: []
cli.record_grade = lambda *_args, **_kwargs: None
assert cli.test_exercise("lab01.q1") == 0
assert len(calls) == 1 and 4 < calls[0] <= 5, calls

target = "lab01/tests/test_answer_1.py::test_answer_1"
policy = {
    "local_root": "lab01",
    "required_imports": [],
    "forbidden_imports": [],
    "prior_mini_modules": [],
    "forbidden_course_roots": [],
}
questions = [
    {"id": "lab01.q1", "title": "one", "file": "lab01/answer.py", "source_policy": policy, "timeout_seconds": 3, "tests": {"public": [target]}},
    {"id": "lab01.q2", "title": "two", "file": "lab01/answer.py", "source_policy": policy, "timeout_seconds": 9, "tests": {"public": [target]}},
]
cli.find_lab = lambda _lab_id: {"id": "lab01", "questions": questions}
calls.clear()
assert cli.grade_lab("lab01") == 0
assert len(calls) == 2, calls
assert 2 < calls[0] <= 3, calls
assert 8 < calls[1] <= 9, calls
'''

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=_learner_environment(generated_course),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group contract")
def test_cli_timeout_returns_one_and_reaps_test_descendant(tmp_path: Path) -> None:
    spec_path = tmp_path / "timeout-spec.json"
    spec = make_spec(1)
    question = spec["labs"][0]["questions"][0]
    question["public_test"]["code"] = (
        "import signal\n"
        "import subprocess\n"
        "import sys\n"
        "import time\n\n"
        "def test_answer_1():\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "    print(f'CHILD_PID={child.pid}', flush=True)\n"
        "    signal.alarm(3)\n"
        "    while True:\n"
        "        time.sleep(0.05)\n"
    )
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    course = tmp_path / "timeout-course"
    scaffold(spec_path, course)
    _unlock_first_lab(course)

    completed = _run_cli(course, "test", "lab01.q1", timeout=8)
    output = completed.stdout + completed.stderr
    match = re.search(r"CHILD_PID=(\d+)", output)
    assert match is not None, output
    child_pid = int(match.group(1))
    try:
        assert completed.returncode == 1, output
        assert "timed out" in output.lower()
        assert _wait_for_pid_exit(child_pid)
    finally:
        if _pid_exists(child_pid):
            os.kill(child_pid, signal.SIGKILL)


def test_progression_cli_unlock_uses_the_backend_knowledge_prerequisites(
    generated_course: Path,
) -> None:
    blocked_first_lab = _run_cli(
        generated_course,
        "unlock",
        "lab01",
        input_text="1\n",
    )

    assert blocked_first_lab.returncode == 3
    assert "unlock lab00" in blocked_first_lab.stderr
    assert "answer>" not in blocked_first_lab.stdout

    foundation = _run_cli(
        generated_course,
        "unlock",
        "lab00",
        input_text=_quiz_input(generated_course, "lab00"),
    )
    first_lab = _run_cli(
        generated_course,
        "unlock",
        "lab01",
        input_text=_quiz_input(generated_course, "lab01"),
    )
    blocked_later_lab = _run_cli(
        generated_course,
        "unlock",
        "lab02",
        input_text="1\n",
    )

    assert foundation.returncode == 0, foundation.stdout + foundation.stderr
    assert first_lab.returncode == 0, first_lab.stdout + first_lab.stderr
    assert blocked_later_lab.returncode == 3
    assert "complete lab01" in blocked_later_lab.stderr
    assert "answer>" not in blocked_later_lab.stdout


def test_progression_record_grade_requires_every_declared_question(
    generated_course: Path,
) -> None:
    manifest_path = generated_course / "labs" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_lab = manifest["labs"][0]
    first_lab["questions"].append(
        {
            **first_lab["questions"][0],
            "id": "lab01.q2",
            "title": "Second answer",
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    script = r'''
from coursekit.progress import read_state, record_grade

record_grade("lab01", ["lab01.q1"], verified=True, passed=True)
first = read_state()
assert "lab01" not in first["completed_labs"], first

record_grade("lab01", ["lab01.q2"], verified=True, passed=True)
second = read_state()
assert second["completed_labs"] == ["lab01"], second
'''

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=generated_course / "labs",
        env=_learner_environment(generated_course),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_review_cli_unlock_supports_object_choice_ids(
    generated_course: Path,
) -> None:
    knowledge_path = generated_course / "labs/_course/knowledge.json"
    knowledge = json.loads(knowledge_path.read_text(encoding="utf-8"))
    knowledge["labs"]["lab00"]["questions"] = [
        {
            "id": "lab00.k01",
            "prompt": "Ready?",
            "choices": [
                {"id": "no", "text": "No", "feedback": "Not ready yet."},
                {"id": "yes", "text": "Yes", "feedback": "Ready to continue."},
                {"id": "later", "text": "Later", "feedback": "Review first."},
            ],
            "answer_id": "yes",
            "explanation": "Yes.",
        }
    ]
    knowledge_path.write_text(json.dumps(knowledge), encoding="utf-8")

    completed = _run_cli(
        generated_course,
        "unlock",
        "lab00",
        input_text="2\n",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "2. Yes" in completed.stdout
    assert "Ready to continue." in completed.stdout
    assert "{'id':" not in completed.stdout
    state = json.loads(
        (generated_course / "labs/.coursekit/state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["knowledge"]["lab00"]["lab00.k01"] is True
