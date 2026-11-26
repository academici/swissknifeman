"""Secret resolution boundaries: explicit source, no implicit disclosure, redaction before use."""

import builtins
import copy
import io
import json
import pickle
import socket
import sys
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry

from skm.adapters.secrets.env import EnvSecretResolver
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed
from skm.platform.config import secrets
from skm.platform.config.keys import freeze_json
from skm.platform.config.secrets import SecretRef, SecretResolvers, SecretValue, mask_secret_refs
from skm.platform.jsonc.canonical import canonical_bytes
from skm.platform.logging.envelope import safe_fields
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.schema.registry import SchemaRegistry

TEXT = "synthetic-revealed-value-9482"
REF = SecretRef.parse("secret://env/SKM_TEST_SECRET")
SECRET = {"$ref": "urn:skm:config:secret-ref:v1"}


def registry(*resolvers):
    redactor = Redactor(patterns=())
    return SecretResolvers(resolvers, on_reveal=redactor.register_secret), redactor


def test_handle_has_only_explicit_plaintext_access():
    handle = SecretValue(REF, TEXT)
    assert handle.reveal() == TEXT
    assert str(handle) == repr(handle) == f"<secret {REF}>"
    assert TEXT not in repr({"history": [handle]})
    assert not hasattr(handle, "__dict__")
    with pytest.raises(TypeError):
        vars(handle)


@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_every_pickle_protocol_is_refused(protocol):
    with pytest.raises(TypeError, match="cannot be serialized") as caught:
        pickle.dumps(SecretValue(REF, TEXT), protocol=protocol)
    assert TEXT not in str(caught.value)


@pytest.mark.parametrize("serialize", [json.dumps, canonical_bytes, copy.copy, copy.deepcopy])
def test_json_and_copy_paths_do_not_extract_plaintext(serialize):
    handle = SecretValue(REF, TEXT)
    with pytest.raises(TypeError) as caught:
        serialize(handle)
    assert TEXT not in str(caught.value)
    assert TEXT not in json.dumps({"value": handle}, default=str)


@pytest.mark.parametrize("payload", ["explain", "export", "error", "history", "event"])
def test_handle_is_not_serializable_inside_payloads(payload):
    with pytest.raises(TypeError):
        json.dumps({payload: {"value": SecretValue(REF, TEXT)}})


def test_resolve_registers_with_redactor_before_returning_handle():
    resolvers, redactor = registry(EnvSecretResolver({REF.path: TEXT}))
    handle = resolvers.resolve(str(REF))
    assert handle.reveal() == TEXT
    assert redactor.text("received " + TEXT) == "received " + MASK
    assert redactor.document({"error": TEXT, "history": [TEXT], "event": {TEXT: TEXT}}) == {
        "error": MASK,
        "history": [MASK],
        "event": {MASK: MASK},
    }
    # Real logging projection excludes handles without attempting reveal/str/repr.
    assert safe_fields("config.resolved", {"digest": handle, "secret": handle}) == {}
    assert TEXT not in repr(resolvers)


def test_each_resolution_reads_exactly_one_backend_and_registers_once():
    calls = []
    revealed = []

    class Backend:
        scheme = "env"

        def resolve(self, ref):
            calls.append(ref)
            return TEXT

    resolvers = SecretResolvers([Backend()], on_reveal=revealed.append)
    handle = resolvers.resolve(REF)
    handle.reveal()
    handle.reveal()
    assert calls == [REF]
    assert revealed == [TEXT]


def test_registry_captures_dispatch_and_cannot_be_mutated():
    class Backend:
        scheme = "env"

        def resolve(self, ref):
            return TEXT

    backend = Backend()
    inputs = [backend]
    resolvers, _ = registry(*inputs)
    inputs.clear()
    backend.scheme = "file"
    cast(Any, backend).resolve = lambda ref: "replaced-source"
    assert resolvers.resolve(REF).reveal() == TEXT
    with pytest.raises(FrozenInstanceError):
        cast(Any, resolvers)._on_reveal = lambda value: None
    with pytest.raises(TypeError):
        cast(Any, resolvers)._resolvers["env"] = backend.resolve
    with pytest.raises(BackendUnavailable):
        resolvers.resolve("secret://file/synthetic")


def test_duplicate_backend_never_overwrites_an_admitted_source():
    with pytest.raises(ValueError, match="duplicate"):
        registry(EnvSecretResolver({REF.path: TEXT}), EnvSecretResolver({REF.path: "other-source"}))


def test_keyring_without_adapter_never_falls_back_to_environment():
    resolvers, _ = registry(EnvSecretResolver({REF.path: TEXT}))
    with pytest.raises(BackendUnavailable) as caught:
        resolvers.resolve("secret://keyring/skm/test")
    assert caught.value.code == ErrorCode.BACKEND_UNAVAILABLE
    assert dict(caught.value.details) == {"ref": "secret://keyring/skm/test"}


@pytest.mark.parametrize("failure", ["exception", "backend", "validation", "wrong_result", "callback"])
def test_untrusted_backend_and_callback_errors_never_escape(failure):
    class Backend:
        scheme = "env"

        def resolve(self, ref):
            if failure == "exception":
                raise OSError(TEXT)
            if failure == "backend":
                raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, TEXT, details={"value": TEXT})
            if failure == "validation":
                error = ValidationFailed(
                    ErrorCode.CONFIG_INVALID, TEXT, details={"reason": "secret_unresolved", "value": TEXT}
                )
                error.add_note(TEXT)
                raise error
            return object() if failure == "wrong_result" else TEXT

    def on_reveal(value):
        if failure == "callback":
            raise RuntimeError(value)

    resolvers = SecretResolvers(cast(Any, [Backend()]), on_reveal=on_reveal)
    expected = ValidationFailed if failure == "validation" else BackendUnavailable
    with pytest.raises(expected) as caught:
        resolvers.resolve(REF)
    error = caught.value
    assert error.__context__ is error.__cause__ is None
    assert TEXT not in "".join(traceback.format_exception(error))
    assert TEXT not in json.dumps(error.to_problem())


def test_invalid_reference_does_not_reach_backend_or_callback():
    callbacks = []
    resolvers = SecretResolvers([], on_reveal=callbacks.append)
    with pytest.raises(ValidationFailed) as caught:
        resolvers.resolve(TEXT)
    assert dict(caught.value.details) == {"reason": "secret_ref_invalid"}
    assert TEXT not in str(caught.value)
    assert callbacks == []


def test_nested_masking_preserves_only_reference_metadata_and_copies_public_data():
    schema = {
        "type": "object",
        "additionalProperties": {
            "type": "object",
            "properties": {
                "target": {"properties": {"secret": SECRET}},
                "env_refs": {"additionalProperties": SECRET},
                "items": {"items": SECRET},
            },
        },
    }
    value = {
        "test": {
            "target": {"secret": str(REF), "url": "https://example.invalid/hook"},
            "env_refs": {"SAFE": str(REF), "BAD": TEXT},
            "items": [str(REF), TEXT, None, {"nested": TEXT}],
            "enabled": True,
        }
    }
    masked = cast(Any, mask_secret_refs(cast(Any, value), cast(Any, schema)))
    assert masked["test"]["target"] == value["test"]["target"]
    assert masked["test"]["env_refs"] == {"SAFE": str(REF), "BAD": "<redacted>"}
    assert masked["test"]["items"] == [str(REF), "<redacted>", None, "<redacted>"]
    assert TEXT not in json.dumps(masked)
    masked["test"]["target"]["url"] = "changed"
    assert value["test"]["target"]["url"] == "https://example.invalid/hook"


