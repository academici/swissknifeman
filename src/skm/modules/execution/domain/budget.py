"""Budget ledger: atomic reserve, truthful settle, release (execution §4.15, §5.6).

Pure functions over ``BudgetAccount`` / ``BudgetReservation`` values; the repository applies the returned
rows under ``SELECT … ORDER BY id FOR UPDATE``. A reservation is admission, not a bill:

* ``reserve`` is all-or-nothing over the run and task accounts of one dimension; the hard limit applies
  only where it is set (``limit_value is None`` never refuses) and a token estimate is never a hidden cap.
* ``settle`` records the actual usage even when it is larger than the reservation or the limit. An
  overrun is reported (``SettleOutcome.exhausted``) so that the caller writes ``BUDGET_EXHAUSTED`` and
  pauses the run in the same commit; every later ``reserve`` of an over-limit account is refused.
* Unknown usage is never zero: ``charge_estimate`` charges the estimate, ``block`` charges the whole
  reservation and marks the run unmetered. The known part of a partial report is a floor for the charge.
* Closing is idempotent: a reservation that is already ``settled`` or ``released`` is not charged or
  freed again; a late actual is returned in ``late_actual`` and stays evidence for recovery.

Money of the ``usd`` dimension is integer USD micros in every account and reservation.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, Protocol
from uuid import UUID

from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from skm.kernel.ids import RunId, TaskId
    from skm.modules.execution.domain.ids import BudgetReservationId, StepId

__all__ = [
    "RESERVED_DIMENSIONS",
    "BudgetAccount",
    "BudgetDimension",
    "BudgetExhausted",
    "BudgetOverrun",
    "BudgetReservation",
    "SettleOutcome",
    "UsageCharge",
    "UsageFacts",
    "charge",
    "close_reservation",
    "fresh_token_floor",
    "limit_from_config",
    "record_spend",
    "release",
    "reserve",
    "settle",
    "settle_detailed",
    "settle_usage",
    "usage_charge",
    "usd_to_micros",
    "warn_exceeded",
]


class BudgetDimension(StrEnum):
    USD = "usd"
    TOKENS = "tokens"
    WALL_SECONDS = "wall_seconds"
    ATTEMPTS = "attempts"
    REVIEW_ROUNDS = "review_rounds"
    TOOL_CALLS = "tool_calls"


# dimensions reserved before the step runs (§5.6); the others are spent directly or checked later
RESERVED_DIMENSIONS: Final = frozenset(
    {BudgetDimension.USD, BudgetDimension.TOKENS, BudgetDimension.REVIEW_ROUNDS}
)

type UnknownUsagePolicy = Literal["charge_estimate", "block"]
type Exposure = Literal["finalized", "estimated", "unknown"]

_MAX_ACCOUNTS: Final = 4  # ck_budget_reservations__accounts
_ZERO: Final = Decimal(0)
_MICROS: Final = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class BudgetAccount:
    id: UUID
    run_id: RunId
    scope: Literal["run", "task"]
    task_id: TaskId | None
    dimension: BudgetDimension
    limit_value: Decimal | None
    spent: Decimal
    reserved: Decimal
    row_version: int

    def __post_init__(self) -> None:
        problems: list[str] = []
        if (self.scope == "run") != (self.task_id is None):
            problems.append("scope run has no task_id, scope task has one")
        if self.spent < 0 or self.reserved < 0:
            problems.append("spent and reserved are not negative")
        if self.limit_value is not None and self.limit_value <= 0:
            problems.append("limit_value is positive; a config 0 means None")
        if self.row_version < 1:
            problems.append("row_version >= 1")
        if self.dimension is BudgetDimension.USD:
            for name in ("limit_value", "spent", "reserved"):
                value = getattr(self, name)
                if value is not None and value != value.to_integral_value():
                    problems.append(f"usd {name} is whole micros")
        if problems:
            raise ValueError("budget account invariants violated: " + "; ".join(problems))


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    id: BudgetReservationId
    account_ids: tuple[UUID, ...]
    dimension: BudgetDimension
    step_id: StepId | None
    amount: Decimal
    state: Literal["reserved", "settled", "released"]
    settled_amount: Decimal | None
    created_at: datetime
    settled_at: datetime | None

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.amount <= 0:
            problems.append("amount > 0")
        if not 1 <= len(self.account_ids) <= _MAX_ACCOUNTS or len(set(self.account_ids)) != len(
            self.account_ids
        ):
            problems.append(f"1..{_MAX_ACCOUNTS} distinct account ids")
        if (self.state == "reserved") != (self.settled_at is None):
            problems.append("settled_at is set exactly when the reservation is closed")
        if (self.state == "settled") != (self.settled_amount is not None):
            problems.append("settled_amount is set exactly when the reservation is settled")
        if self.settled_amount is not None and self.settled_amount < 0:
            problems.append("settled_amount >= 0")
        if self.dimension is BudgetDimension.USD:
            for name in ("amount", "settled_amount"):
                value = getattr(self, name)
                if value is not None and value != value.to_integral_value():
                    problems.append(f"usd {name} is whole micros")
        if problems:
            raise ValueError("budget reservation invariants violated: " + "; ".join(problems))


class BudgetExhausted(Exception):
    """A reserve that would pass a hard limit, or any reserve of an unmetered run.

    Internal refusal (§5.6): worker commands commit it as a refusal; it is not a bus exception that rolls
    back the stage and its cleanup. ``committed`` is ``spent + reserved`` before the refused amount.
    """

    def __init__(
        self,
        dimension: BudgetDimension,
        limit: Decimal | None,
        committed: Decimal,
        requested: Decimal,
        *,
        reason: Literal["limit", "unmetered"] = "limit",
        scope: Literal["run", "task"] | None = None,
        task_id: TaskId | None = None,
    ) -> None:
        self.dimension = dimension
        self.limit = limit
        self.committed = committed
        self.requested = requested
        self.reason = reason
        self.scope = scope
        self.task_id = task_id
        super().__init__(
            f"budget {dimension.value} exhausted ({reason}): "
            f"limit={limit} committed={committed} requested={requested}"
        )

    def details(self) -> JsonObject:
        """Payload of ``Escalate(budget, BUDGET_EXHAUSTED)``; decimals travel as strings."""
        return {
            "dimension": self.dimension.value,
            "reason": self.reason,
            "scope": self.scope,
            "task_id": None if self.task_id is None else str(self.task_id),
            "limit": None if self.limit is None else str(self.limit),
            "committed": str(self.committed),
            "requested": str(self.requested),
        }


@dataclass(frozen=True, slots=True)
class BudgetOverrun:
    """Spent passed a hard limit: the actual was kept, the run pauses and later reserves are refused."""

    account_id: UUID
    dimension: BudgetDimension
    scope: Literal["run", "task"]
    task_id: TaskId | None
    limit: Decimal
    spent: Decimal


@dataclass(frozen=True, slots=True)
class SettleOutcome:
    accounts: tuple[BudgetAccount, ...]
    reservation: BudgetReservation
    applied: bool  # False: the reservation was already closed, nothing moved
    charged: Decimal  # added to spent; 0 for a release or a replay
    basis: Literal["actual", "estimate", "reservation", "released", "none"]
    exposure: (
        Exposure  # finalized: reported usage in full; estimated: partial/estimated; unknown: nothing measured
    )
    unmetered: bool  # block policy took an unknown usage: the run is unmetered until the owner answers
    exhausted: tuple[BudgetOverrun, ...]
    late_actual: Decimal | None = (
        None  # an actual that arrived after the reservation was closed: evidence only
    )


class UsageSubagents(Protocol):
    @property
    def used(self) -> bool | None: ...
    @property
    def disclosed(self) -> bool: ...


class UsageFacts(Protocol):
    """The fields of ``runtimes.UsageReport`` the ledger reads (K9); execution has no usage type."""

    @property
    def input_tokens(self) -> int | None: ...
    @property
    def output_tokens(self) -> int | None: ...
    @property
    def cache_write_tokens(self) -> int | None: ...
    @property
    def cost_usd_micros(self) -> int | None: ...
    @property
    def status(self) -> str: ...
    @property
    def subagents(self) -> UsageSubagents: ...


@dataclass(frozen=True, slots=True)
class UsageCharge:
    """What a step's usage means for one dimension: a known actual, or none plus the known part (floor)."""

    dimension: BudgetDimension
    actual: Decimal | None  # None: unknown, the unknown-usage policy applies
    floor: Decimal  # the measured part of a partial report; a charge is never below it
    exposure: Exposure


