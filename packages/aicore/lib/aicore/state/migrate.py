"""Move the old XDG machine folders into the machine home (``aicore config migrate-home``).

Before the machine home the machine used ``~/.config/swissknifeman``, ``~/.local/state/swissknifeman`` and
``~/.cache/swissknifeman`` (each moved by its ``XDG_*_HOME``), and the data of the modules and the workspaces
in ``~/.local/share/swissknifeman`` (the machine home itself, unless ``XDG_DATA_HOME`` moved it). The three
folders become ``<home>/config``, ``<home>/state`` and ``<home>/cache``; the children of a data folder that is
not the machine home are moved into it. Nothing is merged or overwritten: a target that already holds
something is reported as a conflict and left alone. stdlib only.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from .locations import PathLike, legacy_machine_dirs, machine_home

KINDS = ("config", "state", "cache")


class MigrationError(Exception):
    """The migration cannot run at all (for example ``SKM_HOME`` is set)."""


@dataclass(frozen=True)
class Move:
    """One folder or entry: ``status`` is ``moved`` (``planned`` in a dry run), ``conflict`` or ``absent``."""

    kind: str
    source: Path
    target: Path
    status: str

    def as_dict(self) -> Dict[str, str]:
        return {"kind": self.kind, "from": str(self.source), "to": str(self.target), "status": self.status}


def _is_empty_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and not any(path.iterdir())


def _same(first: Path, second: Path) -> bool:
    return os.path.realpath(first) == os.path.realpath(second)


def _move(kind: str, source: Path, target: Path, dry_run: bool) -> Move:
    if _is_empty_dir(target) and not dry_run:
        target.rmdir()
    elif target.exists() or target.is_symlink():
        if not _is_empty_dir(target):
            return Move(kind, source, target, "conflict")
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    return Move(kind, source, target, "planned" if dry_run else "moved")


def migrate_home(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None, *,
                 dry_run: bool = False) -> List[Move]:
    """Move the old XDG folders into the machine home and report every folder looked at.

    ``MigrationError`` under ``SKM_HOME`` (a sandbox has no old folders to bring in). Running it again is safe:
    folders already moved are ``absent``.
    """
    environment = os.environ if env is None else env
    if environment.get("SKM_HOME", ""):
        raise MigrationError("SKM_HOME is set: the sandbox machine home has no old XDG folders to move; unset it to migrate")
    base = machine_home(environment, home)
    old = legacy_machine_dirs(environment, home)
    report: List[Move] = []
    for kind in KINDS:
        source, target = old[kind], base / kind
        if _same(source, target) or not (source.exists() or source.is_symlink()):
            report.append(Move(kind, source, target, "absent"))
            continue
        report.append(_move(kind, source, target, dry_run))
    data = old["data"]
    if not _same(data, base) and data.is_dir():
        for child in sorted(data.iterdir()):
            report.append(_move("data", child, base / child.name, dry_run))
        if not dry_run and _is_empty_dir(data):
            data.rmdir()
    return report
