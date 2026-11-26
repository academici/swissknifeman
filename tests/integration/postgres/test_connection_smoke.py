"""A real connection to the dedicated test database, without migrations."""

import psycopg
import pytest

pytestmark = pytest.mark.pg


def test_select_one(pg_dsn: str) -> None:
    with psycopg.connect(pg_dsn, connect_timeout=2, options="-c default_transaction_read_only=on") as conn:
        assert conn.execute("SELECT 1").fetchone() == (1,)
