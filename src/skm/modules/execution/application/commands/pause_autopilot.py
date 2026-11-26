"""Pause dispatch; existing runs retain their execution authority."""

from dataclasses import replace
from typing import Any

from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._incident_gate import schedule_boundary
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application.commands.start_autopilot import (
    hold_authority,
    load_state,
    policy_for,
    project_scope,
    save_state,
    status_result,
)
from skm.modules.execution.domain.autopilot import AutopilotStateKind


class PauseAutopilot(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:pause-autopilot:v1"


class PauseAutopilotResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:pause-autopilot:v1"


def handle(cmd: PauseAutopilot, ctx: Any, uow: UnitOfWork) -> PauseAutopilotResult:
    state = load_state(cmd, ctx, uow, lock=True)
    if state.state not in {AutopilotStateKind.RUNNING, AutopilotStateKind.PAUSED}:
        raise error_for(ErrorCode.INVALID_TRANSITION, "only running autopilot can pause")
    if cmd.get("stop_after"):
        schedule_boundary(uow, ctx, state, cmd["stop_after"], cmd["reason"])
    updated = save_state(
        uow,
        ctx,
        state,
        replace(state, state=AutopilotStateKind.PAUSED, counters=hold_authority(state, ctx)),
        reason=cmd["reason"],
    )
    return PauseAutopilotResult(status_result(updated, policy_for(ctx)))


SPEC = CommandSpec(
    name="execution.pause_autopilot",
    dto=PauseAutopilot,
    result=PauseAutopilotResult,
    permission="run.control",
    scope_of=project_scope,
    handler=handle,
)
