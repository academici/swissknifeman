"""``narrow``: base value, narrowing chain and K16 variant A (settings §B.5.3)."""

import json
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import (
    CHAIN_OPEN_LEVELS,
    EXPLICIT_LEVELS,
    MISSING,
    KeySpec,
    Level,
    MergeStrategy,
    NarrowDirection,
    NarrowSpec,
)
from skm.platform.config.layers import Contribution, LayerRef
from skm.platform.config.merge import KeyResolution, fold, narrow_value, narrow_widens
from skm.platform.schema.registry import SchemaRegistry
from unit.platform.config.merge_support import SCOPES, WORK, key_spec

ROOT = Path(__file__).resolve().parents[4]
EXPLAIN = ROOT / "tests/fixtures/corpus/examples/config/explain-execution-review-max-rounds.json"
CLASSIFICATION = ("restricted", "confidential", "internal", "public")


def spec(
    narrow: NarrowSpec,
    schema: dict[str, Any],
    *,
    default: object = MISSING,
    override: bool = False,
    levels: frozenset[Level] = WORK,
) -> KeySpec:
    return key_spec(
        "x.ceiling",
        schema,
        MergeStrategy.NARROW,
        default=default,
        levels=levels,
        override=override,
        narrow=narrow,
    )


MIN = spec(NarrowSpec(NarrowDirection.MIN), {"type": "integer"}, default=2, override=True)
MIN_UNLIMITED = spec(NarrowSpec(NarrowDirection.MIN, unlimited=0), {"type": "number"}, default=20)
MAX = spec(NarrowSpec(NarrowDirection.MAX), {"type": "integer"}, default=1)
AND = spec(NarrowSpec(NarrowDirection.AND), {"type": "boolean"}, default=True)
OR = spec(NarrowSpec(NarrowDirection.OR), {"type": "boolean"}, default=False)
INTERSECT = spec(NarrowSpec(NarrowDirection.INTERSECT), {"type": "array"}, default=["a", "b"])
INTERSECT_UNLIMITED = spec(NarrowSpec(NarrowDirection.INTERSECT, unlimited=[]), {"type": "array"}, default=[])
ENUM = spec(
    NarrowSpec(order=CLASSIFICATION), {"type": "string", "enum": list(CLASSIFICATION)}, default="internal"
)
ENUM_MAP = spec(
    NarrowSpec(order=("advisor", "owner")),
    {"type": "object", "additionalProperties": {"type": "string", "enum": ["advisor", "owner"]}},
    default={"a": "advisor", "b": "owner"},
)


def ref(level: Level, label: str | None = None, scope_id: UUID | None = None, **extra: Any) -> LayerRef:
    if level is Level.DEFAULT:
        return LayerRef(level)
    if level is Level.PACK:
        return LayerRef(level, label=label or "", pack_id=extra.pop("pack_id", "p"), **extra)
    if level is Level.INVOCATION:
        return LayerRef(level, label="--set", source="cli")
    return LayerRef(level, scope_id or SCOPES[level], label or level.value, **extra)


def c(level: Level, value: JsonValue = None, op: str = "set", *, locked: bool = False) -> Contribution:
    return Contribution(
        ref(level), cast("Any", "default" if level is Level.DEFAULT else op), value, locked=locked
    )


def statuses(res: KeyResolution) -> list[tuple[str, str, str | None]]:
    return [(t.contribution.layer.level.value, t.status, t.reason) for t in res.trace]


D, P, IN, W, PR, PL, R, INV = (
    Level.DEFAULT,
    Level.PACK,
    Level.INSTANCE,
    Level.WORKSPACE,
    Level.PROJECT,
    Level.PLAN,
    Level.RUN,
    Level.INVOCATION,
)

