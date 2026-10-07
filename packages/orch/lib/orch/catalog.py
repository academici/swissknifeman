"""Launch catalog plus model mappings: which command starts a role and which model a class means on a provider.

The launch catalog is orch's own file (``configs/launch-catalog.json``). Models come from the ``mappings``
of a routing config that a partner package owns; orch never keeps a copy of model names (I8). The routing
file is found from an explicit path, ``ORCH_ROUTING`` or a bridge that exposes ``routing_path()``.
"""
from __future__ import annotations

from collections.abc import Mapping
import importlib.util
import json
import os
from pathlib import Path

from orch import launch

CLASS_RANK = {"economy": 0, "implementation": 1, "frontier": 2}
ROUTING_ENV = "ORCH_ROUTING"
BRIDGES_DIR = Path(__file__).resolve().parents[2] / "bridges"
UNAVAILABLE = f"no routing config found; pass --routing or set {ROUTING_ENV}"


class CatalogError(ValueError):
    """``ROUTING_UNAVAILABLE`` for an unreadable routing file, ``CATALOG_UNKNOWN`` for a missing mapping entry."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _from_bridges() -> Path | None:
    """First bridge whose ``discovery.py`` finds a routing file; a bridge that cannot is skipped."""
    for module_path in sorted(BRIDGES_DIR.glob("*/discovery.py")):
        spec = importlib.util.spec_from_file_location(f"_orch_bridge_{module_path.parent.name}", module_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            found = Path(module.routing_path())
        except Exception:  # the partner is optional: any failure means "not found here"
            continue
        if found.is_file():
            return found
    return None


def find_routing(explicit: str | Path | None = None) -> Path:
    """Explicit path, then ``ORCH_ROUTING``, then bridge discovery."""
    chosen = explicit or os.environ.get(ROUTING_ENV)
    if chosen:
        return Path(chosen)
    found = _from_bridges()
    if found is None:
        raise CatalogError("ROUTING_UNAVAILABLE", UNAVAILABLE)
    return found


def load_routing(path: str | Path | None = None) -> dict:
    """The routing config as a dict that holds ``mappings``."""
    target = find_routing(path)
    try:
        routing = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CatalogError("ROUTING_UNAVAILABLE", f"cannot read routing config {target} ({error})") from error
    if not isinstance(routing, dict) or not isinstance(routing.get("mappings"), dict):
        raise CatalogError("ROUTING_UNAVAILABLE", f"{target}: routing config must hold an object 'mappings'")
    return routing


def substitute(argv: list[str], values: Mapping[str, str]) -> list[str]:
    """Replace ``{model}``, ``{effort}`` and ``{cwd}``; a placeholder without a value is an error."""
    def fill(match):
        if match[1] not in values:
            raise launch.LaunchError("LAUNCH_INVALID", f"no value for placeholder {{{match[1]}}}")
        return values[match[1]]
    return [launch._PLACEHOLDER_RE.sub(fill, arg) for arg in argv]


class Catalog:
    def __init__(self, routing: dict, launch_catalog: dict | None = None):
        self.routing = routing
        self.launch = launch_catalog if launch_catalog is not None else launch.load_catalog()

    @classmethod
    def load(cls, routing_path: str | Path | None = None) -> "Catalog":
        return cls(load_routing(routing_path))

    def launch_entry(self, role: str, provider: str) -> dict:
        return launch.entry(self.launch, role, provider)

    def _selector(self, provider: str, table: str, key: str) -> str:
        mapping = self.routing["mappings"].get(provider)
        values = mapping.get(table, {}).get(key) if isinstance(mapping, dict) else None
        if not isinstance(values, list) or not values or not isinstance(values[0], str):
            raise CatalogError("CATALOG_UNKNOWN", f"mapping of provider {provider!r} has no {table} entry for {key!r}")
        return values[0]

    def resolve_model(self, provider: str, model_class: str) -> str:
        """First model of the class on the provider (I8: no model names live in orch)."""
        return self._selector(provider, "class_selectors", model_class)

    def resolve_effort(self, provider: str, effort: str) -> str:
        return self._selector(provider, "effort_selectors", effort)
