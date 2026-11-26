"""Load-time reference checks: dependentSchemas loops, $dynamicRef, non-schema targets, nested ``$id``
(§3.3)."""

import json
import socket
import sys
from functools import partial
from pathlib import Path
from typing import Any, NoReturn

import pytest

from skm.platform.schema.findings import SchemaLoadError
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator

DIALECT = "https://json-schema.org/draft/2020-12/schema"
A = "urn:skm:shop:a:v1"


def schema(urn: str, **body: Any) -> dict[str, Any]:
    return {"$schema": DIALECT, "$id": urn, **body}


def load(root: Path, body: dict[str, Any]) -> SchemaRegistry:
    target = root / "shop" / "a.v1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema(A, **body)), encoding="utf-8")
    return SchemaRegistry.load(root)


def rejection(root: Path, body: dict[str, Any]) -> SchemaLoadError:
    with pytest.raises(SchemaLoadError) as raised:
        load(root, body)
    return raised.value


def has(error: SchemaLoadError, pointer: str, code: str, text: str) -> bool:
    return any(
        p.path == "shop/a.v1.json"
        and (p.issue.pointer, p.issue.code) == (pointer, code)
        and text in p.issue.message
        for p in error.problems
    )


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("the schema registry must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# --- dependentSchemas is an in-place applicator

LOOP = {"$ref": "#"}
DEPENDENT_LOOPS = {
    "direct": ({"flag": LOOP}, "/dependentSchemas/flag/$ref"),
    "all-of": ({"flag": {"allOf": [LOOP]}}, "/dependentSchemas/flag/allOf/0/$ref"),
    "any-of": ({"flag": {"anyOf": [LOOP]}}, "/dependentSchemas/flag/anyOf/0/$ref"),
    "one-of": ({"flag": {"oneOf": [LOOP]}}, "/dependentSchemas/flag/oneOf/0/$ref"),
    "if": ({"flag": {"if": LOOP}}, "/dependentSchemas/flag/if/$ref"),
    "then": ({"flag": {"then": LOOP}}, "/dependentSchemas/flag/then/$ref"),
    "else": ({"flag": {"else": LOOP}}, "/dependentSchemas/flag/else/$ref"),
}


@pytest.mark.parametrize("case", sorted(DEPENDENT_LOOPS))
def test_a_loop_through_dependent_schemas_is_refused_at_load(case: str, tmp_path: Path) -> None:
    dependent, pointer = DEPENDENT_LOOPS[case]
    error = rejection(tmp_path, {"dependentSchemas": dependent})
    assert has(error, pointer, "$ref", "circular"), error.problems


def test_a_loop_entered_through_a_reference_and_closed_by_dependent_schemas_is_refused(
    tmp_path: Path,
) -> None:
    body = {
        "$ref": "#/$defs/loop/dependentSchemas/flag",
        "$defs": {"loop": {"dependentSchemas": {"flag": {"$ref": "#/$defs/loop"}}}},
    }
    error = rejection(tmp_path, body)
    assert has(error, "/$defs/loop/dependentSchemas/flag/$ref", "$ref", "circular"), error.problems


def test_dependent_schemas_that_descend_into_the_instance_stay_valid(tmp_path: Path) -> None:
    body = {"dependentSchemas": {"flag": {"properties": {"next": LOOP}}}}
    registry = load(tmp_path, body)
    assert registry.validate(A, {"flag": 1, "next": {"flag": 1, "next": {}}}) == ()


# --- $dynamicRef is checked like $ref


def test_dynamic_ref_to_a_missing_urn_is_refused_at_load(tmp_path: Path) -> None:
    error = rejection(tmp_path, {"properties": {"x": {"$dynamicRef": "urn:skm:shop:missing:v1"}}})
    assert has(error, "/properties/x/$dynamicRef", "$dynamicRef", "unresolved"), error.problems


def test_dynamic_self_reference_without_progress_is_refused_at_load(tmp_path: Path) -> None:
    error = rejection(tmp_path, {"$dynamicRef": "#"})
    assert has(error, "/$dynamicRef", "$dynamicRef", "circular"), error.problems


def test_external_dynamic_reference_is_refused_without_a_connection(tmp_path: Path, no_network: None) -> None:
    error = rejection(tmp_path, {"items": {"$dynamicRef": "https://example.com/s.json"}})
    assert has(error, "/items/$dynamicRef", "$dynamicRef", "forbidden"), error.problems


def test_a_dynamic_cycle_that_exists_only_in_another_documents_scope_is_refused(tmp_path: Path) -> None:
    """``a`` alone is fine; reached from ``z`` (outermost ``$dynamicAnchor n``) its ``#n`` lands back
    in ``z``."""
    files = {
        "shop/a.v1.json": schema(A, **{"$dynamicRef": "#n", "$defs": {"stop": {"$dynamicAnchor": "n"}}}),
        "shop/z.v1.json": schema("urn:skm:shop:z:v1", **{"$dynamicAnchor": "n", "$ref": A}),
    }
    for relative, content in files.items():
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(SchemaLoadError) as raised:
        SchemaRegistry.load(tmp_path)
    closing = {(p.path, p.issue.pointer) for p in raised.value.problems if "circular" in p.issue.message}
    assert closing
    assert closing <= {("shop/a.v1.json", "/$dynamicRef"), ("shop/z.v1.json", "/$ref")}, raised.value.problems


def test_scopes_with_the_same_documents_in_another_order_are_not_conflated(tmp_path: Path) -> None:
    """``m`` is walked with scope [a, z, a] (anchor n -> a, harmless) before [a, z] (anchor n -> z, a
    loop)."""
    stop = {"stop": {"$dynamicAnchor": "n"}}
    child = {"$ref": "urn:skm:shop:z:v1"}
    files = {
        "shop/a.v1.json": schema(
            A, **{"$defs": stop, "$ref": "urn:skm:shop:m:v1", "properties": {"child": child}}
        ),
        "shop/m.v1.json": schema("urn:skm:shop:m:v1", **{"$defs": stop, "$dynamicRef": "#n"}),
        "shop/z.v1.json": schema("urn:skm:shop:z:v1", **{"$dynamicAnchor": "n", "$ref": A}),
    }
    for relative, content in files.items():
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(SchemaLoadError) as raised:
        SchemaRegistry.load(tmp_path)
    closing = {(p.path, p.issue.pointer) for p in raised.value.problems if "circular" in p.issue.message}
    assert closing
    assert closing <= {
        ("shop/a.v1.json", "/$ref"),
        ("shop/m.v1.json", "/$dynamicRef"),
        ("shop/z.v1.json", "/$ref"),
    }, raised.value.problems


def test_a_dynamic_anchor_entered_under_another_base_is_walked_again(tmp_path: Path) -> None:
    """``a.entry`` is harmless under base a (finished first) but its ``#/$defs/end`` means ``m.end``
    via ``m``."""
    m = "urn:skm:shop:m:v1"
    files = {
        "shop/a.v1.json": schema(
            A,
            **{
                "$ref": "#/$defs/entry",
                "$defs": {"entry": {"$dynamicAnchor": "n", "$ref": "#/$defs/end"}, "end": {}},
                "properties": {"child": {"$ref": m}},
            },
        ),
        "shop/m.v1.json": schema(
            m,
            **{
                "$ref": "#/$defs/end",
                "$defs": {"stop": {"$dynamicAnchor": "n"}, "end": {"$dynamicRef": "#n"}},
            },
        ),
    }
    for relative, content in files.items():
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(SchemaLoadError) as raised:
        SchemaRegistry.load(tmp_path)
    closing = {(p.path, p.issue.pointer) for p in raised.value.problems if "circular" in p.issue.message}
    assert closing
    assert closing <= {
        ("shop/a.v1.json", "/$defs/entry/$ref"),
        ("shop/m.v1.json", "/$defs/end/$dynamicRef"),
    }, raised.value.problems


def test_the_same_documents_without_the_looping_anchor_are_accepted(tmp_path: Path) -> None:
    stop = {"stop": {"$dynamicAnchor": "n"}}
    files = {
        "shop/a.v1.json": schema(A, **{"$defs": stop, "$ref": "urn:skm:shop:m:v1"}),
        "shop/m.v1.json": schema("urn:skm:shop:m:v1", **{"$defs": stop, "$dynamicRef": "#n"}),
    }
    for relative, content in files.items():
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(json.dumps(content), encoding="utf-8")
    registry = SchemaRegistry.load(tmp_path)
    assert registry.validate(A, {}) == ()
    assert registry.validate("urn:skm:shop:m:v1", {}) == ()


def test_the_same_dynamic_reference_alone_is_accepted(tmp_path: Path) -> None:
    body = {"$dynamicRef": "#n", "$defs": {"stop": {"$dynamicAnchor": "n"}}}
    assert load(tmp_path, body).validate(A, {}) == ()


def test_a_resolvable_local_dynamic_reference_validates(tmp_path: Path) -> None:
    node = {"$dynamicAnchor": "node", "type": "object", "properties": {"child": {"$dynamicRef": "#node"}}}
    registry = load(tmp_path, {"$defs": {"n": node}, "$ref": "#/$defs/n"})
    assert registry.validate(A, {"child": {"child": {}}}) == ()
    issues = registry.validate(A, {"child": {"child": 1}})
    assert [(i.pointer, i.code) for i in issues] == [("/child/child", "type")]


# --- the target of a reference must be a schema

NOT_SCHEMAS = {
    "string": {"title": "x", "$ref": "#/title"},
    "array": {"required": ["a"], "$ref": "#/required"},
    "number": {"minimum": 3, "$ref": "#/minimum"},
    "invalid-schema-object": {"properties": {"type": {"type": "string"}}, "$ref": "#/properties"},
}


@pytest.mark.parametrize("case", sorted(NOT_SCHEMAS))
def test_a_reference_to_a_non_schema_is_refused_at_load(case: str, tmp_path: Path) -> None:
    error = rejection(tmp_path, NOT_SCHEMAS[case])
    assert has(error, "/$ref", "$ref", "not a schema"), error.problems


def test_references_to_object_and_boolean_schemas_still_work(tmp_path: Path) -> None:
    body = {
        "$defs": {"text": {"type": "string"}, "never": False, "any": True},
        "properties": {
            "x": {"$ref": "#/$defs/text"},
            "y": {"$ref": "#/$defs/never"},
            "z": {"$ref": "#/$defs/any"},
        },
    }
    registry = load(tmp_path, body)
    assert registry.validate(A, {"x": "ok", "z": 1}) == ()
    assert [i.pointer for i in registry.validate(A, {"x": 1, "y": 1})] == ["/x", "/y"]


# --- a nested $id starts its own resolution scope

NESTED = {
    "properties": {
        "x": {
            "$id": "urn:skm:shop:a-part:v1",
            "$defs": {"s": {"type": "string"}},
            "$ref": "#/$defs/s",
        }
    }
}


def test_a_fragment_inside_a_nested_resource_resolves_against_that_resource(tmp_path: Path) -> None:
    registry = load(tmp_path, NESTED)
    assert registry.validate(A, {"x": "ok"}) == ()
    assert [(i.pointer, i.code) for i in registry.validate(A, {"x": 1})] == [("/x", "type")]


def test_a_nested_resource_does_not_see_the_defs_of_its_parent(tmp_path: Path) -> None:
    body = {
        "$defs": {"outer": {"type": "string"}},
        "properties": {"x": {"$id": "urn:skm:shop:a-part:v1", "$ref": "#/$defs/outer"}},
    }
    error = rejection(tmp_path, body)
    assert has(error, "/properties/x/$ref", "$ref", "unresolved"), error.problems


def test_a_loop_inside_a_nested_resource_is_reported_against_the_file(tmp_path: Path) -> None:
    part = {"$id": "urn:skm:shop:a-part:v1", "allOf": [{"$ref": "urn:skm:shop:a-part:v1"}]}
    body = {"properties": {"x": part}}
    error = rejection(tmp_path, body)
    assert has(error, "/properties/x/allOf/0/$ref", "$ref", "circular"), error.problems


# --- a wide integer literal behind a reference is quoted without raising

WIDE = 7 * (10**5001 - 1) // 9  # 5001 sevens: wider than the default int-to-text limit
SHOWN = "7" * 79 + "…"
BIG = "urn:skm:shop:big:v1"


@pytest.fixture
def wide_literals(tmp_path: Path) -> SchemaRegistry:
    """``a`` reaches wide literals in another document, in a nested ``$id`` resource and in a ``oneOf``."""
    files = {
        "shop/big.v1.json": schema(BIG, **{"$defs": {"huge": {"const": WIDE}, "ceiling": {"maximum": WIDE}}}),
        "shop/a.v1.json": schema(
            A,
            type="object",
            properties={
                "const": {"$ref": f"{BIG}#/$defs/huge"},
                "part": {
                    "$id": "urn:skm:shop:a-part:v1",
                    "$defs": {"w": {"enum": [WIDE]}},
                    "$ref": "#/$defs/w",
                },
                "choice": {"oneOf": [{"$ref": f"{BIG}#/$defs/ceiling"}, {"type": "integer"}]},
            },
        ),
    }
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)  # json reads a literal past the limit only when the limit is off
    try:
        for relative, content in files.items():
            (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / relative).write_text(json.dumps(content), encoding="utf-8")
        return SchemaRegistry.load(tmp_path)
    finally:
        sys.set_int_max_str_digits(before)


@pytest.mark.parametrize("limit", [640, 4300, 0], ids=["lowest", "default", "off"])
def test_a_wide_literal_in_a_referenced_or_nested_resource_is_quoted_without_raising(
    wide_literals: SchemaRegistry, limit: int
) -> None:
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(limit)
    try:
        direct = SchemaValidator(wide_literals.get(A), wide_literals.registry)  # dialect_free copies
        for validate in (partial(wide_literals.validate, A), direct.issues):
            assert validate({"const": WIDE, "part": WIDE, "choice": WIDE + 1}) == ()
            found = validate({"const": WIDE + 1, "part": 5, "choice": WIDE})
            assert [(i.pointer, i.code) for i in found] == [
                ("/choice", "oneOf"),
                ("/const", "const"),
                ("/part", "enum"),
            ]
            assert found[0].message.startswith(f"{SHOWN} is valid under each of ")
            assert found[1].message == f"{SHOWN} was expected"
            assert found[2].message == f"5 is not one of [{SHOWN}]"
        loaded: Any = wide_literals.get(BIG)
        assert type(loaded["$defs"]["huge"]["const"]) is int  # the loaded document is kept
    finally:
        sys.set_int_max_str_digits(before)