@pytest.mark.parametrize("keyword", ["allOf", "anyOf", "oneOf"])
def test_composed_local_references_mask_plaintext_in_every_branch(keyword):
    schema = {
        "$defs": {"entry": {"properties": {"secret": SECRET}}},
        keyword: [{"type": "object"}, {"$ref": "#/$defs/entry"}],
    }
    assert mask_secret_refs({"secret": TEXT}, schema) == {"secret": "<redacted>"}
    assert mask_secret_refs({"secret": str(REF)}, schema) == {"secret": str(REF)}


def test_packaged_external_reference_masks_mcp_environment_secrets():
    schema = {"$ref": "urn:skm:settings:integrations:v1"}
    value = {"mcp": {"servers": {"test": {"env_refs": {"SAFE": str(REF), "BAD": TEXT}}}}}
    masked = mask_secret_refs(cast(Any, value), schema)
    assert TEXT not in json.dumps(masked)
    assert str(REF) in json.dumps(masked)


def test_pattern_properties_prefix_items_and_flagged_fields_are_masked():
    schema = {"patternProperties": {"^entry": {"prefixItems": [SECRET], "items": {"x-skm-secret": True}}}}
    assert mask_secret_refs({"entry1": [TEXT, TEXT, str(REF)], "public": 3}, cast(Any, schema)) == {
        "entry1": ["<redacted>", "<redacted>", str(REF)],
        "public": 3,
    }


@pytest.mark.parametrize(
    "schema", [{"$ref": "#"}, {"$ref": "urn:skm:missing:schema:v1"}, {"$ref": 5}, {"$ref": ["#"]}]
)
def test_uninterpretable_schema_fails_closed(schema):
    assert mask_secret_refs({"value": TEXT}, schema) == "<redacted>"


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("secret masking must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.mark.parametrize(
    "reference",
    [
        "#/$defs/missing",
        "#/$defs/cycle",
        "#/$defs/text",
        "urn:skm:integrations:defs:v1#/$defs/Missing",
        "urn:skm:missing:schema:v1#/$defs/entry",
        "https://example.invalid/schema.json",
        "file:///etc/schema.json",
        "%%not a reference%%",
        5,
        {"$ref": "#"},
    ],
)
def test_malformed_or_unresolved_nested_references_fail_closed(no_network, reference):
    schema = {
        "$defs": {
            "cycle": {"$ref": "#/$defs/loop"},
            "loop": {"$ref": "#/$defs/cycle"},
            "text": "not a schema",
        },
        "properties": {"value": {"$ref": reference}, "public": {"type": "string"}},
    }
    masked = mask_secret_refs({"value": {"nested": TEXT}, "public": "ok"}, cast(Any, schema))
    assert masked == {"value": "<redacted>", "public": "ok"}
    assert TEXT not in json.dumps(masked)


def test_nested_relative_references_resolve_against_their_own_documents():
    schema = {
        "$defs": {
            "inner": {"properties": {"secret": {"$ref": "#/$defs/secret"}}},
            "secret": SECRET,
            "embedded": {
                "$id": "urn:skm:test:embedded:v1",
                "$defs": {"leaf": {"x-skm-secret": True}},
                "properties": {"leaf": {"$ref": "#/$defs/leaf"}, "public": {"type": "string"}},
            },
        },
        "properties": {
            "chain": {"additionalProperties": {"$ref": "#/$defs/inner"}},
            "embedded": {"$ref": "urn:skm:test:embedded:v1"},
            "hooks": {"$ref": "urn:skm:settings:hooks:v1#/properties/subscriptions"},
        },
    }
    value = {
        "chain": {"a": {"secret": TEXT}, "b": {"secret": str(REF), "public": 1}},
        "embedded": {"leaf": TEXT, "public": "ok"},
        "hooks": {
            "test": {
                "kind": "webhook",
                "target": {"url": "https://example.invalid/skm", "secret": TEXT, "previous_secret": str(REF)},
            }
        },
    }
    masked = cast(Any, mask_secret_refs(cast(Any, value), cast(Any, schema)))
    assert masked["chain"] == {"a": {"secret": "<redacted>"}, "b": {"secret": str(REF), "public": 1}}
    assert masked["embedded"] == {"leaf": "<redacted>", "public": "ok"}
    assert masked["hooks"]["test"]["target"] == {
        "url": "https://example.invalid/skm",
        "secret": "<redacted>",
        "previous_secret": str(REF),
    }
    assert TEXT not in json.dumps(masked)


def embedded(leaf, identifier="urn:skm:test:embedded:v1"):
    """A resource whose ``#/$defs/leaf`` and ``#leaf`` name ``leaf``; its parent declares a colliding one."""
    return {
        "$id": identifier,
        "$defs": {"leaf": {"$anchor": "leaf", **leaf}},
        "properties": {
            "leaf": {"$ref": "#/$defs/leaf"},
            "anchored": {"$ref": "#leaf"},
            "public": {"type": "string"},
        },
    }


def placed(placement, resource):
    """A free-standing root that reaches ``resource`` in place under ``placement``."""
    shapes = {
        "properties": {"properties": {"value": resource}},
        "additionalProperties": {"additionalProperties": resource},
        "patternProperties": {"patternProperties": {"^val": resource}},
        "items": {"properties": {"value": {"items": resource}}},
        "prefixItems": {"properties": {"value": {"prefixItems": [resource]}}},
        "allOf": {"properties": {"value": {"allOf": [{"type": "object"}, resource]}}},
        "anyOf": {"properties": {"value": {"anyOf": [{"type": "object"}, resource]}}},
        "oneOf": {"properties": {"value": {"oneOf": [{"type": "string"}, resource]}}},
        "$ref pointer": {
            "$defs": {"resource": resource},
            "properties": {"value": {"$ref": "#/$defs/resource"}},
        },
        "$ref id": {"$defs": {"resource": resource}, "properties": {"value": {"$ref": resource["$id"]}}},
    }
    # The parent's own ``leaf`` and ``#leaf`` carry the opposite annotation.
    parent_leaf = {"x-skm-secret": True} if "x-skm-secret" not in resource["$defs"]["leaf"] else {}
    return {"$defs": {"leaf": {"$anchor": "leaf", **parent_leaf}}, **copy.deepcopy(shapes[placement])}


PLACEMENTS = [
    "properties",
    "additionalProperties",
    "patternProperties",
    "items",
    "prefixItems",
    "allOf",
    "anyOf",
    "oneOf",
    "$ref pointer",
    "$ref id",
]


def wrapped(placement, entry):
    return {"value": [entry] if placement in ("items", "prefixItems") else entry}


@pytest.mark.parametrize("placement", PLACEMENTS)
@pytest.mark.parametrize("identifier", ["urn:skm:test:embedded:v1", "https://example.invalid/embedded.json"])
def test_embedded_resource_entered_in_place_resolves_its_own_colliding_definitions(placement, identifier):
    schema = placed(placement, embedded({"x-skm-secret": True}, identifier))
    entry = {"leaf": TEXT, "anchored": TEXT, "public": "ok"}
    masked = mask_secret_refs(cast(Any, wrapped(placement, entry)), cast(Any, schema))
    redacted = {"leaf": "<redacted>", "anchored": "<redacted>", "public": "ok"}
    assert masked == wrapped(placement, redacted)
    assert TEXT not in json.dumps(masked)
    reference = {"leaf": str(REF), "anchored": str(REF), "public": "ok"}
    assert mask_secret_refs(cast(Any, wrapped(placement, reference)), cast(Any, schema)) == wrapped(
        placement, reference
    )


