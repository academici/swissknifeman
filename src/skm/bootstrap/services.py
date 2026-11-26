"""Background catalogue and process lifecycle wiring (kernel-platform §6).

The catalogue is descriptive, not an active registry. Concrete factories belong to
the packages that implement each service; Protocols are never registered.
"""

import inspect
import math
import signal
from collections.abc import Callable, Collection, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from types import FrameType, GeneratorType
from typing import Any, Protocol

from skm.application_bus.bus import Bus
from skm.application_bus.registry import BusRegistry
from skm.background.janitor import JanitorService, PurgeNotesTask, build_janitor_tasks
from skm.background.learning_recompute import LearningRecompute
from skm.background.lease_sweeper import LeaseSweeper
from skm.background.memory_expirer import MemoryExpirer
from skm.background.scheduler import Scheduler
from skm.background.service_runner import BackgroundService, ServiceRunner
from skm.background.timeout_enforcer import TimeoutEnforcer
from skm.kernel.cancel import Cancelled, CancelSource, CancelToken
from skm.kernel.clock import Clock, Monotonic
from skm.kernel.id_generator import IdGenerator
from skm.kernel.json_types import JsonValue
from skm.modules.exports.public import PurgeNotes
from skm.platform.logging.logger import StructLogger, get_logger

__all__ = [
    "BACKGROUND_SERVICES",
    "SERVICE_CATALOG",
    "ServiceDef",
    "ServiceSpec",
    "build_service_runner",
    "running_services",
    "service_intervals",
]


@dataclass(frozen=True, slots=True)
class ServiceDef:
    """An active registration, only once its factory is implemented."""

    name: str
    factory: Callable[..., BackgroundService]
    module: str | None
    interval_key: str


def _learning_recompute(bus: Bus, **dependencies: Any) -> LearningRecompute:
    return LearningRecompute(
        bus,
        **dependencies,
        uow_factory=bus._uow_factory,  # pyright: ignore[reportPrivateUsage] -- composition-owned wiring
    )


def _janitor(bus: Bus, *, registry: BusRegistry, clock: Clock, ids: IdGenerator) -> JanitorService:
    tasks = build_janitor_tasks(
        enabled_modules=() if "exports" in registry.disabled_modules() else ("exports",),
        exports_purge=PurgeNotesTask(bus, lambda batch: PurgeNotes(batch=batch), ids, clock, batch_size=500),
    )
    return JanitorService(tasks, log=get_logger("background.janitor"))


BACKGROUND_SERVICES: tuple[ServiceDef, ...] = (
    ServiceDef("janitor", _janitor, "exports", "background.janitor.interval_ms"),
    ServiceDef("scheduler", Scheduler, "execution", "background.scheduler.interval_ms"),
    ServiceDef("lease_sweeper", LeaseSweeper, "execution", "background.lease_sweeper.interval_ms"),
    ServiceDef("timeout_enforcer", TimeoutEnforcer, "execution", "background.timeout_enforcer.interval_ms"),
    ServiceDef("memory_expirer", MemoryExpirer, "knowledge", "background.memory_expirer.interval_ms"),
    ServiceDef("learning_recompute", _learning_recompute, "learning", "learning.recompute.interval_seconds"),
)


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    """Non-executable description; ``module=None`` means a platform service."""

    name: str
    module: str | None
    interval_key: str


SERVICE_CATALOG: tuple[ServiceSpec, ...] = (
    ServiceSpec("outbox_relay", None, "background.outbox_relay.interval_ms"),
    ServiceSpec("janitor", None, "background.janitor.interval_ms"),
    ServiceSpec("scheduler", "execution", "background.scheduler.interval_ms"),
    ServiceSpec("lease_sweeper", "execution", "background.lease_sweeper.interval_ms"),
    ServiceSpec("timeout_enforcer", "execution", "background.timeout_enforcer.interval_ms"),
    ServiceSpec("stall_detector", "execution", "background.stall_detector.interval_ms"),
    ServiceSpec("autopilot", "execution", "background.autopilot.interval_ms"),
    ServiceSpec("memory_expirer", "knowledge", "background.memory_expirer.interval_ms"),
    ServiceSpec("learning_recompute", "learning", "learning.recompute.interval_seconds"),
)


class _ConfigValues(Protocol):
    """The read-only part of EffectiveConfig needed here, including resolved defaults."""

    def get(self, key: str, /) -> JsonValue | None: ...


def _positive_integer(config: _ConfigValues, key: str) -> int:
    raw = config.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError(f"missing or invalid positive integer setting: {key}")
    return raw


