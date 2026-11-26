"""``plan_import``: the pure diff of an import document and the current entries (settings §A.4, §A.7.6)."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from runpy import run_path
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import pytest

from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.json_types import JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.settings.domain.entry import VALUE_MAX_BYTES, ConfigEntry, ConfigEntryId, EntryOp, new_entry
from skm.modules.settings.domain.import_plan import ChangeType, EntryChange, ImportPlan, plan_import
from skm.modules.settings.domain.write_rules import WriteContext, WriteRequest, collect_write_problems
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.sources.document import ConfigDocument, DocEntry, parse_document

ROOT = Path(__file__).resolve().parents[4]
SCOPE = ScopeRef(ScopeKind.WORKSPACE, ScopeId(UUID(int=1)))
ACTOR = PrincipalId(UUID(int=2))
NOW = datetime(2026, 10, 28, tzinfo=UTC)


def stored(
    key: str, value: JsonValue | None, *, op: EntryOp = EntryOp.SET, locked: bool = False
) -> ConfigEntry:
    return new_entry(
        entry_id=ConfigEntryId(uuid4()),
        scope=SCOPE,
        key=key,
        op=op,
        value=value,
        locked=locked,
        reason="",
        actor=ACTOR,
        now=NOW,
    )


def current(*entries: ConfigEntry) -> dict[str, ConfigEntry]:
    return {entry.key: entry for entry in entries}


def document(
    entries: Mapping[str, tuple[str, JsonValue]], locks: frozenset[str] = frozenset()
) -> ConfigDocument:
    return ConfigDocument(
        {key: DocEntry(cast("Any", op), value) for key, (op, value) in entries.items()}, locks, ()
    )


def summary(plan: ImportPlan) -> list[tuple[str, str]]:
    return [(change.key, change.change.value) for change in plan.changes]


EXISTING = current(
    stored("demo.a", 1),
    stored("demo.b", "x", locked=True),
    stored("demo.c", [1], op=EntryOp.APPEND),
    stored("demo.d", None, op=EntryOp.UNSET),
)
DOC = document(
    {
        "demo.a": ("set", 1),  # unchanged
        "demo.b": ("set", "x"),  # same value, the document does not lock it → lock_changed
        "demo.c": ("set", [1]),  # same value, other operation → updated
        "demo.e": ("set", {"k": 1}),  # added
    }
)


def test_merge_leaves_other_entries_untouched() -> None:
    plan = plan_import(EXISTING, DOC, mode="merge")
    assert summary(plan) == [
        ("demo.a", "unchanged"),
        ("demo.b", "lock_changed"),
        ("demo.c", "updated"),
        ("demo.e", "added"),
    ]
    by_key = {change.key: change for change in plan.changes}
    assert by_key["demo.b"].before == (EntryOp.SET, "x", True)
    assert by_key["demo.b"].after == (EntryOp.SET, "x", False)
    assert by_key["demo.b"].lock_change
    assert by_key["demo.e"].before is None
    assert by_key["demo.e"].after == (EntryOp.SET, {"k": 1}, False)
    assert not by_key["demo.a"].lock_change
    assert [change.key for change in plan.effective] == ["demo.b", "demo.c", "demo.e"]


def test_replace_also_removes_keys_missing_from_the_document() -> None:
    plan = plan_import(EXISTING, DOC, mode="replace")
    assert summary(plan) == [
        ("demo.a", "unchanged"),
        ("demo.b", "lock_changed"),
        ("demo.c", "updated"),
        ("demo.d", "removed"),
        ("demo.e", "added"),
    ]
    removed = plan.changes[3]
    assert (removed.before, removed.after) == ((EntryOp.UNSET, None, False), None)


def test_document_locks_decide_the_flag() -> None:
    plan = plan_import(
        current(stored("demo.a", 1), stored("demo.b", 2)),
        document({"demo.a": ("set", 1), "demo.b": ("set", 3)}, frozenset({"demo.a", "demo.b"})),
        mode="merge",
    )
    assert summary(plan) == [("demo.a", "lock_changed"), ("demo.b", "updated")]
    assert plan.changes[1].after == (EntryOp.SET, 3, True)
    assert plan.changes[1].lock_change  # an update that also locks still needs config.lock
    assert plan_import({}, document({"demo.a": ("set", 1)}, frozenset({"demo.a"})), mode="merge").changes[
        0
    ].after == (EntryOp.SET, 1, True)


@pytest.mark.parametrize(
    ("before", "after", "change"),
    [
        (1, 1.0, "updated"),  # strict identity: the stored value and its digest would change
        (1, True, "updated"),
        ({"a": 1, "b": 2}, {"b": 2, "a": 1}, "unchanged"),
        ([1, 2], [2, 1], "updated"),
    ],
)
def test_value_comparison_is_strict(before: JsonValue, after: JsonValue, change: str) -> None:
    plan = plan_import(current(stored("demo.a", before)), document({"demo.a": ("set", after)}), mode="merge")
    assert summary(plan) == [("demo.a", change)]


def test_unset_and_append_operations() -> None:
    plan = plan_import(
        current(stored("demo.a", 1), stored("demo.b", None, op=EntryOp.UNSET)),
        document({"demo.a": ("unset", None), "demo.b": ("unset", None), "demo.c": ("append", ["x"])}),
        mode="merge",
    )
    assert summary(plan) == [("demo.a", "updated"), ("demo.b", "unchanged"), ("demo.c", "added")]
    assert plan.changes[0].after == (EntryOp.UNSET, None, False)
    assert plan.changes[2].after == (EntryOp.APPEND, ["x"], False)


def test_changes_are_sorted_by_key() -> None:
    keys = ["demo.z", "demo.b", "alpha.m", "demo.a"]
    plan = plan_import({}, document(dict.fromkeys(keys, ("set", 1))), mode="replace")
    assert [change.key for change in plan.changes] == sorted(keys)
    with pytest.raises(ValueError, match="sorted"):
        ImportPlan(tuple(reversed(plan.changes)))
    with pytest.raises(ValueError, match="sorted"):
        ImportPlan((plan.changes[0], plan.changes[0]))


def test_empty_document() -> None:
    assert plan_import(EXISTING, document({}), mode="merge").changes == ()
    assert {change.change for change in plan_import(EXISTING, document({}), mode="replace").changes} == {
        ChangeType.REMOVED
    }


def test_shape_and_argument_errors() -> None:
    with pytest.raises(ValueError, match="mode"):
        plan_import({}, document({}), mode=cast("Any", "overwrite"))
    with pytest.raises(ValueError, match="listed under"):
        plan_import({"demo.x": stored("demo.a", 1)}, document({}), mode="merge")
    with pytest.raises(ValueError, match="before/after"):
        EntryChange("demo.a", ChangeType.ADDED, (EntryOp.SET, 1, False), (EntryOp.SET, 1, False))
    with pytest.raises(ValueError, match="before/after"):
        EntryChange("demo.a", ChangeType.REMOVED, (EntryOp.SET, 1, False), (EntryOp.SET, 1, False))
    with pytest.raises(ValueError, match="before/after"):
        EntryChange("demo.a", ChangeType.UPDATED, None, (EntryOp.SET, 1, False))
    with pytest.raises(ValueError, match="unset"):
        EntryChange("demo.a", ChangeType.ADDED, None, (EntryOp.UNSET, 1, False))
    # before is a stored entry and keeps the DDL invariants
    with pytest.raises(ValueError, match="unset"):
        EntryChange("demo.a", ChangeType.UPDATED, (EntryOp.SET, None, False), (EntryOp.SET, 1, False))
    with pytest.raises(ValueError, match="array"):
        EntryChange("demo.a", ChangeType.UPDATED, (EntryOp.APPEND, "x", False), (EntryOp.SET, 1, False))
    with pytest.raises(TypeError, match="locked"):
        EntryChange("demo.a", ChangeType.ADDED, None, (EntryOp.SET, 1, cast("Any", 1)))
    with pytest.raises(TypeError, match="JSON"):
        EntryChange("demo.a", ChangeType.ADDED, None, (EntryOp.SET, cast("Any", (1, 2)), False))


def test_after_is_a_copy_of_the_document_value() -> None:
    value: dict[str, JsonValue] = {"k": [1]}
    change = EntryChange("demo.a", ChangeType.ADDED, None, (EntryOp.SET, value, False))
    cast("list[JsonValue]", value["k"]).append(2)
    assert change.after == (EntryOp.SET, {"k": [1]}, False)


@cache
def rule_helpers() -> dict[str, Any]:
    return run_path(str(Path(__file__).with_name("test_write_rules.py")))


def write_problems(change: EntryChange) -> list[tuple[str, str, str | None]]:
    """The import's R1-R16 check of one planned change (§A.7.6), as ``ImportConfig`` runs it."""
    helpers = rule_helpers()
    spec = owner_registry().spec(change.key)
    assert change.after is not None
    op, value, locked = change.after
    req = WriteRequest(SCOPE, change.key, op, value, locked, None, True, "write")
    before = change.before
    existing = None
    if before is not None:
        existing = stored(change.key, before[1], op=before[0], locked=before[2])
    ctx = WriteContext(
        spec, existing, helpers["farther"](spec), helpers["ALL_RIGHTS"], helpers["EngineChecks"](spec)
    )
    return [(problem.rule, problem.code, problem.pointer) for problem in collect_write_problems(req, ctx)]


