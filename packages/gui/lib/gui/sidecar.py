"""The sidecar protocol of ``gui serve --sidecar`` (decision D28), stdlib only.

The desktop shell writes ONE line of JSON to the stdin of the backend and keeps stdin open::

    {"v":1,"secret":"<base64url, >= 32 characters>","port":0,"shell_version":"0.1.0"}

The secret therefore never touches argv, the environment, the disk or a log. After the socket listens the backend
prints exactly one line ``GUI_READY {json}`` to stdout and nothing more; EOF on stdin means the parent is gone.
Messages of :class:`HandshakeError` name the reason, never a value.
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Callable, Dict, Mapping, Optional

PROTOCOL = 1
MAX_LINE = 4096
HANDSHAKE_TIMEOUT_S = 10.0
MIN_SECRET = 32
INVALID = "SIDECAR_HANDSHAKE_INVALID"
READY = "GUI_READY"

_SECRET = re.compile(r"[A-Za-z0-9_-]+")
_SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
                     r"(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?")


class HandshakeError(Exception):
    """The handshake line is not valid; ``reason`` never contains a value of the line."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"{INVALID}: {reason}")
        self.reason = reason


@dataclass(frozen=True)
class Handshake:
    secret: str = field(repr=False)
    port: int
    shell_version: str
    v: int = PROTOCOL


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_handshake(line: bytes) -> Handshake:
    """Parse the handshake line (with or without its ``\\n``); :class:`HandshakeError` for every refusal."""
    if len(line) > MAX_LINE + 1 or (len(line) == MAX_LINE + 1 and not line.endswith(b"\n")):
        raise HandshakeError(f"the line is longer than {MAX_LINE} bytes")
    if not line.strip():
        raise HandshakeError("the line is empty")
    try:
        document = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise HandshakeError("the line is not UTF-8 JSON") from None
    if not isinstance(document, dict):
        raise HandshakeError("the line is not a JSON object")
    for name in ("v", "secret", "port", "shell_version"):
        if name not in document:
            raise HandshakeError(f"the field {name} is missing")
    if not _is_int(document["v"]) or document["v"] != PROTOCOL:
        raise HandshakeError(f"v must be {PROTOCOL}")
    secret = document["secret"]
    if not isinstance(secret, str) or not _SECRET.fullmatch(secret):
        raise HandshakeError("secret must be base64url without padding")
    if len(secret) < MIN_SECRET:
        raise HandshakeError(f"secret is shorter than {MIN_SECRET} characters")
    port = document["port"]
    if not _is_int(port) or not 0 <= port <= 65535:
        raise HandshakeError("port must be an integer from 0 to 65535")
    version = document["shell_version"]
    if not isinstance(version, str) or not _SEMVER.fullmatch(version):
        raise HandshakeError("shell_version must be a semantic version")
    return Handshake(secret=secret, port=port, shell_version=version)


def read_handshake(stream: BinaryIO, timeout: float = HANDSHAKE_TIMEOUT_S) -> Handshake:
    """Read ONE line from ``stream`` (a thread and a queue, so the wait has a deadline) and parse it."""
    answers: "queue.Queue[Any]" = queue.Queue(maxsize=1)

    def read() -> None:
        try:
            answers.put(stream.readline(MAX_LINE + 2))
        except (OSError, ValueError) as error:
            answers.put(error)

    threading.Thread(target=read, name="sidecar-handshake", daemon=True).start()
    try:
        line = answers.get(timeout=timeout)
    except queue.Empty:
        raise HandshakeError(f"no handshake line in {timeout:g} s") from None
    if isinstance(line, Exception):
        raise HandshakeError("stdin cannot be read")
    if not line:
        raise HandshakeError("stdin was closed before the handshake line")
    return parse_handshake(line)


def ready_line(port: int, epoch: str, pid: int, backend: str, protocol: Mapping[str, str]) -> str:
    """``GUI_READY {json}``: compact JSON on one line, without the newline."""
    document: Dict[str, Any] = {"v": PROTOCOL, "port": port, "epoch": epoch, "pid": pid, "backend": backend,
                                "gui_protocol": {"min": protocol["min"], "max": protocol["max"]}}
    return f"{READY} {json.dumps(document, separators=(',', ':'))}"


def watch_stdin(stream: BinaryIO, on_eof: Callable[[], None]) -> threading.Thread:
    """Drain ``stream`` in a daemon thread; at EOF (the parent died or closed it) call ``on_eof`` once."""

    def run() -> None:
        try:
            while stream.read(MAX_LINE):
                pass
        except (OSError, ValueError):
            pass
        on_eof()

    thread = threading.Thread(target=run, name="sidecar-watchdog", daemon=True)
    thread.start()
    return thread


def stdin_stream() -> BinaryIO:
    """The binary stdin of the process, unbuffered: no lock is held by a reader thread that outlives the handshake."""
    return os.fdopen(os.dup(0), "rb", buffering=0)
