"""Where the planner package lives for the legacy `harness run` driver.

Order: `PLANNER_ROOT` → the `planner` package next to this installation → the monorepo
(`find_monorepo_root`) → `PlannerUnavailable`. The same order is used by the orch `task` bridge.
An explicit `monorepo_root` argument is a caller-supplied root and wins without fallthrough.
"""
from __future__ import annotations

import os
from pathlib import Path

from core import find_monorepo_root

PLANNER_ROOT_ENV = "PLANNER_ROOT"
_PLAN_SCRIPT = Path("scripts") / "plan.py"
_ROUTING = Path("configs") / "command-routing.json"


class PlannerUnavailable(RuntimeError):
    """Planner package not found by any step of the discovery order."""


TaskUnavailable = PlannerUnavailable  # Compatibility alias: remove in the next minor release.


def _valid(root):
    return (root / _PLAN_SCRIPT).is_file()


def planner_root(start=None, *, monorepo_root=None):
    """Planner package root; `start` (default: cwd) seeds the monorepo fallback."""
    if monorepo_root is not None:
        return Path(monorepo_root) / "packages" / "planner"
    env = os.environ.get(PLANNER_ROOT_ENV)
    if env and _valid(Path(env)):
        return Path(env).resolve()
    neighbour = Path(__file__).resolve().parents[4] / "planner"
    if _valid(neighbour):
        return neighbour
    found = find_monorepo_root(Path(start) if start is not None else Path.cwd())
    if found is not None and _valid(found / "packages" / "planner"):
        return found / "packages" / "planner"
    raise PlannerUnavailable(
        f"PLANNER_UNAVAILABLE: planner package not found; set {PLANNER_ROOT_ENV} to a directory "
        f"holding {_PLAN_SCRIPT.as_posix()}")


def plan_script(start=None, *, monorepo_root=None):
    return script_in(planner_root(start, monorepo_root=monorepo_root))


def routing_path(start=None, *, monorepo_root=None):
    return routing_in(planner_root(start, monorepo_root=monorepo_root))


def script_in(planner):
    return Path(planner) / _PLAN_SCRIPT


def routing_in(planner):
    return Path(planner) / _ROUTING
