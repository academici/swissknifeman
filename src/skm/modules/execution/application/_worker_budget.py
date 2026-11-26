"""Budget reservations and K4 closing on worker terminal paths."""

from dataclasses import replace
from decimal import Decimal
from typing import Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application.apply_action import apply_action
from skm.modules.execution.application.loaders import load_effective_bundle
from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.budget import (
    BudgetDimension,
    BudgetExhausted,
    UsageCharge,
    close_reservation,
    reserve,
    usage_charge,
)
from skm.modules.execution.domain.decision_request import DecisionKind
from skm.modules.execution.domain.run import pause
from skm.modules.execution.domain.workflow.actions import ActionDecision, Escalate
from skm.modules.execution.ports import BudgetRepository, RunRepository
from skm.modules.extensions.public import PackPins
from skm.modules.runtimes.public import (
    SubagentUsage,
    UsageReport,
    UsageStatus,
    usage_cost,
)


def priced_usage(uow: UnitOfWork, ctx: Any, fenced: Any, step: Any, raw: Any) -> Any:
    """Price measured counters from the pinned catalog, never a worker-supplied money value."""
    usage = parse_usage(raw)
    if usage is None or step is None:
        return usage
    loaded = load_effective_bundle(uow, fenced.run.id)
    return usage_cost(
        uow,
        usage,
        step.runtime_id,
        step.model,
        config=ctx.config,
        pins=cast("PackPins", loaded.bundle.resource_pins.packs),
    )


def amounts(usage: UsageReport, *, review: bool = False) -> dict[BudgetDimension, Decimal | None]:
    result = {
        dimension: usage_charge(usage, dimension).actual
        for dimension in (BudgetDimension.TOKENS, BudgetDimension.USD)
    }
    if review:
        result[BudgetDimension.REVIEW_ROUNDS] = Decimal(1)
    return result


def reserve_step(
    uow: UnitOfWork,
    ctx: Any,
    fenced: Any,
    step: Any,
    wanted: dict[BudgetDimension, Decimal | None],
    *,
    precheck: bool = False,
) -> list[Any]:
    repo = uow.repo(BudgetRepository)
    plans: list[Any] = []
    for dim, amount in wanted.items():
        if amount is not None and amount <= 0:
            continue
        accounts = repo.accounts_for(fenced.run.id, fenced.task.id, dim)
        if not accounts:
            continue
        if amount is None:
            if any(account.limit_value is not None for account in accounts):
                raise error_for(
                    ErrorCode.BUDGET_EXHAUSTED,
                    "a limited budget requires an estimate before the step can start",
                    details={"dimension": dim.value, "reason": "unknown_estimate"},
                )
            continue
        try:
            _, reservation = reserve(
                accounts,
                amount,
                reservation_id=ctx.ids.new_id(),
                now=fenced.now,
                step_id=step.id,
                unmetered=fenced.run.unmetered_at is not None,
            )
        except BudgetExhausted as exc:
            raise error_for(ErrorCode.BUDGET_EXHAUSTED, str(exc), details=exc.details()) from exc
        # Domain precheck covers all dimensions before any account update under the run lock.
        plans.append(reservation)
    if precheck:
        return plans
    created: list[Any] = []
    with uow.savepoint():
        for reservation in sorted(plans, key=lambda r: min(str(a) for a in r.account_ids)):
            if not repo.reserve(reservation.account_ids, reservation.amount):
                raise error_for(ErrorCode.BUDGET_EXHAUSTED, "current budget cannot reserve this step")
            repo.add_reservation(reservation)
            created.append(reservation)
    return created


def replace_runtime_reserve(uow: UnitOfWork, ctx: Any, fenced: Any, step: Any, wanted: Any) -> None:
    repo = uow.repo(BudgetRepository)
    # Restore draft reservations and every account/dimension on refusal before terminal cleanup.
    with uow.savepoint():
        for old in repo.open_for_steps((step.id,)):
            repo.release(old)
        reserve_step(uow, ctx, fenced, step, wanted)


def close_budgets(uow: UnitOfWork, fenced: Any, stage: Any, steps: Any) -> Any:
    repo = uow.repo(BudgetRepository)
    _, values = effective_values(uow, fenced.run.id)
    by_id = {s.id: s for s in steps}
    refusal: Any = None
    for reservation in repo.open_for_steps(tuple(by_id)):
        step = by_id[reservation.step_id]
        fixed = reservation.dimension is BudgetDimension.REVIEW_ROUNDS
        accounts = [
            a
            for a in repo.accounts_for(fenced.run.id, fenced.task.id, reservation.dimension)
            if a.id in reservation.account_ids
        ]
        closure = close_reservation(
            accounts,
            reservation,
            runtime_started=stage.runtime_started_at is not None,
            usage=UsageCharge(reservation.dimension, reservation.amount, reservation.amount, "finalized")
            if fixed
            else None
            if step.usage is None
            else usage_charge(step.usage, reservation.dimension),
            usage_so_far=None
            if fixed or step.usage_so_far is None
            else usage_charge(step.usage_so_far, reservation.dimension),
            policy=values.get("budgets.unknown_usage_policy", "block"),
            unknown_charge=reservation.amount,
            now=fenced.now,
        )
        if closure.reservation.state == "released":
            repo.release(reservation)
        else:
            repo.settle(reservation, closure.charged)
        if closure.unmetered:
            run = uow.repo(RunRepository).get(fenced.run.id)
            if run.unmetered_at is None:
                uow.repo(RunRepository).save(
                    replace(run, unmetered_at=fenced.now, row_version=run.row_version + 1),
                    expected_version=run.row_version,
                )
            refusal = {"reason": "unmetered", "scope": "run", "dimension": reservation.dimension.value}
        elif closure.exhausted:
            overrun = closure.exhausted[0]
            refusal = {
                "scope": overrun.scope,
                "dimension": overrun.dimension.value,
                "limit": str(overrun.limit),
                "spent": str(overrun.spent),
            }
    return refusal


def pause_budget(uow: UnitOfWork, ctx: Any, fenced: Any, details: Any) -> None:
    why = cause("stage_outcome", codes=["BUDGET_EXHAUSTED"])
    apply_action(
        ActionDecision(
            Escalate(DecisionKind.BUDGET, "BUDGET_EXHAUSTED", details, BlockingCode.BLOCKED_BY_BUDGET), why
        ),
        ctx,
        uow,
        task_id=fenced.task.id,
        why=why,
    )
    run = uow.repo(RunRepository).get(fenced.run.id)
    if run.status.value == "running":
        paused = pause(run, reason="BUDGET_EXHAUSTED", source="system", stop_code="BUDGET_EXHAUSTED")
        uow.repo(RunRepository).save(paused, expected_version=run.row_version)
        emit(
            uow,
            run,
            "run-paused",
            {
                "by": str(ctx.actor.principal_id),
                "reason": "BUDGET_EXHAUSTED",
                "pause_source": "system",
                "stop_code": "BUDGET_EXHAUSTED",
            },
            why,
        )
    fenced.run = uow.repo(RunRepository).get(fenced.run.id)


def parse_usage(raw: Any) -> Any:
    if raw is None:
        return None
    return UsageReport(
        raw.get("input_tokens"),
        raw.get("output_tokens"),
        raw.get("cache_read_tokens"),
        raw.get("cache_write_tokens"),
        raw.get("reasoning_tokens"),
        raw.get("cost_usd_micros"),
        UsageStatus(raw["status"]),
        raw["source"],
        SubagentUsage(raw["subagents"]["used"], raw["subagents"]["disclosed"]),
    )
