"""``access.revoke_membership`` (access §7.6): removing an owner never leaves the instance without one."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRef
from skm.modules.access.application import authz, events
from skm.modules.access.application.scopes import scope_by_id
from skm.modules.access.domain.membership import can_grant, last_owner_guard
from skm.modules.access.domain.principal import PrincipalState
from skm.modules.access.domain.roles import Role
from skm.modules.access.generated.commands import RevokeMembership
from skm.modules.access.generated.results import RevokeMembershipResult
from skm.modules.access.ports import MembershipRepository, PrincipalRepository

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(cmd: RevokeMembership) -> ScopeRef | None:
    return scope_by_id(cmd.scope_id)


def handle(cmd: RevokeMembership, ctx: CommandContext, uow: UnitOfWork) -> RevokeMembershipResult:
    actor = ctx.actor
    chain = authz.chain_of(uow, ScopeId(cmd.scope_id))
    scope = chain[-1]
    principal_id = PrincipalId(cmd.principal_id)
    memberships = uow.repo(MembershipRepository)
    held = memberships.get(scope.id, principal_id)
    if held is None:  # nothing to remove: no event
        return RevokeMembershipResult(scope_id=scope.id, principal_id=principal_id, removed=False)
    if not can_grant(authz.effective(uow, actor, chain), held.role, scope.kind):  # no escalation in reverse
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "a membership above the revoker's own rights cannot be removed",
            details={
                "permission": "membership.manage",
                "scope_id": str(scope.id),
                "reason": "role_escalation",
            },
        )
    if held.role is Role.OWNER:
        member = uow.repo(PrincipalRepository).get(principal_id)
        removed_active = 1 if member.state is PrincipalState.ACTIVE else 0
        last_owner_guard(
            ScopeRef(scope.kind, scope.id), memberships.count_active_owners(scope.id) - removed_active
        )
    memberships.delete(scope.id, principal_id)
    uow.record(
        events.MembershipRevoked(
            scope_id=scope.id,
            principal_id=principal_id,
            role=held.role,
            workspace_id=authz.workspace_id_of(chain),
        )
    )
    return RevokeMembershipResult(scope_id=scope.id, principal_id=principal_id, removed=True)


SPEC = CommandSpec(
    name="access.revoke_membership",
    dto=RevokeMembership,
    result=RevokeMembershipResult,
    permission="membership.manage",
    scope_of=scope_of,
    handler=handle,
)
