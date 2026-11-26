"""Grok streaming-messages-json token usage normalization and turn accumulation."""

from __future__ import annotations

from collections.abc import Mapping

from skm.adapters.runtimes._cli_session.usage import (
    MessageUsageAccumulator,
    TokenCounts,
    nonneg_counter,
    nonneg_counter_opt,
)

__all__: list[str] = []


def normalize_usage_counts(raw: Mapping[str, object]) -> TokenCounts:
    """Map Grok ``streaming-messages-json`` ``usage`` fields onto SKM normalized token counters.

    Vendor ``total_cost_usd`` / ``costUSD`` are diagnostic only and never populate ``cost_usd_micros``.
    """
    return TokenCounts(
        input_tokens=nonneg_counter(raw.get("input_tokens")),
        output_tokens=nonneg_counter(raw.get("output_tokens")),
        cache_read_tokens=nonneg_counter_opt(raw.get("cache_read_input_tokens")),
        cache_write_tokens=nonneg_counter_opt(raw.get("cache_creation_input_tokens")),
        reasoning_tokens=nonneg_counter_opt(raw.get("reasoning_tokens")),
    )


class UsageAccumulator(MessageUsageAccumulator):
    """Grok session usage; ``spawn_subagent`` and ``Task`` are the native subagents."""

    def __init__(self, *, subagent_disclosed: bool = False) -> None:
        super().__init__(
            normalize_usage_counts,
            subagent_tools=frozenset({"spawn_subagent", "Task"}),
            result_source="grok.stream",
            delta_source="grok.stream",
            subagent_disclosed=subagent_disclosed,
        )
