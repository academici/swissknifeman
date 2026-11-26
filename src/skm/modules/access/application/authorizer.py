"""``RbacAuthorizer``: the bus ``Authorizer`` of the access module (access §4.4, §4.6, §13).

Every call is an admission decision made from facts read now, inside the unit of work of the request. The
order is fixed:

1. the live credential check of §4.6: the principal record, the ``actor.grant.token_id`` row (usable at the
   trusted ``now``, the same principal, the binding the ``Actor`` claims) and the principal kind. A credential
   that is revoked, expired, foreign or owned by a disabled principal is ``UNAUTHENTICATED`` -- one code, one
   message -- and raises out of the pipeline; it is not a permission decision.
2. ``authz.decision`` (the pure ``decide`` table over memberships on the stored scope chain, the grant ceiling
   and the host facts) answers allowed or denied. A denial is returned as the bus ``AuthzDecision``; the bus
   rolls the unit of work back and writes the denied audit in its own short unit.

``Actor`` is an identity, never a cache of rights: neither step remembers anything between calls, so a right
lost between two requests is ``FORBIDDEN`` and a credential lost between them is ``UNAUTHENTICATED`` at the
next call, for commands, for queries without a permission of their own, for the receipt replay
and for the embedded client alike. ``now`` comes from the injected clock, never from a DTO or from the time
of the first authentication. Execution ownership is not decided here (§4.5).
"""

from skm.application_bus.context import AuthBasis, AuthBasisKind
from skm.application_bus.ports import AuthzDecision as BusDecision
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, Unauthenticated
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRecord
from skm.modules.access.application import authz
from skm.modules.access.domain.authorization import Allowed, Denied, is_system_actor
from skm.modules.access.domain.principal import Principal, PrincipalState
from skm.modules.access.domain.roles import SYSTEM_PERMISSIONS
from skm.modules.access.domain.token import ApiToken, TokenId, ensure_token_usable
from skm.modules.access.ports import PrincipalRepository, TokenRepository, WebSessionRepository

__all__ = ["RbacAuthorizer"]


def _unauthenticated() -> Unauthenticated:
    return Unauthenticated(ErrorCode.UNAUTHENTICATED, authz.UNAUTHENTICATED_MESSAGE)


def _binding_matches(actor: Actor, token: ApiToken) -> bool:
    """The grant the ``Actor`` carries is the binding stored in the token row (immutable per row)."""
    grant = actor.grant
    return grant is not None and (
        grant.kind == token.kind.value
        and grant.scope_id == token.scope_id
        and grant.permissions == token.permissions
        and grant.assignment_id == token.assignment_id
        and grant.step_id == token.step_id
        and grant.scope_grants == token.scope_grants
        and grant.assignment_scope_id == token.assignment_scope_id
        and grant.worker_id == token.worker_id
    )


class RbacAuthorizer:
    """Bus ``Authorizer`` over the access repositories of the request's unit of work."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def authorize(
        self,
        uow: UnitOfWork,
        actor: Actor,
        permission: str,
        chain: tuple[ScopeRecord, ...],
        *,
        basis: AuthBasis | None = None,
    ) -> BusDecision:
        principal = self._admitted(uow, actor, permission, basis=basis)
        verdict = authz.decision(uow, actor, permission, chain, principal=principal)
        if isinstance(verdict, Allowed):
            return BusDecision(allowed=True)
        assert isinstance(verdict, Denied)  # noqa: S101 -- AuthzDecision is Allowed | Denied
        return BusDecision(allowed=False, reason_code=authz.BUS_REASON[verdict.reason])

    def authorize_basis(
        self,
        uow: UnitOfWork,
        basis: AuthBasis,
        permission: str,
        chain: tuple[ScopeRecord, ...],
    ) -> BusDecision:
        """Authorize using the unified ``AuthBasis`` (verifies token, web session, or local_owner live)."""
        return self.authorize(uow, basis.actor, permission, chain, basis=basis)

    def admit(
        self,
        uow: UnitOfWork,
        actor: Actor,
        permission: str | None = None,
        *,
        basis: AuthBasis | None = None,
    ) -> None:
        """Access §4.6 for ``actor`` now: ``UNAUTHENTICATED`` unless principal and credential are live.

        The canonical ``SYSTEM_ACTOR`` asking for a system permission is decided by rows 1-2 of the table
        from the actor alone, so the instance can be initialised before the ``system`` row exists; every
        other request of it reads the stored principal like any actor.
        """
        self._admitted(uow, actor, permission, basis=basis)

    def admit_basis(
        self,
        uow: UnitOfWork,
        basis: AuthBasis,
        permission: str | None = None,
    ) -> None:
        """Access §4.6 for ``basis`` now: verifies principal and Bearer token / web session / local_owner."""
        self._admitted(uow, basis.actor, permission, basis=basis)

    def _admitted(
        self,
        uow: UnitOfWork,
        actor: Actor,
        permission: str | None,
        *,
        basis: AuthBasis | None = None,
    ) -> Principal | None:
        """``admit``, returning the principal record it read; ``None`` when the actor alone decided."""
        if basis is not None and basis.actor != actor:
            raise _unauthenticated()
        if (
            (basis is None or basis.kind is AuthBasisKind.SYSTEM)
            and permission in SYSTEM_PERMISSIONS
            and is_system_actor(actor)
        ):
            return None
        try:
            principal = uow.repo(PrincipalRepository).get(actor.principal_id)
        except NotFound:
            raise _unauthenticated() from None
        if principal.kind is not actor.kind:  # the kind is the record's, never a field of the caller
            raise _unauthenticated()
        if basis is not None:
            return self._admit_with_basis(uow, principal, basis)
        if actor.grant is None:
            if principal.state is not PrincipalState.ACTIVE:
                raise _unauthenticated()
            return principal
        return self._admit_token(uow, principal, actor)

    def _admit_with_basis(self, uow: UnitOfWork, principal: Principal, basis: AuthBasis) -> Principal:
        actor = basis.actor
        if basis.kind is AuthBasisKind.BEARER:
            if actor.grant is None or actor.grant.token_id != basis.token_id:
                raise _unauthenticated()
            return self._admit_token(uow, principal, actor)
        if basis.kind is AuthBasisKind.SESSION:
            if (
                actor.grant is not None
                or principal.kind is not PrincipalKind.HUMAN
                or principal.state is not PrincipalState.ACTIVE
                or basis.session_id is None
            ):
                raise _unauthenticated()
            session = uow.repo(WebSessionRepository).get(basis.session_id)
            if (
                session is None
                or session.principal_id != principal.id
                or not session.is_active(self._clock.now())
            ):
                raise _unauthenticated()
            return principal
        if basis.kind is AuthBasisKind.LOCAL_OWNER:
            if (
                actor.grant is not None
                or principal.kind is not PrincipalKind.HUMAN
                or principal.state is not PrincipalState.ACTIVE
            ):
                raise _unauthenticated()
            return principal
        # AuthBasisKind.SYSTEM
        if actor.grant is not None or principal.state is not PrincipalState.ACTIVE:
            raise _unauthenticated()
        return principal

    def _admit_token(self, uow: UnitOfWork, principal: Principal, actor: Actor) -> Principal:
        assert actor.grant is not None  # noqa: S101 -- callers check grant before invoking _admit_token
        try:
            token = uow.repo(TokenRepository).get(TokenId(actor.grant.token_id))
        except NotFound:
            raise _unauthenticated() from None
        ensure_token_usable(token, principal, self._clock.now())
        if not _binding_matches(actor, token):
            raise _unauthenticated()
        return principal
