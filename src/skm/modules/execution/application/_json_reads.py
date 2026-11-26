"""Typed reads of JSON that execution writes itself: views, stage outcomes, admissions and step facts.

These documents are validated when they are written, so a value of the wrong shape is an internal
defect rather than bad input; it is reported as ``INTERNAL_ERROR`` naming the field. Records may hold
these documents frozen (read-only mappings and tuples), so plain and frozen shapes read the same.
"""

from collections.abc import Mapping, Sequence
from typing import cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError
from skm.kernel.json_types import JsonValue


def _defect(field: str, expected: str) -> InternalError:
    return InternalError(
        ErrorCode.INTERNAL_ERROR,
        f"stored execution document field '{field}' is not {expected}",
        details={"field": field, "expected": expected},
    )


def obj(value: object, field: str) -> Mapping[str, JsonValue]:
    """A JSON object, plain or frozen (records hold their documents as read-only mappings)."""
    if isinstance(value, Mapping):
        return cast("Mapping[str, JsonValue]", value)
    raise _defect(field, "an object")


def _array(value: object, field: str) -> Sequence[object]:
    if isinstance(value, list | tuple):
        return cast("Sequence[object]", value)
    raise _defect(field, "an array")


def objects(value: object, field: str) -> list[Mapping[str, JsonValue]]:
    """A JSON array of objects; an absent (``None``) array reads as empty."""
    return [] if value is None else [obj(item, field) for item in _array(value, field)]


def texts(value: object, field: str) -> list[str]:
    """A JSON array of strings; an absent (``None``) array reads as empty."""
    return [] if value is None else [text(item, field) for item in _array(value, field)]


def text(value: object, field: str) -> str:
    if isinstance(value, str):
        return value
    raise _defect(field, "a string")


def optional_text(value: object, field: str) -> str | None:
    return None if value is None else text(value, field)


def integer(value: object, field: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise _defect(field, "an integer")
