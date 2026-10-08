"""The configuration model: module schemas, layers, merging, environment, explain and layer editing.

A module describes its settings in ``configs/config.schema.json`` (the closed profile of
:mod:`aicore.util.schema`; defaults are the ``default`` keywords of the schema). :func:`resolve`
applies the layers from the lowest to the highest::

    defaults -> machine -> project -> extra layers -> env -> invocation (--config FILE) -> flags

and returns a :class:`ResolvedConfig` that knows, for every key, which layer, file and line set it
and which lower values it overrides. Config files are TOML with ``schema_version`` and one table
per module. A layer may remove a key with ``_unset = ["a.b"]`` and extend an array with
``_append = {"a.b" = [...]}``; objects merge by key, arrays and scalars replace. Secret leaves hold
only references (see :mod:`aicore.config.secrets`). stdlib only.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import (Any, Callable, Dict, Iterable, List, Mapping, NamedTuple, Optional, Sequence,
                    Set, Tuple, Union)

from ..state import backup, ensure_dir, machine_config_file, project_config_file
from ..util import io as _io
from ..util import schema as _schema
from . import ConfigError, toml, toml_edit
from .secrets import Secret, is_secret_ref, resolve_ref

CONFIG_FILE_VERSION = 1
LAYER_NAMES = ("defaults", "machine", "project", "env", "invocation", "flags")
FILE_LAYERS = ("machine", "project", "invocation")

Key = Tuple[str, ...]
PathLike = Union[str, "os.PathLike[str]"]

_MODULE_ID = re.compile(r"^[a-z][a-z0-9-]*$")
_PROPERTY = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
_LAYER_ID = re.compile(r"^[a-z][a-z0-9_.-]*$")
_INTEGER = re.compile(r"^[+-]?[0-9]+$")
_NUMBER = re.compile(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$")
_BOOLEANS = {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}
_SCALARS = ("string", "integer", "number", "boolean")
_LEAF_KEYWORDS = {
    "string": {"minLength", "pattern", "enum"},
    "integer": {"minimum", "maximum", "enum"},
    "number": {"minimum", "maximum", "enum"},
    "boolean": {"enum"},
    "array": {"items", "minItems", "uniqueItems"},
}
_COMMON_LEAF = {"type", "description", "title", "default", "x-skm-secret", "x-skm-layers"}
_ITEM_KEYWORDS = {"type", "description", "title", "enum", "minimum", "maximum", "minLength", "pattern"}
_ROOT_KEYWORDS = {"$schema", "$id", "type", "title", "description", "properties", "additionalProperties"}
_TABLE_KEYWORDS = {"type", "title", "description", "properties", "additionalProperties"}
_OPERATORS = ("_unset", "_append")

# Variables already reported as unknown in this process: one warning per variable and module.
_warned_env: Set[Tuple[str, str]] = set()


def _dotted(key: Iterable[str]) -> str:
    return ".".join(key)


def _split_key(key: Union[str, Iterable[str]]) -> Key:
    return tuple(key.split(".")) if isinstance(key, str) else tuple(key)


# ---------------------------------------------------------------------------------------------
# Module schema
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Leaf:
    """One setting of a module schema."""

    key: Key
    type: str  # string | integer | number | boolean | array
    node: Dict[str, Any]
    item_node: Optional[Dict[str, Any]]
    has_default: bool
    default: Any
    secret: bool
    layers: Optional[Tuple[str, ...]]
    description: str


class ModuleSchema:
    """The checked schema of a module's config section, with its leaves in schema order."""

    def __init__(self, module_id: str, registry: _schema.Registry, root: Dict[str, Any],
                 leaves: Dict[Key, Leaf], tables: Set[Key], source: str) -> None:
        self.module_id = module_id
        self.source = source
        self._registry = registry
        self._root = root
        self._id = registry.for_kind("config")[1]
        self.leaves = leaves
        self.tables = tables

    def leaf(self, key: Union[str, Iterable[str]]) -> Leaf:
        found = self.leaves.get(_split_key(key))
        if found is None:
            raise ConfigError("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.module_id!r}",
                              key=_dotted(_split_key(key)))
        return found

    def issues(self, node: Dict[str, Any], value: Any) -> List[_schema.ValidationIssue]:
        return _schema.validate_node(self._registry, node, self._id, value)


def _invalid(source: str, message: str, key: Key = ()) -> ConfigError:
    return ConfigError("CONFIG_SCHEMA_INVALID", message, file=source, key=_dotted(key) or None)


