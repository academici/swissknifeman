"""The core of the closed-profile JSON Schema validator (stdlib only, Python 3.9+).

One implementation of the profile check and of validation. ``aicore.util.schema`` (registry, contract loading) and
the plan schema module of the planner (plan registry, extension slots) both build on it. The file is vendored byte
for byte into the planner by the hub script ``vendor-jsonschema-core.py`` (planner runs without aicore), so edit it
here only and run the script.

The profile supports exactly the keywords in ``SUPPORTED_KEYWORDS`` and the annotations in ``ANNOTATIONS`` (accepted,
never evaluated); any other keyword in a schema file fails closed with ``SchemaProfileError`` at load time.
Validation collects every issue instead of stopping at the first one. A registry is anything with
``resolve(ref, base_id) -> (node, owner_id)``; a ``RefError`` whose class sets ``issue_code`` is reported under that
code instead of ``ref`` (planner uses it for extension slots).
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, NamedTuple

DIALECT = "https://json-schema.org/draft/2020-12/schema"
ERROR_CODES = ("type", "enum", "const", "required", "additional", "pattern", "min_items", "unique",
               "min_length", "one_of", "ref", "minimum", "maximum", "property_name", "max_length", "max_items",
               "min_properties", "max_properties", "dependent_required", "not")
SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum", "const", "properties",
    "required", "additionalProperties", "items", "minItems", "uniqueItems", "minLength", "pattern", "oneOf",
    "default", "minimum", "maximum", "patternProperties", "propertyNames", "maxLength", "maxItems",
    "minProperties", "maxProperties", "dependentRequired", "not",
})
# Keywords a ``propertyNames`` schema may use: a name is a string, so only string checks apply.
_PROPERTY_NAME_KEYWORDS = frozenset({"type", "pattern", "minLength", "maxLength", "description", "enum"})
# Annotations of module configuration schemas: the validator accepts them and ignores them. Any other
# ``x-*`` keyword is outside the profile.
ANNOTATIONS = frozenset({"x-skm-secret", "x-skm-layers"})
_TYPE_NAMES = frozenset({"null", "boolean", "integer", "number", "string", "array", "object"})


class SchemaProfileError(ValueError):
    """A schema file leaves the closed profile, or an unknown schema kind was requested."""


class RefError(LookupError):
    """A ``$ref`` that the registry cannot resolve."""


class ValidationIssue(NamedTuple):
    path: str  # JSON pointer such as "/reads/2/path"; "" is the document root
    code: str
    message: str



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
        elif keyword in ("minItems", "minLength", "maxItems", "maxLength", "minProperties", "maxProperties") and not (
                isinstance(value, int) and not isinstance(value, bool) and value >= 0):
            fail(f"{keyword} must be a non-negative integer")
        elif keyword == "dependentRequired":
            if not (isinstance(value, dict) and all(
                    isinstance(names, list) and all(isinstance(n, str) for n in names) for names in value.values())):
                fail("dependentRequired must map a property name to a list of property names")
        elif keyword == "not":
            _check_profile(value, where, f"{pointer}/not")
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


def _anchor_end(pattern: str) -> str:
    """Rewrite every ``$`` that is an anchor into ``\\Z``: in Python ``$`` also matches before a final newline."""
    out: list[str] = []
    in_class = False
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            out.append(pattern[index:index + 2])
            index += 2
            continue
        if in_class:
            if char == "]":
                in_class = False
        elif char == "[":
            in_class = True
            out.append(char)
            index += 1
            if pattern[index:index + 1] == "^":
                out.append("^")
                index += 1
            if pattern[index:index + 1] == "]":
                out.append("\\]")
                index += 1
            continue
        elif char == "$":
            out.append(r"\Z")
            index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _compile(pattern: str) -> re.Pattern:
    """JSON Schema (ECMA-262) semantics: ASCII classes, and ``$`` only at the very end of the string."""
    return re.compile(_anchor_end(pattern), re.ASCII)



def validate_node(registry: Any, node: dict, base_id: str, value: object) -> list[ValidationIssue]:
    """Validate ``value`` against one schema node (for example a ``oneOf`` branch) owned by ``base_id``."""
    issues: list[ValidationIssue] = []
    _check(registry, node, base_id, value, "", issues)
    return issues


def _check(reg: Any, schema: dict, base: str, value: Any, pointer: str, out: list[ValidationIssue]) -> None:
    def add(code: str, message: str, at: str | None = None) -> None:
        location = pointer if at is None else at
        out.append(ValidationIssue(location, code, f"{location or '/'}: {message}"))

    if "$ref" in schema:
        try:
            target, owner = reg.resolve(schema["$ref"], base)
        except RefError as exc:
            add(getattr(exc, "issue_code", "ref"), str(exc))
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
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            add("max_length", f"string is longer than {schema['maxLength']}")
        pattern = schema.get("pattern")
        if pattern is not None and _compile(pattern).search(value) is None:
            add("pattern", f"{_short(value)} does not match pattern {pattern}")
    elif isinstance(value, list):
        _check_array(reg, schema, base, value, pointer, out, add)
    elif isinstance(value, dict):
        _check_object(reg, schema, base, value, pointer, out, add)
    if "not" in schema:
        trial_not: list[ValidationIssue] = []
        _check(reg, schema["not"], base, value, pointer, trial_not)
        if not trial_not:
            add("not", "must not match the schema of the \"not\" keyword")
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
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        add("max_items", f"array has more than {schema['maxItems']} items")
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
    if len(value) < schema.get("minProperties", 0):
        add("min_properties", f"object has fewer than {schema['minProperties']} properties")
    if "maxProperties" in schema and len(value) > schema["maxProperties"]:
        add("max_properties", f"object has more than {schema['maxProperties']} properties")
    for name, needed in schema.get("dependentRequired", {}).items():
        if name in value:
            for other in needed:
                if other not in value:
                    add("dependent_required", f"property {name!r} requires property {other!r}")
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
