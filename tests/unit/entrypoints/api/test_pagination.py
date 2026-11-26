"""API keyset cursors reject non-canonical encodings and out-of-range limits."""

import base64
import json
from typing import cast
from uuid import UUID

import pytest

from skm.entrypoints.api.pagination import (
    CURSOR_MAX_LENGTH,
    decode_cursor,
    encode_cursor,
    page,
)
from skm.kernel.errors import ValidationFailed
from skm.kernel.pagination import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT

ITEM_ID = UUID("0192f5ca-5001-7000-8000-000000000001")


def test_encode_decode_round_trip_uses_a_canonical_uuid() -> None:
    cursor = encode_cursor(["name", 3], ITEM_ID)
    assert decode_cursor(cursor) == (("name", 3), str(ITEM_ID))


def test_encode_rejects_an_empty_or_non_scalar_sort_key() -> None:
    with pytest.raises(ValidationFailed, match="Invalid cursor sort key"):
        encode_cursor([], ITEM_ID)
    with pytest.raises(ValidationFailed, match="Invalid cursor sort key"):
        encode_cursor(["name", cast("str | int", True)], ITEM_ID)


def test_encode_rejects_an_invalid_id() -> None:
    with pytest.raises(ValidationFailed, match="Invalid cursor id"):
        encode_cursor(["name"], "not-a-uuid")


def test_encode_rejects_a_cursor_that_exceeds_the_length_limit() -> None:
    with pytest.raises(ValidationFailed, match="Cursor exceeds limit"):
        encode_cursor(["x" * CURSOR_MAX_LENGTH], ITEM_ID)


def test_decode_rejects_empty_or_illegal_characters() -> None:
    with pytest.raises(ValidationFailed, match="Invalid pagination cursor"):
        decode_cursor("")
    with pytest.raises(ValidationFailed, match="Invalid pagination cursor"):
        decode_cursor("abc+def")  # standard Base64, not base64url


def test_decode_rejects_padding_and_other_non_canonical_forms() -> None:
    cursor = encode_cursor(["name"], ITEM_ID)
    with pytest.raises(ValidationFailed, match="Invalid pagination cursor"):
        decode_cursor(cursor + "=")
    # Re-encoding would use a hyphenated UUID; a compact id in the payload is not canonical.
    raw = json.dumps({"k": ["name"], "id": ITEM_ID.hex}, separators=(",", ":")).encode()
    compact = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    with pytest.raises(ValidationFailed, match="Invalid pagination cursor"):
        decode_cursor(compact)


def test_decode_rejects_an_unexpected_payload_shape() -> None:
    def packed(payload: object) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    with pytest.raises(ValidationFailed, match="Invalid pagination cursor"):
        decode_cursor(packed(["name", str(ITEM_ID)]))
    with pytest.raises(ValidationFailed, match="Invalid pagination cursor"):
        decode_cursor(packed({"k": ["name"], "id": str(ITEM_ID), "extra": 1}))


def test_page_uses_the_default_limit_and_validates_a_next_cursor() -> None:
    cursor = encode_cursor(["name"], ITEM_ID)
    result = page([{"id": str(ITEM_ID)}], cursor)
    assert result["limit"] == DEFAULT_PAGE_LIMIT
    assert result["next"] == cursor
    assert result["items"] == [{"id": str(ITEM_ID)}]


def test_page_rejects_a_non_int_or_out_of_range_limit() -> None:
    with pytest.raises(ValidationFailed, match="Invalid page limit"):
        page([], None, cast(int, True))
    with pytest.raises(ValidationFailed, match="Invalid page limit"):
        page([], None, 0)
    with pytest.raises(ValidationFailed, match="Invalid page limit"):
        page([], None, MAX_PAGE_LIMIT + 1)


def test_page_rejects_an_invalid_next_cursor() -> None:
    with pytest.raises(ValidationFailed, match="Invalid pagination cursor"):
        page([], "not-a-cursor")
