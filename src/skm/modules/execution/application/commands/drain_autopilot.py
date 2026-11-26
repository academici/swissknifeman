"""Drain existing runs before returning the campaign to idle."""

from dataclasses import replace
from typing import Any

from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application.commands.start_autopilot import (
    load_state,
    policy_for,
    project_scope,
    require_release_authority,
    save_state,
    status_result,
)
from skm.modules.execution.domain.autopilot import AutopilotStateKind


class DrainAutopilot(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:drain-autopilot:v1"


class DrainAutopilotResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:drain-autopilot:v1"


def handle(cmd: DrainAutopilot, ctx: Any, uow: UnitOfWork) -> DrainAutopilotResult:
    state = load_state(cmd, ctx, uow, lock=True)
    if state.state not in {
        AutopilotStateKind.RUNNING,
        AutopilotStateKind.PAUSED,
        AutopilotStateKind.DRAINING,
    }:
        raise error_for(ErrorCode.INVALID_TRANSITION, "only running or paused autopilot can drain")
    require_release_authority(state, ctx)
    counters = {k: v for k, v in state.counters.items() if k != "hold_authority"}
    updated = save_state(
        uow,
        ctx,
        state,
        replace(state, state=AutopilotStateKind.DRAINING, counters=counters),
        reason=cmd["reason"],
    )
    return DrainAutopilotResult(status_result(updated, policy_for(ctx)))


SPEC = CommandSpec(
    name="execution.drain_autopilot",
    dto=DrainAutopilot,
    result=DrainAutopilotResult,
    permission="run.control",
    scope_of=project_scope,
    handler=handle,
)
