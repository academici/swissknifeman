"""Plain JSON copies of the frozen mappings and tuples execution records hold."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from skm.kernel.json_types import JsonValue

__all__ = ["thaw_json"]


def thaw_json(value: object) -> JsonValue:
    """A detached plain JSON copy of a frozen value: mappings become dicts, tuples lists.

    Changing the copy never reaches the record it came from.
    """
    if isinstance(value, Mapping):
        return {str(k): thaw_json(v) for k, v in cast("Mapping[object, object]", value).items()}
    if isinstance(value, list | tuple):
        return [thaw_json(v) for v in cast("Sequence[object]", value)]
    return cast("JsonValue", value)
