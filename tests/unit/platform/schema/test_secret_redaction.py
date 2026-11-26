"""Values of ``x-skm-secret`` fields never reach an issue message, ``to_json`` or ``ValidationFailed``
(§1.2)."""

import json
import shutil
import sys
from enum import Enum
from pathlib import Path
from typing import Any, override

import pytest
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from skm.kernel.errors import ValidationFailed
from skm.platform.schema.locator import default_schema_root
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import REDACTED, SchemaValidator

DIALECT = "https://json-schema.org/draft/2020-12/schema"
BEGIN_STAGE = "urn:skm:execution:command:begin-stage:v1"
WRAPPER = "urn:skm:execution:wrap:v1"
VAULT = "urn:skm:shop:vault:v1"
# a well-formed runtime token plus one character, so that the pattern branch rejects it
TOKEN = "skm_abcdefgh_" + "A1b2C3d4" * 5 + "XyZ" + "!"


@pytest.fixture(scope="module")
def default() -> SchemaRegistry:
    return SchemaRegistry.load_default()


@pytest.fixture
def vault(tmp_path: Path) -> SchemaRegistry:
    body = {
        "$schema": DIALECT,
        "$id": VAULT,
        "type": "object",
        "maxProperties": 2,
        "properties": {
            "note": {"type": "string"},
            "secret": {"type": "string", "x-skm-secret": True},
            "pin": {"type": "string", "x-skm-secret": True},
            "plain": {"type": "string", "x-skm-secret": False},
        },
    }
    target = tmp_path / "shop" / "vault.v1.json"
    target.parent.mkdir()
    target.write_text(json.dumps(body), encoding="utf-8")
    return SchemaRegistry.load(tmp_path)


def begin_stage(**changes: Any) -> dict[str, Any]:
    return {"stage_id": "s1", "round_no": 0, "input_digest": "x", "runtime_token_secret": TOKEN, **changes}


def test_packaged_begin_stage_never_echoes_the_runtime_token(default: SchemaRegistry) -> None:
    issues = default.validate(BEGIN_STAGE, begin_stage())
    own = [i for i in issues if i.pointer == "/runtime_token_secret"]
    assert {i.code for i in own} >= {"anyOf", "pattern"}, issues  # the rejection itself is still reported
    for issue in issues:
        assert TOKEN not in issue.message
        assert TOKEN[:30] not in issue.message
    assert any(REDACTED in i.message for i in own)
    assert TOKEN not in json.dumps([i.to_json() for i in issues])


def test_validation_failed_details_do_not_carry_the_secret(default: SchemaRegistry) -> None:
    with pytest.raises(ValidationFailed) as raised:
        default.require_valid(BEGIN_STAGE, begin_stage())
    assert TOKEN not in str(raised.value.details)
    assert TOKEN not in str(raised.value)


def test_a_valid_token_is_accepted_and_a_null_token_too(default: SchemaRegistry) -> None:
    for token in (TOKEN.removesuffix("!"), None):
        issues = default.validate(BEGIN_STAGE, begin_stage(runtime_token_secret=token))
        assert [i for i in issues if i.pointer == "/runtime_token_secret"] == []


def test_the_parent_object_message_hides_the_secret_value(vault: SchemaRegistry) -> None:
    dto = {"secret": "hunter2-plain", "note": "n", "pin": "p"}
    issues = vault.validate(VAULT, dto)
    parent = [i for i in issues if i.pointer == "" and i.code == "maxProperties"]
    assert parent, issues
    assert "hunter2-plain" not in parent[0].message
    assert REDACTED in parent[0].message
    assert "'note': 'n'" in parent[0].message  # only the secret is hidden


def test_a_non_string_secret_is_hidden_without_cutting_other_numbers(vault: SchemaRegistry) -> None:
    issues = vault.validate(VAULT, {"pin": 123456, "note": 1234567})
    by_pointer = {i.pointer: i.message for i in issues}
    assert "123456" not in by_pointer["/pin"]
    assert REDACTED in by_pointer["/pin"]
    assert by_pointer["/note"] == "1234567 is not of type 'string'"


WIDE = 7 * (10**5001 - 1) // 9  # 5001 sevens: wider than the default int-to-text limit


