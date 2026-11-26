"""``append`` and ``append_unique`` accumulate every contribution in order (settings §B.5.4)."""

import pytest

from skm.platform.config.keys import (
    MISSING,
    KeySpec,
    Level,
    MergeStrategy,
)
from skm.platform.config.merge import KeyResolution, fold
from unit.platform.config.merge_support import contribution as c
from unit.platform.config.merge_support import key_spec
from unit.platform.config.merge_support import layer_ref as ref

ACCUMULATE = [MergeStrategy.APPEND, MergeStrategy.APPEND_UNIQUE]


def spec(merge: MergeStrategy, default: object = MISSING) -> KeySpec:
    return key_spec(
        "context.rules.extra",
        {"type": "array", "items": {"type": "string"}},
        merge,
        owner="context",
        default=default,
        widget="tags",
    )


def statuses(res: KeyResolution) -> list[str]:
    return [t.status for t in res.trace]


def test_spec_example_context_rules_extra() -> None:
    rows = [c(Level.INSTANCE, ["A"]), c(Level.PROJECT, ["B"]), c(Level.PLAN, ["A"])]
    appended = fold(spec(MergeStrategy.APPEND), rows)
    assert appended.value == ["A", "B", "A"]
    assert statuses(appended) == ["used", "used", "winner"]
    unique = fold(spec(MergeStrategy.APPEND_UNIQUE), rows)
    assert unique.value == ["A", "B"]
    assert unique.winner == ref(Level.PLAN)


@pytest.mark.parametrize("merge", ACCUMULATE)
def test_default_pack_and_invocation_are_accumulated_in_layer_order(merge: MergeStrategy) -> None:
    rows = [
        c(Level.DEFAULT, ["d"]),
        c(Level.PACK, ["p"]),
        c(Level.WORKSPACE, ["w", "d"]),
        c(Level.RUN, ["r"]),
        c(Level.INVOCATION, ["i"]),
    ]
    res = fold(spec(merge, ["d"]), rows)
    expected = ["d", "p", "w", "d", "r", "i"] if merge is MergeStrategy.APPEND else ["d", "p", "w", "r", "i"]
    assert res.value == expected
    assert statuses(res) == ["used", "used", "used", "used", "winner"]


@pytest.mark.parametrize("merge", ACCUMULATE)
def test_unset_resets_to_the_default(merge: MergeStrategy) -> None:
    rows = [
        c(Level.DEFAULT, ["d"]),
        c(Level.INSTANCE, ["a"]),
        c(Level.PROJECT, op="unset"),
        c(Level.PLAN, ["b"]),
    ]
    res = fold(spec(merge, ["d"]), rows)
    assert res.value == ["d", "b"]
    assert statuses(res) == ["used", "shadowed", "used", "winner"]


@pytest.mark.parametrize("merge", ACCUMULATE)
def test_unset_without_default_is_missing(merge: MergeStrategy) -> None:
    res = fold(spec(merge), [c(Level.INSTANCE, ["a"]), c(Level.PROJECT, op="unset")])
    assert res.value is MISSING


@pytest.mark.parametrize("merge", ACCUMULATE)
def test_append_operation_is_refused_for_accumulating_keys(merge: MergeStrategy) -> None:
    res = fold(
        spec(merge, []), [c(Level.DEFAULT, []), c(Level.INSTANCE, ["a"]), c(Level.PROJECT, ["b"], "append")]
    )
    assert res.value == ["a"]
    assert res.trace[-1].reason == "op_not_allowed"
    assert [d.code for d in res.diagnostics] == ["CONFIG_OP_NOT_ALLOWED"]


@pytest.mark.parametrize("merge", ACCUMULATE)
def test_non_list_value_is_ignored_not_concatenated(merge: MergeStrategy) -> None:
    res = fold(spec(merge, []), [c(Level.DEFAULT, []), c(Level.INSTANCE, ["a"]), c(Level.PROJECT, "b")])
    assert res.value == ["a"]
    assert res.trace[-1].reason == "op_not_allowed"


def test_append_unique_compares_json_values_not_python_equality() -> None:
    key = spec(MergeStrategy.APPEND_UNIQUE)
    res = fold(key, [c(Level.INSTANCE, [1, True, {"a": 1}]), c(Level.PROJECT, [1.0, {"a": 1}, False, True])])
    assert res.value == [1, True, {"a": 1}, False]
