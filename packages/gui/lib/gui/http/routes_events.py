"""WebSocket ``/v1/events``: subscriptions to the EventHub (``stream/v1``).

The security middleware has checked Host, Origin (required) and the session before ``accept``. A client frame is at
most 64 KiB (else close ``1009``) and must be a ``subscribe`` or ``unsubscribe`` of ``stream/v1`` (else an ``error``
frame ``INPUT_INVALID``); at most 16 subscriptions per connection (``CONCURRENCY_LIMIT``). Each subscription is
pumped by its own task; a slow client loses its queue to ``snapshot_required`` (``overflow``), never the backend.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Dict

from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .. import contracts
from ..core.events import CONTRACT, Subscription
from ..errors import GuiError

MAX_FRAME = 64 * 1024
MAX_SUBSCRIPTIONS = 16


def _error(code: str, message: str, sub=None, issues=None) -> dict:
    frame = {"$schema": CONTRACT, "kind": "error",
             "error": GuiError(code, message, issues=issues).envelope(uuid.uuid4().hex)["error"]}
    if sub is not None:
        frame["sub"] = sub
    return frame


async def events(websocket: WebSocket) -> None:
    hub = websocket.app.state.backend.hub
    await websocket.accept()
    lock = asyncio.Lock()
    subscriptions: Dict[str, Subscription] = {}
    pumps: Dict[str, asyncio.Task] = {}

    async def send(frame: dict) -> None:
        async with lock:
            await websocket.send_text(json.dumps(frame, ensure_ascii=False, separators=(",", ":")))

    async def pump(subscription: Subscription) -> None:
        try:
            while True:
                await send(await subscription.get())
        except (asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            return

    def drop(sub_id: str) -> None:
        subscription = subscriptions.pop(sub_id, None)
        task = pumps.pop(sub_id, None)
        if subscription is not None:
            hub.unsubscribe(subscription)
        if task is not None:
            task.cancel()

    listener = hub.listen()
    heartbeat = asyncio.create_task(pump(listener))
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            raw = message.get("text")
            if raw is None:
                data = message.get("bytes") or b""
                if len(data) > MAX_FRAME:
                    await websocket.close(code=1009)
                    break
                raw = data.decode("utf-8", errors="replace")
            if len(raw.encode("utf-8")) > MAX_FRAME:
                await websocket.close(code=1009)
                break
            try:
                frame = json.loads(raw)
            except ValueError:
                await send(_error("INPUT_INVALID", "a frame must be JSON"))
                continue
            problems = contracts.validate(frame, "stream")
            kind = frame.get("kind") if isinstance(frame, dict) else None
            if problems or kind not in ("subscribe", "unsubscribe"):
                issues = [{"pointer": issue.path, "code": issue.code, "message": issue.message} for issue in problems]
                await send(_error("INPUT_INVALID", "expected a stream/v1 subscribe or unsubscribe frame",
                                  issues=issues[:20] or None))
                continue
            sub_id = frame["id"]
            if kind == "unsubscribe":
                drop(sub_id)
                continue
            if sub_id not in subscriptions and len(subscriptions) >= MAX_SUBSCRIPTIONS:
                await send(_error("CONCURRENCY_LIMIT", f"at most {MAX_SUBSCRIPTIONS} subscriptions per connection",
                                  sub=sub_id))
                continue
            drop(sub_id)
            subscription = hub.subscribe(sub_id, frame["filter"], frame["cursor"], frame["epoch"])
            subscriptions[sub_id] = subscription
            pumps[sub_id] = asyncio.create_task(pump(subscription))
    except WebSocketDisconnect:
        pass
    finally:
        for sub_id in list(subscriptions):
            drop(sub_id)
        hub.unlisten(listener)
        heartbeat.cancel()


ROUTES = [WebSocketRoute("/v1/events", events)]
