"""Machine-local storage over a DSN dedicated to the machine application role."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Final, cast, override
from uuid import UUID

import psycopg
from psycopg.errors import ForeignKeyViolation
from psycopg.types.json import Jsonb

from skm.adapters.postgres.config_store import dumps_value, jsonb_value, loads_value
from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.config.secrets import SecretRef
from skm.platform.machine import (
    MachineBinding,
    MachineCheckout,
    MachineCheckoutKey,
    MachinePrincipal,
    MachineProfile,
    MachineRetry,
    MachineRetryKey,
    MachineSession,
    MachineStore,
)

__all__ = ["PostgresMachineStore"]

_PROFILE = """
SELECT instance_id, origin, endpoint, credential_ref, ca_bundle, revision
FROM skm_host.profiles WHERE installation_id = %s AND name = %s
"""
_INSERT_PROFILE = """
INSERT INTO skm_host.profiles
    (installation_id, name, instance_id, origin, endpoint, credential_ref, ca_bundle)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING
RETURNING revision
"""
_DELETE_PROFILE = """
DELETE FROM skm_host.profiles WHERE installation_id = %s AND name = %s AND revision = %s
RETURNING revision
"""

_SELECT_RETRY = """
SELECT idempotency_key, payload::text, safe_until, receipt::text FROM skm_host.retries
WHERE installation_id = %s AND instance_id = %s AND host_id = %s AND checkout_id = %s AND principal_id = %s
  AND operation = %s AND request_id = %s AND step = %s