# ---------------------------------------------------------------- money and config values


def usd_to_micros(value: Decimal | int | str) -> int:
    """USD (the config unit) to whole micros; sub-micro dust is cut down, a limit is never raised."""
    return int((Decimal(value) * _MICROS).to_integral_value(rounding=ROUND_FLOOR))


def limit_from_config(value: Decimal | int | str, dimension: BudgetDimension) -> Decimal | None:
    """A ``budgets.*`` value to ``limit_value``: ``0`` means no limit, ``max_usd`` becomes micros.

    Only an exact ``0`` is unlimited. A positive ``max_usd`` below one micro is neither unlimited nor 0
    micros (0 means none) and cannot be raised to 1 micro without passing its configured hard limit: it is
    unrepresentable and refused with ``ValueError``. Larger sub-micro dust is cut down, never raised.
    """
    number = Decimal(value)
    if number < 0:
        raise ValueError("a budget limit is not negative")
    if number == 0:
        return None
    if dimension is BudgetDimension.USD:
        micros = usd_to_micros(number)
        if micros < 1:
            raise ValueError(
                f"a usd budget limit below one micro ({number}) is unrepresentable; use 0 for no limit"
            )
        return Decimal(micros)
    return number


def warn_exceeded(spent: Decimal, warn_tokens: int) -> bool:
    """The soft ``budgets.task.warn_tokens`` signal: record and analyse, never stop (0 disables it)."""
    return warn_tokens > 0 and spent > warn_tokens


