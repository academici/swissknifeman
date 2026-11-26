"""Facade of the artifacts module (artifacts §13): the only surface other modules and entrypoints import.

Functions run inside the caller's unit of work and check no permission: the caller is a handler that was
already authorised (scope of the *stored* file and, for a worker, the version grant). The DTOs, results and
views are the generated contract of the commands and queries, which the surfaces use through ``SkmClient``.

The facade has no clock, no id source and no configuration: ``now`` and ``ids`` come from the calling handler.
Byte access goes through the ``BlobContentReader`` the host bound to the caller's unit of work
(``read_text_content``): the signature is the documented one, the store is a dependency of the unit of
work and not a parameter, a global or a process singleton. A facade function never writes bytes, and a
grant, a digest or a storage key is never an access token by itself.

Internal report producers stage/promote through the control-plane BlobStore and BlobCoordination gateways,
then call record_staged_blob and consume_staged_blob in their existing UoW before register_file_version.
The exported staging handler reuses the upload path's validation without opening a nested transaction.
"""

from collections.abc import Sequence
from datetime import datetime
from importlib import import_module
from typing import TYPE_CHECKING, overload

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import FileVersionId, PrincipalId, ProjectId, WorkspaceId, parse_uuid
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRef
from skm.modules.artifacts.application import guards, reads, registration
from skm.modules.artifacts.application.commands.record_staged_blob import handle as record_staged_blob
from skm.modules.artifacts.application.safety_rules import build_safety_rules
from skm.modules.artifacts.application.staging import StagedBlobView, consume_staged
from skm.modules.artifacts.domain import content_safety
from skm.modules.artifacts.domain.access_grant import (
    AccessGrant,
    AccessGrantId,
    GrantReason,
    grant_is_active,
)
from skm.modules.artifacts.domain.binding import BindingRole, FileVersionRef
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyReport, SafetyRules
from skm.modules.artifacts.domain.file import FileId, FileOrigin, FileState
from skm.modules.artifacts.domain.file_version import VersionSource
from skm.modules.artifacts.domain.staged_blob import StagedBlobId, StagedBlobRef
from skm.modules.artifacts.generated.commands import (
    AddFile,
    AddFileDefsStagedBlobRef,
    AddFileDefsVersionSource,
    AddFileVersion,
    AddFileVersionDefsStagedBlobRef,
    AddFileVersionDefsVersionSource,
    RecordStagedBlob,
    RestoreFile,
    TrashFile,
)
from skm.modules.artifacts.generated.queries import (
    GetFile,
    GetFileVersion,
    ListFiles,
    ListFileVersions,
    OpenFileVersionContent,
)
from skm.modules.artifacts.generated.results import (
    AddFileResult,
    AddFileVersionResult,
    RestoreFileResult,
    TrashFileResult,
)
from skm.modules.artifacts.generated.views import (
    FileSummaryView,
    FileVersionView,
    GetFileVersionView,
    GetFileView,
    ListFilesView,
    ListFileVersionsView,
    OpenFileVersionContentView,
)
from skm.modules.artifacts.ports import (
    AccessGrantRepository,
    BlobContentReader,
    BlobCoordination,
    BlobDigestLock,
    BlobStore,
    FileRepository,
    FileVersionRepository,
)

if TYPE_CHECKING:
    from .generated.commands import PruneOrphanObjects as PruneOrphanObjects
    from .generated.queries import FindOrphanBlobs as FindOrphanBlobs
    from .generated.results import (
        PruneOrphanObjectsResult as PruneOrphanObjectsResult,
    )
    from .generated.results import (
        RecordStagedBlobResult as RecordStagedBlobResult,
    )
    from .generated.views import FindOrphanBlobsView as FindOrphanBlobsView

_LAZY_EXPORTS: dict[str, str] = {
    "PruneOrphanObjects": ".generated.commands",
    "FindOrphanBlobs": ".generated.queries",
    **dict.fromkeys(("PruneOrphanObjectsResult", "RecordStagedBlobResult"), ".generated.results"),
    "FindOrphanBlobsView": ".generated.views",
}


def __getattr__(name: str) -> object:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __package__), name)
    globals()[name] = value
    return value


