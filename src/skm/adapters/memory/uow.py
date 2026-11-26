"""Transactional memory backend (adapters §2.2).

Provides ``InMemoryBackend``, ``InMemoryUnitOfWork`` and ``InMemoryUowFactory``.

One unit of work at a time (an ``RLock`` held from ``__enter__`` to ``__exit__``; a second entry by the
holding thread is refused), so the behaviour matches SERIALIZABLE. The unit of work works on a deep copy of
the committed state; ``commit`` publishes events, outbox rows and everything the repositories wrote by
replacing the committed state with that copy in one step, and a unit of work that ends without ``commit``
leaves the committed state untouched.
``peak_active`` counts the most units of work open at the same moment, so a test can prove that a request
never holds two.
"""

import threading
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import fields, is_dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Literal, Self, cast

from skm.adapters.memory.core.state import NIL_UUID, MemoryBackendState, OutboxRecord
from skm.application_bus.registry import OUTBOX_EXTERNAL_PREFIXES, SSE_DESTINATION
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, SkmError
from skm.kernel.events import DomainEvent, EventEnvelope
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import EventId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Isolation, RequestMeta
from skm.platform.schema.registry import SchemaRegistry

__all__ = [
    "InMemoryBackend",
    "InMemoryUnitOfWork",
    "InMemoryUowFactory",
    "MemoryRepoFactories",
]

type MemoryRepoFactories = Mapping[type, Callable[[MemoryBackendState], object]]
type _Phase = Literal["new", "open", "committed", "rolled_back", "closed"]


class InMemoryBackend:
    """Owner of the committed state and of the lock that serialises units of work."""

    def __init__(
        self,
        *,
        factories: MemoryRepoFactories,
        schemas: SchemaRegistry,
        subscriptions: Mapping[str, tuple[str, ...]],
        ids: IdGenerator,
        clock: Clock,
        state: MemoryBackendState | None = None,
    ) -> None:
        self.lock = threading.RLock()
        self.committed = state if state is not None else MemoryBackendState()
        self.committed.core.clock.clock = clock
        self.factories = factories
        self.schemas = schemas
        self.subscriptions = subscriptions
        self.ids = ids
        self.clock = clock
        self.active = 0
        self.peak_active = 0

    def uow_factory(self) -> "InMemoryUowFactory":
        return InMemoryUowFactory(self)


class InMemoryUowFactory:
    """``UnitOfWorkFactory`` of a backend."""

    def __init__(self, backend: InMemoryBackend) -> None:
        self._backend = backend

    def __call__(
        self,
        meta: RequestMeta,
        *,
        readonly: bool = False,
        isolation: Isolation = Isolation.READ_COMMITTED,
    ) -> "InMemoryUnitOfWork":
        backend = self._backend
        return InMemoryUnitOfWork(
            backend,
            backend.factories,
            backend.schemas,
            backend.subscriptions,
            backend.ids,
            backend.clock,
            meta,
            readonly=readonly,
            isolation=isolation,
        )


class _Enqueuer:
    """``uow.outbox``: explicit rows for external consumers, buffered until commit."""

    def __init__(self, enqueue: Callable[[EventId, str, datetime | None], None]) -> None:
        self._enqueue = enqueue

    def enqueue(self, event_id: EventId, destination: str, *, available_at: datetime | None = None) -> None:
        self._enqueue(event_id, destination, available_at)


def _restore_state(target: Any, saved: Any) -> Any:
    """Restore mutable state in place so already issued repositories observe rollback."""
    params: Any = getattr(cast("Any", type(target)), "__dataclass_params__", None)
    if is_dataclass(target) and not isinstance(target, type) and params is not None and not params.frozen:
        for item in fields(target):
            setattr(
                target,
                item.name,
                _restore_state(getattr(target, item.name), getattr(saved, item.name)),
            )
    elif isinstance(target, dict) and isinstance(saved, dict):
        table, snapshot = cast("dict[Any, Any]", target), cast("dict[Any, Any]", saved)
        for key in tuple(table):
            if key not in snapshot:
                del table[key]
        for key, value in snapshot.items():
            table[key] = _restore_state(table.get(key), value)
    elif isinstance(target, list) and isinstance(saved, list):
        target[:] = saved
    elif isinstance(target, set) and isinstance(saved, set):
        target.clear()
        cast("set[Any]", target).update(cast("set[Any]", saved))
    else:
        return saved
    return cast("Any", target)


