"""Where the Task package lives for the legacy `harness run` driver.

Order: `SKM_TASK_ROOT` → the `task` package next to this installation → the monorepo
(`find_monorepo_root`) → `TaskUnavailable`. The same order is used by the orch `task` bridge.
An explicit `monorepo_root` argument is a caller-supplied root and wins without fallthrough.
"""
from __future__ import annotations

import os
from pathlib import Path

from core import find_monorepo_root

TASK_ROOT_ENV = "SKM_TASK_ROOT"
_PLAN_SCRIPT = Path("scripts") / "plan.py"
_ROUTING = Path("configs") / "command-routing.json"


class TaskUnavailable(RuntimeError):
    """Task package not found by any step of the discovery order."""


def _valid(root):
    return (root / _PLAN_SCRIPT).is_file()


def task_root(start=None, *, monorepo_root=None):
    """Task package root; `start` (default: cwd) seeds the monorepo fallback."""
    if monorepo_root is not None:
        return Path(monorepo_root) / "packages" / "task"
    env = os.environ.get(TASK_ROOT_ENV)
    if env and _valid(Path(env)):
        return Path(env).resolve()
    neighbour = Path(__file__).resolve().parents[4] / "task"
    if _valid(neighbour):
        return neighbour
    found = find_monorepo_root(Path(start) if start is not None else Path.cwd())
    if found is not None and _valid(found / "packages" / "task"):
        return found / "packages" / "task"
    raise TaskUnavailable(
        f"TASK_UNAVAILABLE: Task package not found; set {TASK_ROOT_ENV} to a directory "
        f"holding {_PLAN_SCRIPT.as_posix()}")


def plan_script(start=None, *, monorepo_root=None):
    return script_in(task_root(start, monorepo_root=monorepo_root))


def routing_path(start=None, *, monorepo_root=None):
    return routing_in(task_root(start, monorepo_root=monorepo_root))


def script_in(task):
    return Path(task) / _PLAN_SCRIPT


def routing_in(task):
    return Path(task) / _ROUTING
