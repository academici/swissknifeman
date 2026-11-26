"""Token counters and the per-message usage accumulator shared by the CLI runtime adapters.

Vendor cost fields are diagnostic only and never populate ``cost_usd_micros``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Final, cast

from skm.modules.runtimes.domain.usage import SubagentUsage, UsageReport, UsageStatus, unknown_usage

__all__ = ["nonneg_counter", "nonneg_counter_opt"]

MAX_COUNTER: Final = 2**63 - 1


def nonneg_counter(value: object) -> int:
    """Coerce valid non-negative integers; negative, bool, float, string or null become 0."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return min(value, MAX_COUNTER)


def nonneg_counter_opt(value: object) -> int | None:
    """Like ``nonneg_counter`` but an invalid value is unknown (``None``) rather than 0."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return min(value, MAX_COUNTER)


def _sum_opt(a: int | None, b: int | None) -> int | None:
    if a is None and b is None:
        return None
    return min(MAX_COUNTER, (a or 0) + (b or 0))


def _sum_cache(a: int | None, b: int | None) -> int | None:
    return None if a is None or b is None else min(MAX_COUNTER, a + b)


def _max_opt(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


@dataclass(frozen=True, slots=True)
class TokenCounts:
    """Normalized non-negative token counters for one message, turn or result."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None

    def add(self, other: TokenCounts) -> TokenCounts:
        return TokenCounts(
            input_tokens=min(MAX_COUNTER, self.input_tokens + other.input_tokens),
            output_tokens=min(MAX_COUNTER, self.output_tokens + other.output_tokens),
            cache_read_tokens=_sum_cache(self.cache_read_tokens, other.cache_read_tokens),
            cache_write_tokens=_sum_cache(self.cache_write_tokens, other.cache_write_tokens),
            reasoning_tokens=_sum_opt(self.reasoning_tokens, other.reasoning_tokens),
        )

    def max_with(self, other: TokenCounts) -> TokenCounts:
        return TokenCounts(
            input_tokens=max(self.input_tokens, other.input_tokens),
            output_tokens=max(self.output_tokens, other.output_tokens),
            cache_read_tokens=_max_opt(self.cache_read_tokens, other.cache_read_tokens),
            cache_write_tokens=_max_opt(self.cache_write_tokens, other.cache_write_tokens),
            reasoning_tokens=_max_opt(self.reasoning_tokens, other.reasoning_tokens),
        )

    def report(self, *, status: UsageStatus, source: str, subagents: SubagentUsage) -> UsageReport:
        return UsageReport(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens,
            reasoning_tokens=self.reasoning_tokens,
            cost_usd_micros=None,
            status=status,
            source=source,
            subagents=subagents,
        )


class MessageUsageAccumulator:
    """Per-message assistant usage (deduplicated by message id) plus cumulative result usage.

    A terminal result reports its usage; without one the summed message usage is an estimate for
    partial crash accounting, and without either the usage is unknown.
    """

    def __init__(
        self,
        normalize: Callable[[Mapping[str, object]], TokenCounts],
        *,
        subagent_tools: frozenset[str],
        result_source: str,
        delta_source: str,
        subagent_disclosed: bool = False,
    ) -> None:
        self._normalize = normalize
        self._subagent_tools = subagent_tools
        self._result_source = result_source
        self._delta_source = delta_source
        self._by_message_id: dict[str, TokenCounts] = {}
        self._anon_seq = 0
        self._result_counts = TokenCounts()
        self._has_result_usage = False
        self._subagent_seen = False
        self._subagent_disclosed = subagent_disclosed

    def mark_tool(self, tool_name: str) -> None:
        """Record a native subagent invocation."""
        if tool_name in self._subagent_tools:
            self._subagent_seen = True

    def record_assistant_usage(self, message_id: str | None, raw_usage: object) -> None:
        """Track ``message.usage`` deduplicated by ``message.id`` for partial crash accounting."""
        if not isinstance(raw_usage, Mapping):
            return
        counts = self._normalize(cast("Mapping[str, object]", raw_usage))
        if message_id:
            key = message_id
        else:
            self._anon_seq += 1
            key = f"_anon_{self._anon_seq}"
        previous = self._by_message_id.get(key)
        self._by_message_id[key] = counts if previous is None else previous.max_with(counts)

    def record_result_usage(self, raw_usage: object) -> UsageReport | None:
        """Accumulate terminal ``result.usage`` and return the cumulative ``UsageReport``."""
        if not isinstance(raw_usage, Mapping):
            return None
        counts = self._normalize(cast("Mapping[str, object]", raw_usage))
        self._result_counts = self._result_counts.add(counts) if self._has_result_usage else counts
        self._has_result_usage = True
        return self._report(self._result_counts, UsageStatus.REPORTED, self._result_source)

    def final_usage(self) -> UsageReport:
        """Return reported result usage, partial estimated message usage, or ``unknown_usage()``."""
        if self._has_result_usage:
            return self._report(self._result_counts, UsageStatus.REPORTED, self._result_source)
        if self._by_message_id:
            items = iter(self._by_message_id.values())
            total = next(items)
            for item in items:
                total = total.add(item)
            return self._report(total, UsageStatus.ESTIMATED, self._delta_source)
        base = unknown_usage()
        if self._subagent_seen:
            return replace(base, subagents=SubagentUsage(used=True, disclosed=False))
        return base

    def _report(self, counts: TokenCounts, status: UsageStatus, source: str) -> UsageReport:
        disclosed = self._subagent_disclosed if self._subagent_seen else False
        return counts.report(
            status=status,
            source=source,
            subagents=SubagentUsage(used=self._subagent_seen, disclosed=disclosed),
        )