# ---------------------------------------------------------------- usage → charge


def fresh_token_floor(usage: UsageFacts) -> int:
    """The measured part of ``input + output + cache_write`` (K9); a missing counter is unmeasured."""
    return sum(
        value for value in (usage.input_tokens, usage.output_tokens, usage.cache_write_tokens) if value
    )


def usage_charge(usage: UsageFacts | None, dimension: BudgetDimension) -> UsageCharge:
    """Read one step usage for ``tokens`` or ``usd``.

    Missing, unknown or subagent-undisclosed usage has no actual (policy applies) but keeps its measured
    floor; reported tokens without a cost are *not* ``0`` USD; a price is never looked up here, the cost of
    the report is the one pinned when the runtime priced it.
    """
    if dimension not in (BudgetDimension.TOKENS, BudgetDimension.USD):
        raise ValueError(f"usage is charged to tokens or usd, not {dimension.value}")
    if usage is None:
        return UsageCharge(dimension, None, _ZERO, "unknown")
    hidden = usage.subagents.used is True and not usage.subagents.disclosed
    measured = usage.status != "unknown"
    if dimension is BudgetDimension.TOKENS:
        floor = Decimal(fresh_token_floor(usage))
        known = usage.input_tokens is not None and usage.output_tokens is not None
        total = floor if known else None
    else:
        floor = Decimal(usage.cost_usd_micros or 0)
        total = None if usage.cost_usd_micros is None else Decimal(usage.cost_usd_micros)
    if not measured or hidden or total is None:
        return UsageCharge(dimension, None, floor, "unknown")
    return UsageCharge(dimension, total, floor, "finalized" if usage.status == "reported" else "estimated")


# ---------------------------------------------------------------- ledger


def _usd_whole(dimension: BudgetDimension, *values: Decimal | None) -> None:
    if dimension is BudgetDimension.USD:
        for value in values:
            if value is not None and value != value.to_integral_value():
                raise ValueError("usd amounts are whole micros")


def _bump(account: BudgetAccount, *, spent: Decimal = _ZERO, reserved: Decimal = _ZERO) -> BudgetAccount:
    return dataclasses.replace(
        account,
        spent=account.spent + spent,
        reserved=account.reserved + reserved,
        row_version=account.row_version + 1,
    )