# §B.5.3 scenario table for execution.review.max_rounds, narrow(min); one row per line of the table
SCENARIOS: list[tuple[str, list[tuple[Level, int, bool]], int, list[tuple[str, str | None]], Level]] = [
    (
        "explain_example",
        [(D, 2, False), (P, 3, False), (IN, 4, False), (W, 3, True), (PR, 5, False), (PL, 1, False)],
        3,
        [
            ("shadowed", None),
            ("shadowed", None),
            ("used", None),
            ("winner", None),
            ("ignored", "locked_above"),
            ("ignored", "locked_above"),
        ],
        IN,
    ),
    (
        "without_lock",
        [(D, 2, False), (P, 3, False), (IN, 4, False), (W, 3, False), (PR, 5, False), (PL, 1, False)],
        1,
        [
            ("shadowed", None),
            ("shadowed", None),
            ("used", None),
            ("used", None),
            ("ignored", "narrowing_violation"),
            ("winner", None),
        ],
        IN,
    ),
    (
        "instance_not_set",
        [(D, 2, False), (P, 3, False), (W, 5, False), (PR, 4, False)],
        4,
        [("shadowed", None), ("shadowed", None), ("used", None), ("winner", None)],
        W,
    ),
    (
        "near_levels_only",
        [(D, 2, False), (P, 3, False), (PR, 5, False), (PL, 1, False)],
        1,
        [("shadowed", None), ("shadowed", None), ("ignored", "narrowing_violation"), ("winner", None)],
        PL,
    ),
    (
        "near_levels_not_wider_than_base",
        [(D, 2, False), (P, 3, False), (PR, 3, False)],
        3,
        [("shadowed", None), ("shadowed", None), ("winner", None)],
        PR,
    ),
    ("no_explicit", [(D, 2, False), (P, 3, False)], 3, [("shadowed", None), ("winner", None)], P),
    ("default_only", [(D, 2, False)], 2, [("winner", None)], D),
]


@pytest.mark.parametrize(
    ("rows", "value", "expected", "base"),
    [row[1:] for row in SCENARIOS],
    ids=[row[0] for row in SCENARIOS],
)
def test_scenario_table(
    rows: list[tuple[Level, int, bool]], value: int, expected: list[tuple[str, str | None]], base: Level
) -> None:
    res = fold(MIN, [c(level, v, locked=locked) for level, v, locked in rows])
    assert res.value == value
    assert [(t.status, t.reason) for t in res.trace] == expected
    assert res.base == ref(base)
    winner = next(t.contribution.layer for t in res.trace if t.status == "winner")
    assert res.winner == winner


def test_near_levels_violation_names_the_base_value_as_ceiling() -> None:
    res = fold(MIN, [c(D, 2), c(P, 3), c(PR, 5), c(PL, 1)])
    (diagnostic,) = res.diagnostics
    assert diagnostic.code == "CONFIG_NARROWING_VIOLATION"
    assert diagnostic.details["violations"] == [
        {"layer": ref(PR).to_json(), "value": 5, "ceiling": 3, "ceiling_from": ref(P).to_json()}
    ]


def test_explain_example_execution_review_max_rounds_golden() -> None:
    """Golden: ``execution.review.max_rounds`` of examples/config/explain-execution-review-max-rounds.json."""
    document = json.loads(EXPLAIN.read_text())
    report = next(k for k in document["keys"] if k["key"] == "execution.review.max_rounds")
    by_label = {layer.get("label"): layer for layer in document["chain"]}

    def layer_of(doc: Mapping[str, Any]) -> LayerRef:
        level = Level(doc["level"])
        if level is Level.DEFAULT:
            return LayerRef(level)
        if level is Level.PACK:
            return LayerRef(level, pack_id=doc["pack_id"], pack_priority=doc["pack_priority"])
        return LayerRef(
            level,
            UUID(by_label[doc["label"]]["scope_id"]),
            doc["label"],
            entry_id=UUID(doc["entry_id"]),
            row_version=doc["row_version"],
        )

    rows = [
        Contribution(layer_of(entry["layer"]), entry["op"], entry["value"], locked=entry.get("locked", False))
        for entry in report["contributions"]
    ]
    res = fold(catalog_spec("execution.review.max_rounds"), rows)
    assert res.value == report["value"]
    assert [(t.status, t.reason) for t in res.trace] == [
        (entry["status"], entry.get("reason")) for entry in report["contributions"]
    ]
    assert res.winner is not None
    assert res.locked_by is not None
    assert report["winner"].items() <= res.winner.to_json().items()
    assert report["locked_by"].items() <= res.locked_by.to_json().items()
    (diagnostic,) = res.diagnostics
    (expected,) = report["diagnostics"]
    assert (diagnostic.code, diagnostic.severity.value, diagnostic.message, diagnostic.target) == (
        expected["code"],
        expected["severity"],
        expected["message"],
        expected["key"],
    )
    assert expected["layer"].items() <= cast("dict[str, Any]", diagnostic.details["layer"]).items()


