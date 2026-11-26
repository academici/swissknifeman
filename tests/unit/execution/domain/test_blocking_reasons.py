"""BlockingReason catalog and values (execution §4.19, conventions §6.1, CHECK 0013)."""

from __future__ import annotations

import dataclasses
import json
import re
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import TaskId
from skm.kernel.json_types import JsonValue
from skm.modules.execution.domain.blocking_reason import (
    BLOCKING_CATALOG,
    LEGACY_BLOCKING_CODES,
    AllowedAction,
    BlockingCode,
    DeadlineSource,
    NextCheckSource,
    ResolverRole,
    blocking_reason,
    blocking_reason_from_json,
    blocking_reason_to_json,
    migrate_legacy_code,
)
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
SPEC = ROOT / "tests/fixtures/corpus/blocking-reasons.md"
CONVENTIONS = ROOT / "tests/fixtures/corpus/blocking-reason-codes.md"
DDL = ROOT / "src/skm/adapters/postgres/migrations/sql/0001_core_baseline.sql"
CATALOG = ROOT / "tests/fixtures/corpus/examples/execution/blocking-reasons.json"
URN = "urn:skm:execution:blocking-reason:v1"
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
TASK = TaskId(UUID("0193a000-0000-7000-8000-000000000012"))
OTHER_TASK = TaskId(UUID("0193a000-0000-7000-8000-000000000013"))
ID = "0193a000-0000-7000-8000-0000000c0002"

REFS: dict[BlockingCode, dict[str, JsonValue]] = {
    BlockingCode.WAITING_OWNER: {"decision_request_id": ID, "stop_code": "REWORK_LIMIT_REACHED"},
    BlockingCode.WAITING_ANSWER: {"decision_request_id": ID, "question_key": "q-1"},
    BlockingCode.WAITING_ADVISOR: {"decision_request_id": ID, "stage_record_id": ID},
    BlockingCode.WAITING_MANUAL_CHECK: {"check_execution_id": ID, "check_key": "P2.3:V1"},
    BlockingCode.WAITING_APPROVAL: {"intent_id": ID, "decision_request_id": ID},
    BlockingCode.WAITING_PROVIDER: {
        "stage_record_id": ID,
        "error_class": "rate_limit",
        "route": "claude_code/x",
    },
    BlockingCode.WAITING_BUDGET_RESET: {"stop_code": "QUOTA_EXHAUSTED", "reset_at": "2026-10-25T13:00:00Z"},
    BlockingCode.BLOCKED_BY_DEPENDENCY: {"prerequisite_task_ids": [ID]},
    BlockingCode.BLOCKED_BY_MATERIAL: {
        "material_ids": [ID],
        "file_version_ids": [],
        "required_for": "execution",
    },
    BlockingCode.BLOCKED_BY_BUDGET: {
        "decision_request_id": ID,
        "dimension": "usd",
        "scope": "run",
        "limit": 10,
        "spent": 11,
    },
    BlockingCode.BLOCKED_BY_CAPABILITY: {
        "capabilities": ["runtime:claude_code"],
        "required_labels": ["linux"],
        "environment_kind": "git_worktree",
        "isolation_profiles": ["worktree"],
    },
    BlockingCode.BLOCKED_BY_POLICY: {"reason": "kill_switch"},
    BlockingCode.BLOCKED_BY_INTEGRATION: {"integration_task_id": ID},
    BlockingCode.SUSPECTED_STALL: {
        "stage_record_id": ID,
        "silent_seconds": 600,
        "health_reason": "no_progress",
    },
    BlockingCode.RECOVERING: {"stage_record_id": ID, "recovery_record_id": ID, "recovery_step": "snapshot"},
}


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def times(code: BlockingCode) -> dict[str, datetime | None]:
    spec = BLOCKING_CATALOG[code]
    later = NOW + timedelta(minutes=5)
    return {
        "next_check_at": None if spec.next_check is NextCheckSource.NONE else later,
        "deadline_at": later
        if spec.deadline in {DeadlineSource.PROVIDER_WAIT_MAX, DeadlineSource.QUOTA_WAIT_MAX}
        else None,
    }


def build(code: BlockingCode, **changes: Any) -> Any:
    arguments: dict[str, Any] = {"task_id": TASK, "refs": REFS[code], "now": NOW, "message": f"{code} waits"}
    arguments.update(times(code))
    arguments.update(changes)
    return blocking_reason(code, **arguments)


