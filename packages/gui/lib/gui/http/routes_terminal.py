"""Terminal: ``/v1/terminal/sessions*`` and the WebSocket ``/v1/terminal/{id}/io`` (contract ``terminal/v1``).

The terminal is a privilege of the host (decision D29): it is off by default (``[gui.terminal] enabled``), every
session needs the HMAC confirmation of the request, the project must be registered (trusted) and the shell starts in
its root. The WebSocket is behind the security middleware (Host, required Origin, Bearer or cookie); a session id has
128 random bits and one client at a time may hold a session. The frames are JSON text: ``input``, ``resize`` and
``credit`` from the client, ``output``, ``exit`` and ``error`` from the server; the server reads the PTY only while
the client has credit. The content of the terminal is never logged or audited.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from typing import Any, Dict, Optional

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .. import contracts
from ..core import terminal as core
from ..core.terminal import Session
from ..errors import GuiError
from . import confirm
from .errors import endpoint, json_response, read_json

CONTRACT = "urn:swissknifeman:gui:terminal:v1"
MAX_FRAME = 96 * 1024  # a 64 KiB input frame in base64 and its JSON
TICK_S = 0.25
WRITE_QUEUE = 64  # input frames waiting for the PTY; more means the shell does not read
_SESSION_ID = re.compile(r"^term-[0-9a-f]{32}$")


def _state(request: Request):
    return request.app.state.backend


def _issues(problems) -> list:
    return [{"pointer": issue.path, "code": issue.code, "message": issue.message} for issue in problems[:50]]


def _ensure_available(state) -> None:
    if state.desktop:
        raise GuiError("PERMISSION_DENIED", "the terminal is not supported in desktop mode",
                       details={"reason": "terminal_unsupported"})
    if not state.settings.terminal.enabled:
        raise GuiError("PERMISSION_DENIED", "the terminal is off; the owner enables it with [gui.terminal] enabled",
                       details={"reason": "terminal_disabled"})
    if not core.supported():
        raise GuiError("PERMISSION_DENIED", core.PLATFORM_TEXT, details={"reason": "terminal_unsupported"})


@endpoint
async def create(request: Request) -> Response:
    state = _state(request)
    _ensure_available(state)
    body = await read_json(request)
    problems = contracts.validate(body, "terminal")
    if problems or body.get("kind") != "session_request":
        raise GuiError("INPUT_INVALID", "the body is not a terminal/v1 session_request",
                       issues=_issues(problems) or [{"pointer": "/kind", "code": "const", "message": "session_request"}])
    project_id, cols, rows = body["project_id"], body["cols"], body["rows"]
    with state.db_lock:
        project = state.registry.get(project_id)
        root = str(state.registry.resolve(project_id))
    if not project.trusted:
        raise GuiError("PERMISSION_DENIED", f"project {project_id} is not trusted",
                       details={"reason": "project_untrusted"})
    manager = state.terminals
    if manager.count() >= state.settings.terminal.max_sessions:
        raise GuiError("TERMINAL_LIMIT", f"at most {state.settings.terminal.max_sessions} terminal sessions at the "
                                         "same time")
    confirm.require(state, "terminal.start", {"project_id": project_id, "cols": cols, "rows": rows}, body.get("confirm"),
                    risk="high",
                    summary=f"Open a shell ({manager.shell()}) in {root} with the rights of the user who runs the "
                            "backend; what you type and see is not stored")
    session = await asyncio.to_thread(manager.start, project_id, root, cols, rows)
    return json_response(session.document(), 201)


@endpoint
async def sessions(request: Request) -> Response:
    state = _state(request)
    return json_response({"$schema": CONTRACT, "kind": "session_list",
                          "sessions": [session.entry() for session in state.terminals.list()]})


@endpoint
async def close(request: Request) -> Response:
    state = _state(request)
    session_id = request.path_params["session_id"]
    document = await asyncio.to_thread(state.terminals.close, session_id, "closed")
    if document is None:
        raise GuiError("NOT_FOUND", f"no terminal session {session_id!r}")
    return json_response(document)


# --- WebSocket ---------------------------------------------------------------------------------------------------

def _frame(document: Dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def _error(code: str, message: str) -> Dict[str, Any]:
    return {"t": "error", "code": code, "message": message}


def _decode_input(frame: Dict[str, Any]) -> bytes:
    data = frame.get("data")
    if set(frame) != {"t", "data"} or not isinstance(data, str):
        raise ValueError("an input frame is {t, data}")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("data is not base64") from None
    if len(raw) > core.MAX_INPUT_BYTES:
        raise ValueError(f"an input frame carries at most {core.MAX_INPUT_BYTES} bytes")
    return raw


async def io(websocket: WebSocket) -> None:
    state = websocket.app.state.backend
    manager = state.terminals
    await websocket.accept()
    lock = asyncio.Lock()
    credit = asyncio.Event()
    closed_socket = False
    disconnected = False

    async def send(document: Dict[str, Any]) -> None:
        async with lock:
            await websocket.send_text(_frame(document))

    async def refuse(code: str, message: str, close_code: int = 1008) -> None:
        nonlocal closed_socket
        closed_socket = True
        try:
            await send(_error(code, message))
            await websocket.close(code=close_code)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass

    session_id = websocket.path_params["session_id"]
    session: Optional[Session] = manager.get(session_id) if _SESSION_ID.match(session_id) else None
    if session is None:
        await refuse("NOT_FOUND", "no such terminal session")
        return
    if not session.attach():
        await refuse("TERMINAL_BUSY", "another client holds this terminal session")
        return

    async def pump() -> None:
        """Output while the client has credit; the ``exit`` frame when the session ends."""
        try:
            while not session.closed:
                chunk = session.take_output()
                if chunk is not None:
                    seq, data = chunk
                    await send({"t": "output", "seq": seq, "data": base64.b64encode(data).decode("ascii")})
                    continue
                if session.finished():
                    break
                if session.gate.available <= 0:
                    credit.clear()
                    try:
                        await asyncio.wait_for(credit.wait(), TICK_S)
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.to_thread(session.wait_readable, TICK_S)
            await asyncio.to_thread(manager.close, session.id, "exit")  # no-op when a timer or the client ended it first
            await send({"t": "exit", **session.exit_info()})
            await websocket.close(code=1000)
        except (WebSocketDisconnect, RuntimeError, OSError):
            return

    writes: "asyncio.Queue[bytes]" = asyncio.Queue(maxsize=WRITE_QUEUE)

    async def writer() -> None:
        """Input goes to the PTY from here, so a blocked write never stops the receiver from reading ``credit``."""
        while True:
            data = await writes.get()
            try:
                await asyncio.to_thread(session.write, data)
            except (OSError, TimeoutError):
                if not session.closed:
                    await refuse("INTERNAL", "the shell does not accept input")
                return

    task = asyncio.create_task(pump())
    write_task = asyncio.create_task(writer())
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                disconnected = True
                break
            raw = message.get("text")
            if raw is None or len(raw) > MAX_FRAME:
                await refuse("INPUT_INVALID", "a frame must be JSON text of at most 96 KiB", 1009)
                break
            try:
                frame = json.loads(raw)
            except ValueError:
                await refuse("INPUT_INVALID", "a frame must be JSON")
                break
            kind = frame.get("t") if isinstance(frame, dict) else None
            try:
                if kind == "input":
                    data = _decode_input(frame)
                    try:
                        writes.put_nowait(data)
                    except asyncio.QueueFull:
                        await refuse("INTERNAL", "the shell does not accept input")
                        break
                elif kind == "resize":
                    if set(frame) != {"t", "cols", "rows"}:
                        raise ValueError("a resize frame is {t, cols, rows}")
                    try:
                        core.check_size(frame["cols"], frame["rows"])
                    except GuiError as error:
                        raise ValueError(error.message) from None
                    session.resize(frame["cols"], frame["rows"])
                elif kind == "credit":
                    if set(frame) != {"t", "bytes"}:
                        raise ValueError("a credit frame is {t, bytes}")
                    session.gate.grant(frame["bytes"])
                    credit.set()
                else:
                    raise ValueError("a frame is input, resize or credit")
            except ValueError as problem:
                await refuse("INPUT_INVALID", str(problem))
                break
    except WebSocketDisconnect:
        disconnected = True
    finally:
        task.cancel()
        write_task.cancel()
        await asyncio.gather(task, write_task, return_exceptions=True)
        session.detach()
        # The socket is gone (or refused): the session ends now; version 1 has no reconnect.
        await asyncio.shield(asyncio.to_thread(manager.close, session.id, "closed"))
        if not closed_socket and not disconnected:
            try:
                await websocket.close(code=1000)
            except (WebSocketDisconnect, RuntimeError, OSError):
                pass


ROUTES = [
    Route("/v1/terminal/sessions/{session_id}:close", close, methods=["POST"]),
    Route("/v1/terminal/sessions", create, methods=["POST"]),
    Route("/v1/terminal/sessions", sessions, methods=["GET"]),
    WebSocketRoute("/v1/terminal/{session_id}/io", io),
]
