"""Observed material freshness and workflow applicability for readiness rules."""

from typing import Any
from uuid import UUID

from skm.kernel.errors import SkmError
from skm.kernel.ids import FileVersionId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._plain import plain
from skm.modules.execution.domain.task import GATE_KINDS, TaskKind
from skm.modules.execution.domain.task_graph import EdgeKind
from skm.modules.execution.domain.workflow.definition import gate_workflow_violations
from skm.modules.planning import public as planning


def material_facts(uow: UnitOfWork, workspace_id: Any, refs: Any, now: Any) -> list[Any]:
    result: list[Any] = []
    for ref in refs:
        raw = plain(ref)
        version = None
        if raw.get("file_version_id"):
            try:
                ready = artifacts.require_ready_versions(
                    uow, workspace_id, (FileVersionId(UUID(raw["file_version_id"])),)
                )[0]
                version = planning.FileVersionObservation(planning.FileVersionStatus.READY, ready.created_at)
                raw["digest"] = ready.digest
            except SkmError:
                version = planning.FileVersionObservation(planning.FileVersionStatus.NOT_READY, None)
        assessment = planning.assess_material(ref, planning.MaterialObservation(version, None), now=now)
        # Checkout existence remains a host admission assumption. Immutable file and
        # captured external material freshness is decided now from real observations.
        raw.update(
            available=assessment.state
            in {
                planning.MaterialState.AVAILABLE,
                planning.MaterialState.STALE,
                planning.MaterialState.UNKNOWN,
            },
            fresh=assessment.state is not planning.MaterialState.STALE,
            state=assessment.state.value,
        )
        result.append(raw)
    return result


def gate_facts(compiled: Any, graph: Any, workflow: Any, spec: Any) -> list[Any]:
    raw = {t["task_key"]: dict(t) for t in graph["tasks"]}
    required = {str(c.id) for c in spec.checks if c.required}
    result = list(raw.values())
    for task in compiled.tasks:
        if task.kind not in GATE_KINDS:
            continue
        fact = raw.get(task.display_key)
        if fact is None:
            fact = {"task_key": task.display_key}
            result.append(fact)
        checks_required = any(str(b["check_id"]) in required for b in fact.get("checks", []))
        if task.kind is TaskKind.PLAN_ACCEPTANCE:
            checks_required |= any(
                c.required and (c.owner == "plan" or c.rerun_after_integration) for c in spec.checks
            )
        fact.update(
            gate_required=task.review_mode.value == "required" or checks_required,
            gate_supported=not gate_workflow_violations(workflow, task, required_checks=checks_required),
        )
    return result


def progressive_facts(
    document: Any,
    graph: Any,
    tasks: list[Any],
    compiled: Any,
    materials: Any,
    requested_phases: set[str],
) -> tuple[Any, Any, list[Any], tuple[Any, ...]]:
    """Limit readiness to selected tasks, their predecessors and the entities they use."""
    keys = {task.display_key for task in compiled.tasks}
    selected_tasks = [task for task in tasks if task["task_key"] in keys]
    phase_keys = requested_phases | {task["phase"] for task in selected_tasks}
    item_keys = {task["item"] for task in selected_tasks if task["item"] is not None}
    owners = keys | phase_keys | item_keys
    items = [item for item in document["items"] if item["key"] in item_keys]
    criteria = [criterion for criterion in document["criteria"] if criterion["owner"] in owners]
    check_ids = {binding["check_id"] for task in selected_tasks for binding in task["checks"]}
    check_refs = {ref for criterion in criteria for ref in criterion["checks"]}
    requirement_refs = {ref for item in items for ref in item["implements"]}
    requirement_refs.update(ref for criterion in criteria for ref in criterion["requirements"])
    material_ids = {material_id for task in selected_tasks for material_id in task["materials"]}
    doc = {
        **document,
        "phases": [phase for phase in document["phases"] if phase["key"] in phase_keys],
        "items": items,
        "criteria": criteria,
        "requirements": [
            req
            for req in document["requirements"]
            if {req["key"], req["id"]} & requirement_refs or owners.intersection(req["owners"])
        ],
        "checks": [
            check
            for check in document["checks"]
            if check["owner"] in owners
            or check["id"] in check_ids
            or {check["id"], f"{check['owner']}:{check['key']}"} & check_refs
        ],
    }
    # Use the compiler's final edges, which also account for gates omitted by a selection.
    key_by_id = {task.id: task.display_key for task in compiled.tasks}
    scoped_graph = {
        **graph,
        "tasks": selected_tasks,
        "edges": [
            {
                "dependent": key_by_id[edge.dependent_task_id],
                "prerequisite": key_by_id[edge.prerequisite_task_id],
                "reasons": sorted(edge.reasons),
            }
            for edge in compiled.edges
            if edge.kind is not EdgeKind.BATCH
        ],
    }
    selected_materials = tuple(
        ref
        for ref in materials
        if ref["is_global"] or ref["material_id"] in material_ids or owners.intersection(ref["applies_to"])
    )
    return doc, scoped_graph, selected_tasks, selected_materials
