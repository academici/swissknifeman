"""Closed-profile JSON Schema validator (stdlib only).

The one validator of the shared contracts. It supports exactly the keywords in ``SUPPORTED_KEYWORDS`` and the
annotations in ``ANNOTATIONS`` (accepted, never evaluated); any other keyword in a schema file fails closed
with ``SchemaProfileError`` at load time. Validation collects every issue instead of stopping at the first
one. ``load_contract`` loads one contract directory ``<contract>/v<N>/`` of the foundation schemas.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any, Iterator, NamedTuple

DIALECT = "https://json-schema.org/draft/2020-12/schema"
CONTRACT_URN_PREFIX = "urn:swissknifeman:aicore:"
ERROR_CODES = ("type", "enum", "const", "required", "additional", "pattern", "min_items", "unique",
               "min_length", "one_of", "ref", "minimum", "maximum", "property_name")
SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum", "const", "properties",
    "required", "additionalProperties", "items", "minItems", "uniqueItems", "minLength", "pattern", "oneOf",
    "default", "minimum", "maximum", "patternProperties", "propertyNames",
})
# Keywords a ``propertyNames`` schema may use: a name is a string, so only string checks apply.
_PROPERTY_NAME_KEYWORDS = frozenset({"type", "pattern", "minLength", "description", "enum"})
# Annotations of module configuration schemas: the validator accepts them and ignores them. Any other
# ``x-*`` keyword is outside the profile.
ANNOTATIONS = frozenset({"x-skm-secret", "x-skm-layers"})
_VERSION_DIR = re.compile(r"v[1-9][0-9]*")
_TYPE_NAMES = frozenset({"null", "boolean", "integer", "number", "string", "array", "object"})
_cache: dict[tuple[Path, str, tuple[str, ...], str, tuple[Path, ...]], "Registry"] = {}
_CONTRACT_REF = re.compile(r"([a-z][a-z0-9-]*):(v[1-9][0-9]*)")
_SET_ID = re.compile(r"(.+:)([a-z][a-z0-9-]*):(v[1-9][0-9]*)")
_FOUNDATION_SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"


class SchemaProfileError(ValueError):
    """A schema file leaves the closed profile, or an unknown schema kind was requested."""


class RefError(LookupError):
    """A ``$ref`` that the registry cannot resolve."""


class ValidationIssue(NamedTuple):
    path: str  # JSON pointer such as "/reads/2/path"; "" is the document root
    code: str
    message: str


class Registry:
    """Loaded schemas by ``$id``; read-only after construction."""

    def __init__(self, schemas: dict[str, dict], *, urn_prefix: str, kinds: tuple[str, ...], version: str = "v1"):
        self._schemas = schemas
        self.urn_prefix = urn_prefix
        self.kinds = tuple(kinds)
        self.version = version

    def for_kind(self, kind: str) -> tuple[dict, str]:
        schema_id = f"{self.urn_prefix}{kind}:{self.version}"
        if kind not in self.kinds or schema_id not in self._schemas:
            raise SchemaProfileError(f"unknown schema kind: {kind!r}")
        return self._schemas[schema_id], schema_id

    def resolve(self, ref: str, base_id: str) -> tuple[dict, str]:
        """Resolve ``#/$defs/x`` or ``<id>#/$defs/x``; return the node and the id of its owning schema."""
        document, _, fragment = ref.partition("#")
        owner = document or base_id
        node: Any = self._schemas.get(owner)
        if node is None:
            raise RefError(f"unknown schema {owner!r} in $ref {ref!r}")
        if fragment:
            if not fragment.startswith("/$defs/") or fragment.count("/") != 2:
                raise RefError(f"unsupported $ref fragment in {ref!r}")
            node = node.get("$defs", {}).get(fragment[len("/$defs/"):])
            if not isinstance(node, dict):
                raise RefError(f"$ref {ref!r} does not resolve")
        return node, owner


