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
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import (Any, Callable, Dict, Iterable, Iterator, List, Mapping, NamedTuple, Optional, Sequence,
                    Set, Tuple, Union)

from ..state import backup, ensure_dir, machine_config_file, project_config_file
from ..util import io as _io
from ..util import schema as _schema
from ..util.digest import sha256_tagged
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
_MAP_KEYWORDS = {"type", "title", "description", "patternProperties", "additionalProperties"}
ENTRY = "*"  # stands for the name of an entry in the keys of a map's template leaves
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


@dataclass(frozen=True)
class MapSpec:
    """A dictionary table: entries named by ``pattern``, each entry one leaf or one table of leaves.

    The template leaves hold the placeholder :data:`ENTRY` where the entry name goes in their ``key``
    (``("subscriptions", "*", "on")``); :meth:`ModuleSchema.leaf` rewrites them to a real entry.
    """

    key: Key
    pattern: str
    regex: Any
    description: str
    value_leaf: Optional[Leaf]
    value_table: Optional[Dict[str, Leaf]]

    def matches(self, name: str) -> bool:
        return self.regex.search(name) is not None

    def templates(self) -> List[Leaf]:
        return [self.value_leaf] if self.value_leaf is not None else list((self.value_table or {}).values())


class ModuleSchema:
    """The checked schema of a module's config section, with its leaves in schema order.

    ``leaves`` and ``tables`` hold the fixed part of the schema; ``maps`` the dictionary tables, whose
    entries exist only in configuration files (see :class:`MapSpec`).
    """

    def __init__(self, module_id: str, registry: _schema.Registry, root: Dict[str, Any],
                 leaves: Dict[Key, Leaf], tables: Set[Key], source: str,
                 maps: Optional[Dict[Key, MapSpec]] = None) -> None:
        self.module_id = module_id
        self.source = source
        self._registry = registry
        self._root = root
        self._id = registry.for_kind("config")[1]
        self.leaves = leaves
        self.tables = tables
        self.maps: Dict[Key, MapSpec] = maps or {}

    def entry_of(self, key: Key) -> Optional[Tuple[MapSpec, str, Key]]:
        """``(map, entry name, rest of the key)`` when ``key`` lies in an entry of a map, else ``None``."""
        for spec in self.maps.values():
            size = len(spec.key)
            if len(key) > size and key[:size] == spec.key and spec.matches(key[size]):
                return spec, key[size], key[size + 1:]
        return None

    def find_leaf(self, key: Union[str, Iterable[str]]) -> Optional[Leaf]:
        """The leaf of ``key`` (a leaf of an entry is the template leaf with the real key), or ``None``."""
        parts = _split_key(key)
        found = self.leaves.get(parts)
        if found is not None:
            return found
        hit = self.entry_of(parts)
        if hit is None:
            return None
        spec, _name, rest = hit
        if spec.value_leaf is not None and not rest:
            template = spec.value_leaf
        elif spec.value_table is not None and len(rest) == 1 and rest[0] in spec.value_table:
            template = spec.value_table[rest[0]]
        else:
            return None
        return replace(template, key=parts)

    def classify(self, key: Union[str, Iterable[str]]) -> Optional[str]:
        """``leaf``, ``table``, ``map`` or ``entry`` (a table-valued entry of a map); ``None`` if unknown."""
        parts = _split_key(key)
        if parts in self.tables:
            return "table"
        if parts in self.maps:
            return "map"
        if self.find_leaf(parts) is not None:
            return "leaf"
        hit = self.entry_of(parts)
        return "entry" if hit is not None and not hit[2] and hit[0].value_table is not None else None

    def leaf(self, key: Union[str, Iterable[str]]) -> Leaf:
        found = self.find_leaf(key)
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
    maps: Dict[Key, MapSpec] = {}
    _walk_table(root, (), source, leaves, tables, maps, root=True)
    schema = ModuleSchema(module_id, registry, root, leaves, tables, source, maps)
    for leaf in [*leaves.values(), *(t for spec in maps.values() for t in spec.templates())]:
        if leaf.has_default:
            if leaf.secret:
                if not is_secret_ref(leaf.default):
                    raise _invalid(source, "the default of a secret key must be a secret reference", leaf.key)
            elif schema.issues(leaf.node, leaf.default):
                raise _invalid(source, "the default does not satisfy the key's own schema", leaf.key)
    return schema