def service_intervals(config: _ConfigValues, *, names: Collection[str] | None = None) -> Mapping[str, float]:
    """Read resolved catalog settings; explicitly convert milliseconds to seconds.

    Only enabled services need config values. No second set of hardcoded defaults
    lives here: defaults and overrides are supplied by the settings engine.
    """
    selected = {spec.name for spec in SERVICE_CATALOG} if names is None else set(names)
    if selected - {spec.name for spec in SERVICE_CATALOG}:
        raise ValueError("unknown server background service")
    return {
        spec.name: _positive_integer(config, spec.interval_key)
        / (1000.0 if spec.interval_key.endswith("_ms") else 1.0)
        for spec in SERVICE_CATALOG
        if spec.name in selected
    }


def build_service_runner(
    services: Sequence[BackgroundService],
    *,
    config: _ConfigValues,
    clock: Clock,
    log: StructLogger,
    monotonic: Monotonic | None = None,
    cancel_source: CancelSource | None = None,
) -> ServiceRunner:
    """Wire already implemented services; this does not activate catalogue entries.

    The outbox relay supplies an ordinary BackgroundService and receives the shared
    cancel token from its factory. Its full batches are drained without an idle wait.
    """
    names = {service.name for service in services}
    intervals = service_intervals(config, names=names)
    limits = (
        {"outbox_relay": _positive_integer(config, "background.outbox_relay.batch_size")}
        if "outbox_relay" in names
        else {}
    )
    return ServiceRunner(
        services,
        intervals=intervals,
        clock=clock,
        log=log,
        monotonic=monotonic,
        cancel_source=cancel_source,
        batch_limits=limits,
    )


class _SignalReceived(BaseException):
    """Unwind the main thread before acquiring any cancellation or lifecycle locks."""


def _require_frame(frame: FrameType | None) -> FrameType:
    if frame is None:
        raise RuntimeError("signal lifecycle requires Python frame support")
    return frame


def _inside_lifecycle(frame: FrameType | None, lifecycle: FrameType) -> bool:
    """Do not interrupt the lifecycle's own exception handling or context exit.

    ``serving`` can still be true when the generator resumes from yield, including
    before the first cleanup bytecode. Its contextlib adapter must also be protected
    before it resumes the generator. These are read-only frame checks: the signal
    handler never acquires lifecycle/cancellation locks or calls cleanup.
    """
    while frame is not None:
        if frame is lifecycle:
            return True
        if frame.f_globals.get("__name__") == "contextlib" and frame.f_code.co_name in (
            "__enter__",
            "__exit__",
        ):
            generator = getattr(frame.f_locals.get("self"), "gen", None)
            if isinstance(generator, GeneratorType) and generator.gi_frame is lifecycle:
                return True
        frame = frame.f_back
    return False


@contextmanager
def running_services(
    runner: ServiceRunner, *, timeout_seconds: float = 30.0
) -> Generator[CancelToken, None, None]:
    """Main-thread entrypoint context: signals leave the scope, finally stops/joins.

    A signal unwinds into this context before cancellation is propagated to services:
    taking locks in a Python signal handler could deadlock the interrupted thread.
    Signals during startup are deferred until all started threads are tracked. The
    entrypoint handles ``Cancelled("signal")`` as a normal process exit. Other serving/
    startup errors remain primary; shutdown failures become exception notes. The serving
    loop also observes the yielded token for cancellation from a parent process token.
    """
    if isinstance(timeout_seconds, bool) or not math.isfinite(timeout_seconds) or timeout_seconds < 0:
        raise ValueError("shutdown timeout must be finite and non-negative")
    lifecycle_frame = _require_frame(inspect.currentframe())
    previous: dict[signal.Signals, signal._HANDLER] = {}  # pyright: ignore[reportPrivateUsage]
    primary: BaseException | None = None
    signalled = False
    cleaning_up = False
    serving = False

    def on_signal(_signum: int, _frame: FrameType | None) -> None:
        nonlocal signalled
        if not signalled and not cleaning_up:
            signalled = True
            if serving and not _inside_lifecycle(_frame, lifecycle_frame):
                raise _SignalReceived("signal")

    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, on_signal)
        runner.start()
        if signalled:
            raise _SignalReceived("signal")
        serving = True
        yield runner.cancel
    except _SignalReceived:
        primary = Cancelled("signal")
        runner.request_stop("signal")
        raise primary from None
    except BaseException as error:
        primary = error
        raise
    finally:
        cleaning_up = True
        cleanup_errors: list[BaseException] = []
        try:
            if signalled:
                runner.request_stop("signal")
            runner.stop(timeout_seconds=timeout_seconds)
        except BaseException as error:  # noqa: BLE001 - restore every handler before raising
            cleanup_errors.append(error)
        for sig, handler in previous.items():
            try:
                signal.signal(sig, handler)
            except BaseException as error:  # noqa: BLE001 - retain all cleanup failures
                cleanup_errors.append(error)
        if primary is not None:
            for error in cleanup_errors:
                primary.add_note(f"background lifecycle cleanup failed: {error!r}")
        elif cleanup_errors:
            first, *rest = cleanup_errors
            for error in rest:
                first.add_note(f"secondary lifecycle cleanup failed: {error!r}")
            raise first
