"""Projects of the workspace and the checkouts of this machine: attach (``project add`` is the same call), list (also of
all workspaces), show, scan, rebind, detach, remove.

Identity is the pair ``workspace`` + ``project_id`` (both codes) of the marker in the repository
(``.swissknifeman/project.json``); the code of a project is the name of its folder in the workspace and, as a rule, the
name of the checkout folder. Remotes only help ``attach`` find a project that already exists. ``attach`` writes the marker
but never commits it.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from aicore.workspace import (MARKER_RELPATH, WorkspaceError, bind, checkout_remotes, is_code, project_dir,
                              read_bindings, read_marker, read_project, set_paths, unbind, write_marker, write_project)

from . import gitutil, layout, links
from .pathtypes import PathLike

Env = Optional[Mapping[str, str]]

SCAN_DEPTH = 4
SCAN_SKIP = frozenset({"node_modules", ".git", "vendor"})


def _real(path: PathLike) -> Path:
    return Path(os.path.realpath(os.path.abspath(os.path.expanduser(str(path)))))


def slug(name: str) -> str:
    """A project code made from a folder name: lowercase words of letters and digits joined by ``-``."""
    text = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not text:
        return "project"
    if not text[0].isalpha():
        text = "p-" + text
    return text[:40].rstrip("-")


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
           confirm: Optional[Callable[[str], bool]] = None, env: Env = None, home: Optional[PathLike] = None,
           code: Optional[str] = None, link_folders: bool = False) -> Dict[str, Any]:
    """Attach the checkout ``project`` to a project of the workspace (contract: identity). ``code`` is the project code of
    a new project (default: made from the folder name; ``PROJECT_CODE_TAKEN`` when another project has it).

    Returns ``{workspace, project_id, name, created, marker_written, plans_store, binding, next, links}``. ``interactive`` (default: stdin is
    a terminal) allows a question when remotes match one existing project and ``yes`` is not given. ``links`` (only when links were
    made, kept or refused) is the result of :func:`workspace.links.link`: ``link_folders`` asks for the links of ``plans/`` and
    ``tasks/`` and records the choice for the project, else they are made while ``workspace.link_folders`` is on.
    """
    root = _real(project)
    if not root.is_dir():
        raise WorkspaceError("BINDING_PATH_MISSING", f"{root} is not a directory")
    if code is not None and not is_code(code):
        raise WorkspaceError("PROJECT_CODE_INVALID", f"{code!r} is not a code: lowercase letters, digits and single "
                             f"hyphens, starting with a letter, at most 40 characters")
    target = layout.root_of(None, env, home)
    layout.require_initialized(target)
    with gitutil.git_lock(env, home):  # read the marker, pick or create the project and write the marker as one step
        doc = _attach_locked(root, target, name, yes, interactive, confirm, env, home, code)
        made = links.ensure(root, env, home, locked=True, force=link_folders, remember=link_folders)
    if made is not None:
        doc["links"] = made
    return doc


def _attach_locked(root: Path, target: Path, name: Optional[str], yes: bool, interactive: Optional[bool],
                   confirm: Optional[Callable[[str], bool]], env: Env, home: Optional[PathLike],
                   code: Optional[str] = None) -> Dict[str, Any]:
    workspace = layout.require_initialized(target)["code"]
    marker = read_marker(root)
    remotes = checkout_remotes(root)
    created = False
    marker_written = False
    if marker is not None:
        if marker["workspace"] != workspace:
            raise WorkspaceError("WORKSPACE_MISMATCH", f"the marker of {root.name} names the workspace "
                                 f"{marker['workspace']!r}, this command works with {workspace!r} (--workspace)")
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
            project_id = code or slug(root.name)
            if read_project(target, project_id) is not None:
                raise WorkspaceError("PROJECT_CODE_TAKEN", f"the workspace {workspace!r} already has a project "
                                     f"{project_id!r} with other remotes; choose another code with --code")
            record = write_project(target, project_id, name or root.name, remotes=remotes)
            created = True
        project_id = record["project_id"]
        plans_store = "legacy" if _has_plan_folder(root) else "workspace"
        write_marker(root, workspace, project_id, plans_store)
        marker_written = True
        if plans_store == "workspace":
            plans = project_dir(target, project_id) / "plans"
            plans.mkdir(parents=True, exist_ok=True)
            (plans / ".gitkeep").touch()  # git keeps no empty folder: without a file the store is lost in a transfer
    entry = bind(project_id, root, env, home)
    doc: Dict[str, Any] = {"workspace": workspace, "project_id": project_id, "name": record["name"], "created": created,
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


def list_all(env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """The projects of every workspace of this machine: ``{projects, skipped}``. A row is the row of ``list_projects`` plus
    ``workspace`` (its code); a workspace whose documents cannot be read is in ``skipped`` as ``{workspace, error}``."""
    from aicore.state import list_workspaces
    rows: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    for code in list_workspaces(env, home):
        try:
            found = list_projects(layout.scoped_env(code, env), home)
        except WorkspaceError as exc:
            skipped.append({"workspace": code, "error": exc.code})
            continue
        rows.extend({"workspace": code, **row} for row in found)
    return {"projects": rows, "skipped": skipped}


def _held(folder: Path) -> List[str]:
    """What a project folder of the workspace holds besides ``project.json`` and an empty plans store (paths relative to
    the folder, sorted); a symbolic link counts as held."""
    free = {"project.json", *(f"{name}/.gitkeep" for name in ("plans", "tasks"))}
    held: List[str] = []
    for current, dirs, files in os.walk(str(folder)):
        relative = Path(current).relative_to(folder)
        held.extend((relative / name).as_posix() for name in files if (relative / name).as_posix() not in free)
        held.extend((relative / name).as_posix() for name in dirs if os.path.islink(os.path.join(current, name)))
    return sorted(held)


def remove(project_id: str, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Remove a project that holds nothing from the workspace: its folder (``project.json``, an empty plans store) and its
    binding on this machine. A project that holds files (plans, legacy plans, migrations, local-only index) is
    ``PROJECT_NOT_EMPTY`` and nothing changes; the markers in the checkouts are left alone (``markers`` lists those that
    still name the project; ``attach`` writes the record again). Returns ``{workspace, project_id, removed, unbound, markers}``."""
    target = layout.root_of(None, env, home)
    workspace = layout.require_initialized(target)["code"]
    try:
        folder = project_dir(target, project_id)
    except ValueError:
        raise WorkspaceError("PROJECT_UNKNOWN", f"{project_id!r} is not a project id") from None
    with gitutil.git_lock(env, home):
        if not folder.is_dir() or folder.is_symlink():
            raise WorkspaceError("PROJECT_UNKNOWN", f"no project {project_id} in the workspace")
        held = _held(folder)
        if held:
            shown = ", ".join(held[:3]) + (f" and {len(held) - 3} more" if len(held) > 3 else "")
            raise WorkspaceError("PROJECT_NOT_EMPTY", f"the project {project_id} holds {len(held)} file(s) ({shown}); a "
                                 f"project with plans is not removed; `project detach {project_id}` drops only its "
                                 f"binding on this machine")
        entry = read_bindings(env, home)["projects"].get(project_id)
        paths = list(entry["paths"]) if entry else []
        markers = []
        for path in paths:
            try:
                marker = read_marker(path) if os.path.isdir(path) else None
            except WorkspaceError:
                marker = None
            if marker is not None and marker["workspace"] == workspace and marker["project_id"] == project_id:
                markers.append(path)
        try:
            shutil.rmtree(folder)
        except OSError as exc:
            raise WorkspaceError("PROJECT_REMOVE_FAILED", f"cannot remove {folder}: {exc}") from None
        unbind(project_id, None, env, home)
    return {"workspace": workspace, "project_id": project_id, "removed": True, "unbound": paths, "markers": markers}


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
    workspace = layout.require_initialized(target)["code"]
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
                if marker["workspace"] != workspace:
                    skipped.append({"path": current, "reason": "OTHER_WORKSPACE", "workspace": marker["workspace"]})
                elif marker["project_id"] in known:
                    bind(marker["project_id"], current, env, home)
                    bound.append({"project_id": marker["project_id"], "path": current})
                else:
                    unknown.append({"project_id": marker["project_id"], "path": current})
                continue
            dirs[:] = sorted(name for name in dirs
                             if name not in SCAN_SKIP and depth < SCAN_DEPTH and not os.path.islink(os.path.join(current, name)))
    return {"bound": bound, "unknown": unknown, "skipped": skipped}