def test_budget_example_with_unlimited_zero() -> None:
    """§B.5.3 budgets.run.max_usd: 0 is unlimited (+inf)."""
    res = fold(MIN_UNLIMITED, [c(D, 20), c(IN, 0), c(PR, 15), c(R, 20)])
    assert res.value == 15
    assert statuses(res)[-1] == ("run", "ignored", "narrowing_violation")
    assert fold(MIN_UNLIMITED, [c(D, 20), c(IN, 0)]).value == 0
    assert fold(MIN_UNLIMITED, [c(D, 20), c(PR, 50)]).value == 20
    assert fold(MIN_UNLIMITED, [c(D, 20), c(PR, 0)]).value == 20  # unlimited is the widest value
    assert fold(MIN_UNLIMITED, [c(D, 20), c(PR, 15)]).value == 15
    assert fold(MIN_UNLIMITED, [c(D, 20), c(W, 50)]).value == 50


def test_classification_example() -> None:
    """§B.5.3 context.max_classification_for_runtime: public is the strictest value."""
    assert fold(ENUM, [c(D, "internal"), c(IN, "confidential"), c(W, "internal")]).value == "internal"
    res = fold(ENUM, [c(D, "internal"), c(IN, "confidential"), c(W, "internal"), c(PR, "restricted")])
    assert statuses(res)[-1] == ("project", "ignored", "narrowing_violation")
    assert fold(ENUM, [c(D, "internal"), c(PR, "restricted")]).value == "internal"
    assert fold(ENUM, [c(D, "internal"), c(PR, "public")]).value == "public"


@pytest.mark.parametrize(
    ("key", "a", "b", "narrowed", "wider"),
    [
        (MIN, 4, 3, 3, False),
        (MIN, 3, 4, 3, True),
        (MIN, 3, 3, 3, False),
        (MIN_UNLIMITED, 0, 5, 5, False),
        (MIN_UNLIMITED, 5, 0, 5, True),
        (MIN_UNLIMITED, 0, 0, 0, False),
        (MIN_UNLIMITED, 2.5, 3, 2.5, True),
        (MAX, 3, 4, 4, False),
        (MAX, 4, 3, 4, True),
        (AND, True, False, False, False),
        (AND, False, True, False, True),
        (AND, True, True, True, False),
        (OR, False, True, True, False),
        (OR, True, False, True, True),
        (OR, False, False, False, False),
        (INTERSECT, ["a", "b", "c"], ["c", "a"], ["a", "c"], False),
        (INTERSECT, ["a"], ["a", "b"], ["a"], True),
        (INTERSECT, ["a"], [], [], False),
        (INTERSECT_UNLIMITED, [], ["a"], ["a"], False),
        (INTERSECT_UNLIMITED, ["a"], [], ["a"], True),
        (ENUM, "confidential", "internal", "internal", False),
        (ENUM, "internal", "confidential", "internal", True),
        (ENUM, "public", "public", "public", False),
        (ENUM_MAP, {"a": "advisor", "b": "owner"}, {"a": "owner", "c": "advisor"}, None, False),
        (ENUM_MAP, {"a": "owner"}, {"a": "advisor"}, {"a": "owner"}, True),
        (ENUM_MAP, {"a": "owner"}, {}, {"a": "owner"}, False),
    ],
)
def test_narrow_value_for_each_type(
    key: KeySpec, a: JsonValue, b: JsonValue, narrowed: Any, wider: bool
) -> None:
    expected = {"a": "owner", "b": "owner", "c": "advisor"} if narrowed is None else narrowed
    assert narrow_value(key, a, b) == expected
    assert narrow_widens(key, a, b) is wider