class InMemoryUnitOfWork:
    def __init__(  # noqa: PLR0913 - mirrors the adapters §2.2 constructor
        self,
        backend: InMemoryBackend,
        factories: MemoryRepoFactories,
        schemas: SchemaRegistry,
        subscriptions: Mapping[str, tuple[str, ...]],
        ids: IdGenerator,
        clock: Clock,
        meta: RequestMeta,
        *,
        readonly: bool = False,
        isolation: Isolation = Isolation.READ_COMMITTED,
    ) -> None:
        self._backend = backend
        self._factories = factories
        self._schemas = schemas
        self._subscriptions = subscriptions
        self._ids = ids
        self._clock = clock
        self._meta = meta
        self._readonly = readonly
        self.isolation = isolation
        self._phase: _Phase = "new"
        self._working: MemoryBackendState | None = None
        self._repos: dict[type, object] = {}
        self._events: list[DomainEvent] = []
        self._explicit: list[tuple[EventId, str, datetime | None]] = []
        self._enqueuer = _Enqueuer(self._buffer_outbox)

    # ------------------------------------------------------------------ lifecycle
    def __enter__(self) -> Self:
        if self._phase != "new":
            raise RuntimeError("a unit of work cannot be entered twice")
        backend = self._backend
        backend.lock.acquire()
        if backend.active:  # the RLock admits only the owning thread here: a nested unit of work
            backend.lock.release()  # undo this re-acquisition; the outer unit of work keeps its own
            raise RuntimeError("only one unit of work may be open at a time (adapters §2.2)")
        try:
            working = deepcopy(backend.committed)
            working.core.readonly = self._readonly
            self._working = working
            backend.active += 1
            backend.peak_active = max(backend.peak_active, backend.active)
        except BaseException:
            backend.lock.release()
            raise
        self._phase = "open"
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._phase == "new":
            return
        try:
            self._discard()
        finally:
            self._phase = "closed"
            self._backend.active -= 1
            self._backend.lock.release()

    @property
    def readonly(self) -> bool:
        return self._readonly

    def _require_open(self) -> MemoryBackendState:
        if self._phase != "open" or self._working is None:
            raise RuntimeError(f"unit of work is {self._phase}")
        return self._working

    def _discard(self) -> None:
        self._working = None
        self._repos.clear()
        self._events.clear()
        self._explicit.clear()
        if self._phase == "open":
            self._phase = "rolled_back"

    def rollback(self) -> None:
        """Idempotent; the working copy and the buffers are dropped, the committed state is untouched."""
        if self._phase in ("new", "closed"):
            return
        self._discard()

    @contextmanager
    def savepoint(self) -> Generator[None, None, None]:
        working = self._require_open()
        snapshot = deepcopy(working)
        events, explicit = len(self._events), len(self._explicit)
        try:
            yield
        except BaseException:
            _restore_state(working, snapshot)
            self._repos.clear()
            del self._events[events:]
            del self._explicit[explicit:]
            raise

    # ------------------------------------------------------------------ repositories and events
    def repo[R](self, port: type[R]) -> R:
        working = self._require_open()
        existing = self._repos.get(port)
        if existing is None:
            factory = self._factories.get(port)
            if factory is None:
                raise InternalError(
                    ErrorCode.INTERNAL_ERROR,
                    "unknown repository port",
                    details={"port": getattr(port, "__name__", "?")},
                )
            existing = factory(working)
            self._repos[port] = existing
        return existing  # type: ignore[return-value]

    def record(self, event: DomainEvent) -> None:
        self._require_open()
        if self._readonly:
            raise RuntimeError("record() in a readonly unit of work")
        try:
            event.validate(self._schemas)
        except (ValueError, SkmError) as exc:  # a handler defect, not a client error
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "domain event is invalid",
                details={"event": type(event).__name__},
            ) from exc
        self._events.append(event)

    @property
    def outbox(self) -> _Enqueuer:
        return self._enqueuer

    def _buffer_outbox(self, event_id: EventId, destination: str, available_at: datetime | None) -> None:
        self._require_open()
        if self._readonly:
            raise RuntimeError("outbox.enqueue() in a readonly unit of work")
        prefix, separator, rest = destination.partition(":")
        if not separator or not rest or prefix not in OUTBOX_EXTERNAL_PREFIXES:
            raise ValueError("outbox destination must be '<external prefix>:<id>'")
        if available_at is not None and available_at.tzinfo is None:  # as the PostgreSQL unit of work
            raise ValueError("naive datetime is not allowed in outbox.enqueue()")
        self._explicit.append((event_id, destination, available_at))

    # ------------------------------------------------------------------ commit
    def commit(self) -> None:
        working = self._require_open()
        if self._readonly:  # nothing can have been written; the state stays as it is
            self._discard()
            self._phase = "committed"
            return
        try:
            self._publish(working)
        except BaseException:
            self._discard()
            raise
        self._backend.committed = working
        self._working = None
        self._repos.clear()
        self._events.clear()
        self._explicit.clear()
        self._phase = "committed"

    def _publish(self, working: MemoryBackendState) -> None:
        """Assign sequences, write envelopes and outbox rows into the working state (adapters §2.2 step 4)."""
        core = working.core
        now = self._clock.now()
        meta = self._meta
        correlation_id = meta.correlation_id if meta.correlation_id is not None else meta.request_id
        for event in self._events:
            workspace_id = event.scope_workspace_id()
            stream_id = event.stream_id()
            payload = self._checked_payload(event)
            stream_key = (event.stream_kind, stream_id)
            core.stream_seq[stream_key] = core.stream_seq.get(stream_key, 0) + 1
            feed_key = NIL_UUID if workspace_id is None else workspace_id
            core.feed_seq[feed_key] = core.feed_seq.get(feed_key, 0) + 1
            feed = core.feed_seq[feed_key]
            try:
                envelope = EventEnvelope(
                    id=EventId(self._ids.new_id()),
                    type=event.event_type,
                    schema_version=event.schema_version,
                    workspace_id=workspace_id,
                    stream_kind=event.stream_kind,
                    stream_id=stream_id,
                    stream_seq=core.stream_seq[stream_key],
                    workspace_seq=None if workspace_id is None else feed,
                    global_position=feed if workspace_id is None else None,
                    actor_id=None,
                    request_id=meta.request_id,
                    correlation_id=correlation_id,
                    causation_id=meta.request_id,  # the immediate cause is this request
                    parent_causation_id=meta.causation_id,  # and its own cause, stored with the event
                    occurred_at=now,
                    recorded_at=now,
                    payload=payload,
                )
            except ValueError as exc:
                raise InternalError(
                    ErrorCode.INTERNAL_ERROR,
                    "event envelope is invalid",
                    details={"event": type(event).__name__},
                ) from exc
            core.events.append(envelope)
            for consumer_id in self._subscriptions.get(envelope.type, ()):
                self._add_row(working, envelope, consumer_id, now, now)
            if workspace_id is not None:  # exactly one sse row per workspace event
                self._add_row(working, envelope, SSE_DESTINATION, now, now)
        known = {envelope.id: envelope for envelope in core.events}
        for event_id, destination, available_at in self._explicit:
            target = known.get(event_id)
            if target is None:
                raise InternalError(
                    ErrorCode.INTERNAL_ERROR,
                    "outbox row for an unknown event",
                    details={"destination": destination},
                )
            self._add_row(working, target, destination, now, available_at or now)

    def _checked_payload(self, event: DomainEvent) -> JsonObject:
        """Commit-time validation (kernel §2.11): an event may have changed since ``record``.

        The payload is read once into an independent snapshot; the snapshot is what gets validated and
        what the envelope stores, so nothing unchecked can reach the committed state.
        """
        try:
            event.validate_registration(self._schemas)
            snapshot = deepcopy(event.payload())
            self._schemas.require_valid(event.event_type, snapshot)
        except (ValueError, TypeError, SkmError) as exc:
            raise InternalError(
                ErrorCode.INTERNAL_ERROR,
                "domain event is invalid at commit",
                details={"event": type(event).__name__},
            ) from exc
        return snapshot

    def _add_row(
        self,
        working: MemoryBackendState,
        envelope: EventEnvelope,
        destination: str,
        now: datetime,
        available_at: datetime,
    ) -> None:
        core = working.core
        key = (envelope.id, destination)
        if key in core.outbox_keys:  # uq_outbox__event_id_destination: a duplicate is a no-op
            return
        row_id = self._ids.new_id()
        core.outbox_keys.add(key)
        core.outbox[row_id] = OutboxRecord(
            id=row_id,
            event_id=envelope.id,
            destination=destination,
            workspace_id=envelope.workspace_id,
            created_at=now,
            available_at=available_at,
        )
