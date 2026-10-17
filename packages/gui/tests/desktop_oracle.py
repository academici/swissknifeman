"""Python oracle of the desktop shell core (``desktop/src-tauri/core``).

Test code only; it is not part of the product. It implements the same rules as the Rust crate on pure Python, so the
vectors in ``desktop/tests/vectors/*.json`` (the single source of expected values, read by this oracle and by
``core/tests/vectors.rs``) can be checked on a machine without a Rust toolchain.
"""
import json
from collections import deque
from typing import Optional

METHODS = ("GET", "POST", "PATCH")
MAX_PATH = 2048
MAX_BODY = 1_048_576
_HEX = frozenset(b"0123456789abcdefABCDEF")

READY_PREFIX = "GUI_READY "

STABLE_MS = 60_000
WINDOW_MS = 300_000
MAX_RESTARTS = 5
DELAY_CAP_MS = 30_000

MAX_FRAMES = 50
MAX_AGE_MS = 50
QUEUE_LIMIT = 1000


def validate_request(method: str, path: str, body_len: int) -> Optional[str]:
    """None when the request may reach the sidecar, else the adapter error code."""
    if method not in METHODS:
        return "ADAPTER_METHOD"
    if not path.startswith("/v1/"):
        return "ADAPTER_PATH"
    raw = path.encode("utf-8")
    if len(raw) > MAX_PATH:
        return "ADAPTER_PATH"
    for c in raw:
        if c <= 0x20 or c == 0x7F or c >= 0x80 or c == 0x5C or c == 0x23:
            return "ADAPTER_PATH"
    decoded = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == 0x25:  # %
            pair = raw[i + 1:i + 3]
            if len(pair) < 2:
                return "ADAPTER_PATH"
            if any(h not in _HEX for h in pair):
                return "ADAPTER_PATH"
            d = int(pair.decode("ascii"), 16)
            if d < 0x20 or d == 0x7F or d == 0x5C:
                return "ADAPTER_PATH"
            decoded.append(d)
            i += 3
        else:
            decoded.append(c)
            i += 1
    if b".." in decoded:
        return "ADAPTER_PATH"
    if body_len > MAX_BODY:
        return "ADAPTER_BODY_TOO_LARGE"
    return None


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_ready(line: str) -> Optional[dict]:
    """The READY fields of a ``GUI_READY <json>`` line, or None for READY_INVALID."""
    line = line.rstrip("\r\n")
    if not line.startswith(READY_PREFIX):
        return None
    try:
        data = json.loads(line[len(READY_PREFIX):])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if not _is_int(data.get("v")) or data["v"] != 1:
        return None
    port, pid = data.get("port"), data.get("pid")
    if not _is_int(port) or not 1 <= port <= 65535:
        return None
    if not _is_int(pid) or pid <= 0:
        return None
    epoch, backend = data.get("epoch"), data.get("backend")
    if not isinstance(epoch, str) or not epoch or not isinstance(backend, str) or not backend:
        return None
    proto = data.get("gui_protocol")
    if not isinstance(proto, dict):
        return None
    low, high = proto.get("min"), proto.get("max")
    if not isinstance(low, str) or not isinstance(high, str):
        return None
    return {"port": port, "epoch": epoch, "pid": pid, "backend": backend, "gui_protocol": {"min": low, "max": high}}


def backoff_delay(attempt: int) -> int:
    return DELAY_CAP_MS if attempt >= 6 else 500 << attempt


class Policy:
    """Restart policy of the supervisor: backoff, reset after a stable run, ``failed`` after a crash loop."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.attempt = 0
        self.exits = []
        self.failed = False

    def on_exit(self, started_ms: int, exited_ms: int):
        """The restart delay in ms, or ``"failed"``."""
        if self.failed:
            return "failed"
        if max(0, exited_ms - started_ms) >= STABLE_MS:
            self.attempt = 0
        self.exits = [t for t in self.exits if max(0, exited_ms - t) <= WINDOW_MS]
        self.exits.append(exited_ms)
        if len(self.exits) > MAX_RESTARTS:
            self.failed = True
            return "failed"
        delay = backoff_delay(self.attempt)
        self.attempt += 1
        return delay


class Batcher:
    """Batches subscription frames: up to 50 frames or 50 ms, queue of 1000 frames, oldest dropped on overflow."""

    def __init__(self, max_frames: int = MAX_FRAMES, max_age_ms: int = MAX_AGE_MS, queue_limit: int = QUEUE_LIMIT):
        self.max_frames = max_frames
        self.max_age_ms = max_age_ms
        self.queue_limit = queue_limit
        self.queue = deque()
        self.dropped = 0

    def push(self, frame: str, now_ms: int) -> None:
        if len(self.queue) >= self.queue_limit:
            self.queue.popleft()
            self.dropped += 1
        self.queue.append((now_ms, frame))

    def poll(self, now_ms: int):
        """``(frames, dropped)`` when a batch is due, else None."""
        if not self.queue:
            return None
        if len(self.queue) < self.max_frames and max(0, now_ms - self.queue[0][0]) < self.max_age_ms:
            return None
        frames = [self.queue.popleft()[1] for _ in range(min(self.max_frames, len(self.queue)))]
        dropped, self.dropped = self.dropped, 0
        return frames, dropped
