"""Module configuration: layered settings from schemas, TOML files, environment and flags.

Entry points: :func:`resolve` (the effective settings of one module, with explain), :class:`Secret`
and :func:`register_secret_resolver` (secret references), :func:`edit_layer_file` (change one key of
a layer file), :func:`apply_layer_patch` (several changes under a lock and a revision check). ``aicore.config`` may use :mod:`aicore.util` and :mod:`aicore.state`. The TOML parser
is reachable only through :mod:`aicore.config.toml`.
"""
from typing import Optional


class ConfigError(ValueError):
    """A configuration problem with a stable ``code`` and, when known, where it was found.

    ``str()`` is ``<file>:<line>: <layer>: <key>: <message> [<code>]`` without the empty parts.
    """

    def __init__(self, code: str, message: str, *, layer: Optional[str] = None,
                 file: Optional[str] = None, line: Optional[int] = None,
                 key: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.layer = layer
        self.file = file
        self.line = line
        self.key = key

    def __str__(self) -> str:
        where = ""
        if self.file:
            where = f"{self.file}:{self.line}" if self.line else str(self.file)
        elif self.line:
            where = f"line {self.line}"
        parts = [part for part in (where, self.layer, self.key, self.message) if part]
        return f"{': '.join(parts)} [{self.code}]"


from . import toml, toml_edit  # noqa: E402  (ConfigError is defined first: the submodules import it)
from .secrets import Secret, register_secret_resolver  # noqa: E402
from .model import (CONFIG_FILE_VERSION, LAYER_NAMES, EditResult, ExplainEntry, ExtraLayer,  # noqa: E402
                    LayerEditPlan, LayerInfo, LayerSnapshot, Leaf, ModuleSchema, PatchOp, ResolvedConfig,
                    Setting, apply_layer_patch, edit_layer_file, layer_lock, layer_revision,
                    load_module_schema, parse_value, plan_layer_edit, read_layer, resolve)

__all__ = [
    "CONFIG_FILE_VERSION", "ConfigError", "EditResult", "ExplainEntry", "ExtraLayer", "LAYER_NAMES",
    "LayerEditPlan", "LayerInfo", "LayerSnapshot", "Leaf", "ModuleSchema", "PatchOp", "ResolvedConfig",
    "Secret", "Setting", "apply_layer_patch", "edit_layer_file", "layer_lock", "layer_revision",
    "load_module_schema", "parse_value", "plan_layer_edit", "read_layer", "register_secret_resolver",
    "resolve", "toml", "toml_edit",
]
