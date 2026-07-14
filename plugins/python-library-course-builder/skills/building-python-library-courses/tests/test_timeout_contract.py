from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
PLATFORM_ROOT = SKILL_ROOT / "assets" / "course-template" / "platform"
sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(PLATFORM_ROOT))

from scaffold_course import write_canonical_source  # noqa: E402
from validate_course import SpecValidationError, validate_spec  # noqa: E402
from coursekit.compiler import (  # noqa: E402
    SourceValidationError,
    compile_course,
    load_course_source,
)


from tests.course_v2_fixture import MISSING, make_spec  # noqa: E402


def first_author_question(spec: dict[str, object]) -> dict[str, object]:
    return spec["labs"][0]["questions"][0]  # type: ignore[index, return-value]


def canonical_source(
    root: Path, timeout_seconds: object = MISSING
) -> Path:
    spec = validate_spec(make_spec())
    platform = root / "platform"
    write_canonical_source(platform, spec)
    source = platform / "course" / "source"
    lab_path = source / "labs" / "lab01" / "lab.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    question = lab["questions"][0]
    if timeout_seconds is MISSING:
        question.pop("timeout_seconds", None)
    else:
        question["timeout_seconds"] = timeout_seconds
    lab_path.write_text(json.dumps(lab, indent=2) + "\n", encoding="utf-8")
    return source


class AuthoringTimeoutTests(unittest.TestCase):
    def test_omission_defaults_to_30(self) -> None:
        validated = validate_spec(make_spec())

        self.assertEqual(first_author_question(validated)["timeout_seconds"], 30)

    def test_valid_boundaries_are_preserved(self) -> None:
        for timeout_seconds in (1, 90):
            with self.subTest(timeout_seconds=timeout_seconds):
                validated = validate_spec(make_spec(timeout_seconds))
                self.assertEqual(
                    first_author_question(validated)["timeout_seconds"],
                    timeout_seconds,
                )

    def test_invalid_values_are_rejected(self) -> None:
        for timeout_seconds in (True, 0, 91, "30", 1.5):
            with self.subTest(timeout_seconds=timeout_seconds):
                with self.assertRaisesRegex(
                    SpecValidationError, "timeout_seconds"
                ):
                    validate_spec(make_spec(timeout_seconds))

    def test_scaffolder_writes_normalized_value_to_canonical_source(self) -> None:
        for timeout_seconds, expected in ((MISSING, 30), (90, 90)):
            with self.subTest(timeout_seconds=timeout_seconds):
                spec = validate_spec(make_spec(timeout_seconds))
                with tempfile.TemporaryDirectory() as temporary:
                    platform = Path(temporary) / "platform"
                    write_canonical_source(platform, spec)
                    lab = json.loads(
                        (
                            platform
                            / "course/source/labs/lab01/lab.json"
                        ).read_text(encoding="utf-8")
                    )
                self.assertEqual(
                    lab["questions"][0]["timeout_seconds"], expected
                )


class CompilerTimeoutTests(unittest.TestCase):
    def test_direct_compiler_defaults_omission_and_propagates_to_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = canonical_source(root)
            course = load_course_source(source)
            output = root / "compiled"
            compile_course(source, output)

            self.assertEqual(course.labs[0].questions[0].timeout_seconds, 30)
            for manifest_path in (
                output / "manifest.json",
                output / "starter/manifest.json",
            ):
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    manifest["labs"][0]["questions"][0]["timeout_seconds"], 30
                )

    def test_direct_compiler_preserves_valid_boundaries(self) -> None:
        for timeout_seconds in (1, 90):
            with self.subTest(timeout_seconds=timeout_seconds):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    source = canonical_source(root, timeout_seconds)
                    course = load_course_source(source)
                    self.assertEqual(
                        course.labs[0].questions[0].timeout_seconds,
                        timeout_seconds,
                    )

    def test_direct_compiler_rejects_invalid_values(self) -> None:
        for timeout_seconds in (True, 0, 91, "30", 1.5):
            with self.subTest(timeout_seconds=timeout_seconds):
                with tempfile.TemporaryDirectory() as temporary:
                    source = canonical_source(Path(temporary), timeout_seconds)
                    with self.assertRaisesRegex(
                        SourceValidationError, "timeout_seconds"
                    ):
                        load_course_source(source)


if __name__ == "__main__":
    unittest.main()
