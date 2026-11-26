"""Run task compilation from the planning graph (execution §4.4-4.5, §7.1 start_run, K14)."""

from __future__ import annotations

import copy
import dataclasses
import json
import tomllib
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.carry_forward import (
    CompatibilityInputs,
    compare_compatibility,
    compatibility_digest,
)
from skm.modules.execution.domain.task import ReviewMode, Task, TaskKind, TaskStatus
from skm.modules.execution.domain.task_graph import (
    PLAN_ACCEPTANCE_KEY,
    CompiledRunTasks,
    EdgeKind,
    SatisfiedEvidence,
    SelectionRequest,
    TaskFacts,
    compile_run_tasks,
    gate_members,
    prerequisites,
    ready_task_ids,
)
from skm.modules.execution.domain.workflow.definition import WorkflowDefinition, parse_workflow

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES = ROOT / "tests/fixtures/corpus/examples"
NOW = datetime(2026, 10, 25, 11, 40, tzinfo=UTC)
RUN: Any = UUID(int=1)
WORKSPACE: Any = UUID(int=2)


@cache
def graph_document() -> JsonObject:
    return cast(
        "JsonObject", json.loads((EXAMPLES / "plans/compiled-graph.json").read_text(encoding="utf-8"))
    )


def graph() -> JsonObject:
    return copy.deepcopy(graph_document())


@cache
def workflow(name: str) -> WorkflowDefinition:
    document = tomllib.loads((EXAMPLES / f"execution/workflows/{name}.toml").read_text(encoding="utf-8"))
    definition, violations = parse_workflow(cast("JsonValue", document))
    assert violations == ()
    assert definition is not None
    return definition


WITH_PLAN = "reviewed-development"
WITHOUT_PLAN = "quick-fix"


def entity(key: str) -> Any:
    tasks = cast("list[dict[str, Any]]", graph_document()["tasks"])
    return UUID(next(task["entity_id"] for task in tasks if task["task_key"] == key))


def compile_(
    selection: SelectionRequest | None = None,
    satisfied: dict[str, SatisfiedEvidence] | None = None,
    *,
    name: str = WITH_PLAN,
    policy: JsonObject | None = None,
    document: JsonObject | None = None,
    facts: dict[str, TaskFacts] | None = None,
) -> CompiledRunTasks:
    counter = iter(range(1000, 2000))
    source = document if document is not None else graph()
    return compile_run_tasks(
        source,
        workflow(name),
        policy or {},
        selection,
        satisfied or {},
        run_id=RUN,
        workspace_id=WORKSPACE,
        revision_id=UUID(str(source["revision_id"])),  # type: ignore[arg-type]
        new_task_id=lambda: UUID(int=next(counter)),
        now=NOW,
        facts=facts,
    )


def by_key(result: CompiledRunTasks) -> dict[str, Task]:
    return {task.display_key: task for task in result.tasks}


def keys_of(result: CompiledRunTasks, ids: tuple[Any, ...]) -> list[str]:
    names = {task.id: task.display_key for task in result.tasks}
    return [names[found] for found in ids]


def inputs(**changes: Any) -> CompatibilityInputs:
    values: dict[str, Any] = {
        "entity_contract_digest": "sha256:" + "1" * 64,
        "resolved_resources": {"skill:python-testing": "sha256:" + "2" * 64, "agent_profile:executor": "v3"},
        "checks": {"P1:V1": "sha256:" + "3" * 64},
        "config_interpretation_digest": "sha256:" + "4" * 64,
        "acceptance_policy_digest": "sha256:" + "5" * 64,
        "materials": {},
        "predecessor_outputs": {"P1.2": "sha256:" + "6" * 64},
        "baseline": {"api": "a" * 40},
    }
    values.update(changes)
    return CompatibilityInputs(**values)


