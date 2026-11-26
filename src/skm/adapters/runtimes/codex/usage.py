"""Codex JSONL token usage normalization and cumulative/partial turn accumulation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from skm.adapters.runtimes._cli_session.usage import TokenCounts, nonneg_counter, nonneg_counter_opt
from skm.modules.runtimes.domain.usage import (
    SubagentUsage,
    UsageReport,
    UsageStatus,
    unknown_usage,
)

__all__: list[str] = []

_CODEX_SUBAGENTS: Final = SubagentUsage(used=None, disclosed=False)


def normalize_usage_counts(raw: Mapping[str, object]) -> TokenCounts:
    """Map Codex ``usage`` fields onto SKM normalized token counters (Dossier §3.5).

    Codex reports ``cached_input_tokens`` as a subset included within ``input_tokens``:
    - ``cache_read_tokens = cached_input_tokens``
    - ``input_tokens = max(0, raw_input_tokens - cached_input_tokens)``
    Cache writes are unavailable in this stream.
    """
    raw_input = nonneg_counter(raw.get("input_tokens"))
    cached_input = nonneg_counter_opt(raw.get("cached_input_tokens"))
    output_tokens = nonneg_counter(raw.get("output_tokens"))
    reasoning = nonneg_counter_opt(
        raw.get("reasoning_output_tokens")
        if "reasoning_output_tokens" in raw
        else raw.get("reasoning_tokens")
    )
    return TokenCounts(
        input_tokens=raw_input if cached_input is None else max(0, raw_input - cached_input),
        output_tokens=output_tokens,
        cache_read_tokens=cached_input,
        reasoning_tokens=reasoning,
    )


class UsageAccumulator:
    """Tracks cumulative ``turn.completed`` usage and partial crash estimates across a Codex session."""

    def __init__(self) -> None:
        self._turn_counts = TokenCounts()
        self._has_turn_usage = False
        self._delta_counts = TokenCounts()
        self._has_delta_usage = False
        self._turn_open = False

    def start_turn(self) -> None:
        """Mark the beginning of a new turn."""
        self._turn_open = True

    def fail_turn(self) -> None:
        """Mark the current turn as failed without terminal usage."""
        self._turn_open = True

    def record_delta_usage(self, raw_usage: object) -> None:
        """Record mid-turn or item-level usage snapshot for partial crash preservation."""
        if not isinstance(raw_usage, Mapping):
            return
        counts = normalize_usage_counts(cast("Mapping[str, object]", raw_usage))
        self._delta_counts = self._delta_counts.max_with(counts) if self._has_delta_usage else counts
        self._has_delta_usage = True

    def record_turn_usage(self, raw_usage: object) -> UsageReport | None:
        """Record ``turn.completed`` cumulative usage and return a ``REPORTED`` ``UsageReport``."""
        self._turn_open = False
        if not isinstance(raw_usage, Mapping):
            return None
        counts = normalize_usage_counts(cast("Mapping[str, object]", raw_usage))
        if self._has_turn_usage:
            # Codex turn.completed counters are cumulative session totals; if a mocked fixture emits
            # per-turn smaller counters on turn 2, accumulate monotonically.
            if (
                counts.input_tokens >= self._turn_counts.input_tokens
                and counts.output_tokens >= self._turn_counts.output_tokens
                and (
                    counts.cache_read_tokens is None
                    or self._turn_counts.cache_read_tokens is None
                    or counts.cache_read_tokens >= self._turn_counts.cache_read_tokens
                )
            ):
                self._turn_counts = self._turn_counts.max_with(counts)
            else:
                self._turn_counts = self._turn_counts.add(counts)
        else:
            self._turn_counts = counts
        self._has_turn_usage = True
        self._delta_counts = TokenCounts()
        self._has_delta_usage = False
        return self._build_report(
            self._turn_counts,
            status=UsageStatus.REPORTED,
            source="stream:result",
        )

    def final_usage(self, *, completed: bool = True) -> UsageReport:
        """Return reported turn usage, partial estimated crash usage, or ``unknown_usage()``."""
        if self._has_turn_usage and completed and not self._turn_open:
            return self._build_report(
                self._turn_counts,
                status=UsageStatus.REPORTED,
                source="stream:result",
            )
        if self._has_turn_usage:
            combined = (
                self._turn_counts.max_with(self._delta_counts) if self._has_delta_usage else self._turn_counts
            )
            return self._build_report(
                combined,
                status=UsageStatus.ESTIMATED,
                source="stream:delta",
            )
        if self._has_delta_usage:
            return self._build_report(
                self._delta_counts,
                status=UsageStatus.ESTIMATED,
                source="stream:delta",
            )
        return unknown_usage()

    def _build_report(self, counts: TokenCounts, *, status: UsageStatus, source: str) -> UsageReport:
        return counts.report(status=status, source=source, subagents=_CODEX_SUBAGENTS)
