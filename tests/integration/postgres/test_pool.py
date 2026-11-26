"""Pool, session setup and the single start-up connection (adapters §1.2)."""

import logging
import socket
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import psycopg
import pytest

from skm.adapters.postgres.connection import PgSettings, conninfo_of
from skm.adapters.postgres.pool import PoolHandle, connect_single, create_pool
from skm.kernel.errors import BackendUnavailable
from skm.kernel.generated.error_codes import ErrorCode

_SESSION_QUERY = (
    "SELECT current_setting('TimeZone'), current_setting('statement_timeout'), "
    "current_setting('lock_timeout'), current_setting('idle_in_transaction_session_timeout'), "
    "current_setting('search_path'), current_setting('application_name')"
)
_EXPECTED = ("UTC", "12345ms", "6789ms", "4321ms", "pg_catalog", "skm-test")


def _settings(dsn: str, **changes: object) -> PgSettings:
    base = PgSettings(
        dsn=dsn,
        application_name="skm-test",
        pool_min_size=1,
        pool_max_size=2,
        pool_timeout_seconds=5.0,
        statement_timeout_ms=12345,
        lock_timeout_ms=6789,
        idle_in_tx_timeout_ms=4321,
    )
    return replace(base, **changes)


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def pool(pg_dsn: str) -> Iterator[PoolHandle]:
    handle = create_pool(_settings(pg_dsn))
    try:
        yield handle
    finally:
        handle.close()


# --- settings (no database needed) ---------------------------------------------------------------------


def test_settings_validate_and_hide_the_dsn() -> None:
    settings = PgSettings(dsn="postgresql://u:hunter2@h/db", application_name="skm-test")
    assert "hunter2" not in repr(settings)
    assert (settings.pool_min_size, settings.pool_max_size, settings.pool_timeout_seconds) == (1, 2, 10.0)
    assert (settings.statement_timeout_ms, settings.lock_timeout_ms, settings.idle_in_tx_timeout_ms) == (
        30000,
        10000,
        60000,
    )
    for changes, message in (
        ({"application_name": ""}, "application_name"),
        ({"pool_min_size": 3, "pool_max_size": 2}, "pool sizes"),
        ({"pool_max_size": 0, "pool_min_size": 0}, "pool sizes"),
        ({"pool_timeout_seconds": 0}, "pool_timeout_seconds"),
        ({"statement_timeout_ms": -1}, "statement_timeout_ms"),
        ({"lock_timeout_ms": True}, "lock_timeout_ms"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(settings, **changes)


def test_application_name_is_a_conninfo_parameter() -> None:
    conninfo = conninfo_of(PgSettings(dsn="host=h dbname=d", application_name="skm-serve"))
    assert "application_name=skm-serve" in conninfo
    overridden = conninfo_of(
        PgSettings(dsn="host=h dbname=d application_name=other", application_name="skm-cli")
    )
    assert "application_name=skm-cli" in overridden
    assert "other" not in overridden


def test_unreachable_database_fails_at_start_without_leaking_the_password(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dsn = f"postgresql://skm_user:hunter2-secret@127.0.0.1:{_closed_port()}/nodb"
    settings = _settings(dsn, pool_timeout_seconds=1.0)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(BackendUnavailable) as pooled:
            create_pool(settings)
        with pytest.raises(BackendUnavailable) as single:
            connect_single(settings)
    for error in (pooled.value, single.value):
        assert error.code is ErrorCode.BACKEND_UNAVAILABLE
        assert error.retryable is True
        assert dict(error.details) == {"phase": "connect"}
        assert "hunter2-secret" not in str(error) + repr(error.details) + repr(error.to_problem())
    assert "hunter2-secret" not in caplog.text


# --- live PostgreSQL -----------------------------------------------------------------------------------


@pytest.mark.pg
def test_pool_sessions_are_configured(pool: PoolHandle) -> None:
    with pool.connection() as conn:
        assert conn.execute(_SESSION_QUERY).fetchone() == _EXPECTED
        assert conn.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS  # the SELECT opened one
        assert conn.autocommit is False


@pytest.mark.pg
def test_session_settings_survive_a_rollback(pool: PoolHandle) -> None:
    with pool.connection() as conn:
        conn.execute("SELECT 1")
        conn.rollback()
        assert conn.execute(
            "SELECT current_setting('TimeZone'), current_setting('search_path')"
        ).fetchone() == (
            "UTC",
            "pg_catalog",
        )


@pytest.mark.pg
@pytest.mark.parametrize("autocommit", [False, True])
def test_connect_single_configures_the_session(pg_dsn: str, autocommit: bool) -> None:
    conn = connect_single(_settings(pg_dsn), autocommit=autocommit)
    try:
        assert conn.autocommit is autocommit
        assert conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        assert conn.execute(_SESSION_QUERY).fetchone() == _EXPECTED
    finally:
        conn.close()


@pytest.mark.pg
def test_rows_are_tuples_and_values_use_native_types(pool: PoolHandle) -> None:
    with pool.connection() as conn:
        row = conn.execute("SELECT '4b4ed1f7-8e0b-4a54-8f4c-3a7e5d5a5c11'::uuid, now()").fetchone()
    assert isinstance(row, tuple)
    assert str(row[0]) == "4b4ed1f7-8e0b-4a54-8f4c-3a7e5d5a5c11"
    assert row[1].tzinfo is not None


@pytest.mark.pg
def test_exhausted_pool_is_a_retryable_backend_error(pg_dsn: str) -> None:
    handle = create_pool(_settings(pg_dsn, pool_min_size=1, pool_max_size=1, pool_timeout_seconds=0.3))
    try:
        held = handle.getconn()
        try:
            with pytest.raises(BackendUnavailable) as caught:
                handle.getconn()
            assert caught.value.retryable is True
            assert dict(caught.value.details) == {"reason": "pool_timeout"}
            with pytest.raises(BackendUnavailable) as via_context, handle.connection():
                pass
            assert dict(via_context.value.details) == {"reason": "pool_timeout"}
        finally:
            handle.putconn(held)
        with handle.connection() as conn:  # the returned connection is usable again
            assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        handle.close()


@pytest.mark.pg
def test_pool_application_name_is_visible_to_the_server(pool: PoolHandle, pg_dsn: str) -> None:
    with pool.connection() as conn, psycopg.connect(pg_dsn, autocommit=True) as observer:
        pid = conn.execute("SELECT pg_backend_pid()").fetchone()
        assert pid is not None
        seen = observer.execute(
            "SELECT application_name FROM pg_stat_activity WHERE pid = %s", (pid[0],)
        ).fetchone()
    assert seen == ("skm-test",)


@pytest.mark.pg
def test_a_session_dropped_during_setup_is_backend_unavailable(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[psycopg.Connection] = []
    real_connect = psycopg.connect

    def connect_then_drop(conninfo: str, **kwargs: Any) -> psycopg.Connection:
        conn = real_connect(conninfo, **kwargs)
        opened.append(conn)
        with real_connect(pg_dsn, autocommit=True) as admin:
            admin.execute("SELECT pg_terminate_backend(%s)", (conn.info.backend_pid,))
        return conn

    monkeypatch.setattr(psycopg, "connect", connect_then_drop)
    with pytest.raises(BackendUnavailable) as caught:
        connect_single(_settings(pg_dsn))
    assert caught.value.code is ErrorCode.BACKEND_UNAVAILABLE
    assert dict(caught.value.details) == {"phase": "connect"}
    assert opened[0].closed
