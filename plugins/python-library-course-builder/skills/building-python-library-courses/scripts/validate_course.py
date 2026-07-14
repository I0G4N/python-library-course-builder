#!/usr/bin/env python3
"""Validate the authoring spec consumed by the CourseKit scaffolder."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any
from urllib.parse import parse_qsl, urlparse


ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
LAB_PATTERN = re.compile(r"^lab\d{2}$")
TOKEN_PATTERN = re.compile(
    r"\{\{[^{}\r\n]+\}\}|__COURSEKIT_[A-Z0-9_]+__"
)
REQUIREMENT_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9._,-]+\])?"
    r"(?:(?:===|~=|==|!=|<=|>=|<|>)[A-Za-z0-9][A-Za-z0-9.*+!_-]*"
    r"(?:,(?:===|~=|==|!=|<=|>=|<|>)[A-Za-z0-9][A-Za-z0-9.*+!_-]*)*)$"
)
DIRECT_REQUIREMENT_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9._,-]+\])? @ (?:https|git\+https)://\S+$"
)
COMMIT_PATTERN = re.compile(r"^[0-9A-Fa-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9A-Fa-f]{64}$")
VERSION_CLAUSE_PATTERN = re.compile(
    r"^(~=|==|!=|<=|>=|<|>)(\d+)(?:\.(\d+))?(?:\.(\d+|\*))?$"
)
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
LAB_BOUNDS = {
    "small": (3, 5),
    "medium": (6, 8),
    "large": (6, 10),
}
QUESTION_KINDS = {"official_bridge", "reimplementation", "integration"}
QUESTION_EXAMPLE_FIELDS = ("input", "output", "explanation")
AUTHOR_QUESTION_FIELDS = {
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
    "public_test",
    "hidden_test",
}
QUIZ_KINDS = {"execution_trace", "diagnostic"}
CONCEPT_LIST_FIELDS = {
    "mechanism",
    "design_reasons",
    "benefits",
    "tradeoffs",
    "invariants",
    "boundaries",
    "pitfalls",
}


class SpecValidationError(ValueError):
    """The proposed course cannot be scaffolded safely or deterministically."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpecValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SpecValidationError(f"{label} must be an array")
    return value


