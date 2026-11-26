"""Plan template manifest validation and pure scalar substitution (extensions §§4.2, 5)."""

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.extensions.domain.plan_template import (
    render_template,
    validate_inputs,
    validate_manifest,
    validate_schema,
)
from skm.modules.planning.domain.templates import validate_inputs as planning_validate_inputs
from skm.platform.schema.registry import SchemaRegistry


@pytest.mark.parametrize("key", ["feature", "bugfix"])
def test_bundled_template_matches_manifest_and_specification_schemas(key: str) -> None:
    base = Path("resources/packs/core/plan-templates") / key
    manifest = tomllib.loads((base / "manifest.toml").read_text(encoding="utf-8"))
    registry = SchemaRegistry.load_default()
    registry.require_valid("urn:skm:extensions:plan-template:v1", manifest)
    validate_manifest(manifest)

    template = json.loads((base / "template.json").read_text(encoding="utf-8"))
    rendered = render_template(
        template,
        {"title": "Example", "goal": "A concrete goal"},
        manifest["inputs_schema"],
    )
    registry.require_valid("urn:skm:planning:specification:v1", rendered)


def test_render_scalar_slots_escaped_braces_and_preserve_non_strings() -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "enabled": {"type": "boolean"},
        },
        "required": ["name", "count", "enabled"],
        "additionalProperties": False,
    }
    validate_manifest(
        {
            "schema": "urn:skm:extensions:plan-template:v1",
            "key": "feature",
            "version": "1.0.0",
            "title": "Feature",
            "description": "Desc",
            "inputs_schema": schema,
        }
    )
    template: dict[str, Any] = {
        "{{name}}": [
            "Hello {{ inputs.name }} #{{count}} ({{ enabled }})",
            "Literal {{ \"{{\" }}raw{{ \"}}\" }} and {{'{{' }}ok{{'}}'}}",
            4,
            True,
            None,
        ]
    }
    rendered = render_template(template, {"name": "world", "count": 3, "enabled": True}, schema)
    assert rendered == {
        "{{name}}": [
            "Hello world #3 (true)",
            "Literal {{raw}} and {{ok}}",
            4,
            True,
            None,
        ]
    }
    assert template["{{name}}"][0] == "Hello {{ inputs.name }} #{{count}} ({{ enabled }})"


def test_input_payloads_stay_inert_without_code_or_recursive_evaluation() -> None:
    schema = {
        "type": "object",
        "properties": {"payload": {"type": "string"}, "other": {"type": "string"}},
        "required": ["payload", "other"],
        "additionalProperties": False,
    }
    dangerous = "{{ __import__('os').system('echo pwned') }} $(uname) {{other}}"
    rendered = render_template(
        {"text": "{{inputs.payload}}"},
        {"payload": dangerous, "other": "SECRET"},
        schema,
    )
    assert rendered == {"text": dangerous}
    assert render_template({"text": "{{payload}}"}, {"payload": "ok"}) == {"text": "ok"}


@pytest.mark.parametrize(
    ("inputs", "expression"),
    [
        ({}, "{{name}}"),
        ({"other": "x"}, "{{name}}"),
        ({"name": 123}, "{{name}}"),
        ({"name": "x"}, "{{missing}}"),
        ({"name": "x"}, "{{__import__('os')}}"),
        ({"name": "x"}, "{{ 1 + 1 }}"),
        ({"name": "x"}, "{{ inputs.nested.field }}"),
        ({"name": "x"}, "unclosed {{ name"),
        ({"name": "x"}, "stray }} brace"),
    ],
)
def test_bad_inputs_and_expressions_fail_with_schema_invalid(inputs: dict[str, Any], expression: str) -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    with pytest.raises(ValidationFailed) as exc_info:
        render_template({"value": expression}, inputs, schema)
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID


@pytest.mark.parametrize(
    ("rule", "good", "bad"),
    [
        ({"type": "string", "minLength": 2, "maxLength": 3, "pattern": "^a", "enum": ["ab"]}, "ab", "bc"),
        ({"type": "integer", "minimum": 1.5, "maximum": 3.5}, 2, True),
        ({"type": "boolean"}, False, 0),
    ],
)
def test_scalar_constraints(rule: dict[str, Any], good: object, bad: object) -> None:
    schema = {"type": "object", "properties": {"value": rule}, "required": ["value"]}
    for validator in (validate_inputs, planning_validate_inputs):
        validator({"value": good}, schema)
        with pytest.raises(ValidationFailed) as exc_info:
            validator({"value": bad}, schema)
        assert exc_info.value.code is ErrorCode.SCHEMA_INVALID


def test_unbounded_and_unsupported_schema_or_manifest_is_rejected() -> None:
    for schema in (
        {"type": "object", "maxProperties": 51},
        {"type": "object", "additionalProperties": True},
        {"type": "object", "properties": {"x": {"type": "string", "maxLength": 2001}}},
        {"type": "object", "properties": {"x": {"type": "number"}}},
        {"type": "object", "$ref": "#/$defs/x"},
    ):
        with pytest.raises(ValidationFailed) as exc_info:
            validate_schema(schema)
        assert exc_info.value.code is ErrorCode.SCHEMA_INVALID

    with pytest.raises(ValidationFailed) as mf_err:
        validate_manifest(
            {
                "schema": "urn:skm:extensions:plan-template:v1",
                "key": "k",
                "version": "1.0.0",
                "inputs_schema": {"type": "object"},
                "unexpected": True,
            }
        )
    assert mf_err.value.code is ErrorCode.SCHEMA_INVALID
