"""Application loaders for frozen bundles, overlays, work policies, and read facades (execution §§6, 13)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.public import get_manifest
from skm.modules.execution.domain.budget import BudgetDimension, limit_from_config
from skm.modules.execution.domain.contracts import EvidenceOwnerKind
from skm.modules.execution.domain.execution_bundle import (
    DEFAULT_POLICY_KEY,
    ExecutionBundle,
    Reconfiguration,
    effective_value,
)
from skm.modules.execution.domain.output import manifest_to_json
from skm.modules.execution.domain.task import Task, TaskKind, TaskOrigin, TaskStatus
from skm.modules.execution.domain.task_graph import EdgeKind
from skm.modules.execution.domain.work_policy import (
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
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    BudgetRepository,
    BundleRepository,
    CheckRepository,
    EvidenceBindingRepository,
    ExecutionQueries,
    OutputRepository,
    ReconfigurationRecord,
    ReviewRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.modules.planning.public import get_plan_ref, get_revision_meta

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, PlanId, ProjectId, RevisionId, RunId, TaskId
    from skm.kernel.ports_uow import UnitOfWork

__all__ = [
    "LoadedBundleConfig",
    "build_attempt_activity",
    "build_attempt_summary",
    "build_latest_run_outcome",
    "build_run_report_data",
    "build_run_summary",
    "build_task_attempts_for_learning",
    "derive_synthetic_task_work_policy",
    "find_default_work_policy",
    "find_task_work_policy",
    "load_effective_bundle",
    "require_default_work_policy",
    "require_task_work_policy",
]

_BUDGET_KEY_MAP: Final[tuple[tuple[Literal["run", "task"], BudgetDimension, str], ...]] = (
    ("run", BudgetDimension.USD, "budgets.run.max_usd"),
    ("run", BudgetDimension.TOKENS, "budgets.run.max_tokens"),
    ("run", BudgetDimension.WALL_SECONDS, "budgets.run.max_wall_seconds"),
    ("run", BudgetDimension.TOOL_CALLS, "budgets.run.max_tool_calls"),
    ("task", BudgetDimension.USD, "budgets.task.max_usd"),
    ("task", BudgetDimension.TOKENS, "budgets.task.max_tokens"),
    ("task", BudgetDimension.ATTEMPTS, "budgets.task.max_attempts"),
    ("task", BudgetDimension.REVIEW_ROUNDS, "budgets.task.max_review_rounds"),
    ("task", BudgetDimension.TOOL_CALLS, "budgets.task.max_tool_calls"),
)


def _s(val: object) -> str | None:
    return None if val is None else str(val)


def _iso(val: Any) -> str | None:
    return None if val is None else str(val.isoformat())


def _wp_err(msg: str, **details: JsonValue) -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.READINESS_REQUIRED, msg, details={"reason": "work_policy_missing", **details}
    )


@dataclass(frozen=True, slots=True)
class LoadedBundleConfig:
    """Frozen bundle reconstructed with ordered ``RunReconfigured`` overlays (execution §4.2, §7)."""

    bundle: ExecutionBundle
    effective_snapshot: JsonObject
    effective_config_digest: str
    reconfiguration_ids: tuple[UUID, ...]
    reconfigurations: tuple[Reconfiguration, ...]
    budget_limits: Mapping[tuple[Literal["run", "task"], BudgetDimension], Decimal | None]


def _canonical_digest(doc: JsonObject) -> str:
    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _get_dotted(snapshot: Mapping[str, JsonValue], dotted_key: str) -> JsonValue:
    if dotted_key in snapshot:
        return snapshot[dotted_key]
    cur: object = snapshot
    for part in dotted_key.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cast("JsonValue", cur)


def _set_dotted(snapshot: dict[str, JsonValue], dotted_key: str, val: JsonValue) -> None:
    if dotted_key in snapshot or "." not in dotted_key:
        snapshot[dotted_key] = deepcopy(val)
        return
    parts = dotted_key.split(".")
    cur: dict[str, Any] = cast("dict[str, Any]", snapshot)
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            cur[part] = nxt = {}
        cur = cast("dict[str, Any]", nxt)
    cur[parts[-1]] = deepcopy(val)


def _ordered_reconfigurations(
    uow: UnitOfWork, run_id: RunId, records: Sequence[ReconfigurationRecord]
) -> tuple[tuple[ReconfigurationRecord, int], ...]:
    if not records:
        return ()
    by_id = {rec.id: rec for rec in records}
    ordered: list[tuple[ReconfigurationRecord, int]] = []
    seen: set[UUID] = set()
    for idx, rec_id in enumerate(uow.repo(ExecutionQueries).run_reconfiguration_order(run_id), start=1):
        if rec_id in by_id and rec_id not in seen:
            ordered.append((by_id[rec_id], idx))
            seen.add(rec_id)
    for rec in sorted(records, key=lambda r: (r.changed_at, str(r.id))):
        if rec.id not in seen:
            ordered.append((rec, len(ordered) + 1))
    return tuple(ordered)


def _normalize_changes(raw_changes: Mapping[str, JsonValue]) -> JsonObject:
    out: dict[str, JsonValue] = {}
    for key, val in raw_changes.items():
        if isinstance(val, Mapping) and set(val.keys()) == {"old", "new"}:
            out[key] = cast("JsonValue", val["new"])
        else:
            out[key] = val
    return out


def load_effective_bundle(uow: UnitOfWork, run_id: RunId) -> LoadedBundleConfig:
    """Reconstruct effective policy and budget limits from frozen bundle + ``RunReconfigured`` overlays."""
    bundle_repo = uow.repo(BundleRepository)
    bundle = bundle_repo.get(run_id)
    ordered_pairs = _ordered_reconfigurations(uow, run_id, bundle_repo.reconfigurations(run_id))
    overlays = tuple(
        Reconfiguration(stream_seq=seq, changes=_normalize_changes(rec.changes)) for rec, seq in ordered_pairs
    )
    effective_snap: dict[str, JsonValue] = deepcopy(dict(bundle.config_snapshot))
    winning_rec_by_key: dict[str, tuple[int, UUID]] = {}
    all_changed_keys: list[str] = []
    for rec, seq in ordered_pairs:
        for key in rec.changes:
            if key not in all_changed_keys:
                all_changed_keys.append(key)
            winning_rec_by_key[key] = (seq, rec.id)
    for key in all_changed_keys:
        base_val = _get_dotted(bundle.config_snapshot, key)
        _set_dotted(effective_snap, key, effective_value(base_val, key, overlays))
    sorted_wins = sorted(winning_rec_by_key.values(), key=lambda p: p[0])
    winning_ids = tuple(dict.fromkeys(rid for _, rid in sorted_wins))
    budget_limits: dict[tuple[Literal["run", "task"], BudgetDimension], Decimal | None] = {}
    for scope, dim, key in _BUDGET_KEY_MAP:
        raw_val = _get_dotted(effective_snap, key)
        is_num = isinstance(raw_val, int | float | str | Decimal) and not isinstance(raw_val, bool)
        budget_limits[(scope, dim)] = limit_from_config(str(raw_val), dim) if is_num else None
    eff_digest = bundle.config_digest if not ordered_pairs else _canonical_digest(effective_snap)
    return LoadedBundleConfig(
        bundle, effective_snap, eff_digest, winning_ids, overlays, MappingProxyType(budget_limits)
    )


def _frozen_warn_settings(bundle: ExecutionBundle) -> WorkPolicySettings:
    raw_roles = (
        dpol.effective.get("role_intensity")
        if (dpol := (bundle.work_policies or {}).get(DEFAULT_POLICY_KEY))
        else None
    )
    eff_roles = (
        cast("Mapping[str, JsonValue]", raw_roles)
        if isinstance(raw_roles, Mapping)
        else dict[str, JsonValue]()
    )
    role_int = {role: Intensity(str(eff_roles.get(role, "medium"))) for role in ROLE_NAMES}
    ver_raw = dpol.effective.get("verification_intensity", "medium") if dpol else "medium"
    snap = bundle.config_snapshot
    raw_rw = _get_dotted(snap, "execution.work_policy.role_warn_seconds")
    role_warn: dict[str, Mapping[Intensity, int]] = dict(DEFAULT_ROLE_WARN_SECONDS)
    if isinstance(raw_rw, Mapping):
        for role in ROLE_NAMES:
            r_map = raw_rw.get(role)
            if isinstance(r_map, Mapping) and all(lvl.value in r_map for lvl in Intensity):
                role_warn[role] = {lvl: int(cast("int", r_map[lvl.value])) for lvl in Intensity}
    raw_rep = _get_dotted(snap, "execution.work_policy.repro_warn_seconds")
    repro_warn: Mapping[Intensity, int] = DEFAULT_REPRO_WARN_SECONDS
    if isinstance(raw_rep, Mapping) and all(lvl.value in raw_rep for lvl in Intensity):
        repro_warn = {lvl: int(cast("int", raw_rep[lvl.value])) for lvl in Intensity}
    return WorkPolicySettings(role_int, Intensity(str(ver_raw)), role_warn, repro_warn)


def _lookup_task_policy(
    task: Task, policies: Mapping[str, EffectiveWorkPolicy]
) -> EffectiveWorkPolicy | None:
    return policies.get(task.display_key) or policies.get(str(task.id))


def find_default_work_policy(uow: UnitOfWork, run_id: RunId) -> EffectiveWorkPolicy | None:
    bundle = uow.repo(BundleRepository).get(run_id)
    return None if bundle.work_policies is None else bundle.work_policies.get(DEFAULT_POLICY_KEY)


def require_default_work_policy(uow: UnitOfWork, run_id: RunId) -> EffectiveWorkPolicy:
    found = find_default_work_policy(uow, run_id)
    if found is None:
        raise _wp_err("run bundle has no frozen work_policies; live defaults never apply", run_id=str(run_id))
    return found


def derive_synthetic_task_work_policy(
    uow: UnitOfWork,
    run_id: RunId,
    *,
    kind: TaskKind,
    origin: TaskOrigin | None = None,
    group_member_ids: Sequence[TaskId] = (),
) -> EffectiveWorkPolicy:
    """Derive deterministic work policy for a synthetic task strictly from frozen bundle facts."""
    bundle = uow.repo(BundleRepository).get(run_id)
    if bundle.work_policies is None:
        raise _wp_err("run bundle has no frozen work_policies", run_id=str(run_id), kind=kind.value)
    policies = dict(bundle.work_policies)
    task_repo = uow.repo(TaskRepository)
    if kind is TaskKind.GROUP_REVIEW:
        members_map: dict[str, EffectiveWorkPolicy] = {}
        for mid in group_member_ids:
            mtask = task_repo.get(mid)
            if mtask.run_id != run_id:
                raise PreconditionFailed(
                    ErrorCode.INVALID_REFERENCE,
                    "group review member belongs to another run",
                    details={"run_id": str(run_id), "member_task_id": str(mid)},
                )
            mpol = _lookup_task_policy(mtask, policies) or derive_synthetic_task_work_policy(
                uow, run_id, kind=mtask.kind, origin=mtask.origin
            )
            members_map[mtask.display_key] = mpol
        return derive_group_policy(members_map, _frozen_warn_settings(bundle))
    source_key: str | None = None
    if origin is not None and origin.source_task_id is not None:
        try:
            src_task = task_repo.get(origin.source_task_id)
        except NotFound:
            src_task = None
        if (
            src_task is not None
            and src_task.run_id == run_id
            and (sp := _lookup_task_policy(src_task, policies))
        ):
            source_key = src_task.display_key
            policies[source_key] = sp
    return synthetic_work_policy(kind.value, source_key=source_key, policies=policies)


def find_task_work_policy(uow: UnitOfWork, task_id: TaskId) -> EffectiveWorkPolicy | None:
    task_repo = uow.repo(TaskRepository)
    task = task_repo.get(task_id)
    bundle = uow.repo(BundleRepository).get(task.run_id)
    if bundle.work_policies is None:
        return None
    if (direct := _lookup_task_policy(task, bundle.work_policies)) is not None:
        return direct
    if task.kind is TaskKind.GROUP_REVIEW:
        mids = [
            e.prerequisite_task_id
            for e in task_repo.edges_for_run(task.run_id)
            if e.dependent_task_id == task.id and e.kind is EdgeKind.GATE_MEMBER
        ]
        if not mids:
            return None
        return derive_synthetic_task_work_policy(
            uow, task.run_id, kind=task.kind, origin=task.origin, group_member_ids=mids
        )
    if task.kind in {TaskKind.INTEGRATION, TaskKind.FOLLOWUP, TaskKind.PLAN_ACCEPTANCE, TaskKind.PLAN_AUDIT}:
        return derive_synthetic_task_work_policy(uow, task.run_id, kind=task.kind, origin=task.origin)
    return None


def require_task_work_policy(uow: UnitOfWork, task_id: TaskId) -> EffectiveWorkPolicy:
    found = find_task_work_policy(uow, task_id)
    if found is None:
        raise _wp_err("task has no frozen work_policy; live defaults never apply", task_id=str(task_id))
    return found


def build_run_summary(uow: UnitOfWork, run_id: RunId) -> JsonObject:
    run = uow.repo(RunRepository).get(run_id)
    tasks = uow.repo(TaskRepository).list_for_run(run_id)
    default_wp = find_default_work_policy(uow, run_id)
    return {
        "run_id": str(run.id),
        "project_id": str(run.project_id),
        "kind": run.kind.value,
        "plan_id": str(run.plan_id) if run.plan_id is not None else None,
        "plan_alias": get_plan_ref(uow, run.plan_id).alias if run.plan_id is not None else "",
        "revision_id": str(run.revision_id) if run.revision_id is not None else None,
        "revision_no": run.revision_no,
        "status": run.status.value,
        "stop_code": run.stop_code,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "tasks_total": len(tasks),
        "tasks_accepted": sum(1 for t in tasks if t.status is TaskStatus.ACCEPTED),
        "work_policy_default": None if default_wp is None else work_policy_to_json(default_wp),
    }


def build_attempt_summary(uow: UnitOfWork, attempt_id: AttemptId) -> JsonObject:
    attempt = uow.repo(AttemptRepository).get(attempt_id)
    latest_out = uow.repo(OutputRepository).latest(attempt_id)
    return {
        "attempt_id": str(attempt.id),
        "run_id": str(attempt.run_id),
        "task_id": str(attempt.task_id),
        "attempt_no": attempt.attempt_no,
        "state": attempt.state.value,
        "worker_id": _s(attempt.worker_id),
        "host_id": _s(attempt.host_id),
        "current_output_id": _s(attempt.current_output_id),
        "latest_tree_digest": None if latest_out is None else latest_out.manifest.tree_digest,
        "started_at": attempt.started_at.isoformat(),
        "finished_at": _iso(attempt.finished_at),
        "end_reason": attempt.end_reason,
    }


def _task_report_item(uow: UnitOfWork, t: Task) -> JsonObject:
    output_repo, ev_repo = uow.repo(OutputRepository), uow.repo(EvidenceBindingRepository)
    t_wp = find_task_work_policy(uow, t.id)
    acc_out = output_repo.get(t.accepted_output_id) if t.accepted_output_id is not None else None
    checks_src = uow.repo(CheckRepository).for_output(acc_out.id) if acc_out is not None else ()

    def _ev_ids(kind: EvidenceOwnerKind, oid: object) -> list[JsonValue]:
        return [str(f) for f, _ in ev_repo.for_owner(kind, UUID(str(oid)))]

    checks_j: list[JsonValue] = [
        cast(
            "JsonValue",
            {
                "check_execution_id": str(c.id),
                "check_key": c.check_key,
                "state": c.state.value,
                "evidence_file_version_ids": _ev_ids("check_execution", c.id),
            },
        )
        for c in checks_src
    ]
    reviews_j: list[JsonValue] = [
        cast(
            "JsonValue",
            {
                "review_id": str(r.id),
                "output_id": str(r.output_id),
                "round_no": r.round_no,
                "state": r.state.value,
                "verdict": None if r.verdict is None else r.verdict.value,
                "evidence_file_version_ids": _ev_ids("review", r.id),
            },
        )
        for r in uow.repo(ReviewRepository).for_task(t.id)
    ]
    decisions_j: list[JsonValue] = [
        {
            "acceptance_decision_id": str(d.id),
            "decision": d.decision,
            "output_id": _s(d.output_id),
            "decided_at": d.decided_at.isoformat(),
        }
        for d in uow.repo(AcceptanceRepository).decisions_for_task(t.id)
    ]
    return {
        "task_id": str(t.id),
        "display_key": t.display_key,
        "kind": t.kind.value,
        "status": t.status.value,
        "accepted_attempt_id": _s(t.accepted_attempt_id),
        "accepted_output_id": _s(t.accepted_output_id),
        "accepted_output_manifest": None if acc_out is None else manifest_to_json(acc_out.manifest),
        "attempts_count": len(uow.repo(AttemptRepository).list_for_task(t.id)),
        "checks": checks_j,
        "reviews": reviews_j,
        "acceptance_decisions": decisions_j,
        "work_policy": None if t_wp is None else work_policy_to_json(t_wp),
    }


def build_run_report_data(uow: UnitOfWork, run_id: RunId) -> JsonObject:
    """Assemble ``RunReportData`` (§13) without host IO in caller's UoW."""
    run = uow.repo(RunRepository).get(run_id)
    eff_b = load_effective_bundle(uow, run_id)
    tasks = uow.repo(TaskRepository).list_for_run(run_id)
    budget_repo = uow.repo(BudgetRepository)
    usd_accts = budget_repo.accounts_for(run_id, None, BudgetDimension.USD)
    tok_accts = budget_repo.accounts_for(run_id, None, BudgetDimension.TOKENS)
    raw_items = uow.repo(ExecutionQueries).timeline(run_id, None, 200).get("items", ())
    timeline_items = [dict(cast("Mapping[str, JsonValue]", it)) for it in cast("Sequence[Any]", raw_items)]
    default_wp = find_default_work_policy(uow, run_id)
    return {
        "run_id": str(run.id),
        "project_id": str(run.project_id),
        "plan_id": str(run.plan_id) if run.plan_id is not None else None,
        "plan_alias": get_plan_ref(uow, run.plan_id).alias if run.plan_id is not None else "",
        "revision_id": str(run.revision_id) if run.revision_id is not None else None,
        "revision_no": run.revision_no,
        "revision_digest": get_revision_meta(uow, run.revision_id).digest
        if run.revision_id is not None
        else None,
        "status": run.status.value,
        "stop_code": run.stop_code,
        "bundle": {
            "config_digest": eff_b.bundle.config_digest,
            "effective_config_digest": eff_b.effective_config_digest,
            "policy_digest": eff_b.bundle.policy_digest,
            "reconfiguration_ids": [str(rid) for rid in eff_b.reconfiguration_ids],
            "work_policy_default": None if default_wp is None else work_policy_to_json(default_wp),
        },
        "tasks": [_task_report_item(uow, t) for t in tasks],
        "usage": {
            "cost_usd_micros": int(usd_accts[0].spent) if usd_accts else 0,
            "tokens_spent": int(tok_accts[0].spent) if tok_accts else 0,
            "unmetered": run.unmetered_at is not None,
        },
        "timeline": cast("list[JsonValue]", timeline_items),
    }


