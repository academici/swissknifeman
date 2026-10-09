"""Find the planner partner. The bridge never imports it; it only locates its files."""
from __future__ import annotations

import os
from pathlib import Path

PLANNER_ROOT_ENV = "PLANNER_ROOT"
UNAVAILABLE = (f"PLANNER_UNAVAILABLE: planner package not found; set {PLANNER_ROOT_ENV} to a directory "
               "holding scripts/plan.py")
_PLAN_SCRIPT = Path("scripts") / "plan.py"
_ROUTING = Path("configs") / "command-routing.json"
_MONOREPO_MARKER = Path("packages") / "planner" / _PLAN_SCRIPT


class PlannerUnavailable(RuntimeError):
    """Planner package not found by any step of the discovery order."""


def orch_root() -> Path:
    """Root of the orch package this bridge belongs to (``bridges/task/discovery.py`` → ``orch``)."""
    return Path(__file__).resolve().parents[2]


def _valid(root: Path) -> bool:
    return (root / _PLAN_SCRIPT).is_file()


def planner_root(start: Path | str | None = None) -> Path:
    """``PLANNER_ROOT`` → the ``planner`` package next to orch → the monorepo ancestor of ``start`` (default cwd)."""
    env = os.environ.get(PLANNER_ROOT_ENV)
    if env and _valid(Path(env)):
        return Path(env).resolve()
    neighbour = orch_root().parent / "planner"
    if _valid(neighbour):
        return neighbour
    origin = Path(start).resolve() if start is not None else Path.cwd().resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / _MONOREPO_MARKER).is_file():
            return candidate / "packages" / "planner"
    raise PlannerUnavailable(UNAVAILABLE)


def routing_path(start: Path | str | None = None) -> Path:
    return planner_root(start) / _ROUTING


def plan_script(start: Path | str | None = None) -> Path:
    return planner_root(start) / _PLAN_SCRIPT
