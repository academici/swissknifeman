"""``access.grant_membership`` (access §7.5): no escalation, a workspace first, one active owner kept."""

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.application import authz, events
from skm.modules.access.application.scopes import scope_by_id
from skm.modules.access.domain.membership import Membership, can_grant, last_owner_guard
from skm.modules.access.domain.principal import PrincipalState
from skm.modules.access.domain.roles import Role
from skm.modules.access.generated.commands import GrantMembership
from skm.modules.access.generated.results import GrantMembershipResult
from skm.modules.access.generated.results import Role as ResultRole
from skm.modules.access.ports import MembershipRepository, PrincipalRepository

__all__ = ["SPEC", "handle", "scope_of"]

_NEEDS_WORKSPACE = frozenset({ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN})
_WORKSPACE_ROLED = frozenset({PrincipalKind.HUMAN, PrincipalKind.SERVICE})


def scope_of(cmd: GrantMembership) -> ScopeRef | None:
    return scope_by_id(cmd.scope_id)


def handle(cmd: GrantMembership, ctx: CommandContext, uow: UnitOfWork) -> GrantMembershipResult:
    actor, now = ctx.actor, ctx.clock.now()
    chain = authz.chain_of(uow, ScopeId(cmd.scope_id))  # NOT_FOUND for an unknown scope
    scope = chain[-1]
    role = Role(cmd.role.value)
    principal = uow.repo(PrincipalRepository).get(PrincipalId(cmd.principal_id))
    if principal.state is not PrincipalState.ACTIVE:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "the principal is disabled",
            details={"reason": "principal_disabled"},
        )
    if not can_grant(authz.effective(uow, actor, chain), role, scope.kind):
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "a role cannot be granted beyond the granter's own rights",
            details={
                "permission": "membership.manage",
                "scope_id": str(scope.id),
                "reason": "role_escalation",
            },
        )
    memberships = uow.repo(MembershipRepository)
    if scope.kind in _NEEDS_WORKSPACE and principal.kind in _WORKSPACE_ROLED:
        workspace = next(record for record in reversed(chain) if record.kind is ScopeKind.WORKSPACE)
        if memberships.get(workspace.id, principal.id) is None:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "the principal needs a membership of the workspace first",
                details={"reason": "workspace_membership_required"},
            )
    existing = memberships.get(scope.id, principal.id)
    if existing is not None and existing.role is role:  # same role: nothing changes
        return GrantMembershipResult(
            scope_id=scope.id, principal_id=principal.id, role=ResultRole(role.value)
        )
    if existing is not None and existing.role is Role.OWNER:  # a demotion removes an owner of the instance
        last_owner_guard(ScopeRef(scope.kind, scope.id), memberships.count_active_owners(scope.id) - 1)
    memberships.upsert(
        Membership(
            scope_id=scope.id,
            principal_id=principal.id,
            role=role,
            granted_by=actor.principal_id,
            granted_at=now,
        )
    )
    uow.record(
        events.MembershipGranted(
            scope_id=scope.id,
            principal_id=principal.id,
            role=role,
            previous_role=None if existing is None else existing.role,
            workspace_id=authz.workspace_id_of(chain),
        )
    )
    return GrantMembershipResult(scope_id=scope.id, principal_id=principal.id, role=ResultRole(role.value))


SPEC = CommandSpec(
    name="access.grant_membership",
    dto=GrantMembership,
    result=GrantMembershipResult,
    permission="membership.manage",
    scope_of=scope_of,
    handler=handle,
)
