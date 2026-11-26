"""Key metadata types and the key-spec / secret-ref metaschemas (settings §B.1, REG-03)."""

import copy
import json
import pickle
from collections.abc import Iterator
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import (
    BASE_LEVELS,
    CHAIN_LEVELS,
    CHAIN_OPEN_LEVELS,
    CHAIN_STORED_LEVELS,
    EXPLICIT_LEVELS,
    LOCK_LEVELS,
    MISSING,
    SHARED_LEVELS,
    STORED_LEVELS,
    Chain,
    FrozenDict,
    FrozenList,
    KeySpec,
    Level,
    MergeStrategy,
    NarrowDirection,
    NarrowSpec,
    Reload,
    Sensitivity,
    UiHints,
    copy_json,
    freeze_json,
)
from skm.platform.config.secrets import SecretRef

SCHEMAS = Path(__file__).resolve().parents[4] / "src/skm/schemas"
KEY_SPEC = json.loads((SCHEMAS / "config/key-spec.v1.json").read_text())
SECRET_REF = json.loads((SCHEMAS / "config/secret-ref.v1.json").read_text())
X_SKM: dict[str, Any] = {
    "chain": "work",
    "levels": ["instance", "workspace", "project", "plan", "run"],
    "merge": "narrow",
    "reload": "run_frozen",
    "override": False,
    "sensitivity": "public",
    "portable": True,
    "lockable": True,
    "nullable": False,
    "pack": True,
    "confirm": False,
    "narrow": {"direction": "min"},
    "ui": {"group": "Review", "order": 10, "widget": "number"},
}
SCHEMA = {"type": "integer", "minimum": 1, "maximum": 10}


def metaschema_errors(instance: object) -> list[str]:
    return [error.message for error in Draft202012Validator(KEY_SPEC).iter_errors(cast(Any, instance))]


def build(**overrides: Any) -> KeySpec:
    x_skm = {**copy.deepcopy(X_SKM), **overrides}
    return KeySpec.from_metadata(
        key="execution.review.max_rounds",
        section="execution",
        owner="execution",
        value_schema=SCHEMA,
        default=2,
        description="Review rounds.",
        x_skm=x_skm,
    )


# --- metaschema key-spec ---


def test_metaschema_is_a_valid_schema_and_accepts_the_reference_metadata() -> None:
    Draft202012Validator.check_schema(KEY_SPEC)
    assert metaschema_errors(X_SKM) == []


def test_metaschema_accepts_every_optional_field() -> None:
    full = {
        **X_SKM,
        "path": False,
        "write_permission": "hook.manage",
        "validators": ["execution.rounds"],
        "deprecated": {"since": "1.2", "replacement": "execution.review.rounds", "until": "2.0"},
        "narrow": {"direction": "min", "unlimited": 0},
        "ui": {"group": "Review", "order": 0, "widget": "number", "advanced": True, "title": "Rounds"},
    }
    assert metaschema_errors(full) == []


@pytest.mark.parametrize("field", sorted(KEY_SPEC["required"]))
def test_metaschema_requires_every_declared_field(field: str) -> None:
    broken = {key: value for key, value in X_SKM.items() if key != field}
    assert metaschema_errors(broken)


@pytest.mark.parametrize(
    "patch",
    [
        {"unknown_field": True},
        {"chain": "global"},
        {"levels": []},
        {"levels": ["default"]},
        {"levels": ["pack"]},
        {"levels": ["invocation"]},
        {"levels": ["run_bundle"]},  # provenance-only levels are not storable
        {"levels": ["process"]},
        {"levels": ["instance", "instance"]},
        {"merge": "overwrite"},
        {"reload": "never"},
        {"sensitivity": "private"},
        {"override": "yes"},
        {"nullable": None},
        {"write_permission": "Hook-Manage"},
        {"write_permission": "manage"},
        {"validators": ["a", "a"]},
        {"validators": ["NoDot"]},
        {"narrow": {"direction": "sum"}},
        {"narrow": {"order": ["only_one"]}},
        {"narrow": {"order": ["a", "a"]}},
        {"narrow": {"extra": 1}},
        {"deprecated": {"replacement": "a.b"}},
        {"deprecated": {"since": "1", "extra": 1}},
        {"ui": {"group": "", "order": 1, "widget": "number"}},
        {"ui": {"group": "G", "order": -1, "widget": "number"}},
        {"ui": {"group": "G", "order": 1, "widget": "slider"}},
        {"ui": {"group": "G", "order": 1}},
        {"ui": {"group": "G", "order": 1, "widget": "number", "color": "red"}},
    ],
    ids=lambda patch: next(iter(patch)) + ":" + json.dumps(next(iter(patch.values())))[:40],
)
def test_metaschema_rejects_invalid_metadata(patch: dict[str, Any]) -> None:
    assert metaschema_errors({**X_SKM, **patch})