"""
_SESSION_PROFILE_FK: Final = "fk_sessions__profile"


class _ProfileConflict(Exception):
    """Cause a profile replacement to roll back when the new identity is already in use."""


def _profile_from_row(installation_id: UUID, name: str, row: tuple[object, ...]) -> MachineProfile:
    instance_id, origin, endpoint, credential, ca_bundle, revision = row
    return MachineProfile(
        installation_id,
        name,
        cast("UUID", instance_id),
        cast("str", origin),
        cast("str | None", endpoint),
        SecretRef.parse(str(credential)) if credential is not None else None,
        Path(str(ca_bundle)) if ca_bundle is not None else None,
        cast("UUID", revision),
    )


def _checkout_scope(key: MachineCheckoutKey) -> tuple[UUID, UUID, UUID, UUID]:
    return key.installation_id, key.instance_id, key.host_id, key.checkout_id


def _binding_scope(scope: MachinePrincipal, checkout: MachineCheckoutKey) -> tuple[UUID, ...]:
    if scope.installation_id != checkout.installation_id or scope.instance_id != checkout.instance_id:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Checkout identity differs from the machine principal"
        )
    return (*_checkout_scope(checkout), scope.principal_id)


def _retry_scope(key: MachineRetryKey) -> tuple[UUID | str, ...]:
    return (*_binding_scope(key.scope, key.checkout), key.operation, key.request_id, key.step)


def _retry_from_row(key: MachineRetryKey, row: tuple[object, ...]) -> MachineRetry:
    idempotency_key, payload, safe_until, receipt = row
    return MachineRetry(
        key,
        cast("str", idempotency_key),
        cast("JsonObject", loads_value(cast("str", payload))),
        cast("datetime", safe_until),
        cast("JsonObject", loads_value(cast("str", receipt))) if receipt is not None else None,
    )


class PostgresMachineStore(MachineStore):
    """Each repository call owns a short local connection and transaction."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    @contextmanager
    def _connection(self) -> Generator[psycopg.Connection[tuple[object, ...]]]:
        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as connection:
                yield connection
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc

    @override
    def get_installation_id(self) -> UUID | None:
        with self._connection() as conn:
            row = conn.execute("SELECT installation_id FROM skm_host.installation WHERE singleton").fetchone()
        return None if row is None else cast("UUID", row[0])

    @override
    def initialize_installation(self, installation_id: UUID) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO skm_host.installation (installation_id) VALUES (%s)
                ON CONFLICT DO NOTHING
                """,
                (installation_id,),
            )
            row = conn.execute("SELECT installation_id FROM skm_host.installation WHERE singleton").fetchone()
            if row != (installation_id,):
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID, "Machine installation identity differs from bootstrap"
                )

    @override
    def get_operator_setting(self, installation_id: UUID, key: str) -> JsonValue:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value::text FROM skm_host.operator_settings WHERE installation_id = %s AND key = %s",
                (installation_id, key),
            ).fetchone()
        return None if row is None else loads_value(cast("str", row[0]))

    @override
    def set_operator_setting(self, installation_id: UUID, key: str, value: JsonValue) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO skm_host.operator_settings (installation_id, key, value)
                VALUES (%s, %s, %s) ON CONFLICT (installation_id, key) DO UPDATE SET value = EXCLUDED.value
                """,
                (installation_id, key, Jsonb(value, dumps=dumps_value)),
            )

    @override
    def get_user_setting(self, scope: MachinePrincipal, key: str) -> JsonValue:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT value::text FROM skm_host.user_settings
                WHERE installation_id = %s AND instance_id = %s AND principal_id = %s AND key = %s
                """,
                (scope.installation_id, scope.instance_id, scope.principal_id, key),
            ).fetchone()
        return None if row is None else loads_value(cast("str", row[0]))

    @override
    def set_user_setting(self, scope: MachinePrincipal, key: str, value: JsonValue) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO skm_host.user_settings (installation_id, instance_id, principal_id, key, value)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (installation_id, instance_id, principal_id, key)
                DO UPDATE SET value = EXCLUDED.value
                """,
                (
                    scope.installation_id,
                    scope.instance_id,
                    scope.principal_id,
                    key,
                    Jsonb(value, dumps=dumps_value),
                ),
            )

    @override
    def get_profile(self, installation_id: UUID, name: str) -> MachineProfile | None:
        with self._connection() as conn:
            row = conn.execute(_PROFILE, (installation_id, name)).fetchone()
        return None if row is None else _profile_from_row(installation_id, name, row)

    @override
    def list_profiles(self, installation_id: UUID) -> tuple[MachineProfile, ...]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT name, instance_id, origin, endpoint, credential_ref, ca_bundle, revision
                FROM skm_host.profiles WHERE installation_id = %s ORDER BY name
                """,
                (installation_id,),
            ).fetchall()
        return tuple(_profile_from_row(installation_id, str(name), tuple(fields)) for name, *fields in rows)

    @override
    def put_profile(self, profile: MachineProfile, *, expected: MachineProfile | None = None) -> bool:
        if expected is not None and (
            expected.installation_id != profile.installation_id or expected.revision is None
        ):
            return False
        try:
            with self._connection() as conn:
                if expected is not None:
                    if replace(profile, revision=expected.revision) == expected:
                        row = conn.execute(_PROFILE, (expected.installation_id, expected.name)).fetchone()
                        return row is not None and row[-1] == expected.revision
                    deleted = conn.execute(
                        _DELETE_PROFILE, (expected.installation_id, expected.name, expected.revision)
                    ).fetchone()
                    if deleted is None:
                        return False
                row = conn.execute(
                    _INSERT_PROFILE,
                    (
                        profile.installation_id,
                        profile.name,
                        profile.instance_id,
                        profile.origin,
                        profile.endpoint,
                        str(profile.credential_ref) if profile.credential_ref is not None else None,
                        str(profile.ca_bundle) if profile.ca_bundle is not None else None,
                    ),
                ).fetchone()
                if row is None:
                    raise _ProfileConflict
        except _ProfileConflict:
            return False
        else:
            return True

    @override
    def delete_profile(self, profile: MachineProfile) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                _DELETE_PROFILE, (profile.installation_id, profile.name, profile.revision)
            ).fetchone()
        return row is not None

    @override
    def put_session(self, session: MachineSession) -> bool:
        profile = session.profile
        with self._connection() as conn:
            try:
                row = conn.execute(
                    """
                    INSERT INTO skm_host.sessions
                        (installation_id, profile_revision, instance_id, origin,
                         principal_id, handle_hash, expires_at)
                    SELECT installation_id, revision, instance_id, origin, %s, %s, %s
                    FROM skm_host.profiles
                    WHERE installation_id = %s AND name = %s AND revision = %s
                      AND instance_id = %s AND origin = %s
                    ON CONFLICT DO NOTHING RETURNING handle_hash
                    """,
                    (
                        session.principal_id,
                        session.handle_hash,
                        session.expires_at,
                        profile.installation_id,
                        profile.name,
                        profile.revision,
                        profile.instance_id,
                        profile.origin,
                    ),
                ).fetchone()
            except ForeignKeyViolation as exc:
                if exc.diag.constraint_name != _SESSION_PROFILE_FK:
                    raise
                conn.rollback()
                return False
        return row is not None

    @override
    def get_session(self, installation_id: UUID, handle_hash: str, now: datetime) -> MachinePrincipal | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT instance_id, principal_id FROM skm_host.sessions
                WHERE installation_id = %s AND handle_hash = %s AND expires_at > %s
                  AND expires_at > statement_timestamp()
                """,
                (installation_id, handle_hash, now),
            ).fetchone()
        return (
            None
            if row is None
            else MachinePrincipal(installation_id, cast("UUID", row[0]), cast("UUID", row[1]))
        )

    @override
    def delete_session(self, installation_id: UUID, handle_hash: str) -> None:
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM skm_host.sessions WHERE installation_id = %s AND handle_hash = %s",
                (installation_id, handle_hash),
            )

    @override
    def revoke_sessions(self, scope: MachinePrincipal) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                DELETE FROM skm_host.sessions
                WHERE installation_id = %s AND instance_id = %s AND principal_id = %s
                """,
                (scope.installation_id, scope.instance_id, scope.principal_id),
            )

    @override
    def get_checkout(self, key: MachineCheckoutKey) -> MachineCheckout | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT root FROM skm_host.checkouts
                WHERE installation_id = %s AND instance_id = %s AND host_id = %s AND checkout_id = %s
                """,
                _checkout_scope(key),
            ).fetchone()
        return None if row is None else MachineCheckout(key, Path(str(row[0])))

    @override
    def reserve_checkout(self, checkout: MachineCheckout) -> MachineCheckout:
        key = checkout.key
        if not checkout.root.is_absolute():
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Machine checkout root must be absolute")
        with self._connection() as conn:
            row = conn.execute(
                """
                INSERT INTO skm_host.checkouts (installation_id, instance_id, host_id, checkout_id, root)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (installation_id, instance_id, host_id, root) DO NOTHING RETURNING checkout_id
                """,
                (*_checkout_scope(key), str(checkout.root)),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT checkout_id FROM skm_host.checkouts
                    WHERE installation_id = %s AND instance_id = %s AND host_id = %s AND root = %s
                    """,
                    (key.installation_id, key.instance_id, key.host_id, str(checkout.root)),
                ).fetchone()
                if row is None:
                    raise InternalError(ErrorCode.INTERNAL_ERROR, "Reserved machine checkout is missing")
        return replace(checkout, key=replace(key, checkout_id=cast("UUID", row[0])))

    @override
    def get_binding(self, scope: MachinePrincipal, checkout: MachineCheckoutKey) -> MachineBinding | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT workspace_id, project_id, repository_id FROM skm_host.bindings
                WHERE installation_id = %s AND instance_id = %s AND host_id = %s
                  AND checkout_id = %s AND principal_id = %s
                """,
                _binding_scope(scope, checkout),
            ).fetchone()
        if row is None:
            return None
        workspace_id, project_id, repository_id = cast("tuple[UUID, UUID, UUID]", row)
        return MachineBinding(scope, checkout, workspace_id, project_id, repository_id)

    @override
    def put_binding(self, binding: MachineBinding) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO skm_host.bindings
                    (installation_id, instance_id, host_id, checkout_id, principal_id,
                     workspace_id, project_id, repository_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (installation_id, instance_id, host_id, checkout_id, principal_id)
                DO UPDATE SET workspace_id = EXCLUDED.workspace_id, project_id = EXCLUDED.project_id,
                              repository_id = EXCLUDED.repository_id
                """,
                (
                    *_binding_scope(binding.scope, binding.checkout),
                    binding.workspace_id,
                    binding.project_id,
                    binding.repository_id,
                ),
            )

    @override
    def get_retry(self, key: MachineRetryKey) -> MachineRetry | None:
        with self._connection() as conn:
            row = conn.execute(_SELECT_RETRY, _retry_scope(key)).fetchone()
        return None if row is None else _retry_from_row(key, row)

    @override
    def begin_retry(self, retry: MachineRetry) -> MachineRetry:
        key = retry.key
        values = _retry_scope(key)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO skm_host.retries
                    (installation_id, instance_id, host_id, checkout_id, principal_id,
                     operation, request_id, step, idempotency_key, payload, safe_until)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (installation_id, instance_id, host_id, checkout_id, principal_id,
                             operation, request_id, step)
                DO NOTHING
                """,
                (*values, retry.idempotency_key, jsonb_value(retry.payload), retry.safe_until),
            )
            row = conn.execute(_SELECT_RETRY, values).fetchone()
            if row is None:
                raise InternalError(ErrorCode.INTERNAL_ERROR, "Reserved machine retry is missing")
        persisted = _retry_from_row(key, row)
        if dumps_value(persisted.payload) != dumps_value(retry.payload):
            raise Conflict(ErrorCode.IDEMPOTENCY_KEY_REUSED, "Machine retry payload changed")
        return persisted

    @override
    def confirm_retry(self, key: MachineRetryKey, receipt: JsonObject) -> MachineRetry:
        values = _retry_scope(key)
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE skm_host.retries SET receipt = %s
                WHERE installation_id = %s AND instance_id = %s AND host_id = %s AND checkout_id = %s
                  AND principal_id = %s AND operation = %s AND request_id = %s AND step = %s
                  AND receipt IS NULL
                """,
                (jsonb_value(receipt), *values),
            )
            row = conn.execute(_SELECT_RETRY, values).fetchone()
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Machine retry was not reserved")
        persisted = _retry_from_row(key, row)
        if dumps_value(persisted.receipt) != dumps_value(receipt):
            raise Conflict(ErrorCode.IDEMPOTENCY_KEY_REUSED, "Machine retry receipt changed")
        return persisted
