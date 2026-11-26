import inspect
import signal
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import fields
from threading import Event, current_thread
from types import FrameType
from typing import override

import pytest

from fakes.clock import FakeMonotonic, FrozenClock
from skm.background.lease_sweeper import LeaseSweeper
from skm.background.memory_expirer import MemoryExpirer
from skm.background.outbox_relay import OutboxRelay
from skm.background.scheduler import Scheduler
from skm.background.service_runner import ServiceRunner, TickResult
from skm.background.timeout_enforcer import TimeoutEnforcer
from skm.bootstrap.services import (
    BACKGROUND_SERVICES,
    SERVICE_CATALOG,
    ServiceDef,
    ServiceSpec,
    _janitor,
    _learning_recompute,
    build_service_runner,
    running_services,
    service_intervals,
)
from skm.kernel.cancel import Cancelled, CancelSource
from skm.kernel.json_types import JsonValue
from skm.platform.logging.logger import get_logger


def test_exact_descriptive_catalog_and_no_incomplete_active_registrations() -> None:
    assert [s.name for s in SERVICE_CATALOG] == [
        "outbox_relay",
        "janitor",
        "scheduler",
        "lease_sweeper",
        "timeout_enforcer",
        "stall_detector",
        "autopilot",
        "memory_expirer",
        "learning_recompute",
    ]
    excluded = {"vault_push", "idempotency_gc", "staging_gc", "intent_expiry", "outbox_gc", "exports_purge"}
    assert not excluded.intersection(s.name for s in SERVICE_CATALOG)
    assert {f.name for f in fields(ServiceSpec)} == {"name", "module", "interval_key"}
    assert not any(callable(s) or hasattr(s, "factory") for s in SERVICE_CATALOG)
    assert (
        ServiceDef("janitor", _janitor, "exports", "background.janitor.interval_ms"),
        ServiceDef("scheduler", Scheduler, "execution", "background.scheduler.interval_ms"),
        ServiceDef("lease_sweeper", LeaseSweeper, "execution", "background.lease_sweeper.interval_ms"),
        ServiceDef(
            "timeout_enforcer", TimeoutEnforcer, "execution", "background.timeout_enforcer.interval_ms"
        ),
        ServiceDef("memory_expirer", MemoryExpirer, "knowledge", "background.memory_expirer.interval_ms"),
        ServiceDef(
            "learning_recompute", _learning_recompute, "learning", "learning.recompute.interval_seconds"
        ),
    ) == BACKGROUND_SERVICES
    # The platform janitor currently activates only its exports_purge task.
    assert all(
        ServiceSpec(service.name, None if service.name == "janitor" else service.module, service.interval_key)
        in SERVICE_CATALOG
        for service in BACKGROUND_SERVICES
    )
    assert [s.module for s in SERVICE_CATALOG] == [
        None,
        None,
        "execution",
        "execution",
        "execution",
        "execution",
        "execution",
        "knowledge",
        "learning",
    ]


def test_catalog_intervals_convert_ms_but_leave_learning_seconds() -> None:
    config: dict[str, JsonValue] = {
        "background.outbox_relay.interval_ms": 500,
        "background.janitor.interval_ms": 3600000,
        "background.scheduler.interval_ms": 1000,
        "background.lease_sweeper.interval_ms": 5000,
        "background.timeout_enforcer.interval_ms": 10000,
        "background.stall_detector.interval_ms": 15000,
        "background.autopilot.interval_ms": 30000,
        "background.memory_expirer.interval_ms": 600000,
        "learning.recompute.interval_seconds": 86400,
    }
    assert service_intervals(config) == {
        "outbox_relay": 0.5,
        "janitor": 3600,
        "scheduler": 1,
        "lease_sweeper": 5,
        "timeout_enforcer": 10,
        "stall_detector": 15,
        "autopilot": 30,
        "memory_expirer": 600,
        "learning_recompute": 86400,
    }
    config["background.outbox_relay.interval_ms"] = 125
    assert service_intervals(config, names=["outbox_relay"]) == {"outbox_relay": 0.125}
    assert service_intervals({}, names=[]) == {}


@pytest.mark.parametrize("raw", [None, True, 0, -1, 500.0, "500", float("nan"), float("inf")])
@pytest.mark.parametrize("name", ["outbox_relay", "learning_recompute"])
def test_missing_or_invalid_interval_is_not_silently_defaulted(name: str, raw: JsonValue) -> None:
    spec = next(s for s in SERVICE_CATALOG if s.name == name)
    with pytest.raises(ValueError, match=spec.interval_key):
        service_intervals({spec.interval_key: raw}, names=[name])


@pytest.mark.parametrize("name", ["vault_push", "outbox_gc", "missing"])
def test_non_server_service_cannot_be_wired(name: str) -> None:
    with pytest.raises(ValueError, match="unknown server"):
        service_intervals({}, names=[name])


class Relay:
    name = "outbox_relay"

    def __init__(self, cancel: CancelSource) -> None:
        self.cancel = cancel
        self.entered = Event()
        self.thread = None

    def tick(self) -> TickResult:
        self.thread = current_thread()
        self.entered.set()
        self.cancel.token.wait(3600)
        self.cancel.token.raise_if_cancelled()
        raise AssertionError("relay must observe cancellation")