def _walk_table(node: Dict[str, Any], key: Key, source: str, leaves: Dict[Key, Leaf],
                tables: Set[Key], maps: Dict[Key, MapSpec], *, root: bool = False) -> None:
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
        if _is_object(child):
            if child.get("type") != "object":
                raise _invalid(source, "a table must have type object", child_key)
            if "patternProperties" in child:
                maps[child_key] = _make_map(child, child_key, source)
            else:
                tables.add(child_key)
                _walk_table(child, child_key, source, leaves, tables, maps)
        else:
            leaves[child_key] = _make_leaf(child, child_key, source)


def _is_object(node: Dict[str, Any]) -> bool:
    return node.get("type") == "object" or "properties" in node or "patternProperties" in node


def _can_match_dot(pattern: str) -> bool:
    """True when ``pattern`` can consume a ``.``: a dotted entry name would be unreachable through dotted keys.

    The pattern is parsed and its consuming parts are checked (a literal dot, ``.``, a class that holds a dot,
    a negated class or ``\\W``-like category); look-around assertions consume nothing and are skipped.
    """
    try:
        from re import _parser as sre_parse  # Python 3.11+
        from re import _constants as sre_constants
    except ImportError:  # Python 3.9, 3.10
        import sre_constants  # type: ignore[no-redef]
        import sre_parse  # type: ignore[no-redef]
    dot = ord(".")
    repeats = tuple(getattr(sre_constants, name) for name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT")
                    if hasattr(sre_constants, name))

    def class_has_dot(items) -> bool:
        negated = bool(items) and items[0][0] == sre_constants.NEGATE
        found = False
        for op, arg in items:
            if op == sre_constants.LITERAL and arg == dot:
                found = True
            elif op == sre_constants.RANGE and arg[0] <= dot <= arg[1]:
                found = True
            elif op == sre_constants.CATEGORY and arg in (sre_constants.CATEGORY_NOT_DIGIT,
                                                          sre_constants.CATEGORY_NOT_WORD,
                                                          sre_constants.CATEGORY_NOT_SPACE):
                found = True
        return found != negated

    def walk(items) -> bool:
        for op, arg in items:
            if op in (sre_constants.ASSERT, sre_constants.ASSERT_NOT):
                continue
            if op == sre_constants.LITERAL:
                if arg == dot:
                    return True
            elif op == sre_constants.NOT_LITERAL:
                if arg != dot:
                    return True
            elif op == sre_constants.ANY:
                return True
            elif op == sre_constants.IN:
                if class_has_dot(arg):
                    return True
            elif op == sre_constants.CATEGORY:
                if arg in (sre_constants.CATEGORY_NOT_DIGIT, sre_constants.CATEGORY_NOT_WORD,
                           sre_constants.CATEGORY_NOT_SPACE):
                    return True
            elif op == sre_constants.SUBPATTERN:
                if walk(arg[-1]):
                    return True
            elif op in repeats:
                if walk(arg[2]):
                    return True
            elif op == sre_constants.BRANCH:
                if any(walk(branch) for branch in arg[1]):
                    return True
            elif op == getattr(sre_constants, "ATOMIC_GROUP", None):
                if walk(arg):
                    return True
            elif op == sre_constants.GROUPREF_EXISTS:  # (?(1)yes|no)
                if walk(arg[1]) or (arg[2] is not None and walk(arg[2])):
                    return True
            elif op not in (sre_constants.AT, sre_constants.GROUPREF):
                return True  # an operation this walk does not know: assume it can consume a dot
        return False

    try:
        return walk(sre_parse.parse(pattern))
    except Exception:  # noqa: BLE001  (an unparsable pattern is refused by the validator profile anyway)
        return True


