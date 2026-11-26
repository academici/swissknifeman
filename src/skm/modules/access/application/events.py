"""Domain events of the access module (access §9).

Every event belongs to the ``principal`` stream of the affected principal. ``workspace_id`` is the
workspace of the scope the event is about (``None`` for the instance and for principal-level events).
Payloads come from the generated event DTOs and never carry a secret, a hash or a pepper
(``domain.events.SECRET_FIELD_NAMES``).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, override
from uuid import UUID

from skm.kernel.actor import PrincipalKind
from skm.kernel.events import DomainEvent
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.access.domain import events as names
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import TokenId, TokenKind
from skm.modules.access.generated import events as generated

__all__ = [
    "MembershipGranted",
    "MembershipRevoked",
    "PrincipalCreated",
    "PrincipalDisabled",
    "TokenCreated",
    "TokenRevoked",
    "TokenRotated",
]


@dataclass(frozen=True, slots=True)
class PrincipalCreated(DomainEvent):
    event_type: ClassVar[str] = names.PRINCIPAL_CREATED
    stream_kind: ClassVar[str] = names.EVENT_STREAM_KIND

    principal_id: PrincipalId
    kind: PrincipalKind
    display_name: str

    @override
    def stream_id(self) -> UUID:
        return self.principal_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return None

    @override
    def payload(self) -> JsonObject:
        return generated.PrincipalCreated(
            principal_id=self.principal_id,
            kind=generated.PrincipalKind(self.kind.value),
            display_name=self.display_name,
        ).to_json()


@dataclass(frozen=True, slots=True)
class PrincipalDisabled(DomainEvent):
    event_type: ClassVar[str] = names.PRINCIPAL_DISABLED
    stream_kind: ClassVar[str] = names.EVENT_STREAM_KIND

    principal_id: PrincipalId
    reason: str

    @override
    def stream_id(self) -> UUID:
        return self.principal_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return None

    @override
    def payload(self) -> JsonObject:
        return generated.PrincipalDisabled(principal_id=self.principal_id, reason=self.reason).to_json()


@dataclass(frozen=True, slots=True)
class TokenCreated(DomainEvent):
    event_type: ClassVar[str] = names.TOKEN_CREATED
    stream_kind: ClassVar[str] = names.EVENT_STREAM_KIND

    token_id: TokenId
    principal_id: PrincipalId
    kind: TokenKind
    name: str
    prefix: str
    scope_id: ScopeId | None
    expires_at: datetime | None
    workspace_id: WorkspaceId | None

    @override
    def stream_id(self) -> UUID:
        return self.principal_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.TokenCreatedPayload(
            token_id=self.token_id,
            principal_id=self.principal_id,
            kind=generated.TokenKind(self.kind.value),
            name=self.name,
            prefix=self.prefix,
            scope_id=self.scope_id,
            expires_at=self.expires_at,
        ).to_json()


@dataclass(frozen=True, slots=True)
class TokenRotated(DomainEvent):
    event_type: ClassVar[str] = names.TOKEN_ROTATED
    stream_kind: ClassVar[str] = names.EVENT_STREAM_KIND

    token_id: TokenId
    previous_token_id: TokenId
    principal_id: PrincipalId
    kind: TokenKind
    expires_at: datetime | None
    previous_expires_at: datetime | None
    workspace_id: WorkspaceId | None

    @override
    def stream_id(self) -> UUID:
        return self.principal_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.TokenRotated(
            token_id=self.token_id,
            previous_token_id=self.previous_token_id,
            principal_id=self.principal_id,
            kind=generated.TokenKind(self.kind.value),
            expires_at=self.expires_at,
            previous_expires_at=self.previous_expires_at,
        ).to_json()


@dataclass(frozen=True, slots=True)
class TokenRevoked(DomainEvent):
    event_type: ClassVar[str] = names.TOKEN_REVOKED
    stream_kind: ClassVar[str] = names.EVENT_STREAM_KIND

    token_id: TokenId
    principal_id: PrincipalId
    revoked_by: PrincipalId
    workspace_id: WorkspaceId | None

    @override
    def stream_id(self) -> UUID:
        return self.principal_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.TokenRevoked(
            token_id=self.token_id, principal_id=self.principal_id, revoked_by=self.revoked_by
        ).to_json()


@dataclass(frozen=True, slots=True)
class MembershipGranted(DomainEvent):
    event_type: ClassVar[str] = names.MEMBERSHIP_GRANTED
    stream_kind: ClassVar[str] = names.EVENT_STREAM_KIND

    scope_id: ScopeId
    principal_id: PrincipalId
    role: Role
    previous_role: Role | None
    workspace_id: WorkspaceId | None

    @override
    def stream_id(self) -> UUID:
        return self.principal_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.MembershipGranted(
            scope_id=self.scope_id,
            principal_id=self.principal_id,
            role=generated.Role(self.role.value),
            previous_role=None if self.previous_role is None else generated.Role(self.previous_role.value),
        ).to_json()


@dataclass(frozen=True, slots=True)
class MembershipRevoked(DomainEvent):
    event_type: ClassVar[str] = names.MEMBERSHIP_REVOKED
    stream_kind: ClassVar[str] = names.EVENT_STREAM_KIND

    scope_id: ScopeId
    principal_id: PrincipalId
    role: Role
    workspace_id: WorkspaceId | None

    @override
    def stream_id(self) -> UUID:
        return self.principal_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return generated.MembershipRevoked(
            scope_id=self.scope_id, principal_id=self.principal_id, role=generated.Role(self.role.value)
        ).to_json()
