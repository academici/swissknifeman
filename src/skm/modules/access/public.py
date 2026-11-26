"""Facade of the access module (access §13): the only surface other modules and entrypoints import.

Functions run inside the caller's unit of work. ``RbacAuthorizer`` is the bus ``Authorizer`` of the
production composition; the DTOs, results and views are the generated contract of the commands and queries,
which the surfaces use through ``SkmClient``.
"""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.errors import NotFound
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.access.application import authz
from skm.modules.access.application import facade as _facade
from skm.modules.access.application import research_access as _research_access
from skm.modules.access.application.authentication import authenticate_token as _authenticate_token
from skm.modules.access.application.authorizer import RbacAuthorizer
from skm.modules.access.application.facade import issue_bound_worker_token
from skm.modules.access.application.pairing import (
    consume_pairing_token,
    issue_paired_personal_token,
    issue_pairing_token,
    lock_pairing_token,
    prepare_worker_replacement,
    revoke_all_pairing_tokens,
)
from skm.modules.access.application.passwords import authenticate_local_owner_password
from skm.modules.access.application.sessions import (
    SESSION_SECRET_PREFIX,
    authenticate_web_session,
    create_web_session,
    resolve_local_owner,
    revoke_all_web_sessions,
    revoke_web_session,
)
from skm.modules.access.domain.authorization import Allowed, AuthzDecision, Denied
from skm.modules.access.domain.pairing import PairingResult, PairingToken
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.roles import role_permissions as _role_permissions
from skm.modules.access.domain.session import WebSession
from skm.modules.access.domain.token import TokenGrant, TokenId, TokenKind, TokenSecret, token_is_usable
from skm.modules.access.domain.token import generate_secret as _generate_secret
from skm.modules.access.domain.token import parse_secret as parse_secret
from skm.modules.access.generated.commands import (
    CreatePrincipal,
    CreateToken,
    DisablePrincipal,
    GrantMembership,
    RevokeMembership,
    RevokeToken,
    RotateToken,
)
from skm.modules.access.generated.queries import (
    GetPrincipal,
    ListMemberships,
    ListPrincipals,
    ListTokens,
    WhoAmI,
)
from skm.modules.access.generated.results import (
    CreatePrincipalResult,
    CreateTokenResult,
    DisablePrincipalResult,
    GrantMembershipResult,
    RevokeMembershipResult,
    RevokeTokenResult,
    RotateTokenResult,
)
from skm.modules.access.generated.settings import AccessSettings
from skm.modules.access.generated.views import (
    GetPrincipalView,
    ListMembershipsView,
    ListPrincipalsView,
    ListTokensView,
    MembershipView,
    PrincipalSummaryView,
    PrincipalView,
    TokenSummaryView,
    WhoAmIView,
)
from skm.modules.access.permissions import PERMISSIONS
from skm.modules.access.ports import TokenPepperSource, TokenRepository

__all__ = [
    "PERMISSIONS",
    "SESSION_SECRET_PREFIX",
    "SYSTEM_ACTOR",
    "SYSTEM_PRINCIPAL_ID",
    "AccessSettings",
    "Allowed",
    "AuthzDecision",
    "CreatePrincipal",
    "CreatePrincipalResult",
    "CreateToken",
    "CreateTokenResult",
    "Denied",
    "DisablePrincipal",
    "DisablePrincipalResult",
    "GetPrincipal",
    "GetPrincipalView",
    "GrantMembership",
    "GrantMembershipResult",
    "ListMemberships",
    "ListMembershipsView",
    "ListPrincipals",
    "ListPrincipalsView",
    "ListTokens",
    "ListTokensView",
    "MembershipView",
    "PairingResult",
    "PairingToken",
    "PrincipalSummaryView",
    "PrincipalView",
    "RbacAuthorizer",
    "RevokeMembership",
    "RevokeMembershipResult",
    "RevokeToken",
    "RevokeTokenResult",
    "Role",
    "RotateToken",
    "RotateTokenResult",
    "TokenGrant",
    "TokenId",
    "TokenKind",
    "TokenPepperSource",
    "TokenSecret",
    "TokenSummaryView",
    "WebSession",
    "WhoAmI",
    "WhoAmIView",
    "authenticate_local_owner_password",
    "authenticate_token",
    "authenticate_web_session",
    "consume_pairing_token",
    "create_web_session",
    "create_worker_principal",
    "effective_permissions",
    "extend_assignment_tokens",
    "generate_secret",
    "grant_initial_membership",
    "issue_assignment_token",
    "issue_bound_worker_token",
    "issue_paired_personal_token",
    "issue_pairing_token",
    "lock_pairing_token",
    "parse_secret",
    "prepare_worker_replacement",
    "resolve_local_owner",
    "revoke_all_pairing_tokens",
    "revoke_all_web_sessions",
    "revoke_assignment_tokens",
    "revoke_principal_tokens",
    "revoke_web_session",
    "role_permissions",
    "worker_credential_current",
    "workspace_classification_ceiling",
]


def authenticate_token(uow: UnitOfWork, secret_text: str, *, pepper: bytes, now: datetime) -> Actor:
    """``UNAUTHENTICATED`` (one code, one message) unless the secret names a usable token of an active
    principal.

    ``Actor.grant`` carries kind, scope, permissions, ``assignment_id``, ``step_id`` and ``scope_ancestors``.
    """
    return _authenticate_token(uow, secret_text, pepper=pepper, now=now)


