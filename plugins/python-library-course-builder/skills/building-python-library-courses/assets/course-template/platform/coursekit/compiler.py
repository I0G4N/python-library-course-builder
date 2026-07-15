from __future__ import annotations

import ast
from collections import Counter
import copy
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlparse

from .io import json_bytes, read_json, safe_relative_path, unresolved_tokens
from .models import (
    CodingQuestion,
    CompileReport,
    CourseSource,
    LabSource,
    PreparatoryUnitSource,
    SourceReference,
)


class CourseKitError(RuntimeError):
    """Base error for deterministic course compilation."""


class SourceValidationError(CourseKitError):
    """The canonical course source is incomplete or internally inconsistent."""


class DriftError(CourseKitError):
    """Compiled artifacts differ from the canonical source."""

    def __init__(self, paths: Iterable[Path]) -> None:
        self.paths = tuple(paths)
        rendered = ", ".join(path.as_posix() for path in self.paths)
        super().__init__(f"compiled course drift: {rendered}")


class TargetNotEmptyError(CourseKitError):
    """Workspace initialization would overwrite an existing target."""


ARTIFACT_INDEX = Path(".coursekit-artifacts.json")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
PREPARATORY_PATTERN = re.compile(r"^prep(?:0[1-9]|[1-9]\d+)$")
READINESS_SUMMARY_PATTERN = re.compile(r"^[0-9a-f]{12}$")
REQUIREMENT_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9._,-]+\])?"
    r"(?:(?:===|~=|==|!=|<=|>=|<|>)[A-Za-z0-9][A-Za-z0-9.*+!_-]*"
    r"(?:,(?:===|~=|==|!=|<=|>=|<|>)[A-Za-z0-9][A-Za-z0-9.*+!_-]*)*)$"
)
DIRECT_REQUIREMENT_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9._,-]+\])? @ (?:https|git\+https)://\S+$"
)
COMMIT_PATTERN = re.compile(r"^[0-9A-Fa-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PYTHON_CLAUSE_PATTERN = re.compile(
    r"^(~=|==|!=|<=|>=|<|>)(\d+)(?:\.(\d+))?(?:\.(\d+|\*))?$"
)
LAB_BOUNDS = {
    "small": (3, 5),
    "medium": (6, 8),
    "large": (6, 10),
}
QUESTION_KINDS = {"official_bridge", "reimplementation", "integration"}
QUESTION_EXAMPLE_FIELDS = ("input", "output", "explanation")
PUBLIC_QUESTION_FIELDS = (
    "id",
    "kind",
    "title",
    "file",
    "symbol",
    "points",
    "timeout_seconds",
    "prompt",
    "concept_ids",
    "outcome_ids",
    "example",
)
SOURCE_QUESTION_FIELDS = frozenset((*PUBLIC_QUESTION_FIELDS, "tests"))
QUIZ_KINDS = {"execution_trace", "diagnostic"}
QUIZ_QUESTION_FIELDS = {
    "id",
    "kind",
    "prompt",
    "choices",
    "answer_id",
    "explanation",
    "concept_ids",
    "outcome_ids",
}
QUIZ_CHOICE_FIELDS = {"id", "text", "feedback"}
CONCEPT_LIST_FIELDS = {
    "mechanism",
    "design_reasons",
    "benefits",
    "tradeoffs",
    "invariants",
    "boundaries",
    "pitfalls",
}
LESSON_FIELDS = {
    "prerequisites",
    "problem",
    "outcomes",
    "concepts",
    "examples",
    "capstone_bridge",
    "summary",
}
PREREQUISITE_FIELDS = {"id", "title", "why", "refresh"}
PROBLEM_FIELDS = {"context", "naive_approach", "failure"}
OUTCOME_FIELDS = {"id", "text"}
CONCEPT_FIELDS = {
    "id",
    "name",
    "definition",
    "purpose",
    "mental_model",
    "source_claims",
    *CONCEPT_LIST_FIELDS,
}
SOURCE_CLAIM_FIELDS = {"source_id", "claim", "status"}
EXAMPLE_COMMON_FIELDS = {
    "id",
    "title",
    "kind",
    "explanation",
    "concept_ids",
    "outcome_ids",
}
RUNNABLE_EXAMPLE_FIELDS = {
    *EXAMPLE_COMMON_FIELDS,
    "path",
    "command",
    "expected_output",
}
DIAGNOSTIC_EXAMPLE_FIELDS = {
    *EXAMPLE_COMMON_FIELDS,
    "wrong_code",
    "symptom",
    "cause",
    "fix_code",
}
CAPSTONE_BRIDGE_FIELDS = {"input", "output", "increment", "next"}
BASIC_AUDIENCE_FIELDS = {
    "level",
    "assumes",
    "does_not_assume",
    "lab_minutes",
}
BASIC_LAB_MINUTES_FIELDS = {"min", "max"}
ASSESSED_AUDIENCE_FIELDS = {"level", "prerequisite_profile"}
PREREQUISITE_PROFILE_FIELDS = {"assessment", "capabilities"}
CAPABILITY_FIELDS = {
    "id",
    "kind",
    "subject",
    "title",
    "status",
    "decision",
    "basis",
    "source_ids",
    "first_used_in",
    "foundation_concept_ids",
}
V3_PREREQUISITE_PROFILE_FIELDS = {
    "assessment",
    "route_id",
    "readiness_summary",
    "capabilities",
}
V3_CAPABILITY_FIELDS = {
    "id",
    "kind",
    "subject",
    "title",
    "status",
    "decision",
    "basis",
    "source_ids",
    "first_used_in",
    "preparatory_unit_id",
    "preparatory_concept_ids",
}
OPERATIONAL_CONTRACT_FIELDS = {
    "kind",
    "forms",
    "inputs",
    "outputs",
    "effects",
    "failure_modes",
}
OPERATIONAL_INPUT_FIELDS = {"name", "meaning", "form", "example", "constraints"}
OPERATIONAL_OUTPUT_FIELDS = {"name", "meaning", "form", "example"}
OPERATIONAL_FAILURE_FIELDS = {"condition", "observable", "recovery"}
TRACE_STEP_FIELDS = {
    "id",
    "concept_ids",
    "input_state",
    "operation",
    "output_state",
    "explanation",
}
COURSE_MANIFEST_FIELDS = {
    "schema_version",
    "layout_version",
    "course_id",
    "curriculum_id",
    "title",
    "brand",
    "project",
    "language",
    "audience",
    "python_requires",
    "starter_root",
    "source_root",
    "reference_root",
    "capstone",
    "target",
}
COURSE_MANIFEST_OPTIONAL_FIELDS = {"adapter", "python", "reference_components"}
COURSE_MANIFEST_CAPSTONE_FIELDS = {"name", "description"}
COURSE_MANIFEST_TARGET_FIELDS = {"name", "kind", "version", "track"}
COURSE_MANIFEST_TEXT_FIELDS = (
    "course_id",
    "curriculum_id",
    "title",
    "brand",
    "project",
    "language",
    "python_requires",
)
COURSE_MANIFEST_PATH_FIELDS = ("starter_root", "source_root", "reference_root")
CHECKPOINT_FIELDS = {
    "require_submit",
    "git_initialized",
    "git_clean",
    "min_commits",
}
GIT_CHECKPOINT_FIELDS = {"title", "commands"}
MANIFEST_TEST_FIELDS = {"public", "sample", "hidden", "submit"}
FOUNDATION_MANIFEST_FIELDS = {
    "id",
    "order",
    "title",
    "description",
    "graded",
    "directory",
    "readme",
    "git_scope",
    "checkpoint",
}
FOUNDATION_MANIFEST_OPTIONAL_FIELDS = {"demos", "examples", "tests"}
FOUNDATION_MANIFEST_TEXT_FIELDS = ("id", "title", "description")
FOUNDATION_MANIFEST_PATH_FIELDS = ("directory", "readme", "git_scope")
PREPARATORY_MANIFEST_OPTIONAL_FIELDS = {"demos", "examples"}
PREPARATORY_SOURCE_FIELDS = {
    "id",
    "title",
    "category",
    "dag_level",
    "depends_on",
    "capability_ids",
    "study_minutes",
    "lesson",
    "quiz",
    "manifest",
}
LAB_MANIFEST_FIELDS = {
    "order",
    "description",
    "file",
    "directory",
    "readme",
    "git_scope",
    "checkpoint",
    "git_checkpoint",
    "tests",
}
LAB_MANIFEST_TEXT_FIELDS = ("description",)
LAB_MANIFEST_PATH_FIELDS = ("file", "directory", "readme", "git_scope")
STUDY_MINUTES_FIELDS = {"tier", "min", "max", "reason"}
COURSE_SOURCE_COMMON_FIELDS = {
    "schema_version",
    "id",
    "title",
    "description",
    "audience",
    "curriculum_id",
    "compatible_curriculum_ids",
    "language",
    "python_requires",
    "size",
    "dependencies",
    "capstone",
    "lab_order",
    "extensions",
    "manifest",
    "research",
}
COURSE_SOURCE_OPTIONAL_FIELDS = {"knowledge_title"}
COURSE_SOURCE_V2_FIELDS = COURSE_SOURCE_COMMON_FIELDS | {"foundations"}
COURSE_SOURCE_V3_FIELDS = COURSE_SOURCE_COMMON_FIELDS | {
    "preparatory_order",
    "preparatory_units",
}


