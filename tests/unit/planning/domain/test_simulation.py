"""Heuristic estimates keep missing inputs distinct from measured zero prices."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from skm.modules.planning.domain.compile_graph import TaskKind, compile_execution_graph
from skm.modules.planning.domain.simulation import (
    EstimateRange,
    ModelMetrics,
    Simulation,
    estimate_simulation,
)
from skm.platform.schema.registry import SchemaRegistry

from .test_ready_preview import _plan, _spec

if TYPE_CHECKING:
    from skm.modules.planning.domain.compile_graph import ExecutionGraph

_CODEX = ("codex_cli", "example")
_MODEL = ModelMetrics(32000, 4096, Decimal("1.50"), Decimal("2.50"))
_ROUTE = {"class": "implementation", "effort": "low", "runtime": _CODEX[0], "model": _CODEX[1]}


@pytest.fixture
def graph() -> ExecutionGraph:
    doc = _plan(
        [{"key": "P1"}],
        [{"key": "P1.1", "route": _ROUTE}, {"key": "P1.2", "route": {**_ROUTE, "effort": "medium"}}],
    )
    return compile_execution_graph(_spec(doc, SchemaRegistry.load_default()))


def test_simulation_scales_effort_and_excludes_gates(graph: ExecutionGraph) -> None:
    assert any(task.task_kind is TaskKind.PHASE_GATE for task in graph.tasks)
    assert estimate_simulation(graph, {_CODEX: _MODEL}, 100) == Simulation(
        task_count=2,
        tokens=EstimateRange(3840, 15360),
        cost_usd_micros=EstimateRange(6528, 26112),
        duration_seconds=EstimateRange(38, 154),
    )


def test_simulation_uses_limits_and_rounds_outward(graph: ExecutionGraph) -> None:
    metrics = replace(_MODEL, context_window=1000, max_output=3, input_usd_per_million=Decimal("0.0005"))
    assert estimate_simulation(graph, {_CODEX: metrics}, 100) == Simulation(
        task_count=2,
        tokens=EstimateRange(1006, 1006),
        cost_usd_micros=EstimateRange(15, 16),
        duration_seconds=EstimateRange(10, 11),
    )


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (None, Simulation(2, None, None, None)),
        (replace(_MODEL, max_output=None), Simulation(2, None, None, None)),
        (
            replace(_MODEL, input_usd_per_million=None),
            Simulation(2, EstimateRange(3840, 15360), None, EstimateRange(38, 154)),
        ),
        (
            replace(_MODEL, output_usd_per_million=None),
            Simulation(2, EstimateRange(3840, 15360), None, EstimateRange(38, 154)),
        ),
        (
            replace(_MODEL, input_usd_per_million=Decimal(0), output_usd_per_million=Decimal(0)),
            Simulation(2, EstimateRange(3840, 15360), EstimateRange(0, 0), EstimateRange(38, 154)),
        ),
    ],
)
def test_simulation_preserves_independent_unknowns(
    graph: ExecutionGraph, model: ModelMetrics | None, expected: Simulation
) -> None:
    assert estimate_simulation(graph, {} if model is None else {_CODEX: model}, 100) == expected


def test_one_unknown_task_invalidates_the_total(graph: ExecutionGraph) -> None:
    tasks = tuple(replace(task, route=None) if task.task_key == "P1.2" else task for task in graph.tasks)
    assert estimate_simulation(replace(graph, tasks=tasks), {_CODEX: _MODEL}, None) == Simulation(
        2, None, None, None
    )


def test_duration_is_unknown_without_throughput_unless_empty(graph: ExecutionGraph) -> None:
    assert estimate_simulation(graph, {_CODEX: _MODEL}, None).duration_seconds is None
    assert estimate_simulation(replace(graph, tasks=()), {}, None) == Simulation(
        0, EstimateRange(0, 0), EstimateRange(0, 0), EstimateRange(0, 0)
    )
