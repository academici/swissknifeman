"""Build a read-only simulation from the pinned plan source and current model catalog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.source_reader import read_source
from skm.modules.planning.domain.compile_graph import TaskKind, compile_execution_graph
from skm.modules.planning.domain.simulation import ModelMetrics, estimate_simulation
from skm.modules.planning.generated.queries import Simulate
from skm.modules.planning.generated.views import SimulationView
from skm.modules.runtimes.public import catalog

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC"]


def scope_of(query: Simulate) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: Simulate, ctx: QueryContext, uow: UnitOfWork) -> SimulationView:
    source = read_source(
        uow,
        plan_id=query.plan_id,
        revision_id=query.revision_id,
        draft_id=query.draft_id,
        expected_edit_version=query.expected_edit_version,
    )
    graph = compile_execution_graph(source.spec)
    selectors = {
        (route.runtime, route.model)
        for task in graph.tasks
        if task.task_kind in {TaskKind.ITEM, TaskKind.UNIT}
        and (route := task.route) is not None
        and route.runtime is not None
        and route.model is not None
    }
    metrics: dict[tuple[str, str], ModelMetrics] = {}
    if selectors:
        models = catalog(uow, config=ctx.config)
        for runtime_id, model_id in sorted(selectors):
            model = models.model(runtime_id, model_id)
            if model is not None:
                pricing = model.pricing
                metrics[runtime_id, model_id] = ModelMetrics(
                    model.context_window_tokens,
                    model.max_output_tokens,
                    None if pricing is None else pricing.input_per_mtok_usd,
                    None if pricing is None else pricing.output_per_mtok_usd,
                )
    result = estimate_simulation(graph, metrics, query.tokens_per_second)
    return SimulationView.from_json(
        {
            "basis": "heuristic",
            "source": source.source_view_json(),
            "task_count": result.task_count,
            "tokens": None if result.tokens is None else result.tokens._asdict(),
            "cost_usd_micros": None if result.cost_usd_micros is None else result.cost_usd_micros._asdict(),
            "duration_seconds": None
            if result.duration_seconds is None
            else result.duration_seconds._asdict(),
            "tokens_per_second": query.tokens_per_second,
        }
    )


SPEC = QuerySpec(
    name="planning.simulate",
    dto=Simulate,
    result=SimulationView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
