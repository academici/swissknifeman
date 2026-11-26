"""Budget ledger: atomic reserve, truthful settle, release (execution §4.15, §5.6)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.application._worker_budget import amounts, reserve_step
from skm.modules.execution.domain.budget import (
    BudgetAccount,
    BudgetDimension,
    BudgetExhausted,
    BudgetReservation,
    UsageCharge,
    charge,
    close_reservation,
    fresh_token_floor,
    limit_from_config,
    record_spend,
    release,
    reserve,
    settle,
    settle_detailed,
    settle_usage,
    usage_charge,
    usd_to_micros,
    warn_exceeded,
)
from skm.modules.runtimes.public import SubagentUsage, UsageReport, UsageStatus, fresh_tokens, unknown_usage

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 31, 12, 5, tzinfo=UTC)
TOKENS = BudgetDimension.TOKENS
USD = BudgetDimension.USD
D = Decimal


def uid(n: int) -> Any:
    return UUID(int=n)


def account(
    n: int,
    *,
    scope: str = "run",
    limit: int | Decimal | None = None,
    spent: int = 0,
    reserved: int = 0,
    dimension: BudgetDimension = TOKENS,
) -> BudgetAccount:
    return BudgetAccount(
        id=uid(n),
        run_id=uid(1),
        scope=scope,  # type: ignore[arg-type]
        task_id=None if scope == "run" else uid(50),
        dimension=dimension,
        limit_value=None if limit is None else D(limit),
        spent=D(spent),
        reserved=D(reserved),
        row_version=1,
    )


def pair(
    run_limit: int | None = None, task_limit: int | None = None, *, dimension: BudgetDimension = TOKENS
) -> tuple[BudgetAccount, BudgetAccount]:
    return (
        account(10, limit=run_limit, dimension=dimension),
        account(20, scope="task", limit=task_limit, dimension=dimension),
    )


def reserve_on(accounts: Any, amount: int, n: int = 1, **kw: Any) -> Any:
    return reserve(accounts, D(amount), reservation_id=uid(900 + n), now=NOW, step_id=uid(800 + n), **kw)


def usage(
    *,
    input: int | None = 1000,
    output: int | None = 500,
    cache_read: int | None = 7000,
    cache_write: int | None = 200,
    cost: int | None = 12_345,
    status: UsageStatus = UsageStatus.REPORTED,
    subagents: SubagentUsage | None = None,
) -> UsageReport:
    return UsageReport(
        input_tokens=input,
        output_tokens=output,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        reasoning_tokens=None,
        cost_usd_micros=cost,
        status=status,
        source="stream:result",
        subagents=subagents or SubagentUsage(used=False, disclosed=True),
    )


# ---------------------------------------------------------------- reserve


def test_reserve_books_every_account_in_lock_order() -> None:
    run, task = pair(1000, 400)
    for given_order in ((run, task), (task, run)):
        accounts, reservation = reserve_on(given_order, 300)
        assert [a.id for a in accounts] == sorted(a.id for a in (run, task))  # ORDER BY id
        assert reservation.account_ids == tuple(a.id for a in accounts)
        assert all(a.reserved == 300 and a.spent == 0 and a.row_version == 2 for a in accounts)
        assert (reservation.state, reservation.amount, reservation.settled_at) == ("reserved", 300, None)
        assert reservation.dimension is TOKENS
        assert reservation.step_id == uid(801)


def test_reserve_is_all_or_nothing_across_run_and_task() -> None:
    run, task = pair(1000, 100)
    with pytest.raises(BudgetExhausted) as refused:
        reserve_on((run, task), 101)
    assert refused.value.scope == "task"
    assert refused.value.limit == 100
    assert refused.value.reason == "limit"
    assert refused.value.details()["dimension"] == "tokens"
    # the inputs are values: nothing was booked on the run account that would have fit
    assert (run.reserved, run.row_version) == (0, 1)


def test_no_oversubscription_when_reservations_race_for_the_last_tokens() -> None:
    run, task = pair(500, None)
    accounts, _ = reserve_on((run, task), 300, 1)
    with pytest.raises(BudgetExhausted) as refused:
        reserve_on(accounts, 300, 2)
    assert refused.value.committed == 300
    assert refused.value.requested == 300
    accounts, _ = reserve_on(accounts, 200, 3)  # exactly the rest fits: spent + reserved + amount <= limit
    assert next(a for a in accounts if a.scope == "run").reserved == 500


def test_reserve_counts_spent_and_reserved_against_the_limit() -> None:
    accounts = (account(10, limit=1000, spent=600, reserved=300),)
    with pytest.raises(BudgetExhausted):
        reserve_on(accounts, 101)
    reserve_on(accounts, 100)


def test_no_limit_never_refuses_and_an_estimate_is_no_hidden_cap() -> None:
    run, task = pair(None, None)
    accounts, reservation = reserve_on((run, task), 5_000_000)
    assert reservation.amount == 5_000_000
    assert all(a.limit_value is None for a in accounts)


def test_config_zero_means_no_limit_and_usd_limit_is_micros() -> None:
    assert limit_from_config(0, TOKENS) is None
    assert limit_from_config("0.0", USD) is None
    assert limit_from_config(250000, TOKENS) == 250000
    assert limit_from_config("20.0", USD) == 20_000_000
    assert limit_from_config("0.0000019", USD) == 1  # sub-micro dust is cut down, a limit is never raised
    assert usd_to_micros(D("1.5")) == 1_500_000
    with pytest.raises(ValueError, match="not negative"):
        limit_from_config(-1, TOKENS)


@pytest.mark.parametrize("value", ["0.0000004", "0.0000001", 1e-9, D("0.000000999")])
def test_a_positive_usd_limit_below_one_micro_is_unrepresentable_not_unlimited_nor_raised(value: Any) -> None:
    """Regression: the micro cut turned a tiny positive limit into 0 and then into ``None`` (no limit); the
    first repair raised it to 1 micro, above its configured hard limit. It is refused instead."""
    with pytest.raises(ValueError, match="unrepresentable"):
        limit_from_config(value, USD)
    assert limit_from_config("0.000001", USD) == 1  # exactly one micro is representable


def test_usd_is_whole_micros_everywhere() -> None:
    run = account(10, limit=20_000_000, dimension=USD)
    with pytest.raises(ValueError, match="whole micros"):
        reserve([run], D("1.5"), reservation_id=uid(9), now=NOW)
    with pytest.raises(ValueError, match="whole micros"):
        dataclasses.replace(run, spent=D("0.5"))
    accounts, reservation = reserve_on((run,), 1_500_000)
    assert accounts[0].reserved == 1_500_000
    assert reservation.amount == 1_500_000


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: reserve([], D(1), reservation_id=uid(9), now=NOW), id="no accounts"),
        pytest.param(
            lambda: reserve(pair()[:1] * 2, D(1), reservation_id=uid(9), now=NOW), id="duplicate account"
        ),
        pytest.param(
            lambda: reserve([account(10), account(20, dimension=USD)], D(1), reservation_id=uid(9), now=NOW),
            id="two dimensions",
        ),
        pytest.param(lambda: reserve(pair(), D(0), reservation_id=uid(9), now=NOW), id="zero amount"),
        pytest.param(lambda: reserve(pair(), D(-5), reservation_id=uid(9), now=NOW), id="negative amount"),
        pytest.param(lambda: reserve(pair(), D("NaN"), reservation_id=uid(9), now=NOW), id="nan amount"),
        pytest.param(
            lambda: reserve([account(n) for n in range(10, 15)], D(1), reservation_id=uid(9), now=NOW),
            id="five accounts",
        ),
    ],
)
def test_reserve_rejects_malformed_requests(build: Any) -> None:
    with pytest.raises(ValueError, match=r"."):
        build()


def test_unmetered_run_refuses_every_reserve() -> None:
    with pytest.raises(BudgetExhausted) as refused:
        reserve_on(pair(None, None), 1, unmetered=True)
    assert refused.value.reason == "unmetered"


def test_warning_threshold_warns_and_continues() -> None:
    assert warn_exceeded(D(100_001), 100_000) is True
    assert warn_exceeded(D(100_000), 100_000) is False
    assert warn_exceeded(D(10**9), 0) is False  # 0 disables the warning
    # default hard limits are 0 = none: exceeding the warning still reserves and settles
    task = account(20, scope="task", limit=limit_from_config(0, TOKENS), spent=150_000)
    accounts, reservation = reserve_on((task,), 60_000)
    outcome = settle_detailed(accounts, reservation, D(60_000), "charge_estimate", D(0), now=LATER)
    assert outcome.exhausted == ()
    assert outcome.accounts[0].spent == 210_000


def test_a_model_change_keeps_spent_and_counters() -> None:
    """The accounts carry no route: the step on another model draws on the same task/run spend."""
    accounts = pair(1000, 300)
    accounts, first = reserve_on(accounts, 200, 1)
    accounts, _ = settle(accounts, first, D(200), "block", D(0), now=LATER)
    with pytest.raises(BudgetExhausted):  # the second step runs on another model, the task still has 100 left
        reserve_on(accounts, 101, 2)
    accounts, second = reserve_on(accounts, 100, 2)
    assert next(a for a in accounts if a.scope == "task").spent == 200
    assert second.account_ids == tuple(a.id for a in accounts)


def test_direct_charge_for_attempts_checks_the_limit() -> None:
    accounts = tuple(
        dataclasses.replace(a, dimension=BudgetDimension.ATTEMPTS)
        for a in (account(10, limit=3), account(20))
    )
    for _ in range(3):
        accounts = charge(accounts, D(1))
    assert all(a.spent == 3 for a in accounts)
    assert all(a.reserved == 0 for a in accounts)
    with pytest.raises(BudgetExhausted):
        charge(accounts, D(1))


def test_observed_spend_without_a_reservation_is_booked_even_over_the_limit() -> None:
    accounts = tuple(
        dataclasses.replace(a, dimension=BudgetDimension.TOOL_CALLS)
        for a in (account(10, limit=100), account(20))
    )
    accounts, overruns = record_spend(accounts, D(80))
    assert overruns == ()
    accounts, overruns = record_spend(accounts, D(50))  # the calls happened: they are kept, the run is told
    assert all(a.spent == 130 for a in accounts)
    assert [(o.account_id, o.limit, o.spent) for o in overruns] == [(uid(10), 100, 130)]
    with pytest.raises(ValueError, match="not negative"):
        record_spend(accounts, D(-1))


# ---------------------------------------------------------------- settle


def test_settle_books_the_actual_and_frees_the_reservation() -> None:
    accounts, reservation = reserve_on(pair(1000, 400), 300)
    outcome = settle_detailed(accounts, reservation, D(120), "charge_estimate", D(50_000), now=LATER)
    assert outcome.applied
    assert outcome.charged == 120
    assert outcome.basis == "actual"
    assert all(a.spent == 120 and a.reserved == 0 and a.row_version == 3 for a in outcome.accounts)
    assert (outcome.reservation.state, outcome.reservation.settled_amount) == ("settled", 120)
    assert outcome.reservation.settled_at == LATER
    assert outcome.exhausted == ()
    assert outcome.unmetered is False
    assert outcome.exposure == "finalized"
    assert settle(accounts, reservation, D(120), "block", D(0), now=LATER) == (
        outcome.accounts,
        outcome.reservation,
    )


def test_actual_above_the_reservation_and_the_limit_is_kept_and_blocks_the_future() -> None:
    accounts, reservation = reserve_on(pair(1000, 400), 300)
    outcome = settle_detailed(accounts, reservation, D(950), "block", D(0), now=LATER)
    by_scope = {a.scope: a for a in outcome.accounts}
    assert by_scope["task"].spent == 950
    assert by_scope["run"].spent == 950
    assert outcome.reservation.settled_amount == 950
    # the task limit (400) is passed; the run limit (1000) is not
    assert [(o.scope, o.limit, o.spent) for o in outcome.exhausted] == [("task", 400, 950)]
    with pytest.raises(BudgetExhausted) as refused:  # a later reserve is refused for good
        reserve_on(outcome.accounts, 1, 2)
    assert refused.value.scope == "task"


def test_overrun_of_the_run_limit_reports_the_run_account() -> None:
    accounts, reservation = reserve_on(pair(500, None), 400)
    outcome = settle_detailed(accounts, reservation, D(700), "block", D(0), now=LATER)
    assert [o.scope for o in outcome.exhausted] == ["run"]
    assert outcome.exhausted[0].account_id == uid(10)


def test_settle_replay_does_not_charge_twice_and_keeps_the_late_actual() -> None:
    accounts, reservation = reserve_on(pair(1000, 400), 300)
    first = settle_detailed(accounts, reservation, D(120), "block", D(0), now=LATER)
    again = settle_detailed(first.accounts, first.reservation, D(120), "block", D(0), now=LATER)
    assert again.applied is False
    assert again.charged == 0
    assert again.accounts == first.accounts
    assert again.reservation == first.reservation
    assert again.exhausted == ()
    assert again.unmetered is False
    late = settle_detailed(first.accounts, first.reservation, D(900), "block", D(0), now=LATER)
    assert late.accounts == first.accounts
    assert late.late_actual == 900


def test_a_released_reservation_is_not_settled_later() -> None:
    accounts, reservation = reserve_on(pair(1000, 400), 300)
    freed, released = release(accounts, reservation, now=LATER)
    late = settle_detailed(freed, released, D(100), "charge_estimate", D(10), now=LATER)
    assert late.applied is False
    assert late.accounts == freed
    assert late.late_actual == 100


def test_settle_requires_the_accounts_of_the_reservation_and_a_consistent_ledger() -> None:
    accounts, reservation = reserve_on(pair(1000, 400), 300)
    with pytest.raises(ValueError, match="missing"):
        settle(accounts[:1], reservation, D(1), "block", D(0), now=LATER)
    broken = (dataclasses.replace(accounts[0], reserved=D(10)), accounts[1])
    with pytest.raises(ValueError, match="inconsistent"):
        settle(broken, reservation, D(1), "block", D(0), now=LATER)
    with pytest.raises(ValueError, match="not negative"):
        settle(accounts, reservation, D(-1), "block", D(0), now=LATER)
    with pytest.raises(ValueError, match="unknown usage policy"):
        settle(accounts, reservation, None, "charge_fixed", D(0), now=LATER)  # type: ignore[arg-type]


# ---------------------------------------------------------------- unknown usage


def test_unknown_usage_is_never_zero() -> None:
    accounts, reservation = reserve_on(pair(), 300)
    estimate = settle_detailed(accounts, reservation, None, "charge_estimate", D(50_000), now=LATER)
    assert estimate.charged == 50_000
    assert estimate.basis == "estimate"
    assert estimate.exposure == "unknown"
    assert estimate.unmetered is False
    assert all(a.spent == 50_000 and a.reserved == 0 for a in estimate.accounts)
    zero_charge = settle_detailed(accounts, reservation, None, "charge_estimate", D(0), now=LATER)
    assert zero_charge.charged == 300
    assert zero_charge.basis == "estimate"


def test_worker_budget_estimates_distinguish_missing_and_measured_zero() -> None:
    assert amounts(usage(output=None, cost=None), review=True) == {
        TOKENS: None,
        USD: None,
        BudgetDimension.REVIEW_ROUNDS: D(1),
    }
    assert amounts(usage(input=0, output=0, cache_write=0, cost=0)) == {TOKENS: D(0), USD: D(0)}


def test_unknown_worker_cost_cannot_pass_a_finite_budget() -> None:
    repo = SimpleNamespace(accounts_for=lambda *_: (account(1, limit=10, dimension=USD),))
    uow: Any = SimpleNamespace(repo=lambda _: repo)
    fenced = SimpleNamespace(run=SimpleNamespace(id=uid(1)), task=SimpleNamespace(id=uid(2)))
    with pytest.raises(SkmError) as caught:
        reserve_step(uow, None, fenced, None, {USD: None}, precheck=True)
    assert caught.value.code is ErrorCode.BUDGET_EXHAUSTED
    assert caught.value.details == {"dimension": "usd", "reason": "unknown_estimate"}
    assert reserve_step(uow, None, fenced, None, {USD: D(0)}, precheck=True) == []


def test_block_policy_charges_the_reservation_and_marks_the_run_unmetered() -> None:
    accounts, reservation = reserve_on(pair(), 300)
    outcome = settle_detailed(accounts, reservation, None, "block", D(50_000), now=LATER)
    assert outcome.charged == 300
    assert outcome.basis == "reservation"
    assert outcome.unmetered is True
    assert outcome.exposure == "unknown"
    assert outcome.reservation.state == "settled"


UNKNOWN = unknown_usage()

# known / partial / unknown usage  x  priced / unpriced; the policies are crossed in the test below
# (id, report, tokens actual, tokens floor, usd actual, usd floor, exposure when the actual is known)
CASES = [
    ("reported+priced", usage(), 1700, 1700, 12_345, 12_345, "finalized"),
    ("reported+unpriced", usage(cost=None), 1700, 1700, None, 0, "finalized"),
    ("estimated+priced", usage(status=UsageStatus.ESTIMATED), 1700, 1700, 12_345, 12_345, "estimated"),
    ("estimated+unpriced", usage(status=UsageStatus.ESTIMATED, cost=None), 1700, 1700, None, 0, "estimated"),
    ("partial: output missing", usage(output=None, cost=None), None, 1200, None, 0, "unknown"),
    (
        "subagent usage not disclosed",
        usage(subagents=SubagentUsage(used=True, disclosed=False)),
        None,
        1700,
        None,
        12_345,
        "unknown",
    ),
    ("unknown usage", UNKNOWN, None, 0, None, 0, "unknown"),
]
CASE_IDS = [case[0] for case in CASES]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_usage_report_to_charges(case: tuple[Any, ...]) -> None:
    _, report, tokens, tokens_floor, dollars, dollars_floor, exposure = case
    found_tokens, found_usd = usage_charge(report, TOKENS), usage_charge(report, USD)
    assert (found_tokens.actual, found_tokens.floor) == (
        tokens if tokens is None else D(tokens),
        D(tokens_floor),
    )
    assert (found_usd.actual, found_usd.floor) == (
        dollars if dollars is None else D(dollars),
        D(dollars_floor),
    )
    if tokens is not None:
        assert found_tokens.actual == fresh_tokens(
            report
        )  # the K9 formula of the ledger agrees with runtimes
        assert found_tokens.exposure == exposure
    else:
        assert found_tokens.exposure == "unknown"
    if dollars is None:
        assert found_usd.exposure == "unknown"  # reported tokens without a price are not 0 USD


@pytest.mark.parametrize("policy", ["charge_estimate", "block"])
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_closing_a_reservation_is_not_a_finalized_bill(case: tuple[Any, ...], policy: Any) -> None:
    report = case[1]
    for dimension, reserved_amount in ((TOKENS, 3000), (USD, 200_000)):
        accounts, reservation = reserve_on((account(10, dimension=dimension),), reserved_amount)
        found = usage_charge(report, dimension)
        outcome = settle_usage(accounts, reservation, found, policy, D(40_000), now=LATER)
        assert outcome.reservation.state == "settled"
        assert outcome.charged > 0  # unknown or unpriced usage is never booked as zero
        if found.actual is not None:
            assert (outcome.charged, outcome.basis, outcome.exposure) == (
                found.actual,
                "actual",
                found.exposure,
            )
        else:
            assert outcome.exposure == "unknown"
            assert outcome.charged >= found.floor
            assert outcome.unmetered is (policy == "block")
        # only a fully reported usage is a finalized bill
        assert (outcome.exposure == "finalized") == (
            report.status is UsageStatus.REPORTED and found.actual is not None
        )


def test_partial_usage_is_a_floor_for_the_charge() -> None:
    """input is known (3000), output is not: the policy estimate must not undercut what was measured."""
    report = usage(input=3000, output=None, cache_write=None, cost=None)
    found = usage_charge(report, TOKENS)
    assert found.actual is None
    assert found.floor == 3000
    accounts, reservation = reserve_on(pair(), 10_000)
    estimate = settle_usage(accounts, reservation, found, "charge_estimate", D(1_000), now=LATER)
    assert estimate.charged == 3000  # max(estimate 1000, measured 3000)
    block = settle_usage(accounts, reservation, found, "block", D(1_000), now=LATER)
    assert block.charged == 10_000
    assert block.unmetered is True
    floor_over_reservation = settle_detailed(
        accounts, reservation, None, "block", D(0), now=LATER, observed_floor=D(12_000)
    )
    assert floor_over_reservation.charged == 12_000


def test_fresh_tokens_are_input_output_and_cache_write_only() -> None:
    report = usage(input=10, output=20, cache_read=1_000_000, cache_write=5)
    assert usage_charge(report, TOKENS).actual == 35  # cache reads are not fresh (K9)
    assert fresh_token_floor(usage(input=10, output=None, cache_write=5)) == 15
    with pytest.raises(ValueError, match="tokens or usd"):
        usage_charge(report, BudgetDimension.TOOL_CALLS)
    none = usage_charge(None, TOKENS)
    assert (none.actual, none.floor, none.exposure) == (None, 0, "unknown")


def test_settle_usage_rejects_a_charge_of_another_dimension() -> None:
    accounts, reservation = reserve_on(pair(), 100)
    with pytest.raises(ValueError, match="another dimension"):
        settle_usage(accounts, reservation, usage_charge(usage(), USD), "block", D(0), now=LATER)


# ---------------------------------------------------------------- release and emergency close (K4)


def test_release_frees_only_the_reservation() -> None:
    accounts, reservation = reserve_on(pair(1000, 400), 300)
    freed, released = release(accounts, reservation, now=LATER)
    assert all(a.reserved == 0 and a.spent == 0 and a.row_version == 3 for a in freed)
    assert (released.state, released.settled_amount, released.settled_at) == ("released", None, LATER)
    again = release(freed, released, now=LATER)
    assert again == (freed, released)  # idempotent: a closed reservation is not freed twice


def test_release_does_not_undo_a_settlement() -> None:
    accounts, reservation = reserve_on(pair(1000, 400), 300)
    outcome = settle_detailed(accounts, reservation, D(100), "block", D(0), now=LATER)
    assert release(outcome.accounts, outcome.reservation, now=LATER) == (
        outcome.accounts,
        outcome.reservation,
    )


def emergency(
    started: bool,
    *,
    usage_now: UsageCharge | None = None,
    so_far: UsageCharge | None = None,
    policy: Any = "charge_estimate",
    dimension: BudgetDimension = TOKENS,
    amount: int = 3000,
) -> Any:
    accounts, reservation = reserve_on(pair(None, None, dimension=dimension), amount)
    return close_reservation(
        accounts,
        reservation,
        runtime_started=started,
        usage=usage_now,
        usage_so_far=so_far,
        policy=policy,
        unknown_charge=D(40_000),
        now=LATER,
    )


def test_emergency_close_before_runtime_start_releases() -> None:
    outcome = emergency(False)
    assert outcome.reservation.state == "released"
    assert outcome.basis == "released"
    assert outcome.applied
    assert all(a.reserved == 0 and a.spent == 0 for a in outcome.accounts)


def test_emergency_close_after_runtime_start_never_frees_it_for_nothing() -> None:
    reported = usage_charge(usage(), TOKENS)
    so_far = usage_charge(usage(input=400, output=100, cache_write=0, status=UsageStatus.ESTIMATED), TOKENS)
    by_command = emergency(True, usage_now=reported, so_far=so_far)
    assert by_command.charged == 1700
    assert by_command.exposure == "finalized"
    by_so_far = emergency(True, usage_now=None, so_far=so_far)
    assert by_so_far.charged == 500
    assert by_so_far.exposure == "estimated"
    unknown = emergency(True)
    assert unknown.reservation.state == "settled"
    assert unknown.charged == 40_000
    assert unknown.exposure == "unknown"
    assert all(a.spent == 40_000 and a.reserved == 0 for a in unknown.accounts)
    blocked = emergency(True, policy="block")
    assert blocked.charged == 3000
    assert blocked.unmetered is True


def test_emergency_close_uses_the_measured_floor_of_a_partial_report() -> None:
    partial = usage_charge(usage(input=70_000, output=None, cache_write=None, cost=None), TOKENS)
    outcome = emergency(True, usage_now=partial)
    assert outcome.charged == 70_000  # estimate 40000 would undercut the measured input


def test_emergency_close_keeps_the_floor_of_a_terminal_unknown_usage_over_an_earlier_estimate() -> None:
    """Regression: an earlier estimate of 500 won over the terminal partial report that measured 70000."""
    terminal = usage_charge(usage(input=70_000, output=None, cache_write=None, cost=None), TOKENS)
    so_far = usage_charge(usage(input=400, output=100, cache_write=0, status=UsageStatus.ESTIMATED), TOKENS)
    assert (terminal.actual, terminal.floor) == (None, 70_000)
    assert so_far.actual == 500
    blocked = emergency(True, usage_now=terminal, so_far=so_far, policy="block")
    assert blocked.charged == 70_000
    assert blocked.unmetered is True
    assert blocked.basis == "reservation"
    assert blocked.exposure == "unknown"
    assert all(a.spent == 70_000 and a.reserved == 0 for a in blocked.accounts)
    estimated = emergency(True, usage_now=terminal, so_far=so_far)
    assert estimated.charged == 70_000  # the estimate 40000 would undercut the measured input
    assert estimated.unmetered is False
    # undisclosed subagent usage in the terminal report is unknown too and keeps the run unmetered
    hidden = usage_charge(usage(subagents=SubagentUsage(used=True, disclosed=False)), TOKENS)
    assert hidden.actual is None
    assert emergency(True, usage_now=hidden, so_far=so_far, policy="block").unmetered is True
    # an earlier usage that is the only one that measured something is still a floor
    earlier_only = usage_charge(usage(input=90_000, output=None, cache_write=None, cost=None), TOKENS)
    assert emergency(True, usage_now=None, so_far=earlier_only, policy="block").charged == 90_000


def test_emergency_close_keeps_a_terminal_unknown_usage_unknown_even_with_a_zero_floor() -> None:
    """Regression: a terminal usage that measured nothing was replaced by an earlier known estimate."""
    terminal = usage_charge(usage(input=None, output=None, cache_write=None, cost=None), TOKENS)
    so_far = usage_charge(usage(input=400, output=100, cache_write=0, status=UsageStatus.ESTIMATED), TOKENS)
    assert (terminal.actual, terminal.floor, terminal.exposure) == (None, 0, "unknown")
    assert so_far.actual == 500
    estimated = emergency(True, usage_now=terminal, so_far=so_far)
    assert estimated.basis == "estimate"  # not "actual": the earlier estimate is not the bill
    assert estimated.exposure == "unknown"
    assert estimated.charged == 40_000  # the policy estimate; the earlier 500 is only a floor
    assert estimated.unmetered is False
    blocked = emergency(True, usage_now=terminal, so_far=so_far, policy="block")
    assert blocked.basis == "reservation"
    assert blocked.exposure == "unknown"
    assert blocked.charged == 3000
    assert blocked.unmetered is True
    # the measured floor of the earlier estimate still holds when it exceeds the policy charge
    large = usage_charge(
        usage(input=70_000, output=20_000, cache_write=0, status=UsageStatus.ESTIMATED), TOKENS
    )
    assert emergency(True, usage_now=terminal, so_far=large).charged == 90_000
    assert emergency(True, usage_now=terminal, so_far=large, policy="block").charged == 90_000


def test_emergency_close_of_a_review_round_that_started_spends_the_round() -> None:
    outcome = emergency(True, dimension=BudgetDimension.REVIEW_ROUNDS, amount=1)
    assert outcome.charged == 1
    assert outcome.basis == "actual"
    assert emergency(False, dimension=BudgetDimension.REVIEW_ROUNDS, amount=1).reservation.state == "released"


def test_emergency_close_is_idempotent_and_keeps_a_late_actual() -> None:
    accounts, reservation = reserve_on(pair(None, None), 3000)
    first = close_reservation(
        accounts,
        reservation,
        runtime_started=True,
        usage=None,
        usage_so_far=None,
        policy="charge_estimate",
        unknown_charge=D(40_000),
        now=LATER,
    )
    late = close_reservation(
        first.accounts,
        first.reservation,
        runtime_started=True,
        usage=usage_charge(usage(), TOKENS),
        usage_so_far=None,
        policy="charge_estimate",
        unknown_charge=D(40_000),
        now=LATER,
    )
    assert late.applied is False
    assert late.accounts == first.accounts
    assert late.late_actual == 1700
    after_release = close_reservation(
        first.accounts,
        first.reservation,
        runtime_started=False,
        usage=None,
        usage_so_far=None,
        policy="block",
        unknown_charge=D(0),
        now=LATER,
    )
    assert after_release.applied is False
    assert after_release.accounts == first.accounts


def test_dimensions_without_a_reservation_cannot_be_closed() -> None:
    accounts = (account(10, dimension=BudgetDimension.WALL_SECONDS),)
    reservation = BudgetReservation(
        id=uid(1),
        account_ids=(uid(10),),
        dimension=BudgetDimension.WALL_SECONDS,
        step_id=None,
        amount=D(1),
        state="reserved",
        settled_amount=None,
        created_at=NOW,
        settled_at=None,
    )
    with pytest.raises(ValueError, match="no reservation"):
        close_reservation(
            accounts,
            reservation,
            runtime_started=False,
            usage=None,
            usage_so_far=None,
            policy="block",
            unknown_charge=D(0),
            now=LATER,
        )


def test_reservation_and_account_invariants() -> None:
    with pytest.raises(ValueError, match="settled_amount is set exactly"):
        BudgetReservation(
            id=uid(1),
            account_ids=(uid(10),),
            dimension=TOKENS,
            step_id=None,
            amount=D(1),
            state="settled",
            settled_amount=None,
            created_at=NOW,
            settled_at=NOW,
        )
    with pytest.raises(ValueError, match="not negative"):
        dataclasses.replace(account(10), reserved=D(-1))
    with pytest.raises(ValueError, match="config 0 means None"):
        dataclasses.replace(account(10), limit_value=D(0))
    with pytest.raises(ValueError, match="scope run has no task_id"):
        dataclasses.replace(account(10), task_id=uid(5))


# ---------------------------------------------------------------- invariants over any sequence


OPS = st.lists(
    st.tuples(
        st.sampled_from(["reserve", "settle", "settle_unknown", "release", "replay"]),
        st.integers(min_value=1, max_value=400),
        st.integers(min_value=0, max_value=900),
    ),
    max_size=40,
)


@given(OPS, st.integers(min_value=1, max_value=1000), st.sampled_from(["charge_estimate", "block"]))
def test_ledger_invariants_hold_over_any_sequence(
    ops: list[tuple[str, int, int]], limit: int, policy: Any
) -> None:
    """Never negative; reserved is the open reservations; spent is the booked charges."""
    accounts: tuple[BudgetAccount, ...] = pair(limit, limit * 2)
    open_reservations: list[BudgetReservation] = []
    closed: list[BudgetReservation] = []
    booked = D(0)
    for n, (op, amount, actual) in enumerate(ops, start=1):
        if op == "reserve":
            try:
                accounts, reservation = reserve_on(accounts, amount, n)
            except BudgetExhausted:
                continue
            open_reservations.append(reservation)
        elif op in ("settle", "settle_unknown") and open_reservations:
            reservation = open_reservations.pop(0)
            outcome = settle_detailed(
                accounts, reservation, D(actual) if op == "settle" else None, policy, D(7), now=LATER
            )
            accounts, booked = outcome.accounts, booked + outcome.charged
            closed.append(outcome.reservation)
            assert outcome.charged > 0 or (op == "settle" and actual == 0)
        elif op == "release" and open_reservations:
            reservation = open_reservations.pop(0)
            accounts, released = release(accounts, reservation, now=LATER)
            closed.append(released)
        elif op == "replay" and closed:
            before = accounts
            outcome = settle_detailed(accounts, closed[-1], D(actual), policy, D(7), now=LATER)
            accounts = outcome.accounts
            assert accounts == before
            assert outcome.applied is False
        assert all(a.spent >= 0 and a.reserved >= 0 for a in accounts)
        assert all(a.reserved == sum(r.amount for r in open_reservations) for a in accounts)
        assert all(a.spent == booked for a in accounts)
