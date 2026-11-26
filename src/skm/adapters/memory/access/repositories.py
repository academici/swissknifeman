"""Memory implementations of the access repository ports (access §6, §11).

Rows are the immutable domain values themselves. The checks that PostgreSQL gets from constraints are made
here too: a unique token prefix (``Conflict(ALREADY_EXISTS, field=prefix)``), a unique name among the active,
not superseded tokens of a principal (``field=name``), a unique ``(issuer, subject)`` identity and optimistic
``row_version`` updates. FKs, CHECKs and triggers of DDL ``0006`` are not imitated (adapters §2.2): their
contract cases run on PostgreSQL only. ``save`` refuses a copy that would clear a revocation or replace a
successor that was stored (``INVALID_TRANSITION``), as the PostgreSQL adapter does for a stale copy.
``WorkerHostLookup`` has no implementation here: the workspace adapters own it.

Cursors are opaque base64 JSON: ``[created_at, id]`` for principals and tokens, ``[granted_at, scope_id,
principal_id]`` for memberships (keyset order ascending).
"""

import base64
import binascii
import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Final, cast
from uuid import UUID

from skm.adapters.memory.access.state import MemoryAccessState, access_state
from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.pagination import Cursor, Page, validate_cursor, validate_page_limit
from skm.kernel.scopes import ScopeKind
from skm.modules.access.domain.identity import PrincipalIdentity
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import Principal, PrincipalState, ensure_principal_update
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import (
    ApiToken,
    TokenId,
    TokenKind,
    ensure_binding_unchanged,
    ensure_not_revived,
)

__all__ = [
    "TOUCH_INTERVAL",
    "MemoryIdentityRepository",
    "MemoryMembershipRepository",
    "MemoryPrincipalRepository",
    "MemoryTokenRepository",
]

TOUCH_INTERVAL: Final = timedelta(seconds=60)


def _encode_cursor(parts: Sequence[str]) -> Cursor:
    raw = json.dumps(list(parts), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return validate_cursor(base64.urlsafe_b64encode(raw).decode("ascii"))


def _decode_cursor(cursor: str | None, size: int) -> tuple[datetime, *tuple[str, ...]] | None:
    """The keyset of ``cursor``: an aware timestamp first, then ``size - 1`` text parts."""
    if cursor is None:
        return None
    try:
        parts = json.loads(base64.urlsafe_b64decode(validate_cursor(cursor).encode("ascii")))
        items = cast("list[object]", parts) if isinstance(parts, list) else []
        if len(items) != size or not all(isinstance(item, str) for item in items):
            raise ValueError("cursor shape")
        texts = cast("list[str]", items)
        moment = datetime.fromisoformat(texts[0])
        if moment.utcoffset() is None:
            raise ValueError("cursor time is not aware")
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"}
        ) from None
    return (moment, *texts[1:])


def _page[T](rows: list[T], limit: int, cursor_of: Callable[[T], Sequence[str]]) -> Page[T]:
    limit = validate_page_limit(limit)
    items = rows[:limit]
    following = _encode_cursor(cursor_of(items[-1])) if len(rows) > limit else None
    return Page(items=tuple(items), next=following)


def _not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


class MemoryPrincipalRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables: MemoryAccessState = access_state(state)

    def get(self, principal_id: PrincipalId) -> Principal:
        found = self._tables.principals.get(principal_id)
        if found is None:
            raise _not_found("principal", principal_id)
        return found

    def add(self, principal: Principal) -> None:
        self._state.core.require_writable()
        if principal.id in self._tables.principals:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "a principal with this id exists",
                details={"kind": "principal", "ref": str(principal.id)},
            )
        if principal.row_version != 1:
            raise ValueError("a new principal starts at row_version 1")
        self._tables.principals[principal.id] = principal

    def save(self, principal: Principal, *, expected_version: int) -> None:
        self._state.core.require_writable()
        current = self.get(principal.id)
        if current.row_version != expected_version:
            raise Conflict(
                ErrorCode.VERSION_CONFLICT,
                f"version conflict: expected {expected_version}, actual {current.row_version}",
                details={"expected": expected_version, "actual": current.row_version},
            )
        ensure_principal_update(current, principal)
        self._tables.principals[principal.id] = principal

    def password_hash(self, principal_id: PrincipalId) -> bytes | None:
        return self._tables.passwords.get(principal_id)

    def set_first_password(self, principal_id: PrincipalId, password_hash: bytes) -> bool:
        self._state.core.require_writable()
        if self.get(principal_id).kind is not PrincipalKind.HUMAN or principal_id in self._tables.passwords:
            return False
        self._tables.passwords[principal_id] = password_hash
        return True

    def list(self, *, kind: PrincipalKind | None, after: str | None, limit: int) -> Page[Principal]:
        start = _decode_cursor(after, 2)
        rows = sorted(
            (p for p in self._tables.principals.values() if kind is None or p.kind is PrincipalKind(kind)),
            key=lambda p: (p.created_at, str(p.id)),
        )
        if start is not None:
            rows = [p for p in rows if (p.created_at, str(p.id)) > start]
        return _page(rows, limit, lambda p: (p.created_at.isoformat(), str(p.id)))


class MemoryIdentityRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables: MemoryAccessState = access_state(state)

    def find(self, issuer: str, subject: str) -> PrincipalIdentity | None:
        return self._tables.identities.get((issuer, subject))

    def add(self, identity: PrincipalIdentity) -> None:
        self._state.core.require_writable()
        key = (identity.issuer, identity.subject)
        if key in self._tables.identities:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "this external identity is already linked to a principal",
                details={"kind": "identity", "issuer": identity.issuer, "subject": identity.subject},
            )
        self._tables.identities[key] = identity

    def for_principal(self, principal_id: PrincipalId) -> tuple[PrincipalIdentity, ...]:
        return tuple(
            sorted(
                (i for i in self._tables.identities.values() if i.principal_id == principal_id),
                key=lambda i: (i.created_at, i.issuer, i.subject),
            )
        )


def _holds_name(token: ApiToken) -> bool:
    """Partial unique index ``(principal_id, name) WHERE revoked_at IS NULL AND superseded_by IS NULL``."""
    return token.revoked_at is None and token.superseded_by is None


class MemoryTokenRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables: MemoryAccessState = access_state(state)

    # one unit of work at a time makes every read exclusive: ``get_for_update`` needs no lock here
    def get(self, token_id: TokenId) -> ApiToken:
        found = self._tables.tokens.get(token_id)
        if found is None:
            raise _not_found("token", token_id)
        return found

    def get_for_update(self, token_id: TokenId) -> ApiToken:
        return self.get(token_id)

    def find_by_prefix(self, prefix: str) -> ApiToken | None:
        return next((t for t in self._tables.tokens.values() if t.prefix == prefix), None)

    def for_assignment(self, assignment_id: UUID) -> tuple[ApiToken, ...]:
        return tuple(
            sorted(
                (
                    t
                    for t in self._tables.tokens.values()
                    if t.assignment_id == assignment_id and t.revoked_at is None
                ),
                key=lambda t: (t.created_at, str(t.id)),
            )
        )

    def add(self, token: ApiToken) -> None:
        self._state.core.require_writable()
        if token.id in self._tables.tokens:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "a token with this id exists",
                details={"kind": "token", "field": "id"},
            )
        if self.find_by_prefix(token.prefix) is not None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "token prefix collision",
                details={"kind": "token", "field": "prefix"},
            )
        if _holds_name(token) and any(
            other.principal_id == token.principal_id and other.name == token.name and _holds_name(other)
            for other in self._tables.tokens.values()
        ):
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "an active token with this name exists",
                details={"kind": "token", "field": "name"},
            )
        self._tables.tokens[token.id] = token

    def save(self, token: ApiToken) -> None:
        self._state.core.require_writable()
        current = self.get(token.id)
        ensure_binding_unchanged(current, token)
        ensure_not_revived(current, token, successor_exists=current.superseded_by in self._tables.tokens)
        if _holds_name(token) and any(
            other.id != token.id
            and other.principal_id == token.principal_id
            and other.name == token.name
            and _holds_name(other)
            for other in self._tables.tokens.values()
        ):
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "an active token with this name exists",
                details={"kind": "token", "field": "name"},
            )
        self._tables.tokens[token.id] = token

    def touch(self, token_id: TokenId, at: datetime) -> None:
        self._state.core.require_writable()
        current = self.get(token_id)
        if current.last_used_at is None or current.last_used_at < at - TOUCH_INTERVAL:
            self._tables.tokens[token_id] = replace(current, last_used_at=at)

    def list_for(
        self,
        principal_id: PrincipalId | None,
        *,
        include_inactive: bool,
        after: str | None,
        limit: int,
        kind: TokenKind | None = None,
    ) -> Page[ApiToken]:
        start = _decode_cursor(after, 2)
        now = self._state.core.clock.now()
        rows = sorted(
            (
                t
                for t in self._tables.tokens.values()
                if (principal_id is None or t.principal_id == principal_id)
                and (kind is None or t.kind is TokenKind(kind))
                and (
                    include_inactive
                    or (t.revoked_at is None and (t.expires_at is None or t.expires_at > now))
                )
            ),
            key=lambda t: (t.created_at, str(t.id)),
        )
        if start is not None:
            rows = [t for t in rows if (t.created_at, str(t.id)) > start]
        return _page(rows, limit, lambda t: (t.created_at.isoformat(), str(t.id)))


class MemoryMembershipRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables: MemoryAccessState = access_state(state)

    def for_principal(
        self, principal_id: PrincipalId, scope_ids: Sequence[ScopeId]
    ) -> tuple[Membership, ...]:
        wanted = set(scope_ids)
        return tuple(
            sorted(
                (
                    m
                    for m in self._tables.memberships.values()
                    if m.principal_id == principal_id and m.scope_id in wanted
                ),
                key=lambda m: (m.granted_at, str(m.scope_id)),
            )
        )

    def get(self, scope_id: ScopeId, principal_id: PrincipalId) -> Membership | None:
        return self._tables.memberships.get((scope_id, principal_id))

    def upsert(self, membership: Membership) -> None:
        self._state.core.require_writable()
        self._tables.memberships[(membership.scope_id, membership.principal_id)] = membership

    def delete(self, scope_id: ScopeId, principal_id: PrincipalId) -> None:
        self._state.core.require_writable()
        self._tables.memberships.pop((scope_id, principal_id), None)

    def count_active_owners(self, scope_id: ScopeId) -> int:
        return sum(
            1
            for m in self._tables.memberships.values()
            if m.scope_id == scope_id
            and m.role is Role.OWNER
            and (p := self._tables.principals.get(m.principal_id)) is not None
            and p.state is PrincipalState.ACTIVE
        )

    def has_workspace_membership(self, principal_id: PrincipalId) -> bool:
        scopes = self._state.core.scopes
        return any(
            m.principal_id == principal_id
            and (record := scopes.get(m.scope_id)) is not None
            and record.kind is ScopeKind.WORKSPACE
            for m in self._tables.memberships.values()
        )

    def list(
        self, *, scope_id: ScopeId | None, principal_id: PrincipalId | None, after: str | None, limit: int
    ) -> Page[Membership]:
        start = _decode_cursor(after, 3)
        rows = sorted(
            (
                m
                for m in self._tables.memberships.values()
                if (scope_id is None or m.scope_id == scope_id)
                and (principal_id is None or m.principal_id == principal_id)
            ),
            key=lambda m: (m.granted_at, str(m.scope_id), str(m.principal_id)),
        )
        if start is not None:
            rows = [m for m in rows if (m.granted_at, str(m.scope_id), str(m.principal_id)) > start]
        return _page(rows, limit, lambda m: (m.granted_at.isoformat(), str(m.scope_id), str(m.principal_id)))
