"""Pack payload value types and path/size limit validation (extensions §7.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = [
    "DEFAULT_MAX_ARCHIVE_BYTES",
    "DEFAULT_MAX_ARCHIVE_FILES",
    "PackPayload",
    "PayloadFile",
    "check_payload_limits",
    "validate_payload_path",
]

DEFAULT_MAX_ARCHIVE_FILES: Final = 5000
DEFAULT_MAX_ARCHIVE_BYTES: Final = 52_428_800


@dataclass(frozen=True, slots=True)
class PayloadFile:
    path: str
    content: bytes


@dataclass(frozen=True, slots=True)
class PackPayload:
    manifest_text: str
    files: tuple[PayloadFile, ...]


def validate_payload_path(path: str) -> str:
    """Validate that ``path`` is a clean relative POSIX path without ``..``, ``.``, ``\\``, or ``/``."""
    parts = path.split("/")
    if not path or path.startswith("/") or "\\" in path or {"", ".", ".."} & set(parts):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid path in the pack",
            details={"reason": "path_invalid", "path": path},
        )
    return path


def check_payload_limits(
    file_count: int,
    total_bytes: int,
    *,
    max_files: int = DEFAULT_MAX_ARCHIVE_FILES,
    max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> None:
    """Enforce maximum file count and cumulative uncompressed payload size."""
    if file_count > max_files:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "too many files in the pack",
            details={"reason": "too_many_files"},
        )
    if total_bytes > max_bytes:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "the pack is too large",
            details={"reason": "archive_too_large"},
        )
