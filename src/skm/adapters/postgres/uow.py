"""PostgreSQL unit of work (adapters §1.3, kernel-platform §2.11).

One pooled connection per unit of work and one database transaction: repositories built by ``repo`` share
it, ``record`` and ``outbox.enqueue`` only buffer, and ``commit`` writes the buffered events, their sequences
and outbox rows (``PostgresEventWriter``) as the last step before COMMIT, so state, events and outbox commit
or vanish together. Leaving the ``with`` block without ``commit`` rolls back. A failed commit or rollback ends
the unit of work: the connection transaction is rolled back and never continued; a retry needs a new one.
Driver errors are translated by ``translate_pg_error`` with the driver exception kept as ``__cause__``; a
rollback failure while another exception propagates is attached to it as a note instead of replacing it.
"""

from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from datetime import datetime
from types import TracebackType
from typing import Final, Literal, Self

import psycopg

from skm.adapters.postgres.core.events_store import ExplicitOutboxRow, PostgresEventWriter
from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import require_aware
from skm.adapters.postgres.pool import PoolHandle
from skm.application_bus.registry import OUTBOX_EXTERNAL_PREFIXES
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.events import DomainEvent
from skm.kernel.ids import EventId
from skm.kernel.ports_uow import Isolation, RequestMeta

__all__ = ["PostgresUnitOfWork", "PostgresUowFactory"]

type PostgresRepoFactories = Mapping[type, Callable[[psycopg.Connection], object]]
type _Phase = Literal["new", "open", "committed", "rolled_back", "closed"]

_ISOLATION: Final[Mapping[Isolation, psycopg.IsolationLevel]] = {
    Isolation.READ_COMMITTED: psycopg.IsolationLevel.READ_COMMITTED,
    Isolation.REPEATABLE_READ: psycopg.IsolationLevel.REPEATABLE_READ,
    Isolation.SERIALIZABLE: psycopg.IsolationLevel.SERIALIZABLE,
}


class PostgresUowFactory:
    """``UnitOfWorkFactory`` over one pool; ``events`` carries the schemas, ``SubscriptionIndex`` and ids."""

    def __init__(
        self,
        pool: PoolHandle,
        factories: PostgresRepoFactories,
        events: PostgresEventWriter,
        clock: Clock,
    ) -> None:
        self._pool = pool
        self._factories = factories
        self._events = events
        self._clock = clock

    def __call__(
        self,
        meta: RequestMeta,
        *,
        readonly: bool = False,
        isolation: Isolation = Isolation.READ_COMMITTED,
    ) -> "PostgresUnitOfWork":
        return PostgresUnitOfWork(
            self._pool,
            self._factories,
            self._events,
            meta,
            self._clock,
            readonly=readonly,
            isolation=isolation,
        )


class _Enqueuer:
    """``uow.outbox``: explicit rows for external consumers, buffered until commit."""

    def __init__(self, enqueue: Callable[[EventId, str, datetime | None], None]) -> None:
        self._enqueue = enqueue

    def enqueue(self, event_id: EventId, destination: str, *, available_at: datetime | None = None) -> None:
        self._enqueue(event_id, destination, available_at)


