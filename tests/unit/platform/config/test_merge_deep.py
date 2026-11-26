"""``deep_merge``: maps and records merge field-wise, arrays replace, ``$unset`` removes (settings §B.5.5)."""

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import (
    MISSING,
    KeySpec,
    Level,
    MergeStrategy,
)
from skm.platform.config.layers import Contribution
from skm.platform.config.merge import apply_unset_markers, deep_merge, fold, is_unset_marker
from unit.platform.config.merge_support import contribution as c
from unit.platform.config.merge_support import key_spec
from unit.platform.config.merge_support import layer_ref as ref

ROOT = Path(__file__).resolve().parents[4]
EXPLAIN = ROOT / "tests/fixtures/corpus/examples/config/explain-execution-review-max-rounds.json"
UNSET: JsonValue = {"$unset": True}

# a hooks.subscriptions-like map of fixed records: required fields are checked on the result only (R5)
RECORDS: dict[str, Any] = {
    "type": "object",
    "additionalProperties": {
        "type": "object",
        "additionalProperties": False,
        "required": ["enabled", "kind", "url", "retry"],
        "properties": {
            "enabled": {"type": "boolean"},
            "kind": {"type": "string"},
            "url": {"type": "string"},
            "events": {"type": "array", "items": {"type": "string"}},
            "retry": {
                "type": "object",
                "additionalProperties": False,
                "required": ["max_attempts", "backoff"],
                "properties": {
                    "max_attempts": {"type": "integer"},
                    "backoff": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["initial_ms", "factor"],
                        "properties": {"initial_ms": {"type": "integer"}, "factor": {"type": "number"}},
                    },
                },
            },
        },
    },
}
FULL_A: dict[str, Any] = {
    "enabled": True,
    "kind": "webhook",
    "url": "https://a.example",
    "events": ["run-finished"],
    "retry": {"max_attempts": 5, "backoff": {"initial_ms": 1000, "factor": 2.0}},
}
FULL_B: dict[str, Any] = {**FULL_A, "url": "https://b.example", "events": ["run-started"]}


def spec(schema: dict[str, Any] | None = None, default: object = MISSING, key: str = "x.map") -> KeySpec:
    schema = schema or {"type": "object", "additionalProperties": {}}
    return key_spec(key, schema, MergeStrategy.DEEP_MERGE, default=default, widget="map")


def valid(schema: dict[str, Any], value: Any) -> bool:
    return Draft202012Validator(schema).is_valid(value)


def test_profile_by_work_kind_row() -> None:
    default: JsonValue = {"research": "research-only"}
    res = fold(
        spec(default=default),
        [c(Level.DEFAULT, default), c(Level.PROJECT, {"docs": "quick-fix", "research": UNSET})],
    )
    assert res.value == {"docs": "quick-fix"}
    assert [t.status for t in res.trace] == ["used", "winner"]


SUBSCRIPTION_ROWS: list[tuple[list[Contribution], Any]] = [
    (
        [c(Level.WORKSPACE, {"a": FULL_A}), c(Level.PROJECT, {"b": FULL_B})],
        {"a": FULL_A, "b": FULL_B},
    ),
    (
        [
            c(Level.WORKSPACE, {"a": FULL_A}),
            c(Level.PROJECT, {"b": FULL_B}),
            c(Level.PLAN, {"a": {"enabled": False}}),
        ],
        {"a": {**FULL_A, "enabled": False}, "b": FULL_B},
    ),
    (
        [c(Level.WORKSPACE, {"a": FULL_A}), c(Level.PROJECT, {"b": FULL_B}), c(Level.PLAN, {"a": UNSET})],
        {"b": FULL_B},
    ),
]


@pytest.mark.parametrize(
    ("rows", "expected"), SUBSCRIPTION_ROWS, ids=["two_records", "field", "unset_record"]
)
def test_hooks_subscriptions_rows(rows: list[Contribution], expected: Any) -> None:
    res = fold(spec(RECORDS, {}), [c(Level.DEFAULT, {}), *rows])
    assert res.value == expected
    assert valid(RECORDS, res.value)


def test_role_routing_row() -> None:
    rows = [
        c(Level.INSTANCE, {"executor": {"model_class": "implementation", "effort": "high"}}),
        c(Level.PROJECT, {"executor": {"effort": "xhigh"}}),
    ]
    assert fold(spec(), rows).value == {"executor": {"model_class": "implementation", "effort": "xhigh"}}


def test_nested_records_merge_by_field_and_arrays_replace() -> None:
    plan: JsonValue = {"a": {"events": ["x"], "retry": {"backoff": {"factor": 3.0}}}}
    res = fold(
        spec(RECORDS, {}), [c(Level.DEFAULT, {}), c(Level.WORKSPACE, {"a": FULL_A}), c(Level.PLAN, plan)]
    )
    record = cast("dict[str, Any]", res.value)["a"]
    assert record["events"] == ["x"]
    assert record["retry"] == {"max_attempts": 5, "backoff": {"initial_ms": 1000, "factor": 3.0}}
    assert valid(RECORDS, res.value)


def test_unset_marker_at_any_depth() -> None:
    plan: JsonValue = {"a": {"events": UNSET, "retry": {"backoff": {"factor": UNSET}}}, "missing": UNSET}
    value = cast(
        "dict[str, Any]", fold(spec(), [c(Level.WORKSPACE, {"a": FULL_A}), c(Level.PLAN, plan)]).value
    )
    assert "events" not in value["a"]
    assert value["a"]["retry"]["backoff"] == {"initial_ms": 1000}
    assert "missing" not in value


