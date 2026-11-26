"""Store-side rules both execution backends apply before persisting attempts, steps and notes.

The schema check is injected so the domain stays free of the platform schema registry; the error
factories give both backends the same error codes and details.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.attempt import (
    CONTINUATION_MAX_BYTES,
    TERMINAL_ATTEMPT_STATES,
    Attempt,
    continuation_to_json,
)
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.step import AttemptStep, StepState
from skm.modules.execution.domain.step_note import NoteKind, StepNote, Urgency
from skm.modules.execution.domain.work_policy import EffectiveWorkPolicy, work_policy_to_json

if TYPE_CHECKING:
    from skm.modules.execution.domain.execution_bundle import ExecutionBundle
    from skm.modules.execution.domain.readiness import ReadinessReport

__all__ = [
    "CONFIG_SNAPSHOT_MAX_BYTES",
    "EVIDENCE_BINDING_ROLES",
    "PENDING_CONTINUATION_URN",
    "READINESS_REPORT_URN",
    "ROUTE_SNAPSHOT_URN",
    "RUNTIME_OBSERVATION_URN",
    "STEP_JSON_MAX_BYTES",
    "WORK_POLICIES_MAX_BYTES",
    "already_exists",
    "canonical_bytes",
    "check_binding_role",
    "config_snapshot_document",
    "field_owned",
    "invalid_ref",
    "invalid_transition",
    "not_found",
    "schema_invalid",
    "validate_continuation_payload",
    "validate_readiness_report",
    "validate_step_note",
    "validate_step_payloads",
    "version_conflict",
    "work_policies_document",
]

STEP_JSON_MAX_BYTES: Final = 16384
ROUTE_SNAPSHOT_URN: Final = "urn:skm:execution:route-snapshot:v1"
RUNTIME_OBSERVATION_URN: Final = "urn:skm:runtimes:runtime-observation:v1"
PENDING_CONTINUATION_URN: Final = "urn:skm:execution:pending-continuation:v1"
READINESS_REPORT_URN: Final = "urn:skm:execution:readiness-report:v1"
CONFIG_SNAPSHOT_MAX_BYTES: Final = 1_048_576
WORK_POLICIES_MAX_BYTES: Final = 16_777_216

EVIDENCE_BINDING_ROLES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "attempt": frozenset(
            {
                "evidence",
                "transcript",
                "prompt",
                "raw_result",
                "patch",
                "fix_brief",
                "diagnostic",
                "coverage_report",
            }
        ),
        "output": frozenset({"patch", "evidence", "coverage_report"}),
        "check_execution": frozenset({"stdout", "stderr", "report", "evidence"}),
        "review": frozenset({"report", "diff", "transcript", "evidence"}),
    }
)
"""File roles an evidence binding may carry, per owner kind."""

type SchemaCheck = Callable[[str, JsonValue], None]
"""``require_valid(urn, document)``: raises when ``document`` does not match the schema ``urn``."""


def canonical_bytes(value: object) -> bytes:
    """Compact, key-sorted UTF-8 JSON; a value that is not JSON is ``SCHEMA_INVALID``."""
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, f"value is not canonical JSON: {exc}") from None
    return text.encode("utf-8")


def not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


def already_exists(constraint: str, **details: JsonValue) -> Conflict:
    return Conflict(
        ErrorCode.ALREADY_EXISTS,
        f"unique constraint {constraint}",
        details={"constraint": constraint, **details},
    )


def version_conflict(kind: str, ref: object, expected: int | None, actual: int | None) -> Conflict:
    return Conflict(
        ErrorCode.VERSION_CONFLICT,
        f"{kind} row_version mismatch",
        details={"kind": kind, "ref": str(ref), "expected": expected, "actual": actual},
    )


def field_owned(kind: str, field_name: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.FIELD_OWNED,
        f"{kind}.{field_name} is immutable",
        details={"kind": kind, "field": field_name},
    )


def invalid_transition(msg: str, **details: JsonValue) -> PreconditionFailed:
    return PreconditionFailed(ErrorCode.INVALID_TRANSITION, msg, details=dict(details))


def invalid_ref(constraint: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.INVALID_REFERENCE,
        f"foreign key {constraint} violated",
        details={"constraint": constraint, **details},
    )


def schema_invalid(msg: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, msg, details=dict(details))


def validate_step_payloads(
    step: AttemptStep, old_step: AttemptStep | None, *, require_valid: SchemaCheck
) -> None:
    """Size, schema and immutability rules of the step route snapshot and runtime observation."""
    if step.route_snapshot is not None:
        raw_rs = thaw_json(step.route_snapshot)
        if len(canonical_bytes(raw_rs)) > STEP_JSON_MAX_BYTES:
            raise schema_invalid("route_snapshot exceeds 16384 canonical UTF-8 bytes", field="route_snapshot")
        require_valid(ROUTE_SNAPSHOT_URN, raw_rs)
    if step.runtime_observation is not None:
        if step.state is StepState.STARTED:
            raise schema_invalid(
                "runtime_observation is recorded only on a terminal step", field="runtime_observation"
            )
        raw_obs = thaw_json(step.runtime_observation)
        if len(canonical_bytes(raw_obs)) > STEP_JSON_MAX_BYTES:
            raise schema_invalid(
                "runtime_observation exceeds 16384 canonical UTF-8 bytes", field="runtime_observation"
            )
        require_valid(RUNTIME_OBSERVATION_URN, raw_obs)
        if isinstance(raw_obs, dict) and raw_obs.get("request_id") != str(step.id):
            raise schema_invalid(
                "runtime_observation.request_id must equal step.id", field="runtime_observation.request_id"
            )
    if old_step is not None:
        if thaw_json(step.route_snapshot) != thaw_json(old_step.route_snapshot):
            raise field_owned("attempt_step", "route_snapshot")
        if old_step.runtime_observation is None and step.runtime_observation is not None:
            if old_step.state is not StepState.STARTED:
                raise invalid_transition(
                    "late observation on a terminal step is forbidden", step_id=str(step.id)
                )
        elif old_step.runtime_observation is not None and thaw_json(step.runtime_observation) != thaw_json(
            old_step.runtime_observation
        ):
            raise field_owned("attempt_step", "runtime_observation")


def _validate_cursor_params(value: object) -> None:
    forbidden = {
        "config",
        "config_snapshot",
        "config_digest",
        "input_digest",
        "token",
        "manifest",
        "locators",
    }
    if isinstance(value, dict):
        if forbidden.intersection(cast("dict[str, object]", value)):
            raise schema_invalid(
                "continuation params contain forbidden transport fields", field="continuation"
            )
        for child in cast("dict[str, object]", value).values():
            _validate_cursor_params(child)
    elif isinstance(value, list):
        for child in cast("list[object]", value):
            _validate_cursor_params(child)


def validate_continuation_payload(
    attempt: Attempt, old_attempt: Attempt | None, *, require_valid: SchemaCheck
) -> None:
    """A terminal attempt is frozen; a continuation is bounded, schema-valid and free of transport fields."""
    if old_attempt is not None and old_attempt.state in TERMINAL_ATTEMPT_STATES and attempt != old_attempt:
        raise invalid_transition("terminal attempt cannot be mutated", attempt_id=str(attempt.id))
    if attempt.continuation is not None:
        doc = continuation_to_json(attempt.continuation)
        if doc.get("kind") == "stage":
            _validate_cursor_params(doc["stage"])
        if len(canonical_bytes(doc)) > CONTINUATION_MAX_BYTES:
            raise schema_invalid("continuation exceeds 65536 canonical UTF-8 bytes", field="continuation")
        require_valid(PENDING_CONTINUATION_URN, doc)


def validate_step_note(note: StepNote) -> None:
    if not 1 <= len(note.text) <= 20000:
        raise schema_invalid("step note text must be 1..20000 chars", field="text")
    if note.why_blocked is not None and len(note.why_blocked) > 2000:
        raise schema_invalid("step note why_blocked must be <= 2000 chars", field="why_blocked")
    if note.options and len(canonical_bytes(list(note.options))) > 65536:
        raise schema_invalid("step note options exceed 65536 bytes", field="options")
    raw_urgency: object = note.urgency
    if note.kind is NoteKind.QUESTION:
        if raw_urgency not in (Urgency.NORMAL, Urgency.BLOCKING):
            raise schema_invalid("question note urgency is normal or blocking", field="urgency")
    else:
        if note.options or note.why_blocked is not None:
            raise schema_invalid("options and why_blocked belong only to question notes", field="kind")
        if raw_urgency not in (None, Urgency.NORMAL):
            raise schema_invalid("urgency belongs only to question notes", field="urgency")


def work_policies_document(policies: Mapping[str, EffectiveWorkPolicy] | None) -> JsonObject | None:
    """Key-sorted JSON of resolved work policies, bounded to ``WORK_POLICIES_MAX_BYTES``."""
    if policies is None:
        return None
    doc: JsonObject = {k: work_policy_to_json(v) for k, v in sorted(policies.items())}
    if len(canonical_bytes(doc)) > WORK_POLICIES_MAX_BYTES:
        raise schema_invalid("work_policies exceeds 16777216 canonical bytes", field="work_policies")
    return doc


def config_snapshot_document(bundle: ExecutionBundle) -> JsonValue:
    """The bundle config snapshot as JSON, bounded to ``CONFIG_SNAPSHOT_MAX_BYTES``."""
    doc = thaw_json(bundle.config_snapshot)
    if len(canonical_bytes(doc)) > CONFIG_SNAPSHOT_MAX_BYTES:
        raise schema_invalid("config_snapshot exceeds 1048576 canonical bytes", field="config_snapshot")
    return doc


def validate_readiness_report(
    report: ReadinessReport, *, require_valid: SchemaCheck
) -> tuple[JsonObject | None, JsonObject | None]:
    """Size-check and schema-validate a readiness report; return its start request and work policies."""
    wp_doc = work_policies_document(report.work_policies)
    sr_doc = None if report.start_request is None else cast("JsonObject", thaw_json(report.start_request))
    if sr_doc is not None and len(canonical_bytes(sr_doc)) > CONFIG_SNAPSHOT_MAX_BYTES:
        raise schema_invalid("start_request exceeds 1048576 canonical bytes", field="start_request")
    scope_kind = "phase" if report.scope.kind == "phases" else report.scope.kind
    doc: JsonObject = {
        "schema": READINESS_REPORT_URN,
        "id": str(report.id),
        "workspace_id": str(report.workspace_id),
        "project_id": str(report.project_id),
        "plan_id": str(report.plan_id),
        "revision_id": str(report.revision_id),
        "revision_digest": report.revision_digest,
        "status": report.status.value,
        "scope": {"kind": scope_kind, "phase_keys": list(report.scope.phase_keys)},
        "inputs": {
            "requirements": report.inputs.requirements,
            "dependencies": report.inputs.dependencies,
            "write_scopes": report.inputs.write_scopes,
            "criteria": report.inputs.criteria,
            "capability_requirements": report.inputs.capability_requirements,
            "policy": report.inputs.policy,
            "config": report.inputs.config,
            "resources": report.inputs.resources,
            "materials": report.inputs.materials,
        },
        "inputs_digest": report.inputs_digest,
        "policy_digest": report.policy_digest,
        "results": [
            {"rule_id": r.rule_id, "outcome": r.outcome, "findings_count": r.findings_count}
            for r in report.results
        ],
        "findings": [
            {
                "code": f.code,
                "severity": f.severity,
                "entity_id": None if f.entity_id is None else str(f.entity_id),
                "message": f.message,
                "rule_id": f.rule_id,
            }
            for f in report.findings
        ],
        "assumptions": list(report.assumptions),
        "structural_counts": {str(k): int(v) for k, v in report.structural_counts.items()},
        "start_request": sr_doc,
        "work_policies": wp_doc,
        "estimate": cast("JsonObject", thaw_json(report.estimate)),
        "audit": None if report.audit is None else cast("JsonObject", thaw_json(report.audit)),
        "supersedes_report_id": (
            None if report.supersedes_report_id is None else str(report.supersedes_report_id)
        ),
        "validator_version": report.validator_version,
        "created_by": str(report.created_by),
        "created_at": report.created_at.isoformat(),
    }
    require_valid(READINESS_REPORT_URN, doc)
    return sr_doc, wp_doc


def check_binding_role(owner_kind: str, role: str) -> None:
    """``SCHEMA_INVALID`` unless ``role`` may be bound to an ``owner_kind`` owner."""
    allowed = EVIDENCE_BINDING_ROLES.get(owner_kind)
    if allowed is None or role not in allowed:
        raise schema_invalid(f"role {role!r} is not valid for {owner_kind} bindings", field="role")