def _text(mapping: dict[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SpecValidationError(f"{label}.{key} must be a non-empty string")
    if TOKEN_PATTERN.search(value):
        raise SpecValidationError(f"{label}.{key} contains an unresolved token")
    return value


def _safe_path(value: str, label: str) -> PurePosixPath:
    if "\\" in value:
        raise SpecValidationError(f"{label} must use POSIX separators")
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise SpecValidationError(f"{label} must be a safe relative path: {value!r}")
    for part in path.parts:
        stem = part.split(".", 1)[0].upper()
        if ":" in part:
            raise SpecValidationError(
                f"{label} cannot contain a Windows drive or colon segment: {value!r}"
            )
        if part.endswith((" ", ".")) or stem in WINDOWS_RESERVED:
            raise SpecValidationError(
                f"{label} is not portable to Windows: {value!r}"
            )
    return path


def _url_without_credentials_or_query(value: str, *, scheme: str) -> bool:
    try:
        parsed = urlparse(value)
        return bool(
            parsed.scheme == scheme
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
        )
    except ValueError:
        return False


def _sha256_fragment(value: str) -> bool:
    try:
        pairs = parse_qsl(value, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    normalized = [(key.casefold(), item) for key, item in pairs]
    keys = [key for key, _item in normalized]
    hashes = [item for key, item in normalized if key == "sha256"]
    return bool(
        normalized
        and all(key and item for key, item in normalized)
        and len(keys) == len(set(keys))
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


def _version_matches(specifier: str, version: tuple[int, int, int]) -> bool:
    clauses = [clause.strip() for clause in specifier.split(",") if clause.strip()]
    if not clauses:
        return False
    for clause in clauses:
        match = VERSION_CLAUSE_PATTERN.fullmatch(clause)
        if match is None:
            raise SpecValidationError(
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
        else:  # ~= compatible release
            upper = (
                (expected[0], expected[1] + 1, 0)
                if len(components) >= 3
                else (expected[0] + 1, 0, 0)
            )
            matched = expected <= version < upper
        if not matched:
            return False
    return True


def _has_template_upper_bound(specifier: str) -> bool:
    clauses = {clause.strip().replace(" ", "") for clause in specifier.split(",")}
    return bool(
        clauses.intersection({"<3.14", "<3.14.0", "==3.13.*", "~=3.13.0"})
    )


def _python_module(code: str, label: str) -> ast.Module:
    if TOKEN_PATTERN.search(code):
        raise SpecValidationError(f"{label} contains an unresolved token")
    try:
        return ast.parse(code, filename=label)
    except SyntaxError as error:
        raise SpecValidationError(f"{label} is not valid Python: {error}") from error


def _declares(module: ast.Module, name: str) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == name
        for node in module.body
    )


def _string_array(value: Any, label: str, *, minimum: int = 1) -> list[str]:
    items = _array(value, label)
    if len(items) < minimum or not all(
        isinstance(item, str) and item.strip() and not TOKEN_PATTERN.search(item)
        for item in items
    ):
        suffix = f" at least {minimum}" if minimum > 1 else " non-empty"
        raise SpecValidationError(f"{label} must contain{suffix} string(s)")
    return items


def _python_imports(module: ast.Module) -> set[str]:
    imports: set[str] = set()
    importlib_names = {"importlib"}
    import_module_callables: set[str] = set()
    builtin_import_callables = {"__import__"}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                if alias.name == "importlib":
                    importlib_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise SpecValidationError(
                    "coding source uses a relative ImportFrom"
                )
            if not node.module:
                continue
            imports.add(node.module)
            for alias in node.names:
                if alias.name != "*":
                    imports.add(f"{node.module}.{alias.name}")
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
            imports.add(first.value)
    return imports


def _imports_root(imports: set[str], root: str) -> bool:
    return any(name == root or name.startswith(f"{root}.") for name in imports)


def _module_name(path: str) -> str:
    value = PurePosixPath(path)
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
    forbidden_imports: list[str],
    prior_course_roots: list[str],
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
            module = declared_modules[module_name][projection]
            imports = _python_imports(module)
            if any(
                _imports_root(imports, root)
                for root in (*forbidden_imports, *prior_course_roots)
            ):
                raise SpecValidationError(
                    f"{label}.learner_file closure contains a forbidden import"
                )
            for imported in imports:
                if not _imports_root({imported}, lab_id):
                    continue
                helper = _declared_helper(imported, declared_modules)
                if helper is None:
                    if imported == lab_id:
                        continue
                    raise SpecValidationError(
                        f"{label}.learner_file imports an undeclared local helper: {imported}"
                    )
                pending.append(helper)


def _stable_id(mapping: dict[str, Any], label: str) -> str:
    value = _text(mapping, "id", label)
    if not ID_PATTERN.fullmatch(value.replace(".", "-")):
        raise SpecValidationError(f"{label}.id must be a stable lowercase id")
    return value


def _validate_audience(course: dict[str, Any]) -> None:
    audience = _object(course.get("audience"), "course.audience")
    if _text(audience, "level", "course.audience") != "basic-python":
        raise SpecValidationError("course.audience.level must be basic-python")
    _string_array(audience.get("assumes"), "course.audience.assumes")
    _string_array(
        audience.get("does_not_assume"), "course.audience.does_not_assume"
    )
    duration = _object(
        audience.get("lab_minutes"), "course.audience.lab_minutes"
    )
    if duration.get("min") != 30 or duration.get("max") != 45:
        raise SpecValidationError(
            "course.audience.lab_minutes must declare the 30-45 minute range"
        )


def _validate_lesson(
    value: Any,
    *,
    label: str,
    source_ids: set[str],
) -> tuple[set[str], set[str]]:
    lesson = _object(value, label)
    prerequisites = _array(lesson.get("prerequisites"), f"{label}.prerequisites")
    if not prerequisites:
        raise SpecValidationError(f"{label}.prerequisites must not be empty")
    prerequisite_ids: set[str] = set()
    for index, raw in enumerate(prerequisites):
        item_label = f"{label}.prerequisites[{index}]"
        item = _object(raw, item_label)
        item_id = _stable_id(item, item_label)
        if item_id in prerequisite_ids:
            raise SpecValidationError(f"duplicate prerequisite id: {item_id}")
        prerequisite_ids.add(item_id)
        for key in ("title", "why", "refresh"):
            _text(item, key, item_label)

    problem = _object(lesson.get("problem"), f"{label}.problem")
    for key in ("context", "naive_approach", "failure"):
        _text(problem, key, f"{label}.problem")

    outcomes = _array(lesson.get("outcomes"), f"{label}.outcomes")
    if not outcomes:
        raise SpecValidationError(f"{label}.outcomes must not be empty")
    outcome_ids: set[str] = set()
    for index, raw in enumerate(outcomes):
        item_label = f"{label}.outcomes[{index}]"
        item = _object(raw, item_label)
        outcome_id = _stable_id(item, item_label)
        if outcome_id in outcome_ids:
            raise SpecValidationError(f"duplicate outcome id: {outcome_id}")
        outcome_ids.add(outcome_id)
        _text(item, "text", item_label)

    concepts = _array(lesson.get("concepts"), f"{label}.concepts")
    if not concepts:
        raise SpecValidationError(f"{label}.concepts must not be empty")
    concept_ids: set[str] = set()
    for index, raw in enumerate(concepts):
        item_label = f"{label}.concepts[{index}]"
        concept = _object(raw, item_label)
        concept_id = _stable_id(concept, item_label)
        if concept_id in concept_ids:
            raise SpecValidationError(f"duplicate concept id: {concept_id}")
        concept_ids.add(concept_id)
        for key in ("name", "definition", "purpose", "mental_model"):
            _text(concept, key, item_label)
        for key in sorted(CONCEPT_LIST_FIELDS):
            _string_array(concept.get(key), f"{item_label}.{key}")
        claims = _array(
            concept.get("source_claims"), f"{item_label}.source_claims"
        )
        if not claims:
            raise SpecValidationError(f"{item_label}.source_claims must not be empty")
        for claim_index, raw_claim in enumerate(claims):
            claim_label = f"{item_label}.source_claims[{claim_index}]"
            claim = _object(raw_claim, claim_label)
            source_id = _text(claim, "source_id", claim_label)
            if source_id not in source_ids:
                raise SpecValidationError(
                    f"{item_label}.source_claims reference unknown source {source_id}"
                )
            _text(claim, "claim", claim_label)
            if claim.get("status") not in {"documented", "implementation"}:
                raise SpecValidationError(
                    f"{claim_label}.status must be documented or implementation"
                )

    examples = _array(lesson.get("examples"), f"{label}.examples")
    if len(examples) < 2:
        raise SpecValidationError(f"{label}.examples needs at least two examples")
    declared_kinds = {
        raw.get("kind")
        for raw in examples
        if isinstance(raw, dict) and isinstance(raw.get("kind"), str)
    }
    for required in ("runnable", "diagnostic"):
        if required not in declared_kinds:
            raise SpecValidationError(
                f"{label}.examples needs a {required} example"
            )
    example_ids: set[str] = set()
    example_kinds: set[str] = set()
    example_paths: set[str] = set()
    for index, raw in enumerate(examples):
        item_label = f"{label}.examples[{index}]"
        example = _object(raw, item_label)
        example_id = _stable_id(example, item_label)
        if example_id in example_ids:
            raise SpecValidationError(f"duplicate lesson example id: {example_id}")
        example_ids.add(example_id)
        _text(example, "title", item_label)
        kind = _text(example, "kind", item_label)
        if kind not in {"runnable", "diagnostic"}:
            raise SpecValidationError(f"{item_label}.kind must be runnable or diagnostic")
        example_kinds.add(kind)
        _text(example, "explanation", item_label)
        _validate_mappings(
            example,
            label=item_label,
            concept_ids=concept_ids,
            outcome_ids=outcome_ids,
        )
        if kind == "runnable":
            path = _safe_path(_text(example, "path", item_label), f"{item_label}.path")
            if path.suffix != ".py" or path.as_posix() in example_paths:
                raise SpecValidationError(
                    f"{item_label}.path must be a unique Python path"
                )
            example_paths.add(path.as_posix())
            _python_module(_text(example, "code", item_label), f"{item_label}.code")
            command = _text(example, "command", item_label)
            expected_command = f"python {path.as_posix()}"
            if command != expected_command:
                raise SpecValidationError(
                    f"{item_label}.command must be exactly {expected_command!r}"
                )
            _text(example, "expected_output", item_label)
        else:
            for key in ("wrong_code", "symptom", "cause", "fix_code"):
                _text(example, key, item_label)
            _python_module(
                str(example["wrong_code"]), f"{item_label}.wrong_code"
            )
            _python_module(str(example["fix_code"]), f"{item_label}.fix_code")
    bridge = _object(lesson.get("capstone_bridge"), f"{label}.capstone_bridge")
    for key in ("input", "output", "increment", "next"):
        _text(bridge, key, f"{label}.capstone_bridge")
    _string_array(lesson.get("summary"), f"{label}.summary")
    return concept_ids, outcome_ids


def _validate_mappings(
    mapping: dict[str, Any],
    *,
    label: str,
    concept_ids: set[str],
    outcome_ids: set[str],
) -> None:
    declared_concepts = _string_array(
        mapping.get("concept_ids"), f"{label}.concept_ids"
    )
    declared_outcomes = _string_array(
        mapping.get("outcome_ids"), f"{label}.outcome_ids"
    )
    if not set(declared_concepts) <= concept_ids:
        raise SpecValidationError(f"{label}.concept_ids reference unknown concepts")
    if not set(declared_outcomes) <= outcome_ids:
        raise SpecValidationError(f"{label}.outcome_ids reference unknown outcomes")


def _validate_quiz(
    value: Any,
    label: str,
    *,
    concept_ids: set[str],
    outcome_ids: set[str],
    quiz_ids: set[str],
) -> list[tuple[int, int]]:
    questions = _array(value, label)
    if not questions:
        raise SpecValidationError(f"{label} must contain at least one question")
    kinds: set[str] = set()
    positions: list[tuple[int, int]] = []
    for index, raw in enumerate(questions):
        item_label = f"{label}[{index}]"
        question = _object(raw, item_label)
        question_id = _stable_id(question, item_label)
        if question_id in quiz_ids:
            raise SpecValidationError(f"duplicate quiz id: {question_id}")
        quiz_ids.add(question_id)
        kind = _text(question, "kind", item_label)
        if kind not in QUIZ_KINDS:
            raise SpecValidationError(
                f"{item_label}.kind must be execution_trace or diagnostic"
            )
        kinds.add(kind)
        _text(question, "prompt", item_label)
        _text(question, "explanation", item_label)
        choices = _array(question.get("choices"), f"{item_label}.choices")
        if not 3 <= len(choices) <= 4:
            raise SpecValidationError(f"{item_label}.choices must contain 3-4 choices")
        choice_ids: list[str] = []
        for choice_index, raw_choice in enumerate(choices):
            choice_label = f"{item_label}.choices[{choice_index}]"
            choice = _object(raw_choice, choice_label)
            choice_id = _stable_id(choice, choice_label)
            if choice_id in choice_ids:
                raise SpecValidationError(f"duplicate choice id: {choice_id}")
            choice_ids.append(choice_id)
            _text(choice, "text", choice_label)
            _text(choice, "feedback", choice_label)
        answer_id = question.get("answer_id")
        if not isinstance(answer_id, str) or answer_id not in choice_ids:
            raise SpecValidationError(f"{item_label}.answer_id must reference one choice")
        positions.append((choice_ids.index(answer_id), len(choice_ids)))
        _validate_mappings(
            question,
            label=item_label,
            concept_ids=concept_ids,
            outcome_ids=outcome_ids,
        )
    missing = QUIZ_KINDS - kinds
    if missing:
        raise SpecValidationError(
            f"{label} must include execution_trace and diagnostic questions; missing {', '.join(sorted(missing))}"
        )
    return positions


def _validate_test(value: Any, label: str) -> tuple[str, str]:
    test = _object(value, label)
    path = _safe_path(_text(test, "path", label), f"{label}.path")
    if len(path.parts) != 1 or path.suffix != ".py" or not path.name.startswith("test_"):
        raise SpecValidationError(f"{label}.path must be one test_*.py filename")
    selector = _text(test, "selector", label)
    if not selector.startswith("test_"):
        raise SpecValidationError(f"{label}.selector must start with test_")
    code = _text(test, "code", label)
    module = _python_module(code, label)
    if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == selector for node in module.body):
        raise SpecValidationError(f"{label}.code does not declare {selector}")
    return path.as_posix(), code


def validate_spec(payload: Any) -> dict[str, Any]:
    spec = _object(payload, "course spec")
    if spec.get("schema_version") != 2:
        raise SpecValidationError("schema_version must be 2")

    course = _object(spec.get("course"), "course")
    course_id = _text(course, "id", "course")
    if not ID_PATTERN.fullmatch(course_id):
        raise SpecValidationError("course.id must be lowercase kebab-case")
    for key in ("title", "description", "language", "python_requires", "capstone"):
        _text(course, key, "course")
    python_requires = course["python_requires"]
    if (
        not _version_matches(python_requires, (3, 13, 0))
        or not _has_template_upper_bound(python_requires)
        or any(
            _version_matches(python_requires, version)
            for version in ((3, 14, 0), (3, 14, 1), (3, 15, 0))
        )
    ):
        raise SpecValidationError(
            "course.python_requires must include Python 3.13 and exclude Python 3.14 for this template"
        )
    dependencies = _array(course.get("dependencies", []), "course.dependencies")
    if not all(
        isinstance(item, str)
        and item.strip()
        and not TOKEN_PATTERN.search(item)
        and _requirement(item)
        for item in dependencies
    ):
        raise SpecValidationError(
            "course.dependencies must contain pinned or bounded PEP 508 requirement strings"
        )
    size = _text(course, "size", "course")
    if size not in LAB_BOUNDS:
        raise SpecValidationError("course.size must be small, medium, or large")
    _validate_audience(course)

    target = _object(spec.get("target"), "target")
    for key in ("name", "kind", "version", "breadth"):
        _text(target, key, "target")
    if target["kind"] not in {"stdlib", "pypi", "framework", "repository"}:
        raise SpecValidationError("target.kind must be stdlib, pypi, framework, or repository")
    if target["kind"] != "stdlib" and not dependencies:
        raise SpecValidationError("third-party targets require pinned course.dependencies")
    if target["breadth"] not in {"focused", "broad"}:
        raise SpecValidationError("target.breadth must be focused or broad")
    track = target.get("track")
    if target["breadth"] == "broad" and (not isinstance(track, str) or not track.strip()):
        raise SpecValidationError("a broad target requires a chosen target.track before scaffolding")
    if target["breadth"] == "broad" and size != "large":
        raise SpecValidationError("a broad selected target must use course.size large")
    target_import_roots = _string_array(
        target.get("import_roots"), "target.import_roots"
    )
    if any("." in root or not root.replace("_", "a").isidentifier() for root in target_import_roots):
        raise SpecValidationError("target.import_roots must contain top-level Python imports")

    source_ids: set[str] = set()
    sources = _array(target.get("official_sources"), "target.official_sources")
    if not sources:
        raise SpecValidationError("target.official_sources must not be empty")
    for index, raw in enumerate(sources):
        label = f"target.official_sources[{index}]"
        source = _object(raw, label)
        source_id = _text(source, "id", label)
        _text(source, "title", label)
        url = _text(source, "url", label)
        if not _official_source_url(url):
            raise SpecValidationError(f"{label}.url must be an HTTPS URL")
        if source_id in source_ids:
            raise SpecValidationError(f"duplicate official source id: {source_id}")
        source_ids.add(source_id)

    research = _object(spec.get("research"), "research")
    if research.get("status") != "complete":
        raise SpecValidationError("research.status must be complete before scaffolding")
    _text(research, "version_basis", "research")
    notes = _array(research.get("notes"), "research.notes")
    if not notes or not all(isinstance(note, str) and note.strip() for note in notes):
        raise SpecValidationError("research.notes must contain at least one finding")

    foundation = _object(spec.get("foundation"), "foundation")
    if _text(foundation, "id", "foundation") != "lab00":
        raise SpecValidationError("foundation.id must be lab00")
    _text(foundation, "title", "foundation")
    foundation_concepts, foundation_outcomes = _validate_lesson(
        foundation.get("lesson"), label="foundation.lesson", source_ids=source_ids
    )
    quiz_ids: set[str] = set()
    quiz_positions = _validate_quiz(
        foundation.get("quiz"),
        "foundation.quiz",
        concept_ids=foundation_concepts,
        outcome_ids=foundation_outcomes,
        quiz_ids=quiz_ids,
    )

    labs = _array(spec.get("labs"), "labs")
    lower, upper = LAB_BOUNDS[size]
    if not lower <= len(labs) <= upper:
        raise SpecValidationError(
            f"a {size} course must contain {lower}-{upper} graded labs"
        )

    question_ids: set[str] = set()
    prior_mini_modules: list[str] = []
    prior_course_roots: list[str] = []
    previous_target_symbols: list[str] | None = None
    previous = "lab00"
    for offset, raw in enumerate(labs, start=1):
        label = f"labs[{offset - 1}]"
        lab = _object(raw, label)
        lab_id = _text(lab, "id", label)
        expected_id = f"lab{offset:02d}"
        if lab_id != expected_id or not LAB_PATTERN.fullmatch(lab_id):
            raise SpecValidationError(f"labs must be ordered linearly as {expected_id}")
        if _text(lab, "depends_on", label) != previous:
            raise SpecValidationError(f"{lab_id} must depend on {previous}")
        _text(lab, "title", label)
        lab_sources = _array(lab.get("sources"), f"{label}.sources")
        if not lab_sources or any(str(item) not in source_ids for item in lab_sources):
            raise SpecValidationError(f"{label}.sources must reference official source ids")
        concept_ids, outcome_ids = _validate_lesson(
            lab.get("lesson"), label=f"{label}.lesson", source_ids=source_ids
        )

        declared_files: dict[str, tuple[ast.Module, ast.Module]] = {}
        files = _array(lab.get("files"), f"{label}.files")
        if not files:
            raise SpecValidationError(f"{label}.files must not be empty")
        for file_index, raw_file in enumerate(files):
            file_label = f"{label}.files[{file_index}]"
            file_spec = _object(raw_file, file_label)
            path = _safe_path(_text(file_spec, "path", file_label), f"{file_label}.path")
            if not path.parts or path.parts[0] != lab_id or path.suffix != ".py":
                raise SpecValidationError(f"{file_label}.path must be a Python file under {lab_id}/")
            path_text = path.as_posix()
            if path_text in declared_files:
                raise SpecValidationError(f"duplicate Lab file: {path_text}")
            declared_files[path_text] = (
                _python_module(_text(file_spec, "starter", file_label), f"{file_label}.starter"),
                _python_module(_text(file_spec, "reference", file_label), f"{file_label}.reference"),
            )

        questions = _array(lab.get("questions"), f"{label}.questions")
        if not 1 <= len(questions) <= 3:
            raise SpecValidationError(f"{label}.questions must contain 1-3 coding tasks")
        public_files: dict[str, str] = {}
        hidden_files: dict[str, str] = {}
        questions_by_id: dict[str, dict[str, Any]] = {}
        for question_index, raw_question in enumerate(questions):
            question_label = f"{label}.questions[{question_index}]"
            question = _object(raw_question, question_label)
            unknown_fields = sorted(set(question) - AUTHOR_QUESTION_FIELDS)
            if unknown_fields:
                raise SpecValidationError(
                    f"{question_label} has unknown field(s): {', '.join(unknown_fields)}"
                )
            question_id = _stable_id(question, question_label)
            expected_prefix = f"{lab_id}.q"
            if not question_id.startswith(expected_prefix) or question_id in question_ids:
                raise SpecValidationError(f"invalid or duplicate coding question id: {question_id}")
            question_ids.add(question_id)
            questions_by_id[question_id] = question
            for key in ("title", "symbol", "prompt"):
                _text(question, key, question_label)
            kind = _text(question, "kind", question_label)
            if kind not in QUESTION_KINDS:
                raise SpecValidationError(
                    f"{question_label}.kind must be official_bridge, reimplementation, or integration"
                )
            _validate_mappings(
                question,
                label=question_label,
                concept_ids=concept_ids,
                outcome_ids=outcome_ids,
            )
            points = question.get("points")
            if not isinstance(points, int) or isinstance(points, bool) or points <= 0:
                raise SpecValidationError(f"{question_label}.points must be positive")
            timeout_seconds = question.get("timeout_seconds", 30)
            if (
                not isinstance(timeout_seconds, int)
                or isinstance(timeout_seconds, bool)
                or not 1 <= timeout_seconds <= 90
            ):
                raise SpecValidationError(
                    f"{question_label}.timeout_seconds must be an integer from 1 to 90"
                )
            question["timeout_seconds"] = timeout_seconds
            file_path = _safe_path(_text(question, "file", question_label), f"{question_label}.file").as_posix()
            modules = declared_files.get(file_path)
            if modules is None:
                raise SpecValidationError(f"{question_label}.file is not declared in {label}.files")
            symbol = question["symbol"]
            if not all(_declares(module, symbol) for module in modules):
                raise SpecValidationError(f"starter and reference must both declare {symbol}")
            example = _object(question.get("example"), f"{question_label}.example")
            unknown_example_fields = sorted(
                set(example) - set(QUESTION_EXAMPLE_FIELDS)
            )
            if unknown_example_fields:
                raise SpecValidationError(
                    f"{question_label}.example has unknown field(s): {', '.join(unknown_example_fields)}"
                )
            for key in QUESTION_EXAMPLE_FIELDS:
                _text(example, key, f"{question_label}.example")
            for kind, registry in (("public_test", public_files), ("hidden_test", hidden_files)):
                test_path, code = _validate_test(question.get(kind), f"{question_label}.{kind}")
                previous_code = registry.setdefault(test_path, code)
                if previous_code != code:
                    raise SpecValidationError(f"conflicting test file content: {test_path}")

        quiz_positions.extend(
            _validate_quiz(
                lab.get("quiz"),
                f"{label}.quiz",
                concept_ids=concept_ids,
                outcome_ids=outcome_ids,
                quiz_ids=quiz_ids,
            )
        )

        module_cycle = _object(lab.get("module_cycle"), f"{label}.module_cycle")
        reimplementation = _object(
            module_cycle.get("reimplementation"),
            f"{label}.module_cycle.reimplementation",
        )
        reimplementation_label = f"{label}.module_cycle.reimplementation"
        for key in ("module_id", "title"):
            _text(reimplementation, key, reimplementation_label)
        target_symbols = _string_array(
            reimplementation.get("target_symbols"),
            f"{reimplementation_label}.target_symbols",
        )
        _string_array(
            reimplementation.get("lower_level_dependencies"),
            f"{reimplementation_label}.lower_level_dependencies",
        )
        learner_file = _safe_path(
            _text(reimplementation, "learner_file", reimplementation_label),
            f"{reimplementation_label}.learner_file",
        ).as_posix()
        mini_modules = declared_files.get(learner_file)
        if mini_modules is None:
            raise SpecValidationError(
                f"{reimplementation_label}.learner_file must be a declared Lab file"
            )
        reimplementation_questions = _string_array(
            reimplementation.get("question_ids"),
            f"{reimplementation_label}.question_ids",
        )
        if any(
            question_id not in questions_by_id
            or questions_by_id[question_id].get("kind") != "reimplementation"
            for question_id in reimplementation_questions
        ):
            raise SpecValidationError(
                f"{reimplementation_label}.question_ids must reference current reimplementation questions"
            )
        declared_reimplementation_ids = {
            question_id
            for question_id, question in questions_by_id.items()
            if question.get("kind") == "reimplementation"
        }
        if set(reimplementation_questions) != declared_reimplementation_ids:
            raise SpecValidationError(
                f"{reimplementation_label}.question_ids must list every current reimplementation question"
            )
        if any(
            str(questions_by_id[question_id].get("file")) != learner_file
            for question_id in reimplementation_questions
        ):
            raise SpecValidationError(
                f"{reimplementation_label} requires every reimplementation question.file to equal learner_file"
            )
        forbidden_imports = _string_array(
            reimplementation.get("forbidden_imports"),
            f"{reimplementation_label}.forbidden_imports",
        )
        if not set(target_import_roots) <= set(forbidden_imports):
            raise SpecValidationError(
                f"{reimplementation_label}.forbidden_imports must include target.import_roots"
            )
        _validate_reimplementation_closure(
            learner_file=learner_file,
            lab_id=lab_id,
            declared_files=declared_files,
            forbidden_imports=forbidden_imports,
            prior_course_roots=prior_course_roots,
            label=reimplementation_label,
        )

        for file_path, modules in declared_files.items():
            for module in modules:
                imports = _python_imports(module)
                if any(
                    _imports_root(imports, prior_module)
                    for prior_module in (*prior_mini_modules, *prior_course_roots)
                ):
                    raise SpecValidationError(
                        f"{file_path} imports a prior mini implementation or another prior Lab helper"
                    )
        for test_path, code in (*public_files.items(), *hidden_files.items()):
            imports = _python_imports(
                _python_module(code, f"{lab_id} test {test_path}")
            )
            if any(
                _imports_root(imports, prior_module)
                for prior_module in (*prior_mini_modules, *prior_course_roots)
            ):
                raise SpecValidationError(
                    f"{test_path} imports a prior mini implementation or another prior Lab helper"
                )

        if offset == 1:
            if lab.get("official_bridge") is not None:
                raise SpecValidationError("lab01 must not declare official_bridge")
        else:
            official_bridge = _object(
                lab.get("official_bridge"), f"{label}.official_bridge"
            )
            bridge_label = f"{label}.official_bridge"
            if _text(official_bridge, "from_lab", bridge_label) != previous:
                raise SpecValidationError(
                    f"{bridge_label}.from_lab must be the immediately previous Lab"
                )
            mini_module = _text(official_bridge, "mini_module", bridge_label)
            if not prior_mini_modules or mini_module != prior_mini_modules[-1]:
                raise SpecValidationError(
                    f"{bridge_label}.mini_module must name the previous teaching module"
                )
            official_symbols = _string_array(
                official_bridge.get("official_symbols"),
                f"{bridge_label}.official_symbols",
            )
            if previous_target_symbols is None or set(official_symbols) != set(
                previous_target_symbols
            ):
                raise SpecValidationError(
                    f"previous reimplementation target_symbols must equal {bridge_label}.official_symbols"
                )
            required_imports = _string_array(
                official_bridge.get("required_imports"),
                f"{bridge_label}.required_imports",
            )
            if not set(required_imports) <= set(target_import_roots):
                raise SpecValidationError(
                    f"{bridge_label}.required_imports must reference target.import_roots"
                )
            bridge_question_id = _text(
                official_bridge, "question_id", bridge_label
            )
            if (
                not questions
                or questions[0].get("id") != bridge_question_id
                or questions[0].get("kind") != "official_bridge"
            ):
                raise SpecValidationError(
                    f"{lab_id} first coding question must be the official_bridge"
                )
            bridge_question = questions_by_id.get(bridge_question_id)
            if bridge_question is None:
                raise SpecValidationError(
                    f"{bridge_label}.question_id must reference a coding question"
                )
            bridge_file = str(bridge_question["file"])
            for module in declared_files[bridge_file]:
                imports = _python_imports(module)
                missing_imports = [
                    root
                    for root in required_imports
                    if not _imports_root(imports, root)
                ]
                if missing_imports:
                    raise SpecValidationError(
                        f"{bridge_label} question file is missing required import(s): {', '.join(missing_imports)}"
                    )

            observables = _array(
                official_bridge.get("observables"),
                f"{bridge_label}.observables",
            )
            observable_ids: set[str] = set()
            for observable_index, raw_observable in enumerate(observables):
                observable_label = (
                    f"{bridge_label}.observables[{observable_index}]"
                )
                observable = _object(raw_observable, observable_label)
                observable_id = _stable_id(observable, observable_label)
                if observable_id in observable_ids:
                    raise SpecValidationError(
                        f"duplicate official bridge observable: {observable_id}"
                    )
                observable_ids.add(observable_id)
                _text(observable, "description", observable_label)
            if not observable_ids:
                raise SpecValidationError(
                    f"{bridge_label}.observables must not be empty"
                )
            cases = _array(
                official_bridge.get("comparison_cases"),
                f"{bridge_label}.comparison_cases",
            )
            covered_observables: set[str] = set()
            for case_index, raw_case in enumerate(cases):
                case_label = f"{bridge_label}.comparison_cases[{case_index}]"
                case = _object(raw_case, case_label)
                _text(case, "input", case_label)
                if "expected" not in case:
                    raise SpecValidationError(
                        f"{case_label}.expected must declare the comparison result"
                    )
                mapped = _string_array(
                    case.get("observable_ids"), f"{case_label}.observable_ids"
                )
                if not set(mapped) <= observable_ids:
                    raise SpecValidationError(
                        f"{case_label}.observable_ids reference unknown observable"
                    )
                covered_observables.update(mapped)
            if covered_observables != observable_ids:
                raise SpecValidationError(
                    f"{bridge_label}.comparison_cases must cover every observable"
                )

        mini_path = PurePosixPath(learner_file)
        prior_mini_modules.append(
            ".".join((*mini_path.parts[:-1], mini_path.stem))
        )
        prior_course_roots.append(lab_id)
        previous_target_symbols = target_symbols
        previous = lab_id

    if quiz_positions:
        maximum_choices = max(choice_count for _, choice_count in quiz_positions)
        observed_positions = {position for position, _ in quiz_positions}
        if observed_positions != set(range(maximum_choices)):
            raise SpecValidationError("quiz answer positions must use every position")
        counts = Counter(position for position, _ in quiz_positions)
        if max(counts.values()) / len(quiz_positions) > 0.40:
            raise SpecValidationError(
                "no quiz answer position may exceed 40% of the course"
            )

    serialized = json.dumps(spec, ensure_ascii=False)
    token = TOKEN_PATTERN.search(serialized)
    if token:
        raise SpecValidationError(f"course spec contains unresolved token: {token.group(0)}")
    return spec


def load_and_validate(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SpecValidationError(f"course spec does not exist: {source}") from error
    except json.JSONDecodeError as error:
        raise SpecValidationError(f"course spec is invalid JSON: {error}") from error
    return validate_spec(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    args = parser.parse_args(argv)
    try:
        spec = load_and_validate(args.spec)
    except SpecValidationError as error:
        print(f"invalid course spec: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "valid": True,
                "course_id": spec["course"]["id"],
                "target": spec["target"]["name"],
                "labs": len(spec["labs"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
