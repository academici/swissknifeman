"""Regression coverage for settings schema metadata and import preview admission."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from jsonschema.protocols import Validator
from referencing import Registry, Resource
from referencing.jsonschema import Schema

from skm.kernel.json_types import JsonObject, JsonValue

SCHEMAS = Path(__file__).resolve().parents[3] / "src/skm/schemas"
GET_SCHEMA: JsonObject = json.loads((SCHEMAS / "settings/views/get-schema.v1.json").read_text())
GET_SCHEMA_QUERY: JsonObject = json.loads((SCHEMAS / "settings/queries/get-schema.v1.json").read_text())
GET_GENERATION_QUERY: JsonObject = json.loads(
    (SCHEMAS / "settings/queries/get-generation.v1.json").read_text()
)
IMPORT_CONFIG: JsonObject = json.loads((SCHEMAS / "settings/commands/import-config.v1.json").read_text())
REQUIRED_KEY_FIELDS = (
    "key",
    "section",
    "chain",
    "levels",
    "merge",
    "reload",
    "override",
    "sensitivity",
    "portable",
    "lockable",
    "nullable",
    "pack",
    "confirm",
    "value_schema",
    "validators",
    "ui",
)
KEY: JsonObject = {
    "key": "logging.level",
    "section": "logging",
    "chain": "work",
    "levels": ["instance"],
    "merge": "replace",
    "reload": "live",
    "override": False,
    "sensitivity": "public",
    "portable": True,
    "lockable": True,
    "nullable": False,
    "pack": True,
    "confirm": False,
    "value_schema": {"type": "string", "enum": ["info", "debug"]},
    "validators": [],
    "ui": {"group": "Logging", "order": 10, "widget": "select"},
}


def validator(schema: JsonObject) -> Validator:
    resources: list[tuple[str, Resource[Schema]]] = []
    for name in ("kernel/defs", "config/entry", "config/key-spec"):
        document: JsonObject = json.loads((SCHEMAS / f"{name}.v1.json").read_text())
        resources.append((str(document["$id"]), Resource[Schema].from_contents(document)))
    return Draft202012Validator(
        schema,
        registry=Registry[Schema]().with_resources(resources),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def schema_response(key: JsonObject) -> JsonObject:
    return {
        "registry_digest": "sha256:" + "a" * 64,
        "sections": [
            {
                "id": "logging",
                "owner": "platform",
                "title": "Logging",
                "schema_urn": "urn:skm:settings:logging:v1",
                "schema": {},
                "validators": [],
                "keys": [key],
            }
        ],
    }


@pytest.mark.parametrize("schema", [GET_SCHEMA, GET_SCHEMA_QUERY, IMPORT_CONFIG])
def test_schema_is_valid(schema: JsonObject) -> None:
    Draft202012Validator.check_schema(schema)


def test_get_schema_scope_is_the_shared_optional_scope_ref() -> None:
    # settings §A.8: {scope?, section?}; scope is the same scope_ref as get_generation's optional scope
    properties = GET_SCHEMA_QUERY["properties"]
    assert isinstance(properties, dict)
    # section stays first: the generated dataclass keeps GetSchema("storage") as the section
    assert list(properties) == ["section", "scope"]
    assert properties["scope"] == {"$ref": "urn:skm:config:entry:v1#/$defs/scope_ref"}
    assert properties["scope"] == GET_GENERATION_QUERY["properties"]["scope"]  # type: ignore[index]
    assert GET_SCHEMA_QUERY["required"] == []
    assert GET_SCHEMA_QUERY["additionalProperties"] is False


@pytest.mark.parametrize(
    "request_",
    [
        {},
        {"section": "storage"},
        {"scope": {"level": "instance"}},
        {"scope": {"level": "project", "scope_id": "01900000-0000-7000-8000-0000000000c1"}},
        {
            "scope": {"level": "host", "scope_id": "01900000-0000-7000-8000-0000000000f1"},
            "section": "logging",
        },
    ],
)
def test_get_schema_request_accepts_an_optional_scope(request_: JsonObject) -> None:
    validator(GET_SCHEMA_QUERY).validate(request_)


@pytest.mark.parametrize(
    "request_",
    [
        {"scope": "instance"},
        {"scope": None},
        {"scope": {}},
        {"scope": {"level": "galaxy"}},
        {"scope": {"level": "project", "scope_id": "not-a-uuid"}},
        {"scope": {"level": "project", "scope_id": 7}},
        {"scope": {"level": "project", "scope": "x"}},
        {"section": 7},
        {"target": {"level": "instance"}},
    ],
)
def test_get_schema_request_rejects_malformed_scopes(request_: JsonObject) -> None:
    with pytest.raises(ValidationError):
        validator(GET_SCHEMA_QUERY).validate(request_)


def test_key_spec_accepts_required_fields_without_optional_metadata() -> None:
    validator(GET_SCHEMA).validate(schema_response(KEY))


def test_key_spec_accepts_optional_metadata() -> None:
    key = deepcopy(KEY)
    key.update(
        default=None,
        narrow={"direction": "min", "unlimited": 0},
        deprecated={"since": "2.0", "replacement": "logging.level", "until": "3.0"},
    )
    validator(GET_SCHEMA).validate(schema_response(key))


def test_key_spec_rejects_empty_object() -> None:
    with pytest.raises(ValidationError):
        validator(GET_SCHEMA).validate(schema_response({}))


@pytest.mark.parametrize("field", REQUIRED_KEY_FIELDS)
def test_key_spec_requires_each_owner_field(field: str) -> None:
    key = deepcopy(KEY)
    del key[field]
    with pytest.raises(ValidationError):
        validator(GET_SCHEMA).validate(schema_response(key))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("key", "invalid"),
        ("chain", "invalid"),
        ("levels", ["invalid"]),
        ("merge", "invalid"),
        ("reload", "invalid"),
        ("sensitivity", "invalid"),
        ("override", "false"),
        ("value_schema", []),
        ("validators", [42]),
        ("ui", {}),
        ("narrow", {"direction": "invalid"}),
        ("deprecated", {}),
    ],
)
def test_key_spec_enforces_metadata_types(field: str, value: JsonValue) -> None:
    key = deepcopy(KEY)
    key[field] = value
    with pytest.raises(ValidationError):
        validator(GET_SCHEMA).validate(schema_response(key))


@pytest.mark.parametrize(
    ("format_name", "document"),
    [
        ("json", {"unknown": {"x": 1}}),
        ("json", {"schema": "urn:skm:settings:document:v1", "unknown": {"x": 1}}),
        ("json", {"schema": "incorrect"}),
        ("json", {}),
        ("toml", "[unknown]\nx = 1\n"),
    ],
)
def test_import_admits_documents_for_parser_preview(format_name: str, document: JsonValue) -> None:
    request: JsonObject = {
        "scope": {"level": "instance"},
        "format": format_name,
        "dry_run": True,
        "document": document,
    }
    validator(IMPORT_CONFIG).validate(request)


@pytest.mark.parametrize("document", [42, 1.5, [], ["logging"], None, True])
def test_import_rejects_document_types_other_than_string_or_object(document: JsonValue) -> None:
    request: JsonObject = {"scope": {"level": "instance"}, "format": "json", "document": document}
    with pytest.raises(ValidationError):
        validator(IMPORT_CONFIG).validate(request)
