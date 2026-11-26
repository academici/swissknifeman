"""Lifecycle regressions use cancellation/clock ports and explicit thread handshakes."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import timedelta
from threading import Event, Thread, current_thread
from typing import override

import pytest

from fakes.clock import FakeMonotonic, FrozenClock
from skm.background.service_runner import ServiceHealth, ServiceRunner, TickResult
from skm.kernel.cancel import Cancelled, CancelSource, CancelToken
from skm.platform.logging.logger import StructLogger


class RecordingLogger(StructLogger):
    def __init__(self) -> None:
        super().__init__("background.runner")
        self.errors: list[tuple[str, BaseException | None, dict[str, object]]] = []

    @override
    def error(self, event: str, /, *, exc: BaseException | None = None, **fields: object) -> None:
        self.errors.append((event, exc, fields))


class Service:
    def __init__(self, name: str, tick: Callable[[], TickResult]) -> None:
        self.name = name
        self.tick = tick


class AdvancingToken:
    """A CancelToken fake: waits advance duration and then call an observation hook."""

    def __init__(self, source: CancelSource, clock: FakeMonotonic, passes: int) -> None:
        self.source = source
        self.clock = clock
        self.passes = passes
        self.delays: list[float] = []
        self.observe: Callable[[], None] = lambda: None

    @property
    def cancelled(self) -> bool:
        return self.source.token.cancelled

    @property
    def reason(self) -> str | None:
        return self.source.token.reason

    def raise_if_cancelled(self) -> None:
        self.source.token.raise_if_cancelled()

    def wait(self, timeout_seconds: float) -> bool:
        self.delays.append(timeout_seconds)
        self.observe()
        self.clock.advance(timeout_seconds)
        if len(self.delays) == self.passes:
            self.source.cancel("test_complete")
        return self.cancelled


class AdvancingSource(CancelSource):
    def __init__(self, clock: FakeMonotonic, passes: int) -> None:
        super().__init__()
        self.native = CancelSource()
        self.view = AdvancingToken(self.native, clock, passes)

    @property
    @override
    def token(self) -> CancelToken:
        return self.view

    @override
    def cancel(self, reason: str) -> None:
        self.native.cancel(reason)


def test_failure_backoff_recovery_and_override_on_non_daemon_thread() -> None:
    wall, mono, log = FrozenClock(), FakeMonotonic(), RecordingLogger()
    source = AdvancingSource(mono, passes=5)
    first_error = RuntimeError("secret must not be exposed by health")
    actions = iter([first_error, ValueError("invalid"), TickResult(2, 0.25), first_error, TickResult(0)])
    threads: list[Thread] = []

    def tick() -> TickResult:
        threads.append(current_thread())
        action = next(actions)
        if isinstance(action, Exception):
            raise action
        return action

    runner = ServiceRunner(
        [Service("demo", tick)],
        intervals={"demo": 0.5},
        clock=wall,
        log=log,
        monotonic=mono,
        cancel_source=source,
    )
    snapshots: list[ServiceHealth] = []
    source.view.observe = lambda: snapshots.append(runner.health()["demo"])
    assert runner.health()["demo"] == ServiceHealth(None, None, 0, True)
    runner.start()
    try:
        threads_from_runner = list(runner._threads.values())
        for thread in threads_from_runner:
            thread.join(1)
            assert not thread.is_alive()
    finally:
        runner.stop()
    assert source.view.delays == [1.0, 2.0, 0.25, 1.0, 0.5]
    assert [s.consecutive_failures for s in snapshots] == [1, 2, 0, 1, 0]
    assert [s.last_error for s in snapshots] == ["RuntimeError", "ValueError", None, "RuntimeError", None]
    assert snapshots[2].last_ok_at == wall.now()
    assert not snapshots[2].stale
    assert len({id(t) for t in threads}) == 1
    assert threads[0] is not current_thread()
    assert not threads[0].daemon
    assert not threads[0].is_alive()
    assert [entry[0] for entry in log.errors] == ["background.tick.failed"] * 3
    assert log.errors[0][1] is first_error
    assert log.errors[0][2] == {"service": "demo"}


def test_backoff_is_bounded_even_after_more_than_a_thousand_failures() -> None:
    mono = FakeMonotonic()
    source = AdvancingSource(mono, passes=1100)

    def fail() -> TickResult:
        raise RuntimeError("unavailable")

    runner = ServiceRunner(
        [Service("demo", fail)],
        intervals={"demo": 1},
        clock=FrozenClock(),
        log=RecordingLogger(),
        monotonic=mono,
        cancel_source=source,
    )
    runner.start()
    for thread in runner._threads.values():
        thread.join(2)
    runner.stop()
    assert source.view.delays[:7] == [2, 4, 8, 16, 32, 60, 60]
    assert max(source.view.delays) == 60
    assert runner.health()["demo"].consecutive_failures == 1100


def test_full_batch_runs_immediately_then_returns_to_catalog_interval() -> None:
    mono = FakeMonotonic()
    source = AdvancingSource(mono, passes=3)
    results = iter([TickResult(10, 99), TickResult(1, 0), TickResult(0)])
    runner = ServiceRunner(
        [Service("demo", lambda: next(results))],
        intervals={"demo": 3},
        clock=FrozenClock(),
        log=RecordingLogger(),
        monotonic=mono,
        cancel_source=source,
        batch_limits={"demo": 10},
    )
    runner.start()
    for thread in runner._threads.values():
        thread.join(1)
    runner.stop()
    assert source.view.delays == [0, 0, 3]


def test_stale_uses_monotonic_age_even_if_utc_jumps_in_both_directions() -> None:
    wall, mono = FrozenClock(), FakeMonotonic()
    source = AdvancingSource(mono, passes=1)
    runner = ServiceRunner(
        [Service("demo", lambda: TickResult(0))],
        intervals={"demo": 2},
        clock=wall,
        log=RecordingLogger(),
        monotonic=mono,
        cancel_source=source,
    )
    runner.start()
    for thread in runner._threads.values():
        thread.join(1)
    runner.stop()
    snapshot = runner.health()["demo"]
    observed = snapshot.last_ok_at
    wall.advance(timedelta(days=100))
    assert not runner.health()["demo"].stale
    mono.advance(4)  # exactly three intervals since success
    assert not runner.health()["demo"].stale
    wall.advance(timedelta(days=-200))
    mono.advance(0.01)
    assert runner.health()["demo"].stale
    assert runner.health()["demo"].last_ok_at == observed
    assert not snapshot.stale
    with pytest.raises(FrozenInstanceError):
        snapshot.stale = True  # type: ignore[misc]


@pytest.mark.parametrize("fail", [False, True])
def test_stop_interrupts_idle_and_backoff_and_start_is_idempotent(fail: bool) -> None:
    entered = Event()
    calls: list[Thread] = []

    def tick() -> TickResult:
        calls.append(current_thread())
        entered.set()
        if fail:
            raise RuntimeError("fail")
        return TickResult(0)

    runner = ServiceRunner(
        [Service("demo", tick)], intervals={"demo": 3600}, clock=FrozenClock(), log=RecordingLogger()
    )
    runner.start()
    runner.start()
    try:
        assert entered.wait(1)
    finally:
        runner.stop(timeout_seconds=1)
    runner.stop(timeout_seconds=0)
    assert len(calls) == 1
    assert all(not t.is_alive() for t in calls)
    with pytest.raises(RuntimeError, match="cannot restart"):
        runner.start()


def test_stop_cancels_cooperative_tick_without_failure_or_success() -> None:
    source = CancelSource()
    entered = Event()

    def tick() -> TickResult:
        entered.set()
        source.token.wait(3600)
        source.token.raise_if_cancelled()
        raise AssertionError("tick must be cancelled")

    log = RecordingLogger()
    runner = ServiceRunner(
        [Service("demo", tick)],
        intervals={"demo": 1},
        clock=FrozenClock(),
        log=log,
        cancel_source=source,
    )
    runner.start()
    try:
        assert entered.wait(1)
    finally:
        runner.stop(timeout_seconds=1)
    assert runner.cancel.reason == "shutdown"
    assert runner.health()["demo"] == ServiceHealth(None, None, 0, True)
    assert not log.errors
    assert all(not t.is_alive() for t in runner._threads.values())


def test_hung_ticks_report_all_names_and_remain_joinable_after_deadline() -> None:
    release = Event()
    entered = [Event(), Event()]

    def tick(event: Event) -> TickResult:
        event.set()
        release.wait()
        return TickResult(0)

    runner = ServiceRunner(
        [Service("a", lambda: tick(entered[0])), Service("b", lambda: tick(entered[1]))],
        intervals={"a": 1, "b": 1},
        clock=FrozenClock(),
        log=RecordingLogger(),
        monotonic=FakeMonotonic(),
    )
    runner.start()
    try:
        assert all(e.wait(1) for e in entered)
        with pytest.raises(TimeoutError, match="a, b"):
            runner.stop(timeout_seconds=0)
        assert runner.cancel.cancelled
        assert all(t.is_alive() for t in runner._threads.values())
        assert all(h.stale for h in runner.health().values())
    finally:
        release.set()
        runner.stop(timeout_seconds=1)
    assert all(not t.is_alive() for t in runner._threads.values())


def test_parent_cancellation_wakes_services_and_precancelled_start_does_not_tick() -> None:
    parent = CancelSource()
    source = CancelSource(parent=parent.token)
    entered = Event()
    runner = ServiceRunner(
        [Service("demo", lambda: (entered.set(), TickResult(0))[1])],
        intervals={"demo": 3600},
        clock=FrozenClock(),
        log=RecordingLogger(),
        cancel_source=source,
    )
    runner.start()
    try:
        assert entered.wait(1)
        parent.cancel("signal")
        for thread in runner._threads.values():
            thread.join(1)
            assert not thread.is_alive()
    finally:
        runner.stop()
    assert runner.cancel.reason == "signal"

    unused = ServiceRunner(
        [Service("demo", lambda: pytest.fail("cancelled runner must not tick"))],
        intervals={"demo": 1},
        clock=FrozenClock(),
        log=RecordingLogger(),
        cancel_source=source,
    )
    with pytest.raises(Cancelled, match="signal"):
        unused.start()
    assert not unused._threads


def test_fatal_thread_error_is_returned_to_owner_after_all_threads_join() -> None:
    class Fatal(BaseException):
        pass

    original = Fatal("terminal")
    entered = Event()

    def tick() -> TickResult:
        entered.set()
        raise original

    runner = ServiceRunner(
        [Service("fatal", tick)], intervals={"fatal": 1}, clock=FrozenClock(), log=RecordingLogger()
    )
    runner.start()
    assert entered.wait(1)
    with pytest.raises(Fatal) as caught:
        runner.stop()
    assert caught.value is original
    assert all(not t.is_alive() for t in runner._threads.values())
    runner.stop()


@pytest.mark.parametrize("delay", [-1, float("nan"), float("inf"), True])
def test_invalid_intervals_and_delays_are_rejected_before_start(delay: float) -> None:
    with pytest.raises(ValueError, match="invalid delay"):
        TickResult(0, delay)
    with pytest.raises(ValueError, match="finite and positive"):
        ServiceRunner(
            [Service("demo", lambda: TickResult(0))],
            intervals={"demo": delay},
            clock=FrozenClock(),
            log=RecordingLogger(),
        )


def test_invalid_names_limits_counts_and_zero_interval_are_rejected() -> None:
    service = Service("demo", lambda: TickResult(0))
    for services, intervals, limits in [
        ([service, service], {"demo": 1}, {}),
        ([Service("", service.tick)], {"": 1}, {}),
        ([service], {"demo": 0}, {}),
        ([service], {"demo": 1}, {"demo": 0}),
        ([service], {"demo": 1}, {"demo": True}),
        ([service], {"demo": 1}, {"unknown": 1}),
    ]:
        with pytest.raises(ValueError, match=r"name|duration|batch limit"):
            ServiceRunner(
                services,
                intervals=intervals,
                batch_limits=limits,
                clock=FrozenClock(),
                log=RecordingLogger(),
            )
    with pytest.raises(KeyError):
        ServiceRunner([service], intervals={}, clock=FrozenClock(), log=RecordingLogger())
    for processed in (-1, True, 1.5):
        with pytest.raises(ValueError, match="processed"):
            TickResult(processed)  # type: ignore[arg-type]


def test_empty_runner_and_invalid_stop_deadline() -> None:
    runner = ServiceRunner([], intervals={}, clock=FrozenClock(), log=RecordingLogger())
    assert runner.health() == {}
    runner.start()
    for timeout in (-1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="invalid delay or timeout"):
            runner.stop(timeout_seconds=timeout)
    runner.stop(timeout_seconds=0)


class JoinThread(Thread):
    """Thread port fake with deterministic duration and startup/cleanup outcomes."""

    def __init__(self, mono: FakeMonotonic, *, hung: bool = True, fail_start: bool = False) -> None:
        super().__init__(daemon=False)
        self.mono = mono
        self.hung = hung
        self.fail_start = fail_start
        self.alive = False
        self.timeouts: list[float | None] = []

    @override
    def start(self) -> None:
        if self.fail_start:
            raise OSError("no thread resources")
        self.alive = True

    @override
    def join(self, timeout: float | None = None) -> None:
        self.timeouts.append(timeout)
        if self.hung:
            assert timeout is not None
            self.mono.advance(timeout)
        else:
            self.alive = False

    @override
    def is_alive(self) -> bool:
        return self.alive


class ThreadPortRunner(ServiceRunner):
    threads: dict[str, JoinThread]

    @override
    def _new_thread(self, name: str, state: object) -> Thread:
        return self.threads[name]


def test_shutdown_deadline_is_shared_across_all_thread_joins() -> None:
    mono = FakeMonotonic()
    runner = ThreadPortRunner(
        [Service("a", lambda: TickResult(0)), Service("b", lambda: TickResult(0))],
        intervals={"a": 1, "b": 1},
        clock=FrozenClock(),
        log=RecordingLogger(),
        monotonic=mono,
    )
    a, b = JoinThread(mono), JoinThread(mono)
    runner.threads = {"a": a, "b": b}
    runner.start()
    with pytest.raises(TimeoutError, match="a, b"):
        runner.stop(timeout_seconds=2)
    assert a.timeouts == [2]
    assert b.timeouts == [0]
    assert mono.monotonic() == 2
    a.hung = b.hung = False
    runner.stop(timeout_seconds=0)
    assert not a.is_alive()
    assert not b.is_alive()


@pytest.mark.parametrize("hung", [False, True])
def test_failed_thread_start_cleans_up_partial_start_and_retains_secondary_failure(hung: bool) -> None:
    mono = FakeMonotonic()
    runner = ThreadPortRunner(
        [Service("a", lambda: TickResult(0)), Service("b", lambda: TickResult(0))],
        intervals={"a": 1, "b": 1},
        clock=FrozenClock(),
        log=RecordingLogger(),
        monotonic=mono,
    )
    a = JoinThread(mono, hung=hung)
    runner.threads = {"a": a, "b": JoinThread(mono, fail_start=True)}
    with pytest.raises(OSError, match="no thread resources") as caught:
        runner.start()
    assert runner.cancel.cancelled
    assert a.timeouts == [30]
    if hung:
        assert any("TimeoutError" in note and "a" in note for note in caught.value.__notes__)
    else:
        assert not a.is_alive()
    a.hung = False
    runner.stop()
    assert not a.is_alive()


def test_successful_service_progresses_while_another_tick_hangs() -> None:
    blocked, progressed, release = Event(), Event(), Event()

    def hang() -> TickResult:
        blocked.set()
        release.wait()
        return TickResult(0)

    runner = ServiceRunner(
        [Service("hung", hang), Service("active", lambda: (progressed.set(), TickResult(1))[1])],
        intervals={"hung": 3600, "active": 3600},
        clock=FrozenClock(),
        log=RecordingLogger(),
    )
    runner.start()
    try:
        assert blocked.wait(1)
        assert progressed.wait(1)
        assert runner.health()["hung"].stale
        assert len({t.ident for t in runner._threads.values()}) == 2
    finally:
        release.set()
        runner.stop(timeout_seconds=1)
    assert runner.health()["active"].last_ok_at is not None
    assert all(not t.is_alive() for t in runner._threads.values())


def test_failures_preserve_success_timestamp_and_become_stale_until_recovery() -> None:
    wall, mono = FrozenClock(), FakeMonotonic()
    source = AdvancingSource(mono, passes=5)
    actions = iter([TickResult(0), RuntimeError(), RuntimeError(), RuntimeError(), TickResult(1)])

    def tick() -> TickResult:
        action = next(actions)
        if isinstance(action, Exception):
            raise action
        return action

    runner = ServiceRunner(
        [Service("demo", tick)],
        intervals={"demo": 1},
        clock=wall,
        log=RecordingLogger(),
        monotonic=mono,
        cancel_source=source,
    )
    snapshots: list[ServiceHealth] = []
    source.view.observe = lambda: snapshots.append(runner.health()["demo"])
    runner.start()
    for thread in runner._threads.values():
        thread.join(1)
    runner.stop()
    assert [s.stale for s in snapshots] == [False, False, False, True, False]
    assert [s.consecutive_failures for s in snapshots] == [0, 1, 2, 3, 0]
    assert all(s.last_ok_at == wall.now() for s in snapshots)


def test_logger_failure_does_not_lose_original_tick_exception() -> None:
    original = ValueError("tick failed")
    entered = Event()

    class FailingLogger(RecordingLogger):
        @override
        def error(self, event: str, /, *, exc: BaseException | None = None, **fields: object) -> None:
            raise OSError("log output failed")

    def tick() -> TickResult:
        entered.set()
        raise original

    runner = ServiceRunner(
        [Service("demo", tick)], intervals={"demo": 1}, clock=FrozenClock(), log=FailingLogger()
    )
    runner.start()
    assert entered.wait(1)
    with pytest.raises(ValueError, match="tick failed") as caught:
        runner.stop()
    assert caught.value is original
    assert isinstance(original.__cause__, OSError)
    assert any("logging failed" in note for note in original.__notes__)
    assert all(not t.is_alive() for t in runner._threads.values())


@pytest.mark.parametrize("reason", ["timeout", "lease_lost"])
def test_operation_cancellation_retries_with_failure_health_and_recovers(reason: str) -> None:
    wall, mono, log = FrozenClock(), FakeMonotonic(), RecordingLogger()
    source = AdvancingSource(mono, passes=2)
    operation = CancelSource(parent=source.token)
    operation.cancel(reason)
    calls = 0

    def tick() -> TickResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            operation.token.raise_if_cancelled()
        return TickResult(1)

    runner = ServiceRunner(
        [Service("demo", tick)],
        intervals={"demo": 0.5},
        clock=wall,
        log=log,
        monotonic=mono,
        cancel_source=source,
    )
    snapshots: list[ServiceHealth] = []
    root_cancelled: list[bool] = []

    def observe() -> None:
        snapshots.append(runner.health()["demo"])
        root_cancelled.append(runner.cancel.cancelled)

    source.view.observe = observe
    runner.start()
    try:
        for thread in runner._threads.values():
            thread.join(1)
    finally:
        runner.stop(timeout_seconds=1)
    assert calls == 2
    assert source.view.delays == [1, 0.5]
    assert snapshots == [ServiceHealth(None, "Cancelled", 1, True), ServiceHealth(wall.now(), None, 0, False)]
    assert root_cancelled == [False, False]
    assert len(log.errors) == 1
    event, error, fields = log.errors[0]
    assert event == "background.tick.failed"
    assert isinstance(error, Cancelled)
    assert error.reason == reason
    assert fields == {"service": "demo"}
    assert all(not thread.is_alive() for thread in runner._threads.values())
