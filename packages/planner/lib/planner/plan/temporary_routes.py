"""Explicit owner-approved, local route substitutions without editing a plan."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .model import PlanError


def approved(plan, route, actor) -> bool:
    path = os.environ.get("SKM_PLANNER_TEMPORARY_ROUTES")
    if not path or plan is None:
        return False
    try:
        policy = json.loads(Path(path).read_text(encoding="utf-8"))
        if policy.get("kind") != "temporary_owner_instruction":
            raise ValueError("unexpected policy kind")
        roots = policy["plan_roots"]
        substitutions = policy["substitutions"]
        if not isinstance(roots, list) or not isinstance(substitutions, dict):
            raise ValueError("invalid roots or substitutions")
        if str(plan.root.resolve()) not in roots:
            return False
        keys = ("provider", "model", "effort")
        if not all(isinstance(route.get(k), str) and route[k] for k in keys):
            return False
        source = "/".join(route[k] for k in keys)
        if not all(isinstance(actor.get(k), str) and actor[k] for k in keys):
            return False
        return substitutions.get(source) == "/".join(actor[k] for k in keys)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise PlanError("ROUTING_UNAVAILABLE", f"invalid temporary route policy: {exc}") from None
