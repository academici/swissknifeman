"""Always-enabled platform declaration; handlers are registered by their owner leaves.

``platform.doctor`` is registered; composition supplies its ``DoctorRunner`` gateway
(kernel-platform §5.6). The platform declares no ``doctor_checks`` of its own yet; the runner also serves the
recorded reports of the enabled modules' checks, which ``App.doctor`` collects host-side (§5.2a).

``platform.migration_status`` reads the chain and the history through the ``SchemaVersionReader``
repository port. There is no ``platform.apply_migrations`` (K21): applying migrations is the local CLI
operation ``skm db migrate``. The ``skm db`` group reaches the migration runner, the DSN of the migrator role
and the schema snapshot only through the functions below (entrypoints may import bootstrap, not adapters).

``platform.list_dead_outbox`` and ``platform.retry_outbox`` (``admin.events``) read and requeue dead
outbox rows through the core ``OutboxStore`` repository port.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from itertools import batched
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import TYPE_CHECKING, Any, Final, Self, cast
from urllib.parse import urlsplit
from uuid import UUID

import skm.adapters.postgres.migrations as _migrations_package
from skm.adapters.memory.core.storage_inspector import MemoryStorageInspector
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.secrets.env import EnvSecretResolver
from skm.adapters.secrets.file import FileSecretResolver
from skm.application_bus.context import CommandContext
from skm.application_bus.middleware import request_digest
from skm.application_bus.platform.doctor import DOCTOR
from skm.application_bus.platform.migrations import MIGRATION_STATUS, SchemaVersionReader
from skm.application_bus.platform.outbox import LIST_DEAD_OUTBOX, RETRY_OUTBOX
from skm.application_bus.platform.storage import (
    REPAIR_STORAGE_SAFE,
    VERIFY_STORAGE,
    StorageInspector,
    StorageObjects,
    StorageRepair,
)
from skm.application_bus.ports import DoctorRunner, IdempotencyReceipt, IdempotencyStore
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    CapabilityUnavailable,
    Conflict,
    InternalError,
    NotFound,
    SkmError,
    ValidationFailed,
)
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import Isolation, RequestMeta, UnitOfWork, UnitOfWorkFactory
from skm.modules.artifacts.application.commands.expire_staged_blobs import SPEC as EXPIRE_STAGED_BLOBS
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.staged_blob import StagedBlob, StagedBlobId
from skm.modules.artifacts.generated.commands import ExpireStagedBlobs
from skm.modules.artifacts.ports import BlobLocationRef, BlobStore, StagedBlobRepository
from skm.platform.config.bootstrap import BootstrapConfig, load_bootstrap
from skm.platform.config.secrets import SecretRef, SecretResolvers
from skm.platform.generated.commands import RepairStorageSafe, RetryOutbox
from skm.platform.generated.results import RepairStorageSafeResult, VerifyStorageResult
from skm.platform.storage.repair import repair_report
from skm.platform.storage.verify import ExpiredStage, Location
from skm.platform.system_clock import SystemClock

if TYPE_CHECKING:
    from skm.adapters.postgres.migrations.runner import MigrationFile, MigrationRunner, MigrationState

__all__ = [
    "PLATFORM_MANIFEST",
    "SNAPSHOT_FILE",
    "MigrationFile",
    "MigrationRunner",
    "MigrationState",
    "MigratorDsn",
    "local_known_version",
    "local_migration_runner",
    "local_schema_snapshot",
    "resolve_migrator_dsn",
]

PLATFORM_MANIFEST = ModuleManifest(
    id="platform",
    depends_on=(),
    optional=False,
    db_schema="skm_core",
    settings_sections=(),
    permissions=frozenset({"config.read", "admin.storage", "admin.events"}),
    commands=(RETRY_OUTBOX, REPAIR_STORAGE_SAFE),
    queries=(DOCTOR, MIGRATION_STATUS, LIST_DEAD_OUTBOX, VERIFY_STORAGE),
    subscribers=(),
    host_operations=(),
    repository_ports=(SchemaVersionReader, StorageInspector),
    gateway_ports=(DoctorRunner, StorageObjects, StorageRepair),
)

MEMORY_STORAGE_REPOSITORIES = {StorageInspector: MemoryStorageInspector}


def memory_uow_open(backend: InMemoryBackend) -> Callable[[], bool]:
    def check() -> bool:
        if not backend.lock.acquire(blocking=False):
            return False  # held by another thread: this one is outside every unit of work of the backend
        try:
            return backend.active > 0  # the RLock was re-entered: this thread's own unit of work is open
        finally:
            backend.lock.release()

    return check


def _blob_location(location: Location) -> BlobLocationRef:
    return {
        "backend_id": location.backend_id,
        "storage_key": location.storage_key,
        "storage_version": location.storage_version,
    }


class _StorageObjects:
    def __init__(self, store: BlobStore) -> None:
        self._store = store

    def exists(self, location: Location) -> bool:
        try:
            return self._store.exists(_blob_location(location))
        except ValidationFailed:
            return False  # malformed stored location or an unavailable backend
        except InternalError as error:
            if error.details.get("reason") != "blob_corrupt":
                raise
            return False

    def verify(self, location: Location, digest: str) -> bool:
        try:
            return self._store.verify(_blob_location(location), digest)
        except NotFound:
            return False

    def objects(self, workspace_id: UUID) -> Iterable[Location]:
        for row in self._store.iter_objects(WorkspaceId(workspace_id)):
            yield Location(str(row["backend_id"]), str(row["storage_key"]))


class _SelectedStaging:
    """Limit the owner command to reported candidates, in digest lock order."""

    def __init__(
        self, uow: UnitOfWork, candidates: tuple[ExpiredStage, ...], *, committed: tuple[StagedBlob, ...] = ()
    ) -> None:
        self._uow = uow
        self._repo = uow.repo(StagedBlobRepository)
        self._candidates = candidates
        self._committed = committed
        self._objects = {(row.backend_id, row.storage_key): row for row in committed}
        self._rows: dict[StagedBlobId, StagedBlob] = {}
        self.removed: list[StagedBlob] = []

    def repo[R](self, port: type[R]) -> R:
        if port is StagedBlobRepository:
            return cast("R", self)
        return self._uow.repo(port)

    def expired_digests(
        self, now: datetime, *, limit: int
    ) -> tuple[tuple[WorkspaceId, ContentDigest, str], ...]:
        del now
        unique = dict.fromkeys(
            (WorkspaceId(item.workspace_id), ContentDigest(item.digest), item.location.backend_id)
            for item in self._candidates
        )
        return tuple(unique)[:limit]

    def expired(self, now: datetime, *, limit: int) -> tuple[StagedBlob, ...]:
        if self._committed:
            return self._committed[:limit]
        # Recheck after the owner has acquired digest locks so promotion and consumption can win safely.
        current = {item.id: item for item in self._uow.repo(StorageInspector).expired_staging(now)}
        for item in self._candidates[:limit]:
            if current.get(item.id) != item:
                continue
            try:
                row = self._repo.get_for_update(StagedBlobId(item.id))
            except NotFound:
                continue
            if row.consumed_at is None and row.expires_at <= now:
                self._rows[row.id] = row
        return tuple(self._rows.values())

    def purge_consumed(self, before: datetime, *, limit: int) -> int:
        del before, limit
        return 0

    def delete(self, staged_blob_id: StagedBlobId) -> None:
        if not self._committed:
            self._repo.delete(staged_blob_id)
            self.removed.append(self._rows[staged_blob_id])

    def key_referenced(self, backend_id: str, storage_key: str) -> bool:
        if self._repo.key_referenced(backend_id, storage_key):
            return True
        row = self._objects[backend_id, storage_key]
        return self._uow.repo(StorageInspector).has_blob(row.workspace_id, row.digest.value)


def _leave_staging_remnants(*, stale_before: datetime) -> int:
    del stale_before
    return 0


class _StorageCommandUow:
    """Release the bus connection during owner transactions, then open one for its receipt and audit."""

    def __init__(
        self, factory: UnitOfWorkFactory, meta: RequestMeta, isolation: Isolation, ttl: timedelta
    ) -> None:
        self.factory, self.ttl = factory, ttl
        self._meta, self._isolation = meta, isolation
        self.uow = factory(meta, isolation=isolation)
        self.preview = False
        self._open = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.uow, name)

    def __enter__(self) -> Self:
        self.uow.__enter__()
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._open:
            self._open = False
            self.uow.__exit__(exc_type, exc, tb)

    def close_plan(self) -> None:
        self.__exit__(None, None, None)

    def open_result(self) -> None:
        self.uow = self.factory(self._meta, isolation=self._isolation)
        self.__enter__()

    def commit(self) -> None:
        if self.preview:
            self.uow.rollback()
        else:
            self.uow.commit()


def storage_command_uows(factory: UnitOfWorkFactory, ttl: timedelta) -> UnitOfWorkFactory:
    def open_uow(
        meta: RequestMeta,
        *,
        readonly: bool = False,
        isolation: Isolation = Isolation.READ_COMMITTED,
    ) -> UnitOfWork:
        if readonly:
            return factory(meta, readonly=True, isolation=isolation)
        return cast("UnitOfWork", _StorageCommandUow(factory, meta, isolation, ttl))

    return open_uow


_PLAN_OPERATION = "platform.storage_repair_plan"
_ACTION_OPERATION = "platform.storage_repair_action"


def _store_receipt(store: IdempotencyStore, receipt: IdempotencyReceipt) -> None:
    try:
        store.put(receipt)
    except Conflict as error:
        if error.code is not ErrorCode.ALREADY_EXISTS:
            raise
        # The bus retries from authorization, then reads the winning plan or action receipt.
        raise Conflict(ErrorCode.SERIALIZATION_FAILURE, "Concurrent storage repair") from error


class _RepairOwnerCommands:
    """Run the owner commands under the authority of the authorized storage repair."""

    def __init__(
        self, factory: UnitOfWorkFactory, ttl: timedelta, ctx: CommandContext, generation: str
    ) -> None:
        self._factory, self._ttl = factory, ttl
        self._ctx, self._generation = ctx, generation

    def _run(
        self,
        identity: str,
        digest: str,
        action: Callable[[CommandContext, UnitOfWork], JsonObject],
    ) -> JsonObject:
        ctx = self._ctx
        key = f"storage-repair:{self._generation}:{identity}"
        meta = replace(ctx.meta, idempotency_key=key)
        with self._factory(meta) as uow:
            store = uow.repo(IdempotencyStore)
            prior = store.get(None, ctx.actor.principal_id, _ACTION_OPERATION, key)
            if prior is not None:
                return prior.result
            result = action(replace(ctx, meta=meta), uow)
            now = ctx.clock.now()
            _store_receipt(
                store,
                IdempotencyReceipt(
                    None,
                    ctx.actor.principal_id,
                    _ACTION_OPERATION,
                    key,
                    digest,
                    result,
                    now,
                    now + self._ttl,
                ),
            )
            uow.commit()
            return result

    def expire_staged(self, index: int, ids: tuple[str, ...]) -> frozenset[str]:
        removed: list[StagedBlob] = []
        cmd = ExpireStagedBlobs(limit=len(ids))
        wanted = set(ids)

        def expire(ctx: CommandContext, uow: UnitOfWork) -> JsonObject:
            candidates = sorted(
                (
                    row
                    for row in uow.repo(StorageInspector).expired_staging(ctx.clock.now())
                    if str(row.id) in wanted
                ),
                key=lambda row: (row.location.backend_id, row.workspace_id, row.digest, row.id),
            )
            selected = _SelectedStaging(uow, tuple(candidates))
            metadata_only = replace(ctx, gateways=GatewayTable({}, "control_plane_gateway"))
            EXPIRE_STAGED_BLOBS.handler(cmd, metadata_only, cast("UnitOfWork", selected))
            removed.extend(selected.removed)
            return {"expired": [str(row.id) for row in removed]}

        result = self._run(f"staging:{index}", request_digest(EXPIRE_STAGED_BLOBS, cmd), expire)
        if removed and self._ctx.gateways.has(BlobStore):
            self._delete_unreferenced(tuple(removed))
        return frozenset(cast("list[str]", result["expired"]))

    def retry_outbox(self, ident: str) -> bool:
        cmd = RetryOutbox(outbox_id=UUID(ident))
        result = self._run(
            f"outbox:{ident}",
            request_digest(RETRY_OUTBOX, cmd),
            lambda ctx, uow: RETRY_OUTBOX.handler(cmd, ctx, uow).to_json(),
        )
        return result["requeued"] == 1

    def _delete_unreferenced(self, rows: tuple[StagedBlob, ...]) -> None:
        ctx = self._ctx
        candidates = tuple(
            ExpiredStage(
                row.id, row.workspace_id, row.digest.value, Location(row.backend_id, row.storage_key)
            )
            for row in rows
        )
        try:
            store = ctx.gateways.get(BlobStore)
            scoped_store = SimpleNamespace(
                exists=store.exists,
                delete_unreferenced=store.delete_unreferenced,
                recover_staging=_leave_staging_remnants,
            )
            cleanup = replace(ctx, gateways=GatewayTable({BlobStore: scoped_store}, "control_plane_gateway"))
            with self._factory(ctx.meta) as uow:
                # The artifact owner reacquires the digest locks and checks live references before deletion.
                selected = _SelectedStaging(uow, candidates, committed=rows)
                EXPIRE_STAGED_BLOBS.handler(
                    ExpireStagedBlobs(limit=len(rows)), cleanup, cast("UnitOfWork", selected)
                )
                uow.commit()
        except (SkmError, OSError):
            # An interrupted cleanup can leave an orphan, which verification reports.
            ctx.log.warning("storage.expired_object_cleanup_failed")


class _StorageRepair:
    def prepare_preview(self, ctx: CommandContext, uow: UnitOfWork) -> None:
        key = ctx.meta.idempotency_key
        store = uow.repo(IdempotencyStore)
        if key is not None and store.get(None, ctx.actor.principal_id, _PLAN_OPERATION, key) is not None:
            raise Conflict(ErrorCode.IDEMPOTENCY_KEY_REUSED, "Idempotency-Key was used for another request")
        self._boundary(uow).preview = True

    def apply(
        self,
        cmd: RepairStorageSafe,
        inspect: Callable[[], VerifyStorageResult],
        ctx: CommandContext,
        uow: UnitOfWork,
    ) -> RepairStorageSafeResult:
        boundary = self._boundary(uow)
        generation, inspection = self._plan(cmd, inspect, ctx, boundary)
        boundary.close_plan()
        commands = _RepairOwnerCommands(boundary.factory, boundary.ttl, ctx, generation)
        staged = (item.target.id for item in inspection.findings if item.code == "STAGED_EXPIRED")
        repaired = {
            ("STAGED_EXPIRED", ident)
            for index, batch in enumerate(batched(staged, 1000))
            for ident in commands.expire_staged(index, batch)
        }
        repaired.update(
            ("OUTBOX_DEAD", item.target.id)
            for item in inspection.findings
            if item.code == "OUTBOX_DEAD" and commands.retry_outbox(item.target.id)
        )
        boundary.open_result()
        return repair_report(inspection.findings, frozenset(repaired), dry_run=False)

    @staticmethod
    def _plan(
        cmd: RepairStorageSafe,
        inspect: Callable[[], VerifyStorageResult],
        ctx: CommandContext,
        boundary: _StorageCommandUow,
    ) -> tuple[str, VerifyStorageResult]:
        key = ctx.meta.idempotency_key
        if key is None:
            raise RuntimeError("storage repair requires an idempotency key")
        principal = ctx.actor.principal_id
        store = boundary.uow.repo(IdempotencyStore)
        digest = request_digest(REPAIR_STORAGE_SAFE, cmd)
        receipt = store.get(None, principal, _PLAN_OPERATION, key)
        if receipt is not None:
            if receipt.request_digest != digest:
                raise Conflict(
                    ErrorCode.IDEMPOTENCY_KEY_REUSED, "Idempotency-Key was used for another request"
                )
            return str(receipt.result["generation"]), VerifyStorageResult.from_json(
                cast("JsonObject", receipt.result["inspection"])
            )
        generation = str(ctx.ids.new_id())
        inspection = inspect()
        now = ctx.clock.now()
        _store_receipt(
            store,
            IdempotencyReceipt(
                None,
                principal,
                _PLAN_OPERATION,
                key,
                digest,
                {"generation": generation, "inspection": inspection.to_json()},
                now,
                now + boundary.ttl,
            ),
        )
        boundary.uow.commit()
        return generation, inspection

    @staticmethod
    def _boundary(uow: UnitOfWork) -> _StorageCommandUow:
        if not isinstance(uow, _StorageCommandUow):
            raise RuntimeError("storage repair requires the composed command unit of work")
        return uow


def bind_storage_gateways(entries: dict[type[object], object], inspection: StorageObjects | None) -> None:
    entries[StorageRepair] = _StorageRepair()
    if inspection is None and (store := entries.get(BlobStore)) is not None:
        inspection = _StorageObjects(cast("BlobStore", store))
    if inspection is not None:
        entries.setdefault(StorageObjects, inspection)


# The package copy of the normalized snapshot; written only by ``skm db snapshot --write`` (make db-snapshot).
SNAPSHOT_FILE: Final = Path(_migrations_package.__file__).resolve().parent / "schema.snapshot.sql"
_APPLIED_BY: Final = "skm db"


def __getattr__(name: str) -> type[MigrationFile] | type[MigrationRunner] | type[MigrationState]:
    if name in {"MigrationFile", "MigrationRunner", "MigrationState"}:
        from skm.adapters.postgres.migrations import runner

        return getattr(runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass(frozen=True, slots=True)
class MigratorDsn:
    """A resolved connection string and the credential texts that must never be shown."""

    dsn: str = field(repr=False)
    secrets: tuple[str, ...] = field(repr=False)


def _passwords(dsn: str) -> tuple[str, ...]:
    """The password of a URL or key/value DSN, as written and as libpq decodes it."""
    from skm.adapters.postgres.connection import dsn_password

    written = urlsplit(dsn).password if "://" in dsn else None
    return tuple(item for item in (written, dsn_password(dsn)) if item)


def _no_dsn() -> CapabilityUnavailable:
    return CapabilityUnavailable(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        "migrations are applied locally: no database DSN is available here",
        details={
            "hint": "run `skm db migrate` on a host with database access, or pass --database-url "
            "(or set database.migrator_url in the bootstrap)"
        },
    )


def _configured(bootstrap: BootstrapConfig) -> SecretRef | str | None:
    """Bootstrap ``database.migrator_url``, otherwise ``database.url`` (the runtime user's DSN)."""
    return bootstrap.database_migrator_url or bootstrap.database_url


def resolve_migrator_dsn(
    explicit: str | None,
    *,
    bootstrap_path: str | None,
    instance: str | None,
    environ: dict[str, str] | None,
    home: Path,
) -> MigratorDsn:
    """``--database-url``, else bootstrap ``database.migrator_url``, else ``database.url`` (cli §6.3, K21).

    Only ``skm db`` reads ``migrator_url``; serve, worker and the API never do. An explicit URL needs no
    bootstrap. A bootstrap without a DSN (an ``http`` profile) is refused with a hint, without any API call.
    """
    env = dict(environ or {})
    revealed: list[str] = []
    if explicit:
        dsn = explicit
    else:
        bootstrap = load_bootstrap(bootstrap_path, env, home, instance=instance)
        configured = _configured(bootstrap)
        if configured is None:
            raise _no_dsn()
        if isinstance(configured, str):
            dsn = configured
        else:
            resolvers = SecretResolvers(
                (EnvSecretResolver(env), FileSecretResolver()), on_reveal=revealed.append
            )
            dsn = resolvers.resolve(configured).reveal()
    if not dsn.strip():
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "the database DSN is empty", details={"field": "database.url"}
        )
    return MigratorDsn(dsn, tuple(dict.fromkeys(item for item in (dsn, *_passwords(dsn), *revealed) if item)))


def local_known_version() -> int:
    from skm.adapters.postgres.migrations.runner import discover_migrations, known_version

    return known_version(discover_migrations())


def local_migration_runner(dsn: str) -> MigrationRunner:
    """The runner over the packaged chain; transactional only, one advisory lock per ``migrate``."""
    from skm.adapters.postgres.migrations.runner import MigrationRunner, discover_migrations, package_loader

    return MigrationRunner(dsn, discover_migrations(), package_loader(), SystemClock(), _APPLIED_BY)


def local_schema_snapshot(dsn: str) -> str:
    """The normalized ``pg_dump --schema-only`` text of the database at ``dsn``; nothing is written."""
    from skm.adapters.postgres.migrations.snapshot import schema_snapshot

    return schema_snapshot(dsn)
