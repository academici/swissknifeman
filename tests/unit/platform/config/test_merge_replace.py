"""``replace`` and the generic fold gates (settings §B.5.1-B.5.2)."""

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import (
    MISSING,
    STORED_LEVELS,
    Chain,
    KeySpec,
    Level,
    MergeStrategy,
)
from skm.platform.config.layers import Contribution, LayerRef
from skm.platform.config.merge import ContributionTrace, KeyResolution, fold
from unit.platform.config.merge_support import SCOPES, WORK, key_spec


def spec(
    schema: dict[str, Any] | None = None,
    *,
    default: object = MISSING,
    levels: frozenset[Level] = WORK,
    override: bool = False,
    pack: bool = True,
    chain: Chain = Chain.WORK,
) -> KeySpec:
    return key_spec(
        "x.value",
        schema or {"type": "integer"},
        MergeStrategy.REPLACE,
        default=default,
        levels=levels,
        chain=chain,
        override=override,
        pack=pack,
    )


def ref(level: Level) -> LayerRef:
    if level is Level.DEFAULT:
        return LayerRef(level)
    if level is Level.PACK:
        return LayerRef(level, label="pack:p", pack_id="p", pack_priority=0)
    if level is Level.INVOCATION:
        return LayerRef(level, label="--set", source="cli")
    if level in STORED_LEVELS:
        return LayerRef(level, SCOPES[level], level.value)
    return LayerRef(level)


def c(level: Level, value: JsonValue = None, op: str = "set", *, locked: bool = False) -> Contribution:
    op = "default" if level is Level.DEFAULT else op
    return Contribution(ref(level), cast("Any", op), value, locked=locked)


def statuses(res: KeyResolution) -> list[tuple[str, str, str | None]]:
    return [(t.contribution.layer.level.value, t.status, t.reason) for t in res.trace]


def codes(res: KeyResolution) -> list[str]:
    return [d.code for d in res.diagnostics]


def test_only_default_is_the_winner() -> None:
    res = fold(spec(default=30000), [c(Level.DEFAULT, 30000)])
    assert (res.value, res.winner, res.locked_by, res.base) == (30000, ref(Level.DEFAULT), None, None)
    assert statuses(res) == [("default", "winner", None)]
    assert res.present
    assert res.diagnostics == ()


def test_set_shadows_everything_farther() -> None:
    res = fold(
        spec(default=2), [c(Level.DEFAULT, 2), c(Level.PACK, 3), c(Level.INSTANCE, 4), c(Level.PLAN, 9)]
    )
    assert res.value == 9
    assert res.winner == ref(Level.PLAN)
    assert [s for _, s, _ in statuses(res)] == ["shadowed", "shadowed", "shadowed", "winner"]


def test_unset_restores_the_default_and_hides_everything_but_the_default() -> None:
    res = fold(
        spec(default=2),
        [c(Level.DEFAULT, 2), c(Level.PACK, 3), c(Level.INSTANCE, 4), c(Level.PROJECT, op="unset")],
    )
    assert res.value == 2
    assert statuses(res) == [
        ("default", "used", None),
        ("pack", "shadowed", None),
        ("instance", "shadowed", None),
        ("project", "winner", None),
    ]


def test_set_after_unset_wins_again() -> None:
    res = fold(spec(default=2), [c(Level.DEFAULT, 2), c(Level.INSTANCE, op="unset"), c(Level.PLAN, 7)])
    assert res.value == 7
    assert [s for _, s, _ in statuses(res)] == ["shadowed", "shadowed", "winner"]


def test_unset_without_a_default_leaves_the_key_missing() -> None:
    res = fold(spec(), [c(Level.INSTANCE, 4), c(Level.PROJECT, op="unset")])
    assert res.value is MISSING
    assert not res.present
    assert statuses(res) == [("instance", "shadowed", None), ("project", "winner", None)]


def test_no_contribution_is_missing_without_winner() -> None:
    res = fold(spec(), [])
    assert (res.value, res.winner, res.trace, res.diagnostics) == (MISSING, None, (), ())


