"""Live HTTP delivery against real access, lease and execution repositories."""

import asyncio
import json
from collections import deque
from contextlib import asynccontextmanager
from typing import override
from uuid import uuid4

import httpx
import pytest
from starlette.datastructures import Headers
from starlette.routing import Route
from starlette.types import Message, Scope

from contracts.execution._worker_protocol_support import claim, make_case, worker_claim
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_lock_order import expire_now
from contracts.execution.test_step_notes import owned_agent
from integration.api.test_sse import _Stream
from integration.api.test_worker_protocol import bearer, problem, worker_api
from integration.api.test_worker_protocol import worker_side as worker_side
from security.api.harness import BASE, TestClient
from skm.adapters.http_client.live import stream_live
from skm.application_bus.ports import EventReader
from skm.entrypoints.api.app import create_app
from skm.kernel.error_codes import ErrorCode
from skm.modules.access.public import (
    CreateToken,
    CreateTokenResult,
    GrantMembership,
    RevokeMembership,
    RevokeToken,
)
from skm.modules.execution.public import CancelRun
from skm.platform.logging.redaction import MASK, Redactor
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

_AT = "2026-11-18T12:00:00.000000Z"
_HOST_SECRET = "known-live-secret-27"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def live_clock(exec_side, monkeypatch):
    monkeypatch.setattr("skm.entrypoints.api.live.SystemClock", lambda: exec_side.clock)
    monkeypatch.setattr("skm.entrypoints.api.app.SystemClock", lambda: exec_side.clock)


@pytest.fixture
def live_case(worker_side):
    side, worker, reader = worker_side
    _, _, _, assignment = make_case(side)
    return side, worker, reader, assignment, worker_claim(side, claim(side))


def _publish_path(claim):
    return f"/api/v1/worker/attempts/{claim['attempt_id']}/live"


def _subscribe_path(claim):
    return f"/api/v1/attempts/{claim['attempt_id']}/live"


def _publish_headers(worker, claim):
    return {
        **worker,
        "Content-Type": "application/x-ndjson",
        "SKM-Worker-Claim": json.dumps(claim),
    }


def _text(seq, text="public output"):
    return {"type": "text_delta", "seq": seq, "at": _AT, "channel": "assistant", "text": text}


def _completed(seq):
    return {
        "type": "session_completed",
        "seq": seq,
        "at": _AT,
        "stop_reason": "end_turn",
        "final_text_digest": "sha256:" + "1" * 64,
    }


def _failed(seq, message):
    return {
        "type": "session_failed",
        "seq": seq,
        "at": _AT,
        "failure": {
            "error_class": "crash",
            "code": "RUNTIME_CRASHED",
            "retryable": False,
            "safe_message": message,
            "retry_after_seconds": None,
            "scope": None,
            "evidence": "process",
        },
    }


def _ndjson(*events):
    return b"".join(json.dumps(event, separators=(",", ":")).encode() + b"\n" for event in events)


def _journal_head(side):
    with side.uow(readonly=True) as uow:
        return uow.repo(EventReader).head_workspace_seq(side.ws)


def _reader(side, **restrictions):
    token = side.client.dispatch(CreateToken(name=f"live-{uuid4()}", **restrictions))
    assert isinstance(token, CreateTokenResult)
    return token


def _cancel(side, assignment):
    side.client.dispatch(CancelRun(assignment.run_id, "close live attempt"), idempotency_key="cancel-live")


def test_publish_requires_current_worker_claim_before_parsing(live_case):
    side, worker, reader, assignment, claim = live_case
    path = _publish_path(claim)
    with TestClient(worker_api(side), base_url=BASE, headers=reader) as client:
        headers = _publish_headers(reader, claim)
        problem(client.post(path, content=b"invalid", headers=headers), 403, "FORBIDDEN")
        for invalid in ({"attempt_id": str(uuid4())}, {"assignment_id": 3}, {"worker_id": False}):
            headers = _publish_headers(worker, {**claim, **invalid})
            problem(client.post(path, content=b"invalid", headers=headers), 422, "SCHEMA_INVALID")
        for stale in ({"fencing_token": claim["fencing_token"] + 1}, {"worker_id": str(side.worker2)}):
            headers = _publish_headers(worker, {**claim, **stale})
            problem(client.post(path, content=b"invalid", headers=headers), 409, "LEASE_LOST")

        headers = _publish_headers(worker, claim)
        assert client.post(path, content=_ndjson(_text(1)), headers=headers).status_code == 202
        expire_now(side, assignment)
        problem(client.post(path, content=_ndjson(_text(2)), headers=headers), 409, "LEASE_LOST")
        _cancel(side, assignment)
        problem(client.post(path, content=_ndjson(_text(2)), headers=headers), 409, "LEASE_LOST")
        with stream_live(client, assignment.attempt_id) as frames:
            assert list(frames) == [("text_delta", 1, _text(1)), ("end", None, {})]


