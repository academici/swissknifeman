"""Worker live delivery over a controlled HTTP transport."""

import asyncio
import json
from threading import Event
from uuid import uuid4

import httpx
import pytest

from integration.api.test_live import _HOST_SECRET, _ndjson, _publish_path, _text
from security.api.harness import BASE
from skm.adapters.http_client.live import LivePublisher
from skm.platform.logging.redaction import MASK, Redactor


def test_worker_publisher_batches_redacts_and_drops_without_waiting():
    sending, cancelled = Event(), Event()
    requests: list[httpx.Request] = []

    async def receive(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        sending.set()
        try:
            return await asyncio.Future[httpx.Response]()
        finally:
            cancelled.set()

    raw = {
        "assignment_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "worker_id": str(uuid4()),
        "fencing_token": 1,
    }
    redactor = Redactor()
    redactor.register_secret(_HOST_SECRET)
    worker_secret = "live-worker-secret"
    publisher = LivePublisher(
        BASE,
        worker_secret,
        raw,
        settings={"api.live.batch_ms": 100, "api.limits.max_body_bytes": 512},
        redactor=redactor,
        max_entries=2,
        transport=httpx.MockTransport(receive),
    )
    try:
        assert publisher.offer(_ndjson(_text(1, _HOST_SECRET)).rstrip(b"\n"))
        assert publisher.offer(_ndjson(_text(2, worker_secret)).rstrip(b"\n"))
        assert sending.wait(4)
        request = requests[0]
        assert request.url.path == _publish_path(raw)
        assert request.headers["content-type"] == "application/x-ndjson"
        assert json.loads(request.headers["skm-worker-claim"]) == raw
        assert request.content == _ndjson(_text(1, MASK), _text(2, MASK))

        assert not publisher.offer(b"a" * 512)  # The newline counts against the byte ceiling.
        large = _ndjson(_text(3, "a" * 260)).rstrip(b"\n")
        assert publisher.offer(large)
        assert not publisher.offer(large)
        assert publisher.offer(_ndjson(_text(4)).rstrip(b"\n"))
        assert not publisher.offer(_ndjson(_text(5)).rstrip(b"\n"))
        assert publisher.live_events_dropped == 3
        assert publisher.live_delivery_gap
    finally:
        publisher.close()
    assert publisher.live_events_dropped == 7  # Three rejected, two queued, two in flight.
    assert publisher.live_delivery_gap
    assert cancelled.is_set()
    publisher.close()
    assert publisher.live_events_dropped == 7


def test_worker_masks_split_deltas_and_settles_only_unacknowledged_events():
    first, second, blocked, release, finished = (Event() for _ in range(5))
    bodies: list[bytes] = []

    async def receive(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        if len(bodies) == 1:
            first.set()
        elif len(bodies) == 2:
            second.set()
        else:
            blocked.set()
            try:
                await asyncio.Future[None]()
            except asyncio.CancelledError:
                # Simulate a transport that stays in cleanup past the bounded join.
                await asyncio.to_thread(release.wait, 4)
                finished.set()
        return httpx.Response(202)

    redactor = Redactor()
    redactor.register_secret(_HOST_SECRET)
    credential = "worker-credential-for-split-test"
    publisher = LivePublisher(
        BASE,
        credential,
        {"attempt_id": str(uuid4())},
        redactor=redactor,
        settings={"api.live.batch_ms": 40},
        transport=httpx.MockTransport(receive),
    )
    try:
        assert publisher.offer(_ndjson(_text(1, _HOST_SECRET[:10])))
        assert publisher.offer(_ndjson(_text(2, _HOST_SECRET[10:] + " " + credential[:12])))
        assert first.wait(4)
        assert publisher.offer(_ndjson(_text(3, credential[12:] + " between " + _HOST_SECRET + " public")))
        assert second.wait(4)
        assert publisher.offer(_ndjson(_text(4)))
        assert blocked.wait(4)
        assert publisher.offer(_ndjson(_text(5)))
        deltas = [json.loads(line)["text"] for body in bodies[:2] for line in body.splitlines()]
        joined = "".join(deltas)
        assert MASK in joined
        assert _HOST_SECRET[:10] not in joined
        assert _HOST_SECRET[10:] not in joined
        assert credential not in joined
        assert credential[12:] not in joined
        assert joined.endswith(" between " + MASK + " public")
        assert not publisher.live_delivery_gap
        publisher.close()
        assert not finished.is_set()
        assert publisher.live_events_dropped == 2
        assert publisher.live_delivery_gap
    finally:
        release.set()
        publisher.close()
    assert finished.is_set()
    assert publisher.live_events_dropped == 2


@pytest.mark.parametrize(
    ("acknowledgement", "dropped"), [("pinned", 0), ("wrong", 1), ("missing", 1), ("duplicate", 1)]
)
def test_worker_publisher_requires_exact_instance_acknowledgement(acknowledgement, dropped):
    instance_id = uuid4()
    received = Event()
    requests = []
    response_headers = {
        "pinned": [("SKM-Instance-Id", str(instance_id))],
        "wrong": [("SKM-Instance-Id", str(uuid4()))],
        "missing": [],
        "duplicate": [("SKM-Instance-Id", str(instance_id))] * 2,
    }

    async def receive(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        received.set()
        return httpx.Response(202, headers=response_headers[acknowledgement])

    publisher = LivePublisher(
        BASE,
        "synthetic-live-token",
        {"attempt_id": str(uuid4())},
        expected_instance_id=instance_id,
        transport=httpx.MockTransport(receive),
    )
    try:
        assert publisher.offer(_ndjson(_text(1)))
        assert received.wait(4)
        publisher.flush()
        assert publisher.dropped == dropped
        assert requests[0].headers.get_list("SKM-Instance-Id") == [str(instance_id)]
    finally:
        publisher.close()
