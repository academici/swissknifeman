"""janitor service: ticks its housekeeping tasks in order (kernel-platform §6).

A task is built by bootstrap (``application_bus.outbox_gc.IdempotencyGc``, ``OutboxGc``, and the command
tasks ``ExpireStagedBlobsTask`` / ``IntentExpiryTask``) and handed in here, so this layer stays free of bus
internals and module generated DTOs. Every tick runs every task once; a task that fails does not stop the
others, and the first failure is raised afterwards so the runner records it and backs off.
"""

import base64
from collections.abc import Callable, Collection, Sequence
from typing import Final, Protocol, override

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.platform.logging.logger import StructLogger

from .service_runner import BackgroundService, TickResult

__all__ = [
    "ExpireStagedBlobsTask",
    "IntentExpiryTask",
    "Janitor",
    "JanitorCommandDispatcher",
    "JanitorService",
    "JanitorTask",
    "PurgeNotesTask",
    "build_janitor_tasks",
]

_DEFAULT_BATCH_SIZE: Final = 100
_SERVICE_ACTOR: Final = Actor(
    principal_id=SYSTEM_PRINCIPAL_ID,
    kind=PrincipalKind.SERVICE,
    display_name="system",
)


def _service_request_meta(ids: IdGenerator, clock: Clock) -> RequestMeta:
    token = base64.b32encode(ids.new_id().bytes).decode("ascii").rstrip("=")
    return RequestMeta(
        request_id=f"req_{token}",
        surface=Surface.BACKGROUND,
        idempotency_key=None,
        received_at=clock.now(),
    )


class Janitor(BackgroundService, Protocol):
    name: str = "janitor"


class JanitorTask(Protocol):
    name: str

    def run(self) -> int:
        """One run of the task in its own short units of work; the number of rows it handled."""
        ...


class JanitorCommandDispatcher(Protocol):
    """Minimal command dispatch surface injected by bootstrap."""

    def dispatch(self, cmd: object, *, actor: Actor, meta: RequestMeta) -> object: ...


def _drain_expired(
    dispatcher: JanitorCommandDispatcher,
    command_factory: Callable[[int], object],
    ids: IdGenerator,
    clock: Clock,
    *,
    actor: Actor,
    batch_size: int,
) -> int:
    total = 0
    while True:
        result = dispatcher.dispatch(
            command_factory(batch_size),
            actor=actor,
            meta=_service_request_meta(ids, clock),
        )
        expired_raw = getattr(result, "expired", 0)
        expired = expired_raw if isinstance(expired_raw, int) and not isinstance(expired_raw, bool) else 0
        total += expired
        if expired < batch_size:
            return total


class _BatchedExpiryTask:
    """Dispatch an expiry command in bounded batches until a batch comes back short."""

    name: str

    def __init__(
        self,
        dispatcher: JanitorCommandDispatcher,
        command_factory: Callable[[int], object],
        ids: IdGenerator,
        clock: Clock,
        *,
        actor: Actor = _SERVICE_ACTOR,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        if isinstance(batch_size, bool) or batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self._dispatcher = dispatcher
        self._command_factory = command_factory
        self._ids = ids
        self._clock = clock
        self._actor = actor
        self._batch_size = batch_size

    def run(self) -> int:
        return _drain_expired(
            self._dispatcher,
            self._command_factory,
            self._ids,
            self._clock,
            actor=self._actor,
            batch_size=self._batch_size,
        )


class ExpireStagedBlobsTask(_BatchedExpiryTask):
    """``staging_gc`` task dispatching ``artifacts.expire_staged_blobs`` in bounded batches."""

    name: str = "staging_gc"


class IntentExpiryTask(_BatchedExpiryTask):
    """``intent_expiry`` task dispatching ``policy.expire_intents`` when ``policy`` is enabled."""

    name: str = "intent_expiry"


class PurgeNotesTask(_BatchedExpiryTask):
    """Sweep one bounded batch of vault notes per janitor tick."""

    name = "exports_purge"

    @override
    def run(self) -> int:
        result = self._dispatcher.dispatch(
            self._command_factory(self._batch_size),
            actor=self._actor,
            meta=_service_request_meta(self._ids, self._clock),
        )
        purged = getattr(result, "purged", None)
        if type(purged) is not int:
            raise TypeError("Expected a vault-note purge result")
        return purged


def build_janitor_tasks(
    *,
    enabled_modules: Collection[str],
    idempotency_gc: JanitorTask | None = None,
    staging_gc: JanitorTask | None = None,
    intent_expiry: JanitorTask | None = None,
    outbox_gc: JanitorTask | None = None,
    exports_purge: JanitorTask | None = None,
) -> tuple[JanitorTask, ...]:
    """Assemble active janitor tasks in canonical ``kernel-platform`` §6 order, gated by enabled modules."""
    enabled = frozenset(enabled_modules)
    ordered: list[JanitorTask] = []
    if idempotency_gc is not None:
        ordered.append(idempotency_gc)
    if staging_gc is not None and "artifacts" in enabled:
        ordered.append(staging_gc)
    if intent_expiry is not None and "policy" in enabled:
        ordered.append(intent_expiry)
    if outbox_gc is not None:
        ordered.append(outbox_gc)
    if exports_purge is not None and "exports" in enabled:
        ordered.append(exports_purge)
    return tuple(ordered)


class JanitorService:
    name: str = "janitor"

    def __init__(self, tasks: Sequence[JanitorTask], *, log: StructLogger) -> None:
        names = [task.name for task in tasks]
        if len(set(names)) != len(names):
            raise ValueError("janitor task names must be unique")
        self._tasks = tuple(tasks)
        self._log = log

    def tick(self) -> TickResult:
        processed = 0
        failure: Exception | None = None
        for task in self._tasks:
            try:
                handled = task.run()
            except Exception as exc:  # noqa: BLE001 - one failing task never stops the others
                self._log.warning("janitor.task.failed", task=task.name, error_type=type(exc).__name__)
                failure = failure or exc
                continue
            processed += handled
        if failure is not None:
            raise failure
        return TickResult(processed)
