"""Extension slots of the plan schema: fields the engine declares and a bridge describes (stdlib).

The engine declares a slot as a ``$ref`` to ``urn:swissknifeman:task:plan:extension:<slot>:v1`` and knows nothing of
its content. A bridge supplies the slot with ``"extends": {"<slot>": "<schema file inside the bridge>"}`` in its
``bridge.json``; the file follows the closed schema profile and refers only to its own ``#/$defs``. With exactly one
supplier the field is validated by that schema. Without a supplier, or with more than one, the field is refused with
``EXTENSION_UNAVAILABLE``. A document without the field never reads a bridge.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import bridges, schema
from .model import PlanError

SLOTS = ("orchestration.options",)
UNAVAILABLE = "EXTENSION_UNAVAILABLE"
_cache: dict[tuple, dict | str] = {}


def slot_id(slot: str) -> str:
    return f"{schema.EXTENSION_PREFIX}{slot}:v1"


def slot_of(schema_id: str) -> str | None:
    return next((slot for slot in SLOTS if slot_id(slot) == schema_id), None)


def clear_cache() -> None:
    _cache.clear()


def suppliers(slot: str) -> list[tuple[str, Path]]:
    """``(bridge name, schema path)`` of every bridge that supplies ``slot``, in name order."""
    found = []
    for directory, manifest in bridges.scan():
        target = (manifest.get("extends") or {}).get(slot)
        if target:
            found.append((manifest["name"], directory.resolve() / target))
    return found


def _load(slot: str) -> dict | str:
    """The supplied schema of ``slot``, or the reason why there is none."""
    try:
        found = suppliers(slot)
    except PlanError as exc:
        return f"the bridges cannot be read ({exc})"
    if not found:
        return "no bridge supplies it (bridge.json extends); remove the field or install the bridge of its executor"
    if len(found) > 1:
        return "bridges " + ", ".join(name for name, _ in found) + " all supply it; keep one"
    name, path = found[0]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        schema._check_profile(document, f"bridge {name}: {path.name}", "", root=True)
    except (OSError, ValueError) as exc:  # SchemaProfileError is a ValueError
        return f"bridge {name} supplies an unusable schema: {exc}"
    return document


def schema_for(schema_id: str) -> dict:
    """Schema of the slot ``schema_id``; ``ExtensionUnavailable`` when it cannot be had. Remembered per bridge roots."""
    slot = slot_of(schema_id)
    if slot is None:
        raise schema.ExtensionUnavailable(f"{UNAVAILABLE}: unknown extension slot {schema_id!r}")
    key = (tuple(str(root) for root in bridges.roots()), slot)
    if key not in _cache:
        _cache[key] = _load(slot)
    found = _cache[key]
    if isinstance(found, str):
        raise schema.ExtensionUnavailable(f"{UNAVAILABLE}: {slot}: {found}")
    return found