def rebind(project_id: str, path: PathLike, env: Env = None, home: Optional[PathLike] = None, *,
           preserve_paths: bool = False, include_paths: Sequence[PathLike] = ()) -> Dict[str, Any]:
    """Replace the paths of a project by one checkout whose marker names the project.

    With ``preserve_paths``, keep the previous paths and make ``path`` primary, atomically including ``include_paths``.
    Every supplied checkout must have the same workspace/project marker; include paths require preservation.
    """
    if include_paths and not preserve_paths:
        raise ValueError("--include-path requires --preserve-paths")
    target = layout.root_of(None, env, home)
    workspace = layout.require_initialized(target)["code"]
    if not _is_project(target, project_id):
        raise WorkspaceError("PROJECT_UNKNOWN", f"no project {project_id} in the workspace")
    root = _real(path)
    roots = [root, *(_real(item) for item in include_paths)]
    for checkout in roots:
        if not checkout.is_dir():
            raise WorkspaceError("BINDING_PATH_MISSING", f"{checkout} is not a directory")
        marker = read_marker(checkout)
        if marker is None:
            raise WorkspaceError("BINDING_MARKER_MISMATCH", f"{checkout} has no marker, not the marker of {project_id}")
        if marker["workspace"] != workspace:
            raise WorkspaceError("WORKSPACE_MISMATCH", f"{checkout} belongs to the workspace {marker['workspace']!r}")
        if marker["project_id"] != project_id:
            raise WorkspaceError("BINDING_MARKER_MISMATCH",
                                 f"{checkout} has the marker of {marker['project_id']}, not the marker of {project_id}")
    entry = (set_paths(project_id, roots, env, home, preserve=True, primary=root) if preserve_paths
             else set_paths(project_id, roots, env, home))
    if entry is None:  # set_paths removes a project only for no paths
        raise WorkspaceError("BINDING_PATH_MISSING", f"{root} could not be bound to {project_id}")
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
