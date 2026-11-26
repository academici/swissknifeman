"""The port ``workspace:plans-migrator``: finding the plugin that fills it and calling it.

The workspace module never imports the bridge. The plugin is the one named by ``workspace.plans_migrator`` in the
configuration (``[aicore.plugins.<id>]``, machine layer); when the configuration has no such entry, a module of the hub
that declares the port in ``provides.ports`` is used with its ``extension.json`` (not trusted: it gets no variables beyond
the allowlist of ``aicore.ext.environment``). Nothing is cached: every call looks the registration up again.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aicore.config import ConfigError, resolve
from aicore.ext import plugins, units
from aicore.ext.errors import ExtError
from aicore.workspace import WorkspaceError

from . import gitutil
from .pathtypes import PathLike

POINT = "workspace:plans-migrator"
DEFAULT_PLUGIN = "workspace-planner"
HINT = ("register the bridge: swissknifeman config set aicore plugins.workspace-planner.manifest "
        "<hub>/bridges/workspace-planner/extension.json")

Env = Optional[Mapping[str, str]]


def plugin_id(env: Env = None, home: Optional[PathLike] = None) -> str:
    """``workspace.plans_migrator`` of the configuration (machine and defaults layers); the default when unreadable."""
    try:
        config = resolve("workspace", unit_root=gitutil.UNIT_ROOT, env=env, home=home, warn=lambda message: None)
        value = config.get("plans_migrator")
    except (ConfigError, TypeError, ValueError):
        return DEFAULT_PLUGIN
    return value if isinstance(value, str) and value else DEFAULT_PLUGIN


def _unit_folders(env: Env) -> List[Path]:
    """Module folders of the hub: those ``discover_units`` finds, and the bridges next to the packages folders."""
    found: List[Path] = [unit.root for unit in units.discover_units(env).values()]
    environment = os.environ if env is None else env
    roots = [Path(part) for part in environment.get("SKM_UNITS_PATH", "").split(os.pathsep) if part]
    for root in roots or [Path(__file__).resolve().parents[3]]:
        bridges = root.parent / "bridges"
        try:
            found.extend(sorted(entry for entry in bridges.iterdir() if (entry / "unit.json").is_file()))
        except OSError:
            continue
    return found


def _declares_port(folder: Path) -> bool:
    try:
        document = json.loads((folder / "unit.json").read_text(encoding="utf-8"))
        ports = document["provides"]["ports"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return isinstance(ports, list) and any(isinstance(port, dict) and port.get("id") == POINT for port in ports)


def _hub_registration(env: Env) -> Optional[plugins.Registration]:
    for folder in _unit_folders(env):
        if not _declares_port(folder) or not (folder / "extension.json").is_file():
            continue
        try:
            manifest = plugins.load_manifest(folder / "extension.json")
        except ExtError as exc:
            raise WorkspaceError("MIGRATOR_UNAVAILABLE", f"{folder.name}: {exc.code}: {exc.message}") from None
        return plugins.Registration(id=manifest.id, manifest_path=str(manifest.path), trusted=False,
                                    timeout_seconds=manifest.timeout_seconds or plugins.DEFAULT_TIMEOUT_S,
                                    enabled=True, manifest=manifest, problem=None)
    return None


def registration(env: Env = None, home: Optional[PathLike] = None) -> plugins.Registration:
    """The usable registration of the plans migrator; ``MIGRATOR_UNAVAILABLE`` (with the way to register it) otherwise."""
    wanted = plugin_id(env, home)
    try:
        found: Optional[plugins.Registration] = plugins.find_registration(wanted, None, env=env, home=home)
    except ExtError as exc:
        if exc.code != "PLUGIN_NOT_FOUND":
            raise WorkspaceError("MIGRATOR_UNAVAILABLE", f"{exc.code}: {exc.message}") from None
        found = _hub_registration(env)
        if found is None:
            raise WorkspaceError("MIGRATOR_UNAVAILABLE", f"no plugin {wanted} is registered and no module of the hub "
                                 f"declares the port {POINT}; {HINT}") from None
    if not found.enabled:
        raise WorkspaceError("MIGRATOR_UNAVAILABLE", f"plugin {found.id} is disabled in [aicore.plugins]")
    if found.problem is not None or found.manifest is None:
        problem = found.problem or {"code": "PLUGIN_MANIFEST_INVALID", "message": "no manifest"}
        raise WorkspaceError("MIGRATOR_UNAVAILABLE", f"plugin {found.id}: {problem['code']}: {problem['message']}")
    if POINT not in found.manifest.points:
        raise WorkspaceError("MIGRATOR_UNAVAILABLE", f"plugin {found.id} does not provide {POINT}")
    return found


def call(op: str, payload: Mapping[str, Any], env: Env = None, home: Optional[PathLike] = None) -> Dict[str, Any]:
    """Invoke the migrator with ``{"op": op, **payload}`` and return its answer.

    A plugin that cannot be found, started or understood is ``MIGRATOR_UNAVAILABLE`` with the code of the plugin layer
    in the message. A refusal of ``apply`` is an answer (``result: refused``), not an error: the caller reads it.
    """
    chosen = registration(env, home)
    request = {"op": op, **dict(payload)}
    result = plugins.invoke_one(chosen, POINT, request, env=env)
    if result.status != "ok" or not isinstance(result.output, dict):
        detail = f"{result.code or result.status}: {result.error or 'no output'}"
        if result.code in ("BRIDGE_PARTNER_UNAVAILABLE", "AICORE_NOT_FOUND"):
            detail += "; the bridge needs the planner library (PLANNER_ROOT or a planner command), set trusted = true " \
                      f"in [aicore.plugins.{chosen.id}] to pass PLANNER_ROOT"
        raise WorkspaceError("MIGRATOR_UNAVAILABLE", f"plugin {chosen.id} {op}: {detail}")
    return result.output
