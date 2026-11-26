"""``extensions.quarantine_resource`` (extensions §7.3): a manual quarantine; a repeat changes nothing."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.ids import ResourceVersionId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.extensions.domain.events import ResourceQuarantined
from skm.modules.extensions.domain.keys import PackVersionId
from skm.modules.extensions.domain.quarantine import QuarantineEntry
from skm.modules.extensions.generated.commands import QuarantineResource
from skm.modules.extensions.generated.results import QuarantineResourceResult
from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: QuarantineResource, ctx: CommandContext, uow: UnitOfWork) -> QuarantineResourceResult:
    version_id = ResourceVersionId(cmd.resource_version_id)
    version = uow.repo(ResourceRepository).get_version(version_id).version
    quarantine = uow.repo(QuarantineRepository)
    if version_id not in quarantine.quarantined_ids([version_id]):
        quarantine.add(
            QuarantineEntry(
                version_id=version_id,
                reason=cmd.reason,
                report={},
                created_by=ctx.actor.principal_id,
                created_at=ctx.clock.now(),
            )
        )
        pack_version = uow.repo(PackRepository).get_version(PackVersionId(version.pack_version_id))
        uow.record(
            ResourceQuarantined(
                pack_id=pack_version.pack_id,
                resource_version_id=version_id,
                kind=version.kind.value,
                key=version.key,
                reason_kind="manual",
                reasons=(cmd.reason,),
            )
        )
    return QuarantineResourceResult(resource_version_id=version_id, quarantined=True)


SPEC = CommandSpec(
    name="extensions.quarantine_resource",
    dto=QuarantineResource,
    result=QuarantineResourceResult,
    permission="ext.install",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
