"""Control-plane upload and content-open coordinator (artifacts §6.1, §7, §8; kernel-platform §4.6).

Not a bus handler: streams raw bytes outside every database transaction so byte IO and SHA-256 hashing never
hold row locks or UoW pool connections. Pre-authorises ``file.write`` and reads the workspace's live
``artifacts.upload.max_bytes`` in a short read-only unit of work, streams into ``BlobStore.stage``, verifies
exact size and optional ``expected_digest`` (discarding staging on mismatch), then under
``BlobCoordination.hold`` promotes the immutable object and dispatches ``artifacts.record_staged_blob``.
"""

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from typing import Any, BinaryIO, Final, cast

from skm.application_bus.context import AuthBasis
from skm.application_bus.ports import (
    AuditLog,
    AuditRecord,
    Authorizer,
    AuthzDecision,
    ScopeChainResolver,
)
from skm.kernel.actor import Actor
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.gateways import Gateways
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import FileVersionId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.upload_rules import (
    HEAD_BYTES,
    detect_media_type,
    normalize_media_type,
)
from skm.modules.artifacts.generated.commands import RecordStagedBlob
from skm.modules.artifacts.generated.queries import OpenFileVersionContent
from skm.modules.artifacts.generated.results import RecordStagedBlobResult
from skm.modules.artifacts.generated.settings import ArtifactsSettings
from skm.modules.artifacts.generated.views import OpenFileVersionContentView
from skm.modules.artifacts.ports import BlobCoordination, BlobStore
from skm.modules.workspace import public as workspace
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, ScopeTree

__all__ = [
    "UploadDeps",
    "bind_embedded_upload",
    "open_file_version_content_embedded",
    "upload_blob_embedded",
]

_ROLE_LACKS_PERMISSION: Final = "ROLE_LACKS_PERMISSION"
_ACTION_UPLOAD: Final = "artifacts.upload_blob"

type DispatchRecordFn = Callable[..., RecordStagedBlobResult]
type AskContentFn = Callable[..., OpenFileVersionContentView]


@dataclass(frozen=True, slots=True)
class UploadDeps:
    uow_factory: UnitOfWorkFactory
    authorizer: Authorizer
    scopes: ScopeChainResolver
    config: ConfigLoader
    gateways: Gateways
    clock: Clock
    ids: IdGenerator
    dispatch_record: DispatchRecordFn
    ask_content: AskContentFn


def _record_denied(
    deps: UploadDeps,
    *,
    actor: Actor,
    meta: RequestMeta,
    workspace_id: WorkspaceId | None,
    scope: ScopeRef | None,
    reason_code: str,
    opaque: bool,
) -> Forbidden:
    scope_json: JsonObject | None = None if scope is None else {"kind": scope.kind.value, "id": str(scope.id)}
    with deps.uow_factory(meta, readonly=False) as audit_uow:
        audit_uow.repo(AuditLog).append(
            AuditRecord(
                id=deps.ids.new_id(),
                workspace_id=workspace_id,
                actor_id=actor.principal_id,
                action=_ACTION_UPLOAD,
                target={"scope": scope_json, "permission": "file.write"},
                decision="denied",
                reason_code=reason_code,
                request_id=meta.request_id,
                recorded_at=deps.clock.now(),
            )
        )
        audit_uow.commit()
    if opaque:
        return Forbidden(
            ErrorCode.FORBIDDEN,
            "permission file.write is required",
            details={"permission": "file.write", "scope": None, "reason_code": _ROLE_LACKS_PERMISSION},
        )
    return Forbidden(
        ErrorCode.FORBIDDEN,
        "permission file.write is required",
        details={
            "permission": "file.write",
            "scope": None if scope is None else str(scope.id),
            "reason_code": reason_code,
        },
    )


def _authorize(
    authorizer: Authorizer,
    uow: Any,
    actor: Actor,
    chain: tuple[ScopeRecord, ...],
    auth_basis: AuthBasis | None,
) -> AuthzDecision:
    if auth_basis is not None:
        authorize_basis = getattr(authorizer, "authorize_basis", None)
        if callable(authorize_basis):
            return cast("AuthzDecision", authorize_basis(uow, auth_basis, "file.write", chain))
    return authorizer.authorize(uow, actor, "file.write", chain)


