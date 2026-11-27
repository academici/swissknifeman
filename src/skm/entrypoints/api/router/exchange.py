"""Bounded SSE replay for independently cancellable HTTP subscribers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.types import Send

__all__ = ["Exchange", "Reply", "max_response_bytes", "max_sse_event_bytes"]

max_response_bytes = 16 * 1024 * 1024
max_sse_event_bytes = 1024 * 1024
_MAX_REPLAY_FRAMES = 4096


@dataclass(frozen=True, slots=True)
class Reply:
    status: int
    headers: dict[str, str] = field(default_factory=dict[str, str])
    body: bytes | None = None


class Exchange:
    """Replay one in-flight stream's prefix, then retain only unread events.

    A subscriber that arrives after the replay window closes starts a new exchange.
    Existing subscribers exert backpressure and can independently disconnect.
    """

    def __init__(self, produce: Callable[[Exchange], Awaitable[None]]) -> None:
        self.joinable = True
        self._positions: dict[object, int] = {}
        self._frames: dict[int, bytes] = {}
        self._size = self._offset = 0
        self._reply: Reply | None = None
        self._changed = asyncio.Event()
        self._done = False
        self.task = asyncio.create_task(self._run(produce))

    def _notify(self) -> None:
        self._changed.set()
        self._changed = asyncio.Event()

    async def _run(self, produce: Callable[[Exchange], Awaitable[None]]) -> None:
        try:
            await produce(self)
        finally:
            self.joinable = False
            self._done = True
            self._notify()

    def reply(self, reply: Reply) -> None:
        self._reply = reply
        self._notify()

    def subscribe(self) -> object:
        subscriber = object()
        self._positions[subscriber] = 0
        return subscriber

    def leave(self, subscriber: object) -> None:
        del self._positions[subscriber]
        self._notify()

    async def push(self, frame: bytes) -> None:
        if len(frame) > max_sse_event_bytes:
            raise ValueError("generated SSE event exceeds its limit")
        while self._size + len(frame) > max_response_bytes or len(self._frames) >= _MAX_REPLAY_FRAMES:
            self.joinable = False
            minimum = min(self._positions.values(), default=self._offset + len(self._frames))
            if minimum == self._offset:
                await self._changed.wait()
                continue
            self._size -= len(self._frames.pop(self._offset))
            self._offset += 1
        self._frames[self._offset + len(self._frames)] = frame
        self._size += len(frame)
        self._notify()

    async def send(self, subscriber: object, send: Send) -> None:
        while self._reply is None and not self._done:
            await self._changed.wait()
        if self._reply is None:
            # Propagate an unexpected producer failure without starting an incomplete response.
            self.task.result()
            raise RuntimeError("router exchange completed without a response")
        reply = self._reply
        headers = [(key.encode("ascii"), value.encode("latin-1")) for key, value in reply.headers.items()]
        await send({"type": "http.response.start", "status": reply.status, "headers": headers})
        if reply.body is not None:
            await send({"type": "http.response.body", "body": reply.body})
            return
        index = self._positions[subscriber]
        while True:
            if index in self._frames:
                await send({"type": "http.response.body", "body": self._frames[index], "more_body": True})
                index += 1
                self._positions[subscriber] = index
                self._notify()
            elif self._done:
                await send({"type": "http.response.body", "body": b""})
                return
            else:
                await self._changed.wait()
