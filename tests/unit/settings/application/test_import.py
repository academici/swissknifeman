"""``settings.import_config`` through the bus (settings §A.7.6, §B.5, §B.11.4).

Invariants: a dry run writes nothing and shows exactly what applying the same document does; every problem
is collected before anything is written and a failed import (a rule or a cross-key validator) leaves no
entry, history, generation or event; one import is one generation and one ``ConfigChanged``; export →
import is a no-op; an exported scope without a local entry exports the absence, so the import creates no
override and the inherited value keeps following its farther level. Explicit unset, removing the entry,
setting an empty value and leaving the key out of a merge document are four different results.
"""

from pathlib import Path
from runpy import run_path
from typing import Any, cast

import pytest

from skm.application_bus.middleware import request_digest
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.settings.application.commands import import_config as import_module
from skm.modules.settings.domain.history import ChangeKind
from skm.modules.settings.generated import commands, queries

h = run_path(str(Path(__file__).with_name("test_commands.py")))
harness, set_value, refused, allowed_audit = h["harness"], h["set_value"], h["refused"], h["allowed_audit"]
PROJECT, PLAN, SCOPE_IDS = h["PROJECT"], h["PLAN"], h["SCOPE_IDS"]

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = (ROOT / "tests/fixtures/corpus/examples/config/project-import.toml").read_text(encoding="utf-8")
ROUNDS = "execution.review.max_rounds"
TARGETS = "integrations.targets"


def import_config(level: str, document: Any, **fields: Any) -> commands.ImportConfig:
    fields.setdefault("format", "toml" if isinstance(document, str) else "json")
    return commands.ImportConfig(
        scope=commands.ImportConfigDefsScopeRef(level=level, scope_id=SCOPE_IDS[level]),  # type: ignore[arg-type]
        document=document,
        **fields,
    )


def export_config(level: str, fmt: str = "toml", **fields: Any) -> queries.ExportConfig:
    return queries.ExportConfig(
        scope=queries.ExportConfigDefsScopeRef(level=level, scope_id=SCOPE_IDS[level]),  # type: ignore[arg-type]
        format=fmt,  # type: ignore[arg-type]
        **fields,
    )


def get_value(level: str, key: str) -> Any:
    return queries.GetValue(
        scope=queries.GetValueDefsScopeRef(level=level, scope_id=SCOPE_IDS[level]),  # type: ignore[arg-type]
        key=key,
    )


def effective(made: Any, level: str, key: str) -> Any:
    return made.ask(get_value(level, key)).value


def codes(error: SkmError) -> list[str]:
    return sorted(
        cast("dict[str, Any]", item)["code"] for item in cast("list[Any]", error.details["problems"])
    )


# ---------------------------------------------------------------------------------------------------------
# dry run and apply


def test_dry_run_of_the_example_writes_nothing_and_apply_matches_the_preview() -> None:
    made = harness()
    made.run(set_value("instance", ROUNDS, 4))
    before = made.snapshot()
    preview = made.run(import_config("project", EXAMPLE, dry_run=True, confirmed=True))
    assert made.snapshot() == before
    assert (preview.dry_run, preview.applied, preview.generation, preview.problems) == (True, False, None, ())
    keys = [item.key for item in preview.changes]
    assert keys == sorted(keys)
    assert "execution.generation.command" in keys
    assert {item.change for item in preview.changes} == {"added"}
    unset = next(item for item in preview.changes if item.key == "execution.consilium.members")
    assert unset.after == {"op": "unset", "locked": False}
    diff = {item.key: (item.before, item.after) for item in preview.effective_diff}
    assert diff[ROUNDS] == (4, 2)
    assert diff["budgets.run.max_usd"] == (20.0, 15.0)
    assert diff["execution.generation.command"] == ([], ["python3", "tools/gen.py"])
    assert diff["execution.workflow.profile_by_work_kind"] == (
        {"research": "research-only"},
        {"docs": "quick-fix"},
    )

    applied = made.run(import_config("project", EXAMPLE, confirmed=True))
    assert (applied.dry_run, applied.applied, applied.generation) == (False, True, 2)
    assert applied.changes == preview.changes
    assert applied.effective_diff == preview.effective_diff
    assert applied.entries_digest_after == preview.entries_digest_after
    assert applied.entries_digest_before == preview.entries_digest_before
    created = [record for record in made.history if record.generation == 2]
    assert len(created) == len(keys)
    assert {record.change_kind for record in created} == {ChangeKind.CREATED}
    [event] = [event for event in made.events if event.payload["generation"] == 2]
    assert event.payload["keys"] == keys
    assert set(event.payload["changes"].values()) == {"created"}
    for item in applied.effective_diff:
        assert effective(made, "project", item.key) == item.after


