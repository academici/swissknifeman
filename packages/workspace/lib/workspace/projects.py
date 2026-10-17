"""Projects of the workspace and the checkouts of this machine: attach, list, show, scan, rebind, detach.

Identity is the ``project_id`` of the marker in the repository (``.swissknifeman/project.json``); remotes only help
``attach`` find a project that already exists. ``attach`` writes the marker but never commits it.
"""
from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

from aicore.workspace import (MARKER_RELPATH, WorkspaceError, bind, checkout_remotes, new_id, project_dir,
                              read_bindings, read_marker, read_project, set_paths, unbind, write_marker, write_project)

from . import gitutil, layout

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]

SCAN_DEPTH = 4
SCAN_SKIP = frozenset({"node_modules", ".git", "vendor"})


def _real(path: PathLike) -> Path:
    return Path(os.path.realpath(os.path.abspath(os.path.expanduser(str(path)))))


def _has_plan_folder(root: Path) -> bool:
    try:
        return any(child.is_dir() for child in (root / "plans").iterdir())
    except OSError:
        return False


def _known_projects(target: Path) -> List[Dict[str, Any]]:
    """The valid ``project.json`` documents of the workspace, by folder name."""
    found = []
    for project_id in layout.project_ids(target):
        try:
            record = read_project(target, project_id)
        except WorkspaceError:
            continue
        if record is not None:
            found.append(record)
    return found


def _confirm_default(question: str) -> bool:
    print(question, end=" ", file=sys.stderr, flush=True)
    answer = sys.stdin.readline().strip().lower()
    return answer in ("y", "yes")