@pytest.mark.parametrize(
    "section",
    [
        {"id": "execution", "owner": "execution", "title": "Execution"},
        {"id": "plugins.acme", "owner": "extensions", "title": "Acme"},
        {"id": "plugins.acme.sub", "owner": "extensions", "title": "Acme sub"},
        {"id": "x", "owner": "ab", "title": "t"} | {"id": "ab"},
        {
            "id": "logging",
            "owner": "platform",
            "title": "L",
            "validators": [{"id": "a.b", "keys": ["k"], "rule": "r"}],
        },
    ],
)
def test_section_metaschema_accepts(section: dict[str, Any]) -> None:
    validator = Draft202012Validator({"$ref": "#/$defs/section", "$defs": KEY_SPEC["$defs"]})
    assert list(validator.iter_errors(section)) == []


@pytest.mark.parametrize(
    "section",
    [
        {"id": "Execution", "owner": "execution", "title": "t"},
        {"id": "a", "owner": "execution", "title": "t"},
        {"id": "plugins.", "owner": "extensions", "title": "t"},
        {"id": "execution", "owner": "Execution", "title": "t"},
        {"id": "execution", "owner": "execution", "title": ""},
        {"id": "execution", "owner": "execution", "title": "t", "extra": 1},
        {"id": "execution", "owner": "execution"},
        {
            "id": "e",
            "owner": "execution",
            "title": "t",
            "validators": [{"id": "a.b", "keys": [], "rule": "r"}],
        },
    ],
)
def test_section_metaschema_rejects(section: dict[str, Any]) -> None:
    validator = Draft202012Validator({"$ref": "#/$defs/section", "$defs": KEY_SPEC["$defs"]})
    assert list(validator.iter_errors(section))


# --- metaschema secret-ref ---


@pytest.mark.parametrize(
    "text",
    [
        "secret://env/SKM_DATABASE_URL",
        "secret://env/_X",
        "secret://file/~/.local/state/skm/secrets/token-pepper",
        "secret://file//abs/path",
        "secret://keyring/skm-prod/api-token",
        *SECRET_REF["examples"],
    ],
)
def test_secret_ref_schema_accepts(text: str) -> None:
    assert list(Draft202012Validator(SECRET_REF).iter_errors(text)) == []


@pytest.mark.parametrize(
    "value",
    [
        "TOKEN",
        "secret://env/lower",
        "secret://env/",
        "secret://env/1ABC",
        "secret://env/" + "A" * 129,
        "secret://file/",
        "secret://file/has space",
        "secret://keyring/service",
        "secret://keyring/a/",
        "secret://keyring/a b/c",
        "secret://vault/x",
        None,
        5,
        {"scheme": "env"},
    ],
)
def test_secret_ref_schema_rejects(value: object) -> None:
    assert list(Draft202012Validator(SECRET_REF).iter_errors(cast(Any, value)))


