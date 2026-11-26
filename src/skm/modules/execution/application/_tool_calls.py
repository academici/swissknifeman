"""Journal provider-observed calls and book only newly inserted rows under the run lock."""

from dataclasses import replace
from decimal import Decimal
from typing import Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._live_control import request_stop
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._worker_protocol import FencedContext
from skm.modules.execution.application.commands.expire_leases import monitor
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension, limit_from_config
from skm.modules.execution.domain.live_control import (
    IncidentGate,
    ObservedCoverage,
    ToolCall,
    ToolCallObservation,
    crossed_percent,
)
from skm.modules.execution.domain.run import RunStatus, pause
from skm.modules.execution.domain.stage_record import StageRecord
from skm.modules.execution.domain.step import AttemptStep
from skm.modules.execution.ports import BudgetRepository, RunRepository, StepRepository


def record_calls(
    uow: UnitOfWork, ctx: Any, fenced: FencedContext, stage: StageRecord, step: AttemptStep, batch: Any
) -> bool:
    """Return whether this batch requested cancellation. The caller holds the current fence."""
    if batch["coverage"] == "unavailable" or not batch["calls"]:
        return False
    if stage.runtime_started_at is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "tool observations require a started runtime")
    coverage = cast("ObservedCoverage", batch["coverage"])
    journal = uow.repo(StepRepository)
    inserted = journal.add_tool_calls(
        [
            ToolCallObservation(
                step.id,
                ToolCall(call["call_id"], call.get("tool"), call["duration_ms"]),
                coverage,
                fenced.claim.fencing_token,
                fenced.now,
            )
            for call in batch["calls"]
        ]
    )
    if not inserted:
        return False
    budget = uow.repo(BudgetRepository)
    accounts = budget.accounts_for(fenced.run.id, fenced.task.id, BudgetDimension.TOOL_CALLS)
    if not any(account.scope == "run" for account in accounts):
        # A legacy run may predate the ledger. The run lock serializes account creation and charging.
        _, frozen = effective_values(uow, fenced.run.id)
        limit = limit_from_config(
            str(frozen.get("budgets.run.max_tool_calls", 0)), BudgetDimension.TOOL_CALLS
        )
        account = BudgetAccount(
            ctx.ids.new_id(),
            fenced.run.id,
            "run",
            None,
            BudgetDimension.TOOL_CALLS,
            limit,
            Decimal(0),
            Decimal(0),
            1,
        )
        budget.add_accounts((account,))
        accounts = (account, *accounts)
    budget.record_spend([account.id for account in accounts], Decimal(inserted))
    trip = False
    for account in accounts:
        key = f"budgets.{account.scope}.max_tool_calls"
        live = limit_from_config(str(value(ctx.config, key, 0) or 0), BudgetDimension.TOOL_CALLS)
        limits = [limit for limit in (account.limit_value, live) if limit is not None]
        if not limits:
            continue
        limit = min(limits)
        spent = account.spent + inserted
        trip |= spent >= limit
        for percent in crossed_percent(replace(account, limit_value=limit), spent):
            monitor(
                uow,
                ctx,
                fenced.run,
                name="timeout_enforcer",
                rule=f"tool_calls_{account.scope}_{percent}",
                stage=stage,
                thresholds={"percent": percent, "spent": int(spent), "limit": int(limit)},
                verdict="action_required" if percent == 100 else "suspected",
                action="pause" if percent == 100 else "none",
                reason="BUDGET_EXHAUSTED" if percent == 100 else "TOOL_CALLS_BUDGET_WARNING",
            )
    return trip and _trip(uow, ctx, fenced, stage, step)


def _trip(uow: UnitOfWork, ctx: Any, fenced: FencedContext, stage: StageRecord, step: AttemptStep) -> bool:
    code = "BUDGET_EXHAUSTED"
    requested = request_stop(uow, ctx, stage, fenced.assignment, fenced.lease, fenced.now, code=code)
    run = fenced.run
    if not requested and run.status not in {RunStatus.RUNNING, RunStatus.WAITING}:
        return True
    uow.repo(StepRepository).add_incident_gate(
        IncidentGate(
            ctx.ids.new_id(),
            fenced.task.id,
            step.id,
            fenced.claim.fencing_token,
            "budget_breaker",
            ctx.actor.principal_id,
            code,
            {"dimension": BudgetDimension.TOOL_CALLS.value},
            fenced.now,
        )
    )
    if run.status in {RunStatus.RUNNING, RunStatus.WAITING}:
        updated = pause(run, reason=code, source="system", stop_code=code)
        uow.repo(RunRepository).save(updated, expected_version=run.row_version)
        emit(
            uow,
            run,
            "run-paused",
            {"reason": code, "by": str(ctx.actor.principal_id), "pause_source": "system", "stop_code": code},
            cause("wait_changed", codes=[code]),
        )
        fenced.run = updated
    return True
