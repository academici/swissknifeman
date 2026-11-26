"""Heuristic ranges for one uncached implementation call per compiled work task."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import TYPE_CHECKING, NamedTuple

from skm.modules.planning.domain.compile_graph import TaskKind
from skm.modules.planning.domain.item import Effort

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.modules.planning.domain.compile_graph import ExecutionGraph

__all__ = ["EstimateRange", "ModelMetrics", "Simulation", "estimate_simulation"]

_EFFORT_SCALE = {Effort.LOW: 1, Effort.MEDIUM: 2, Effort.HIGH: 3, Effort.XHIGH: 4, Effort.MAX: 5}


class EstimateRange(NamedTuple):
    min: int
    max: int


@dataclass(frozen=True, slots=True)
class ModelMetrics:
    context_window: int
    max_output: int | None
    input_usd_per_million: Decimal | None
    output_usd_per_million: Decimal | None


@dataclass(frozen=True, slots=True)
class Simulation:
    task_count: int
    tokens: EstimateRange | None
    cost_usd_micros: EstimateRange | None
    duration_seconds: EstimateRange | None


def estimate_simulation(
    graph: ExecutionGraph,
    metrics: Mapping[tuple[str, str], ModelMetrics],
    tokens_per_second: int | None,
) -> Simulation:
    """Sum work across items and units, excluding synthetic gates and scheduling delays."""
    tasks = [task for task in graph.tasks if task.task_kind in {TaskKind.ITEM, TaskKind.UNIT}]
    token_min = token_max = 0
    cost_min = cost_max = Decimal(0)
    priced = True
    for task in tasks:
        route = task.route
        model = (
            metrics.get((route.runtime, route.model))
            if route is not None and route.runtime is not None and route.model is not None
            else None
        )
        if route is None or model is None or model.max_output is None:
            return Simulation(len(tasks), None, None, None)

        # At low effort, allow 1-4k input and 256-1k output. Scale by effort,
        # using half the context for each side at most.
        scale = _EFFORT_SCALE[route.effort]
        input_max = min(4096 * scale, model.context_window // 2)
        output_max = min(1024 * scale, model.max_output, model.context_window // 2)
        input_min, output_min = min(1024 * scale, input_max), min(256 * scale, output_max)
        token_min += input_min + output_min
        token_max += input_max + output_max
        if model.input_usd_per_million is None or model.output_usd_per_million is None:
            priced = False
        else:
            cost_min += input_min * model.input_usd_per_million + output_min * model.output_usd_per_million
            cost_max += input_max * model.input_usd_per_million + output_max * model.output_usd_per_million

    duration = None
    if tokens_per_second is not None:
        duration = EstimateRange(
            token_min // tokens_per_second,
            (token_max + tokens_per_second - 1) // tokens_per_second,
        )
    elif not tasks:
        duration = EstimateRange(0, 0)
    return Simulation(
        len(tasks),
        EstimateRange(token_min, token_max),
        EstimateRange(
            int(cost_min.to_integral_value(rounding=ROUND_FLOOR)),
            int(cost_max.to_integral_value(rounding=ROUND_CEILING)),
        )
        if priced
        else None,
        duration,
    )
