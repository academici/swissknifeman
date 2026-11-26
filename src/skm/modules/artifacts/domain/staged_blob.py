"""Staged blob: physical staging record and its public ref, which carries no storage location."""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import NewType
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject

from .blob import ContentDigest

__all__ = ["StagedBlob", "StagedBlobId", "StagedBlobRef", "consume", "is_expired", "staged_blob_ref"]

# The wire DTO is generated from artifacts:defs/staged_blob_ref; the domain keeps the JSON shape.
type StagedBlobRef = JsonObject


StagedBlobId = NewType("StagedBlobId", UUID)


@dataclass(frozen=True, slots=True)
class StagedBlob:
    id: StagedBlobId
    workspace_id: WorkspaceId
    digest: ContentDigest
    size_bytes: int
    media_type: str
    detected_media_type: str
    backend_id: str
    storage_key: str
    created_by: PrincipalId
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None
    consumed_request_id: str | None


def is_expired(staged: StagedBlob, now: datetime) -> bool:
    return staged.consumed_at is None and staged.expires_at <= now


def staged_blob_ref(staged: StagedBlob) -> StagedBlobRef:
    """The public handle: identity, digest, size and media type; never backend or storage key."""
    return {
        "staged_blob_id": str(staged.id),
        "workspace_id": str(staged.workspace_id),
        "digest": staged.digest.value,
        "size": staged.size_bytes,
        "media_type": staged.media_type,
    }


def consume(
    staged: StagedBlob, ref: StagedBlobRef, workspace_id: WorkspaceId, request_id: str, now: datetime
) -> StagedBlob:
    if not (staged.workspace_id == workspace_id and ref.get("workspace_id") == str(workspace_id)):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "staged blob belongs to another workspace",
            details={"reason": "other_workspace"},
        )
    if ref.get("digest") != staged.digest.value or ref.get("size") != staged.size_bytes:
        raise ValidationFailed(
            ErrorCode.BLOB_DIGEST_MISMATCH, "staged blob ref does not match the staged bytes"
        )
    if staged.consumed_at is not None:
        raise Conflict(ErrorCode.STAGED_BLOB_CONSUMED, "staged blob is already consumed")
    if is_expired(staged, now):
        raise PreconditionFailed(ErrorCode.STAGED_BLOB_EXPIRED, "staged blob has expired")
    return replace(staged, consumed_at=now, consumed_request_id=request_id)
