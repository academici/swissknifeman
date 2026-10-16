"""Instruction overlays of the planner commands: the rules a person adds to a command without touching the module.

Every command of the module owns one slot ``planner:<command>`` declared in ``provides.overlay_slots`` of
``unit.json``. The command text asks ``plan.py overlays planner:<command>`` for the block and follows what it
prints. With aicore the files come from ``[aicore.overlays."<slot>"]`` of the layered configuration; without
aicore there are none, the block is empty and the command is unchanged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import status

PLANNER_ROOT = Path(__file__).resolve().parents[3]
MODULE = "planner"


def slots() -> list:
    """The slot names (a command id without the module) declared in ``unit.json``."""
    unit = json.loads((PLANNER_ROOT / "unit.json").read_text(encoding="utf-8"))
    return list(unit["provides"]["overlay_slots"])


def normalize(slot: str) -> str:
    """The full slot ``planner:<id>`` of ``<id>`` or ``planner:<id>``; ``PlanError(OVERLAY_SLOT_UNKNOWN)`` otherwise."""
    from planner.plan.model import PlanError
    name = slot[len(MODULE) + 1:] if slot.startswith(MODULE + ":") else slot
    known = slots()
    if name not in known:
        raise PlanError("OVERLAY_SLOT_UNKNOWN",
                        f"no overlay slot {slot!r} in module {MODULE} (declared: {', '.join(sorted(known))})")
    return f"{MODULE}:{name}"


def project_root(cwd: str | Path | None = None, project: str | Path | None = None) -> Path | None:
    """``project`` when given, else the project the working directory belongs to (``None`` without aicore or outside
    a git repository or ``.swissknifeman`` folder). Under the project launcher its root wins and a ``project`` naming
    another folder raises ``PROJECT_CONTEXT_CONFLICT`` (a ``LookupError``)."""
    if status()["aicore"] != "available":
        return Path(project) if project is not None else None
    from aicore.state import find_project_root, resolve_project
    if project is not None:
        return resolve_project(cwd if cwd is not None else os.getcwd(), explicit=project).root
    root = find_project_root(cwd if cwd is not None else os.getcwd())
    return root if (root / ".git").exists() or (root / ".swissknifeman").is_dir() else None


def resolve(slot: str, *, project: str | Path | None = None) -> dict[str, Any]:
    """The overlays of a slot: ``{"slot", "text", "overlays", "warnings", "aicore"}``.

    ``text`` is the block to print (empty without overlays), ``overlays`` and ``warnings`` follow
    ``aicore.ext.overlays.describe_overlays``. Without aicore both are empty and ``warnings`` holds
    ``AICORE_UNAVAILABLE``. Refusals: ``OVERLAY_SLOT_UNKNOWN``, ``OVERLAY_TOO_LARGE``, ``CONFIG_INVALID``.
    """
    from planner.plan.model import PlanError
    full = normalize(slot)
    info = status()
    if info["aicore"] != "available":
        return {"slot": full, "text": "", "overlays": [], "warnings": ["AICORE_UNAVAILABLE"], "aicore": info}
    from aicore.ext import overlays as ext
    from aicore.ext.errors import ExtError
    from aicore.ext.units import UnitDoc, discover_units
    from planner.plan import settings
    units = discover_units()
    if MODULE not in units:  # a standalone checkout: the module declares its own slots
        unit_file = PLANNER_ROOT / "unit.json"
        units[MODULE] = UnitDoc(MODULE, PLANNER_ROOT, json.loads(unit_file.read_text(encoding="utf-8")))
    try:
        found = ext.resolve_overlays(full, project=project, units=units, config_file=settings.invocation_file())
    except ExtError as exc:
        if exc.code == "OVERLAY_TOO_LARGE":
            raise PlanError("OVERLAY_TOO_LARGE", exc.message) from None
        if exc.code == "OVERLAY_SLOT_UNKNOWN":
            raise PlanError("OVERLAY_SLOT_UNKNOWN", exc.message) from None
        raise PlanError("CONFIG_INVALID", exc.message) from None
    described = ext.describe_overlays(found)
    return {"slot": full, "text": ext.render_overlays(found), "overlays": described["overlays"],
            "warnings": described["warnings"], "aicore": info}