def _leaves(node: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for name, child in node.get("properties", {}).items():
        if "x-skm" in child:
            yield name, child
        else:
            yield from ((f"{name}.{sub}", leaf) for sub, leaf in _leaves(child))


def test_every_shipped_settings_leaf_satisfies_the_metaschema_and_builds_a_spec() -> None:
    count = 0
    for path in sorted((SCHEMAS / "settings").glob("*.v1.json")):
        if path.name == "document.v1.json":
            continue
        document = json.loads(path.read_text())
        if "x-skm-section" not in document:
            continue
        section = document["x-skm-section"]
        for name, leaf in _leaves(document):
            assert metaschema_errors(leaf["x-skm"]) == [], f"{section['id']}.{name}"
            value_schema = {k: v for k, v in leaf.items() if k not in ("x-skm", "default", "description")}
            spec = KeySpec.from_metadata(
                key=f"{section['id']}.{name}",
                section=section["id"],
                owner=section["owner"],
                value_schema=value_schema,
                default=leaf.get("default", MISSING),
                description=leaf.get("description", ""),
                x_skm=leaf["x-skm"],
            )
            assert spec.value_type in {"string", "integer", "number", "boolean", "array", "object", "secret"}
            count += 1
    assert count > 100


# --- level vocabulary ---


def test_chain_levels_follow_the_spec_and_are_read_only() -> None:
    assert CHAIN_LEVELS[Chain.WORK] == (
        Level.DEFAULT,
        Level.PACK,
        Level.INSTANCE,
        Level.WORKSPACE,
        Level.PROJECT,
        Level.PLAN,
        Level.RUN,
        Level.INVOCATION,
    )
    assert CHAIN_LEVELS[Chain.HOST] == (
        Level.DEFAULT,
        Level.PACK,
        Level.INSTANCE,
        Level.HOST,
        Level.INVOCATION,
    )
    with pytest.raises(TypeError):
        cast(Any, CHAIN_LEVELS)[Chain.WORK] = ()
    with pytest.raises(TypeError):
        cast(Any, CHAIN_STORED_LEVELS)[Chain.WORK] = frozenset()


def test_level_sets() -> None:
    assert {
        Level.INSTANCE,
        Level.WORKSPACE,
        Level.PROJECT,
        Level.PLAN,
        Level.RUN,
        Level.HOST,
    } == STORED_LEVELS
    assert {Level.INSTANCE, Level.WORKSPACE, Level.HOST} == SHARED_LEVELS
    assert {Level.INSTANCE, Level.WORKSPACE} == LOCK_LEVELS
    assert {Level.DEFAULT, Level.PACK} == BASE_LEVELS
    assert STORED_LEVELS | {Level.INVOCATION} == EXPLICIT_LEVELS
    assert SHARED_LEVELS | {Level.INVOCATION} == CHAIN_OPEN_LEVELS
    assert CHAIN_STORED_LEVELS[Chain.WORK] == STORED_LEVELS - {Level.HOST}
    assert CHAIN_STORED_LEVELS[Chain.HOST] == {Level.INSTANCE, Level.HOST}


def test_provenance_only_levels_are_in_no_chain_and_not_stored() -> None:
    for level in (Level.RUN_BUNDLE, Level.PROCESS):
        assert all(level not in levels for levels in CHAIN_LEVELS.values())
        assert level not in STORED_LEVELS | EXPLICIT_LEVELS | BASE_LEVELS


def test_enum_values_match_the_metaschema_vocabulary() -> None:
    assert {m.value for m in MergeStrategy} == set(KEY_SPEC["properties"]["merge"]["enum"])
    assert {m.value for m in Reload} == set(KEY_SPEC["properties"]["reload"]["enum"])
    assert {m.value for m in Sensitivity} == set(KEY_SPEC["properties"]["sensitivity"]["enum"])
    assert {m.value for m in Chain} == set(KEY_SPEC["properties"]["chain"]["enum"])
    assert {m.value for m in NarrowDirection} == set(
        KEY_SPEC["properties"]["narrow"]["properties"]["direction"]["enum"]
    )
    assert {m.value for m in STORED_LEVELS} == set(KEY_SPEC["properties"]["levels"]["items"]["enum"])


# --- MISSING ---


def test_missing_is_a_falsy_singleton_distinct_from_none() -> None:
    from skm.platform.config.keys import Missing

    assert repr(MISSING) == "MISSING"
    assert MISSING is not None
    assert MISSING != None  # noqa: E711 - the point of the test
    assert not MISSING
    assert Missing() is MISSING
    assert copy.copy(MISSING) is MISSING
    assert copy.deepcopy({"x": [MISSING]})["x"][0] is MISSING
    assert pickle.loads(pickle.dumps(MISSING)) is MISSING  # noqa: S301 - our own bytes


def test_nullable_is_metadata_and_independent_of_a_json_null_default() -> None:
    absent = replace(build(nullable=True), value_schema={"type": ["integer", "null"]}, default=MISSING)
    null_default = replace(absent, default=None)
    assert absent.default is MISSING
    assert absent.nullable is True
    assert null_default.default is None
    assert null_default.default != absent.default
    assert build().nullable is False


# --- KeySpec ---


def test_from_metadata_maps_every_field() -> None:
    spec = build(
        path=True,
        write_permission="hook.manage",
        confirm=True,
        validators=["execution.rounds"],
        deprecated={"since": "1.0", "replacement": "execution.review.rounds"},
        narrow={"direction": "min", "unlimited": 0},
        ui={
            "group": "Review",
            "order": 3,
            "widget": "number",
            "advanced": True,
            "help_url": "https://x.example/h",
        },
    )
    assert (spec.key, spec.section, spec.owner, spec.default, spec.description) == (
        "execution.review.max_rounds",
        "execution",
        "execution",
        2,
        "Review rounds.",
    )
    assert spec.chain is Chain.WORK
    assert spec.merge is MergeStrategy.NARROW
    assert spec.reload is Reload.RUN_FROZEN
    assert spec.levels == {Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.PLAN, Level.RUN}
    assert spec.sensitivity is Sensitivity.PUBLIC
    assert (spec.override, spec.portable, spec.lockable, spec.nullable, spec.pack) == (
        False,
        True,
        True,
        False,
        True,
    )
    assert (spec.confirm, spec.path, spec.write_permission) == (True, True, "hook.manage")
    assert spec.narrow == NarrowSpec(NarrowDirection.MIN, None, 0)
    assert spec.validators == ("execution.rounds",)
    assert spec.deprecated is not None
    assert spec.deprecated.replacement == "execution.review.rounds"
    assert spec.deprecated.until is None
    assert spec.ui == UiHints("Review", 3, "number", True, None, "https://x.example/h")


def test_from_metadata_defaults_for_optional_fields() -> None:
    spec = build(narrow=None)
    assert (spec.path, spec.write_permission, spec.validators, spec.deprecated) == (False, None, (), None)
    assert spec.narrow is None
    assert spec.ui == UiHints("Review", 10, "number")


@pytest.mark.parametrize("field", sorted(KEY_SPEC["required"]))
def test_from_metadata_rejects_a_missing_required_field(field: str) -> None:
    x_skm = {key: value for key, value in X_SKM.items() if key != field}
    with pytest.raises(ValueError, match=field):
        KeySpec.from_metadata(
            key="a.b",
            section="a",
            owner="a",
            value_schema=SCHEMA,
            default=MISSING,
            description="",
            x_skm=x_skm,
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"extra": 1},
        {"chain": "global"},
        {"levels": ["default"]},
        {"levels": ["run_bundle"]},
        {"levels": []},
        {"merge": "overwrite"},
        {"reload": "never"},
        {"sensitivity": "private"},
        {"narrow": {"direction": "sum"}},
        {"narrow": {"order": ["x"]}},
        {"narrow": {"junk": 1}},
        {"ui": {"group": "G", "order": 1, "widget": "w", "junk": 1}},
        {"deprecated": {"since": "1", "junk": 1}},
    ],
    ids=lambda patch: next(iter(patch)),
)
def test_from_metadata_rejects_invalid_metadata(patch: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"\w"):
        build(**patch)