__all__ = [
    "AddFile",
    "AddFileDefsStagedBlobRef",
    "AddFileDefsVersionSource",
    "AddFileResult",
    "AddFileVersion",
    "AddFileVersionDefsStagedBlobRef",
    "AddFileVersionDefsVersionSource",
    "AddFileVersionResult",
    "BindingRole",
    "BlobCoordination",
    "BlobStore",
    "Classification",
    "ContentDigest",
    "FileId",
    "FileOrigin",
    "FileSummaryView",
    "FileVersionRef",
    "FileVersionView",
    "FindOrphanBlobs",
    "FindOrphanBlobsView",
    "GetFile",
    "GetFileVersion",
    "GetFileVersionView",
    "GetFileView",
    "GrantReason",
    "ListFileVersions",
    "ListFileVersionsView",
    "ListFiles",
    "ListFilesView",
    "OpenFileVersionContent",
    "OpenFileVersionContentView",
    "PruneOrphanObjects",
    "PruneOrphanObjectsResult",
    "RecordStagedBlob",
    "RecordStagedBlobResult",
    "RestoreFile",
    "RestoreFileResult",
    "SafetyReport",
    "StagedBlobId",
    "StagedBlobRef",
    "StagedBlobView",
    "TrashFile",
    "TrashFileResult",
    "build_safety_rules",
    "consume_staged_blob",
    "extend_grants",
    "file_id_of_version",
    "get_file_version",
    "grant_access",
    "latest_ready_version",
    "read_text_content",
    "record_staged_blob",
    "register_file_version",
    "require_ready_versions",
    "require_version_read",
    "revoke_grants",
    "scan_document",
]

_PAGE = 100


def register_file_version(  # noqa: PLR0913 -- signature fixed by artifacts §13
    uow: UnitOfWork,
    *,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    title: str,
    origin: FileOrigin,
    staged: StagedBlobView,
    original_filename: str,
    media_type: str | None,
    source: VersionSource,
    classification: Classification,
    safety: SafetyReport,
    created_by: PrincipalId,
    ids: IdGenerator,
    now: datetime,
) -> FileVersionRef:
    """A new file with version 1 for evidence, transcripts, patches and reports of execution (K8).

    ``staged`` is the result of ``consume_staged_blob`` in the same unit of work; ``safety`` and
    ``classification`` come from the caller (scan and conservative source floor already applied). The filename
    is validated first; the project must belong to ``workspace_id`` and so must the staged bytes (another
    workspace is ``FORBIDDEN``). No active-project admission is checked: a recording that completes admitted
    work may follow an archive (workspace §5.4).
    """
    if staged.workspace_id == workspace_id:
        uow.repo(BlobDigestLock).lock_digest(workspace_id, staged.digest, staged.backend_id)
    return registration.register(
        uow,
        workspace_id=workspace_id,
        project_id=project_id,
        title=title,
        origin=origin,
        staged=staged,
        original_filename=original_filename,
        media_type=media_type,
        source=source,
        classification=classification,
        safety=safety,
        created_by=created_by,
        ids=ids,
        now=now,
    )


def _not_found(ids: Sequence[FileVersionId]) -> NotFound:
    return NotFound(
        ErrorCode.NOT_FOUND,
        "file version not found",
        details={"kind": "file_version", "ids": [str(item) for item in ids]},
    )


def require_ready_versions(
    uow: UnitOfWork, workspace_id: WorkspaceId, ids: Sequence[FileVersionId]
) -> tuple[FileVersionView, ...]:
    """Every version exists in ``workspace_id``, its file is not trashed and its bytes are available.

    ``NOT_FOUND`` for an unknown version or one of another workspace (indistinguishable), otherwise
    ``FILE_VERSION_NOT_READY`` with ``details.ids``. Views come back in the order asked, without repeats.
    """
    wanted = tuple(dict.fromkeys(ids))
    if not wanted:
        return ()
    ordered_ids = tuple(sorted(wanted, key=str))
    found = {version.id: version for version in uow.repo(FileVersionRepository).many(ordered_ids)}
    foreign = [item for item in wanted if item not in found or found[item].workspace_id != workspace_id]
    if foreign:
        raise _not_found(foreign)
    files = uow.repo(FileRepository)
    files_by_id = {
        file_id: files.get(file_id) for file_id in sorted({found[item].file_id for item in wanted}, key=str)
    }
    unready = [item for item in wanted if not reads.ready(uow, files_by_id[found[item].file_id], found[item])]
    if unready:
        raise PreconditionFailed(
            ErrorCode.FILE_VERSION_NOT_READY,
            "a file version is trashed or its bytes are not available",
            details={"ids": [str(item) for item in unready]},
        )
    return tuple(reads.version_view_of(uow, found[item]) for item in wanted)


