"""Deterministic instruction carriers; no path is resolved against a host filesystem."""

from __future__ import annotations

from collections.abc import Sequence


def static_prefix(pattern: str) -> str:
    """Return the directory before the first wildcard, filename or traversal component."""
    parts: list[str] = []
    components = pattern.split("/")
    for part in components:
        if part == ".." or any(char in part for char in "*?["):
            break
        if part and part != ".":
            parts.append(part)
    else:
        if parts and not pattern.endswith("/"):
            parts.pop()
    return "/".join(parts)


def instruction_carrier_dirs(write_scope_patterns: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """Include every ancestor, even when most carrier directories have no instructions."""
    result: set[tuple[str, str]] = set()
    for mount, pattern in write_scope_patterns:
        result.add((mount, ""))
        prefix = static_prefix(pattern)
        parts = prefix.split("/") if prefix else []
        result.update((mount, "/".join(parts[:depth])) for depth in range(1, len(parts) + 1))
    return tuple(sorted(result, key=lambda item: (item[0], item[1].count("/") + bool(item[1]), item[1])))
