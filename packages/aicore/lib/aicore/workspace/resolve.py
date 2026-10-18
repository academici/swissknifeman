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
from aicore.state.locations import is_code, workspace_root, workspaces_root

from . import WorkspaceError
from .bindings import read_bindings
from .documents import read_marker
from .links import is_workspace_link

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]


@dataclass(frozen=True)
class PlansStore:
    """``kind`` is ``legacy`` or ``workspace``; ``reason`` is ``no-marker``, ``marker-legacy`` or ``marker-workspace``;
    ``project_id`` (the project code) and ``workspace`` (the workspace code) are ``None`` without a marker."""

    kind: str
    plans_root: Path
    project_id: Optional[str]
    reason: str
    workspace: Optional[str] = None


def resolve_plans_store(project_root: PathLike, env: Env = None, home: Optional[PathLike] = None) -> PlansStore:
    """The plan store of the checkout at ``project_root``. An invalid marker is ``PROJECT_MARKER_INVALID``; a marker that
    points at the workspace whose project folder is missing is ``WORKSPACE_PROJECT_MISSING``. Nothing is created."""
    root = Path(project_root)
    marker = read_marker(root)
    if marker is None:
        return PlansStore("legacy", root / "plans", None, "no-marker")
    if marker["plans_store"] == "legacy":
        return PlansStore("legacy", root / "plans", marker["project_id"], "marker-legacy", marker.get("workspace"))
    workspace = workspace_root(env, home, code=marker["workspace"])
    plans = workspace / "projects" / marker["project_id"] / "plans"
    if plans.is_dir():
        return PlansStore("workspace", plans, marker["project_id"], "marker-workspace", marker["workspace"])
    raise WorkspaceError("WORKSPACE_PROJECT_MISSING",
                         f"plans of project {marker['project_id']} live in the workspace {marker['workspace']} "
                         f"({workspace}); run `swissknifeman workspace clone <url>` or `swissknifeman workspace sync --pull`")


def legacy_plans_present(project_root: PathLike, env: Env = None, home: Optional[PathLike] = None) -> bool:
    """Whether ``<project_root>/plans`` still holds a plan folder (a child directory with ``plan.json``). A symbolic link
    ``plans`` that points into the workspace project folder the marker binds is the workspace store itself (the optional link
    of ``workspace project link``), not an old copy: it holds nothing legacy."""
    if is_workspace_link(project_root, "plans", env, home):
        return False
    plans = Path(project_root) / "plans"
    try:
        return any((child / "plan.json").is_file() for child in plans.iterdir() if child.is_dir())
    except OSError:
        return False


def _workspace_project_of(plan_dir: str, env: Env, home: Optional[PathLike]) -> Optional[tuple]:
    """``(workspace code, project code)`` when ``plan_dir`` is ``<workspaces>/<ws>/projects/<id>/plans[/...]``, else
    ``None``."""
    base = os.path.realpath(str(workspaces_root(env, home)))
    try:
        relative = os.path.relpath(plan_dir, base)
    except ValueError:
        return None
    parts = relative.split(os.sep)
    if len(parts) >= 4 and is_code(parts[0]) and parts[1] == "projects" and is_code(parts[2]) and parts[3] == "plans":
        return parts[0], parts[2]
    return None


def _marker_key(root: PathLike) -> Optional[tuple]:
    try:
        marker = read_marker(root)
    except WorkspaceError:
        return None
    return (marker["workspace"], marker["project_id"]) if marker else None


def source_root_of(plan_dir: PathLike, env: Env = None, home: Optional[PathLike] = None,
                   launcher: Optional[PathLike] = None) -> Optional[Path]:
    """The checkout a plan folder belongs to, or ``None`` when it is not bound on this machine.

    A plan folder in the workspace: the launcher project when its marker has the same project id (another id is
    ``PROJECT_CONTEXT_CONFLICT``), else the primary binding of the project and then the other bound paths whose marker has
    that id. A plan folder outside the workspace: the parent of its ``plans/`` folder. ``launcher`` defaults to the
    launcher project of this process (:func:`aicore.state.launcher_root`).
    """
    real = os.path.realpath(str(plan_dir))
    found = _workspace_project_of(real, env, home)
    if found is None:
        for candidate in (Path(real), *Path(real).parents):
            if candidate.name == "plans":
                return candidate.parent
        return None
    workspace, project_id = found
    key = (workspace, project_id)
    bound = Path(launcher) if launcher is not None else _launcher_root(env)
    if bound is not None:
        launcher_key = _marker_key(bound)
        if launcher_key == key:
            return bound
        if launcher_key is not None:
            raise WorkspaceError("PROJECT_CONTEXT_CONFLICT", f"the launcher project is {launcher_key[0]}/{launcher_key[1]}, "
                                 f"but the plan belongs to {workspace}/{project_id}; run the command from that project")
    scoped = dict(os.environ if env is None else env)
    scoped["SKM_WORKSPACE"] = workspace
    entry = read_bindings(scoped, home)["projects"].get(project_id)
    if entry is None:
        return None
    for candidate in [entry["primary"]] + [path for path in entry["paths"] if path != entry["primary"]]:
        if os.path.isdir(candidate) and _marker_key(candidate) == key:
            return Path(candidate)
    return None
