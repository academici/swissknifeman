"""Project catalog: which folder of the vault belongs to a project."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, List, Optional, Union

from . import errors, frontmatter, settings as _settings

CATALOG_FILE = ".projects.json"

PathLike = Union[str, "os.PathLike[str]"]


@dataclass(frozen=True)
class VaultProject:
    """A project folder in the vault; ``via`` is ``catalog`` or ``control-note``."""

    name: str
    folder: Path
    via: str


def _real(text: str, home: Path, base: Optional[Path] = None) -> str:
    expanded = _settings.expand(text, home)
    if base is not None and not os.path.isabs(expanded):
        expanded = str(base / expanded)
    return os.path.realpath(expanded)


def _from_catalog(vault: Path, target: str, home: Path, warnings: Optional[List[str]]) -> Optional[VaultProject]:
    path = vault / CATALOG_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data["projects"]
        if not isinstance(entries, list):
            raise ValueError("projects is not a list")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if warnings is not None:
            warnings.append(_settings.warning(errors.CATALOG_INVALID,
                                              f"{path} is unreadable ({exc}); using control notes"))
        return None
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            continue
        repo, folder = entry.get("repo"), entry.get("vault_path")
        if not isinstance(repo, str) or not isinstance(folder, str) or not repo or not folder:
            continue
        if _real(repo, home) == target:
            name = entry.get("name")
            folder_path = Path(_real(folder, home, vault))
            return VaultProject(name if isinstance(name, str) and name else folder_path.name, folder_path, "catalog")
    return None


def _control_notes(root: Path) -> Iterator[Path]:
    """Notes ``<root>/<category>/<Name>/<Name>.md`` and ``<root>/<Name>/<Name>.md``, sorted by path."""
    found: List[Path] = []
    try:
        level1 = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return
    for first in level1:
        found.append(first / f"{first.name}.md")
        try:
            level2 = sorted(p for p in first.iterdir() if p.is_dir())
        except OSError:
            continue
        found.extend(second / f"{second.name}.md" for second in level2)
    for note in sorted(found):
        if note.is_file():
            yield note


def _from_notes(vault: Path, target: str, projects_dir: str, home: Path,
                warnings: Optional[List[str]]) -> Optional[VaultProject]:
    hits: List[Path] = []
    for note in _control_notes(vault / projects_dir):
        repo: Any = frontmatter.read(note).get("repo")
        repos = repo if isinstance(repo, list) else [repo]
        if any(isinstance(item, str) and item and _real(item, home) == target for item in repos):
            hits.append(note)
    if not hits:
        return None
    if len(hits) > 1 and warnings is not None:
        warnings.append(_settings.warning(
            errors.CATALOG_AMBIGUOUS,
            f"{len(hits)} control notes claim this project ({', '.join(str(h) for h in hits)}); using {hits[0]}"))
    return VaultProject(hits[0].parent.name, hits[0].parent, "control-note")


def find_project(vault: PathLike, project_root: PathLike, *, projects_dir: str = "05-Projects",
                 home: Optional[PathLike] = None, warnings: Optional[List[str]] = None) -> Optional[VaultProject]:
    """The vault folder of ``project_root``, or None.

    The generated catalog ``<vault>/.projects.json`` comes first, then the control notes under
    ``<vault>/<projects_dir>``. Paths compare by ``os.path.realpath`` after ``~`` is expanded against ``home``.
    Problems (``CATALOG_INVALID``, ``CATALOG_AMBIGUOUS``) are appended to ``warnings`` when it is given.
    """
    vault_path = Path(vault)
    home_path = _settings.home_dir(None, home)
    target = _real(str(project_root), home_path)
    return (_from_catalog(vault_path, target, home_path, warnings)
            or _from_notes(vault_path, target, projects_dir, home_path, warnings))