def _mapping(payload: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SourceValidationError(f"{label} must be a JSON object")
    return payload


def _list(payload: Any, *, label: str) -> list[Any]:
    if not isinstance(payload, list):
        raise SourceValidationError(f"{label} must be a JSON array")
    return payload


def _text(payload: dict[str, Any], key: str, *, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SourceValidationError(f"{label}.{key} must be a non-empty string")
    return value


def _url_without_credentials_or_query(value: str, *, scheme: str) -> bool:
    try:
        parsed = urlparse(value)
        port = parsed.port
        return bool(
            parsed.scheme == scheme
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and (port is None or 1 <= port <= 65_535)
        )
    except ValueError:
        return False


def _sha256_fragment(value: str) -> bool:
    raw_pairs: list[tuple[str, str]] = []
    for field in value.split("&"):
        key, separator, item = field.partition("=")
        if not separator or not key or not item:
            return False
        raw_pairs.append((key, item))
    try:
        pairs = parse_qsl(value, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    normalized_keys = [key.casefold() for key, _item in pairs]
    hashes = [item for key, item in raw_pairs if key == "sha256"]
    return bool(
        len(pairs) == len(raw_pairs)
        and all(key and item for key, item in pairs)
        and len(normalized_keys) == len(set(normalized_keys))
        and len(hashes) == 1
        and SHA256_PATTERN.fullmatch(hashes[0])
    )


def _direct_requirement(value: str) -> bool:
    if not DIRECT_REQUIREMENT_PATTERN.fullmatch(value):
        return False
    _name, _separator, url = value.partition(" @ ")
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if not _url_without_credentials_or_query(url, scheme=parsed.scheme):
        return False
    if parsed.scheme == "git+https":
        _repository, separator, commit = parsed.path.rpartition("@")
        return bool(separator and COMMIT_PATTERN.fullmatch(commit))
    if parsed.scheme == "https":
        return _sha256_fragment(parsed.fragment)
    return False


def _requirement(value: str) -> bool:
    return bool(REQUIREMENT_PATTERN.fullmatch(value) or _direct_requirement(value))


def _official_source_url(value: str) -> bool:
    return _url_without_credentials_or_query(value, scheme="https")


def _python_version_matches(specifier: str, version: tuple[int, int, int]) -> bool:
    clauses = [clause.strip() for clause in specifier.split(",") if clause.strip()]
    if not clauses:
        return False
    for clause in clauses:
        match = PYTHON_CLAUSE_PATTERN.fullmatch(clause)
        if match is None:
            raise SourceValidationError(
                "course.python_requires must use simple PEP 440 comparison clauses"
            )
        operator, major, minor, patch = match.groups()
        components = [int(major)]
        if minor is not None:
            components.append(int(minor))
        if patch not in {None, "*"}:
            components.append(int(patch))
        expected = tuple((*components, *(0 for _ in range(3 - len(components)))))
        if operator == "==" and patch == "*":
            matched = version[:2] == expected[:2]
        elif operator == "==":
            matched = version == expected
        elif operator == "!=":
            matched = version != expected
        elif operator == ">=":
            matched = version >= expected
        elif operator == "<=":
            matched = version <= expected
        elif operator == ">":
            matched = version > expected
        elif operator == "<":
            matched = version < expected
        else:
            upper = (
                (expected[0], expected[1] + 1, 0)
                if len(components) >= 3
                else (expected[0] + 1, 0, 0)
            )
            matched = expected <= version < upper
        if not matched:
            return False
    return True


def _python_requires(payload: dict[str, Any]) -> str:
    value = _text(payload, "python_requires", label="course")
    clauses = {clause.strip().replace(" ", "") for clause in value.split(",")}
    bounded = bool(
        clauses.intersection({"<3.14", "<3.14.0", "==3.13.*", "~=3.13.0"})
    )
    if (
        not _python_version_matches(value, (3, 13, 0))
        or not bounded
        or any(
            _python_version_matches(value, version)
            for version in ((3, 14, 0), (3, 14, 1), (3, 15, 0))
        )
    ):
        raise SourceValidationError(
            "course.python_requires must include Python 3.13 and exclude Python 3.14 for this template"
        )
    return value


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        return _mapping(read_json(path), label=label)
    except FileNotFoundError as error:
        raise SourceValidationError(f"missing {label}: {path}") from error
    except ValueError as error:
        raise SourceValidationError(str(error)) from error


def _read_text(path: Path, *, label: str) -> str:
    try:
        text = path.read_text()
    except FileNotFoundError as error:
        raise SourceValidationError(f"missing {label}: {path}") from error
    tokens = unresolved_tokens(text)
    if tokens:
        raise SourceValidationError(
            f"unresolved template token(s) in {path}: {', '.join(tokens)}"
        )
    return text


def _relative(value: str, *, label: str) -> Path:
    try:
        return Path(*safe_relative_path(value, label=label).parts)
    except ValueError as error:
        raise SourceValidationError(str(error)) from error


def _identifier(value: str, *, label: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise SourceValidationError(
            f"{label} must use lowercase letters, digits, hyphens, or underscores: {value!r}"
        )
    return value


def _stable_id(payload: dict[str, Any], *, label: str) -> str:
    value = _text(payload, "id", label=label)
    if not IDENTIFIER_PATTERN.fullmatch(value.replace(".", "-")):
        raise SourceValidationError(f"{label}.id must be a stable lowercase id")
    return value


def _strings(payload: Any, *, label: str, minimum: int = 1) -> tuple[str, ...]:
    values = _list(payload, label=label)
    if len(values) < minimum or not all(
        isinstance(value, str) and value.strip() for value in values
    ):
        raise SourceValidationError(
            f"{label} must contain at least {minimum} non-empty string(s)"
        )
    return tuple(values)


def _parse_python(code: str, *, label: str) -> ast.Module:
    try:
        return ast.parse(code, filename=label)
    except SyntaxError as error:
        raise SourceValidationError(f"{label} is not valid Python: {error}") from error


def _imports(module: ast.Module) -> set[str]:
    result: set[str] = set()
    importlib_names = {"importlib"}
    import_module_callables: set[str] = set()
    builtin_import_callables = {"__import__"}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.add(alias.name)
                if alias.name == "importlib":
                    importlib_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise SourceValidationError(
                    "coding source uses a relative ImportFrom"
                )
            if not node.module:
                continue
            result.add(node.module)
            for alias in node.names:
                if alias.name != "*":
                    result.add(f"{node.module}.{alias.name}")
                local_name = alias.asname or alias.name
                if node.module == "importlib" and alias.name == "import_module":
                    import_module_callables.add(local_name)
                if node.module == "builtins" and alias.name == "__import__":
                    builtin_import_callables.add(local_name)
    for node in ast.walk(module):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and function.attr == "import_module"
            and isinstance(function.value, ast.Name)
            and function.value.id in importlib_names
        ) or (
            isinstance(function, ast.Name)
            and function.id in import_module_callables | builtin_import_callables
        ):
            result.add(first.value)
    return result


def _imports_root(imports: set[str], root: str) -> bool:
    return any(name == root or name.startswith(f"{root}.") for name in imports)


def _module_name(path: str) -> str:
    value = Path(path)
    parts = value.parts[:-1] if value.name == "__init__.py" else (*value.parts[:-1], value.stem)
    return ".".join(parts)


def _declared_helper(
    imported: str,
    declared_modules: dict[str, tuple[ast.Module, ast.Module]],
) -> str | None:
    candidates = [
        name
        for name in declared_modules
        if imported == name or imported.startswith(f"{name}.")
    ]
    return max(candidates, key=len) if candidates else None


def _validate_reimplementation_closure(
    *,
    learner_file: str,
    lab_id: str,
    declared_files: dict[str, tuple[ast.Module, ast.Module]],
    forbidden_imports: tuple[str, ...],
    prior_course_roots: tuple[str, ...],
    label: str,
) -> None:
    declared_modules = {
        _module_name(path): modules for path, modules in declared_files.items()
    }
    entry = _module_name(learner_file)
    for projection in (0, 1):
        pending = [entry]
        visited: set[str] = set()
        while pending:
            module_name = pending.pop()
            if module_name in visited:
                continue
            visited.add(module_name)
            imports = _imports(declared_modules[module_name][projection])
            if any(
                _imports_root(imports, root)
                for root in (*forbidden_imports, *prior_course_roots)
            ):
                raise SourceValidationError(
                    f"{label}.learner_file closure contains a forbidden import"
                )
            for imported in imports:
                if not _imports_root({imported}, lab_id):
                    continue
                helper = _declared_helper(imported, declared_modules)
                if helper is None:
                    if imported == lab_id:
                        continue
                    raise SourceValidationError(
                        f"{label}.learner_file imports an undeclared local helper: {imported}"
                    )
                pending.append(helper)


def _require_exact_fields(
    payload: dict[str, Any], expected: set[str], *, label: str
) -> None:
    missing = sorted(expected - set(payload))
    unknown = sorted(set(payload) - expected)
    if missing:
        raise SourceValidationError(
            f"{label} is missing required field(s): {', '.join(missing)}"
        )
    if unknown:
        raise SourceValidationError(
            f"{label} has unknown field(s): {', '.join(unknown)}"
        )


def _require_fields_with_optional(
    payload: dict[str, Any],
    required: set[str],
    optional: set[str],
    *,
    label: str,
) -> None:
    _require_exact_fields(
        payload,
        required | (set(payload) & optional),
        label=label,
    )


def _validate_audience(
    payload: dict[str, Any], *, schema_version: int = 2
) -> dict[str, Any]:
    audience = _mapping(payload.get("audience"), label="course.audience")
    level = _text(audience, "level", label="course.audience")
    if level == "basic-python":
        if schema_version == 3:
            raise SourceValidationError(
                "schema v3 course.audience.level must be assessed"
            )
        _require_exact_fields(
            audience, BASIC_AUDIENCE_FIELDS, label="course.audience"
        )
        _strings(audience.get("assumes"), label="course.audience.assumes")
        _strings(
            audience.get("does_not_assume"),
            label="course.audience.does_not_assume",
        )
        duration = _mapping(
            audience.get("lab_minutes"), label="course.audience.lab_minutes"
        )
        _require_exact_fields(
            duration,
            BASIC_LAB_MINUTES_FIELDS,
            label="course.audience.lab_minutes",
        )
        if duration.get("min") != 30 or duration.get("max") != 45:
            raise SourceValidationError(
                "course.audience.lab_minutes must declare the 30-45 minute range"
            )
        return copy.deepcopy(audience)
    if level != "assessed":
        raise SourceValidationError(
            "course.audience.level must be basic-python or assessed"
        )

    _require_exact_fields(
        audience, ASSESSED_AUDIENCE_FIELDS, label="course.audience"
    )
    profile_label = "course.audience.prerequisite_profile"
    profile = _mapping(
        audience.get("prerequisite_profile"), label=profile_label
    )
    if schema_version == 3:
        _require_exact_fields(
            profile, V3_PREREQUISITE_PROFILE_FIELDS, label=profile_label
        )
        if profile.get("assessment") != "evidence-dialogue":
            raise SourceValidationError(
                f"{profile_label}.assessment must be evidence-dialogue"
            )
        route_id = _text(profile, "route_id", label=profile_label)
        if not IDENTIFIER_PATTERN.fullmatch(route_id.replace("-", "_")):
            raise SourceValidationError(
                f"{profile_label}.route_id must be a stable lowercase id"
            )
        summary = _text(profile, "readiness_summary", label=profile_label)
        if not READINESS_SUMMARY_PATTERN.fullmatch(summary):
            raise SourceValidationError(
                f"{profile_label}.readiness_summary must be 12 lowercase hex characters"
            )
        capabilities = _list(
            profile.get("capabilities"), label=f"{profile_label}.capabilities"
        )
        if not capabilities:
            raise SourceValidationError(
                f"{profile_label}.capabilities must not be empty"
            )
        capability_ids: set[str] = set()
        for index, raw in enumerate(capabilities):
            item_label = f"{profile_label}.capabilities[{index}]"
            capability = _mapping(raw, label=item_label)
            _require_exact_fields(
                capability, V3_CAPABILITY_FIELDS, label=item_label
            )
            capability_id = _stable_id(capability, label=item_label)
            if capability_id in capability_ids:
                raise SourceValidationError(
                    f"duplicate capability id: {capability_id}"
                )
            capability_ids.add(capability_id)
            for key in ("subject", "title", "basis", "first_used_in"):
                _text(capability, key, label=item_label)
            if capability.get("kind") not in {"python", "library", "domain"}:
                raise SourceValidationError(
                    f"{item_label}.kind must be python, library, or domain"
                )
            status = capability.get("status")
            if status not in {"known", "missing"}:
                raise SourceValidationError(
                    f"{item_label}.status must be known or missing"
                )
            decision = capability.get("decision")
            if decision not in {"assume", "preparatory"}:
                raise SourceValidationError(
                    f"{item_label}.decision must be assume or preparatory"
                )
            source_ids = _strings(
                capability.get("source_ids"), label=f"{item_label}.source_ids"
            )
            if len(source_ids) != len(set(source_ids)):
                raise SourceValidationError(
                    f"{item_label}.source_ids must be unique"
                )
            concept_ids = _list(
                capability.get("preparatory_concept_ids"),
                label=f"{item_label}.preparatory_concept_ids",
            )
            if not all(
                isinstance(value, str)
                and value.strip()
                and IDENTIFIER_PATTERN.fullmatch(value.replace(".", "-"))
                for value in concept_ids
            ) or len(concept_ids) != len(set(concept_ids)):
                raise SourceValidationError(
                    f"{item_label}.preparatory_concept_ids must contain unique stable ids"
                )
            preparatory_unit_id = capability.get("preparatory_unit_id")
            if status == "known":
                if (
                    decision != "assume"
                    or preparatory_unit_id is not None
                    or concept_ids
                ):
                    raise SourceValidationError(
                        f"{item_label} known capability must be assumed without preparatory mappings"
                    )
            elif (
                decision != "preparatory"
                or not isinstance(preparatory_unit_id, str)
                or not PREPARATORY_PATTERN.fullmatch(preparatory_unit_id)
                or not concept_ids
            ):
                raise SourceValidationError(
                    f"{item_label} missing capability must map to one prep unit and its concepts"
                )
        return copy.deepcopy(audience)

    _require_exact_fields(
        profile, PREREQUISITE_PROFILE_FIELDS, label=profile_label
    )
    if profile.get("assessment") != "learner-self-report":
        raise SourceValidationError(
            f"{profile_label}.assessment must be learner-self-report"
        )
    capabilities = _list(
        profile.get("capabilities"), label=f"{profile_label}.capabilities"
    )
    if not capabilities:
        raise SourceValidationError(f"{profile_label}.capabilities must not be empty")

    capability_ids: set[str] = set()
    for index, raw in enumerate(capabilities):
        item_label = f"{profile_label}.capabilities[{index}]"
        capability = _mapping(raw, label=item_label)
        _require_exact_fields(capability, CAPABILITY_FIELDS, label=item_label)
        capability_id = _stable_id(capability, label=item_label)
        if capability_id in capability_ids:
            raise SourceValidationError(f"duplicate capability id: {capability_id}")
        capability_ids.add(capability_id)
        for key in ("subject", "title"):
            _text(capability, key, label=item_label)
        if capability.get("kind") not in {"python", "library", "domain"}:
            raise SourceValidationError(
                f"{item_label}.kind must be python, library, or domain"
            )
        status = capability.get("status")
        if status not in {"known", "partial", "missing", "unsure"}:
            raise SourceValidationError(
                f"{item_label}.status must be known, partial, missing, or unsure"
            )
        decision = capability.get("decision")
        if decision not in {"assume", "foundation"}:
            raise SourceValidationError(
                f"{item_label}.decision must be assume or foundation"
            )
        if capability.get("basis") not in {
            "explicit-prerequisite",
            "selected-route-usage",
        }:
            raise SourceValidationError(
                f"{item_label}.basis must be explicit-prerequisite or selected-route-usage"
            )
        source_ids = _strings(
            capability.get("source_ids"), label=f"{item_label}.source_ids"
        )
        if len(source_ids) != len(set(source_ids)):
            raise SourceValidationError(f"{item_label}.source_ids must be unique")
        _text(capability, "first_used_in", label=item_label)
        foundation_ids = _list(
            capability.get("foundation_concept_ids"),
            label=f"{item_label}.foundation_concept_ids",
        )
        if not all(
            isinstance(value, str)
            and value.strip()
            and IDENTIFIER_PATTERN.fullmatch(value.replace(".", "-"))
            for value in foundation_ids
        ) or len(foundation_ids) != len(set(foundation_ids)):
            raise SourceValidationError(
                f"{item_label}.foundation_concept_ids must contain unique stable ids"
            )
        if status == "known":
            if decision != "assume" or foundation_ids:
                raise SourceValidationError(
                    f"{item_label}.decision must be assume and foundation_concept_ids must be empty when status is known"
                )
        elif decision != "foundation" or not foundation_ids:
            raise SourceValidationError(
                f"{item_label}.decision must be foundation with non-empty foundation_concept_ids when status is {status}"
            )
    return copy.deepcopy(audience)


def _manifest_boolean(
    payload: dict[str, Any], key: str, *, label: str
) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise SourceValidationError(f"{label}.{key} must be a boolean")
    return value


def _manifest_non_negative_integer(
    payload: dict[str, Any], key: str, *, label: str, minimum: int = 0
) -> int:
    value = payload.get(key)
    if type(value) is not int or value < minimum:
        raise SourceValidationError(
            f"{label}.{key} must be an integer greater than or equal to {minimum}"
        )
    return value


def _manifest_relative_path(
    payload: dict[str, Any], key: str, *, label: str
) -> str:
    value = _text(payload, key, label=label)
    _relative(value, label=f"{label}.{key}")
    return value


def _manifest_string_list(
    payload: dict[str, Any],
    key: str,
    *,
    label: str,
    minimum: int = 0,
    paths: bool = False,
) -> list[str]:
    item_label = f"{label}.{key}"
    values = _list(payload.get(key), label=item_label)
    if len(values) < minimum or not all(
        isinstance(value, str) and value.strip() for value in values
    ):
        raise SourceValidationError(
            f"{item_label} must contain at least {minimum} non-empty string(s)"
        )
    if paths:
        for index, value in enumerate(values):
            _relative(value, label=f"{item_label}[{index}]")
    return values


def _require_manifest_fields(
    payload: dict[str, Any], expected: set[str], *, label: str, exact: bool
) -> None:
    if exact:
        _require_exact_fields(payload, expected, label=label)
        return
    missing = sorted(expected - set(payload))
    if missing:
        raise SourceValidationError(
            f"{label} is missing required field(s): {', '.join(missing)}"
        )


def _validate_manifest_checkpoint(
    payload: Any, *, label: str, exact: bool = True
) -> dict[str, Any]:
    checkpoint = _mapping(payload, label=label)
    _require_manifest_fields(
        checkpoint, CHECKPOINT_FIELDS, label=label, exact=exact
    )
    for key in ("require_submit", "git_initialized", "git_clean"):
        _manifest_boolean(checkpoint, key, label=label)
    _manifest_non_negative_integer(checkpoint, "min_commits", label=label)
    return checkpoint


def _validate_manifest_tests(
    payload: Any, *, label: str, exact: bool = True
) -> dict[str, Any]:
    tests = _mapping(payload, label=label)
    _require_manifest_fields(tests, MANIFEST_TEST_FIELDS, label=label, exact=exact)
    for key in ("public", "sample", "hidden", "submit"):
        _manifest_string_list(tests, key, label=label)
    return tests


def _validate_course_manifest_shape(
    manifest: dict[str, Any],
    *,
    label: str,
    exact: bool = True,
    schema_version: int = 2,
) -> dict[str, Any]:
    if exact:
        _require_fields_with_optional(
            manifest,
            COURSE_MANIFEST_FIELDS,
            COURSE_MANIFEST_OPTIONAL_FIELDS,
            label=label,
        )
    else:
        _require_manifest_fields(
            manifest, COURSE_MANIFEST_FIELDS, label=label, exact=False
        )
    if (
        type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != schema_version
    ):
        raise SourceValidationError(
            f"{label}.schema_version must be {schema_version}"
        )
    if (
        type(manifest.get("layout_version")) is not int
        or manifest["layout_version"] != 3
    ):
        raise SourceValidationError(f"{label}.layout_version must be 3")
    for key in COURSE_MANIFEST_TEXT_FIELDS:
        _text(manifest, key, label=label)
    for key in COURSE_MANIFEST_PATH_FIELDS:
        _manifest_relative_path(manifest, key, label=label)

    capstone_label = f"{label}.capstone"
    capstone = _mapping(manifest.get("capstone"), label=capstone_label)
    _require_manifest_fields(
        capstone,
        COURSE_MANIFEST_CAPSTONE_FIELDS,
        label=capstone_label,
        exact=exact,
    )
    for key in ("name", "description"):
        _text(capstone, key, label=capstone_label)

    target_label = f"{label}.target"
    target = _mapping(manifest.get("target"), label=target_label)
    _require_manifest_fields(
        target,
        COURSE_MANIFEST_TARGET_FIELDS,
        label=target_label,
        exact=exact,
    )
    for key in ("name", "kind", "version"):
        _text(target, key, label=target_label)
    track = target.get("track")
    if track is not None and (not isinstance(track, str) or not track.strip()):
        raise SourceValidationError(
            f"{target_label}.track must be null or a non-empty string"
        )

    _validate_audience(
        {"audience": manifest.get("audience")},
        schema_version=schema_version,
    )
    if "adapter" in manifest:
        _manifest_relative_path(manifest, "adapter", label=label)
    if "python" in manifest:
        _text(manifest, "python", label=label)
    if "reference_components" in manifest:
        _manifest_string_list(
            manifest,
            "reference_components",
            label=label,
            paths=True,
        )
    return manifest


def _validate_course_manifest(
    course: dict[str, Any], *, audience: dict[str, Any], schema_version: int = 2
) -> None:
    label = "course.manifest"
    manifest = _mapping(course.get("manifest"), label=label)
    _validate_course_manifest_shape(
        manifest, label=label, schema_version=schema_version
    )
    manifest_audience = _validate_audience(
        {"audience": manifest.get("audience")},
        schema_version=schema_version,
    )
    if manifest_audience != audience:
        if schema_version == 3:
            raise SourceValidationError(
                "course.manifest.audience readiness profile must match "
                "course.audience"
            )
        raise SourceValidationError(
            "course.manifest.audience must match course.audience"
        )


def _validate_foundation_manifest_shape(
    manifest: dict[str, Any], *, label: str, exact: bool = True
) -> dict[str, Any]:
    if exact:
        _require_fields_with_optional(
            manifest,
            FOUNDATION_MANIFEST_FIELDS,
            FOUNDATION_MANIFEST_OPTIONAL_FIELDS,
            label=label,
        )
    else:
        _require_manifest_fields(
            manifest, FOUNDATION_MANIFEST_FIELDS, label=label, exact=False
        )
    for key in FOUNDATION_MANIFEST_TEXT_FIELDS:
        _text(manifest, key, label=label)
    if _manifest_non_negative_integer(manifest, "order", label=label) != 0:
        raise SourceValidationError(f"{label}.order must be 0")
    _manifest_boolean(manifest, "graded", label=label)
    for key in FOUNDATION_MANIFEST_PATH_FIELDS:
        _manifest_relative_path(manifest, key, label=label)
    _validate_manifest_checkpoint(
        manifest.get("checkpoint"),
        label=f"{label}.checkpoint",
        exact=exact,
    )
    for key in ("demos", "examples"):
        if key in manifest:
            _manifest_string_list(manifest, key, label=label, paths=True)
    if "tests" in manifest:
        _validate_manifest_tests(
            manifest["tests"], label=f"{label}.tests", exact=exact
        )
    return manifest


def _validate_foundation_manifest(foundations: dict[str, Any]) -> None:
    label = "foundation.manifest"
    manifest = _mapping(foundations.get("manifest"), label=label)
    _validate_foundation_manifest_shape(manifest, label=label)
    if "demos" in foundations:
        _manifest_string_list(
            foundations, "demos", label="foundation", paths=True
        )


def _validate_preparatory_manifest(
    payload: dict[str, Any], *, unit_id: str, order: int
) -> None:
    label = f"{unit_id}.manifest"
    manifest = _mapping(payload.get("manifest"), label=label)
    _require_fields_with_optional(
        manifest,
        FOUNDATION_MANIFEST_FIELDS,
        PREPARATORY_MANIFEST_OPTIONAL_FIELDS,
        label=label,
    )
    for key in FOUNDATION_MANIFEST_TEXT_FIELDS:
        _text(manifest, key, label=label)
    if manifest["id"] != unit_id:
        raise SourceValidationError(f"{label}.id must be {unit_id}")
    if _manifest_non_negative_integer(manifest, "order", label=label) != order:
        raise SourceValidationError(f"{label}.order must be {order}")
    if _manifest_boolean(manifest, "graded", label=label):
        raise SourceValidationError(f"{label}.graded must be false")
    for key in FOUNDATION_MANIFEST_PATH_FIELDS:
        _manifest_relative_path(manifest, key, label=label)
    if manifest["directory"] != unit_id:
        raise SourceValidationError(f"{label}.directory must be {unit_id}")
    if manifest["readme"] != f"{unit_id}/README.md":
        raise SourceValidationError(
            f"{label}.readme must be {unit_id}/README.md"
        )
    if manifest["git_scope"] != unit_id:
        raise SourceValidationError(f"{label}.git_scope must be {unit_id}")
    checkpoint = _validate_manifest_checkpoint(
        manifest.get("checkpoint"), label=f"{label}.checkpoint"
    )
    if checkpoint != {
        "require_submit": False,
        "git_initialized": False,
        "git_clean": False,
        "min_commits": 0,
    }:
        raise SourceValidationError(
            f"{label}.checkpoint must declare an ungraded knowledge-only unit"
        )
    for key in ("demos", "examples"):
        if key in manifest:
            _manifest_string_list(manifest, key, label=label, paths=True)


def _validate_lab_manifest_shape(
    manifest: dict[str, Any], *, label: str, exact: bool = True
) -> dict[str, Any]:
    _require_manifest_fields(
        manifest, LAB_MANIFEST_FIELDS, label=label, exact=exact
    )
    for key in LAB_MANIFEST_TEXT_FIELDS:
        _text(manifest, key, label=label)
    _manifest_non_negative_integer(manifest, "order", label=label, minimum=1)
    for key in LAB_MANIFEST_PATH_FIELDS:
        _manifest_relative_path(manifest, key, label=label)
    _validate_manifest_checkpoint(
        manifest.get("checkpoint"),
        label=f"{label}.checkpoint",
        exact=exact,
    )
    git_label = f"{label}.git_checkpoint"
    git_checkpoint = _mapping(manifest.get("git_checkpoint"), label=git_label)
    _require_manifest_fields(
        git_checkpoint,
        GIT_CHECKPOINT_FIELDS,
        label=git_label,
        exact=exact,
    )
    _text(git_checkpoint, "title", label=git_label)
    _manifest_string_list(
        git_checkpoint, "commands", label=git_label, minimum=1
    )
    _validate_manifest_tests(
        manifest.get("tests"), label=f"{label}.tests", exact=exact
    )
    return manifest


def _validate_lab_manifest(payload: dict[str, Any], *, label: str) -> None:
    manifest_label = f"{label}.manifest"
    manifest = _mapping(payload.get("manifest"), label=manifest_label)
    _validate_lab_manifest_shape(manifest, label=manifest_label)


def _validate_assessed_profile_references(
    profile: dict[str, Any],
    *,
    source_ids: set[str],
    lab_ids: set[str],
    foundation_concept_ids: set[str],
    foundation_concept_sources: dict[str, set[str]],
) -> None:
    capabilities = profile["capabilities"]
    mapped_foundation_concept_ids: set[str] = set()
    for index, capability in enumerate(capabilities):
        item_label = (
            f"course.audience.prerequisite_profile.capabilities[{index}]"
        )
        unknown_sources = sorted(set(capability["source_ids"]) - source_ids)
        if unknown_sources:
            raise SourceValidationError(
                f"{item_label}.source_ids reference unknown official source(s): {', '.join(unknown_sources)}"
            )
        if capability["first_used_in"] not in lab_ids:
            raise SourceValidationError(
                f"{item_label}.first_used_in must resolve to a graded Lab id"
            )
        unknown_concepts = sorted(
            set(capability["foundation_concept_ids"]) - foundation_concept_ids
        )
        if unknown_concepts:
            raise SourceValidationError(
                f"{item_label}.foundation_concept_ids reference unknown Lab 00 concept(s): {', '.join(unknown_concepts)}"
            )
        if capability["decision"] == "foundation":
            mapped_foundation_concept_ids.update(
                capability["foundation_concept_ids"]
            )
            cited_sources = {
                source_id
                for concept_id in capability["foundation_concept_ids"]
                for source_id in foundation_concept_sources[concept_id]
            }
            if not cited_sources.intersection(capability["source_ids"]):
                raise SourceValidationError(
                    f"capability {capability['id']} foundation_concept_ids must cite at least one capability source_ids value"
                )
    if not mapped_foundation_concept_ids:
        raise SourceValidationError(
            "course.audience.prerequisite_profile must contain at least one "
            "foundation capability for an evidenced prerequisite gap"
        )
    orphan_concept_ids = sorted(
        foundation_concept_ids - mapped_foundation_concept_ids
    )
    if orphan_concept_ids:
        raise SourceValidationError(
            "Lab 00 concept(s) must be mapped from at least one foundation "
            f"capability: {', '.join(orphan_concept_ids)}"
        )


def _validate_v3_profile_references(
    profile: dict[str, Any],
    *,
    source_ids: set[str],
    lab_ids: set[str],
    preparatory_units: tuple[PreparatoryUnitSource, ...],
) -> None:
    units_by_id = {unit.unit_id: unit for unit in preparatory_units}
    mapped_by_unit: dict[str, list[str]] = {
        unit.unit_id: [] for unit in preparatory_units
    }
    mapped_concepts_by_unit: dict[str, set[str]] = {
        unit.unit_id: set() for unit in preparatory_units
    }
    concept_sources = {
        unit.unit_id: {
            str(concept["id"]): {
                str(claim["source_id"])
                for claim in concept["source_claims"]
            }
            for concept in unit.lesson_outline["concepts"]
        }
        for unit in preparatory_units
    }
    for index, capability in enumerate(profile["capabilities"]):
        label = f"course.audience.prerequisite_profile.capabilities[{index}]"
        unknown_sources = sorted(set(capability["source_ids"]) - source_ids)
        if unknown_sources:
            raise SourceValidationError(
                f"{label}.source_ids reference unknown official source(s): "
                + ", ".join(unknown_sources)
            )
        if capability["first_used_in"] not in lab_ids:
            raise SourceValidationError(
                f"{label}.first_used_in must resolve to a graded Lab id"
            )
        unit_id = capability["preparatory_unit_id"]
        if unit_id is None:
            continue
        unit = units_by_id.get(str(unit_id))
        if unit is None or unit.unit_id == "lab00":
            raise SourceValidationError(
                f"{label}.preparatory_unit_id must resolve to a prep unit"
            )
        if capability["kind"] != unit.category:
            raise SourceValidationError(
                f"{label}.kind must match preparatory unit category"
            )
        mapped_by_unit[unit.unit_id].append(str(capability["id"]))
        declared_concepts = set(concept_sources[unit.unit_id])
        mapped_concepts = set(capability["preparatory_concept_ids"])
        unknown_concepts = sorted(mapped_concepts - declared_concepts)
        if unknown_concepts:
            raise SourceValidationError(
                f"{label}.preparatory_concept_ids reference unknown concept(s): "
                + ", ".join(unknown_concepts)
            )
        cited_sources = {
            source_id
            for concept_id in mapped_concepts
            for source_id in concept_sources[unit.unit_id][concept_id]
        }
        if not cited_sources.intersection(capability["source_ids"]):
            raise SourceValidationError(
                f"capability {capability['id']} preparatory concepts must cite at least one capability source"
            )
        mapped_concepts_by_unit[unit.unit_id].update(mapped_concepts)

    for unit in preparatory_units:
        expected = [] if unit.unit_id == "lab00" else mapped_by_unit[unit.unit_id]
        if list(unit.capability_ids) != expected:
            raise SourceValidationError(
                f"{unit.unit_id}.capability_ids must exactly match its readiness capability mappings"
            )
        if unit.unit_id != "lab00":
            declared_concepts = set(concept_sources[unit.unit_id])
            if mapped_concepts_by_unit[unit.unit_id] != declared_concepts:
                missing = sorted(
                    declared_concepts - mapped_concepts_by_unit[unit.unit_id]
                )
                raise SourceValidationError(
                    f"{unit.unit_id} concept(s) lack preparatory capability coverage: {', '.join(missing)}"
                )


def _validate_study_minutes(
    payload: Any, *, label: str, foundation: bool
) -> None:
    minutes = _mapping(payload, label=label)
    tier = minutes.get("tier")
    if foundation:
        _require_exact_fields(
            minutes, {"tier", "min", "max", "reason"}, label=label
        )
        if (
            tier != "foundation"
            or type(minutes.get("min")) is not int
            or type(minutes.get("max")) is not int
            or minutes["min"] != 45
            or minutes["max"] != 60
        ):
            raise SourceValidationError(
                f"{label} must be foundation tier with the exact 45-60 minute range"
            )
        _text(minutes, "reason", label=label)
        return
    if tier == "standard":
        _require_exact_fields(minutes, {"tier", "min", "max"}, label=label)
        if (
            type(minutes.get("min")) is not int
            or type(minutes.get("max")) is not int
            or minutes["min"] != 30
            or minutes["max"] != 45
        ):
            raise SourceValidationError(
                f"{label} standard tier must use the exact 30-45 minute range"
            )
        return
    if tier == "extended":
        _require_exact_fields(
            minutes, {"tier", "min", "max", "reason"}, label=label
        )
        if (
            type(minutes.get("min")) is not int
            or type(minutes.get("max")) is not int
            or minutes["min"] != 45
            or minutes["max"] != 60
        ):
            raise SourceValidationError(
                f"{label} extended tier must use the exact 45-60 minute range"
            )
        _text(minutes, "reason", label=label)
        return
    raise SourceValidationError(f"{label}.tier must be standard or extended")


def _validate_preparatory_study_minutes(
    payload: Any, *, label: str, orientation: bool
) -> None:
    minutes = _mapping(payload, label=label)
    tier = minutes.get("tier")
    if orientation:
        _require_exact_fields(minutes, {"tier", "min", "max"}, label=label)
        if (
            tier != "orientation"
            or type(minutes.get("min")) is not int
            or type(minutes.get("max")) is not int
            or minutes["min"] != 15
            or minutes["max"] != 30
        ):
            raise SourceValidationError(
                f"{label} must use the exact 15-30 minute orientation range"
            )
        return
    if tier == "standard":
        _require_exact_fields(minutes, {"tier", "min", "max"}, label=label)
        if (
            type(minutes.get("min")) is not int
            or type(minutes.get("max")) is not int
            or minutes["min"] != 30
            or minutes["max"] != 45
        ):
            raise SourceValidationError(
                f"{label} standard tier must use the exact 30-45 minute range"
            )
        return
    if tier == "extended":
        _require_exact_fields(
            minutes, {"tier", "min", "max", "reason"}, label=label
        )
        if (
            type(minutes.get("min")) is not int
            or type(minutes.get("max")) is not int
            or minutes["min"] != 45
            or minutes["max"] != 60
        ):
            raise SourceValidationError(
                f"{label} extended tier must use the exact 45-60 minute range"
            )
        _text(minutes, "reason", label=label)
        return
    raise SourceValidationError(
        f"{label}.tier must be orientation, standard, or extended"
    )


def _validate_source_tree(root: Path) -> None:
    if not root.is_dir():
        raise SourceValidationError(f"course source directory is missing: {root}")
    if root.is_symlink():
        raise SourceValidationError(f"course source root cannot be a symlink: {root}")
    if (root / "authoring-spec.json").exists():
        raise SourceValidationError(
            "course/source/authoring-spec.json is not canonical in schema v2"
        )
    legacy_lessons = [
        path for path in root.rglob("lesson.md") if path.is_file() or path.is_symlink()
    ]
    if legacy_lessons:
        raise SourceValidationError(
            f"schema v2 lessons must use lesson.json, not {legacy_lessons[0]}"
        )
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SourceValidationError(f"course source cannot contain symlink: {path}")
        if path.is_file():
            try:
                tokens = unresolved_tokens(path.read_text())
            except UnicodeDecodeError:
                continue
            if tokens:
                raise SourceValidationError(
                    f"unresolved template token(s) in {path}: {', '.join(tokens)}"
                )


def _validate_output_root(output: Path) -> None:
    if output.is_symlink():
        raise SourceValidationError(f"output root cannot be a symlink: {output}")
    if output.exists() and not output.is_dir():
        raise SourceValidationError(f"output root must be a directory: {output}")


def _validate_output_paths(output: Path, artifacts: Iterable[Path]) -> None:
    for artifact in artifacts:
        current = output
        for part in artifact.parts:
            current = current / part
            if current.is_symlink():
                raise SourceValidationError(
                    f"output artifact path cannot contain symlink: {current}"
                )
            if current.exists() and current != output / artifact and not current.is_dir():
                raise SourceValidationError(
                    f"output artifact parent must be a directory: {current}"
                )


def _validate_mappings(
    payload: dict[str, Any],
    *,
    label: str,
    concept_ids: set[str],
    outcome_ids: set[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    concepts = _strings(payload.get("concept_ids"), label=f"{label}.concept_ids")
    outcomes = _strings(payload.get("outcome_ids"), label=f"{label}.outcome_ids")
    if not set(concepts) <= concept_ids:
        raise SourceValidationError(f"{label}.concept_ids reference unknown concepts")
    if not set(outcomes) <= outcome_ids:
        raise SourceValidationError(f"{label}.outcome_ids reference unknown outcomes")
    return concepts, outcomes


def _validate_operational_contract(
    concept: dict[str, Any], *, label: str
) -> None:
    contract_label = f"{label}.operational_contract"
    contract = _mapping(concept.get("operational_contract"), label=contract_label)
    _require_exact_fields(
        contract, OPERATIONAL_CONTRACT_FIELDS, label=contract_label
    )
    if contract.get("kind") not in {
        "api",
        "mechanism",
        "formula",
        "lifecycle",
        "data-model",
    }:
        raise SourceValidationError(
            f"{contract_label}.kind must be api, mechanism, formula, lifecycle, or data-model"
        )
    for key in ("forms", "effects"):
        _strings(contract.get(key), label=f"{contract_label}.{key}")

    inputs = _list(contract.get("inputs"), label=f"{contract_label}.inputs")
    if not inputs:
        raise SourceValidationError(f"{contract_label}.inputs must not be empty")
    for index, raw in enumerate(inputs):
        item_label = f"{contract_label}.inputs[{index}]"
        item = _mapping(raw, label=item_label)
        _require_exact_fields(item, OPERATIONAL_INPUT_FIELDS, label=item_label)
        for key in ("name", "meaning", "form", "example"):
            _text(item, key, label=item_label)
        _strings(item.get("constraints"), label=f"{item_label}.constraints")

    outputs = _list(contract.get("outputs"), label=f"{contract_label}.outputs")
    if not outputs:
        raise SourceValidationError(f"{contract_label}.outputs must not be empty")
    for index, raw in enumerate(outputs):
        item_label = f"{contract_label}.outputs[{index}]"
        item = _mapping(raw, label=item_label)
        _require_exact_fields(item, OPERATIONAL_OUTPUT_FIELDS, label=item_label)
        for key in ("name", "meaning", "form", "example"):
            _text(item, key, label=item_label)

    failures = _list(
        contract.get("failure_modes"), label=f"{contract_label}.failure_modes"
    )
    if not failures:
        raise SourceValidationError(
            f"{contract_label}.failure_modes must not be empty"
        )
    for index, raw in enumerate(failures):
        item_label = f"{contract_label}.failure_modes[{index}]"
        item = _mapping(raw, label=item_label)
        _require_exact_fields(item, OPERATIONAL_FAILURE_FIELDS, label=item_label)
        for key in ("condition", "observable", "recovery"):
            _text(item, key, label=item_label)


def _validate_trace(
    example: dict[str, Any], *, label: str, concept_ids: set[str]
) -> None:
    trace_label = f"{label}.trace"
    trace = _list(example.get("trace"), label=trace_label)
    if len(trace) < 2:
        raise SourceValidationError(f"{trace_label} must contain at least two steps")
    example_concepts = set(example["concept_ids"])
    step_ids: set[str] = set()
    for index, raw in enumerate(trace):
        step_label = f"{trace_label}[{index}]"
        step = _mapping(raw, label=step_label)
        _require_exact_fields(step, TRACE_STEP_FIELDS, label=step_label)
        step_id = _stable_id(step, label=step_label)
        if step_id in step_ids:
            raise SourceValidationError(
                f"{trace_label} has duplicate step id: {step_id}"
            )
        step_ids.add(step_id)
        mapped = set(
            _strings(step.get("concept_ids"), label=f"{step_label}.concept_ids")
        )
        if not mapped <= concept_ids or not mapped <= example_concepts:
            raise SourceValidationError(
                f"{trace_label} concept_ids must belong to the lesson and be a subset of the runnable example concept_ids"
            )
        for key in ("input_state", "operation", "output_state", "explanation"):
            _text(step, key, label=step_label)


def _validate_assessed_coverage(
    lesson: dict[str, Any],
    *,
    label: str,
    concept_ids: set[str],
    outcome_ids: set[str],
    quiz: tuple[dict[str, Any], ...],
    questions: tuple[CodingQuestion, ...] | None,
) -> None:
    examples = lesson["examples"]
    runnable_trace_concepts = {
        concept_id
        for example in examples
        if example["kind"] == "runnable"
        for step in example["trace"]
        for concept_id in step["concept_ids"]
    }
    quiz_concepts = {
        concept_id for item in quiz for concept_id in item["concept_ids"]
    }
    diagnostic_concepts = {
        concept_id
        for example in examples
        if example["kind"] == "diagnostic"
        for concept_id in example["concept_ids"]
    } | {
        concept_id
        for item in quiz
        if item["kind"] == "diagnostic"
        for concept_id in item["concept_ids"]
    }
    surfaces = [
        ("runnable trace", runnable_trace_concepts),
        ("quiz", quiz_concepts),
    ]
    if questions is not None:
        coding_concepts = {
            concept_id for question in questions for concept_id in question.concept_ids
        }
        surfaces.append(("coding question", coding_concepts))
    surfaces.append(("diagnostic", diagnostic_concepts))
    for concept_id in sorted(concept_ids):
        for surface, covered in surfaces:
            if concept_id not in covered:
                raise SourceValidationError(
                    f"{label} concept {concept_id} is missing {surface} coverage"
                )

    example_outcomes = {
        outcome_id for example in examples for outcome_id in example["outcome_ids"]
    }
    assessment_outcomes = {
        outcome_id for item in quiz for outcome_id in item["outcome_ids"]
    }
    if questions is not None:
        assessment_outcomes.update(
            outcome_id
            for question in questions
            for outcome_id in question.outcome_ids
        )
    for outcome_id in sorted(outcome_ids):
        if outcome_id not in example_outcomes:
            raise SourceValidationError(
                f"{label} outcome {outcome_id} is missing example coverage"
            )
        if outcome_id not in assessment_outcomes:
            raise SourceValidationError(
                f"{label} outcome {outcome_id} is missing quiz or coding question coverage"
            )


def _load_lesson(
    path: Path,
    *,
    label: str,
    source_ids: set[str],
    assessed: bool = False,
) -> tuple[dict[str, Any], set[str], set[str]]:
    lesson = _read_json(path, label=label)
    _require_exact_fields(lesson, LESSON_FIELDS, label=label)
    prerequisites = _list(
        lesson.get("prerequisites"), label=f"{label}.prerequisites"
    )
    if not prerequisites:
        raise SourceValidationError(f"{label}.prerequisites must not be empty")
    prerequisite_ids: set[str] = set()
    for index, raw in enumerate(prerequisites):
        item_label = f"{label}.prerequisites[{index}]"
        item = _mapping(raw, label=item_label)
        _require_exact_fields(item, PREREQUISITE_FIELDS, label=item_label)
        item_id = _stable_id(item, label=item_label)
        if item_id in prerequisite_ids:
            raise SourceValidationError(f"duplicate prerequisite id: {item_id}")
        prerequisite_ids.add(item_id)
        for key in ("title", "why", "refresh"):
            _text(item, key, label=item_label)

    problem = _mapping(lesson.get("problem"), label=f"{label}.problem")
    _require_exact_fields(problem, PROBLEM_FIELDS, label=f"{label}.problem")
    for key in ("context", "naive_approach", "failure"):
        _text(problem, key, label=f"{label}.problem")

    outcomes = _list(lesson.get("outcomes"), label=f"{label}.outcomes")
    if not outcomes:
        raise SourceValidationError(f"{label}.outcomes must not be empty")
    outcome_ids: set[str] = set()
    for index, raw in enumerate(outcomes):
        item_label = f"{label}.outcomes[{index}]"
        item = _mapping(raw, label=item_label)
        _require_exact_fields(item, OUTCOME_FIELDS, label=item_label)
        outcome_id = _stable_id(item, label=item_label)
        if outcome_id in outcome_ids:
            raise SourceValidationError(f"duplicate outcome id: {outcome_id}")
        outcome_ids.add(outcome_id)
        _text(item, "text", label=item_label)

    concepts = _list(lesson.get("concepts"), label=f"{label}.concepts")
    if not concepts:
        raise SourceValidationError(f"{label}.concepts must not be empty")
    concept_ids: set[str] = set()
    for index, raw in enumerate(concepts):
        item_label = f"{label}.concepts[{index}]"
        concept = _mapping(raw, label=item_label)
        concept_fields = CONCEPT_FIELDS | ({"operational_contract"} if assessed else set())
        _require_exact_fields(concept, concept_fields, label=item_label)
        concept_id = _stable_id(concept, label=item_label)
        if concept_id in concept_ids:
            raise SourceValidationError(f"duplicate concept id: {concept_id}")
        concept_ids.add(concept_id)
        for key in ("name", "definition", "purpose", "mental_model"):
            _text(concept, key, label=item_label)
        for key in sorted(CONCEPT_LIST_FIELDS):
            _strings(concept.get(key), label=f"{item_label}.{key}")
        claims = _list(
            concept.get("source_claims"), label=f"{item_label}.source_claims"
        )
        if not claims:
            raise SourceValidationError(f"{item_label}.source_claims must not be empty")
        for claim_index, raw_claim in enumerate(claims):
            claim_label = f"{item_label}.source_claims[{claim_index}]"
            claim = _mapping(raw_claim, label=claim_label)
            _require_exact_fields(claim, SOURCE_CLAIM_FIELDS, label=claim_label)
            source_id = _text(claim, "source_id", label=claim_label)
            if source_id not in source_ids:
                raise SourceValidationError(
                    f"{claim_label} references unknown source {source_id}"
                )
            _text(claim, "claim", label=claim_label)
            if claim.get("status") not in {"documented", "implementation"}:
                raise SourceValidationError(
                    f"{claim_label}.status must be documented or implementation"
                )
        if assessed:
            _validate_operational_contract(concept, label=item_label)

    examples = _list(lesson.get("examples"), label=f"{label}.examples")
    if len(examples) < 2:
        raise SourceValidationError(f"{label}.examples needs at least two examples")
    hydrated = copy.deepcopy(lesson)
    hydrated_examples = hydrated["examples"]
    kinds: set[str] = set()
    example_ids: set[str] = set()
    example_paths: set[str] = set()
    for index, raw in enumerate(examples):
        item_label = f"{label}.examples[{index}]"
        example = _mapping(raw, label=item_label)
        hydrated_example = _mapping(hydrated_examples[index], label=item_label)
        example_id = _stable_id(example, label=item_label)
        if example_id in example_ids:
            raise SourceValidationError(f"duplicate lesson example id: {example_id}")
        example_ids.add(example_id)
        _text(example, "title", label=item_label)
        kind = _text(example, "kind", label=item_label)
        if kind not in {"runnable", "diagnostic"}:
            raise SourceValidationError(f"{item_label}.kind must be runnable or diagnostic")
        example_fields = (
            RUNNABLE_EXAMPLE_FIELDS
            | ({"trace"} if assessed or "trace" in example else set())
            if kind == "runnable"
            else DIAGNOSTIC_EXAMPLE_FIELDS
        )
        _require_exact_fields(example, example_fields, label=item_label)
        kinds.add(kind)
        _text(example, "explanation", label=item_label)
        _validate_mappings(
            example,
            label=item_label,
            concept_ids=concept_ids,
            outcome_ids=outcome_ids,
        )
        if kind == "runnable":
            if assessed or "trace" in example:
                _validate_trace(example, label=item_label, concept_ids=concept_ids)
            if "code" in example:
                raise SourceValidationError(
                    f"{item_label}.code must live in its declared example file"
                )
            relative = _relative(
                _text(example, "path", label=item_label),
                label=f"{item_label}.path",
            )
            if relative.suffix != ".py" or relative.as_posix() in example_paths:
                raise SourceValidationError(
                    f"{item_label}.path must be a unique Python path"
                )
            example_paths.add(relative.as_posix())
            code = _read_text(path.parent / relative, label=f"{item_label} code")
            _parse_python(code, label=f"{item_label}.code")
            hydrated_example["code"] = code
            command = _text(example, "command", label=item_label)
            expected_command = f"python {relative.as_posix()}"
            if command != expected_command:
                raise SourceValidationError(
                    f"{item_label}.command must be exactly {expected_command!r}"
                )
            _text(example, "expected_output", label=item_label)
        else:
            for key in ("wrong_code", "symptom", "cause", "fix_code"):
                _text(example, key, label=item_label)
            _parse_python(str(example["wrong_code"]), label=f"{item_label}.wrong_code")
            _parse_python(str(example["fix_code"]), label=f"{item_label}.fix_code")
    for required in ("runnable", "diagnostic"):
        if required not in kinds:
            raise SourceValidationError(f"{label}.examples needs a {required} example")

    bridge = _mapping(
        lesson.get("capstone_bridge"), label=f"{label}.capstone_bridge"
    )
    _require_exact_fields(
        bridge, CAPSTONE_BRIDGE_FIELDS, label=f"{label}.capstone_bridge"
    )
    for key in ("input", "output", "increment", "next"):
        _text(bridge, key, label=f"{label}.capstone_bridge")
    _strings(lesson.get("summary"), label=f"{label}.summary")
    return hydrated, concept_ids, outcome_ids


def _markdown_list(title: str, values: Iterable[str]) -> list[str]:
    return [f"#### {title}", "", *(f"- {value}" for value in values), ""]


def _render_legacy_lesson(
    title: str,
    lesson: dict[str, Any],
    *,
    sources: dict[str, SourceReference],
) -> str:
    """Render every structured field as deterministic, portable Markdown."""

    lines = [f"# {title}", "", "## 先修知识", ""]
    for item in lesson["prerequisites"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"**为什么重要：** {item['why']}",
                "",
                f"**复习提示：** {item['refresh']}",
                "",
            ]
        )
    problem = lesson["problem"]
    lines.extend(
        [
            "## 问题",
            "",
            f"**背景：** {problem['context']}",
            "",
            f"**朴素方案：** {problem['naive_approach']}",
            "",
            f"**失败表现：** {problem['failure']}",
            "",
            "## 学习目标",
            "",
            *(f"- {item['text']} (`{item['id']}`)" for item in lesson["outcomes"]),
            "",
            "## 核心概念",
            "",
        ]
    )
    for concept in lesson["concepts"]:
        lines.extend(
            [
                f"### {concept['name']}",
                "",
                f"**定义：** {concept['definition']}",
                "",
                f"**用途：** {concept['purpose']}",
                "",
                "#### 机制",
                "",
                *(f"{index}. {step}" for index, step in enumerate(concept["mechanism"], 1)),
                "",
                f"**心智模型：** {concept['mental_model']}",
                "",
            ]
        )
        for heading, key in (
            ("设计理由", "design_reasons"),
            ("收益", "benefits"),
            ("权衡", "tradeoffs"),
            ("不变量", "invariants"),
            ("边界", "boundaries"),
            ("常见陷阱", "pitfalls"),
        ):
            lines.extend(_markdown_list(heading, concept[key]))
        lines.extend(["#### 官方来源声明", ""])
        for claim in concept["source_claims"]:
            source = sources[claim["source_id"]]
            lines.append(
                f"- [{source.title}]({source.url}) ({claim['status']}): {claim['claim']}"
            )
        lines.append("")

    lines.extend(["## 示例", ""])
    for example in lesson["examples"]:
        lines.extend([f"### {example['title']}", ""])
        if example["kind"] == "runnable":
            lines.extend(
                [
                    "```python",
                    str(example["code"]).rstrip("\n"),
                    "```",
                    "",
                    f"**运行：** `{example['command']}`",
                    "",
                    "**预期输出：**",
                    "",
                    "```text",
                    str(example["expected_output"]).rstrip("\n"),
                    "```",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "**错误代码：**",
                    "",
                    "```python",
                    str(example["wrong_code"]).rstrip("\n"),
                    "```",
                    "",
                    f"**现象：** {example['symptom']}",
                    "",
                    f"**原因：** {example['cause']}",
                    "",
                    "**修复：**",
                    "",
                    "```python",
                    str(example["fix_code"]).rstrip("\n"),
                    "```",
                    "",
                ]
            )
        lines.extend(
            [
                str(example["explanation"]),
                "",
                "**相关概念：** "
                + ", ".join(f"`{value}`" for value in example["concept_ids"]),
                "",
                "**对应目标：** "
                + ", ".join(f"`{value}`" for value in example["outcome_ids"]),
                "",
            ]
        )

    bridge = lesson["capstone_bridge"]
    lines.extend(
        [
            "## 结课项目衔接",
            "",
            f"**输入：** {bridge['input']}",
            "",
            f"**输出：** {bridge['output']}",
            "",
            f"**增量：** {bridge['increment']}",
            "",
            f"**下一步：** {bridge['next']}",
            "",
            "## 总结",
            "",
            *(f"- {item}" for item in lesson["summary"]),
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _derive_practice_links(
    lesson: dict[str, Any],
    activities: Iterable[dict[str, Any] | CodingQuestion],
    *,
    kind: str,
) -> list[dict[str, str]]:
    """Project the first authored activity for each concept without a reverse map."""

    normalized: list[dict[str, Any]] = []
    for activity in activities:
        normalized.append(
            activity.raw if isinstance(activity, CodingQuestion) else activity
        )
    title_key = "prompt" if kind == "knowledge-check" else "title"
    links: list[dict[str, str]] = []
    for concept in lesson["concepts"]:
        concept_id = str(concept["id"])
        activity = next(
            (
                item
                for item in normalized
                if concept_id in [str(value) for value in item.get("concept_ids", [])]
            ),
            None,
        )
        if activity is None:
            continue
        links.append(
            {
                "concept_id": concept_id,
                "kind": kind,
                "item_id": str(activity["id"]),
                "title": str(activity[title_key]),
            }
        )
    return links


def _render_assessed_lesson(
    title: str,
    lesson: dict[str, Any],
    *,
    sources: dict[str, SourceReference],
    study_minutes: dict[str, Any],
    practice_links: Iterable[dict[str, str]],
) -> str:
    """Render the assessed learner path before optional implementation detail."""

    contract_kind_labels = {
        "api": "API 调用",
        "data-model": "数据模型",
        "mechanism": "运行机制",
        "formula": "计算关系",
        "lifecycle": "生命周期",
    }
    claim_status_labels = {
        "documented": "公开契约",
        "implementation": "实现细节",
    }
    study = f"{study_minutes['min']}–{study_minutes['max']} 分钟"
    lines = [f"# {title}", "", f"**预计学习时间：** {study}", ""]
    reason = study_minutes.get("reason")
    if reason:
        lines.extend([f"**为什么需要这些时间：** {reason}", ""])

    lines.extend(["## 先修知识", ""])
    for item in lesson["prerequisites"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"**为什么重要：** {item['why']}",
                "",
                f"**复习提示：** {item['refresh']}",
                "",
            ]
        )
    problem = lesson["problem"]
    lines.extend(
        [
            "## 问题",
            "",
            f"**项目背景：** {problem['context']}",
            "",
            f"**看似直接的做法：** {problem['naive_approach']}",
            "",
            f"**它会怎样失败：** {problem['failure']}",
            "",
            "## 学习目标",
            "",
            *(f"- {item['text']}" for item in lesson["outcomes"]),
            "",
            "## 核心概念",
            "",
        ]
    )

    for concept in lesson["concepts"]:
        contract = concept["operational_contract"]
        lines.extend(
            [
                f"### {concept['name']}",
                "",
                f"**定义：** {concept['definition']}",
                "",
                f"**用途：** {concept['purpose']}",
                "",
                "#### 先这样理解",
                "",
                str(concept["mental_model"]),
                "",
                "#### 输入和输出是什么",
                "",
                f"**理解角度：** {contract_kind_labels[str(contract['kind'])]}",
                "",
                "**可用形式：**",
                "",
                *(f"- `{form}`" for form in contract["forms"]),
                "",
                "**输入：**",
                "",
            ]
        )
        for item in contract["inputs"]:
            lines.extend(
                [
                    f"- **{item['name']}**：{item['meaning']}",
                    f"  - 形式：`{item['form']}`",
                    f"  - 具体例子：`{item['example']}`",
                    "  - 约束：" + "；".join(str(value) for value in item["constraints"]),
                ]
            )
        lines.extend(["", "**输出：**", ""])
        for item in contract["outputs"]:
            lines.extend(
                [
                    f"- **{item['name']}**：{item['meaning']}",
                    f"  - 形式：`{item['form']}`",
                    f"  - 具体例子：`{item['example']}`",
                ]
            )
        lines.extend(["", "**可观察影响：**", ""])
        lines.extend(f"- {value}" for value in contract["effects"])
        lines.extend(["", "**失败时会发生什么：**", ""])
        for failure in contract["failure_modes"]:
            lines.extend(
                [
                    f"- 条件：{failure['condition']}",
                    f"  - 可观察结果：{failure['observable']}",
                    f"  - 恢复方式：{failure['recovery']}",
                ]
            )
        lines.append("")

    runnable_examples = [
        example for example in lesson["examples"] if example["kind"] == "runnable"
    ]
    lines.extend(["## 可运行示例", ""])
    for example in runnable_examples:
        lines.extend(
            [
                f"### {example['title']}",
                "",
                str(example["explanation"]),
                "",
                "```python",
                str(example["code"]).rstrip("\n"),
                "```",
                "",
                "#### 拿一个具体输入走一遍",
                "",
            ]
        )
        for index, step in enumerate(example["trace"], 1):
            lines.extend(
                [
                    f"{index}. **输入状态：** {step['input_state']}",
                    f"   - **执行动作：** {step['operation']}",
                    f"   - **输出状态：** {step['output_state']}",
                    f"   - **为什么：** {step['explanation']}",
                ]
            )
        lines.append("")

    links = list(practice_links)
    lines.extend(["## 接下来练什么", ""])
    for link in links:
        if link["kind"] == "coding-question":
            lines.append(
                f"- **{link['title']}**：`uv run course test {link['item_id']}`"
            )
        else:
            lines.append(f"- **{link['title']}**：进入本章知识检查。")
    lines.append("")

    bridge = lesson["capstone_bridge"]
    lines.extend(
        [
            "## 结课项目衔接",
            "",
            f"**输入：** {bridge['input']}",
            "",
            f"**输出：** {bridge['output']}",
            "",
            f"**增量：** {bridge['increment']}",
            "",
            f"**下一步：** {bridge['next']}",
            "",
            "## 总结",
            "",
            *(f"- {item}" for item in lesson["summary"]),
            "",
            "<details>",
            "<summary>运行细节</summary>",
            "",
        ]
    )
    for concept in lesson["concepts"]:
        lines.extend([f"### {concept['name']} 如何运行", ""])
        lines.extend(
            f"{index}. {step}" for index, step in enumerate(concept["mechanism"], 1)
        )
        lines.append("")
    for example in runnable_examples:
        lines.extend(
            [
                f"**运行命令：** `{example['command']}`",
                "",
                "**预期输出：**",
                "",
                "```text",
                str(example["expected_output"]).rstrip("\n"),
                "```",
                "",
            ]
        )
    for example in lesson["examples"]:
        if example["kind"] != "diagnostic":
            continue
        lines.extend(
            [
                f"### {example['title']}",
                "",
                "```python",
                str(example["wrong_code"]).rstrip("\n"),
                "```",
                "",
                f"**现象：** {example['symptom']}",
                "",
                f"**原因：** {example['cause']}",
                "",
                "```python",
                str(example["fix_code"]).rstrip("\n"),
                "```",
                "",
                str(example["explanation"]),
                "",
            ]
        )
    lines.extend(["</details>", "", "<details>", "<summary>需要保持的条件</summary>", ""])
    for concept in lesson["concepts"]:
        lines.extend([f"### {concept['name']}", "", "**必须保持：**", ""])
        lines.extend(f"- {value}" for value in concept["invariants"])
        lines.extend(["", "**适用边界：**", ""])
        lines.extend(f"- {value}" for value in concept["boundaries"])
        lines.extend(["", "**容易踩坑：**", ""])
        lines.extend(f"- {value}" for value in concept["pitfalls"])
        lines.append("")
    lines.extend(["</details>", "", "<details>", "<summary>依据与延伸</summary>", ""])
    for concept in lesson["concepts"]:
        lines.extend([f"### {concept['name']}", "", "**设计考虑：**", ""])
        lines.extend(f"- {value}" for value in concept["design_reasons"])
        lines.extend(["", "**收益：**", ""])
        lines.extend(f"- {value}" for value in concept["benefits"])
        lines.extend(["", "**取舍：**", ""])
        lines.extend(f"- {value}" for value in concept["tradeoffs"])
        lines.extend(["", "**官方依据：**", ""])
        for claim in concept["source_claims"]:
            source = sources[str(claim["source_id"])]
            lines.append(
                f"- [{source.title}]({source.url})"
                f"（{claim_status_labels[str(claim['status'])]}）：{claim['claim']}"
            )
        lines.append("")
    lines.extend(["</details>", ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_lesson(
    title: str,
    lesson: dict[str, Any],
    *,
    sources: dict[str, SourceReference],
    assessed: bool = False,
    study_minutes: dict[str, Any] | None = None,
    practice_links: Iterable[dict[str, str]] = (),
) -> str:
    if not assessed:
        return _render_legacy_lesson(title, lesson, sources=sources)
    if study_minutes is None:
        raise SourceValidationError("assessed lesson needs study_minutes")
    return _render_assessed_lesson(
        title,
        lesson,
        sources=sources,
        study_minutes=study_minutes,
        practice_links=practice_links,
    )


def _lab_lesson_title(lab_id: str, title: str) -> str:
    """Give compiled Lab Markdown a stable, zero-padded heading."""

    canonical = f"Lab {lab_id.removeprefix('lab')}"
    if title.casefold() == canonical.casefold():
        return canonical
    return f"{canonical}: {title}"


def _validate_quiz(
    items: Any,
    *,
    label: str,
    concept_ids: set[str],
    outcome_ids: set[str],
) -> tuple[tuple[dict[str, Any], ...], tuple[tuple[int, int], ...]]:
    questions = _list(items, label=label)
    if not questions:
        raise SourceValidationError(f"{label} must contain at least one question")
    seen: set[str] = set()
    kinds: set[str] = set()
    validated: list[dict[str, Any]] = []
    positions: list[tuple[int, int]] = []
    for index, raw in enumerate(questions):
        item_label = f"{label}[{index}]"
        question = _mapping(raw, label=item_label)
        _require_exact_fields(question, QUIZ_QUESTION_FIELDS, label=item_label)
        question_id = _stable_id(question, label=item_label)
        if question_id in seen:
            raise SourceValidationError(f"duplicate quiz id: {question_id}")
        seen.add(question_id)
        kind = _text(question, "kind", label=item_label)
        if kind not in QUIZ_KINDS:
            raise SourceValidationError(
                f"{item_label}.kind must be execution_trace or diagnostic"
            )
        kinds.add(kind)
        _text(question, "prompt", label=item_label)
        choices = _list(question.get("choices"), label=f"{item_label}.choices")
        if not 3 <= len(choices) <= 4:
            raise SourceValidationError(f"{item_label}.choices must contain 3-4 choices")
        choice_ids: list[str] = []
        for choice_index, raw_choice in enumerate(choices):
            choice_label = f"{item_label}.choices[{choice_index}]"
            choice = _mapping(raw_choice, label=choice_label)
            _require_exact_fields(choice, QUIZ_CHOICE_FIELDS, label=choice_label)
            choice_id = _stable_id(choice, label=choice_label)
            if choice_id in choice_ids:
                raise SourceValidationError(f"duplicate choice id: {choice_id}")
            choice_ids.append(choice_id)
            _text(choice, "text", label=choice_label)
            _text(choice, "feedback", label=choice_label)
        answer_id = _text(question, "answer_id", label=item_label)
        if answer_id not in choice_ids:
            raise SourceValidationError(f"{item_label}.answer_id must reference a choice")
        positions.append((choice_ids.index(answer_id), len(choice_ids)))
        _text(question, "explanation", label=question_id)
        _validate_mappings(
            question,
            label=item_label,
            concept_ids=concept_ids,
            outcome_ids=outcome_ids,
        )
        validated.append(question)
    missing = QUIZ_KINDS - kinds
    if missing:
        raise SourceValidationError(
            f"{label} must include execution_trace and diagnostic questions"
        )
    return tuple(validated), tuple(positions)


def _selector_file(selector: str, *, hidden: bool) -> Path:
    raw_path = selector.split("::", 1)[0]
    relative = _relative(raw_path, label="test selector")
    if hidden:
        prefix = Path("tests/hidden")
        try:
            return relative.relative_to(prefix)
        except ValueError as error:
            raise SourceValidationError(
                f"hidden test selector must start with tests/hidden/: {selector}"
            ) from error
    return relative


def _selector_node(selector: str) -> str:
    _raw_path, separator, node = selector.partition("::")
    if not separator or not node or "::" in node:
        raise SourceValidationError(
            f"test selector must include exactly one node: {selector}"
        )
    if not node.startswith("test_"):
        raise SourceValidationError(f"test selector node must start with test_: {selector}")
    return node


def _public_selector_file(selector: str, *, lab_id: str) -> Path:
    relative = _selector_file(selector, hidden=False)
    try:
        return relative.relative_to(Path(lab_id) / "tests")
    except ValueError as error:
        raise SourceValidationError(
            f"public test selector must start with {lab_id}/tests/: {selector}"
        ) from error


def _declares_symbol(path: Path, symbol: str) -> bool:
    try:
        module = ast.parse(path.read_text(), filename=str(path))
    except (FileNotFoundError, SyntaxError) as error:
        raise SourceValidationError(f"cannot inspect Python file {path}: {error}") from error
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == symbol
        for node in module.body
    )


def _validate_test_selector(path: Path, selector: str) -> None:
    node_name = _selector_node(selector)
    module = _parse_python(
        _read_text(path, label=f"{selector} source"),
        label=f"{selector} source",
    )
    if not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == node_name
        for node in module.body
    ):
        raise SourceValidationError(
            f"{selector} source does not declare {node_name}"
        )


def _validate_question(
    raw: Any,
    *,
    label: str,
    lab_root: Path,
    concept_ids: set[str],
    outcome_ids: set[str],
) -> CodingQuestion:
    payload = _mapping(raw, label=label)
    unknown_fields = sorted(set(payload) - SOURCE_QUESTION_FIELDS)
    if unknown_fields:
        raise SourceValidationError(
            f"{label} has unknown field(s): {', '.join(unknown_fields)}"
        )
    question_id = _stable_id(payload, label=label)
    lab_id = lab_root.name
    if not question_id.startswith(f"{lab_id}.q"):
        raise SourceValidationError(
            f"{label}.id must use the {lab_id}.q prefix"
        )
    _text(payload, "title", label=question_id)
    _text(payload, "prompt", label=question_id)
    kind = _text(payload, "kind", label=question_id)
    if kind not in QUESTION_KINDS:
        raise SourceValidationError(
            f"{question_id}.kind must be official_bridge, reimplementation, or integration"
        )
    mapped_concepts, mapped_outcomes = _validate_mappings(
        payload,
        label=question_id,
        concept_ids=concept_ids,
        outcome_ids=outcome_ids,
    )
    file_value = _text(payload, "file", label=question_id)
    file_path = _relative(file_value, label=f"{question_id} file")
    if not file_path.parts or file_path.parts[0] != lab_id:
        raise SourceValidationError(
            f"{question_id} file must stay under {lab_id}/: {file_value}"
        )
    symbol = _text(payload, "symbol", label=question_id)
    points = payload.get("points")
    if not isinstance(points, int) or isinstance(points, bool) or points <= 0:
        raise SourceValidationError(f"{question_id} points must be a positive integer")
    timeout_seconds = payload.get("timeout_seconds", 30)
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 90
    ):
        raise SourceValidationError(
            f"{question_id} timeout_seconds must be an integer from 1 to 90"
        )
    tests = _mapping(payload.get("tests"), label=f"{question_id}.tests")
    public = tuple(
        str(item)
        for item in _list(tests.get("public"), label=f"{question_id}.tests.public")
    )
    hidden = tuple(
        str(item)
        for item in _list(tests.get("hidden"), label=f"{question_id}.tests.hidden")
    )
    if not public or not hidden:
        raise SourceValidationError(f"{question_id} needs public and hidden tests")
    if len(public) != 1 or len(hidden) != 1:
        raise SourceValidationError(
            f"{question_id} needs exactly one public and hidden test"
        )
    example = _mapping(payload.get("example"), label=f"{question_id}.example")
    unknown_example_fields = sorted(set(example) - set(QUESTION_EXAMPLE_FIELDS))
    if unknown_example_fields:
        raise SourceValidationError(
            f"{question_id}.example has unknown field(s): {', '.join(unknown_example_fields)}"
        )
    for key in QUESTION_EXAMPLE_FIELDS:
        _text(example, key, label=f"{question_id}.example")

    starter = lab_root / "starter" / file_path
    reference = lab_root / "reference" / file_path
    for implementation, implementation_kind in (
        (starter, "starter"),
        (reference, "reference"),
    ):
        if not implementation.is_file():
            raise SourceValidationError(
                f"missing {implementation_kind} file for {question_id}: {implementation}"
            )
        if not _declares_symbol(implementation, symbol):
            raise SourceValidationError(
                f"{implementation_kind} file {implementation} does not declare symbol {symbol}"
            )
    for selector in public:
        path = lab_root / "tests/public" / _public_selector_file(
            selector, lab_id=lab_id
        )
        if not path.is_file():
            raise SourceValidationError(f"missing public test for {question_id}: {path}")
        _validate_test_selector(path, selector)
    for selector in hidden:
        path = lab_root / "tests/hidden" / _selector_file(selector, hidden=True)
        if not path.is_file():
            raise SourceValidationError(f"missing hidden test for {question_id}: {path}")
        _validate_test_selector(path, selector)

    normalized = copy.deepcopy(payload)
    normalized["timeout_seconds"] = timeout_seconds
    return CodingQuestion(
        question_id=question_id,
        kind=kind,
        file=file_value,
        symbol=symbol,
        concept_ids=mapped_concepts,
        outcome_ids=mapped_outcomes,
        points=points,
        timeout_seconds=timeout_seconds,
        public_tests=public,
        hidden_tests=hidden,
        raw=normalized,
    )


def load_course_source(source_root: Path | str) -> CourseSource:
    unresolved_root = Path(source_root).absolute()
    _validate_source_tree(unresolved_root)
    root = unresolved_root.resolve()
    course = _read_json(root / "course.json", label="course.json")
    schema_version = course.get("schema_version")
    if schema_version not in {2, 3}:
        raise SourceValidationError("course.json schema_version must be 2 or 3")
    _require_fields_with_optional(
        course,
        COURSE_SOURCE_V2_FIELDS if schema_version == 2 else COURSE_SOURCE_V3_FIELDS,
        COURSE_SOURCE_OPTIONAL_FIELDS,
        label="course.json",
    )
    course_id = _text(course, "id", label="course")
    title = _text(course, "title", label="course")
    description = _text(course, "description", label="course")
    audience = _validate_audience(course, schema_version=schema_version)
    _validate_course_manifest(
        course, audience=audience, schema_version=schema_version
    )
    assessed_profile = (
        _mapping(
            audience.get("prerequisite_profile"),
            label="course.audience.prerequisite_profile",
        )
        if audience["level"] == "assessed"
        else None
    )
    size = _text(course, "size", label="course")
    if size not in LAB_BOUNDS:
        raise SourceValidationError("course.size must be small, medium, or large")
    raw_dependencies = _list(course.get("dependencies", []), label="course.dependencies")
    if not all(
        isinstance(value, str) and value.strip() and _requirement(value)
        for value in raw_dependencies
    ):
        raise SourceValidationError(
            "course.dependencies must contain pinned or bounded PEP 508 requirement strings"
        )
    dependencies = tuple(str(value) for value in raw_dependencies)
    curriculum_id = _text(course, "curriculum_id", label="course")
    if schema_version == 2:
        expected_curriculum_id = f"{course_id}-v2"
    else:
        profile = _mapping(
            audience.get("prerequisite_profile"),
            label="course.audience.prerequisite_profile",
        )
        expected_curriculum_id = (
            f"{course_id}-v3-{profile['readiness_summary']}"
        )
    if curriculum_id != expected_curriculum_id:
        raise SourceValidationError(
            f"course.curriculum_id must be {expected_curriculum_id}"
        )

    source_payload = _read_json(root / "sources.json", label="sources.json")
    target = copy.deepcopy(
        _mapping(source_payload.get("target"), label="sources.json.target")
    )
    for key in ("name", "kind", "version", "breadth"):
        _text(target, key, label="target")
    if target["kind"] not in {"stdlib", "pypi", "framework", "repository"}:
        raise SourceValidationError(
            "target.kind must be stdlib, pypi, framework, or repository"
        )
    if target["kind"] != "stdlib" and not dependencies:
        raise SourceValidationError(
            "third-party targets require pinned course.dependencies"
        )
    if target["breadth"] not in {"focused", "broad"}:
        raise SourceValidationError("target.breadth must be focused or broad")
    track = target.get("track")
    if target["breadth"] == "broad" and (
        not isinstance(track, str) or not track.strip()
    ):
        raise SourceValidationError("a broad target requires a non-empty target.track")
    if target["breadth"] == "broad" and size != "large":
        raise SourceValidationError("a broad target requires course.size large")
    import_roots = _strings(
        target.get("import_roots"), label="sources.json.target.import_roots"
    )
    if any("." in value or not value.replace("_", "a").isidentifier() for value in import_roots):
        raise SourceValidationError("target.import_roots must be top-level Python imports")
    sources: list[SourceReference] = []
    source_ids: set[str] = set()
    raw_sources = _list(source_payload.get("sources"), label="sources.json.sources")
    if not raw_sources:
        raise SourceValidationError("target official sources must not be empty")
    if target.get("official_sources") != raw_sources:
        raise SourceValidationError(
            "sources.json target.official_sources must match sources.json.sources"
        )
    for index, raw in enumerate(raw_sources):
        payload = _mapping(raw, label=f"sources[{index}]")
        source_id = _text(payload, "id", label=f"sources[{index}]")
        if source_id in source_ids:
            raise SourceValidationError(f"duplicate source id: {source_id}")
        source_ids.add(source_id)
        url = _text(payload, "url", label=source_id)
        if not _official_source_url(url):
            raise SourceValidationError(f"source URL must be an HTTPS URL: {url}")
        sources.append(
            SourceReference(source_id, _text(payload, "title", label=source_id), url)
        )
    source_map = {source.source_id: source for source in sources}

    research = copy.deepcopy(
        _mapping(course.get("research"), label="course.research")
    )
    if research.get("status") != "complete":
        raise SourceValidationError("research.status must be complete")
    _text(research, "version_basis", label="research")
    _strings(research.get("notes"), label="research.notes")

    preparatory_units: list[PreparatoryUnitSource] = []
    if schema_version == 2:
        foundations = _mapping(course.get("foundations"), label="course.foundations")
        _validate_foundation_manifest(foundations)
        foundation_id = _identifier(
            _text(foundations, "id", label="foundations"), label="foundations.id"
        )
        if foundation_id != "lab00":
            raise SourceValidationError("foundation id must be lab00")
        if assessed_profile is not None or "study_minutes" in foundations:
            _validate_study_minutes(
                foundations.get("study_minutes"),
                label="foundation.study_minutes",
                foundation=True,
            )
        foundation_lesson_path = root / _relative(
            _text(foundations, "lesson", label="foundations"),
            label="foundation lesson",
        )
        if foundation_lesson_path.name != "lesson.json":
            raise SourceValidationError("foundation lesson must be lesson.json")
        (
            foundation_lesson_outline,
            foundation_concepts,
            foundation_outcomes,
        ) = _load_lesson(
            foundation_lesson_path,
            label="foundation lesson",
            source_ids=source_ids,
            assessed=assessed_profile is not None,
        )
        foundation_concept_sources = {
            str(concept["id"]): {
                str(claim["source_id"]) for claim in concept["source_claims"]
            }
            for concept in foundation_lesson_outline["concepts"]
        }
        foundation_quiz_path = root / _relative(
            _text(foundations, "quiz", label="foundations"),
            label="foundation quiz",
        )
        foundation_quiz_payload = _read_json(
            foundation_quiz_path, label="foundation quiz"
        )
        foundation_quiz, foundation_positions = _validate_quiz(
            foundation_quiz_payload.get("questions"),
            label="foundation quiz",
            concept_ids=foundation_concepts,
            outcome_ids=foundation_outcomes,
        )
        if assessed_profile is not None:
            _validate_assessed_coverage(
                foundation_lesson_outline,
                label="lab00",
                concept_ids=foundation_concepts,
                outcome_ids=foundation_outcomes,
                quiz=foundation_quiz,
                questions=None,
            )
        foundation_practice_links = _derive_practice_links(
            foundation_lesson_outline,
            foundation_quiz,
            kind="knowledge-check",
        )
        foundation_lesson = _render_lesson(
            _text(foundations, "title", label="foundations"),
            foundation_lesson_outline,
            sources=source_map,
            assessed=assessed_profile is not None,
            study_minutes=foundations.get("study_minutes"),
            practice_links=foundation_practice_links,
        )
        initial_dependency = foundation_id
        initial_quiz_ids = {
            str(question["id"]) for question in foundation_quiz
        }
        initial_quiz_positions = list(foundation_positions)
    else:
        foundations = {}
        foundation_id = "lab00"
        foundation_lesson = ""
        foundation_lesson_outline = {}
        foundation_concepts: set[str] = set()
        foundation_outcomes: set[str] = set()
        foundation_concept_sources: dict[str, set[str]] = {}
        foundation_quiz = ()
        raw_preparatory_order = _list(
            course.get("preparatory_order"), label="preparatory_order"
        )
        preparatory_order = [str(item) for item in raw_preparatory_order]
        if (
            not preparatory_order
            or preparatory_order[0] != "lab00"
            or len(preparatory_order) != len(set(preparatory_order))
        ):
            raise SourceValidationError(
                "preparatory_order must start with lab00 and contain unique ids"
            )
        raw_preparatory = course.get("preparatory_units")
        if isinstance(raw_preparatory, dict):
            preparatory_registry = {
                str(key): _mapping(value, label=f"preparatory_units.{key}")
                for key, value in raw_preparatory.items()
            }
        elif isinstance(raw_preparatory, list):
            preparatory_registry = {}
            for index, value in enumerate(raw_preparatory):
                item = _mapping(value, label=f"preparatory_units[{index}]")
                item_id = _text(
                    item, "id", label=f"preparatory_units[{index}]"
                )
                if item_id in preparatory_registry:
                    raise SourceValidationError(
                        f"duplicate preparatory unit id: {item_id}"
                    )
                preparatory_registry[item_id] = item
        else:
            raise SourceValidationError(
                "course.preparatory_units must be an object or array"
            )
        if set(preparatory_registry) != set(preparatory_order):
            raise SourceValidationError(
                "preparatory_units must exactly match preparatory_order"
            )

        prep_quiz_ids: set[str] = set()
        prep_quiz_positions: list[tuple[int, int]] = []
        previous_unit: str | None = None
        previous_level = 0
        for index, unit_id in enumerate(preparatory_order):
            expected_id = "lab00" if index == 0 else f"prep{index:02d}"
            if unit_id != expected_id:
                raise SourceValidationError(
                    f"preparatory units must be ordered linearly as {expected_id}"
                )
            payload = preparatory_registry[unit_id]
            _require_exact_fields(
                payload, PREPARATORY_SOURCE_FIELDS, label=f"preparatory_units.{unit_id}"
            )
            if _text(payload, "id", label=unit_id) != unit_id:
                raise SourceValidationError(
                    f"preparatory_order id {unit_id} does not match declared id"
                )
            title_value = _text(payload, "title", label=unit_id)
            category = _text(payload, "category", label=unit_id)
            if index == 0:
                if category != "orientation" or payload.get("depends_on") is not None:
                    raise SourceValidationError(
                        "lab00 must be an orientation with null depends_on"
                    )
            else:
                if category not in {"python", "library", "domain"}:
                    raise SourceValidationError(
                        f"{unit_id}.category must be python, library, or domain"
                    )
                if payload.get("depends_on") != previous_unit:
                    raise SourceValidationError(
                        f"{unit_id}.depends_on must be {previous_unit}"
                    )
            dag_level = payload.get("dag_level")
            if (
                type(dag_level) is not int
                or dag_level < (0 if index == 0 else 1)
                or (index == 0 and dag_level != 0)
                or (index > 0 and dag_level < previous_level)
            ):
                raise SourceValidationError(
                    f"{unit_id}.dag_level is inconsistent with preparatory order"
                )
            previous_level = dag_level
            raw_capability_ids = _list(
                payload.get("capability_ids"), label=f"{unit_id}.capability_ids"
            )
            if not all(
                isinstance(value, str) and value.strip()
                for value in raw_capability_ids
            ) or len(raw_capability_ids) != len(set(raw_capability_ids)):
                raise SourceValidationError(
                    f"{unit_id}.capability_ids must contain unique strings"
                )
            capability_ids = tuple(str(value) for value in raw_capability_ids)
            if (index == 0 and capability_ids) or (index > 0 and not capability_ids):
                raise SourceValidationError(
                    f"{unit_id}.capability_ids do not match its preparatory role"
                )
            _validate_preparatory_study_minutes(
                payload.get("study_minutes"),
                label=f"{unit_id}.study_minutes",
                orientation=index == 0,
            )
            _validate_preparatory_manifest(
                payload, unit_id=unit_id, order=index
            )
            unit_root = root / "preparatory_units" / _relative(
                unit_id, label="preparatory unit id"
            )
            for forbidden in ("starter", "reference", "tests"):
                if (unit_root / forbidden).exists():
                    raise SourceValidationError(
                        f"{unit_id} is knowledge-only and cannot contain {forbidden}"
                    )
            lesson_relative = _relative(
                _text(payload, "lesson", label=unit_id),
                label=f"{unit_id} lesson",
            )
            lesson_path = root / lesson_relative
            if lesson_path.parent != unit_root:
                raise SourceValidationError(
                    f"{unit_id} lesson must live under preparatory_units/{unit_id}"
                )
            if lesson_path.name != "lesson.json":
                raise SourceValidationError(f"{unit_id} lesson must be lesson.json")
            lesson_outline, concept_ids, outcome_ids = _load_lesson(
                lesson_path,
                label=f"{unit_id} lesson",
                source_ids=source_ids,
                assessed=True,
            )
            quiz_relative = _relative(
                _text(payload, "quiz", label=unit_id),
                label=f"{unit_id} quiz",
            )
            quiz_path = root / quiz_relative
            if quiz_path.parent != unit_root:
                raise SourceValidationError(
                    f"{unit_id} quiz must live under preparatory_units/{unit_id}"
                )
            quiz_payload = _read_json(quiz_path, label=f"{unit_id} quiz")
            quiz, positions = _validate_quiz(
                quiz_payload.get("questions"),
                label=f"{unit_id} quiz",
                concept_ids=concept_ids,
                outcome_ids=outcome_ids,
            )
            for question in quiz:
                quiz_id = str(question["id"])
                if quiz_id in prep_quiz_ids:
                    raise SourceValidationError(f"duplicate quiz id: {quiz_id}")
                prep_quiz_ids.add(quiz_id)
            prep_quiz_positions.extend(positions)
            _validate_assessed_coverage(
                lesson_outline,
                label=unit_id,
                concept_ids=concept_ids,
                outcome_ids=outcome_ids,
                quiz=quiz,
                questions=None,
            )
            practice_links = _derive_practice_links(
                lesson_outline, quiz, kind="knowledge-check"
            )
            lesson = _render_lesson(
                title_value,
                lesson_outline,
                sources=source_map,
                assessed=True,
                study_minutes=payload["study_minutes"],
                practice_links=practice_links,
            )
            declared_source_ids = tuple(
                dict.fromkeys(
                    str(claim["source_id"])
                    for concept in lesson_outline["concepts"]
                    for claim in concept["source_claims"]
                )
            )
            preparatory_units.append(
                PreparatoryUnitSource(
                    unit_id=unit_id,
                    title=title_value,
                    category=category,
                    dag_level=dag_level,
                    depends_on=(
                        str(payload["depends_on"])
                        if payload.get("depends_on") is not None
                        else None
                    ),
                    capability_ids=capability_ids,
                    source_ids=declared_source_ids,
                    quiz=quiz,
                    root=unit_root,
                    lesson=lesson,
                    lesson_outline=lesson_outline,
                    raw=copy.deepcopy(payload),
                )
            )
            previous_unit = unit_id
        initial_dependency = preparatory_units[-1].unit_id
        initial_quiz_ids = prep_quiz_ids
        initial_quiz_positions = prep_quiz_positions

    order = [str(item) for item in _list(course.get("lab_order"), label="lab_order")]
    if not order or len(order) != len(set(order)):
        raise SourceValidationError("lab_order must contain unique Lab ids")
    if set(order).intersection({foundation_id, *(unit.unit_id for unit in preparatory_units)}):
        raise SourceValidationError(
            "preparatory and graded Lab ids must be distinct"
        )
    lower, upper = LAB_BOUNDS[size]
    if not lower <= len(order) <= upper:
        raise SourceValidationError(
            f"a {size} course must contain {lower}-{upper} graded labs"
        )
    labs: list[LabSource] = []
    question_ids: set[str] = set()
    quiz_ids = set(initial_quiz_ids)
    quiz_positions = list(initial_quiz_positions)
    prior_mini_modules: list[str] = []
    prior_course_roots: list[str] = []
    previous_target_symbols: tuple[str, ...] | None = None
    previous = initial_dependency
    for offset, lab_id in enumerate(order, start=1):
        _identifier(lab_id, label="lab id")
        expected_id = f"lab{offset:02d}"
        if lab_id != expected_id:
            raise SourceValidationError(f"labs must be ordered linearly as {expected_id}")
        lab_root = root / "labs" / _relative(lab_id, label="lab id")
        payload = _read_json(lab_root / "lab.json", label=f"{lab_id}/lab.json")
        _validate_lab_manifest(payload, label=lab_id)
        declared_id = _text(payload, "id", label=f"{lab_id}/lab.json")
        if declared_id != lab_id:
            raise SourceValidationError(
                f"lab_order id {lab_id} does not match declared id {declared_id}"
            )
        depends_on = _text(payload, "depends_on", label=lab_id)
        if depends_on != previous:
            raise SourceValidationError(
                f"{lab_id} must depend on {previous}, not {depends_on}"
            )
        if assessed_profile is not None or "study_minutes" in payload:
            _validate_study_minutes(
                payload.get("study_minutes"),
                label=f"{lab_id}.study_minutes",
                foundation=False,
            )
        declared_sources = tuple(
            str(item)
            for item in _list(payload.get("sources"), label=f"{lab_id}.sources")
        )
        if not declared_sources:
            raise SourceValidationError(
                f"{lab_id}.sources must reference official sources"
            )
        unknown_sources = sorted(set(declared_sources) - source_ids)
        if unknown_sources:
            raise SourceValidationError(
                f"{lab_id} references unknown source(s): {', '.join(unknown_sources)}"
            )
        lesson_path = lab_root / _relative(
            _text(payload, "lesson", label=lab_id), label=f"{lab_id} lesson"
        )
        if lesson_path.name != "lesson.json":
            raise SourceValidationError(f"{lab_id} lesson must be lesson.json")
        lesson_outline, concept_ids, outcome_ids = _load_lesson(
            lesson_path,
            label=f"{lab_id} lesson",
            source_ids=source_ids,
            assessed=assessed_profile is not None,
        )
        declared_files: dict[str, tuple[ast.Module, ast.Module]] = {}
        declared_file_order: list[str] = []
        for file_index, raw_file in enumerate(
            _list(payload.get("files"), label=f"{lab_id}.files")
        ):
            file_label = f"{lab_id}.files[{file_index}]"
            file_payload = _mapping(raw_file, label=file_label)
            file_value = _text(file_payload, "path", label=file_label)
            file_path = _relative(file_value, label=f"{file_label}.path")
            if not file_path.parts or file_path.parts[0] != lab_id or file_path.suffix != ".py":
                raise SourceValidationError(
                    f"{file_label}.path must be a Python file under {lab_id}/"
                )
            if file_value in declared_files:
                raise SourceValidationError(f"duplicate Lab file: {file_value}")
            starter_code = _read_text(
                lab_root / "starter" / file_path, label=f"{file_label} starter"
            )
            reference_code = _read_text(
                lab_root / "reference" / file_path, label=f"{file_label} reference"
            )
            declared_files[file_value] = (
                _parse_python(starter_code, label=f"{file_label}.starter"),
                _parse_python(reference_code, label=f"{file_label}.reference"),
            )
            declared_file_order.append(file_value)
        if not declared_files:
            raise SourceValidationError(f"{lab_id}.files must not be empty")

        questions = tuple(
            _validate_question(
                raw,
                label=f"{lab_id}.questions[{index}]",
                lab_root=lab_root,
                concept_ids=concept_ids,
                outcome_ids=outcome_ids,
            )
            for index, raw in enumerate(
                _list(payload.get("questions"), label=f"{lab_id}.questions")
            )
        )
        if not 1 <= len(questions) <= 3:
            raise SourceValidationError(f"{lab_id} must declare 1-3 coding questions")
        for question in questions:
            if question.file not in declared_files:
                raise SourceValidationError(
                    f"{question.question_id}.file is not declared in {lab_id}.files"
                )
            if question.question_id in question_ids:
                raise SourceValidationError(
                    f"duplicate coding question id: {question.question_id}"
                )
            question_ids.add(question.question_id)
        quiz, positions = _validate_quiz(
            payload.get("quiz"),
            label=f"{lab_id}.quiz",
            concept_ids=concept_ids,
            outcome_ids=outcome_ids,
        )
        for question in quiz:
            quiz_id = str(question["id"])
            if quiz_id in quiz_ids:
                raise SourceValidationError(f"duplicate quiz id: {quiz_id}")
            quiz_ids.add(quiz_id)
        quiz_positions.extend(positions)
        if assessed_profile is not None:
            _validate_assessed_coverage(
                lesson_outline,
                label=lab_id,
                concept_ids=concept_ids,
                outcome_ids=outcome_ids,
                quiz=quiz,
                questions=questions,
            )
        practice_links = _derive_practice_links(
            lesson_outline,
            questions,
            kind="coding-question",
        )
        lesson = _render_lesson(
            _lab_lesson_title(lab_id, _text(payload, "title", label=lab_id)),
            lesson_outline,
            sources=source_map,
            assessed=assessed_profile is not None,
            study_minutes=payload.get("study_minutes"),
            practice_links=practice_links,
        )

        questions_by_id = {question.question_id: question for question in questions}
        cycle = _mapping(payload.get("module_cycle"), label=f"{lab_id}.module_cycle")
        reimplementation = _mapping(
            cycle.get("reimplementation"),
            label=f"{lab_id}.module_cycle.reimplementation",
        )
        reimplementation_label = f"{lab_id}.module_cycle.reimplementation"
        module_id = _text(reimplementation, "module_id", label=reimplementation_label)
        if not IDENTIFIER_PATTERN.fullmatch(module_id.replace(".", "-")):
            raise SourceValidationError(f"{reimplementation_label}.module_id is invalid")
        _text(reimplementation, "title", label=reimplementation_label)
        target_symbols = _strings(
            reimplementation.get("target_symbols"),
            label=f"{reimplementation_label}.target_symbols",
        )
        _strings(
            reimplementation.get("lower_level_dependencies"),
            label=f"{reimplementation_label}.lower_level_dependencies",
        )
        learner_file = _text(
            reimplementation, "learner_file", label=reimplementation_label
        )
        if learner_file not in declared_files:
            raise SourceValidationError(
                f"{reimplementation_label}.learner_file must be a declared Lab file"
            )
        reimplementation_questions = _strings(
            reimplementation.get("question_ids"),
            label=f"{reimplementation_label}.question_ids",
        )
        declared_reimplementation_ids = {
            question.question_id
            for question in questions
            if question.kind == "reimplementation"
        }
        if set(reimplementation_questions) != declared_reimplementation_ids:
            raise SourceValidationError(
                f"{reimplementation_label}.question_ids must list every current reimplementation question"
            )
        if any(
            questions_by_id[question_id].file != learner_file
            for question_id in reimplementation_questions
        ):
            raise SourceValidationError(
                f"{reimplementation_label} requires every reimplementation question.file to equal learner_file"
            )
        forbidden_imports = _strings(
            reimplementation.get("forbidden_imports"),
            label=f"{reimplementation_label}.forbidden_imports",
        )
        if not set(import_roots) <= set(forbidden_imports):
            raise SourceValidationError(
                f"{reimplementation_label}.forbidden_imports must include target.import_roots"
            )
        _validate_reimplementation_closure(
            learner_file=learner_file,
            lab_id=lab_id,
            declared_files=declared_files,
            forbidden_imports=forbidden_imports,
            prior_course_roots=tuple(prior_course_roots),
            label=reimplementation_label,
        )
        for file_value, modules in declared_files.items():
            for module in modules:
                imported = _imports(module)
                if any(
                    _imports_root(imported, prior_module)
                    for prior_module in (*prior_mini_modules, *prior_course_roots)
                ):
                    raise SourceValidationError(
                        f"{file_value} imports a prior mini implementation or another prior Lab helper"
                    )
        for question in questions:
            for selector, hidden in (
                (question.public_tests[0], False),
                (question.hidden_tests[0], True),
            ):
                if hidden:
                    relative = _selector_file(selector, hidden=True)
                    test_path = lab_root / "tests/hidden" / relative
                else:
                    relative = _public_selector_file(selector, lab_id=lab_id)
                    test_path = lab_root / "tests/public" / relative
                imported = _imports(
                    _parse_python(
                        _read_text(test_path, label=f"{selector} source"),
                        label=f"{selector} source",
                    )
                )
                if any(
                    _imports_root(imported, prior_module)
                    for prior_module in (*prior_mini_modules, *prior_course_roots)
                ):
                    raise SourceValidationError(
                        f"{selector} imports a prior mini implementation or another prior Lab helper"
                    )

        if offset == 1:
            if payload.get("official_bridge") is not None:
                raise SourceValidationError("lab01 must not declare official_bridge")
        else:
            bridge = _mapping(
                payload.get("official_bridge"), label=f"{lab_id}.official_bridge"
            )
            bridge_label = f"{lab_id}.official_bridge"
            if _text(bridge, "from_lab", label=bridge_label) != previous:
                raise SourceValidationError(
                    f"{bridge_label}.from_lab must be the immediately previous Lab"
                )
            mini_module = _text(bridge, "mini_module", label=bridge_label)
            if not prior_mini_modules or mini_module != prior_mini_modules[-1]:
                raise SourceValidationError(
                    f"{bridge_label}.mini_module must name the previous teaching module"
                )
            official_symbols = _strings(
                bridge.get("official_symbols"),
                label=f"{bridge_label}.official_symbols",
            )
            if previous_target_symbols is None or set(official_symbols) != set(
                previous_target_symbols
            ):
                raise SourceValidationError(
                    f"previous reimplementation target_symbols must equal {bridge_label}.official_symbols"
                )
            required_imports = _strings(
                bridge.get("required_imports"),
                label=f"{bridge_label}.required_imports",
            )
            if not set(required_imports) <= set(import_roots):
                raise SourceValidationError(
                    f"{bridge_label}.required_imports must reference target.import_roots"
                )
            bridge_question_id = _text(bridge, "question_id", label=bridge_label)
            if (
                not questions
                or questions[0].question_id != bridge_question_id
                or questions[0].kind != "official_bridge"
            ):
                raise SourceValidationError(
                    f"{lab_id} first coding question must be the official_bridge"
                )
            bridge_question = questions_by_id.get(bridge_question_id)
            if bridge_question is None:
                raise SourceValidationError(
                    f"{bridge_label}.question_id must reference a coding question"
                )
            for module in declared_files[bridge_question.file]:
                imported = _imports(module)
                missing_imports = [
                    root_name
                    for root_name in required_imports
                    if not _imports_root(imported, root_name)
                ]
                if missing_imports:
                    raise SourceValidationError(
                        f"{bridge_label} question file is missing required import(s): {', '.join(missing_imports)}"
                    )
            observables = _list(
                bridge.get("observables"), label=f"{bridge_label}.observables"
            )
            observable_ids: set[str] = set()
            for observable_index, raw_observable in enumerate(observables):
                observable_label = f"{bridge_label}.observables[{observable_index}]"
                observable = _mapping(raw_observable, label=observable_label)
                observable_id = _stable_id(observable, label=observable_label)
                if observable_id in observable_ids:
                    raise SourceValidationError(
                        f"duplicate official bridge observable: {observable_id}"
                    )
                observable_ids.add(observable_id)
                _text(observable, "description", label=observable_label)
            if not observable_ids:
                raise SourceValidationError(f"{bridge_label}.observables must not be empty")
            covered: set[str] = set()
            cases = _list(
                bridge.get("comparison_cases"),
                label=f"{bridge_label}.comparison_cases",
            )
            for case_index, raw_case in enumerate(cases):
                case_label = f"{bridge_label}.comparison_cases[{case_index}]"
                case = _mapping(raw_case, label=case_label)
                _text(case, "input", label=case_label)
                if "expected" not in case:
                    raise SourceValidationError(
                        f"{case_label}.expected must declare the comparison result"
                    )
                mapped = _strings(
                    case.get("observable_ids"), label=f"{case_label}.observable_ids"
                )
                if not set(mapped) <= observable_ids:
                    raise SourceValidationError(
                        f"{case_label}.observable_ids reference unknown observable"
                    )
                covered.update(mapped)
            if covered != observable_ids:
                raise SourceValidationError(
                    f"{bridge_label}.comparison_cases must cover every observable"
                )

        mini_path = _relative(learner_file, label=f"{reimplementation_label}.learner_file")
        prior_mini_modules.append(".".join((*mini_path.parts[:-1], mini_path.stem)))
        prior_course_roots.append(lab_id)
        previous_target_symbols = target_symbols
        concepts = tuple(str(item["name"]) for item in lesson_outline["concepts"])
        capstone_increment = str(lesson_outline["capstone_bridge"]["increment"])
        labs.append(
            LabSource(
                lab_id=lab_id,
                title=_text(payload, "title", label=lab_id),
                depends_on=depends_on,
                source_ids=declared_sources,
                concepts=concepts,
                capstone_increment=capstone_increment,
                questions=questions,
                quiz=quiz,
                root=lab_root,
                lesson=lesson,
                lesson_outline=lesson_outline,
                raw=copy.deepcopy(payload),
            )
        )
        previous = lab_id

    if assessed_profile is not None and schema_version == 2:
        _validate_assessed_profile_references(
            assessed_profile,
            source_ids=source_ids,
            lab_ids={lab.lab_id for lab in labs},
            foundation_concept_ids=foundation_concepts,
            foundation_concept_sources=foundation_concept_sources,
        )
    elif assessed_profile is not None:
        _validate_v3_profile_references(
            assessed_profile,
            source_ids=source_ids,
            lab_ids={lab.lab_id for lab in labs},
            preparatory_units=tuple(preparatory_units),
        )

    if quiz_positions:
        maximum_choices = max(choice_count for _, choice_count in quiz_positions)
        observed_positions = {position for position, _ in quiz_positions}
        if observed_positions != set(range(maximum_choices)):
            raise SourceValidationError("quiz answer positions must use every position")
        counts = Counter(position for position, _ in quiz_positions)
        if max(counts.values()) / len(quiz_positions) > 0.40:
            raise SourceValidationError(
                "no quiz answer position may exceed 40% of the course"
            )

    compatible = tuple(
        str(item)
        for item in _list(
            course.get("compatible_curriculum_ids", []),
            label="compatible_curriculum_ids",
        )
    )
    if schema_version == 2 and any(value.endswith("-v1") for value in compatible):
        raise SourceValidationError("schema v2 cannot declare a v1 compatible curriculum")
    if schema_version == 3 and compatible != (curriculum_id,):
        raise SourceValidationError(
            "schema v3 compatible_curriculum_ids must contain only its readiness-specific curriculum id"
        )
    extensions = tuple(
        _mapping(item, label="extension")
        for item in _list(course.get("extensions", []), label="extensions")
    )
    return CourseSource(
        schema_version=schema_version,
        course_id=course_id,
        title=title,
        description=description,
        audience=audience,
        curriculum_id=curriculum_id,
        compatible_curriculum_ids=compatible,
        language=_text(course, "language", label="course"),
        python_requires=_python_requires(course),
        size=size,
        dependencies=dependencies,
        capstone=_text(course, "capstone", label="course"),
        extensions=extensions,
        foundation_lesson=foundation_lesson,
        foundation_lesson_outline=foundation_lesson_outline,
        foundation_quiz=foundation_quiz,
        sources=tuple(sources),
        target=target,
        research=research,
        preparatory_units=tuple(preparatory_units),
        labs=tuple(labs),
        root=root,
        course=copy.deepcopy(course),
        foundation=copy.deepcopy(foundations),
    )


def _question_source_policy(
    lab: LabSource,
    question: CodingQuestion,
    *,
    prior_mini_modules: tuple[str, ...],
    prior_course_roots: tuple[str, ...],
) -> dict[str, Any]:
    cycle = _mapping(lab.raw.get("module_cycle"), label=f"{lab.lab_id}.module_cycle")
    reimplementation = _mapping(
        cycle.get("reimplementation"),
        label=f"{lab.lab_id}.module_cycle.reimplementation",
    )
    forbidden_imports: tuple[str, ...] = ()
    if question.kind == "reimplementation":
        forbidden_imports = _strings(
            reimplementation.get("forbidden_imports"),
            label=f"{lab.lab_id}.module_cycle.reimplementation.forbidden_imports",
        )
    required_imports: tuple[str, ...] = ()
    bridge = lab.raw.get("official_bridge")
    if isinstance(bridge, dict) and bridge.get("question_id") == question.question_id:
        required_imports = _strings(
            bridge.get("required_imports"),
            label=f"{lab.lab_id}.official_bridge.required_imports",
        )
    return {
        "local_root": lab.lab_id,
        "required_imports": list(required_imports),
        "forbidden_imports": list(forbidden_imports),
        "prior_mini_modules": list(prior_mini_modules),
        "forbidden_course_roots": list(prior_course_roots),
    }


def _manifest(course: CourseSource, *, learner: bool = False) -> dict[str, Any]:
    labs: list[dict[str, Any]] = []
    prior_mini_modules: list[str] = []
    prior_course_roots: list[str] = []
    for lab in course.labs:
        questions = []
        for question in lab.questions:
            tests: dict[str, Any] = {
                "sample": list(question.public_tests),
                "public": list(question.public_tests),
            }
            if not learner:
                tests["hidden"] = list(question.hidden_tests)
                tests["submit"] = list(
                    dict.fromkeys(question.public_tests + question.hidden_tests)
                )
            else:
                tests["submit"] = list(question.public_tests)
            rendered_question = {
                key: copy.deepcopy(question.raw[key])
                for key in PUBLIC_QUESTION_FIELDS
                if key in question.raw
            }
            rendered_question["example"] = {
                key: copy.deepcopy(question.raw["example"][key])
                for key in QUESTION_EXAMPLE_FIELDS
            }
            rendered_question.update(
                {
                    "id": question.question_id,
                    "file": question.file,
                    "symbol": question.symbol,
                    "points": question.points,
                    "timeout_seconds": question.timeout_seconds,
                    "tests": tests,
                    "source_policy": _question_source_policy(
                        lab,
                        question,
                        prior_mini_modules=tuple(prior_mini_modules),
                        prior_course_roots=tuple(prior_course_roots),
                    ),
                }
            )
            questions.append(rendered_question)

        raw_lab_manifest = _mapping(
            lab.raw.get("manifest", {}), label=f"{lab.lab_id}.manifest"
        )
        rendered_lab = (
            _project_lab_manifest(raw_lab_manifest)
            if learner
            else copy.deepcopy(raw_lab_manifest)
        )
        rendered_lab.update(
            {
                "id": lab.lab_id,
                "title": lab.title,
                "directory": lab.lab_id,
                "readme": f"{lab.lab_id}/README.md",
                "depends_on": lab.depends_on,
                "concepts": list(lab.concepts),
                "questions": questions,
            }
        )
        if course.schema_version == 3:
            rendered_lab.update({"unit_type": "lab", "graded": True})
        if "study_minutes" in lab.raw:
            rendered_lab["study_minutes"] = (
                _project_study_minutes(lab.raw["study_minutes"])
                if learner
                else copy.deepcopy(lab.raw["study_minutes"])
            )
        if learner and isinstance(rendered_lab.get("tests"), dict):
            public = list(
                dict.fromkeys(
                    rendered_lab["tests"].get("public")
                    or rendered_lab["tests"].get("sample")
                    or []
                )
            )
            rendered_lab["tests"] = {
                "public": public,
                "sample": public,
                "submit": public,
            }
        labs.append(rendered_lab)
        reimplementation = lab.raw["module_cycle"]["reimplementation"]
        mini_path = Path(str(reimplementation["learner_file"]))
        prior_mini_modules.append(
            ".".join((*mini_path.parts[:-1], mini_path.stem))
        )
        prior_course_roots.append(lab.lab_id)

    raw_course_manifest = _mapping(
        course.course.get("manifest", {}), label="course.manifest"
    )
    base = (
        _project_course_manifest(
            raw_course_manifest, schema_version=course.schema_version
        )
        if learner
        else copy.deepcopy(raw_course_manifest)
    )
    # Curriculum schema is compiler-owned; canonical metadata cannot downgrade it.
    base["schema_version"] = course.schema_version
    base.setdefault("layout_version", 3)
    base.update(
        {
            "engine_version": 1,
            "course_id": course.course_id,
            "title": course.title,
            "curriculum_id": course.curriculum_id,
            "compatible_curriculum_ids": list(course.compatible_curriculum_ids),
            "language": course.language,
            "audience": (
                _project_audience(course.audience)
                if learner
                else copy.deepcopy(course.audience)
            ),
            "content": "content.json" if not learner else "_course/content.json",
            "extensions": list(course.extensions),
            "total_points": course.total_points,
            "labs": labs,
        }
    )
    profile = course.audience.get("prerequisite_profile")
    if course.audience.get("level") == "assessed" and isinstance(profile, dict):
        capabilities = profile.get("capabilities", [])
        if course.schema_version == 3:
            base["readiness"] = {
                "route_id": str(profile["route_id"]),
                "summary": str(profile["readiness_summary"]),
                "assumed": [
                    str(item["title"])
                    for item in capabilities
                    if isinstance(item, dict) and item.get("decision") == "assume"
                ],
                "preparatory": [
                    str(item["title"])
                    for item in capabilities
                    if isinstance(item, dict)
                    and item.get("decision") == "preparatory"
                ],
            }
        else:
            base["readiness"] = {
                "assumed": [
                    str(item["title"])
                    for item in capabilities
                    if isinstance(item, dict) and item.get("decision") == "assume"
                ],
                "foundation": [
                    str(item["title"])
                    for item in capabilities
                    if isinstance(item, dict) and item.get("decision") == "foundation"
                ],
            }
    if "python" not in base:
        base["python_requires"] = course.python_requires
    if "capstone" not in base:
        base["capstone"] = course.capstone

    if course.schema_version == 2:
        raw_foundation_manifest = _mapping(
            course.foundation.get("manifest", {}), label="foundation.manifest"
        )
        foundation = (
            _project_foundation_manifest(raw_foundation_manifest)
            if learner
            else copy.deepcopy(raw_foundation_manifest)
        )
        foundation.update(
            {
                "id": course.foundation["id"],
                "title": course.foundation["title"],
                "graded": False,
                "directory": course.foundation["id"],
                "readme": f"{course.foundation['id']}/README.md",
            }
        )
        if "study_minutes" in course.foundation:
            foundation["study_minutes"] = (
                _project_study_minutes(course.foundation["study_minutes"])
                if learner
                else copy.deepcopy(course.foundation["study_minutes"])
            )
        if "examples" not in foundation:
            foundation["examples"] = [
                f"{course.foundation['id']}/{example['path']}"
                for example in course.foundation_lesson_outline["examples"]
                if example["kind"] == "runnable"
            ]
        if "demos" in course.foundation:
            if learner:
                _manifest_string_list(
                    course.foundation, "demos", label="foundation", paths=True
                )
                foundation["demos"] = list(course.foundation["demos"])
            else:
                foundation["demos"] = copy.deepcopy(course.foundation["demos"])
        if learner and isinstance(foundation.get("tests"), dict):
            public = list(
                dict.fromkeys(
                    foundation["tests"].get("public")
                    or foundation["tests"].get("sample")
                    or []
                )
            )
            foundation["tests"] = {
                "public": public,
                "sample": public,
                "submit": public,
            }
        base["foundations"] = foundation
    else:
        rendered_units: list[dict[str, Any]] = []
        for order, unit in enumerate(course.preparatory_units):
            raw_manifest = _mapping(
                unit.raw.get("manifest", {}), label=f"{unit.unit_id}.manifest"
            )
            rendered = (
                _project_preparatory_manifest(
                    raw_manifest, unit_id=unit.unit_id, order=order
                )
                if learner
                else copy.deepcopy(raw_manifest)
            )
            rendered.update(
                {
                    "id": unit.unit_id,
                    "title": unit.title,
                    "kind": "preparatory",
                    "unit_type": (
                        "orientation" if unit.unit_id == "lab00" else "preparatory"
                    ),
                    "category": unit.category,
                    "dag_level": unit.dag_level,
                    "depends_on": unit.depends_on,
                    "capability_ids": list(unit.capability_ids),
                    "graded": False,
                    "directory": unit.unit_id,
                    "readme": f"{unit.unit_id}/README.md",
                    "study_minutes": _project_study_minutes(
                        unit.raw["study_minutes"]
                    ),
                }
            )
            if "examples" not in rendered:
                rendered["examples"] = [
                    f"{unit.unit_id}/{example['path']}"
                    for example in unit.lesson_outline["examples"]
                    if example["kind"] == "runnable"
                ]
            rendered_units.append(rendered)
        base["preparatory_units"] = rendered_units
    base["knowledge"] = "knowledge.json" if not learner else "_course/knowledge.json"

    if learner:
        base["starter_root"] = "."
        base["source_root"] = "."
        adapter = base.get("adapter")
        if isinstance(adapter, str) and adapter.startswith("starter/"):
            base["adapter"] = adapter.removeprefix("starter/")
        base["student_workspace"] = True
        base.pop("reference_root", None)
        base.pop("reference_components", None)
    return base


def _knowledge(course: CourseSource) -> dict[str, Any]:
    if course.schema_version == 2:
        preparatory = {
            course.foundation["id"]: {
                "title": course.foundation["title"],
                "questions": [
                    _project_quiz_question(question)
                    for question in course.foundation_quiz
                ],
            }
        }
    else:
        preparatory = {
            unit.unit_id: {
                "title": unit.title,
                "questions": [
                    _project_quiz_question(question) for question in unit.quiz
                ],
            }
            for unit in course.preparatory_units
        }
    return {
        "schema_version": course.schema_version,
        "curriculum_id": course.curriculum_id,
        "title": course.course.get(
            "knowledge_title", f"{course.title} 知识检查"
        ),
        "labs": {
            **preparatory,
            **{
                lab.lab_id: {
                    "title": lab.title,
                    "questions": [
                        _project_quiz_question(question)
                        for question in lab.quiz
                    ],
                }
                for lab in course.labs
            },
        },
    }


def _project_fields(
    payload: dict[str, Any], allowed: set[str]
) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in payload.items()
        if key in allowed
    }


def _project_audience(audience: dict[str, Any]) -> dict[str, Any]:
    if audience.get("level") == "basic-python":
        projected = _project_fields(audience, BASIC_AUDIENCE_FIELDS)
        projected["lab_minutes"] = _project_fields(
            audience["lab_minutes"], BASIC_LAB_MINUTES_FIELDS
        )
        return projected

    projected = _project_fields(audience, ASSESSED_AUDIENCE_FIELDS)
    if (
        isinstance(audience.get("prerequisite_profile"), dict)
        and audience["prerequisite_profile"].get("assessment")
        == "evidence-dialogue"
    ):
        profile = _project_fields(
            audience["prerequisite_profile"],
            V3_PREREQUISITE_PROFILE_FIELDS,
        )
        profile["capabilities"] = [
            _project_fields(capability, V3_CAPABILITY_FIELDS)
            for capability in audience["prerequisite_profile"]["capabilities"]
        ]
        projected["prerequisite_profile"] = profile
        return projected
    profile = _project_fields(
        audience["prerequisite_profile"], PREREQUISITE_PROFILE_FIELDS
    )
    profile["capabilities"] = [
        _project_fields(capability, CAPABILITY_FIELDS)
        for capability in audience["prerequisite_profile"]["capabilities"]
    ]
    projected["prerequisite_profile"] = profile
    return projected


def _project_study_minutes(minutes: dict[str, Any]) -> dict[str, Any]:
    return _project_fields(minutes, STUDY_MINUTES_FIELDS)


def _project_manifest_tests(tests: dict[str, Any]) -> dict[str, Any]:
    _validate_manifest_tests(tests, label="manifest.tests", exact=False)
    return {
        key: list(tests[key])
        for key in ("public", "sample", "hidden", "submit")
    }


def _project_manifest_checkpoint(
    checkpoint: dict[str, Any], *, label: str
) -> dict[str, Any]:
    _validate_manifest_checkpoint(checkpoint, label=label, exact=False)
    return {
        "require_submit": checkpoint["require_submit"],
        "git_initialized": checkpoint["git_initialized"],
        "git_clean": checkpoint["git_clean"],
        "min_commits": checkpoint["min_commits"],
    }


def _project_course_manifest(
    manifest: dict[str, Any], *, schema_version: int = 2
) -> dict[str, Any]:
    _validate_course_manifest_shape(
        manifest,
        label="course.manifest",
        exact=False,
        schema_version=schema_version,
    )
    projected = {
        "schema_version": manifest["schema_version"],
        "layout_version": manifest["layout_version"],
        **{key: manifest[key] for key in COURSE_MANIFEST_TEXT_FIELDS},
        **{key: manifest[key] for key in COURSE_MANIFEST_PATH_FIELDS},
    }
    projected["audience"] = _project_audience(manifest["audience"])
    projected["capstone"] = {
        "name": manifest["capstone"]["name"],
        "description": manifest["capstone"]["description"],
    }
    projected["target"] = {
        "name": manifest["target"]["name"],
        "kind": manifest["target"]["kind"],
        "version": manifest["target"]["version"],
        "track": manifest["target"]["track"],
    }
    if "adapter" in manifest:
        projected["adapter"] = manifest["adapter"]
    if "python" in manifest:
        projected["python"] = manifest["python"]
    if "reference_components" in manifest:
        projected["reference_components"] = list(manifest["reference_components"])
    return projected


def _project_foundation_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _validate_foundation_manifest_shape(
        manifest, label="foundation.manifest", exact=False
    )
    projected = {
        **{key: manifest[key] for key in FOUNDATION_MANIFEST_TEXT_FIELDS},
        **{key: manifest[key] for key in FOUNDATION_MANIFEST_PATH_FIELDS},
        "order": manifest["order"],
        "graded": manifest["graded"],
    }
    projected["checkpoint"] = _project_manifest_checkpoint(
        manifest["checkpoint"], label="foundation.manifest.checkpoint"
    )
    for key in ("demos", "examples"):
        if key in manifest:
            projected[key] = list(manifest[key])
    if "tests" in manifest:
        projected["tests"] = _project_manifest_tests(manifest["tests"])
    return projected


def _project_preparatory_manifest(
    manifest: dict[str, Any], *, unit_id: str, order: int
) -> dict[str, Any]:
    _validate_preparatory_manifest(
        {"manifest": manifest}, unit_id=unit_id, order=order
    )
    projected = {
        **{key: manifest[key] for key in FOUNDATION_MANIFEST_TEXT_FIELDS},
        **{key: manifest[key] for key in FOUNDATION_MANIFEST_PATH_FIELDS},
        "order": manifest["order"],
        "graded": False,
    }
    projected["checkpoint"] = _project_manifest_checkpoint(
        manifest["checkpoint"], label=f"{unit_id}.manifest.checkpoint"
    )
    for key in ("demos", "examples"):
        if key in manifest:
            projected[key] = list(manifest[key])
    return projected


def _project_lab_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _validate_lab_manifest_shape(manifest, label="lab.manifest", exact=False)
    projected = {
        **{key: manifest[key] for key in LAB_MANIFEST_TEXT_FIELDS},
        **{key: manifest[key] for key in LAB_MANIFEST_PATH_FIELDS},
        "order": manifest["order"],
    }
    projected["checkpoint"] = _project_manifest_checkpoint(
        manifest["checkpoint"], label="lab.manifest.checkpoint"
    )
    projected["git_checkpoint"] = {
        "title": manifest["git_checkpoint"]["title"],
        "commands": list(manifest["git_checkpoint"]["commands"]),
    }
    projected["tests"] = _project_manifest_tests(manifest["tests"])
    return projected


def _project_quiz_question(question: dict[str, Any]) -> dict[str, Any]:
    projected = _project_fields(question, QUIZ_QUESTION_FIELDS)
    projected["choices"] = [
        _project_fields(choice, QUIZ_CHOICE_FIELDS)
        for choice in question["choices"]
    ]
    return projected


def _project_operational_contract(contract: dict[str, Any]) -> dict[str, Any]:
    projected = _project_fields(contract, OPERATIONAL_CONTRACT_FIELDS)
    projected["inputs"] = [
        _project_fields(item, OPERATIONAL_INPUT_FIELDS)
        for item in contract["inputs"]
    ]
    projected["outputs"] = [
        _project_fields(item, OPERATIONAL_OUTPUT_FIELDS)
        for item in contract["outputs"]
    ]
    projected["failure_modes"] = [
        _project_fields(item, OPERATIONAL_FAILURE_FIELDS)
        for item in contract["failure_modes"]
    ]
    return projected


def _project_lesson_outline(
    lesson: dict[str, Any], *, assessed: bool
) -> dict[str, Any]:
    projected = _project_fields(lesson, LESSON_FIELDS)
    projected["prerequisites"] = [
        _project_fields(item, PREREQUISITE_FIELDS)
        for item in lesson["prerequisites"]
    ]
    projected["problem"] = _project_fields(lesson["problem"], PROBLEM_FIELDS)
    projected["outcomes"] = [
        _project_fields(item, OUTCOME_FIELDS) for item in lesson["outcomes"]
    ]

    concept_fields = CONCEPT_FIELDS | ({"operational_contract"} if assessed else set())
    concepts: list[dict[str, Any]] = []
    for concept in lesson["concepts"]:
        item = _project_fields(concept, concept_fields)
        item["source_claims"] = [
            _project_fields(claim, SOURCE_CLAIM_FIELDS)
            for claim in concept["source_claims"]
        ]
        if assessed:
            item["operational_contract"] = _project_operational_contract(
                concept["operational_contract"]
            )
        concepts.append(item)
    projected["concepts"] = concepts

    examples: list[dict[str, Any]] = []
    for example in lesson["examples"]:
        if example["kind"] == "runnable":
            allowed = RUNNABLE_EXAMPLE_FIELDS | {"code"}
            if "trace" in example:
                allowed.add("trace")
            item = _project_fields(example, allowed)
            if "trace" in example:
                item["trace"] = [
                    _project_fields(step, TRACE_STEP_FIELDS)
                    for step in example["trace"]
                ]
        else:
            item = _project_fields(example, DIAGNOSTIC_EXAMPLE_FIELDS)
        examples.append(item)
    projected["examples"] = examples
    projected["capstone_bridge"] = _project_fields(
        lesson["capstone_bridge"], CAPSTONE_BRIDGE_FIELDS
    )
    return projected


def _content(course: CourseSource) -> dict[str, Any]:
    sources = {source.source_id: source for source in course.sources}
    assessed = course.course["audience"]["level"] == "assessed"

    def source_payload(source_id: str) -> dict[str, str]:
        source = sources[source_id]
        return {"id": source.source_id, "title": source.title, "url": source.url}

    foundation: dict[str, Any] | None = None
    preparatory: list[dict[str, Any]] = []
    if course.schema_version == 2:
        foundation = {
            "id": course.foundations["id"],
            "title": course.foundations["title"],
            "lesson": course.foundation_lesson,
            "lesson_outline": _project_lesson_outline(
                course.foundation_lesson_outline, assessed=assessed
            ),
            "sources": [
                source_payload(source_id)
                for source_id in dict.fromkeys(
                    str(claim["source_id"])
                    for concept in course.foundation_lesson_outline["concepts"]
                    for claim in concept["source_claims"]
                )
            ],
        }
        if "study_minutes" in course.foundation:
            foundation["study_minutes"] = _project_study_minutes(
                course.foundation["study_minutes"]
            )
        foundation_links = _derive_practice_links(
            course.foundation_lesson_outline,
            course.foundation_quiz,
            kind="knowledge-check",
        )
        if foundation_links:
            foundation["practice_links"] = foundation_links
    else:
        for unit in course.preparatory_units:
            payload = {
                "id": unit.unit_id,
                "title": unit.title,
                "kind": "preparatory",
                "category": unit.category,
                "dag_level": unit.dag_level,
                "depends_on": unit.depends_on,
                "capability_ids": list(unit.capability_ids),
                "lesson": unit.lesson,
                "lesson_outline": _project_lesson_outline(
                    unit.lesson_outline, assessed=True
                ),
                "sources": [
                    source_payload(source_id) for source_id in unit.source_ids
                ],
                "study_minutes": _project_study_minutes(
                    unit.raw["study_minutes"]
                ),
            }
            links = _derive_practice_links(
                unit.lesson_outline, unit.quiz, kind="knowledge-check"
            )
            if links:
                payload["practice_links"] = links
            preparatory.append(payload)

    labs: list[dict[str, Any]] = []
    for lab in course.labs:
        payload: dict[str, Any] = {
            "id": lab.lab_id,
            "title": lab.title,
            "lesson": lab.lesson,
            "lesson_outline": _project_lesson_outline(
                lab.lesson_outline, assessed=assessed
            ),
            "sources": [source_payload(source_id) for source_id in lab.source_ids],
            "concepts": list(lab.concepts),
            "capstone_increment": lab.capstone_increment,
        }
        if "study_minutes" in lab.raw:
            payload["study_minutes"] = _project_study_minutes(
                lab.raw["study_minutes"]
            )
        links = _derive_practice_links(
            lab.lesson_outline,
            lab.questions,
            kind="coding-question",
        )
        if links:
            payload["practice_links"] = links
        labs.append(payload)

    result: dict[str, Any] = {
        "schema_version": course.schema_version,
        "course_id": course.course_id,
        "labs": labs,
    }
    if foundation is not None:
        result["foundations"] = foundation
    else:
        result["preparatory_units"] = preparatory
    return result


def _authoring_test(
    lab: LabSource,
    selector: str,
    *,
    hidden: bool,
) -> dict[str, str]:
    node = _selector_node(selector)
    if hidden:
        relative = _selector_file(selector, hidden=True)
        source = lab.root / "tests/hidden" / relative
    else:
        relative = _public_selector_file(selector, lab_id=lab.lab_id)
        source = lab.root / "tests/public" / relative
    return {
        "path": relative.as_posix(),
        "selector": node,
        "code": _read_text(source, label=f"{selector} source"),
    }


def _authoring_spec(course: CourseSource) -> dict[str, Any]:
    """Reconstruct the normalized inline authoring contract from split source."""

    course_payload = {
        key: copy.deepcopy(course.course[key])
        for key in (
            "id",
            "title",
            "description",
            "language",
            "python_requires",
            "size",
            "dependencies",
            "capstone",
            "audience",
        )
    }
    labs: list[dict[str, Any]] = []
    for lab in course.labs:
        files = []
        for raw_file in _list(lab.raw.get("files"), label=f"{lab.lab_id}.files"):
            file_payload = _mapping(raw_file, label=f"{lab.lab_id}.file")
            file_value = _text(file_payload, "path", label=f"{lab.lab_id}.file")
            relative = _relative(file_value, label=f"{lab.lab_id}.file.path")
            files.append(
                {
                    "path": file_value,
                    "starter": _read_text(
                        lab.root / "starter" / relative,
                        label=f"{file_value} starter",
                    ),
                    "reference": _read_text(
                        lab.root / "reference" / relative,
                        label=f"{file_value} reference",
                    ),
                }
            )

        questions = []
        for question in lab.questions:
            if len(question.public_tests) != 1 or len(question.hidden_tests) != 1:
                raise SourceValidationError(
                    f"{question.question_id} needs exactly one public and hidden test for authoring parity"
                )
            payload = copy.deepcopy(question.raw)
            payload.pop("tests", None)
            payload["public_test"] = _authoring_test(
                lab, question.public_tests[0], hidden=False
            )
            payload["hidden_test"] = _authoring_test(
                lab, question.hidden_tests[0], hidden=True
            )
            questions.append(payload)

        payload: dict[str, Any] = {
            "id": lab.lab_id,
            "title": lab.title,
            "depends_on": lab.depends_on,
            "lesson": copy.deepcopy(lab.lesson_outline),
            "sources": list(lab.source_ids),
            "files": files,
            "questions": questions,
            "quiz": [copy.deepcopy(question) for question in lab.quiz],
            "module_cycle": copy.deepcopy(lab.raw["module_cycle"]),
        }
        if "study_minutes" in lab.raw:
            payload["study_minutes"] = copy.deepcopy(lab.raw["study_minutes"])
        if "official_bridge" in lab.raw:
            payload["official_bridge"] = copy.deepcopy(lab.raw["official_bridge"])
        labs.append(payload)

    result: dict[str, Any] = {
        "schema_version": course.schema_version,
        "course": course_payload,
        "target": copy.deepcopy(course.target),
        "research": copy.deepcopy(course.research),
        "labs": labs,
    }
    if course.schema_version == 2:
        foundation_payload = {
            "id": str(course.foundation["id"]),
            "title": str(course.foundation["title"]),
            "lesson": copy.deepcopy(course.foundation_lesson_outline),
            "quiz": [copy.deepcopy(question) for question in course.foundation_quiz],
        }
        if "study_minutes" in course.foundation:
            foundation_payload["study_minutes"] = copy.deepcopy(
                course.foundation["study_minutes"]
            )
        result["foundation"] = foundation_payload
    else:
        result["preparatory_units"] = [
            {
                "id": unit.unit_id,
                "category": unit.category,
                "dag_level": unit.dag_level,
                "depends_on": unit.depends_on,
                "capability_ids": list(unit.capability_ids),
                "study_minutes": copy.deepcopy(unit.raw["study_minutes"]),
                "title": unit.title,
                "lesson": copy.deepcopy(unit.lesson_outline),
                "quiz": [copy.deepcopy(question) for question in unit.quiz],
            }
            for unit in course.preparatory_units
        ]
    return result


def _copy_tree_contents(source: Path, target: Path) -> None:
    if not source.is_dir():
        raise SourceValidationError(f"missing source directory: {source}")
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.is_file() and destination.read_bytes() == path.read_bytes():
                continue
            raise SourceValidationError(
                f"compiled artifact collision at {destination.relative_to(target)}"
            )
        shutil.copy2(path, destination)


def _copy_lesson_examples(
    source_root: Path,
    lesson: dict[str, Any],
    target_root: Path,
) -> None:
    for example in lesson["examples"]:
        if example["kind"] != "runnable":
            continue
        relative = _relative(str(example["path"]), label="lesson example")
        source = source_root / relative
        destination = target_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            raise SourceValidationError(
                f"compiled artifact collision at lesson example {destination}"
            )
        shutil.copy2(source, destination)


def _build_tree(course: CourseSource, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_bytes(json_bytes(_manifest(course)))
    (root / "knowledge.json").write_bytes(json_bytes(_knowledge(course)))
    (root / "content.json").write_bytes(json_bytes(_content(course)))
    (root / "authoring-spec.json").write_bytes(json_bytes(_authoring_spec(course)))

    if course.schema_version == 2:
        foundation_id = str(course.foundations["id"])
        foundation = root / "starter" / foundation_id
        foundation.mkdir(parents=True)
        (foundation / "README.md").write_text(course.foundation_lesson)
        _copy_lesson_examples(
            course.root / "foundations",
            course.foundation_lesson_outline,
            foundation,
        )
    else:
        for unit in course.preparatory_units:
            destination = root / "starter" / unit.unit_id
            destination.mkdir(parents=True)
            (destination / "README.md").write_text(unit.lesson)
            _copy_lesson_examples(
                unit.root, unit.lesson_outline, destination
            )

    for lab in course.labs:
        _copy_tree_contents(lab.root / "starter", root / "starter")
        _copy_tree_contents(lab.root / "reference", root / "reference")
        _copy_tree_contents(
            lab.root / "tests/public", root / "starter" / lab.lab_id / "tests"
        )
        _copy_tree_contents(lab.root / "tests/hidden", root / "tests/hidden")
        readme = root / "starter" / lab.lab_id / "README.md"
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(lab.lesson)
        _copy_lesson_examples(lab.root, lab.lesson_outline, root / "starter" / lab.lab_id)

    (root / "starter/manifest.json").write_bytes(
        json_bytes(_manifest(course, learner=True))
    )
    course_data = root / "starter/_course"
    course_data.mkdir(parents=True, exist_ok=True)
    (course_data / "knowledge.json").write_bytes(json_bytes(_knowledge(course)))
    (course_data / "content.json").write_bytes(json_bytes(_content(course)))

    generated = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root) != ARTIFACT_INDEX
    )
    generated.append(ARTIFACT_INDEX.as_posix())
    (root / ARTIFACT_INDEX).write_bytes(
        json_bytes({"schema_version": 1, "files": generated})
    )


def _generated_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file()
    }


def _previous_artifacts(output: Path) -> set[Path]:
    index = output / ARTIFACT_INDEX
    if not index.exists():
        return set()
    try:
        payload = _mapping(read_json(index), label="artifact index")
        if payload.get("schema_version") != 1:
            raise SourceValidationError("artifact index schema_version must be 1")
        return {
            _relative(str(value), label="artifact index path")
            for value in _list(payload.get("files"), label="artifact index files")
        }
    except (ValueError, FileNotFoundError) as error:
        raise CourseKitError(f"invalid CourseKit artifact index: {index}: {error}") from error


def _same_file(expected: Path, actual: Path) -> bool:
    return actual.is_file() and expected.read_bytes() == actual.read_bytes()


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _apply_transaction(
    *, expected: Path, output: Path, changed: tuple[Path, ...], backup: Path
) -> None:
    actions: list[tuple[Path, bool]] = []
    try:
        for artifact in changed:
            source = expected / artifact
            destination = output / artifact
            saved = backup / artifact
            had_destination = destination.exists() or destination.is_symlink()
            if had_destination:
                saved.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, saved)
            actions.append((artifact, had_destination))
            if source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)
    except BaseException:
        for artifact, had_destination in reversed(actions):
            destination = output / artifact
            saved = backup / artifact
            _remove_path(destination)
            if had_destination and saved.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(saved, destination)
        raise