class PostgresUnitOfWork:
    def __init__(
        self,
        pool: PoolHandle,
        factories: PostgresRepoFactories,
        events: PostgresEventWriter,
        meta: RequestMeta,
        clock: Clock,
        *,
        readonly: bool = False,
        isolation: Isolation = Isolation.READ_COMMITTED,
    ) -> None:
        self._pool = pool
        self._factories = factories
        self._writer = events
        self._meta = meta
        self._clock = clock
        self._readonly = readonly
        self._isolation = isolation
        self._phase: _Phase = "new"
        self._conn: psycopg.Connection | None = None
        self._repos: dict[type, object] = {}
        self._events: list[DomainEvent] = []
        self._explicit: list[ExplicitOutboxRow] = []
        self._enqueuer = _Enqueuer(self._buffer_outbox)

    # ------------------------------------------------------------------ lifecycle
    def __enter__(self) -> Self:
        if self._phase != "new":
            raise RuntimeError("a unit of work cannot be entered twice")
        conn = self._pool.getconn()  # BackendUnavailable(reason=pool_timeout, retryable) when none is free
        try:
            conn.isolation_level = _ISOLATION[self._isolation]
            conn.read_only = self._readonly
        except psycopg.Error as exc:
            self._pool.putconn(conn)
            raise translate_pg_error(exc) from exc
        except BaseException:
            self._pool.putconn(conn)
            raise
        self._conn = conn  # the first statement opens the transaction implicitly
        self._phase = "open"
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        conn = self._conn
        if self._phase == "new" or conn is None:
            return
        try:
            if self._phase == "open":  # no commit: the handler's writes vanish (kernel §2.11 rule 3)
                self._rollback_connection(conn, exc)
        finally:
            self._discard()
            self._phase = "closed"
            self._conn = None
            self._release(conn)

    @property
    def readonly(self) -> bool:
        return self._readonly

    @property
    def isolation(self) -> Isolation:
        return self._isolation

    @property
    def connection(self) -> psycopg.Connection:
        """The transaction connection, for core adapters (idempotency, audit) only, never for handlers."""
        return self._require_open()

    def _require_open(self) -> psycopg.Connection:
        if self._phase != "open" or self._conn is None:
            raise RuntimeError(f"unit of work is {self._phase}")
        return self._conn

    def _discard(self) -> None:
        self._repos.clear()
        self._events.clear()
        self._explicit.clear()

    def _rollback_connection(self, conn: psycopg.Connection, active: BaseException | None) -> None:
        """Roll back; a failure becomes a note on ``active`` or, without one, the translated error."""
        self._phase = "rolled_back"
        try:
            conn.rollback()
        except psycopg.Error as exc:
            if active is None:
                raise translate_pg_error(exc) from exc
            active.add_note(f"rollback of the unit of work failed as well: {type(exc).__name__}")

    def _release(self, conn: psycopg.Connection) -> None:
        """Hand the connection back with the pool defaults; a broken connection is discarded by the pool."""
        if not conn.closed and conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE:
            try:
                conn.read_only = None
                conn.isolation_level = None
            except psycopg.Error:
                pass  # the pool checks the connection state itself
        self._pool.putconn(conn)

    def rollback(self) -> None:
        """Idempotent; the buffers are dropped and the connection transaction is rolled back."""
        conn = self._conn
        if self._phase != "open" or conn is None:
            return
        self._discard()
        self._rollback_connection(conn, None)

    @contextmanager
    def savepoint(self) -> Generator[None, None, None]:
        conn = self._require_open()
        events, explicit = len(self._events), len(self._explicit)
        try:
            # Ensure transaction() creates a savepoint even before the first repository call.
            conn.execute("SELECT 1")
            with conn.transaction():
                yield
        except BaseException as exc:
            del self._events[events:]
            del self._explicit[explicit:]
            if isinstance(exc, psycopg.Error):
                raise translate_pg_error(exc) from exc
            raise

    # ------------------------------------------------------------------ repositories and events
    def repo[R](self, port: type[R]) -> R:
        conn = self._require_open()
        existing = self._repos.get(port)
        if existing is None:
            factory = self._factories.get(port)
            if factory is None:
                raise InternalError(
                    ErrorCode.INTERNAL_ERROR,
                    "unknown repository port",
                    details={"port": getattr(port, "__qualname__", "?")},
                )
            existing = factory(conn)
            self._repos[port] = existing
        return existing  # type: ignore[return-value]

    def record(self, event: DomainEvent) -> None:
        self._require_open()
        if self._readonly:
            raise RuntimeError("record() in a readonly unit of work")
        self._writer.validate(event)
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
        if available_at is not None:
            require_aware(available_at)
        self._explicit.append((event_id, destination, available_at))

    # ------------------------------------------------------------------ commit
    def commit(self) -> None:
        conn = self._require_open()
        if self._readonly and (self._events or self._explicit):  # adapters §1.3 step 4.1
            raise InternalError(ErrorCode.INTERNAL_ERROR, "readonly unit of work has buffered writes")
        try:
            self._writer.write(
                conn,
                tuple(self._events),
                self._meta,
                occurred_at=self._clock.now(),
                explicit=tuple(self._explicit),
            )
            conn.commit()
        except psycopg.Error as exc:
            error = translate_pg_error(exc)
            self._fail(conn, error)
            raise error from exc
        except BaseException as exc:
            self._fail(conn, exc)
            raise
        self._discard()
        self._phase = "committed"

    def _fail(self, conn: psycopg.Connection, error: BaseException) -> None:
        """A failed commit ends the unit of work; the transaction is rolled back, never reused."""
        self._discard()
        self._rollback_connection(conn, error)
