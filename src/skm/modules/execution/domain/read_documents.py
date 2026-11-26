"""Read documents of execution query views, shared by every ``ExecutionQueries`` backend (execution §6.2, §8).

Backends only load the records; the documents are built here so the memory and PostgreSQL read models
cannot drift apart in shape or in how work policies are resolved.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue

from .blocking_reason import blocking_reason_to_json
from .execution_bundle import DEFAULT_POLICY_KEY, ExecutionBundle
from .frozen_json import thaw_json
from .output import Output, manifest_to_json
from .stage_record import CONTROL_PLANE_STAGE_TYPES, StageRecord
from .task import Task, TaskKind
from .task_graph import EdgeKind, TaskEdge
from .work_policy import (
    DEFAULT_REPRO_WARN_SECONDS,
    DEFAULT_ROLE_WARN_SECONDS,
    ROLE_NAMES,
    EffectiveWorkPolicy,
    Intensity,
    WorkPolicySettings,
    derive_group_policy,
    synthetic_work_policy,
    work_policy_to_json,
)

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, TaskId

    from .attempt import Attempt
    from .budget import BudgetAccount
    from .check_execution import CheckExecution
    from .environment import ExecutionEnvironment
    from .external_effect import ExternalEffect
    from .finding import Finding
    from .recovery import RecoveryRecord
    from .review import Review
    from .step import AttemptStep

__all__ = [
    "AttemptDetailParts",
    "build_attempt_detail_doc",
    "build_attempt_summary_doc",
    "build_budget_view_doc",
    "build_step_view_doc",
    "build_task_doc",
    "event_short_code",
    "iso",
    "parse_time_id_cursor",
    "resolve_task_work_policy",
    "timeline_kind",
]

_STAGE_EVENT_SUFFIXES: Final = ("stage-started:", "stage-completed:")
_STEP_EVENT_SUFFIXES: Final = ("step-started:", "step-completed:")


@dataclass(frozen=True, slots=True)
class AttemptDetailParts:
    env: ExecutionEnvironment | None
    stages: Sequence[StageRecord]
    steps: Sequence[AttemptStep]
    outs: Sequence[Output]
    checks: Sequence[CheckExecution]
    revs: Sequence[Review]
    fnds: Sequence[Finding]
    effs: Sequence[ExternalEffect]
    recs: Sequence[RecoveryRecord]


def _malformed_cursor() -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID, "malformed pagination cursor", details={"field": "after"}
    )


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat()


def parse_time_id_cursor(after: str | None) -> tuple[datetime, str] | None:
    if after is None:
        return None
    dt_part, sep, id_part = after.partition("|")
    if not sep or not dt_part or not id_part:
        raise _malformed_cursor()
    try:
        parsed_dt = datetime.fromisoformat(dt_part)
        parsed_id = str(UUID(id_part))
    except ValueError:
        raise _malformed_cursor() from None
    return parsed_dt, parsed_id


def timeline_kind(event_type: str) -> str:
    if "stage-recovered:" in event_type:
        return "recovery"
    if any(sfx in event_type for sfx in _STAGE_EVENT_SUFFIXES):
        return "stage"
    if any(sfx in event_type for sfx in _STEP_EVENT_SUFFIXES):
        return "step"
    if "diagnostic" in event_type:
        return "diagnostic"
    return "event"


def event_short_code(event_type: str) -> str:
    parts = event_type.split(":")
    return parts[4] if len(parts) >= 5 else event_type


def _warn_settings(bundle: ExecutionBundle) -> WorkPolicySettings:
    default_pol = (bundle.work_policies or {}).get(DEFAULT_POLICY_KEY)
    eff_roles: Mapping[str, Any] = (
        cast("Mapping[str, Any]", default_pol.effective.get("role_intensity", {}))
        if default_pol is not None
        else {}
    )
    role_int = {role: Intensity(str(eff_roles.get(role, "medium"))) for role in ROLE_NAMES}
    ver_int = Intensity(
        str(default_pol.effective.get("verification_intensity", "medium")) if default_pol else "medium"
    )
    return WorkPolicySettings(role_int, ver_int, dict(DEFAULT_ROLE_WARN_SECONDS), DEFAULT_REPRO_WARN_SECONDS)


def resolve_task_work_policy(
    task: Task,
    bundle: ExecutionBundle | None,
    tasks_by_id: Mapping[TaskId, Task],
    edges: Sequence[TaskEdge],
) -> EffectiveWorkPolicy | None:
    if bundle is None or bundle.work_policies is None:
        return None
    policies = dict(bundle.work_policies)
    direct = policies.get(task.display_key) or policies.get(str(task.id))
    if direct is not None:
        return direct
    if task.kind is TaskKind.GROUP_REVIEW:
        member_ids = [
            e.prerequisite_task_id
            for e in edges
            if e.dependent_task_id == task.id and e.kind is EdgeKind.GATE_MEMBER
        ]
        members_map: dict[str, EffectiveWorkPolicy] = {}
        for mid in sorted(member_ids, key=str):
            mt = tasks_by_id.get(mid)
            if mt is not None:
                mp = policies.get(mt.display_key) or policies.get(str(mt.id))
                if mp is not None:
                    members_map[mt.display_key] = mp
        return derive_group_policy(members_map, _warn_settings(bundle)) if members_map else None
    if task.kind in {TaskKind.INTEGRATION, TaskKind.FOLLOWUP, TaskKind.PLAN_ACCEPTANCE, TaskKind.PLAN_AUDIT}:
        src_key: str | None = None
        if task.origin is not None and task.origin.source_task_id is not None:
            src = tasks_by_id.get(task.origin.source_task_id)
            if src is not None and src.run_id == task.run_id:
                sp = policies.get(src.display_key) or policies.get(str(src.id))
                if sp is not None:
                    src_key = src.display_key
                    policies[src_key] = sp
        try:
            return synthetic_work_policy(task.kind.value, source_key=src_key, policies=policies)
        except (ValueError, KeyError, TypeError):
            return None
    return None


def build_attempt_summary_doc(att: Attempt, outs: Sequence[Output]) -> JsonObject:
    return {
        "attempt_id": str(att.id),
        "attempt_no": att.attempt_no,
        "state": att.state.value,
        "worker_id": None if att.worker_id is None else str(att.worker_id),
        "host_id": None if att.host_id is None else str(att.host_id),
        "started_at": iso(att.started_at),
        "finished_at": iso(att.finished_at),
        "end_reason": att.end_reason,
        "outputs": [
            {
                "output_id": str(o.id),
                "seq": o.seq,
                "source": o.source.value,
                "manifest_digest": o.manifest_digest,
                "sealed_at": o.sealed_at.isoformat(),
            }
            for o in outs
        ],
    }


def build_task_doc(
    task: Task,
    *,
    bundle: ExecutionBundle | None,
    tasks_by_id: Mapping[TaskId, Task],
    edges: Sequence[TaskEdge],
    attempts: Sequence[Attempt],
    outputs_by_attempt: Mapping[AttemptId, Sequence[Output]],
    summary_only: bool,
) -> JsonObject:
    wp = resolve_task_work_policy(task, bundle, tasks_by_id, edges)
    if summary_only:
        return {
            "task_id": str(task.id),
            "display_key": task.display_key,
            "kind": task.kind.value,
            "status": task.status.value,
            "blocking_reason": (
                None if task.blocking_reason is None else blocking_reason_to_json(task.blocking_reason)
            ),
            "review_mode": task.review_mode.value,
            "review_profile": task.review_profile,
            "work_policy": None
            if wp is None
            else {"effective": thaw_json(wp.effective), "digest": wp.digest},
            "work_policy_digest": None if wp is None else wp.digest,
            "accepted_output_id": None if task.accepted_output_id is None else str(task.accepted_output_id),
            "check_fix_rounds": task.check_fix_rounds,
            "review_rounds": task.review_rounds,
            "row_version": task.row_version,
        }
    gate_members = sorted(
        str(e.prerequisite_task_id)
        for e in edges
        if e.dependent_task_id == task.id and e.kind is EdgeKind.GATE_MEMBER
    )
    followups = sorted(
        str(t.id)
        for t in tasks_by_id.values()
        if t.kind is TaskKind.FOLLOWUP and t.origin is not None and t.origin.source_task_id == task.id
    )
    return {
        "task_id": str(task.id),
        "display_key": task.display_key,
        "kind": task.kind.value,
        "status": task.status.value,
        "blocking_reason": (
            None if task.blocking_reason is None else blocking_reason_to_json(task.blocking_reason)
        ),
        "review_mode": task.review_mode.value,
        "review_profile": task.review_profile,
        "work_policy": None if wp is None else work_policy_to_json(wp),
        "attempts": [build_attempt_summary_doc(a, outputs_by_attempt.get(a.id, ())) for a in attempts],
        "accepted_output_id": None if task.accepted_output_id is None else str(task.accepted_output_id),
        "check_fix_rounds": task.check_fix_rounds,
        "review_rounds": task.review_rounds,
        "gate_members": cast("list[JsonValue]", gate_members),
        "followups": cast("list[JsonValue]", followups),
        "row_version": task.row_version,
    }


def build_attempt_detail_doc(att: Attempt, parts: AttemptDetailParts) -> JsonObject:
    env_doc: JsonObject | None = (
        None
        if parts.env is None
        else {
            "environment_id": str(parts.env.id),
            "kind": parts.env.kind.value,
            "state": parts.env.state.value,
            "branch": parts.env.branch,
            "local_locator": parts.env.local_locator,
        }
    )
    return {
        "attempt_id": str(att.id),
        "attempt_no": att.attempt_no,
        "state": att.state.value,
        "worker_id": None if att.worker_id is None else str(att.worker_id),
        "host_id": None if att.host_id is None else str(att.host_id),
        "started_at": iso(att.started_at),
        "finished_at": iso(att.finished_at),
        "end_reason": att.end_reason,
        "stages": [
            {
                "stage_record_id": str(s.id),
                "seq": s.seq,
                "stage_id": s.stage_id,
                "stage_type": s.stage_type,
                "side": "control_plane" if s.stage_type in CONTROL_PLANE_STAGE_TYPES else "host",
                "round_no": s.round_no,
                "state": s.state.value,
                "started_at": s.started_at.isoformat(),
                "finished_at": iso(s.finished_at),
                "environment": env_doc,
            }
            for s in parts.stages
        ],
        "steps": [
            {
                "step_id": str(s.id),
                "stage_record_id": str(s.stage_record_id),
                "role": s.role.value,
                "purpose": s.purpose.value,
                "runtime_id": s.runtime_id,
                "model": s.model,
                "state": s.state.value,
                "started_at": s.started_at.isoformat(),
                "finished_at": iso(s.finished_at),
            }
            for s in parts.steps
        ],
        "outputs": [
            {
                "output_id": str(o.id),
                "seq": o.seq,
                "source": o.source.value,
                "manifest": manifest_to_json(o.manifest),
                "manifest_digest": o.manifest_digest,
                "sealed_at": o.sealed_at.isoformat(),
            }
            for o in parts.outs
        ],
        "checks": [
            {
                "check_execution_id": str(c.id),
                "output_id": str(c.output_id),
                "check_spec_id": str(c.check_spec_id),
                "check_key": c.check_key,
                "kind": c.kind.value,
                "state": c.state.value,
                "summary": c.summary,
                "round_no": c.round_no,
                "exit_code": c.exit_code,
                "finished_at": iso(c.finished_at),
            }
            for c in parts.checks
        ],
        "reviews": [
            {
                "review_id": str(r.id),
                "output_id": str(r.output_id),
                "round_no": r.round_no,
                "profile_key": r.profile_key,
                "state": r.state.value,
                "verdict": None if r.verdict is None else r.verdict.value,
                "residual_risk": r.residual_risk,
            }
            for r in parts.revs
        ],
        "findings": [
            {
                "finding_id": str(f.id),
                "review_id": str(f.review_id),
                "finding_key": f.finding_key,
                "first_seen_review_id": str(f.first_seen_review_id),
                "severity": f.severity.value,
                "category": f.category,
                "message": f.message,
                "state": f.state.value,
            }
            for f in parts.fnds
        ],
        "effects": [
            {
                "effect_id": str(e.id),
                "kind": e.kind.value,
                "state": e.state.value,
                "request_digest": e.request_digest,
            }
            for e in parts.effs
        ],
        "recoveries": [
            {
                "recovery_id": str(r.id),
                "trigger": r.trigger,
                "outcome": r.outcome,
                "at": r.at.isoformat(),
            }
            for r in parts.recs
        ],
    }


def build_step_view_doc(step: AttemptStep, usage: JsonObject | None) -> JsonObject:
    """The step view document; ``usage`` is the step usage already rendered by the runtimes codec."""
    doc: JsonObject = {
        "step_id": str(step.id),
        "role": step.role.value,
        "purpose": step.purpose.value,
        "parent_step_id": None if step.parent_step_id is None else str(step.parent_step_id),
        "runtime_id": step.runtime_id,
        "model": step.model,
        "route_reason": step.route_reason,
        "session_mode": step.session_mode,
        "fresh_reason": step.fresh_reason,
        "session_fingerprint_digest": step.session_fingerprint_digest,
        "state": step.state.value,
        "usage": usage,
        "repairs": list[JsonValue](step.repairs),
        "schema_errors": [thaw_json(e) for e in step.schema_errors],
        "route_snapshot": None if step.route_snapshot is None else thaw_json(step.route_snapshot),
        "runtime_observation": (
            None if step.runtime_observation is None else thaw_json(step.runtime_observation)
        ),
        "context_manifest_id": str(step.context_manifest_id),
        "transcript_file_version_id": (
            None if step.transcript_file_version_id is None else str(step.transcript_file_version_id)
        ),
        "raw_result_file_version_id": (
            None if step.raw_result_file_version_id is None else str(step.raw_result_file_version_id)
        ),
        "payload_visibility": "available",
    }
    if step.result is not None:
        doc["result"] = thaw_json(step.result)
    return doc


def build_budget_view_doc(accounts: Sequence[BudgetAccount], unknown_usage_steps: int) -> JsonObject:
    """The run budget view: every account with its remaining headroom, plus steps of unknown usage."""
    return {
        "accounts": [
            {
                "account_id": str(a.id),
                "scope": a.scope,
                "task_id": None if a.task_id is None else str(a.task_id),
                "dimension": a.dimension.value,
                "limit": None if a.limit_value is None else str(a.limit_value),
                "spent": str(a.spent),
                "reserved": str(a.reserved),
                "remaining": None if a.limit_value is None else str(a.limit_value - a.spent - a.reserved),
            }
            for a in accounts
        ],
        "unknown_usage_steps": unknown_usage_steps,
    }