@pytest.mark.parametrize(
    ("key", "value"),
    [
        (MIN, True),
        (MIN, "3"),
        (AND, 0),
        (INTERSECT, "a"),
        (ENUM, "secret"),
        (ENUM, 1),
        (ENUM_MAP, {"a": "nobody"}),
        (ENUM_MAP, ["owner"]),
    ],
)
def test_values_that_cannot_be_compared_are_refused(key: KeySpec, value: JsonValue) -> None:
    good = cast("JsonValue", key.default)
    with pytest.raises(ValueError, match=r"required|is not one of"):
        narrow_value(key, good, value)
    with pytest.raises(ValueError, match=r"required|is not one of"):
        narrow_widens(key, good, value)
    res = fold(key, [c(D, good), c(IN, good), c(PR, value)])
    assert res.value == good
    assert statuses(res)[-1] == ("project", "ignored", "narrowing_violation")


def test_a_corrupt_value_cannot_open_the_chain() -> None:
    res = fold(AND, [c(D, True), c(IN, "yes"), c(PR, True)])
    assert statuses(res)[1] == ("instance", "ignored", "narrowing_violation")
    assert res.value is True
    assert res.base == ref(PR)


def test_enum_map_narrows_per_key_and_keeps_farther_keys() -> None:
    """execution.autonomy.category_audience: per category the stricter value wins; keys cannot be removed."""
    res = fold(ENUM_MAP, [c(D, {"a": "advisor", "b": "owner"}), c(PR, {"a": "owner"}), c(PL, {"c": "owner"})])
    assert res.value == {"a": "owner", "b": "owner", "c": "owner"}
    widened = fold(ENUM_MAP, [c(D, {"a": "advisor", "b": "owner"}), c(PR, {"a": "owner", "b": "advisor"})])
    assert widened.value == {"a": "advisor", "b": "owner"}
    assert statuses(widened)[-1] == ("project", "ignored", "narrowing_violation")


def test_without_explicit_contributions_pack_else_default_is_the_base() -> None:
    res = fold(MIN, [c(D, 2), c(P, 3)])
    assert (res.value, res.base, res.winner) == (3, ref(P), ref(P))
    assert fold(MIN, [c(D, 2)]).base == ref(D)
    assert fold(MIN, []).value is MISSING


def test_later_pack_replaces_an_earlier_pack_as_base() -> None:
    rows = [c(D, 2), Contribution(ref(P, pack_id="a"), "set", 5), Contribution(ref(P, pack_id="b"), "set", 4)]
    res = fold(MIN, [*rows, c(PR, 5)])
    assert res.value == 4
    assert [s for _, s, _ in statuses(res)] == ["shadowed", "shadowed", "winner", "ignored"]


@pytest.mark.parametrize("level", sorted(CHAIN_OPEN_LEVELS - {Level.HOST}))
def test_open_levels_may_start_the_chain_wider_than_the_base(level: Level) -> None:
    res = fold(MIN, [c(D, 2), c(P, 3), c(level, 9)])
    assert (res.value, res.base, res.winner) == (9, ref(level), ref(level))
    assert [s for _, s, _ in statuses(res)] == ["shadowed", "shadowed", "winner"]


@pytest.mark.parametrize("level", [PR, PL, R])
def test_member_levels_only_narrow_the_base(level: Level) -> None:
    res = fold(MIN, [c(D, 2), c(P, 3), c(level, 4)])
    assert (res.value, res.base, res.winner) == (3, ref(P), ref(P))
    assert statuses(res)[-1] == (level.value, "ignored", "narrowing_violation")