def test_every_problem_is_collected_and_a_failed_import_writes_nothing() -> None:
    made = harness()
    document = {
        "schema": "urn:skm:settings:document:v1",
        "execution": {"review": {"max_rounds": 9}, "workflow": {"profile": 7}},
        "nope": {"key": 1},
        "unset": ["execution.advisor.human_gate"],
        "append": {"execution.generation.command": ["x"]},
    }
    preview = made.run(import_config("project", document, dry_run=True))
    found = sorted(item.code for item in preview.problems)
    assert found == sorted(
        [
            "CONFIG_INVALID",  # profile is not a string
            "CONFIG_NARROWING_VIOLATION",  # 9 is wider than the default 2
            "CONFIG_OP_NOT_ALLOWED",  # unset of a union key
            "CONFIRMATION_REQUIRED",  # generation.command needs confirmed
            "CONFIG_UNKNOWN_KEY",  # nope.key
        ]
    )
    assert {item.key for item in preview.problems} >= {ROUNDS, "execution.workflow.profile"}
    error = refused(made, import_config("project", document), ErrorCode.CONFIG_INVALID)
    assert codes(error) == sorted(item.code for item in preview.problems)


def test_a_failed_cross_key_candidate_leaves_no_trace() -> None:
    made = harness()
    document = {"budgets": {"run": {"max_usd": 10}, "task": {"max_usd": 15}}}
    preview = made.run(import_config("project", document, dry_run=True))
    assert [item.code for item in preview.problems] == ["CONFIG_INVALID"]
    assert preview.problems[0].key == "budgets.run.max_usd"
    error = refused(made, import_config("project", document), ErrorCode.CONFIG_INVALID)
    assert codes(error) == ["CONFIG_INVALID"]
    assert made.entries("project") == {}
    assert made.generation == 0
    assert made.history == []
    assert made.events == []


def test_cas_digest_guards_the_whole_scope() -> None:
    made = harness()
    first = made.run(import_config("project", {"execution": {"review": {"max_rounds": 1}}}))
    stale = first.entries_digest_before
    error = refused(
        made,
        import_config("project", {"execution": {"review": {"max_rounds": 2}}}, expected_entries_digest=stale),
        ErrorCode.VERSION_CONFLICT,
    )
    assert error.details == {"expected": stale, "actual": first.entries_digest_after}
    fresh = import_config(
        "project",
        {"execution": {"review": {"max_rounds": 2}}},
        expected_entries_digest=first.entries_digest_after,
    )
    assert made.run(fresh).changes[0].change == "updated"


def test_replace_removes_absent_entries_and_merge_keeps_them() -> None:
    made = harness()
    made.run(
        import_config(
            "project", {"execution": {"review": {"max_rounds": 1}, "workflow": {"profile": "quick-fix"}}}
        )
    )
    merged = made.run(import_config("project", {"execution": {"review": {"max_rounds": 2}}}))
    assert [(item.key, item.change) for item in merged.changes] == [(ROUNDS, "updated")]
    assert set(made.entries("project")) == {ROUNDS, "execution.workflow.profile"}
    replaced = made.run(
        import_config("project", {"execution": {"review": {"max_rounds": 2}}}, mode="replace")
    )
    assert [(item.key, item.change) for item in replaced.changes] == [
        (ROUNDS, "unchanged"),
        ("execution.workflow.profile", "removed"),
    ]
    assert set(made.entries("project")) == {ROUNDS}
    assert made.history[-1].change_kind is ChangeKind.REMOVED


def test_lock_changes_are_their_own_change_kind() -> None:
    made = harness()
    made.run(set_value("workspace", ROUNDS, 3))
    result = made.run(
        import_config("workspace", {"lock": [ROUNDS], "execution": {"review": {"max_rounds": 3}}})
    )
    assert [(item.key, item.change) for item in result.changes] == [(ROUNDS, "lock_changed")]
    assert made.history[-1].change_kind is ChangeKind.LOCKED
    assert [event.type.split(":")[-2] for event in made.events[-2:]] == ["config-changed", "config-locked"]
    assert made.events[-2].payload["changes"] == {ROUNDS: "lock_changed"}
    locked_project = refused(
        made,
        import_config("project", {"lock": [ROUNDS], "execution": {"review": {"max_rounds": 1}}}),
        ErrorCode.CONFIG_INVALID,
    )
    # R7: workspace locks the key above; R9: a lock only at instance/workspace; both are collected
    assert codes(locked_project) == ["CONFIG_LOCKED", "CONFIG_SCOPE_NOT_ALLOWED"]


