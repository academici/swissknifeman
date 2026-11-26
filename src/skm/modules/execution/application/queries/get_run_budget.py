"""``execution.get_run_budget`` query handler (execution §8)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import NotFound
from skm.kernel.ids import RunId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.execution.application._primitives import attempts_for_run
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.domain.budget import BudgetDimension, usage_charge, warn_exceeded
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.generated.queries import GetRunBudget
from skm.modules.execution.generated.views import RunBudgetView
from skm.modules.execution.ports import ExecutionQueries, RunRepository, StageRepository, StepRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _token_usage(uow: UnitOfWork, run_id: RunId) -> tuple[dict[str, Decimal], set[str]]:
    measured: dict[str, Decimal] = defaultdict(Decimal)
    unknown: set[str] = set()
    stages, steps = uow.repo(StageRepository), uow.repo(StepRepository)
    for attempt in attempts_for_run(uow, run_id):
        task_id = str(attempt.task_id)
        for entry in stages.history(attempt.id).entries:
            for step in steps.for_stage(entry.record.id):
                if step.state is StepState.STARTED:
                    unknown.add(task_id)
                    continue
                report = usage_charge(step.usage, BudgetDimension.TOKENS)
                if report.exposure != "finalized" or report.actual is None:
                    unknown.add(task_id)
                else:
                    measured[task_id] += report.actual
    return measured, unknown


def handle(query: GetRunBudget, _ctx: QueryContext, uow: UnitOfWork) -> RunBudgetView:
    run_id = RunId(query.run_id)
    uow.repo(RunRepository).get(run_id)
    view = dict(uow.repo(ExecutionQueries).budget_view(run_id))
    try:
        _, frozen = effective_values(uow, run_id)
    except NotFound:
        return RunBudgetView.from_json(view)
    threshold = frozen.get("budgets.task.warn_tokens")
    if type(threshold) is not int:
        return RunBudgetView.from_json(view)
    measured, unknown = _token_usage(uow, run_id)
    accounts = view.get("accounts")
    if isinstance(accounts, list):
        for account in accounts:
            if not isinstance(account, dict) or account.get("dimension") != "tokens":
                continue
            task_id = account.get("task_id")
            if not isinstance(task_id, str):
                continue
            account["warn_tokens"] = threshold
            actual = measured.get(task_id, Decimal(0))
            account["actual_tokens"] = None if task_id in unknown else str(actual)
            if warn_exceeded(actual, threshold):
                account["soft_overrun"] = {
                    "measured_tokens": str(actual),
                    "expected_tokens": threshold,
                    "partial": task_id in unknown,
                }
    return RunBudgetView.from_json(view)


SPEC = QuerySpec(
    name="execution.get_run_budget",
    dto=GetRunBudget,
    result=RunBudgetView,
    permission="run.read",
    scope_of=lambda q: ScopeRef(ScopeKind.RUN, ScopeId(q.run_id)),
    handler=handle,
)