def evidence(key: str, target: CompatibilityInputs | None = None, **changes: Any) -> SatisfiedEvidence:
    values: dict[str, Any] = {
        "source_task_id": UUID(int=77),
        "source_entity_id": entity(key),
        "source": inputs(),
        "target": target if target is not None else inputs(),
    }
    values.update(changes)
    return SatisfiedEvidence(**values)


# --- the full run


def test_full_run_compiles_every_task_with_its_revision_identity() -> None:
    result = compile_()
    tasks = by_key(result)
    order = cast("list[str]", graph_document()["topological_order"])
    assert list(tasks) == [*order, PLAN_ACCEPTANCE_KEY]
    assert [task.position for task in result.tasks] == list(range(len(order) + 1))
    for key in order:
        assert tasks[key].spec_entity_id == entity(key)
        assert tasks[key].status is TaskStatus.BLOCKED
        assert tasks[key].run_id == RUN
    assert {task.kind for task in result.tasks} == {
        TaskKind.UNIT, TaskKind.ITEM, TaskKind.ITEM_GATE, TaskKind.PHASE_GATE, TaskKind.PLAN_ACCEPTANCE,
    }  # fmt: skip
    assert result.selection is None
    assert result.compiler_version == 1


def test_review_modes_by_kind() -> None:
    tasks = by_key(compile_())
    assert tasks["P1.1/U1"].review_mode is ReviewMode.SELF
    assert tasks["P1.1#gate"].review_mode is ReviewMode.REQUIRED
    assert tasks["P1.2"].review_mode is ReviewMode.REQUIRED
    assert tasks["P2.3"].review_mode is ReviewMode.WAIVED
    assert tasks["P1#gate"].review_mode is ReviewMode.WAIVED  # execution.gates.phase_review = off
    assert tasks[PLAN_ACCEPTANCE_KEY].review_mode is ReviewMode.WAIVED
    for value, mode in (
        ("always", ReviewMode.REQUIRED),
        ("on_risk", ReviewMode.SELF),
        ("off", ReviewMode.WAIVED),
    ):
        assert by_key(compile_(policy={"phase_review": value}))["P2#gate"].review_mode is mode


def test_work_kind_scope_and_profile() -> None:
    facts = {"P1.2": TaskFacts("docs", "security"), "P1.1#gate": TaskFacts("code", "reviewer")}
    tasks = by_key(compile_(facts=facts))
    assert (tasks["P1.2"].work_kind, tasks["P1.2"].review_profile) == ("docs", "security")
    assert tasks["P1.1/U1"].work_kind == "code"
    assert tasks["P1.1#gate"].work_kind == "review"  # gates never write code
    assert tasks["P1.1#gate"].declared_write_scope == ()
    unit_scope = tasks["P1.1/U1"].declared_write_scope
    assert unit_scope is not None
    assert [(found.mount, found.pattern) for found in unit_scope] == [("api", "migrations/versions/*.py")]


def test_planning_edges_become_blocks_edges_with_their_reasons() -> None:
    result = compile_()
    tasks = by_key(result)
    blocks = [edge for edge in result.edges if edge.kind is EdgeKind.BLOCKS]
    assert len(blocks) == len(cast("list[Any]", graph_document()["edges"]))
    p23 = {
        keys_of(result, (edge.prerequisite_task_id,))[0]: edge.reasons
        for edge in blocks
        if edge.dependent_task_id == tasks["P2.3"].id
    }
    assert p23 == {
        "P1#gate": {"PHASE_DEPENDS_ON"},
        "P2.1#gate": {"BATCH_ORDER", "ITEM_DEPENDS_ON"},
        "P2.2#gate": {"BATCH_ORDER", "ITEM_DEPENDS_ON"},
    }
    assert keys_of(result, gate_members(tasks["P1#gate"], result.edges)) == ["P1.1#gate", "P1.2"]
    assert keys_of(result, gate_members(tasks["P1.1#gate"], result.edges)) == ["P1.1/U1", "P1.1/U2"]


