"""Context assembly request DTOs and pure work-policy snapshot validation (context §5.0)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import PrincipalId, parse_uuid
from skm.kernel.json_types import JsonValue
from skm.modules.context.domain.blocks import canonical_json_digest as jsonc_digest

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from skm.kernel.ids import (
        EntityId,
        FileVersionId,
        PlanId,
        ProjectId,
        ResourceVersionId,
        RevisionId,
        WorkspaceId,
    )
    from skm.kernel.json_types import JsonObject
    from skm.modules.context.domain.contracts import Digest, FindingItem, SelfLoadView
    from skm.modules.context.domain.research import ResearchItem, ResearchQuerySpec

__all__ = [
    "INTENSITY_VALUES",
    "ROLE_NAMES",
    "AnswerItem",
    "CandidateRef",
    "ContextMapItem",
    "ContextRequest",
    "ExecutionBlocks",
    "HistoryItem",
    "PermissionsSummary",
    "PreviousAttemptSummary",
    "ResumeInfo",
    "RunParams",
    "RuntimeTarget",
    "StepPurpose",
    "ValidatedWorkPolicy",
    "format_work_policy_trailer",
    "validate_owner_ref",
    "validate_request_envelope",
    "validate_work_policy",
]

type IntensityValue = Literal["light", "medium", "heavy"]

INTENSITY_VALUES: Final[frozenset[str]] = frozenset(("light", "medium", "heavy"))
ROLE_NAMES: Final[frozenset[str]] = frozenset(
    ("scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar")
)


@dataclass(frozen=True, slots=True)
class StepPurpose:
    role: str
    stage_id: str
    step_ref: str | None
    attempt_no: int
    round_no: int


@dataclass(frozen=True, slots=True)
class RuntimeTarget:
    runtime_id: str
    model: str
    context_window_tokens: int
    capabilities: frozenset[str]
    tools: frozenset[str]
    notes: tuple[str, ...]
    route_source: str
    operation: str
    config_mode: Literal["isolated", "inherit"]
    self_loads: tuple[SelfLoadView, ...]
    degraded: frozenset[str]
    self_loaded_instruction_files: tuple[str, ...]
    forbidden_params: tuple[str, ...] = ()
    legacy_prompt_phrases: tuple[str, ...] = ()
    incompatible_param_groups: tuple[tuple[str, ...], ...] = ()
    parameters: Mapping[str, JsonValue] = field(default_factory=dict[str, JsonValue])


@dataclass(frozen=True, slots=True)
class PermissionsSummary:
    write_scope: tuple[str, ...]
    read_scope: tuple[str, ...]
    commands_allowed: tuple[str, ...]
    commands_denied: tuple[str, ...]
    network: Literal["none", "allowlist", "any"]
    network_allow: tuple[str, ...]
    external_effects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunParams:
    run_id: str
    workflow_key: str
    attempt_no: int
    round_no: int
    integration_branch: str | None
    commit_policy: str
    progress_format: str
    output_language: str
    rules_extra: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionBlocks:
    work_policy: Mapping[str, JsonValue]
    decision_answers: tuple[AnswerItem, ...]
    review_feedback: Mapping[str, JsonValue] | None
    previous_attempt: PreviousAttemptSummary | None
    candidate: CandidateRef | None
    findings_under_review: tuple[FindingItem, ...]
    context_map: ContextMapItem | None
    research: tuple[ResearchItem, ...]
    history: tuple[HistoryItem, ...]
    operator_steering: str | None = None


@dataclass(frozen=True, slots=True)
class ResumeInfo:
    session_ref: str
    previous_task_digest: Digest


@dataclass(frozen=True, slots=True)
class ContextRequest:
    workspace_id: WorkspaceId
    project_id: ProjectId
    plan_id: PlanId | None
    revision_id: RevisionId | None
    entity_id: EntityId | None
    project_slug: str
    purpose: StepPurpose
    agent_profile_version_id: ResourceVersionId
    runtime: RuntimeTarget
    permissions: PermissionsSummary
    run: RunParams
    execution_blocks: ExecutionBlocks
    resume: ResumeInfo | None
    task_risk: Literal["low", "medium", "high"]
    research_queries: tuple[ResearchQuerySpec, ...]
    pack_pins: Mapping[str, UUID] | None


@dataclass(frozen=True, slots=True)
class AnswerItem:
    request_id: str
    question: str
    answer: JsonValue
    answered_by_kind: Literal["owner", "advisor", "consilium"]
    at: datetime


@dataclass(frozen=True, slots=True)
class PreviousAttemptSummary:
    attempt_no: int
    outcome: str
    reason_code: str
    changed_paths: tuple[str, ...]
    note: str
    patch_file_version_id: FileVersionId | None


@dataclass(frozen=True, slots=True)
class CandidateRef:
    output_id: UUID
    manifest_digest: str
    diff_file_version_id: FileVersionId
    changed_paths: tuple[str, ...]
    base_commit: str
    head_commit: str


@dataclass(frozen=True, slots=True)
class ContextMapItem:
    step_ref: str
    text: str
    digest: str


@dataclass(frozen=True, slots=True)
class HistoryItem:
    step_ref: str
    role: str
    outcome: str
    summary: str


@dataclass(frozen=True, slots=True)
class ValidatedWorkPolicy:
    """Validated data-only work policy snapshot for prompt rendering and manifest diagnostics."""

    role: str
    role_intensity: IntensityValue
    verification_intensity: IntensityValue
    warn_seconds: int
    emergency_wall_seconds: int | None
    repro_warn_seconds: int | None
    provenance: tuple[JsonObject, ...]
    clamps: tuple[str, ...]
    soft_warnings: tuple[JsonObject, ...]
    digest: Digest


def _invalid_policy(field: str, message: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        f"invalid work_policy ({field}): {message}",
        details={"field": f"work_policy.{field}"},
    )


def _require_intensity(value: object, field: str) -> IntensityValue:
    if not isinstance(value, str) or value not in INTENSITY_VALUES:
        raise _invalid_policy(field, "must be one of 'light', 'medium', 'heavy'")
    return cast("IntensityValue", value)


def _require_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _invalid_policy(field, "must be a positive integer")
    return value


def _optional_positive_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _require_positive_int(value, field)


def _object_tuple(raw: object, field: str) -> tuple[JsonObject, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise _invalid_policy(field, "must be an array of objects")
    items: list[JsonObject] = []
    for entry in cast("Sequence[object]", raw):
        if not isinstance(entry, Mapping):
            raise _invalid_policy(field, "entries must be JSON objects")
        emap = cast("Mapping[object, JsonValue]", entry)
        items.append({str(k): v for k, v in emap.items()})
    return tuple(items)


def _validate_full_document(raw: Mapping[str, JsonValue], *, role: str) -> ValidatedWorkPolicy:
    effective = raw.get("effective")
    requested = raw.get("requested")
    role_warn = raw.get("role_warn_seconds")
    emergency_map = raw.get("emergency_role_seconds")
    if (
        not isinstance(effective, Mapping)
        or not isinstance(requested, Mapping)
        or not isinstance(role_warn, Mapping)
        or not isinstance(emergency_map, Mapping)
    ):
        raise _invalid_policy("effective", "canonical work_policy requires object maps")
    eff_map = cast("Mapping[str, JsonValue]", effective)
    req_map = cast("Mapping[str, JsonValue]", requested)
    rw_map = cast("Mapping[str, JsonValue]", role_warn)
    em_map = cast("Mapping[str, JsonValue]", emergency_map)
    eff_roles = eff_map.get("role_intensity")
    req_roles = req_map.get("role_intensity")
    if not isinstance(eff_roles, Mapping) or not isinstance(req_roles, Mapping):
        raise _invalid_policy("role_intensity", "role_intensity must be an object")
    eff_roles_map = cast("Mapping[str, JsonValue]", eff_roles)
    req_roles_map = cast("Mapping[str, JsonValue]", req_roles)
    for r_key, r_val in eff_roles_map.items():
        _require_intensity(r_val, f"effective.role_intensity.{r_key}")
    for r_key, r_val in req_roles_map.items():
        _require_intensity(r_val, f"requested.role_intensity.{r_key}")
    role_intensity = _require_intensity(eff_roles_map.get(role), f"effective.role_intensity.{role}")
    verification = _require_intensity(
        eff_map.get("verification_intensity"), "effective.verification_intensity"
    )
    _require_intensity(req_map.get("verification_intensity"), "requested.verification_intensity")
    warn_seconds = _require_positive_int(rw_map.get(role), f"role_warn_seconds.{role}")
    repro_warn = _require_positive_int(raw.get("triage_repro_warn_seconds"), "triage_repro_warn_seconds")
    emergency_seconds = _optional_positive_int(em_map.get(role), f"emergency_role_seconds.{role}")
    provenance = _object_tuple(raw.get("provenance"), "provenance")
    soft_warnings = _object_tuple(raw.get("soft_warnings"), "soft_warnings")
    clamps_raw = raw.get("clamps", ())
    if not isinstance(clamps_raw, Sequence) or isinstance(clamps_raw, str | bytes):
        raise _invalid_policy("clamps", "must be an array of strings")
    clamps = tuple(str(item) for item in cast("Sequence[object]", clamps_raw))
    expected_digest = jsonc_digest(
        {
            "requested": dict(req_map),
            "effective": dict(eff_map),
            "role_warn_seconds": dict(rw_map),
            "triage_repro_warn_seconds": repro_warn,
            "emergency_role_seconds": dict(em_map),
        }
    )
    given_digest = raw.get("digest")
    if given_digest is not None and (not isinstance(given_digest, str) or given_digest != expected_digest):
        raise _invalid_policy("digest", "digest does not match canonical work_policy payload")
    return ValidatedWorkPolicy(
        role=role,
        role_intensity=role_intensity,
        verification_intensity=verification,
        warn_seconds=warn_seconds,
        emergency_wall_seconds=emergency_seconds,
        repro_warn_seconds=repro_warn,
        provenance=provenance,
        clamps=clamps,
        soft_warnings=soft_warnings,
        digest=expected_digest,
    )


def validate_work_policy(raw: Mapping[str, JsonValue] | None, *, role: str) -> ValidatedWorkPolicy:
    """Validate ``ExecutionBlocks.work_policy`` before draft assembly or runtime launch."""
    if role not in ROLE_NAMES:
        raise _invalid_policy("role", f"unknown role {role!r}")
    if not isinstance(raw, Mapping) or not raw:
        raise _invalid_policy("root", "work_policy snapshot is required and cannot be empty")
    if "effective" in raw and "requested" in raw:
        return _validate_full_document(raw, role=role)
    role_intensity = _require_intensity(raw.get("intensity"), "intensity")
    verification_raw = raw.get("verification_intensity", raw.get("verification"))
    verification = _require_intensity(verification_raw, "verification_intensity")
    warn_seconds = _require_positive_int(raw.get("warn_seconds"), "warn_seconds")
    emergency_seconds = _optional_positive_int(raw.get("emergency_wall_seconds"), "emergency_wall_seconds")
    repro_warn = _optional_positive_int(raw.get("triage_repro_warn_seconds"), "triage_repro_warn_seconds")
    provenance = _object_tuple(raw.get("provenance"), "provenance")
    soft_warnings = _object_tuple(raw.get("soft_warnings"), "soft_warnings")
    clamps_raw = raw.get("clamps", ())
    if not isinstance(clamps_raw, Sequence) or isinstance(clamps_raw, str | bytes):
        raise _invalid_policy("clamps", "must be an array of strings")
    clamps = tuple(str(item) for item in cast("Sequence[object]", clamps_raw))
    canonical_payload: JsonObject = {
        "role": role,
        "intensity": role_intensity,
        "verification_intensity": verification,
        "warn_seconds": warn_seconds,
        "emergency_wall_seconds": emergency_seconds,
        "triage_repro_warn_seconds": repro_warn,
    }
    computed = jsonc_digest(canonical_payload)
    given_digest = raw.get("digest")
    if given_digest is not None and (not isinstance(given_digest, str) or given_digest != computed):
        raise _invalid_policy("digest", "digest does not match compact work_policy payload")
    return ValidatedWorkPolicy(
        role=role,
        role_intensity=role_intensity,
        verification_intensity=verification,
        warn_seconds=warn_seconds,
        emergency_wall_seconds=emergency_seconds,
        repro_warn_seconds=repro_warn,
        provenance=provenance,
        clamps=clamps,
        soft_warnings=soft_warnings,
        digest=computed,
    )


def format_work_policy_trailer(policy: ValidatedWorkPolicy) -> str:
    """Deterministic markdown lines capturing provenance, clamps, and active soft warnings."""
    lines: list[str] = []
    if policy.provenance:
        prov_items = [
            f"{entry.get('field', '?')}={entry.get('source', '?')}:{entry.get('ref', '?')}"
            for entry in sorted(
                policy.provenance,
                key=lambda item: (str(item.get("field", "")), str(item.get("ref", ""))),
            )
        ]
        lines.append(f"Policy provenance: {', '.join(prov_items)}.")
    if policy.clamps:
        lines.append(f"Policy clamps: {', '.join(policy.clamps)}.")
    if policy.soft_warnings:
        warn_items = [
            f"{w.get('kind', 'role')}:{w.get('role', policy.role)}"
            f"({w.get('actual_seconds', '?')}s>{w.get('expected_seconds', policy.warn_seconds)}s)"
            for w in policy.soft_warnings
        ]
        lines.append(
            "Observed soft warnings (advisory only; continue useful authorized work): "
            + ", ".join(warn_items)
            + "."
        )
    return "\n".join(lines)


def validate_owner_ref(owner_ref: str, step_ref: str | None) -> PrincipalId | None:
    """Validate the immutable owner and return the principal for a standalone manifest."""
    if step_ref is not None and step_ref and owner_ref == f"step:{step_ref}":
        return None
    if step_ref is None and owner_ref.startswith("standalone:"):
        try:
            principal = PrincipalId(parse_uuid(owner_ref.removeprefix("standalone:")))
        except ValueError:
            pass
        else:
            if owner_ref == f"standalone:{principal}":
                return principal
    raise ValidationFailed(
        ErrorCode.SCHEMA_INVALID, "invalid context manifest owner binding", details={"owner_ref": owner_ref}
    )


def validate_request_envelope(
    req: ContextRequest, owner_ref: str, *, adhoc: bool = False
) -> ValidatedWorkPolicy:
    """Validate ``owner_ref``, step purpose counters, entity requirement, and ``work_policy``."""
    standalone = validate_owner_ref(owner_ref, req.purpose.step_ref) is not None
    if req.purpose.attempt_no < 1 or req.purpose.round_no < 1:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid step purpose counters",
            details={"step_ref": req.purpose.step_ref},
        )
    if adhoc and (standalone or any(x is not None for x in (req.plan_id, req.revision_id, req.entity_id))):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "ad hoc context must be a project-scoped step")
    if not standalone and not adhoc and (req.plan_id is None or req.revision_id is None):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "a step requires a plan and revision")
    if (req.revision_id is not None and req.plan_id is None) or (
        req.entity_id is not None and req.revision_id is None
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "a revision requires a plan and an entity requires a revision"
        )
    if (
        not standalone
        and not adhoc
        and req.entity_id is None
        and not (req.purpose.role == "advisor" and req.purpose.stage_id == "plan_audit")
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "entity_id is required unless role='advisor' and stage_id='plan_audit'",
            details={"role": req.purpose.role, "stage_id": req.purpose.stage_id},
        )
    return validate_work_policy(req.execution_blocks.work_policy, role=req.purpose.role)
