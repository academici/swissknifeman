"""Deterministic time sources for tests (ports: ``skm.kernel.clock``)."""

from datetime import UTC, datetime, timedelta

__all__ = ["FakeMonotonic", "FrozenClock"]

DEFAULT_START = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)


class FrozenClock:
    """``Clock`` that returns a fixed instant until a test moves it, forward or backward."""

    def __init__(self, start: datetime = DEFAULT_START) -> None:
        self._now = self._checked(start)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def set(self, value: datetime) -> None:
        self._now = self._checked(value)

    @staticmethod
    def _checked(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("FrozenClock needs a timezone-aware UTC datetime")
        return value


class FakeMonotonic:
    """``Monotonic`` that only moves when a test advances it."""

    def __init__(self, start: float = 0.0) -> None:
        self._value = start

    def monotonic(self) -> float:
        return self._value

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("a monotonic clock cannot go backwards")
        self._value += seconds