# --- one closed code set everywhere ------------------------------------------------------------------


def spec_rows() -> dict[str, list[str]]:
    section = SPEC.read_text(encoding="utf-8")
    rows: dict[str, list[str]] = {}
    for line in section.splitlines():
        match = re.match(r"\| `([A-Z_]+)` \|(.*)\|$", line.replace("\\|", "/"))
        if match:
            rows[match.group(1)] = [cell.strip() for cell in match.group(2).split("|")]
    return rows


def ref_names(cell: str) -> set[str]:
    """Ref names of a table cell; value lists in parentheses (``(rate_limit/quota)``) are not refs,
    an added ref in parentheses (``(+ agent-only `reap_step_id`)``) is."""
    without_values = re.sub(r"\((?![^)]*\+)[^)]*\)", "", cell)
    return set(re.findall(r"`([a-z_]+)(?:\[\])?\??(?: = [A-Z_]+)?`", without_values))


def test_every_code_is_the_same_in_spec_conventions_ddl_schema_and_example_catalog() -> None:
    domain = {code.value for code in BlockingCode}
    assert set(BLOCKING_CATALOG) == set(BlockingCode)
    assert set(spec_rows()) == domain

    section = CONVENTIONS.read_text(encoding="utf-8")
    assert set(re.findall(r"`([A-Z][A-Z_]+)`", section)) - {"BlockingCode"} == domain

    ddl = DDL.read_text(encoding="utf-8")
    check = re.search(r"ck_run_tasks__blocking_code CHECK \(.*?ARRAY\[(.*?)\]", ddl, re.DOTALL)
    assert check is not None
    assert set(re.findall(r"'([A-Z_]+)'", check.group(1))) == domain

    schema = registry().get(URN)
    assert set(schema["properties"]["code"]["enum"]) == domain  # type: ignore[index,arg-type]

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert {entry["code"] for entry in catalog["codes"]} == domain
    assert registry().validate("urn:skm:execution:blocking-reason-catalog:v1", catalog) == ()


@pytest.mark.parametrize("code", list(BlockingCode), ids=str)
def test_catalog_row_matches_the_spec_table(code: BlockingCode) -> None:
    status, refs, resolver, actions, _times = spec_rows()[code.value]
    spec = BLOCKING_CATALOG[code]
    names = ref_names(refs)
    assert set(spec.required_refs) <= names <= set(spec.refs)
    assert names == set(spec.refs)
    roles = [token for token in re.findall(r"`([A-Za-z_]+)`", resolver) if token in {*ResolverRole, "None"}]
    expected_role = None if roles[0] == "None" else ResolverRole(roles[0])
    assert spec.resolver_role == expected_role
    listed = {AllowedAction(token) for token in re.findall(r"`([a-z_]+)`", actions)}
    variants = set(spec.allowed_actions)
    if code is BlockingCode.BLOCKED_BY_DEPENDENCY:
        variants |= {AllowedAction.RESTART_TASK, AllowedAction.SKIP_TASK}
    assert variants == listed
    if "рабочий статус" not in status:
        # "(run `paused`)" names the run status, not a task status
        assert spec.task_statuses == set(re.findall(r"`([a-z_]+)`", re.sub(r"\([^)]*\)", "", status)))


@pytest.mark.parametrize("code", list(BlockingCode), ids=str)
def test_example_catalog_lists_the_same_actions_and_role(code: BlockingCode) -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    entry = next(found for found in catalog["codes"] if found["code"] == code.value)
    spec = BLOCKING_CATALOG[code]
    actions = set(spec.allowed_actions)
    if code is BlockingCode.BLOCKED_BY_DEPENDENCY:
        actions |= {AllowedAction.RESTART_TASK, AllowedAction.SKIP_TASK}
    assert {AllowedAction(found) for found in entry["allowed_actions"]} == actions
    assert set(spec.required_refs) <= set(entry["refs"]) <= set(spec.refs)
    if entry["resolver_role"] in set(ResolverRole):
        assert spec.resolver_role == ResolverRole(entry["resolver_role"])
    if entry["next_check_at"] is None:
        assert spec.next_check is NextCheckSource.NONE
    else:
        assert spec.next_check is not NextCheckSource.NONE


