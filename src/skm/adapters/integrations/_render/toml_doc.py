"""Minimal pure-Python TOML writer for integration target configs (integrations §4.6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from skm.modules.integrations.domain.merged_toml import (
    dumps_merged_toml,
    dumps_merged_toml_bytes,
    format_toml_inline_table,
    format_toml_key,
    format_toml_table,
    format_toml_value,
)

__all__ = [
    "dumps",
    "dumps_bytes",
    "format_inline_table",
    "format_key",
    "format_table",
    "format_value",
]


def format_key(key: str) -> str:
    """Format a single TOML key segment."""
    return format_toml_key(key)


def format_inline_table(mapping: Mapping[str, Any]) -> str:
    """Format ``mapping`` as a TOML inline table."""
    return format_toml_inline_table(mapping)


def format_value(value: Any) -> str:
    """Format a primitive TOML value, list, or inline table."""
    return format_toml_value(value)


def format_table(path: Sequence[str], mapping: Mapping[str, Any]) -> str:
    """Format a ``[table]`` or ``[table.subtable]`` section."""
    return format_toml_table(path, mapping)


def dumps(document: Mapping[str, Any]) -> str:
    """Serialize ``document`` into canonical TOML text."""
    return dumps_merged_toml(document)


def dumps_bytes(document: Mapping[str, Any]) -> bytes:
    """Serialize ``document`` into canonical UTF-8 TOML bytes."""
    return dumps_merged_toml_bytes(document)
