"""Bounded validation of a user-supplied Draft 2020-12 JSON Schema."""

import json
import os
import re
import stat
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlsplit

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012, Schema

__all__ = ["load_user_json_schema", "validate_user_json"]

_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_DEFAULT_MAX_SCHEMA_BYTES = 262_144
_ARRAY_INDEX = re.compile(r"0|[1-9][0-9]*")
# urlsplit strips some control characters and accepts malformed percent escapes.
_INVALID_URI_TOKEN = re.compile(r"[^A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]|%(?![0-9A-Fa-f]{2})")


def _read_schema_bytes(path: Path, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise ValueError("schema byte limit must be positive")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("user JSON Schema must be a regular file")
            if info.st_size > max_bytes:
                raise ValueError("user JSON Schema exceeds the byte limit")
            data = source.read(max_bytes + 1)
    except OSError:
        raise ValueError("cannot read user JSON Schema") from None
    if len(data) > max_bytes:
        raise ValueError("user JSON Schema exceeds the byte limit")
    return data


def _check_pointer_indices(document: Schema, ref: str) -> None:
    # Referencing casts array tokens with int(), which also accepts signs and leading zeros.
    current: object = document
    for token in unquote(ref[2:]).split("/"):
        if isinstance(current, list):
            if _ARRAY_INDEX.fullmatch(token) is None:
                raise ValueError("invalid JSON Pointer array index")
            current = cast("list[object]", current)[int(token)]
        elif isinstance(current, dict):
            key = token.replace("~1", "/").replace("~0", "~")
            current = cast("dict[str, object]", current)[key]
        else:
            raise ValueError("JSON Pointer must traverse objects or arrays")


def _check_user_references(schema: Schema) -> None:
    root = DRAFT202012.create_resource(schema)
    pending = [(root, Registry[Schema]().resolver_with_root(root))]
    checked: set[int] = set()
    while pending:
        resource, resolver = pending.pop()
        node = resource.contents
        if isinstance(node, bool) or id(node) in checked:
            continue
        checked.add(id(node))
        if node.get("$schema", _DIALECT) not in (_DIALECT, _DIALECT + "#"):
            raise ValueError("user JSON Schema must use Draft 2020-12")
        identifier = node.get("$id")
        if isinstance(identifier, str):
            if _INVALID_URI_TOKEN.search(identifier):
                raise ValueError("invalid user JSON Schema $id")
            try:
                urlsplit(identifier)
            except ValueError:
                raise ValueError("invalid user JSON Schema $id") from None
        for keyword in ("$ref", "$dynamicRef"):
            ref = node.get(keyword)
            if not isinstance(ref, str):
                continue
            if ref and not ref.startswith("#"):
                raise ValueError("external JSON Schema references are forbidden")
            try:
                if ref.startswith("#/"):
                    _check_pointer_indices(resolver.lookup("#").contents, ref)
                target = resolver.lookup(ref)
            except (Unresolvable, AttributeError, LookupError, TypeError, ValueError):
                raise ValueError("unresolvable user JSON Schema reference") from None
            if id(target.contents) not in checked:
                # A pointer can reach data outside schema keywords, where the metaschema
                # has no rules for the contents until they are used as a schema.
                Draft202012Validator.check_schema(target.contents)
                pending.append((DRAFT202012.create_resource(target.contents), target.resolver))
        try:
            pending.extend((child, resolver.in_subresource(child)) for child in resource.subresources())
        except ValueError:
            raise ValueError("invalid user JSON Schema") from None


def load_user_json_schema(
    schema_path: Path, *, max_schema_bytes: int = _DEFAULT_MAX_SCHEMA_BYTES
) -> dict[str, Any] | bool:
    """Return the checked schema with no external reference or dialect resolution."""
    data = _read_schema_bytes(schema_path, max_schema_bytes)
    try:
        schema: object = json.loads(data)
    except (ValueError, RecursionError):
        raise ValueError("invalid user JSON Schema JSON") from None
    if not isinstance(schema, (dict, bool)):
        raise ValueError("user JSON Schema must be an object or boolean")
    checked = cast("dict[str, Any] | bool", schema)
    try:
        Draft202012Validator.check_schema(checked)
        json.dumps(checked, allow_nan=False)
    except (SchemaError, AttributeError, TypeError, ValueError, RecursionError, OverflowError):
        raise ValueError("invalid user JSON Schema") from None
    try:
        _check_user_references(checked)
    except (SchemaError, AttributeError, TypeError, RecursionError, OverflowError):
        # Referencing can read a child's dialect and ID before it is checked in the traversal.
        raise ValueError("invalid user JSON Schema") from None
    return checked


def validate_user_json(
    payload: object, schema_path: Path, *, max_schema_bytes: int = _DEFAULT_MAX_SCHEMA_BYTES
) -> tuple[bool, str | None]:
    """Allow same-document references and keep retrieval disabled even during validation."""
    try:
        schema = load_user_json_schema(schema_path, max_schema_bytes=max_schema_bytes)
        validator: Any = Draft202012Validator(schema, registry=Registry())
        if validator.is_valid(payload):
            return True, None
    except Unresolvable:
        return False, "unresolvable user JSON Schema reference"
    except ValueError as error:
        return False, str(error)
    except (SchemaError, AttributeError, TypeError, RecursionError, OverflowError):
        return False, "invalid user JSON Schema"
    return False, "response does not match the user JSON Schema"