def test_live_instance_pin_is_checked_before_publication(live_case):
    side, worker, reader, assignment, claim = live_case
    headers = _publish_headers(worker, claim)
    path = _publish_path(claim)
    instance = str(side.app.instance_id)
    with TestClient(worker_api(side), base_url=BASE, headers=reader) as client:
        wrong = client.post(
            path,
            headers={**headers, "SKM-Instance-Id": str(uuid4())},
            content=_ndjson(_text(1, "wrong instance")),
        )
        problem(wrong, 422, "CONFIG_INVALID")
        assert wrong.headers.get_list("SKM-Instance-Id") == [instance]
        accepted = client.post(
            path, headers={**headers, "SKM-Instance-Id": instance}, content=_ndjson(_text(1))
        )
        assert accepted.status_code == 202, accepted.text
        assert accepted.headers.get_list("SKM-Instance-Id") == [instance]
        _cancel(side, assignment)
        with stream_live(client, assignment.attempt_id) as frames:
            assert list(frames) == [("text_delta", 1, _text(1)), ("end", None, {})]


@pytest.mark.parametrize("invalidate", [expire_now, _cancel])
def test_claim_lost_during_batch_redaction_leaves_ring_unchanged(live_case, invalidate):
    side, worker, reader, assignment, claim = live_case

    class InvalidateOnRedaction(Redactor):
        @override
        def document(self, value):
            clean = super().document(value)
            if isinstance(value, dict) and value.get("seq") == 2:
                invalidate(side, assignment)
            return clean

    headers = _publish_headers(worker, claim)
    with TestClient(
        worker_api(side, redactor=InvalidateOnRedaction()), base_url=BASE, headers=reader
    ) as client:
        path = _publish_path(claim)
        assert client.post(path, headers=headers, content=_ndjson(_text(1))).status_code == 202
        response = client.post(path, headers=headers, content=_ndjson(_text(2), _completed(3)))
        problem(response, 409, "LEASE_LOST")
        if invalidate is expire_now:
            _cancel(side, assignment)
        with stream_live(client, assignment.attempt_id) as frames:
            assert list(frames) == [("text_delta", 1, _text(1)), ("end", None, {})]


def test_assignment_token_cannot_publish(worker_side):
    side, _, _ = worker_side
    _, _, _, claimed, _, _, _, _, secret = owned_agent(side)
    raw = worker_claim(side, claimed)
    with TestClient(worker_api(side), base_url=BASE) as client:
        response = client.post(
            _publish_path(raw), content=b"invalid", headers=_publish_headers(bearer(secret), raw)
        )
        problem(response, 403, "FORBIDDEN")


@pytest.mark.parametrize("terminal", [_completed(1), _failed(1, "runtime failed")])
def test_ndjson_bounds_validation_and_atomic_redacted_replay(live_case, terminal):
    side, worker, reader, assignment, claim = live_case
    redactor = Redactor()
    redactor.register_secret(_HOST_SECRET)
    api = worker_api(side, redactor=redactor, settings={"api.limits.max_body_bytes": 1024})
    path = _publish_path(claim)
    headers = _publish_headers(worker, claim)
    head = _journal_head(side)
    with TestClient(api, base_url=BASE, headers=reader) as client:
        problem(client.post(path, json=_text(1), headers=worker), 415, "UNSUPPORTED_MEDIA_TYPE")
        problem(client.post(path, content=b"a" * 1025, headers=headers), 413, "PAYLOAD_TOO_LARGE")
        for bad_line in (b"\xff\n", b"{\n", _ndjson({**_text(2), "type": "unknown"}), b"\n"):
            response = client.post(path, content=_ndjson(_text(1)) + bad_line, headers=headers)
            problem(response, 422, "SCHEMA_INVALID")
        response = client.post(path, content=_ndjson(terminal, _text(2)), headers=headers)
        problem(response, 422, "SCHEMA_INVALID")
        token_secret = worker["Authorization"].split()[1]
        text = _text(1, f"{_HOST_SECRET}\n{token_secret}\npublic")
        failed = _failed(2, _HOST_SECRET)
        response = client.post(path, content=_ndjson(text, failed), headers=headers)
        assert response.status_code == 202, response.text
        problem(client.post(path, content=b"invalid", headers=headers), 422, "SCHEMA_INVALID")
        assert _journal_head(side) == head
        _cancel(side, assignment)

        with stream_live(client, assignment.attempt_id) as frames:
            assert list(frames) == [
                ("text_delta", 1, {**text, "text": f"{MASK}\n{MASK}\npublic"}),
                ("session_failed", 2, _failed(2, MASK)),
                ("end", None, {}),
            ]