def load_registry(schema_dir: Path, *, urn_prefix: str, kinds: tuple[str, ...], version: str = "v1",
                  extra_dirs: tuple[Path, ...] = ()) -> Registry:
    """Load and profile-check schemas; cache by directory and registry parameters.

    ``version`` is the suffix of the ``$id`` of every kind (``<urn_prefix><kind>:<version>``). The schemas of
    ``extra_dirs`` join the registry for ``$ref`` resolution only; ``kinds`` names the schemas to validate.
    """
    directory = Path(schema_dir).resolve()
    extras = tuple(Path(extra).resolve() for extra in extra_dirs)
    key = (directory, urn_prefix, tuple(kinds), version, extras)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    schemas = _read_schemas(directory)
    for extra in extras:
        for schema_id, schema in _read_schemas(extra).items():
            if schema_id in schemas:
                raise SchemaProfileError(f"{extra}: duplicate $id {schema_id!r}")
            schemas[schema_id] = schema
    registry = Registry(schemas, urn_prefix=urn_prefix, kinds=tuple(kinds), version=version)
    _cache[key] = registry
    return registry


def _read_schemas(directory: Path) -> dict[str, dict]:
    schemas: dict[str, dict] = {}
    for path in sorted(directory.glob("*.schema.json")):
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
        raise SchemaProfileError(f"no *.schema.json files in {directory}")
    return schemas


def load_schema_file(path: Path, *, urn_prefix: str, kind: str, version: str = "v1") -> Registry:
    """Load and profile-check one schema file whose ``$id`` must be ``<urn_prefix><kind>:<version>``.

    For schemas that live outside the foundation contracts (a module's config schema). Not cached.
    """
    path = Path(path)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SchemaProfileError(f"{path.name}: cannot load schema: {exc}") from exc
    _check_profile(schema, path.name, "", root=True)
    schema_id = f"{urn_prefix}{kind}:{version}"
    if schema.get("$id") != schema_id:
        raise SchemaProfileError(f"{path.name}: $id must be {schema_id!r}, got {schema.get('$id')!r}")
    return Registry({schema_id: schema}, urn_prefix=urn_prefix, kinds=(kind,), version=version)


def load_contract(contract_dir: Path, *, urn_prefix: str = CONTRACT_URN_PREFIX,
                  foundation: Path | None = None) -> tuple[Registry, str]:
    """Load one contract directory ``<contract>/v<N>/``; return its registry and its kind.

    The kind is the stem of the single ``<kind>.schema.json`` file and must equal the contract name; the
    ``$id`` must be ``<urn_prefix><kind>:v<N>`` for the version ``v<N>`` named by the directory. ``foundation``
    is the directory of the foundation contracts that a reference may reach when they are not beside this one
    (default: the schemas of aicore itself).
    """
    directory = Path(contract_dir).resolve()
    version, kind = directory.name, directory.parent.name
    if not _VERSION_DIR.fullmatch(version):
        raise SchemaProfileError(f"{directory}: directory name must be v<N>, got {version!r}")
    files = sorted(directory.glob("*.schema.json"))
    if [path.name for path in files] != [f"{kind}.schema.json"]:
        raise SchemaProfileError(f"{directory}: expected exactly {kind}.schema.json, found "
                                 f"{[path.name for path in files]}")
    extras = _referenced_contract_dirs(directory, urn_prefix, foundation)
    registry = load_registry(directory, urn_prefix=urn_prefix, kinds=(kind,), version=version, extra_dirs=extras)
    registry.for_kind(kind)  # raises when the $id does not match the directory
    return registry, kind