DOCUMENT_SCHEMA = "urn:skm:settings:document:v1"


@pytest.mark.parametrize(
    ("data", "key", "op", "value", "existing"),
    [
        (
            {"append": {"execution.generation.command": "python3"}},
            "execution.generation.command",
            EntryOp.APPEND,
            "python3",
            stored("execution.generation.command", ["make"]),
        ),
        (
            {"execution": {"review": {"max_rounds": None}}},
            "execution.review.max_rounds",
            EntryOp.SET,
            None,
            stored("execution.review.max_rounds", 2),
        ),
    ],
)
@pytest.mark.parametrize("mode", ["merge", "replace"])
def test_document_values_invalid_for_an_entry_reach_r5(
    data: dict[str, JsonValue],
    key: str,
    op: EntryOp,
    value: JsonValue,
    existing: ConfigEntry,
    mode: Literal["merge", "replace"],
) -> None:
    """append of a non-array and set of null parse cleanly and are R5 problems of the import, not a crash."""
    parsed = parse_document(json.dumps({"schema": DOCUMENT_SCHEMA, **data}), "json", owner_registry())
    assert not parsed.problems
    for entries, change_type in ((current(), ChangeType.ADDED), (current(existing), ChangeType.UPDATED)):
        plan = plan_import(entries, parsed, mode=mode)
        (change,) = plan.changes
        assert (change.key, change.change, change.after) == (key, change_type, (op, value, False))
        found = write_problems(change)
        assert found, found
        assert {(rule, code) for rule, code, _ in found} == {("R5", "CONFIG_INVALID")}


