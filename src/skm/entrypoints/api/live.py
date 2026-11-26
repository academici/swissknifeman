"""Fenced NDJSON ingress and ephemeral per-attempt SSE replay."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from collections.abc import AsyncGenerator, Callable, Mapping
from dataclasses import dataclass
from io import BytesIO
from itertools import groupby, islice
from typing import cast
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from skm.application_bus.context import AuthBasis
from skm.bootstrap.composition import App
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, SkmError, error_for
from skm.kernel.ids import AttemptId, ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Isolation, RequestMeta
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access.public import RbacAuthorizer, effective_permissions
from skm.modules.execution.public import get_attempt_summary, require_live_attempt_claim
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.system_clock import SystemClock

from .auth import request_auth_basis
from .middleware import BodyPolicy
from .request_context import request_meta
from .sse import (
    _MAX_REVOCATION_RECHECK_SECONDS,  # pyright: ignore[reportPrivateUsage]
    _cursor_input,  # pyright: ignore[reportPrivateUsage]
    _Response,  # pyright: ignore[reportPrivateUsage]
    _Subscription,  # pyright: ignore[reportPrivateUsage]
)

__all__ = ["LIVE_BODY_POLICY", "AttemptLive"]

_PUBLISH_PATH = "/api/v1/worker/attempts/{attempt_id}/live"
_SUBSCRIBE_PATH = "/api/v1/attempts/{attempt_id}/live"
_EVENT_SCHEMA = "urn:skm:runtimes:session-event:v1"
_SESSION_TERMINAL_EVENTS = frozenset({"session_completed", "session_failed"})
_CLAIM_IDS = frozenset({"assignment_id", "attempt_id", "worker_id"})
_CLAIM_FIELDS = _CLAIM_IDS | {"fencing_token"}
_SSE_HEADERS = {"X-Accel-Buffering": "no"}
LIVE_BODY_POLICY = BodyPolicy("POST", _PUBLISH_PATH, media_type="application/x-ndjson")


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON property")
    return result


def _reject_constant(value: str) -> JsonValue:
    raise ValueError(f"invalid JSON constant {value}")


def _load_json(value: str) -> JsonValue:
    return json.loads(value, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _attempt_id(request: Request) -> AttemptId:
    try:
        return AttemptId(UUID(request.path_params["attempt_id"]))
    except ValueError:
        raise error_for(ErrorCode.NOT_FOUND, "Attempt not found") from None


def _worker_claim(request: Request, attempt_id: AttemptId) -> JsonObject:
    values = request.headers.getlist("skm-worker-claim")
    try:
        if len(values) != 1:
            raise ValueError("expected one worker claim")
        claim = _load_json(values[0])
        if not isinstance(claim, dict) or claim.keys() != _CLAIM_FIELDS:
            raise ValueError("invalid worker claim fields")
        if any(not isinstance(claim[field], str) for field in _CLAIM_IDS):
            raise ValueError("invalid worker claim IDs")
        claimed_attempt = UUID(cast("str", claim["attempt_id"]))
    except (ValueError, RecursionError):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid SKM-Worker-Claim header") from None
    if claimed_attempt != attempt_id:
        raise error_for(ErrorCode.SCHEMA_INVALID, "claim.attempt_id does not match path attempt_id")
    return claim


def _redact_deltas(events: list[JsonObject], tail: str, redactors: tuple[Redactor, ...]) -> str:
    """Mask consecutive deltas together, projecting matches back to their original frames."""
    for is_text, group in groupby(events, key=lambda event: event.get("type") == "text_delta"):
        if not is_text:
            tail = ""
            continue
        deltas = list(group)
        parts = [cast("str", event["text"]) for event in deltas]
        joined = tail + "".join(parts)
        spans: list[tuple[int, int]] = []
        # Always retain the preceding delta, including one larger than the usual window.
        keep = max(4096, len(parts[-1]))
        for redactor in redactors:
            known = redactor._known()  # pyright: ignore[reportPrivateUsage] -- original-input span projection
            spans.extend(redactor._spans(joined, known))  # pyright: ignore[reportPrivateUsage]
            for secret in known:
                keep = max(keep, len(secret))
                # A registered prefix at the open end may be completed by the next POST.
                at = joined.find(secret[0], max(0, len(joined) - len(secret) + 1))
                while at >= 0:
                    if secret.startswith(joined[at:]):
                        spans.append((at, len(joined)))
                        break
                    at = joined.find(secret[0], at + 1)

        merged: deque[tuple[int, int]] = deque()
        for start, stop in sorted(spans):
            if merged and start <= merged[-1][1]:
                merged[-1] = merged[-1][0], max(stop, merged[-1][1])
            elif start < stop:
                merged.append((start, stop))
        offset = len(tail)
        for event, part in zip(deltas, parts, strict=True):
            end = offset + len(part)
            cursor = offset
            clean: list[str] = []
            while merged and merged[0][0] < end:
                start, stop = merged[0]
                if stop > cursor:
                    clean.extend((joined[cursor : max(cursor, start)], MASK))
                    cursor = min(stop, end)
                if stop > end:
                    break
                merged.popleft()
            event["text"] = "".join(clean) + joined[cursor:end]
            offset = end
        tail = joined[-keep:]
    return tail


def _gap(after: int, oldest: int | None) -> str:
    cursor = 0 if oldest is None else oldest - 1
    reason = "buffer_missing" if oldest is None else "buffer_evicted"
    data = json.dumps({"reason": reason, "after": after, "oldest": oldest}, separators=(",", ":"))
    return f"id: {cursor}\nevent: gap\ndata: {data}\n\n"


@dataclass(slots=True)
class _Buffer:
    frames: deque[str]
    tail: str = ""
    head: int = 0

    def replay(self, after: int, limit: int) -> tuple[int, str]:
        oldest = self.head - len(self.frames) + 1
        gap = ""
        restarted = after > self.head
        if restarted or after < oldest - 1:
            gap = _gap(after, None if restarted else oldest)
            after = oldest - 1
        if after >= self.head:
            return after, gap
        start = after - oldest + 1
        stop = min(start + limit, len(self.frames))
        frames = islice(self.frames, start, stop)
        return oldest + stop - 1, gap + "".join(
            f"id: {ident}\n{frame}" for ident, frame in enumerate(frames, after + 1)
        )


class _LiveResponse(_Response):
    def __init__(
        self, body: AsyncGenerator[str], feed: _Subscription, heartbeat: int, check: Callable[[], bool]
    ) -> None:
        super().__init__(body, feed, heartbeat=heartbeat, check=check)


class AttemptLive:
    def __init__(
        self,
        app: App,
        settings: Mapping[str, JsonValue],
        counts: dict[tuple[str, UUID], int],
        redactor: Redactor,
    ) -> None:
        self._app = app
        self._clock = getattr(app, "clock", None) or SystemClock()
        self._auth = RbacAuthorizer(self._clock)
        self._buffer_size = max(1, cast("int", settings.get("api.live.buffer_events", 2000)))
        self._queue_size = max(1, cast("int", settings.get("api.sse.queue_size", 1000)))
        self._batch_size = min(self._queue_size, max(1, cast("int", settings.get("api.sse.batch_size", 200))))
        self._max_streams = max(1, cast("int", settings.get("api.sse.max_streams_per_token", 8)))
        self._heartbeat = max(1, cast("int", settings.get("api.sse.heartbeat_seconds", 15)))
        self._poll = max(1, cast("int", settings.get("api.sse.poll_ms", 2000))) / 1000
        self._buffers: dict[AttemptId, _Buffer] = {}
        self._feeds: dict[AttemptId, set[_Subscription]] = {}
        self._counts = counts
        self._redactor = redactor
        self._writers: dict[AttemptId, asyncio.Lock] = {}

    def routes(self) -> tuple[Route, Route]:
        return (
            Route(_PUBLISH_PATH, self.publish, methods=["POST"]),
            Route(_SUBSCRIBE_PATH, self.subscribe, methods=["GET"]),
        )

    def notify_access_changed(self) -> None:
        """Wake active live attempt subscribers to immediately re-check credentials and memberships."""
        for subscriptions in tuple(self._feeds.values()):
            for subscription in tuple(subscriptions):
                subscription.wake_check()

    async def publish(self, request: Request) -> Response:
        basis = request_auth_basis(request)
        if not basis.is_worker_token:
            raise error_for(ErrorCode.FORBIDDEN, "Live publish requires a worker token")
        attempt_id = _attempt_id(request)
        claim = _worker_claim(request, attempt_id)
        meta = request_meta(request)
        await run_in_threadpool(self._require_claim, basis, meta, attempt_id, claim)
        body = await request.body()
        async with self._writers.setdefault(attempt_id, asyncio.Lock()):
            buffer = self._buffers.get(attempt_id)
            if buffer is None:
                buffer = _Buffer(deque(maxlen=self._buffer_size))
            frames, tail = await run_in_threadpool(
                self._parse_batch, body, cast("Redactor", request.state.redactor), buffer.tail
            )

            loop = asyncio.get_running_loop()

            pending = True

            async def append() -> None:
                if not pending:
                    return  # The request was cancelled and no longer owns the writer lock.
                buffer.frames.extend(frames)
                buffer.head += len(frames)
                buffer.tail = tail
                self._buffers[attempt_id] = buffer
                for feed in tuple(self._feeds.get(attempt_id, ())):
                    for _ in frames:
                        feed.notify()
                        if feed.closed.done():
                            break

            try:
                await run_in_threadpool(
                    self._require_claim,
                    basis,
                    meta,
                    attempt_id,
                    claim,
                    lambda: asyncio.run_coroutine_threadsafe(append(), loop).result(),
                )
            finally:
                pending = False
        return Response(status_code=202)

    def _require_claim(
        self,
        basis: AuthBasis,
        meta: RequestMeta,
        attempt_id: AttemptId,
        claim: JsonObject,
        append: Callable[[], None] | None = None,
    ) -> None:
        # The execution facade locks the lease and tests its current fence. Exiting rolls back
        # its value-preserving renewal, keeping live publication outside the durable write path.
        actor = basis.actor
        with self._app.uow_factory(meta) as uow:
            self._auth.admit_basis(uow, basis)
            try:
                require_live_attempt_claim(
                    uow, actor, attempt_id=attempt_id, raw_claim=claim, now=self._clock.now()
                )
            except SkmError as error:
                if error.code == ErrorCode.FORBIDDEN:
                    raise error_for(ErrorCode.LEASE_LOST, "Worker does not hold the attempt claim") from None
                raise
            attempt = get_attempt_summary(uow, attempt_id)
            run = uow.repo(ScopeRegistry).get(ScopeId(UUID(cast("str", attempt["run_id"]))))
            if run.workspace_id is None or "worker.claim" not in effective_permissions(
                uow, actor, ScopeId(run.workspace_id)
            ):
                raise error_for(ErrorCode.FORBIDDEN, "Live publish requires worker.claim")

            if append is not None:
                # Keep the DB fence locked until the ASGI loop has made the whole batch visible.
                append()

    def _parse_batch(self, body: bytes, redactor: Redactor, tail: str) -> tuple[list[str], str]:
        events: list[JsonObject] = []
        terminal = False
        try:
            for line in BytesIO(body):
                if terminal:
                    raise ValueError("Terminal SessionEvent must end the batch")
                event = _load_json(line.decode("utf-8"))
                if not isinstance(event, dict) or self._app.schemas.validate(_EVENT_SCHEMA, event):
                    raise ValueError("invalid SessionEvent")
                events.append(event)
                terminal = cast("str", event["type"]) in _SESSION_TERMINAL_EVENTS
            if not events:
                raise ValueError("empty SessionEvent batch")
            tail = _redact_deltas(events, tail, (self._redactor, redactor))
            frames: list[str] = []
            for event in events:
                data = json.dumps(redactor.document(event), separators=(",", ":"), allow_nan=False)
                frames.append(f"event: {event['type']}\ndata: {data}\n\n")
        except (ValueError, RecursionError):
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid SessionEvent in NDJSON batch") from None
        return frames, tail

    async def subscribe(self, request: Request) -> Response:
        attempt_id = _attempt_id(request)
        after = _cursor_input(
            request.headers.getlist("last-event-id") or request.query_params.getlist("after")
        )
        basis = request_auth_basis(request)
        quota_key = basis.stream_quota_key
        meta = request_meta(request)
        await run_in_threadpool(self._attempt_finished, basis, meta, attempt_id)
        if request.method == "HEAD":
            return Response(media_type="text/event-stream", headers=_SSE_HEADERS)
        count = self._counts.get(quota_key, 0)
        if count >= self._max_streams:
            raise error_for(ErrorCode.TOO_MANY_STREAMS, "Too many active event streams")

        def release() -> None:
            self._feeds[attempt_id].remove(feed)
            if not self._feeds[attempt_id]:
                del self._feeds[attempt_id]
            self._counts[quota_key] -= 1
            if not self._counts[quota_key]:
                del self._counts[quota_key]

        feed = _Subscription(self._queue_size, release)
        self._counts[quota_key] = count + 1
        self._feeds.setdefault(attempt_id, set()).add(feed)
        return _LiveResponse(
            self._stream(basis, meta, attempt_id, after or 0, feed),
            feed,
            self._heartbeat,
            lambda: self._attempt_finished(basis, meta, attempt_id),
        )

    def _attempt_finished(self, basis: AuthBasis, meta: RequestMeta, attempt_id: AttemptId) -> bool:
        with self._app.uow_factory(meta, readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
            self._auth.admit_basis(uow, basis)
            try:
                attempt = get_attempt_summary(uow, attempt_id)
                run_id = ScopeId(UUID(cast("str", attempt["run_id"])))
                if "run.read" in effective_permissions(uow, basis.actor, run_id):
                    return attempt["finished_at"] is not None
            except NotFound:
                pass
        raise error_for(ErrorCode.NOT_FOUND, "Attempt not found")

    async def _stream(
        self, basis: AuthBasis, meta: RequestMeta, attempt_id: AttemptId, after: int, feed: _Subscription
    ) -> AsyncGenerator[str]:
        loop = asyncio.get_running_loop()
        heartbeat_at = loop.time() + self._heartbeat
        first = True
        try:
            while not feed.closed.done():
                feed.drain()
                finished = await run_in_threadpool(self._attempt_finished, basis, meta, attempt_id)
                if feed.closed.done():
                    return
                buffer = self._buffers.get(attempt_id)
                if buffer is not None:
                    after, frames = buffer.replay(after, self._batch_size)
                    more = after < buffer.head
                    if frames:
                        yield frames
                    if more:
                        first = False
                        continue
                elif first:
                    yield _gap(after, None)
                    after = 0
                if finished:
                    yield "event: end\ndata: {}\n\n"
                    return
                if loop.time() >= heartbeat_at:
                    heartbeat_at = loop.time() + self._heartbeat
                    yield f": ping {time.time_ns() // 1_000_000}\n\n"
                first = False
                await feed.wait(
                    min(self._poll, _MAX_REVOCATION_RECHECK_SECONDS, max(0.0, heartbeat_at - loop.time()))
                )
        except SkmError:
            # Reconnect goes through normal HTTP admission after a live credential or scope changes.
            return
