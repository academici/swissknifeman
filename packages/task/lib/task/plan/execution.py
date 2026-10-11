"""Execution scenario of an item: which run-policy profile runs it (stdlib).

The scenario is a name: an orchestration run-policy profile, or ``solo`` for the current session. The engine only
resolves the name; whether a profile of that name exists is checked by the bridge that executes it. This engine has
no configuration layer: without a scenario on the item, its phase or the plan the scenario is ``solo``.
"""
from __future__ import annotations

from . import store
from .model import item_phase

DEFAULT = "solo"
# Where the scenario came from, most specific first.
SOURCES = ("item", "phase", "plan", "default")


def _declared(doc: object) -> str | None:
    orchestration = doc.get("orchestration") if isinstance(doc, dict) else None
    value = orchestration.get("scenario") if isinstance(orchestration, dict) else None
    return value if isinstance(value, str) and value else None


def scenario(plan: store.Plan, item_id: str) -> tuple[str, str]:
    """``(name, source)``: the first scenario set on the item, its phase, the plan, else ``solo``."""
    for source, doc in (("item", plan.items[item_id]), ("phase", plan.phases.get(item_phase(item_id))),
                        ("plan", plan.plan)):
        name = _declared(doc)
        if name:
            return name, source
    return DEFAULT, "default"
