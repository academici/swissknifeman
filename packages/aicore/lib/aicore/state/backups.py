"""Timestamped backups with rotation, replacing ``*.bak`` files next to the original.

A backup lands in ``<backups>/<stamp>/<relative path>`` where ``<backups>`` is the project's
``.swissknifeman/backups`` for a file inside the project and the machine state directory's
``backups`` otherwise. Rotation looks only at stamp-named sub-directories of that directory,
so anything else stored next to them is never touched. The rotation window counts stamps of
one backups directory, not files. stdlib only.
"""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Mapping, Optional, Tuple

from .locations import PathLike, project_backups_dir, state_dir

DEFAULT_KEEP = 10
_STAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
_STAMP = re.compile(r"^(\d{8}T\d{12}Z)(?:-(\d+))?$")


def _utc(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _order(name: str):
    match = _STAMP.match(name)
    return (match.group(1), int(match.group(2) or 0)) if match else None


def _backups_root(project: Optional[PathLike], env: Optional[Mapping[str, str]],
                  home: Optional[PathLike]) -> Path:
    if project is not None:
        return project_backups_dir(project)
    return state_dir(env=env, home=home) / "backups"


def _relative(source: Path, project: Optional[PathLike], env: Optional[Mapping[str, str]],
              home: Optional[PathLike]) -> Tuple[bool, Path]:
    """(inside the project, path of the copy below the stamp directory)."""
    if project is not None:
        try:
            return True, source.relative_to(Path(os.path.abspath(project)))
        except ValueError:
            pass
    user = Path(os.path.abspath(home if home is not None else (
        (env if env is not None else os.environ).get("HOME") or Path.home())))
    try:
        return False, source.relative_to(user)
    except ValueError:
        return False, Path(*source.parts[1:])


def backup(path: PathLike, *, project: Optional[PathLike] = None, keep: int = DEFAULT_KEEP,
           now: Optional[datetime] = None, env: Optional[Mapping[str, str]] = None,
           home: Optional[PathLike] = None) -> Optional[Path]:
    """Copy the file at *path* into a new stamp directory and rotate; ``None`` if no file."""
    if keep < 1:
        raise ValueError(f"keep must be at least 1, got {keep}")
    source = Path(os.path.abspath(path))
    if not source.is_file():
        return None
    inside, relative = _relative(source, project, env, home)
    root = _backups_root(project if inside else None, env, home)
    stamp = _utc(now).strftime(_STAMP_FORMAT)
    # An equal stamp gets a suffix above every existing one, so a copy made after rotation removed
    # the bare stamp still sorts as the newest.
    taken = [_order(entry.name)[1] for entry in _stamp_dirs(root) if _order(entry.name)[0] == stamp]
    name = f"{stamp}-{max(taken) + 1}" if taken else stamp
    copy = root / name / relative
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, copy)
    _rotate(root, keep)
    return copy


def _stamp_dirs(root: Path) -> List[Path]:
    if not root.is_dir():
        return []
    found = [entry for entry in root.iterdir()
             if entry.is_dir() and not entry.is_symlink() and _order(entry.name) is not None]
    return sorted(found, key=lambda entry: _order(entry.name))


def _rotate(root: Path, keep: int) -> None:
    for old in _stamp_dirs(root)[:-keep]:
        shutil.rmtree(old)


def list_backups(project: Optional[PathLike] = None, *, env: Optional[Mapping[str, str]] = None,
                 home: Optional[PathLike] = None) -> List[Tuple[str, List[Path]]]:
    """``[(stamp, [copied files])]`` of one backups directory, newest first."""
    root = _backups_root(project, env, home)
    listing = []
    for entry in reversed(_stamp_dirs(root)):
        files = sorted(item for item in entry.rglob("*") if item.is_file())
        listing.append((entry.name, files))
    return listing