def _make_map(node: Dict[str, Any], key: Key, source: str) -> MapSpec:
    """Check a dictionary table: one anchored pattern, entries that are a leaf or a table of leaves."""
    extra = set(node) - _MAP_KEYWORDS
    if extra:
        raise _invalid(source, f"keyword {sorted(extra)[0]!r} is not allowed on a map", key)
    if node.get("additionalProperties") is not False:
        raise _invalid(source, "every map must set additionalProperties to false", key)
    description = node.get("description")
    if not isinstance(description, str) or not description.strip():
        raise _invalid(source, "every map needs a description", key)
    patterns = node["patternProperties"]
    if len(patterns) != 1:
        raise _invalid(source, "a map takes exactly one pattern", key)
    pattern, value = next(iter(patterns.items()))
    if not (pattern.startswith("^") and pattern.endswith("$") and not pattern.endswith("\\$")):
        raise _invalid(source, f"the pattern {pattern!r} of a map must be anchored with ^ and $", key)
    regex = _schema._compile(pattern)  # noqa: SLF001  (the validator's own dialect)
    if regex.search("a.b") is not None or _can_match_dot(pattern):
        raise _invalid(source, f"map keys cannot contain dots, but the pattern {pattern!r} allows them", key)
    entry_key = key + (ENTRY,)
    if not _is_object(value):
        return MapSpec(key, pattern, regex, description, _make_leaf(value, entry_key, source), None)
    if value.get("type") != "object" or "patternProperties" in value:
        raise _invalid(source, "an entry is a leaf or a table of leaves, not a nested map", key)
    extra = set(value) - _TABLE_KEYWORDS
    if extra:
        raise _invalid(source, f"keyword {sorted(extra)[0]!r} is not allowed on an entry", key)
    properties = value.get("properties")
    if value.get("additionalProperties") is not False or not isinstance(properties, dict) or not properties:
        raise _invalid(source, "an entry table must list its properties and set additionalProperties to false",
                       key)
    template: Dict[str, Leaf] = {}
    for name, child in properties.items():
        if not _PROPERTY.match(name):
            raise _invalid(source, f"invalid key name {name!r}: use lowercase words joined by single "
                                   "underscores", entry_key + (name,))
        if _is_object(child):
            raise _invalid(source, "an entry holds leaves only", entry_key + (name,))
        template[name] = _make_leaf(child, entry_key + (name,), source)
    return MapSpec(key, pattern, regex, description, None, template)


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

    __slots__ = ("module", "project", "layers", "warnings", "_schema", "_values", "_history", "_env",
                 "_entries")

    def __init__(self, schema: ModuleSchema, values: Dict[Key, Any], history: Dict[Key, List[Setting]],
                 layers: Sequence[LayerInfo], project: Optional[str], warnings: Sequence[str],
                 env: Optional[Mapping[str, str]], entries: Optional[Dict[Key, List[str]]] = None) -> None:
        for name, value in (("module", schema.module_id), ("project", project), ("layers", tuple(layers)),
                            ("warnings", tuple(warnings)), ("_schema", schema), ("_values", values),
                            ("_history", history), ("_env", env), ("_entries", entries or {})):
            object.__setattr__(self, name, value)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("ResolvedConfig is immutable")

    def __repr__(self) -> str:
        return f"ResolvedConfig(module={self.module!r}, keys={len(self._values)})"

    def get(self, key: Union[str, Iterable[str]], default: Any = None) -> Any:
        """Value of a leaf, or a nested dict for a table or a map (``{}`` while it has no entries).

        ``default`` is returned for an unset leaf and for an entry that does not exist. A leaf of an existing
        entry that no layer set has the default of its schema.
        """
        parts = _split_key(key)
        kind = self._schema.classify(parts)
        if kind == "leaf":
            value = self._values.get(parts, _MISSING)
            return default if value is _MISSING else copy.deepcopy(value)
        if kind in ("table", "map"):
            return self._nested(parts)
        if kind == "entry":
            hit = self._schema.entry_of(parts)
            assert hit is not None
            return self._nested(parts) if hit[1] in self._entries.get(hit[0].key, ()) else default
        raise ConfigError("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.module!r}", key=_dotted(parts))

    def _nested(self, prefix: Key) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for map_key in self._schema.maps:  # a map without entries is an empty dictionary
            if map_key[:len(prefix)] == prefix:
                cursor = out
                for part in map_key[len(prefix):]:
                    cursor = cursor.setdefault(part, {})
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
        if self._schema.classify(prefix) is None:
            raise ConfigError("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.module!r}",
                              key=_dotted(prefix))
        return [self._entry(leaf_key) for leaf_key in self._ordered_keys()
                if leaf_key[:len(prefix)] == prefix and leaf_key in self._values]

    def _ordered_keys(self) -> Iterable[Key]:
        """The schema's leaves in schema order, then the entries of each map (first seen first, leaves in order)."""
        yield from self._schema.leaves
        for spec in self._schema.maps.values():
            for name in self._entries.get(spec.key, ()):
                if spec.value_leaf is not None:
                    yield spec.key + (name,)
                else:
                    for prop in spec.value_table or ():
                        yield spec.key + (name, prop)

    def _entry(self, key: Key) -> ExplainEntry:
        leaf = self._schema.leaf(key)
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
        self.entries: Dict[Key, List[str]] = {key: [] for key in schema.maps}
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
        self.history.setdefault(key, []).append(Setting(layer, file, line, source, copy.deepcopy(value)))

    def _touch(self, leaf: Leaf) -> None:
        """Create the entry of a map that ``leaf`` belongs to, with the defaults of its leaves."""
        hit = self.schema.entry_of(leaf.key)
        if hit is None:
            return
        spec, name, _rest = hit
        if name in self.entries[spec.key]:
            return
        self.entries[spec.key].append(name)
        for template in spec.templates():
            if template.has_default:
                key = spec.key + (name,) + (() if spec.value_leaf is not None else (template.key[-1],))
                self.values[key] = copy.deepcopy(template.default)
                self.history[key] = [Setting("defaults", None, None, None, copy.deepcopy(template.default))]

    def _drop_entry(self, spec: MapSpec, name: str) -> None:
        for key in [k for k in self.values if k[:len(spec.key) + 1] == spec.key + (name,)]:
            del self.values[key]
            self.history.pop(key, None)
        if name in self.entries[spec.key]:
            self.entries[spec.key].remove(name)

    def set_value(self, leaf: Leaf, value: Any, layer: str, file: Optional[str], line: Optional[int],
                  source: Optional[str]) -> None:
        self._allowed(leaf, layer, file, line)
        self._check_value(leaf, value, layer, file, line)
        self._touch(leaf)
        self._record(leaf.key, copy.deepcopy(value), layer, file, line, source)

    def _flatten(self, body: Mapping[str, Any], base: Key, layer: str, file: Optional[str],
                 line_of: Callable[[Key], Optional[int]]) -> List[Tuple[Leaf, Any, Optional[int]]]:
        found: List[Tuple[Leaf, Any, Optional[int]]] = []
        for name, value in body.items():
            key = base + (name,)
            kind = self.schema.classify(key)
            if kind == "leaf":
                found.append((self.schema.leaf(key), value, line_of(key)))
            elif kind is not None:  # table, map or entry
                if not isinstance(value, Mapping):
                    raise self._fail("CONFIG_TYPE", "expected a table", layer, file, line_of(key), key)
                found.extend(self._flatten(value, key, layer, file, line_of))
            else:
                raise self._fail("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.schema.module_id!r}",
                                 layer, file, line_of(key), key)
        return found

    def _unset(self, name: str, layer: str, file: Optional[str], line: Optional[int]) -> None:
        """``_unset`` of a leaf (back to its default), a table (every leaf), an entry or a map (removed)."""
        key = _split_key(name)
        kind = self.schema.classify(key)
        if kind is None or (kind == "table" and not key):
            raise self._fail("CONFIG_UNKNOWN_KEY", f"unknown key for module {self.schema.module_id!r}",
                             layer, file, line, key)
        if kind == "leaf":
            leaf = self.schema.leaf(key)
            hit = self.schema.entry_of(key)
            if hit is not None and hit[1] not in self.entries[hit[0].key]:
                return  # nothing to reset: the entry does not exist
            self._allowed(leaf, layer, file, line)
            self._reset(leaf, layer, file, line)
            return
        for leaf_key, leaf in self.schema.leaves.items():
            if kind == "table" and leaf_key[:len(key)] == key:
                self._allowed(leaf, layer, file, line)
                self._reset(leaf, layer, file, line)
        for spec in self.schema.maps.values():
            if kind == "entry":
                hit = self.schema.entry_of(key)
                names = [hit[1]] if hit is not None and hit[0] is spec else []
            else:  # a table or a map: the entries of the maps at or below it
                names = list(self.entries[spec.key]) if spec.key[:len(key)] == key else []
            for entry in names:
                owned = [k for k in self.values if k[:len(spec.key) + 1] == spec.key + (entry,)]
                for owned_key in owned:  # a layer may remove only what it may define
                    self._allowed(self.schema.leaf(owned_key), layer, file, line)
                self._drop_entry(spec, entry)

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
            self._unset(name, layer, file, line_of(("_unset",)))
        for leaf, items, line in appended:
            self._allowed(leaf, layer, file, line)
            self._touch(leaf)
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
                leaf = self.schema.find_leaf(key)
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
            hit = self.schema.entry_of(leaf.key)
            if hit is not None and hit[0].value_leaf is not None:  # an entry that is one leaf is its value
                self._drop_entry(hit[0], hit[1])
                return
        self.history.setdefault(leaf.key, []).append(Setting(layer, file, line, "_unset", None))

    def finish(self) -> None:
        """Validate the merged tree once more (array bounds after appends, for example)."""
        for key, value in self.values.items():
            leaf = self.schema.leaf(key)
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