def test_member_level_starts_the_chain_when_there_is_no_base_value() -> None:
    res = fold(spec(NarrowSpec(NarrowDirection.MIN), {"type": "integer"}), [c(PR, 9), c(R, 10)])
    assert (res.value, res.base) == (9, ref(PR))
    assert statuses(res)[-1] == ("run", "ignored", "narrowing_violation")


def test_invocation_without_override_cannot_widen_or_narrow() -> None:
    key = spec(NarrowSpec(NarrowDirection.MIN), {"type": "integer"}, default=2)
    res = fold(key, [c(D, 2), c(INV, 1)])
    assert (res.value, statuses(res)[-1]) == (2, ("invocation", "ignored", "override_not_allowed"))


def test_invocation_with_override_narrows_after_explicit_levels() -> None:
    res = fold(MIN, [c(D, 2), c(IN, 4), c(INV, 5)])
    assert res.value == 4
    assert statuses(res)[-1] == ("invocation", "ignored", "narrowing_violation")
    assert fold(MIN, [c(D, 2), c(IN, 4), c(INV, 3)]).value == 3


def test_unset_and_append_are_refused_for_narrow_keys() -> None:
    res = fold(MIN, [c(D, 2), c(IN, 4), c(PR, op="unset"), c(PL, [1], "append")])
    assert res.value == 4
    assert [t.reason for t in res.trace[2:]] == ["op_not_allowed", "op_not_allowed"]
    pack_unset = fold(MIN, [c(D, 2), Contribution(ref(P), "unset", None)])
    assert (pack_unset.value, pack_unset.trace[-1].reason) == (2, "op_not_allowed")


def test_a_narrow_key_without_metadata_is_a_programming_error() -> None:
    broken = spec(NarrowSpec(), {"type": "integer"}, default=2)
    with pytest.raises(ValueError, match="direction or an order"):
        fold(broken, [c(D, 2)])


# ---------------------------------------------------------------------------------------------------------
# ceiling keys of the catalog: a member (project/plan/run) on a fresh installation cannot widen them


@cache
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def catalog_spec(key: str) -> KeySpec:
    section, *path = key.split(".")
    node: Any = schemas().get(f"urn:skm:settings:{section}:v1")
    for name in path:
        node = node["properties"][name]
    leaf = {k: v for k, v in node.items() if k not in ("default", "description", "x-skm")}
    return KeySpec.from_metadata(
        key=key,
        section=section,
        owner=section,
        value_schema=leaf,
        default=node.get("default", MISSING),
        description=node.get("description", ""),
        x_skm=node["x-skm"],
    )


# key → (value a member would like, value an operator may set): both wider than the catalog default
CEILINGS: dict[str, tuple[JsonValue, JsonValue]] = {
    "policy.ceiling.network": ("any", "any"),
    "policy.ceiling.network_allowlist": (["*"], ["example.com"]),
    "policy.ceiling.shell": (True, True),  # default true is the widest value; still never wider
    "policy.ceiling.external_effects": (["git_commit", "git_push", "publish"], ["git_commit", "git_push"]),
    "policy.ceiling.isolation_profiles": (["none", "worktree"], ["none", "worktree", "container"]),
    "runtimes.config_isolation.required": (False, False),
    "budgets.run.max_usd": (0, 1000),
    "checks.shell.allowed": (True, True),
    "context.max_classification_for_runtime": ("restricted", "confidential"),
    "execution.evidence.required": (False, False),
}


