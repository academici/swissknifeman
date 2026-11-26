"""Shared helpers of the policy PostgreSQL adapters (policy §6, §11; DDL ``0012``).

Each adapter module keeps its SQL and its row mapping next to each other; this module holds what they share:
driver errors through ``translate_pg_error``, the errors of the memory adapter (``NOT_FOUND``,
``VERSION_CONFLICT``), storage damage and cursor keysets bound to their filter. Keysets ascend by
``(created_at, id)``; timestamps travel as ISO strings with their offset.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.pagination import decode_cursor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed

__all__ = ["Row", "damaged", "ensure_kept", "keyset", "not_found", "run", "time_key", "version_conflict"]

type Row = tuple[object, ...]


def run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def damaged(table: str, ref: object, exc: Exception) -> InternalError:
    """A row that does not fit the domain value is storage damage (``INTERNAL_ERROR``)."""
    error = InternalError(
        ErrorCode.INTERNAL_ERROR,
        f"skm_policy.{table} row is malformed",
        details={"table": f"skm_policy.{table}", "id": str(ref)},
    )
    error.__cause__ = exc
    return error


def not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


def version_conflict(kind: str, expected: int, actual: int) -> Conflict:
    return Conflict(
        ErrorCode.VERSION_CONFLICT,
        f"version conflict: expected {expected}, actual {actual}",
        details={"kind": kind, "expected": expected, "actual": actual},
    )


def time_key(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    if moment.utcoffset() is None:  # a naive time cannot be ordered against timestamptz
        raise ValueError("naive cursor time")
    return moment


def keyset(
    after: str | None, digest: str, first: Callable[[str], datetime]
) -> tuple[datetime | None, UUID | None]:
    """The keyset ``(created_at, id)`` of ``after``; ``(None, None)`` for the first page.

    A cursor of another filter (another workspace, scope or state) is ``SCHEMA_INVALID`` (``field=after``).
    """
    if after is None:
        return None, None
    values = decode_cursor(after, expected_query_digest=digest).sort_values
    if len(values) != 2 or not all(isinstance(value, str) for value in values):
        raise _bad_cursor()
    texts = cast("tuple[str, str]", values)
    try:
        return first(texts[0]), UUID(texts[1])
    except ValueError as exc:
        raise _bad_cursor() from exc


def _bad_cursor() -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"})


def ensure_kept(kind: str, current: object, after: object, fields: Sequence[str]) -> None:
    """``save`` guard: the identity and the arguments of a stored value are never rewritten."""
    changed = [name for name in fields if getattr(current, name) != getattr(after, name)]
    if changed:
        raise ValueError(f"a stored {kind} keeps its {', '.join(changed)}")
