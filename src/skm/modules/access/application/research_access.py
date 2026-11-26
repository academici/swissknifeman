"""Workspace classification ceilings from live memberships, never actor-cached roles."""

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.application.authorizer import RbacAuthorizer
from skm.modules.access.domain.roles import ROLE_CLASSIFICATION_CEILINGS, ROLE_RANK, Role
from skm.modules.access.ports import MembershipRepository


def workspace_ceiling(
    uow: UnitOfWork,
    actor: Actor,
    workspace_id: WorkspaceId,
    *,
    clock: Clock,
) -> str:
    RbacAuthorizer(clock).admit(uow, actor)
    if actor.kind is PrincipalKind.WORKER:
        raise Forbidden(ErrorCode.FORBIDDEN, "workers use the active run classification ceiling")
    chain = uow.repo(ScopeRegistry).ancestors(ScopeId(workspace_id))
    if not chain or chain[-1].kind is not ScopeKind.WORKSPACE:
        raise Forbidden(ErrorCode.FORBIDDEN, "workspace classification scope is unavailable")
    memberships = uow.repo(MembershipRepository).for_principal(actor.principal_id, [s.id for s in chain])
    roles = [Role(m.role) for m in memberships if m.role in ROLE_CLASSIFICATION_CEILINGS]
    if not roles:
        raise Forbidden(ErrorCode.FORBIDDEN, "a workspace role is required for research")
    return ROLE_CLASSIFICATION_CEILINGS[max(roles, key=ROLE_RANK.__getitem__)]
