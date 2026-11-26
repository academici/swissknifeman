"""``access.disable_principal`` (access §7.2): disabling revokes every usable token of the principal."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import PrincipalId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRef, ScopeRegistry
from skm.kernel.versions import ExpectedVersion, check_expected
from skm.modules.access.application import events
from skm.modules.access.application.facade import revoke_principal_tokens
from skm.modules.access.domain.membership import last_owner_guard
from skm.modules.access.domain.principal import disable
from skm.modules.access.domain.roles import Role
from skm.modules.access.generated.commands import DisablePrincipal
from skm.modules.access.generated.results import DisablePrincipalResult
from skm.modules.access.ports import MembershipRepository, PrincipalRepository

__all__ = ["SPEC", "handle"]


def handle(cmd: DisablePrincipal, ctx: CommandContext, uow: UnitOfWork) -> DisablePrincipalResult:
    actor, now = ctx.actor, ctx.clock.now()
    principals = uow.repo(PrincipalRepository)
    principal = principals.get(PrincipalId(cmd.principal_id))
    check_expected(principal.row_version, ExpectedVersion(cmd.expected_row_version))
    if principal.id == actor.principal_id:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "a principal cannot disable itself",
            details={"reason": "self"},
        )
    changed = disable(principal)
    if changed is principal:  # already disabled: no write, no event
        return DisablePrincipalResult(principal_id=principal.id, row_version=principal.row_version)
    instance = uow.repo(ScopeRegistry).instance()
    memberships = uow.repo(MembershipRepository)
    held = memberships.get(instance.id, principal.id)
    if held is not None and held.role is Role.OWNER:  # the instance keeps one active owner
        last_owner_guard(
            ScopeRef(instance.kind, instance.id), memberships.count_active_owners(instance.id) - 1
        )
    principals.save(changed, expected_version=principal.row_version)
    revoke_principal_tokens(uow, principal.id, by=actor.principal_id, now=now, disable=False)
    uow.record(events.PrincipalDisabled(principal_id=principal.id, reason=cmd.reason))
    return DisablePrincipalResult(principal_id=changed.id, row_version=changed.row_version)


SPEC = CommandSpec(
    name="access.disable_principal",
    dto=DisablePrincipal,
    result=DisablePrincipalResult,
    permission="principal.manage",
    scope_of=None,
    handler=handle,
)