@pytest.mark.parametrize("placement", PLACEMENTS)
def test_embedded_public_definition_is_not_masked_by_a_colliding_parent_secret(placement):
    schema = placed(placement, embedded({"type": "string"}))
    entry = {"leaf": "public-leaf", "anchored": "public-anchor", "public": "ok"}
    assert mask_secret_refs(cast(Any, wrapped(placement, entry)), cast(Any, schema)) == wrapped(
        placement, entry
    )


def test_relative_embedded_ids_rebase_against_their_parent_resource():
    inner = {
        "$id": "nested/inner.json",
        "$defs": {"leaf": {"x-skm-secret": True}},
        "properties": {"leaf": {"$ref": "#/$defs/leaf"}, "sibling": {"$ref": "../../sibling.json"}},
    }
    schema = {
        "$id": "https://example.invalid/root/schema.json",
        "$defs": {
            "leaf": {"type": "string"},
            # inner's base is .../root/outer/nested/inner.json, so ../../sibling.json is .../root/sibling.json
            "sibling": {"$id": "sibling.json", "x-skm-secret": True},
            "decoy": {"$id": "../sibling.json", "type": "string"},  # the same reference from a missed base
        },
        "properties": {"outer": {"$id": "outer/", "properties": {"inner": inner}}},
    }
    value = {"outer": {"inner": {"leaf": TEXT, "sibling": TEXT}}}
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == {
        "outer": {"inner": {"leaf": "<redacted>", "sibling": "<redacted>"}}
    }


def test_a_reference_beside_an_id_resolves_inside_that_resource():
    schema = {
        "$defs": {"leaf": {"type": "string"}},
        "properties": {
            "value": {
                "$id": "urn:skm:test:self:v1",
                "$ref": "#/$defs/leaf",
                "$defs": {"leaf": {"x-skm-secret": True}},
            }
        },
    }
    assert mask_secret_refs({"value": TEXT}, cast(Any, schema)) == {"value": "<redacted>"}


@pytest.mark.parametrize(
    "reference", ["urn:skm:config:secret-ref:v1#", "urn:skm:test:alias:v1", "urn:skm:test:alias:v1#"]
)
def test_any_reference_reaching_the_secret_ref_schema_masks_literals(reference):
    schema = {
        "$defs": {"alias": {"$id": "urn:skm:test:alias:v1", "$ref": "urn:skm:config:secret-ref:v1"}},
        "properties": {"value": {"$ref": reference}, "public": {"type": "string"}},
    }
    assert mask_secret_refs({"value": TEXT, "public": "ok"}, cast(Any, schema)) == {
        "value": "<redacted>",
        "public": "ok",
    }
    assert mask_secret_refs({"value": str(REF)}, cast(Any, schema)) == {"value": str(REF)}


def test_dynamic_reference_is_followed_like_a_reference():
    schema = {
        "$defs": {"leaf": {"x-skm-secret": True}, "ref": SECRET},
        "properties": {
            "leaf": {"$dynamicRef": "#/$defs/leaf"},
            "ref": {"$dynamicRef": "#/$defs/ref"},
            "urn": {"$dynamicRef": "urn:skm:config:secret-ref:v1"},
            "public": {"$dynamicRef": "urn:skm:kernel:defs:v1"},
        },
    }
    value = {"leaf": TEXT, "ref": TEXT, "urn": TEXT, "public": "ok"}
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == {
        "leaf": "<redacted>",
        "ref": "<redacted>",
        "urn": "<redacted>",
        "public": "ok",
    }


def generic_list(root_item):
    """Draft 2020-12's generic list: the outermost ``$dynamicAnchor: item`` in the dynamic scope applies."""
    return {
        "$id": "https://example.invalid/root.json",
        "$ref": "list.json",
        "$defs": {
            "item": {"$dynamicAnchor": "item", **root_item},
            "list": {
                "$id": "list.json",
                "type": "array",
                "items": {"$dynamicRef": "#item"},
                "$defs": {"default": {"$dynamicAnchor": "item"}},
            },
        },
    }


def test_dynamic_reference_follows_the_dynamic_scope_like_validation(packaged_registry):
    secret = generic_list({"x-skm-secret": True})
    assert mask_secret_refs([TEXT, str(REF)], cast(Any, secret)) == ["<redacted>", str(REF)]
    public = generic_list({"type": "string"})
    # the validator selects the same declaration: the root's item, not the list's default
    resolver = packaged_registry.resolver_for(public)
    assert resolver.lookup("list.json").resolver.lookup("#item").contents == public["$defs"]["item"]
    assert mask_secret_refs(["public"], cast(Any, public)) == ["public"]


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": None},
        {"$dynamicRef": None},
        {"$dynamicRef": 5},
        {"$dynamicRef": "#/$defs/missing"},
        {"$id": []},
        {"$id": 5},
        {"allOf": None},
        {"anyOf": {"type": "object"}},
        {"oneOf": "x"},
        {"properties": None},
        {"properties": []},
        {"patternProperties": None},
        {"properties": {"value": "string"}},
        {"properties": {"value": 5}},
        {"properties": {"value": None}},
        {"additionalProperties": "string"},
        {"patternProperties": {"(": {"type": "string"}}},
        {"properties": {"value": {"$id": []}}},
        {"$id": "https://example.invalid/root.json", "properties": {"value": {"$id": "http://[invalid"}}},
        {"properties": {"value": {"$ref": None, "type": "string"}}},
        {"properties": {"value": {"items": "string"}}},
        {"properties": {"value": {"prefixItems": {"x-skm-secret": True}}}},
        {"$defs": {"target": {"properties": {"value": None}}}, "$ref": "#/$defs/target"},
        {"$defs": {"target": "not a schema"}, "properties": {"value": {"$dynamicRef": "#/$defs/target"}}},
    ],
)
def test_malformed_declarations_fail_closed_instead_of_raising(no_network, schema):
    value = {"value": [TEXT] if "items" in json.dumps(schema).lower() else TEXT}
    masked = mask_secret_refs(cast(Any, value), cast(Any, schema))
    assert TEXT not in json.dumps(masked)


def test_malformed_declarations_keep_their_public_siblings():
    schema = {
        "properties": {"value": {"$ref": None}, "other": "string", "public": {"type": "string"}},
        "patternProperties": {"^pub": {"type": "string"}},
    }
    value = {"value": TEXT, "other": TEXT, "public": "ok"}
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == {
        "value": "<redacted>",
        "other": "<redacted>",
        "public": "ok",
    }


@pytest.mark.parametrize(
    "declaration",
    [
        {"type": 5},
        {"type": ["string", "strnig"]},
        {"type": ["string", "string"]},
        {"required": "secret"},
        {"minLength": -1},
        {"minimum": "zero"},
        {"multipleOf": 0},
        {"enum": {}},
        {"dependentRequired": {"name": 5}},
        {"pattern": "("},
        {"allOf": []},
        {"$schema": "http://json-schema.org/draft-07/schema#"},
        *[
            {keyword: child}
            for keyword in (
                "items",
                "additionalProperties",
                "unevaluatedProperties",
                "unevaluatedItems",
                "contains",
            )
            for child in (5, None, [], "not a schema")
        ],
    ],
)
@pytest.mark.parametrize("keyword", [None, "$ref", "$dynamicRef", "anyOf"])
def test_invalid_keyword_values_mask_only_the_reached_member(declaration, keyword, offline):
    member = declaration
    if keyword in ("$ref", "$dynamicRef"):
        # const is instance data, not a subschema: the reference target needs its own admission check.
        member = {keyword: "#/$defs/data/const"}
    elif keyword == "anyOf":
        member = {"anyOf": [{}, declaration]}
    schema = {
        "$defs": {"data": {"const": declaration}},
        "properties": {"secret": member, "public": {"type": "string"}},
    }
    value = {"secret": TEXT, "public": "ok"}
    original = copy.deepcopy(schema)
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == {"secret": "<redacted>", "public": "ok"}
    assert schema == original
    assert value == {"secret": TEXT, "public": "ok"}
    assert offline == []


