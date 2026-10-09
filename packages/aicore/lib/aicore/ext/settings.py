"""The ``[aicore]`` section of the configuration: events, subscriptions, plugins and overlays.

One call to :func:`aicore.config.resolve` gives every layer; this module reshapes the result and gives
each overlay file the layer it came from. Executable definitions (``run``, ``plugin``, ``manifest``,
``trusted``) are accepted only from the machine layer by the schema, so a cloned repository cannot start a
command (see the schema). stdlib and ``aicore`` only.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .. import config as _config
from ..config.units import foundation_root
from .errors import ExtError

PathLike = Union[str, "os.PathLike[str]"]
Overlay = Tuple[str, str, Optional[str]]  # (absolute path, layer name, file of the layer)


@dataclass(frozen=True)
class ExtSettings:
    """Effective extension settings. ``overlays`` maps ``<module>:<slot>`` to ``(path, layer, layer file)``.

    Every plugin entry carries the schema default ``timeout_seconds``; ``plugin_timeouts_set`` names the plugins
    whose value was set by a layer, so that a manifest default is not hidden by the schema default.
    """

    delivery: str
    timeout_seconds: int
    max_attempts: int
    subscriptions: Dict[str, Dict[str, Any]]
    plugins: Dict[str, Dict[str, Any]]
    overlays: Dict[str, List[Overlay]]
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    plugin_timeouts_set: Tuple[str, ...] = field(default_factory=tuple)  # plugins whose timeout is not the default


def _expand(path: str, env: Mapping[str, str], home: Optional[PathLike]) -> str:
    if path == "~" or path.startswith("~/"):
        base = str(home) if home is not None else env.get("HOME") or str(Path.home())
        return os.path.normpath(base + path[1:])
    return path


def collapse_home(path: str, env: Mapping[str, str], home: Optional[PathLike] = None) -> str:
    """``path`` with the home directory written as ``~`` (the inverse of the expansion of ``~`` above)."""
    base = (str(home) if home is not None else env.get("HOME") or str(Path.home())).rstrip("/")
    if base and (path == base or path.startswith(base + "/")):
        return "~" + path[len(base):]
    return path


def _origins(resolved: "_config.ResolvedConfig", key: Tuple[str, ...]) -> List[Tuple[str, str, Optional[str]]]:
    """``(element, layer, file)`` for each element of an array key, replaying the layers that set it."""
    entry = resolved.explain(key)[0]
    history = list(reversed(entry.overridden)) + [_config.Setting(entry.layer, entry.file, entry.line,
                                                                  entry.source, entry.value)]
    elements: List[Tuple[str, str, Optional[str]]] = []
    for setting in history:
        if setting.source == "_unset":
            elements = []
        elif setting.source == "_append":
            elements += [(item, setting.layer, setting.file) for item in setting.value[len(elements):]]
        else:
            elements = [(item, setting.layer, setting.file) for item in setting.value]
    if [item[0] for item in elements] != list(entry.value):  # cannot happen; keep the value, name the winner
        elements = [(item, entry.layer, entry.file) for item in entry.value]
    return elements


def load(project_root: Optional[PathLike], *, env: Optional[Mapping[str, str]] = None,
         home: Optional[PathLike] = None, config_file: Optional[PathLike] = None) -> ExtSettings:
    """The extension settings for ``project_root`` (None: machine layers only).

    A configuration error is an ``ExtError("CONFIG_INVALID")`` whose text is the (value-free) message of the
    configuration module.
    """
    environment = os.environ if env is None else env
    try:
        resolved = _config.resolve("aicore", unit_root=foundation_root(), project=project_root,
                                   config_file=config_file, env=environment, home=home,
                                   warn=lambda _message: None)
    except _config.ConfigError as exc:
        raise ExtError("CONFIG_INVALID", str(exc)) from None
    tree = resolved.as_dict()
    events = tree.get("events", {})
    subscriptions = {name: copy.deepcopy(body) for name, body in tree.get("subscriptions", {}).items()}
    plugins = {name: copy.deepcopy(body) for name, body in tree.get("plugins", {}).items()}
    for body in plugins.values():
        if isinstance(body.get("manifest"), str):
            body["manifest"] = _expand(body["manifest"], environment, home)
    timeouts_set = tuple(name for name in plugins
                         if resolved.explain(("plugins", name, "timeout_seconds"))[0].layer != "defaults")
    overlays: Dict[str, List[Overlay]] = {}
    for slot in tree.get("overlays", {}):
        resolved_files: List[Overlay] = []
        for raw, layer, layer_file in _origins(resolved, ("overlays", slot)):
            path = _expand(raw, environment, home)
            if not os.path.isabs(path):
                base = os.path.dirname(layer_file) if layer_file else (str(project_root) if project_root
                                                                         else os.getcwd())
                path = os.path.normpath(os.path.join(base, path))
            resolved_files.append((path, layer, layer_file))
        overlays[slot] = resolved_files
    return ExtSettings(delivery=events["delivery"], timeout_seconds=events["timeout_seconds"],
                       max_attempts=events["max_attempts"], subscriptions=subscriptions, plugins=plugins,
                       overlays=overlays, warnings=tuple(resolved.warnings), plugin_timeouts_set=timeouts_set)
