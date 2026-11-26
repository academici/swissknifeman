"""Unit-of-work primitives shared by the action table, gates, commands and worker results.

Persisting attempts and task transitions, listing attempts of a run, the server clock of background commands,
initial budget accounts and the cached schema registry. Nothing here dispatches an action, so every caller can
import it at module level without closing an import cycle."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from functools import cache
from typing import Any, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import AttemptId, RunId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import save_task
from skm.modules.execution.application._json_reads import objects, text
from skm.modules.execution.domain import task as task_rules
from skm.modules.execution.domain.attempt import (
    Attempt,
    settle_advance,
)
from skm.modules.execution.domain.budget import (
    BudgetAccount,
    BudgetDimension,
    limit_from_config,
)
from skm.modules.execution.domain.ids import ExternalEffectId
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import (
    AttemptRepository,
    ExecutionQueries,
    RunRepository,
)
from skm.platform.schema.registry import SchemaRegistry


def save_attempt(uow: UnitOfWork, attempt: Any) -> None:
    repo = uow.repo(AttemptRepository)
    repo.save(attempt, expected_version=repo.version(attempt.id))


def clear_advance(uow: UnitOfWork, attempt: Any) -> None:
    if attempt.continuation is not None and attempt.continuation.kind == "advance":
        save_attempt(uow, settle_advance(attempt))


def move(
    uow: UnitOfWork, ctx: Any, run: Any, task: Any, status: Any, why: Any, *, blocking: Any = None
) -> Any:
    if task.status is status:
        updated = replace(task, blocking_reason=blocking, row_version=task.row_version + 1)
    else:
        rules = task_rules.task_rules(task.status, status)
        if not rules and status in {TaskStatus.INTEGRATING, TaskStatus.CHECKING, TaskStatus.REVIEWING}:
            if task.status is TaskStatus.AWAITING_DECISION:
                task = move(uow, ctx, run, task, TaskStatus.EXECUTING, why)
            if task.status is TaskStatus.ASSIGNED:
                task = move(uow, ctx, run, task, TaskStatus.EXECUTING, why)
            if task.status is TaskStatus.EXECUTING and status is not TaskStatus.EXECUTING:
                task = move(uow, ctx, run, task, TaskStatus.CHECKING, why)
            rules = task_rules.task_rules(task.status, status)
        if not rules:
            raise error_for(ErrorCode.INVALID_TRANSITION, "action does not match task transition table")
        updated = task_rules.transition(task, status, rule=rules[0].rule_id, blocking=blocking)
    save_task(uow, run, task, updated, why, ctx.clock.now())
    return updated


def attempts_for_run(uow: UnitOfWork, run_id: RunId) -> tuple[Attempt, ...]:
    return uow.repo(AttemptRepository).list_for_run(run_id)


class _ServerClock:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def now(self) -> Any:
        return self._uow.repo(RunRepository).now()


def server_context(ctx: Any, uow: UnitOfWork) -> Any:
    return replace(ctx, clock=_ServerClock(uow))


def budget_accounts(
    ctx: Any, run_id: Any, task_ids: Any, values: Any, *, include_run: bool = False
) -> list[BudgetAccount]:
    accounts: list[BudgetAccount] = []
    for scope, dimensions in BUDGET_DIMENSIONS.items():
        targets = (None,) if scope == "run" and include_run else () if scope == "run" else task_ids
        for task_id in targets:
            accounts.extend(
                BudgetAccount(
                    ctx.ids.new_id(),
                    run_id,
                    cast("Any", scope),
                    task_id,
                    dimension,
                    limit_from_config(str(values[f"budgets.{scope}.max_{dimension.value}"]), dimension),
                    Decimal(0),
                    Decimal(0),
                    1,
                )
                for dimension in dimensions
            )
    return accounts


@cache
def schemas() -> Any:
    return SchemaRegistry.load_default()


BUDGET_DIMENSIONS = {
    "run": tuple(BudgetDimension),
    "task": (
        BudgetDimension.USD,
        BudgetDimension.TOKENS,
        BudgetDimension.ATTEMPTS,
        BudgetDimension.WALL_SECONDS,
    ),
}


def attempt_effect_ids(uow: UnitOfWork, attempt_id: AttemptId) -> list[ExternalEffectId]:
    """External effects the attempt view lists for an attempt, in view order."""
    view = uow.repo(ExecutionQueries).attempt_view(attempt_id)
    return [
        ExternalEffectId(UUID(text(row["effect_id"], "effects.effect_id")))
        for row in objects(view.get("effects"), "effects")
    ]
