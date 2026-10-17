"""Closed-profile JSON Schema validator for v4 plan documents (stdlib only).

Supports exactly the keywords in ``SUPPORTED_KEYWORDS``; any other keyword in a schema file fails
closed with ``SchemaProfileError`` at load time. Validation collects every issue instead of stopping at the
first one.

A ``$ref`` to an id under ``EXTENSION_PREFIX`` names an extension slot: the engine declares the field, a bridge
supplies its schema (``extends`` of ``bridge.json``, see ``extensions``). A slot without a supplier is an
``extension`` issue, never a crash.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any, NamedTuple

SCHEMA_URN_PREFIX = "urn:swissknifeman:task:plan:"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
KINDS = ("plan", "brief", "phase", "item", "unit", "decision", "log-event", "document", "snapshot", "envelope",
         "bridge", "check-evidence", "read-get", "read-list", "read-events", "read-artifact", "read-links",
         "read-neighborhood", "read-catalog", "read-commits", "read-ready", "read-followups", "read-plans")
ERROR_CODES = ("type", "enum", "const", "required", "additional", "pattern", "min_items", "unique",
               "min_length", "one_of", "ref", "minimum", "maximum")
EXTENSION_PREFIX = f"{SCHEMA_URN_PREFIX}extension:"
# Issue code of an extension slot without a usable supplier; engine-only, outside the shared closed profile.
EXTENSION_CODE = "extension"
SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum", "const", "properties",
    "required", "additionalProperties", "items", "minItems", "uniqueItems", "minLength", "pattern", "oneOf",
    "default", "minimum", "maximum",
})
_TYPE_NAMES = frozenset({"null", "boolean", "integer", "number", "string", "array", "object"})
_cache: dict[Path, "Registry"] = {}


class SchemaProfileError(ValueError):
    """A schema file leaves the closed profile, or an unknown schema kind was requested."""


class RefError(LookupError):
    """A ``$ref`` that the registry cannot resolve."""


class ExtensionUnavailable(RefError):
    """An extension slot that no bridge supplies (or whose supplied schema is unusable)."""


class ValidationIssue(NamedTuple):
    path: str  # JSON pointer such as "/reads/2/path"; "" is the document root
    code: str
    message: str


class Registry:
    """Loaded schemas by ``$id``; read-only after construction."""

    def __init__(self, schemas: dict[str, dict]):
        self._schemas = schemas

    def for_kind(self, kind: str) -> tuple[dict, str]:
        schema_id = f"{SCHEMA_URN_PREFIX}{kind}:v1"
        if kind not in KINDS or schema_id not in self._schemas:
            raise SchemaProfileError(f"unknown schema kind: {kind!r}")
        return self._schemas[schema_id], schema_id

    def resolve(self, ref: str, base_id: str) -> tuple[dict, str]:
        """Resolve ``#/$defs/x`` or ``<id>#/$defs/x``; return the node and the id of its owning schema."""
        document, _, fragment = ref.partition("#")
        owner = document or base_id
        node: Any = self._schemas.get(owner)
        if node is None and owner.startswith(EXTENSION_PREFIX):
            from . import extensions  # late: extensions reads bridge manifests, which are validated here
            node = extensions.schema_for(owner)
        if node is None:
            raise RefError(f"unknown schema {owner!r} in $ref {ref!r}")
        if fragment:
            if not fragment.startswith("/$defs/") or fragment.count("/") != 2:
                raise RefError(f"unsupported $ref fragment in {ref!r}")
            node = node.get("$defs", {}).get(fragment[len("/$defs/"):])
            if not isinstance(node, dict):
                raise RefError(f"$ref {ref!r} does not resolve")
        return node, owner


def default_schema_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "schemas" / "plan" / "v1"


