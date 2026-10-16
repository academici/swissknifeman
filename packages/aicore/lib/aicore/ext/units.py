"""What the modules declare in their ``unit.json`` for the extension layer.

Units are found under the same roots as the configuration schemas (``SKM_UNITS_PATH``, else the folder
that holds this foundation). A ``unit.json`` that cannot be read is skipped with one warning; fields are
read defensively, so a module with an unexpected shape loses only the entry that is wrong.
stdlib and ``aicore`` only.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ..config import units as _config_units
from ..util.paths import is_within
from .errors import warn_once


@dataclass(frozen=True)
class UnitDoc:
    """A module: its id, folder and the parsed ``unit.json``."""

    id: str
    root: Path
    doc: Dict[str, Any]


def discover_units(env: Optional[Mapping[str, str]] = None) -> Dict[str, UnitDoc]:
    """All modules by id (the first root wins); an unreadable ``unit.json`` is skipped with a warning."""
    found: Dict[str, UnitDoc] = {}
    for folder in _config_units.unit_dirs(env):
        path = folder / "unit.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warn_once("UNIT_INVALID", f"{path} was skipped: {exc.__class__.__name__}", key=str(path))
            continue
        unit_id = doc.get("id") if isinstance(doc, dict) else None
        if not isinstance(unit_id, str) or not unit_id:
            warn_once("UNIT_INVALID", f"{path} was skipped: it has no module id", key=str(path))
            continue
        found.setdefault(unit_id, UnitDoc(unit_id, folder, doc))
    return found


def _provides(unit: UnitDoc) -> Mapping[str, Any]:
    value = unit.doc.get("provides")
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> list:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def declared_events(units: Mapping[str, UnitDoc]) -> Dict[str, str]:
    """Event type -> module id, from ``provides.events`` (the first module to declare a type wins)."""
    found: Dict[str, str] = {}
    for unit in units.values():
        for event_type in _strings(_provides(unit).get("events")):
            found.setdefault(event_type, unit.id)
    return found


def overlay_slots(units: Mapping[str, UnitDoc]) -> Dict[str, str]:
    """Full slot ``<module>:<slot>`` -> module id, from ``provides.overlay_slots``."""
    return {f"{unit.id}:{slot}": unit.id for unit in units.values()
            for slot in _strings(_provides(unit).get("overlay_slots"))}


def extension_points(units: Mapping[str, UnitDoc]) -> Dict[str, Dict[str, Any]]:
    """Full point ``<module>:<id>`` -> ``{"module", "id", "description"}``, from ``provides.extension_points``."""
    found: Dict[str, Dict[str, Any]] = {}
    for unit in units.values():
        points = _provides(unit).get("extension_points")
        for point in points if isinstance(points, list) else []:
            if isinstance(point, dict) and isinstance(point.get("id"), str) and point["id"]:
                found.setdefault(f"{unit.id}:{point['id']}", {
                    "module": unit.id, "id": point["id"],
                    "description": point["description"] if isinstance(point.get("description"), str) else ""})
    return found


def _inside(root: Path, path: Path) -> bool:
    return is_within(path, root)  # fails closed, also on a symlink loop


def module_subscriptions(units: Mapping[str, UnitDoc]) -> Dict[str, Dict[str, Any]]:
    """Default subscriptions of the modules by full id ``<module>:<id>``.

    Each value has ``module``, ``id``, ``on``, ``run`` (the first element made absolute inside the module
    folder), ``timeout_seconds`` (or None) and ``description``. An entry that is wrong or whose command
    leaves the module folder is skipped with a warning.
    """
    found: Dict[str, Dict[str, Any]] = {}
    for unit in units.values():
        entries = unit.doc.get("subscribes")
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            name, patterns, run = entry.get("id"), _strings(entry.get("on")), _strings(entry.get("run"))
            full = f"{unit.id}:{name}"
            if not isinstance(name, str) or not name or not patterns or not run:
                warn_once("UNIT_INVALID", f"a subscription of module {unit.id} was skipped: "
                          "it needs id, on and run", key=full)
                continue
            command = unit.root / run[0]
            if os.path.isabs(run[0]) or not _inside(unit.root, command):
                warn_once("UNIT_INVALID", f"subscription {full} was skipped: its command must stay inside "
                          "the module folder", key=full)
                continue
            timeout = entry.get("timeout_seconds")
            found.setdefault(full, {
                "module": unit.id, "id": name, "on": patterns, "run": [str(command)] + run[1:],
                "timeout_seconds": timeout if isinstance(timeout, int) and not isinstance(timeout, bool) else None,
                "description": entry["description"] if isinstance(entry.get("description"), str) else ""})
    return found
