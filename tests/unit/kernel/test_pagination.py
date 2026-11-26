"""Opaque keyset pagination bounds (``kernel/defs.v1.json``: page-cursor, page-limit, page-meta)."""

import json
from pathlib import Path

import pytest

from skm.kernel.pagination import (
    CURSOR_MAX_LENGTH,
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    MIN_PAGE_LIMIT,
    Cursor,
    Page,
    PageRequest,
    validate_cursor,
    validate_page_limit,
)

DEFS = Path(__file__).resolve().parents[3] / "src/skm/schemas/kernel/defs.v1.json"


def test_bounds_match_the_kernel_schema() -> None:
    defs = json.loads(DEFS.read_text(encoding="utf-8"))["$defs"]

    assert defs["page-cursor"]["minLength"] == 1
    assert defs["page-cursor"]["maxLength"] == CURSOR_MAX_LENGTH
    assert defs["page-limit"]["minimum"] == MIN_PAGE_LIMIT
    assert defs["page-limit"]["maximum"] == MAX_PAGE_LIMIT
    assert defs["page-limit"]["default"] == DEFAULT_PAGE_LIMIT


@pytest.mark.parametrize("value", ["a", "eyJrIjoxfQ==", "x" * CURSOR_MAX_LENGTH, "ключ", " "])
def test_cursor_is_opaque_text(value: str) -> None:
    assert validate_cursor(value) == value


@pytest.mark.parametrize("value", ["", "x" * (CURSOR_MAX_LENGTH + 1)])
def test_cursor_bounds_are_enforced(value: str) -> None:
    with pytest.raises(ValueError, match="cursor length"):
        validate_cursor(value)


def test_cursor_must_be_str() -> None:
    with pytest.raises(TypeError):
        validate_cursor(b"abc")  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [MIN_PAGE_LIMIT, DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT])
def test_page_limit_inside_bounds(value: int) -> None:
    assert validate_page_limit(value) == value


@pytest.mark.parametrize("value", [0, -1, MAX_PAGE_LIMIT + 1])
def test_page_limit_outside_bounds(value: int) -> None:
    with pytest.raises(ValueError, match="page limit must be in"):
        validate_page_limit(value)


def test_page_limit_maximum_can_only_be_lowered() -> None:
    assert validate_page_limit(200, maximum=200) == 200
    with pytest.raises(ValueError, match="page limit must be in"):
        validate_page_limit(201, maximum=200)
    with pytest.raises(ValueError, match="maximum"):
        validate_page_limit(10, maximum=MAX_PAGE_LIMIT + 1)
    with pytest.raises(ValueError, match="maximum"):
        validate_page_limit(1, maximum=0)


@pytest.mark.parametrize("value", [True, 1.0, "5", None])
def test_page_limit_must_be_int(value: object) -> None:
    with pytest.raises(TypeError):
        validate_page_limit(value)  # type: ignore[arg-type]


def test_page_request_defaults_and_validation() -> None:
    assert PageRequest() == PageRequest(after=None, limit=DEFAULT_PAGE_LIMIT)
    assert PageRequest(after=Cursor("abc"), limit=5).limit == 5
    with pytest.raises(ValueError, match="page limit"):
        PageRequest(limit=0)
    with pytest.raises(ValueError, match="cursor length"):
        PageRequest(after=Cursor(""))


def test_page_next_is_null_on_last_page() -> None:
    last = Page(items=("a", "b"))
    middle = Page(items=("a",), next=Cursor("k"))

    assert last.next is None
    assert middle.next == "k"
    with pytest.raises(ValueError, match="cursor length"):
        Page(items=(), next=Cursor(""))
