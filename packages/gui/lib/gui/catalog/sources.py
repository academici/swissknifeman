"""Sources of GUI contributions: hub units and external extensions that declare ``provides.gui``.

A failing source never raises: it becomes a ``CATALOG_SOURCE_UNAVAILABLE`` problem and the other sources still count.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from aicore.config import ConfigError
from aicore.config.units import UNITS_PATH_VAR, unit_dirs
from aicore.ext import settings as ext_settings
from aicore.ext.errors import ExtError
from aicore.ext.plugins import registered_plugins

SOURCE_UNAVAILABLE = "CATALOG_SOURCE_UNAVAILABLE"
UMBRELLA_VAR = "SKM_UMBRELLA"
UMBRELLA_SCHEMA = "umbrella-units/v1"
UMBRELLA_TIMEOUT_S = 30
UNITS_SOURCE = "swissknifeman units list"
EXTENSIONS_SOURCE = "aicore.plugins"


@dataclass(frozen=True)
class Source:
    """One declared contribution: ``gui`` is the raw ``provides.gui`` path, relative to ``root``."""

    kind: str  # "unit" or "extension"
    owner: str  # id of the unit.json or extension.json
    root: Path  # the owner root: the unit folder or the folder of extension.json
    manifest: Path
    gui: str

    def sort_key(self) -> Tuple[str, str, str]:
        return (self.owner, self.kind, str(self.root / self.gui))


@dataclass
class Collected:
    sources: List[Source]
    problems: List[Dict[str, Any]]  # rejected-entry shaped: {owner, file, code, message}


def _problem(source: str, message: str) -> Dict[str, Any]:
    return {"owner": None, "file": source, "code": SOURCE_UNAVAILABLE, "message": message}


def unit_roots(env: Optional[Mapping[str, str]] = None) -> Tuple[List[Path], Optional[Dict[str, Any]]]:
    """Unit folders from ``SKM_UNITS_PATH`` when set, else from the hub registry; and a problem or ``None``."""
    environment = dict(os.environ if env is None else env)
    if environment.get(UNITS_PATH_VAR):
        for part in environment[UNITS_PATH_VAR].split(os.pathsep):
            if part and not Path(part).is_dir():
                return [], _problem(UNITS_SOURCE, f"{UNITS_PATH_VAR} entry is not a directory: {part}")
        return [Path(path) for path in unit_dirs(environment)], None
    executable = environment.get(UMBRELLA_VAR) or shutil.which("swissknifeman", path=environment.get("PATH"))
    if not executable:
        return [], _problem(UNITS_SOURCE, f"swissknifeman not found (set {UMBRELLA_VAR} or {UNITS_PATH_VAR})")
    try:
        result = subprocess.run([executable, "units", "list", "--json"], capture_output=True, text=True,
                                env=environment, timeout=UMBRELLA_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        return [], _problem(UNITS_SOURCE, f"cannot run swissknifeman: {exc.__class__.__name__}")
    if result.returncode != 0:
        return [], _problem(UNITS_SOURCE, f"swissknifeman units list exited with {result.returncode}")
    try:
        doc = json.loads(result.stdout)
        rows = doc["units"]
        if doc.get("schema") != UMBRELLA_SCHEMA or not isinstance(rows, list):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return [], _problem(UNITS_SOURCE, f"swissknifeman units list did not print {UMBRELLA_SCHEMA}")
    hub_root = doc.get("hub_root")
    roots: List[Path] = []
    for row in rows:
        root = row.get("root") if isinstance(row, dict) else None
        if not isinstance(root, str) or not root:
            continue
        if os.path.isabs(root):
            roots.append(Path(root))
        elif isinstance(hub_root, str) and os.path.isabs(hub_root):
            roots.append(Path(hub_root) / root)
        else:
            return [], _problem(UNITS_SOURCE, "swissknifeman units list gave relative roots without hub_root "
                                              "(update swissknifeman)")
    return roots, None


def _manifest(path: Path) -> Optional[Dict[str, Any]]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def declared(kind: str, manifest: Path) -> Optional[Source]:
    """The contribution a ``unit.json`` or ``extension.json`` declares, or ``None`` when it declares none."""
    doc = _manifest(manifest)
    if doc is None:
        return None
    provides = doc.get("provides")
    owner = doc.get("id")
    gui = provides.get("gui") if isinstance(provides, dict) else None
    if not isinstance(owner, str) or not isinstance(gui, str) or not gui:
        return None
    return Source(kind=kind, owner=owner, root=manifest.parent, manifest=manifest, gui=gui)


def unit_sources(roots: List[Path]) -> List[Source]:
    found = (declared("unit", Path(root) / "unit.json") for root in roots)
    return [source for source in found if source is not None]


def extension_sources(project: Optional[Path], env: Optional[Mapping[str, str]] = None
                      ) -> Tuple[List[Source], Optional[Dict[str, Any]]]:
    """Enabled, loadable extensions of ``[aicore.plugins]`` that declare ``provides.gui``."""
    try:
        settings = ext_settings.load(project, env=env)
        registrations, _problems = registered_plugins(settings, env=env)
    except (ExtError, ConfigError, OSError) as exc:
        return [], _problem(EXTENSIONS_SOURCE, f"cannot read the plugin configuration: "
                                               f"{getattr(exc, 'code', exc.__class__.__name__)}")
    sources = []
    for registration in registrations:
        manifest = registration.manifest
        if not registration.usable or manifest is None:
            continue
        source = declared("extension", Path(manifest.path))
        if source is not None:
            sources.append(source)
    return sources, None


def collect(project: Optional[Path] = None, env: Optional[Mapping[str, str]] = None) -> Collected:
    """Every declared contribution of the hub units and the external extensions, with source problems."""
    roots, problem = unit_roots(env)
    problems = [problem] if problem else []
    sources = unit_sources(roots)
    extensions, problem = extension_sources(project, env)
    sources.extend(extensions)
    if problem:
        problems.append(problem)
    return Collected(sources=sources, problems=problems)
