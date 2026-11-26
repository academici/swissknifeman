"""Validation and scalar substitution for plan template resources."""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from typing import Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = [
    "PlanTemplateManifest",
    "render_template",
    "validate_inputs",
    "validate_manifest",
    "validate_schema",
]

PlanTemplateManifest = dict[str, Any]
_TOKEN = re.compile(r"\{\{\s*(?:\"(\{\{|\}\})\"|'(\{\{|\}\})'|(?:inputs\.)?([a-zA-Z_][a-zA-Z0-9_]*))\s*\}\}")


def validate_schema(schema: Mapping[str, Any]) -> None:  # noqa: PLR0912 - validate the supported schema subset
    """Accept only the bounded, scalar subset supported by plan templates."""
    try:
        if set(schema) - {"type", "properties", "required", "additionalProperties", "maxProperties"}:
            raise ValueError("unsupported object schema keyword")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        maximum = schema.get("maxProperties", 50)
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            raise ValueError("invalid object schema")
        properties = cast("Mapping[Any, Any]", properties)
        required = cast("list[Any]", required)
        if (
            schema.get("type") != "object"
            or len(properties) > 50
            or any(not isinstance(name, str) or name not in properties for name in required)
            or len(set(required)) != len(required)
            or schema.get("additionalProperties", False) is not False
            or type(maximum) is not int
            or not 0 <= maximum <= 50
        ):
            raise ValueError("invalid object schema")
        for name, rule in properties.items():
            if not isinstance(name, str) or not isinstance(rule, Mapping):
                raise ValueError("invalid property schema")
            rule = cast("Mapping[str, Any]", rule)
            kind = rule.get("type")
            allowed = {"type", "enum"}
            if kind == "string":
                allowed |= {"minLength", "maxLength", "pattern"}
                for key in ("minLength", "maxLength"):
                    if key in rule and (type(rule[key]) is not int or not 0 <= rule[key] <= 2000):
                        raise ValueError("invalid string length")
                if rule.get("minLength", 0) > rule.get("maxLength", 2000):
                    raise ValueError("invalid string length range")
                if "pattern" in rule:
                    if not isinstance(rule["pattern"], str):
                        raise ValueError("invalid pattern")
                    re.compile(rule["pattern"])
            elif kind == "integer":
                allowed |= {"minimum", "maximum"}
                for key in ("minimum", "maximum"):
                    if key in rule and (
                        type(rule[key]) not in (int, float)
                        or (isinstance(rule[key], float) and not math.isfinite(rule[key]))
                    ):
                        raise ValueError("invalid integer bound")
                if "minimum" in rule and "maximum" in rule and rule["minimum"] > rule["maximum"]:
                    raise ValueError("invalid integer range")
            elif kind != "boolean":
                raise ValueError("unsupported input type")
            if set(rule) - allowed:
                raise ValueError("unsupported property schema keyword")
            if "enum" in rule:
                enum = rule["enum"]
                expected = {"string": str, "integer": int, "boolean": bool}[kind]
                if not isinstance(enum, list):
                    raise ValueError("invalid enum")
                enum = cast("list[Any]", enum)
                if not enum or any(type(value) is not expected for value in enum):
                    raise ValueError("invalid enum")
    except (ValueError, TypeError, re.error) as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "invalid template input schema", details={"reason": str(exc)}
        ) from exc


def validate_inputs(inputs: Mapping[str, Any], input_schema: Mapping[str, Any]) -> None:
    validate_schema(input_schema)
    properties = input_schema.get("properties", {})
    if (
        len(inputs) > input_schema.get("maxProperties", 50)
        or set(inputs) - set(properties)
        or set(input_schema.get("required", [])) - set(inputs)
    ):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid template inputs")
    for name, value in inputs.items():
        rule = properties[name]
        kind = rule["type"]
        expected = {"string": str, "integer": int, "boolean": bool}[kind]
        valid = type(value) is expected
        if valid and "enum" in rule:
            valid = value in rule["enum"]
        if valid and kind == "string":
            valid = rule.get("minLength", 0) <= len(value) <= rule.get("maxLength", 2000) and (
                "pattern" not in rule or re.search(rule["pattern"], value) is not None
            )
        if valid and kind == "integer":
            valid = ("minimum" not in rule or value >= rule["minimum"]) and (
                "maximum" not in rule or value <= rule["maximum"]
            )
        if not valid:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "invalid template input", details={"input": name}
            )


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    allowed = {"schema", "key", "version", "title", "description", "inputs_schema"}
    if (
        set(manifest) - allowed
        or manifest.get("schema") != "urn:skm:extensions:plan-template:v1"
        or not isinstance(manifest.get("key"), str)
        or not manifest["key"]
        or not isinstance(manifest.get("version"), str)
        or not manifest["version"]
        or ("title" in manifest and not isinstance(manifest["title"], str))
        or ("description" in manifest and not isinstance(manifest["description"], str))
        or not isinstance(manifest.get("inputs_schema"), Mapping)
    ):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid plan template manifest")
    validate_schema(cast("Mapping[str, Any]", manifest["inputs_schema"]))


def _validate_raw_scalars(inputs: Mapping[str, Any]) -> None:
    if len(inputs) > 50 or any(
        type(key) is not str
        or type(val) not in (str, int, bool)
        or (isinstance(val, str) and len(val) > 2000)
        for key, val in inputs.items()
    ):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid template inputs")


def render_template(
    template: Mapping[str, Any],
    inputs: Mapping[str, Any],
    input_schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if input_schema is not None:
        validate_inputs(inputs, input_schema)
    else:
        _validate_raw_scalars(inputs)

    def render(value: Any) -> Any:
        if isinstance(value, str):

            def substitute(match: re.Match[str]) -> str:
                escaped = match.group(1) or match.group(2)
                if escaped is not None:
                    return escaped
                name = match.group(3)
                if name is None or name not in inputs or type(inputs[name]) not in (str, int, bool):
                    raise ValidationFailed(
                        ErrorCode.SCHEMA_INVALID,
                        "unknown or non-scalar template input",
                        details={"input": name or ""},
                    )
                item = inputs[name]
                return str(item).lower() if isinstance(item, bool) else str(item)

            remaining = _TOKEN.sub("", value)
            if "{{" in remaining or "}}" in remaining:
                raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid template expression")
            return _TOKEN.sub(substitute, value)
        if isinstance(value, Mapping):
            return {key: render(item) for key, item in cast("Mapping[str, Any]", value).items()}
        if isinstance(value, list):
            return [render(item) for item in cast("list[Any]", value)]
        return copy.deepcopy(value)

    return render(template)
