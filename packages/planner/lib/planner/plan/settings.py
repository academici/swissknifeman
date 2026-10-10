"""Effective ``[planner]`` configuration of a plan or of a plans root (stdlib; aicore only through the integration).

``for_plan`` adds the ``plan.settings`` layer of the plan, ``for_root`` serves commands that have no plan yet.
The result is remembered per process and refreshed when the plan file, a configuration file, the environment or
the ``--config`` file changes. The numbers and defaults the engine used to hard-code are read from here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import store

_INVOCATION: dict = {"file": None}
_CACHE: dict = {}


def set_invocation(path: str | Path | None) -> None:
    """Set the ``--config`` file of this process (``None`` clears it)."""
    _INVOCATION["file"] = None if path is None else Path(path)
    _CACHE.clear()


def invocation_file() -> Path | None:
    return _INVOCATION["file"]


def project_root_of(plans_root: Path) -> Path | None:
    """The project a ``plans/`` folder (or ``plans/archive/``) belongs to; ``None`` for any other folder name."""
    root = Path(plans_root)
    if root.name == store.ARCHIVE:
        root = root.parent
    return root.parent if root.name == "plans" else None


def _stamp(path: Path | None) -> tuple:
    try:
        stat = Path(path).stat()
    except (OSError, TypeError):
        return ()
    return (str(path), stat.st_mtime_ns, stat.st_size)


def _signature(project_root: Path | None, extra: tuple) -> tuple:
    """What a cached result depends on besides the plan: configuration files, environment and ``--config``."""
    from planner.integration import config
    files: list = [invocation_file(), *config.layer_files(project_root)]
    env = tuple(sorted((k, v) for k, v in os.environ.items()
                       if k.startswith("SKM_") or k in ("HOME", "XDG_CONFIG_HOME")))
    return (env, tuple(_stamp(f) for f in files), extra)


def _resolve(project_root: Path | None, plan_settings: dict | None, extra: tuple):
    key = (project_root, _signature(project_root, extra))
    if key not in _CACHE:
        from planner.integration import config
        _CACHE[key] = config.resolve(project_root=project_root, plan_settings=plan_settings,
                                     config_file=invocation_file())
    return _CACHE[key]


def for_plan(plan: store.Plan):
    """Configuration for ``plan``: its project's files and its ``plan.settings`` layer."""
    document = plan.plan if isinstance(plan.plan, dict) else {}
    plan_settings = document.get("settings") if isinstance(document.get("settings"), dict) else None
    return _resolve(project_root_of(plan.root.parent), plan_settings,
                    (str(plan.root), json.dumps(plan_settings, sort_keys=True, default=str)))


def for_root(plans_root: str | Path):
    """Configuration for commands without a plan (``new``): machine, project, environment, ``--config``."""
    return _resolve(project_root_of(Path(plans_root)), None, ("root", str(plans_root)))
