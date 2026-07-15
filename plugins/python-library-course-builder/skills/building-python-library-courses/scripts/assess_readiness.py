#!/usr/bin/env python3
"""Build a deterministic, evidence-backed readiness plan for one course route."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse


ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
LAB_PATTERN = re.compile(r"^lab\d{2}$")
PREPARATORY_PATTERN = re.compile(r"^prep(?:0[1-9]|[1-9]\d+)$")
SUMMARY_PATTERN = re.compile(r"^[0-9a-f]{12}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CATEGORY_ORDER = {"python": 0, "library": 1, "domain": 2}
DIAGNOSTIC_KINDS = {"prediction", "code_reading", "micro_code"}
EVIDENCE_KINDS = {"code", "conversation", "self_report"}
EVIDENCE_VERDICTS = {"sufficient", "missing", "claim"}
UNKNOWN_ANSWERS = {
    "不会",
    "我不会",
    "不知道",
    "我不知道",
    "不清楚",
    "不会做",
    "idk",
    "i don't know",
    "i do not know",
}
PLAN_CAPABILITY_FIELDS = {
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
}
PLAN_UNIT_FIELDS = {
    "id",
    "category",
    "dag_level",
    "depends_on",
    "capability_ids",
    "study_minutes",
}


class ReadinessValidationError(ValueError):
    """The route, evidence, or readiness plan is incomplete or inconsistent."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReadinessValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReadinessValidationError(f"{label} must be an array")
    return value


