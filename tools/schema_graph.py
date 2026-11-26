"""Offline schema graphs and exact JSON encoding shared by the compatibility checker."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urljoin

from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

LOCK_PATH = Path("src/skm/schemas/schema-lock.json")
LOCK_URN = "urn:skm:tooling:schema-lock:v1"
ANNOTATIONS = {"title", "description", "default", "examples", "$comment", "deprecated"}
MAPPINGS = {"properties", "$defs", "patternProperties", "dependentSchemas"}
SINGLE = {"items", "additionalProperties", "contains", "propertyNames", "if", "then", "else", "not"}
LISTS = {"oneOf", "anyOf", "allOf", "prefixItems"}
# The int-to-text limit of an interpreter is 0 (off) or at least 640 digits
# (sys.int_info.str_digits_check_threshold). The registry admits wider integer literals, so integers from
# _WIDE_INT up are written here in parts of _INT_PART_DIGITS digits and read by the registry's bounded
# policy: the lock, its digests and the messages hold the exact digits whatever the limit is.
_WIDE_INT = 10**640
_INT_PART_DIGITS = 512
_MARKERS = re.compile(r"skm-wide-int-([0-9]+)-")


class RefError(ValueError):
    """A reference cannot be resolved entirely within the local graph."""


def digits(number: int) -> str:
    """The decimal text of ``number``, also past the interpreter's int-to-text limit."""
    magnitude, parts = abs(number), []
    while magnitude >= 10**_INT_PART_DIGITS:
        magnitude, part = divmod(magnitude, 10**_INT_PART_DIGITS)
        parts.append(f"{part:0{_INT_PART_DIGITS}d}")
    return ("-" if number < 0 else "") + str(magnitude) + "".join(reversed(parts))


def loads(text: str) -> Any:
    """JSON text whose integer tokens are read as the schema registry reads them: past an enabled
    int-to-text limit only up to the registry's bounded width, so a lock admits what a schema file admits."""
    from skm.platform.schema.registry import _integer  # pyright: ignore[reportPrivateUsage]

    return json.loads(text, parse_int=_integer)


def _mark(value: Any, marker: str, wide: list[int]) -> Any:
    """A copy of ``value`` with each wide integer replaced by ``marker`` and its index in ``wide``.

    The copy is built with an explicit stack: ``json.dumps`` writes deeper nesting than Python calls reach.
    """
    root = [value]
    entered: set[int] = set()
    pending: list[tuple[Any, Any]] = [(root, 0)]
    while pending:
        holder, slot = pending.pop()
        if holder is None:  # every child of the container ``slot`` is copied
            entered.discard(slot)
            continue
        node = holder[slot]
        if isinstance(node, (dict, list, tuple)):
            if id(node) in entered:
                raise ValueError("Circular reference detected")
            entered.add(id(node))
            clone = dict(node) if isinstance(node, dict) else list(node)
            holder[slot] = clone
            pending.append((None, id(node)))
            pending.extend((clone, key) for key in (clone if isinstance(clone, dict) else range(len(clone))))
        elif isinstance(node, int) and not isinstance(node, bool) and not -_WIDE_INT < node < _WIDE_INT:
            wide.append(node)
            holder[slot] = f"{marker}{len(wide) - 1}"
    return root[0]


def dumps(value: Any, **options: Any) -> str:
    """``json.dumps`` that writes every integer with its exact digits, also past the int-to-text limit.

    A value ``json.dumps`` can write is written by it alone. Otherwise each wide integer is rendered as a
    marker string first and its digits replace the quoted marker. A marker is used only when the text holds
    no other occurrence of it, so no string of ``value`` is touched: when the first marker occurs elsewhere,
    the second is one the first text does not hold at all, so the value is written at most three times.
    """
    if options.get("indent") == 2 and isinstance(value, dict) and value.get("schema") == LOCK_URN:
        options = {**options, "indent": None, "separators": (",", ": ")}
    try:
        return json.dumps(value, **options)
    except ValueError:  # an integer past the int-to-text limit; any other error recurs below
        pass
    marker, wide = "skm-wide-int-0-", list[int]()
    text = json.dumps(_mark(value, marker, wide), **options)
    if text.count(marker) != len(wide):
        taken = set(_MARKERS.findall(text))
        marker = f"skm-wide-int-{min(n for n in range(len(taken) + 1) if str(n) not in taken)}-"
        wide.clear()
        text = json.dumps(_mark(value, marker, wide), **options)
    parts = [digits(number) for number in wide]
    return re.sub(f'"{marker}([0-9]+)"', lambda match: parts[int(match[1])], text)