@pytest.mark.parametrize(
    "keyword", ["items", "additionalProperties", "unevaluatedProperties", "unevaluatedItems", "contains"]
)
@pytest.mark.parametrize("child", [5, None, [], "not a schema"])
def test_malformed_member_schema_shapes_fail_closed_on_a_scalar(keyword, child, offline):
    assert mask_secret_refs(TEXT, {keyword: child}) == "<redacted>"
    assert offline == []


@pytest.mark.parametrize("placement", ["direct", "property", "$ref", "$dynamicRef"])
def test_supported_dialect_empty_fragment_preserves_public_values(placement, offline):
    declaration = {"$schema": "https://json-schema.org/draft/2020-12/schema#", "type": "string"}
    if placement == "direct":
        assert mask_secret_refs("public", declaration) == "public"
    else:
        member = declaration if placement == "property" else {placement: "#/$defs/public"}
        schema = {"$defs": {"public": declaration}, "properties": {"value": member, "safe": {}}}
        value: dict[str, Any] = {"value": "public", "safe": "ok"}
        assert mask_secret_refs(value, schema) == value
    assert offline == []


@pytest.mark.parametrize("keyword", ["propertyNames", "contentSchema"])
@pytest.mark.parametrize("malformed", [False, True])
def test_deep_unapplied_schemas_preserve_public_scalars_and_reject_malformed_children(
    keyword, malformed, offline
):
    declaration: dict[str, Any] = {"type": 5} if malformed else {}
    for _ in range(500):
        declaration = {keyword: declaration}
    before = sys.getrecursionlimit()
    expected = "<redacted>" if malformed else "public"
    assert mask_secret_refs("public", declaration) == expected
    schema = {"$defs": {"target": declaration}, "properties": {"value": {"$ref": "#/$defs/target"}}}
    assert mask_secret_refs({"value": "public", "safe": "ok"}, schema) == {"value": expected, "safe": "ok"}
    assert sys.getrecursionlimit() == before
    assert offline == []


def test_unused_malformed_definitions_remain_lazy(offline):
    schema = {"$defs": {"unused": {"propertyNames": {"type": 5}}}, "type": "string"}
    assert mask_secret_refs("public", schema) == "public"
    assert offline == []


def test_schema_admission_does_not_cache_mutable_inputs_between_calls():
    declaration: dict[str, Any] = {"type": "string"}
    schema = {"properties": {"secret": declaration, "public": {"type": "string"}}}
    value = {"secret": TEXT, "public": "ok"}
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == value
    declaration["type"] = 5
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == {"secret": "<redacted>", "public": "ok"}
    declaration["type"] = "string"
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == value


@pytest.mark.parametrize("limit", [640, 4300, 0])
def test_frozen_leaf_schema_and_wide_literals_keep_valid_public_data(limit, offline):
    wide = 10**5000
    schema = freeze_json(
        {
            "properties": {
                "secret": {"x-skm-secret": True, "const": wide},
                "public": {"type": "integer", "maximum": wide, "enum": [wide, 0]},
            },
        },
        "value_schema",
    )  # KeySpec stores SettingsRegistry leaves in this representation.
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(limit)
    try:
        assert mask_secret_refs({"secret": TEXT, "public": wide}, cast(Any, schema)) == {
            "secret": "<redacted>",
            "public": wide,
        }
        assert sys.get_int_max_str_digits() == limit
    finally:
        sys.set_int_max_str_digits(before)
    assert offline == []


def test_schema_admission_is_cached_only_within_a_call(monkeypatch, packaged_registry):
    calls = []
    validate = packaged_registry.is_valid_schema

    def counted(schema):
        calls.append(schema)
        return validate(schema)

    monkeypatch.setattr(secrets, "_schemas", lambda: packaged_registry)
    monkeypatch.setattr(packaged_registry, "is_valid_schema", counted)
    leaf = {"type": "string"}
    schema = {"items": {"anyOf": [leaf, leaf]}}
    value = ["public"] * 100
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == value
    assert len(calls) == 3  # root, item, shared leaf; no full subtree check per item or reference visit
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == value
    assert len(calls) == 6


def test_schema_admission_work_is_bounded_and_resets_per_call(monkeypatch, offline):
    monkeypatch.setattr(secrets, "_SCHEMA_VISITS", 30)
    # Unknown keywords may contain arbitrary JSON; even such literal data must not cause an eager scan.
    schema = {"extension": [TEXT] * 100}
    assert mask_secret_refs({"secret": TEXT}, cast(Any, schema)) == "<redacted>"
    assert mask_secret_refs("public", {"type": "string"}) == "public"
    assert offline == []


@pytest.mark.parametrize("keyword", ["allOf", "anyOf", "oneOf"])
def test_composed_packaged_references_mask_plaintext_in_every_branch(keyword):
    webhook = {"$ref": "urn:skm:integrations:defs:v1#/$defs/hook_subscription/properties/target/oneOf/0"}
    schema = {keyword: [{"$ref": "#/$defs/public"}, webhook], "$defs": {"public": {"type": "object"}}}
    value = {"url": "https://hooks.example.com/skm", "secret": TEXT, "previous_secret": str(REF)}
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == {**value, "secret": "<redacted>"}


@pytest.fixture(scope="module")
def packaged_registry():
    return SchemaRegistry.load_default()


@pytest.fixture(scope="module")
def subscriptions_schema(packaged_registry):
    return cast(Any, packaged_registry.get("urn:skm:settings:hooks:v1"))["properties"]["subscriptions"]


def test_actual_explain_example_stays_reference_only(subscriptions_schema):
    example = Path("tests/fixtures/corpus/examples/config/explain-execution-review-max-rounds.json")
    data = json.loads(example.read_text(encoding="utf-8"))
    hooks = next(key for key in data["keys"] if key["key"] == "hooks.subscriptions")
    original = copy.deepcopy(hooks["value"])
    assert mask_secret_refs(hooks["value"], subscriptions_schema) == original
    assert hooks["value"] == original


@pytest.mark.parametrize(
    ("kind", "target"),
    [
        (
            "webhook",
            {
                "url": "https://hooks.example.com/skm",
                "secret": str(REF),
                "previous_secret": "secret://keyring/skm/previous",
                "headers": {"X-Public": "ok"},
            },
        ),
        ("webhook", {"url": "https://hooks.example.com/skm", "secret": str(REF), "previous_secret": None}),
        (
            "command",
            {
                "argv": ["synthetic-hook", "--check"],
                "cwd": "checkout",
                "env_allow": ["PATH"],
                "env_refs": {"TOKEN": str(REF), "FILE": "secret://file/~/secret"},
            },
        ),
        (
            "event_sink",
            {
                "sink_id": "synthetic_sink",
                "config": {"enabled": True, "nested": {"items": [None, "public", 42]}, "ratio": 1.5},
            },
        ),
    ],
)
def test_packaged_hook_target_alternatives_preserve_valid_data(
    subscriptions_schema, packaged_registry, kind, target
):
    value = {
        "test": {
            "class": "observation",
            "kind": kind,
            "execution_location": "host" if kind == "command" else "control_plane",
            "event_types": ["urn:skm:execution:event:run-finished:v1"],
            "target": target,
        }
    }
    assert packaged_registry.validate("urn:skm:settings:hooks:v1", {"subscriptions": value}) == ()
    original = copy.deepcopy(value)
    masked = mask_secret_refs(cast(Any, value), subscriptions_schema)
    assert masked == original
    assert value == original
    cast(Any, masked)["test"]["target"]["changed"] = True
    assert value == original


