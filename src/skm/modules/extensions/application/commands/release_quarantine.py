"""``extensions.release_quarantine`` (extensions §7.4): the owner decides; the row stays as history."""

from typing import Final

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import ResourceVersionId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access import public as access
from skm.modules.extensions.domain.events import ResourceReleased
from skm.modules.extensions.domain.keys import PackVersionId
from skm.modules.extensions.generated.commands import ReleaseQuarantine
from skm.modules.extensions.generated.results import ReleaseQuarantineResult
from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository

__all__ = ["SPEC", "handle"]

_MAX_STORED_REASON: Final = 1000  # ck_resource_quarantine__release_reason


def _require_instance_owner(ctx: CommandContext, uow: UnitOfWork) -> None:
    instance = ScopeId(uow.repo(ScopeRegistry).instance().id)
    held = access.effective_permissions(uow, ctx.actor, instance)
    if not access.role_permissions(access.Role.OWNER) <= held:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "only the instance owner releases a quarantine",
            details={"reason": "owner_required"},
        )


def handle(cmd: ReleaseQuarantine, ctx: CommandContext, uow: UnitOfWork) -> ReleaseQuarantineResult:
    _require_instance_owner(ctx, uow)
    if len(cmd.reason) > _MAX_STORED_REASON:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "the release reason is too long",
            details={"reason": "release_reason_too_long"},
        )
    version_id = ResourceVersionId(cmd.resource_version_id)
    version = uow.repo(ResourceRepository).get_version(version_id).version
    uow.repo(QuarantineRepository).release(
        version_id, by=ctx.actor.principal_id, reason=cmd.reason, at=ctx.clock.now()
    )
    pack_version = uow.repo(PackRepository).get_version(PackVersionId(version.pack_version_id))
    uow.record(
        ResourceReleased(
            pack_id=pack_version.pack_id,
            resource_version_id=version_id,
            kind=version.kind.value,
            key=version.key,
            released_by=ctx.actor.principal_id,
            reason=cmd.reason,
        )
    )
    return ReleaseQuarantineResult(resource_version_id=version_id, quarantined=False)


SPEC = CommandSpec(
    name="extensions.release_quarantine",
    dto=ReleaseQuarantine,
    result=ReleaseQuarantineResult,
    permission="ext.install",
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
