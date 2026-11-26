"""``union``: the sorted set of all applied contributions, default and pack included (settings §B.5.3)."""

from typing import cast

from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import (
    KeySpec,
    Level,
    MergeStrategy,
    Reload,
)
from skm.platform.config.merge import fold
from unit.platform.config.merge_support import contribution as c
from unit.platform.config.merge_support import key_spec
from unit.platform.config.merge_support import layer_ref as ref

GATE: list[JsonValue] = ["security", "destructive", "public_api", "scope_expansion"]
CATEGORIES = [
    "security",
    "destructive",
    "public_api",
    "scope_expansion",
    "product",
    "legal",
    "cost",
    "data_loss",
]
ORDERED_LEVELS = [Level.PACK, Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.PLAN, Level.RUN]


def spec(default: list[JsonValue]) -> KeySpec:
    return key_spec(
        "execution.advisor.human_gate",
        {
            "type": "array",
            "items": {"type": "string", "enum": cast("list[JsonValue]", CATEGORIES)},
            "uniqueItems": True,
        },
        MergeStrategy.UNION,
        owner="execution",
        default=default,
        reload=Reload.RUN_FROZEN,
        widget="tags",
    )


def test_spec_example_human_gate() -> None:
    """§B.5.3: instance adds ``other``; an empty project contribution adds nothing."""
    rows = [c(Level.DEFAULT, GATE), c(Level.INSTANCE, ["other"]), c(Level.PROJECT, [])]
    res = fold(spec(GATE), rows)
    assert res.value == ["destructive", "other", "public_api", "scope_expansion", "security"]
    assert [t.status for t in res.trace] == ["used", "used", "winner"]
    assert res.winner == ref(Level.PROJECT)


def test_union_includes_default_and_pack_and_sorts() -> None:
    rows = [c(Level.DEFAULT, ["security"]), c(Level.PACK, ["cost"]), c(Level.RUN, ["legal", "cost"])]
    rows.append(c(Level.INVOCATION, ["data_loss"]))
    res = fold(spec(["security"]), rows)
    assert res.value == ["cost", "data_loss", "legal", "security"]
    assert [t.status for t in res.trace] == ["used", "used", "used", "winner"]
    assert res.base is None


def test_near_levels_cannot_remove_default_elements() -> None:
    """No base-value rule for union: a project without farther explicit levels still keeps G27 categories."""
    res = fold(spec(GATE), [c(Level.DEFAULT, GATE), c(Level.PROJECT, ["product"])])
    assert set(cast("list[str]", res.value)) == {*cast("list[str]", GATE), "product"}


def test_unset_is_refused() -> None:
    rows = [c(Level.DEFAULT, GATE), c(Level.INSTANCE, ["cost"]), c(Level.PROJECT, op="unset")]
    res = fold(spec(GATE), rows)
    assert "cost" in cast("list[str]", res.value)
    assert res.trace[-1].reason == "op_not_allowed"
    assert [d.code for d in res.diagnostics] == ["CONFIG_OP_NOT_ALLOWED"]


def test_append_and_non_list_values_are_refused() -> None:
    rows = [c(Level.DEFAULT, GATE), c(Level.INSTANCE, ["cost"], "append"), c(Level.PROJECT, "cost")]
    res = fold(spec(GATE), rows)
    assert res.value == sorted(cast("list[str]", GATE))
    assert [t.reason for t in res.trace[1:]] == ["op_not_allowed", "op_not_allowed"]


@given(
    default=st.lists(st.sampled_from(CATEGORIES), unique=True),
    layers=st.lists(
        st.tuples(st.sampled_from(ORDERED_LEVELS), st.lists(st.sampled_from(CATEGORIES), max_size=4)),
        max_size=6,
    ),
)
def test_union_never_loses_an_element(default: list[str], layers: list[tuple[Level, list[str]]]) -> None:
    ordered = sorted(layers, key=lambda item: ORDERED_LEVELS.index(item[0]))
    rows = [c(Level.DEFAULT, cast("list[JsonValue]", default))]
    rows += [c(level, cast("list[JsonValue]", value)) for level, value in ordered]
    res = fold(spec(cast("list[JsonValue]", default)), rows)
    result = cast("list[str]", res.value)
    assert result == sorted(set(result))
    assert set(result) == set(default).union(*(value for _, value in ordered))
    assert all(t.status in ("used", "winner") for t in res.trace)