# ---------------------------------------------------------------------------------------------------------
# export → import


def test_export_then_import_is_a_no_op() -> None:
    made = harness()
    made.run(import_config("project", EXAMPLE, confirmed=True))
    for fmt in ("toml", "json"):
        exported = made.ask(export_config("project", fmt))
        assert exported == made.ask(export_config("project", fmt))  # deterministic
        before = made.snapshot()
        document = exported.to_json()["document"]
        if fmt == "json":  # the JSON document carries the float 15.0 through the bus request digest
            assert cast("dict[str, Any]", document)["budgets"]["run"]["max_usd"] == 15.0
        dto = import_config("project", document, format=fmt, expected_entries_digest=exported.digest)
        result = made.run(dto)
        assert {item.change for item in result.changes} == {"unchanged"}
        assert result.applied
        assert result.effective_diff == ()
        assert result.generation == made.generation
        assert made.snapshot() == before


RUN_USD = "budgets.run.max_usd"


def budget(amount: Any) -> dict[str, Any]:
    return {"schema": "urn:skm:settings:document:v1", "budgets": {"run": {"max_usd": amount}}}


def test_a_json_document_with_a_float_imports_through_the_bus() -> None:
    made = harness()
    before = made.snapshot()
    preview = made.run(import_config("project", budget(15.0), dry_run=True))
    assert made.snapshot() == before
    assert (preview.problems, [(item.key, item.after) for item in preview.effective_diff]) == (
        (),
        [(RUN_USD, 15.0)],
    )
    applied = made.run(import_config("project", budget(15.0)))
    assert (applied.applied, applied.generation, applied.changes) == (True, 1, preview.changes)
    assert allowed_audit(made, "settings.import_config").workspace_id == SCOPE_IDS["workspace"]
    assert type(made.entries("project")[RUN_USD].value) is float
    assert effective(made, "project", RUN_USD) == 15.0

    exported = made.ask(export_config("project", "json"))
    document = exported.to_json()["document"]
    assert cast("dict[str, Any]", document)["budgets"]["run"]["max_usd"] == 15.0
    before = made.snapshot()
    again = made.run(import_config("project", document, expected_entries_digest=exported.digest))
    assert ({item.change for item in again.changes}, again.effective_diff) == ({"unchanged"}, ())
    assert (again.generation, made.snapshot()) == (1, before)

    wider = refused(made, import_config("project", budget(25.5)), ErrorCode.CONFIG_INVALID)
    assert codes(wider) == ["CONFIG_NARROWING_VIOLATION"]
    stale = import_config("project", budget(12.5), expected_entries_digest=applied.entries_digest_before)
    refused(made, stale, ErrorCode.VERSION_CONFLICT)
    assert effective(made, "project", RUN_USD) == 15.0


def test_a_float_import_replays_by_its_idempotency_key() -> None:
    made = harness()
    dto = import_config("project", budget(12.5))
    first = made.run(dto, key="import-1")
    audits, before = made.audits, made.snapshot()
    replay = made.run(import_config("project", budget(12.5)), key="import-1")
    assert replay == first
    assert (made.snapshot(), made.audits) == (before, audits)
    [receipt] = made.receipts
    assert receipt.request_digest == request_digest(import_module.SPEC, dto)
    for amount in (12, 12.75, "12.5"):  # the integer, another float, the string
        with pytest.raises(SkmError) as caught:
            made.run(import_config("project", budget(amount)), key="import-1")
        assert caught.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
        assert made.snapshot() == before
    other = made.run(import_config("project", budget(10.5)), key="import-2")
    assert (other.generation, effective(made, "project", RUN_USD)) == (2, 10.5)
    assert len(made.receipts) == 2


def test_a_scope_without_a_local_entry_exports_the_absence_of_the_key() -> None:
    made = harness()
    made.run(set_value("project", ROUNDS, 1))  # value A, inherited by the plan
    assert effective(made, "plan", ROUNDS) == 1
    exported = made.ask(export_config("plan"))
    assert exported.entries == ()
    assert ROUNDS not in str(exported.document)
    result = made.run(import_config("plan", exported.document))
    assert result.changes == ()
    assert made.entries("plan") == {}
    made.run(set_value("project", ROUNDS, 2, expected_row_version=1))  # value B at project
    assert effective(made, "plan", ROUNDS) == 2  # the plan keeps following project


