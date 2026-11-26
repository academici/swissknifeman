"""Outbox claim at the profile's PostgreSQL cardinality."""

from time import perf_counter
from uuid import uuid4

import psycopg
import pytest

from contracts.execution.seed_helpers import seed_run
from fixtures.execution.harness import recovery as recovery
from integration.api.test_sse import _append
from skm.application_bus.ports import OutboxStore
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

pytestmark = [pytest.mark.perf, pytest.mark.pg]


def test_outbox_claim_at_retention_limit(recovery, measure):
    side = recovery
    with side.uow() as uow:
        run = seed_run(side, uow)
        uow.commit()
    for _ in range(1000):
        _append(side, run.id)
    with psycopg.connect(side.dsn, autocommit=True) as conn:
        conn.execute("SET statement_timeout = '20min'")
        for batch in range(10):
            stream = uuid4()
            conn.execute(
                """
                INSERT INTO skm_core.domain_events
                    (id, workspace_id, stream_kind, stream_id, stream_seq, workspace_seq,
                     event_type, correlation_id, payload, occurred_at)
                SELECT gen_random_uuid(), %s, 'run', %s, n, n + %s,
                       'urn:skm:execution:event:run-resumed:v1', 'perf', '{}', now()
                FROM generate_series(1, 10000) AS n
                """,
                (side.ws, stream, 100_000 + batch * 10_000),
            )
            conn.execute(
                """
                INSERT INTO skm_core.outbox (id, event_id, destination, state, available_at, delivered_at)
                SELECT gen_random_uuid(), e.id,
                       CASE WHEN n = 1 THEN 'sse' ELSE 'perf.consumer_' || n END,
                       'delivered', now(), now()
                FROM skm_core.domain_events e CROSS JOIN generate_series(1, 30) AS n
                WHERE e.stream_id = %s
                """,
                (stream,),
            )
        # Leave just the run's 1,000 SSE rows pending; other fixture deliveries are irrelevant.
        conn.execute(
            """
            DELETE FROM skm_core.outbox
            WHERE state = 'pending' AND NOT (destination = 'sse' AND event_id IN (
                SELECT id FROM skm_core.domain_events WHERE stream_id = %s
            ))
            """,
            (run.id,),
        )
        conn.execute("ANALYZE skm_core.outbox")
        assert dict(conn.execute("SELECT state, count(*) FROM skm_core.outbox GROUP BY state")) == {
            "delivered": 3_000_000,
            "pending": 1000,
        }
        now_row = conn.execute("SELECT clock_timestamp()").fetchone()
        assert now_row is not None
        (now,) = now_row
    samples = []
    for _ in range(30):
        with side.uow() as uow:
            start = perf_counter()
            items = uow.repo(OutboxStore).claim(destination="sse", relay_id="perf", now=now, limit=100)
            samples.append((perf_counter() - start) * 1000)
            assert len(items) == 100
            uow.rollback()  # Restore the same pending population before the next measurement.
    stats = measure(
        "outbox_claim_ms",
        samples,
        delivered=3_000_000,
        pending=1000,
        historical_events=100_000,
        delivered_sse=100_000,
        batch=100,
    )
    assert stats["p95"] <= 20
