"""Ids of workspace documents (devices, the workspace identity): ``<prefix>_`` and 26 Crockford base32 characters (48 bits of
milliseconds, 80 random). Workspaces and projects are named by a code (:func:`is_code`), not by an id."""
from __future__ import annotations

import re
import secrets
import time
from typing import Optional

from aicore.state.locations import is_code  # noqa: F401  (re-exported: codes of workspaces and projects)

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
TIME_CHARS = 10
RANDOM_CHARS = 16
_PREFIX = re.compile(r"[a-z][a-z0-9]*")
_BODY = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")


def _encode(number: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(ALPHABET[number & 31])
        number >>= 5
    return "".join(reversed(chars))


def new_id(prefix: str, now_ms: Optional[int] = None, rand: Optional[bytes] = None) -> str:
    """A new id. ``now_ms`` (milliseconds since the epoch) and ``rand`` (10 bytes) are for tests; the time part makes
    ids of one prefix sort by creation."""
    if not _PREFIX.fullmatch(prefix):
        raise ValueError(f"invalid id prefix {prefix!r}")
    millis = int(time.time() * 1000) if now_ms is None else now_ms
    if not 0 <= millis < 1 << 48:
        raise ValueError("now_ms must fit in 48 bits")
    noise = secrets.token_bytes(10) if rand is None else rand
    if len(noise) != 10:
        raise ValueError("rand must be 10 bytes")
    return f"{prefix}_{_encode(millis, TIME_CHARS)}{_encode(int.from_bytes(noise, 'big'), RANDOM_CHARS)}"


def is_id(value: object, prefix: str) -> bool:
    """Whether ``value`` is an id of ``prefix``."""
    return isinstance(value, str) and value.startswith(prefix + "_") and _BODY.fullmatch(value[len(prefix) + 1:]) is not None