def test_json_null_is_a_value_not_an_unset() -> None:
    res = fold(spec({"type": ["integer", "null"]}, default=1), [c(Level.DEFAULT, 1), c(Level.RUN, None)])
    assert res.value is None
    assert res.present
    assert res.winner == ref(Level.RUN)


def test_array_append_example_of_the_spec() -> None:
    """§B.5.2: execution.generation.command."""
    array = spec({"type": "array", "items": {"type": "string"}}, default=[])
    rows = [c(Level.DEFAULT, []), c(Level.INSTANCE, ["make", "gen"]), c(Level.PROJECT, ["--fast"], "append")]
    res = fold(array, rows)
    assert res.value == ["make", "gen", "--fast"]
    assert [s for _, s, _ in statuses(res)] == ["shadowed", "used", "winner"]
    reset = fold(array, [*rows, c(Level.PLAN, op="unset")])
    assert reset.value == []
    assert [s for _, s, _ in statuses(reset)] == ["used", "shadowed", "shadowed", "winner"]


def test_append_without_a_farther_value_starts_from_empty() -> None:
    array = spec({"type": "array", "items": {"type": "string"}})
    assert fold(array, [c(Level.PROJECT, ["a"], "append"), c(Level.RUN, ["b"], "append")]).value == ["a", "b"]


@pytest.mark.parametrize(
    ("key", "value"),
    [(spec(), [1]), (spec({"type": "array"}), "not-a-list")],
    ids=["scalar_key", "non_list_value"],
)
def test_append_is_only_for_replace_arrays(key: KeySpec, value: JsonValue) -> None:
    res = fold(key, [c(Level.INSTANCE, 1), c(Level.PROJECT, value, "append")])
    assert statuses(res)[-1] == ("project", "ignored", "op_not_allowed")
    assert res.value == 1
    assert codes(res) == ["CONFIG_OP_NOT_ALLOWED"]


def test_level_outside_the_key_levels_is_ignored() -> None:
    key = spec(default=1, levels=frozenset({Level.INSTANCE, Level.WORKSPACE}))
    res = fold(key, [c(Level.DEFAULT, 1), c(Level.INSTANCE, 2), c(Level.PROJECT, 3), c(Level.RUN, 4)])
    assert res.value == 2
    assert statuses(res)[2:] == [
        ("project", "ignored", "scope_not_allowed"),
        ("run", "ignored", "scope_not_allowed"),
    ]
    assert codes(res) == ["CONFIG_SCOPE_NOT_ALLOWED"]
    assert res.diagnostics[0].message.startswith("2 contributions are ignored")
    assert res.diagnostics[0].target == "x.value"
    assert res.diagnostics[0].severity == "warning"


@pytest.mark.parametrize("level", [Level.HOST, Level.RUN_BUNDLE, Level.PROCESS])
def test_levels_outside_the_chain_or_provenance_only_are_ignored(level: Level) -> None:
    res = fold(spec(default=1), [c(Level.DEFAULT, 1), c(level, 5)])
    assert res.value == 1
    assert statuses(res)[-1] == (level.value, "ignored", "scope_not_allowed")


def test_pack_value_needs_pack_permission() -> None:
    res = fold(spec(default=1, pack=False), [c(Level.DEFAULT, 1), c(Level.PACK, 5)])
    assert res.value == 1
    assert statuses(res)[-1] == ("pack", "ignored", "pack_not_allowed")
    assert codes(res) == ["CONFIG_PACK_NOT_ALLOWED"]


def test_invocation_needs_override() -> None:
    rows = [c(Level.DEFAULT, 1), c(Level.INSTANCE, 2), c(Level.INVOCATION, 9)]
    refused = fold(spec(default=1), rows)
    assert refused.value == 2
    assert statuses(refused)[-1] == ("invocation", "ignored", "override_not_allowed")
    assert codes(refused) == ["CONFIG_OVERRIDE_NOT_ALLOWED"]
    allowed = fold(spec(default=1, override=True), rows)
    assert (allowed.value, allowed.winner) == (9, ref(Level.INVOCATION))


