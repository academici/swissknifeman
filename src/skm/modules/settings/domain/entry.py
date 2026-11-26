"""Stored contribution of one level: a row of ``skm_config.entries`` (settings §A.4).

An entry is an immutable value. Every change goes through ``new_entry``/``change_entry``/``set_lock``, which
bump ``row_version`` by exactly one; the repository writes the result conditionally on the version that was
read (CAS, §A.11), so a value change with a lock change saves that version + 2. ``same_content`` is the
strict no-op test of R15: a float is not the integer it equals and a boolean is not a number, so "no change"
also means "the entries digest does not change" (``digest.py``). A stored value is any JSON value of at most
64 KiB canonical JSON (§A.4, ``value_issue``): a request may carry any JSON value and R5 reports it, an entry
refuses it. ``canonical_json`` writes integers of any width without the interpreter's int-to-text limit, so
the size and the digest of a value do not depend on ``sys.set_int_max_str_digits``.
"""

import json
import math
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Final, NewType, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ids import PrincipalId
from skm.kernel.json_types import JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef

__all__ = [
    "KEY_PATTERN",
    "LOCK_SCOPE_KINDS",
    "REASON_MAX_LENGTH",
    "VALUE_MAX_BYTES",
    "ConfigEntry",
    "ConfigEntryId",
    "EntryOp",
    "canonical_json",
    "change_entry",
    "check_op_value",
    "copy_value",
    "int_text",
    "new_entry",
    "same_content",
    "same_value",
    "set_lock",
    "value_issue",
    "version_conflict",
]

KEY_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}")
REASON_MAX_LENGTH: Final = 2000
LOCK_SCOPE_KINDS: Final = frozenset({ScopeKind.INSTANCE, ScopeKind.WORKSPACE})
VALUE_MAX_BYTES: Final = 65536  # canonical JSON of a stored value, UTF-8 (§A.4, ck_entries__value_size)
# The int-to-text limit of an interpreter is 0 (off) or at least sys.int_info.str_digits_check_threshold
# (640 digits), so ``str`` of a part below 10**512 is never refused: a wider integer is written part by part.
_INT_PART_DIGITS: Final = 512
_INT_PART: Final = 10**_INT_PART_DIGITS
_SURROGATE: Final = re.compile("[\ud800-\udfff]")


class EntryOp(StrEnum):
    SET = "set"  # value of the level (deep_merge: a partial map, may hold {"$unset": true})
    UNSET = "unset"  # reset to the default on this level: farther contributions except default are hidden
    APPEND = "append"  # append items to the farther result (array keys with merge=replace only)


ConfigEntryId = NewType("ConfigEntryId", UUID)


