"""Run timeline, indexed audit reads and a logical PostgreSQL backup at annual volume."""

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from skm.adapters.postgres.execution.queries import PostgresExecutionQueries
from skm.kernel.ids import RunId
from support.pg import PgSession, seed_instance
from support.seed import SEED

pytestmark = [pytest.mark.perf, pytest.mark.pg]
EVENTS = 20_000_000
AUDIT = 10_000_000
BATCH = 500_000
AUDIT_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def history_database(pg_dsn, request):
    session = PgSession(worker="perf" + uuid4().hex[:10], pid=os.getpid())
    try:
        yield session.open(request.config.getoption("--perf-history-dsn") or pg_dsn)
    finally:
        session.close()


def _load_history(conn, run_id):
    # Keep every migrated constraint and index. Interleave 1,000 run streams
    # with 20,000 rows in the selected run.
    conn.execute("SET statement_timeout = '20min'")
    seed_instance(conn)
    for offset in range(0, EVENTS, BATCH):
        conn.execute(
            """
            INSERT INTO skm_core.domain_events
                (id, workspace_id, stream_kind, stream_id, stream_seq, workspace_seq,
                 event_type, correlation_id, payload, occurred_at)
            SELECT lpad(to_hex(n), 32, '0')::uuid, %s, 'run',
                   CASE WHEN n %% 1000 = 0 THEN %s ELSE md5((n %% 1000)::text)::uuid END,
                   (n + 999) / 1000, n,
                   'urn:skm:execution:event:run-resumed:v1', 'perf', '{}',
                   '2026-01-01 00:00:00+00'::timestamptz + n * interval '1 second'
            FROM generate_series(%s, %s) AS n
            """,
            (SEED.workspace_id, run_id, offset + 1, offset + BATCH),
        )
    for offset in range(0, AUDIT, BATCH):
        conn.execute(
            """
            INSERT INTO skm_core.audit_records
                (id, workspace_id, actor_id, action, decision, request_id, recorded_at)
            SELECT lpad(to_hex(n), 32, '0')::uuid, %s, %s, 'execution.start_run', 'allowed', 'perf',
                   %s::timestamptz + n * interval '1 second'
            FROM generate_series(%s, %s) AS n
            """,
            (SEED.workspace_id, SEED.instance_id, AUDIT_EPOCH, offset + 1, offset + BATCH),
        )
    conn.execute("ANALYZE skm_core.domain_events, skm_core.audit_records")


def _audit_page(conn, cursor: tuple[datetime, UUID], limit: int):
    # Exercise the keyset SQL directly while the production audit read endpoint is absent.
    return conn.execute(
        """
        SELECT id, actor_id, action, target, decision, recorded_at
        FROM skm_core.audit_records WHERE workspace_id = %s
          AND (recorded_at, id) < (%s, %s)
        ORDER BY recorded_at DESC, id DESC LIMIT %s
        """,
        (SEED.workspace_id, *cursor, limit),
    ).fetchall()


def test_audit_keyset_preserves_timestamp_ties(history_database):
    newest = AUDIT_EPOCH + timedelta(seconds=1)
    records = [
        (1, AUDIT_EPOCH),
        (3, AUDIT_EPOCH),
        (4, AUDIT_EPOCH),
        (5, AUDIT_EPOCH - timedelta(seconds=2)),
        (2, AUDIT_EPOCH - timedelta(seconds=1)),
        (6, newest),
    ]
    with psycopg.connect(history_database.dsn, autocommit=True) as conn:
        seed_instance(conn)
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO skm_core.audit_records
                    (id, workspace_id, actor_id, action, decision, request_id, recorded_at)
                VALUES (%s, %s, %s, 'execution.start_run', 'allowed', 'perf', %s)
                """,
                [(UUID(int=i), SEED.workspace_id, SEED.instance_id, recorded) for i, recorded in records],
            )
        cursor = (newest, UUID(int=6))
        for expected in ([4, 3], [1, 2], [5]):
            rows = _audit_page(conn, cursor, 2)
            assert [row[0].int for row in rows] == expected
            last = rows[-1]
            cursor = (last[-1], last[0])
        assert _audit_page(conn, cursor, 2) == []


def test_history_and_backup(history_database, measure, tmp_path):
    db = history_database
    run_id = RunId(uuid4())
    with psycopg.connect(db.dsn, autocommit=True) as conn:
        assert conn.info.server_version // 10000 == 16
        _load_history(conn, run_id)
        queries = PostgresExecutionQueries(conn)
        event_count = conn.execute(
            "SELECT count(*) FROM skm_core.domain_events WHERE workspace_id=%s", (SEED.workspace_id,)
        ).fetchone()
        audit_count = conn.execute(
            "SELECT count(*) FROM skm_core.audit_records WHERE workspace_id=%s", (SEED.workspace_id,)
        ).fetchone()
        database_size = conn.execute("SELECT pg_database_size(current_database())").fetchone()
        assert event_count == (EVENTS,)
        assert audit_count == (AUDIT,)
        assert database_size is not None
        (db_bytes,) = database_size
        events, audit = EVENTS, AUDIT

        timeline_samples, audit_samples = [], []
        for page in range(30):
            after = page * 600
            start = perf_counter()
            timeline = queries.timeline(run_id, after, 100)
            timeline_samples.append((perf_counter() - start) * 1000)
            items = timeline["items"]
            assert isinstance(items, list)
            assert len(items) == 100
            first = items[0]
            assert isinstance(first, dict)
            assert first["seq"] == after + 1

            anchor = AUDIT - page * 300_000
            cursor = (AUDIT_EPOCH + timedelta(seconds=anchor), UUID(int=anchor))
            start = perf_counter()
            rows = _audit_page(conn, cursor, 100)
            audit_samples.append((perf_counter() - start) * 1000)
            assert len(rows) == 100
            assert rows[0][0] == UUID(int=anchor - 1)

    facts = {"events": events, "audit": audit, "database_bytes": db_bytes, "page_size": 100}
    timeline_stats = measure("timeline_ms", timeline_samples, **facts)
    audit_stats = measure("audit_sql_ms", audit_samples, **facts)
    dump = tmp_path / "database.dump"
    parameters = conninfo_to_dict(db.dsn)
    env = {
        **os.environ,
        **{f"PG{k.upper()}": v for k, v in parameters.items() if k != "dbname"},
        "PGDATABASE": parameters["dbname"],
    }
    pg_dump, pg_restore = shutil.which("pg_dump"), shutil.which("pg_restore")
    assert pg_dump is not None
    assert pg_restore is not None
    start = perf_counter()
    subprocess.run([pg_dump, "--format=custom", "--file", str(dump)], env=env, check=True, timeout=1800)
    elapsed = perf_counter() - start
    subprocess.run([pg_restore, "--list", str(dump)], check=True, stdout=subprocess.DEVNULL, timeout=30)
    measure("pg_dump_s", [elapsed], archive_bytes=dump.stat().st_size, database_bytes=db_bytes)
    assert timeline_stats["p95"] <= 200
    assert audit_stats["p95"] <= 200
