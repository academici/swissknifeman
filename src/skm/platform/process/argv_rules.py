"""Validation of an argv vector, without shell parsing or interpolation."""

from collections.abc import Sequence
from typing import Final

__all__ = ["MAX_ARGV", "MAX_ARG_LEN", "check_argv"]

MAX_ARG_LEN: Final = 32_768
MAX_ARGV: Final = 4_096


def check_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if isinstance(argv, (str, bytes)) or not argv or len(argv) > MAX_ARGV:
        raise ValueError("argv must be a non-empty sequence within MAX_ARGV")
    result = tuple(argv)
    for item in result:
        if not isinstance(item, str) or "\0" in item or len(item) > MAX_ARG_LEN:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("argv elements must be strings without NUL, within MAX_ARG_LEN")
    if not result[0]:
        raise ValueError("argv executable must not be empty")
    return result