@pytest.mark.parametrize(
    ("kind", "target", "expected"),
    [
        (
            "webhook",
            {"url": "https://hooks.example.com/skm", "secret": TEXT, "previous_secret": str(REF)},
            {"url": "https://hooks.example.com/skm", "secret": "<redacted>", "previous_secret": str(REF)},
        ),
        (
            "webhook",
            {"secret": str(REF), "previous_secret": TEXT},
            {"secret": str(REF), "previous_secret": "<redacted>"},
        ),
        (
            "command",
            {"argv": ["synthetic-hook"], "env_refs": {"SAFE": str(REF), "BAD": TEXT}},
            {"argv": ["synthetic-hook"], "env_refs": {"SAFE": str(REF), "BAD": "<redacted>"}},
        ),
        (
            "command",
            {"env_refs": {"SAFE": str(REF), "BAD": TEXT}},
            {"env_refs": {"SAFE": str(REF), "BAD": "<redacted>"}},
        ),
        (
            "webhook",
            {"secret": TEXT, "previous_secret": TEXT, "env_refs": {"SAFE": str(REF), "BAD": TEXT}},
            {
                "secret": "<redacted>",
                "previous_secret": "<redacted>",
                "env_refs": {"SAFE": str(REF), "BAD": "<redacted>"},
            },
        ),
    ],
)
def test_packaged_hook_alternatives_mask_literals_even_when_no_branch_validates(
    subscriptions_schema, kind, target, expected
):
    value = {"test": {"kind": kind, "target": target}}
    original = copy.deepcopy(value)
    assert mask_secret_refs(cast(Any, value), subscriptions_schema) == {
        "test": {"kind": kind, "target": expected}
    }
    assert value == original


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
@pytest.mark.parametrize("reverse", [False, True])
def test_alternatives_combine_secret_annotations_from_original_data(keyword, reverse):
    branches = [
        {"properties": {"secret": SECRET, "url": {"type": "string"}}, "additionalProperties": False},
        {"properties": {"env_refs": {"additionalProperties": SECRET}}, "additionalProperties": False},
    ]
    value = {"secret": TEXT, "url": "https://example.invalid", "env_refs": {"SAFE": str(REF), "BAD": TEXT}}
    schema = {keyword: branches[::-1] if reverse else branches}
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == {
        "secret": "<redacted>",
        "url": "https://example.invalid",
        "env_refs": {"SAFE": str(REF), "BAD": "<redacted>"},
    }


def test_allof_still_combines_secret_annotations():
    schema = {
        "allOf": [
            {"properties": {"first": SECRET}},
            {"properties": {"second": SECRET}},
        ]
    }
    assert mask_secret_refs({"first": TEXT, "second": TEXT, "public": "ok"}, cast(Any, schema)) == {
        "first": "<redacted>",
        "second": "<redacted>",
        "public": "ok",
    }


# --- conditional, negated, dependent, unevaluated and contains applicators

DECLARED = {"properties": {"secret": SECRET}}


@pytest.mark.parametrize(
    "schema",
    [
        pytest.param({"if": DECLARED}, id="if"),
        pytest.param({"if": {"required": ["secret"]}, "then": DECLARED}, id="selected-then"),
        pytest.param({"if": {"required": ["absent"]}, "else": DECLARED}, id="selected-else"),
        # Validation would select the other branch; which one applies is not decided here.
        pytest.param({"if": {"required": ["absent"]}, "then": DECLARED}, id="unselected-then"),
        pytest.param({"if": {"required": ["secret"]}, "else": DECLARED}, id="unselected-else"),
        pytest.param({"not": {"required": ["absent"], **DECLARED}}, id="not"),
        pytest.param({"dependentSchemas": {"public": DECLARED}}, id="dependentSchemas"),
        pytest.param(
            {"properties": {"public": {"type": "string"}}, "unevaluatedProperties": SECRET}, id="unevaluated"
        ),
        pytest.param(
            {
                "allOf": [{"if": {"$ref": "#/$defs/entry"}, "then": {"$ref": "#/$defs/entry"}}],
                "$defs": {"entry": DECLARED},
            },
            id="referenced-conditional",
        ),
    ],
)
def test_object_applicators_mask_secret_declarations(schema):
    Draft202012Validator.check_schema(schema)
    for value in ({"secret": TEXT, "public": "ok"}, {"secret": {"nested": TEXT}, "public": "ok"}):
        masked = mask_secret_refs(cast(Any, value), cast(Any, schema))
        assert masked == {"secret": "<redacted>", "public": "ok"}
    assert mask_secret_refs({"secret": str(REF), "public": "ok"}, cast(Any, schema)) == {
        "secret": str(REF),
        "public": "ok",
    }


@pytest.mark.parametrize(
    ("schema", "first"),
    [
        pytest.param(
            {"prefixItems": [{"type": "string"}], "unevaluatedItems": SECRET}, "ok", id="unevaluated"
        ),
        pytest.param({"if": {"prefixItems": [{"const": "ok"}], "items": SECRET}}, "ok", id="if"),
        # Every item may be one that ``contains`` matches.
        pytest.param({"prefixItems": [{"const": "ok"}], "contains": SECRET}, "<redacted>", id="contains"),
    ],
)
def test_array_applicators_mask_secret_declarations(schema, first):
    Draft202012Validator.check_schema(schema)
    masked = mask_secret_refs(["ok", TEXT, str(REF), {"nested": TEXT}], cast(Any, schema))
    assert masked == [first, "<redacted>", str(REF), "<redacted>"]


def test_applicators_that_provably_do_not_apply_keep_public_data():
    value = {"secret": "public-value", "public": "ok"}
    for schema in (
        {"then": DECLARED, "else": DECLARED},  # ignored without ``if``
        {"dependentSchemas": {"absent": DECLARED}},
        {"additionalProperties": {"type": "string"}, "unevaluatedProperties": SECRET},
        {"properties": {"secret": {"type": "string"}, "public": {}}, "unevaluatedProperties": SECRET},
        {"patternProperties": {"^(secret|public)$": {"type": "string"}}, "unevaluatedProperties": SECRET},
    ):
        Draft202012Validator.check_schema(schema)
        assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == value
    for schema in (
        {"items": {"type": "string"}, "unevaluatedItems": SECRET},
        {"dependentSchemas": {"0": SECRET}},
    ):
        assert mask_secret_refs(["public-value"], cast(Any, schema)) == ["public-value"]


def remainder_schema(array, applied, unevaluated):
    if array:
        return {"prefixItems": [{}], "items": applied, "unevaluatedItems": unevaluated}
    return {
        "properties": {"public": {}},
        "additionalProperties": applied,
        "unevaluatedProperties": unevaluated,
    }


def remainder_value(array, extra):
    return ["ok", extra] if array else {"public": "ok", "extra": extra}


