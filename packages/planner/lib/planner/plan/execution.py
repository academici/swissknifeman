"""Execution scenario of an item: which run-policy profile runs it (stdlib).

The scenario is a name: an orchestration run-policy profile, or ``solo`` for the current session. The planner
only resolves the name; whether a profile of that name exists is checked by the bridge that executes it.
"""
from __future__ import annotations

from . import settings, store
from .model import item_phase

# Where the scenario came from, most specific first.
SOURCES = ("item", "phase", "plan", "config:by_class", "config:default")


def _declared(doc: object) -> str | None:
    orchestration = doc.get("orchestration") if isinstance(doc, dict) else None
    value = orchestration.get("scenario") if isinstance(orchestration, dict) else None
    return value if isinstance(value, str) and value else None


def scenario(plan: store.Plan, item_id: str) -> tuple[str, str]:
    """``(name, source)``: the first scenario set on the item, its phase, the plan, then the configured class and default.

    An item without a route (migrated plans) skips the class entry.
    """
    for source, doc in (("item", plan.items[item_id]), ("phase", plan.phases.get(item_phase(item_id))),
                        ("plan", plan.plan)):
        name = _declared(doc)
        if name:
            return name, source
    config = settings.for_plan(plan)
    route = plan.items[item_id].get("route")
    route_class = route.get("class") if isinstance(route, dict) else None
    if route_class:
        name = config.get(f"orchestration.by_class.{route_class}")
        if name:
            return name, "config:by_class"
    return config.get("orchestration.default_scenario"), "config:default"
