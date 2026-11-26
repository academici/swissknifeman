"""Segment-based write fence; non-UTF8 names fail closed (adapters §3.5)."""

from collections.abc import Iterable, Sequence

from skm.modules.execution.domain.output import matches_path as matches
from skm.modules.execution.domain.output import normalize_pattern as normalize_pattern

__all__ = ["matches", "normalize_pattern", "outside", "validate_scope"]


def outside[T: (str, bytes)](paths: Iterable[T], write_scope: Sequence[str]) -> tuple[T, ...]:
    patterns = tuple(normalize_pattern(pattern) for pattern in write_scope)
    result: set[T] = set()
    for raw in paths:
        try:
            path = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            path.encode("utf-8", "strict")
        except UnicodeError:
            result.add(raw)
            continue
        if not any(matches(path, pattern) for pattern in patterns):
            result.add(raw)
    return tuple(sorted(result))


def validate_scope(write_scope: Sequence[str], *, read_only: bool = False) -> None:
    if not write_scope and not read_only:
        raise ValueError("executable task requires a non-empty declared_write_scope")
    for pattern in write_scope:
        normalize_pattern(pattern)