def load_module_schema(path: PathLike, module_id: str) -> ModuleSchema:
    """Load and check ``configs/config.schema.json`` of ``module_id`` (``CONFIG_SCHEMA_INVALID`` on any defect)."""
    source = str(path)
    if not _MODULE_ID.match(module_id or ""):
        raise _invalid(source, f"invalid module id {module_id!r}")
    try:
        registry = _schema.load_schema_file(Path(path), urn_prefix=f"urn:swissknifeman:{module_id}:",
                                            kind="config")
    except _schema.SchemaProfileError as exc:
        raise _invalid(source, str(exc)) from None
    root = registry.for_kind("config")[0]
    if root.get("type") != "object":
        raise _invalid(source, "the root of a config schema must have type object")
    leaves: Dict[Key, Leaf] = {}
    tables: Set[Key] = {()}
    _walk_table(root, (), source, leaves, tables, root=True)
    schema = ModuleSchema(module_id, registry, root, leaves, tables, source)
    for leaf in leaves.values():
        if leaf.has_default:
            if leaf.secret:
                if not is_secret_ref(leaf.default):
                    raise _invalid(source, "the default of a secret key must be a secret reference", leaf.key)
            elif schema.issues(leaf.node, leaf.default):
                raise _invalid(source, "the default does not satisfy the key's own schema", leaf.key)
    return schema


def _walk_table(node: Dict[str, Any], key: Key, source: str, leaves: Dict[Key, Leaf],
                tables: Set[Key], *, root: bool = False) -> None:
    extra = set(node) - (_ROOT_KEYWORDS if root else _TABLE_KEYWORDS)
    if extra:
        raise _invalid(source, f"keyword {sorted(extra)[0]!r} is not allowed on a table", key)
    if node.get("additionalProperties") is not False:
        raise _invalid(source, "every table must set additionalProperties to false", key)
    properties = node.get("properties")
    if not isinstance(properties, dict):
        raise _invalid(source, "a table must list its properties", key)
    for name, child in properties.items():
        child_key = key + (name,)
        if not _PROPERTY.match(name):
            raise _invalid(source, f"invalid key name {name!r}: use lowercase words joined by single "
                                   "underscores", child_key)
        if child.get("type") == "object" or "properties" in child:
            if child.get("type") != "object":
                raise _invalid(source, "a table must have type object", child_key)
            tables.add(child_key)
            _walk_table(child, child_key, source, leaves, tables)
        else:
            leaves[child_key] = _make_leaf(child, child_key, source)


def _leaf_type(node: Dict[str, Any], key: Key, source: str) -> str:
    declared = node.get("type")
    if declared is not None:
        if declared not in _LEAF_KEYWORDS:
            raise _invalid(source, "a key must be a string, integer, number, boolean or array", key)
        return declared
    options = node.get("enum")
    if not isinstance(options, list) or not options:
        raise _invalid(source, "a key needs a type or an enum", key)
    kinds = set()
    for option in options:
        kinds.add("boolean" if isinstance(option, bool) else "integer" if isinstance(option, int)
                  else "number" if isinstance(option, float) else "string" if isinstance(option, str) else "")
    if len(kinds) != 1 or "" in kinds:
        raise _invalid(source, "enum values must be scalars of one type", key)
    return kinds.pop()


def _make_leaf(node: Dict[str, Any], key: Key, source: str) -> Leaf:
    kind = _leaf_type(node, key, source)
    allowed = _COMMON_LEAF | _LEAF_KEYWORDS[kind]
    extra = set(node) - allowed
    if extra:
        raise _invalid(source, f"keyword {sorted(extra)[0]!r} is not allowed on a {kind} key", key)
    description = node.get("description")
    if not isinstance(description, str) or not description.strip():
        raise _invalid(source, "every key needs a description", key)
    secret = node.get("x-skm-secret") is True
    if secret and (kind != "string" or set(node) - (_COMMON_LEAF)):
        raise _invalid(source, "a secret key is a plain string: only description and default are allowed", key)
    layers = node.get("x-skm-layers")
    if layers is not None:
        for name in layers:
            if not _LAYER_ID.match(name):
                raise _invalid(source, f"invalid layer name {name!r} in x-skm-layers", key)
    item_node = None
    if kind == "array":
        item_node = node.get("items")
        if not isinstance(item_node, dict):
            raise _invalid(source, "an array key must declare its items", key)
        item_kind = item_node.get("type")
        if item_kind is None and "enum" in item_node:
            item_kind = _leaf_type(item_node, key, source)
        if item_kind not in _SCALARS or set(item_node) - _ITEM_KEYWORDS:
            raise _invalid(source, "array items must be scalars (string, integer, number or boolean)", key)
    return Leaf(key=key, type=kind, node=node, item_node=item_node, has_default="default" in node,
                default=copy.deepcopy(node.get("default")), secret=secret,
                layers=tuple(layers) if layers is not None else None, description=description)