def test_direct_construction_rejects_a_non_stored_level_and_non_json_values() -> None:
    spec = build()
    with pytest.raises(ValueError, match="levels"):
        replace(spec, levels=frozenset({Level.INVOCATION}))
    with pytest.raises(ValueError, match="levels"):
        replace(spec, levels=frozenset())
    with pytest.raises(TypeError):
        replace(spec, default={1, 2})
    with pytest.raises(TypeError):
        replace(spec, default=float("nan"))
    with pytest.raises(TypeError):
        replace(spec, value_schema={"enum": [(1, 2)]})
    with pytest.raises(ValueError, match="empty"):
        replace(spec, key="")


def test_spec_is_immutable_and_isolated_from_its_inputs() -> None:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}, "default_hint": ["a"]}
    default: list[str] = ["a"]
    spec = replace(build(narrow=None, merge="append"), value_schema=schema, default=default)
    schema["items"]["type"] = "integer"
    default.append("b")
    assert spec.value_schema["items"] == {"type": "string"}
    assert spec.default == ["a"]
    with pytest.raises(FrozenInstanceError):
        cast(Any, spec).key = "other"
    with pytest.raises(FrozenInstanceError):
        cast(Any, spec.ui).group = "other"
    with pytest.raises(AttributeError):
        cast(Any, spec.levels).add(Level.HOST)
    assert not hasattr(spec, "__dict__")
    assert isinstance(spec.levels, frozenset)
    assert isinstance(spec.validators, tuple)


