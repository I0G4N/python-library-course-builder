from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    title: str
    url: str


@dataclass(frozen=True)
class CodingQuestion:
    question_id: str
    kind: str
    file: str
    symbol: str
    concept_ids: tuple[str, ...]
    outcome_ids: tuple[str, ...]
    points: int
    timeout_seconds: int
    public_tests: tuple[str, ...]
    hidden_tests: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True)
class LabSource:
    lab_id: str
    title: str
    depends_on: str
    source_ids: tuple[str, ...]
    concepts: tuple[str, ...]
    capstone_increment: str
    questions: tuple[CodingQuestion, ...]
    quiz: tuple[dict[str, Any], ...]
    root: Path
    lesson: str
    lesson_outline: dict[str, Any]
    raw: dict[str, Any]


@dataclass(frozen=True)
class PreparatoryUnitSource:
    unit_id: str
    title: str
    category: str
    dag_level: int
    depends_on: str | None
    capability_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    quiz: tuple[dict[str, Any], ...]
    root: Path
    lesson: str
    lesson_outline: dict[str, Any]
    raw: dict[str, Any]


@dataclass(frozen=True)
class CourseSource:
    schema_version: int
    course_id: str
    title: str
    description: str
    audience: dict[str, Any]
    curriculum_id: str
    compatible_curriculum_ids: tuple[str, ...]
    language: str
    python_requires: str
    size: str
    dependencies: tuple[str, ...]
    capstone: str
    extensions: tuple[dict[str, Any], ...]
    foundation_lesson: str
    foundation_lesson_outline: dict[str, Any]
    foundation_quiz: tuple[dict[str, Any], ...]
    sources: tuple[SourceReference, ...]
    target: dict[str, Any]
    research: dict[str, Any]
    labs: tuple[LabSource, ...]
    root: Path
    course: dict[str, Any]
    foundation: dict[str, Any]
    preparatory_units: tuple[PreparatoryUnitSource, ...] = ()

    @property
    def total_points(self) -> int:
        return sum(question.points for lab in self.labs for question in lab.questions)

    @property
    def foundations(self) -> dict[str, Any]:
        """Backward-compatible alias for the singular foundation component."""

        return self.foundation


@dataclass(frozen=True)
class CompileReport:
    output_root: Path
    written: tuple[Path, ...]