def file_id_of_version(uow: UnitOfWork, workspace_id: WorkspaceId, version_id: FileVersionId) -> FileId:
    """Return the owning ``FileId`` of ``version_id`` in ``workspace_id``.

    Raises ``NOT_FOUND`` (``kind="file_version"``) when ``version_id`` does not exist or belongs to another
    workspace, matching ``require_ready_versions`` workspace isolation.
    """
    found = uow.repo(FileVersionRepository).many((version_id,))
    if not found or found[0].workspace_id != workspace_id:
        raise _not_found((version_id,))
    return found[0].file_id


def get_file_version(uow: UnitOfWork, version_id: FileVersionId) -> FileVersionView:
    version = uow.repo(FileVersionRepository).get(version_id)
    return reads.version_view_of(uow, version)


def _holds_active_grant(
    uow: UnitOfWork,
    actor: Actor,
    version_id: FileVersionId,
    workspace_id: WorkspaceId,
    now: datetime,
) -> bool:
    token = actor.grant
    ref: str | None = None
    if token is not None and token.kind == "assignment":
        if token.assignment_id is None:
            return False
        ref = str(token.assignment_id)
    grant = uow.repo(AccessGrantRepository).active_for(
        actor.principal_id, version_id, now, reason=GrantReason.ASSIGNMENT, ref=ref
    )
    return (
        grant is not None
        and grant.reason is GrantReason.ASSIGNMENT
        and (ref is None or grant.ref == ref)
        and grant.principal_id == actor.principal_id
        and grant.file_version_id == version_id
        and grant.workspace_id == workspace_id
        and grant_is_active(grant, now)
    )


def require_version_read(
    uow: UnitOfWork,
    actor: Actor,
    clock: Clock,
    version_id: FileVersionId,
    *,
    default_scope: ScopeRef | None = None,
    reported_version_id: FileVersionId | None = None,
) -> None:
    """Verify ``actor`` holds ``file.read`` on the stored file's scope and, for a worker, an active grant.

    When ``version_id`` does not exist and ``default_scope`` is given, ``file.read`` on ``default_scope`` (and
    worker grant rejection) is still enforced before any missing-version observation is returned. When
    ``reported_version_id`` is provided (e.g. while checking a resolved ``latest_at_publish`` version), any
    worker grant denial reports ``reported_version_id`` so the latest version id is never leaked.
    """
    effective_vid = version_id if reported_version_id is None else reported_version_id
    found = uow.repo(FileVersionRepository).many((version_id,))
    if not found:
        if default_scope is not None:
            guards.require(uow, clock, actor, "file.read", default_scope)
        if actor.kind is PrincipalKind.WORKER:
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                "no active access grant for this file version",
                details={"reason": "no_active_grant", "file_version_id": str(effective_vid)},
            )
        return
    version = found[0]
    file = uow.repo(FileRepository).get(version.file_id)
    guards.require(uow, clock, actor, "file.read", guards.file_scope(file))
    if actor.kind is PrincipalKind.WORKER and not _holds_active_grant(
        uow, actor, version.id, version.workspace_id, clock.now()
    ):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "no active access grant for this file version",
            details={"reason": "no_active_grant", "file_version_id": str(effective_vid)},
        )


def consume_staged_blob(
    uow: UnitOfWork, *, ref: StagedBlobRef, workspace_id: WorkspaceId, request_id: str, now: datetime
) -> StagedBlobView:
    """Check and mark the staged blob consumed in the caller's unit of work (``consume`` of artifacts §5).

    A rollback of that unit leaves the blob staged. The view carries the storage address for the scan.
    """
    raw_id = ref.get("staged_blob_id")
    if isinstance(raw_id, str):
        try:
            staged_id = StagedBlobId(parse_uuid(raw_id))
        except ValueError:
            staged_id = None
        if staged_id is not None:
            uow.repo(BlobDigestLock).lock_staged(workspace_id, staged_id)
    return consume_staged(uow, ref=ref, workspace_id=workspace_id, request_id=request_id, now=now)


