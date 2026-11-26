"""Sustained domain event ingress and SSE fan-out over a real skm serve."""

import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import httpx
import psycopg
import pytest

from perf.test_http_profile import anyio_backend as anyio_backend
from perf.test_http_profile import http, open_loop
from perf.test_http_profile import server as server
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.kernel.ids import WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.workspace.application.events import WorkspaceCreated
from skm.modules.workspace.domain.slug import Slug
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

pytestmark = [pytest.mark.perf, pytest.mark.pg, pytest.mark.anyio]
RATE = 50
SECONDS = 60
MAX_RELAY_LAG_SECONDS = 60  # background.outbox_relay.max_lag_seconds, shipped default.
DRAIN_SECONDS = 5  # Cover more than two default api.sse.poll_ms intervals.


@dataclass
class _FeedObservations:
    received: list[int] = field(default_factory=list)
    disconnects: list[str] = field(default_factory=list)
    finished_at: float | None = None
    drained: bool = False


async def _read_feed(instance, token, after, expected, ready, observation):
    received, stops = observation.received, observation.disconnects
    loop = asyncio.get_running_loop()
    cursor = after
    async with http(instance) as client:
        for _ in range(5):
            drain = asyncio.timeout(None)
            try:
                async with client.stream(
                    "GET",
                    "/api/v1/events",
                    params={"workspace_id": instance.workspace_id},
                    headers={"Authorization": f"Bearer {token}", "Last-Event-ID": str(cursor)},
                ) as response:
                    response.raise_for_status()
                    ready.set()
                    event_id = None
                    async with drain:
                        async for line in response.aiter_lines():
                            if line.startswith("id: "):
                                event_id = int(line[4:])
                            elif line.startswith("event: cursor"):
                                event_id = None
                            elif not line and event_id is not None:
                                received.append(event_id)
                                cursor, event_id = event_id, None
                                if len(received) == expected:
                                    observation.finished_at = loop.time()
                                    drain.reschedule(observation.finished_at + DRAIN_SECONDS)
                    stops.append("eof")
            except TimeoutError:
                if not drain.expired():
                    raise
                observation.drained = True
                return
            except httpx.TransportError as error:
                stops.append(type(error).__name__)
            if observation.finished_at is not None:
                return


async def _relay_lag(conn, workspace, floor):
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT coalesce(extract(epoch FROM clock_timestamp() - min(o.created_at)), 0)
            FROM skm_core.outbox o JOIN skm_core.domain_events e ON e.id = o.event_id
            WHERE e.workspace_id = %s AND e.workspace_seq > %s
              AND o.destination = 'sse' AND o.state <> 'delivered'
            """,
            (workspace, floor),
        )
        (age,) = await cur.fetchone()
        return float(age)


async def _watch_lag(conn, workspace, floor, stopped):
    samples = []
    while not stopped.is_set():
        samples.append(await _relay_lag(conn, workspace, floor))
        with suppress(TimeoutError):
            await asyncio.wait_for(stopped.wait(), timeout=1)
    return samples


async def _wait_for_delivery(conn, workspace, floor):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + MAX_RELAY_LAG_SECONDS
    while loop.time() < deadline:
        pending_age = await _relay_lag(conn, workspace, floor)
        if pending_age == 0 or pending_age >= MAX_RELAY_LAG_SECONDS:
            return
        await asyncio.sleep(0.1)


async def _server_counts(conn, workspace, floor):
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT e.workspace_seq, e.recorded_at, o.delivered_at
            FROM skm_core.domain_events e LEFT JOIN skm_core.outbox o
              ON o.event_id = e.id AND o.destination = 'sse'
            WHERE e.workspace_id = %s AND e.workspace_seq > %s
            ORDER BY e.workspace_seq
            """,
            (workspace, floor),
        )
        return await cur.fetchall()


async def _publish_events(dsn, workspace):
    # Model domain event producers without putting the separate HTTP command budget in series.
    clock = SystemClock()
    schemas = SchemaRegistry.load(Path(__file__).resolve().parents[2] / "src/skm/schemas")
    writer = PostgresEventWriter(schemas=schemas, subscriptions={}, ids=Uuid7Generator(clock))
    loop = asyncio.get_running_loop()

    with psycopg.connect(dsn) as conn, ThreadPoolExecutor(max_workers=1) as write_thread:

        def append(i):
            event = WorkspaceCreated(WorkspaceId(UUID(workspace)), Slug("perf-workspace"), f"Sample {i}")
            now = clock.now()
            with conn.transaction():
                writer.write(
                    conn,
                    (event,),
                    RequestMeta(f"perf-event-{i}", Surface.BACKGROUND, None, now),
                    occurred_at=now,
                )
            return True

        async def publish(i):
            return await loop.run_in_executor(write_thread, append, i)

        started = loop.time()
        return started, await open_loop(RATE, SECONDS, publish)