def _text(mapping: dict[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReadinessValidationError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def _stable_id(mapping: dict[str, Any], key: str, label: str) -> str:
    value = _text(mapping, key, label)
    if not ID_PATTERN.fullmatch(value):
        raise ReadinessValidationError(
            f"{label}.{key} must be a stable lowercase id"
        )
    return value


def _exact_fields(
    mapping: dict[str, Any],
    expected: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    missing = sorted(expected - set(mapping))
    unknown = sorted(set(mapping) - expected - optional)
    if missing:
        raise ReadinessValidationError(
            f"{label} is missing required field(s): {', '.join(missing)}"
        )
    if unknown:
        raise ReadinessValidationError(
            f"{label} has unknown field(s): {', '.join(unknown)}"
        )


def _string_array(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    items = _array(value, label)
    if (not allow_empty and not items) or any(
        not isinstance(item, str) or not item.strip() for item in items
    ):
        qualifier = "" if allow_empty else " non-empty"
        raise ReadinessValidationError(
            f"{label} must contain{qualifier} strings"
        )
    normalized = [item.strip() for item in items]
    if len(normalized) != len(set(normalized)):
        raise ReadinessValidationError(f"{label} must contain unique values")
    return normalized


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validate_route(payload: Any) -> tuple[dict[str, Any], list[str], dict[str, int]]:
    route_spec = copy.deepcopy(_object(payload, "route specification"))
    _exact_fields(
        route_spec,
        {"schema_version", "route", "official_sources", "capabilities"},
        "route specification",
    )
    if route_spec.get("schema_version") != 1:
        raise ReadinessValidationError("route specification.schema_version must be 1")

    route = _object(route_spec.get("route"), "route specification.route")
    _exact_fields(route, {"id", "title"}, "route specification.route")
    _stable_id(route, "id", "route specification.route")
    _text(route, "title", "route specification.route")

    source_ids: set[str] = set()
    sources = _array(
        route_spec.get("official_sources"), "route specification.official_sources"
    )
    if not sources:
        raise ReadinessValidationError(
            "route specification.official_sources must not be empty"
        )
    for index, raw_source in enumerate(sources):
        label = f"route specification.official_sources[{index}]"
        source = _object(raw_source, label)
        _exact_fields(source, {"id", "title", "url", "kind", "version"}, label)
        source_id = _stable_id(source, "id", label)
        if source_id in source_ids:
            raise ReadinessValidationError(f"duplicate official source id: {source_id}")
        source_ids.add(source_id)
        for key in ("title", "kind", "version"):
            _text(source, key, label)
        url = _text(source, "url", label)
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ReadinessValidationError(f"{label}.url must be an HTTPS URL")

    capabilities = _array(
        route_spec.get("capabilities"), "route specification.capabilities"
    )
    if not capabilities:
        raise ReadinessValidationError(
            "route specification.capabilities must not be empty"
        )
    capability_ids: list[str] = []
    diagnostic_ids: set[str] = set()
    for index, raw_capability in enumerate(capabilities):
        label = f"route specification.capabilities[{index}]"
        capability = _object(raw_capability, label)
        _exact_fields(
            capability,
            {
                "id",
                "kind",
                "subject",
                "title",
                "requires",
                "source_ids",
                "first_used_in",
                "prep_tier",
                "diagnostic",
            },
            label,
            optional={"prep_reason"},
        )
        capability_id = _stable_id(capability, "id", label)
        if capability_id in capability_ids:
            raise ReadinessValidationError(
                f"duplicate capability id: {capability_id}"
            )
        capability_ids.append(capability_id)
        if capability.get("kind") not in CATEGORY_ORDER:
            raise ReadinessValidationError(
                f"{label}.kind must be python, library, or domain"
            )
        for key in ("subject", "title"):
            _text(capability, key, label)
        _string_array(capability.get("requires"), f"{label}.requires", allow_empty=True)
        capability_sources = _string_array(
            capability.get("source_ids"), f"{label}.source_ids"
        )
        unknown_sources = sorted(set(capability_sources) - source_ids)
        if unknown_sources:
            raise ReadinessValidationError(
                f"{label}.source_ids reference unknown official source(s): "
                + ", ".join(unknown_sources)
            )
        first_used_in = _text(capability, "first_used_in", label)
        if not LAB_PATTERN.fullmatch(first_used_in) or first_used_in == "lab00":
            raise ReadinessValidationError(
                f"{label}.first_used_in must identify a graded lab"
            )
        tier = capability.get("prep_tier")
        if tier not in {"standard", "extended"}:
            raise ReadinessValidationError(
                f"{label}.prep_tier must be standard or extended"
            )
        if tier == "extended":
            _text(capability, "prep_reason", label)
        elif "prep_reason" in capability:
            raise ReadinessValidationError(
                f"{label}.prep_reason is only valid for extended prep"
            )

        diagnostic_label = f"{label}.diagnostic"
        diagnostic = _object(capability.get("diagnostic"), diagnostic_label)
        _exact_fields(
            diagnostic,
            {"id", "kind", "prompt", "choices", "answer_id"},
            diagnostic_label,
        )
        diagnostic_id = _stable_id(diagnostic, "id", diagnostic_label)
        if diagnostic_id in diagnostic_ids:
            raise ReadinessValidationError(
                f"duplicate diagnostic question id: {diagnostic_id}"
            )
        diagnostic_ids.add(diagnostic_id)
        if diagnostic.get("kind") not in DIAGNOSTIC_KINDS:
            raise ReadinessValidationError(
                f"{diagnostic_label}.kind must be prediction, code_reading, or micro_code"
            )
        _text(diagnostic, "prompt", diagnostic_label)
        choices = _array(diagnostic.get("choices"), f"{diagnostic_label}.choices")
        if not 3 <= len(choices) <= 4:
            raise ReadinessValidationError(
                f"{diagnostic_label}.choices must contain 3-4 choices"
            )
        choice_ids: set[str] = set()
        for choice_index, raw_choice in enumerate(choices):
            choice_label = f"{diagnostic_label}.choices[{choice_index}]"
            choice = _object(raw_choice, choice_label)
            _exact_fields(choice, {"id", "text"}, choice_label)
            choice_id = _stable_id(choice, "id", choice_label)
            if choice_id in choice_ids:
                raise ReadinessValidationError(
                    f"duplicate diagnostic choice id: {choice_id}"
                )
            choice_ids.add(choice_id)
            _text(choice, "text", choice_label)
        if diagnostic.get("answer_id") not in choice_ids:
            raise ReadinessValidationError(
                f"{diagnostic_label}.answer_id must reference a choice"
            )

    known_ids = set(capability_ids)
    for index, capability in enumerate(capabilities):
        unknown = sorted(set(capability["requires"]) - known_ids)
        if unknown:
            raise ReadinessValidationError(
                f"route specification.capabilities[{index}].requires references "
                f"unknown capability(s): {', '.join(unknown)}"
            )

    position = {capability_id: index for index, capability_id in enumerate(capability_ids)}
    by_id = {str(item["id"]): item for item in capabilities}
    indegree = {
        capability_id: len(by_id[capability_id]["requires"])
        for capability_id in capability_ids
    }
    dependents: dict[str, list[str]] = {capability_id: [] for capability_id in capability_ids}
    for capability_id in capability_ids:
        for dependency in by_id[capability_id]["requires"]:
            dependents[str(dependency)].append(capability_id)
    ready = sorted(
        [capability_id for capability_id, count in indegree.items() if count == 0],
        key=position.__getitem__,
    )
    ordered: list[str] = []
    levels: dict[str, int] = {}
    while ready:
        capability_id = ready.pop(0)
        ordered.append(capability_id)
        dependencies = [str(value) for value in by_id[capability_id]["requires"]]
        levels[capability_id] = (
            1 + max((levels[dependency] for dependency in dependencies), default=0)
        )
        for dependent in sorted(dependents[capability_id], key=position.__getitem__):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort(key=position.__getitem__)
    if len(ordered) != len(capability_ids):
        cyclic = [item for item in capability_ids if item not in ordered]
        raise ReadinessValidationError(
            "capability DAG contains a cycle involving: " + ", ".join(cyclic)
        )
    return route_spec, ordered, levels


def _validate_evidence(payload: Any, *, route_id: str) -> dict[str, Any]:
    evidence = copy.deepcopy(_object(payload, "evidence report"))
    _exact_fields(
        evidence,
        {"schema_version", "evidence", "responses"},
        "evidence report",
        optional={"route_id"},
    )
    if evidence.get("schema_version") != 1:
        raise ReadinessValidationError("evidence report.schema_version must be 1")
    if "route_id" in evidence and evidence.get("route_id") != route_id:
        raise ReadinessValidationError("evidence report.route_id does not match route")
    _array(evidence.get("evidence"), "evidence report.evidence")
    _array(evidence.get("responses"), "evidence report.responses")
    return evidence


def _set_resolution(
    resolutions: dict[str, tuple[str, str]],
    capability_id: str,
    status: str,
    basis: str,
) -> None:
    previous = resolutions.get(capability_id)
    current = (status, basis)
    if previous is not None and previous[0] != status:
        raise ReadinessValidationError(
            f"conflicting readiness evidence for capability {capability_id}"
        )
    resolutions.setdefault(capability_id, current)


def _normalize_unknown_answer(value: str) -> str:
    return " ".join(value.strip().casefold().rstrip("。.!！?").split())


def _build_preparatory_units(
    *,
    ordered_ids: list[str],
    levels: dict[str, int],
    capabilities_by_id: dict[str, dict[str, Any]],
    missing_ids: set[str],
) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = [
        {
            "id": "lab00",
            "category": "orientation",
            "dag_level": 0,
            "depends_on": None,
            "capability_ids": [],
            "study_minutes": {
                "tier": "orientation",
                "min": 15,
                "max": 30,
            },
        }
    ]
    grouped: dict[tuple[int, str], list[str]] = {}
    for capability_id in ordered_ids:
        if capability_id not in missing_ids:
            continue
        capability = capabilities_by_id[capability_id]
        key = (levels[capability_id], str(capability["kind"]))
        grouped.setdefault(key, []).append(capability_id)
    keys = sorted(grouped, key=lambda item: (item[0], CATEGORY_ORDER[item[1]]))
    previous = "lab00"
    for index, (dag_level, category) in enumerate(keys, start=1):
        capability_ids = grouped[(dag_level, category)]
        extended = [
            capabilities_by_id[capability_id]
            for capability_id in capability_ids
            if capabilities_by_id[capability_id]["prep_tier"] == "extended"
        ]
        if extended:
            reasons = list(
                dict.fromkeys(str(item["prep_reason"]) for item in extended)
            )
            minutes: dict[str, Any] = {
                "tier": "extended",
                "min": 45,
                "max": 60,
                "reason": " ".join(reasons),
            }
        else:
            minutes = {"tier": "standard", "min": 30, "max": 45}
        unit_id = f"prep{index:02d}"
        units.append(
            {
                "id": unit_id,
                "category": category,
                "dag_level": dag_level,
                "depends_on": previous,
                "capability_ids": capability_ids,
                "study_minutes": minutes,
            }
        )
        previous = unit_id
    return units


def _safe_plan_projection(plan: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema_version",
        "status",
        "route_id",
        "route_digest",
        "official_sources",
        "official_source_ids",
        "capability_dag",
        "required_capability_ids",
        "mastered_capability_ids",
        "missing_capability_ids",
        "capabilities",
        "preparatory_units",
        "preparatory_time",
        "readiness_summary",
    )
    return {key: copy.deepcopy(plan[key]) for key in keys}


def _readiness_summary(plan: dict[str, Any]) -> str:
    """Derive the learner-profile identity from the plan's safe decisions."""

    return _digest(
        {
            "route_id": plan["route_id"],
            "route_digest": plan["route_digest"],
            "resolutions": [
                {"id": item["id"], "status": item["status"]}
                for item in plan["capabilities"]
            ],
            "preparatory_units": plan["preparatory_units"],
        }
    )[:12]


def _validate_plan_minutes(
    value: Any, *, label: str, orientation: bool
) -> dict[str, Any]:
    minutes = _object(value, label)
    if orientation:
        _exact_fields(minutes, {"tier", "min", "max"}, label)
        if minutes != {"tier": "orientation", "min": 15, "max": 30}:
            raise ReadinessValidationError(
                f"{label} must be the exact 15-30 minute orientation tier"
            )
        return minutes
    tier = minutes.get("tier")
    if tier == "standard":
        _exact_fields(minutes, {"tier", "min", "max"}, label)
        if minutes != {"tier": "standard", "min": 30, "max": 45}:
            raise ReadinessValidationError(
                f"{label} must be the exact 30-45 minute standard tier"
            )
        return minutes
    if tier == "extended":
        _exact_fields(minutes, {"tier", "min", "max", "reason"}, label)
        if (
            type(minutes.get("min")) is not int
            or type(minutes.get("max")) is not int
            or minutes["min"] != 45
            or minutes["max"] != 60
        ):
            raise ReadinessValidationError(
                f"{label} must use the exact 45-60 minute extended tier"
            )
        _text(minutes, "reason", label)
        return minutes
    raise ReadinessValidationError(f"{label}.tier must be standard or extended")


def validate_ready_plan(payload: Any) -> dict[str, Any]:
    """Validate plan integrity without retaining its temporary raw evidence."""

    plan = copy.deepcopy(_object(payload, "readiness plan"))
    required = {
        "schema_version",
        "status",
        "route_id",
        "route_digest",
        "official_sources",
        "official_source_ids",
        "capability_dag",
        "required_capability_ids",
        "mastered_capability_ids",
        "missing_capability_ids",
        "capabilities",
        "preparatory_units",
        "preparatory_time",
        "readiness_summary",
        "plan_digest",
    }
    missing = sorted(required - set(plan))
    if missing:
        raise ReadinessValidationError(
            "readiness plan is missing required field(s): " + ", ".join(missing)
        )
    if plan.get("schema_version") != 1:
        raise ReadinessValidationError("readiness plan.schema_version must be 1")
    if plan.get("status") != "ready":
        raise ReadinessValidationError("readiness plan status must be ready")
    _stable_id(plan, "route_id", "readiness plan")
    route_digest = plan.get("route_digest")
    if not isinstance(route_digest, str) or not SHA256_PATTERN.fullmatch(route_digest):
        raise ReadinessValidationError("readiness plan.route_digest must be sha256")
    summary = plan.get("readiness_summary")
    if not isinstance(summary, str) or not SUMMARY_PATTERN.fullmatch(summary):
        raise ReadinessValidationError(
            "readiness plan.readiness_summary must be 12 lowercase hex characters"
        )
    sources = _array(plan.get("official_sources"), "readiness plan.official_sources")
    if not sources:
        raise ReadinessValidationError(
            "readiness plan.official_sources must not be empty"
        )
    normalized_sources: list[dict[str, Any]] = []
    for index, raw_source in enumerate(sources):
        label = f"readiness plan.official_sources[{index}]"
        source = _object(raw_source, label)
        _exact_fields(source, {"id", "title", "url", "kind", "version"}, label)
        _stable_id(source, "id", label)
        for key in ("title", "kind", "version"):
            _text(source, key, label)
        parsed = urlparse(_text(source, "url", label))
        if parsed.scheme != "https" or not parsed.netloc:
            raise ReadinessValidationError(f"{label}.url must be an HTTPS URL")
        normalized_sources.append(source)
    source_ids = _string_array(
        plan.get("official_source_ids"), "readiness plan.official_source_ids"
    )
    if source_ids != [str(source["id"]) for source in normalized_sources]:
        raise ReadinessValidationError(
            "readiness plan official_source_ids must match official_sources order"
        )
    raw_dag = _array(plan.get("capability_dag"), "readiness plan.capability_dag")

    required_ids = _string_array(
        plan.get("required_capability_ids"),
        "readiness plan.required_capability_ids",
    )
    mastered_ids = _string_array(
        plan.get("mastered_capability_ids"),
        "readiness plan.mastered_capability_ids",
        allow_empty=True,
    )
    missing_ids = _string_array(
        plan.get("missing_capability_ids"),
        "readiness plan.missing_capability_ids",
        allow_empty=True,
    )
    if set(mastered_ids).intersection(missing_ids) or set(mastered_ids + missing_ids) != set(required_ids):
        raise ReadinessValidationError(
            "readiness plan must resolve every required capability exactly once"
        )
    if len(raw_dag) != len(required_ids):
        raise ReadinessValidationError(
            "readiness plan.capability_dag must follow required_capability_ids"
        )
    dag_by_id: dict[str, dict[str, Any]] = {}
    dag_levels: dict[str, int] = {}
    for index, (raw_entry, required_id) in enumerate(
        zip(raw_dag, required_ids, strict=True)
    ):
        label = f"readiness plan.capability_dag[{index}]"
        entry = _object(raw_entry, label)
        required_fields = {"id", "kind", "requires", "dag_level", "prep_tier"}
        _exact_fields(entry, required_fields, label, optional={"prep_reason"})
        capability_id = _stable_id(entry, "id", label)
        if capability_id != required_id:
            raise ReadinessValidationError(
                "readiness plan.capability_dag must follow required_capability_ids"
            )
        if entry.get("kind") not in CATEGORY_ORDER:
            raise ReadinessValidationError(
                f"{label}.kind must be python, library, or domain"
            )
        dependencies = _string_array(
            entry.get("requires"), f"{label}.requires", allow_empty=True
        )
        if any(dependency not in dag_by_id for dependency in dependencies):
            raise ReadinessValidationError(
                f"{label}.requires must reference earlier DAG capabilities"
            )
        expected_level = 1 + max(
            (dag_levels[dependency] for dependency in dependencies), default=0
        )
        if entry.get("dag_level") != expected_level:
            raise ReadinessValidationError(
                f"{label}.dag_level does not match its dependencies"
            )
        tier = entry.get("prep_tier")
        if tier not in {"standard", "extended"}:
            raise ReadinessValidationError(
                f"{label}.prep_tier must be standard or extended"
            )
        if tier == "extended":
            _text(entry, "prep_reason", label)
        elif "prep_reason" in entry:
            raise ReadinessValidationError(
                f"{label}.prep_reason is only valid for extended prep"
            )
        dag_by_id[capability_id] = entry
        dag_levels[capability_id] = expected_level
    capabilities = _array(plan.get("capabilities"), "readiness plan.capabilities")
    if len(capabilities) != len(required_ids):
        raise ReadinessValidationError(
            "readiness plan.capabilities must follow required_capability_ids"
        )
    known_from_capabilities: list[str] = []
    missing_from_capabilities: list[str] = []
    capability_kinds: dict[str, str] = {}
    for index, (raw_capability, required_id) in enumerate(
        zip(capabilities, required_ids, strict=True)
    ):
        label = f"readiness plan.capabilities[{index}]"
        capability = _object(raw_capability, label)
        _exact_fields(capability, PLAN_CAPABILITY_FIELDS, label)
        capability_id = _stable_id(capability, "id", label)
        if capability_id != required_id:
            raise ReadinessValidationError(
                "readiness plan.capabilities must follow required_capability_ids"
            )
        kind = capability.get("kind")
        if kind not in CATEGORY_ORDER:
            raise ReadinessValidationError(
                f"{label}.kind must be python, library, or domain"
            )
        capability_kinds[capability_id] = str(kind)
        if dag_by_id[capability_id]["kind"] != kind:
            raise ReadinessValidationError(
                f"{label}.kind does not match capability_dag"
            )
        for key in ("subject", "title", "basis"):
            _text(capability, key, label)
        capability_sources = _string_array(
            capability.get("source_ids"), f"{label}.source_ids"
        )
        if set(capability_sources) - set(source_ids):
            raise ReadinessValidationError(
                f"{label}.source_ids reference unknown official sources"
            )
        first_used_in = _text(capability, "first_used_in", label)
        if not LAB_PATTERN.fullmatch(first_used_in) or first_used_in == "lab00":
            raise ReadinessValidationError(
                f"{label}.first_used_in must identify a graded lab"
            )
        status = capability.get("status")
        decision = capability.get("decision")
        prep_id = capability.get("preparatory_unit_id")
        if status == "known":
            if decision != "assume" or prep_id is not None:
                raise ReadinessValidationError(
                    f"{label} known capability must be assumed without prep"
                )
            known_from_capabilities.append(capability_id)
        elif status == "missing":
            if (
                decision != "preparatory"
                or not isinstance(prep_id, str)
                or not PREPARATORY_PATTERN.fullmatch(prep_id)
            ):
                raise ReadinessValidationError(
                    f"{label} missing capability must map to a prep unit"
                )
            missing_from_capabilities.append(capability_id)
        else:
            raise ReadinessValidationError(f"{label}.status must be known or missing")
    if mastered_ids != known_from_capabilities or missing_ids != missing_from_capabilities:
        raise ReadinessValidationError(
            "readiness plan capability statuses must match mastered and missing ids"
        )
    units = _array(plan.get("preparatory_units"), "readiness plan.preparatory_units")
    if not units:
        raise ReadinessValidationError(
            "readiness plan.preparatory_units must start with lab00"
        )
    expected_units = _build_preparatory_units(
        ordered_ids=required_ids,
        levels=dag_levels,
        capabilities_by_id=dag_by_id,
        missing_ids=set(missing_ids),
    )
    if units != expected_units:
        raise ReadinessValidationError(
            "readiness plan.preparatory_units do not match its capability DAG"
        )
    planned_missing: list[str] = []
    planned_unit_by_capability: dict[str, str] = {}
    previous_id: str | None = None
    previous_level = 0
    previous_category_order = -1
    for index, raw_unit in enumerate(units):
        label = f"readiness plan.preparatory_units[{index}]"
        unit = _object(raw_unit, label)
        _exact_fields(unit, PLAN_UNIT_FIELDS, label)
        expected_id = "lab00" if index == 0 else f"prep{index:02d}"
        if unit.get("id") != expected_id:
            raise ReadinessValidationError(f"{label}.id must be {expected_id}")
        capability_ids = _string_array(
            unit.get("capability_ids"),
            f"{label}.capability_ids",
            allow_empty=index == 0,
        )
        dag_level = unit.get("dag_level")
        if index == 0:
            if (
                unit.get("category") != "orientation"
                or dag_level != 0
                or unit.get("depends_on") is not None
                or capability_ids
            ):
                raise ReadinessValidationError(
                    "readiness plan lab00 must be the fixed orientation"
                )
            _validate_plan_minutes(
                unit.get("study_minutes"), label=f"{label}.study_minutes", orientation=True
            )
        else:
            category = unit.get("category")
            if category not in CATEGORY_ORDER:
                raise ReadinessValidationError(
                    f"{label}.category must be python, library, or domain"
                )
            if unit.get("depends_on") != previous_id:
                raise ReadinessValidationError(
                    f"{label}.depends_on must be {previous_id}"
                )
            if type(dag_level) is not int or dag_level < 1 or dag_level < previous_level:
                raise ReadinessValidationError(
                    f"{label}.dag_level must be nondecreasing and positive"
                )
            category_order = CATEGORY_ORDER[str(category)]
            if dag_level == previous_level and category_order <= previous_category_order:
                raise ReadinessValidationError(
                    f"{label} must follow python -> library -> domain within its DAG level"
                )
            for capability_id in capability_ids:
                if capability_id not in capability_kinds:
                    raise ReadinessValidationError(
                        f"{label}.capability_ids reference an unknown capability"
                    )
                if capability_kinds[capability_id] != category:
                    raise ReadinessValidationError(
                        f"{label}.category must match every capability kind"
                    )
            _validate_plan_minutes(
                unit.get("study_minutes"), label=f"{label}.study_minutes", orientation=False
            )
            planned_missing.extend(capability_ids)
            planned_unit_by_capability.update(
                {capability_id: expected_id for capability_id in capability_ids}
            )
            previous_category_order = category_order
        previous_id = expected_id
        previous_level = int(dag_level)
    if len(planned_missing) != len(missing_ids) or set(planned_missing) != set(missing_ids):
        raise ReadinessValidationError(
            "readiness plan preparatory units must cover every missing capability once"
        )
    unit_ids = {str(unit["id"]) for unit in units}
    for capability in capabilities:
        prep_id = capability["preparatory_unit_id"]
        if prep_id is not None and prep_id not in unit_ids:
            raise ReadinessValidationError(
                f"readiness plan capability {capability['id']} references an unknown prep unit"
            )
        if prep_id is not None and planned_unit_by_capability.get(capability["id"]) != prep_id:
            raise ReadinessValidationError(
                f"readiness plan capability {capability['id']} does not match its prep unit"
            )
    calculated_time = {
        "min": sum(int(unit["study_minutes"]["min"]) for unit in units),
        "max": sum(int(unit["study_minutes"]["max"]) for unit in units),
    }
    if plan.get("preparatory_time") != calculated_time:
        raise ReadinessValidationError(
            "readiness plan.preparatory_time does not match its units"
        )
    if plan["readiness_summary"] != _readiness_summary(plan):
        raise ReadinessValidationError(
            "readiness plan.readiness_summary does not match its decisions"
        )
    supplied_digest = plan.get("plan_digest")
    expected_digest = _digest(_safe_plan_projection(plan))
    if supplied_digest != expected_digest:
        raise ReadinessValidationError("readiness plan digest does not match its content")
    return _safe_plan_projection(plan) | {"plan_digest": supplied_digest}


def assess_readiness(route_payload: Any, evidence_payload: Any) -> dict[str, Any]:
    """Return one next diagnostic or a complete, integrity-checked ready plan."""

    route, ordered_ids, levels = _validate_route(route_payload)
    route_id = str(route["route"]["id"])
    evidence = _validate_evidence(evidence_payload, route_id=route_id)
    capabilities_by_id = {
        str(capability["id"]): capability for capability in route["capabilities"]
    }
    diagnostic_to_capability = {
        str(capability["diagnostic"]["id"]): str(capability["id"])
        for capability in route["capabilities"]
    }
    resolutions: dict[str, tuple[str, str]] = {}

    for index, raw_item in enumerate(evidence["evidence"]):
        label = f"evidence report.evidence[{index}]"
        item = _object(raw_item, label)
        _exact_fields(
            item,
            {"capability_id", "kind", "verdict"},
            label,
            optional={"content", "question_id", "answer_id"},
        )
        capability_id = _text(item, "capability_id", label)
        if capability_id not in capabilities_by_id:
            raise ReadinessValidationError(
                f"{label}.capability_id references an unknown capability"
            )
        kind = item.get("kind")
        verdict = item.get("verdict")
        if kind not in EVIDENCE_KINDS:
            raise ReadinessValidationError(f"{label}.kind is unsupported")
        if verdict not in EVIDENCE_VERDICTS:
            raise ReadinessValidationError(f"{label}.verdict is unsupported")
        if "content" in item and not isinstance(item["content"], str):
            raise ReadinessValidationError(f"{label}.content must be a string")
        has_question = "question_id" in item
        has_answer = "answer_id" in item
        if has_question != has_answer:
            raise ReadinessValidationError(
                f"{label}.question_id and answer_id must be supplied together"
            )
        if (has_question or has_answer) and kind != "conversation":
            raise ReadinessValidationError(
                f"{label} diagnostic proof is only valid for conversation evidence"
            )
        if has_question:
            question_id = _text(item, "question_id", label)
            answer_id = _text(item, "answer_id", label)
            diagnostic = capabilities_by_id[capability_id]["diagnostic"]
            if question_id != diagnostic["id"]:
                raise ReadinessValidationError(
                    f"{label}.question_id does not match its capability diagnostic"
                )
        if verdict == "missing":
            _set_resolution(resolutions, capability_id, "missing", "evidence")
        elif verdict == "sufficient" and kind == "code":
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                _set_resolution(
                    resolutions, capability_id, "known", "code-evidence"
                )
        elif verdict == "sufficient" and kind == "conversation" and has_question:
            diagnostic = capabilities_by_id[capability_id]["diagnostic"]
            if answer_id == diagnostic["answer_id"]:
                _set_resolution(
                    resolutions,
                    capability_id,
                    "known",
                    "conversation-diagnostic-evidence",
                )
            else:
                _set_resolution(
                    resolutions,
                    capability_id,
                    "missing",
                    "conversation-diagnostic-evidence",
                )
        # Free-form conversation and self-report claims never establish mastery.

    asked_ids: set[str] = set()
    for index, raw_response in enumerate(evidence["responses"]):
        label = f"evidence report.responses[{index}]"
        response = _object(raw_response, label)
        _exact_fields(response, {"question_id", "answer"}, label)
        question_id = _text(response, "question_id", label)
        if question_id not in diagnostic_to_capability:
            raise ReadinessValidationError(
                f"{label}.question_id references an unknown diagnostic"
            )
        if question_id in asked_ids:
            raise ReadinessValidationError(
                f"duplicate response for diagnostic question {question_id}"
            )
        asked_ids.add(question_id)
        answer = response.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ReadinessValidationError(f"{label}.answer must be a non-empty string")
        capability_id = diagnostic_to_capability[question_id]
        expected_capability_id = next(
            (item for item in ordered_ids if item not in resolutions), None
        )
        if capability_id != expected_capability_id:
            expected_question = (
                capabilities_by_id[expected_capability_id]["diagnostic"]["id"]
                if expected_capability_id is not None
                else "none"
            )
            raise ReadinessValidationError(
                f"{label} must answer the current next_question {expected_question}"
            )
        diagnostic = capabilities_by_id[capability_id]["diagnostic"]
        normalized = _normalize_unknown_answer(answer)
        if normalized in UNKNOWN_ANSWERS:
            _set_resolution(
                resolutions, capability_id, "missing", "declared-missing"
            )
        elif answer.strip() == diagnostic["answer_id"]:
            _set_resolution(
                resolutions, capability_id, "known", "diagnostic-answer"
            )
        else:
            _set_resolution(
                resolutions, capability_id, "missing", "diagnostic-answer"
            )

    mastered_ids = [
        capability_id
        for capability_id in ordered_ids
        if resolutions.get(capability_id, (None, None))[0] == "known"
    ]
    missing_ids = [
        capability_id
        for capability_id in ordered_ids
        if resolutions.get(capability_id, (None, None))[0] == "missing"
    ]
    needs_evidence_ids = [
        capability_id for capability_id in ordered_ids if capability_id not in resolutions
    ]
    asked_question_ids = [
        str(capabilities_by_id[capability_id]["diagnostic"]["id"])
        for capability_id in ordered_ids
        if str(capabilities_by_id[capability_id]["diagnostic"]["id"]) in asked_ids
    ]
    common: dict[str, Any] = {
        "schema_version": 1,
        "status": "needs_evidence" if needs_evidence_ids else "ready",
        "route_id": route_id,
        "route_digest": _digest(route),
        "official_sources": copy.deepcopy(route["official_sources"]),
        "official_source_ids": [str(item["id"]) for item in route["official_sources"]],
        "capability_dag": [
            {
                "id": capability_id,
                "kind": capabilities_by_id[capability_id]["kind"],
                "requires": copy.deepcopy(
                    capabilities_by_id[capability_id]["requires"]
                ),
                "dag_level": levels[capability_id],
                "prep_tier": capabilities_by_id[capability_id]["prep_tier"],
                **(
                    {
                        "prep_reason": capabilities_by_id[capability_id][
                            "prep_reason"
                        ]
                    }
                    if "prep_reason" in capabilities_by_id[capability_id]
                    else {}
                ),
            }
            for capability_id in ordered_ids
        ],
        "required_capability_ids": ordered_ids,
        "mastered_capability_ids": mastered_ids,
        "missing_capability_ids": missing_ids,
        "needs_evidence_capability_ids": needs_evidence_ids,
        "asked_question_ids": asked_question_ids,
        "temporary_evidence": evidence,
    }
    if needs_evidence_ids:
        capability_id = needs_evidence_ids[0]
        diagnostic = copy.deepcopy(capabilities_by_id[capability_id]["diagnostic"])
        diagnostic.pop("answer_id")
        common["next_question"] = {
            "capability_id": capability_id,
            **diagnostic,
        }
        return common

    units = _build_preparatory_units(
        ordered_ids=ordered_ids,
        levels=levels,
        capabilities_by_id=capabilities_by_id,
        missing_ids=set(missing_ids),
    )
    unit_by_capability = {
        str(capability_id): str(unit["id"])
        for unit in units[1:]
        for capability_id in unit["capability_ids"]
    }
    capability_plan = []
    for capability_id in ordered_ids:
        capability = capabilities_by_id[capability_id]
        status, basis = resolutions[capability_id]
        capability_plan.append(
            {
                "id": capability_id,
                "kind": capability["kind"],
                "subject": capability["subject"],
                "title": capability["title"],
                "status": status,
                "decision": "assume" if status == "known" else "preparatory",
                "basis": basis,
                "source_ids": copy.deepcopy(capability["source_ids"]),
                "first_used_in": capability["first_used_in"],
                "preparatory_unit_id": unit_by_capability.get(capability_id),
            }
        )
    time = {
        "min": sum(int(unit["study_minutes"]["min"]) for unit in units),
        "max": sum(int(unit["study_minutes"]["max"]) for unit in units),
    }
    common.update(
        {
            "capabilities": capability_plan,
            "preparatory_units": units,
            "preparatory_time": time,
        }
    )
    common["readiness_summary"] = _readiness_summary(common)
    common["plan_digest"] = _digest(_safe_plan_projection(common))
    common["next_question"] = None
    validate_ready_plan(common)
    return common


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ReadinessValidationError(f"{label} does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ReadinessValidationError(f"{label} is invalid JSON: {path}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = assess_readiness(
            _load_json(args.route, "route specification"),
            _load_json(args.evidence, "evidence report"),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ReadinessValidationError) as error:
        print(f"readiness assessment failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "route_id": report["route_id"],
                "output": str(args.output),
                "next_capability": (
                    report["next_question"]["capability_id"]
                    if report.get("next_question")
                    else None
                ),
                "preparatory_time": report.get("preparatory_time"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
