"""Lock: an instance/workspace lock ignores every nearer contribution (settings §B.5.1 step 4, §B.5.6)."""

from typing import Any, cast

import pytest

from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import (
    KeySpec,
    Level,
    MergeStrategy,
    NarrowDirection,
    NarrowSpec,
)
from skm.platform.config.layers import Contribution, LayerRef
from skm.platform.config.merge import KeyResolution, fold
from unit.platform.config.merge_support import SCOPES, WORK, key_spec


def spec(
    merge: MergeStrategy = MergeStrategy.REPLACE,
    *,
    levels: frozenset[Level] = WORK,
    schema: dict[str, Any] | None = None,
) -> KeySpec:
    narrow = NarrowSpec(NarrowDirection.MIN) if merge is MergeStrategy.NARROW else None
    return key_spec("x.value", schema or {"type": "integer"}, merge, default=2, levels=levels, narrow=narrow)


def ref(level: Level) -> LayerRef:
    if level is Level.DEFAULT:
        return LayerRef(level)
    if level is Level.PACK:
        return LayerRef(level, pack_id="p")
    if level is Level.INVOCATION:
        return LayerRef(level, label="--set", source="cli")
    return LayerRef(level, SCOPES[level], f"{level.value}:x")


def c(level: Level, value: JsonValue = None, op: str = "set", *, locked: bool = False) -> Contribution:
    return Contribution(
        ref(level), cast("Any", "default" if level is Level.DEFAULT else op), value, locked=locked
    )


def forged_lock(contribution: Contribution) -> Contribution:
    """A row changed outside the commands: ``Contribution`` refuses such a lock, so bypass its checks."""
    forged = object.__new__(Contribution)
    for name in ("layer", "op", "value"):
        object.__setattr__(forged, name, getattr(contribution, name))
    object.__setattr__(forged, "locked", True)
    return forged


def statuses(res: KeyResolution) -> list[tuple[str, str, str | None]]:
    return [(t.contribution.layer.level.value, t.status, t.reason) for t in res.trace]


@pytest.mark.parametrize("level", [Level.INSTANCE, Level.WORKSPACE])
def test_lock_fixes_the_value_and_ignores_nearer_levels(level: Level) -> None:
    rows = [c(Level.DEFAULT, 2), c(level, 5, locked=True), c(Level.PROJECT, 7), c(Level.RUN, op="unset")]
    res = fold(spec(), rows)
    assert (res.value, res.winner, res.locked_by) == (5, ref(level), ref(level))
    assert statuses(res)[2:] == [("project", "ignored", "locked_above"), ("run", "ignored", "locked_above")]
    assert [d.code for d in res.diagnostics] == ["CONFIG_LOCKED"]
    diagnostic = res.diagnostics[0]
    assert diagnostic.message == f"2 contributions below {level.value}:x are ignored: the key is locked there"
    assert diagnostic.details["layer"] == ref(level).to_json()


def test_invocation_after_a_lock_is_ignored_even_with_override() -> None:
    res = fold(spec(), [c(Level.DEFAULT, 2), c(Level.INSTANCE, 5, locked=True), c(Level.INVOCATION, 9)])
    assert res.value == 5
    assert statuses(res)[-1] == ("invocation", "ignored", "locked_above")
    assert res.diagnostics[0].message == "1 contribution below instance:x is ignored: the key is locked there"


def test_a_farther_lock_wins_over_a_nearer_lock() -> None:
    rows = [c(Level.INSTANCE, 5, locked=True), c(Level.WORKSPACE, 4, locked=True), c(Level.PROJECT, 3)]
    res = fold(spec(), rows)
    assert (res.value, res.locked_by) == (5, ref(Level.INSTANCE))
    assert [s for _, s, _ in statuses(res)] == ["winner", "ignored", "ignored"]


def test_lock_does_not_hide_farther_contributions() -> None:
    res = fold(
        spec(MergeStrategy.NARROW),
        [c(Level.DEFAULT, 2), c(Level.INSTANCE, 4), c(Level.WORKSPACE, 3, locked=True)],
    )
    assert (res.value, res.base, res.locked_by) == (3, ref(Level.INSTANCE), ref(Level.WORKSPACE))
    assert [s for _, s, _ in statuses(res)] == ["shadowed", "used", "winner"]


@pytest.mark.parametrize("level", [Level.PROJECT, Level.PLAN, Level.RUN])
def test_lock_on_a_level_without_lock_right_is_ignored_with_a_diagnostic(level: Level) -> None:
    rows = [c(Level.DEFAULT, 2), c(Level.INSTANCE, 5), forged_lock(c(level, 4)), c(Level.RUN, 3)]
    res = fold(spec(), rows)
    assert res.locked_by is None
    assert res.value == 3  # the value of the forged row still counts, its lock does not
    diagnostic = next(d for d in res.diagnostics if d.details.get("reason") == "lock_level")
    assert diagnostic.code == "CONFIG_SCOPE_NOT_ALLOWED"
    assert diagnostic.details["layers"] == [ref(level).to_json()]
    assert all(t.reason != "locked_above" for t in res.trace)


def test_forged_pack_and_invocation_locks_do_not_lock() -> None:
    rows = [forged_lock(c(Level.PACK, 4)), forged_lock(c(Level.INVOCATION, 3))]
    res = fold(spec(), [c(Level.DEFAULT, 2), *rows])
    assert (res.value, res.locked_by) == (3, None)
    assert len([d for d in res.diagnostics if d.code == "CONFIG_SCOPE_NOT_ALLOWED"]) == 1


def test_an_ignored_locked_contribution_does_not_lock() -> None:
    narrow = spec(MergeStrategy.NARROW, levels=frozenset({Level.INSTANCE, Level.PROJECT, Level.PLAN}))
    rows = [c(Level.DEFAULT, 2), c(Level.WORKSPACE, 1, locked=True), c(Level.PROJECT, 2), c(Level.PLAN, 1)]
    res = fold(narrow, rows)
    assert res.locked_by is None
    assert statuses(res)[1] == ("workspace", "ignored", "scope_not_allowed")
    assert res.value == 1


def test_level_gates_come_before_the_lock() -> None:
    narrow = spec(levels=frozenset({Level.INSTANCE, Level.PLAN}))
    res = fold(narrow, [c(Level.INSTANCE, 5, locked=True), c(Level.PROJECT, 3), c(Level.PLAN, 1)])
    assert statuses(res)[1:] == [
        ("project", "ignored", "scope_not_allowed"),
        ("plan", "ignored", "locked_above"),
    ]
    assert [d.code for d in res.diagnostics] == ["CONFIG_SCOPE_NOT_ALLOWED", "CONFIG_LOCKED"]


def test_locked_union_accepts_no_new_elements() -> None:
    union = spec(MergeStrategy.UNION, schema={"type": "array", "items": {"type": "string"}})
    rows = [Contribution(LayerRef(Level.DEFAULT), "default", ["a"]), c(Level.WORKSPACE, ["b"], locked=True)]
    res = fold(union, [*rows, c(Level.PROJECT, ["c"])])
    assert res.value == ["a", "b"]
    assert res.trace[-1].reason == "locked_above"