@pytest.mark.parametrize("separate_posts", [False, True])
def test_subscriber_text_masks_secrets_split_between_deltas(live_case, separate_posts):
    side, worker, reader, assignment, claim = live_case
    redactor = Redactor()
    redactor.register_secret(_HOST_SECRET)
    headers = _publish_headers(worker, claim)
    with TestClient(worker_api(side, redactor=redactor), base_url=BASE, headers=reader) as client:
        half = len(_HOST_SECRET) // 2
        token = "ghp_" + "A" * 30
        parts = [
            _text(1, "before " + _HOST_SECRET[:half]),
            _text(2, _HOST_SECRET[half:] + " " + token[:12]),
            _text(3, token[12:] + " after"),
            _completed(4),
        ]
        for batch in [[part] for part in parts] if separate_posts else [parts]:
            response = client.post(_publish_path(claim), content=_ndjson(*batch), headers=headers)
            assert response.status_code == 202, response.text
        _cancel(side, assignment)
        with stream_live(client, assignment.attempt_id) as frames:
            deltas = [event for name, _, event in frames if name == "text_delta" and isinstance(event, dict)]
        assert [event["seq"] for event in deltas] == [1, 2, 3]
        joined = "".join(str(event["text"]) for event in deltas)
        assert joined.startswith("before ")
        assert joined.endswith(" after")
        assert MASK in joined
        assert _HOST_SECRET[:half] not in joined
        assert _HOST_SECRET[half:] not in joined
        assert token not in joined
        assert token[12:] not in joined


def test_ring_gap_cursor_precedence_and_restart(live_case):
    side, worker, reader, assignment, claim = live_case
    api = worker_api(side, settings={"api.live.buffer_events": 2, "api.sse.batch_size": 1})
    with TestClient(api, base_url=BASE, headers=reader) as client:
        response = client.post(
            _publish_path(claim),
            content=_ndjson(_text(1), _text(2), _completed(3)),
            headers=_publish_headers(worker, claim),
        )
        assert response.status_code == 202, response.text
        _cancel(side, assignment)
        with stream_live(client, assignment.attempt_id) as frames:
            assert list(frames) == [
                ("gap", 1, {"after": 0, "oldest": 2, "reason": "buffer_evicted"}),
                ("text_delta", 2, _text(2)),
                ("session_completed", 3, _completed(3)),
                ("end", None, {}),
            ]
        resumed = client.get(
            _subscribe_path(claim), params={"after": "invalid"}, headers={"Last-Event-ID": "2"}
        )
        assert "id: 3\nevent: session_completed" in resumed.text
        assert "event: gap" not in resumed.text
        assert "event: text_delta" not in resumed.text

    with (
        TestClient(worker_api(side), base_url=BASE, headers=reader) as restarted,
        stream_live(restarted, assignment.attempt_id, after=3) as frames,
    ):
        assert list(frames) == [
            ("gap", 0, {"after": 3, "oldest": None, "reason": "buffer_missing"}),
            ("end", None, {}),
        ]


def test_restart_replays_new_buffer_when_previous_cursor_is_ahead(live_case):
    side, worker, reader, assignment, claim = live_case
    with TestClient(worker_api(side), base_url=BASE, headers=reader) as original:
        response = original.post(
            _publish_path(claim),
            content=_ndjson(_text(1), _text(2), _text(3)),
            headers=_publish_headers(worker, claim),
        )
        assert response.status_code == 202, response.text

    with TestClient(worker_api(side), base_url=BASE, headers=reader) as restarted:
        response = restarted.post(
            _publish_path(claim),
            content=_ndjson(_text(4), _completed(5)),
            headers=_publish_headers(worker, claim),
        )
        assert response.status_code == 202, response.text
        _cancel(side, assignment)
        with stream_live(restarted, assignment.attempt_id, after=3) as frames:
            assert list(frames) == [
                ("gap", 0, {"after": 3, "oldest": None, "reason": "buffer_missing"}),
                ("text_delta", 1, _text(4)),
                ("session_completed", 2, _completed(5)),
                ("end", None, {}),
            ]


