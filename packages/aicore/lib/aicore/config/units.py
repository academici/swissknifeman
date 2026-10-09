"""Find the modules that declare a configuration schema.

Roots come from ``SKM_UNITS_PATH`` (entries separated by ``os.pathsep``; an entry is either a module
folder with a ``unit.json`` or a folder that holds module folders). Without it the folder that holds
this foundation is scanned (the ``packages/`` layout of the hub).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional


UNITS_PATH_VAR = "SKM_UNITS_PATH"


@dataclass(frozen=True)
class UnitInfo:
    """A module with a configuration schema: its id, folder, schema file and the schema path as declared."""

    id: str
    root: Path
    schema_path: Path
    schema_rel: str


def foundation_root() -> Path:
    """The folder of this ``aicore`` module (``lib/aicore/config/units.py`` is three levels below it)."""
    return Path(__file__).resolve().parents[3]


def load_unit(root) -> Optional[UnitInfo]:
    """The :class:`UnitInfo` of the module folder ``root``, or ``None`` if it declares no ``provides.config``."""
    base = Path(root)
    try:
        doc = json.loads((base / "unit.json").read_text(encoding="utf-8"))
        unit_id = doc["id"]
        relative = doc["provides"]["config"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(unit_id, str) or not isinstance(relative, str) or not relative:
        return None
    return UnitInfo(unit_id, base, base / relative, relative)


def _roots(env: Mapping[str, str]) -> list:
    value = env.get(UNITS_PATH_VAR, "")
    if value:
        return [Path(part) for part in value.split(os.pathsep) if part]
    return [foundation_root().parent]


def unit_dirs(env: Optional[Mapping[str, str]] = None) -> list:
    """Every module folder (one that holds a ``unit.json``) under the roots, in root order, without repeats."""
    environment = os.environ if env is None else env
    found: list = []
    for root in _roots(environment):
        if (root / "unit.json").is_file():
            candidates = [root]
        else:
            try:
                candidates = sorted(entry for entry in root.iterdir() if (entry / "unit.json").is_file())
            except OSError:
                continue
        found.extend(candidate for candidate in candidates if candidate not in found)
    return found


def discover(env: Optional[Mapping[str, str]] = None) -> Dict[str, UnitInfo]:
    """Modules with ``provides.config`` by id; the first root wins when an id repeats."""
    found: Dict[str, UnitInfo] = {}
    for candidate in unit_dirs(env):
        info = load_unit(candidate)
        if info is not None and info.id not in found:
            found[info.id] = info
    return found
