"""Where the plans of a project live, and which checkout a plan belongs to (stdlib only).

Same rule as ``aicore.workspace.resolve``; read here so the plan store stays stdlib-only (the precedent is
``launcher_project_root``). The project marker ``<root>/.swissknifeman/project.json`` decides: no marker or
``plans_store == "legacy"`` is ``<root>/plans``, ``"workspace"`` is ``<workspace>/projects/<id>/plans``. The shared
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
_PROJECT_ID = re.compile(r"^prj_[0-9A-HJKMNP-TV-Z]{26}$")
_ABSOLUTE = re.compile(r"^(/|[A-Za-z]:[\\/]).+$")
_BOUND_AT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

Env = Optional[Mapping[str, str]]


@dataclass(frozen=True)
class PlansStore:
    """``kind`` is ``legacy`` or ``workspace``; ``reason`` is ``no-marker``, ``marker-legacy`` or ``marker-workspace``;
    ``project_id`` is ``None`` without a marker."""

    kind: str
    plans_root: Path
    project_id: Optional[str]
    reason: str


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


def workspace_root(env: Env = None) -> Path:
    """The portable workspace: ``SKM_WORKSPACE_ROOT`` (absolute), else ``<data>/workspace`` (``$SKM_HOME/data`` or
    ``$XDG_DATA_HOME|~/.local/share`` + ``/swissknifeman``). Nothing is created."""
    environment = _environment(env)
    value = environment.get("SKM_WORKSPACE_ROOT", "")
    if value:
        if not os.path.isabs(value):
            raise ValueError(f"SKM_WORKSPACE_ROOT must be an absolute path, got {value!r}")
        return Path(value)
    home = _skm_home(environment)
    if home is not None:
        return home / "data" / "workspace"
    return _xdg(environment, "XDG_DATA_HOME", _user_home(environment) / ".local" / "share") / "swissknifeman" / "workspace"


def state_dir(env: Env = None) -> Path:
    """Machine files of the workspace (bindings, locks): ``$SKM_HOME/state/workspace`` or
    ``$XDG_STATE_HOME|~/.local/state`` + ``/swissknifeman/workspace``."""
    environment = _environment(env)
    home = _skm_home(environment)
    if home is not None:
        return home / "state" / "workspace"
    return _xdg(environment, "XDG_STATE_HOME", _user_home(environment) / ".local" / "state") / "swissknifeman" / "workspace"


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
    extra = sorted(set(document) - {"$schema", "project_id", "plans_store"})
    if extra:
        return f"unknown field {extra[0]!r}"
    if document.get("$schema") != _MARKER_SCHEMA:
        return "$schema must be " + _MARKER_SCHEMA
    project_id = document.get("project_id")
    if not isinstance(project_id, str) or not _PROJECT_ID.match(project_id):
        return "project_id must look like prj_ and 26 Crockford base32 characters"
    if document.get("plans_store") not in ("legacy", "workspace"):
        return "plans_store must be legacy or workspace"
    return None


def read_bindings(env: Env = None) -> dict:
    """The machine bindings (no lock; the writer replaces the file atomically); an empty document when absent; a damaged
    file is ``PlanError('WORKSPACE_LAYOUT_INVALID')``."""
    path = state_dir(env) / BINDINGS_FILE
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
        if not _PROJECT_ID.match(project_id):
            return f"invalid project id {project_id!r}"
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
        return PlansStore("legacy", root / "plans", marker["project_id"], "marker-legacy")
    workspace = workspace_root(env)
    plans = workspace / "projects" / marker["project_id"] / "plans"
    if plans.is_dir():
        return PlansStore("workspace", plans, marker["project_id"], "marker-workspace")
    raise PlanError("WORKSPACE_PROJECT_MISSING",
                    f"plans of project {marker['project_id']} live in the portable workspace {workspace}; run "
                    f"`swissknifeman workspace clone <url>` or `swissknifeman workspace sync --pull`")


def legacy_plans_present(project_root: "str | os.PathLike[str]") -> bool:
    """Whether ``<project_root>/plans`` still holds a plan folder (a child directory with ``plan.json``)."""
    plans = Path(project_root) / "plans"
    try:
        return any((child / "plan.json").is_file() for child in plans.iterdir() if child.is_dir())
    except OSError:
        return False


def workspace_project_of(plan_dir: "str | os.PathLike[str]", env: Env = None) -> Optional[str]:
    """The project id when ``plan_dir`` is ``<workspace>/projects/<id>/plans[/...]``, else ``None``."""
    projects = os.path.realpath(str(workspace_root(env) / "projects"))
    try:
        relative = os.path.relpath(os.path.realpath(str(plan_dir)), projects)
    except ValueError:
        return None
    parts = relative.split(os.sep)
    if len(parts) >= 2 and parts[0] not in ("..", ".") and parts[1] == "plans":
        return parts[0]
    return None


def _marker_id(root: "str | os.PathLike[str]") -> Optional[str]:
    try:
        marker = read_marker(root)
    except PlanError:
        return None
    return marker["project_id"] if marker else None


def source_root_of(plan_dir: "str | os.PathLike[str]", env: Env = None,
                   launcher: "str | os.PathLike[str] | None" = None) -> Optional[Path]:
    """The checkout a plan folder belongs to, or ``None`` when it is not bound on this machine.

    A plan folder in the workspace: the launcher project when its marker has the same project id (another id is
    ``PROJECT_CONTEXT_CONFLICT``), else the primary binding of the project and then the other bound paths whose marker has
    that id. A plan folder outside the workspace: the parent of its ``plans/`` folder. ``launcher`` defaults to the
    launcher project of this process.
    """
    real = os.path.realpath(str(plan_dir))
    project_id = workspace_project_of(real, env)
    if project_id is None:
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
    bound = Path(launcher) if launcher is not None else launcher_root(env)
    if bound is not None:
        launcher_id = _marker_id(bound)
        if launcher_id == project_id:
            return bound
        if launcher_id is not None:
            raise PlanError("PROJECT_CONTEXT_CONFLICT", f"the launcher project is {launcher_id}, but the plan "
                            f"belongs to {project_id}; run the command from that project")
    entry = read_bindings(env)["projects"].get(project_id)
    if entry is None:
        return None
    for candidate in [entry["primary"]] + [path for path in entry["paths"] if path != entry["primary"]]:
        if os.path.isdir(candidate) and _marker_id(candidate) == project_id:
            return Path(candidate)
    return None
