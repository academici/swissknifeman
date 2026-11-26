"""Authority monotonicity of the catalog ceiling keys (settings §B.5.3, §B.5.6, K16 variant A).

Source idea: ``packages/orch/tests/test_authority_monotonic.py`` (legacy orch floors, 10 tests). The scenarios
below are restated from settings §B.5.3/§B.5.6 and ``legacy-map/orch.md``: an operator level sets the
ceiling, nearer levels only tighten it, and the expectations are an explicit table, not derived from the
implementation. Keys and metadata come from the packaged section schemas.
"""

from functools import cache
from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import MISSING, KeySpec, Level
from skm.platform.config.merge import KeyResolution, fold, narrow_widens
from skm.platform.schema.registry import SchemaRegistry
from unit.platform.config.merge_support import contribution as c
from unit.platform.config.merge_support import layer_ref as ref

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


@cache
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


@cache
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


def resolve(key: str, rows: list[tuple[Level, JsonValue] | tuple[Level, JsonValue, bool]]) -> KeyResolution:
    spec = catalog_spec(key)
    built = [c(D, cast("JsonValue", spec.default))]
    built += [c(row[0], row[1], locked=len(row) == 3 and bool(row[2])) for row in rows]
    return fold(spec, built)


Row = tuple[Level, JsonValue] | tuple[Level, JsonValue, bool]
U, S, X = "used", "shadowed", "ignored"
WIN = "winner"

# name, key, explicit rows (after the catalog default), expected value, expected statuses (default first)
TABLE: list[tuple[str, str, list[Row], JsonValue, list[str]]] = [
    (
        "operator_ceiling_member_tightens",
        "policy.ceiling.network",
        [(IN, "allowlist"), (PR, "none")],
        "none",
        [S, U, WIN],
    ),
    (
        "member_cannot_loosen_operator",
        "policy.ceiling.network",
        [(IN, "none"), (PR, "any"), (R, "allowlist")],
        "none",
        [S, WIN, X, X],
    ),
    (
        "workspace_cannot_loosen_instance",
        "policy.ceiling.shell",
        [(IN, False), (W, True), (PL, True)],
        False,
        [S, WIN, X, X],
    ),
    (
        "budget_unlimited_below_a_limit_is_refused",
        "budgets.run.max_usd",
        [(IN, 50), (W, 0), (R, 10)],
        10,
        [S, U, X, WIN],
    ),
    (
        "isolation_profiles_intersect",
        "policy.ceiling.isolation_profiles",
        [(IN, ["worktree", "container"]), (PR, ["container", "none"]), (PL, ["container"])],
        ["container"],
        [S, U, X, WIN],
    ),
    (
        "operator_relaxes_member_requires_config_isolation",
        "runtimes.config_isolation.required",
        [(IN, False), (PR, True), (PL, False)],
        True,
        [S, U, WIN, X],
    ),
    (
        "classification_cannot_be_raised_back",
        "context.max_classification_for_runtime",
        [(W, "public"), (PR, "internal")],
        "public",
        [S, WIN, X],
    ),
    (
        "lock_freezes_the_ceiling",
        "execution.review.max_rounds",
        [(IN, 4), (W, 3, True), (PR, 1)],
        3,
        [S, U, WIN, X],
    ),
    (
        "denylist_accumulates_and_never_shrinks",
        "policy.ceiling.commands_denylist",
        [(IN, ["curl"]), (PR, []), (R, ["wget"])],
        ["curl", "git push --force", "git reset --hard", "rm -rf /", "wget"],
        [U, U, U, WIN],
    ),
    (
        "fresh_installation_member_only",
        "checks.shell.allowed",
        [(PR, True)],
        False,
        [WIN, X],
    ),
]


@pytest.mark.parametrize(
    ("key", "rows", "value", "expected"),
    [row[1:] for row in TABLE],
    ids=[row[0] for row in TABLE],
)
def test_authority_monotonic_table(key: str, rows: list[Row], value: JsonValue, expected: list[str]) -> None:
    res = resolve(key, rows)
    assert res.value == value
    assert [t.status for t in res.trace] == expected
    assert {t.reason for t in res.trace if t.status == "ignored"} <= {"narrowing_violation", "locked_above"}


def test_stale_member_contribution_after_the_operator_tightened() -> None:
    """The operator lowers the ceiling below an older project value: the project value no longer applies."""
    before = resolve("budgets.run.max_usd", [(IN, 30), (PR, 25)])
    after = resolve("budgets.run.max_usd", [(IN, 15), (PR, 25)])
    assert (before.value, after.value) == (25, 15)
    assert after.trace[-1].reason == "narrowing_violation"
    assert after.diagnostics[0].details["violations"] == [
        {"layer": ref(PR).to_json(), "value": 25, "ceiling": 15, "ceiling_from": ref(IN).to_json()}
    ]


def test_member_invocation_cannot_override_a_ceiling() -> None:
    res = resolve("policy.ceiling.network", [(INV, "any")])
    assert res.value == "allowlist"
    assert res.trace[-1].reason == "override_not_allowed"


# ---------------------------------------------------------------------------------------------------------
# property: a chain with only project/plan/run contributions is never wider than the base value

ENUMS = {
    "policy.ceiling.external_effects": ["git_commit", "git_push", "pr_create", "message", "publish"],
    "policy.ceiling.isolation_profiles": ["none", "worktree", "landlock", "container", "acme:box"],
    "policy.ceiling.network_allowlist": ["*", "example.com", "a.example:443"],
}
MEMBER_VALUES: dict[str, st.SearchStrategy[JsonValue]] = {
    "policy.ceiling.network": st.sampled_from(["any", "allowlist", "none"]),
    "policy.ceiling.shell": st.booleans(),
    "runtimes.config_isolation.required": st.booleans(),
    "budgets.run.max_usd": st.one_of(st.integers(0, 200), st.floats(0, 200, allow_nan=False)),
    "checks.shell.allowed": st.booleans(),
    "context.max_classification_for_runtime": st.sampled_from(
        ["public", "internal", "confidential", "restricted"]
    ),
    "execution.evidence.required": st.booleans(),
    "execution.review.max_rounds": st.integers(1, 10),
    **{
        key: cast("st.SearchStrategy[JsonValue]", st.lists(st.sampled_from(items), unique=True))
        for key, items in ENUMS.items()
    },
}


@given(
    key=st.sampled_from(sorted(MEMBER_VALUES)),
    data=st.data(),
    levels=st.lists(st.sampled_from([PR, PL, R]), min_size=1, max_size=4),
)
def test_member_only_chain_is_never_wider_than_the_base(
    key: str, data: st.DataObject, levels: list[Level]
) -> None:
    spec = catalog_spec(key)
    order = [PR, PL, R]
    rows: list[Row] = [
        (level, data.draw(MEMBER_VALUES[key]))
        for level in sorted(levels, key=order.index)
        if level in spec.levels
    ]
    res = resolve(key, rows)
    assert not narrow_widens(spec, cast("JsonValue", spec.default), cast("JsonValue", res.value))
    for trace in res.trace[1:]:
        if trace.status != "ignored":
            assert not narrow_widens(spec, trace.contribution.value, cast("JsonValue", res.value))