def canonical(value: Any) -> str:
    return dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def schema_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def normalize(node: Any) -> Any:
    """Remove annotations at schema positions; property names and literal values survive."""
    if not isinstance(node, dict):
        return copy.deepcopy(node)
    result = {}
    for key, value in node.items():
        if key in ANNOTATIONS or key.startswith("x-skm"):
            continue
        if key in MAPPINGS:
            result[key] = {name: normalize(child) for name, child in value.items()}
        elif key in SINGLE:
            result[key] = normalize(value)
        elif key in LISTS:
            result[key] = [normalize(child) for child in value]
        else:
            result[key] = copy.deepcopy(value)
    return result


def equal(first: Any, second: Any) -> bool:
    # JSON booleans differ from numbers; 1 and 1.0 denote the same JSON value.
    if isinstance(first, bool) or isinstance(second, bool):
        return type(first) is type(second) and first == second
    if isinstance(first, dict) and isinstance(second, dict):
        return first.keys() == second.keys() and all(equal(v, second[k]) for k, v in first.items())
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(equal(a, b) for a, b in zip(first, second, strict=True))
    return first == second


compile_pattern = re.compile


class Graph:
    """An isolated offline ref graph for one comparison side, including nested resources."""

    def __init__(self, documents: Mapping[str, Any]):
        self.documents = {urn: self._rebase(normalize(doc), urn) for urn, doc in documents.items()}
        self.registry: Registry[Any] = (
            Registry()
            .with_resources(
                (urn, Resource.from_contents(doc, default_specification=DRAFT202012))
                for urn, doc in self.documents.items()
            )
            .crawl()
        )

    def _rebase(self, node: Any, base: str) -> Any:
        if not isinstance(node, dict):
            return node
        base = urljoin(base, node.get("$id", "")) or base
        result = {}
        for key, value in node.items():
            if key == "$ref":
                if not value.startswith(("#", "urn:skm:")):
                    raise RefError(f"reference {value!r} must be local or urn:skm:")
                result[key] = base + value if value.startswith("#") else value
            elif key in MAPPINGS:
                result[key] = {name: self._rebase(child, base) for name, child in value.items()}
            elif key in SINGLE:
                result[key] = self._rebase(value, base)
            elif key in LISTS:
                result[key] = [self._rebase(child, base) for child in value]
            else:
                result[key] = value
        return result

    def resolve(self, ref: str, base: str) -> tuple[Any, str]:
        if not ref.startswith(("#", "urn:skm:")):
            raise RefError(f"reference {ref!r} must be local or urn:skm:")
        try:
            target = self.registry.resolver(base_uri=base).lookup(ref).contents
        except Unresolvable as error:
            raise RefError(f"unresolved reference {ref!r} in {base}") from error
        if not isinstance(target, (dict, bool)):
            raise RefError(f"reference {ref!r} does not point to a schema")
        return target, ref.partition("#")[0] or base


# rule -> whether the change breaks documents that were valid by the old schema
RULES: dict[str, bool] = {
    "schema-widened": False,
    "constraint-changed": True,
    "property-removed": True,
    "property-added": False,
    "required-added": True,
    "required-removed": False,
    "enum-narrowed": True,
    "enum-widened": False,
    "enum-added": True,
    "type-changed": True,
    "type-widened": False,
    "const-changed": True,
    "pattern-changed": True,
    "pattern-removed": False,
    "bound-tightened": True,
    "bound-relaxed": False,
    "additional-closed": True,
    "pattern-property-removed": True,
    # non-breaking only when the old object was closed and no existing name can meet the new pattern;
    # otherwise the change is reported as breaking (see _Comparer._objects)
    "pattern-property-added": False,
    "property-names-changed": True,
    "unique-added": True,
    "not-changed": True,
    "dependent-required-added": True,
    "oneof-changed": True,
    "ref-changed": False,
    "ref-sibling-conflict": True,
    # set-level rules of contracts that hold several documents (see _compare_set)
    "kind-removed": True,
    "kind-added": False,
}

BOUNDS = (
    ("minLength", 0, "min"),
    ("minItems", 0, "min"),
    ("minimum", None, "min"),
    ("maximum", None, "max"),
    ("maxLength", None, "max"),
    ("maxItems", None, "max"),
    ("minProperties", 0, "min"),
    ("maxProperties", None, "max"),
    ("exclusiveMinimum", None, "min"),
    ("exclusiveMaximum", None, "max"),
)


class Change(NamedTuple):
    path: str  # JSON pointer into the schema, "" is the root
    rule: str  # a key of RULES
    breaking: bool
    message: str


DIRECTIONS = ("input", "output", "both")