def test_subscribe_hides_unreadable_and_unknown_attempts(live_case):
    side, _, reader, _, claim = live_case
    path = _subscribe_path(claim)
    with TestClient(worker_api(side), base_url=BASE, headers=reader) as client:
        for restricted in ({"scope_id": side.ws2}, {"scope_id": side.ws, "permissions": ("workspace.read",)}):
            token = _reader(side, **restricted)
            problem(client.get(path, headers=bearer(token.secret)), 404, "NOT_FOUND")
        problem(client.get(_subscribe_path({"attempt_id": uuid4()})), 404, "NOT_FOUND")
        for after in ("-1", "x", "9223372036854775808"):
            problem(client.get(path, params={"after": after}), 422, "SCHEMA_INVALID")


def test_incompatible_schema_has_no_live_routes(live_case):
    side, _, _, _, _ = live_case
    api = create_app(side.app, settings={}, schema_check=lambda: ErrorCode.SCHEMA_NOT_MIGRATED)
    assert {route.path for route in api.routes if isinstance(route, Route)}.isdisjoint(
        {"/api/v1/worker/attempts/{attempt_id}/live", "/api/v1/attempts/{attempt_id}/live"}
    )


@asynccontextmanager
async def _open(api, path, reader, *, blocked=False, query=b""):
    incoming: asyncio.Queue[Message] = asyncio.Queue()
    messages: asyncio.Queue[Message] = asyncio.Queue()
    incoming.put_nowait({"type": "http.request", "body": b""})
    headers = {"Host": "127.0.0.1:8765", **reader}
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "query_string": query,
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
    }

    async def send(message: Message) -> None:
        messages.put_nowait(message)
        if blocked and message.get("more_body"):
            await asyncio.Future()

    task = asyncio.create_task(api(scope, incoming.get, send))
    try:
        start = await asyncio.wait_for(messages.get(), 4)
        assert start["type"] == "http.response.start"
        yield _Stream(start["status"], Headers(raw=start["headers"]), messages, deque(), task)
    finally:
        incoming.put_nowait({"type": "http.disconnect"})
        await asyncio.wait_for(task, 4)


@pytest.mark.anyio
async def test_replay_spans_three_sessions_until_attempt_finishes(live_case):
    side, worker, reader, assignment, claim = live_case
    api = worker_api(side, settings={"api.sse.heartbeat_seconds": 1, "api.sse.batch_size": 2})

    def started(role):
        return {
            "type": "session_started",
            "seq": 1,
            "at": _AT,
            "session_ref": role,
            "model": None,
            "runtime_version": None,
        }

    usage = {
        "type": "usage_reported",
        "seq": 2,
        "at": _AT,
        "usage": {
            "input_tokens": 12,
            "output_tokens": 2,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
            "reasoning_tokens": None,
            "cost_usd_micros": None,
            "status": "reported",
            "source": "stream:result",
            "subagents": {"used": None, "disclosed": False},
        },
        "cumulative": True,
    }
    batches = (
        (started("scout"), _text(2, "context brief"), _completed(3)),
        (
            started("executor"),
            {
                "type": "tool_requested",
                "seq": 2,
                "at": _AT,
                "call_id": "read-1",
                "tool": "read",
                "args_preview": "README.md",
                "args_digest": "sha256:" + "2" * 64,
            },
            {
                "type": "tool_completed",
                "seq": 3,
                "at": _AT,
                "call_id": "read-1",
                "status": "ok",
                "duration_ms": 10,
            },
            {"type": "checkpoint_available", "seq": 4, "at": _AT, "session_ref": "executor"},
            _completed(5),
        ),
        (
            started("reviewer"),
            usage,
            {"type": "cancel_ignored", "seq": 3, "at": _AT, "signal": "SIGTERM"},
            _failed(4, "runtime failed"),
        ),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url=BASE) as client:
        for batch in batches:
            response = await asyncio.wait_for(
                client.post(
                    _publish_path(claim), content=_ndjson(*batch), headers=_publish_headers(worker, claim)
                ),
                timeout=4,
            )
            assert response.status_code == 202, response.text

    async with _open(api, _subscribe_path(claim), reader) as stream:
        assert stream.status == 200
        events = [event for batch in batches for event in batch]
        for cursor, event in enumerate(events, start=1):
            frame = await stream.take()
            assert frame is not None
            ident, kind, data = frame.splitlines()
            assert ident == f"id: {cursor}"
            assert kind == f"event: {event['type']}"
            assert json.loads(data.removeprefix("data: ")) == event
        assert (await stream.take() or "").startswith(": ping ")

        _cancel(side, assignment)
        assert await stream.take() == "event: end\ndata: {}"
        assert await stream.take() is None


