"""Classify provider HTTP 429 evidence before waiting or changing accounts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["RateLimitAction", "RateLimitDecision", "classify_rate_limit"]

_QUOTA_MARKERS = ("session limit", "weekly limit", "quota exceeded", "insufficient credits")
_DEFAULT_COOLDOWN_S = 60


class RateLimitAction(StrEnum):
    WAIT_SAME_SLOT = "wait_same_slot"
    ROTATE_SLOT = "rotate_slot"


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    action: RateLimitAction
    wait_s: float = 0
    cooldown_until: datetime | None = None
    is_quota_exhausted: bool = False


def _numeric(value: str | int | float | None) -> float | None:
    try:
        number = float(value) if value is not None and not isinstance(value, bool) else -1
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _future_date(value: datetime | str | None, now: datetime) -> datetime | None:
    try:
        if isinstance(value, str):
            if (timestamp := _numeric(value)) is not None:
                value = datetime.fromtimestamp(timestamp, tz=UTC)
            else:
                try:
                    value = datetime.fromisoformat(value)
                except ValueError:
                    value = parsedate_to_datetime(value)
    except (ValueError, OverflowError, OSError):
        return None
    return value if value is not None and value.tzinfo is not None and value > now else None


def _quota_signal(headers: Mapping[str, str], message: str) -> bool:
    return (
        headers.get("anthropic-ratelimit-unified-status", "").strip().casefold() == "rejected"
        or any(
            name.startswith("anthropic-ratelimit-unified-")
            and name.endswith("-utilization")
            and (_numeric(value) or 0) >= 1
            for name, value in headers.items()
        )
        or any(marker in message.casefold() for marker in _QUOTA_MARKERS)
    )


def classify_rate_limit(  # noqa: PLR0913 - bounded retry state and independent provider evidence
    http_status: int | None,
    *,
    now: datetime,
    headers: Mapping[str, str] | None = None,
    message: str = "",
    retry_after: float | str | None = None,
    reset_at: datetime | str | None = None,
    attempt: int = 1,
    total_wait_s: float = 0,
    burst_max_s: float = 60,
    max_total_wait_s: float = 60,
    max_attempts: int = 3,
) -> RateLimitDecision | None:
    """Classify a failed attempt (one-based), with explicit quota taking precedence over Retry-After."""
    if http_status != 429:
        return None
    if (
        now.tzinfo is None
        or min(attempt, max_attempts) < 1
        or any(not math.isfinite(n) or n < 0 for n in (total_wait_s, burst_max_s, max_total_wait_s))
    ):
        raise ValueError("invalid rate limit retry budget")
    response = {key.casefold(): value for key, value in (headers or {}).items()}
    quota = _quota_signal(response, message)
    reset = reset_at if reset_at is not None else response.get("anthropic-ratelimit-unified-reset")
    if not quota and attempt < max_attempts:
        raw_delay = retry_after if retry_after is not None else response.get("retry-after")
        delay = _numeric(raw_delay)
        if delay is None and isinstance(raw_delay, str) and (date := _future_date(raw_delay, now)):
            delay = (date - now).total_seconds()
        burst = delay is not None and delay <= burst_max_s
        budget = max_total_wait_s - total_wait_s
        if burst and delay is not None and 0 <= delay <= budget:
            return RateLimitDecision(RateLimitAction.WAIT_SAME_SLOT, wait_s=delay)
        if not burst and attempt == 1 and budget > 0 and burst_max_s > 0:
            return RateLimitDecision(
                RateLimitAction.WAIT_SAME_SLOT, wait_s=min(delay or 5, burst_max_s, budget)
            )
    return RateLimitDecision(
        RateLimitAction.ROTATE_SLOT,
        cooldown_until=_future_date(reset, now) or now + timedelta(seconds=_DEFAULT_COOLDOWN_S),
        is_quota_exhausted=quota,
    )