def test_plan_acceptance_depends_on_every_phase_gate() -> None:
    result = compile_()
    plan = by_key(result)[PLAN_ACCEPTANCE_KEY]
    assert (plan.kind, plan.spec_entity_id, plan.origin, plan.work_kind) == (
        TaskKind.PLAN_ACCEPTANCE,
        None,
        None,
        "review",
    )
    members = [edge for edge in result.edges if edge.dependent_task_id == plan.id]
    assert {edge.kind for edge in members} == {EdgeKind.GATE_MEMBER}
    assert keys_of(result, gate_members(plan, result.edges)) == ["P1#gate", "P2#gate"]


def test_plan_acceptance_needs_the_stage_in_the_workflow() -> None:
    assert PLAN_ACCEPTANCE_KEY not in by_key(compile_(name=WITHOUT_PLAN))


def test_required_batches_group_work_tasks_without_blocking_them() -> None:
    result = compile_()
    batch = [edge for edge in result.edges if edge.kind is EdgeKind.BATCH]
    assert sorted(keys_of(result, tuple(edge.dependent_task_id for edge in batch))) == ["P2.2/U1", "P2.2/U2"]
    assert set(keys_of(result, tuple(edge.prerequisite_task_id for edge in batch))) == {"P2.1/U1"}
    p22 = by_key(result)["P2.2/U1"]
    assert keys_of(result, prerequisites(p22.id, result.edges)) == ["P1#gate"]


def test_initial_tasks_are_blocked_with_their_prerequisites() -> None:
    result = compile_()
    tasks = by_key(result)
    reason = tasks["P1.1#gate"].blocking_reason
    assert reason is not None
    assert reason.code is BlockingCode.BLOCKED_BY_DEPENDENCY
    assert sorted(cast("list[str]", reason.refs["prerequisite_task_ids"])) == sorted(
        str(tasks[key].id) for key in ("P1.1/U1", "P1.1/U2")
    )
    assert keys_of(result, ready_task_ids(result.tasks, result.edges)) == ["P1.1/U1"]


def test_ready_only_when_every_prerequisite_is_accepted_or_skipped() -> None:
    result = compile_()
    tasks = by_key(result)

    def with_status(statuses: dict[str, TaskStatus]) -> list[Task]:
        changed = []
        for task in result.tasks:
            status = statuses.get(task.display_key)
            if status is None:
                changed.append(task)
            else:
                accepted = {"accepted_attempt_id": UUID(int=5)} if status is TaskStatus.ACCEPTED else {}
                changed.append(dataclasses.replace(task, status=status, blocking_reason=None, **accepted))
        return changed

    accepted = with_status({"P1.1/U1": TaskStatus.ACCEPTED})
    assert keys_of(result, ready_task_ids(accepted, result.edges)) == ["P1.1/U2"]
    skipped = with_status({"P1.1/U1": TaskStatus.SKIPPED, "P1.1/U2": TaskStatus.ACCEPTED})
    assert keys_of(result, ready_task_ids(skipped, result.edges)) == ["P1.1#gate"]
    for status in (TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.SUPERSEDED, TaskStatus.INTEGRATING):
        assert tasks["P1.1/U2"].id not in ready_task_ids(with_status({"P1.1/U1": status}), result.edges)


def test_compilation_is_deterministic() -> None:
    assert compile_() == compile_()


# --- selection (K14)


def test_selected_tasks_with_their_not_accepted_ancestors_and_no_plan_acceptance() -> None:
    result = compile_(SelectionRequest(task_keys=("P1.2",)))
    assert [task.display_key for task in result.tasks] == ["P1.1/U1", "P1.1/U2", "P1.1#gate", "P1.2"]
    assert result.selection is not None
    assert result.selection.compiled_keys == ("P1.1/U1", "P1.1/U2", "P1.1#gate", "P1.2")
    assert result.selection.task_keys == ("P1.2",)
    assert result.selection.satisfied == ()