@pytest.mark.parametrize("key", sorted(CEILINGS))
def test_member_on_a_fresh_installation_does_not_widen_ceiling_keys(key: str) -> None:
    ceiling = catalog_spec(key)
    assert ceiling.merge is MergeStrategy.NARROW
    default = cast("JsonValue", ceiling.default)
    member_value, operator_value = CEILINGS[key]
    members = [level for level in (PR, PL, R) if level in ceiling.levels]
    rows = [c(D, default), *(c(level, member_value) for level in members)]
    res = fold(ceiling, rows)
    assert not narrow_widens(ceiling, default, cast("JsonValue", res.value))
    if narrow_widens(ceiling, default, member_value):
        assert res.value == default
        assert {t.reason for t in res.trace[1:]} == {"narrowing_violation"}
    # positive control: the same value from an operator level opens the chain (K16 variant A)
    opened = fold(
        ceiling, [c(D, default), c(IN, operator_value), *(c(level, member_value) for level in members)]
    )
    if narrow_widens(ceiling, operator_value, member_value):
        assert opened.value == operator_value
    else:
        assert opened.value == narrow_value(ceiling, operator_value, member_value)
    assert opened.base == ref(IN)
    # the operator value really is wider than the default (shell: the default is already the widest value)
    assert narrow_widens(ceiling, default, operator_value) is (key != "policy.ceiling.shell")


def test_union_ceiling_commands_denylist_keeps_the_default_for_members() -> None:
    denylist = catalog_spec("policy.ceiling.commands_denylist")
    default = cast("list[str]", denylist.default)
    res = fold(denylist, [c(D, cast("JsonValue", default)), c(PR, []), c(PL, ["make deploy"])])
    assert set(default) | {"make deploy"} == set(cast("list[str]", res.value))


def test_ceiling_keys_refuse_invocation_and_packs_where_the_catalog_says_so() -> None:
    shell = catalog_spec("checks.shell.allowed")
    res = fold(shell, [c(D, False), c(P, True), c(INV, True)])
    assert res.value is False
    assert [t.reason for t in res.trace[1:]] == ["pack_not_allowed", "override_not_allowed"]


# ---------------------------------------------------------------------------------------------------------
# properties


ORDER = [P, IN, W, PR, PL, R, INV]
VALUES: list[tuple[KeySpec, st.SearchStrategy[JsonValue]]] = [
    (MIN, st.integers(0, 6)),
    (MIN_UNLIMITED, st.integers(0, 6)),
    (MAX, st.integers(0, 6)),
    (AND, st.booleans()),
    (OR, st.booleans()),
    (INTERSECT, cast("st.SearchStrategy[JsonValue]", st.lists(st.sampled_from("abcd"), unique=True))),
    (
        INTERSECT_UNLIMITED,
        cast("st.SearchStrategy[JsonValue]", st.lists(st.sampled_from("abcd"), unique=True)),
    ),
    (ENUM, st.sampled_from(CLASSIFICATION)),
    (
        ENUM_MAP,
        cast(
            "st.SearchStrategy[JsonValue]",
            st.dictionaries(st.sampled_from("abc"), st.sampled_from(["advisor", "owner"]), max_size=3),
        ),
    ),
]


@st.composite
def chains(draw: st.DrawFn) -> tuple[KeySpec, list[Contribution]]:
    key, values = draw(st.sampled_from(VALUES))
    rows = [c(D, draw(values))] if draw(st.booleans()) else []
    levels = draw(st.lists(st.sampled_from(ORDER), max_size=7))
    rows += [c(level, draw(values)) for level in sorted(levels, key=ORDER.index)]
    return key, rows


@given(chains())
def test_result_is_never_wider_than_any_applied_explicit_value(
    case: tuple[KeySpec, list[Contribution]],
) -> None:
    key, rows = case
    res = fold(key, rows)
    applied = [t.contribution for t in res.trace if t.status != "ignored"]
    explicit = [item for item in applied if item.layer.level in EXPLICIT_LEVELS]
    reasons = {t.reason for t in res.trace if t.status == "ignored"}
    assert reasons <= {"narrowing_violation", "override_not_allowed"}
    assert key.override or not any(item.layer.level is INV for item in applied)
    if res.value is MISSING:
        assert not applied
        return
    value = cast("JsonValue", res.value)
    for item in explicit:
        assert not narrow_widens(key, item.value, value)
    if explicit:
        assert res.base == explicit[0].layer
    base = [item for item in applied if item.layer.level in (D, P)]
    if base and not any(item.layer.level in CHAIN_OPEN_LEVELS for item in explicit):
        assert not narrow_widens(key, base[-1].value, value)
