"""Authorized storage inspection and bounded repair."""

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Final, Protocol
from uuid import UUID

from skm.application_bus.context import CommandContext, QueryContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode, QuerySpec
from skm.kernel.gateways import control_plane_gateway
from skm.kernel.ports_uow import Isolation, UnitOfWork, repository_port
from skm.platform.generated.commands import RepairStorageSafe
from skm.platform.generated.queries import VerifyStorage
from skm.platform.generated.results import RepairStorageSafeResult, VerifyStorageResult
from skm.platform.storage.repair import repair_report, selected_codes
from skm.platform.storage.verify import (
    CATALOG,
    LEVELS,
    EvidenceCheck,
    ExpiredStage,
    Finding,
    Level,
    Location,
    ObjectInventory,
    check_evidence,
    check_objects,
    report,
)

__all__ = ["REPAIR_STORAGE_SAFE", "VERIFY_STORAGE", "StorageInspector", "StorageObjects", "StorageRepair"]


@repository_port
class StorageInspector(Protocol):
    """Read raw integrity facts within the caller's snapshot."""

    def inspect(
        self,
        level: Level,
        *,
        now: datetime,
        recovery_before: datetime,
    ) -> Iterable[Finding]: ...

    def expired_staging(self, now: datetime) -> Iterable[ExpiredStage]: ...

    def has_blob(self, workspace_id: UUID, digest: str) -> bool: ...

    def evidence(self) -> Iterable[EvidenceCheck]: ...

    def inventory(self) -> ObjectInventory: ...


@control_plane_gateway
class StorageObjects(Protocol):
    """Read-only access to final blob objects."""

    def exists(self, location: Location) -> bool: ...

    def verify(self, location: Location, digest: str) -> bool: ...

    def objects(self, workspace_id: UUID) -> Iterable[Location]: ...


@control_plane_gateway
class StorageRepair(Protocol):
    """Apply a durable inspection plan through transaction-owning repair facades."""

    def prepare_preview(self, ctx: CommandContext, uow: UnitOfWork) -> None: ...

    def apply(
        self,
        cmd: RepairStorageSafe,
        inspect: Callable[[], VerifyStorageResult],
        ctx: CommandContext,
        uow: UnitOfWork,
    ) -> RepairStorageSafeResult: ...


def _inspect(
    levels: tuple[Level, ...],
    ctx: CommandContext | QueryContext,
    uow: UnitOfWork,
    *,
    codes: frozenset[str] | None = None,
) -> VerifyStorageResult:
    inspector = uow.repo(StorageInspector)
    now = ctx.clock.now()
    window = ctx.config.get("execution.supervisor.window_seconds")
    seconds = window if isinstance(window, int) else 3600
    before = now - timedelta(seconds=seconds)
    findings = [
        item
        for level in levels
        for item in inspector.inspect(
            level,
            now=now,
            recovery_before=before,
        )
    ]
    blobs = ctx.gateways.get(StorageObjects) if ctx.gateways.has(StorageObjects) else None
    if "execution" in levels:
        findings.extend(check_evidence(inspector.evidence(), None if blobs is None else blobs.exists))
    if blobs is not None and ("files" in levels or "cryptographic" in levels):
        findings.extend(
            check_objects(inspector.inventory(), levels, blobs.exists, blobs.verify, blobs.objects)
        )
    return report(levels, (item for item in findings if codes is None or item.code in codes))


def handle_verify_storage(query: VerifyStorage, ctx: QueryContext, uow: UnitOfWork) -> VerifyStorageResult:
    levels = LEVELS if query.levels is None else tuple(dict.fromkeys(query.levels))
    return _inspect(levels, ctx, uow)


def handle_repair_storage_safe(
    cmd: RepairStorageSafe,
    ctx: CommandContext,
    uow: UnitOfWork,
) -> RepairStorageSafeResult:
    codes = selected_codes(cmd.codes)
    selected = {CATALOG[code][0] for code in codes}
    levels: tuple[Level, ...] = tuple(level for level in LEVELS if level in selected)
    repair = ctx.gateways.get(StorageRepair)

    def inspect() -> VerifyStorageResult:
        return _inspect(levels, ctx, uow, codes=codes)

    if cmd.dry_run:
        repair.prepare_preview(ctx, uow)
        return repair_report(inspect().findings, frozenset(), dry_run=True)
    return repair.apply(cmd, inspect, ctx, uow)


VERIFY_STORAGE: Final = QuerySpec(
    name="platform.verify_storage",
    dto=VerifyStorage,
    result=VerifyStorageResult,
    permission="admin.storage",
    scope_of=None,
    isolation=Isolation.REPEATABLE_READ,
    handler=handle_verify_storage,
)
REPAIR_STORAGE_SAFE: Final = CommandSpec(
    name="platform.repair_storage_safe",
    dto=RepairStorageSafe,
    result=RepairStorageSafeResult,
    permission="admin.storage",
    scope_of=None,
    isolation=Isolation.READ_COMMITTED,
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle_repair_storage_safe,
)