def _locked(accounts: Sequence[BudgetAccount]) -> tuple[BudgetAccount, ...]:
    """Accounts in the fixed lock order (``ORDER BY id``); one order everywhere rules out deadlocks."""
    ordered = tuple(sorted(accounts, key=lambda account: account.id.int))
    if not 1 <= len(ordered) <= _MAX_ACCOUNTS:
        raise ValueError(f"a reservation covers 1..{_MAX_ACCOUNTS} accounts")
    if len({account.id for account in ordered}) != len(ordered):
        raise ValueError("duplicate budget account")
    if (
        len({account.dimension for account in ordered}) != 1
        or len({account.run_id for account in ordered}) != 1
    ):
        raise ValueError("the accounts of one reservation share a run and a dimension")
    return ordered


def reserve(
    accounts: Sequence[BudgetAccount],
    amount: Decimal,
    *,
    reservation_id: BudgetReservationId,
    now: datetime,
    step_id: StepId | None = None,
    unmetered: bool = False,
) -> tuple[tuple[BudgetAccount, ...], BudgetReservation]:
    """Admit ``amount`` on every account or on none: ``spent + reserved + amount <= limit`` where one is set.

    ``unmetered`` is ``run.unmetered_at is not None``: no reserve passes until the owner answers. Raises
    ``BudgetExhausted`` (the first refusing account in lock order) and changes nothing. The accounts are
    returned in lock order with ``reserved`` raised and ``row_version`` incremented.
    """
    if not amount.is_finite() or amount <= 0:
        raise ValueError("a reservation amount is positive")
    ordered = _locked(accounts)
    dimension = ordered[0].dimension
    _usd_whole(dimension, amount)
    if unmetered:
        raise BudgetExhausted(dimension, None, _ZERO, amount, reason="unmetered")
    for account in ordered:
        committed = account.spent + account.reserved
        if account.limit_value is not None and committed + amount > account.limit_value:
            raise BudgetExhausted(
                dimension,
                account.limit_value,
                committed,
                amount,
                scope=account.scope,
                task_id=account.task_id,
            )
    reservation = BudgetReservation(
        id=reservation_id,
        account_ids=tuple(account.id for account in ordered),
        dimension=dimension,
        step_id=step_id,
        amount=amount,
        state="reserved",
        settled_amount=None,
        created_at=now,
        settled_at=None,
    )
    return tuple(_bump(account, reserved=amount) for account in ordered), reservation


def charge(accounts: Sequence[BudgetAccount], amount: Decimal) -> tuple[BudgetAccount, ...]:
    """Spend directly, without a reservation (``attempts`` at the creation of an attempt, §5.6).

    The limit is checked like a reserve; a refusal changes nothing.
    """
    if not amount.is_finite() or amount <= 0:
        raise ValueError("a charge is positive")
    ordered = _locked(accounts)
    _usd_whole(ordered[0].dimension, amount)
    for account in ordered:
        committed = account.spent + account.reserved
        if account.limit_value is not None and committed + amount > account.limit_value:
            raise BudgetExhausted(
                account.dimension,
                account.limit_value,
                committed,
                amount,
                scope=account.scope,
                task_id=account.task_id,
            )
    return tuple(_bump(account, spent=amount) for account in ordered)


def record_spend(
    accounts: Sequence[BudgetAccount], amount: Decimal
) -> tuple[tuple[BudgetAccount, ...], tuple[BudgetOverrun, ...]]:
    """Book an observed spend without a reservation (``wall_seconds``, ``tool_calls``): it happened, keep it.

    Nothing is refused; passing a limit is reported so that the next stage is blocked (§5.6).
    """
    if not amount.is_finite() or amount < 0:
        raise ValueError("an observed spend is not negative")
    ordered = _locked(accounts)
    _usd_whole(ordered[0].dimension, amount)
    moved = tuple(_bump(account, spent=amount) for account in ordered)
    return moved, _overruns(moved)


def _overruns(accounts: Sequence[BudgetAccount]) -> tuple[BudgetOverrun, ...]:
    return tuple(
        BudgetOverrun(a.id, a.dimension, a.scope, a.task_id, a.limit_value, a.spent)
        for a in accounts
        if a.limit_value is not None and a.spent > a.limit_value
    )


