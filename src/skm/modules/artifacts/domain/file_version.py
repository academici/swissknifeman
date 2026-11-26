"""FileVersion: an immutable, sequential version of one active file."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import FileVersionId, PrincipalId, WorkspaceId

from .blob import Blob, BlobId
from .content_safety import SafetyReport
from .file import File, FileId, FileState
from .upload_rules import validate_filename

__all__ = ["FileVersion", "VersionSource", "new_version"]


@dataclass(frozen=True, slots=True)
class VersionSource:
    kind: Literal["upload", "evidence", "import", "capture", "generated"]
    ref: str | None
    captured_at: datetime | None


@dataclass(frozen=True, slots=True)
class FileVersion:
    id: FileVersionId
    workspace_id: WorkspaceId
    file_id: FileId
    version_no: int
    blob_id: BlobId
    original_filename: str
    declared_media_type: str | None
    description: str
    source: VersionSource
    safety: SafetyReport
    created_by: PrincipalId
    created_at: datetime


def _invalid(field: str, reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID, f"{field} is invalid", details={"field": field, "reason": reason}
    )


def new_version(  # noqa: PLR0913 - keyword-only signature fixed by artifacts §5
    *,
    version_id: FileVersionId,
    file: File,
    previous_no: int,
    blob: Blob,
    original_filename: str,
    declared_media_type: str | None,
    description: str,
    source: VersionSource,
    safety: SafetyReport,
    created_by: PrincipalId,
    now: datetime,
) -> FileVersion:
    if file.state is not FileState.ACTIVE:
        raise PreconditionFailed(
            ErrorCode.FILE_TRASHED,
            "cannot add a version to a trashed file",
            details={"file_id": str(file.id)},
        )
    if blob.workspace_id != file.workspace_id:
        # Blobs deduplicate inside one workspace only.
        raise _invalid("blob_id", "other_workspace")
    original_filename = validate_filename(original_filename)  # §4.5: the stored name is the NFC form
    if len(description) > 2000:
        raise _invalid("description", "too_long")
    if source.ref is not None and len(source.ref) > 500:
        raise _invalid("source.ref", "too_long")
    return FileVersion(
        id=version_id,
        workspace_id=file.workspace_id,
        file_id=file.id,
        version_no=previous_no + 1,
        blob_id=blob.id,
        original_filename=original_filename,
        declared_media_type=declared_media_type,
        description=description,
        source=source,
        safety=safety,
        created_by=created_by,
        created_at=now,
    )
