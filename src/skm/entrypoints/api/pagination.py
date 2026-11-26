"""Bounded canonical base64url keyset cursors (API §2.2)."""

import base64
import binascii
import json
import re
from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, MIN_PAGE_LIMIT
from skm.platform.schema.registry import SchemaRegistry

__all__ = ["CURSOR_MAX_LENGTH", "PAGE_SCHEMA_URN", "decode_cursor", "encode_cursor", "page"]

CURSOR_MAX_LENGTH = 512
PAGE_SCHEMA_URN = "urn:skm:api:page:v1"


def encode_cursor(sort_key: Sequence[str | int], id: str | UUID) -> str:
    keys = list(sort_key)
    if not keys or any(type(k) not in {str, int} for k in keys):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid cursor sort key")
    try:
        identifier = str(UUID(str(id)))
    except ValueError as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid cursor id") from exc
    raw = json.dumps({"k": keys, "id": identifier}, ensure_ascii=False, separators=(",", ":")).encode()
    cursor = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    if len(cursor) > CURSOR_MAX_LENGTH:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Cursor exceeds limit")
    return cursor


def decode_cursor(cursor: str) -> tuple[tuple[str | int, ...], str]:
    try:
        if not 0 < len(cursor) <= CURSOR_MAX_LENGTH or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
            raise ValueError("Invalid cursor encoding")
        value = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if not isinstance(value, dict):
            raise ValueError("Invalid cursor shape")
        value = cast("dict[str, Any]", value)
        if set(value) != {"k", "id"} or not isinstance(value["k"], list):
            raise ValueError("Invalid cursor shape")
        if encode_cursor(cast("list[str | int]", value["k"]), value["id"]) != cursor:
            raise ValueError("Non-canonical cursor")
        return tuple(cast("list[str | int]", value["k"])), value["id"]
    except (ValueError, TypeError, UnicodeError, binascii.Error) as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid pagination cursor") from exc


def page(
    items: list[Any],
    next_cursor: str | None,
    limit: int = DEFAULT_PAGE_LIMIT,
    *,
    max_limit: int = MAX_PAGE_LIMIT,
) -> dict[str, Any]:
    if type(limit) is not int or not MIN_PAGE_LIMIT <= limit <= max_limit:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid page limit", details={"field": "limit"})
    if next_cursor is not None:
        decode_cursor(next_cursor)
    result = {"items": items, "next": next_cursor, "limit": limit}
    SchemaRegistry.load_default().require_valid(PAGE_SCHEMA_URN, result)
    return result
