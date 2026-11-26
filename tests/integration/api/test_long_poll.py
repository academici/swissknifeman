"""Long-poll concurrency, ASGI disconnect and real bus receipts on both backends."""

import asyncio
import json
import threading

import anyio
import httpx
import pytest

from contracts.execution._worker_protocol_support import make_case, worker_claim
from contracts.execution.harness import exec_side as exec_side
from integration.api.test_worker_protocol import (
    CLAIM_PATH,
    HEARTBEAT_PATH,
    checked,
    claim_body,
    worker_api,
)
from integration.api.test_worker_protocol import worker_side as worker_side
from security.api.harness import BASE
from skm.application_bus.ports import IdempotencyStore
from skm.entrypoints.api.long_poll import mount_worker
from skm.modules.execution.public import ClaimAssignment
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

EMPTY = {"outcome": "nothing_to_claim"}
MAX_WAIT = 10


class AssignmentSignal:
    def __init__(self):
        self._event = asyncio.Event()
        self.changed = asyncio.Condition()
        self.waiters = 0

    async def wait(self):
        event = self._event
        async with self.changed:
            self.waiters += 1
            self.changed.notify_all()
        try:
            await event.wait()
        finally:
            async with self.changed:
                self.waiters -= 1
                self.changed.notify_all()

    async def count(self, count):
        async with self.changed:
            await asyncio.wait_for(self.changed.wait_for(lambda: self.waiters == count), 4)

    def notify(self):
        self._event.set()
        self._event = asyncio.Event()


def claim_http(client, side, key, *, seconds=MAX_WAIT):
    return client.post(
        CLAIM_PATH,
        json=claim_body(side, max_wait_seconds=seconds),
        headers={"Idempotency-Key": key},
    )


def test_long_poll_cap_preserves_health_heartbeat_and_worker_threads(worker_side):
    side, headers, operator = worker_side
    # The fixture's PostgreSQL pool has four connections. Five parked claims would exhaust it.
    max_waiters = 5
    make_case(side)

    async def exercise():
        anyio.to_thread.current_default_thread_limiter().total_tokens = 2
        signal = AssignmentSignal()
        api = worker_api(
            side,
            settings={"api.worker.max_long_polls": max_waiters, "api.sse.poll_ms": 60000},
        )
        mount_worker(api, wake_up=signal.wait)
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transport, base_url=BASE, headers=headers) as client:
            claimed = checked(await claim_http(client, side, "first", seconds=0))
            claim = worker_claim(side, claimed)
            tasks = [
                asyncio.create_task(claim_http(client, side, f"wait-{number}"))
                for number in range(max_waiters)
            ]
            try:
                await signal.count(max_waiters)
                async with asyncio.timeout(4):
                    excess, health, heartbeat = await asyncio.gather(
                        claim_http(client, side, "over-limit"),
                        client.get("/health/details", headers=operator),
                        client.post(
                            f"/api/v1/worker/assignments/{claim['assignment_id']}/heartbeat",
                            json={"claim": claim},
                            headers={"Idempotency-Key": "keep-alive"},
                        ),
                    )
                assert checked(excess) == EMPTY
                checked(health)
                assert checked(heartbeat)["lease_expires_at"]
                assert not any(task.done() for task in tasks)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            await signal.count(0)

    asyncio.run(exercise())


@pytest.mark.parametrize("notify", [False, True], ids=["fallback", "notification"])
def test_new_assignment_wakes_waiter_and_replay_keeps_assignment(worker_side, monkeypatch, notify):
    side, headers, _ = worker_side
    seen = []
    original = side.app.bus.dispatch

    async def exercise():
        loop = asyncio.get_running_loop()
        initial = asyncio.Event()
        signal = AssignmentSignal()

        def observed(dto, *, actor, meta, auth_basis=None):
            result = original(dto, actor=actor, meta=meta, auth_basis=auth_basis)
            if isinstance(dto, ClaimAssignment):
                seen.append((dto, meta, threading.get_ident(), result))
                loop.call_soon_threadsafe(initial.set)
            return result

        monkeypatch.setattr(side.app.bus, "dispatch", observed)
        api = worker_api(
            side,
            settings={"api.sse.poll_ms": 60000 if notify else 75},
        )
        if notify:
            original_routes = tuple(api.routes)
            mount_worker(api, wake_up=signal.wait)
            assert tuple(api.routes) == original_routes
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transport, base_url=BASE, headers=headers) as client:
            checked(
                await client.post(HEARTBEAT_PATH, json={"worker_id": str(side.worker1), "capabilities": None})
            )
            pending = asyncio.create_task(claim_http(client, side, "same-key"))
            try:
                await asyncio.wait_for(initial.wait(), 4)
                if notify:
                    await signal.count(1)
                assert not pending.done()
                _, first_meta, _, first_result = seen[0]
                assert first_result.to_json() == EMPTY
                with side.uow(readonly=True) as uow:
                    assert (
                        uow.repo(IdempotencyStore).get(
                            side.ws,
                            side.worker1_client._actor.principal_id,
                            "execution.claim_assignment",
                            "same-key",
                        )
                        is None
                    )
                _, _, _, assignment = await asyncio.to_thread(make_case, side)
                if notify:
                    signal.notify()
                original_response = await asyncio.wait_for(pending, 4)
                claimed = checked(original_response)
                assert claimed["assignment_id"] == str(assignment.id)
                assert checked(await claim_http(client, side, "same-key")) == claimed
                assert {meta.idempotency_key for _, meta, _, _ in seen} == {"same-key"}
                assert len({meta.request_id for _, meta, _, _ in seen}) == len(seen) >= 3
                assert all(thread != threading.get_ident() for _, _, thread, _ in seen)
                assert all(meta.correlation_id == first_meta.request_id for _, meta, _, _ in seen[1:-1])
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(exercise())


async def disconnected_claim(api, side, headers, disconnect):
    body = json.dumps(claim_body(side, max_wait_seconds=MAX_WAIT)).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": "POST",
        "path": CLAIM_PATH,
        "query_string": b"",
        "headers": [
            (b"host", b"127.0.0.1:8765"),
            (b"content-type", b"application/json"),
            (b"authorization", headers["Authorization"].encode()),
            (b"idempotency-key", b"disconnect"),
        ],
    }
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(_message):
        pass

    await api(scope, receive, send)


def test_disconnect_releases_last_long_poll_slot(worker_side):
    side, headers, _ = worker_side

    async def exercise():
        signal = AssignmentSignal()
        api = worker_api(
            side,
            settings={"api.worker.max_long_polls": 1, "api.sse.poll_ms": 60000},
        )
        mount_worker(api, wake_up=signal.wait)
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transport, base_url=BASE, headers=headers) as client:
            checked(
                await client.post(HEARTBEAT_PATH, json={"worker_id": str(side.worker1), "capabilities": None})
            )
            disconnect = asyncio.Event()
            pending = asyncio.create_task(disconnected_claim(api, side, headers, disconnect))
            try:
                await signal.count(1)
                disconnect.set()
                await asyncio.wait_for(pending, 4)
                await signal.count(0)
                # If the slot leaked, this claim would finish before it reaches the wake-up source.
                next_claim = asyncio.create_task(claim_http(client, side, "after-disconnect", seconds=1))
                try:
                    await signal.count(1)
                    assert checked(await asyncio.wait_for(next_claim, 4)) == EMPTY
                finally:
                    next_claim.cancel()
                    await asyncio.gather(next_claim, return_exceptions=True)
                await signal.count(0)
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(exercise())