def test_host_chain_accepts_host_contributions() -> None:
    key = spec(default=1, levels=frozenset({Level.INSTANCE, Level.HOST}), chain=Chain.HOST)
    res = fold(key, [c(Level.DEFAULT, 1), c(Level.INSTANCE, 2), c(Level.HOST, 3)])
    assert (res.value, res.winner) == (3, ref(Level.HOST))


def test_one_diagnostic_per_reason_in_gate_order() -> None:
    key = spec(default=1, levels=frozenset({Level.INSTANCE}), pack=False)
    rows = [c(Level.DEFAULT, 1), c(Level.PACK, 2), c(Level.INSTANCE, 3), c(Level.PROJECT, 4)]
    rows += [c(Level.PLAN, 5), c(Level.INVOCATION, 6)]
    res = fold(key, rows)
    assert codes(res) == [
        "CONFIG_SCOPE_NOT_ALLOWED",
        "CONFIG_PACK_NOT_ALLOWED",
        "CONFIG_OVERRIDE_NOT_ALLOWED",
    ]
    assert res.diagnostics[0].details["layers"] == [ref(Level.PROJECT).to_json(), ref(Level.PLAN).to_json()]
    assert res.diagnostics[1].message == "1 contribution is ignored: packs may not set this key"


@pytest.mark.parametrize(
    "rows",
    [
        [c(Level.PROJECT, 1), c(Level.INSTANCE, 2)],
        [c(Level.INVOCATION, 1), c(Level.RUN, 2)],
        [c(Level.INSTANCE, 1), c(Level.DEFAULT, 2)],
        [c(Level.DEFAULT, 1), c(Level.DEFAULT, 2)],
    ],
    ids=["project_before_instance", "invocation_before_run", "default_late", "two_defaults"],
)
def test_contributions_out_of_chain_order_are_a_programming_error(rows: list[Contribution]) -> None:
    with pytest.raises(ValueError, match=r"out of order|one default"):
        fold(spec(), rows)


def test_resolution_is_frozen_and_trace_states_are_checked() -> None:
    res = fold(spec({"type": "object"}), [c(Level.INSTANCE, {"a": [1]})])
    with pytest.raises(TypeError, match="immutable"):
        cast("dict[str, Any]", res.value)["a"].append(2)
    with pytest.raises(FrozenInstanceError):
        cast("Any", res).value = 1
    contribution = c(Level.INSTANCE, 1)
    with pytest.raises(ValueError, match="reason"):
        ContributionTrace(contribution, "ignored")
    with pytest.raises(ValueError, match="reason"):
        ContributionTrace(contribution, "used", "locked_above")
    with pytest.raises(ValueError, match="status"):
        ContributionTrace(contribution, cast("Any", "overridden"))


def test_explain_example_storage_statement_timeout() -> None:
    """``storage.statement_timeout_ms`` of examples/config/explain-execution-review-max-rounds.json."""
    res = fold(spec(default=30000), [c(Level.DEFAULT, 30000)])
    assert res.winner is not None
    assert res.winner.to_json() == {"level": "default"}
    assert [(t.contribution.op, t.contribution.value, t.status) for t in res.trace] == [
        ("default", 30000, "winner")
    ]


def test_layer_ref_display_and_json() -> None:
    assert ref(Level.DEFAULT).display == "default"
    assert LayerRef(Level.PACK, pack_id="core").display == "pack:core"
    assert LayerRef(Level.INVOCATION, source="env").display == "env"
    stored = LayerRef(Level.PLAN, SCOPES[Level.PLAN], "plan:PLAN7", entry_id=SCOPES[Level.RUN], row_version=2)
    assert stored.display == "plan:PLAN7"
    assert stored.to_json() == {
        "level": "plan",
        "scope_id": str(SCOPES[Level.PLAN]),
        "label": "plan:PLAN7",
        "entry_id": str(SCOPES[Level.RUN]),
        "row_version": 2,
    }
    assert LayerRef(Level.PACK, pack_id="o", pack_priority=10).to_json() == {
        "level": "pack",
        "pack_id": "o",
        "pack_priority": 10,
    }
