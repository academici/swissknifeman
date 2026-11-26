"""``artifacts.expire_staged_blobs`` (artifacts §7): janitor expiry of staged blobs and staging remnants.

Follows the intentional "metadata row first, physical object second" order so an interruption between steps
can leave only an unreferenced orphan object (found by ``find_orphan_blobs`` / ``prune_orphan_objects``) and
never a database row pointing at deleted bytes. Consumed rows older than
``artifacts.staging.consumed_retention_days`` are purged without touching stored objects.
"""

from datetime import timedelta

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts.generated.commands import ExpireStagedBlobs
from skm.modules.artifacts.generated.results import ExpireStagedBlobsResult
from skm.modules.artifacts.generated.settings import ArtifactsSettings
from skm.modules.artifacts.ports import (
    BlobDigestLock,
    BlobLocationRef,
    BlobStore,
    StagedBlobRepository,
)

__all__ = ["SPEC", "handle"]

_MAX_LIMIT = 1000


def handle(cmd: ExpireStagedBlobs, ctx: CommandContext, uow: UnitOfWork) -> ExpireStagedBlobsResult:
    if isinstance(cmd.limit, bool) or not (1 <= cmd.limit <= _MAX_LIMIT):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "limit must be in 1..1000",
            details={"field": "limit", "limit": cmd.limit},
        )
    now = ctx.clock.now()
    section = ctx.config.section(ArtifactsSettings)
    staged_repo = uow.repo(StagedBlobRepository)
    digest_lock = uow.repo(BlobDigestLock)

    # Acquire transaction-scoped digest locks in canonical order BEFORE row locks (artifacts §6.1).
    locked: set[tuple[str, str, str]] = set()
    for ws_id, digest, backend_id in staged_repo.expired_digests(
        now, limit=min(cmd.limit * 2, _MAX_LIMIT * 2)
    ):
        digest_lock.lock_digest(ws_id, digest, backend_id)
        locked.add((backend_id, str(ws_id), digest.value))

    expired_rows = tuple(
        row
        for row in staged_repo.expired(now, limit=cmd.limit)
        if (row.backend_id, str(row.workspace_id), row.digest.value) in locked
    )
    for row in expired_rows:
        staged_repo.delete(row.id)

    consumed_cutoff = now - timedelta(days=section.staging.consumed_retention_days)
    staged_repo.purge_consumed(consumed_cutoff, limit=cmd.limit)

    objects_deleted = 0
    if ctx.gateways.has(BlobStore):
        store = ctx.gateways.get(BlobStore)
        checked_keys: set[tuple[str, str]] = set()
        for row in expired_rows:
            key_pair = (row.backend_id, row.storage_key)
            if key_pair in checked_keys:
                continue
            checked_keys.add(key_pair)
            if not staged_repo.key_referenced(row.backend_id, row.storage_key):
                location: BlobLocationRef = {
                    "backend_id": row.backend_id,
                    "storage_key": row.storage_key,
                    "storage_version": None,
                }
                existed = store.exists(location)
                store.delete_unreferenced(location)
                if existed:
                    objects_deleted += 1
        store.recover_staging(stale_before=now - timedelta(hours=section.staging.ttl_hours))

    return ExpireStagedBlobsResult(expired=len(expired_rows), objects_deleted=objects_deleted)


SPEC = CommandSpec(
    name="artifacts.expire_staged_blobs",
    dto=ExpireStagedBlobs,
    result=ExpireStagedBlobsResult,
    permission="admin.storage",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    internal=True,
    allowed_kinds=frozenset({PrincipalKind.SERVICE}),
    audit=False,
)