def copy_value(value: object, path: str = "value") -> JsonValue:
    """Plain deep copy of a JSON value; ``TypeError`` for anything that is not JSON (NaN, tuple, set)."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{path}: non-finite float is not JSON")
        return value
    if isinstance(value, list):
        return [
            copy_value(item, f"{path}[{index}]") for index, item in enumerate(cast("list[object]", value))
        ]
    if isinstance(value, Mapping):
        copied: dict[str, JsonValue] = {}
        for key, item in cast("Mapping[object, object]", value).items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: object keys must be strings")
            copied[key] = copy_value(item, f"{path}.{key}")
        return copied
    raise TypeError(f"{path}: {type(value).__name__} is not a JSON value")


def int_text(value: int) -> str:
    """Decimal text of an integer as ``json`` writes it, of any width and under any int-to-text limit."""
    number = int(value)
    if -_INT_PART < number < _INT_PART:
        return str(number)
    rest, parts = abs(number), list[str]()
    while rest >= _INT_PART:
        rest, part = divmod(rest, _INT_PART)
        parts.append(str(part).zfill(_INT_PART_DIGITS))
    parts.append(("-" if number < 0 else "") + str(rest))
    return "".join(reversed(parts))


def _min_digits(number: int) -> int:
    """A lower bound of the decimal digits of ``number``, read from its bit length (log10(2) > 0.30102)."""
    return (abs(number).bit_length() - 1) * 30102 // 100000 + 1


def _pieces(value: object) -> Iterator[str | int]:
    """Canonical JSON text in order; an integer stays a number, so a reader may bound it before writing it."""
    if value is None:
        yield "null"
    elif isinstance(value, bool):
        yield "true" if value else "false"
    elif isinstance(value, int):
        yield value
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is not JSON")
        yield float.__repr__(value)
    elif isinstance(value, str):
        yield json.dumps(value, ensure_ascii=False)
    elif isinstance(value, list | tuple):
        yield "["
        for index, item in enumerate(cast("list[object]", value)):
            if index:
                yield ","
            yield from _pieces(item)
        yield "]"
    elif isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        if not all(isinstance(name, str) for name in mapping):
            raise TypeError("object keys must be strings")
        yield "{"
        for index, name in enumerate(sorted(cast("dict[str, object]", mapping))):
            yield ("," if index else "") + json.dumps(name, ensure_ascii=False) + ":"
            yield from _pieces(mapping[name])
        yield "}"
    else:
        raise TypeError(f"{type(value).__name__} is not a JSON value")


def canonical_json(value: object) -> str:
    """Canonical JSON v1 text, as ``json.dumps(value, sort_keys=True, separators=(",", ":"),
    ensure_ascii=False)`` writes it, with integers of any width (``int_text``); NaN is a ``ValueError``."""
    return "".join(piece if isinstance(piece, str) else int_text(piece) for piece in _pieces(value))


def _oversized(value: JsonValue) -> bool:
    """Canonical JSON of ``value`` takes more than ``VALUE_MAX_BYTES``; the count stops at the bound, so an
    integer far beyond it is never written out."""
    room = VALUE_MAX_BYTES
    for piece in _pieces(value):
        if isinstance(piece, int):
            if _min_digits(piece) > room:
                return True
            piece = int_text(piece)  # noqa: PLW2901 -- the number becomes its text
        room -= len(piece.encode("utf-8"))
        if room < 0:
            return True
    return False


def _surrogate(value: JsonValue | None, pointer: str) -> tuple[str, str, str] | None:
    if isinstance(value, str):
        if _SURROGATE.search(value) is None:
            return None
        return pointer, "lone_surrogate", "a string holds a lone surrogate, which is not UTF-8 text"
    if isinstance(value, list):
        children = ((str(index), item) for index, item in enumerate(value))
    elif isinstance(value, dict):
        if any(_SURROGATE.search(name) is not None for name in value):
            return pointer, "lone_surrogate", "an object key holds a lone surrogate, which is not UTF-8 text"
        children = ((name.replace("~", "~0").replace("/", "~1"), item) for name, item in value.items())
    else:
        return None
    for name, item in children:
        found = _surrogate(item, f"{pointer}/{name}")
        if found is not None:
            return found
    return None


def value_issue(value: JsonValue | None) -> tuple[str, str, str] | None:
    """Why a JSON value cannot be stored, as ``(pointer, code, message)``; ``None`` when it can.

    A lone surrogate (a string or an object key, for example a parsed ``"\\ud800"`` escape) has no UTF-8
    form; canonical JSON of the value may take at most ``VALUE_MAX_BYTES`` (any JSON value, any integer
    width within it). The message never quotes the value and the pointer never holds the refused key.
    """
    found = _surrogate(value, "")
    if found is not None:
        return found
    if value is not None and _oversized(value):
        return "", "maxSize", f"canonical JSON of the value takes more than {VALUE_MAX_BYTES} bytes"
    return None


def _strict(value: JsonValue) -> tuple[object, ...]:
    """Type-tagged identity: bool, int and float are distinct, objects compare by content."""
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", repr(value))
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, list):
        return ("list", tuple(_strict(item) for item in value))
    return ("object", tuple(sorted((key, _strict(item)) for key, item in value.items())))


def same_value(left: JsonValue, right: JsonValue) -> bool:
    """Strict JSON identity used for no-op detection and import diffs."""
    return _strict(left) == _strict(right)


def version_conflict(expected: int, actual: int) -> Conflict:
    """``Conflict(VERSION_CONFLICT, {expected, actual})``; ``actual = 0`` without an entry (R11, CAS)."""
    return Conflict(
        ErrorCode.VERSION_CONFLICT,
        "the config entry was changed concurrently",
        details={"expected": expected, "actual": actual},
    )


def _version(value: object, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def _reason(value: object) -> str:
    if not isinstance(value, str) or len(value) > REASON_MAX_LENGTH:
        raise ValueError(f"reason must be a string of at most {REASON_MAX_LENGTH} characters")
    return value


def check_op_value(op: EntryOp, value: object) -> None:
    """``None ⇔ UNSET`` and ``APPEND ⇒ array`` (``ck_entries__op_value``, ``ck_entries__append_array``); the
    value is storable canonical JSON (``value_issue``, ``ck_entries__value_size``), so its digest exists."""
    if (op is EntryOp.UNSET) != (value is None):
        raise ValueError("value is None exactly for op=unset")
    if op is EntryOp.APPEND and not isinstance(value, list):
        raise ValueError("op=append carries an array")
    found = value_issue(cast("JsonValue", value))
    if found is not None:
        pointer, _code, message = found
        raise ValueError(f"value at {pointer!r} is not storable canonical JSON: {message}")


@dataclass(frozen=True, slots=True)
class ConfigEntry:
    id: ConfigEntryId
    scope: ScopeRef  # kind ∈ stored levels, id: the scope UUID (instance: id of the instance scope)
    key: str  # ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$
    op: EntryOp
    value: JsonValue | None  # None ⇔ op = UNSET
    locked: bool
    row_version: int  # ≥ 1
    reason: str  # ≤ 2000 characters
    created_by: PrincipalId
    created_at: datetime
    updated_by: PrincipalId
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.id), UUID):
            raise TypeError("id must be a UUID")
        if not isinstance(cast("object", self.scope), ScopeRef):
            raise TypeError("scope must be a ScopeRef")
        if not isinstance(cast("object", self.key), str) or KEY_PATTERN.fullmatch(self.key) is None:
            raise ValueError(f"invalid settings key {self.key!r}")
        op = EntryOp(self.op)
        value = copy_value(self.value)
        check_op_value(op, value)
        if not isinstance(cast("object", self.locked), bool):
            raise TypeError("locked must be a bool")
        _version(self.row_version, "row_version", 1)
        _reason(self.reason)
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        object.__setattr__(self, "op", op)
        object.__setattr__(self, "value", value)


def _lockable_scope(scope: ScopeRef, locked: bool) -> None:
    if locked and scope.kind not in LOCK_SCOPE_KINDS:
        raise ValueError("only instance and workspace entries can be locked")


def new_entry(  # noqa: PLR0913 -- signature fixed by settings §A.4
    *,
    entry_id: ConfigEntryId,
    scope: ScopeRef,
    key: str,
    op: EntryOp,
    value: JsonValue | None,
    locked: bool,
    reason: str,
    actor: PrincipalId,
    now: datetime,
) -> ConfigEntry:
    """A new entry with ``row_version = 1``."""
    _lockable_scope(scope, locked)
    return ConfigEntry(
        id=entry_id,
        scope=scope,
        key=key,
        op=op,
        value=value,
        locked=locked,
        row_version=1,
        reason=reason,
        created_by=actor,
        created_at=now,
        updated_by=actor,
        updated_at=now,
    )


def change_entry(
    entry: ConfigEntry,
    *,
    op: EntryOp,
    value: JsonValue | None,
    reason: str,
    actor: PrincipalId,
    now: datetime,
) -> ConfigEntry:
    """New operation and value; ``row_version + 1``; ``locked`` and the creation stamp are kept."""
    return replace(
        entry,
        op=op,
        value=value,
        row_version=entry.row_version + 1,
        reason=reason,
        updated_by=actor,
        updated_at=now,
    )


def set_lock(
    entry: ConfigEntry, *, locked: bool, reason: str, actor: PrincipalId, now: datetime
) -> ConfigEntry:
    """Lock or unlock; ``row_version + 1``. An unchanged flag is the caller's no-op, not a new version."""
    if not isinstance(cast("object", locked), bool):
        raise TypeError("locked must be a bool")
    if locked == entry.locked:
        raise ValueError("the lock flag does not change: handle it as a no-op")
    _lockable_scope(entry.scope, locked)
    return replace(
        entry,
        locked=locked,
        row_version=entry.row_version + 1,
        reason=reason,
        updated_by=actor,
        updated_at=now,
    )


def same_content(entry: ConfigEntry, op: EntryOp, value: JsonValue | None, locked: bool) -> bool:
    """R15: the entry already holds this operation, value and lock flag (nothing is written)."""
    return entry.op == op and entry.locked is locked and same_value(entry.value, value)