def test_markers_in_a_fresh_subtree_are_dropped() -> None:
    res = fold(spec(), [c(Level.PROJECT, {"n": {"keep": 1, "drop": UNSET, "deep": {"x": UNSET}}})])
    assert res.value == {"n": {"keep": 1, "deep": {}}}
    assert apply_unset_markers({"a": UNSET, "b": [UNSET]}) == {"b": [UNSET]}  # arrays are values, not merged
    assert apply_unset_markers(3) == 3


def test_partial_record_is_valid_only_with_farther_contributions() -> None:
    """R5 (b): a field-wise contribution fails the full schema alone and passes merged with farther levels."""
    partial: JsonValue = {"a": {"enabled": False, "retry": {"max_attempts": 1}}}
    assert not valid(RECORDS, partial)
    alone = fold(spec(RECORDS, {}), [c(Level.DEFAULT, {}), c(Level.PLAN, partial)])
    assert not valid(RECORDS, alone.value)
    merged = fold(
        spec(RECORDS, {}), [c(Level.DEFAULT, {}), c(Level.WORKSPACE, {"a": FULL_A}), c(Level.PLAN, partial)]
    )
    assert valid(RECORDS, merged.value)
    assert cast("dict[str, Any]", merged.value)["a"]["retry"] == {
        "max_attempts": 1,
        "backoff": {"initial_ms": 1000, "factor": 2.0},
    }


def test_unset_resets_to_the_default_map() -> None:
    default: JsonValue = {"research": "research-only"}
    rows = [c(Level.DEFAULT, default), c(Level.INSTANCE, {"docs": "quick"}), c(Level.PROJECT, op="unset")]
    res = fold(spec(default=default), [*rows, c(Level.PLAN, {"x": "y"})])
    assert res.value == {"research": "research-only", "x": "y"}
    assert [t.status for t in res.trace] == ["used", "shadowed", "used", "winner"]


def test_append_and_non_object_values_are_refused() -> None:
    rows = [c(Level.INSTANCE, {"a": 1}), c(Level.PROJECT, ["x"], "append"), c(Level.PLAN, ["x"])]
    res = fold(spec(), rows)
    assert res.value == {"a": 1}
    assert [t.reason for t in res.trace] == [None, "op_not_allowed", "op_not_allowed"]


def test_deep_merge_does_not_change_its_inputs() -> None:
    base: dict[str, JsonValue] = {"a": {"b": [1]}, "c": 1}
    overlay: dict[str, JsonValue] = {"a": {"d": 2}, "c": UNSET}
    before = copy.deepcopy((base, overlay))
    merged = deep_merge(base, overlay)
    cast("dict[str, Any]", merged["a"])["b"].append(9)
    assert (base, overlay) == before
    assert merged == {"a": {"b": [1, 9], "d": 2}}


@pytest.mark.parametrize(
    ("value", "marker"),
    [({"$unset": True}, True), ({"$unset": 1}, False), ({"$unset": True, "x": 1}, False), ("$unset", False)],
)
def test_unset_marker_shape(value: object, marker: bool) -> None:
    assert is_unset_marker(value) is marker


def test_explain_example_hooks_subscriptions() -> None:
    """Golden: key ``hooks.subscriptions`` of examples/config/explain-execution-review-max-rounds.json."""
    report = next(k for k in json.loads(EXPLAIN.read_text())["keys"] if k["key"] == "hooks.subscriptions")
    default, workspace = (entry["value"] for entry in report["contributions"])
    res = fold(
        spec(default={}, key="hooks.subscriptions"),
        [
            c(Level.DEFAULT, default),
            Contribution(ref(Level.WORKSPACE, "workspace:personal"), "set", workspace),
        ],
    )
    assert res.value == report["value"]
    assert [t.status for t in res.trace] == [entry["status"] for entry in report["contributions"]]
    assert res.winner is not None
    assert {k: v for k, v in res.winner.to_json().items() if k != "scope_id"} == report["winner"]


# keys a*, b* hold nested maps, x*, y* hold scalars: the shapes a section schema gives (one type per path)
SCALARS = st.one_of(st.integers(-3, 3), st.text("ab", max_size=2), st.booleans(), st.lists(st.integers(0, 2)))


def _tree(depth: int) -> st.SearchStrategy[dict[str, JsonValue]]:
    scalar_keys = st.sampled_from(["x", "y", "z"])
    if depth == 0:
        return st.dictionaries(scalar_keys, cast("st.SearchStrategy[JsonValue]", SCALARS), max_size=3)
    child = cast("st.SearchStrategy[JsonValue]", _tree(depth - 1))
    nested = st.dictionaries(st.sampled_from(["a", "b"]), child, max_size=2)
    leaves = st.dictionaries(scalar_keys, cast("st.SearchStrategy[JsonValue]", SCALARS), max_size=3)
    return st.builds(lambda n, s: {**n, **s}, nested, leaves)


@given(_tree(2), _tree(2), _tree(2))
def test_deep_merge_is_associative(
    a: dict[str, JsonValue], b: dict[str, JsonValue], c3: dict[str, JsonValue]
) -> None:
    assert deep_merge(deep_merge(a, b), c3) == deep_merge(a, deep_merge(b, c3))


@given(_tree(2), _tree(2))
def test_fold_equals_pairwise_deep_merge(a: dict[str, JsonValue], b: dict[str, JsonValue]) -> None:
    res = fold(spec(default={}), [c(Level.DEFAULT, {}), c(Level.INSTANCE, a), c(Level.RUN, b)])
    assert res.value == deep_merge(a, b)
    assert deep_merge({}, a) == a
