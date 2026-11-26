"""``planning.plan_stats`` (planning §5.9, §8): counts, coverage, write scope, and graph metrics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import read_source
from skm.modules.planning.domain.compile_graph import compile_execution_graph
from skm.modules.planning.domain.stats import compute_stats
from skm.modules.planning.generated.queries import PlanStats
from skm.modules.planning.generated.views import PlanStatsView

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]


def scope_of(query: PlanStats) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: PlanStats, _ctx: QueryContext, uow: UnitOfWork) -> PlanStatsView:
    source = read_source(
        uow,
        plan_id=query.plan_id,
        revision_id=query.revision_id,
        draft_id=query.draft_id,
        expected_edit_version=query.expected_edit_version,
    )
    graph = compile_execution_graph(source.spec)
    stats = compute_stats(source.spec, graph)
    counts_json: JsonObject = {
        k: {bk: dict(bv) for bk, bv in v.items()} if isinstance(v, Mapping) else v
        for k, v in stats.counts.items()
    }
    payload = {
        "counts": counts_json,
        "items_per_phase": dict(stats.items_per_phase),
        "units_per_item": dict(stats.units_per_item),
        "criteria_coverage": dict(stats.criteria_coverage),
        "requirements_coverage": dict(stats.requirements_coverage),
        "write_scope": dict(stats.write_scope),
        "graph": dict(stats.graph),
        "skeleton_phases": list(stats.skeleton_phases),
        "materials_required": dict(stats.materials_required),
        "source": source.source_view_json(),
    }
    return PlanStatsView.from_json(payload)


SPEC = QuerySpec(
    name="planning.plan_stats",
    dto=PlanStats,
    result=PlanStatsView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
