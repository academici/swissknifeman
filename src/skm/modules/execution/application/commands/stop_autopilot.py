"""Stop a campaign; emergency cancellation shares the caller's transaction."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec
from skm.kernel.ids import RunId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._json_reads import objects, optional_text, text
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application.commands import cancel_run
from skm.modules.execution.application.commands.start_autopilot import (
    hold_authority,
    load_state,
    policy_for,
    project_scope,
    save_state,
    status_result,
)
from skm.modules.execution.domain.autopilot import AutopilotStateKind
from skm.modules.execution.generated.commands import CancelRun
from skm.modules.execution.ports import ExecutionQueries, RunRepository


class StopAutopilot(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:stop-autopilot:v1"


class StopAutopilotResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:stop-autopilot:v1"


def project_runs(uow: UnitOfWork, project_id: Any) -> list[Any]:
    """Page the project inventory, including terminal history; never silently truncate it."""
    result: list[Any] = []
    after = None
    while True:
        page = uow.repo(ExecutionQueries).runs_page(project_id, after, 200, frozenset())
        result.extend(
            uow.repo(RunRepository).get(RunId(UUID(text(item["run_id"], "items.run_id"))))
            for item in objects(page.get("items"), "items")
        )
        after = optional_text(page.get("next_after"), "next_after")
        if after is None:
            return result


def handle(cmd: StopAutopilot, ctx: Any, uow: UnitOfWork) -> StopAutopilotResult:
    state = load_state(cmd, ctx, uow, lock=True)
    emergency = state.emergency or cmd.get("emergency", False)
    updated = save_state(
        uow,
        ctx,
        state,
        replace(
            state,
            state=AutopilotStateKind.STOPPED,
            emergency=emergency,
            counters=hold_authority(state, ctx),
            stop_code="AUTOPILOT_STOPPED",
            stop_detail=cmd["reason"][:2000],
        ),
        reason=cmd["reason"],
    )
    cancelled: list[Any] = []
    if emergency:
        for run in sorted(project_runs(uow, state.project_id), key=lambda r: str(r.id)):
            if run.status.value not in {"succeeded", "failed", "cancelled"}:
                cancel_run.handle(CancelRun(run.id, cmd["reason"]), ctx, uow)
                cancelled.append(run.id)
    return StopAutopilotResult(status_result(updated, policy_for(ctx), cancelled))


SPEC = CommandSpec(
    name="execution.stop_autopilot",
    dto=StopAutopilot,
    result=StopAutopilotResult,
    permission="run.control",
    scope_of=project_scope,
    handler=handle,
)
