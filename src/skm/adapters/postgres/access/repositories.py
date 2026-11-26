"""PostgreSQL implementations of the access repository ports (access §6, §11; DDL ``0006``).

Constructed per unit of work over its connection; they never commit or close it. ``_principal``,
``_identity``, ``_token`` and ``_membership`` map the rows of ``skm_access`` onto the domain values field by
field; a row that does not fit them is storage damage (``INTERNAL_ERROR``). No plaintext secret reaches this
module: ``secret_hash`` is the peppered HMAC and ``prefix`` its public lookup key.

Constraints. The ``ck_*``/``uq_*`` constraints, the kind triggers and the FKs of ``0006`` stay the authority
and are never bypassed; a violation surfaces through ``translate_pg_error``. Inserts run ``ON CONFLICT DO
NOTHING``: a duplicate id, prefix, active name or identity becomes ``Conflict(ALREADY_EXISTS, details.field)``
as in the memory adapter and leaves the transaction usable, so ``create_token`` and ``rotate_token`` draw a
new secret after a prefix collision in the same unit of work.

Token locks. ``get_for_update`` reads the row ``FOR UPDATE``; revoke, rotate, assignment renewal and the
facade revocations read it that way before ``save``, so they queue on the row and the later one decides on
what the earlier one committed: a token gets one successor and a revoked token is not rotated. ``save`` locks
the row again and refuses a stale copy that would clear a revocation or replace a successor that exists
(``INVALID_TRANSITION``, as in the memory adapter).

Owner lock. ``count_active_owners`` first takes the transaction advisory lock of the scope, then counts in a
new statement, locking the owner memberships ``FOR UPDATE`` and their principals ``FOR SHARE``. The commands
that remove an owner (``revoke_membership``, a demotion, ``disable_principal``) count before they write, so a
second one waits until the first commits and, under READ COMMITTED, counts what the first left: two
concurrent removals never both pass ``last_owner_guard``. The advisory lock needs no table privilege; the
runtime role ``skm_app`` may not lock rows of the append-only ``skm_core.scopes``.

Time and paging. ``list_for`` judges expiry with the clock the repository was built with (``SystemClock`` by
default, the test clock in contract suites), as the memory adapter uses the backend clock; ``updated_at`` of
a saved principal comes from the same clock. Keysets ascend by ``(created_at, id)`` and ``(granted_at,
scope_id, principal_id)``; cursors are bound to their filter (``adapters/postgres/pagination.py``).
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from hashlib import sha256
from typing import Final, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.pagination import decode_cursor, page_of, query_digest
from skm.kernel.actor import PrincipalKind, ScopeGrant
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.pagination import Page, validate_page_limit
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
from skm.platform.system_clock import SystemClock

__all__ = [
    "OWNER_LOCK_CLASS",
    "PostgresIdentityRepository",
    "PostgresMembershipRepository",
    "PostgresPrincipalRepository",
    "PostgresTokenRepository",
    "owner_lock_key",
]

type _Row = tuple[object, ...]

# First key of the two-key advisory lock ``pg_advisory_xact_lock(class, scope)`` serializing owner changes.
OWNER_LOCK_CLASS: Final = 0x534B_4D41  # "SKMA"

# ---------------------------------------------------------------------------------------------- statements
_PRINCIPAL: Final = (
    "SELECT id, kind, display_name, state, row_version, created_at, created_by FROM skm_access.principals "
)
_PRINCIPAL_GET: Final = _PRINCIPAL + "WHERE id = %s"
_PRINCIPAL_LOCKED: Final = _PRINCIPAL_GET + " FOR UPDATE"
_PRINCIPAL_EXISTS: Final = "SELECT 1 FROM skm_access.principals WHERE id = %s"
_PRINCIPAL_INSERT: Final = """
INSERT INTO skm_access.principals
    (id, kind, display_name, state, row_version, created_at, created_by, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
_PRINCIPAL_UPDATE: Final = """
UPDATE skm_access.principals
   SET display_name = %s, state = %s, row_version = %s, updated_at = greatest(updated_at, %s)
 WHERE id = %s AND row_version = %s
RETURNING id
"""
_PRINCIPAL_LIST: Final = (
    _PRINCIPAL
    + """
 WHERE (%(kind)s::text IS NULL OR kind = %(kind)s::text)
   AND (%(at)s::timestamptz IS NULL OR (created_at, id) > (%(at)s::timestamptz, %(id)s::uuid))
 ORDER BY created_at, id
 LIMIT %(limit)s
"""
)

_IDENTITY: Final = "SELECT principal_id, issuer, subject, created_at FROM skm_access.principal_identities "
_IDENTITY_FIND: Final = _IDENTITY + "WHERE issuer = %s AND subject = %s"
_IDENTITY_OF: Final = (
    _IDENTITY + 'WHERE principal_id = %s ORDER BY created_at, issuer COLLATE "C", subject COLLATE "C"'
)
_IDENTITY_INSERT: Final = """
INSERT INTO skm_access.principal_identities (principal_id, issuer, subject, created_at)
VALUES (%s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING issuer
"""

_TOKEN: Final = (
    "SELECT id, principal_id, kind, name, prefix, secret_hash, scope_id, permissions, expires_at, "
    "created_at, created_by, last_used_at, revoked_at, revoked_by, assignment_id, step_id, "
    "superseded_by, scope_grants, assignment_scope_id, worker_id "
    "FROM skm_access.api_tokens "
)
_TOKEN_GET: Final = _TOKEN + "WHERE id = %s"
_TOKEN_LOCKED: Final = _TOKEN_GET + " FOR UPDATE"
_TOKEN_BY_PREFIX: Final = _TOKEN + "WHERE prefix = %s"
_TOKEN_OF_ASSIGNMENT: Final = (
    _TOKEN + "WHERE assignment_id = %s AND revoked_at IS NULL ORDER BY created_at, id"
)
_TOKEN_EXISTS: Final = "SELECT 1 FROM skm_access.api_tokens WHERE id = %s"
_TOKEN_PREFIX_TAKEN: Final = "SELECT 1 FROM skm_access.api_tokens WHERE prefix = %s"
# the partial unique index uq_api_tokens__principal_id_name_active
_TOKEN_NAME_TAKEN: Final = (
    "SELECT 1 FROM skm_access.api_tokens WHERE principal_id = %s AND name = %s "
    "AND revoked_at IS NULL AND superseded_by IS NULL AND id <> %s"
)
_TOKEN_INSERT: Final = """
INSERT INTO skm_access.api_tokens
    (id, principal_id, kind, name, prefix, secret_hash, scope_id, permissions, expires_at, created_at,
     created_by, last_used_at, revoked_at, revoked_by, assignment_id, step_id, superseded_by,
     scope_grants, assignment_scope_id, worker_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING RETURNING id
"""
# identity, owner, secret, scope, permissions and assignment binding never change (ensure_binding_unchanged)
_TOKEN_UPDATE: Final = """
UPDATE skm_access.api_tokens
   SET name = %s, expires_at = %s, last_used_at = %s, revoked_at = %s, revoked_by = %s, superseded_by = %s
 WHERE id = %s
"""
_TOKEN_TOUCH: Final = """
UPDATE skm_access.api_tokens SET last_used_at = %(at)s
 WHERE id = %(id)s AND (last_used_at IS NULL OR last_used_at < %(at)s - interval '60 seconds')
RETURNING id
"""
_TOKEN_LIST: Final = (
    _TOKEN
    + """
 WHERE (%(principal)s::uuid IS NULL OR principal_id = %(principal)s::uuid)
   AND (%(kind)s::text IS NULL OR kind = %(kind)s::text)
   AND (%(all)s OR (revoked_at IS NULL AND (expires_at IS NULL OR expires_at > %(now)s::timestamptz)))
   AND (%(at)s::timestamptz IS NULL OR (created_at, id) > (%(at)s::timestamptz, %(id)s::uuid))
 ORDER BY created_at, id
 LIMIT %(limit)s
"""
)

_MEMBERSHIP: Final = (
    "SELECT scope_id, principal_id, role, granted_by, granted_at FROM skm_access.memberships "
)
_MEMBERSHIP_GET: Final = _MEMBERSHIP + "WHERE scope_id = %s AND principal_id = %s"
_MEMBERSHIP_FOR: Final = (
    _MEMBERSHIP + "WHERE principal_id = %s AND scope_id = ANY(%s) ORDER BY granted_at, scope_id"
)
_MEMBERSHIP_UPSERT: Final = """
INSERT INTO skm_access.memberships (scope_id, principal_id, role, granted_by, granted_at)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (scope_id, principal_id)
DO UPDATE SET role = EXCLUDED.role, granted_by = EXCLUDED.granted_by, granted_at = EXCLUDED.granted_at
"""
_MEMBERSHIP_DELETE: Final = "DELETE FROM skm_access.memberships WHERE scope_id = %s AND principal_id = %s"
_OWNER_LOCK: Final = "SELECT pg_advisory_xact_lock(%s::int4, %s::int4)"
# A separate statement after the lock: under READ COMMITTED its snapshot includes what the previous holder
# committed. Row locks keep writers that skip the advisory lock off the counted rows until this one ends.
# The rows are locked in principal order whatever the plan, so two counters cannot deadlock each other.
_ACTIVE_OWNERS: Final = """
SELECT count(*) FROM (
    SELECT m.principal_id
      FROM skm_access.memberships m JOIN skm_access.principals p ON p.id = m.principal_id
     WHERE m.scope_id = %s AND m.role = 'owner' AND p.state = 'active'
     ORDER BY m.principal_id
       FOR UPDATE OF m FOR SHARE OF p
) AS owners
"""
_HAS_WORKSPACE_MEMBERSHIP: Final = """
SELECT EXISTS (
    SELECT 1 FROM skm_access.memberships m JOIN skm_core.scopes s ON s.id = m.scope_id
     WHERE m.principal_id = %s AND s.kind = 'workspace'
)
"""
_MEMBERSHIP_LIST: Final = (
    _MEMBERSHIP
    + """
 WHERE (%(scope)s::uuid IS NULL OR scope_id = %(scope)s::uuid)
   AND (%(principal)s::uuid IS NULL OR principal_id = %(principal)s::uuid)
   AND (%(at)s::timestamptz IS NULL
        OR (granted_at, scope_id, principal_id) > (%(at)s::timestamptz, %(sid)s::uuid, %(pid)s::uuid))
 ORDER BY granted_at, scope_id, principal_id
 LIMIT %(limit)s
"""
)


# ---------------------------------------------------------------------------------------------- helpers
def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def _damaged(table: str, ref: object, exc: Exception) -> InternalError:
    error = InternalError(
        ErrorCode.INTERNAL_ERROR,
        f"skm_access.{table} row is malformed",
        details={"table": f"skm_access.{table}", "id": str(ref)},
    )
    error.__cause__ = exc
    return error


def _not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


def _bad_cursor() -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"})


def _keyset(after: str | None, digest: str, size: int) -> tuple[datetime | None, tuple[UUID | None, ...]]:
    """The keyset of ``after``: an aware timestamp, then ``size - 1`` ids (``None`` for the first page)."""
    if after is None:
        return None, (None,) * (size - 1)
    values = decode_cursor(after, expected_query_digest=digest).sort_values
    if len(values) != size or not all(isinstance(value, str) for value in values):
        raise _bad_cursor()
    texts = cast("tuple[str, ...]", values)
    try:
        moment = datetime.fromisoformat(texts[0])
        ids = tuple(UUID(text) for text in texts[1:])
    except ValueError as exc:
        raise _bad_cursor() from exc
    if moment.utcoffset() is None:  # a naive time cannot be ordered against timestamptz
        raise _bad_cursor()
    return moment, ids


def _uuid_or_none(value: object) -> UUID | None:
    return None if value is None else cast("UUID", value)


def owner_lock_key(scope_id: UUID) -> tuple[int, int]:
    """``(class, object)`` of the owner advisory lock of a scope; the object key is a signed 32-bit hash."""
    digest = sha256(b"skm_access.owners:" + scope_id.bytes).digest()
    return OWNER_LOCK_CLASS, int.from_bytes(digest[:4], "big", signed=True)


# ---------------------------------------------------------------------------------------------- rows
def _principal(row: _Row) -> Principal:
    try:
        return Principal(
            id=PrincipalId(cast("UUID", row[0])),
            kind=PrincipalKind(cast("str", row[1])),
            display_name=cast("str", row[2]),
            state=PrincipalState(cast("str", row[3])),
            row_version=cast("int", row[4]),
            created_at=cast("datetime", row[5]),
            created_by=None if row[6] is None else PrincipalId(cast("UUID", row[6])),
        )
    except (TypeError, ValueError) as exc:
        raise _damaged("principals", row[0], exc) from exc


def _identity(row: _Row) -> PrincipalIdentity:
    try:
        return PrincipalIdentity(
            principal_id=PrincipalId(cast("UUID", row[0])),
            issuer=cast("str", row[1]),
            subject=cast("str", row[2]),
            created_at=cast("datetime", row[3]),
        )
    except (TypeError, ValueError) as exc:
        raise _damaged("principal_identities", f"{row[1]}/{row[2]}", exc) from exc


def _permissions(value: object) -> frozenset[str] | None:
    return None if value is None else frozenset(cast("list[str]", value))


def _token(row: _Row) -> ApiToken:
    try:
        return ApiToken(
            id=TokenId(cast("UUID", row[0])),
            principal_id=PrincipalId(cast("UUID", row[1])),
            kind=TokenKind(cast("str", row[2])),
            name=cast("str", row[3]),
            prefix=cast("str", row[4]),
            secret_hash=bytes(cast("bytes", row[5])),
            scope_id=None if row[6] is None else ScopeId(cast("UUID", row[6])),
            permissions=_permissions(row[7]),
            expires_at=cast("datetime | None", row[8]),
            created_at=cast("datetime", row[9]),
            created_by=PrincipalId(cast("UUID", row[10])),
            last_used_at=cast("datetime | None", row[11]),
            revoked_at=cast("datetime | None", row[12]),
            revoked_by=None if row[13] is None else PrincipalId(cast("UUID", row[13])),
            assignment_id=_uuid_or_none(row[14]),
            step_id=_uuid_or_none(row[15]),
            superseded_by=None if row[16] is None else TokenId(cast("UUID", row[16])),
            scope_grants=None
            if row[17] is None
            else tuple(
                ScopeGrant(ScopeId(UUID(scope)), frozenset(permissions))
                for scope, permissions in sorted(cast("dict[str, list[str]]", row[17]).items())
            ),
            assignment_scope_id=None if row[18] is None else ScopeId(cast("UUID", row[18])),
            worker_id=_uuid_or_none(row[19]),
        )
    except (TypeError, ValueError) as exc:
        raise _damaged("api_tokens", row[0], exc) from exc


def _token_params(token: ApiToken) -> tuple[object, ...]:
    """Parameters of ``_TOKEN_INSERT``; permissions are stored sorted, so equal sets give equal arrays."""
    return (
        token.id,
        token.principal_id,
        TokenKind(token.kind).value,
        token.name,
        token.prefix,
        token.secret_hash,
        token.scope_id,
        None if token.permissions is None else sorted(token.permissions),
        token.expires_at,
        token.created_at,
        token.created_by,
        token.last_used_at,
        token.revoked_at,
        token.revoked_by,
        token.assignment_id,
        token.step_id,
        token.superseded_by,
        None
        if token.scope_grants is None
        else Jsonb({str(pair.scope_id): sorted(pair.permissions) for pair in token.scope_grants}),
        token.assignment_scope_id,
        token.worker_id,
    )


def _membership(row: _Row) -> Membership:
    try:
        return Membership(
            scope_id=ScopeId(cast("UUID", row[0])),
            principal_id=PrincipalId(cast("UUID", row[1])),
            role=Role(cast("str", row[2])),
            granted_by=None if row[3] is None else PrincipalId(cast("UUID", row[3])),
            granted_at=cast("datetime", row[4]),
        )
    except (TypeError, ValueError) as exc:
        raise _damaged("memberships", f"{row[0]}/{row[1]}", exc) from exc


def _holds_name(token: ApiToken) -> bool:
    """Partial unique index ``(principal_id, name) WHERE revoked_at IS NULL AND superseded_by IS NULL``."""
    return token.revoked_at is None and token.superseded_by is None


# ---------------------------------------------------------------------------------------------- repositories
class PostgresPrincipalRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def get(self, principal_id: PrincipalId) -> Principal:
        row = _run(lambda: self._conn.execute(_PRINCIPAL_GET, (principal_id,)).fetchone())
        if row is None:
            raise _not_found("principal", principal_id)
        return _principal(row)

    def add(self, principal: Principal) -> None:
        if _run(lambda: self._conn.execute(_PRINCIPAL_EXISTS, (principal.id,)).fetchone()) is not None:
            raise _principal_exists(principal)
        if principal.row_version != 1:
            raise ValueError("a new principal starts at row_version 1")
        params = (
            principal.id,
            PrincipalKind(principal.kind).value,
            principal.display_name,
            PrincipalState(principal.state).value,
            principal.row_version,
            principal.created_at,
            principal.created_by,
            principal.created_at,
        )
        if _run(lambda: self._conn.execute(_PRINCIPAL_INSERT, params).fetchone()) is None:
            raise _principal_exists(principal)  # a concurrent writer took the id

    def save(self, principal: Principal, *, expected_version: int) -> None:
        """Compare-and-set on ``row_version``; the row stays locked until the unit of work ends."""
        row = _run(lambda: self._conn.execute(_PRINCIPAL_LOCKED, (principal.id,)).fetchone())
        if row is None:
            raise _not_found("principal", principal.id)
        current = _principal(row)
        if current.row_version != expected_version:
            raise _version_conflict(expected_version, current.row_version)
        ensure_principal_update(current, principal)
        params = (
            principal.display_name,
            PrincipalState(principal.state).value,
            principal.row_version,
            self._clock.now(),
            principal.id,
            expected_version,
        )
        if _run(lambda: self._conn.execute(_PRINCIPAL_UPDATE, params).fetchone()) is None:
            raise _version_conflict(expected_version, current.row_version)  # unreachable under the lock

    def password_hash(self, principal_id: PrincipalId) -> bytes | None:
        row = _run(
            lambda: self._conn.execute(
                "SELECT password_hash FROM skm_access.principals WHERE id = %s", (principal_id,)
            ).fetchone()
        )
        return None if row is None else cast("bytes | None", row[0])

    def set_first_password(self, principal_id: PrincipalId, password_hash: bytes) -> bool:
        return (
            _run(
                lambda: self._conn.execute(
                    """UPDATE skm_access.principals SET password_hash = %s
               WHERE id = %s AND kind = 'human' AND password_hash IS NULL RETURNING id""",
                    (password_hash, principal_id),
                ).fetchone()
            )
            is not None
        )

    def list(self, *, kind: PrincipalKind | None, after: str | None, limit: int) -> Page[Principal]:
        limit = validate_page_limit(limit)
        kind_value = None if kind is None else PrincipalKind(kind).value
        digest = query_digest({"kind": "access_principals", "principal_kind": kind_value})
        at, (start,) = _keyset(after, digest, 2)
        params = {"kind": kind_value, "at": at, "id": start, "limit": limit + 1}
        rows = _run(lambda: self._conn.execute(_PRINCIPAL_LIST, params).fetchall())
        return page_of(
            [_principal(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda p: (p.created_at.isoformat(), str(p.id)),
        )


def _principal_exists(principal: Principal) -> Conflict:
    return Conflict(
        ErrorCode.ALREADY_EXISTS,
        "a principal with this id exists",
        details={"kind": "principal", "ref": str(principal.id)},
    )


def _version_conflict(expected: int, actual: int) -> Conflict:
    return Conflict(
        ErrorCode.VERSION_CONFLICT,
        f"version conflict: expected {expected}, actual {actual}",
        details={"expected": expected, "actual": actual},
    )


class PostgresIdentityRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def find(self, issuer: str, subject: str) -> PrincipalIdentity | None:
        row = _run(lambda: self._conn.execute(_IDENTITY_FIND, (issuer, subject)).fetchone())
        return None if row is None else _identity(row)

    def add(self, identity: PrincipalIdentity) -> None:
        params = (identity.principal_id, identity.issuer, identity.subject, identity.created_at)
        if _run(lambda: self._conn.execute(_IDENTITY_INSERT, params).fetchone()) is None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "this external identity is already linked to a principal",
                details={"kind": "identity", "issuer": identity.issuer, "subject": identity.subject},
            )

    def for_principal(self, principal_id: PrincipalId) -> tuple[PrincipalIdentity, ...]:
        rows = _run(lambda: self._conn.execute(_IDENTITY_OF, (principal_id,)).fetchall())
        return tuple(_identity(row) for row in rows)


class PostgresTokenRepository:
    def __init__(self, conn: psycopg.Connection, *, clock: Clock | None = None) -> None:
        self._conn = conn
        self._clock: Clock = clock if clock is not None else SystemClock()

    def _exists(self, token_id: TokenId) -> bool:
        return _run(lambda: self._conn.execute(_TOKEN_EXISTS, (token_id,)).fetchone()) is not None

    def get(self, token_id: TokenId) -> ApiToken:
        row = _run(lambda: self._conn.execute(_TOKEN_GET, (token_id,)).fetchone())
        if row is None:
            raise _not_found("token", token_id)
        return _token(row)

    def get_for_update(self, token_id: TokenId) -> ApiToken:
        """The committed row, locked ``FOR UPDATE`` until the unit of work ends (revoke, rotate, renew)."""
        row = _run(lambda: self._conn.execute(_TOKEN_LOCKED, (token_id,)).fetchone())
        if row is None:
            raise _not_found("token", token_id)
        return _token(row)

    def find_by_prefix(self, prefix: str) -> ApiToken | None:
        row = _run(lambda: self._conn.execute(_TOKEN_BY_PREFIX, (prefix,)).fetchone())
        return None if row is None else _token(row)

    def for_assignment(self, assignment_id: UUID) -> tuple[ApiToken, ...]:
        rows = _run(lambda: self._conn.execute(_TOKEN_OF_ASSIGNMENT, (assignment_id,)).fetchall())
        return tuple(_token(row) for row in rows)

    def add(self, token: ApiToken) -> None:
        params = _token_params(token)
        if _run(lambda: self._conn.execute(_TOKEN_INSERT, params).fetchone()) is not None:
            return
        # Nothing inserted: name the unique key that refused the row, in the order of the memory adapter.
        if self._exists(token.id):
            raise _token_conflict("a token with this id exists", "id")
        if _run(lambda: self._conn.execute(_TOKEN_PREFIX_TAKEN, (token.prefix,)).fetchone()) is not None:
            raise _token_conflict("token prefix collision", "prefix")
        raise _token_conflict("an active token with this name exists", "name")

    def save(self, token: ApiToken) -> None:
        current = self.get_for_update(token.id)
        ensure_binding_unchanged(current, token)
        successor = current.superseded_by
        ensure_not_revived(
            current,
            token,
            successor_exists=successor is not None and self._exists(successor),
        )
        name_key = (token.principal_id, token.name, token.id)
        if (
            _holds_name(token)
            and _run(lambda: self._conn.execute(_TOKEN_NAME_TAKEN, name_key).fetchone()) is not None
        ):
            raise _token_conflict("an active token with this name exists", "name")
        params = (
            token.name,
            token.expires_at,
            token.last_used_at,
            token.revoked_at,
            token.revoked_by,
            token.superseded_by,
            token.id,
        )
        _run(lambda: self._conn.execute(_TOKEN_UPDATE, params))

    def touch(self, token_id: TokenId, at: datetime) -> None:
        """``last_used_at = at`` unless it was set less than 60 seconds before ``at``."""
        params = {"id": token_id, "at": at}
        if _run(lambda: self._conn.execute(_TOKEN_TOUCH, params).fetchone()) is None and not self._exists(
            token_id
        ):
            raise _not_found("token", token_id)

    def list_for(
        self,
        principal_id: PrincipalId | None,
        *,
        include_inactive: bool,
        after: str | None,
        limit: int,
        kind: TokenKind | None = None,
    ) -> Page[ApiToken]:
        limit = validate_page_limit(limit)
        kind_value = None if kind is None else TokenKind(kind).value
        digest = query_digest(
            {
                "kind": "access_tokens",
                "principal_id": None if principal_id is None else str(principal_id),
                "token_kind": kind_value,
                "include_inactive": include_inactive,
            }
        )
        at, (start,) = _keyset(after, digest, 2)
        params = {
            "principal": principal_id,
            "kind": kind_value,
            "all": include_inactive,
            "now": self._clock.now(),
            "at": at,
            "id": start,
            "limit": limit + 1,
        }
        rows = _run(lambda: self._conn.execute(_TOKEN_LIST, params).fetchall())
        return page_of(
            [_token(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda t: (t.created_at.isoformat(), str(t.id)),
        )


def _token_conflict(message: str, field: str) -> Conflict:
    return Conflict(ErrorCode.ALREADY_EXISTS, message, details={"kind": "token", "field": field})


class PostgresMembershipRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def for_principal(
        self, principal_id: PrincipalId, scope_ids: Sequence[ScopeId]
    ) -> tuple[Membership, ...]:
        wanted = list(dict.fromkeys(scope_ids))
        if not wanted:
            return ()
        rows = _run(lambda: self._conn.execute(_MEMBERSHIP_FOR, (principal_id, wanted)).fetchall())
        return tuple(_membership(row) for row in rows)

    def get(self, scope_id: ScopeId, principal_id: PrincipalId) -> Membership | None:
        row = _run(lambda: self._conn.execute(_MEMBERSHIP_GET, (scope_id, principal_id)).fetchone())
        return None if row is None else _membership(row)

    def upsert(self, membership: Membership) -> None:
        params = (
            membership.scope_id,
            membership.principal_id,
            Role(membership.role).value,
            membership.granted_by,
            membership.granted_at,
        )
        _run(lambda: self._conn.execute(_MEMBERSHIP_UPSERT, params))

    def delete(self, scope_id: ScopeId, principal_id: PrincipalId) -> None:
        _run(lambda: self._conn.execute(_MEMBERSHIP_DELETE, (scope_id, principal_id)))

    def count_active_owners(self, scope_id: ScopeId) -> int:
        """Active owners of the scope, counted under its owner lock (held until the unit of work ends)."""
        _run(lambda: self._conn.execute(_OWNER_LOCK, owner_lock_key(scope_id)))
        row = _run(lambda: self._conn.execute(_ACTIVE_OWNERS, (scope_id,)).fetchone())
        return 0 if row is None else cast("int", row[0])

    def has_workspace_membership(self, principal_id: PrincipalId) -> bool:
        row = _run(lambda: self._conn.execute(_HAS_WORKSPACE_MEMBERSHIP, (principal_id,)).fetchone())
        return row is not None and bool(row[0])

    def list(
        self, *, scope_id: ScopeId | None, principal_id: PrincipalId | None, after: str | None, limit: int
    ) -> Page[Membership]:
        limit = validate_page_limit(limit)
        digest = query_digest(
            {
                "kind": "access_memberships",
                "scope_id": None if scope_id is None else str(scope_id),
                "principal_id": None if principal_id is None else str(principal_id),
            }
        )
        at, (start_scope, start_principal) = _keyset(after, digest, 3)
        params = {
            "scope": scope_id,
            "principal": principal_id,
            "at": at,
            "sid": start_scope,
            "pid": start_principal,
            "limit": limit + 1,
        }
        rows = _run(lambda: self._conn.execute(_MEMBERSHIP_LIST, params).fetchall())
        return page_of(
            [_membership(row) for row in rows],
            limit=limit,
            digest=digest,
            key_of=lambda m: (m.granted_at.isoformat(), str(m.scope_id), str(m.principal_id)),
        )