def test_phases_select_their_tasks() -> None:
    result = compile_(SelectionRequest(phases=("P1",)))
    assert [task.display_key for task in result.tasks] == [
        "P1.1/U1",
        "P1.1/U2",
        "P1.1#gate",
        "P1.2",
        "P1#gate",
    ]


def test_stop_after_is_inclusive() -> None:
    result = compile_(SelectionRequest(phases=("P1", "P2"), stop_after="P1.2"))
    assert [task.display_key for task in result.tasks] == ["P1.1/U1", "P1.1/U2", "P1.1#gate", "P1.2"]
    only_stop = compile_(SelectionRequest(stop_after="P1.1#gate"))
    assert [task.display_key for task in only_stop.tasks] == ["P1.1/U1", "P1.1/U2", "P1.1#gate"]


def test_a_proven_satisfied_ancestor_is_not_compiled() -> None:
    result = compile_(SelectionRequest(task_keys=("P2.3",)), {"P1#gate": evidence("P1#gate")})
    keys = [task.display_key for task in result.tasks]
    assert keys == ["P2.1/U1", "P2.1/U2", "P2.1#gate", "P2.2/U1", "P2.2/U2", "P2.2#gate", "P2.3"]
    assert result.selection is not None
    assert [(found.display_key, found.source_task_id) for found in result.selection.satisfied] == [
        ("P1#gate", UUID(int=77))
    ]
    p23 = by_key(result)["P2.3"]
    assert sorted(keys_of(result, prerequisites(p23.id, result.edges))) == ["P2.1#gate", "P2.2#gate"]
    assert keys_of(result, ready_task_ids(result.tasks, result.edges)) == ["P2.1/U1", "P2.2/U1"]


@pytest.mark.parametrize(
    "target",
    [
        inputs(checks={"P1:V1": "sha256:" + "9" * 64}),  # a mandatory check changed
        inputs(
            resolved_resources={"skill:python-testing": "sha256:" + "8" * 64, "agent_profile:executor": "v3"}
        ),
        inputs(baseline={"api": "b" * 40}),
        inputs(acceptance_policy_digest="sha256:" + "7" * 64),
        inputs(materials={"design.pdf": "sha256:" + "0" * 64}),
        inputs(predecessor_outputs={"P1.2": "sha256:" + "0" * 64}),
        inputs(config_interpretation_digest="sha256:" + "0" * 64),
        inputs(baseline=None),  # target evidence missing
        inputs(resolved_resources=None),
    ],
    ids=[
        "check",
        "skill",
        "baseline",
        "acceptance",
        "material",
        "predecessor",
        "config",
        "no-baseline",
        "no-pins",
    ],
)
def test_changed_or_missing_evidence_keeps_the_ancestor(target: CompatibilityInputs) -> None:
    result = compile_(SelectionRequest(task_keys=("P2.3",)), {"P1#gate": evidence("P1#gate", target)})
    keys = [task.display_key for task in result.tasks]
    assert "P1#gate" in keys
    assert {"P1.1/U1", "P1.2"} <= set(keys)
    assert result.selection is not None
    assert result.selection.satisfied == ()


def test_the_same_spec_with_another_pinned_skill_is_not_compatible() -> None:
    source = inputs()
    target = inputs(
        resolved_resources={
            **dict(source.resolved_resources or {}),
            "skill:python-testing": "sha256:" + "f" * 64,
        }
    )
    assert source.entity_contract_digest == target.entity_contract_digest
    verdict = compare_compatibility(source, target)
    assert (verdict.compatible, verdict.differing) == (False, ("resolved_resources",))


def test_a_name_or_another_entity_is_not_evidence() -> None:
    other_entity = evidence("P1#gate", source_entity_id=entity("P2#gate"))
    result = compile_(SelectionRequest(task_keys=("P2.3",)), {"P1#gate": other_entity})
    assert "P1#gate" in by_key(result)
    unknown = compile_(SelectionRequest(task_keys=("P2.3",)), {"P9#gate": evidence("P1#gate")})
    assert "P1#gate" in by_key(unknown)