@pytest.mark.parametrize("limit", [640, 4300, 0])  # sys.set_int_max_str_digits: the lowest, the default, off
def test_a_wide_integer_secret_is_hidden_and_does_not_raise(vault: SchemaRegistry, limit: int) -> None:
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(limit)
    try:
        issues = vault.validate(VAULT, {"pin": WIDE, "secret": -WIDE, "note": 10**640})
        by_pointer = {(i.pointer, i.code): i.message for i in issues}
        assert by_pointer[("/pin", "type")] == f"{REDACTED} is not of type 'string'"
        assert by_pointer[("/secret", "type")] == f"{REDACTED} is not of type 'string'"
        assert by_pointer[("/note", "type")].startswith("1" + "0" * 78 + "…")  # an unflagged number is shown
        parent = by_pointer[("", "maxProperties")]
        assert "777" not in parent
        assert REDACTED in parent
        assert "777" not in json.dumps([i.to_json() for i in issues])
        with pytest.raises(ValidationFailed) as raised:
            vault.require_valid(VAULT, {"pin": WIDE})
        assert "777" not in str(raised.value.details)
    finally:
        sys.set_int_max_str_digits(before)


@pytest.mark.parametrize("limit", [640, 4300, 0])
def test_a_wide_schema_literal_next_to_a_secret_does_not_disclose_it(limit: int) -> None:
    """The quoted literal shows the same leading digits as a secret close to it: both are hidden."""
    pin = {"x-skm-secret": True, "type": "integer"}
    body = {
        "$schema": DIALECT,
        "type": "object",
        "properties": {
            "close": {**pin, "const": WIDE},
            "listed": {**pin, "enum": [10**5000]},
            "negated": {**pin, "not": {"const": WIDE}},
            "choice": {**pin, "oneOf": [{"maximum": WIDE}, {"minimum": 0}]},
        },
    }
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(limit)
    try:
        validator = SchemaValidator(body, Registry())
        assert validator.issues({"close": WIDE, "listed": 10**5000, "negated": 5, "choice": -1}) == ()
        issues = validator.issues({"close": WIDE + 1, "listed": WIDE, "negated": WIDE, "choice": WIDE})
        by_pointer = {i.pointer: i.message for i in issues}
        assert sorted(by_pointer) == ["/choice", "/close", "/listed", "/negated"]
        assert by_pointer["/close"] == f"{REDACTED} was expected"
        literal = "1" + "0" * 78 + "…"  # a schema literal is no secret: it stays shown
        assert by_pointer["/listed"] == f"{REDACTED} is not one of [{literal}]"
        assert by_pointer["/negated"] == f"{REDACTED} should not be valid under {{'const': {REDACTED}}}"
        assert by_pointer["/choice"].startswith(f"{REDACTED} is valid under each of ")
        assert "777" not in json.dumps([i.to_json() for i in issues])
    finally:
        sys.set_int_max_str_digits(before)


@pytest.mark.parametrize(
    ("divisor", "valid", "secret"),
    [
        (10, 1e23, 1.5),
        (10, -7e300, -1.5),
        (int(1e23), 0.0, 1e23),
        (0.1, 0.3, 0.30000000000000004),
        (0.1, -0.3, -0.30000000000000004),
        (0.75, 9, 2**53),
        (1e-323, 1e-323, 5e-324),
        (2.0, 0.0, float("inf")),
        (2, 0.0, float("nan")),
    ],
)
def test_decimal_multiple_of_through_a_reference_keeps_numeric_secrets_hidden(
    tmp_path: Path, divisor: int | float, valid: int | float, secret: int | float
) -> None:
    numeric_uri = "urn:skm:shop:number:v1"
    numeric = {
        "$schema": DIALECT,
        "$id": numeric_uri,
        "type": "number",
        "multipleOf": divisor,
        "x-skm-secret": True,
    }
    body = {
        "$schema": DIALECT,
        "$id": VAULT,
        "properties": {"outer": {"items": {"anyOf": [{"type": "string"}, {"$ref": numeric_uri}]}}},
    }
    folder = tmp_path / "shop"
    folder.mkdir()
    (folder / "number.v1.json").write_text(json.dumps(numeric), encoding="utf-8")
    (folder / "vault.v1.json").write_text(json.dumps(body), encoding="utf-8")
    registry = SchemaRegistry.load(tmp_path)
    assert registry.validate(VAULT, {"outer": [valid]}) == ()
    registry.require_valid(VAULT, {"outer": [valid]})
    dto = {"outer": [secret]}
    found = registry.validate(VAULT, dto)
    assert [(i.pointer, i.code) for i in found] == [("/outer/0", "anyOf"), ("/outer/0", "multipleOf")]
    assert all(REDACTED in i.message for i in found)
    assert repr(secret) not in json.dumps([i.to_json() for i in found])
    with pytest.raises(ValidationFailed) as raised:
        registry.require_valid(VAULT, dto)
    assert repr(secret) not in str(raised.value.details)
    direct = SchemaValidator(body, registry.registry)
    assert direct.issues(dto) == found
    assert registry.get(numeric_uri)["$schema"] == DIALECT


