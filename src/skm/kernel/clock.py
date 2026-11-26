"""Time sources (kernel-platform §2.8).

Implementations live in ``platform/system_clock.py`` and in test fakes.
"""

from datetime import datetime
from typing import Protocol

__all__ = ["Clock", "Monotonic"]


class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware UTC; microseconds are kept."""
        ...


class Monotonic(Protocol):
    def monotonic(self) -> float:
        """Seconds, only for durations and timeouts."""
        ...