def _load_file(layer: str, path: Path, module_id: str, *, must_exist: bool = False,
               text: Optional[str] = None
               ) -> Tuple[LayerInfo, Optional[Dict[str, Any]], Optional[toml.LineIndex]]:
    file = str(path)
    if text is None:
        if not path.exists():
            if must_exist:
                raise ConfigError("CONFIG_FILE_INVALID", "the file does not exist", layer=layer, file=file)
            return LayerInfo(layer, file, False), None, None
        text = _decode_file(layer, path, file)
    elif text.startswith("\ufeff"):
        text = text[1:]
    section, index = _read_layer(layer, file, text, module_id)
    return LayerInfo(layer, file, section is not None), section, index


def _decode_file(layer: str, path: Path, file: str) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        reason = "not valid UTF-8" if isinstance(exc, UnicodeDecodeError) else exc.strerror or "unreadable"
        raise ConfigError("CONFIG_FILE_INVALID", f"cannot read the file: {reason}", layer=layer,
                          file=file) from None


# ``SKM_<MODULE>_ROOT`` names the folder of a module for the tools that look for it (bridges, locators). It is not
# read as configuration unless the module's schema has a top-level key ``root``.
LOCATOR_SUFFIX = "ROOT"


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
        if leaf is None and name[len(prefix):] == LOCATOR_SUFFIX:
            continue  # SKM_<MODULE>_ROOT locates the module's folder; it is not a configuration key
        if leaf is None:
            if any(name[len(prefix):].startswith("__".join(map_key).upper() + "__") for map_key in state.schema.maps):
                message = (f"[CONFIG_ENV_UNKNOWN] environment variable {name} names an entry of a {module_id} "
                           "map, which the environment cannot set (use a config file or --config); ignoring it")
            else:
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
        leaf = state.schema.find_leaf(key)
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
            warn: Optional[Callable[[str], None]] = None,
            layer_texts: Optional[Mapping[str, str]] = None) -> ResolvedConfig:
    """Resolve the configuration of ``module_id`` from all layers.

    ``schema`` is a :class:`ModuleSchema` or a path to ``config.schema.json``; without it the schema
    is found through ``unit.json`` (``provides.config``) in ``unit_root``. ``project`` is the project
    root (its ``.swissknifeman/config.toml`` is the project layer; ``None`` means no project layer),
    ``config_file`` the ``--config FILE`` layer, ``flags`` a mapping of dotted keys to values from
    the command line (``None`` values are skipped, text values are parsed by the key's type). ``env``
    and ``home`` default to the process environment and home directory. ``warn`` receives the
    ``CONFIG_ENV_UNKNOWN`` notices (default: stderr, once per process and variable); they are also in
    ``ResolvedConfig.warnings``. ``layer_texts`` maps ``machine`` and ``project`` to a text that is read instead
    of the file (the file name in the provenance stays the real path; nothing is read or written), which gives
    the effective settings of a change before it is written.
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
        override = layer_texts.get(layer) if layer_texts else None
        info, section, index = _load_file(layer, path, module_id, text=override)
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
                          None if project is None else str(project), notices, environment, state.entries)


# ---------------------------------------------------------------------------------------------
# Writing a layer
# ---------------------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------------------
# Writing a layer
# ---------------------------------------------------------------------------------------------

_BOM = "﻿"
_LOCK_POLL_S = 0.05
PatchOp = Tuple[str, str, Any]  # ("set", key, value) | ("unset", key, None)


class _EditRefused(ConfigError, toml_edit.TomlEditError):
    """``CONFIG_EDIT_REFUSED``; still a ``TomlEditError`` for callers of ``edit_layer_file`` that catch that."""


class _EditFields(NamedTuple):
    changed: bool
    backup: Optional[Path]


class EditResult(_EditFields):
    """``(changed, backup)`` of a write, plus ``revision``: the digest of the file after it (before it, if unchanged).

    A tuple of two so that ``changed, backup = result`` keeps working; ``revision`` is an attribute.
    """

    revision: str

    def __new__(cls, changed: bool, backup: Optional[Path], revision: str = "") -> "EditResult":
        self = super().__new__(cls, changed, backup)
        self.revision = revision
        return self

    def __repr__(self) -> str:
        return f"EditResult(changed={self.changed!r}, backup={self.backup!r}, revision={self.revision!r})"


def layer_revision(data: bytes) -> str:
    """The revision of a layer file: the tagged sha256 of its bytes (a missing file is ``b""``)."""
    return sha256_tagged(data)


@dataclass(frozen=True)
class LayerSnapshot:
    """A layer file as it is on disk: text without BOM, revision of the raw bytes, the module's own values."""

    file: str
    exists: bool
    text: str
    revision: str
    values: Dict[str, Any]  # dotted key -> value set in this layer (secret values that are not references redacted)
    lines: Dict[str, int]  # dotted key -> 1-based line


