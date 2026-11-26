"""Declarative contract; behavior belongs to the owning implementation leaf."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from skm.kernel.actor import PrincipalKind
from skm.kernel.gateways import control_plane_gateway
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.pagination import Page
from skm.kernel.ports_uow import repository_port

from .domain.identity import PrincipalIdentity
from .domain.membership import Membership
from .domain.pairing import PairingResult, PairingToken
from .domain.principal import Principal
from .domain.session import WebSession
from .domain.token import ApiToken, TokenId, TokenKind

__all__ = [
    "IdentityRepository",
    "MembershipRepository",
    "PairingRepository",
    "PrincipalRepository",
    "TokenPepperSource",
    "TokenRepository",
    "WebSessionRepository",
    "WorkerHostLookup",
]


@repository_port
class PrincipalRepository(Protocol):
    def get(self, principal_id: PrincipalId) -> Principal: ...  # NotFound(kind="principal")
    def add(self, principal: Principal) -> None: ...
    def save(self, principal: Principal, *, expected_version: int) -> None: ...  # Conflict(VERSION_CONFLICT)
    def list(self, *, kind: PrincipalKind | None, after: str | None, limit: int) -> Page[Principal]: ...
    def password_hash(self, principal_id: PrincipalId) -> bytes | None: ...
    def set_first_password(self, principal_id: PrincipalId, password_hash: bytes) -> bool: ...


@repository_port
class IdentityRepository(Protocol):
    def find(self, issuer: str, subject: str) -> PrincipalIdentity | None: ...
    def add(self, identity: PrincipalIdentity) -> None: ...  # Conflict(ALREADY_EXISTS)
    def for_principal(self, principal_id: PrincipalId) -> tuple[PrincipalIdentity, ...]: ...


@repository_port
class TokenRepository(Protocol):
    def get(self, token_id: TokenId) -> ApiToken: ...
    def get_for_update(self, token_id: TokenId) -> ApiToken: ...
    def find_by_prefix(self, prefix: str) -> ApiToken | None: ...
    def for_assignment(
        self, assignment_id: UUID
    ) -> tuple[ApiToken, ...]: ...  # активные токены kind=assignment
    def add(
        self, token: ApiToken
    ) -> None: ...  # Conflict(ALREADY_EXISTS, details.field = "prefix" | "name"): prefix or active token name
    def save(
        self, token: ApiToken
    ) -> (
        None
    ): ...  # отзыв, ротация и продление assignment (get_for_update); assignment_id/step_id неизменяемы
    def touch(
        self, token_id: TokenId, at: datetime
    ) -> None: ...  # last_used_at; adapter throttles updates to once per 60 seconds
    def list_for(
        self,
        principal_id: PrincipalId | None,
        *,
        include_inactive: bool,
        after: str | None,
        limit: int,
        kind: TokenKind | None = None,
    ) -> Page[ApiToken]: ...


@repository_port
class MembershipRepository(Protocol):
    def for_principal(
        self, principal_id: PrincipalId, scope_ids: Sequence[ScopeId]
    ) -> tuple[Membership, ...]: ...
    def get(self, scope_id: ScopeId, principal_id: PrincipalId) -> Membership | None: ...
    def upsert(self, membership: Membership) -> None: ...  # PK (scope_id, principal_id); смена роли — замена
    def delete(self, scope_id: ScopeId, principal_id: PrincipalId) -> None: ...
    def count_active_owners(self, scope_id: ScopeId) -> int: ...  # join principals.state='active'
    def has_workspace_membership(
        self, principal_id: PrincipalId
    ) -> bool: ...  # EXISTS membership на scope kind=workspace (строка 6b §4.4)
    def list(
        self, *, scope_id: ScopeId | None, principal_id: PrincipalId | None, after: str | None, limit: int
    ) -> Page[Membership]: ...


@control_plane_gateway
class TokenPepperSource(Protocol):
    def pepper(
        self,
    ) -> bytes: ...  # at least 32 bytes; the adapter reads secret://file/<state_dir>/secrets/token-pepper


@repository_port
class WorkerHostLookup(Protocol):
    """Host and workspace scopes of non-retired workers (access §4.4, §6).

    The workspace adapter owns the query, preserving the workspace -> access dependency.
    RbacAuthorizer treats a missing registration as an empty set.
    """

    def host_ids(self, principal_id: PrincipalId) -> frozenset[ScopeId]: ...
    def workspace_scope_id(self, principal_id: PrincipalId) -> ScopeId | None: ...


@repository_port
class PairingRepository(Protocol):
    def add(self, pairing: PairingToken) -> None: ...
    def get_for_update(self, pairing_id: UUID) -> PairingToken | None: ...
    def consume(self, pairing_id: UUID, result: PairingResult, now: datetime) -> None: ...
    def revoke(self, pairing_id: UUID, now: datetime) -> None: ...
    def revoke_all(self, now: datetime) -> int: ...


@repository_port
class WebSessionRepository(Protocol):
    def add(self, session: WebSession) -> None: ...
    def get(self, session_id: UUID) -> WebSession | None: ...
    def find_by_hash(self, secret_hash: bytes) -> WebSession | None: ...
    def revoke(self, session_id: UUID, now: datetime) -> bool: ...
    def revoke_for_principal(self, principal_id: PrincipalId, now: datetime) -> int: ...
    def revoke_all(self, now: datetime) -> int: ...
