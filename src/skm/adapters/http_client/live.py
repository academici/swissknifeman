"""Best-effort worker live publication and client replay over HTTP."""

from __future__ import annotations

import asyncio
import json
import ssl
from collections import deque
from collections.abc import Callable, Generator, Iterator, Mapping
from contextlib import contextmanager, suppress
from itertools import groupby
from threading import Event, Lock, Thread
from typing import cast
from uuid import UUID

import httpx

from skm.adapters.http_client.auth import CLIENT_VERSION
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.logging.redaction import Redactor, mask_spans

__all__ = ["LivePublisher", "stream_live"]

_MAX_COUNTER = 2**63 - 1
_HTTP_DEADLINE_SECONDS = 5


class LivePublisher:
    """One attempt's live sink. The runtime only calls ``offer`` and reads ``dropped``."""

    def __init__(  # noqa: PLR0913 -- explicit transport, batching, and binding options
        self,
        base_url: str,
        token: str | Callable[[], str],
        claim: Mapping[str, JsonValue],
        *,
        settings: Mapping[str, JsonValue] | None = None,
        redactor: Redactor | None = None,
        max_entries: int = 256,
        transport: httpx.AsyncBaseTransport | None = None,
        verify: ssl.SSLContext | bool = True,
        expected_instance_id: UUID | None = None,
    ) -> None:
        settings = settings or {}
        self._max_bytes = cast("int", settings.get("api.limits.max_body_bytes", 1_048_576))
        self._interval = cast("int", settings.get("api.live.batch_ms", 250)) / 1000
        if min(max_entries, self._max_bytes, self._interval) <= 0:
            raise ValueError("Live publisher ceilings and batch interval must be positive")
        self._max_entries = max_entries
        self._base_url = base_url
        self._path = f"/api/v1/worker/attempts/{UUID(cast('str', claim['attempt_id']))}/live"
        self._headers = {
            "SKM-Worker-Claim": json.dumps(dict(claim), separators=(",", ":"), allow_nan=False),
            "Content-Type": "application/x-ndjson",
            "SKM-Client-Version": CLIENT_VERSION,
        }
        self._expected_instance = str(expected_instance_id) if expected_instance_id is not None else None
        if self._expected_instance is not None:
            self._headers["SKM-Instance-Id"] = self._expected_instance
        self._transport = transport
        self._verify = verify
        self._token = token if callable(token) else lambda: token
        self._redactor = redactor or Redactor()
        self._credential_redactor = Redactor(patterns=())
        self._queue: deque[bytes] = deque()
        self._queued_bytes = 0
        self._lock = Lock()
        self._loss_lock = Lock()
        self._dropped = 0
        self._in_flight = 0
        self._tail = ""
        self._closed = False
        self._idle = Event()
        self._idle.set()
        self._flush_requested = False
        self._sender: tuple[asyncio.AbstractEventLoop, asyncio.Task[None], asyncio.Event] | None = None
        self._thread = Thread(target=self._send_loop, daemon=True, name="skm-live-publisher")
        self._thread.start()

    @property
    def dropped(self) -> int:
        with self._loss_lock:
            return self._dropped

    @property
    def live_events_dropped(self) -> int:
        return self.dropped

    @property
    def live_delivery_gap(self) -> bool:
        return self.dropped > 0

    def offer(self, event: bytes) -> bool:
        """Offer one serialized event from the runtime capture thread."""
        if self._lock.acquire(blocking=False):
            try:
                size = len(event) + 1  # NDJSON separator
                if (
                    not self._closed
                    and len(self._queue) < self._max_entries
                    and size <= self._max_bytes - self._queued_bytes
                ):
                    self._queue.append(event)
                    self._queued_bytes += size
                    self._idle.clear()
                    return True
            finally:
                self._lock.release()
        self._drop(1)
        return False

    def _drop(self, count: int) -> None:
        with self._loss_lock:
            self._dropped = min(_MAX_COUNTER, self._dropped + count)

    def _discard_pending(self) -> None:
        # Called under _lock. A late acknowledgement cannot settle these events twice.
        self._drop(len(self._queue) + self._in_flight)
        self._queue.clear()
        self._in_flight = self._queued_bytes = 0
        self._idle.set()

    def flush(self) -> None:
        """Give final deltas a bounded delivery window while the claim is still valid."""
        with self._lock:
            if self._idle.is_set():
                return
            self._flush_requested = True
            sender = self._sender
        if sender is not None:
            loop, _, wake = sender
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(wake.set)
        self._idle.wait(0.25)

    def close(self) -> None:
        """Cancel delivery and settle all unacknowledged events before returning."""
        with self._lock:
            sender = None if self._closed else self._sender
            self._closed = True
        if sender is not None:
            loop, task, _ = sender
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(task.cancel)
        self._thread.join(timeout=0.25)
        with self._lock:
            self._discard_pending()

    def _send_loop(self) -> None:
        try:
            with suppress(asyncio.CancelledError):
                asyncio.run(self._run())
        finally:
            with self._lock:
                self._closed = True
                self._sender = None
                self._discard_pending()

    async def _run(self) -> None:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Live publisher requires a running task")
        wake = asyncio.Event()
        with self._lock:
            if self._closed:
                return
            self._sender = asyncio.get_running_loop(), task, wake
            if self._flush_requested:
                wake.set()
        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            transport=self._transport,
            trust_env=False,
            verify=self._verify,
        ) as client:
            while not self._closed:
                with suppress(TimeoutError):
                    await asyncio.wait_for(wake.wait(), timeout=self._interval)
                wake.clear()
                with self._lock:
                    queued, self._queue = self._queue, deque()
                    self._queued_bytes = 0
                    self._in_flight = len(queued)
                if not queued:
                    continue
                token = self._token()
                self._credential_redactor.register_secret(token)
                for body, count in self._batches(queued):
                    if self._closed:
                        return
                    delivered = await self._post(client, body, token)
                    self._settle(count, delivered)

    def _settle(self, count: int, delivered: bool) -> None:
        with self._lock:
            if self._in_flight:
                self._in_flight -= count
                if not delivered:
                    self._drop(count)
            if not self._queue and not self._in_flight:
                self._idle.set()

    def _text(self, value: str) -> str:
        return self._credential_redactor.text(self._redactor.text(value))

    def _redact_deltas(self, events: list[JsonObject]) -> None:
        # Coalesce only within one output channel and only if masking changes a frame boundary.
        def channel(event: JsonObject) -> JsonValue:
            return event.get("channel") if event.get("type") == "text_delta" else None

        for name, group in groupby(events, key=channel):
            if name is None:
                self._tail = ""
                continue
            deltas = list(group)
            parts = [cast("str", event["text"]) for event in deltas]
            raw = "".join(parts)
            joined = self._tail + raw
            boundary = len(self._tail)
            current = self._text(raw)
            if self._tail and self._text(joined) != self._text(self._tail) + current:
                # Project onto unsent text by original offsets. Previously sent text cannot be replayed.
                spans: list[tuple[int, int]] = []
                known: set[str] = set()
                for redactor in (self._redactor, self._credential_redactor):
                    values = redactor._known()  # pyright: ignore[reportPrivateUsage]
                    known.update(values)
                    spans.extend(
                        (max(start - boundary, 0), stop - boundary)
                        for start, stop in redactor._spans(joined, values)  # pyright: ignore[reportPrivateUsage]
                        if stop > boundary
                    )
                current = self._text(mask_spans(raw, spans, tuple(known)))
            if current != "".join(self._text(part) for part in parts):
                deltas[0]["text"] = current
                for delta in deltas[1:]:
                    delta["text"] = ""
            self._tail = joined[-self._max_bytes :]

    def _batches(self, queued: deque[bytes]) -> Iterator[tuple[bytes, int]]:
        events: list[JsonObject] = []
        for raw in queued:
            try:
                event: JsonValue = json.loads(raw.decode("utf-8"))
                if not isinstance(event, dict) or (
                    event.get("type") == "text_delta" and not isinstance(event.get("text"), str)
                ):
                    raise ValueError("invalid live event")
                events.append(event)
            except (ValueError, RecursionError):
                self._settle(1, False)
        self._redact_deltas(events)
        batch = bytearray()
        count = 0
        for event in events:
            try:
                clean = self._credential_redactor.document(self._redactor.document(event))
                line = json.dumps(clean, separators=(",", ":"), allow_nan=False).encode() + b"\n"
            except (ValueError, RecursionError):
                self._settle(1, False)
                continue
            if len(line) > self._max_bytes:
                self._settle(1, False)
                continue
            if len(batch) + len(line) > self._max_bytes:
                yield bytes(batch), count
                batch.clear()
                count = 0
            batch.extend(line)
            count += 1
        if batch:
            yield bytes(batch), count

    async def _post(self, client: httpx.AsyncClient, body: bytes, token: str) -> bool:
        try:
            async with (
                asyncio.timeout(_HTTP_DEADLINE_SECONDS),
                client.stream(
                    "POST", self._path, content=body, headers={"Authorization": f"Bearer {token}"}
                ) as response,
            ):
                if self._expected_instance is not None and response.headers.get_list("SKM-Instance-Id") != [
                    self._expected_instance
                ]:
                    return False
                return response.status_code == 202
        except (TimeoutError, httpx.RequestError):
            return False


def _frames(lines: Iterator[str]) -> Iterator[tuple[str, int | None, JsonValue]]:
    name = "message"
    ident: int | None = None
    data: list[str] = []
    for line in lines:
        if not line:
            if data:
                yield name, ident, json.loads("\n".join(data))
            name, ident = "message", None
            data.clear()
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            name = value
        elif field == "id":
            ident = int(value)
        elif field == "data":
            data.append(value)


@contextmanager
def stream_live(
    client: httpx.Client, attempt_id: UUID, *, after: int = 0
) -> Generator[Iterator[tuple[str, int | None, JsonValue]]]:
    """Open an authenticated live stream using the supplied client's base URL and credentials."""
    with client.stream(
        "GET",
        f"/api/v1/attempts/{attempt_id}/live",
        params={"after": after},
        headers={"Accept": "text/event-stream", "SKM-Client-Version": CLIENT_VERSION},
    ) as response:
        response.raise_for_status()
        yield _frames(response.iter_lines())
