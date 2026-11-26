"""Observed checkout files, applied records, and pure managed-part extraction (integrations §4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from skm.kernel.ids import FileVersionId

from .managed_block import extract_blocks
from .merged_json import dumps_merged_json_bytes, extract_owned_json
from .merged_toml import extract_owned_toml, merge_owned_toml
from .ownership import ManagedBoundary, Ownership, sha256_tagged
from .target import Surface

if TYPE_CHECKING:
    from .projection import ProjectionId

__all__ = [
    "AppliedFileRecord",
    "FileKind",
    "ObservedFile",
    "extract_managed_bytes",
    "extract_managed_digest",
    "observe_bytes",
]


class FileKind(StrEnum):
    MISSING = "missing"
    REGULAR = "regular"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    FIFO = "fifo"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ObservedFile:
    relative_path: str
    exists: bool
    is_symlink: bool
    whole_digest: str | None
    managed_digest: str | None
    boundary_valid: bool
    has_conflict_file: bool
    file_kind: FileKind | None = None
    outside_root: bool = False

    @property
    def effective_kind(self) -> FileKind:
        if self.file_kind is not None:
            return self.file_kind
        if self.is_symlink:
            return FileKind.SYMLINK
        if not self.exists:
            return FileKind.MISSING
        return FileKind.REGULAR


@dataclass(frozen=True, slots=True)
class AppliedFileRecord:
    projection_id: ProjectionId
    relative_path: str
    surface: Surface
    boundary: ManagedBoundary
    applied_managed_digest: str
    applied_whole_digest: str
    pre_image_file_version_id: FileVersionId | None
    renderer: str
    applied_at: datetime


def extract_managed_bytes(raw: bytes, boundary: ManagedBoundary) -> bytes | None:
    """Extract canonical managed bytes for ``boundary``, or ``None`` if boundary syntax is invalid."""
    if boundary.ownership is Ownership.MANAGED_FILE:
        return raw
    if boundary.ownership is Ownership.MANAGED_BLOCK:
        return extract_blocks(raw, boundary.block_ids)
    if boundary.ownership is Ownership.MERGED_JSON:
        try:
            owned_obj = extract_owned_json(raw, boundary.owned_keys)
        except ValueError:
            return None
        return dumps_merged_json_bytes(owned_obj)
    if boundary.ownership is Ownership.MERGED_TOML:
        try:
            text = raw.decode("utf-8")
            owned_toml = extract_owned_toml(text, boundary.owned_keys)
            rendered = merge_owned_toml("", owned_toml, boundary.owned_keys)
        except (UnicodeDecodeError, ValueError):
            return None
        return rendered.encode("utf-8")
    return None


def extract_managed_digest(raw: bytes, boundary: ManagedBoundary) -> tuple[str | None, bool]:
    """Return ``(managed_digest, boundary_valid)`` for ``raw`` under ``boundary``."""
    extracted = extract_managed_bytes(raw, boundary)
    if extracted is None:
        return None, False
    return sha256_tagged(extracted), True


def observe_bytes(
    relative_path: str,
    raw: bytes | None,
    boundary: ManagedBoundary,
    *,
    is_symlink: bool = False,
    has_conflict_file: bool = False,
    file_kind: FileKind | None = None,
    outside_root: bool = False,
) -> ObservedFile:
    """Build an ``ObservedFile`` purely from in-memory bytes and stat metadata."""
    resolved_kind = file_kind
    if resolved_kind is None:
        if is_symlink:
            resolved_kind = FileKind.SYMLINK
        elif raw is None:
            resolved_kind = FileKind.MISSING
        else:
            resolved_kind = FileKind.REGULAR

    if is_symlink or resolved_kind is FileKind.SYMLINK:
        return ObservedFile(
            relative_path=relative_path,
            exists=raw is not None,
            is_symlink=True,
            whole_digest=None,
            managed_digest=None,
            boundary_valid=False,
            has_conflict_file=has_conflict_file,
            file_kind=FileKind.SYMLINK,
            outside_root=outside_root,
        )

    if resolved_kind not in (FileKind.MISSING, FileKind.REGULAR):
        return ObservedFile(
            relative_path=relative_path,
            exists=True,
            is_symlink=False,
            whole_digest=None,
            managed_digest=None,
            boundary_valid=False,
            has_conflict_file=has_conflict_file,
            file_kind=resolved_kind,
            outside_root=outside_root,
        )

    if raw is None or resolved_kind is FileKind.MISSING:
        return ObservedFile(
            relative_path=relative_path,
            exists=False,
            is_symlink=False,
            whole_digest=None,
            managed_digest=None,
            boundary_valid=True,
            has_conflict_file=has_conflict_file,
            file_kind=FileKind.MISSING,
            outside_root=outside_root,
        )

    whole_digest = sha256_tagged(raw)
    managed_digest, boundary_valid = extract_managed_digest(raw, boundary)
    return ObservedFile(
        relative_path=relative_path,
        exists=True,
        is_symlink=False,
        whole_digest=whole_digest,
        managed_digest=managed_digest,
        boundary_valid=boundary_valid,
        has_conflict_file=has_conflict_file,
        file_kind=FileKind.REGULAR,
        outside_root=outside_root,
    )
