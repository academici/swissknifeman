"""``ConfigStore`` and ``ScopeTree`` over ``skm_config`` and ``skm_core.scopes`` (settings §B.10, §A.11).

Both are constructed per unit of work over its connection (``uow.repo(ConfigStore)``), so the resolver of a
settings command sees the uncommitted entries of its own transaction; they never commit or close it.
``PostgresScopeTree`` is the scope tree of ``adapters/postgres/core/scopes.py`` (one ``WITH RECURSIVE`` query
per chain); labels are ``instance`` and ``<level>:<id>`` until the scope owners add ``skm_core.scope_labels``.

``pending_writes`` answers whether the current transaction changed configuration it has not committed yet:
every writer of ``adapters/postgres/settings`` calls ``mark_pending`` (a transaction-local setting, gone at
COMMIT or ROLLBACK and undone with a rolled-back savepoint), and an update of the generation row by the top
transaction counts even without the mark (its ``xmin`` is the current transaction id). A read-only
transaction never has an id, so it never has pending writes.

This module also defines the JSON form of stored values once for every ``skm_config`` reader and writer.
Values enter ``jsonb`` through ``jsonb_value`` and leave as ``value::text`` read by ``loads_value``, so a
stored value reads back as the same JSON value of the same type: a float keeps a fraction (``jsonb`` prints a
numeric without an exponent, so ``1e16`` would come back as an integer; it is written positionally with
``.0``, which the numeric keeps), and an integer of any width (``int_text``) is written and read without the
interpreter's int-to-text limit. A row that does not fit the domain types is storage damage: readers raise
``INTERNAL_ERROR`` and never guess a value.
"""

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Final, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from skm.adapters.postgres.core.scopes import PostgresScopeTree
from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.json_types import JsonValue
from skm.modules.settings.domain.entry import int_text
from skm.platform.config.store import StoredContribution, StoredOp

__all__ = [
    "PostgresConfigStore",
    "PostgresScopeTree",
    "damaged_row",
    "dumps_value",
    "generation_row_missing",
    "jsonb_value",
    "loads_value",
    "mark_pending",
]

_MARK: Final = "SELECT set_config('skm.config_pending', 'on', true)"
_GENERATION: Final = "SELECT value FROM skm_config.generation WHERE id = 1"
# xmin is 32 bits; the transaction id of pg_current_xact_id_if_assigned() carries the epoch above them.
_PENDING: Final = """
SELECT coalesce(current_setting('skm.config_pending', true), '') = 'on'
       OR coalesce(xmin::text = (pg_current_xact_id_if_assigned()::text::bigint % 4294967296)::text, false)
  FROM skm_config.generation WHERE id = 1
"""
_ENTRIES_FOR: Final = (
    "SELECT id, scope_id, key, op, value::text, locked, row_version FROM skm_config.entries "
    'WHERE scope_id = ANY(%s) ORDER BY scope_id, key COLLATE "C"'
)
_INT_CHUNK: Final = 512  # digits per int() call, far below any int-to-text limit (at least 640)
_OPS: Final = frozenset({"set", "unset", "append"})


# ---------------------------------------------------------------------------------------------- values
def _float_text(value: float) -> str:
    text = float.__repr__(value)
    if "e" not in text:
        return text
    positional = format(Decimal(text), "f")  # the exact digits of the shortest repr, without an exponent
    return positional if "." in positional else positional + ".0"


def _pieces(value: object, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif isinstance(value, bool):
        out.append("true" if value else "false")
    elif isinstance(value, int):
        out.append(int_text(value))
    elif isinstance(value, float):
        out.append(_float_text(value))
    elif isinstance(value, str):
        out.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, list | tuple):
        out.append("[")
        for index, item in enumerate(cast("Sequence[object]", value)):
            if index:
                out.append(",")
            _pieces(item, out)
        out.append("]")
    elif isinstance(value, dict):
        mapping = cast("dict[str, object]", value)
        out.append("{")
        for index, name in enumerate(sorted(mapping)):
            out.append(("," if index else "") + json.dumps(name, ensure_ascii=False) + ":")
            _pieces(mapping[name], out)
        out.append("}")
    else:
        raise TypeError(f"{type(value).__name__} is not a JSON value")


def dumps_value(value: object) -> str:
    """JSON text of a ``jsonb`` parameter: sorted keys, integers of any width, floats with a fraction."""
    out: list[str] = []
    _pieces(value, out)
    return "".join(out)


def jsonb_value(value: JsonValue | None) -> Jsonb | None:
    """The ``jsonb`` parameter of a value; ``None`` stays SQL NULL (an unset entry carries no value)."""
    return None if value is None else Jsonb(value, dumps=dumps_value)


def _parse_int(text: str) -> int:
    negative = text.startswith("-")
    digits = text[1:] if negative else text
    number = 0
    for start in range(0, len(digits), _INT_CHUNK):
        part = digits[start : start + _INT_CHUNK]
        number = number * 10 ** len(part) + int(part)
    return -number if negative else number


def loads_value(text: str | None) -> JsonValue | None:
    """The JSON value of ``jsonb::text``; ``None`` for SQL NULL."""
    if text is None:
        return None
    return cast("JsonValue", json.loads(text, parse_int=_parse_int))


def damaged_row(table: str, row_id: object, exc: Exception) -> InternalError:
    error = InternalError(
        ErrorCode.INTERNAL_ERROR,
        f"skm_config.{table} row is malformed",
        details={"table": f"skm_config.{table}", "id": str(row_id)},
    )
    error.__cause__ = exc
    return error


def generation_row_missing() -> InternalError:
    """The singleton row of ``skm_config.generation`` is seeded by 0005 and cannot be deleted (trigger)."""
    return InternalError(
        ErrorCode.INTERNAL_ERROR,
        "the config generation row is missing",
        details={"table": "skm_config.generation"},
    )


def mark_pending(conn: psycopg.Connection) -> None:
    """Note in the current transaction that it changed configuration (read by ``pending_writes``)."""
    try:
        conn.execute(_MARK)
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def _stored(row: Sequence[object]) -> StoredContribution:
    try:
        op = cast("str", row[3])
        if op not in _OPS:
            raise ValueError("unknown op")
        return StoredContribution(
            entry_id=cast("UUID", row[0]),
            key=cast("str", row[2]),
            op=cast("StoredOp", op),
            value=loads_value(cast("str | None", row[4])),
            locked=cast("bool", row[5]),
            row_version=cast("int", row[6]),
        )
    except (TypeError, ValueError) as exc:
        raise damaged_row("entries", row[0], exc) from exc


# ---------------------------------------------------------------------------------------------- store
class PostgresConfigStore:
    """Read side of ``skm_config`` for the resolver, on the connection of one unit of work."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def generation(self) -> int:
        try:
            row = self._conn.execute(_GENERATION).fetchone()
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
        if row is None:
            raise generation_row_missing()
        return cast("int", row[0])

    def pending_writes(self) -> bool:
        try:
            row = self._conn.execute(_PENDING).fetchone()
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
        if row is None:
            raise generation_row_missing()
        return bool(row[0])

    def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, StoredContribution]]:
        wanted = list(dict.fromkeys(scope_ids))
        if not wanted:
            return {}
        try:
            rows = self._conn.execute(_ENTRIES_FOR, (wanted,)).fetchall()
        except psycopg.Error as exc:
            raise translate_pg_error(exc) from exc
        found: dict[UUID, dict[str, StoredContribution]] = {}
        for row in rows:
            contribution = _stored(row)
            found.setdefault(cast("UUID", row[1]), {})[contribution.key] = contribution
        return found