@dataclass(frozen=True)
class LayerEditPlan:
    text_before: str
    text_after: str
    changed: bool
    before: Dict[str, Any]  # value of the key of each operation in the layer before (absent key: not in the dict)
    after: Dict[str, Any]
    issues: Tuple[ConfigError, ...]


def _read_bytes(layer: str, target: Path, file: str) -> Tuple[bool, bytes]:
    try:
        if not target.exists():
            return False, b""
        return True, target.read_bytes()
    except OSError as exc:
        raise ConfigError("CONFIG_FILE_INVALID", f"cannot read the file: {exc.strerror or 'unreadable'}",
                          layer=layer, file=file) from None


def _decode(layer: str, data: bytes, file: str) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError("CONFIG_FILE_INVALID", "cannot read the file: not valid UTF-8", layer=layer,
                          file=file) from None
    return text[1:] if text.startswith(_BOM) else text


def _check_layer(layer: str) -> None:
    if layer not in FILE_LAYERS:
        raise ValueError(f"layer must be one of {', '.join(FILE_LAYERS)}, got {layer!r}")


def _layer_values(module: ModuleSchema, section: Optional[Mapping[str, Any]], index: Optional[toml.LineIndex],
                  module_id: str) -> Tuple[Dict[str, Any], Dict[str, int]]:
    values: Dict[str, Any] = {}
    lines: Dict[str, int] = {}

    def walk(body: Mapping[str, Any], base: Key) -> None:
        for name, value in body.items():
            key = base + (name,)
            kind = module.classify(key)
            if kind == "leaf":
                leaf = module.leaf(key)
                values[_dotted(key)] = ("(value redacted)" if leaf.secret and not (
                    isinstance(value, str) and is_secret_ref(value)) else copy.deepcopy(value))
                line = index.lookup((module_id,) + key) if index is not None else None
                if line is not None:
                    lines[_dotted(key)] = line
            elif kind is not None and isinstance(value, Mapping):
                walk(value, key)

    walk({k: v for k, v in (section or {}).items() if k not in _OPERATORS}, ())
    return values, lines


