"""brain settings: the ``[brain]`` configuration and the legacy sources it still honours.

Values come from ``aicore.config`` (schema ``configs/config.schema.json``: defaults, machine file,
project file, environment, ``--config``). Two legacy sources fill gaps only: the ``memory_brain``
object of ``<project>/.swissknife.json`` (vault path and document sync) and, in :mod:`brain.vault`,
the ``MAIND_BRAIN_VAULT`` variable. A key set by the configuration always wins over a legacy source.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from aicore.config import ConfigError, resolve

from . import errors

UNIT_ROOT = Path(__file__).resolve().parents[2]
SYNCED_FOLDERS = ("docs", "docs-public", "plans")
DEFAULT_PATTERNS = ("docs/**/*.md", "README.md")
LEGACY_FILE = ".swissknife.json"

PathLike = Union[str, "os.PathLike[str]"]


@dataclass(frozen=True)
class BrainSettings:
    """The effective ``[brain]`` settings of one project (or of the machine without a project)."""

    vault_path: Optional[str]
    vault_source: str  # "config", "legacy-project" or "none"
    projects_dir: str
    docs_enabled: bool
    docs_direction: str
    docs_patterns: Tuple[str, ...]
    docs_source: str  # "config", "legacy" or "defaults"
    notes_enabled: bool
    notes_folder: str
    notes_fallback_folder: str
    warnings: Tuple[str, ...] = ()


def warning(code: str, message: str) -> str:
    return f"{code}: {message}"


LEGACY_VAULT_WARNING = warning(errors.BRAIN_LEGACY_CONFIG,
                               f"{LEGACY_FILE}::memory_brain is deprecated; "
                               "set brain.vault_path in the machine configuration")
LEGACY_DOCS_WARNING = warning(errors.BRAIN_LEGACY_CONFIG,
                              f"{LEGACY_FILE}::memory_brain document sync is deprecated; "
                              "set brain.docs.* in the project configuration")


def home_dir(env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None) -> Path:
    """The home directory used for ``~``: ``home``, else ``$HOME`` of ``env``, else the process home."""
    if home is not None:
        return Path(home)
    environment = os.environ if env is None else env
    return Path(environment.get("HOME") or os.path.expanduser("~"))


def expand(text: str, home: Path) -> str:
    """Expand a leading ``~`` against ``home`` (not against the real home of the process)."""
    if text == "~":
        return str(home)
    if text.startswith("~/"):
        return str(home / text[2:])
    return text


def read_legacy(project: Optional[PathLike]) -> Optional[Dict[str, Any]]:
    """The ``memory_brain`` object of ``<project>/.swissknife.json``; None for a missing file, bad JSON or a
    string value (a string names the memory "brain" of the project, it is not a vault path)."""
    if project is None:
        return None
    try:
        data = json.loads((Path(project) / LEGACY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    block = data.get("memory_brain") if isinstance(data, dict) else None
    return block if isinstance(block, dict) else None


def _legacy_docs(block: Dict[str, Any]) -> Tuple[str, Tuple[str, ...]]:
    sync = block.get("sync")
    sync = sync if isinstance(sync, dict) else {}
    direction = sync.get("direction")
    if direction not in ("pull", "push", "bidirectional"):
        direction = "pull"
    patterns = sync.get("patterns")
    if isinstance(patterns, list) and patterns and all(isinstance(p, str) and p for p in patterns):
        return direction, tuple(patterns)
    return direction, DEFAULT_PATTERNS


def check_notes_folder(folder: str) -> None:
    """Refuse a notes folder inside a synchronized folder: a sync would copy notes into the project."""
    first = [part for part in folder.replace("\\", "/").split("/") if part not in ("", ".")][:1]
    if first and first[0] in SYNCED_FOLDERS:
        raise ConfigError(errors.CONFIG_NOTES_FOLDER,
                          f"{folder!r} is inside the synchronized folder {first[0]!r}; choose another folder",
                          key="notes.folder")


def load(project: Optional[PathLike] = None, *, env: Optional[Mapping[str, str]] = None,
         home: Optional[PathLike] = None, config_file: Optional[PathLike] = None) -> BrainSettings:
    """Resolve the settings for a project (``None``: machine, environment and ``config_file`` layers only).

    Raises :class:`aicore.config.ConfigError` for an invalid layer or for ``notes.folder`` inside a synchronized
    folder (code ``CONFIG_NOTES_FOLDER``).
    """
    config = resolve("brain", unit_root=UNIT_ROOT, project=project, config_file=config_file, env=env,
                     home=home, warn=lambda message: None)
    notes: list = []
    legacy = read_legacy(project)

    vault_path = config.get("vault_path")
    vault_source = "config" if vault_path else "none"
    legacy_path = legacy.get("path") if legacy else None
    if not vault_path and isinstance(legacy_path, str) and legacy_path.strip():
        vault_path, vault_source = legacy_path.strip(), "legacy-project"
        notes.append(LEGACY_VAULT_WARNING)

    docs_keys = ("docs.enabled", "docs.direction", "docs.patterns")
    docs_in_config = any(config.explain(key)[0].layer != "defaults" for key in docs_keys)
    docs_enabled = config.get("docs.enabled")
    docs_direction = config.get("docs.direction")
    docs_patterns = tuple(config.get("docs.patterns"))
    docs_source = "config" if docs_in_config else "defaults"
    if legacy is not None and not docs_in_config:
        docs_enabled = True
        docs_direction, docs_patterns = _legacy_docs(legacy)
        docs_source = "legacy"
        notes.append(LEGACY_DOCS_WARNING)

    notes_folder = config.get("notes.folder")
    check_notes_folder(notes_folder)
    return BrainSettings(
        vault_path=vault_path, vault_source=vault_source, projects_dir=config.get("catalog.projects_dir"),
        docs_enabled=bool(docs_enabled), docs_direction=docs_direction, docs_patterns=docs_patterns,
        docs_source=docs_source, notes_enabled=bool(config.get("notes.enabled")), notes_folder=notes_folder,
        notes_fallback_folder=config.get("notes.fallback_folder"),
        warnings=tuple(dict.fromkeys(notes + list(config.warnings))))
