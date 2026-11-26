"""JSON-plain rendering of application values for payloads, digests and receipts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, cast
from uuid import UUID

__all__ = ["plain"]


def plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in fields(value) if not f.name.startswith("_")}
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in cast("Mapping[Any, Any]", value).items()}
    if isinstance(value, tuple | list):
        return [plain(v) for v in cast("list[Any]", value)]
    if isinstance(value, set | frozenset):
        return sorted(plain(v) for v in cast("set[Any]", value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return cast("Any", value).isoformat()
    return value