def read_layer(path: PathLike, module_id: str, *, schema: Any, layer: str) -> LayerSnapshot:
    """Read a layer file without a lock: its text, revision and the values this layer sets for ``module_id``."""
    _check_layer(layer)
    module = _schema_for(module_id, schema, None)
    target = Path(os.path.realpath(path))
    file = str(path)
    exists, data = _read_bytes(layer, target, file)
    text = _decode(layer, data, file)
    section, index = _read_layer(layer, file, text, module_id)
    values, lines = _layer_values(module, section, index, module_id)
    return LayerSnapshot(file, exists, text, layer_revision(data), values, lines)


def _lookup(section: Optional[Mapping[str, Any]], key: Key) -> Tuple[bool, Any]:
    node: Any = section or {}
    for part in key:
        if not isinstance(node, Mapping) or part not in node:
            return False, None
        node = node[part]
    return True, node


def plan_layer_edit(text: str, module_id: str, ops: Sequence[PatchOp], *, schema: Any, layer: str,
                    file: str = "<string>") -> LayerEditPlan:
    """Apply ``ops`` (``("set", key, value)`` / ``("unset", key, None)``) to ``text`` in memory, in order.

    Nothing is read or written. An operation that is refused or makes the section invalid is skipped and
    reported in ``issues``; the others are applied. Raises :class:`ConfigError` if ``text`` itself is invalid.
    """
    _check_layer(layer)
    module = _schema_for(module_id, schema, None)
    if text.startswith(_BOM):
        text = text[1:]
    section, _index = _read_layer(layer, file, text, module_id)
    base = text if section is not None else f"schema_version = {CONFIG_FILE_VERSION}\n" + text
    current = base
    issues: List[ConfigError] = []
    keys: List[Key] = []
    for op in ops:
        name: Any = None
        try:
            kind, name, value = op
            if kind not in ("set", "unset"):
                raise ConfigError("CONFIG_EDIT_REFUSED", f"unknown operation {kind!r}", layer=layer, file=file,
                                  key=_dotted(_split_key(name)))
            leaf = module.leaf(name)
            edit_path = (module_id,) + leaf.key
            if kind == "unset":
                new_text = toml_edit.unset_value(current, edit_path, source=file)
            else:
                if leaf.secret and not (isinstance(value, str) and is_secret_ref(value)):
                    raise ConfigError("SECRET_REF_INVALID", "not a secret reference of the form <scheme>://<name> "
                                      "(value redacted)", layer=layer, file=file, key=_dotted(leaf.key))
                new_text = toml_edit.set_value(current, edit_path, value, source=file)
            new_section, new_index = _read_layer(layer, file, new_text, module_id)
            _State(module).apply_section(layer, new_section or {}, file=file, index=new_index,
                                         prefix=(module_id,))
        except toml_edit.TomlEditError as exc:
            issues.append(_EditRefused("CONFIG_EDIT_REFUSED", str(exc), layer=layer, file=file,
                                       key=_dotted(_split_key(name)) if isinstance(name, (str, tuple, list)) else None))
        except ConfigError as exc:
            if exc.layer is None:
                exc.layer = layer
            issues.append(exc)
        except (TypeError, ValueError) as exc:
            issues.append(ConfigError("CONFIG_EDIT_REFUSED", f"malformed operation: {exc}", layer=layer, file=file))
        else:
            current = new_text
            keys.append(leaf.key)
    reference = base if section is None else text
    changed = current != reference
    text_after = current if changed else text
    final_section = _read_layer(layer, file, text_after, module_id)[0]
    before: Dict[str, Any] = {}
    after: Dict[str, Any] = {}
    for key in keys:
        for source, target in ((section, before), (final_section, after)):
            found, value = _lookup(source, key)
            if found:
                target[_dotted(key)] = copy.deepcopy(value)
    return LayerEditPlan(text, text_after, changed, before, after, tuple(issues))


