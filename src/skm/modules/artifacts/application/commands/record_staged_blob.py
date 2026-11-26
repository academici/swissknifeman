"""``artifacts.record_staged_blob`` (artifacts §7): internal metadata commit for promoted bytes.

Invoked by the control-plane upload coordinator under ``BlobCoordination.hold`` after ``BlobStore.promote``
has made the content-addressed object durable. Validates the active workspace, object layout, store presence
and effective upload ceiling, then records the ``StagedBlob`` row with ``expires_at = now + ttl_hours``;
no domain event is emitted (bus audit records the command).
"""

from datetime import timedelta

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.staged_blob import StagedBlob, StagedBlobId
from skm.modules.artifacts.domain.upload_rules import normalize_media_type
from skm.modules.artifacts.generated.commands import RecordStagedBlob
from skm.modules.artifacts.generated.results import RecordStagedBlobResult
from skm.modules.artifacts.generated.settings import ArtifactsSettings
from skm.modules.artifacts.ports import BlobLocationRef, BlobStore, StagedBlobRepository
from skm.modules.workspace import public as workspace

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: RecordStagedBlob) -> ScopeRef:
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(cmd.workspace_id))


def _parse_digest(raw: str) -> ContentDigest:
    try:
        return ContentDigest(raw)
    except ValueError:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "digest is invalid",
            details={"field": "digest", "reason": "invalid_digest"},
        ) from None


def _require_media_type(value: str, field: str) -> str:
    try:
        normalized = normalize_media_type(value)
    except ValidationFailed:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"{field} is invalid",
            details={"field": field, "reason": "invalid_media_type"},
        ) from None
    if normalized is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"{field} is invalid",
            details={"field": field, "reason": "invalid_media_type"},
        )
    return normalized


def handle(cmd: RecordStagedBlob, ctx: CommandContext, uow: UnitOfWork) -> RecordStagedBlobResult:
    workspace_id = WorkspaceId(cmd.workspace_id)
    workspace.require_active_workspace(uow, workspace_id)
    digest = _parse_digest(cmd.digest)
    media_type = _require_media_type(cmd.media_type, "media_type")
    detected = _require_media_type(cmd.detected_media_type, "detected_media_type")
    section = ctx.config.section(ArtifactsSettings)
    if cmd.size > section.upload.max_bytes:
        raise ValidationFailed(
            ErrorCode.BLOB_TOO_LARGE,
            "upload exceeds artifacts.upload.max_bytes",
            details={"limit": section.upload.max_bytes, "size": cmd.size},
        )
    hex_digest = digest.value.removeprefix("sha256:")
    expected_key = f"{workspace_id}/objects/{hex_digest[:2]}/{hex_digest}"
    if cmd.storage_key != expected_key:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "storage_key does not match workspace and digest",
            details={"reason": "invalid_storage_key"},
        )
    if ctx.gateways.has(BlobStore):
        location: BlobLocationRef = {
            "backend_id": cmd.backend_id,
            "storage_key": cmd.storage_key,
            "storage_version": None,
        }
        try:
            stat = ctx.gateways.get(BlobStore).stat(location)
        except NotFound:
            raise PreconditionFailed(
                ErrorCode.FILE_VERSION_NOT_READY,
                "promoted blob bytes are not present in the store",
                details={"storage_key": cmd.storage_key},
            ) from None
        if stat.size_bytes != cmd.size:
            raise ValidationFailed(
                ErrorCode.BLOB_DIGEST_MISMATCH,
                "stored object size does not match declared size",
                details={"reason": "size", "expected": cmd.size, "actual": stat.size_bytes},
            )
    now = ctx.clock.now()
    staged = StagedBlob(
        id=StagedBlobId(ctx.ids.new_id()),
        workspace_id=workspace_id,
        digest=digest,
        size_bytes=cmd.size,
        media_type=media_type,
        detected_media_type=detected,
        backend_id=cmd.backend_id,
        storage_key=cmd.storage_key,
        created_by=ctx.actor.principal_id,
        created_at=now,
        expires_at=now + timedelta(hours=section.staging.ttl_hours),
        consumed_at=None,
        consumed_request_id=None,
    )
    uow.repo(StagedBlobRepository).add(staged)
    return RecordStagedBlobResult(
        staged_blob_id=staged.id,
        workspace_id=workspace_id,
        digest=digest.value,
        size=staged.size_bytes,
        media_type=staged.media_type,
    )


SPEC = CommandSpec(
    name="artifacts.record_staged_blob",
    dto=RecordStagedBlob,
    result=RecordStagedBlobResult,
    permission="file.write",
    scope_of=scope_of,
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle,
    allowed_kinds=frozenset(PrincipalKind),  # workers stage evidence blobs (artifacts §7)
)