NESTED: dict[str, Any] = {"items": {"type": "string", "enum": ["a", "b"]}, "list": [1, {"k": [2]}], "n": None}


def assert_deeply_immutable(value: object) -> None:
    """Every container reachable from ``value`` rejects every mutating call and stays unchanged."""
    before = copy_json(value, "v")
    if isinstance(value, dict):
        node = cast("dict[str, Any]", value)
        assert isinstance(node, FrozenDict)
        for attempt in (
            lambda: node.__setitem__("x", 1),
            lambda: node.__delitem__(next(iter(node), "x")),
            lambda: node.update({"x": 1}),
            lambda: node.setdefault("x", 1),
            lambda: node.pop("x", None),
            node.popitem,
            node.clear,
            lambda: node.__ior__({"x": 1}),
        ):
            with pytest.raises(TypeError, match="immutable"):
                attempt()
        for child in node.values():
            assert_deeply_immutable(child)
    elif isinstance(value, list):
        seq = cast("list[Any]", value)
        assert isinstance(seq, FrozenList)
        for attempt in (
            lambda: seq.append(1),
            lambda: seq.extend([1]),
            lambda: seq.insert(0, 1),
            lambda: seq.__setitem__(0, 1),
            lambda: seq.__delitem__(0),
            seq.pop,
            lambda: seq.remove(0),
            seq.clear,
            lambda: seq.sort(key=str),
            seq.reverse,
            lambda: seq.__iadd__([1]),
            lambda: seq.__imul__(2),
        ):
            with pytest.raises(TypeError, match="immutable"):
                attempt()
        for child in seq:
            assert_deeply_immutable(child)
    assert copy_json(value, "v") == before


def test_freeze_json_is_deep_immutable_equal_to_plain_json_and_json_schema_compatible() -> None:
    frozen = freeze_json(NESTED, "v")
    assert isinstance(frozen, FrozenDict)
    assert frozen == NESTED
    assert json.loads(json.dumps(frozen)) == NESTED
    assert_deeply_immutable(frozen)
    assert Draft202012Validator(frozen).is_valid("a")
    assert copy.deepcopy(frozen) == NESTED
    assert type(copy.deepcopy(frozen)) is FrozenDict
    assert type(pickle.loads(pickle.dumps(frozen))) is FrozenDict  # noqa: S301 - our own bytes
    thawed = copy_json(frozen, "v")
    assert type(thawed) is dict
    cast("dict[str, Any]", thawed)["items"]["type"] = "integer"  # a plain copy is the caller's own
    assert cast("dict[str, Any]", frozen)["items"]["type"] == "string"


@pytest.mark.parametrize("bad", [{1, 2}, float("nan"), {"a": (1,)}, {1: "x"}, [object()]])
def test_freeze_json_rejects_non_json(bad: object) -> None:
    with pytest.raises(TypeError):
        freeze_json(bad, "v")


def test_key_spec_value_schema_and_default_are_deeply_immutable_through_direct_construction() -> None:
    schema = {"type": "array", "items": {"type": "string"}, "examples": [["a"]]}
    default: list[Any] = ["a", {"k": ["v"]}]
    spec = replace(build(narrow=None, merge="append"), value_schema=schema, default=default)
    schema["items"]["type"] = "integer"
    default[1]["k"].append("z")
    assert spec.value_schema["items"] == {"type": "string"}
    assert spec.default == ["a", {"k": ["v"]}]
    assert_deeply_immutable(spec.value_schema)
    assert_deeply_immutable(spec.default)
    assert spec.value_type == "array"
    assert Draft202012Validator(spec.value_schema).is_valid(["x"])
    assert spec.value_schema == schema | {"items": {"type": "string"}}


def test_key_spec_from_metadata_deeply_freezes_schema_default_and_unlimited() -> None:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}, "uniqueItems": True}
    default: list[JsonValue] = ["a"]
    unlimited: list[str] = []
    x_skm = {
        **copy.deepcopy(X_SKM),
        "merge": "narrow",
        "narrow": {"direction": "intersect", "unlimited": unlimited},
    }
    spec = KeySpec.from_metadata(
        key="a.b", section="a", owner="a", value_schema=schema, default=default, description="", x_skm=x_skm
    )
    schema["items"]["type"] = "integer"
    default.append("b")
    unlimited.append("x")
    x_skm["narrow"]["unlimited"] = ["y"]
    assert spec.value_schema["items"] == {"type": "string"}
    assert spec.default == ["a"]
    assert spec.narrow is not None
    assert spec.narrow.unlimited == []
    assert_deeply_immutable(spec.value_schema)
    assert_deeply_immutable(spec.default)
    assert_deeply_immutable(spec.narrow.unlimited)
    # re-reading the same objects after the attempts above shows the original state
    assert spec.default == ["a"]
    assert spec.narrow.unlimited == []