def test_missing_evidence_on_both_sides_is_not_equality() -> None:
    both_missing = inputs(materials=None)
    assert compatibility_digest(both_missing) is None
    verdict = compare_compatibility(both_missing, both_missing)
    assert verdict.compatible is False
    assert verdict.missing == ("source.materials", "target.materials")


def test_a_chosen_task_is_compiled_even_with_evidence() -> None:
    result = compile_(SelectionRequest(task_keys=("P1.2",)), {"P1.2": evidence("P1.2")})
    assert "P1.2" in by_key(result)


def test_a_gate_is_compiled_only_with_all_its_members() -> None:
    result = compile_(SelectionRequest(task_keys=("P1.1#gate",)), {"P1.1/U1": evidence("P1.1/U1")})
    assert [task.display_key for task in result.tasks] == ["P1.1/U2"]


def test_a_dependent_of_a_left_out_gate_waits_for_its_compiled_members() -> None:
    result = compile_(SelectionRequest(task_keys=("P1.2",)), {"P1.1/U1": evidence("P1.1/U1")})
    tasks = by_key(result)
    assert list(tasks) == ["P1.1/U2", "P1.2"]
    edge = next(found for found in result.edges if found.dependent_task_id == tasks["P1.2"].id)
    assert keys_of(result, (edge.prerequisite_task_id,)) == ["P1.1/U2"]
    assert edge.reasons == {"ITEM_DEPENDS_ON"}
    assert keys_of(result, ready_task_ids(result.tasks, result.edges)) == ["P1.1/U2"]


@pytest.mark.parametrize(
    ("selection", "keys"),
    [
        (SelectionRequest(task_keys=("P9.9",)), ["P9.9"]),
        (SelectionRequest(phases=("P7",)), ["P7"]),
        (SelectionRequest(task_keys=("P1.2",), stop_after="P1.9"), ["P1.9"]),
        (SelectionRequest(task_keys=("P0.1", "P1.2"), phases=("P5",)), ["P0.1", "P5"]),
    ],
)
def test_unknown_keys_are_not_found(selection: SelectionRequest, keys: list[str]) -> None:
    with pytest.raises(SkmError) as caught:
        compile_(selection)
    assert caught.value.code is ErrorCode.NOT_FOUND
    assert caught.value.details["keys"] == keys


def test_an_empty_selection_result_has_no_tasks() -> None:
    with pytest.raises(SkmError) as caught:
        compile_(SelectionRequest(task_keys=("P1.2",), stop_after="P1.1/U1"))
    assert caught.value.code is ErrorCode.NO_TASKS


# --- graph protection


def test_a_graph_of_another_revision_is_refused() -> None:
    document = graph()
    with pytest.raises(SkmError) as caught:
        compile_run_tasks(
            document, workflow(WITH_PLAN), {}, None, {}, run_id=RUN, workspace_id=WORKSPACE,
            revision_id=cast("Any", UUID(int=9)), new_task_id=lambda: UUID(int=1), now=NOW,
        )  # fmt: skip
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_a_cycle_is_refused() -> None:
    document = graph()
    edges = cast("list[JsonValue]", document["edges"])
    edges.append({"dependent": "P1.1/U1", "prerequisite": "P1.2", "reasons": ["unit_depends_on"]})
    with pytest.raises(SkmError) as caught:
        compile_(document=document)
    assert caught.value.code is ErrorCode.DEPENDENCY_CYCLE


def test_the_view_field_names_are_read_too() -> None:
    document = graph()
    for task in cast("list[dict[str, Any]]", document["tasks"]):
        task["phase_key"] = task.pop("phase")
        task["item_key"] = task.pop("item")
        task["materials"] = []
    for group in cast("list[dict[str, Any]]", document["batch_groups"]):
        group["phase_key"] = group.pop("phase")
        group["batch_key"] = group.pop("batch")
    assert compile_(document=document) == compile_()
