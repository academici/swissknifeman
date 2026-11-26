"""ASGI streaming driver for SSE tests with bounded waits."""

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.types import Message, Scope

from contracts.execution.harness import ExecSide
from contracts.execution.seed_helpers import record_run_event
from skm.kernel.ids import RunId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.public import CreateTokenResult

_EVENTS = "/api/v1/events"


@dataclass
class _Stream:
    status: int
    headers: Headers
    messages: asyncio.Queue[Message]
    frames: deque[str]
    task: asyncio.Task[None]

    async def take(self) -> str | None:
        while not self.frames:
            message = await asyncio.wait_for(self.messages.get(), 4)
            assert message["type"] == "http.response.body"
            body = message["body"].decode()
            if not message.get("more_body", False):
                return body or None
            assert body.endswith("\n\n")
            self.frames.extend(body.removesuffix("\n\n").split("\n\n"))
        return self.frames.popleft()


@asynccontextmanager
async def _open(
    app: Starlette,
    token: CreateTokenResult,
    workspace: WorkspaceId,
    *,
    last: int | None = None,
    params: tuple[tuple[str, str], ...] = (),
    pause: asyncio.Event | None = None,
) -> AsyncIterator[_Stream]:
    incoming = asyncio.Queue[Message]()
    await incoming.put({"type": "http.request", "body": b""})
    messages = asyncio.Queue[Message]()
    headers = {"host": "127.0.0.1:8765", **{"Authorization": f"Bearer {token.secret}"}}
    if last is not None:
        headers["last-event-id"] = str(last)
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": _EVENTS,
        "query_string": urlencode((("workspace_id", str(workspace)), *params)).encode(),
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "root_path": "",
    }

    async def send(message: Message) -> None:
        await messages.put(message)
        if pause is not None and message.get("more_body"):
            await pause.wait()

    task = asyncio.create_task(app(scope, incoming.get, send))
    try:
        start = await asyncio.wait_for(messages.get(), 4)
        assert start["type"] == "http.response.start"
        yield _Stream(start["status"], Headers(raw=start["headers"]), messages, deque(), task)
    finally:
        await incoming.put({"type": "http.disconnect"})
        await asyncio.wait_for(task, 4)


def _cursor(seq: int) -> str:
    return f"id: {seq}\nevent: cursor\ndata: {{}}"


async def _expect_event(
    stream: _Stream,
    seq: int,
    name: str,
    stream_id: UUID,
    kind: str = "run",
    *,
    stream_seq: int | None = None,
) -> None:
    frame = await stream.take()
    assert frame is not None
    identifier, event, data = frame.splitlines()
    assert identifier == f"id: {seq}"
    assert event == f"event: {name}"
    envelope = json.loads(data.removeprefix("data: "))
    assert envelope["workspace_seq"] == seq
    if stream_seq is not None:
        assert envelope["stream_seq"] == stream_seq
    assert (envelope["stream_kind"], envelope["stream_id"]) == (kind, str(stream_id))


def _record(side: ExecSide, uow: UnitOfWork, run: RunId, *, paused: bool = False) -> None:
    payload: JsonObject = {
        "workspace_id": str(side.ws),
        "project_id": str(side.proj),
        "run_id": str(run),
        "by": str(side.owner.principal_id),
    }
    if paused:
        payload.update(reason="paused", pause_source="owner")
    record_run_event(side, uow, run, "run-paused" if paused else "run-resumed", payload)


def _append(side: ExecSide, run: RunId, *, paused: bool = False) -> None:
    with side.uow() as uow:
        _record(side, uow, run, paused=paused)
        uow.commit()
