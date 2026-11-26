"""Normalize Gemini CLI's cumulative stream result statistics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from skm.adapters.runtimes._cli_session.usage import nonneg_counter_opt
from skm.modules.runtimes.domain.usage import SubagentUsage, UsageReport, UsageStatus, unknown_usage

__all__ = ["parse_usage"]


def parse_usage(raw: object) -> UsageReport:
    if not isinstance(raw, Mapping):
        return unknown_usage()
    stats = cast("Mapping[str, object]", raw)
    prompt = nonneg_counter_opt(stats.get("input_tokens"))
    output = nonneg_counter_opt(stats.get("output_tokens"))
    cached = nonneg_counter_opt(stats.get("cached"))

    # Newer streams report fresh input directly. Older streams can omit the cache split.
    fresh = nonneg_counter_opt(stats.get("input"))
    if fresh is None and prompt is not None and cached is not None and prompt >= cached:
        fresh = prompt - cached
    if fresh is None and output is None and cached is None:
        return unknown_usage()
    return UsageReport(
        input_tokens=fresh,
        output_tokens=output,
        cache_read_tokens=cached,
        cache_write_tokens=None,
        reasoning_tokens=None,
        cost_usd_micros=None,
        status=UsageStatus.REPORTED,
        source="stream:result",
        subagents=SubagentUsage(used=None, disclosed=False),
    )