@pytest.mark.anyio
@pytest.mark.parametrize("wake", ["publish", "heartbeat"])
async def test_live_revocation_rechecked_before_further_frames(live_case, wake):
    side, worker, _, _, claim = live_case
    token = _reader(side)
    api = worker_api(side, settings={"api.sse.heartbeat_seconds": 1 if wake == "heartbeat" else 60})
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url=BASE) as client,
        _open(api, _subscribe_path(claim), bearer(token.secret), query=b"after=34") as stream,
    ):
        assert stream.status == 200
        first = await stream.take()
        assert first is not None
        assert first.startswith("id: 0\nevent: gap\n")
        if wake == "heartbeat":
            assert (await stream.take() or "").startswith(": ping ")
        side.client.dispatch(RevokeToken(token.token_id))
        if wake == "publish":
            response = await client.post(
                _publish_path(claim), content=_ndjson(_text(1)), headers=_publish_headers(worker, claim)
            )
            assert response.status_code == 202, response.text
        assert await stream.take() is None


@pytest.mark.anyio
async def test_live_rechecks_run_read_on_heartbeat(live_case):
    side, worker, _, _, claim = live_case
    api = worker_api(side, settings={"api.sse.heartbeat_seconds": 1})
    async with _open(api, _subscribe_path(claim), worker) as stream:
        assert stream.status == 200
        assert "event: gap" in (await stream.take() or "")
        principal = side.worker1_client._actor.principal_id
        side.client.dispatch(RevokeMembership(side.ws, principal))
        assert await stream.take() is None


@pytest.mark.anyio
@pytest.mark.parametrize("close_by", ["overflow", "disconnect"])
async def test_blocked_sse_send_releases_slot(live_case, close_by):
    side, worker, reader, _, claim = live_case
    api = worker_api(side, settings={"api.sse.queue_size": 1, "api.sse.max_streams_per_token": 1})
    path = _subscribe_path(claim)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url=BASE) as client:
        async with _open(api, path, reader, blocked=True) as slow:
            assert slow.status == 200
            assert slow.headers["content-type"] == "text/event-stream; charset=utf-8"
            assert slow.headers["cache-control"] == "no-store"
            assert slow.headers["x-accel-buffering"] == "no"
            assert "event: gap" in (await slow.take() or "")
            excess = await asyncio.wait_for(client.get(path, headers=reader), 4)
            problem(excess, 429, "TOO_MANY_STREAMS")
            durable = await asyncio.wait_for(
                client.get("/api/v1/events", params={"workspace_id": str(side.ws)}, headers=reader), 4
            )
            problem(durable, 429, "TOO_MANY_STREAMS")
            if close_by == "overflow":
                headers = _publish_headers(worker, claim)
                for seq in (1, 2):
                    response = await asyncio.wait_for(
                        client.post(_publish_path(claim), content=_ndjson(_text(seq)), headers=headers), 4
                    )
                    assert response.status_code == 202, response.text
                await asyncio.wait_for(asyncio.shield(slow.task), 4)
                async with _open(api, path, reader) as reopened:
                    assert reopened.status == 200
                    assert "id: 1\nevent: text_delta" in (await reopened.take() or "")
        async with _open(api, path, reader) as reopened:
            assert reopened.status == 200


@pytest.mark.anyio
@pytest.mark.parametrize("revoke", ["token", "run.read"])
async def test_revocation_cancels_blocked_send_without_publication(live_case, revoke):
    side, worker, _, _, claim = live_case
    api = worker_api(side, settings={"api.sse.max_streams_per_token": 1, "api.sse.heartbeat_seconds": 1})
    token = _reader(side)
    headers = bearer(token.secret) if revoke == "token" else worker
    path = _subscribe_path(claim)
    async with _open(api, path, headers, blocked=True) as slow:
        assert slow.status == 200
        assert "event: gap" in (await slow.take() or "")
        if revoke == "token":
            side.client.dispatch(RevokeToken(token.token_id))
        else:
            principal = side.worker1_client._actor.principal_id
            side.client.dispatch(RevokeMembership(side.ws, principal))
        await asyncio.wait_for(asyncio.shield(slow.task), 4)
        if revoke == "run.read":
            side.client.dispatch(
                GrantMembership.from_json(
                    {"scope_id": str(side.ws), "principal_id": str(principal), "role": "worker"}
                )
            )
            async with _open(api, path, headers) as reopened:
                assert reopened.status == 200
