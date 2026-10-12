"""Where the planner package lives for the legacy `harness run` driver.

Order: `PLANNER_ROOT` → `SKM_TASK_ROOT` (deprecated) → `PLANNER_PLAN_PY` (the folder above its `scripts/`) → the
`planner` command on `PATH` (the folder above the real file's directory) → `PlannerUnavailable`.
There is no step for a neighbouring folder or a monorepo root.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PLANNER_ROOT_ENV = "PLANNER_ROOT"
PLAN_PY_ENV = "PLANNER_PLAN_PY"
LEGACY_ROOT_ENV = "SKM_TASK_ROOT"  # Compatibility alias: remove in the next minor release.
_LEGACY_ROOT_WARNED = False  # Compatibility alias: remove in the next minor release.
_PLAN_SCRIPT = Path("scripts") / "plan.py"


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


def _from_plan_py():
    env = os.environ.get(PLAN_PY_ENV)
    if not env:
        return None
    script = Path(os.path.expanduser(env)).resolve()
    root = script.parent.parent
    return root if script.is_file() and script.name == _PLAN_SCRIPT.name and _valid(root) else None


def _from_path():
    found = shutil.which("planner")
    if not found:
        return None
    root = Path(found).resolve().parent.parent
    return root if _valid(root) else None


def planner_root():
    """Planner package root found through the environment or `PATH`."""
    env = os.environ.get(PLANNER_ROOT_ENV)
    if env and _valid(Path(env)):
        return Path(env).resolve()
    legacy = _legacy_root()  # Compatibility alias: remove in the next minor release.
    if legacy is not None:
        return legacy
    for step in (_from_plan_py, _from_path):
        root = step()
        if root is not None:
            return root
    raise PlannerUnavailable(
        f"PLANNER_UNAVAILABLE: planner package not found; set {PLANNER_ROOT_ENV} to a directory "
        f"holding {_PLAN_SCRIPT.as_posix()}")


def plan_script():
    return script_in(planner_root())


def script_in(planner):
    return Path(planner) / _PLAN_SCRIPT
