"""Layered ``[planner]`` configuration: aicore resolves it when the foundation is present, the schema defaults otherwise.

With aicore the order is defaults -> machine file -> project file -> ``plan.settings`` -> environment ->
``--config`` file -> flags. Without it only the schema defaults and the ``plan.settings`` layer apply; asking for
``--config`` then needs the foundation (``AICORE_REQUIRED``). The schema is ``configs/config.schema.json``.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import require, status

PLANNER_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_FILE = PLANNER_ROOT / "configs" / "config.schema.json"
PLAN_SETTINGS_LAYER = "plan.settings"

_DEFAULTS: dict = {}


def schema_defaults() -> dict:
    """``{dotted key: default}`` of every leaf of the schema in schema order (read once per process)."""
    if not _DEFAULTS:
        def walk(node: dict, prefix: tuple) -> None:
            for name, child in node.get("properties", {}).items():
                if child.get("type") == "object":
                    walk(child, prefix + (name,))
                else:
                    _DEFAULTS[".".join(prefix + (name,))] = child["default"]
        walk(json.loads(SCHEMA_FILE.read_text(encoding="utf-8")), ())
    return copy.deepcopy(_DEFAULTS)


def layer_files(project_root: str | Path | None) -> list:
    """The machine and project configuration files that can feed a resolution (none without aicore)."""
    if not status()["aicore"] == "available":
        return []
    from aicore.state import machine_config_file, project_config_file
    files = [Path(machine_config_file())]
    if project_root is not None:
        files.append(Path(project_config_file(project_root)))
    return files


def plan_settings_layer(plan_settings: Mapping | None) -> dict:
    """The ``[planner]`` section the settings of a plan contribute: only ``context_budget_kb`` (an integer >= 1).

    The plan schema has no upper bound, the configuration has one: a larger value is lowered to it, so an old plan
    keeps working (a warning threshold that large never fires anyway).
    """
    kb = (plan_settings or {}).get("context_budget_kb")
    if isinstance(kb, int) and not isinstance(kb, bool) and kb >= 1:
        return {"context": {"budget_kb": min(kb, _budget_maximum())}}
    return {}


def _budget_maximum() -> int:
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    return schema["properties"]["context"]["properties"]["budget_kb"]["maximum"]


def _nested(values: Mapping[str, Any]) -> dict:
    tree: dict = {}
    for key, value in values.items():
        cursor = tree
        *parents, leaf = key.split(".")
        for part in parents:
            cursor = cursor.setdefault(part, {})
        cursor[leaf] = copy.deepcopy(value)
    return tree


@dataclass(frozen=True)
class PlannerConfig:
    """The effective configuration. ``values`` maps dotted keys to values, ``sources`` to the layer that set them."""

    values: Mapping[str, Any]
    sources: Mapping[str, str]
    layers: tuple
    aicore: Mapping[str, Any]
    resolved: Any = None  # aicore.config.ResolvedConfig, or None without aicore

    def get(self, key: str) -> Any:
        """The value of a leaf key such as ``context.budget_kb``."""
        if key not in self.values:
            raise _invalid(f"unknown key {key!r} for module 'planner'")
        return copy.deepcopy(self.values[key])

    def path(self, key: str) -> Path | None:
        """A folder key as a path, ``None`` for an empty value. ``~`` is expanded; a relative path is taken from the
        folder of the file that set it (the working directory when no file did)."""
        text = self.get(key)
        if not text:
            return None
        folder = Path(os.path.expanduser(text))
        if folder.is_absolute():
            return folder
        base = Path.cwd()
        if self.resolved is not None:
            entry = self.resolved.explain(key)[0]
            if entry.file:
                base = Path(entry.file).parent
        return base / folder

    def as_dict(self) -> dict:
        """The whole tree as nested dictionaries."""
        return _nested(self.values)

    def explain(self, key: str | None = None) -> list:
        """Where each value comes from. With aicore: its entries (layer, file, line, overridden); without:
        ``{key, value, layer}`` rows. ``key`` selects one key or the keys under a table."""
        if self.resolved is not None:
            from aicore.config import ConfigError
            try:
                return [entry.as_dict() for entry in self.resolved.explain(key)]
            except ConfigError as exc:  # an unknown key
                raise _invalid(str(exc)) from None
        rows = [{"key": name, "value": copy.deepcopy(value), "layer": self.sources[name]}
                for name, value in self.values.items()
                if key is None or name == key or name.startswith(key + ".")]
        if key is not None and not rows:
            raise _invalid(f"unknown key {key!r} for module 'planner'")
        return rows

    def explain_text(self, key: str | None = None) -> str:
        """Human text of :meth:`explain`: key, value, source layer and what it overrides."""
        if self.resolved is not None:
            from aicore.config import ConfigError
            try:
                return self.resolved.explain_text(key)
            except ConfigError as exc:
                raise _invalid(str(exc)) from None
        return "\n".join(f"{row['key']} = {json.dumps(row['value'], ensure_ascii=False)}\n  from {row['layer']}"
                         for row in self.explain(key))

    def explain_json(self, key: str | None = None) -> dict:
        """``config-explain/v1`` with aicore; ``{"aicore", "entries"}`` without it."""
        if self.resolved is not None:
            from aicore.config import ConfigError
            try:
                return self.resolved.explain_json(key)
            except ConfigError as exc:
                raise _invalid(str(exc)) from None
        return {"aicore": dict(self.aicore), "entries": self.explain(key)}


def _invalid(message: str):
    from planner.plan.model import PlanError
    return PlanError("CONFIG_INVALID", message)


def resolve(*, project_root: str | Path | None, plan_settings: Mapping | None = None,
            config_file: str | Path | None = None, env: Mapping[str, str] | None = None,
            home: str | Path | None = None) -> PlannerConfig:
    """Resolve the configuration for a project (``None``: no project layer) and, optionally, a plan's settings."""
    info = status()
    section = plan_settings_layer(plan_settings)
    if info["aicore"] == "available":
        from aicore.config import ConfigError, ExtraLayer
        from aicore.config import resolve as aicore_resolve
        layers = [ExtraLayer(PLAN_SETTINGS_LAYER, section)] if section else []
        try:
            resolved = aicore_resolve("planner", unit_root=PLANNER_ROOT, project=project_root, extra_layers=layers,
                                      config_file=config_file, env=env, home=home)
        except ConfigError as exc:
            raise _invalid(str(exc)) from None
        values: dict = {}
        sources: dict = {}
        for key in schema_defaults():
            values[key] = resolved.get(key)
        for entry in resolved.explain():
            sources[entry.key] = entry.layer
        layer_rows = tuple({"name": layer.name, "file": layer.file, "present": layer.present}
                           for layer in resolved.layers)
        return PlannerConfig(values, sources, layer_rows, info, resolved)
    if config_file is not None:
        require("--config")
    values = schema_defaults()
    sources = {key: "defaults" for key in values}
    if section:
        values["context.budget_kb"], sources["context.budget_kb"] = section["context"]["budget_kb"], PLAN_SETTINGS_LAYER
    layers = ({"name": "defaults", "file": None, "present": True},
              {"name": PLAN_SETTINGS_LAYER, "file": None, "present": bool(section)})
    return PlannerConfig(values, sources, layers, info, None)