@contextmanager
def layer_lock(path: PathLike, *, timeout_s: float = 5.0) -> Iterator[None]:
    """Hold an exclusive ``flock`` on ``<realpath of path>.lock`` (a file next to the layer, never deleted).

    The lock is on a neighbour because ``os.replace`` gives the layer file a new inode. Polls every 50 ms and
    raises ``ConfigError('CONFIG_LOCKED')`` after ``timeout_s``.
    """
    import fcntl

    target = Path(os.path.realpath(path))
    lock_file = str(target) + ".lock"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_file, os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0), 0o600)
    except OSError as exc:
        raise ConfigError("CONFIG_FILE_INVALID", f"cannot open the lock file: {exc.strerror or 'error'}",
                          file=lock_file) from None
    try:
        deadline = time.monotonic() + max(timeout_s, 0.0)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ConfigError("CONFIG_LOCKED", f"another writer holds the lock of this file "
                                      f"(waited {timeout_s:g} s); try again", file=str(target)) from None
                time.sleep(_LOCK_POLL_S)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


def _verify_written(layer: str, target: Path, file: str, module: ModuleSchema, module_id: str,
                    expected: bytes) -> bool:
    try:
        data = target.read_bytes()
        if data != expected:
            return False
        section, index = _read_layer(layer, file, _decode(layer, data, file), module_id)
        _State(module).apply_section(layer, section or {}, file=file, index=index, prefix=(module_id,))
    except (OSError, ConfigError):
        return False
    return True