async def _open_observers(instance, http_client, floor, clients, count):
    tokens = []
    for i in range((clients + 7) // 8):
        response = await http_client.post("/api/v1/tokens", json={"name": f"perf-sse-{i}"})
        assert response.status_code == 201, response.text
        tokens.append(response.json()["secret"])
    ready = [asyncio.Event() for _ in range(clients)]
    observations = [_FeedObservations() for _ in range(clients)]
    feeds = [
        asyncio.create_task(_read_feed(instance, tokens[i // 8], floor, count, open_event, observations[i]))
        for i, open_event in enumerate(ready)
    ]
    return ready, feeds, observations


@pytest.mark.parametrize("clients", [1, 50])
async def test_domain_events_and_sse_fanout(server, measure, clients):
    instance, _ = server
    workspace = instance.workspace_id
    count = RATE * SECONDS
    async with (
        http(instance, limits=httpx.Limits(max_connections=128, max_keepalive_connections=32)) as producer,
        await psycopg.AsyncConnection.connect(instance.dsn, autocommit=True) as conn,
    ):
        cur = await conn.execute(
            "SELECT coalesce(max(workspace_seq), 0) FROM skm_core.domain_events WHERE workspace_id = %s",
            (workspace,),
        )
        row = await cur.fetchone()
        assert row is not None
        (floor,) = row
        ready, feeds, observations = await _open_observers(instance, producer, floor, clients, count)
        stopped = asyncio.Event()
        lag = None
        try:
            async with asyncio.timeout(150):
                await asyncio.wait_for(asyncio.gather(*(event.wait() for event in ready)), 15)
                lag = asyncio.create_task(_watch_lag(conn, workspace, floor, stopped))
                started, results = await _publish_events(instance.dsn, workspace)
                done, pending = await asyncio.wait(feeds, timeout=65 + DRAIN_SECONDS)
                for task in done:
                    task.result()
                if clients == 1:
                    await _wait_for_delivery(conn, workspace, floor)
                rows = await _server_counts(conn, workspace, floor)
        finally:
            stopped.set()
            for task in feeds:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*feeds, return_exceptions=True)
            live_lag = await lag if lag is not None else []

    expected = list(range(floor + 1, floor + 1 + count))
    stops = Counter(stop for stream in observations for stop in stream.disconnects)
    mismatched = sum(stream.received != expected for stream in observations)
    latency_by_second = {}
    if rows:
        origin = rows[0][1]
        for _, recorded, delivered in rows:
            if delivered is not None:
                bucket = int((recorded - origin).total_seconds())
                latest = (delivered - recorded).total_seconds()
                latency_by_second[bucket] = max(latency_by_second.get(bucket, 0.0), latest)
    actual = [seq for seq, _, _ in rows]
    published = sum(committed for _, _, committed in results)
    counts = Counter(int((recorded - rows[0][1]).total_seconds()) for _, recorded, _ in rows)
    commit_span = (rows[-1][1] - rows[0][1]).total_seconds() if rows else 0.0
    facts = {
        "commit_span_s": round(commit_span, 3),
        "clients": clients,
        "seconds": SECONDS,
        "target_events_per_second": RATE,
        "published": published,
        "completed_streams": sum(len(stream.received) == count for stream in observations),
        "drained_streams": sum(stream.drained for stream in observations),
        "drain_seconds": DRAIN_SECONDS,
        "received_frames": sum(len(stream.received) for stream in observations),
        "duplicates": sum(len(stream.received) - len(set(stream.received)) for stream in observations),
        "timed_out_streams": len(pending),
        "mismatched": mismatched,
        "stream_disconnects": dict(stops),
        "undelivered": sum(delivered is None for _, _, delivered in rows),
        "events_per_second": [counts[i] for i in range(max(counts, default=-1) + 1)],
    }
    measure(
        "sse_last_frame_s",
        [stream.finished_at - started for stream in observations if stream.finished_at is not None],
        **facts,
    )
    measure("oldest_pending_s", live_lag, **facts)
    delivered_lag = [latency_by_second[i] for i in sorted(latency_by_second)]
    measure("max_delivery_lag_per_second_s", delivered_lag, **facts)
    measure(
        "publish_lateness_per_second_ms",
        [max(item[1] for item in results[i : i + RATE]) for i in range(0, len(results), RATE)],
        **facts,
    )
    assert 58 <= commit_span <= 61
    assert published == count
    assert actual == expected
    assert not pending
    assert mismatched == 0
    assert not stops
    assert all(stream.drained for stream in observations)
    if clients == 1:
        assert all(delivered is not None for _, _, delivered in rows)
        assert max(live_lag + delivered_lag) < MAX_RELAY_LAG_SECONDS
