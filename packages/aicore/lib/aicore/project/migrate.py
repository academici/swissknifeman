"""``aicore project migrate``: move the project layer out of the checkout into ``projects/<code>/local/`` of the workspace.

A launcher-only checkout keeps ``.swissknifeman/launcher.py`` (with its lock) and ``project.json`` and nothing else of the
project layer. An older checkout may still hold ``config.toml``, ``state/``, ``backups/`` and ``stubs/`` there; :func:`plan`
lists what would move and :func:`apply` moves it. A file is never overwritten: one that is already in ``local/`` with the same
bytes is dropped from the checkout, one with other bytes is a conflict and both copies stay. A symbolic link is refused.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping

from aicore.state import LauncherError
from aicore.state.locations import PROJECT_DIRNAME, project_local_dir
from aicore.workspace import ensure_local

#: Names in ``<checkout>/.swissknifeman/`` that belong to the project layer and move to ``local/`` (same names there).
MOVABLE = ("config.toml", "state", "backups", "stubs")
CONFIG_MODE = 0o600


def leftovers(root: Path) -> List[str]:
    """The names of :data:`MOVABLE` that exist in the checkout (a symbolic link counts)."""
    base = Path(root) / PROJECT_DIRNAME
    return [name for name in MOVABLE if os.path.lexists(base / name)]


def _local(root: Path, env: Mapping[str, str]) -> Path:
    local = project_local_dir(root, env=env)
    if local is None:
        raise LauncherError("PROJECT_LOCAL_UNAVAILABLE",
                            f"{root} has no .swissknifeman/project.json, or the workspace it names has no folder for the "
                            f"project on this machine; run `swissknifeman workspace project attach` first")
    if local.is_symlink():
        raise LauncherError("PROJECT_LOCAL_UNAVAILABLE", f"{local} is a symbolic link")
    return local


def _same(first: Path, second: Path) -> bool:
    try:
        return first.read_bytes() == second.read_bytes()
    except OSError:
        return False


def _entries(source: Path, target: Path, relative: str, items: List[Dict[str, Any]]) -> None:
    """Append one item per file of ``source`` (a file or a folder): ``move``, ``drop`` (identical copy already there),
    ``conflict`` or ``refused`` (symbolic link)."""
    if source.is_symlink():
        items.append({"path": relative, "action": "refused", "code": "PROJECT_MIGRATE_SYMLINK",
                      "reason": "a symbolic link is not moved"})
    elif source.is_dir():
        if os.path.lexists(target) and not target.is_dir():
            items.append({"path": relative, "action": "conflict", "reason": "local/ holds a file in the place of a folder"})
            return
        for child in sorted(source.iterdir(), key=lambda entry: entry.name):
            _entries(child, target / child.name, f"{relative}/{child.name}", items)
    elif not os.path.lexists(target):
        items.append({"path": relative, "action": "move"})
    elif target.is_file() and not target.is_symlink() and _same(source, target):
        items.append({"path": relative, "action": "drop"})
    else:
        items.append({"path": relative, "action": "conflict", "reason": "local/ holds a different file of that name"})


def plan(root: Path, env: Mapping[str, str]) -> Dict[str, Any]:
    """``{local, items: [{path, action, code?, reason?}]}``: what :func:`apply` does. ``PROJECT_LOCAL_UNAVAILABLE`` when the
    checkout is not tied to a workspace project folder on this machine."""
    root = Path(root)
    local = _local(root, env)
    base = root / PROJECT_DIRNAME
    items: List[Dict[str, Any]] = []
    for name in leftovers(root):
        _entries(base / name, local / name, name, items)
    return {"local": str(local), "items": items}


def _prune(folder: Path) -> None:
    """Remove ``folder`` and the empty folders under it; a folder that still holds a file stays."""
    if folder.is_symlink() or not folder.is_dir():
        return
    for child in folder.iterdir():
        _prune(child)
    try:
        folder.rmdir()
    except OSError:
        pass


def apply(root: Path, result: Dict[str, Any]) -> Dict[str, Any]:
    """Carry out a :func:`plan` result. Each file is moved with one rename (a copy and a delete across devices); a failure
    stops the run and the files already moved stay moved (run it again: the rest is still listed)."""
    base = Path(root) / PROJECT_DIRNAME
    local = Path(result["local"])
    ensure_local(local.parents[2],local.parent.name)
    for item in result["items"]:
        source, target = base / item["path"], local / item["path"]
        if item["action"] == "drop":
            source.unlink()
        elif item["action"] == "move":
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.move(str(source), str(target))
            if item["path"] == "config.toml":
                os.chmod(target, CONFIG_MODE)
    for name in MOVABLE:
        if name != "config.toml":
            _prune(base / name)
    return {**result, "applied": True, "remaining": leftovers(root)}


def run(root: Path, env: Mapping[str, str], *, dry_run: bool = False) -> Dict[str, Any]:
    """Plan and (unless ``dry_run``) apply; the result of :func:`plan` plus ``applied`` and ``remaining`` after a run."""
    result = plan(root, env)
    if dry_run or not any(item["action"] in ("move", "drop") for item in result["items"]):
        return {**result, "applied": False, "remaining": leftovers(root)}
    return apply(root, result)
