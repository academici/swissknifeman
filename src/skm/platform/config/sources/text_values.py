"""Typed invocation text, without legacy JSON-or-string coercion (settings §B.11.3)."""

import json
import math
import re
from collections.abc import Mapping

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import KeySpec, copy_json

__all__ = ["parse_text_value"]

_INTEGER = re.compile(r"[+-]?[0-9]+")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def _parse(kind: str, schema: Mapping[str, JsonValue], text: str) -> JsonValue:
    if kind in ("string", "secret"):
        return text
    token = text.strip()
    if kind == "integer" and _INTEGER.fullmatch(token):
        return int(token)
    if kind == "number" and _NUMBER.fullmatch(token):
        number = float(token)
        if math.isfinite(number):
            return number
    if kind == "boolean":
        if token.lower() in ("true", "1", "yes", "on"):
            return True
        if token.lower() in ("false", "0", "no", "off"):
            return False
    if kind == "array":
        if token.startswith("["):
            value = copy_json(json.loads(token), "text")
            if isinstance(value, list):
                return value
        else:
            return _csv(schema, token)
    if kind == "object":
        value = copy_json(json.loads(token), "text")
        if isinstance(value, dict):
            return value
    raise ValueError(f"expected {kind} text")


def _csv(schema: Mapping[str, JsonValue], token: str) -> JsonValue:
    items = schema.get("items", {})
    if not isinstance(items, dict):
        raise ValueError("array item schema is required")
    item_kind = items.get("type", "string")
    if not isinstance(item_kind, str):
        raise ValueError("use JSON for ambiguous array items")
    return [] if not token else [_parse(item_kind, items, part.strip()) for part in token.split(",")]


def parse_text_value(spec: KeySpec, text: str) -> JsonValue:
    """Parse by the declared type. Range, enum and reference validation stays with the registry/fold."""
    try:
        return _parse(spec.value_type, spec.value_schema, text)
    except (ValueError, TypeError, OverflowError, RecursionError):
        # Parser exception messages may quote credentials or nested secret fields.
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "Cannot parse configuration text",
            details={"key": spec.key, "reason": "text_value", "message": "invalid text for key type"},
        ) from None