def _members(accounts: Sequence[BudgetAccount], reservation: BudgetReservation) -> tuple[BudgetAccount, ...]:
    by_id = {account.id: account for account in accounts}
    missing = [account_id for account_id in reservation.account_ids if account_id not in by_id]
    if missing:
        raise ValueError(f"accounts of the reservation are missing: {', '.join(str(i) for i in missing)}")
    return _locked([by_id[account_id] for account_id in reservation.account_ids])


def _closed(
    members: tuple[BudgetAccount, ...], reservation: BudgetReservation, late_actual: Decimal | None
) -> SettleOutcome:
    return SettleOutcome(
        accounts=members,
        reservation=reservation,
        applied=False,
        charged=_ZERO,
        basis="none",
        exposure="unknown",
        unmetered=False,
        exhausted=(),
        late_actual=late_actual,
    )


def _settle(
    accounts: Sequence[BudgetAccount],
    reservation: BudgetReservation,
    actual: Decimal | None,
    policy: UnknownUsagePolicy,
    unknown_charge: Decimal,
    *,
    now: datetime,
    floor: Decimal,
    exposure: Exposure | None,
) -> SettleOutcome:
    members = _members(accounts, reservation)
    if reservation.state != "reserved":
        return _closed(
            members, reservation, actual
        )  # replay: the first booking stands, the late actual is evidence
    if policy not in ("charge_estimate", "block"):
        raise ValueError(f"unknown usage policy {policy!r}")
    if (actual is not None and actual < 0) or floor < 0 or unknown_charge < 0:
        raise ValueError("usage amounts are not negative")
    _usd_whole(reservation.dimension, actual, floor, unknown_charge)
    unmetered = False
    basis: Literal["actual", "estimate", "reservation"]
    shown: Exposure
    if actual is not None:
        booked, basis, shown = actual, "actual", exposure or "finalized"
    elif policy == "charge_estimate":
        booked = max(unknown_charge if unknown_charge > 0 else reservation.amount, floor)
        basis, shown = "estimate", "unknown"
    else:
        booked = max(reservation.amount, floor)
        basis, shown, unmetered = "reservation", "unknown", True
    moved: list[BudgetAccount] = []
    for account in members:
        if account.reserved < reservation.amount:
            raise ValueError(
                f"account {account.id} holds less than the reservation: the ledger is inconsistent"
            )
        moved.append(_bump(account, spent=booked, reserved=-reservation.amount))
    closed = dataclasses.replace(reservation, state="settled", settled_amount=booked, settled_at=now)
    return SettleOutcome(
        accounts=tuple(moved),
        reservation=closed,
        applied=True,
        charged=booked,
        basis=basis,
        exposure=shown,
        unmetered=unmetered,
        exhausted=_overruns(moved),
    )


def settle_detailed(
    accounts: Sequence[BudgetAccount],
    reservation: BudgetReservation,
    actual: Decimal | None,
    policy: UnknownUsagePolicy,
    unknown_charge: Decimal,
    *,
    now: datetime,
    observed_floor: Decimal = _ZERO,
) -> SettleOutcome:
    """Close a reservation with the actual usage — always recorded, also above the reservation or the limit.

    ``actual is None`` is an unknown usage: ``charge_estimate`` charges ``unknown_charge`` (the reservation
    when it is 0), ``block`` charges the whole reservation and marks the run unmetered; either way the
    charge is at least ``observed_floor``, the measured part of a partial report. Replaying a closed
    reservation charges nothing again.
    """
    return _settle(
        accounts, reservation, actual, policy, unknown_charge, now=now, floor=observed_floor, exposure=None
    )


def settle(
    accounts: Sequence[BudgetAccount],
    reservation: BudgetReservation,
    actual: Decimal | None,
    policy: UnknownUsagePolicy,
    unknown_charge: Decimal,
    *,
    now: datetime,
    observed_floor: Decimal = _ZERO,
) -> tuple[tuple[BudgetAccount, ...], BudgetReservation]:
    outcome = settle_detailed(
        accounts, reservation, actual, policy, unknown_charge, now=now, observed_floor=observed_floor
    )
    return outcome.accounts, outcome.reservation


