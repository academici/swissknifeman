"""Where the plans of a project live, and which checkout a plan belongs to.

One rule for every reader of plans (aicore, the planner copy ``planner.plan.workspace``): the project marker
``<root>/.swissknifeman/project.json`` decides, a plan-store switch is the marker's ``plans_store``. The shared vectors
``schemas/workspace/v1/resolution-vectors.json`` pin the behaviour; change them only together with every implementation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Union

from aicore.state.locations import launcher_root as _launcher_root
from aicore.state.locations import workspace_root

from . import WorkspaceError
from .bindings import read_bindings
from .documents import read_marker

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]


@dataclass(frozen=True)
class PlansStore:
    """``kind`` is ``legacy`` or ``workspace``; ``reason`` is ``no-marker``, ``marker-legacy`` or ``marker-workspace``;
    ``project_id`` is ``None`` without a marker."""

    kind: str
    plans_root: Path
    project_id: Optional[str]
    reason: str


def resolve_plans_store(project_root: PathLike, env: Env = None, home: Optional[PathLike] = None) -> PlansStore:
    """The plan store of the checkout at ``project_root``. An invalid marker is ``PROJECT_MARKER_INVALID``; a marker that
    points at the workspace whose project folder is missing is ``WORKSPACE_PROJECT_MISSING``. Nothing is created."""
    root = Path(project_root)
    marker = read_marker(root)
    if marker is None:
        return PlansStore("legacy", root / "plans", None, "no-marker")
    if marker["plans_store"] == "legacy":
        return PlansStore("legacy", root / "plans", marker["project_id"], "marker-legacy")
    workspace = workspace_root(env, home)
    plans = workspace / "projects" / marker["project_id"] / "plans"
    if plans.is_dir():
        return PlansStore("workspace", plans, marker["project_id"], "marker-workspace")
    raise WorkspaceError("WORKSPACE_PROJECT_MISSING",
                         f"plans of project {marker['project_id']} live in the portable workspace {workspace}; run "
                         f"`swissknifeman workspace clone <url>` or `swissknifeman workspace sync --pull`")


def legacy_plans_present(project_root: PathLike) -> bool:
    """Whether ``<project_root>/plans`` still holds a plan folder (a child directory with ``plan.json``)."""
    plans = Path(project_root) / "plans"
    try:
        return any((child / "plan.json").is_file() for child in plans.iterdir() if child.is_dir())
    except OSError:
        return False


def _workspace_project_of(plan_dir: str, env: Env, home: Optional[PathLike]) -> Optional[str]:
    """The project id when ``plan_dir`` is ``<workspace>/projects/<id>/plans[/...]``, else ``None``."""
    projects = os.path.realpath(str(workspace_root(env, home) / "projects"))
    try:
        relative = os.path.relpath(plan_dir, projects)
    except ValueError:
        return None
    parts = relative.split(os.sep)
    if len(parts) >= 2 and parts[0] not in ("..", ".") and parts[1] == "plans":
        return parts[0]
    return None


def _marker_id(root: PathLike) -> Optional[str]:
    try:
        marker = read_marker(root)
    except WorkspaceError:
        return None
    return marker["project_id"] if marker else None


def source_root_of(plan_dir: PathLike, env: Env = None, home: Optional[PathLike] = None,
                   launcher: Optional[PathLike] = None) -> Optional[Path]:
    """The checkout a plan folder belongs to, or ``None`` when it is not bound on this machine.

    A plan folder in the workspace: the launcher project when its marker has the same project id (another id is
    ``PROJECT_CONTEXT_CONFLICT``), else the primary binding of the project and then the other bound paths whose marker has
    that id. A plan folder outside the workspace: the parent of its ``plans/`` folder. ``launcher`` defaults to the
    launcher project of this process (:func:`aicore.state.launcher_root`).
    """
    real = os.path.realpath(str(plan_dir))
    project_id = _workspace_project_of(real, env, home)
    if project_id is None:
        for candidate in (Path(real), *Path(real).parents):
            if candidate.name == "plans":
                return candidate.parent
        return None
    bound = Path(launcher) if launcher is not None else _launcher_root(env)
    if bound is not None:
        launcher_id = _marker_id(bound)
        if launcher_id == project_id:
            return bound
        if launcher_id is not None:
            raise WorkspaceError("PROJECT_CONTEXT_CONFLICT", f"the launcher project is {launcher_id}, but the plan "
                                 f"belongs to {project_id}; run the command from that project")
    entry = read_bindings(env, home)["projects"].get(project_id)
    if entry is None:
        return None
    for candidate in [entry["primary"]] + [path for path in entry["paths"] if path != entry["primary"]]:
        if os.path.isdir(candidate) and _marker_id(candidate) == project_id:
            return Path(candidate)
    return None
