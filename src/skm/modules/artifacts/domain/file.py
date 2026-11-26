"""File: owned identity of versions; classification only rises, current version is its own."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import NewType, Protocol
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, WorkspaceId

from .classification import Classification, ensure_not_lowered

__all__ = [
    "File",
    "FileId",
    "FileOrigin",
    "FileState",
    "new_file",
    "reclassify",
    "restore",
    "set_current",
    "trash",
]


class FileState(StrEnum):
    ACTIVE = "active"
    TRASHED = "trashed"


class FileOrigin(StrEnum):
    UPLOAD = "upload"
    EVIDENCE = "evidence"
    TRANSCRIPT = "transcript"
    PATCH = "patch"
    REPORT = "report"
    IMPORT = "import"
    CAPTURE = "capture"


FileId = NewType("FileId", UUID)


@dataclass(frozen=True, slots=True)
class File:
    id: FileId
    workspace_id: WorkspaceId
    project_id: ProjectId | None
    title: str
    origin: FileOrigin
    classification: Classification
    current_version_id: FileVersionId | None
    state: FileState
    row_version: int
    created_at: datetime
    created_by: PrincipalId


def new_file(
    *,
    file_id: FileId,
    workspace_id: WorkspaceId,
    project_id: ProjectId | None,
    title: str,
    origin: FileOrigin,
    classification: Classification,
    created_by: PrincipalId,
    now: datetime,
) -> File:
    trimmed = title.strip()
    if not 1 <= len(trimmed) <= 300:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "title must be 1..300 characters",
            details={"field": "title", "reason": "length"},
        )
    return File(
        id=file_id,
        workspace_id=workspace_id,
        project_id=project_id,
        title=trimmed,
        origin=origin,
        classification=classification,
        current_version_id=None,
        state=FileState.ACTIVE,
        row_version=1,
        created_at=now,
        created_by=created_by,
    )


class _VersionOfFile(Protocol):
    @property
    def id(self) -> FileVersionId: ...
    @property
    def file_id(self) -> FileId: ...
    @property
    def workspace_id(self) -> WorkspaceId: ...


def set_current(file: File, version: _VersionOfFile) -> File:
    """Point the file at one of its own versions; a foreign version is a programming error."""
    if version.file_id != file.id or version.workspace_id != file.workspace_id:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "current version belongs to another file",
            details={"reason": "foreign_current_version"},
        )
    return replace(file, current_version_id=version.id, row_version=file.row_version + 1)


def trash(file: File) -> File:
    if file.state is FileState.TRASHED:
        return file
    return replace(file, state=FileState.TRASHED, row_version=file.row_version + 1)


def restore(file: File) -> File:
    if file.state is FileState.ACTIVE:
        return file
    return replace(file, state=FileState.ACTIVE, row_version=file.row_version + 1)


def reclassify(file: File, classification: Classification) -> File:
    """Raise the classification; lowering is refused, an equal value is a no-op."""
    ensure_not_lowered(file.classification, classification)
    if classification is file.classification:
        return file
    return replace(file, classification=classification, row_version=file.row_version + 1)