def build_latest_run_outcome(
    uow: UnitOfWork,
    project_id: ProjectId,
    plan_id: PlanId | None = None,
    *,
    revision_id: RevisionId | None = None,
) -> JsonObject | None:
    """Implement ``latest_run_outcome`` (§13, ench3): exact project/plan/revision filter, no service plans."""
    latest_id = uow.repo(ExecutionQueries).latest_run_id(project_id, plan_id, revision_id=revision_id)
    if latest_id is None:
        return None
    run = uow.repo(RunRepository).get(latest_id)
    items: dict[str, JsonValue] = {}
    counts: dict[str, int] = {}
    for t in uow.repo(TaskRepository).list_for_run(run.id):
        st = t.status.value
        counts[st] = counts.get(st, 0) + 1
        if t.kind in {TaskKind.ITEM, TaskKind.UNIT}:
            items[t.display_key] = st
    return {
        "run_id": str(run.id),
        "project_id": str(run.project_id),
        "plan_id": str(run.plan_id) if run.plan_id is not None else None,
        "revision_id": str(run.revision_id) if run.revision_id is not None else None,
        "revision_no": run.revision_no,
        "status": run.status.value,
        "items": items,
        "counts": cast("JsonObject", counts),
    }


def _scan_manifest_exposure(
    uow: UnitOfWork, manifest_id: Any, lesson_map: dict[tuple[str, str, str], JsonObject]
) -> bool:
    try:
        manifest = get_manifest(uow, manifest_id)
    except NotFound:
        return False
    if manifest.state.value != "final":
        return False
    ok = True
    for blk in manifest.blocks:
        if blk.included is not True:
            continue
        if blk.block_type.value == "memory":
            if blk.source_version is None or blk.content_digest is None:
                ok = False
            else:
                key = (blk.source_ref, blk.source_version, blk.content_digest)
                lesson_map[key] = {"id": key[0], "version": key[1], "content_digest": key[2]}
        elif (
            blk.block_type.value in {"review_feedback", "history", "context_map", "research"}
            and not blk.source_ref
        ):
            ok = False
    return ok


