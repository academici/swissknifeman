"""Snapshot of the aicore model catalog inside the routing config.

``configs/command-routing.json`` carries the model selectors and the model inventory of every provider so
that the engine reads them without aicore. The projection renderer writes them from the canonical catalog
(``aicore.provider.models``); the rest of the file is hand-written and stays untouched.
"""
from __future__ import annotations

import copy
import json

SNAPSHOT_FIELDS = ("class_selectors", "effort_selectors", "model_inventory")
_INLINE_LISTS = frozenset({"argv"})


def routing_snapshot(routing: dict) -> dict:
    """Return ``routing`` with the catalog fields of every provider taken from the aicore catalog."""
    from aicore.provider.models import load_model_catalog

    catalog = load_model_catalog()
    mappings = routing.get("mappings") or {}
    ids = [item.provider_id for item in catalog.providers]
    if sorted(ids) != sorted(mappings):
        raise ValueError(f"MODEL_SNAPSHOT_PROVIDERS: catalog providers {ids} differ from routing mappings "
                         f"{list(mappings)}")
    snapshot = copy.deepcopy(routing)
    for provider in catalog.providers:
        mapping = snapshot["mappings"][provider.provider_id]
        mapping["class_selectors"] = {key: list(value) for key, value in provider.class_selectors.items()}
        mapping["effort_selectors"] = {key: list(value) for key, value in provider.effort_selectors.items()}
        mapping["model_inventory"] = provider.inventory_dict()
    return snapshot


def routing_text(routing: dict) -> str:
    """Serialize the routing config: two-space indent, ``argv`` arrays on one line, trailing newline."""
    return _dump(routing, "", 0) + "\n"


def _dump(value, key: str, level: int) -> str:
    pad = "  " * (level + 1)
    if isinstance(value, dict) and value:
        rows = [f"{pad}{json.dumps(name, ensure_ascii=False)}: {_dump(item, name, level + 1)}"
                for name, item in value.items()]
        return "{\n" + ",\n".join(rows) + "\n" + "  " * level + "}"
    if isinstance(value, list) and value:
        if key in _INLINE_LISTS:
            return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in value) + "]"
        return "[\n" + ",\n".join(f"{pad}{_dump(item, '', level + 1)}" for item in value) + "\n" + "  " * level + "]"
    return json.dumps(value, ensure_ascii=False)