@pytest.mark.parametrize("array", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_failed_remaining_applicators_do_not_hide_unevaluated_secrets(array, nested):
    secret = {"type": "integer", "x-skm-secret": True}
    unevaluated = {"properties": {"secret": secret, "ref": secret}} if nested else secret
    schema = remainder_schema(array, {"type": "integer"}, unevaluated)
    extra = {"secret": TEXT, "ref": str(REF), "public": "ok"} if nested else TEXT
    masked = {"secret": "<redacted>", "ref": str(REF), "public": "ok"} if nested else "<redacted>"
    value = remainder_value(array, extra)
    Draft202012Validator.check_schema(schema)
    errors = {error.validator for error in Draft202012Validator(schema).iter_errors(value)}
    # The installed validator treats sibling items as evaluated even on failure. Inspect its
    # unevaluated annotations conservatively too, without claiming the two keywords are identical.
    assert errors == ({"type"} if array else {"type", "unevaluatedProperties"})
    assert mask_secret_refs(cast(Any, value), schema) == remainder_value(array, masked)
    assert value == remainder_value(array, extra)
    if not nested:
        reference = remainder_value(array, str(REF))
        assert mask_secret_refs(cast(Any, reference), schema) == reference


@pytest.mark.parametrize("array", [False, True])
@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
@pytest.mark.parametrize("reverse", [False, True])
def test_alternatives_merge_unevaluated_masks_after_a_failed_remaining_applicator(array, keyword, reverse):
    branch = remainder_schema(array, {"type": "integer"}, {"properties": {"secret": {"x-skm-secret": True}}})
    branches = [branch, {}]
    schema = {keyword: list(reversed(branches)) if reverse else branches}
    value = remainder_value(array, {"secret": TEXT, "public": "ok"})
    Draft202012Validator.check_schema(schema)
    assert Draft202012Validator(schema).is_valid(value)
    assert mask_secret_refs(cast(Any, value), schema) == remainder_value(
        array, {"secret": "<redacted>", "public": "ok"}
    )


@pytest.mark.parametrize("array", [False, True])
@pytest.mark.parametrize(
    "applied",
    [
        {"type": "string", "minLength": 100},
        {"type": "string", "maxLength": 1},
        {"type": "string", "pattern": "^absent$"},
        {"const": "other"},
        {"anyOf": [{"type": "integer"}]},
        {"$ref": "#/$defs/applied"},
        # Even a valid schema outside the bounded proof is inspected conservatively.
        {"type": "string", "minLength": 1},
    ],
)
def test_uncertain_remaining_applicators_inspect_unevaluated_annotations(array, applied):
    schema = remainder_schema(array, applied, {"x-skm-secret": True})
    schema["$defs"] = {"applied": {"type": "integer"}}
    Draft202012Validator.check_schema(schema)
    assert mask_secret_refs(cast(Any, remainder_value(array, TEXT)), schema) == remainder_value(
        array, "<redacted>"
    )


@pytest.mark.parametrize("array", [False, True])
@pytest.mark.parametrize(
    ("applied", "extra"),
    [
        (True, "public"),
        ({}, "public"),
        ({"type": "string"}, "public"),
        ({"type": ["integer", "string"]}, "public"),
        ({"type": "integer"}, 1.0),
        ({"type": "number"}, 1.5),
        ({"type": "boolean"}, False),
        ({"type": "null"}, None),
        ({"type": "object"}, {"public": "ok"}),
        ({"type": "array"}, ["public"]),
    ],
)
def test_proven_remaining_applicators_keep_public_members(array, applied, extra):
    schema = remainder_schema(array, applied, {"x-skm-secret": True})
    value = remainder_value(array, extra)
    Draft202012Validator.check_schema(schema)
    assert Draft202012Validator(schema).is_valid(value)
    assert mask_secret_refs(cast(Any, value), schema) == value


@pytest.mark.parametrize("array", [False, True])
@pytest.mark.parametrize(
    ("declared", "extra"),
    [
        ("null", TEXT),
        ("boolean", 0),
        ("integer", True),
        ("integer", 1.5),
        ("number", False),
        ("string", 1),
        ("array", {}),
        ("object", []),
    ],
)
def test_rejected_remaining_types_keep_unevaluated_secrets(array, declared, extra):
    schema = remainder_schema(array, {"type": declared}, {"x-skm-secret": True})
    value = remainder_value(array, extra)
    assert mask_secret_refs(cast(Any, value), schema) == remainder_value(array, "<redacted>")
    assert value == remainder_value(array, extra)


@pytest.mark.parametrize("array", [False, True])
@pytest.mark.parametrize(
    ("declared", "extra", "expected"),
    [
        ("string", TEXT, TEXT),
        (["integer", "string"], TEXT, TEXT),
        ("integer", 1.0, 1.0),
        ("integer", True, "<redacted>"),
        ("integer", TEXT, "<redacted>"),
        ("object", {"public": "ok"}, {"public": "ok"}),
        ("object", MappingProxyType({"secret": TEXT}), "<redacted>"),
    ],
)
def test_remaining_type_proof_accepts_frozen_declarations(array, declared, extra, expected):
    applied = MappingProxyType({"type": declared})
    schema = MappingProxyType(remainder_schema(array, applied, {"x-skm-secret": True}))
    value = remainder_value(array, extra)
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == remainder_value(array, expected)
    assert value == remainder_value(array, extra)


@pytest.mark.parametrize("array", [False, True])
@pytest.mark.parametrize(
    ("declared", "extra"),
    [("integer", 1), ("number", 1.5), ("string", TEXT), ("array", [TEXT]), ("object", {"secret": TEXT})],
)
def test_type_proof_keeps_non_json_subclass_values_fail_closed(array, declared, extra):
    subclass = type("Subclass", (type(extra),), {})(extra)
    schema = remainder_schema(array, {"type": declared}, {"x-skm-secret": True})
    assert mask_secret_refs(cast(Any, remainder_value(array, subclass)), schema) == remainder_value(
        array, "<redacted>"
    )


@pytest.mark.parametrize("array", [False, True])
def test_remaining_and_unevaluated_declarations_keep_both_nested_masks(array):
    schema = remainder_schema(array, {"properties": {"first": SECRET}}, {"properties": {"second": SECRET}})
    value = remainder_value(array, {"first": TEXT, "second": TEXT, "public": "ok"})
    assert mask_secret_refs(cast(Any, value), schema) == remainder_value(
        array, {"first": "<redacted>", "second": "<redacted>", "public": "ok"}
    )


@pytest.mark.parametrize("array", [False, True])
def test_unevaluated_false_after_a_remaining_applicator_requires_proven_applicability(array):
    value = remainder_value(array, TEXT)
    failed = remainder_schema(array, {"type": "integer"}, False)
    expected = value if array else remainder_value(array, "<redacted>")
    assert mask_secret_refs(cast(Any, value), failed) == expected
    unknown = remainder_schema(array, {"type": "string", "minLength": 1}, False)
    assert mask_secret_refs(cast(Any, value), unknown) == value
    # In an alternative, a failing declaration cannot erase the public data of another branch.
    assert mask_secret_refs(cast(Any, value), {"anyOf": [failed, {}]}) == value


@pytest.mark.parametrize("array", [False, True])
def test_unevaluated_fallback_uses_the_shared_visit_budget_offline(array, monkeypatch, offline):
    schema = remainder_schema(array, {"type": "integer"}, {"x-skm-secret": True})
    value = remainder_value(array, TEXT)
    monkeypatch.setattr(secrets, "_VISITS", 4)  # root, public member, applied member, unevaluated member
    assert mask_secret_refs(cast(Any, value), schema) == remainder_value(array, "<redacted>")
    monkeypatch.setattr(secrets, "_VISITS", 3)
    assert mask_secret_refs(cast(Any, value), schema) == "<redacted>"
    assert offline == []


def test_unevaluated_members_reachable_through_in_place_branches_are_masked_conservatively():
    # Validation would leave ``public`` evaluated by ``allOf``; without proof the annotation applies.
    schema = {"allOf": [{"properties": {"public": {"type": "string"}}}], "unevaluatedProperties": SECRET}
    assert mask_secret_refs({"public": TEXT}, cast(Any, schema)) == {"public": "<redacted>"}
    schema = {"contains": {"const": "ok"}, "unevaluatedItems": SECRET}
    assert mask_secret_refs(["ok", TEXT], cast(Any, schema)) == ["<redacted>", "<redacted>"]


def test_rejecting_unevaluated_keywords_mask_only_members_that_nothing_else_may_evaluate():
    closed = {"properties": {"public": {"type": "string"}}, "unevaluatedProperties": False}
    assert mask_secret_refs({"public": "ok", "extra": TEXT}, cast(Any, closed)) == {
        "public": "ok",
        "extra": "<redacted>",
    }
    assert mask_secret_refs(["ok", TEXT], {"prefixItems": [{}], "unevaluatedItems": False}) == [
        "ok",
        "<redacted>",
    ]
    # A branch may evaluate the member, so ``false`` is not proof that it is unknown data.
    composed = {"allOf": [{"properties": {"extra": {"type": "string"}}}], "unevaluatedProperties": False}
    assert mask_secret_refs({"extra": "ok"}, cast(Any, composed)) == {"extra": "ok"}
    contained = {"contains": {"const": "ok"}, "unevaluatedItems": False}
    assert mask_secret_refs(["ok"], cast(Any, contained)) == ["ok"]
    # An unselected or negated ``false`` and a ``false`` dependency of an absent property reject nothing here.
    for schema in (
        {"if": False, "then": False, "else": False},
        {"not": False},
        {"dependentSchemas": {"absent": False}},
    ):
        assert mask_secret_refs({"public": "ok"}, cast(Any, schema)) == {"public": "ok"}
    assert mask_secret_refs({"public": "ok"}, {"dependentSchemas": {"public": False}}) == "<redacted>"


@pytest.mark.parametrize(
    "schema",
    [
        {"if": "not a schema"},
        {"if": {}, "then": 5},
        {"if": {}, "else": ["not", "a", "schema"]},
        {"not": None},
        {"dependentSchemas": ["public"]},
        {"dependentSchemas": {"public": "not a schema"}},
        {"not": {"$ref": "#"}},
        {"if": {"$ref": "#/$defs/missing"}},
    ],
)
def test_malformed_or_cyclic_applicators_fail_closed(no_network, schema):
    assert mask_secret_refs({"public": TEXT}, cast(Any, schema)) == "<redacted>"


def test_malformed_member_applicators_mask_their_members(no_network):
    assert mask_secret_refs(
        {"public": "ok", "extra": TEXT}, {"properties": {"public": {}}, "unevaluatedProperties": 5}
    ) == {
        "public": "ok",
        "extra": "<redacted>",
    }
    assert mask_secret_refs([TEXT], {"contains": "not a schema"}) == ["<redacted>"]
    assert mask_secret_refs([TEXT], {"unevaluatedItems": None}) == ["<redacted>"]


def test_extracted_packaged_hook_conditional_masks_command_environment_literals(packaged_registry):
    conditional = {"$ref": "urn:skm:integrations:defs:v1#/$defs/hook_subscription/allOf/0"}
    target = {"argv": ["synthetic-hook"], "env_refs": {"SAFE": str(REF), "BAD": TEXT}}
    value = {"kind": "command", "execution_location": "host", "target": target}
    masked = mask_secret_refs(cast(Any, value), conditional)
    assert masked == {**value, "target": {**target, "env_refs": {"SAFE": str(REF), "BAD": "<redacted>"}}}
    assert TEXT not in json.dumps(masked)
    valid = {**value, "target": {**target, "env_refs": {"SAFE": str(REF)}}}
    assert mask_secret_refs(cast(Any, valid), conditional) == valid


# --- bounded traversal: reference cycles and branching expansion


class Runaway(BaseException):
    """Stops a walk the masker did not bound: ``except Exception`` in the masker cannot swallow it."""


@pytest.fixture
def lookups(monkeypatch):
    """Masker lookups, excluding the separate validator's bundled metaschema lookups, with a hard stop."""
    calls: list[str] = []
    resolver = type(Registry().resolver())  # ``referencing`` does not export the class itself
    lookup = resolver.lookup
    limit = 5 * secrets._VISITS  # a bounded walk makes at most 4 lookups per visit

    def counting(self, ref):
        if not self._base_uri.startswith("https://json-schema.org/draft/2020-12/"):
            calls.append(ref)
            if len(calls) > limit:
                raise Runaway
        return lookup(self, ref)

    mask_secret_refs("warm-up", {})  # load the packaged schemas before counting
    monkeypatch.setattr(resolver, "lookup", counting)
    return calls


@pytest.fixture
def offline(monkeypatch):
    """Counts, then refuses, every connection, URL or file opening; a swallowed refusal is still counted."""
    attempts: list[str] = []

    def refusing(name):
        def refuse(*_args, **_kwargs):
            attempts.append(name)
            raise AssertionError("secret masking must stay offline")

        return refuse

    mask_secret_refs("warm-up", {})  # loading the packaged schemas reads files; that is expected once
    for owner, name in [
        (socket.socket, "connect"),
        (socket, "getaddrinfo"),
        (socket, "create_connection"),
        (urllib.request, "urlopen"),
        (builtins, "open"),
        (io, "open"),
        (Path, "open"),
    ]:
        monkeypatch.setattr(owner, name, refusing(name))
    return attempts


def branches(composition, keyword, reference, width):
    return {composition: [{keyword: reference} for _ in range(width)]}


CYCLES = {
    "root": lambda c, k, w: branches(c, k, "#", w),
    "definition": lambda c, k, w: {
        "$defs": {"loop": branches(c, k, "#/$defs/loop", w)},
        "$ref": "#/$defs/loop",
    },
    "resources": lambda c, k, w: {
        "$id": "https://example.invalid/a.json",
        **branches(c, k, "b.json", w),
        "$defs": {"b": {"$id": "b.json", **branches(c, k, "a.json", w)}},
    },
    "dynamic anchor": lambda c, k, w: {
        "$id": "https://example.invalid/loop.json",
        "$dynamicAnchor": "node",
        **branches(c, k, "#node", w),
    },
}


@pytest.mark.parametrize("shape", sorted(CYCLES))
@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef"])
@pytest.mark.parametrize("composition", ["allOf", "anyOf", "oneOf"])
@pytest.mark.parametrize("width", [2, 3])
@pytest.mark.parametrize("value", [TEXT, {"value": TEXT, "public": "ok"}, [TEXT]])
def test_branching_reference_cycles_fail_closed_after_few_lookups(
    lookups, offline, shape, keyword, composition, width, value
):
    # Unbounded, the review's {"anyOf":[{"$dynamicRef":"#"}]*2} took about 2**33 lookups; stopping only at
    # the depth bound still takes over 64. A repeated context ends the walk on its first return.
    schema = CYCLES[shape](composition, keyword, width)
    original = copy.deepcopy(value)
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == "<redacted>"
    assert len(lookups) <= 16
    assert value == original
    assert offline == []


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef"])
def test_a_reference_cycle_masks_only_the_member_that_reaches_it(lookups, offline, keyword):
    schema = {
        "$defs": {"secret": SECRET},
        "properties": {
            "loop": branches("anyOf", keyword, "#/properties/loop", 2),
            "secret": {keyword: "#/$defs/secret"},
            "ref": {keyword: "#/$defs/secret"},
            "public": {"type": "string"},
            # recursion that consumes the instance is progress, not a cycle
            "tree": {"properties": {"token": SECRET, "next": {keyword: "#/properties/tree"}}},
        },
    }
    value = {
        "loop": {"nested": "public"},
        "secret": TEXT,
        "ref": str(REF),
        "public": "ok",
        "tree": {"token": TEXT, "next": {"token": str(REF), "next": {"token": TEXT}}},
    }
    original = copy.deepcopy(value)
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == {
        "loop": "<redacted>",
        "secret": "<redacted>",
        "ref": str(REF),
        "public": "ok",
        "tree": {"token": "<redacted>", "next": {"token": str(REF), "next": {"token": "<redacted>"}}},
    }
    assert value == original
    assert len(lookups) <= 32
    assert offline == []


def diamonds(levels):
    """``levels`` pairs of alternatives without a cycle: 2**levels paths reach the last definition."""
    defs: dict[str, Any] = {f"n{i}": branches("anyOf", "$ref", f"#/$defs/n{i + 1}", 2) for i in range(levels)}
    defs[f"n{levels}"] = {"type": "string"}
    return {"$defs": defs, "properties": {"value": {"$ref": "#/$defs/n0"}, "public": {"type": "string"}}}


def nested(levels):
    value: Any = TEXT
    for _ in range(levels):
        value = [value]
    return value


# every level of the instance doubles the work, so the size of the data alone does not bound it
LISTS = {**branches("anyOf", "$ref", "#/$defs/list", 2), "$defs": {"list": {"items": {"$ref": "#"}}}}
PAIR = {"value": "ok", "public": "ok"}


@pytest.mark.parametrize(
    ("value", "schema", "expected"),
    [
        (PAIR, diamonds(4), PAIR),
        (PAIR, diamonds(30), "<redacted>"),  # 2**30 paths, each within the depth bound
        (PAIR, diamonds(40), {"value": "<redacted>", "public": "ok"}),  # the depth bound masks the member
        (nested(3), LISTS, nested(3)),
        (nested(30), LISTS, "<redacted>"),
    ],
    ids=["small diamonds", "exponential diamonds", "too deep diamonds", "shallow list", "deep list"],
)
def test_branching_expansion_without_a_cycle_stops_at_the_visit_budget(
    lookups, offline, value, schema, expected
):
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == expected
    assert len(lookups) <= 4 * secrets._VISITS
    assert offline == []


def test_each_call_has_its_own_budget_and_an_exhausted_one_masks_everything(monkeypatch):
    schema = {"properties": {"secret": SECRET, "public": {"type": "string"}}}
    value = {"secret": TEXT, "public": "ok"}
    expected = {"secret": "<redacted>", "public": "ok"}
    monkeypatch.setattr(secrets, "_VISITS", 3)  # the root and its two members
    for _ in range(3):  # a finished call leaves nothing behind for the next one
        assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == expected
    monkeypatch.setattr(secrets, "_VISITS", 2)
    assert mask_secret_refs(cast(Any, value), cast(Any, schema)) == "<redacted>"


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef"])
def test_repeated_references_without_a_cycle_are_not_mistaken_for_one(lookups, keyword):
    schema = {
        "$defs": {
            "secret": SECRET,
            "node": {
                "properties": {
                    "token": {keyword: "#/$defs/secret"},
                    "label": {"type": "string"},
                    "children": {"items": {keyword: "#/$defs/node"}},
                }
            },
        },
        "allOf": [{keyword: "#/$defs/node"}, {keyword: "#/$defs/node"}],
        "anyOf": [{keyword: "#/$defs/node"}, {"$ref": "#/$defs/node"}],
    }

    def tree(levels):
        children = [tree(levels - 1)] if levels else []
        return {"token": TEXT if levels % 2 else str(REF), "label": f"level-{levels}", "children": children}

    def masked(levels):
        children = [masked(levels - 1)] if levels else []
        token = "<redacted>" if levels % 2 else str(REF)
        return {"token": token, "label": f"level-{levels}", "children": children}

    assert mask_secret_refs(cast(Any, tree(6)), cast(Any, schema)) == masked(6)
    assert len(lookups) < 4 * secrets._VISITS


def extensible_tree(token):
    """A tree whose node the root rebinds through ``$dynamicAnchor``, as in Draft 2020-12's examples."""
    return {
        "$id": "https://example.invalid/root.json",
        "$dynamicAnchor": "node",
        "$ref": "tree.json",
        "properties": {"token": token},
        "$defs": {
            "tree": {
                "$id": "tree.json",
                "$dynamicAnchor": "node",
                "properties": {"label": {"type": "string"}, "children": {"items": {"$dynamicRef": "#node"}}},
            }
        },
    }


def branching_tree(levels):
    children = [branching_tree(levels - 1), branching_tree(levels - 1)] if levels else []
    return {"token": TEXT, "label": f"level-{levels}", "children": children}


def test_dynamic_bindings_apply_again_at_every_level_of_the_instance(lookups, offline, packaged_registry):
    secret = extensible_tree({"x-skm-secret": True})
    resolver = packaged_registry.resolver_for(secret)
    assert resolver.lookup("tree.json").resolver.lookup("#node").contents == secret  # outermost wins

    def masked(levels):
        children = [masked(levels - 1), masked(levels - 1)] if levels else []
        return {"token": "<redacted>", "label": f"level-{levels}", "children": children}

    assert mask_secret_refs(cast(Any, branching_tree(5)), cast(Any, secret)) == masked(5)
    public = extensible_tree({"type": "string"})
    assert mask_secret_refs(cast(Any, branching_tree(5)), cast(Any, public)) == branching_tree(5)
    assert offline == []


def test_concurrent_calls_keep_their_own_cycles_and_budgets(monkeypatch):
    monkeypatch.setattr(secrets, "_VISITS", 2_000)  # small enough that exhausting it is cheap
    cyclic = {
        "properties": {"loop": branches("anyOf", "$dynamicRef", "#/properties/loop", 2), "public": {}},
    }
    cases = [
        ({"loop": TEXT, "public": "ok"}, cyclic, {"loop": "<redacted>", "public": "ok"}),
        (PAIR, diamonds(30), "<redacted>"),
        (branching_tree(3), extensible_tree({"x-skm-secret": True}), None),
        (branching_tree(3), extensible_tree({"type": "string"}), branching_tree(3)),
    ]
    expected = [mask_secret_refs(cast(Any, value), cast(Any, schema)) for value, schema, _ in cases]
    assert [result for _, _, result in cases if result is not None] == [expected[0], expected[1], expected[3]]
    assert TEXT not in json.dumps(expected[2])

    def run(index):
        value, schema, _ = cases[index % len(cases)]
        return mask_secret_refs(cast(Any, value), cast(Any, schema))

    calls = 12 * len(cases)  # a dynamic anchor costs a registry crawl per call (~0.1 s), so keep this small
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, range(calls)))
    assert results == [expected[index % len(cases)] for index in range(calls)]
