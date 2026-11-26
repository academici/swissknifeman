"""Canonical JSON v1 for content identity, independent of document rendering.

Ported from aicore/util/digest.py. Callers convert timestamps, decimals and
identifiers before canonicalization; floats are never accepted by the core.
"""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, cast

__all__ = [
    "CANONICALIZATION_VERSION",
    "InvalidUnicodeError",
    "canonical_bytes",
    "canonical_value",
    "format_decimal",
    "format_timestamp",
]

CANONICALIZATION_VERSION: Final = 1


class InvalidUnicodeError(ValueError):
    """A string (value or object key) is not valid Unicode text, e.g. holds an unpaired surrogate.

    Canonical JSON is UTF-8 and cannot carry such a string; it is a property of the caller's data, so the
    message never repeats the offending text.
    """


def _require_text(text: str) -> str:
    if not text.isascii():
        try:
            text.encode("utf-8")
        except UnicodeEncodeError:
            raise InvalidUnicodeError("canonical JSON strings must be valid Unicode text") from None
    return text


def canonical_value(value: object) -> object:
    """Sort mapping keys and convert arrays to tuples, preserving legacy rules."""
    if isinstance(value, str):
        return _require_text(value)
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, float):
        raise TypeError("canonical JSON values must not use floats")
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        if not all(isinstance(key, str) for key in mapping):
            raise TypeError("canonical JSON object keys must be strings")
        for key in cast(Mapping[str, object], mapping):
            _require_text(key)
        return {key: canonical_value(item) for key, item in sorted(mapping.items())}
    if isinstance(value, (tuple, list)):
        return tuple(canonical_value(item) for item in cast(tuple[object, ...] | list[object], value))
    raise TypeError("value is not canonical JSON data")


def canonical_bytes(value: object) -> bytes:
    """Serialize canonical data as compact UTF-8, without a BOM or newline."""
    return json.dumps(
        canonical_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def format_timestamp(value: datetime) -> str:
    """Render an aware datetime in UTC with six fractional digits and Z."""
    if value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def format_decimal(value: Decimal) -> str:
    """Render a finite decimal without an exponent or fractional trailing zeros."""
    if not value.is_finite():
        raise ValueError("decimal must be finite")
    # Equivalent to normalize() in fixed notation without rounding to the
    # ambient Decimal context's precision (which must not change identity).
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