def apply_layer_patch(path: PathLike, module_id: str, ops: Sequence[PatchOp], *, schema: Any, layer: str,
                      expected_revision: Optional[str] = None, lock_timeout_s: float = 5.0,
                      project: Optional[PathLike] = None, env: Optional[Mapping[str, str]] = None,
                      home: Optional[PathLike] = None) -> EditResult:
    """Write ``ops`` into a layer file: the one way aicore writes a layer.

    Under :func:`layer_lock`: read the bytes, compare ``expected_revision`` (if given) with their revision
    (``CONFIG_REVISION_CONFLICT`` and nothing written otherwise), plan the edit (the first issue is raised),
    back up the file, replace it atomically, then read it again: bytes that differ from what was written or an
    invalid section restore the old file (a new file is removed) and raise ``CONFIG_FILE_INVALID``.
    Comments are kept; a symlink is followed so the link stays. Without changes nothing is written.
    """
    _check_layer(layer)
    module = _schema_for(module_id, schema, None)
    target = Path(os.path.realpath(path))
    file = str(path)
    if layer == "machine" and not target.parent.exists():  # the lock file lives next to the layer file
        ensure_dir(target.parent)
    with layer_lock(target, timeout_s=lock_timeout_s):
        existed, data = _read_bytes(layer, target, file)
        revision = layer_revision(data)
        if expected_revision is not None and expected_revision != revision:
            raise ConfigError("CONFIG_REVISION_CONFLICT", f"the file changed since revision {expected_revision}",
                              layer=layer, file=file)
        plan = plan_layer_edit(_decode(layer, data, file), module_id, ops, schema=module, layer=layer, file=file)
        if plan.issues:
            raise plan.issues[0]
        if not plan.changed:
            return EditResult(False, None, revision)
        saved = backup(path, project=project, env=env, home=home) if existed else None
        mode = stat.S_IMODE(target.stat().st_mode) if existed else None
        written = plan.text_after.encode("utf-8")
        _io.atomic_write_text(target, plan.text_after, mode=mode)
        if not _verify_written(layer, target, file, module, module_id, written):
            if existed:
                _io.durable_replace(target, saved.read_bytes() if saved is not None else data, mode=mode)
            else:
                target.unlink()
            raise ConfigError("CONFIG_FILE_INVALID", "the file read back differs from what was written or is "
                              "invalid; the previous content was restored", layer=layer, file=file)
        return EditResult(True, saved, layer_revision(written))


def edit_layer_file(path: PathLike, module_id: str, key: Union[str, Iterable[str]], value: Any = None, *,
                    schema: Any, layer: str = "machine", remove: bool = False,
                    project: Optional[PathLike] = None, env: Optional[Mapping[str, str]] = None,
                    home: Optional[PathLike] = None) -> EditResult:
    """Set (or, with ``remove``, delete) one key in a layer file, keeping its comments.

    One operation of :func:`apply_layer_patch` (so under the layer lock, without a revision check): the key
    is checked against the module schema (unknown key, type, range, forbidden layer), the old file is backed
    up with :func:`aicore.state.backup` and replaced atomically. On any error the file is left untouched.
    A missing or empty file is created with ``schema_version``. ``value`` is typed (use :func:`parse_value`
    for text). A symlink is followed, so the link stays. Raises :class:`ConfigError`.
    """
    name = key if isinstance(key, str) else ".".join(key)
    op: PatchOp = ("unset", name, None) if remove else ("set", name, value)
    return apply_layer_patch(path, module_id, [op], schema=schema, layer=layer, project=project, env=env,
                             home=home)
