"""Connection pool of one process (adapters §1.2)."""

from collections.abc import Generator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from threading import Lock
from time import monotonic

import psycopg
import psycopg_pool
from psycopg.rows import TupleRow, tuple_row

from skm.adapters.postgres.connection import PgSettings, configure_session, connect_single, conninfo_of
from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.errors import BackendUnavailable
from skm.kernel.generated.error_codes import ErrorCode

# ``PgSettings`` and ``PoolHandle`` are concrete types, not port bindings: importable by name, not exports.
__all__ = ["connect_single", "create_pool"]


class PoolHandle:
    """Owns the ``ConnectionPool``; ``close()`` is the process shutdown hook."""

    _scope: ContextVar[list["PoolHandle"] | None] = ContextVar("owned_pg_pools", default=None)

    @classmethod
    @contextmanager
    def collect(cls) -> Generator[list["PoolHandle"]]:
        """Collect just the pools constructed by this composition, including blob coordination."""
        owned: list[PoolHandle] = []
        token = cls._scope.set(owned)
        try:
            yield owned
        finally:
            cls._scope.reset(token)

    def __init__(self, pool: psycopg_pool.ConnectionPool, settings: PgSettings) -> None:
        self._pool = pool
        self._settings = settings
        self._active: set[psycopg.Connection] = set()
        self._lock = Lock()
        self.deadline: float | None = None
        self._stopping = False
        if (owned := self._scope.get()) is not None:
            owned.append(self)

    @property
    def pool(self) -> psycopg_pool.ConnectionPool:
        return self._pool

    @property
    def settings(self) -> PgSettings:
        return self._settings

    def getconn(self) -> psycopg.Connection:
        """A free connection or ``BackendUnavailable(reason=pool_timeout)``; give it back with ``putconn``."""
        try:
            conn = self._pool.getconn(timeout=self._settings.pool_timeout_seconds)
        except psycopg_pool.PoolTimeout as exc:
            raise translate_pg_error(exc) from exc
        with self._lock:
            if self._stopping:
                self._pool.putconn(conn)
                raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Database pool is stopping")
            self._active.add(conn)
        return conn

    def putconn(self, conn: psycopg.Connection) -> None:
        with self._lock:
            self._active.discard(conn)
        self._pool.putconn(conn)

    def has_active_connections(self) -> bool:
        with self._lock:
            return bool(self._active)

    def cancel_active(self) -> bool:
        with self._lock:
            self._stopping = True
            for conn in self._active:
                with suppress(psycopg.Error):
                    conn.cancel()
            return bool(self._active)

    @contextmanager
    def connection(self) -> Generator[psycopg.Connection]:
        """Borrow a connection; a clean exit commits, an error rolls back (``ConnectionPool.connection``
        rules)."""
        conn = self.getconn()
        try:
            with conn:
                yield conn
        finally:
            self.putconn(conn)

    def close(self) -> None:
        close_timeout = min(5.0, max(0.05, self._settings.lock_timeout_ms / 1000))
        if self.deadline is not None:
            self.cancel_active()
            # psycopg_pool applies timeout separately to each worker and the scheduler.
            remaining = max(0.0, self.deadline - monotonic())
            close_timeout = min(close_timeout, remaining / (self._pool.num_workers + 1))
        self._pool.close(timeout=close_timeout)


def create_pool(settings: PgSettings) -> PoolHandle:
    """Open the pool and wait for ``pool_min_size`` connections; an unreachable database fails here.

    Raises ``BackendUnavailable(BACKEND_UNAVAILABLE, details={"phase": "connect"})``.
    """

    def configure(conn: psycopg.Connection) -> None:
        configure_session(conn, settings)

    pool: psycopg_pool.ConnectionPool[psycopg.Connection[TupleRow]] = psycopg_pool.ConnectionPool(
        conninfo_of(settings),
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        timeout=settings.pool_timeout_seconds,
        max_idle=300,
        kwargs={"autocommit": False, "row_factory": tuple_row},
        configure=configure,
        open=True,
        name=settings.application_name,
    )
    try:
        pool.wait(timeout=settings.pool_timeout_seconds)
    except psycopg_pool.PoolTimeout as exc:
        pool.close()
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE, "cannot connect to the database", details={"phase": "connect"}
        ) from exc
    except BaseException:
        pool.close()
        raise
    return PoolHandle(pool, settings)
