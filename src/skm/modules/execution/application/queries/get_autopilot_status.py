"""Read the campaign and its approved queue through public planning and fresh readiness."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import SkmError
from skm.kernel.ids import PlanId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.execution.application._start_inputs import prepare_inputs, value
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application.commands.start_autopilot import load_state, policy_for, project_scope
from skm.modules.execution.domain.readiness import canonical_start_request, changed_inputs
from skm.modules.execution.ports import ExecutionQueries, ReadinessRepository, RunRepository
from skm.modules.planning import public as planning
from skm.platform.config import ConfigLoader, ConfigStore, PackConfigSource, ScopeTree


class GetAutopilotStatus(WireRecord):
    SCHEMA_URN = "urn:skm:execution:query:get-autopilot-status:v1"


class AutopilotStatusView(WireRecord):
    SCHEMA_URN = "urn:skm:execution:view:get-autopilot-status:v1"


def scoped_context(uow: UnitOfWork, ctx: Any, scope: ScopeRef) -> Any:
    """Resolve the plan's own settings in this UoW; project configuration is not its snapshot."""
    config = ConfigLoader(ctx.config.registry, uow.repo(PackConfigSource)).effective(
        uow.repo(ConfigStore),
        uow.repo(ScopeTree),
        scope,
    )
    return replace(ctx, scope=scope, scope_chain=uow.repo(ScopeRegistry).ancestors(scope.id), config=config)


def resolve_plan(uow: UnitOfWork, project_id: Any, ref: str) -> Any:
    try:
        plan = planning.get_plan_ref(uow, PlanId(UUID(ref.removeprefix("plan:"))))
    except ValueError:
        # The public facade has no alias resolver. Enumerate only scopes belonging to this project,
        # then ask the owner for its primary and retained aliases; no foreign repository imports.
        after = None
        plan = None
        while True:
            scopes = uow.repo(ScopeRegistry).list_scopes(after=after, limit=500)
            for item in scopes:
                if item.kind is ScopeKind.PLAN and item.parent_id == project_id:
                    candidate = planning.get_plan_ref(uow, PlanId(item.id))
                    summary = planning.get_plan_summary(uow, candidate.plan_id)
                    if candidate.alias == ref or any(alias.alias == ref for alias in summary.aliases):
                        plan = candidate
                        break
            if plan is not None or len(scopes) < 500:
                break
            after = scopes[-1].id
    if plan is None or plan.project_id != project_id:
        return None
    return plan


def approved_queue(uow: UnitOfWork, ctx: Any, project_id: Any, *, lock: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for ref in policy_for(ctx).queue:
        row: dict[str, Any] = {"ref": ref, "status": "not_ready"}
        try:
            plan = resolve_plan(uow, project_id, ref)
            if plan is None:
                rows.append({"ref": ref, "status": "not_ready", "error_code": "NOT_FOUND"})
                continue
            if plan.purpose.value == "review_requests" or plan.plan_id in seen:
                continue
            seen.add(plan.plan_id)
            if lock and plan.lifecycle.value == "active":
                plan = planning.require_active_plan(uow, plan.plan_id)
            row = {
                "ref": ref,
                "plan_id": str(plan.plan_id),
                "alias": plan.alias,
                "revision_id": None if plan.current_revision_id is None else str(plan.current_revision_id),
                "status": "not_ready",
                "lifecycle": plan.lifecycle.value,
            }
            rows.append(row)
            if plan.lifecycle.value != "active":
                row["status"] = "archived"
                continue
            if plan.current_revision_id is None:
                continue
            latest = uow.repo(ExecutionQueries).latest_run_id(
                project_id,
                plan.plan_id,
                revision_id=plan.current_revision_id,
            )
            if latest is not None and uow.repo(RunRepository).get(latest).status.value == "succeeded":
                row["status"] = "complete"
                continue
            report = uow.repo(ReadinessRepository).latest_for(plan.current_revision_id)
            if report is None:
                continue
            plan_ctx = scoped_context(uow, ctx, ScopeRef(ScopeKind.PLAN, ScopeId(plan.plan_id)))
            current = prepare_inputs(
                uow, plan_ctx, plan.plan_id, plan.current_revision_id, {}, None, read_only=True
            )
            stale = (
                report.start_request != canonical_start_request({}, None)
                or bool(changed_inputs(report, current.inputs))
                or (ctx.clock.now() - report.created_at).total_seconds()
                > value(plan_ctx.config, "execution.readiness.max_age_seconds", 3600)
            )
            row.update(status="stale" if stale else report.status.value, report_id=str(report.id))
        except SkmError as error:
            if error.code.value not in {
                "NOT_FOUND",
                "PLAN_ARCHIVED",
                "PROJECT_ARCHIVED",
                "READINESS_REQUIRED",
                "CONFIG_INVALID",
            }:
                raise
            row.update(
                status="archived" if error.code.value == "PLAN_ARCHIVED" else "stale",
                error_code=error.code.value,
            )
            if row not in rows:
                rows.append(row)
    return rows


def handle(query: GetAutopilotStatus, ctx: Any, uow: UnitOfWork) -> AutopilotStatusView:
    state = load_state(query, ctx, uow)
    policy = policy_for(ctx)
    return AutopilotStatusView(
        effective_state=state.state.value if policy.allowed and policy.enabled else "disabled",
        state=state.state.value,
        emergency=state.emergency,
        current_run_id=None if state.current_run_id is None else str(state.current_run_id),
        queue=approved_queue(uow, ctx, state.project_id),
        counters=dict(state.counters),
        stop_code=state.stop_code,
        stop_detail=state.stop_detail,
        session_started_at=None if state.session_started_at is None else state.session_started_at.isoformat(),
    )


SPEC = QuerySpec(
    name="execution.get_autopilot_status",
    dto=GetAutopilotStatus,
    result=AutopilotStatusView,
    permission="run.read",
    scope_of=project_scope,
    handler=handle,
)
