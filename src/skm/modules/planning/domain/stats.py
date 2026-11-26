"""Aggregated plan statistics over a specification and its compiled execution graph (planning §5.9)."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from skm.modules.planning.domain.check_spec import CheckCategory, CheckKind
from skm.modules.planning.domain.criterion import Criterion, VerificationMode
from skm.modules.planning.domain.decision import DecisionState
from skm.modules.planning.domain.material import MaterialKind, MaterialStage
from skm.modules.planning.domain.phase import DesignState
from skm.modules.planning.domain.requirement import Priority
from skm.modules.planning.domain.review_requirement import WaivedReview

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.modules.planning.domain.compile_graph import ExecutionGraph
    from skm.modules.planning.domain.specification import Specification

__all__ = ["PlanStats", "compute_stats"]

type _Breakdown = Mapping[str, Mapping[str, int]]


@dataclass(frozen=True, slots=True)
class PlanStats:
    counts: Mapping[str, int | _Breakdown]
    items_per_phase: Mapping[str, int]
    units_per_item: Mapping[str, int]
    criteria_coverage: Mapping[str, int]
    requirements_coverage: Mapping[str, int]
    write_scope: Mapping[str, int]
    graph: Mapping[str, int]
    skeleton_phases: tuple[str, ...]
    materials_required: Mapping[str, int]


def _check_key(criterion: Criterion, ref: str) -> str:
    return ref if ":" in ref else f"{criterion.owner.split('/', 1)[0]}:{ref}"


def _criteria_coverage(spec: Specification) -> dict[str, int]:
    checks_by_key = {f"{check.owner}:{check.key}": check for check in spec.checks}
    owners = {entity.key: entity for entity in (*spec.items, *spec.units)}
    with_check_or_manual = 0
    with_review = 0
    unlinked = 0

    for criterion in spec.criteria:
        found = [
            checks_by_key[key]
            for ref in criterion.checks
            if (key := _check_key(criterion, ref)) in checks_by_key
        ]
        dangling = len(found) < len(criterion.checks)
        match criterion.verification_mode:
            case VerificationMode.CHECK:
                if not criterion.checks:
                    unlinked += 1
                else:
                    with_check_or_manual += 1
            case VerificationMode.MANUAL:
                if not dangling and not any(c.kind is CheckKind.MANUAL for c in found):
                    unlinked += 1
                else:
                    with_check_or_manual += 1
            case VerificationMode.REVIEW:
                owner = owners.get(criterion.owner)
                review = None if owner is None else spec.review_requirement_for(owner.id)
                if isinstance(review, WaivedReview):
                    unlinked += 1
                else:
                    with_review += 1

    return {
        "total": len(spec.criteria),
        "with_check_or_manual": with_check_or_manual,
        "with_review": with_review,
        "unlinked": unlinked,
    }


def _max_graph_width(graph: ExecutionGraph) -> int:
    if not graph.tasks:
        return 0
    prereqs: dict[str, list[str]] = {task.task_key: [] for task in graph.tasks}
    for edge in graph.edges:
        if edge.prerequisite in prereqs and edge.dependent in prereqs:
            prereqs[edge.dependent].append(edge.prerequisite)

    levels: dict[str, int] = {}

    def level_of(task_key: str, visiting: set[str]) -> int:
        if task_key in levels:
            return levels[task_key]
        if task_key in visiting:
            return 0
        visiting.add(task_key)
        preds = prereqs.get(task_key, [])
        lvl = 0 if not preds else 1 + max(level_of(p, visiting) for p in preds)
        visiting.remove(task_key)
        levels[task_key] = lvl
        return lvl

    layer_counts: dict[int, int] = {}
    for task in graph.tasks:
        lvl = level_of(task.task_key, set())
        layer_counts[lvl] = layer_counts.get(lvl, 0) + 1
    return max(layer_counts.values(), default=0)


def compute_stats(spec: Specification, graph: ExecutionGraph) -> PlanStats:
    """Compute aggregated statistics for ``spec`` and its compiled ``graph`` (planning §5.9)."""
    checks_counts: _Breakdown = MappingProxyType(
        {
            "by_kind": MappingProxyType(
                {k.value: sum(1 for c in spec.checks if c.kind is k) for k in CheckKind}
            ),
            "by_category": MappingProxyType(
                {cat.value: sum(1 for c in spec.checks if c.category is cat) for cat in CheckCategory}
            ),
        }
    )
    decisions_counts: _Breakdown = MappingProxyType(
        {
            "by_state": MappingProxyType(
                {s.value: sum(1 for d in spec.decisions if d.state is s) for s in DecisionState}
            ),
        }
    )
    materials_counts: _Breakdown = MappingProxyType(
        {
            "by_kind": MappingProxyType(
                {k.value: sum(1 for m in spec.materials if m.kind is k) for k in MaterialKind}
            ),
        }
    )
    counts: dict[str, int | _Breakdown] = {
        "phases": len(spec.phases),
        "items": len(spec.items),
        "units": len(spec.units),
        "requirements": len(spec.requirements),
        "criteria": len(spec.criteria),
        "checks": checks_counts,
        "decisions": decisions_counts,
        "materials": materials_counts,
    }

    items_per_phase: dict[str, int] = {phase.key: 0 for phase in spec.phases}
    for item in spec.items:
        items_per_phase[item.phase] = items_per_phase.get(item.phase, 0) + 1

    units_per_item: dict[str, int] = {item.key: 0 for item in spec.items}
    for unit in spec.units:
        item_key = unit.key.split("/", 1)[0]
        units_per_item[item_key] = units_per_item.get(item_key, 0) + 1

    implemented = {key for entity in (*spec.items, *spec.units) for key in entity.implements}
    implemented.update(key for criterion in spec.criteria for key in criterion.requirements)
    must_reqs = [req for req in spec.requirements if req.priority is Priority.MUST]
    requirements_coverage = {
        "must_total": len(must_reqs),
        "must_implemented": sum(1 for req in must_reqs if bool(req.owners) or req.key in implemented),
    }

    write_scope = {
        "units_with_scope": sum(1 for unit in spec.units if bool(unit.write_scope)),
        "items_without_hints": sum(1 for item in spec.items if not item.change_hints),
    }

    graph_stats = {
        "tasks": len(graph.tasks),
        "edges": len(graph.edges),
        "max_width": _max_graph_width(graph),
    }

    skeleton_phases = tuple(phase.key for phase in spec.phases if phase.design_state is DesignState.SKELETON)

    materials_required = {
        "execution": sum(1 for m in spec.materials if MaterialStage.EXECUTION in m.required_for),
        "review": sum(1 for m in spec.materials if MaterialStage.REVIEW in m.required_for),
        "acceptance": sum(1 for m in spec.materials if MaterialStage.ACCEPTANCE in m.required_for),
    }

    return PlanStats(
        counts=MappingProxyType(counts),
        items_per_phase=MappingProxyType(items_per_phase),
        units_per_item=MappingProxyType(units_per_item),
        criteria_coverage=MappingProxyType(_criteria_coverage(spec)),
        requirements_coverage=MappingProxyType(requirements_coverage),
        write_scope=MappingProxyType(write_scope),
        graph=MappingProxyType(graph_stats),
        skeleton_phases=skeleton_phases,
        materials_required=MappingProxyType(materials_required),
    )