STORED_OF: dict[str, JsonValue] = {
    "execution.review.max_rounds": 2,
    "execution.workflow.profile_by_work_kind": {"docs": "quick-fix"},
    "execution.generation.command": ["make"],
}


@pytest.mark.parametrize(
    ("data", "key", "op", "pointer"),
    [
        ({"execution": {"review": {"max_rounds": "\ud800"}}}, "execution.review.max_rounds", EntryOp.SET, ""),
        (
            {"execution": {"workflow": {"profile_by_work_kind": {"\ud800": "quick-fix"}}}},
            "execution.workflow.profile_by_work_kind",
            EntryOp.SET,
            "",
        ),
        (
            {"execution": {"workflow": {"profile_by_work_kind": {"docs": "quick\udfff"}}}},
            "execution.workflow.profile_by_work_kind",
            EntryOp.SET,
            "/docs",
        ),
        (
            {"append": {"execution.generation.command": "\ud800"}},
            "execution.generation.command",
            EntryOp.APPEND,
            "",
        ),
        (
            {"append": {"execution.generation.command": ["make", "\ud800"]}},
            "execution.generation.command",
            EntryOp.APPEND,
            "/1",
        ),
    ],
)
@pytest.mark.parametrize("mode", ["merge", "replace"])
def test_parsed_lone_surrogates_are_planned_and_reach_r5(
    data: dict[str, JsonValue], key: str, op: EntryOp, pointer: str, mode: Literal["merge", "replace"]
) -> None:
    """A JSON ``\\ud800`` escape parses to a lone surrogate: the plan keeps it and R5 reports it."""
    text = json.dumps({"schema": DOCUMENT_SCHEMA, **data})  # ASCII: the surrogates travel as escapes
    parsed = parse_document(text, "json", owner_registry())
    assert not parsed.problems
    existing = stored(key, STORED_OF[key])
    for entries, change_type in ((current(), ChangeType.ADDED), (current(existing), ChangeType.UPDATED)):
        (change,) = plan_import(entries, parsed, mode=mode).changes
        assert (change.key, change.change) == (key, change_type)
        assert change.after is not None
        assert change.after[0] is op
        assert write_problems(change) == [("R5", "CONFIG_INVALID", pointer)]