def test_outbox_contract_uses_common_runner_and_shared_cancel_token() -> None:
    source = CancelSource()
    relay = Relay(source)
    contract: OutboxRelay = relay
    runner = build_service_runner(
        [contract],
        config={"background.outbox_relay.interval_ms": 500, "background.outbox_relay.batch_size": 100},
        clock=FrozenClock(),
        log=get_logger("background.runner"),
        cancel_source=source,
    )
    assert runner._states["outbox_relay"].interval == 0.5
    assert runner._states["outbox_relay"].batch_limit == 100
    runner.start()
    try:
        assert relay.entered.wait(1)
    finally:
        runner.stop(timeout_seconds=1)
    assert relay.thread is not None
    assert not relay.thread.is_alive()
    assert not relay.thread.daemon
    assert runner.health()["outbox_relay"].consecutive_failures == 0
    assert "outbox_relay" not in {service.name for service in BACKGROUND_SERVICES}


def test_invalid_batch_size_is_rejected_before_relay_starts() -> None:
    relay = Relay(CancelSource())
    with pytest.raises(ValueError, match="batch_size"):
        build_service_runner(
            [relay],
            config={"background.outbox_relay.interval_ms": 500},
            clock=FrozenClock(),
            log=get_logger("background.runner"),
        )
    assert not relay.entered.is_set()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_entrypoint_signal_cancels_and_context_stops_then_restores_handlers(sig: signal.Signals) -> None:
    original = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    source = CancelSource()
    relay = Relay(source)
    runner = ServiceRunner(
        [relay],
        intervals={"outbox_relay": 1},
        clock=FrozenClock(),
        log=get_logger("background.runner"),
        cancel_source=source,
    )

    def serve() -> None:
        with running_services(runner):
            assert relay.entered.wait(1)
            try:
                signal.raise_signal(sig)
            except Exception as error:
                raise AssertionError("serving swallowed the shutdown signal") from error
            pytest.fail("signal must leave the serving scope")

    with pytest.raises(Cancelled, match="signal"):
        serve()
    assert runner.cancel.cancelled
    assert runner.cancel.reason == "signal"
    assert all(signal.getsignal(s) == handler for s, handler in original.items())
    assert relay.thread is not None
    assert not relay.thread.is_alive()


def test_entrypoint_preserves_primary_exception_and_secondary_shutdown_timeout() -> None:
    entered, release = Event(), Event()
    primary = RuntimeError("serving failed")
    original = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}

    class Hung:
        name = "hung"

        def tick(self) -> TickResult:
            entered.set()
            release.wait()
            return TickResult(0)

    runner = ServiceRunner(
        [Hung()],
        intervals={"hung": 1},
        clock=FrozenClock(),
        log=get_logger("background.runner"),
        monotonic=FakeMonotonic(),
    )

    def serve() -> None:
        with running_services(runner, timeout_seconds=0):
            assert entered.wait(1)
            raise primary

    try:
        with pytest.raises(RuntimeError, match="serving failed") as caught:
            serve()
        assert caught.value is primary
        assert any("TimeoutError" in note and "hung" in note for note in primary.__notes__)
        assert all(signal.getsignal(s) == handler for s, handler in original.items())
    finally:
        release.set()
        runner.stop(timeout_seconds=1)
    assert all(not t.is_alive() for t in runner._threads.values())


def test_entrypoint_partial_start_failure_still_stops_threads_and_restores_handlers() -> None:
    class FailingStartup(ServiceRunner):
        @override
        def start(self) -> None:
            super().start()
            raise RuntimeError("startup failed")

    source = CancelSource()
    relay = Relay(source)
    original = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    runner = FailingStartup(
        [relay],
        intervals={"outbox_relay": 1},
        clock=FrozenClock(),
        log=get_logger("background.runner"),
        cancel_source=source,
    )
    with pytest.raises(RuntimeError, match="startup failed"), running_services(runner):
        pytest.fail("failed startup must not enter serving loop")
    assert all(not t.is_alive() for t in runner._threads.values())
    assert all(signal.getsignal(s) == handler for s, handler in original.items())


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_signal_during_startup_is_deferred_until_threads_are_owned(sig: signal.Signals) -> None:
    class SignalledStartup(ServiceRunner):
        @override
        def start(self) -> None:
            super().start()
            signal.raise_signal(sig)

    source = CancelSource()
    relay = Relay(source)
    original = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    runner = SignalledStartup(
        [relay],
        intervals={"outbox_relay": 1},
        clock=FrozenClock(),
        log=get_logger("background.runner"),
        cancel_source=source,
    )
    with pytest.raises(Cancelled, match="signal"), running_services(runner):
        pytest.fail("signal during startup must prevent serving")
    assert source.token.reason == "signal"
    assert all(not t.is_alive() for t in runner._threads.values())
    assert all(signal.getsignal(s) == handler for s, handler in original.items())