def settle_usage(
    accounts: Sequence[BudgetAccount],
    reservation: BudgetReservation,
    usage: UsageCharge,
    policy: UnknownUsagePolicy,
    unknown_charge: Decimal,
    *,
    now: datetime,
) -> SettleOutcome:
    """``settle`` from a step usage; the exposure keeps the truth (not a final bill)."""
    if usage.dimension is not reservation.dimension:
        raise ValueError("the usage belongs to another dimension than the reservation")
    return _settle(
        accounts,
        reservation,
        usage.actual,
        policy,
        unknown_charge,
        now=now,
        floor=usage.floor,
        exposure=usage.exposure,
    )


def release(
    accounts: Sequence[BudgetAccount], reservation: BudgetReservation, *, now: datetime
) -> tuple[tuple[BudgetAccount, ...], BudgetReservation]:
    """Free the reservation of a step whose runtime never started (K4); a closed one stays as is."""
    members = _members(accounts, reservation)
    if reservation.state != "reserved":
        return members, reservation
    freed: list[BudgetAccount] = []
    for account in members:
        if account.reserved < reservation.amount:
            raise ValueError(
                f"account {account.id} holds less than the reservation: the ledger is inconsistent"
            )
        freed.append(_bump(account, reserved=-reservation.amount))
    return tuple(freed), dataclasses.replace(reservation, state="released", settled_at=now)


def close_reservation(
    accounts: Sequence[BudgetAccount],
    reservation: BudgetReservation,
    *,
    runtime_started: bool,
    usage: UsageCharge | None,
    usage_so_far: UsageCharge | None,
    policy: UnknownUsagePolicy,
    unknown_charge: Decimal,
    now: datetime,
) -> SettleOutcome:
    """Close the reservation of a stage that ended without ``record_stage_result`` (K4).

    No ``runtime_started_at``: the runtime was never called, ``release``. Otherwise ``settle``: the usage the
    command sent, else the last ``usage_so_far``, else an unknown usage under the policy — a started step is
    never freed as if it cost nothing. A ``review_rounds`` round that started is spent (``settle(1)``).
    """
    if reservation.dimension not in RESERVED_DIMENSIONS:
        raise ValueError(f"{reservation.dimension.value} has no reservation")
    if not runtime_started:
        freed, closed = release(accounts, reservation, now=now)
        applied = closed.state == "released" and reservation.state == "reserved"
        return SettleOutcome(
            accounts=freed,
            reservation=closed,
            applied=applied,
            charged=_ZERO,
            basis="released" if applied else "none",
            exposure="unknown",
            unmetered=False,
            exhausted=(),
        )
    if reservation.dimension is BudgetDimension.REVIEW_ROUNDS:
        return _settle(
            accounts,
            reservation,
            Decimal(1),
            policy,
            unknown_charge,
            now=now,
            floor=_ZERO,
            exposure="finalized",
        )
    sources = [candidate for candidate in (usage, usage_so_far) if candidate is not None]
    for candidate in sources:
        if candidate.dimension is not reservation.dimension:
            raise ValueError("the usage belongs to another dimension than the reservation")
    # A terminal usage that is not a known total (partial report, undisclosed subagents, nothing measured)
    # is newer than an earlier estimate: it stays unknown, it does not give way to it even when its own floor
    # is 0; the policy applies and the largest measured part stays the floor (an estimate that was reported
    # earlier is measured too).
    terminal_unknown = usage is not None and usage.actual is None
    known = None if terminal_unknown else next((c for c in sources if c.actual is not None), None)
    if known is not None:
        return _settle(
            accounts,
            reservation,
            known.actual,
            policy,
            unknown_charge,
            now=now,
            floor=known.floor,
            exposure=known.exposure,
        )
    floor = max(
        (
            candidate.floor if candidate.actual is None else max(candidate.floor, candidate.actual)
            for candidate in sources
        ),
        default=_ZERO,
    )
    return _settle(accounts, reservation, None, policy, unknown_charge, now=now, floor=floor, exposure=None)