def test_unset_remove_empty_set_and_absent_merge_key_differ() -> None:
    made = harness()
    made.run(set_value("instance", TARGETS, ["codex"]))
    made.run(import_config("project", {"unset": [TARGETS]}))
    assert made.entries("project")[TARGETS].op.value == "unset"
    assert effective(made, "project", TARGETS) == ["claude_code"]  # unset: the default, instance hidden

    made.run(import_config("project", {"execution": {"review": {"max_rounds": 1}}}, mode="replace"))
    assert TARGETS not in made.entries("project")
    assert effective(made, "project", TARGETS) == ["codex"]  # removed: the farther level again

    made.run(import_config("project", {"integrations": {"targets": []}}))
    assert made.entries("project")[TARGETS].value == []
    assert effective(made, "project", TARGETS) == []  # an empty value is a value

    before = made.entries("project")[TARGETS]
    merged = made.run(import_config("project", {"execution": {"review": {"max_rounds": 2}}}))
    assert TARGETS not in {item.key for item in merged.changes}
    assert made.entries("project")[TARGETS] == before  # absent from a merge document: untouched
    assert effective(made, "project", TARGETS) == []


def test_parse_problems_and_document_size() -> None:
    made = harness()
    preview = made.run(import_config("project", "not = [toml", dry_run=True))
    assert [item.code for item in preview.problems] == ["CONFIG_INVALID"]
    assert preview.problems[0].key is None
    assert "document_syntax" in preview.problems[0].message
    preview = made.run(
        import_config(
            "project", {"schema": "urn:other", "execution": {"review": {"max_rounds": 1}}}, dry_run=True
        )
    )
    assert [item.code for item in preview.problems] == ["CONFIG_INVALID"]
    with pytest.raises(SkmError) as caught:
        made.run(import_config("project", {"execution": {"x": "y" * 1_100_000}}))
    assert caught.value.code in (ErrorCode.CONFIG_INVALID, ErrorCode.SCHEMA_INVALID)


# ---------------------------------------------------------------------------------------------------------
# rights of the planned changes, partial deep_merge contributions, document size

HOOKS, SUBSCRIPTION = h["HOOKS"], h["SUBSCRIPTION"]


def test_clearing_a_stored_lock_without_a_lock_list_needs_config_lock() -> None:
    made = harness()
    made.run(set_value("workspace", ROUNDS, 3, locked=True))
    document = {"execution": {"review": {"max_rounds": 3}}}
    made.authorizer.allowed = {"config.write", "config.write_shared"}
    preview = made.run(import_config("workspace", document, dry_run=True))
    assert [(item.key, item.change) for item in preview.changes] == [(ROUNDS, "lock_changed")]
    assert [item.code for item in preview.problems] == ["FORBIDDEN"]
    error = refused(made, import_config("workspace", document), ErrorCode.CONFIG_INVALID)
    assert codes(error) == ["FORBIDDEN"]
    made.authorizer.allow_all()
    applied = made.run(import_config("workspace", document))
    assert applied.changes == preview.changes
    assert made.entries("workspace")[ROUNDS].locked is False
    assert made.history[-1].change_kind is ChangeKind.UNLOCKED


def test_a_replace_import_removing_a_key_with_its_own_right_needs_that_right() -> None:
    made = harness()
    made.run(set_value("project", HOOKS, {}, confirmed=True))
    document = {"execution": {"review": {"max_rounds": 1}}}
    made.authorizer.allowed = {"config.write"}  # what the bus can see from this document
    error = refused(
        made, import_config("project", document, mode="replace", confirmed=True), ErrorCode.CONFIG_INVALID
    )
    assert codes(error) == ["FORBIDDEN"]
    assert {call.permission for call in made.authorizer.calls} >= {"hook.manage"}
    made.authorizer.allowed = {"config.write", "hook.manage"}
    result = made.run(import_config("project", document, mode="replace", confirmed=True))
    assert {(item.key, item.change) for item in result.changes} == {(ROUNDS, "added"), (HOOKS, "removed")}
    assert set(made.entries("project")) == {ROUNDS}


def request_audits(made: Any) -> list[Any]:
    return [item for item in made.audits if item.request_id == made.request_id]