def load_registry(schema_dir: Path | None = None) -> Registry:
    """Load and profile-check ``*.schema.json`` files; cached per directory path."""
    directory = Path(schema_dir) if schema_dir is not None else default_schema_dir()
    key = directory.resolve()
    cached = _cache.get(key)
    if cached is not None:
        return cached
    schemas: dict[str, dict] = {}
    for path in sorted(key.glob("*.schema.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SchemaProfileError(f"{path.name}: cannot load schema: {exc}") from exc
        _check_profile(schema, path.name, "", root=True)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise SchemaProfileError(f"{path.name}: missing $id")
        if schema_id in schemas:
            raise SchemaProfileError(f"{path.name}: duplicate $id {schema_id!r}")
        schemas[schema_id] = schema
    if not schemas:
        raise SchemaProfileError(f"no *.schema.json files in {key}")
    registry = Registry(schemas)
    _cache[key] = registry
    return registry


def clear_registry_cache() -> None:
    _cache.clear()
    from . import extensions
    extensions.clear_cache()


def _check_profile(node: Any, where: str, pointer: str, *, root: bool = False) -> None:
    """Reject keywords outside the closed profile and malformed keyword values."""
    def fail(message: str) -> None:
        raise SchemaProfileError(f"{where}: {message} at {pointer or '/'}")

    if not isinstance(node, dict):
        fail("schema node must be an object")
    for keyword, value in node.items():
        if keyword not in SUPPORTED_KEYWORDS:
            fail(f"unsupported keyword {keyword!r}")
        if keyword == "$schema" and (not root or value != DIALECT):
            fail(f"$schema must be {DIALECT!r} on the root only")
        elif keyword == "additionalProperties" and value is not False:
            fail("additionalProperties may only be false")
        elif keyword == "type":
            names = [value] if isinstance(value, str) else value
            if not isinstance(names, list) or not names or any(n not in _TYPE_NAMES for n in names):
                fail(f"invalid type {value!r}")
        elif keyword == "required" and not (isinstance(value, list) and all(isinstance(n, str) for n in value)):
            fail("required must be a list of strings")
        elif keyword == "enum" and not (isinstance(value, list) and value):
            fail("enum must be a non-empty list")
        elif keyword in ("minItems", "minLength") and not (
                isinstance(value, int) and not isinstance(value, bool) and value >= 0):
            fail(f"{keyword} must be a non-negative integer")
        elif keyword == "uniqueItems" and not isinstance(value, bool):
            fail("uniqueItems must be a boolean")
        elif keyword in ("minimum", "maximum") and not (
                isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)):
            fail(f"{keyword} must be a finite number")
        elif keyword == "pattern":
            try:
                _compile(value)
            except (re.error, TypeError) as exc:
                fail(f"invalid pattern {value!r}: {exc}")
        elif keyword == "$ref" and not isinstance(value, str):
            fail("$ref must be a string")
        elif keyword in ("properties", "$defs"):
            if not isinstance(value, dict):
                fail(f"{keyword} must be an object")
            for name, child in value.items():
                _check_profile(child, where, f"{pointer}/{keyword}/{name}")
        elif keyword == "items":
            _check_profile(value, where, f"{pointer}/items")
        elif keyword == "oneOf":
            if not isinstance(value, list) or not value:
                fail("oneOf must be a non-empty list")
            for index, child in enumerate(value):
                _check_profile(child, where, f"{pointer}/oneOf/{index}")


def _compile(pattern: str) -> re.Pattern:
    """JSON Schema (ECMA-262) semantics: ASCII classes, and ``$`` only at the very end of the string."""
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        pattern = pattern[:-1] + r"\Z"
    return re.compile(pattern, re.ASCII)


def validate(doc: object, kind: str, registry: Registry | None = None) -> list[ValidationIssue]:
    """Validate ``doc`` against the schema of ``kind``; return every issue found."""
    reg = registry if registry is not None else load_registry()
    schema, schema_id = reg.for_kind(kind)
    issues: list[ValidationIssue] = []
    _check(reg, schema, schema_id, doc, "", issues)
    return issues


def validate_node(registry: Registry, node: dict, base_id: str, value: object) -> list[ValidationIssue]:
    """Validate ``value`` against one schema node (for example a ``oneOf`` branch) owned by ``base_id``."""
    issues: list[ValidationIssue] = []
    _check(registry, node, base_id, value, "", issues)
    return issues


def _check(reg: Registry, schema: dict, base: str, value: Any, pointer: str, out: list[ValidationIssue]) -> None:
    def add(code: str, message: str, at: str | None = None) -> None:
        location = pointer if at is None else at
        out.append(ValidationIssue(location, code, f"{location or '/'}: {message}"))

    if "$ref" in schema:
        try:
            target, owner = reg.resolve(schema["$ref"], base)
        except ExtensionUnavailable as exc:
            add(EXTENSION_CODE, str(exc))
        except RefError as exc:
            add("ref", str(exc))
        else:
            _check(reg, target, owner, value, pointer, out)
    names = schema.get("type")
    if names is not None:
        names = [names] if isinstance(names, str) else names
        if not any(_is_type(value, n) for n in names):
            add("type", f"expected {' or '.join(names)}, got {_type_name(value)}")
            return
    if "enum" in schema and not any(_equal(value, option) for option in schema["enum"]):
        add("enum", "must be one of " + ", ".join(json.dumps(o, ensure_ascii=False) for o in schema["enum"]))
    if "const" in schema and not _equal(value, schema["const"]):
        add("const", f"must equal {json.dumps(schema['const'], ensure_ascii=False)}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            add("minimum", f"{value} is less than the minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            add("maximum", f"{value} is greater than the maximum {schema['maximum']}")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            add("min_length", f"string is shorter than {schema['minLength']}")
        pattern = schema.get("pattern")
        if pattern is not None and _compile(pattern).search(value) is None:
            add("pattern", f"{_short(value)} does not match pattern {pattern}")
    elif isinstance(value, list):
        _check_array(reg, schema, base, value, pointer, out, add)
    elif isinstance(value, dict):
        _check_object(reg, schema, base, value, pointer, out, add)
    branches = schema.get("oneOf")
    if branches is not None:
        matched = 0
        for branch in branches:
            trial: list[ValidationIssue] = []
            _check(reg, branch, base, value, pointer, trial)
            matched += not trial
        if matched != 1:
            add("one_of", f"matches {matched} of {len(branches)} oneOf branches, expected exactly 1")


def _check_array(reg, schema, base, value, pointer, out, add) -> None:
    if len(value) < schema.get("minItems", 0):
        add("min_items", f"array has fewer than {schema['minItems']} items")
    if schema.get("uniqueItems"):
        for j, later in enumerate(value):
            first = next((i for i in range(j) if _equal(value[i], later)), None)
            if first is not None:
                add("unique", f"items {first} and {j} are equal")
                break
    item_schema = schema.get("items")
    if item_schema is not None:
        for index, element in enumerate(value):
            _check(reg, item_schema, base, element, f"{pointer}/{index}", out)


def _check_object(reg, schema, base, value, pointer, out, add) -> None:
    for name in schema.get("required", ()):
        if name not in value:
            add("required", f"missing required property {name!r}")
    properties = schema.get("properties", {})
    for name, child in properties.items():
        if name in value:
            _check(reg, child, base, value[name], f"{pointer}/{_escape(name)}", out)
    if schema.get("additionalProperties") is False:
        for name in value:
            if name not in properties:
                add("additional", f"unexpected property {name!r}", f"{pointer}/{_escape(name)}")


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _is_type(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    return isinstance(value, dict)  # "object"


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    return {int: "integer", float: "number", str: "string", list: "array", dict: "object"}.get(
        type(value), type(value).__name__)


def _equal(a: Any, b: Any) -> bool:
    """JSON equality: booleans never equal numbers; ints and floats compare by value."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def _short(value: str) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + '..."'
