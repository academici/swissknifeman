"""``artifacts.find_orphan_blobs`` (artifacts §8): read-only orphan and missing blob report."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.artifacts.domain.orphans import (
    MissingObject,
    OrphanObject,
    OrphanReport,
    build_orphan_report,
)
from skm.modules.artifacts.generated.queries import FindOrphanBlobs
from skm.modules.artifacts.generated.views import (
    FindOrphanBlobsView,
    FindOrphanBlobsViewMissingObjectsItem,
    FindOrphanBlobsViewOrphanObjectsItem,
)
from skm.modules.artifacts.ports import BlobLocationRef, BlobRepository, BlobStore

__all__ = ["SPEC", "collect_orphan_report", "handle"]

_SCOPE_PAGE_LIMIT = 500


def _target_workspaces(uow: UnitOfWork, workspace_id: WorkspaceId | None) -> tuple[WorkspaceId, ...]:
    scopes = uow.repo(ScopeRegistry)
    if workspace_id is not None:
        try:
            record = scopes.get(ScopeId(workspace_id))
        except NotFound:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "workspace not found",
                details={"kind": "workspace", "ref": str(workspace_id)},
            ) from None
        if record.kind is not ScopeKind.WORKSPACE:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "workspace not found",
                details={"kind": "workspace", "ref": str(workspace_id)},
            )
        return (workspace_id,)

    found: list[WorkspaceId] = []
    after: ScopeId | None = None
    while True:
        batch = scopes.list_scopes(after=after, limit=_SCOPE_PAGE_LIMIT)
        if not batch:
            break
        found.extend(WorkspaceId(record.id) for record in batch if record.kind is ScopeKind.WORKSPACE)
        if len(batch) < _SCOPE_PAGE_LIMIT:
            break
        after = batch[-1].id
    return tuple(found)


def collect_orphan_report(
    uow: UnitOfWork,
    store: BlobStore,
    *,
    workspace_id: WorkspaceId | None,
    backend_id: str,
) -> OrphanReport:
    """Compare physical ``BlobStore`` objects against ``blob_locations`` without mutating state."""
    workspaces = _target_workspaces(uow, workspace_id)
    blob_repo = uow.repo(BlobRepository)
    orphans: list[OrphanObject] = []
    missing: list[MissingObject] = []

    for ws_id in workspaces:
        known_keys = blob_repo.all_keys(ws_id, backend_id)
        entries = blob_repo.entries_in_backend(ws_id, backend_id)
        present_keys: set[str] = set()

        for location in store.iter_objects(ws_id):
            if location.get("backend_id") != backend_id:
                continue
            storage_key = location.get("storage_key")
            if not isinstance(storage_key, str):
                continue
            present_keys.add(storage_key)
            if storage_key not in known_keys:
                try:
                    stat = store.stat(location)
                except NotFound:
                    present_keys.discard(storage_key)
                    continue
                orphans.append(
                    OrphanObject(
                        storage_key=storage_key,
                        size_bytes=stat.size_bytes,
                        created_at=stat.created_at,
                    )
                )

        for blob_id, storage_key in entries:
            if storage_key not in present_keys:
                loc: BlobLocationRef = {
                    "backend_id": backend_id,
                    "storage_key": storage_key,
                    "storage_version": None,
                }
                if not store.exists(loc):
                    missing.append(MissingObject(blob_id=blob_id, storage_key=storage_key))

    return build_orphan_report(orphans, missing)


def handle(query: FindOrphanBlobs, ctx: QueryContext, uow: UnitOfWork) -> FindOrphanBlobsView:
    if not ctx.gateways.has(BlobStore):
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "blob store is not available",
            details={"capability": "blob_store"},
        )
    ws_id = None if query.workspace_id is None else WorkspaceId(query.workspace_id)
    report = collect_orphan_report(
        uow,
        ctx.gateways.get(BlobStore),
        workspace_id=ws_id,
        backend_id=query.backend_id,
    )
    return FindOrphanBlobsView(
        orphan_objects=tuple(
            FindOrphanBlobsViewOrphanObjectsItem(
                storage_key=item.storage_key,
                size_bytes=item.size_bytes,
                created_at=item.created_at,
            )
            for item in report.orphan_objects
        ),
        missing_objects=tuple(
            FindOrphanBlobsViewMissingObjectsItem(
                blob_id=item.blob_id,
                storage_key=item.storage_key,
            )
            for item in report.missing_objects
        ),
        report_digest=report.report_digest,
    )


SPEC = QuerySpec(
    name="artifacts.find_orphan_blobs",
    dto=FindOrphanBlobs,
    result=FindOrphanBlobsView,
    permission="admin.storage",
    scope_of=None,
    handler=handle,
)