def attach(project: PathLike, name: Optional[str] = None, yes: bool = False, interactive: Optional[bool] = None,
           confirm: Optional[Callable[[str], bool]] = None, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Attach the checkout ``project`` to a project of the workspace (contract: identity).

    Returns ``{project_id, name, created, marker_written, plans_store, binding, next}``. ``interactive`` (default: stdin is
    a terminal) allows a question when remotes match one existing project and ``yes`` is not given.
    """
    root = _real(project)
    if not root.is_dir():
        raise WorkspaceError("BINDING_PATH_MISSING", f"{root} is not a directory")
    target = layout.root_of(None, env, home)
    layout.require_initialized(target)
    with gitutil.git_lock(env, home):  # read the marker, pick or create the project and write the marker as one step
        return _attach_locked(root, target, name, yes, interactive, confirm, env, home)


def _attach_locked(root: Path, target: Path, name: Optional[str], yes: bool, interactive: Optional[bool],
                   confirm: Optional[Callable[[str], bool]], env: Env, home: Optional[PathLike]) -> Dict[str, Any]:
    marker = read_marker(root)
    remotes = checkout_remotes(root)
    created = False
    marker_written = False
    if marker is not None:
        project_id = marker["project_id"]
        plans_store = marker["plans_store"]
        record = read_project(target, project_id)
        if record is None:
            record = write_project(target, project_id, name or root.name, remotes=remotes)
            created = True
    else:
        matches = [record for record in _known_projects(target) if set(record["identity"]["remotes"]) & set(remotes)]
        if len(matches) > 1:
            listing = ", ".join(f"{item['project_id']} ({item['name']})" for item in matches)
            raise WorkspaceError("PROJECT_AMBIGUOUS", f"the remotes of {root.name} match several projects: {listing}; "
                                 f"add the marker of the right one to the checkout and attach again")
        record = None
        if len(matches) == 1:
            found = matches[0]
            ask = sys.stdin.isatty() if interactive is None else interactive
            if not yes:
                question = f"Use the existing project {found['project_id']} ({found['name']}) for {root.name}? [y/N]"
                if not ask or not (confirm or _confirm_default)(question):
                    raise WorkspaceError("ATTACH_CONFIRM_REQUIRED",
                                         f"the remotes of {root.name} match the project {found['project_id']} "
                                         f"({found['name']}); repeat with --yes to use it")
            record = found
        else:
            record = write_project(target, new_id("prj"), name or root.name, remotes=remotes)
            created = True
        project_id = record["project_id"]
        plans_store = "legacy" if _has_plan_folder(root) else "workspace"
        write_marker(root, project_id, plans_store)
        marker_written = True
        if plans_store == "workspace":
            plans = project_dir(target, project_id) / "plans"
            plans.mkdir(parents=True, exist_ok=True)
            (plans / ".gitkeep").touch()  # git keeps no empty folder: without a file the store is lost in a transfer
    entry = bind(project_id, root, env, home)
    doc: Dict[str, Any] = {"project_id": project_id, "name": record["name"], "created": created,
                           "marker_written": marker_written, "plans_store": plans_store,
                           "binding": {"paths": entry["paths"], "primary": entry["primary"]}}
    if marker_written:
        doc["next"] = (f"git -C {shlex.quote(str(root))} add {MARKER_RELPATH} && "
                       f"git -C {shlex.quote(str(root))} commit -m 'chore: project marker'")
    return doc


def list_projects(env: Env = None, home: Optional[PathLike] = None) -> List[Dict[str, Any]]:
    """The projects of the workspace with their binding on this machine."""
    target = layout.root_of(None, env, home)
    layout.require_initialized(target)
    rows = []
    for row in layout.project_rows(target, env, home):
        item = {"project_id": row["project_id"], "name": row["name"], "status": row["status"], "bound": row["bound"],
                "paths": row["paths"]}
        if "error" in row:
            item["error"] = row["error"]
        rows.append(item)
    return rows


def _names(folder: Path, only_dirs: bool = True) -> List[str]:
    try:
        return sorted(child.name for child in folder.iterdir() if (child.is_dir() or not only_dirs))
    except OSError:
        return []


def show(project_id: str, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """``project.json``, the binding on this machine and the folders the project holds in the workspace."""
    target = layout.root_of(None, env, home)
    layout.require_initialized(target)
    try:
        folder = project_dir(target, project_id)
    except ValueError:
        raise WorkspaceError("PROJECT_UNKNOWN", f"{project_id!r} is not a project id") from None
    record = read_project(target, project_id)
    if record is None:
        raise WorkspaceError("PROJECT_UNKNOWN", f"no project {project_id} in the workspace")
    entry = read_bindings(env, home)["projects"].get(project_id)
    plans = folder / "plans"
    migrations = [name[:-5] for name in _names(folder / "migrations", only_dirs=False) if name.endswith(".json")]
    return {"project": record, "binding": entry,
            "plans": {"plans": [name for name in _names(plans) if name != "archive"],
                      "archived": _names(plans / "archive"), "legacy": _names(folder / "legacy-plans"),
                      "migrations": migrations}}


def scan(directories: Sequence[PathLike], env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Find checkouts with a marker under ``directories`` (depth 4) and bind those of known projects. A marker whose id
    is not in the workspace is reported as ``unknown``; no project is created."""
    target = layout.root_of(None, env, home)
    layout.require_initialized(target)
    known = {record["project_id"] for record in _known_projects(target)}
    bound: List[Dict[str, str]] = []
    unknown: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    for directory in directories:
        base = _real(directory)
        if not base.is_dir():
            skipped.append({"path": str(base), "reason": "missing"})
            continue
        for current, dirs, _files in os.walk(str(base)):
            depth = 0 if current == str(base) else len(Path(current).relative_to(base).parts)
            if os.path.isfile(os.path.join(current, MARKER_RELPATH)):
                dirs[:] = []  # a checkout: do not look into it
                try:
                    marker = read_marker(current)
                except WorkspaceError as exc:
                    skipped.append({"path": current, "reason": exc.code})
                    continue
                if marker is None:
                    continue
                if marker["project_id"] in known:
                    bind(marker["project_id"], current, env, home)
                    bound.append({"project_id": marker["project_id"], "path": current})
                else:
                    unknown.append({"project_id": marker["project_id"], "path": current})
                continue
            dirs[:] = sorted(name for name in dirs
                             if name not in SCAN_SKIP and depth < SCAN_DEPTH and not os.path.islink(os.path.join(current, name)))
    return {"bound": bound, "unknown": unknown, "skipped": skipped}


def rebind(project_id: str, path: PathLike, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Replace the paths of a project by one checkout whose marker names the project."""
    target = layout.root_of(None, env, home)
    layout.require_initialized(target)
    if not _is_project(target, project_id):
        raise WorkspaceError("PROJECT_UNKNOWN", f"no project {project_id} in the workspace")
    root = _real(path)
    if not root.is_dir():
        raise WorkspaceError("BINDING_PATH_MISSING", f"{root} is not a directory")
    marker = read_marker(root)
    if marker is None or marker["project_id"] != project_id:
        found = "no marker" if marker is None else f"the marker of {marker['project_id']}"
        raise WorkspaceError("BINDING_MARKER_MISMATCH", f"{root} has {found}, not the marker of {project_id}")
    entry = set_paths(project_id, [root], env, home)
    return {"project_id": project_id, "binding": {"paths": entry["paths"], "primary": entry["primary"]}}


def detach(project_id: str, path: Optional[PathLike] = None, env: Env = None,
           home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Remove the binding of a project (all of it, or one path) from this machine; the workspace is not changed."""
    target = layout.root_of(None, env, home)
    layout.require_initialized(target)
    entry = read_bindings(env, home)["projects"].get(project_id)
    if entry is None and not _is_project(target, project_id):
        raise WorkspaceError("PROJECT_UNKNOWN", f"no project {project_id} in the workspace or in the bindings")
    removed = unbind(project_id, path, env, home)
    remaining = read_bindings(env, home)["projects"].get(project_id)
    return {"project_id": project_id, "removed": removed,
            "binding": None if remaining is None else {"paths": remaining["paths"], "primary": remaining["primary"]}}


def _is_project(target: Path, project_id: str) -> bool:
    try:
        return read_project(target, project_id) is not None
    except (WorkspaceError, ValueError):
        return False
