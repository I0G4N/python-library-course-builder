"""Shared fail-closed AST preflight for learner coding-question sources."""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import Any


POLICY_FIELDS = {
    "local_root",
    "required_imports",
    "forbidden_imports",
    "prior_mini_modules",
    "forbidden_course_roots",
}


class SourcePolicyError(ValueError):
    """Learner source violates the compiler-declared import contract."""


def _policy_error(message: str) -> SourcePolicyError:
    return SourcePolicyError(f"[coursekit] source policy violation: {message}")


def _names(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise _policy_error(f"{field} must be a list of non-empty module names")
    return tuple(value)


def _matches(imported: str, boundary: str) -> bool:
    return imported == boundary or imported.startswith(f"{boundary}.")


def imported_modules(source: str, *, filename: str) -> set[str]:
    """Return literal imports, including aliased from-imports and dynamic imports."""

    try:
        module = ast.parse(source, filename=filename)
    except SyntaxError as error:
        raise _policy_error(f"{filename} is not valid Python: {error}") from error

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
                raise _policy_error(f"{filename} uses a relative import")
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
        is_import_module = (
            isinstance(function, ast.Attribute)
            and function.attr == "import_module"
            and isinstance(function.value, ast.Name)
            and function.value.id in importlib_names
        ) or (
            isinstance(function, ast.Name)
            and function.id in import_module_callables
        )
        is_builtin_import = (
            isinstance(function, ast.Name)
            and function.id in builtin_import_callables
        )
        if is_import_module or is_builtin_import:
            imports.add(first.value)
    return imports


def _safe_file(workspace: Path, relative_value: str) -> Path:
    relative = PurePosixPath(relative_value)
    if (
        not relative_value
        or "\\" in relative_value
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise _policy_error(f"unsafe learner source path: {relative_value!r}")
    current = workspace
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise _policy_error(f"learner source cannot use symlinks: {relative_value}")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(workspace.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError) as error:
        raise _policy_error(f"learner source is unavailable: {relative_value}") from error
    if not resolved.is_file():
        raise _policy_error(f"learner source is not a regular file: {relative_value}")
    return resolved


def _local_module_file(
    workspace: Path, module_name: str, *, local_root: str
) -> Path | None:
    if not _matches(module_name, local_root):
        return None
    parts = module_name.split(".")
    for size in range(len(parts), 0, -1):
        prefix = parts[:size]
        for suffix in (("__init__.py",), (f"{prefix[-1]}.py",)):
            relative_parts = (
                (*prefix, *suffix)
                if suffix == ("__init__.py",)
                else (*prefix[:-1], *suffix)
            )
            candidate = workspace.joinpath(*relative_parts)
            if candidate.is_file() and not candidate.is_symlink():
                return candidate
    return None


def preflight_question_source(
    workspace_root: Path,
    question_file: str,
    policy: Any,
) -> None:
    """Validate the question file and every reachable same-Lab helper before pytest."""

    if not isinstance(policy, dict):
        raise _policy_error("question source_policy is missing or invalid")
    unknown = sorted(set(policy) - POLICY_FIELDS)
    if unknown:
        raise _policy_error(f"source_policy has unknown field(s): {', '.join(unknown)}")
    local_root = policy.get("local_root")
    if not isinstance(local_root, str) or not local_root or "." in local_root:
        raise _policy_error("source_policy.local_root must be one top-level module")
    required = _names(policy.get("required_imports"), field="required_imports")
    forbidden = _names(policy.get("forbidden_imports"), field="forbidden_imports")
    prior_minis = _names(policy.get("prior_mini_modules"), field="prior_mini_modules")
    prior_roots = _names(
        policy.get("forbidden_course_roots"), field="forbidden_course_roots"
    )

    workspace = Path(workspace_root)
    entry = _safe_file(workspace, question_file)
    direct_source = entry.read_text(encoding="utf-8")
    direct_imports = imported_modules(direct_source, filename=question_file)
    missing = [
        name
        for name in required
        if not any(_matches(imported, name) for imported in direct_imports)
    ]
    if missing:
        raise _policy_error(
            "question file is missing required import(s): " + ", ".join(missing)
        )

    pending = [entry]
    visited: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        relative = path.relative_to(workspace.resolve()).as_posix()
        imports = imported_modules(path.read_text(encoding="utf-8"), filename=relative)
        for imported in imports:
            blocked = next(
                (
                    boundary
                    for boundary in (*forbidden, *prior_minis, *prior_roots)
                    if _matches(imported, boundary)
                ),
                None,
            )
            if blocked is not None:
                raise _policy_error(
                    f"{relative} imports forbidden module {imported!r} ({blocked!r})"
                )
            if _matches(imported, local_root):
                helper = _local_module_file(
                    workspace, imported, local_root=local_root
                )
                if helper is None:
                    if imported == local_root:
                        continue
                    raise _policy_error(
                        f"{relative} imports undeclared or missing local helper {imported!r}"
                    )
                pending.append(helper.resolve())