def _schema_for(module_id: str, schema: Any, unit_root: Optional[PathLike]) -> ModuleSchema:
    if isinstance(schema, ModuleSchema):
        if schema.module_id != module_id:
            raise _invalid(schema.source, f"the schema belongs to module {schema.module_id!r}, not {module_id!r}")
        return schema
    if schema is not None:
        return load_module_schema(schema, module_id)
    if unit_root is None:
        raise _invalid("<none>", "resolve() needs a schema or the unit_root of the module")
    manifest = Path(unit_root) / "unit.json"
    try:
        unit = json.loads(manifest.read_text(encoding="utf-8"))
        relative = unit["provides"]["config"]
        unit_id = unit["id"]
    except (OSError, ValueError, KeyError, TypeError):
        raise _invalid(str(manifest), "unit.json must exist and declare provides.config") from None
    if unit_id != module_id:
        raise _invalid(str(manifest), f"unit.json describes module {unit_id!r}, not {module_id!r}")
    return load_module_schema(Path(unit_root) / relative, module_id)


# ---------------------------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ExtraLayer:
    """A module-specific layer between ``project`` and ``env`` (a legacy file, ``plan.settings``).

    ``data`` is the module's section (the content of ``[<module>]``, ``_unset``/``_append``
    allowed); ``index`` maps key paths relative to ``data`` to line numbers of ``file``.
    """

    name: str
    data: Mapping[str, Any]
    file: Optional[str] = None
    index: Optional[toml.LineIndex] = None


@dataclass(frozen=True)
class LayerInfo:
    name: str
    file: Optional[str]
    present: bool


class Setting(NamedTuple):
    """One value a layer gave to a key (``source``: variable, ``--config``, ``flag``, layer name, ``_unset``)."""

    layer: str
    file: Optional[str]
    line: Optional[int]
    source: Optional[str]
    value: Any

    def as_dict(self) -> Dict[str, Any]:
        return {"layer": self.layer, "file": self.file, "line": self.line, "source": self.source,
                "value": copy.deepcopy(self.value)}


@dataclass(frozen=True)
class ExplainEntry:
    """Where the effective value of a key comes from and what it overrides (nearest first)."""

    key: str
    value: Any
    layer: str
    file: Optional[str]
    line: Optional[int]
    source: Optional[str]
    secret: bool
    has_default: bool
    default: Any
    overridden: Tuple[Setting, ...]

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "key": self.key, "value": copy.deepcopy(self.value), "layer": self.layer, "file": self.file,
            "line": self.line, "source": self.source, "secret": self.secret,
        }
        if self.has_default:
            out["default"] = copy.deepcopy(self.default)
        out["overridden"] = [item.as_dict() for item in self.overridden]
        return out

    def text(self) -> str:
        lines = [f"{self.key} = {_render(self.value)}",
                 f"  from {_where(self.layer, self.file, self.line, self.source)}"]
        if self.overridden:
            parts = []
            for item in self.overridden:
                where = _where(item.layer, item.file, item.line, item.source)
                parts.append(f"{where} unset" if item.source == "_unset" else f"{where} = {_render(item.value)}")
            lines.append("  overrides " + "; ".join(parts))
        return "\n".join(lines)


