"""Workspace SSE decoding, cursor advancement and bounded reconnects."""

import json
import re
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future
from contextlib import AbstractContextManager, suppress
from itertools import takewhile
from queue import SimpleQueue
from socket import SHUT_RDWR, socket
from threading import Event, Lock, Thread

import httpx

from skm.kernel.clock import Monotonic
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, InternalError, ValidationFailed
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject

from .retry import TRANSPORT_FAILURES, transport_error

__all__ = ["read_events"]

_MAX_CURSOR = 2**63 - 1
_IDLE_SECONDS = 0.5


def _frames(lines: Iterable[str]) -> Iterator[tuple[int, str, str]]:
    cursor = None
    kind = ""
    data: list[str] = []
    for line in lines:
        if not line:
            if cursor is not None and data:
                yield cursor, kind, "\n".join(data)
            cursor, kind = None, ""
            data.clear()
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "id" and re.fullmatch(r"[0-9]{1,19}", value) and int(value) <= _MAX_CURSOR:
            cursor = int(value)
        elif field == "event":
            kind = value
        elif field == "data":
            data.append(value)


def _envelope(data: str, workspace: WorkspaceId, cursor: int) -> EventEnvelope:
    try:
        body: JsonObject = json.loads(data)
        event = EventEnvelope.from_json(body)
        if event.workspace_id == workspace and event.workspace_seq == cursor:
            return event
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    raise InternalError(ErrorCode.INTERNAL_ERROR, "Invalid workspace event")


type _Frame = tuple[int, str, str]
type _OpenStream = Callable[[int | None, float], AbstractContextManager[httpx.Response]]


def _timed_frames(
    connection: AbstractContextManager[httpx.Response], clock: Monotonic, deadline: float, *, snapshot: bool
) -> Iterator[_Frame]:
    # A socket read timeout restarts on every chunk. Wait for a complete frame against
    # the caller's deadline, including the time spent waiting for response headers.
    requests = SimpleQueue[Future[_Frame | None] | None]()
    stopped = Event()
    lock = Lock()
    active: httpx.Response | None = None

    def read() -> None:
        nonlocal active
        reply = requests.get()
        if reply is None:
            return
        try:
            with connection as response:
                with lock:
                    if stopped.is_set():
                        return
                    active = response
                try:
                    lines = takewhile(
                        lambda _: not stopped.is_set() and (snapshot or clock.monotonic() < deadline),
                        response.iter_lines(),
                    )
                    frames = _frames(lines)
                    while reply is not None:
                        frame = next(frames, None)
                        reply.set_result(frame)
                        if frame is None:
                            return
                        reply = requests.get()
                finally:
                    with lock:
                        active = None
        except BaseException as error:  # noqa: BLE001 -- propagate reader failure to the iterator
            if reply is not None and not reply.done():
                reply.set_exception(error)

    Thread(target=read, name="skm-http-events", daemon=True).start()
    drain = False
    try:
        while True:
            remaining = _IDLE_SECONDS if drain else deadline - clock.monotonic()
            if remaining <= 0:
                return
            reply = Future[_Frame | None]()
            requests.put(reply)
            try:
                frame = reply.result(timeout=remaining)
            except TimeoutError:
                return
            if frame is None or (not snapshot and clock.monotonic() >= deadline):
                return
            drain = snapshot
            yield frame
    finally:
        stopped.set()
        requests.put(None)
        with lock:
            if active is not None and not active.is_closed:
                # SSE requests have a dedicated HTTP/1 connection. Wake recv before closing.
                stream = active.extensions.get("network_stream")
                sock = stream.get_extra_info("socket") if stream is not None else None
                if isinstance(sock, socket) and active.http_version == "HTTP/1.1":
                    with suppress(OSError):
                        sock.shutdown(SHUT_RDWR)
                active.close()


def read_events(
    open_stream: _OpenStream,
    *,
    workspace_id: WorkspaceId,
    after: int,
    wait_seconds: float,
    timeout_seconds: float,
    clock: Monotonic,
    sleeper: Callable[[float], None],
    finite_snapshot: bool = False,
) -> Iterator[EventEnvelope]:
    if not 0 <= after <= _MAX_CURSOR:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid event cursor")
    deadline = clock.monotonic() + (wait_seconds if wait_seconds > 0 else timeout_seconds)
    last = after
    resume: int | None = None
    delay = 1.0
    while (remaining := deadline - clock.monotonic()) > 0:
        timeout = min(remaining, timeout_seconds)
        failure = None
        try:
            for cursor, kind, data in _timed_frames(
                open_stream(resume, timeout),
                clock,
                deadline,
                snapshot=wait_seconds <= 0 and not finite_snapshot,
            ):
                if cursor > last:
                    last = cursor
                    delay = 1.0
                    if kind != "cursor":
                        yield _envelope(data, workspace_id, cursor)
            if wait_seconds <= 0:
                if finite_snapshot and clock.monotonic() >= deadline:
                    raise transport_error()
                return
        except httpx.ReadTimeout:
            if not finite_snapshot and (wait_seconds <= 0 or clock.monotonic() >= deadline):
                return
            failure = transport_error()
        except TRANSPORT_FAILURES:
            failure = transport_error()
        except BackendUnavailable as error:
            if not error.retryable:
                raise
            failure = error
        resume = last
        remaining = deadline - clock.monotonic()
        if failure is not None and remaining <= delay and (finite_snapshot or remaining > 0):
            raise failure
        if remaining <= 0:
            return
        sleeper(min(delay, remaining))
        delay = min(30.0, delay * 2)
