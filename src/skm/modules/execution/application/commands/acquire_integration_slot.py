"""Fenced slot acquisition with durable target and run host pins."""

from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, error_for
from skm.kernel.ids import RepositoryId
from skm.kernel.outcomes import Waiting
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application._worker_protocol import fenced_scope, lock_fenced_context
from skm.modules.execution.ports import EnvironmentRepository, IntegrationSlotRepository


class AcquireIntegrationSlot(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:acquire-integration-slot:v1"


class AcquireIntegrationSlotResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:acquire-integration-slot:v1"
    __slots__ = ("waiting",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Generic receipts must not cache an expected wait as future slot authority.
        self.waiting = (
            Waiting(ErrorCode.SLOT_BUSY, "integration slot is busy")
            if self.get("outcome") == "waiting"
            else None
        )


def handle(cmd: AcquireIntegrationSlot, ctx: Any, uow: UnitOfWork) -> AcquireIntegrationSlotResult:
    fenced = lock_fenced_context(uow, ctx, cmd["claim"])
    if fenced.run.status.value != "running":
        raise error_for(ErrorCode.LEASE_LOST, "run is not active")
    repository_id, branch = RepositoryId(UUID(cmd["repository_id"])), cmd["target_branch"]
    if (
        not isinstance(branch, str)
        or not branch
        or branch.startswith(("-", "/"))
        or any(c in branch for c in ("..", "@{", "\\", " ", "\n", "\r", "\0", ":", "*", "?", "[", "~", "^"))
    ):
        raise error_for(ErrorCode.SCHEMA_INVALID, "invalid integration branch")
    environment = uow.repo(EnvironmentRepository).for_attempt(fenced.attempt.id)
    if environment is None or repository_id not in {b.repository_id for b in environment.baseline}:
        raise error_for(ErrorCode.INVALID_REFERENCE, "repository is not an attempt mount")
    slots = uow.repo(IntegrationSlotRepository)
    host = fenced.worker.host_id
    target_host, _ = slots.pin_target_host(repository_id, branch, host, fenced.now)
    run_host = slots.pin_host(fenced.run.id, repository_id, target_host, fenced.now)
    if target_host != host or run_host != host:
        raise error_for(ErrorCode.INTEGRATION_HOST_MISMATCH, "target and run must use their pinned host")
    slot = slots.acquire(repository_id, branch, fenced.attempt.id, host, fenced.now, fenced.lease.expires_at)
    if slot is None:
        return AcquireIntegrationSlotResult(
            outcome="waiting",
            code="SLOT_BUSY",
            retry_after_seconds=max(1, int(ctx.config.get("execution.integration.slot_poll_seconds") or 5)),
        )
    if slot.expires_at is None:
        # acquire stores the lease expiry it is given; a held slot without one is a repository defect
        raise InternalError(ErrorCode.INTERNAL_ERROR, "acquired integration slot has no expiry")
    return AcquireIntegrationSlotResult(
        slot_id=str(slot.id), fencing_token=slot.fencing_token, expires_at=slot.expires_at.isoformat()
    )


SPEC = CommandSpec(
    name="execution.acquire_integration_slot",
    dto=AcquireIntegrationSlot,
    result=AcquireIntegrationSlotResult,
    permission="worker.claim",
    scope_of=None,
    scope_resolver=fenced_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
)
