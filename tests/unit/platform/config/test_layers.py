"""Layer references and contributions (settings §B.3)."""

from dataclasses import FrozenInstanceError
from typing import Any, cast
from uuid import uuid4

import pytest

from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import STORED_LEVELS, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef

STORED = sorted(STORED_LEVELS)


def stored(level: Level = Level.WORKSPACE, **extra: Any) -> LayerRef:
    return LayerRef(level, uuid4(), f"{level.value}:x", **extra)


def test_provenance_shapes_from_the_explain_example() -> None:
    assert LayerRef(Level.DEFAULT).scope_id is None
    pack = LayerRef(Level.PACK, label="pack:example-overlay", pack_id="example-overlay", pack_priority=10)
    assert (pack.pack_id, pack.pack_priority) == ("example-overlay", 10)
    entry = stored(entry_id=uuid4(), row_version=3)
    assert entry.row_version == 3
    for source in ("env", "cli", "config-file:./x.toml"):
        assert LayerRef(Level.INVOCATION, source=source).source == source
    for level in (Level.RUN_BUNDLE, Level.PROCESS):
        assert LayerRef(level).scope_id is None


@pytest.mark.parametrize("level", STORED)
def test_stored_layer_requires_a_uuid_scope(level: Level) -> None:
    for bad in (None, "0191e2a4-7c3f-7b21-8a54-3f6d2c1b9e07", 1):
        with pytest.raises(ValueError, match="scope_id"):
            LayerRef(level, cast(Any, bad))


@pytest.mark.parametrize(
    "level", [Level.DEFAULT, Level.PACK, Level.INVOCATION, Level.RUN_BUNDLE, Level.PROCESS]
)
def test_non_stored_layer_has_no_scope(level: Level) -> None:
    extra: dict[str, Any] = {"pack_id": "p"} if level is Level.PACK else {}
    extra |= {"source": "env"} if level is Level.INVOCATION else {}
    with pytest.raises(ValueError, match="scope_id"):
        LayerRef(level, uuid4(), **extra)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"level": Level.PACK},  # pack without id
        {"level": Level.WORKSPACE, "pack_id": "p"},
        {"level": Level.DEFAULT, "pack_priority": 1},
        {"level": Level.INVOCATION},  # invocation without source
        {"level": Level.INVOCATION, "source": "file"},
        {"level": Level.INVOCATION, "source": "config-file:"},
        {"level": Level.DEFAULT, "source": "env"},
        {"level": Level.DEFAULT, "entry_id": uuid4()},
        {"level": Level.PACK, "pack_id": "p", "row_version": 1},
        {"level": Level.WORKSPACE, "row_version": 0},
        {"level": Level.WORKSPACE, "row_version": True},
        {"level": Level.WORKSPACE, "row_version": -1},
    ],
    ids=lambda kwargs: ",".join(f"{k}" for k in kwargs),
)
def test_layer_ref_rejects_inconsistent_fields(kwargs: dict[str, Any]) -> None:
    if kwargs["level"] in STORED_LEVELS:
        kwargs = {**kwargs, "scope_id": uuid4()}
    with pytest.raises(ValueError, match=r"\w"):
        LayerRef(**kwargs)


def test_layer_ref_equality_ignores_nothing_but_is_hashable_and_frozen() -> None:
    scope_id = uuid4()
    first = LayerRef(Level.PROJECT, scope_id, "project:a")
    assert first == LayerRef(Level.PROJECT, scope_id, "project:a")
    assert len({first, LayerRef(Level.PROJECT, scope_id, "project:a")}) == 1
    with pytest.raises(FrozenInstanceError):
        cast(Any, first).label = "x"


def test_contribution_ops_and_default_level() -> None:
    assert Contribution(LayerRef(Level.DEFAULT), "default", 2).op == "default"
    assert Contribution(stored(), "set", 3).value == 3
    assert Contribution(stored(), "append", ["a"]).value == ["a"]
    unset = Contribution(stored(), "unset", None)
    assert unset.value is None
    assert Contribution(stored(), "set", None).value is None  # JSON null is a value; op tells it from unset