# --- per code values -----------------------------------------------------------------------------------


@pytest.mark.parametrize("code", list(BlockingCode), ids=str)
def test_each_code_builds_its_table_value_and_matches_the_schema(code: BlockingCode) -> None:
    reason = build(code)
    spec = BLOCKING_CATALOG[code]
    assert reason.resolver_role == spec.resolver_role
    assert reason.allowed_actions == spec.allowed_actions
    assert reason.since == NOW
    document = blocking_reason_to_json(reason)
    assert registry().validate(URN, document) == ()
    assert blocking_reason_from_json(document) == reason


@pytest.mark.parametrize("code", list(BlockingCode), ids=str)
def test_next_check_and_deadline_follow_the_table(code: BlockingCode) -> None:
    spec = BLOCKING_CATALOG[code]
    later = NOW + timedelta(hours=1)
    if spec.next_check is NextCheckSource.NONE:
        with pytest.raises(SkmError, match="never rechecked"):
            build(code, next_check_at=later)
    else:
        with pytest.raises(SkmError, match="needs next_check_at"):
            build(code, next_check_at=None)
    if spec.deadline is DeadlineSource.NONE:
        with pytest.raises(SkmError, match="no deadline"):
            build(code, deadline_at=later)
    elif spec.deadline in {DeadlineSource.PROVIDER_WAIT_MAX, DeadlineSource.QUOTA_WAIT_MAX}:
        with pytest.raises(SkmError, match="needs deadline_at"):
            build(code, deadline_at=None)
    else:  # a decision request or an intent may have no deadline
        assert build(code, deadline_at=None).deadline_at is None
        assert build(code, deadline_at=later).deadline_at == later


@pytest.mark.parametrize("code", list(BlockingCode), ids=str)
def test_missing_or_foreign_refs_are_refused(code: BlockingCode) -> None:
    spec = BLOCKING_CATALOG[code]
    required = spec.required_refs[0]
    refs = {name: value for name, value in REFS[code].items() if name != required}
    with pytest.raises(SkmError, match="needs refs"):
        build(code, refs=refs)
    with pytest.raises(SkmError, match="does not carry refs"):
        build(code, refs={**REFS[code], "unrelated": 1})


def test_since_survives_a_rewrite_of_the_same_code() -> None:
    first = build(BlockingCode.WAITING_PROVIDER)
    later = NOW + timedelta(minutes=3)
    rewritten = build(
        BlockingCode.WAITING_PROVIDER,
        now=later,
        previous=first,
        next_check_at=later + timedelta(minutes=1),
        deadline_at=later + timedelta(hours=6),
    )
    assert rewritten.since == NOW
    assert rewritten.next_check_at == later + timedelta(minutes=1)
    other_code = build(BlockingCode.SUSPECTED_STALL, now=later, previous=first)
    assert other_code.since == later
    other_task = build(BlockingCode.WAITING_PROVIDER, task_id=OTHER_TASK, now=later, previous=first)
    assert other_task.since == later


def test_failed_prerequisites_make_the_owner_resolve_with_restart_or_skip() -> None:
    waiting = build(BlockingCode.BLOCKED_BY_DEPENDENCY)
    assert waiting.resolver_role is None
    assert waiting.allowed_actions == (AllowedAction.WAIT,)
    failed = build(
        BlockingCode.BLOCKED_BY_DEPENDENCY, refs={"prerequisite_task_ids": [ID], "failed_task_ids": [ID]}
    )
    assert failed.resolver_role is ResolverRole.OWNER
    assert failed.allowed_actions == (AllowedAction.RESTART_TASK, AllowedAction.SKIP_TASK)


def test_resolver_role_override_is_limited_to_check_and_question_audiences() -> None:
    manual = build(BlockingCode.WAITING_MANUAL_CHECK)
    assert manual.resolver_role is ResolverRole.MEMBER
    assert (
        build(BlockingCode.WAITING_MANUAL_CHECK, resolver_role=ResolverRole.OWNER).resolver_role
        is ResolverRole.OWNER
    )
    assert (
        build(BlockingCode.WAITING_ANSWER, resolver_role=ResolverRole.MAINTAINER).resolver_role
        is ResolverRole.MAINTAINER
    )
    with pytest.raises(SkmError, match="human role"):
        build(BlockingCode.WAITING_MANUAL_CHECK, resolver_role=ResolverRole.SYSTEM)
    with pytest.raises(SkmError, match="always resolved"):
        build(BlockingCode.WAITING_OWNER, resolver_role=ResolverRole.MEMBER)


