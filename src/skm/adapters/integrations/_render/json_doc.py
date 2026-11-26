"""Canonical JSON writer for integration target configuration files (integrations §4.6)."""

from __future__ import annotations

from typing import Any

from skm.modules.integrations.domain.merged_json import dumps_merged_json, dumps_merged_json_bytes

__all__ = ["dumps", "dumps_bytes"]


def dumps(value: Any) -> str:
    """Serialize ``value`` with ``indent=2``, ``ensure_ascii=False``, and trailing ``\\n``."""
    return dumps_merged_json(value)


def dumps_bytes(value: Any) -> bytes:
    """Serialize ``value`` as UTF-8 bytes via ``dumps``."""
    return dumps_merged_json_bytes(value)
