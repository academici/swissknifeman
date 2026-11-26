"""Scriptable ``Authorizer`` for bus unit tests.

The production one is ``access.public.RbacAuthorizer``.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from skm.application_bus.ports import AuthzDecision
from skm.kernel.actor import Actor
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRecord

__all__ = ["AuthzCall", "FakeAuthorizer"]


@dataclass(frozen=True, slots=True)
class AuthzCall:
    principal_id: UUID
    permission: str
    scope_id: UUID
    readonly: bool  # the UoW the decision was read in


class FakeAuthorizer:
    """Allows ``allowed`` permissions (``None``: all) and refuses the rest with ``reason_code``.

    ``calls`` records every decision so a test can prove that authorization ran, in which UoW and how often.
    """

    def __init__(
        self, allowed: Iterable[str] | None = None, *, reason_code: str = "ROLE_LACKS_PERMISSION"
    ) -> None:
        self.allowed: set[str] | None = None if allowed is None else set(allowed)
        self.reason_code = reason_code
        self.calls: list[AuthzCall] = []

    def authorize(
        self,
        uow: UnitOfWork,
        actor: Actor,
        permission: str,
        chain: tuple[ScopeRecord, ...],
    ) -> AuthzDecision:
        self.calls.append(AuthzCall(actor.principal_id, permission, chain[-1].id, uow.readonly))
        if self.allowed is None or permission in self.allowed:
            return AuthzDecision(allowed=True)
        return AuthzDecision(allowed=False, reason_code=self.reason_code)

    def deny_all(self) -> None:
        self.allowed = set()

    def allow_all(self) -> None:
        self.allowed = None
