"""``artifacts.prune_orphan_objects`` (artifacts §7, G22): manual-only prune of confirmed orphan objects.

Recomputes the orphan report and refuses with ``PreconditionFailed(INVALID_TRANSITION, "report_changed")``
if ``report_digest`` no longer matches what the operator confirmed. Skips objects younger than
``artifacts.staging.ttl_hours`` and rechecks ``StagedBlobRepository.key_referenced`` under the digest
coordination guard before calling ``BlobStore.delete_unreferenced``. Never modifies ``missing_objects``.
"""

from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from datetime import timedelta

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed, ValidationFailed
from skm.kernel.ids import WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.application.queries.find_orphan_blobs import collect_orphan_report
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.orphans import (
    parse_object_storage_key,
    prunable,
)
from skm.modules.artifacts.generated.commands import PruneOrphanObjects
from skm.modules.artifacts.generated.results import PruneOrphanObjectsResult
from skm.modules.artifacts.generated.settings import ArtifactsSettings
from skm.modules.artifacts.ports import (
    BlobCoordination,
    BlobDigestLock,
    BlobLocationRef,
    BlobStore,
    StagedBlobRepository,
)
from skm.platform.logging.logger import get_logger

__all__ = ["SPEC", "handle"]

_log = get_logger("artifacts.prune_orphan_objects")


@contextmanager
def _hold_digest(
    ctx: CommandContext,
    uow: UnitOfWork,
    workspace_id: WorkspaceId,
    digest: ContentDigest,
    backend_id: str,
) -> Generator[None]:
    if ctx.gateways.has(BlobCoordination):
        guard: AbstractContextManager[None] = ctx.gateways.get(BlobCoordination).hold(
            workspace_id, digest, backend_id
        )
        with guard:
            yield
        return
    uow.repo(BlobDigestLock).lock_digest(workspace_id, digest, backend_id)
    yield


def handle(cmd: PruneOrphanObjects, ctx: CommandContext, uow: UnitOfWork) -> PruneOrphanObjectsResult:
    if cmd.confirm is not True:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "confirm must be true",
            details={"field": "confirm"},
        )
    if not ctx.gateways.has(BlobStore):
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "blob store is not available",
            details={"capability": "blob_store"},
        )

    store = ctx.gateways.get(BlobStore)
    ws_id = None if cmd.workspace_id is None else WorkspaceId(cmd.workspace_id)
    report = collect_orphan_report(uow, store, workspace_id=ws_id, backend_id=cmd.backend_id)
    if report.report_digest != cmd.report_digest:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "orphan report changed since confirmation",
            details={"reason": "report_changed"},
        )

    now = ctx.clock.now()
    section = ctx.config.section(ArtifactsSettings)
    min_age = timedelta(hours=section.staging.ttl_hours)
    candidates = prunable(report, now=now, min_age=min_age)

    staged_repo = uow.repo(StagedBlobRepository)
    deleted = 0
    skipped_referenced = 0
    for item in candidates:
        obj_ws_id, digest = parse_object_storage_key(item.storage_key)
        with _hold_digest(ctx, uow, obj_ws_id, digest, cmd.backend_id):
            if staged_repo.key_referenced(cmd.backend_id, item.storage_key):
                skipped_referenced += 1
                continue
            location: BlobLocationRef = {
                "backend_id": cmd.backend_id,
                "storage_key": item.storage_key,
                "storage_version": None,
            }
            existed = store.exists(location)
            store.delete_unreferenced(location)
            if existed:
                deleted += 1

    _log.info(
        "artifacts.orphan_objects.pruned",
        backend_id=cmd.backend_id,
        workspace_id=None if ws_id is None else str(ws_id),
        report_digest=cmd.report_digest,
        deleted=deleted,
        skipped_referenced=skipped_referenced,
    )
    return PruneOrphanObjectsResult(deleted=deleted, skipped_referenced=skipped_referenced)


SPEC = CommandSpec(
    name="artifacts.prune_orphan_objects",
    dto=PruneOrphanObjects,
    result=PruneOrphanObjectsResult,
    permission="admin.storage",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
