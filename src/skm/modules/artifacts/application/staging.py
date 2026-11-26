"""Staged blob consume and the blob row of a new version (artifacts §4.2, §5, §7, §13).

``consume_staged`` is the one place a staged ref turns into a consumed row: the ref must name a row of the
same workspace that is neither consumed nor expired and carry its exact digest and size. It runs inside the
caller's unit of work, so a rollback leaves the row staged (the janitor removes it after its TTL).
``ensure_blob`` deduplicates bytes inside one workspace only: another workspace with the same digest gets a
blob of its own, and no file, grant or classification is ever shared through a digest.
"""

from dataclasses import dataclass
from datetime import datetime

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import WorkspaceId, parse_uuid
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.domain.blob import (
    Blob,
    BlobAvailability,
    BlobId,
    BlobLocation,
    ContentDigest,
    LocationState,
)
from skm.modules.artifacts.domain.staged_blob import StagedBlobId, StagedBlobRef, consume
from skm.modules.artifacts.ports import BlobLocationRef, BlobRepository, StagedBlobRepository

__all__ = ["StagedBlobView", "consume_staged", "ensure_blob"]


@dataclass(frozen=True, slots=True)
class StagedBlobView:
    """What a caller of ``consume_staged_blob`` needs: the bytes' identity and where to read their start."""

    staged_blob_id: StagedBlobId
    workspace_id: WorkspaceId
    digest: ContentDigest
    size_bytes: int
    media_type: str
    detected_media_type: str
    backend_id: str
    storage_key: str

    def location(self) -> BlobLocationRef:
        return {"backend_id": self.backend_id, "storage_key": self.storage_key, "storage_version": None}


def _staged_id(ref: StagedBlobRef) -> StagedBlobId:
    raw = ref.get("staged_blob_id")
    try:
        if not isinstance(raw, str):
            raise TypeError("staged_blob_id must be text")
        return StagedBlobId(parse_uuid(raw))
    except (TypeError, ValueError):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "staged blob ref is malformed",
            details={"field": "blob.staged_blob_id", "reason": "not_a_uuid"},
        ) from None


def consume_staged(
    uow: UnitOfWork, *, ref: StagedBlobRef, workspace_id: WorkspaceId, request_id: str, now: datetime
) -> StagedBlobView:
    staged_blobs = uow.repo(StagedBlobRepository)
    staged = staged_blobs.get_for_update(_staged_id(ref))
    consumed = consume(staged, ref, workspace_id, request_id, now)
    staged_blobs.save(consumed)
    return StagedBlobView(
        staged_blob_id=consumed.id,
        workspace_id=consumed.workspace_id,
        digest=consumed.digest,
        size_bytes=consumed.size_bytes,
        media_type=consumed.media_type,
        detected_media_type=consumed.detected_media_type,
        backend_id=consumed.backend_id,
        storage_key=consumed.storage_key,
    )


def ensure_blob(uow: UnitOfWork, staged: StagedBlobView, *, ids: IdGenerator, now: datetime) -> Blob:
    """The workspace's blob of these bytes: the existing one, or a new blob with the staged location."""
    blobs = uow.repo(BlobRepository)
    found = blobs.find(staged.workspace_id, staged.digest, staged.size_bytes)
    if found is not None:
        return found
    blob = Blob(
        id=BlobId(ids.new_id()),
        workspace_id=staged.workspace_id,
        digest=staged.digest,
        size_bytes=staged.size_bytes,
        detected_media_type=staged.detected_media_type,
        availability=BlobAvailability.AVAILABLE,
        created_at=now,
        verified_at=None,
    )
    location = BlobLocation(
        blob_id=blob.id,
        backend_id=staged.backend_id,
        storage_key=staged.storage_key,
        storage_version=None,
        state=LocationState.PRESENT,
        verified_at=None,
    )
    try:
        blobs.add(blob, location)
    except Conflict as error:
        if error.code is not ErrorCode.ALREADY_EXISTS:
            raise
        raced = blobs.find(staged.workspace_id, staged.digest, staged.size_bytes)  # lost the race: reuse
        if raced is None:
            raise
        return raced
    return blob
