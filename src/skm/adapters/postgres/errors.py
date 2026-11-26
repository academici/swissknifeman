"""SQLSTATE -> ``SkmError`` translation (adapters §1.7).

The table mirrors ``examples/adapters/postgres/sqlstate-map.json``. Messages are fixed text and never echo
the driver message, which may carry connection details or row values; only the named ``details`` keys are
copied from ``exc.diag``.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

import psycopg
import psycopg_pool

from skm.kernel.errors import SkmError, error_for
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.json_types import JsonValue

__all__ = ["translate_pg_error"]


@dataclass(frozen=True, slots=True)
class _Rule:
    code: ErrorCode
    retryable: bool
    message: str
    reason: str | None = None
    hint: str | None = None
    # names of the details copied from the driver diagnostics
    details: tuple[str, ...] = ()


_DB_FAILED: Final = "database rejected the statement"
_RESTRICT: Final = "23001"
_FOREIGN_KEY: Final = "23503"
_UNAVAILABLE: Final = "database backend is unavailable"
_NOT_MIGRATED: Final = "database schema is not migrated"

_BY_SQLSTATE: Final[Mapping[str, _Rule]] = {
    "23505": _Rule(ErrorCode.ALREADY_EXISTS, False, "unique constraint violated", details=("constraint",)),
    "23503": _Rule(ErrorCode.INVALID_REFERENCE, False, "foreign key violated", details=("constraint",)),
    "23514": _Rule(ErrorCode.SCHEMA_INVALID, False, "check constraint violated", details=("constraint",)),
    "23P01": _Rule(ErrorCode.ALREADY_EXISTS, False, "exclusion constraint violated", details=("constraint",)),
    "23502": _Rule(ErrorCode.INTERNAL_ERROR, False, "not-null constraint violated", details=("column",)),
    "22P02": _Rule(ErrorCode.SCHEMA_INVALID, False, "invalid text representation"),
    "22007": _Rule(ErrorCode.SCHEMA_INVALID, False, "invalid datetime format"),
    "22008": _Rule(ErrorCode.SCHEMA_INVALID, False, "datetime field overflow"),
    "22003": _Rule(ErrorCode.SCHEMA_INVALID, False, "numeric value out of range"),
    "40001": _Rule(ErrorCode.SERIALIZATION_FAILURE, True, "serialization failure"),
    "40P01": _Rule(ErrorCode.SERIALIZATION_FAILURE, True, "deadlock detected"),
    "55P03": _Rule(ErrorCode.SERIALIZATION_FAILURE, True, "lock not available", reason="lock_timeout"),
    "57014": _Rule(ErrorCode.BACKEND_UNAVAILABLE, True, "statement canceled", reason="statement_timeout"),
    "57P01": _Rule(ErrorCode.BACKEND_UNAVAILABLE, True, _UNAVAILABLE),
    "57P02": _Rule(ErrorCode.BACKEND_UNAVAILABLE, True, _UNAVAILABLE),
    "57P03": _Rule(ErrorCode.BACKEND_UNAVAILABLE, True, _UNAVAILABLE),
    "42P01": _Rule(ErrorCode.SCHEMA_NOT_MIGRATED, False, _NOT_MIGRATED, hint="skm db migrate"),
    "42703": _Rule(ErrorCode.SCHEMA_NOT_MIGRATED, False, _NOT_MIGRATED, hint="skm db migrate"),
    "3F000": _Rule(ErrorCode.SCHEMA_NOT_MIGRATED, False, _NOT_MIGRATED, hint="skm db migrate"),
    "42501": _Rule(ErrorCode.INTERNAL_ERROR, False, "insufficient database privilege", reason="db_privilege"),
    "P0001": _Rule(
        ErrorCode.INTERNAL_ERROR, False, "database trigger rejected the change", details=("trigger_message",)
    ),
}
_BY_CLASS: Final[Mapping[str, _Rule]] = {
    "08": _Rule(ErrorCode.BACKEND_UNAVAILABLE, True, _UNAVAILABLE),
    "53": _Rule(ErrorCode.BACKEND_UNAVAILABLE, True, _UNAVAILABLE),
}
_OPERATIONAL: Final = _Rule(ErrorCode.BACKEND_UNAVAILABLE, True, _UNAVAILABLE)
_POOL_TIMEOUT: Final = _Rule(
    ErrorCode.BACKEND_UNAVAILABLE, True, "no database connection became free in time", reason="pool_timeout"
)
_DEFAULT: Final = _Rule(ErrorCode.INTERNAL_ERROR, False, _DB_FAILED)

_DIAG: Final[Mapping[str, Callable[[psycopg.errors.Diagnostic], str | None]]] = {
    "constraint": lambda diag: diag.constraint_name,
    "column": lambda diag: diag.column_name,
    "trigger_message": lambda diag: diag.message_primary,
}


def _build(
    rule: _Rule, exc: BaseException, *, sqlstate: str | None, diag: psycopg.errors.Diagnostic | None
) -> SkmError:
    details: dict[str, JsonValue] = {}
    if rule.reason is not None:
        details["reason"] = rule.reason
    if rule.hint is not None:
        details["hint"] = rule.hint
    for name in rule.details:
        value = _DIAG[name](diag) if diag is not None else None
        if value is not None:
            details[name] = value
    if rule is _DEFAULT and sqlstate is not None:
        details["sqlstate"] = sqlstate
    error = error_for(rule.code, rule.message, details=details, retryable=rule.retryable)
    error.__cause__ = exc
    return error


def translate_pg_error(exc: psycopg.Error | psycopg_pool.PoolTimeout) -> SkmError:
    """Map a driver error to the canonical ``SkmError``; the driver exception stays as ``__cause__``."""
    if isinstance(exc, psycopg_pool.PoolTimeout):
        return _build(_POOL_TIMEOUT, exc, sqlstate=None, diag=None)
    sqlstate = exc.sqlstate
    if sqlstate is None:
        rule = _OPERATIONAL if isinstance(exc, psycopg.OperationalError) else _DEFAULT
        return _build(rule, exc, sqlstate=None, diag=None)
    if sqlstate == _RESTRICT and exc.diag.constraint_name is not None:
        # Newer servers report an ON DELETE/UPDATE RESTRICT key as restrict_violation; a trigger's
        # restrict_violation names no constraint and stays a database failure.
        sqlstate = _FOREIGN_KEY
    rule = _BY_SQLSTATE.get(sqlstate) or _BY_CLASS.get(sqlstate[:2]) or _DEFAULT
    return _build(rule, exc, sqlstate=sqlstate, diag=exc.diag)