W641 = 10**640  # 641 digits: wider than the lowest int-to-text limit
W5001 = 10**5000 + 7  # 5001 digits: wider than the default limit


@pytest.mark.parametrize(
    ("key", "op", "value", "pointer"),
    [
        pytest.param("execution.review.max_rounds", "set", W5001, "", id="set-int5001"),
        pytest.param("execution.workflow.profile_by_work_kind", "set", {"docs": W5001}, "/docs", id="map"),
        pytest.param("execution.generation.command", "append", ["make", -W5001], "/1", id="append-item"),
        pytest.param("execution.generation.command", "append", W5001, "", id="append-int5001"),
    ],
)
@pytest.mark.parametrize("limit", [4300, 0])
def test_wide_integers_of_a_document_are_planned_and_reach_r5(
    key: str, op: str, value: JsonValue, pointer: str, limit: int
) -> None:
    """A 5001-digit integer is planned as written; where the key schema refuses it, R5 says so (whether or
    not the interpreter may write the integer into the engine's finding)."""
    with rule_helpers()["int_text_limit"](limit):
        for entries in (current(), current(stored(key, STORED_OF[key]))):
            (change,) = plan_import(entries, document({key: (op, value)}), mode="merge").changes
            assert change.after == (EntryOp(op), value, False)
            assert write_problems(change) == [("R5", "CONFIG_INVALID", pointer)]


@pytest.mark.parametrize(
    ("key", "op", "value"),
    [
        pytest.param("execution.review.max_rounds", "set", 10**VALUE_MAX_BYTES, id="int65537"),
        pytest.param(
            "execution.workflow.profile_by_work_kind", "set", {"docs": "x" * VALUE_MAX_BYTES}, id="map"
        ),
        pytest.param("execution.generation.command", "append", ["make", 10**1_000_000], id="append-huge"),
    ],
)
def test_document_values_over_64_kib_are_planned_and_reach_r5(key: str, op: str, value: JsonValue) -> None:
    for entries in (current(), current(stored(key, STORED_OF[key]))):
        (change,) = plan_import(entries, document({key: (op, value)}), mode="merge").changes
        assert write_problems(change) == [("R5", "CONFIG_INVALID", "")]