def load_contract_set(contract_dir: Path, *, foundation: Path | None = None) -> tuple[Registry, list[str]]:
    """Load a contract directory ``<contract>/v<N>/`` that holds several ``<kind>.schema.json`` documents.

    The kind of a document is the last segment of its ``$id``; every ``$id`` must be ``<prefix><kind>:v<N>`` for
    one ``<prefix>`` shared by the directory and for the version ``v<N>`` named by the directory. The file name is
    not read (it may spell the kind with dots). References to the foundation contracts resolve as in
    ``load_contract`` (including ``foundation``). Return the registry and the sorted kinds.
    """
    directory = Path(contract_dir).resolve()
    version = directory.name
    if not _VERSION_DIR.fullmatch(version):
        raise SchemaProfileError(f"{directory}: directory name must be v<N>, got {version!r}")
    schemas = _read_schemas(directory)
    prefix: str | None = None
    kinds: list[str] = []
    for schema_id in schemas:
        match = _SET_ID.fullmatch(schema_id)
        if match is None or match.group(3) != version:
            raise SchemaProfileError(f"{directory}: $id {schema_id!r} must be <prefix><kind>:{version}")
        if prefix is not None and match.group(1) != prefix:
            raise SchemaProfileError(f"{directory}: $id {schema_id!r} does not share the prefix {prefix!r}")
        prefix = match.group(1)
        kinds.append(match.group(2))
    kinds.sort()
    registry = load_registry(directory, urn_prefix=prefix or "", kinds=tuple(kinds), version=version,
                             extra_dirs=_referenced_contract_dirs(directory, CONTRACT_URN_PREFIX, foundation))
    for schema_id, document in schemas.items():
        for ref in _refs(document):
            try:
                registry.resolve(ref, schema_id)
            except RefError as exc:
                raise SchemaProfileError(f"{directory.parent.name}/{version}: unresolved reference {ref!r}: {exc}")
    return registry, kinds


def _referenced_contract_dirs(directory: Path, urn_prefix: str,
                              foundation: Path | None = None) -> tuple[Path, ...]:
    """Sibling contract directories that ``$ref`` values reach from ``directory``, transitively.

    A ``$ref`` to ``<urn_prefix><contract>:v<N>`` (with or without a fragment) names the directory
    ``<schemas>/<contract>/v<N>`` next to the one being loaded; for the foundation prefix a directory missing
    there is looked up in ``foundation`` (default: the schemas of aicore itself).
    """
    schemas_root = directory.parent.parent
    found: list[Path] = []
    pending = [directory]
    seen = {directory}
    while pending:
        current = pending.pop(0)
        current_schemas = _read_schemas(current)
        own_ids = set(current_schemas)
        for schema in current_schemas.values():
            for ref in _refs(schema):
                document = ref.partition("#")[0]
                if not document.startswith(urn_prefix) or document in own_ids:
                    continue
                match = _CONTRACT_REF.fullmatch(document[len(urn_prefix):])
                target = schemas_root / match.group(1) / match.group(2) if match else None
                if match and urn_prefix == CONTRACT_URN_PREFIX and not _has_schemas(target):
                    target = (foundation or _FOUNDATION_SCHEMAS) / match.group(1) / match.group(2)
                if target is None or not _has_schemas(target):
                    raise SchemaProfileError(f"{current.parent.name}/{current.name}: unresolved contract "
                                             f"reference {ref!r}")
                target = target.resolve()
                if target not in seen:
                    seen.add(target)
                    found.append(target)
                    pending.append(target)
    return tuple(found)


def _has_schemas(directory: Path | None) -> bool:
    return directory is not None and directory.is_dir() and any(directory.glob("*.schema.json"))


def _refs(node: Any) -> Iterator[str]:
    """Every ``$ref`` string in the schema nodes below ``node`` (keyword values that hold schemas only)."""
    if not isinstance(node, dict):
        return
    if isinstance(node.get("$ref"), str):
        yield node["$ref"]
    for keyword in ("properties", "$defs", "patternProperties"):
        for child in (node.get(keyword) or {}).values():
            yield from _refs(child)
    for keyword in ("items", "propertyNames"):
        yield from _refs(node.get(keyword))
    for child in node.get("oneOf") or ():
        yield from _refs(child)