def _schema_valid_variant(reason: Any, **changes: Any) -> dict[str, Any]:
    document = {**blocking_reason_to_json(reason), **changes}
    assert registry().validate(URN, document) == ()
    return document


@pytest.mark.parametrize("code", list(BlockingCode), ids=str)
def test_stored_resolver_and_actions_follow_the_catalog(code: BlockingCode) -> None:
    reason = build(code)
    spec = BLOCKING_CATALOG[code]
    wrong_role = ResolverRole.SYSTEM if spec.resolver_role is not ResolverRole.SYSTEM else ResolverRole.OWNER
    document = _schema_valid_variant(reason, resolver_role=wrong_role.value)
    with pytest.raises(SkmError, match="resolved by") as caught:
        blocking_reason_from_json(document)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    actions = [action.value for action in spec.allowed_actions]
    substitute = next(action.value for action in AllowedAction if action.value not in actions)
    for wrong in (actions[:-1], [*actions[:-1], substitute], [*actions, substitute]):
        with pytest.raises(SkmError, match="offers exactly") as caught:
            blocking_reason_from_json(_schema_valid_variant(reason, allowed_actions=wrong))
        assert caught.value.code is ErrorCode.SCHEMA_INVALID
    reordered = _schema_valid_variant(reason, allowed_actions=actions[::-1])
    assert set(blocking_reason_from_json(reordered).allowed_actions) == set(spec.allowed_actions)


def test_a_system_wait_is_not_an_owner_escalation() -> None:
    document = _schema_valid_variant(
        build(BlockingCode.WAITING_OWNER), resolver_role="system", allowed_actions=["wait"]
    )
    with pytest.raises(SkmError) as caught:
        blocking_reason_from_json(document)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(SkmError, match="resolved by"):
        dataclasses.replace(build(BlockingCode.WAITING_OWNER), resolver_role=ResolverRole.SYSTEM)


def test_legitimate_resolver_variants_round_trip() -> None:
    failed_refs: dict[str, JsonValue] = {"prerequisite_task_ids": [ID], "failed_task_ids": [ID]}
    variants = [
        build(BlockingCode.BLOCKED_BY_DEPENDENCY, refs=failed_refs),
        *(
            build(code, resolver_role=role)
            for code in (BlockingCode.WAITING_MANUAL_CHECK, BlockingCode.WAITING_ANSWER)
            for role in (ResolverRole.OWNER, ResolverRole.MAINTAINER, ResolverRole.MEMBER)
        ),
    ]
    for reason in variants:
        assert blocking_reason_from_json(_schema_valid_variant(reason)) == reason
    failed = blocking_reason_to_json(variants[0])
    # the failed-prerequisite form keeps the owner and its actions; the plain wait form is refused for it
    with pytest.raises(SkmError, match="resolved by"):
        blocking_reason_from_json({**failed, "resolver_role": None, "allowed_actions": ["wait"]})
    plain = blocking_reason_to_json(build(BlockingCode.BLOCKED_BY_DEPENDENCY))
    with pytest.raises(SkmError, match="resolved by"):
        blocking_reason_from_json(
            {**plain, "resolver_role": "owner", "allowed_actions": ["restart_task", "skip_task"]}
        )
    for code in (BlockingCode.WAITING_MANUAL_CHECK, BlockingCode.WAITING_ANSWER):
        for role in ("system", "advisor", None):
            with pytest.raises(SkmError, match="human role"):
                blocking_reason_from_json({**blocking_reason_to_json(build(code)), "resolver_role": role})


