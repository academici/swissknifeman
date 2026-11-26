"""Release only the current holder; a stale release never frees a successor's slot."""

from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.application._worker_protocol import fenced_scope, lock_fenced_context
from skm.modules.execution.domain.ids import IntegrationSlotId
from skm.modules.execution.ports import IntegrationSlotRepository


class ReleaseIntegrationSlot(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:release-integration-slot:v1"


class ReleaseIntegrationSlotResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:release-integration-slot:v1"


def handle(cmd: ReleaseIntegrationSlot, ctx: Any, uow: UnitOfWork) -> ReleaseIntegrationSlotResult:
    fenced = lock_fenced_context(uow, ctx, cmd["claim"], allow_terminal=True)
    try:
        uow.repo(IntegrationSlotRepository).release(
            IntegrationSlotId(UUID(cmd["slot_id"])), fenced.attempt.id, cmd["fencing_token"]
        )
    except SkmError as error:
        if error.code not in {ErrorCode.LEASE_LOST, ErrorCode.NOT_FOUND}:
            raise
        return ReleaseIntegrationSlotResult(released=False, diagnostic=error.code.value)
    return ReleaseIntegrationSlotResult(released=True)


SPEC = CommandSpec(
    name="execution.release_integration_slot",
    dto=ReleaseIntegrationSlot,
    result=ReleaseIntegrationSlotResult,
    permission="worker.claim",
    scope_of=None,
    scope_resolver=fenced_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
)