def test_a_denied_replace_import_keeps_config_invalid_and_is_audited_as_denied() -> None:
    made = harness()
    made.run(set_value("project", HOOKS, {"audit": SUBSCRIPTION}, confirmed=True))
    made.run(set_value("project", "execution.workflow.profile", "quick-fix"))
    document = {"execution": {"review": {"max_rounds": 1}}}
    made.authorizer.allowed = {"config.write"}
    before = made.history, made.entries("project"), made.receipts
    error = refused(
        made, import_config("project", document, mode="replace", confirmed=True), ErrorCode.CONFIG_INVALID
    )
    assert codes(error) == ["FORBIDDEN"]  # the import contract: every problem, CONFIG_INVALID
    [problem] = cast("list[dict[str, Any]]", error.details["problems"])
    assert (problem["rule"], problem["key"]) == ("R16", HOOKS)
    [denied] = request_audits(made)
    assert (denied.action, denied.decision, denied.reason_code) == (
        "settings.import_config",
        "denied",
        "ROLE_LACKS_PERMISSION",
    )
    assert denied.workspace_id == SCOPE_IDS["workspace"]
    assert denied.target == {"scope": {"kind": "project", "id": str(PROJECT)}, "permission": "hook.manage"}
    # the removal of the other entry and the added key were rolled back with the rest
    assert (made.history, made.entries("project"), made.receipts) == before
    assert "HOOK_SECRET" not in repr((made.audits, error.to_problem()))
    assert made.backend.active == 0


def test_an_import_that_clears_a_lock_without_config_lock_is_audited_once() -> None:
    made = harness()
    made.run(set_value("workspace", ROUNDS, 3, locked=True))
    made.authorizer.allowed = {"config.write", "config.write_shared"}
    document = {"execution": {"review": {"max_rounds": 3}}}
    error = refused(made, import_config("workspace", document, mode="replace"), ErrorCode.CONFIG_INVALID)
    assert codes(error) == ["FORBIDDEN"]
    [denied] = request_audits(made)
    assert (denied.decision, denied.target["permission"]) == ("denied", "config.lock")
    assert made.entries("workspace")[ROUNDS].locked is True


def test_an_import_with_only_validation_problems_writes_no_denied_audit() -> None:
    made = harness()
    document = {"execution": {"review": {"max_rounds": 9}}, "nope": {"key": 1}}
    error = refused(made, import_config("project", document), ErrorCode.CONFIG_INVALID)
    assert "FORBIDDEN" not in codes(error)
    assert error.__cause__ is None
    assert made.audits == []


def test_a_document_with_a_non_finite_number_is_schema_invalid() -> None:
    made = harness()
    for value in (float("nan"), float("inf")):
        error = refused(made, import_config("project", budget(value)), ErrorCode.SCHEMA_INVALID)
        assert error.details["reason"] == "not_json"
    assert (made.audits, made.authorizer.calls) == ([], [])


def test_a_partial_hook_contribution_imports_over_the_inherited_subscription() -> None:
    made = harness()
    made.run(set_value("workspace", HOOKS, {"audit": SUBSCRIPTION}, confirmed=True))
    partial = {
        "hooks": {"subscriptions": {"audit": {"kind": "webhook", "target": {"headers": {"X": "new"}}}}}
    }
    before = made.snapshot()
    preview = made.run(import_config("project", partial, dry_run=True, confirmed=True))
    assert made.snapshot() == before
    assert preview.problems == ()
    [diff] = preview.effective_diff
    assert diff.after["audit"]["target"] == {**SUBSCRIPTION["target"], "headers": {"X": "new"}}
    applied = made.run(import_config("project", partial, confirmed=True))
    assert (applied.changes, applied.effective_diff) == (preview.changes, preview.effective_diff)
    assert applied.entries_digest_after == preview.entries_digest_after
    bad = {"hooks": {"subscriptions": {"audit": {"target": {"headers": {"X": 1}}}}}}
    assert made.run(import_config("project", bad, dry_run=True, confirmed=True)).problems
    refused(made, import_config("project", bad, confirmed=True), ErrorCode.CONFIG_INVALID)


LIMIT = import_module.DOCUMENT_MAX_BYTES


@pytest.mark.parametrize(
    "document",
    [
        "#" + "x" * (LIMIT - 1),  # ASCII, exactly 1 MiB
        "#" + "ж" * ((LIMIT - 2) // 2) + "x",  # two-byte characters, exactly 1 MiB
    ],
)
def test_a_document_of_exactly_one_mib_is_accepted(document: str) -> None:
    assert len(document.encode("utf-8")) == LIMIT
    made = harness()
    for dry_run in (True, False):
        result = made.run(import_config("project", document, dry_run=dry_run))
        assert (result.problems, result.changes) == ((), ())


def test_a_multibyte_document_over_one_mib_is_refused_in_both_modes() -> None:
    document = "#" + "ж" * 600_000  # 600001 characters, 1200001 bytes
    made = harness()
    for dry_run in (True, False):
        error = refused(made, import_config("project", document, dry_run=dry_run), ErrorCode.CONFIG_INVALID)
        assert error.details == {"reason": "document_too_large"}
    assert import_module.permissions_of(import_config("project", document)) == ("config.write",)