def compile_course(
    source_root: Path | str,
    output_root: Path | str,
    *,
    check: bool = False,
) -> CompileReport:
    course = load_course_source(source_root)
    output = Path(output_root).absolute()
    _validate_output_root(output)
    if not check:
        output.parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = output.parent if output.parent.is_dir() else None
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}-coursekit-", dir=temporary_parent
    ) as temporary:
        expected = Path(temporary) / "compiled"
        _build_tree(course, expected)
        desired = _generated_files(expected)
        previous = _previous_artifacts(output)
        stale = previous - desired
        changed = tuple(
            sorted(
                stale
                | {
                    artifact
                    for artifact in desired
                    if not _same_file(expected / artifact, output / artifact)
                },
                key=lambda path: path.as_posix(),
            )
        )
        _validate_output_paths(output, changed)
        if check and changed:
            raise DriftError(changed)
        if check or not changed:
            return CompileReport(output_root=output, written=())

        output.mkdir(parents=True, exist_ok=True)
        _apply_transaction(
            expected=expected,
            output=output,
            changed=changed,
            backup=Path(temporary) / "backup",
        )
        return CompileReport(output_root=output, written=changed)


def initialize_workspace(
    compiled_root: Path | str, target: Path | str
) -> list[Path]:
    compiled = Path(compiled_root).resolve()
    destination = Path(target).absolute()
    if destination.is_symlink() or (
        destination.exists()
        and (not destination.is_dir() or any(destination.iterdir()))
    ):
        raise TargetNotEmptyError(f"workspace target is not empty: {destination}")
    starter = compiled / "starter"
    if not starter.is_dir():
        raise CourseKitError(f"compiled starter is missing: {starter}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    had_empty_destination = destination.exists()
    try:
        with tempfile.TemporaryDirectory(
            prefix=f".{destination.name}-workspace-", dir=destination.parent
        ) as temporary:
            transaction = Path(temporary)
            staged = transaction / "workspace"
            staged.mkdir()
            _copy_tree_contents(starter, staged)
            learner_manifest = staged / "manifest.json"
            if not learner_manifest.is_file():
                raise CourseKitError(
                    f"compiled learner manifest is missing: {starter / 'manifest.json'}"
                )
            written = [
                path.relative_to(staged)
                for path in sorted(staged.rglob("*"))
                if path.is_file()
            ]
            saved = transaction / "original-empty-target"
            if had_empty_destination:
                os.replace(destination, saved)
            try:
                os.replace(staged, destination)
            except OSError:
                if had_empty_destination and saved.exists() and not destination.exists():
                    os.replace(saved, destination)
                raise
            return written
    except CourseKitError:
        raise
    except OSError as error:
        raise CourseKitError(
            f"workspace initialization failed without changing the target: {error}"
        ) from error