def _render(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _where(layer: str, file: Optional[str], line: Optional[int], source: Optional[str]) -> str:
    text = layer
    if file:
        text += f" {file}:{line}" if line else f" {file}"
    elif source and source not in (layer, "flag", "_unset", "_append"):
        text += f" {source}"
    return text


_MISSING = object()


class ResolvedConfig:
    """The effective configuration of one module. Immutable; secrets appear as references only."""

    __slots__ = ("module", "project", "layers", "warnings", "_schema", "_values", "_history", "_env")

    def __init__(self, schema: ModuleSchema, values: Dict[Key, Any], history: Dict[Key, List[Setting]],
                 layers: Sequence[LayerInfo], project: Optional[str], warnings: Sequence[str],
                 env: Optional[Mapping[str, str]]) -> None:
        for name, value in (("module", schema.module_id), ("project", project), ("layers", tuple(layers)),
                            ("warnings", tuple(warnings)), ("_schema", schema), ("_values", values),
                            ("_history", history), ("_env", env)):
            object.__setattr__(self, name, value)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("ResolvedConfig is immutable")

    def __repr__(self) -> str:
        return f"ResolvedConfig(module={self.module!r}, keys={len(self._values)})"

    def get(self, key: Union[str, Iterable[str]], default: Any = None) -> Any:
        """Value of a leaf (a table gives a nested dict of its set values); ``default`` if it is unset."""
        parts = _split_key(key)
        if parts in self._schema.leaves:
            value = self._values.get(parts, _MISSING)
            return default if value is _MISSING else copy.deepcopy(value)
        if parts in self._schema.tables:
            return self._nested(parts)
        raise ConfigError("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.module!r}", key=_dotted(parts))

    def _nested(self, prefix: Key) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in self._values.items():
            if key[:len(prefix)] != prefix:
                continue
            cursor = out
            for part in key[len(prefix):-1]:
                cursor = cursor.setdefault(part, {})
            cursor[key[-1]] = copy.deepcopy(value)
        return out

    def as_dict(self) -> Dict[str, Any]:
        """A deep copy of the whole tree; secret keys hold their reference string."""
        return self._nested(())

    def secret(self, key: Union[str, Iterable[str]]) -> Secret:
        """The :class:`Secret` handle of a secret key; the value is looked up only on ``reveal()``."""
        leaf = self._schema.leaf(key)
        name = _dotted(leaf.key)
        if not leaf.secret:
            raise ConfigError("CONFIG_TYPE", "is not a secret key", key=name)
        ref = self._values.get(leaf.key)
        if ref is None:
            raise ConfigError("SECRET_UNRESOLVED", "no secret reference is set", key=name)
        env = self._env
        return Secret(ref, lambda: resolve_ref(ref, env))

    def explain(self, key: Union[str, Iterable[str], None] = None) -> List[ExplainEntry]:
        """Entries of one key, of the keys under a table, or (no ``key``) of every set key."""
        prefix: Key = () if key is None else _split_key(key)
        if prefix not in self._schema.tables and prefix not in self._schema.leaves:
            raise ConfigError("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.module!r}",
                              key=_dotted(prefix))
        return [self._entry(leaf_key) for leaf_key in self._schema.leaves
                if leaf_key[:len(prefix)] == prefix and leaf_key in self._values]

    def _entry(self, key: Key) -> ExplainEntry:
        leaf = self._schema.leaves[key]
        records = self._history[key]
        if records[-1].source == "_unset":  # reset to the default: the schema is the effective source
            winner, older = records[0], records[1:]
        else:
            winner, older = records[-1], records[:-1]
        value = copy.deepcopy(self._values[key])
        return ExplainEntry(
            key=_dotted(key), value=value, layer=winner.layer, file=winner.file, line=winner.line,
            source=winner.source, secret=leaf.secret, has_default=leaf.has_default,
            default=copy.deepcopy(leaf.default), overridden=tuple(reversed(older)))

    def explain_text(self, key: Union[str, Iterable[str], None] = None) -> str:
        return "\n".join(entry.text() for entry in self.explain(key))

    def explain_json(self, key: Union[str, Iterable[str], None] = None) -> Dict[str, Any]:
        """The ``config-explain/v1`` document."""
        return {
            "$schema": "urn:swissknifeman:aicore:config-explain:v1",
            "module": self.module,
            "project": self.project,
            "config_file_version": CONFIG_FILE_VERSION,
            "layers": [{"name": layer.name, "file": layer.file, "present": layer.present}
                       for layer in self.layers],
            "entries": [entry.as_dict() for entry in self.explain(key)],
        }


# ---------------------------------------------------------------------------------------------
# Applying layers
# ---------------------------------------------------------------------------------------------

def _text_value(leaf: Leaf, text: str) -> Any:
    """Parse text (environment, flags, ``config set``) by the leaf type; ``ValueError`` names the expectation."""
    if leaf.type == "string":
        return text
    stripped = text.strip()
    if leaf.type == "integer":
        if not _INTEGER.match(stripped):
            raise ValueError("expected an integer")
        return int(stripped)
    if leaf.type == "number":
        if not _NUMBER.match(stripped) or not math.isfinite(float(stripped)):
            raise ValueError("expected a number")
        return float(stripped)
    if leaf.type == "boolean":
        if stripped.lower() not in _BOOLEANS:
            raise ValueError("expected true, false, yes, no, 1 or 0")
        return _BOOLEANS[stripped.lower()]
    try:
        value = json.loads(stripped)
    except ValueError:
        value = None
    if not isinstance(value, list):
        raise ValueError("expected a JSON array")
    return value


def parse_value(schema: ModuleSchema, key: Union[str, Iterable[str]], text: str) -> Any:
    """Parse the text of a value for ``key`` as environment variables and ``config set`` do."""
    leaf = schema.leaf(key)
    try:
        return _text_value(leaf, text)
    except ValueError as exc:
        raise ConfigError("CONFIG_TYPE", f"{exc}" + (" (value redacted)" if leaf.secret else ""),
                          key=_dotted(leaf.key)) from None


class _State:
    """Values and per-key history while layers are applied from the lowest to the highest."""

    def __init__(self, schema: ModuleSchema) -> None:
        self.schema = schema
        self.values: Dict[Key, Any] = {}
        self.history: Dict[Key, List[Setting]] = {}
        for key, leaf in schema.leaves.items():
            if leaf.has_default:
                self.values[key] = copy.deepcopy(leaf.default)
                self.history[key] = [Setting("defaults", None, None, None, copy.deepcopy(leaf.default))]
            else:
                self.history[key] = []

    # -- checks -------------------------------------------------------------------------------

    def _fail(self, code: str, message: str, layer: str, file: Optional[str], line: Optional[int],
              key: Key) -> ConfigError:
        return ConfigError(code, message, layer=layer, file=file, line=line, key=_dotted(key) or None)

    def _allowed(self, leaf: Leaf, layer: str, file: Optional[str], line: Optional[int]) -> None:
        if leaf.layers is not None and layer not in leaf.layers and layer != "defaults":
            raise self._fail("CONFIG_LAYER_FORBIDDEN",
                             f"cannot be set in the {layer} layer (allowed: {', '.join(leaf.layers)})",
                             layer, file, line, leaf.key)

    def _check_value(self, leaf: Leaf, value: Any, layer: str, file: Optional[str],
                     line: Optional[int]) -> None:
        if leaf.secret:
            if not isinstance(value, str):
                raise self._fail("CONFIG_TYPE", "expected a secret reference string (value redacted)",
                                 layer, file, line, leaf.key)
            if not is_secret_ref(value):
                raise self._fail("SECRET_REF_INVALID", "not a secret reference of the form <scheme>://<name> "
                                 "(value redacted)", layer, file, line, leaf.key)
            return
        issues = self.schema.issues(leaf.node, value)
        if issues:
            raise self._fail("CONFIG_TYPE", _issue_text(issues[0]), layer, file, line, leaf.key)

    # -- layer application --------------------------------------------------------------------

    def _record(self, key: Key, value: Any, layer: str, file: Optional[str], line: Optional[int],
                source: Optional[str]) -> None:
        self.values[key] = value
        self.history[key].append(Setting(layer, file, line, source, copy.deepcopy(value)))

    def set_value(self, leaf: Leaf, value: Any, layer: str, file: Optional[str], line: Optional[int],
                  source: Optional[str]) -> None:
        self._allowed(leaf, layer, file, line)
        self._check_value(leaf, value, layer, file, line)
        self._record(leaf.key, copy.deepcopy(value), layer, file, line, source)

    def _flatten(self, body: Mapping[str, Any], base: Key, layer: str, file: Optional[str],
                 line_of: Callable[[Key], Optional[int]]) -> List[Tuple[Leaf, Any, Optional[int]]]:
        found: List[Tuple[Leaf, Any, Optional[int]]] = []
        for name, value in body.items():
            key = base + (name,)
            if key in self.schema.leaves:
                found.append((self.schema.leaves[key], value, line_of(key)))
            elif key in self.schema.tables:
                if not isinstance(value, Mapping):
                    raise self._fail("CONFIG_TYPE", "expected a table", layer, file, line_of(key), key)
                found.extend(self._flatten(value, key, layer, file, line_of))
            else:
                raise self._fail("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.schema.module_id!r}",
                                 layer, file, line_of(key), key)
        return found

    def _targets(self, name: str, layer: str, file: Optional[str], line: Optional[int]) -> List[Leaf]:
        key = _split_key(name)
        if key in self.schema.leaves:
            return [self.schema.leaves[key]]
        if key in self.schema.tables and key:
            return [leaf for leaf_key, leaf in self.schema.leaves.items() if leaf_key[:len(key)] == key]
        raise self._fail("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.schema.module_id!r}",
                         layer, file, line, key)

    def apply_section(self, layer: str, section: Mapping[str, Any], *, file: Optional[str],
                      index: Optional[toml.LineIndex], prefix: Key, source: Optional[str] = None) -> None:
        """Apply ``_unset``, then ``_append``, then plain values of one layer's section."""
        def line_of(key: Key) -> Optional[int]:
            return index.lookup(prefix + key) if index is not None else None

        unset = section.get("_unset")
        append = section.get("_append")
        body = {k: v for k, v in section.items() if k not in _OPERATORS}
        if unset is not None and not (isinstance(unset, list) and all(isinstance(k, str) for k in unset)):
            raise self._fail("CONFIG_TYPE", "_unset must be a list of key names", layer, file,
                             line_of(("_unset",)), ("_unset",))
        if append is not None and not isinstance(append, Mapping):
            raise self._fail("CONFIG_TYPE", "_append must be a table of key = [values]", layer, file,
                             line_of(("_append",)), ("_append",))
        plain = self._flatten(body, (), layer, file, line_of)
        plain_keys = {leaf.key for leaf, _value, _line in plain}
        appended = self._appends(append, layer, file, line_of) if append else []
        for leaf, _items, line in appended:
            if leaf.key in plain_keys:
                raise self._fail("CONFIG_CONFLICT", "is set and appended to in the same layer", layer, file,
                                 line, leaf.key)
        for name in unset or ():
            line = line_of(("_unset",))
            for leaf in self._targets(name, layer, file, line):
                self._allowed(leaf, layer, file, line)
                self._reset(leaf, layer, file, line)
        for leaf, items, line in appended:
            self._allowed(leaf, layer, file, line)
            current = self.values.get(leaf.key, [])
            self._record(leaf.key, copy.deepcopy(current) + copy.deepcopy(items), layer, file, line, "_append")
        for leaf, value, line in plain:
            self.set_value(leaf, value, layer, file, line, source)

    def _appends(self, append: Mapping[str, Any], layer: str, file: Optional[str],
                 line_of: Callable[[Key], Optional[int]]) -> List[Tuple[Leaf, List[Any], Optional[int]]]:
        found: List[Tuple[Leaf, List[Any], Optional[int]]] = []

        def walk(table: Mapping[str, Any], base: Key) -> None:
            for name, value in table.items():
                key = base + _split_key(name)
                line = line_of(("_append",) + key)
                if isinstance(value, Mapping):
                    walk(value, key)
                    continue
                leaf = self.schema.leaves.get(key)
                if leaf is None:
                    raise self._fail("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.schema.module_id!r}",
                                     layer, file, line, key)
                if leaf.type != "array":
                    raise self._fail("CONFIG_TYPE", "_append works only on array keys", layer, file, line, key)
                if not isinstance(value, list):
                    raise self._fail("CONFIG_TYPE", "_append takes a list", layer, file, line, key)
                for position, element in enumerate(value):
                    issues = self.schema.issues(leaf.item_node or {}, element)
                    if issues:
                        raise self._fail("CONFIG_TYPE", f"element {position}: {_issue_text(issues[0])}",
                                         layer, file, line, key)
                found.append((leaf, value, line))

        walk(append, ())
        return found

    def _reset(self, leaf: Leaf, layer: str, file: Optional[str], line: Optional[int]) -> None:
        if leaf.has_default:
            self.values[leaf.key] = copy.deepcopy(leaf.default)
        else:
            self.values.pop(leaf.key, None)
        self.history[leaf.key].append(Setting(layer, file, line, "_unset", None))

    def finish(self) -> None:
        """Validate the merged tree once more (array bounds after appends, for example)."""
        for key, value in self.values.items():
            leaf = self.schema.leaves[key]
            if leaf.secret:
                continue
            issues = self.schema.issues(leaf.node, value)
            if issues:
                last = self.history[key][-1]
                raise self._fail("CONFIG_TYPE", _issue_text(issues[0]), last.layer, last.file, last.line, key)


def _issue_text(issue: _schema.ValidationIssue) -> str:
    _location, _, rest = issue.message.partition(": ")
    return f"element {issue.path}: {rest}" if issue.path else rest


# ---------------------------------------------------------------------------------------------
# Files, environment, flags
# ---------------------------------------------------------------------------------------------

def _read_layer(layer: str, file: str, text: str, module_id: str
                ) -> Tuple[Optional[Dict[str, Any]], Optional[toml.LineIndex]]:
    """Parse and version-check the text of a config file; ``(section, index)`` or ``(None, None)`` if empty."""
    try:
        data = toml.loads(text, source=file)
    except ConfigError as exc:
        exc.layer = layer
        raise
    if not data:
        return None, None
    index = toml.LineIndex.from_text(text)

    def fail(code: str, message: str, key: Key) -> ConfigError:
        return ConfigError(code, message, layer=layer, file=file, line=index.lookup(key),
                           key=_dotted(key) or None)

    if "schema_version" not in data:
        raise fail("CONFIG_VERSION_MISSING", f"add `schema_version = {CONFIG_FILE_VERSION}` at the top of "
                                              "the file", ())
    version = data["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise fail("CONFIG_VERSION_INVALID", "schema_version must be a whole number of at least 1",
                   ("schema_version",))
    if version > CONFIG_FILE_VERSION:
        raise fail("CONFIG_VERSION_NEWER", f"schema_version {version} was written by a newer swissknifeman "
                                            f"(this one reads {CONFIG_FILE_VERSION}); upgrade", ("schema_version",))
    for name, value in data.items():
        if name != "schema_version" and not isinstance(value, dict):
            raise fail("CONFIG_UNKNOWN_KEY", "only schema_version and [module] tables are allowed at the "
                                              "top level", (name,))
    return data.get(module_id, {}), index


def _load_file(layer: str, path: Path, module_id: str, *, must_exist: bool = False
               ) -> Tuple[LayerInfo, Optional[Dict[str, Any]], Optional[toml.LineIndex]]:
    file = str(path)
    if not path.exists():
        if must_exist:
            raise ConfigError("CONFIG_FILE_INVALID", "the file does not exist", layer=layer, file=file)
        return LayerInfo(layer, file, False), None, None
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        reason = "not valid UTF-8" if isinstance(exc, UnicodeDecodeError) else exc.strerror or "unreadable"
        raise ConfigError("CONFIG_FILE_INVALID", f"cannot read the file: {reason}", layer=layer,
                          file=file) from None
    section, index = _read_layer(layer, file, text, module_id)
    return LayerInfo(layer, file, section is not None), section, index


def _warn_stderr(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def _apply_env(state: _State, env: Mapping[str, str], warn: Callable[[str], None],
               notices: List[str]) -> bool:
    module_id = state.schema.module_id
    prefix = "SKM_" + module_id.upper().replace("-", "_") + "_"
    names = {"__".join(key).upper(): leaf for key, leaf in state.schema.leaves.items()}
    applied = False
    for name in sorted(env):
        if not name.startswith(prefix):
            continue
        leaf = names.get(name[len(prefix):])
        if leaf is None:
            message = (f"[CONFIG_ENV_UNKNOWN] environment variable {name} matches no {module_id} "
                       "configuration key; ignoring it")
            notices.append(message)
            if (module_id, name) not in _warned_env:
                _warned_env.add((module_id, name))
                warn(message)
            continue
        text = env[name]
        key = _dotted(leaf.key)
        if leaf.secret:
            if not is_secret_ref(text):
                raise ConfigError("SECRET_REF_INVALID", f"{name} must hold a reference such as env://NAME "
                                  "(value redacted)", layer="env", key=key)
            value: Any = text
        else:
            try:
                value = _text_value(leaf, text)
            except ValueError as exc:
                raise ConfigError("CONFIG_ENV_VALUE", f"{name}: {exc}", layer="env", key=key) from None
        state.set_value(leaf, value, "env", None, None, name)
        applied = True
    return applied


def _apply_flags(state: _State, flags: Mapping[str, Any]) -> bool:
    applied = False
    for name, raw in flags.items():
        if raw is None:
            continue
        key = _split_key(name)
        leaf = state.schema.leaves.get(key)
        if leaf is None:
            raise ConfigError("CONFIG_UNKNOWN_KEY", f"unknown key for module {state.schema.module_id!r}",
                              layer="flags", key=_dotted(key))
        if isinstance(raw, str):
            try:
                value: Any = raw if leaf.secret else _text_value(leaf, raw)
            except ValueError as exc:
                raise ConfigError("CONFIG_TYPE", str(exc), layer="flags", key=_dotted(key)) from None
        else:
            value = raw
        state.set_value(leaf, value, "flags", None, None, "flag")
        applied = True
    return applied


def resolve(module_id: str, *, unit_root: Optional[PathLike] = None, schema: Any = None,
            project: Optional[PathLike] = None, config_file: Optional[PathLike] = None,
            extra_layers: Sequence[ExtraLayer] = (), flags: Optional[Mapping[str, Any]] = None,
            env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
            warn: Optional[Callable[[str], None]] = None) -> ResolvedConfig:
    """Resolve the configuration of ``module_id`` from all layers.

    ``schema`` is a :class:`ModuleSchema` or a path to ``config.schema.json``; without it the schema
    is found through ``unit.json`` (``provides.config``) in ``unit_root``. ``project`` is the project
    root (its ``.swissknifeman/config.toml`` is the project layer; ``None`` means no project layer),
    ``config_file`` the ``--config FILE`` layer, ``flags`` a mapping of dotted keys to values from
    the command line (``None`` values are skipped, text values are parsed by the key's type). ``env``
    and ``home`` default to the process environment and home directory. ``warn`` receives the
    ``CONFIG_ENV_UNKNOWN`` notices (default: stderr, once per process and variable); they are also in
    ``ResolvedConfig.warnings``.
    """
    module = _schema_for(module_id, schema, unit_root)
    state = _State(module)
    layers: List[LayerInfo] = [LayerInfo("defaults", None, True)]
    notices: List[str] = []
    environment = os.environ if env is None else env
    warn = warn or _warn_stderr
    prefix: Key = (module_id,)

    machine = Path(machine_config_file(env=environment, home=home))
    candidates: List[Tuple[str, Path]] = [("machine", machine)]
    if project is not None:
        candidates.append(("project", Path(project_config_file(project))))
    for layer, path in candidates:
        info, section, index = _load_file(layer, path, module_id)
        layers.append(info)
        if section:
            state.apply_section(layer, section, file=info.file, index=index, prefix=prefix)
    if project is None:
        layers.insert(2, LayerInfo("project", None, False))

    for extra in extra_layers:
        if extra.name in LAYER_NAMES or not _LAYER_ID.match(extra.name or ""):
            raise ConfigError("CONFIG_FILE_INVALID", f"invalid extra layer name {extra.name!r}")
        if not isinstance(extra.data, Mapping):
            raise ConfigError("CONFIG_TYPE", "extra layer data must be a table", layer=extra.name)
        layers.append(LayerInfo(extra.name, extra.file, bool(extra.data)))
        if extra.data:
            state.apply_section(extra.name, extra.data, file=extra.file, index=extra.index, prefix=(),
                                source=extra.name)

    env_applied = _apply_env(state, environment, warn, notices)
    layers.append(LayerInfo("env", None, env_applied))

    if config_file is not None:
        info, section, index = _load_file("invocation", Path(config_file), module_id, must_exist=True)
        layers.append(info)
        if section:
            state.apply_section("invocation", section, file=info.file, index=index, prefix=prefix,
                                source="--config")
    else:
        layers.append(LayerInfo("invocation", None, False))

    flags_applied = _apply_flags(state, flags) if flags else False
    layers.append(LayerInfo("flags", None, flags_applied))

    state.finish()
    return ResolvedConfig(module, state.values, state.history, layers,
                          None if project is None else str(project), notices, environment)


# ---------------------------------------------------------------------------------------------
# Writing a layer
# ---------------------------------------------------------------------------------------------

class EditResult(NamedTuple):
    changed: bool
    backup: Optional[Path]


def edit_layer_file(path: PathLike, module_id: str, key: Union[str, Iterable[str]], value: Any = None, *,
                    schema: Any, layer: str = "machine", remove: bool = False,
                    project: Optional[PathLike] = None, env: Optional[Mapping[str, str]] = None,
                    home: Optional[PathLike] = None) -> EditResult:
    """Set (or, with ``remove``, delete) one key in a layer file, keeping its comments.

    Steps: parse the file, edit the text with :mod:`aicore.config.toml_edit`, check the resulting
    section of the layer against the module schema (unknown key, type, range, forbidden layer),
    back the old file up with :func:`aicore.state.backup` and replace it atomically. On any error
    the file is left untouched. A missing or empty file is created with ``schema_version``.
    ``value`` is typed (use :func:`parse_value` for text). A symlink is followed, so the link stays.
    Raises :class:`ConfigError`, or ``toml_edit.TomlEditError`` for layouts the editor refuses.
    """
    if layer not in FILE_LAYERS:
        raise ValueError(f"layer must be one of {', '.join(FILE_LAYERS)}, got {layer!r}")
    module = _schema_for(module_id, schema, None)
    leaf = module.leaf(key)
    target = Path(os.path.realpath(path))
    file = str(path)
    existed = target.exists()
    try:
        text = target.read_bytes().decode("utf-8") if existed else ""
    except (OSError, UnicodeDecodeError) as exc:
        reason = "not valid UTF-8" if isinstance(exc, UnicodeDecodeError) else exc.strerror or "unreadable"
        raise ConfigError("CONFIG_FILE_INVALID", f"cannot read the file: {reason}", layer=layer,
                          file=file) from None
    if text.startswith("﻿"):
        text = text[1:]
    section, _index = _read_layer(layer, file, text, module_id)
    base = text
    if section is None:  # absent or empty: start the file with its version line
        base = f"schema_version = {CONFIG_FILE_VERSION}\n" + text
    edit_path = (module_id,) + leaf.key
    if remove:
        new_text = toml_edit.unset_value(base, edit_path, source=file)
    else:
        if leaf.secret and not is_secret_ref(value):
            raise ConfigError("SECRET_REF_INVALID", "not a secret reference of the form <scheme>://<name> "
                              "(value redacted)", layer=layer, key=_dotted(leaf.key))
        new_text = toml_edit.set_value(base, edit_path, value, source=file)
    new_section, new_index = _read_layer(layer, file, new_text, module_id)
    scratch = _State(module)
    scratch.apply_section(layer, new_section or {}, file=file, index=new_index, prefix=(module_id,))
    if new_text == text or (remove and new_text == base):
        return EditResult(False, None)
    saved = backup(path, project=project, env=env, home=home) if existed else None
    mode = stat.S_IMODE(target.stat().st_mode) if existed else None
    if layer == "machine" and not target.parent.exists():
        ensure_dir(target.parent)
    _io.atomic_write_text(target, new_text, mode=mode)
    return EditResult(True, saved)
