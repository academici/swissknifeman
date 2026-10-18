"""Where the plans of a project live, and which checkout a plan belongs to (stdlib only).

Same rule as ``aicore.workspace.resolve``; read here so the plan store stays stdlib-only (the precedent is
``launcher_project_root``). The project marker ``<root>/.swissknifeman/project.json`` decides: no marker or
``plans_store == "legacy"`` is ``<root>/plans``, ``"workspace"`` is ``<workspaces>/<workspace>/projects/<id>/plans``. The shared
vectors ``packages/aicore/schemas/workspace/v1/resolution-vectors.json`` pin both copies (``tests/engine/test_workspace.py``);
change the rule only together with aicore.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from .model import PlanError

MARKER_RELPATH = ".swissknifeman/project.json"
BINDINGS_FILE = "bindings.json"
_MARKER_SCHEMA = "urn:swissknifeman:aicore:project-marker:v1"
_BINDINGS_SCHEMA = "urn:swissknifeman:aicore:workspace-bindings:v1"
_CODE = re.compile(r"^[a-z]([a-z0-9]|-(?=[a-z0-9])){0,39}$")
_ABSOLUTE = re.compile(r"^(/|[A-Za-z]:[\\/]).+$")
_BOUND_AT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

Env = Optional[Mapping[str, str]]


@dataclass(frozen=True)
class PlansStore:
    """``kind`` is ``legacy`` or ``workspace``; ``reason`` is ``no-marker``, ``marker-legacy`` or ``marker-workspace``;
    ``project_id`` (project code) and ``workspace`` (workspace code) are ``None`` without a marker."""

    kind: str
    plans_root: Path
    project_id: Optional[str]
    reason: str
    workspace: Optional[str] = None


# ---------------------------------------------------------------- locations

def _environment(env: Env) -> Mapping[str, str]:
    return os.environ if env is None else env


def _xdg(env: Mapping[str, str], name: str, default: Path) -> Path:
    value = env.get(name, "")
    # A relative path in an XDG variable is invalid and ignored.
    return Path(value) if value and os.path.isabs(value) else default


def _skm_home(env: Mapping[str, str]) -> Optional[Path]:
    value = env.get("SKM_HOME", "")
    if not value:
        return None
    if not os.path.isabs(value):
        raise ValueError(f"SKM_HOME must be an absolute path, got {value!r}")
    return Path(value)


def _user_home(env: Mapping[str, str]) -> Path:
    return Path(env["HOME"]) if env.get("HOME") else Path.home()


def _machine_home(environment: Mapping[str, str]) -> Path:
    """The machine home: ``$SKM_HOME``, else ``~/.local/share/swissknifeman`` (same rule as ``aicore.state.machine_home``)."""
    home = _skm_home(environment)
    if home is not None:
        return home
    return _user_home(environment) / ".local" / "share" / "swissknifeman"


def _machine_dir(environment: Mapping[str, str], kind: str, legacy: Path) -> Path:
    """``<machine home>/<kind>``; without ``SKM_HOME`` the old XDG folder ``legacy`` while only that one exists."""
    new = _machine_home(environment) / kind
    if _skm_home(environment) is None and not new.exists() and legacy.exists():
        return legacy
    return new


def workspaces_root(env: Env = None) -> Path:
    """The folder of the workspaces: ``SKM_WORKSPACES_ROOT``, else ``SKM_WORKSPACES`` (absolute), else
    ``<machine home>/workspaces`` (``$SKM_HOME`` or ``~/.local/share/swissknifeman``). Nothing is created."""
    environment = _environment(env)
    for name in ("SKM_WORKSPACES_ROOT", "SKM_WORKSPACES"):
        value = environment.get(name, "")
        if value:
            if not os.path.isabs(value):
                raise ValueError(f"{name} must be an absolute path, got {value!r}")
            return Path(value)
    old = _xdg(environment, "XDG_DATA_HOME", _user_home(environment) / ".local" / "share") / "swissknifeman" / "workspaces"
    return _machine_dir(environment, "workspaces", old)


def workspace_root(code: str, env: Env = None) -> Path:
    """The workspace ``code``: ``workspaces_root()/<code>``."""
    if not _CODE.match(code):
        raise ValueError(f"invalid workspace code {code!r}")
    return workspaces_root(env) / code


def state_dir(code: str, env: Env = None) -> Path:
    """Machine files of the workspace ``code`` (bindings, locks): ``<machine home>/state/workspaces/<code>``."""
    if not _CODE.match(code):
        raise ValueError(f"invalid workspace code {code!r}")
    environment = _environment(env)
    old = _xdg(environment, "XDG_STATE_HOME", _user_home(environment) / ".local" / "state") / "swissknifeman"
    return _machine_dir(environment, "state", old) / "workspaces" / code


def launcher_root(env: Env = None) -> Optional[Path]:
    """The project root the project-local launcher bound to this process, else ``None``; the variables of another process
    (a different ``SKM_LAUNCHER_PID``) bind nothing. Same rule as ``aicore.state.launcher_root``."""
    environment = _environment(env)
    if environment.get("SKM_LAUNCHER_ACTIVE") != "1" or environment.get("SKM_LAUNCHER_PID") != str(os.getpid()):
        return None
    root = environment.get("SKM_LAUNCHER_PROJECT_ROOT", "")
    return Path(root) if root else None


# ---------------------------------------------------------------- documents

def read_marker(root: "str | os.PathLike[str]") -> Optional[dict]:
    """The project marker of the checkout at ``root``; ``None`` when there is no file; not JSON, not an object or not
    matching the contract: ``PlanError('PROJECT_MARKER_INVALID')``."""
    path = Path(root) / MARKER_RELPATH
    if not path.exists() and not path.is_symlink():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise PlanError("PROJECT_MARKER_INVALID",
                        f"{MARKER_RELPATH} is not readable JSON: {exc.__class__.__name__}") from None
    problem = _marker_problem(document)
    if problem:
        raise PlanError("PROJECT_MARKER_INVALID", f"{MARKER_RELPATH} does not match {_MARKER_SCHEMA}: {problem}")
    return document


def _marker_problem(document: object) -> Optional[str]:
    if not isinstance(document, dict):
        return "must hold a JSON object"
    extra = sorted(set(document) - {"$schema", "workspace", "project_id", "plans_store"})
    if extra:
        return f"unknown field {extra[0]!r}"
    if document.get("$schema") != _MARKER_SCHEMA:
        return "$schema must be " + _MARKER_SCHEMA
    for key in ("workspace", "project_id"):
        value = document.get(key)
        if not isinstance(value, str) or not _CODE.match(value):
            return f"{key} must be a code: lowercase letters, digits and single hyphens, at most 40 characters"
    if document.get("plans_store") not in ("legacy", "workspace"):
        return "plans_store must be legacy or workspace"
    return None


def read_bindings(code: str, env: Env = None) -> dict:
    """The machine bindings (no lock; the writer replaces the file atomically); an empty document when absent; a damaged
    file is ``PlanError('WORKSPACE_LAYOUT_INVALID')``."""
    path = state_dir(code, env) / BINDINGS_FILE
    if not path.exists():
        return {"$schema": _BINDINGS_SCHEMA, "projects": {}}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise PlanError("WORKSPACE_LAYOUT_INVALID",
                        f"{BINDINGS_FILE} is not readable JSON: {exc.__class__.__name__}") from None
    problem = _bindings_problem(document)
    if problem:
        raise PlanError("WORKSPACE_LAYOUT_INVALID", f"{BINDINGS_FILE} does not match the contract: {problem}")
    return document


def _bindings_problem(document: object) -> Optional[str]:
    if not isinstance(document, dict) or set(document) != {"$schema", "projects"}:
        return "must hold exactly $schema and projects"
    if document["$schema"] != _BINDINGS_SCHEMA:
        return "$schema must be " + _BINDINGS_SCHEMA
    projects = document["projects"]
    if not isinstance(projects, dict):
        return "projects must be an object"
    for project_id, entry in projects.items():
        if not _CODE.match(project_id):
            return f"invalid project code {project_id!r}"
        if not isinstance(entry, dict) or set(entry) != {"paths", "primary", "bound_at"}:
            return f"{project_id}: must hold exactly paths, primary and bound_at"
        paths = entry["paths"]
        if (not isinstance(paths, list) or not paths or len(set(map(str, paths))) != len(paths)
                or not all(isinstance(p, str) and _ABSOLUTE.match(p) for p in paths)):
            return f"{project_id}: paths must be unique absolute paths"
        if not isinstance(entry["primary"], str) or not _ABSOLUTE.match(entry["primary"]):
            return f"{project_id}: primary must be an absolute path"
        if not isinstance(entry["bound_at"], str) or not _BOUND_AT.match(entry["bound_at"]):
            return f"{project_id}: bound_at must be a UTC time"
    return None


# ---------------------------------------------------------------- resolution

def resolve_plans_store(project_root: "str | os.PathLike[str]", env: Env = None) -> PlansStore:
    """The plan store of the checkout at ``project_root``. An invalid marker is ``PROJECT_MARKER_INVALID``; a marker that
    points at the workspace whose project folder is missing is ``WORKSPACE_PROJECT_MISSING``. Nothing is created."""
    root = Path(project_root)
    marker = read_marker(root)
    if marker is None:
        return PlansStore("legacy", root / "plans", None, "no-marker")
    if marker["plans_store"] == "legacy":
        return PlansStore("legacy", root / "plans", marker["project_id"], "marker-legacy", marker["workspace"])
    workspace = workspace_root(marker["workspace"], env)
    plans = workspace / "projects" / marker["project_id"] / "plans"
    if plans.is_dir():
        return PlansStore("workspace", plans, marker["project_id"], "marker-workspace", marker["workspace"])
    raise PlanError("WORKSPACE_PROJECT_MISSING",
                    f"plans of project {marker['project_id']} live in the workspace {marker['workspace']} ({workspace}); "
                    f"run `swissknifeman workspace clone <url>` or `swissknifeman workspace sync --pull`")


def is_workspace_link(project_root: "str | os.PathLike[str]", name: str = "plans", env: Env = None) -> bool:
    """Whether ``<project_root>/<name>`` is a symbolic link that points into the workspace project folder the marker binds
    (the optional link of ``workspace project link``). Same rule as ``aicore.workspace.is_workspace_link``; a checkout without
    a marker, an unusable marker and any other entry give ``False``."""
    path = Path(project_root) / name
    if not path.is_symlink():
        return False
    try:
        marker = read_marker(project_root)
        if marker is None:
            return False
        folder = os.path.realpath(str(workspace_root(marker["workspace"], env) / "projects" / marker["project_id"]))
    except (PlanError, ValueError, OSError):
        return False
    real = os.path.realpath(str(path))
    return real == folder or real.startswith(folder.rstrip(os.sep) + os.sep)


def legacy_plans_present(project_root: "str | os.PathLike[str]", env: Env = None) -> bool:
    """Whether ``<project_root>/plans`` still holds a plan folder (a child directory with ``plan.json``). A symbolic link
    ``plans`` into the workspace project folder the marker binds is the workspace store, not an old copy."""
    if is_workspace_link(project_root, "plans", env):
        return False
    plans = Path(project_root) / "plans"
    try:
        return any((child / "plan.json").is_file() for child in plans.iterdir() if child.is_dir())
    except OSError:
        return False


def workspace_project_of(plan_dir: "str | os.PathLike[str]", env: Env = None) -> Optional[tuple]:
    """``(workspace code, project code)`` when ``plan_dir`` is ``<workspaces>/<ws>/projects/<id>/plans[/...]``, else
    ``None``."""
    base = os.path.realpath(str(workspaces_root(env)))
    try:
        relative = os.path.relpath(os.path.realpath(str(plan_dir)), base)
    except ValueError:
        return None
    parts = relative.split(os.sep)
    if len(parts) >= 4 and _CODE.match(parts[0]) and parts[1] == "projects" and _CODE.match(parts[2]) and parts[3] == "plans":
        return parts[0], parts[2]
    return None


def _marker_key(root: "str | os.PathLike[str]") -> Optional[tuple]:
    try:
        marker = read_marker(root)
    except PlanError:
        return None
    return (marker["workspace"], marker["project_id"]) if marker else None


def source_root_of(plan_dir: "str | os.PathLike[str]", env: Env = None,
                   launcher: "str | os.PathLike[str] | None" = None) -> Optional[Path]:
    """The checkout a plan folder belongs to, or ``None`` when it is not bound on this machine.

    A plan folder in the workspace: the launcher project when its marker has the same project id (another id is
    ``PROJECT_CONTEXT_CONFLICT``), else the primary binding of the project and then the other bound paths whose marker has
    that id. A plan folder outside the workspace: the parent of its ``plans/`` folder. ``launcher`` defaults to the
    launcher project of this process.
    """
    real = os.path.realpath(str(plan_dir))
    found = workspace_project_of(real, env)
    if found is None:
        for candidate in (Path(real), *Path(real).parents):
            if candidate.name == "plans":
                return candidate.parent
        # a custom legacy location (``--plans-root DIR``) inside the launcher project belongs to that checkout
        inside = Path(launcher) if launcher is not None else launcher_root(env)
        if inside is not None:
            inside_real = Path(os.path.realpath(str(inside)))
            if Path(real) == inside_real or inside_real in Path(real).parents:
                return inside
        return None
    workspace, project_id = found
    key = (workspace, project_id)
    bound = Path(launcher) if launcher is not None else launcher_root(env)
    if bound is not None:
        launcher_key = _marker_key(bound)
        if launcher_key == key:
            return bound
        if launcher_key is not None:
            raise PlanError("PROJECT_CONTEXT_CONFLICT", f"the launcher project is {launcher_key[0]}/{launcher_key[1]}, "
                            f"but the plan belongs to {workspace}/{project_id}; run the command from that project")
    entry = read_bindings(workspace, env)["projects"].get(project_id)
    if entry is None:
        return None
    for candidate in [entry["primary"]] + [path for path in entry["paths"] if path != entry["primary"]]:
        if os.path.isdir(candidate) and _marker_key(candidate) == key:
            return Path(candidate)
    return None