@pytest.mark.parametrize(
    ("layer", "op", "value"),
    [
        (LayerRef(Level.DEFAULT), "set", 1),  # default level only carries op default
        (stored(), "default", 1),  # and op default only comes from the default level
        (stored(), "replace", 1),
        (stored(), "unset", 5),  # unset carries no value
        (stored(), "set", {1, 2}),
        (stored(), "set", float("inf")),
        (stored(), "set", {1: "x"}),
    ],
)
def test_contribution_rejects_invalid_combinations(layer: LayerRef, op: str, value: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        Contribution(layer, cast(Any, op), cast(JsonValue, value))


@pytest.mark.parametrize("level", [Level.INSTANCE, Level.WORKSPACE])
def test_lock_comes_only_from_instance_and_workspace(level: Level) -> None:
    assert Contribution(stored(level), "set", 1, locked=True).locked is True


@pytest.mark.parametrize(
    "layer",
    [
        stored(Level.PROJECT),
        stored(Level.PLAN),
        stored(Level.RUN),
        stored(Level.HOST),
        LayerRef(Level.PACK, pack_id="p"),
        LayerRef(Level.INVOCATION, source="cli"),
    ],
)
def test_nearer_levels_cannot_lock(layer: LayerRef) -> None:
    with pytest.raises(ValueError, match="lock"):
        Contribution(layer, "set", 1, locked=True)


def test_contribution_snapshots_its_value_and_is_frozen() -> None:
    value: dict[str, Any] = {"a": [1]}
    contribution = Contribution(stored(), "set", value)
    value["a"].append(2)
    assert contribution.value == {"a": [1]}
    with pytest.raises(FrozenInstanceError):
        cast(Any, contribution).value = 0
    assert not hasattr(contribution, "__dict__")


@pytest.mark.parametrize("op", ["set", "append", "default"])
def test_contribution_value_is_deeply_immutable(op: str) -> None:
    level = Level.DEFAULT if op == "default" else Level.WORKSPACE
    ref = LayerRef(level) if op == "default" else stored()
    value: dict[str, Any] = {"a": [1, {"b": [2]}]}
    contribution = Contribution(ref, cast(Any, op), value)
    value["a"][1]["b"].append(3)
    held = cast("dict[str, Any]", contribution.value)
    for attempt in (
        lambda: held.__setitem__("x", 1),
        lambda: held.update({"x": 1}),
        held.clear,
        lambda: held["a"].append(2),
        lambda: held["a"].__setitem__(0, 9),
        lambda: held["a"][1]["b"].append(4),
        lambda: held["a"][1].pop("b"),
    ):
        with pytest.raises(TypeError, match="immutable"):
            attempt()
    assert contribution.value == {"a": [1, {"b": [2]}]}  # re-read after every attempt


def test_contribution_scalar_and_null_values_stay_plain() -> None:
    assert Contribution(stored(), "set", None).value is None
    assert Contribution(stored(), "set", "s").value == "s"
    assert Contribution(stored(), "append", [1]).value == [1]


def test_layer_collects_contributions_read_only() -> None:
    ref = stored(Level.PROJECT)
    contribution = Contribution(ref, "set", 4)
    source = {"execution.review.max_rounds": contribution}
    layer = Layer(ref, source)
    source["other.key"] = contribution
    assert dict(layer.contributions) == {"execution.review.max_rounds": contribution}
    with pytest.raises(TypeError):
        cast(Any, layer.contributions)["x"] = contribution
    with pytest.raises(FrozenInstanceError):
        cast(Any, layer).ref = ref


def test_layer_rejects_a_contribution_from_another_level() -> None:
    ref = stored(Level.PROJECT)
    foreign = Contribution(stored(Level.PLAN), "set", 1)
    with pytest.raises(ValueError, match="level"):
        Layer(ref, {"a.b": foreign})
