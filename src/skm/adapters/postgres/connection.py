"""Connection settings, session setup and the single start-up/LISTEN connection (adapters §1.2)."""

from dataclasses import dataclass, field

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import tuple_row

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.errors import BackendUnavailable
from skm.kernel.generated.error_codes import ErrorCode

# ``PgSettings`` is a concrete value type, not a port binding: importable by name, not an export.
__all__ = ["configure_session", "connect_single", "conninfo_of", "dsn_password"]


@dataclass(frozen=True, slots=True)
class PgSettings:
    """``dsn`` is already resolved from its SecretRef; it is excluded from ``repr`` and never logged."""

    dsn: str = field(repr=False)
    application_name: str  # "skm-serve" | "skm-worker" | "skm-cli" | "skm-test"
    pool_min_size: int = 1
    pool_max_size: int = 2
    pool_timeout_seconds: float = 10.0
    statement_timeout_ms: int = 30000
    lock_timeout_ms: int = 10000
    idle_in_tx_timeout_ms: int = 60000

    def __post_init__(self) -> None:
        if not self.application_name:
            raise ValueError("application_name must not be empty")
        if not 0 <= self.pool_min_size <= self.pool_max_size or self.pool_max_size < 1:
            raise ValueError(
                "pool sizes must satisfy 0 <= pool_min_size <= pool_max_size and pool_max_size >= 1"
            )
        if self.pool_timeout_seconds <= 0:
            raise ValueError("pool_timeout_seconds must be positive")
        for name in ("statement_timeout_ms", "lock_timeout_ms", "idle_in_tx_timeout_ms"):
            value: object = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


def conninfo_of(settings: PgSettings) -> str:
    """The DSN with ``application_name`` applied; the result carries the secret and must not be logged."""
    return make_conninfo(settings.dsn, application_name=settings.application_name)


def configure_session(conn: psycopg.Connection, settings: PgSettings) -> None:
    """UTC, timeouts and an empty search path; ends with a commit so a pool sees the connection idle.

    The timeouts go through ``set_config(..., false)`` (session scope, same effect as ``SET``) so that the
    values are bound parameters and never part of the statement text.
    """
    conn.execute("SET TIME ZONE 'UTC'")
    conn.execute("SELECT set_config('statement_timeout', %s, false)", (str(settings.statement_timeout_ms),))
    conn.execute("SELECT set_config('lock_timeout', %s, false)", (str(settings.lock_timeout_ms),))
    conn.execute(
        "SELECT set_config('idle_in_transaction_session_timeout', %s, false)",
        (str(settings.idle_in_tx_timeout_ms),),
    )
    conn.execute("SET search_path = pg_catalog")
    conn.commit()


def connect_single(settings: PgSettings, *, autocommit: bool = False) -> psycopg.Connection:
    """Start-up connection (schema check, process config) and the LISTEN connection (``autocommit=True``).

    Everything else goes through the pool. Failure is ``BackendUnavailable(details.phase="connect")``.
    """
    try:
        conn = psycopg.connect(
            conninfo_of(settings),
            autocommit=autocommit,
            row_factory=tuple_row,
            connect_timeout=max(1, int(settings.pool_timeout_seconds)),
        )
    except psycopg.Error as exc:
        raise _unavailable() from translate_pg_error(exc)
    try:
        configure_session(conn, settings)
    except BaseException as primary:
        conn.close()
        # a server that drops the session right after accepting it is as unavailable as one that refuses it
        if isinstance(primary, psycopg.OperationalError):
            raise _unavailable() from translate_pg_error(primary)
        raise
    return conn


def _unavailable() -> BackendUnavailable:
    return BackendUnavailable(
        ErrorCode.BACKEND_UNAVAILABLE, "cannot connect to the database", details={"phase": "connect"}
    )


def dsn_password(dsn: str) -> str | None:
    """The password libpq takes from a URL or key/value DSN (quotes and %-escapes undone); ``None`` if absent
    or the DSN does not parse."""
    try:
        value = conninfo_to_dict(dsn).get("password")
    except psycopg.Error:
        return None
    return None if value is None else str(value)
