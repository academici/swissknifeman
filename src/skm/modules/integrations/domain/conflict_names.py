"""Conflict sidecar file naming helpers for non-destructive reconciliation (integrations §4.4)."""

from __future__ import annotations

from typing import Final

__all__ = [
    "DEFAULT_CONFLICT_SUFFIX",
    "conflict_path",
    "is_conflict_path",
    "original_path",
]

DEFAULT_CONFLICT_SUFFIX: Final[str] = ".skm-new"


def _validate_suffix(suffix: str) -> None:
    if not suffix:
        raise ValueError("conflict suffix must not be empty")


def conflict_path(relative_path: str, *, suffix: str = DEFAULT_CONFLICT_SUFFIX) -> str:
    """Return the sidecar conflict path ``<relative_path><suffix>``."""
    _validate_suffix(suffix)
    if not relative_path:
        raise ValueError("relative_path must not be empty")
    return f"{relative_path}{suffix}"


def is_conflict_path(path: str, *, suffix: str = DEFAULT_CONFLICT_SUFFIX) -> bool:
    """Return True when ``path`` names a conflict sidecar with ``suffix``."""
    _validate_suffix(suffix)
    if not path.endswith(suffix) or len(path) <= len(suffix):
        return False
    stem = path[: -len(suffix)]
    return not stem.endswith(("/", "\\"))


def original_path(conflict_file_path: str, *, suffix: str = DEFAULT_CONFLICT_SUFFIX) -> str:
    """Strip ``suffix`` from ``conflict_file_path`` when it is a conflict path."""
    _validate_suffix(suffix)
    if is_conflict_path(conflict_file_path, suffix=suffix):
        return conflict_file_path[: -len(suffix)]
    return conflict_file_path