def grant_access(
    uow: UnitOfWork,
    *,
    principal_id: PrincipalId,
    version_ids: Sequence[FileVersionId],
    reason: GrantReason,
    ref: str,
    expires_at: datetime,
    ids: IdGenerator,
    now: datetime,
) -> int:
    """One grant per exact version for the claim ``(reason, ref)``; returns how many rows were added.

    A principal already holding an active grant of the same claim on a version gets no second row (a repeated
    issue appends nothing, and neither does it move the expiry: ``extend_grants`` renews). The claim is looked
    up exactly, so another claim of the same principal expiring later never hides it; the workspace of each
    grant is the workspace of its version, never the caller's.
    """
    if expires_at <= now:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "a grant must expire after it is issued",
            details={"field": "expires_at", "reason": "not_in_the_future"},
        )
    versions = uow.repo(FileVersionRepository)
    grants = uow.repo(AccessGrantRepository)
    wanted = tuple(dict.fromkeys(version_ids))
    found = {version.id: version for version in versions.many(wanted)}
    for version_id in wanted:
        if version_id not in found:
            found[version_id] = versions.get(version_id)
    held = grants.held_claims(principal_id, wanted, now, reason=reason, ref=ref)
    fresh = [
        AccessGrant(
            id=AccessGrantId(ids.new_id()),
            workspace_id=found[version_id].workspace_id,
            principal_id=principal_id,
            file_version_id=version_id,
            reason=reason,
            ref=ref,
            expires_at=expires_at,
            created_at=now,
            revoked_at=None,
        )
        for version_id in wanted
        if version_id not in held
    ]
    grants.add_many(fresh)
    return len(fresh)


def revoke_grants(uow: UnitOfWork, *, reason: GrantReason, ref: str, now: datetime) -> int:
    """Close every grant of the claim; a new open after this is refused, an open stream may finish."""
    return uow.repo(AccessGrantRepository).revoke_by_ref(reason, ref, now)


def extend_grants(
    uow: UnitOfWork, *, reason: GrantReason, ref: str, expires_at: datetime, now: datetime
) -> int:
    """Extend only the still-active grants of the claim in place: no new rows, expiry never shortened.

    Revoked and expired grants are not revived (re-issue after a revoke is ``grant_access``). Returns the
    number of active grants of the claim.
    """
    return uow.repo(AccessGrantRepository).extend_by_ref(reason, ref, expires_at, now)


def scan_document(document: JsonValue, rules: SafetyRules) -> SafetyReport:
    return content_safety.scan_document(document, rules)


@overload
def latest_ready_version(uow: UnitOfWork, file_id: FileId, /) -> FileVersionView | None: ...


@overload
def latest_ready_version(
    uow: UnitOfWork, workspace_id: WorkspaceId, file_id: FileId, /
) -> FileVersionView | None: ...


def latest_ready_version(
    uow: UnitOfWork,
    first: FileId | WorkspaceId,
    second: FileId | None = None,
    /,
) -> FileVersionView | None:
    """The newest ready version of an active file, ``None`` for a trashed file or one without ready bytes.

    A published revision pins an exact version and never uses this lookup.
    """
    if second is None:
        workspace_id: WorkspaceId | None = None
        file_id = FileId(first)
    else:
        workspace_id = WorkspaceId(first)
        file_id = second
    file = uow.repo(FileRepository).get(file_id)
    if workspace_id is not None and file.workspace_id != workspace_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "file not found",
            details={"kind": "file", "ref": str(file_id)},
        )
    if file.state is not FileState.ACTIVE:
        return None
    versions = uow.repo(FileVersionRepository)
    after: str | None = None
    while True:
        page = versions.list(file.id, after=after, limit=_PAGE)
        for version in page.items:
            if reads.present_location(uow, reads.version_blob(uow, version)) is not None:
                return reads.version_view_of(uow, version)
        if page.next is None:
            return None
        after = page.next


def read_text_content(uow: UnitOfWork, file_version_id: FileVersionId, *, max_bytes: int) -> str | None:
    """The UTF-8 text of an available version; ``None`` for binary, NUL-bearing or over ``max_bytes``.

    Read through the ``BlobContentReader`` of the caller's unit of work (bound there by the host), never a
    host locator. ``NOT_FOUND`` for an unknown version, ``FILE_VERSION_NOT_READY`` when the bytes are missing,
    ``CAPABILITY_UNAVAILABLE`` when the host bound no store. Scope, the worker grant and classification are
    the caller's decision: this function is no permission check and no way around one.
    """
    version = uow.repo(FileVersionRepository).get(file_version_id)
    blob = reads.version_blob(uow, version)
    location = reads.require_present_location(uow, blob, version)
    if blob.size_bytes > max_bytes:
        return None
    try:
        data = reads.open_text(uow.repo(BlobContentReader), location, max_bytes=max_bytes)
    except NotFound:
        raise PreconditionFailed(
            ErrorCode.FILE_VERSION_NOT_READY,
            "the bytes of this file version are not in the store",
            details={"ids": [str(version.id)]},
        ) from None
    if data is None or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None