@pytest.mark.parametrize("as_enum", [False, True], ids=["subclass", "enum"])
@pytest.mark.parametrize("operand", ["instance", "divisor", "both"])
def test_programmatic_float_subclasses_keep_multiple_of_secrets_hidden(as_enum: bool, operand: str) -> None:
    class Unit(float, Enum):
        HALF = 0.5
        ONE = 1.0

    class DisplayFloat(float):
        @override
        def __repr__(self) -> str:
            return f"secret-float({float.__repr__(self)})"

    float_type = Unit if as_enum else DisplayFloat
    divisor = float_type(1.0) if operand in {"divisor", "both"} else 1
    valid = float_type(1.0) if operand in {"instance", "both"} else 1.0
    secret = float_type(0.5) if operand in {"instance", "both"} else 0.5
    numeric_uri = "urn:skm:shop:number:v1"
    numeric = {"$schema": DIALECT, "type": "number", "multipleOf": divisor, "x-skm-secret": True}
    body: dict[str, Any] = {"properties": {"pin": {"anyOf": [{"type": "string"}, {"$ref": numeric_uri}]}}}
    resources: Registry[Any] = Registry().with_resource(numeric_uri, DRAFT202012.create_resource(numeric))
    registry = SchemaRegistry({VAULT: body, numeric_uri: numeric}, resources)
    assert registry.is_valid_schema(numeric)
    assert registry.validate(VAULT, {"pin": valid}) == ()
    registry.require_valid(VAULT, {"pin": valid})
    found = registry.validate(VAULT, {"pin": secret})
    assert [(i.pointer, i.code) for i in found] == [("/pin", "anyOf"), ("/pin", "multipleOf")]
    assert all(REDACTED in issue.message for issue in found)
    assert repr(secret) not in json.dumps([issue.to_json() for issue in found])
    assert SchemaValidator(body, resources).issues({"pin": secret}) == found
    with pytest.raises(ValidationFailed) as raised:
        registry.require_valid(VAULT, {"pin": secret})
    assert repr(secret) not in str(raised.value.details)


def test_secret_false_and_unflagged_fields_keep_their_values(vault: SchemaRegistry) -> None:
    issues = vault.validate(VAULT, {"plain": 7})
    assert [i.message for i in issues] == ["7 is not of type 'string'"]


def test_redaction_does_not_leak_between_validations(vault: SchemaRegistry) -> None:
    vault.validate(VAULT, {"secret": 5})
    assert [i.message for i in vault.validate(VAULT, {"note": 5})] == ["5 is not of type 'string'"]