def build_attempt_activity(uow: UnitOfWork, attempt_id: AttemptId) -> JsonObject:
    """Build ``AttemptActivityView`` (§13): step activity, usage, and server-verified lesson exposure."""
    attempt = uow.repo(AttemptRepository).get(attempt_id)
    task = uow.repo(TaskRepository).get(attempt.task_id)
    steps = [step for entry in uow.repo(StageRepository).history(attempt_id).entries for step in entry.steps]
    latest_out = uow.repo(OutputRepository).latest(attempt_id)
    activities: list[JsonValue] = []
    any_activity_unknown = usage_unknown = has_any_usage = False
    totals = [0, 0, 0]
    lesson_map: dict[tuple[str, str, str], JsonObject] = {}
    exposure_coverage: Literal["complete", "unknown"] = "complete" if steps else "unknown"

    for s in steps:
        if s.activity is None:
            any_activity_unknown = True
        else:
            activities.append({str(k): v for k, v in s.activity.items()})
        u = s.usage
        if u is None or str(u.status) not in {"reported", "complete"}:
            usage_unknown = True
        elif u.cost_usd_micros is None or u.input_tokens is None or u.output_tokens is None:
            has_any_usage = usage_unknown = True
        else:
            has_any_usage = True
            totals[0] += u.cost_usd_micros
            totals[1] += u.input_tokens
            totals[2] += u.output_tokens
        if s.session_mode == "resume" or not _scan_manifest_exposure(uow, s.context_manifest_id, lesson_map):
            exposure_coverage = "unknown"

    is_accepted = task.status is TaskStatus.ACCEPTED and task.accepted_attempt_id == attempt.id
    usage_summary: JsonObject | None = (
        None
        if (usage_unknown or not has_any_usage)
        else {
            "status": "reported",
            "input_tokens": totals[1],
            "output_tokens": totals[2],
            "cost_usd_micros": totals[0],
        }
    )
    cpaths = [cp.path for cp in latest_out.manifest.changed_paths] if latest_out else []
    return {
        "attempt_id": str(attempt.id),
        "run_id": str(attempt.run_id),
        "task_id": str(attempt.task_id),
        "attempt_no": attempt.attempt_no,
        "state": attempt.state.value,
        "outcome": "SUCCESS" if is_accepted else attempt.state.value.upper(),
        "accepted": is_accepted,
        "source_step_ids": cast("list[JsonValue]", [str(s.id) for s in steps]),
        "activities": None if (any_activity_unknown and not activities) else activities,
        "activity_complete": bool(steps) and not any_activity_unknown,
        "usage": usage_summary,
        "changed_paths": cast("list[JsonValue]", cpaths),
        "result_codes": [s.error_code for s in steps if s.error_code is not None],
        "exposed_lesson_refs": [lesson_map[k] for k in sorted(lesson_map)],
        "exposure_coverage": exposure_coverage,
    }


def load_check_executions(uow: UnitOfWork, attempt_id: AttemptId) -> tuple[JsonObject, ...]:
    checks = cast("list[JsonObject]", dict(uow.repo(ExecutionQueries).attempt_view(attempt_id))["checks"])
    return tuple(
        {"check_key": str(row["check_key"]), "state": str(row["state"])}
        for row in sorted(checks, key=lambda row: cast("int", row["round_no"]))
    )


def build_task_attempts_for_learning(uow: UnitOfWork, task_id: TaskId) -> tuple[JsonObject, ...]:
    """List empirical attempt activity views of ``task_id``; carry-forward without attempt yields ``()``."""
    uow.repo(TaskRepository).get(task_id)
    attempts = uow.repo(AttemptRepository).list_for_task(task_id)
    return tuple(build_attempt_activity(uow, attempt.id) for attempt in attempts)
