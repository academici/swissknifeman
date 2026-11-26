"""Runtime identifiers (runtimes §3, §9).

``RuntimeId`` is an open registry key (built-in adapters and plugin runtime components), not a closed
enum: the legacy closed ``ProviderId`` made a new provider a code change.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import NAMESPACE_URL, UUID, uuid5

__all__ = [
    "Digest",
    "ModelId",
    "RuntimeId",
    "SessionRef",
    "format_utc",
    "is_digest",
    "is_runtime_id",
    "parse_runtime_id",
    "parse_utc",
    "require_utc",
    "runtime_stream_id",
]

type RuntimeId = str
type ModelId = str
type SessionRef = str
type Digest = str

# fullmatch: "$" would accept a trailing newline.
_RUNTIME_ID: Final = re.compile(r"[a-z][a-z0-9_]{1,31}")
_DIGEST: Final = re.compile(r"sha256:[0-9a-f]{64}")


def is_runtime_id(value: object) -> bool:
    return isinstance(value, str) and _RUNTIME_ID.fullmatch(value) is not None


def is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def parse_runtime_id(value: object) -> RuntimeId:
    if not is_runtime_id(value):
        raise ValueError(f"not a runtime id: {value!r}")
    return str(value)


def require_utc(value: object, name: str) -> None:
    """Observer times are tz-aware UTC (adapter wall clock), never naive."""
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a tz-aware UTC datetime")


def format_utc(value: datetime) -> str:
    """RFC 3339 with ``Z`` (``urn:skm:kernel:defs:v1#/$defs/timestamp``)."""
    require_utc(value, "timestamp")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_utc(text: object, name: str) -> datetime:
    if not isinstance(text, str) or not text.endswith("Z"):
        raise ValueError(f"{name} must be an RFC 3339 UTC timestamp ending in Z")
    value = datetime.fromisoformat(text)
    require_utc(value, name)
    return value


def runtime_stream_id(runtime_id: RuntimeId) -> UUID:
    """Stream id of ``CapabilityVerified`` (stream_kind ``runtime``): uuid5 of ``skm:runtime:<id>``."""
    return uuid5(NAMESPACE_URL, f"skm:runtime:{parse_runtime_id(runtime_id)}")
