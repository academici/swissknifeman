"""Shared identifier types (kernel-platform §2.2).

``uuid7()`` is pure: the caller supplies the time and the entropy (ADR 0007, RFC 9562 §5.7).
Module-specific ids (``TokenId``, ``DraftId``, ...) live in ``modules/<m>/domain`` of the owning module.
"""

import re
from typing import Final, NewType
from uuid import UUID

__all__ = [
    "UUID7_MAX_RAND_A",
    "UUID7_MAX_RAND_B",
    "UUID7_MAX_UNIX_MS",
    "AttemptId",
    "ContextManifestId",
    "EntityId",
    "EventId",
    "FileVersionId",
    "HostId",
    "PlanId",
    "PrincipalId",
    "ProjectId",
    "RepositoryId",
    "ResourceVersionId",
    "RevisionId",
    "RunId",
    "ScopeId",
    "TaskId",
    "ToolIntentId",
    "WorkerId",
    "WorkspaceId",
    "parse_uuid",
    "uuid7",
    "uuid7_timestamp_ms",
]

WorkspaceId = NewType("WorkspaceId", UUID)
ProjectId = NewType("ProjectId", UUID)
RepositoryId = NewType("RepositoryId", UUID)
HostId = NewType("HostId", UUID)
WorkerId = NewType("WorkerId", UUID)
PrincipalId = NewType("PrincipalId", UUID)
ScopeId = NewType("ScopeId", UUID)
PlanId = NewType("PlanId", UUID)
RevisionId = NewType("RevisionId", UUID)
EntityId = NewType("EntityId", UUID)  # stable id of a plan specification entity
RunId = NewType("RunId", UUID)
TaskId = NewType("TaskId", UUID)
AttemptId = NewType("AttemptId", UUID)
FileVersionId = NewType("FileVersionId", UUID)
ResourceVersionId = NewType("ResourceVersionId", UUID)
ContextManifestId = NewType("ContextManifestId", UUID)
ToolIntentId = NewType("ToolIntentId", UUID)
EventId = NewType("EventId", UUID)

UUID7_MAX_RAND_A: Final = (1 << 12) - 1
UUID7_MAX_RAND_B: Final = (1 << 62) - 1
UUID7_MAX_UNIX_MS: Final = (1 << 48) - 1

_UUID7_VERSION_BITS: Final = 0x7 << 76
_UUID_VARIANT_BITS: Final = 0b10 << 62
_CANONICAL_UUID: Final = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _check_range(name: str, value: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"{name} must be int, got {type(value).__name__}")
    if not 0 <= value <= maximum:
        raise ValueError(f"{name} must be in [0, {maximum}], got {value}")


def uuid7(unix_ms: int, rand_a: int, rand_b: int) -> UUID:
    """Build a UUIDv7 from an explicit millisecond timestamp and entropy (RFC 9562 §5.7).

    Bits 0-47 hold ``unix_ms`` big-endian, 48-51 the version, 52-63 ``rand_a``, 64-65 the RFC variant and
    66-127 ``rand_b``. Out-of-range arguments raise ``ValueError``.
    """
    _check_range("unix_ms", unix_ms, UUID7_MAX_UNIX_MS)
    _check_range("rand_a", rand_a, UUID7_MAX_RAND_A)
    _check_range("rand_b", rand_b, UUID7_MAX_RAND_B)
    return UUID(int=(unix_ms << 80) | _UUID7_VERSION_BITS | (rand_a << 64) | _UUID_VARIANT_BITS | rand_b)


def uuid7_timestamp_ms(value: UUID) -> int:
    """Return the 48-bit millisecond timestamp of a UUIDv7; other versions raise ``ValueError``."""
    if value.version != 7:
        raise ValueError(f"not a UUIDv7: {value}")
    return value.int >> 80


def parse_uuid(text: str) -> UUID:
    """Parse canonical 36-character UUIDs, rejecting braces, URNs and bare hex."""
    if not isinstance(text, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"UUID text must be str, got {type(text).__name__}")
    if _CANONICAL_UUID.fullmatch(text) is None:
        raise ValueError(f"not a canonical UUID: {text!r}")
    return UUID(text)
