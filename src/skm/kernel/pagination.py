"""Opaque keyset pagination primitives (``kernel/defs.v1.json``: page-cursor, page-limit, page-meta).

A cursor is an opaque string for callers; only the adapter that issued it knows its key structure
(``adapters/postgres/pagination.py``, ``entrypoints/api/pagination.py``). The kernel only fixes the bounds.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, NewType

__all__ = [
    "CURSOR_MAX_LENGTH",
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_LIMIT",
    "MIN_PAGE_LIMIT",
    "Cursor",
    "Page",
    "PageRequest",
    "validate_cursor",
    "validate_page_limit",
]

CURSOR_MAX_LENGTH: Final = 512
MIN_PAGE_LIMIT: Final = 1
MAX_PAGE_LIMIT: Final = 500
DEFAULT_PAGE_LIMIT: Final = 50

Cursor = NewType("Cursor", str)  # opaque, 1..512 characters


def validate_cursor(value: str) -> Cursor:
    """Check the cursor bounds only; the content stays opaque."""
    if not isinstance(value, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"cursor must be str, got {type(value).__name__}")
    if not 1 <= len(value) <= CURSOR_MAX_LENGTH:
        raise ValueError(f"cursor length must be in [1, {CURSOR_MAX_LENGTH}], got {len(value)}")
    return Cursor(value)


def validate_page_limit(value: int, *, maximum: int = MAX_PAGE_LIMIT) -> int:
    """Return ``value`` when it lies in ``[MIN_PAGE_LIMIT, maximum]``; ``maximum`` may only be lowered."""
    if isinstance(value, bool) or not isinstance(value, int):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"page limit must be int, got {type(value).__name__}")
    if not MIN_PAGE_LIMIT <= maximum <= MAX_PAGE_LIMIT:
        raise ValueError(f"page limit maximum must be in [{MIN_PAGE_LIMIT}, {MAX_PAGE_LIMIT}], got {maximum}")
    if not MIN_PAGE_LIMIT <= value <= maximum:
        raise ValueError(f"page limit must be in [{MIN_PAGE_LIMIT}, {maximum}], got {value}")
    return value


@dataclass(frozen=True, slots=True)
class PageRequest:
    """``after`` is the cursor of the previous page (``None`` for the first one)."""

    after: Cursor | None = None
    limit: int = DEFAULT_PAGE_LIMIT

    def __post_init__(self) -> None:
        if self.after is not None:
            validate_cursor(self.after)
        validate_page_limit(self.limit)


@dataclass(frozen=True, slots=True)
class Page[T]:
    """One keyset page; ``next`` is ``None`` on the last page."""

    items: Sequence[T]
    next: Cursor | None = None

    def __post_init__(self) -> None:
        if self.next is not None:
            validate_cursor(self.next)
