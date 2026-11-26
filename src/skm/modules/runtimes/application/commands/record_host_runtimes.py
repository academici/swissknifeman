"""``runtimes.record_host_runtimes`` (runtimes §7.1): upsert observed runtimes and remove missing ones."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import HostId, ScopeId, WorkerId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access import public as access
from skm.modules.runtimes.application.host_availability import record_host_offers, record_worker_snapshot
from skm.modules.runtimes.domain.events import HostRuntimeRecordedItem, HostRuntimesRecorded
from skm.modules.runtimes.domain.installation import (
    AuthState,
    RuntimeInstallation,
    diff_installations,
    public_installation_details,
    public_runtime_version,
)
from skm.modules.runtimes.generated.commands import RecordHostRuntimes
from skm.modules.runtimes.generated.results import (
    RecordHostRuntimesResult,
    RecordHostRuntimesResultRuntimesItem,
)
from skm.modules.runtimes.ports import (
    CapabilityCatalog,
    HostModelAvailabilityRepository,
    HostRuntimeRepository,
)
from skm.modules.workspace import public as workspace

__all__ = ["SENTINEL_DETECTED_AT", "SPEC", "handle"]

# Host operations lack a clock by purity rules; when an adapter's detect() fails before producing a timestamp,
# it supplies SENTINEL_DETECTED_AT and the bus handler stamps ctx.clock.now().
SENTINEL_DETECTED_AT: Final = datetime(1970, 1, 1, tzinfo=UTC)


def _publisher(uow: UnitOfWork, ctx: CommandContext, host_id: HostId) -> workspace.WorkerView | None:
    if ctx.actor.kind is not PrincipalKind.WORKER:
        return None
    worker = workspace.worker_for_principal(uow, ctx.actor.principal_id)
    grant = ctx.actor.grant
    if (
        worker is None
        or worker.host_id != host_id
        or worker.state == "retired"
        or grant is None
        or grant.kind != "worker"
        or grant.worker_id != worker.worker_id
        or "worker.claim" not in access.effective_permissions(uow, ctx.actor, ScopeId(worker.workspace_id))
    ):
        raise Forbidden(ErrorCode.FORBIDDEN, "Worker publication requires its current registration")
    return worker


def _replay_guard(cmd: RecordHostRuntimes, ctx: CommandContext, uow: UnitOfWork) -> None:
    worker = _publisher(uow, ctx, HostId(cmd.host_id))
    grant = ctx.actor.grant
    if worker is not None and (
        grant is None
        or not access.worker_credential_current(uow, grant.token_id, worker.worker_id, now=ctx.clock.now())
    ):
        raise Forbidden(ErrorCode.FORBIDDEN, "Worker credential cannot replay current offers")


def handle(cmd: RecordHostRuntimes, ctx: CommandContext, uow: UnitOfWork) -> RecordHostRuntimesResult:
    host_id = HostId(cmd.host_id)
    workspace.get_host(uow, host_id)

    worker = _publisher(uow, ctx, host_id)
    grant = ctx.actor.grant
    if worker is None and (cmd.refresh_model_offers or cmd.model_offers_observed_at is not None):
        raise Forbidden(ErrorCode.FORBIDDEN, "Only a registered worker publishes a full model snapshot")

    registered = ctx.gateways.get(CapabilityCatalog).registered()
    now = ctx.clock.now()
    seen: set[str] = set()
    observed: list[RuntimeInstallation] = []

    for item in cmd.installations:
        if item.runtime_id not in registered:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"unknown runtime {item.runtime_id!r}",
                details={"runtime_id": item.runtime_id, "reason": "unknown_runtime"},
            )
        if item.runtime_id in seen:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"duplicate runtime {item.runtime_id!r} in installations",
                details={"runtime_id": item.runtime_id, "reason": "duplicate_runtime"},
            )
        seen.add(item.runtime_id)
        detected_at = now if item.detected_at == SENTINEL_DETECTED_AT else item.detected_at
        try:
            installation = RuntimeInstallation(
                host_id=host_id,
                runtime_id=item.runtime_id,
                version=item.version if worker is None else public_runtime_version(item.version),
                binary_locator=item.binary_locator if worker is None else None,
                auth_state=AuthState(item.auth_state),
                detected_at=detected_at,
                details=dict(item.details) if worker is None else public_installation_details(item.details),
            )
        except (TypeError, ValueError) as exc:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"invalid runtime installation for {item.runtime_id!r}: {exc}",
                details={"runtime_id": item.runtime_id},
            ) from exc
        observed.append(installation)

    if worker is None:
        repo = uow.repo(HostRuntimeRepository)
        diff = diff_installations(repo.list_for_host(host_id), observed)
        for installation in diff.upserted:
            repo.upsert(installation)
        if diff.removed:
            repo.remove_missing(host_id, frozenset(item.runtime_id for item in observed))
        record_host_offers(uow, cmd, ctx.config, observed, now)
    elif grant is not None:
        worker_id = WorkerId(worker.worker_id)
        previous = uow.repo(HostModelAvailabilityRepository).worker_snapshot(worker_id)
        diff = diff_installations(() if previous is None else previous.installations, observed)
        record_worker_snapshot(
            uow,
            ctx,
            cmd,
            observed,
            worker_id=worker_id,
            worker_runtimes=frozenset(worker.capabilities.runtimes),
            publisher_id=grant.token_id,
            now=now,
        )
    else:
        raise Forbidden(ErrorCode.FORBIDDEN, "Worker publication requires its current registration")

    changed_ids = {item.runtime_id for item in diff.upserted}
    if diff.has_changes:
        uow.record(
            HostRuntimesRecorded(
                host_id=host_id,
                runtimes=tuple(
                    HostRuntimeRecordedItem(
                        runtime_id=item.runtime_id,
                        version=item.version if worker is None else public_runtime_version(item.version),
                        auth_state=item.auth_state,
                    )
                    for item in observed
                ),
                removed=diff.removed,
            )
        )

    return RecordHostRuntimesResult(
        host_id=host_id,
        runtimes=tuple(
            RecordHostRuntimesResultRuntimesItem(
                runtime_id=item.runtime_id,
                version=item.version if worker is None else public_runtime_version(item.version),
                auth_state=item.auth_state.value,
                changed=item.runtime_id in changed_ids,
            )
            for item in observed
        ),
        removed=diff.removed,
    )


SPEC = CommandSpec(
    name="runtimes.record_host_runtimes",
    dto=RecordHostRuntimes,
    result=RecordHostRuntimesResult,
    permission="runtime.manage",
    scope_of=lambda cmd: ScopeRef(ScopeKind.HOST, ScopeId(cmd.host_id)),
    allowed_kinds=frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE, PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
    replay_guard=_replay_guard,
)