def clear_registry_cache() -> None:
    _cache.clear()


def _check_profile(node: Any, where: str, pointer: str, *, root: bool = False) -> None:
    """Reject keywords outside the closed profile and malformed keyword values."""
    def fail(message: str) -> None:
        raise SchemaProfileError(f"{where}: {message} at {pointer or '/'}")

    if not isinstance(node, dict):
        fail("schema node must be an object")
    for keyword, value in node.items():
        if keyword not in SUPPORTED_KEYWORDS and keyword not in ANNOTATIONS:
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
        elif keyword == "x-skm-secret" and not isinstance(value, bool):
            fail("x-skm-secret must be a boolean")
        elif keyword == "x-skm-layers" and not (
                isinstance(value, list) and value and all(isinstance(n, str) and n for n in value)):
            fail("x-skm-layers must be a non-empty list of layer names")
        elif keyword == "pattern":
            try:
                _compile(value)
            except (re.error, TypeError) as exc:
                fail(f"invalid pattern {value!r}: {exc}")
        elif keyword == "$ref" and not isinstance(value, str):
            fail("$ref must be a string")
        elif keyword in ("properties", "$defs", "patternProperties"):
            if not isinstance(value, dict):
                fail(f"{keyword} must be an object")
            for name, child in value.items():
                if keyword == "patternProperties":
                    try:
                        _compile(name)
                    except re.error as exc:
                        fail(f"invalid pattern {name!r}: {exc}")
                _check_profile(child, where, f"{pointer}/{keyword}/{name}")
        elif keyword == "propertyNames":
            _check_profile(value, where, f"{pointer}/propertyNames")
            outside = sorted(set(value) - _PROPERTY_NAME_KEYWORDS)
            if outside:
                fail(f"propertyNames may only use {sorted(_PROPERTY_NAME_KEYWORDS)}, got {outside}")
            if value.get("type", "string") != "string":
                fail("propertyNames type must be \"string\": names are strings")
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


def validate(doc: object, kind: str, registry: Registry) -> list[ValidationIssue]:
    """Validate ``doc`` against the schema of ``kind``; return every issue found."""
    reg = registry
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
        matched, trials = 0, []
        for branch in branches:
            trial: list[ValidationIssue] = []
            _check(reg, branch, base, value, pointer, trial)
            matched += not trial
            trials.append((branch, trial))
        if matched != 1:
            add("one_of", f"matches {matched} of {len(branches)} oneOf branches, expected exactly 1"
                + (_closest(trials) if matched == 0 else ""))


def _closest(trials: list) -> str:
    """The issues of the branch that came nearest, so a reader learns which field and value to change rather than only
    that no branch matched (a branch that names the value's own keys wins a tie)."""
    def score(trial) -> tuple:
        branch, issues = trial
        return (len(issues), -len(branch.get("required", ()) or ()))
    branch, issues = min(trials, key=score)
    name = branch.get("description") or branch.get("title") or "the nearest branch"
    shown = "; ".join(issue.message for issue in issues[:3])
    return f"; {str(name).rstrip('.')}: {shown}" if shown else ""


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
    patterns = [(_compile(pattern), child) for pattern, child in schema.get("patternProperties", {}).items()]
    names_schema = schema.get("propertyNames")
    closed = schema.get("additionalProperties") is False
    for name, item in value.items():
        at = f"{pointer}/{_escape(name)}"
        if names_schema is not None:
            name_issues = validate_node(reg, names_schema, base, name)
            if name_issues:  # one issue per name: the first failed check says why
                add("property_name", f"property name {_short(name)} is not allowed: {name_issues[0].message[3:]}", at)
        covered = name in properties
        for regex, child in patterns:
            if regex.search(name) is not None:
                covered = True
                _check(reg, child, base, item, at, out)
        if closed and not covered:
            add("additional", f"unexpected property {name!r}", at)


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
