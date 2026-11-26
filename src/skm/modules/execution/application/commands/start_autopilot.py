"""Persisted autopilot sessions and shared command boundaries (execution §4.21, §7.1)."""

from dataclasses import fields, replace
from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.application._events import cause, event_class
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.domain.autopilot import (
    OWNER_CODES,
    AutopilotPolicy,
    AutopilotState,
    AutopilotStateKind,
    start_session,
)
from skm.modules.execution.ports import AutopilotRepository, ExecutionQueries, RunRepository
from skm.modules.workspace.public import require_active_project, workspace_of_project


class StartAutopilot(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:start-autopilot:v1"


class StartAutopilotResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:start-autopilot:v1"


def project_scope(cmd: Any) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cmd["project_id"])))


def policy_for(ctx: Any) -> AutopilotPolicy:
    default = AutopilotPolicy()
    return AutopilotPolicy(
        **{
            f.name: value(ctx.config, "execution.autopilot." + f.name, getattr(default, f.name))
            for f in fields(default)
        }
    )


def load_state(cmd: Any, ctx: Any, uow: UnitOfWork, *, lock: bool = False) -> AutopilotState:
    pid = ProjectId(UUID(cmd["project_id"]))
    # Autopilot ownership always precedes any run lock, including the first row insertion.
    repo = uow.repo(AutopilotRepository)
    state = repo.get(pid, for_update=lock)
    if state is None:
        state = AutopilotState(
            pid,
            workspace_of_project(uow, pid),
            AutopilotStateKind.IDLE,
            False,
            None,
            None,
            {},
            {},
            None,
            None,
            ctx.actor.principal_id,
            uow.repo(RunRepository).now(),
            1,
        )
        if lock:
            repo.save(state, expected_version=None)
    return state


def status_result(state: AutopilotState, policy: AutopilotPolicy, cancelled: Any = ()) -> dict[str, Any]:
    result: dict[str, Any] = {
        "project_id": str(state.project_id),
        "state": state.state.value,
        "effective_state": state.state.value if policy.allowed and policy.enabled else "disabled",
        "emergency": state.emergency,
        "cancelled_run_ids": [str(i) for i in cancelled],
    }
    if state.current_run_id is not None:
        result["current_run_id"] = str(state.current_run_id)
    if state.stop_code is not None:
        result["stop_code"] = state.stop_code
    return result


def save_state(
    uow: UnitOfWork,
    ctx: Any,
    old: AutopilotState,
    new: AutopilotState,
    *,
    reason: str = "",
    session_reset: bool = False,
    code: str | None = None,
) -> AutopilotState:
    if new == old:
        return old
    updated = replace(
        new,
        updated_by=ctx.actor.principal_id,
        updated_at=uow.repo(RunRepository).now(),
        row_version=old.row_version + 1,
    )
    uow.repo(AutopilotRepository).save(updated, expected_version=old.row_version)
    if (old.state, old.current_run_id, old.emergency) != (
        new.state,
        new.current_run_id,
        new.emergency,
    ) or session_reset:
        data: JsonObject = {
            "workspace_id": str(new.workspace_id),
            "project_id": str(new.project_id),
            "from": old.state.value,
            "to": new.state.value,
            "emergency": new.emergency,
            "by": str(ctx.actor.principal_id),
            "session_reset": session_reset,
            "previous_code": old.stop_code,
            "code": code or new.stop_code,
            "run_id": None if new.current_run_id is None else str(new.current_run_id),
            "reason": reason,
            "cause": cause("operator_resume" if session_reset else "wait_changed"),
        }
        if session_reset:
            data["previous_counters"] = {k: v for k, v in old.counters.items() if k != "hold_authority"}
        uow.record(
            event_class("urn:skm:execution:event:autopilot-state-changed:v1")(
                new.project_id,
                new.workspace_id,
                data,
            )
        )
    return updated


def owner_hold(state: AutopilotState) -> bool:
    manual = state.state is AutopilotStateKind.PAUSED or state.stop_code == "AUTOPILOT_STOPPED"
    # Manual holds from older campaigns have no authority marker.
    return (
        state.emergency
        or state.stop_code in OWNER_CODES
        or state.counters.get("hold_authority") == "owner"
        or (manual and state.counters.get("hold_authority") != "coordinator")
    )


def hold_authority(state: AutopilotState, ctx: Any) -> JsonObject:
    counters = dict(state.counters)
    if ctx.actor.kind is PrincipalKind.HUMAN or owner_hold(state):
        counters["hold_authority"] = "owner"
    else:
        counters["hold_authority"] = "coordinator"
    return counters


def require_release_authority(state: AutopilotState, ctx: Any) -> None:
    if ctx.actor.kind is not PrincipalKind.HUMAN and owner_hold(state):
        raise error_for(ErrorCode.FORBIDDEN, "an owner must release the campaign hold")


def handle(cmd: StartAutopilot, ctx: Any, uow: UnitOfWork) -> StartAutopilotResult:
    state = load_state(cmd, ctx, uow, lock=True)
    require_active_project(uow, state.project_id)
    require_release_authority(state, ctx)
    policy = policy_for(ctx)
    updated, reset = start_session(
        state,
        policy,
        uow.repo(RunRepository).now(),
        new_session=cmd.get("new_session", False),
        reason=cmd["reason"],
        clear_emergency=cmd.get("clear_emergency", False),
        limits=cmd.get("limits"),
    )
    if "hold_authority" in updated.counters:
        updated = replace(
            updated, counters={k: v for k, v in updated.counters.items() if k != "hold_authority"}
        )
    if reset and state.current_run_id is not None:
        run = uow.repo(RunRepository).get(state.current_run_id, for_update=True)
        counters = {
            **updated.counters,
            "event_run_id": str(run.id),
            "event_seq": uow.repo(ExecutionQueries).head_run_seq(run.id),
        }
        if run.status.value in {"succeeded", "failed", "cancelled"}:
            counters["completed_run_id"] = str(run.id)
        updated = replace(updated, counters=counters)
    updated = save_state(uow, ctx, state, updated, reason=cmd["reason"], session_reset=reset)
    return StartAutopilotResult(status_result(updated, policy))


SPEC = CommandSpec(
    name="execution.start_autopilot",
    dto=StartAutopilot,
    result=StartAutopilotResult,
    permission="run.control",
    scope_of=project_scope,
    handler=handle,
    permissions_of=lambda cmd: ("deviation.accept",) if cmd.get("clear_emergency") else (),
)