def worker_credential_current(
    uow: UnitOfWork,
    token_id: UUID,
    worker_id: UUID,
    *,
    now: datetime | Callable[[], datetime],
    lock: bool = False,
) -> bool:
    """Check current worker authority, optionally serializing the caller's write with rotation.

    Supply a clock reader when validity must be sampled after waiting for the token lock.
    """
    tokens = uow.repo(TokenRepository)
    try:
        token = tokens.get_for_update(TokenId(token_id)) if lock else tokens.get(TokenId(token_id))
    except NotFound:
        return False
    return (
        token.kind is TokenKind.WORKER
        and token.worker_id == worker_id
        and token.superseded_by is None
        and token_is_usable(token, now() if callable(now) else now)
    )


def effective_permissions(uow: UnitOfWork, actor: Actor, scope_id: ScopeId) -> frozenset[str]:
    """Permissions ``actor`` holds on ``scope_id`` now: roles on the chain, narrowed by its current grant."""
    return authz.effective(uow, actor, authz.chain_of(uow, scope_id))


def role_permissions(role: Role) -> frozenset[str]:
    return _role_permissions(Role(role))


def workspace_classification_ceiling(
    uow: UnitOfWork,
    actor: Actor,
    workspace_id: WorkspaceId,
    *,
    clock: Clock,
) -> str:
    """Current workspace role ceiling, independent of DTO ceilings and runtime defaults."""
    return _research_access.workspace_ceiling(uow, actor, workspace_id, clock=clock)


def create_worker_principal(  # noqa: PLR0913 -- signature fixed by access §13
    uow: UnitOfWork,
    *,
    display_name: str,
    workspace_scope_id: ScopeId,
    issuer: Actor,
    worker_id: UUID,
    host_scope_id: ScopeId | None = None,
    token_name: str,
    pepper: bytes,
    entropy: Callable[[int], bytes],
    now: datetime,
    settings: AccessSettings | None = None,
) -> tuple[PrincipalId, TokenId, str]:
    """For ``workspace.register_worker``: a worker principal, its membership and its token (secret once).

    ``settings`` is the caller's effective ``access`` section; without it the schema defaults apply.
    """
    return _facade.create_worker_principal(
        uow,
        display_name=display_name,
        workspace_scope_id=workspace_scope_id,
        issuer=issuer,
        worker_id=worker_id,
        host_scope_id=host_scope_id,
        token_name=token_name,
        pepper=pepper,
        entropy=entropy,
        now=now,
        settings=settings,
    )


def issue_assignment_token(  # noqa: PLR0913 -- signature fixed by access §13
    uow: UnitOfWork,
    *,
    worker: Actor,
    secret: TokenSecret,
    run_scope_id: ScopeId,
    assignment_id: UUID,
    step_id: UUID,
    expires_at: datetime,
    permissions: frozenset[str],
    pepper: bytes,
    now: datetime,
) -> TokenSummaryView:
    """For ``execution.begin_stage``: the token of one step.

    Repeating the same secret for the same binding is a no-op; another step never takes over an old secret
    (``FORBIDDEN``); a second secret for a bound step is ``ALREADY_EXISTS``; revoked and expired tokens are
    not revived.
    """
    return _facade.issue_assignment_token(
        uow,
        worker=worker,
        secret=secret,
        run_scope_id=run_scope_id,
        assignment_id=assignment_id,
        step_id=step_id,
        expires_at=expires_at,
        permissions=permissions,
        pepper=pepper,
        now=now,
    )


def extend_assignment_tokens(
    uow: UnitOfWork, *, assignment_id: UUID, expires_at: datetime, now: datetime
) -> int:
    """For ``execution.renew_lease``: lengthen the usable tokens of the assignment; dead ones stay dead."""
    return _facade.extend_assignment_tokens(uow, assignment_id=assignment_id, expires_at=expires_at, now=now)


def revoke_assignment_tokens(
    uow: UnitOfWork, *, assignment_id: UUID, by: PrincipalId, now: datetime, step_id: UUID | None = None
) -> int:
    """Revoke the tokens of an assignment, or only the binding of ``step_id``; repeating it is a no-op."""
    return _facade.revoke_assignment_tokens(uow, assignment_id=assignment_id, by=by, now=now, step_id=step_id)


def generate_secret(entropy: Callable[[int], bytes]) -> TokenSecret:
    """Pure; the host side of a worker draws the secret of a step here."""
    return _generate_secret(entropy)


def grant_initial_membership(
    uow: UnitOfWork, *, scope_id: ScopeId, principal_id: PrincipalId, role: Role, now: datetime
) -> None:
    """For handlers that create a scope: the creator gets ``role`` without ``can_grant``."""
    _facade.grant_initial_membership(uow, scope_id=scope_id, principal_id=principal_id, role=role, now=now)


def revoke_principal_tokens(
    uow: UnitOfWork, principal_id: PrincipalId, *, by: PrincipalId, now: datetime, disable: bool
) -> int:
    """Revoke every usable token of the principal; ``disable`` also disables it. Returns the count."""
    return _facade.revoke_principal_tokens(uow, principal_id, by=by, now=now, disable=disable)


SYSTEM_ACTOR = Actor(principal_id=SYSTEM_PRINCIPAL_ID, kind=PrincipalKind.SERVICE, display_name="system")
