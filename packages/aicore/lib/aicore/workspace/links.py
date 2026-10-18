"""The optional links ``plans/`` and ``tasks/`` in a checkout (decision D5).

A checkout of a workspace project may carry the symbolic links ``<checkout>/plans`` and ``<checkout>/tasks`` to the folders
``<workspace>/projects/<code>/plans`` and ``.../tasks``, so an IDE that opens the code sees them without the plans becoming part
of the code repository: the links are listed in the repository's own ``.git/info/exclude`` (never in a tracked file). This module
holds what every reader needs and no setting: where the links must point, what a folder of the checkout is
(:func:`inspect_folder`), whether a link points into the bound workspace project (:func:`is_workspace_link`, which readers of the
old ``<checkout>/plans`` use to ignore it) and the managed block of ``.git/info/exclude``. Making and removing the links and the
setting ``workspace.link_folders`` belong to the workspace module. stdlib only.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from aicore.state.locations import workspace_root
from aicore.util.io import atomic_write_text

from . import WorkspaceError
from .documents import project_dir, read_marker

LINK_NAMES = ("plans", "tasks")
BEGIN = "# skm:links begin (managed by swissknifeman workspace project link: do not edit between the markers)"
END = "# skm:links end"

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]


def bound_project_folder(root: PathLike, env: Env = None, home: Optional[PathLike] = None) -> Optional[Path]:
    """``<workspaces>/<workspace>/projects/<code>`` named by the marker of the checkout ``root``; ``None`` without a marker.
    An invalid marker is ``PROJECT_MARKER_INVALID``. The folder need not exist."""
    marker = read_marker(root)
    if marker is None:
        return None
    try:
        return project_dir(workspace_root(env, home, code=marker["workspace"]), marker["project_id"])
    except ValueError as exc:
        raise WorkspaceError("WORKSPACE_ROOT_INVALID", str(exc)) from None


def link_target(folder: PathLike, name: str) -> Path:
    """The workspace folder the link ``name`` of a project must point to."""
    if name not in LINK_NAMES:
        raise ValueError(f"{name!r} is not one of {', '.join(LINK_NAMES)}")
    return Path(folder) / name


def _real(path: PathLike) -> str:
    return os.path.realpath(str(path))


def _inside(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def inspect_folder(root: PathLike, name: str, folder: PathLike) -> Dict[str, Any]:
    """What ``<root>/<name>`` is, against the project folder ``folder`` of the workspace.

    ``state`` is ``absent`` (nothing there), ``linked`` (a symbolic link that resolves to ``folder/<name>``; ``dangling`` is true
    while that target does not exist), ``foreign`` (a symbolic link to anywhere else) or ``real`` (a folder or a file that is
    not a link). ``points_to`` is the resolved target of a link. Nothing is created or changed."""
    path = Path(root) / name
    expected = link_target(folder, name)
    result: Dict[str, Any] = {"name": name, "path": str(path), "target": str(expected), "state": "absent",
                              "dangling": False, "points_to": None}
    if os.path.islink(path):
        resolved = _real(path)
        result["points_to"] = resolved
        result["dangling"] = not os.path.exists(path)
        result["state"] = "linked" if resolved == _real(expected) else "foreign"
    elif os.path.lexists(path):
        result["state"] = "real"
    return result


def inspect_folders(root: PathLike, env: Env = None, home: Optional[PathLike] = None) -> Optional[List[Dict[str, Any]]]:
    """:func:`inspect_folder` of every name in ``LINK_NAMES``; ``None`` for a checkout without a marker."""
    folder = bound_project_folder(root, env, home)
    return None if folder is None else [inspect_folder(root, name, folder) for name in LINK_NAMES]


def is_workspace_link(root: PathLike, name: str = "plans", env: Env = None, home: Optional[PathLike] = None) -> bool:
    """Whether ``<root>/<name>`` is a symbolic link that points into the workspace project folder the marker of ``root`` binds.
    Such a link is the workspace store seen from the checkout, not a copy of it: readers of the old ``<root>/plans`` ignore it.
    A checkout without a marker, an unusable marker and any other entry give ``False``."""
    path = Path(root) / name
    if not os.path.islink(path):
        return False
    try:
        folder = bound_project_folder(root, env, home)
    except (WorkspaceError, OSError):
        return False
    return folder is not None and _inside(_real(path), _real(folder))


def exclude_file(root: PathLike) -> Optional[Path]:
    """``.git/info/exclude`` of the repository at ``root`` (also for a worktree or a submodule, where ``.git`` is a file);
    ``None`` when ``root`` is not a git working tree or git is not installed."""
    try:
        done = subprocess.run(["git", "rev-parse", "--git-path", "info/exclude"], cwd=str(root), capture_output=True,
                              text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    text = done.stdout.strip()
    if done.returncode != 0 or not text:
        return None
    return Path(text) if os.path.isabs(text) else (Path(root) / text).resolve()


def _split_block(lines: Sequence[str], path: Path) -> "tuple[List[str], Optional[int], List[str]]":
    """``(lines outside the block, index where the block was, lines inside)``; a half block is refused."""
    kept: List[str] = []
    inside: List[str] = []
    at: Optional[int] = None
    open_block = False
    for line in lines:
        if line.strip() == BEGIN:
            if open_block:
                raise WorkspaceError("LINKS_EXCLUDE_INVALID", f"{path} has a second begin line of the links block")
            open_block = True
            if at is None:
                at = len(kept)
        elif line.strip() == END and open_block:
            open_block = False
        elif open_block:
            inside.append(line)
        else:
            kept.append(line)
    if open_block:
        raise WorkspaceError("LINKS_EXCLUDE_INVALID", f"{path} has a links begin line without an end line")
    return kept, at, inside


def read_exclude(root: PathLike) -> List[str]:
    """The names in the links block of ``.git/info/exclude`` (``plans`` for the line ``/plans``); empty without the block."""
    path = exclude_file(root)
    if path is None:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    try:
        _kept, _at, inside = _split_block(lines, path)
    except WorkspaceError:
        return []
    return [line[1:] for line in inside if line.startswith("/") and line[1:] in LINK_NAMES]


def write_exclude(root: PathLike, names: Sequence[str]) -> Optional[Path]:
    """Make the links block of ``.git/info/exclude`` list exactly ``names`` (``/name`` lines); every line outside the block
    stays. Without names the block is removed, and a file without a block is not touched. Returns the file, or ``None`` when
    ``root`` is not a git working tree (nothing to exclude from). A half block is ``LINKS_EXCLUDE_INVALID``."""
    path = exclude_file(root)
    if path is None:
        return None
    wanted = [f"/{name}" for name in LINK_NAMES if name in names]
    try:
        old = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        old = ""
    except (OSError, UnicodeError) as exc:
        raise WorkspaceError("LINKS_EXCLUDE_INVALID", f"{path} is not readable: {exc.__class__.__name__}") from None
    kept, at, _inside_lines = _split_block(old.splitlines(), path)
    if not wanted:
        if at is None:
            return path
        lines = kept
    else:
        place = len(kept) if at is None else at
        lines = kept[:place] + [BEGIN, *wanted, END] + kept[place:]
    text = "\n".join(lines) + "\n" if lines else ""
    if text != old:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, text)
    return path
