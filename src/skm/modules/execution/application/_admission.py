"""Restrictive future admission guards; never rewrite a saved stage binding."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._control import assignments_for_run, live_guard
from skm.modules.execution.application._primitives import attempts_for_run
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.domain.assignment import AssignmentState
from skm.modules.execution.domain.budget import BudgetDimension, limit_from_config
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES
from skm.modules.execution.ports import (
    BudgetRepository,
    RecoveryRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)


def require_run_admission(uow: UnitOfWork, ctx: Any, run: Any, values: Any) -> None:
    live_guard(uow, ctx, run)
    if run.unmetered_at is not None:
        raise error_for(ErrorCode.BUDGET_EXHAUSTED, "unknown usage requires an owner decision")
    _cost_limits(uow, ctx, run, None, include_reserved=False)
    wall = value(ctx.config, "budgets.run.max_wall_seconds", 0)
    frozen_wall = values.get("budgets.run.max_wall_seconds", 0)
    bounds = [Decimal(str(v)) for v in (wall, frozen_wall) if v and Decimal(str(v)) > 0]
    if bounds and Decimal(
        str(uow.repo(RunRepository).active_seconds(run.id, uow.repo(RunRepository).now()))
    ) >= min(bounds):
        raise error_for(ErrorCode.BUDGET_EXHAUSTED, "run active stage-seconds reached the current ceiling")


def _cost_limits(uow: UnitOfWork, ctx: Any, run: Any, task_id: Any, *, include_reserved: bool) -> None:
    for dim in (
        BudgetDimension.USD,
        BudgetDimension.TOKENS,
        BudgetDimension.TOOL_CALLS,
        BudgetDimension.WALL_SECONDS,
    ):
        for account in uow.repo(BudgetRepository).accounts_for(run.id, task_id, dim):
            key = f"budgets.{account.scope}.max_{dim.value}"
            live = limit_from_config(str(value(ctx.config, key, 0) or 0), dim)
            bounds = [limit for limit in (account.limit_value, live) if limit is not None]
            if bounds and account.spent + (account.reserved if include_reserved else 0) >= min(bounds):
                raise error_for(
                    ErrorCode.BUDGET_EXHAUSTED, "a current live ceiling prevents future admission"
                )


def require_future_admission(uow: UnitOfWork, ctx: Any, run: Any, task: Any, values: Any) -> bool:
    require_run_admission(uow, ctx, run, values)
    _cost_limits(uow, ctx, run, task.id, include_reserved=True)
    live_parallel = value(ctx.config, "execution.parallel.max_units", 2)
    limit = min(live_parallel, values.get("execution.parallel.max_units", live_parallel))
    leased = {a.attempt_id for a in assignments_for_run(uow, run.id) if a.state is AssignmentState.LEASED}
    leased.update(
        t.current_attempt_id
        for t in uow.repo(TaskRepository).list_for_run(run.id)
        if t.blocking_reason and t.blocking_reason.code.value == "RECOVERING"
    )
    for attempt in attempts_for_run(uow, run.id):
        if any(
            e.record.state in ACTIVE_STAGE_STATES
            or uow.repo(RecoveryRepository).open_for_stage(e.record.id) is not None
            for e in uow.repo(StageRepository).history(attempt.id).entries
        ):
            leased.add(attempt.id)
    return task.current_attempt_id in leased or len(leased) < limit
