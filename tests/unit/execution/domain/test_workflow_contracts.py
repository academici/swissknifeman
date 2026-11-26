"""Closed workflow and role result contracts (execution §5.2-§5.3, §5.7-§5.8)."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tomllib
from dataclasses import fields
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from skm.kernel.json_types import JsonValue
from skm.modules.execution.domain.review import Verdict
from skm.modules.execution.domain.role_contracts import (
    ROLE_CONTRACTS,
    FilesystemAccess,
    ResultKind,
    ShellAccess,
    WriteAuthority,
    result_schema_urn,
    role_for_result_schema,
)
from skm.modules.execution.domain.run import RunKind
from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageRecord
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.task import ReviewMode, TaskKind
from skm.modules.execution.domain.workflow.actions import Done, Noop
from skm.modules.execution.domain.workflow.definition import (
    _HANDLERS,
    AGENT_STAGE_ROLES,
    WORKFLOW_SCHEMA,
    OnOutcome,
    StageParams,
    StageType,
    WorkflowDefinition,
    applicable_kinds,
    applies_to_kind,
    parse_workflow,
)
from skm.modules.execution.domain.workflow.history import StageEntry, StageHistory
from skm.modules.execution.domain.workflow.predicates import (
    PREDICATE_TYPES,
    AnyPredicates,
    PredicateKind,
    ReviewModeIs,
    ReviewVerdictIs,
    RiskAtLeast,
    RunKindIn,
    TaskKindIn,
    WorkKind,
    parse_condition,
)
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES = ROOT / "tests/fixtures/corpus/examples"
WORKFLOWS = sorted((EXAMPLES / "execution/workflows").glob("*.toml"))
ROLE_RESULTS = EXAMPLES / "execution/examples/role-results"
PROFILES = sorted((EXAMPLES / "agent-profiles").glob("*.toml"))
UUID = "01900000-0000-7000-8000-000000000001"


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def schema_ok(urn: str, document: object) -> bool:
    return registry().validate(urn, document) == ()


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def example(name: str) -> dict[str, Any]:
    return load_toml(EXAMPLES / f"execution/workflows/{name}.toml")


def parsed(document: object) -> WorkflowDefinition:
    definition, violations = parse_workflow(cast(JsonValue, document))
    assert violations == (), violations
    assert definition is not None
    return definition


def reasons(document: object) -> set[str]:
    definition, violations = parse_workflow(cast(JsonValue, document))
    assert definition is None
    assert violations
    return {item.reason for item in violations}


def stage(document: dict[str, Any], stage_id: str) -> dict[str, Any]:
    return next(item for item in document["stage"] if item["id"] == stage_id)


def minimal(*stages: dict[str, Any], roles: list[str] | None = None) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": WORKFLOW_SCHEMA,
        "id": "probe",
        "version": "1.0.0",
        "applies_to": ["code"],
        "stage": [{"id": "prepare", "type": "prepare_environment"}, *stages],
    }
    if roles is not None:
        document["requires_roles"] = roles
    return document


EXECUTE = {"id": "execute", "type": "agent_step", "role": "executor"}


def test_reviewer_with_fix_is_an_opt_in_review_stage_parameter() -> None:
    doc = minimal(
        EXECUTE,
        {"id": "checks", "type": "run_checks"},
        {
            "id": "review",
            "type": "agent_review",
            "params": {"reviewer_with_fix": True, "profile": "reviewer-with-fix"},
        },
        roles=["executor", "reviewer"],
    )
    assert registry().validate(WORKFLOW_SCHEMA, doc) == ()
    workflow, issues = parse_workflow(doc)
    assert not issues
    assert workflow is not None
    assert workflow.stages[-1].params.reviewer_with_fix is True
    assert workflow.stages[-1].params.as_json()["reviewer_with_fix"] is True
    doc["stage"][1] = {**EXECUTE, "params": {"reviewer_with_fix": True}}
    _, issues = parse_workflow(doc)
    assert issues


# --- the five workflow examples -------------------------------------------------------------------


def test_all_five_workflow_examples_exist() -> None:
    assert [path.stem for path in WORKFLOWS] == [
        "plan-audit",
        "quick-fix",
        "research-only",
        "review-only",
        "reviewed-development",
    ]


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.stem)
def test_workflow_example_is_schema_valid_and_parses_without_defects(path: Path) -> None:
    document = load_toml(path)
    assert registry().validate(WORKFLOW_SCHEMA, document) == ()
    definition = parsed(document)
    assert definition.id == path.stem
    assert [item.id for item in definition.stages] == [item["id"] for item in document["stage"]]
    assert {item.role for item in definition.stages} - {None} <= set(definition.requires_roles)


APPLICABLE = {
    "reviewed-development": {
        TaskKind.UNIT: [
            *("prepare", "scout", "execute", "checks", "review"),
            *("triage", "advise", "accept", "integrate", "recheck"),
        ],
        TaskKind.ITEM_GATE: ["gate_prepare", "gate_checks", "review", "triage", "advise", "phase_gate"],
        TaskKind.PHASE_GATE: ["gate_prepare", "gate_checks", "review", "triage", "advise", "phase_gate"],
        TaskKind.GROUP_REVIEW: ["gate_prepare", "review", "triage", "advise", "phase_gate"],
        TaskKind.PLAN_ACCEPTANCE: ["gate_prepare", "gate_checks", "plan_acceptance"],
        TaskKind.PLAN_AUDIT: [],
    },
    "quick-fix": {
        TaskKind.ITEM: ["prepare", "execute", "checks", "review", "triage", "accept", "integrate"],
        TaskKind.PHASE_GATE: [],
        TaskKind.PLAN_ACCEPTANCE: [],
    },
    "research-only": {TaskKind.FOLLOWUP: ["prepare", "research", "review", "triage", "accept"]},
    "review-only": {TaskKind.ITEM: ["prepare", "review", "triage", "accept"], TaskKind.UNIT: []},
    "plan-audit": {TaskKind.PLAN_AUDIT: ["prepare", "audit"], TaskKind.UNIT: []},
}


@pytest.mark.parametrize(
    ("name", "kind"), [(name, kind) for name, table in APPLICABLE.items() for kind in table]
)
def test_for_kinds_and_gate_stage_applicability(name: str, kind: TaskKind) -> None:
    definition = parsed(example(name))
    applied = [item.id for item in definition.stages if applies_to_kind(item, kind)]
    assert applied == APPLICABLE[name][kind]


def test_gate_stage_types_ignore_for_kinds_and_acceptance_gate_skips_gate_tasks() -> None:
    document = minimal(
        {"id": "phase", "type": "phase_gate", "for_kinds": ["unit"]},
        {"id": "plan", "type": "plan_acceptance"},
        {"id": "accept", "type": "acceptance_gate", "for_kinds": ["unit", "item_gate"]},
    )
    document["stage"][0]["for_kinds"] = list(TaskKind)
    by_id = {item.id: item for item in parsed(document).stages}
    assert applicable_kinds(by_id["phase"]) == {
        TaskKind.ITEM_GATE,
        TaskKind.PHASE_GATE,
        TaskKind.GROUP_REVIEW,
    }
    assert applicable_kinds(by_id["plan"]) == {TaskKind.PLAN_ACCEPTANCE}
    assert applicable_kinds(by_id["accept"]) == {TaskKind.UNIT}


def test_stage_declarations_are_typed_and_implied_roles_are_filled() -> None:
    by_id = {item.id: item for item in parsed(example("reviewed-development")).stages}
    assert by_id["review"].role is RoleId.REVIEWER
    assert by_id["advise"].role is RoleId.ADVISOR
    assert by_id["checks"].role is None
    assert by_id["scout"].optional is True
    assert by_id["execute"].optional is False
    assert by_id["prepare"].for_kinds == {
        TaskKind.ADHOC,
        TaskKind.UNIT,
        TaskKind.ITEM,
        TaskKind.INTEGRATION,
        TaskKind.FOLLOWUP,
    }
    assert by_id["review"].skip_when == ReviewModeIs(ReviewMode.WAIVED)
    assert by_id["triage"].when == AnyPredicates(
        (ReviewVerdictIs(Verdict.RED), ReviewVerdictIs(Verdict.ATTENTION))
    )
    assert by_id["checks"].on == OnOutcome(checks_failed="rework", checks_error="retry_once_then_escalate")
    assert by_id["review"].params.as_json() == {"audit_scope": "corrected", "profile": "reviewer"}
    assert by_id["phase_gate"].params == StageParams(blocks_next_phase=True)
    quick = {item.id: item for item in parsed(example("quick-fix")).stages}
    assert quick["review"].when == AnyPredicates((ReviewModeIs(ReviewMode.REQUIRED), RiskAtLeast(60)))
    review_only = {item.id: item for item in parsed(example("review-only")).stages}
    assert review_only["prepare"].when == RunKindIn(frozenset({RunKind.REVIEW_REQUEST}))


def test_task_kind_and_risk_at_least_predicates_are_closed_and_typed() -> None:
    assert parse_condition({"task_kind": ["unit", "phase_gate"]}) == TaskKindIn(
        frozenset({TaskKind.UNIT, TaskKind.PHASE_GATE})
    )
    assert parse_condition({"risk_at_least": 0}) == RiskAtLeast(0)
    assert parse_condition({"risk_at_least": 100}) == RiskAtLeast(100)
    for bad in ({"risk_at_least": 101}, {"risk_at_least": True}, {"task_kind": ["gate"]}, {"task_kind": []}):
        document = minimal({**EXECUTE, "when": bad})
        assert not schema_ok(WORKFLOW_SCHEMA, document), bad
        assert reasons(document) <= {"invalid_value", "invalid_shape"}, bad


# --- the closed sets agree with the schema --------------------------------------------------------


def test_closed_sets_match_the_workflow_schema() -> None:
    defs = cast(dict[str, Any], registry().get(WORKFLOW_SCHEMA)["$defs"])
    assert set(defs["stage_type"]["enum"]) == set(StageType)
    assert set(defs["role"]["enum"]) == set(RoleId)
    assert set(defs["task_kind"]["enum"]) == set(TaskKind)
    assert set(defs["work_kind"]["enum"]) == set(WorkKind)
    assert set(defs["predicate"]["properties"]["run_kind"]["items"]["enum"]) == set(RunKind)
    assert set(defs["predicate"]["properties"]) == set(PredicateKind) == set(PREDICATE_TYPES)
    assert set(defs["params"]["properties"]) == {item.name for item in fields(StageParams)}
    handlers = defs["on"]["properties"]
    assert set(handlers) == {item.name for item in fields(OnOutcome)} == set(_HANDLERS)
    for name, (allowed, _) in _HANDLERS.items():
        assert set(handlers[name]["enum"]) == allowed
    agent_step = next(
        rule
        for rule in defs["stage"]["allOf"]
        if rule["if"]["properties"]["type"].get("const") == "agent_step"
    )
    assert set(agent_step["then"]["properties"]["role"]["enum"]) == AGENT_STAGE_ROLES[StageType.AGENT_STEP]


# --- unknown stage / predicate / role and impossible transitions are refused before a run ----------


SCHEMA_AND_DOMAIN_REJECT = {
    "unknown stage type": (minimal({"id": "fix", "type": "report_fix"}), "unknown_stage_type"),
    "report_fixer role": (
        minimal({"id": "fix", "type": "agent_step", "role": "report_fixer"}),
        "unknown_role",
    ),
    "unknown requires role": (minimal(EXECUTE, roles=["executor", "report_fixer"]), "unknown_role"),
    "unknown predicate": (minimal({**EXECUTE, "when": {"eval": "task.risk > 3"}}), "unknown_predicate"),
    "unknown predicate in any": (
        minimal({**EXECUTE, "when": {"any": [{"review_mode": "self"}, {"python": "True"}]}}),
        "unknown_predicate",
    ),
    "condition deeper than two": (
        minimal({**EXECUTE, "when": {"all": [{"any": [{"review_mode": "self"}]}]}}),
        "unknown_predicate",
    ),
    "predicate with two keys": (
        minimal({**EXECUTE, "when": {"review_mode": "self", "route_flag": "scout"}}),
        "invalid_shape",
    ),
    "role on a non-agent stage": (
        minimal(EXECUTE, {"id": "checks", "type": "run_checks", "role": "executor"}),
        "role_mismatch",
    ),
    "review run by another role": (
        minimal({"id": "review", "type": "agent_review", "role": "executor"}),
        "role_mismatch",
    ),
    "agent step without role": (minimal({"id": "execute", "type": "agent_step"}), "role_mismatch"),
    "unknown stage field": (minimal({**EXECUTE, "script": "rm -rf /"}), "unknown_field"),
    "unknown parameter": (minimal({**EXECUTE, "params": {"command": "x"}}), "unknown_field"),
    "unknown handler value": (
        minimal({**EXECUTE, "on": {"result_invalid": "report_fixer"}}),
        "invalid_value",
    ),
    "retries above five": (minimal({**EXECUTE, "params": {"retries": 6}}), "invalid_value"),
}


@pytest.mark.parametrize("case", SCHEMA_AND_DOMAIN_REJECT)
def test_schema_and_parser_both_refuse(case: str) -> None:
    document, reason = SCHEMA_AND_DOMAIN_REJECT[case]
    assert not schema_ok(WORKFLOW_SCHEMA, document)
    assert reason in reasons(document)


# Schema-valid documents whose transitions cannot happen; only the parser can see them.
DOMAIN_ONLY_REJECT = {
    "duplicate stage id": (minimal(EXECUTE, {**EXECUTE, "role": "executor"}), "duplicate_stage_id"),
    "role without a pinned profile": (
        minimal(EXECUTE, {"id": "review", "type": "agent_review"}, roles=["executor"]),
        "role_not_required",
    ),
    "empty requires_roles": (minimal(EXECUTE, roles=[]), "role_not_required"),
    "conflict handler on checks": (
        minimal(EXECUTE, {"id": "checks", "type": "run_checks", "on": {"conflict": "escalate"}}),
        "handler_not_applicable",
    ),
    "verdict handler on agent step": (
        minimal({**EXECUTE, "on": {"verdict_red": "escalate"}}),
        "handler_not_applicable",
    ),
    "result_invalid handler on checks": (
        minimal(EXECUTE, {"id": "checks", "type": "run_checks", "on": {"result_invalid": "escalate"}}),
        "handler_not_applicable",
    ),
    "checks scope on a review": (
        minimal(EXECUTE, {"id": "review", "type": "agent_review", "params": {"scope": "task"}}),
        "param_not_applicable",
    ),
    "push on an agent step": (minimal({**EXECUTE, "params": {"push": "intent"}}), "param_not_applicable"),
    "retries on a control-plane gate": (
        minimal(EXECUTE, {"id": "accept", "type": "acceptance_gate", "params": {"retries": 1}}),
        "param_not_applicable",
    ),
    "rework without an executor": (
        minimal({"id": "checks", "type": "run_checks", "on": {"checks_failed": "rework"}}),
        "handler_target_missing",
    ),
    "triage without a triager": (
        minimal(EXECUTE, {"id": "review", "type": "agent_review", "on": {"verdict_attention": "triage"}}),
        "handler_target_missing",
    ),
    "skip_if_optional on a required stage": (
        minimal({**EXECUTE, "on": {"result_invalid": "skip_if_optional"}}),
        "handler_target_missing",
    ),
    "acceptance gate only for gate tasks": (
        minimal(EXECUTE, {"id": "accept", "type": "acceptance_gate", "for_kinds": ["phase_gate"]}),
        "stage_never_applies",
    ),
    "work before prepare": (
        {**minimal(), "stage": [EXECUTE, {"id": "prepare", "type": "prepare_environment"}]},
        "prepare_not_first",
    ),
    "gate stage without its prepare": (
        minimal(EXECUTE, {"id": "phase", "type": "phase_gate"}),
        "prepare_not_first",
    ),
    "two environments for one kind": (
        minimal({"id": "again", "type": "prepare_environment", "for_kinds": ["unit"]}, EXECUTE),
        "duplicate_prepare",
    ),
}


@pytest.mark.parametrize("case", DOMAIN_ONLY_REJECT)
def test_parser_refuses_schema_valid_impossible_transitions(case: str) -> None:
    document, reason = DOMAIN_ONLY_REJECT[case]
    assert schema_ok(WORKFLOW_SCHEMA, document), registry().validate(WORKFLOW_SCHEMA, document)
    assert reason in reasons(document)


def test_example_mutations_are_refused_with_a_pointer() -> None:
    document = example("reviewed-development")
    broken = copy.deepcopy(document)
    stage(broken, "review")["on"]["verdict_red"] = "rework"
    definition, violations = parse_workflow(cast(JsonValue, broken))
    assert definition is None
    assert [(item.pointer, item.reason) for item in violations] == [
        ("/stage/6/on/verdict_red", "invalid_value")
    ]
    broken = copy.deepcopy(document)
    broken["stage"] = [item for item in broken["stage"] if item["id"] != "triage"]
    assert reasons(broken) == {"handler_target_missing"}
    assert schema_ok(WORKFLOW_SCHEMA, broken)


# A handler target must serve every task kind its source stage applies to, not merely exist somewhere.
def narrowed(name: str, stage_id: str, kinds: list[str]) -> dict[str, Any]:
    document = example(name)
    stage(document, stage_id)["for_kinds"] = kinds
    return document


UNCOVERED_TARGET = {
    "quick-fix triage only for integration": (
        narrowed("quick-fix", "triage", ["integration"]),
        {"/stage/3/on/verdict_attention", "/stage/3/on/verdict_red"},
        {"adhoc", "unit", "item", "followup"},
    ),
    "quick-fix executor only for item": (
        narrowed("quick-fix", "execute", ["item"]),
        {"/stage/2/on/checks_failed"},
        {"adhoc", "unit", "integration", "followup"},
    ),
    "gate review without a gate triager": (
        narrowed("reviewed-development", "triage", ["adhoc", "unit", "item", "integration", "followup"]),
        {"/stage/6/on/verdict_attention", "/stage/6/on/verdict_red"},
        {"item_gate", "phase_gate", "group_review"},
    ),
    "mixed work and gate rework without an item executor": (
        {
            **minimal(),
            "stage": [
                {"id": "prepare", "type": "prepare_environment", "for_kinds": ["unit", "item", "phase_gate"]},
                {**EXECUTE, "for_kinds": ["unit"]},
                {
                    "id": "checks",
                    "type": "run_checks",
                    "for_kinds": ["unit", "item", "phase_gate"],
                    "on": {"checks_failed": "rework"},
                },
            ],
        },
        {"/stage/2/on/checks_failed"},
        {"item"},
    ),
}


@pytest.mark.parametrize("case", UNCOVERED_TARGET)
def test_handler_target_must_serve_every_kind_of_its_source(case: str) -> None:
    document, pointers, kinds = UNCOVERED_TARGET[case]
    assert schema_ok(WORKFLOW_SCHEMA, document), registry().validate(WORKFLOW_SCHEMA, document)
    definition, violations = parse_workflow(cast(JsonValue, document))
    assert definition is None
    assert {item.pointer for item in violations} == pointers
    for item in violations:
        assert item.reason == "handler_target_missing"
        assert set(item.message.rsplit("task kind ", 1)[1].split(", ")) == kinds


def test_several_target_stages_cover_the_source_kinds_together() -> None:
    document = example("reviewed-development")
    gate_triage = {**stage(document, "triage"), "id": "gate_triage"}
    stage(document, "triage")["for_kinds"] = ["adhoc", "unit", "item", "integration", "followup"]
    gate_triage["for_kinds"] = ["item_gate", "phase_gate", "group_review"]
    document["stage"].insert(document["stage"].index(stage(document, "triage")) + 1, gate_triage)
    assert schema_ok(WORKFLOW_SCHEMA, document)
    by_id = {item.id: item for item in parsed(document).stages}
    assert applicable_kinds(by_id["triage"]) | applicable_kinds(by_id["gate_triage"]) >= applicable_kinds(
        by_id["review"]
    )
    quick = narrowed("quick-fix", "triage", ["integration"])
    quick["stage"].append(
        {**stage(quick, "triage"), "id": "triage_work", "for_kinds": ["adhoc", "unit", "item", "followup"]}
    )
    assert schema_ok(WORKFLOW_SCHEMA, quick)
    parsed(quick)


# An explicit null is outside workflow:v1; the parser must not read it as an absent field.
@pytest.mark.parametrize("field", ["when", "skip_when", "role", "requires_roles"])
def test_explicit_null_is_refused_by_schema_and_parser(field: str) -> None:
    document = example("quick-fix")
    target = document if field == "requires_roles" else stage(document, "review")
    target[field] = None
    assert not schema_ok(WORKFLOW_SCHEMA, document)
    definition, violations = parse_workflow(cast(JsonValue, document))
    assert definition is None
    pointer = "/requires_roles" if field == "requires_roles" else f"/stage/3/{field}"
    assert pointer in {item.pointer for item in violations}, violations


@pytest.mark.parametrize("field", ["when", "skip_when"])
def test_absent_or_valid_condition_is_accepted(field: str) -> None:
    absent = example("quick-fix")
    stage(absent, "review").pop(field, None)
    assert schema_ok(WORKFLOW_SCHEMA, absent)
    assert getattr(parsed(absent).stages[3], field) is None
    valid = example("quick-fix")
    stage(valid, "review")[field] = {"review_mode": "required"}
    assert schema_ok(WORKFLOW_SCHEMA, valid)
    assert getattr(parsed(valid).stages[3], field) == ReviewModeIs(ReviewMode.REQUIRED)


def test_every_defect_of_every_stage_is_reported() -> None:
    document = minimal(
        {"id": "a", "type": "report_fix"},
        {"id": "b", "type": "agent_step", "role": "report_fixer"},
        {**EXECUTE, "when": {"eval": "1"}},
    )
    _, violations = parse_workflow(cast(JsonValue, document))
    assert [(item.pointer, item.reason) for item in violations] == [
        ("/stage/1/type", "unknown_stage_type"),
        ("/stage/2/role", "unknown_role"),
        ("/stage/3/when/eval", "unknown_predicate"),
    ]


JSON = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=8),
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4),
    max_leaves=12,
)


@settings(max_examples=200, deadline=None)
@given(junk=JSON, where=st.sampled_from(["root", "stage", "when", "params", "on", "role", "for_kinds"]))
def test_parser_is_total_and_refuses_junk(junk: Any, where: str) -> None:
    if where == "root":
        document: Any = junk
    elif where == "stage":
        document = minimal(junk)
    elif where == "when":
        document = minimal({**EXECUTE, "when": junk})
    else:
        document = minimal({**EXECUTE, where: junk})
    definition, violations = parse_workflow(document)
    assert (definition is None) == bool(violations)
    if definition is not None:
        assert schema_ok(WORKFLOW_SCHEMA, document)


# --- seven role contracts: schemas, profiles, same-role retry -------------------------------------


def test_exactly_seven_roles_and_no_report_fixer() -> None:
    assert [role.value for role in RoleId] == [
        "scout",
        "executor",
        "reviewer",
        "triager",
        "advisor",
        "researcher",
        "registrar",
    ]
    assert set(ROLE_CONTRACTS) == set(RoleId)
    assert "report_fixer" not in {role.value for role in RoleId}
    assert not [urn for urn in registry().urns() if "report-fixer" in urn or "report_fixer" in urn]
    extensions_roles = cast(dict[str, Any], registry().get("urn:skm:extensions:defs:v1"))["$defs"]["role_id"]
    assert set(extensions_roles["enum"]) == set(RoleId)


@pytest.mark.parametrize("role", list(RoleId), ids=str)
def test_role_contract_names_a_registered_closed_schema(role: RoleId) -> None:
    contract = ROLE_CONTRACTS[role]
    assert contract.role is role
    assert contract.result_schema_urn == result_schema_urn(role) == f"urn:skm:execution:role-result:{role}:v1"
    assert role_for_result_schema(contract.result_schema_urn) is role
    document = cast(dict[str, Any], registry().get(contract.result_schema_urn))
    assert document["properties"]["schema"] == {"const": contract.result_schema_urn}
    assert document["additionalProperties"] is False
    assert "schema" in document["required"]
    assert role in AGENT_STAGE_ROLES[contract.stage_type]
    assert (contract.write_authority is WriteAuthority.CODE_SCOPE) == (role is RoleId.EXECUTOR)
    path = ROOT / f"src/skm/schemas/execution/role-result-{role}.v1.json"
    assert json.loads(path.read_text(encoding="utf-8"))["$id"] == contract.result_schema_urn


def test_result_kinds_are_the_heal_and_drift_kinds() -> None:
    kinds = {role: contract.result_kind for role, contract in ROLE_CONTRACTS.items()}
    assert kinds[RoleId.EXECUTOR] is ResultKind.STAGE_REPORT
    assert kinds[RoleId.REVIEWER] is ResultKind.REVIEW_FINDINGS
    assert kinds[RoleId.TRIAGER] is ResultKind.TRIAGE_RESULT
    assert len(set(kinds.values())) == len(RoleId)


def test_foreign_result_schemas_map_to_no_role() -> None:
    for urn in (
        "urn:skm:execution:role-result:report_fixer:v1",
        "urn:skm:execution:role-result:executor:v2",
        "urn:skm:execution:fix-brief:v1",
        "urn:skm:execution:workflow:v1",
    ):
        assert role_for_result_schema(urn) is None


@pytest.mark.parametrize("role", list(RoleId), ids=str)
def test_role_result_example_validates_against_its_contract(role: RoleId) -> None:
    urn = ROLE_CONTRACTS[role].result_schema_urn
    if role is RoleId.RESEARCHER:
        document: Any = {
            "schema": urn,
            "status": "partial",
            "query": "Does the refresh-token reuse rule revoke the family?",
            "claims": [{"text": "Reuse invalidates the family.", "document_ids": [UUID]}],
            "contradictions": [],
            "unknowns": ["server behaviour under clock skew"],
            "sources_used": ["rfc-9700"],
            "follow_up_queries": [],
            "usage_complete": True,
        }
    else:
        document = json.loads((ROLE_RESULTS / f"{role}.json").read_text(encoding="utf-8"))
    assert registry().validate(urn, document) == ()
    for other in set(RoleId) - {role}:
        assert not schema_ok(ROLE_CONTRACTS[other].result_schema_urn, document), other


def test_invalid_results_are_refused_for_the_same_role_retry() -> None:
    executor = ROLE_CONTRACTS[RoleId.EXECUTOR].result_schema_urn
    for name in ("executor.invalid.json", "executor.unhealable.json"):
        assert not schema_ok(executor, json.loads((ROLE_RESULTS / name).read_text(encoding="utf-8"))), name
    assert schema_ok(
        executor, json.loads((ROLE_RESULTS / "executor.healed.json").read_text(encoding="utf-8"))
    )
    hint = json.loads((ROLE_RESULTS / "executor.schema-errors.json").read_text(encoding="utf-8"))
    assert hint["next"]["stage_id"] == "execute"
    assert hint["next"]["purpose"] == "result_retry"
    assert hint["next"]["feedback"]["schema_errors_step_id"] == hint["step_id"]


def test_researcher_refuses_legacy_shape_and_foreign_document_ids() -> None:
    urn = ROLE_CONTRACTS[RoleId.RESEARCHER].result_schema_urn
    legacy = json.loads((ROLE_RESULTS / "researcher.json").read_text(encoding="utf-8"))
    assert {"answer", "limitations"} & set(legacy)
    assert not schema_ok(urn, legacy)
    valid: dict[str, Any] = {
        "schema": urn,
        "status": "complete",
        "query": "q",
        "claims": [{"text": "c", "document_ids": [UUID]}],
        "contradictions": [],
        "unknowns": [],
        "sources_used": ["local-docs"],
        "follow_up_queries": [],
    }
    assert schema_ok(urn, valid)
    for bad in (
        {**valid, "claims": [{"text": "c", "document_ids": ["S1"]}]},
        {**valid, "claims": [{"text": "c", "document_ids": [UUID] * 11}]},
        {**valid, "claims": [{"text": "c", "source_ids": [UUID]}]},
        {**valid, "sources_used": ["Local Docs"]},
        {**valid, "unknowns": [""]},
        {**valid, "answer": "x"},
    ):
        assert not schema_ok(urn, bad), bad


@pytest.mark.parametrize("path", PROFILES, ids=lambda path: path.stem)
def test_agent_profile_result_schema_and_tools_fit_the_role_contract(path: Path) -> None:
    profile = load_toml(path)
    contract = ROLE_CONTRACTS[RoleId(profile["role"])]
    assert profile["result_schema"] == contract.result_schema_urn
    assert profile["result_schema"] in registry().urns()
    allowed = set(profile["permissions"].get("layer", {}).get("tools", {}).get("allow", []))
    if allowed & {"fs.write", "fs.edit", "fs.delete"}:
        assert contract.tools.filesystem is FilesystemAccess.WRITE
    if "fs.read" in allowed:
        assert contract.tools.filesystem is not FilesystemAccess.NONE
    if "shell.run" in allowed:
        assert contract.tools.shell is not ShellAccess.NONE


def test_fix_brief_example_validates() -> None:
    for name in ("fix-brief.json", "fix-brief.truncated.json"):
        document = json.loads((EXAMPLES / "execution/examples" / name).read_text(encoding="utf-8"))
        assert registry().validate("urn:skm:execution:fix-brief:v1", document) == (), name


def test_contracts_load_without_application_handlers() -> None:
    probe = (
        "import sys\n"
        "import skm.modules.execution.domain.role_contracts\n"
        "import skm.modules.execution.domain.workflow.definition\n"
        "from skm.platform.schema.registry import SchemaRegistry\n"
        "SchemaRegistry.load_default()\n"
        "bad = sorted(m for m in sys.modules if m.startswith('skm.modules.') and '.application' in m)\n"
        "print(bad)\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"


# --- history and action markers --------------------------------------------------------------------


def record(seq: int, stage_id: str, outcome: StageOutcomeKind | None) -> StageEntry:
    started = datetime(2026, 10, 1, tzinfo=UTC)
    fake = cast(Any, None)
    return StageEntry(
        StageRecord(
            id=fake,
            attempt_id=fake,
            run_id=fake,
            task_id=fake,
            seq=seq,
            stage_id=stage_id,
            stage_type="agent_step",
            round_no=1,
            mode=fake,
            retry_of_id=None,
            state=fake,
            input_digest="sha256:" + "0" * 64,
            outcome_kind=outcome,
            outcome=None,
            error_code=None,
            started_at=started,
            finished_at=None,
            fencing_token=1,
            runtime_started_at=None,
            process_identities=(),
            reused_from_step_id=None,
        ),
        (),
    )


def test_result_retries_count_same_stage_invalid_results_since_a_valid_one() -> None:
    invalid, success = StageOutcomeKind.RESULT_INVALID, StageOutcomeKind.SUCCESS
    history = StageHistory(
        (
            record(5, "execute", invalid),
            record(1, "execute", invalid),
            record(2, "execute", success),
            record(3, "checks", invalid),
            record(4, "execute", StageOutcomeKind.RUNTIME_ERROR),
            record(6, "review", invalid),
            record(7, "review", StageOutcomeKind.VERDICT_GREEN),
        )
    )
    assert history.result_retries_used("execute") == 1
    assert history.result_retries_used("checks") == 1
    assert history.result_retries_used("review") == 0
    assert history.result_retries_used("triage") == 0
    assert [entry.record.seq for entry in history.of_stage("execute")] == [1, 2, 4, 5]
    last = history.last()
    assert last is not None
    assert last.record.seq == 7
    assert StageHistory(()).last() is None


def test_terminal_markers_compare_by_value() -> None:
    assert Done() == Done()
    assert Noop() == Noop()
    assert Done() != Noop()
