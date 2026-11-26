"""Exact-byte SKM webhook signatures, including key rotation and replay tolerance."""

import hashlib
import hmac
from collections.abc import Sequence

__all__ = ["sign", "verify"]


def sign(body: bytes, *, secrets: Sequence[str], timestamp: int) -> str:
    message = str(timestamp).encode("ascii") + b"." + body
    signatures = [hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest() for key in secrets]
    return ",".join([f"t={timestamp}", *(f"v1={value}" for value in signatures)])


def verify(body: bytes, header: str, *, secret: str, now: int, tolerance_seconds: int = 300) -> bool:
    parts = [part.split("=", 1) for part in header.split(",")]
    if any(len(part) != 2 for part in parts):
        return False
    timestamps = [value for key, value in parts if key == "t"]
    signatures = [value for key, value in parts if key == "v1"]
    if len(timestamps) != 1 or not signatures:
        return False
    try:
        timestamp = int(timestamps[0])
        if str(timestamp) != timestamps[0] or abs(now - timestamp) > tolerance_seconds:
            return False
        expected = sign(body, secrets=[secret], timestamp=timestamp).split("v1=", 1)[1]
        # Evaluate every signature, including during rotation.
        return bool(sum(hmac.compare_digest(expected, value) for value in signatures))
    except (ValueError, TypeError, UnicodeError):
        return False