def test_narrow_spec_unlimited_is_deeply_immutable_and_missing_stays_missing() -> None:
    narrow = NarrowSpec(NarrowDirection.INTERSECT, None, {"a": [1]})
    assert_deeply_immutable(narrow.unlimited)
    assert narrow.unlimited == {"a": [1]}
    assert NarrowSpec().unlimited is MISSING
    assert KeySpec.__dataclass_fields__["default"].type  # MISSING default survives freezing:
    assert replace(build(), default=MISSING).default is MISSING


def test_narrow_spec_snapshots_unlimited_and_order() -> None:
    unlimited: list[str] = []
    narrow = NarrowSpec(NarrowDirection.INTERSECT, None, cast(Any, unlimited))
    unlimited.append("x")
    assert narrow.unlimited == []
    assert NarrowSpec(None, ["a", "b"]).order == ("a", "b")  # type: ignore[arg-type]
    assert NarrowSpec(None, ("a", "b")).unlimited is MISSING
    assert NarrowSpec(NarrowDirection.MIN, None, 0).unlimited == 0
    assert NarrowSpec(NarrowDirection.MIN, None, None).unlimited is None  # null is a value, not MISSING
    with pytest.raises(ValueError, match=r"narrow\.order"):
        NarrowSpec(None, ("a",))
    with pytest.raises(ValueError, match=r"narrow\.order"):
        NarrowSpec(None, ("a", "a"))
    with pytest.raises(ValueError, match=r"narrow\.direction"):
        NarrowSpec("sum")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [(m, m in (MergeStrategy.NARROW, MergeStrategy.UNION)) for m in MergeStrategy],
)
def test_monotonic_means_narrow_or_union(strategy: MergeStrategy, expected: bool) -> None:
    assert replace(build(), merge=strategy).monotonic is expected


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"type": "string"}, "string"),
        ({"type": "integer"}, "integer"),
        ({"type": "number"}, "number"),
        ({"type": "boolean"}, "boolean"),
        ({"type": "array", "items": {"type": "string"}}, "array"),
        ({"type": "object", "additionalProperties": {"type": "string"}}, "object"),
        ({"type": ["string", "null"]}, "string"),
        ({"$ref": "urn:skm:config:secret-ref:v1"}, "secret"),
        ({"anyOf": [{"type": "string", "enum": ["a"]}, {"type": "string", "pattern": "^b$"}]}, "string"),
    ],
)
def test_value_type(schema: dict[str, Any], expected: str) -> None:
    assert replace(build(), value_schema=schema).value_type == expected


@pytest.mark.parametrize(
    "schema",
    [
        {},
        {"type": ["string", "integer"]},
        {"type": "null"},
        {"anyOf": [{"type": "string"}, {"type": "integer"}]},
    ],
)
def test_value_type_rejects_an_ambiguous_schema(schema: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="single JSON type"):
        _ = replace(build(), value_schema=schema).value_type


# --- secret-ref: schema and SecretRef.parse agree on the end of the string ---

VALID_REFS = ["secret://env/SKM_TOKEN", "secret://file/~/.secrets/token", "secret://keyring/skm/user"]


@pytest.mark.parametrize("text", VALID_REFS)
def test_secret_ref_schema_and_parser_accept_the_same_references(text: str) -> None:
    assert Draft202012Validator(SECRET_REF).is_valid(text)
    assert str(SecretRef.parse(text)) == text


@pytest.mark.parametrize("text", VALID_REFS)
@pytest.mark.parametrize("tail", ["\n", "\r\n", " ", "\n\n"])
def test_secret_ref_with_a_trailing_line_break_or_space_is_rejected_by_both(text: str, tail: str) -> None:
    assert not Draft202012Validator(SECRET_REF).is_valid(text + tail)
    with pytest.raises(ValidationFailed):
        SecretRef.parse(text + tail)
