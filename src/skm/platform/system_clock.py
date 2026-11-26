"""System time sources (kernel-platform §3.1). The only place that reads the wall clock."""

import time
from datetime import UTC, datetime

__all__ = ["SystemClock", "SystemMonotonic"]


class SystemClock:
    """``Clock`` on the system wall clock: timezone-aware UTC, microseconds kept."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class SystemMonotonic:
    """``Monotonic`` on ``time.monotonic()``; only for durations and timeouts."""

    def monotonic(self) -> float:
        return time.monotonic()
