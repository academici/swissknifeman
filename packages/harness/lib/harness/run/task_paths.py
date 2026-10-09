"""Where the planner package lives for the legacy `harness run` driver.

Order: `PLANNER_ROOT` → `SKM_TASK_ROOT` (deprecated) → the `planner` package next to this installation → the monorepo
(`find_monorepo_root`) → `PlannerUnavailable`. The same order is used by the orch `task` bridge.
An explicit `monorepo_root` argument is a caller-supplied root and wins without fallthrough.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from core import find_monorepo_root

PLANNER_ROOT_ENV = "PLANNER_ROOT"
LEGACY_ROOT_ENV = "SKM_TASK_ROOT"  # Compatibility alias: remove in the next minor release.
_LEGACY_ROOT_WARNED = False  # Compatibility alias: remove in the next minor release.
_PLAN_SCRIPT = Path("scripts") / "plan.py"
_ROUTING = Path("configs") / "command-routing.json"


class PlannerUnavailable(RuntimeError):
    """Planner package not found by any step of the discovery order."""


TaskUnavailable = PlannerUnavailable  # Compatibility alias: remove in the next minor release.


def _valid(root):
    return (root / _PLAN_SCRIPT).is_file()


def _legacy_root():
    """`SKM_TASK_ROOT` when it holds scripts/plan.py; warns once per process. Compatibility alias: remove in the next minor release."""
    global _LEGACY_ROOT_WARNED
    env = os.environ.get(LEGACY_ROOT_ENV)
    if not (env and _valid(Path(env))):
        return None
    if not _LEGACY_ROOT_WARNED:
        _LEGACY_ROOT_WARNED = True
        print(f"SKM_TASK_ROOT_DEPRECATED: {LEGACY_ROOT_ENV} is deprecated; set {PLANNER_ROOT_ENV}",
              file=sys.stderr)
    return Path(env).resolve()


def planner_root(start=None, *, monorepo_root=None):
    """Planner package root; `start` (default: cwd) seeds the monorepo fallback."""
    if monorepo_root is not None:
        return Path(monorepo_root) / "packages" / "planner"
    env = os.environ.get(PLANNER_ROOT_ENV)
    if env and _valid(Path(env)):
        return Path(env).resolve()
    legacy = _legacy_root()  # Compatibility alias: remove in the next minor release.
    if legacy is not None:
        return legacy
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
