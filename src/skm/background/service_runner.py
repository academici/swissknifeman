"""Cooperative, threaded background lifecycle (kernel-platform §6).

Intervals and delays are seconds. Services keep ``tick()`` argument-free and receive
the runner's shared cancellation token at composition time. Python cannot kill a hung
thread: a shutdown timeout reports its name and retains it for a subsequent join.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from threading import RLock, Thread, current_thread
from typing import Protocol

from skm.kernel.cancel import Cancelled, CancelSource, CancelToken
from skm.kernel.clock import Clock, Monotonic
from skm.platform.logging.logger import StructLogger
from skm.platform.system_clock import SystemMonotonic

__all__ = ["BackgroundService", "ServiceHealth", "ServiceRunner", "TickResult"]


@dataclass(frozen=True, slots=True)
class TickResult:
    processed: int
    next_delay_seconds: float | None = None

    def __post_init__(self) -> None:
        if type(self.processed) is not int or self.processed < 0:
            raise ValueError("processed must be a non-negative integer")
        if self.next_delay_seconds is not None:
            _duration(self.next_delay_seconds, positive=False)


class BackgroundService(Protocol):
    name: str

    def tick(self) -> TickResult: ...


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    last_ok_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    stale: bool


def _duration(value: float, *, positive: bool) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError("duration must be finite and positive" if positive else "invalid delay or timeout")
    return float(value)


def _tick_result(value: object) -> TickResult:
    if not isinstance(value, TickResult):
        raise TypeError("background tick must return TickResult")
    return value


@dataclass(slots=True)
class _State:
    service: BackgroundService
    interval: float
    batch_limit: int | None
    last_ok_at: datetime | None = None
    last_ok_monotonic: float | None = None
    last_error: str | None = None
    consecutive_failures: int = 0


class ServiceRunner:
    """One non-daemon thread per service; start once, stop/join safely more than once.

    ``clock`` supplies UTC observation timestamps; ``monotonic`` alone supplies age
    and shutdown budgets. A service with no successful tick is stale. Health exposes
    exception types, never potentially secret exception messages. ``batch_limits``
    enables immediate draining; other services can request a zero next delay directly.
    """

    def __init__(
        self,
        services: Sequence[BackgroundService],
        *,
        intervals: Mapping[str, float],
        clock: Clock,
        log: StructLogger,
        monotonic: Monotonic | None = None,
        cancel_source: CancelSource | None = None,
        batch_limits: Mapping[str, int] | None = None,
    ) -> None:
        self._clock = clock
        self._log = log
        self._monotonic = monotonic if monotonic is not None else SystemMonotonic()
        self._cancel_source = cancel_source if cancel_source is not None else CancelSource()
        self._lock = RLock()
        self._states: dict[str, _State] = {}
        limits = dict(batch_limits or {})
        for service in services:
            name = service.name
            if not name or name in self._states:
                raise ValueError(f"empty or duplicate background service name: {name!r}")
            interval = _duration(intervals[name], positive=True)
            limit = limits.get(name)
            if limit is not None and (type(limit) is not int or limit <= 0):
                raise ValueError(f"invalid batch limit for {name!r}")
            self._states[name] = _State(service, interval, limit)
        if limits.keys() - self._states.keys():
            raise ValueError("batch limits reference unknown services")
        self._threads: dict[str, Thread] = {}
        self._terminal_errors: list[BaseException] = []
        self._started = False
        self._closed = False

    @property
    def cancel(self) -> CancelToken:
        return self._cancel_source.token

    def request_stop(self, reason: str = "shutdown") -> None:
        """Cancel ticks and wake interval/backoff waits without joining threads."""
        self._cancel_source.cancel(reason)

    def start(self) -> None:
        try:
            with self._lock:
                if self._closed:
                    raise RuntimeError("a stopped ServiceRunner cannot restart")
                if self._started:
                    return
                self.cancel.raise_if_cancelled()
                self._started = True
                for name, state in self._states.items():
                    thread = self._new_thread(name, state)
                    thread.start()
                    self._threads[name] = thread
        except BaseException as primary:
            if isinstance(primary, Cancelled):
                self.request_stop(primary.reason)
            try:
                self.stop()
            except BaseException as cleanup:  # noqa: BLE001 - retain the startup exception
                primary.add_note(f"background startup cleanup failed: {cleanup!r}")
            raise

    def _new_thread(self, name: str, state: _State) -> Thread:
        return Thread(target=self._run, args=(name, state), name=f"skm.background.{name}", daemon=False)

    def stop(self, *, timeout_seconds: float = 30.0) -> None:
        deadline = self._monotonic.monotonic() + _duration(timeout_seconds, positive=False)
        self.request_stop()
        with self._lock:
            self._closed = True
            threads = tuple(self._threads.items())
        errors: list[BaseException] = []
        for _name, thread in threads:
            if thread is current_thread():
                continue  # cancellation is effective, but this thread cannot join itself
            try:
                thread.join(max(0.0, deadline - self._monotonic.monotonic()))
            except BaseException as error:  # noqa: BLE001 - finish joins before propagating
                errors.append(error)  # still attempt every other join
        alive = [name for name, thread in threads if thread.is_alive()]
        if alive:
            errors.append(TimeoutError(f"background shutdown deadline exceeded: {', '.join(alive)}"))
        with self._lock:
            errors.extend(self._terminal_errors)
            self._terminal_errors.clear()
        if errors:
            primary, *secondary = errors
            for error in secondary:
                primary.add_note(f"secondary background shutdown failure: {error!r}")
            raise primary

    def health(self) -> Mapping[str, ServiceHealth]:
        with self._lock:
            now = self._monotonic.monotonic()
            return {
                name: ServiceHealth(
                    state.last_ok_at,
                    state.last_error,
                    state.consecutive_failures,
                    state.last_ok_monotonic is None or now - state.last_ok_monotonic > 3 * state.interval,
                )
                for name, state in self._states.items()
            }

    def _run(self, name: str, state: _State) -> None:
        try:
            self._loop(name, state)
        except BaseException as error:  # noqa: BLE001 - transfer fatal thread errors to the owner
            # Fatal thread/clock/logger errors must reach the owner at stop(), rather
            # than disappearing through threading.excepthook while shutdown looks OK.
            with self._lock:
                state.last_error = type(error).__name__
                self._terminal_errors.append(error)

    def _loop(self, name: str, state: _State) -> None:
        backoff = min(state.interval, 60.0)
        while not self.cancel.cancelled:
            try:
                result = _tick_result(state.service.tick())
                ok_at = self._clock.now()
                ok_monotonic = self._monotonic.monotonic()
            except Exception as error:  # noqa: BLE001 - isolate service failures and retry
                if isinstance(error, Cancelled) and self.cancel.cancelled:
                    return  # only cancellation of this runner ends the service
                with self._lock:
                    state.last_error = type(error).__name__
                    state.consecutive_failures += 1
                backoff = min(backoff * 2, 60.0)
                delay = backoff
                try:
                    self._log.error("background.tick.failed", exc=error, service=name)
                except BaseException as logging_error:
                    error.add_note(f"background failure logging failed: {logging_error!r}")
                    raise error from logging_error
            else:
                with self._lock:
                    state.last_ok_at = ok_at
                    state.last_ok_monotonic = ok_monotonic
                    state.last_error = None
                    state.consecutive_failures = 0
                backoff = min(state.interval, 60.0)
                delay = state.interval if result.next_delay_seconds is None else result.next_delay_seconds
                if state.batch_limit is not None and result.processed == state.batch_limit:
                    delay = 0.0
            if self.cancel.wait(delay):
                return
