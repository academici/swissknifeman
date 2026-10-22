"""Pure provider-health composition over owner-produced evidence.

This module reads no provider targets and performs no I/O.  Callers supply the
desired requirement set and immutable, redacted evidence rows produced by the
owning package; the evaluator only checks coverage, freshness, and aggregate
semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Literal

from ..util import timefmt
from ..util.digest import digest_json
from .status import StatusDiagnostic


HEALTH_CONTRACT_VERSION = "1.0.0"
EvidenceState = Literal[
    "pass", "not-selected", "not-required", "unsupported", "unavailable",
    "unresolved", "unknown", "error",
]
RowStatus = Literal[
    "pass", "not-selected", "not-required", "unsupported", "unavailable",
    "unresolved", "unknown", "stale", "missing", "duplicate", "error",
]
AggregateStatus = Literal["green", "non-green"]

_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")
_EVIDENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SENSITIVE_RE = re.compile(r"(?:secret|token|password|api[-_.]?key)", re.I)


@dataclass(frozen=True, order=True)
class HealthRequirement:
    """One desired provider/axis obligation for a sealed project."""

    provider_id: str
    axis_id: str
    selected: bool
    required: bool

    def __post_init__(self) -> None:
        _require_identifier(self.provider_id, "provider")
        _require_identifier(self.axis_id, "axis")
        if not isinstance(self.selected, bool) or not isinstance(self.required, bool):
            raise TypeError("PH_REQUIREMENT_INVALID")
        if self.required and not self.selected:
            raise ValueError("PH_REQUIRED_PROVIDER_NOT_SELECTED")

    @property
    def key(self) -> tuple[str, str]:
        return self.provider_id, self.axis_id


@dataclass(frozen=True, order=True)
class HealthEvidence:
    """A redacted owner-produced observation; its value is never recomputed here."""

    provider_id: str
    axis_id: str
    state: EvidenceState
    evidence_id: str
    source_id: str
    observed_at: str
    expires_at: str

    def __post_init__(self) -> None:
        _require_identifier(self.provider_id, "provider")
        _require_identifier(self.axis_id, "axis")
        if self.state not in {
            "pass", "not-selected", "not-required", "unsupported", "unavailable",
            "unresolved", "unknown", "error",
        }:
            raise ValueError("PH_STATE_UNKNOWN")
        for value in (self.evidence_id, self.source_id):
            if (not isinstance(value, str) or not _EVIDENCE_ID_RE.fullmatch(value)
                    or _SENSITIVE_RE.search(value)):
                raise ValueError("PH_REDACTION_REQUIRED")
        observed = _timestamp(self.observed_at)
        expires = _timestamp(self.expires_at)
        if expires <= observed:
            raise ValueError("PH_FRESHNESS_INVALID")

    @property
    def key(self) -> tuple[str, str]:
        return self.provider_id, self.axis_id


@dataclass(frozen=True, order=True)
class HealthRow:
    provider_id: str
    axis_id: str
    selected: bool
    required: bool
    status: RowStatus
    evidence_id: str | None
    source_id: str | None
    observed_at: str | None
    expires_at: str | None

    @property
    def healthy(self) -> bool:
        if self.selected and self.required:
            return self.status == "pass"
        if not self.selected:
            return self.status == "not-selected"
        return self.status in {"pass", "not-required", "unsupported"}

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "axis_id": self.axis_id,
            "selected": self.selected,
            "required": self.required,
            "status": self.status,
            "healthy": self.healthy,
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class ProjectHealth:
    project_id: str
    evaluated_at: str
    rows: tuple[HealthRow, ...]
    diagnostics: tuple[StatusDiagnostic, ...]
    aggregate: AggregateStatus
    result_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": HEALTH_CONTRACT_VERSION,
            "project_id": self.project_id,
            "evaluated_at": self.evaluated_at,
            "rows": [row.to_dict() for row in self.rows],
            "diagnostics": [_diagnostic_value(item) for item in self.diagnostics],
            "aggregate": self.aggregate,
            "result_digest": self.result_digest,
        }


@dataclass(frozen=True)
class FleetHealth:
    evaluated_at: str
    required_project_ids: tuple[str, ...]
    projects: tuple[ProjectHealth, ...]
    diagnostics: tuple[StatusDiagnostic, ...]
    aggregate: AggregateStatus
    result_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": HEALTH_CONTRACT_VERSION,
            "evaluated_at": self.evaluated_at,
            "required_project_ids": list(self.required_project_ids),
            "projects": [project.to_dict() for project in self.projects],
            "diagnostics": [_diagnostic_value(item) for item in self.diagnostics],
            "aggregate": self.aggregate,
            "result_digest": self.result_digest,
        }


def evaluate_project(*, project_id: str, requirements: tuple[HealthRequirement, ...],
                     evidence: tuple[HealthEvidence, ...], evaluated_at: str) -> ProjectHealth:
    """Evaluate one exact requirement/evidence set without masking missing peers."""
    _require_project_id(project_id)
    now = _timestamp(evaluated_at)
    _require_tuple(requirements, "PH_REQUIREMENTS_INVALID")
    _require_tuple(evidence, "PH_EVIDENCE_INVALID")
    if not all(isinstance(item, HealthRequirement) for item in requirements):
        raise TypeError("PH_REQUIREMENTS_INVALID")
    if not all(isinstance(item, HealthEvidence) for item in evidence):
        raise TypeError("PH_EVIDENCE_INVALID")

    requirement_groups = _group_by_key(requirements)
    evidence_groups = _group_by_key(evidence)
    diagnostics: list[StatusDiagnostic] = []
    rows: list[HealthRow] = []

    for key in sorted(requirement_groups):
        declarations = requirement_groups[key]
        observations = evidence_groups.get(key, ())
        if len(declarations) != 1:
            rows.append(_synthetic_row(key, "duplicate"))
            diagnostics.append(_diagnostic("PH_DUPLICATE_REQUIREMENT", project_id, key))
            continue
        requirement = declarations[0]
        if not observations:
            rows.append(_synthetic_row(key, "missing", requirement))
            diagnostics.append(_diagnostic("PH_EVIDENCE_MISSING", project_id, key))
            continue
        if len(observations) != 1:
            rows.append(_synthetic_row(key, "duplicate", requirement))
            diagnostics.append(_diagnostic("PH_EVIDENCE_DUPLICATE", project_id, key))
            continue
        observation = observations[0]
        status: RowStatus = "stale" if _timestamp(observation.expires_at) <= now else observation.state
        row = HealthRow(
            provider_id=requirement.provider_id,
            axis_id=requirement.axis_id,
            selected=requirement.selected,
            required=requirement.required,
            status=status,
            evidence_id=observation.evidence_id,
            source_id=observation.source_id,
            observed_at=observation.observed_at,
            expires_at=observation.expires_at,
        )
        rows.append(row)
        if not row.healthy:
            diagnostics.append(_diagnostic(_failure_code(row), project_id, key))

    for key in sorted(set(evidence_groups) - set(requirement_groups)):
        diagnostics.append(_diagnostic("PH_EVIDENCE_EXTRA", project_id, key))

    ordered_rows = tuple(sorted(rows))
    ordered_diagnostics = _ordered_diagnostics(diagnostics)
    aggregate: AggregateStatus = (
        "green" if ordered_rows and all(row.healthy for row in ordered_rows)
        and not ordered_diagnostics else "non-green"
    )
    unsigned = _project_value(
        project_id, evaluated_at, ordered_rows, ordered_diagnostics, aggregate,
    )
    return ProjectHealth(
        project_id=project_id,
        evaluated_at=evaluated_at,
        rows=ordered_rows,
        diagnostics=ordered_diagnostics,
        aggregate=aggregate,
        result_digest=digest_json(unsigned),
    )


def evaluate_fleet(*, required_project_ids: tuple[str, ...],
                   projects: tuple[ProjectHealth, ...], evaluated_at: str) -> FleetHealth:
    """Evaluate exact sealed fleet membership and all project aggregates."""
    _timestamp(evaluated_at)
    _require_tuple(required_project_ids, "PH_PROJECT_SET_INVALID")
    _require_tuple(projects, "PH_PROJECTS_INVALID")
    if not required_project_ids or not all(isinstance(item, str) for item in required_project_ids):
        raise ValueError("PH_PROJECT_SET_INVALID")
    for project_id in required_project_ids:
        _require_project_id(project_id)
    required = tuple(sorted(required_project_ids))
    if len(set(required)) != len(required):
        raise ValueError("PH_PROJECT_SET_INVALID")
    if not all(isinstance(item, ProjectHealth) for item in projects):
        raise TypeError("PH_PROJECTS_INVALID")

    groups: dict[str, list[ProjectHealth]] = {}
    for project in projects:
        groups.setdefault(project.project_id, []).append(project)
    diagnostics: list[StatusDiagnostic] = []
    accepted: list[ProjectHealth] = []
    for project_id in required:
        rows = groups.get(project_id, ())
        if not rows:
            diagnostics.append(_fleet_diagnostic("PH_PROJECT_MISSING", project_id))
        elif len(rows) != 1:
            diagnostics.append(_fleet_diagnostic("PH_PROJECT_DUPLICATE", project_id))
        else:
            accepted.append(rows[0])
    for project_id in sorted(set(groups) - set(required)):
        diagnostics.append(_fleet_diagnostic("PH_PROJECT_EXTRA", project_id))

    ordered_projects = tuple(sorted(accepted, key=lambda item: item.project_id))
    ordered_diagnostics = _ordered_diagnostics(diagnostics)
    aggregate: AggregateStatus = (
        "green" if len(ordered_projects) == len(required)
        and all(project.aggregate == "green" for project in ordered_projects)
        and not ordered_diagnostics else "non-green"
    )
    unsigned = _fleet_value(
        evaluated_at, required, ordered_projects, ordered_diagnostics, aggregate,
    )
    return FleetHealth(
        evaluated_at=evaluated_at,
        required_project_ids=required,
        projects=ordered_projects,
        diagnostics=ordered_diagnostics,
        aggregate=aggregate,
        result_digest=digest_json(unsigned),
    )


def _synthetic_row(key: tuple[str, str], status: RowStatus,
                   requirement: HealthRequirement | None = None) -> HealthRow:
    return HealthRow(
        provider_id=key[0],
        axis_id=key[1],
        selected=True if requirement is None else requirement.selected,
        required=True if requirement is None else requirement.required,
        status=status,
        evidence_id=None,
        source_id=None,
        observed_at=None,
        expires_at=None,
    )


def _failure_code(row: HealthRow) -> str:
    if row.status == "stale":
        return "PH_EVIDENCE_STALE"
    if row.status == "unsupported" and row.required:
        return "PH_REQUIRED_UNSUPPORTED"
    if row.status == "not-selected" or not row.selected:
        return "PH_SELECTION_MISMATCH"
    if row.status == "not-required" and row.required:
        return "PH_REQUIREMENT_MISMATCH"
    return "PH_AXIS_NON_GREEN"


def _diagnostic(code: str, project_id: str,
                key: tuple[str, str]) -> StatusDiagnostic:
    source = f"{project_id}:{key[0]}:{key[1]}"
    return StatusDiagnostic("error", code, code, source)


def _fleet_diagnostic(code: str, project_id: str) -> StatusDiagnostic:
    return StatusDiagnostic("error", code, code, f"fleet:{project_id}")


def _ordered_diagnostics(values: list[StatusDiagnostic]) -> tuple[StatusDiagnostic, ...]:
    return tuple(sorted(values, key=lambda item: (
        {"error": 0, "warning": 1, "info": 2}[item.severity], item.source_ref, item.code,
    )))


def _group_by_key(values: tuple[object, ...]) -> dict[tuple[str, str], tuple[object, ...]]:
    groups: dict[tuple[str, str], list[object]] = {}
    for value in values:
        groups.setdefault(value.key, []).append(value)  # type: ignore[attr-defined]
    return {key: tuple(items) for key, items in groups.items()}


def _project_value(project_id: str, evaluated_at: str, rows: tuple[HealthRow, ...],
                   diagnostics: tuple[StatusDiagnostic, ...], aggregate: str) -> dict[str, object]:
    return {
        "contract_version": HEALTH_CONTRACT_VERSION,
        "project_id": project_id,
        "evaluated_at": evaluated_at,
        "rows": [row.to_dict() for row in rows],
        "diagnostics": [_diagnostic_value(item) for item in diagnostics],
        "aggregate": aggregate,
    }


def _fleet_value(evaluated_at: str, required_project_ids: tuple[str, ...],
                 projects: tuple[ProjectHealth, ...], diagnostics: tuple[StatusDiagnostic, ...],
                 aggregate: str) -> dict[str, object]:
    return {
        "contract_version": HEALTH_CONTRACT_VERSION,
        "evaluated_at": evaluated_at,
        "required_project_ids": list(required_project_ids),
        "projects": [project.to_dict() for project in projects],
        "diagnostics": [_diagnostic_value(item) for item in diagnostics],
        "aggregate": aggregate,
    }


def _diagnostic_value(value: StatusDiagnostic) -> dict[str, str]:
    return {
        "severity": value.severity,
        "code": value.code,
        "message": value.message,
        "source_ref": value.source_ref,
    }


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"PH_{label.upper()}_ID_INVALID")


def _require_project_id(value: object) -> None:
    if not isinstance(value, str) or not _PROJECT_ID_RE.fullmatch(value):
        raise ValueError("PH_PROJECT_ID_INVALID")


def _require_tuple(value: object, code: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(code)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("PH_TIMESTAMP_INVALID")
    parsed = timefmt.parse_rfc3339(value)
    if parsed is None:
        raise ValueError("PH_TIMESTAMP_INVALID")
    return parsed