@pytest.fixture(scope="module")
def wrapped(tmp_path_factory: pytest.TempPathFactory) -> SchemaRegistry:
    """The packaged schemas plus a document that reaches begin-stage through ``$ref`` (own ``$schema``)."""
    root = tmp_path_factory.mktemp("wrapped")
    packaged = Path(str(default_schema_root()))
    shutil.copytree(packaged, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    wrapper = {
        "$schema": DIALECT,
        "$id": WRAPPER,
        "type": "object",
        "properties": {"inner": {"$ref": BEGIN_STAGE}},
    }
    (root / "execution" / "wrap.v1.json").write_text(json.dumps(wrapper), encoding="utf-8")
    return SchemaRegistry.load(root)


def test_the_token_is_hidden_when_begin_stage_is_reached_through_a_reference(wrapped: SchemaRegistry) -> None:
    direct = wrapped.validate(BEGIN_STAGE, begin_stage())
    via_ref = wrapped.validate(WRAPPER, {"inner": begin_stage()})
    shape = {(i.code, i.pointer.removeprefix("/inner")) for i in via_ref}
    assert shape == {(i.code, i.pointer) for i in direct}
    assert {"anyOf", "pattern"} <= {i.code for i in via_ref if i.pointer.endswith("/runtime_token_secret")}
    for issues in (direct, via_ref):
        assert all(TOKEN not in i.message and TOKEN[:30] not in i.message for i in issues)
        assert TOKEN not in json.dumps([i.to_json() for i in issues])


def test_a_directly_built_validator_over_the_original_registry_hides_the_token(
    wrapped: SchemaRegistry,
) -> None:
    validator = SchemaValidator(wrapped.get(WRAPPER), wrapped.registry)  # documents still carry "$schema"
    issues = validator.issues({"inner": begin_stage()})
    assert {"anyOf", "pattern"} <= {i.code for i in issues if i.pointer == "/inner/runtime_token_secret"}
    assert all(TOKEN not in i.message and TOKEN[:30] not in i.message for i in issues)
    assert TOKEN not in json.dumps([i.to_json() for i in issues])
    assert "$schema" in wrapped.get(BEGIN_STAGE)  # the registered documents were not changed


def test_the_token_is_hidden_when_a_short_circuiting_if_stops_before_the_secret_field(
    wrapped: SchemaRegistry,
) -> None:
    gate = {
        "$id": "urn:skm:shop:gate:v1",
        "type": "object",
        "properties": {"runtime_token_secret": {"type": "integer"}},  # the outer schema is not flagged itself
        "if": {"$ref": BEGIN_STAGE},  # is_valid() stops at the bad input_digest, before the secret field
    }
    dto = begin_stage()
    issues = SchemaValidator(gate, wrapped.registry).issues(dto)
    own = [i for i in issues if i.pointer == "/runtime_token_secret"]
    assert [i.code for i in own] == ["type"]  # the rejection itself is kept
    assert REDACTED in own[0].message
    assert all(TOKEN not in i.message and TOKEN[:30] not in i.message for i in issues)
    assert TOKEN not in json.dumps([i.to_json() for i in issues])


def test_a_secret_flagged_through_a_reference_is_hidden(tmp_path: Path) -> None:
    body = {
        "$schema": DIALECT,
        "$id": VAULT,
        "type": "object",
        "$defs": {"hidden": {"type": "string", "x-skm-secret": True}},
        "properties": {"outer": {"type": "object", "properties": {"key": {"$ref": "#/$defs/hidden"}}}},
    }
    target = tmp_path / "shop" / "vault.v1.json"
    target.parent.mkdir()
    target.write_text(json.dumps(body), encoding="utf-8")
    issues = SchemaRegistry.load(tmp_path).validate(VAULT, {"outer": {"key": 12345678}})
    assert [(i.pointer, i.code) for i in issues] == [("/outer/key", "type")]
    assert "12345678" not in issues[0].message
    assert REDACTED in issues[0].message


@pytest.mark.parametrize(("target", "accepts"), [(True, True), (False, False)])
def test_a_directly_built_validator_keeps_boolean_schema_resources(target: bool, accepts: bool) -> None:
    uri = "urn:skm:shop:flag:v1"
    registry: Registry[Any] = Registry().with_resources([(uri, DRAFT202012.create_resource(target))])
    holder = {"$id": "urn:skm:shop:holder:v1", "properties": {"x": {"$ref": uri}}}
    issues = SchemaValidator(holder, registry).issues({"x": 1})
    assert [i.code for i in issues if i.code == "$ref"] == []  # resolved, never "unresolved reference"
    assert [i.pointer for i in issues] == ([] if accepts else ["/x"])


CREDS_SCHEMA = {
    "$schema": DIALECT,
    "$id": VAULT,
    "type": "object",
    "properties": {
        "creds": {
            "x-skm-secret": True,
            "type": "object",
            "properties": {"password": {"type": "string", "minLength": 20}},
            "required": ["password"],
        },
        "list": {
            "x-skm-secret": True,
            "type": "array",
            "items": {"type": "string", "pattern": "^safe$"},
        },
    },
}


@pytest.fixture
def creds(tmp_path: Path) -> SchemaRegistry:
    target = tmp_path / "shop" / "vault.v1.json"
    target.parent.mkdir()
    target.write_text(json.dumps(CREDS_SCHEMA), encoding="utf-8")
    return SchemaRegistry.load(tmp_path)


@pytest.mark.parametrize(
    ("dto", "pointer", "code"),
    [
        ({"creds": {"password": "hunter2"}}, "/creds/password", "minLength"),
        ({"list": ["hunter2"]}, "/list/0", "pattern"),
        ({"list": ["safe", {"deep": ["hunter2"]}]}, "/list/1", "type"),
    ],
)
def test_values_nested_in_a_secret_container_are_hidden(
    creds: SchemaRegistry, dto: dict[str, Any], pointer: str, code: str
) -> None:
    issues = creds.validate(VAULT, dto)
    assert (pointer, code) in [(i.pointer, i.code) for i in issues]  # the finding itself is kept
    assert not [i for i in issues if "hunter2" in i.message]
    assert "hunter2" not in json.dumps([i.to_json() for i in issues])
    with pytest.raises(ValidationFailed) as raised:
        creds.require_valid(VAULT, dto)
    assert "hunter2" not in str(raised.value.details)
    assert any(REDACTED in i.message for i in issues if i.pointer == pointer)


def test_an_empty_secret_container_does_not_blank_other_messages(creds: SchemaRegistry) -> None:
    issues = creds.validate(VAULT, {"creds": {}, "list": []})
    assert [(i.pointer, i.code, i.message) for i in issues] == [
        ("/creds", "required", "'password' is a required property")
    ]


def test_references_that_recurse_without_progress_are_reported_not_raised() -> None:
    validator = SchemaValidator({"$id": "urn:skm:shop:loop:v1", "$ref": "#"}, Registry())
    issues = validator.issues({})
    assert [i.code for i in issues] == ["$ref"]
