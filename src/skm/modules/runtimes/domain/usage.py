"""Normalized usage of a runtime session (runtimes §4.8, ``urn:skm:runtimes:usage-report:v1``).

Missing usage is ``None`` with ``status = unknown``, never zero. Money is integer USD micros; prices are
``Decimal`` from decimal strings of the catalog. ``fresh_tokens`` ports legacy ``orch`` usage accounting:
``input + output + cache_write``, cache reads re-count context every turn and are not fresh.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.runtimes.domain.catalog import Pricing

__all__ = [
    "SubagentUsage",
    "UsageReport",
    "UsageStatus",
    "cache_hit_rate",
    "cost",
    "estimate_from_prompt",
    "fresh_tokens",
    "merge_usage",
    "unknown_usage",
    "usage_from_json",
    "usage_to_json",
]

_MAX_COUNTER: Final = 2**63 - 1


class UsageStatus(StrEnum):
    REPORTED = "reported"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


# Worse status wins when two reports are combined.
_STATUS_RANK: Final = {UsageStatus.REPORTED: 0, UsageStatus.ESTIMATED: 1, UsageStatus.UNKNOWN: 2}


def _counter(value: object, name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int or None")
    if not 0 <= value <= _MAX_COUNTER:
        raise ValueError(f"{name} must be within 0..2**63-1")


@dataclass(frozen=True, slots=True)
class SubagentUsage:
    used: bool | None  # runtime reported native subagents (None: unknown)
    disclosed: bool  # their usage is included in the counters of this report

    def __post_init__(self) -> None:
        if self.used is not None and not isinstance(self.used, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("used must be bool or None")
        if not isinstance(self.disclosed, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("disclosed must be bool")


@dataclass(frozen=True, slots=True)
class UsageReport:
    """The only usage definition in the product (K9); execution DTOs ``$ref`` its schema."""

    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    reasoning_tokens: int | None
    cost_usd_micros: int | None  # computed by cost(), never taken from the runtime
    status: UsageStatus
    source: str  # "stream:result", "stream:delta", "estimate:prompt_chars", "none"
    subagents: SubagentUsage

    def __post_init__(self) -> None:
        for name in _COUNTERS:
            _counter(getattr(self, name), name)
        _counter(self.cost_usd_micros, "cost_usd_micros")
        object.__setattr__(self, "status", UsageStatus(self.status))
        if not isinstance(self.source, str) or not self.source:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("source must be a non-empty string")
        if not isinstance(self.subagents, SubagentUsage):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("subagents must be SubagentUsage")
        # unknown means nothing was measured: a zero would read as a measured absence of spend.
        if self.status is UsageStatus.UNKNOWN and not self.is_empty():
            raise ValueError("usage with status unknown carries no counters and no cost")

    def is_empty(self) -> bool:
        return self.cost_usd_micros is None and all(getattr(self, name) is None for name in _COUNTERS)


_COUNTERS: Final = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)


def unknown_usage(source: str = "none") -> UsageReport:
    """Usage of a session that reported nothing (§4.6 rule 2: the result always carries a report)."""
    return UsageReport(
        input_tokens=None,
        output_tokens=None,
        cache_read_tokens=None,
        cache_write_tokens=None,
        reasoning_tokens=None,
        cost_usd_micros=None,
        status=UsageStatus.UNKNOWN,
        source=source,
        subagents=SubagentUsage(used=None, disclosed=False),
    )


def _either_used(first: bool | None, second: bool | None) -> bool | None:
    if first is True or second is True:
        return True
    if first is None or second is None:
        return None
    return False


def _merge_subagents(acc: SubagentUsage, event: SubagentUsage, *, cumulative: bool) -> SubagentUsage:
    used = _either_used(acc.used, event.used)
    if cumulative:
        # The replacing total discloses subagents only if it knows about the ones seen earlier.
        disclosed = event.disclosed if used is not True or event.used is True else False
    else:
        disclosed = acc.disclosed and event.disclosed
    return SubagentUsage(used=used, disclosed=disclosed)


def _add(first: int | None, second: int | None) -> int | None:
    if first is None:
        return second
    if second is None:
        return first
    return first + second


_NO_SUBAGENT_FACTS: Final = SubagentUsage(used=None, disclosed=False)


def _is_neutral(report: UsageReport) -> bool:
    """No counters, no cost and no subagent facts: an accumulator that has seen nothing yet."""
    return (
        report.status is UsageStatus.UNKNOWN and report.is_empty() and report.subagents == _NO_SUBAGENT_FACTS
    )


def merge_usage(acc: UsageReport, event: UsageReport, *, cumulative: bool) -> UsageReport:
    """Fold one ``usage_reported`` into the running total: cumulative replaces, a delta adds.

    Subagent facts survive both forms. An unknown delta after measured usage makes the total ``estimated``
    (some spend is not counted); unknown is never folded in as zero. The initial accumulator without any
    facts (``unknown_usage()``) is neutral: the first report is kept whole, its subagent facts included.
    """
    if _is_neutral(acc):
        return event
    subagents = _merge_subagents(acc.subagents, event.subagents, cumulative=cumulative)
    if cumulative or acc.is_empty():
        return _replace(event, subagents=subagents)
    if event.is_empty():
        status = UsageStatus.ESTIMATED if acc.status is UsageStatus.REPORTED else acc.status
        return _replace(acc, status=status, subagents=subagents)
    status = max(acc.status, event.status, key=_STATUS_RANK.__getitem__)
    both_cost = acc.cost_usd_micros is not None and event.cost_usd_micros is not None
    return UsageReport(
        input_tokens=_add(acc.input_tokens, event.input_tokens),
        output_tokens=_add(acc.output_tokens, event.output_tokens),
        cache_read_tokens=_add(acc.cache_read_tokens, event.cache_read_tokens),
        cache_write_tokens=_add(acc.cache_write_tokens, event.cache_write_tokens),
        reasoning_tokens=_add(acc.reasoning_tokens, event.reasoning_tokens),
        cost_usd_micros=_add(acc.cost_usd_micros, event.cost_usd_micros) if both_cost else None,
        status=status,
        source=event.source,
        subagents=subagents,
    )


def _replace(
    report: UsageReport, *, subagents: SubagentUsage, status: UsageStatus | None = None
) -> UsageReport:
    return UsageReport(
        input_tokens=report.input_tokens,
        output_tokens=report.output_tokens,
        cache_read_tokens=report.cache_read_tokens,
        cache_write_tokens=report.cache_write_tokens,
        reasoning_tokens=report.reasoning_tokens,
        cost_usd_micros=report.cost_usd_micros,
        status=report.status if status is None else status,
        source=report.source,
        subagents=subagents,
    )


def cost(usage: UsageReport, pricing: Pricing | None) -> int | None:
    """Cost in USD micros, rounded up (ROUND_CEILING).

    ``None`` without pricing, when input or output is unknown, or when cache tokens were spent at a price the
    catalog does not state: an unpriced part is unknown, not free.
    """
    if pricing is None or usage.input_tokens is None or usage.output_tokens is None:
        return None
    parts = [
        (usage.input_tokens, pricing.input_per_mtok_usd),
        (usage.output_tokens, pricing.output_per_mtok_usd),
        (usage.cache_read_tokens, pricing.cache_read_per_mtok_usd),
        (usage.cache_write_tokens, pricing.cache_write_per_mtok_usd),
    ]
    total = Decimal(0)
    for tokens, price in parts:
        if not tokens:
            continue
        if price is None:
            return None
        # USD per million tokens times tokens is exactly micro-USD.
        total += Decimal(tokens) * price
    return int(total.to_integral_value(rounding=ROUND_CEILING))


def cache_hit_rate(usage: UsageReport) -> float | None:
    """Share of cache traffic served by reads, when both cache counters are available."""
    reads, writes = usage.cache_read_tokens, usage.cache_write_tokens
    if reads is None or writes is None or reads + writes == 0:
        return None
    return reads / (reads + writes)


def fresh_tokens(usage: UsageReport) -> int | None:
    """``input + output + cache_write`` for the token budget; cache reads are not fresh; unknown is None."""
    if usage.input_tokens is None or usage.output_tokens is None:
        return None
    return usage.input_tokens + usage.output_tokens + (usage.cache_write_tokens or 0)


def estimate_from_prompt(prompt_tokens: int, output_tokens_guess: int) -> UsageReport:
    """An ``estimated`` report used for budget reservation before a session reports usage."""
    return UsageReport(
        input_tokens=prompt_tokens,
        output_tokens=output_tokens_guess,
        cache_read_tokens=None,
        cache_write_tokens=None,
        reasoning_tokens=None,
        cost_usd_micros=None,
        status=UsageStatus.ESTIMATED,
        source="estimate:prompt_chars",
        subagents=SubagentUsage(used=None, disclosed=False),
    )


def usage_to_json(usage: UsageReport) -> JsonObject:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cost_usd_micros": usage.cost_usd_micros,
        "status": usage.status.value,
        "source": usage.source,
        "subagents": {"used": usage.subagents.used, "disclosed": usage.subagents.disclosed},
    }


def usage_from_json(data: Mapping[str, JsonValue]) -> UsageReport:
    """Decode a schema-shaped document; ``__post_init__`` re-checks every field type."""
    subagents = data["subagents"]
    if not isinstance(subagents, Mapping):
        raise TypeError("subagents must be an object")
    return UsageReport(
        input_tokens=cast("int | None", data["input_tokens"]),
        output_tokens=cast("int | None", data["output_tokens"]),
        cache_read_tokens=cast("int | None", data["cache_read_tokens"]),
        cache_write_tokens=cast("int | None", data["cache_write_tokens"]),
        reasoning_tokens=cast("int | None", data["reasoning_tokens"]),
        cost_usd_micros=cast("int | None", data["cost_usd_micros"]),
        status=UsageStatus(cast("str", data["status"])),
        source=cast("str", data["source"]),
        subagents=SubagentUsage(
            used=cast("bool | None", subagents["used"]), disclosed=cast("bool", subagents["disclosed"])
        ),
    )