def test_additional_signal_during_cleanup_does_not_interrupt_cleanup() -> None:
    class SignalledStop(ServiceRunner):
        @override
        def stop(self, *, timeout_seconds: float = 30.0) -> None:
            signal.raise_signal(signal.SIGTERM)
            super().stop(timeout_seconds=timeout_seconds)

    runner = SignalledStop([], intervals={}, clock=FrozenClock(), log=get_logger("background.runner"))
    original = signal.getsignal(signal.SIGTERM)
    with running_services(runner):
        pass
    assert runner.cancel.reason == "shutdown"
    assert signal.getsignal(signal.SIGTERM) == original


@pytest.mark.parametrize("timeout", [-1, float("nan"), float("inf"), True])
def test_invalid_context_timeout_is_rejected_before_start(timeout: float) -> None:
    runner = ServiceRunner([], intervals={}, clock=FrozenClock(), log=get_logger("background.runner"))
    with (
        pytest.raises(ValueError, match="shutdown timeout"),
        running_services(runner, timeout_seconds=timeout),
    ):
        pytest.fail("invalid timeout must be rejected before entering context")
    assert not runner.cancel.cancelled
    assert not runner._started


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
@pytest.mark.parametrize(
    ("boundary", "body_fails", "cleanup_fails"),
    [
        ("cleanup", False, False),
        ("cleanup", True, False),
        ("cleanup", False, True),
        ("cleanup", True, True),
        ("primary", True, False),
        ("context_exit", False, False),
        ("context_exit", True, False),
    ],
)
def test_signal_at_serving_exit_preserves_cleanup_and_primary(
    sig: signal.Signals, boundary: str, body_fails: bool, cleanup_fails: bool
) -> None:
    cleanup_error = OSError("secondary shutdown failure")

    class ObservedStop(ServiceRunner):
        stop_calls = 0

        @override
        def stop(self, *, timeout_seconds: float = 30.0) -> None:
            self.stop_calls += 1
            super().stop(timeout_seconds=timeout_seconds)
            if cleanup_fails:
                raise cleanup_error

    source = CancelSource()
    relay = Relay(source)
    runner = ObservedStop(
        [relay],
        intervals={"outbox_relay": 1},
        clock=FrozenClock(),
        log=get_logger("background.runner"),
        cancel_source=source,
    )
    manager = running_services(runner, timeout_seconds=1)
    lifecycle = inspect.unwrap(running_services)
    lines, first_line = inspect.getsourcelines(lifecycle)
    target = "cleaning_up = True" if boundary == "cleanup" else "primary = error"
    line_number = first_line + next(i for i, line in enumerate(lines) if line.strip() == target)
    target_code = lifecycle.__code__
    if boundary == "context_exit":
        target_code = type(manager).__exit__.__code__
    original_handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    original_trace = sys.gettrace()
    injected = False
    primary = RuntimeError("serving failed at exit")
    caught: BaseException | None = None

    def trace(frame: FrameType, event: str, _arg: object):
        nonlocal injected
        boundary_reached = (
            event == "call"
            if boundary == "context_exit"
            else (event == "line" and frame.f_lineno == line_number)
        )
        if not injected and frame.f_code is target_code and boundary_reached:
            injected = True
            signal.raise_signal(sig)
        return trace

    try:
        sys.settrace(trace)
        try:
            with manager:
                assert relay.entered.wait(1)
                if body_fails:
                    raise primary
        except BaseException as error:  # noqa: BLE001 - inspect the exact result after cleanup
            caught = error
        finally:
            sys.settrace(original_trace)
        assert injected
        assert runner.stop_calls == 1
        assert runner.cancel.cancelled
        assert runner.cancel.reason == "signal"
        assert relay.thread is not None
        assert not relay.thread.daemon
        assert not relay.thread.is_alive()
        assert all(signal.getsignal(s) == handler for s, handler in original_handlers.items())
        if body_fails:
            assert caught is primary
            if cleanup_fails:
                assert any("secondary shutdown failure" in note for note in primary.__notes__)
        elif cleanup_fails:
            assert caught is cleanup_error
        else:
            assert caught is None
    finally:
        sys.settrace(original_trace)
        for sig_to_restore, handler in original_handlers.items():
            signal.signal(sig_to_restore, handler)
        cleanup_fails = False
        runner.stop(timeout_seconds=1)


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_signal_inside_other_context_manager_still_leaves_serving_scope(sig: signal.Signals) -> None:
    source = CancelSource()
    relay = Relay(source)
    runner = ServiceRunner(
        [relay],
        intervals={"outbox_relay": 1},
        clock=FrozenClock(),
        log=get_logger("background.runner"),
        cancel_source=source,
    )
    original_handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}

    @contextmanager
    def unrelated_context() -> Generator[None, None, None]:
        yield
        signal.raise_signal(sig)
        pytest.fail("a different context manager must not defer the serving signal")

    def serve() -> None:
        with running_services(runner), unrelated_context():
            assert relay.entered.wait(1)

    with pytest.raises(Cancelled, match="signal"):
        serve()
    assert runner.cancel.reason == "signal"
    assert relay.thread is not None
    assert not relay.thread.is_alive()
    assert all(signal.getsignal(s) == handler for s, handler in original_handlers.items())