def test_code_specific_ref_values_are_checked() -> None:
    with pytest.raises(SkmError, match="error_class"):
        build(
            BlockingCode.WAITING_PROVIDER,
            refs={**REFS[BlockingCode.WAITING_PROVIDER], "error_class": "crash"},
        )
    with pytest.raises(SkmError, match="QUOTA_EXHAUSTED"):
        build(BlockingCode.WAITING_BUDGET_RESET, refs={"stop_code": "BUDGET_EXHAUSTED", "reset_at": "x"})
    with pytest.raises(SkmError, match="policy reason"):
        build(BlockingCode.BLOCKED_BY_POLICY, refs={"reason": "dislike"})
    unmetered = build(
        BlockingCode.BLOCKED_BY_BUDGET, refs={**REFS[BlockingCode.BLOCKED_BY_BUDGET], "reason": "unmetered"}
    )
    assert unmetered.refs["reason"] == "unmetered"
    reap = {"stage_record_id": ID, "reap_stage_record_id": ID, "reap_step_id": ID, "recovery_step": "reap"}
    assert build(BlockingCode.RECOVERING, refs=reap).refs["reap_step_id"] == ID
    with pytest.raises(SkmError, match="exactly one"):
        build(BlockingCode.RECOVERING, refs={**reap, "recovery_record_id": ID})
    with pytest.raises(SkmError, match="reap barrier"):
        build(
            BlockingCode.RECOVERING,
            refs={"stage_record_id": ID, "recovery_record_id": ID, "reap_step_id": ID, "recovery_step": "x"},
        )


def test_message_is_cut_to_three_hundred_characters() -> None:
    reason = build(BlockingCode.WAITING_OWNER, message="x" * 400)
    assert len(reason.message) == 300
    assert reason.message.endswith("…")


def test_refs_cannot_be_changed_after_construction() -> None:
    refs = dict(REFS[BlockingCode.WAITING_OWNER])
    reason = build(BlockingCode.WAITING_OWNER, refs=refs)
    refs["stop_code"] = "CHANGED"
    assert reason.refs["stop_code"] == "REWORK_LIMIT_REACHED"
    with pytest.raises(TypeError):
        reason.refs["stop_code"] = "CHANGED"


@pytest.mark.parametrize(
    ("legacy", "current"),
    [
        ("WAITING_DEPENDENCIES", BlockingCode.BLOCKED_BY_DEPENDENCY),
        ("PREREQUISITE_FAILED", BlockingCode.BLOCKED_BY_DEPENDENCY),
        ("WAITING_GROUP_REVIEW", BlockingCode.BLOCKED_BY_DEPENDENCY),
        ("WAITING_ESCALATION", BlockingCode.WAITING_OWNER),
        ("REWORK_LIMIT_REACHED", BlockingCode.WAITING_OWNER),
        ("WAITING_INTEGRATION_TASK", BlockingCode.BLOCKED_BY_INTEGRATION),
        ("WAITING_HOST", BlockingCode.BLOCKED_BY_CAPABILITY),
        ("WAITING_CAPABILITY", BlockingCode.BLOCKED_BY_CAPABILITY),
        ("BUDGET_EXHAUSTED", BlockingCode.BLOCKED_BY_BUDGET),
        ("RUN_PAUSED", None),
        ("WAITING_ANSWER", BlockingCode.WAITING_ANSWER),
    ],
)
def test_legacy_codes_migrate_to_the_closed_set(legacy: str, current: BlockingCode | None) -> None:
    assert migrate_legacy_code(legacy) is current


def test_unknown_codes_are_not_guessed() -> None:
    assert set(LEGACY_BLOCKING_CODES) & {code.value for code in BlockingCode} == set()
    with pytest.raises(SkmError, match="unknown blocking code"):
        migrate_legacy_code("WAITING_SOMETHING")


def test_schema_refuses_values_outside_the_contract() -> None:
    document = blocking_reason_to_json(build(BlockingCode.WAITING_OWNER))
    assert registry().validate(URN, {**document, "code": "WAITING_FOR_GODOT"}) != ()
    assert registry().validate(URN, {**document, "resolver_role": "worker"}) != ()
    assert registry().validate(URN, {**document, "allowed_actions": ["wait", "wait"]}) != ()
    assert registry().validate(URN, {**document, "message": "x" * 301}) != ()
    assert registry().validate(URN, {key: value for key, value in document.items() if key != "task_id"}) != ()
    member = blocking_reason_to_json(build(BlockingCode.WAITING_MANUAL_CHECK))
    assert member["resolver_role"] == "member"
    assert registry().validate(URN, member) == ()
    no_resolver = blocking_reason_to_json(build(BlockingCode.BLOCKED_BY_INTEGRATION))
    assert no_resolver["resolver_role"] is None
    assert registry().validate(URN, no_resolver) == ()
