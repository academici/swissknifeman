"""Keyset pagination (adapters §1.9): cursors are bound to the filter that produced them."""

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from skm.adapters.postgres.jsonb import canonical_dumps
from skm.kernel.errors import ValidationFailed
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.pagination import CURSOR_MAX_LENGTH, DEFAULT_PAGE_LIMIT, Page
from skm.kernel.pagination import Cursor as OpaqueCursor

__all__ = [
    "MAX_LIMIT",
    "decode_cursor",
    "encode_cursor",
    "keyset_clause",
    "page_of",
    "query_digest",
    "validate_limit",
]

MAX_LIMIT: Final = 200
_IDENTIFIER: Final = re.compile(r"[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?")
_DIGEST: Final = re.compile(r"[0-9a-f]{16}")


@dataclass(frozen=True, slots=True)
class Cursor:
    sort_values: tuple[str | int, ...]  # sort columns of the last returned row, timestamps as ISO strings
    query_digest: str  # first 16 hex of the digest of the normalized filter


def _bad_cursor(reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "cursor is not valid for this query",
        details={"field": "after", "reason": reason},
    )


def query_digest(filters: Mapping[str, object]) -> str:
    """Digest of the normalized filter parameters; the caller drops ``after`` and ``limit`` first."""
    return hashlib.sha256(canonical_dumps(dict(filters)).encode("utf-8")).hexdigest()[:16]


def encode_cursor(cursor: Cursor) -> str:
    if _DIGEST.fullmatch(cursor.query_digest) is None:
        raise ValueError("query digest must be 16 lowercase hex characters")
    payload = canonical_dumps({"v": 1, "k": list(cursor.sort_values), "q": cursor.query_digest})
    text = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    if len(text) > CURSOR_MAX_LENGTH:
        raise ValueError(f"encoded cursor exceeds {CURSOR_MAX_LENGTH} characters")
    return text


def decode_cursor(text: str, *, expected_query_digest: str) -> Cursor:
    """Parse a cursor; any defect or a digest of another filter is ``SCHEMA_INVALID`` with ``field=after``."""
    if not 1 <= len(text) <= CURSOR_MAX_LENGTH or not text.isascii():
        raise _bad_cursor("malformed")
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        document: object = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise _bad_cursor("malformed") from None
    if not isinstance(document, dict):
        raise _bad_cursor("malformed")
    body = cast("dict[str, object]", document)
    keys = body.get("k")
    digest = body.get("q")
    if body.keys() != {"v", "k", "q"} or body["v"] != 1 or isinstance(body["v"], bool):
        raise _bad_cursor("malformed")
    if not isinstance(keys, list) or not keys or not isinstance(digest, str):
        raise _bad_cursor("malformed")
    values = cast("list[object]", keys)
    if any(isinstance(v, bool) or not isinstance(v, str | int) for v in values):
        raise _bad_cursor("malformed")
    if digest != expected_query_digest:
        raise _bad_cursor("query_mismatch")
    return Cursor(tuple(cast("list[str | int]", values)), digest)


def keyset_clause(
    columns: Sequence[str], cursor: Cursor | None, *, descending: bool = True
) -> tuple[str, tuple[str | int, ...]]:
    """Row-comparison condition continuing after ``cursor``; ``("TRUE", ())`` for the first page.

    ``columns`` are trusted code constants (validated as identifiers), values travel as ``%s`` parameters. The
    ORDER BY must list the same columns, the last of them unique (``id``), all in one direction.
    """
    if not columns or any(_IDENTIFIER.fullmatch(c) is None for c in columns):
        raise ValueError("keyset columns must be non-empty plain identifiers")
    if cursor is None:
        return "TRUE", ()
    if len(cursor.sort_values) != len(columns):
        raise _bad_cursor("key_mismatch")
    operator = "<" if descending else ">"
    marks = ", ".join("%s" for _ in columns)
    return f"({', '.join(columns)}) {operator} ({marks})", cursor.sort_values


def validate_limit(limit: int | None) -> int:
    """``None`` -> default 50; above ``MAX_LIMIT`` or below 1 -> ``SCHEMA_INVALID`` (``field=limit``)."""
    if limit is None:
        return DEFAULT_PAGE_LIMIT
    if isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, f"limit must be between 1 and {MAX_LIMIT}", details={"field": "limit"}
        )
    return limit


def page_of[T](
    rows: Sequence[T], *, limit: int, digest: str, key_of: Callable[[T], tuple[str | int, ...]]
) -> Page[T]:
    """Build a page from the ``limit + 1`` rows that were queried; an extra row yields ``next`` from row
    ``limit``."""
    if len(rows) <= limit:
        return Page(items=tuple(rows), next=None)
    items = tuple(rows[:limit])
    return Page(items=items, next=OpaqueCursor(encode_cursor(Cursor(key_of(items[-1]), digest))))