def _authorize_and_load_limits(
    deps: UploadDeps,
    *,
    actor: Actor,
    meta: RequestMeta,
    workspace_id: WorkspaceId,
    auth_basis: AuthBasis | None = None,
) -> tuple[int, str]:
    target = ScopeRef(ScopeKind.WORKSPACE, ScopeId(workspace_id))
    denial: tuple[WorkspaceId | None, ScopeRef | None, str, bool] | None = None
    with deps.uow_factory(meta, readonly=True) as uow:
        try:
            chain: tuple[ScopeRecord, ...] = deps.scopes.chain(uow, target)
        except NotFound as missing:
            inst_chain = deps.scopes.chain(uow, None)
            verdict = _authorize(deps.authorizer, uow, actor, inst_chain, auth_basis)
            uow.rollback()
            if verdict.allowed:
                raise missing
            denial = (None, None, verdict.reason_code or _ROLE_LACKS_PERMISSION, True)
            max_bytes, backend_id = 0, ""
        else:
            verdict = _authorize(deps.authorizer, uow, actor, chain, auth_basis)
            if not verdict.allowed:
                uow.rollback()
                denial = (workspace_id, target, verdict.reason_code or _ROLE_LACKS_PERMISSION, False)
                max_bytes, backend_id = 0, ""
            else:
                workspace.require_active_workspace(uow, workspace_id)
                section = deps.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), target).section(
                    ArtifactsSettings
                )
                max_bytes, backend_id = section.upload.max_bytes, section.blobs.backend
                uow.rollback()
    if denial is not None:
        denied_ws, denied_scope, reason, opaque = denial
        raise _record_denied(
            deps,
            actor=actor,
            meta=meta,
            workspace_id=denied_ws,
            scope=denied_scope,
            reason_code=reason,
            opaque=opaque,
        )
    return max_bytes, backend_id


def _tracked_chunks(stream: Iterable[bytes], *, max_bytes: int, head: bytearray) -> Iterator[bytes]:
    received = 0
    for chunk in stream:
        data = chunk if type(chunk) is bytes else memoryview(chunk).tobytes()
        if len(data) > max_bytes - received:
            raise ValidationFailed(
                ErrorCode.BLOB_TOO_LARGE,
                "blob exceeds artifacts.upload.max_bytes",
                details={"limit": max_bytes, "received_at_least": received + len(data)},
            )
        if len(head) < HEAD_BYTES and data:
            head.extend(data[: HEAD_BYTES - len(head)])
        received += len(data)
        yield data


def upload_blob_embedded(  # noqa: PLR0913 -- explicit upload coordinator parameters
    deps: UploadDeps,
    *,
    actor: Actor,
    meta: RequestMeta,
    workspace_id: WorkspaceId,
    stream: Iterable[bytes],
    size: int,
    expected_digest: str | None = None,
    media_type: str | None = None,
    auth_basis: AuthBasis | None = None,
) -> RecordStagedBlobResult:
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "size must be a non-negative integer",
            details={"field": "size", "reason": "negative_size"},
        )
    if expected_digest is not None:
        try:
            ContentDigest(expected_digest)
        except ValueError:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "expected_digest is invalid",
                details={"field": "expected_digest", "reason": "invalid_digest"},
            ) from None
    declared = normalize_media_type(media_type)
    store = deps.gateways.get(BlobStore)
    coordination = deps.gateways.get(BlobCoordination)
    max_bytes, backend_id = _authorize_and_load_limits(
        deps, actor=actor, meta=meta, workspace_id=workspace_id, auth_basis=auth_basis
    )
    if size > max_bytes:
        raise ValidationFailed(
            ErrorCode.BLOB_TOO_LARGE,
            "upload exceeds artifacts.upload.max_bytes",
            details={"limit": max_bytes, "size": size},
        )
    head = bytearray()
    staged = store.stage(workspace_id, _tracked_chunks(stream, max_bytes=max_bytes, head=head))
    if staged.size_bytes != size:
        store.discard(staged)
        raise ValidationFailed(
            ErrorCode.BLOB_DIGEST_MISMATCH,
            "uploaded byte count does not match declared size",
            details={"reason": "size", "expected": size, "actual": staged.size_bytes},
        )
    if expected_digest is not None and staged.digest != expected_digest:
        store.discard(staged)
        raise ValidationFailed(
            ErrorCode.BLOB_DIGEST_MISMATCH,
            "uploaded digest does not match expected digest",
            details={"reason": "digest", "expected": expected_digest, "actual": staged.digest},
        )
    detected = detect_media_type(bytes(head))
    record_meta = (
        meta
        if meta.idempotency_key is not None
        else replace(meta, idempotency_key=f"idem_{deps.ids.new_id().hex}")
    )
    with coordination.hold(workspace_id, ContentDigest(staged.digest), backend_id):
        location = store.promote(staged, expected_digest=expected_digest)
        cmd = RecordStagedBlob(
            workspace_id=workspace_id,
            digest=staged.digest,
            size=staged.size_bytes,
            media_type=declared or detected,
            detected_media_type=detected,
            backend_id=str(location["backend_id"]),
            storage_key=str(location["storage_key"]),
        )
        if auth_basis is not None:
            return deps.dispatch_record(cmd, actor, record_meta, auth_basis)
        return deps.dispatch_record(cmd, actor, record_meta)