def test_stored_before_must_be_storable() -> None:
    values: tuple[JsonValue, ...] = (
        "\ud800",
        {"\udc00": 1},
        {"n": 10 ** (VALUE_MAX_BYTES - 6)},  # 65537 bytes of canonical JSON
        "x" * (VALUE_MAX_BYTES - 1),
    )
    for value in values:
        with pytest.raises(ValueError, match="not storable canonical JSON"):
            EntryChange("demo.a", ChangeType.UPDATED, (EntryOp.SET, value, False), (EntryOp.SET, 1, False))
        with pytest.raises(ValueError, match="not storable canonical JSON"):
            stored("demo.a", value)
        # the document side is a request: it is kept for R5
        change = EntryChange("demo.a", ChangeType.ADDED, None, (EntryOp.SET, value, False))
        assert change.after == (EntryOp.SET, value, False)


@pytest.mark.parametrize("limit", [640, 4300, 0])
def test_wide_integers_are_stored_and_diffed_exactly(limit: int) -> None:
    """Stored and planned sides accept the same integers: any width up to 64 KiB of canonical JSON."""
    edge: JsonValue = {"n": 10 ** (VALUE_MAX_BYTES - 6) - 1}  # exactly 65536 bytes
    wide: JsonValue = {"n": W5001}
    with rule_helpers()["int_text_limit"](limit):
        existing = current(stored("demo.a", wide), stored("demo.b", [W641]), stored("demo.c", edge))
        doc = document(
            {
                "demo.a": ("set", wide),  # unchanged
                "demo.b": ("set", [W641 + 1]),  # the next integer is another value
                "demo.c": ("set", edge),  # unchanged at the size edge
                "demo.d": ("set", -W5001),  # added
            }
        )
        plan = plan_import(existing, doc, mode="replace")
        assert summary(plan) == [
            ("demo.a", "unchanged"),
            ("demo.b", "updated"),
            ("demo.c", "unchanged"),
            ("demo.d", "added"),
        ]
        assert plan.changes[1].before == (EntryOp.SET, [W641], False)


@cache
def owner_registry() -> SettingsRegistry:
    inputs = run_path(str(ROOT / "tests/unit/platform/config/test_registry_all_sections.py"))
    return cast("SettingsRegistry", inputs["real_registry"]())


def test_project_import_example() -> None:
    text = (ROOT / "tests/fixtures/corpus/examples/config/project-import.toml").read_text(encoding="utf-8")
    parsed = parse_document(text, "toml", owner_registry())
    assert not parsed.problems
    existing = current(
        stored("execution.review.max_rounds", 2),
        stored("integrations.targets", ["codex"]),
        stored("context.rules.extra", ["Write code, comments and docs of this repository in English."]),
    )
    merge = {change.key: change for change in plan_import(existing, parsed, mode="merge").changes}
    assert merge["execution.review.max_rounds"].change is ChangeType.UNCHANGED
    assert merge["context.rules.extra"].change is ChangeType.UNCHANGED
    assert merge["integrations.targets"].change is ChangeType.UPDATED
    assert merge["execution.consilium.members"].after == (EntryOp.UNSET, None, False)
    assert merge["execution.generation.command"].after == (EntryOp.APPEND, ["python3", "tools/gen.py"], False)
    assert merge["budgets.run.max_usd"].after == (EntryOp.SET, 15.0, False)
    profiles = merge["execution.workflow.profile_by_work_kind"].after
    assert profiles is not None
    assert profiles[1] == {"docs": "quick-fix", "research": {"$unset": True}}
    assert set(merge) == set(parsed.entries)
    assert {change.change for key, change in merge.items() if key not in existing} == {ChangeType.ADDED}
    replace_plan = plan_import({**existing, "demo.gone": stored("demo.gone", 1)}, parsed, mode="replace")
    assert {(c.key, c.change) for c in replace_plan.changes if c.key not in parsed.entries} == {
        ("demo.gone", ChangeType.REMOVED)
    }
