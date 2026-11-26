"""The optional links ``plans/`` and ``tasks/`` in a checkout (decision D5): make, remove and keep them.

The setting ``workspace.link_folders`` (default off; machine layer, per-project override in ``projects/<code>/local/config.toml``)
says whether a project's checkout carries symbolic links ``<checkout>/plans`` and ``<checkout>/tasks`` to the folders of the
project in the workspace. ``attach``/``add`` and ``sync`` call :func:`ensure` / :func:`keep` and so make or repair the links of
every project whose setting is on; :func:`link` and :func:`unlink` are the explicit commands and record the choice for the one
project (``link_folders = true|false`` in its ``local/config.toml``). The links are listed in the checkout's own
``.git/info/exclude`` (never in a tracked file). Rules that hold everywhere:

- a real folder or file, and a link that points anywhere but the project folder, is never replaced or removed (it is reported
  as ``refused``/``skipped``);
- ``plans/`` is linked only while the plans of the project live in the workspace (``plans_store`` of the marker);
- the folders in the workspace are created when missing (``tasks/`` with a ``.gitkeep``, as the plans store has one);
- an automatic call (:func:`ensure`, :func:`keep`) never fails the command that made it: a problem is part of its result.

Readers that look at the old ``<checkout>/plans`` ignore a link into the bound workspace: :func:`aicore.workspace.is_workspace_link`.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aicore.config import ConfigError, resolve
from aicore.config.model import edit_layer_file
from aicore.state import project_config_file
from aicore.workspace import (LINK_NAMES, WorkspaceError, bound_project_folder, ensure_local, inspect_folder, read_bindings,
                              read_marker)
from aicore.workspace.links import read_exclude, write_exclude

from . import gitutil, layout
from .pathtypes import PathLike

Env = Optional[Mapping[str, str]]

SETTING = "link_folders"
SCHEMA = gitutil.UNIT_ROOT / "configs" / "config.schema.json"


def _real(path: PathLike) -> Path:
    return Path(os.path.realpath(os.path.abspath(os.path.expanduser(str(path)))))


def enabled(root: PathLike, env: Env = None, home: Optional[PathLike] = None) -> bool:
    """``workspace.link_folders`` for the checkout ``root`` (defaults, machine, then the project layer); off when the
    configuration cannot be read."""
    try:
        config = resolve("workspace", unit_root=gitutil.UNIT_ROOT, project=root, env=env, home=home, warn=lambda message: None)
        return bool(config.get(SETTING))
    except (ConfigError, WorkspaceError, ValueError, TypeError):
        return False


def set_enabled(root: PathLike, value: bool, env: Env = None, home: Optional[PathLike] = None) -> Path:
    """Write ``link_folders = value`` into the project layer of the checkout (``local/config.toml`` of the project in its
    workspace) and return that file. ``PROJECT_UNKNOWN`` while the project is not in the workspace on this machine,
    ``PROJECT_LOCAL_CONFIG_INVALID`` when the file cannot be edited (it is left as it was)."""
    marker = read_marker(root)
    folder = bound_project_folder(root, env, home)
    if marker is None or folder is None:
        raise WorkspaceError("PROJECT_MARKER_MISSING", f"{root} has no project marker")
    ensure_local(folder.parents[1], marker["project_id"])
    target = project_config_file(root, env=env, home=home)
    try:
        edit_layer_file(target, "workspace", SETTING, bool(value), schema=SCHEMA, layer="project", project=root, env=env,
                        home=home)
    except ConfigError as exc:
        raise WorkspaceError("PROJECT_LOCAL_CONFIG_INVALID", exc.message) from None
    return target


def _context(root: Path, env: Env, home: Optional[PathLike]) -> Dict[str, Any]:
    """The marker and the project folder of ``root`` in the selected workspace, or the refusal that says why not."""
    marker = read_marker(root)
    if marker is None:
        raise WorkspaceError("PROJECT_MARKER_MISSING", f"{root} has no project marker; run `workspace project attach` first")
    workspace = layout.require_initialized(layout.root_of(None, env, home))["code"]
    if marker["workspace"] != workspace:
        raise WorkspaceError("WORKSPACE_MISMATCH", f"the marker of {root.name} names the workspace {marker['workspace']!r}, "
                             f"this command works with {workspace!r} (--workspace)")
    folder = bound_project_folder(root, env, home)
    if folder is None or not folder.is_dir():
        raise WorkspaceError("PROJECT_UNKNOWN", f"no project {marker['project_id']} in the workspace {workspace}; run "
                             f"`workspace project attach` or `workspace sync --pull`")
    return {"marker": marker, "folder": folder, "workspace": workspace}


def _make_target(target: Path, name: str, env: Env, home: Optional[PathLike], locked: bool) -> None:
    """Create the workspace folder a link points to (``tasks/`` gets a ``.gitkeep``: git keeps no empty folder)."""
    if target.is_dir() and (name != "tasks" or any(target.iterdir())):
        return

    def make() -> None:
        target.mkdir(parents=True, exist_ok=True)
        if name == "tasks" and not any(target.iterdir()):
            (target / ".gitkeep").touch()

    try:
        if locked:
            make()
        else:
            with gitutil.git_lock(env, home):
                make()
    except OSError as exc:
        raise WorkspaceError("LINK_FAILED", f"cannot create {target}: {exc}") from None


def _result(root: Path, context: Dict[str, Any], rows: List[Dict[str, Any]], exclude: Optional[Path],
            enabled_now: Optional[bool], problem: Optional[str] = None) -> Dict[str, Any]:
    doc: Dict[str, Any] = {"workspace": context["workspace"], "project_id": context["marker"]["project_id"],
                           "path": str(root), "links": rows, "exclude": None if exclude is None else str(exclude),
                           "enabled": enabled_now}
    if problem:
        doc["problem"] = problem
    return doc


def _sync_exclude(root: Path, folder: Path) -> Optional[Path]:
    names = [name for name in LINK_NAMES if inspect_folder(root, name, folder)["state"] == "linked"]
    return write_exclude(root, names)


def _take_back(rows: List[Dict[str, Any]]) -> None:
    """Remove the links a failed :func:`link` call made: an absolute link that no exclude line covers would show up in the
    checkout as an untracked path."""
    for row in rows:
        if row.get("action") == "created":
            try:
                os.unlink(row["path"])
            except OSError:
                pass


def link(root: PathLike, env: Env = None, home: Optional[PathLike] = None, remember: bool = True,
         locked: bool = False) -> Dict[str, Any]:
    """Make the links ``plans`` and ``tasks`` in the checkout ``root`` and list them in ``.git/info/exclude``.

    Returns ``{workspace, project_id, path, links, exclude, enabled}``; a row of ``links`` is ``{name, path, target, action,
    reason?}`` with ``action`` ``created``, ``kept`` (already the right link), ``refused`` (a real folder or a link elsewhere
    is in the way; ``reason`` ``real-folder`` or ``link-elsewhere``) or ``skipped`` (``plans-store-legacy``). ``remember`` also
    records ``link_folders = true`` for this project when a link is in place (a failure to write it is ``problem``).
    ``locked`` says that the caller holds ``git.lock``."""
    checkout = _real(root)
    context = _context(checkout, env, home)
    folder, marker = context["folder"], context["marker"]
    rows: List[Dict[str, Any]] = []
    for name in LINK_NAMES:
        found = inspect_folder(checkout, name, folder)
        row = {"name": name, "path": found["path"], "target": found["target"]}
        if name == "plans" and marker["plans_store"] != "workspace":
            row.update(action="skipped", reason="plans-store-legacy")
        elif found["state"] == "real":
            row.update(action="refused", reason="real-folder")
        elif found["state"] == "foreign":
            row.update(action="refused", reason="link-elsewhere")
        else:
            target = Path(found["target"])
            _make_target(target, name, env, home, locked)
            if found["state"] == "absent":
                try:
                    os.symlink(str(_real(target)), found["path"])
                except OSError as exc:
                    _take_back(rows)
                    raise WorkspaceError("LINK_FAILED", f"cannot link {found['path']}: {exc}") from None
                row["action"] = "created"
            else:
                row["action"] = "kept"
        rows.append(row)
    try:
        exclude = _sync_exclude(checkout, folder)
    except (WorkspaceError, OSError):
        _take_back(rows)
        raise
    problem = None
    now: Optional[bool] = None
    if remember and any(row["action"] in ("created", "kept") for row in rows):
        try:
            set_enabled(checkout, True, env, home)
            now = True
        except WorkspaceError as exc:
            problem = exc.code
    return _result(checkout, context, rows, exclude, now if remember else None, problem)


def unlink(root: PathLike, env: Env = None, home: Optional[PathLike] = None, remember: bool = True) -> Dict[str, Any]:
    """Remove the links ``plans`` and ``tasks`` that point to the project folder and their lines in ``.git/info/exclude``.
    A real folder and a link to anywhere else stay (``action`` ``skipped``, ``reason`` ``real-folder`` or ``link-elsewhere``);
    nothing there is ``absent``. ``remember`` records ``link_folders = false`` for this project, so ``sync`` does not make the
    links again while the machine setting is on. The folders in the workspace are not touched."""
    checkout = _real(root)
    marker = read_marker(checkout)
    if marker is None:
        raise WorkspaceError("PROJECT_MARKER_MISSING", f"{checkout} has no project marker")
    workspace = layout.require_initialized(layout.root_of(None, env, home))["code"]
    if marker["workspace"] != workspace:
        raise WorkspaceError("WORKSPACE_MISMATCH", f"the marker of {checkout.name} names the workspace "
                             f"{marker['workspace']!r}, this command works with {workspace!r} (--workspace)")
    folder = bound_project_folder(checkout, env, home)
    if folder is None:
        raise WorkspaceError("PROJECT_MARKER_MISSING", f"{checkout} has no project marker")
    context = {"marker": marker, "folder": folder, "workspace": workspace}
    rows: List[Dict[str, Any]] = []
    for name in LINK_NAMES:
        found = inspect_folder(checkout, name, folder)
        row = {"name": name, "path": found["path"], "target": found["target"]}
        if found["state"] == "linked":
            try:
                os.unlink(found["path"])
            except OSError as exc:
                raise WorkspaceError("LINK_FAILED", f"cannot remove {found['path']}: {exc}") from None
            row["action"] = "removed"
        elif found["state"] == "absent":
            row["action"] = "absent"
        else:
            row.update(action="skipped", reason="real-folder" if found["state"] == "real" else "link-elsewhere")
        rows.append(row)
    exclude = _sync_exclude(checkout, folder)
    problem = None
    now: Optional[bool] = None
    if remember:
        try:
            set_enabled(checkout, False, env, home)
            now = False
        except WorkspaceError as exc:
            problem = exc.code
    return _result(checkout, context, rows, exclude, now, problem)


def ensure(root: PathLike, env: Env = None, home: Optional[PathLike] = None, locked: bool = False,
           force: bool = False, remember: bool = False) -> Optional[Dict[str, Any]]:
    """Make or repair the links of the checkout ``root`` when its setting is on (``force`` skips that test and ``remember``
    records the choice for the project, as :func:`link` does); ``None`` when it is off. Never raises: a refusal is
    ``{"problem": CODE, "message": ...}`` in the result."""
    if not force and not enabled(root, env, home):
        return None
    try:
        return link(root, env, home, remember=remember, locked=locked)
    except (WorkspaceError, OSError) as exc:
        code = exc.code if isinstance(exc, WorkspaceError) else "LINK_FAILED"
        return {"path": str(root), "links": [], "problem": code, "message": str(getattr(exc, "message", exc))}


def keep(env: Env = None, home: Optional[PathLike] = None, locked: bool = False) -> List[Dict[str, Any]]:
    """:func:`ensure` for every checkout bound in this workspace on this machine (the ``sync`` step). Only checkouts whose
    setting is on appear in the result; one that does nothing new (all links kept) is left out."""
    try:
        bound = read_bindings(env, home)["projects"]
        workspace = layout.require_initialized(layout.root_of(None, env, home))["code"]
    except WorkspaceError:
        return []
    found: List[Dict[str, Any]] = []
    for project_id, entry in sorted(bound.items()):
        for path in entry["paths"]:
            try:
                marker = read_marker(path) if os.path.isdir(path) else None
            except WorkspaceError:
                continue
            if marker is None or marker["workspace"] != workspace or marker["project_id"] != project_id:
                continue
            doc = ensure(path, env, home, locked=locked)
            if doc is not None and (doc.get("problem") or any(row["action"] in ("created", "refused") for row in doc["links"])):
                found.append(doc)
    return found


def state(root: PathLike, env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """What the checkout has now, for ``project list``-like views and the doctor: ``{enabled, links, listed}`` where ``links``
    are the :func:`aicore.workspace.inspect_folder` rows and ``listed`` the names in ``.git/info/exclude``."""
    checkout = _real(root)
    folder = bound_project_folder(checkout, env, home)
    rows = [] if folder is None else [inspect_folder(checkout, name, folder) for name in LINK_NAMES]
    return {"enabled": enabled(checkout, env, home), "links": rows, "listed": read_exclude(checkout)}