def open_file_version_content_embedded(
    deps: UploadDeps,
    *,
    actor: Actor,
    meta: RequestMeta,
    file_version_id: FileVersionId,
    auth_basis: AuthBasis | None = None,
) -> BinaryIO:
    store = deps.gateways.get(BlobStore)
    query = OpenFileVersionContent(file_version_id=file_version_id)
    view = (
        deps.ask_content(query, actor, meta, auth_basis)
        if auth_basis is not None
        else deps.ask_content(query, actor, meta)
    )
    try:
        return store.open(view.location)
    except NotFound:
        raise PreconditionFailed(
            ErrorCode.FILE_VERSION_NOT_READY,
            "the bytes of this file version are not in the store",
            details={"ids": [str(file_version_id)]},
        ) from None


def bind_embedded_upload(  # noqa: PLR0913 - explicit composition wiring
    uow_factory: UnitOfWorkFactory,
    authorizer: Authorizer,
    scopes: ScopeChainResolver,
    config: ConfigLoader,
    gateways: Gateways,
    clock: Clock,
    ids: IdGenerator,
    dispatch: Callable[..., object],
    ask: Callable[..., object],
) -> tuple[Callable[..., RecordStagedBlobResult], Callable[..., BinaryIO]]:
    def _dispatch_record(
        cmd: RecordStagedBlob,
        act: Actor,
        meta: RequestMeta,
        basis: AuthBasis | None = None,
    ) -> RecordStagedBlobResult:
        res = (
            dispatch(cmd, actor=act, meta=meta, auth_basis=basis)
            if basis is not None
            else dispatch(cmd, actor=act, meta=meta)
        )
        return cast("RecordStagedBlobResult", res)

    def _ask_content(
        q: OpenFileVersionContent,
        act: Actor,
        meta: RequestMeta,
        basis: AuthBasis | None = None,
    ) -> OpenFileVersionContentView:
        res = (
            ask(q, actor=act, meta=meta, auth_basis=basis)
            if basis is not None
            else ask(q, actor=act, meta=meta)
        )
        return cast("OpenFileVersionContentView", res)

    deps = UploadDeps(
        uow_factory=uow_factory,
        authorizer=authorizer,
        scopes=scopes,
        config=config,
        gateways=gateways,
        clock=clock,
        ids=ids,
        dispatch_record=_dispatch_record,
        ask_content=_ask_content,
    )

    def upload(
        *,
        actor: Actor,
        meta: RequestMeta,
        workspace_id: WorkspaceId,
        stream: Iterable[bytes],
        size: int,
        expected_digest: str | None,
        media_type: str | None,
        auth_basis: AuthBasis | None = None,
    ) -> RecordStagedBlobResult:
        return upload_blob_embedded(
            deps,
            actor=actor,
            meta=meta,
            workspace_id=workspace_id,
            stream=stream,
            size=size,
            expected_digest=expected_digest,
            media_type=media_type,
            auth_basis=auth_basis,
        )

    def open_content(
        *,
        actor: Actor,
        meta: RequestMeta,
        file_version_id: Any,
        auth_basis: AuthBasis | None = None,
    ) -> BinaryIO:
        return open_file_version_content_embedded(
            deps, actor=actor, meta=meta, file_version_id=file_version_id, auth_basis=auth_basis
        )

    return upload, open_content
