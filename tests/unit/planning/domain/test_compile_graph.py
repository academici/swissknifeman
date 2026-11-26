"""Execution graph v1: golden graph, edge rules, ownership, work-policy facts, cycles and reachability."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.planning.domain.compile_graph import (
    COMPILER_VERSION,
    EdgeReason,
    ExecutionGraph,
    TaskKind,
    TaskNode,
    compile_execution_graph,
)
from skm.modules.planning.domain.execution_constraints import PathRule
from skm.modules.planning.domain.item import (
    AuthorityKind,
    Intensity,
    RoleName,
    WorkPolicyOverride,
    route_to_doc,
    work_policy_to_doc,
)
from skm.modules.planning.domain.review_requirement import ReviewMode
from skm.modules.planning.domain.specification import EntityKind, Specification, from_document, to_document
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES = ROOT / "tests/fixtures/corpus/examples/plans"
SPECIFICATION = "urn:skm:planning:specification:v1"
REVISION = "0192f5c5-0000-7000-8000-000000000101"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _example() -> dict[str, Any]:
    return json.loads((EXAMPLES / "auth-refresh.specification.json").read_text())


def _spec(doc: dict[str, Any], registry: SchemaRegistry | None = None) -> Specification:
    if registry is not None:
        registry.require_valid(SPECIFICATION, doc)
    spec, findings = from_document(doc)
    assert findings == ()
    return spec


def _plan(
    phases: list[dict[str, Any]],
    items: list[dict[str, Any]],
    units: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """A minimal schema-valid document; entities get sequential ids in document order."""
    counter = iter(range(1, 10_000))

    def with_id(entity: dict[str, Any]) -> dict[str, Any]:
        return {"id": f"0192f5c4-0000-7000-8000-{next(counter):012x}", **entity}

    return {
        "schema": SPECIFICATION,
        "title": "Synthetic plan",
        "goal": "Exercise the compiler.",
        "phases": [
            with_id({"title": p["key"], "goal": "g", "design_state": "detailed", **p}) for p in phases
        ],
        "items": [
            with_id(
                {
                    "phase": i["key"].split(".")[0],
                    "title": i["key"],
                    "summary": "s",
                    "why": "w",
                    "review": {"mode": "self", "reason": "synthetic"},
                    **i,
                }
            )
            for i in items
        ],
        **({"units": [with_id({"title": u["key"], "goal": "g", **u}) for u in units]} if units else {}),
        **extra,
    }


def _edges(graph: ExecutionGraph) -> dict[tuple[str, str], set[str]]:
    return {(e.dependent, e.prerequisite): {r.value for r in e.reasons} for e in graph.edges}


def _task(graph: ExecutionGraph, key: str) -> TaskNode:
    return next(task for task in graph.tasks if task.task_key == key)


def _golden_view(graph: ExecutionGraph) -> dict[str, Any]:
    """The shape of ``examples/plans/compiled-graph.json`` (task materials are asserted separately)."""

    def task(node: TaskNode) -> dict[str, Any]:
        return {
            "task_key": node.task_key,
            "task_kind": node.task_kind.value,
            "entity_id": str(node.entity_id),
            "entity_kind": node.entity_kind.value,
            "phase": node.phase_key,
            "item": node.item_key,
            "checks": [{"check_key": c.check_key, "check_id": str(c.check_id)} for c in node.checks],
            "review": None if node.review is None else node.review.value,
            "criteria": list(node.criteria),
            "route": None if node.route is None else route_to_doc(node.route),
            "write_scope": None
            if node.write_scope is None
            else [{"mount": r.mount, "pattern": r.pattern} for r in node.write_scope],
            "authority": node.authority.value,
            "item_work_policy": None
            if node.item_work_policy is None
            else work_policy_to_doc(node.item_work_policy),
            "unit_work_policy": None
            if node.unit_work_policy is None
            else work_policy_to_doc(node.unit_work_policy),
        }

    return {
        "compiler_version": graph.compiler_version,
        "revision_id": None if graph.revision_id is None else str(graph.revision_id),
        "tasks": [task(node) for node in graph.tasks],
        "edges": [
            {
                "dependent": e.dependent,
                "prerequisite": e.prerequisite,
                "reasons": sorted(r.value for r in e.reasons),
            }
            for e in graph.edges
        ],
        "batch_groups": [
            {"phase": g.phase_key, "batch": g.batch_key, "mode": g.mode.value, "tasks": list(g.tasks)}
            for g in graph.batch_groups
        ],
        "topological_order": list(graph.topological_order),
    }


# ---------------------------------------------------------------- golden


def test_golden_graph_matches_the_example(registry):
    graph = compile_execution_graph(_spec(_example(), registry), REVISION)  # type: ignore[arg-type]
    golden = json.loads((EXAMPLES / "compiled-graph.json").read_text())
    assert COMPILER_VERSION == 1
    assert (len(graph.tasks), len(graph.edges)) == (13, 20)
    assert _golden_view(graph) == golden


def test_draft_graph_has_no_revision_and_compiles_deterministically(registry):
    spec = _spec(_example(), registry)
    first = compile_execution_graph(spec)
    assert first.revision_id is None
    assert first == compile_execution_graph(spec)
    assert first == compile_execution_graph(_spec(_example()))


def test_task_materials_follow_global_and_applies_to(registry):
    graph = compile_execution_graph(_spec(_example(), registry))
    storage, auth, threats = (
        "0192f5c4-0000-7000-8000-000000000046",
        "0192f5c4-0000-7000-8000-000000000047",
        "0192f5c4-0000-7000-8000-000000000048",
    )
    by_task = {task.task_key: [str(m) for m in task.materials] for task in graph.tasks}
    assert by_task["P1.1/U1"] == [storage, auth]
    assert by_task["P1#gate"] == [storage, auth]
    assert by_task["P2.1/U1"] == [auth]
    assert by_task["P2.3"] == [auth, threats]
    assert by_task["P2#gate"] == [auth]


# ---------------------------------------------------------------- tasks and ownership


def test_item_without_units_is_one_task_and_unknown_footprint_is_none(registry):
    doc = _plan([{"key": "P1"}], [{"key": "P1.1"}, {"key": "P1.2", "change_hints": []}])
    graph = compile_execution_graph(_spec(doc, registry))
    assert [t.task_key for t in graph.tasks] == ["P1.1", "P1.2", "P1#gate"]
    item = _task(graph, "P1.1")
    assert (item.task_kind, item.entity_kind, item.item_key) == (TaskKind.ITEM, EntityKind.ITEM, "P1.1")
    assert item.write_scope is None
    gate = _task(graph, "P1#gate")
    assert (gate.task_kind, gate.entity_kind, gate.item_key, gate.write_scope) == (
        TaskKind.PHASE_GATE,
        EntityKind.PHASE,
        None,
        (),
    )


def test_unit_without_write_scope_is_unknown_not_empty(registry):
    doc = _plan(
        [{"key": "P1"}],
        [{"key": "P1.1", "change_hints": [{"mount": "repo", "pattern": "src/a.py", "change": "modify"}]}],
        [{"key": "P1.1/U1"}, {"key": "P1.1/U2", "write_scope": [{"mount": "repo", "pattern": "src/a.py"}]}],
    )
    graph = compile_execution_graph(_spec(doc, registry))
    assert _task(graph, "P1.1/U1").write_scope is None
    assert _task(graph, "P1.1/U2").write_scope == (PathRule("repo", "src/a.py"),)
    assert _task(graph, "P1.1#gate").write_scope == ()


def test_checks_criteria_and_review_bind_to_their_owning_task(registry):
    doc = _plan(
        [{"key": "P1"}],
        [
            {"key": "P1.1", "review": {"mode": "required"}},
            {"key": "P1.2", "review": {"mode": "waived", "reason": "r", "waived_by": "owner"}},
        ],
        [{"key": "P1.1/U1", "checks": ["V2"]}, {"key": "P1.1/U2"}],
        checks=[
            {"key": key, "owner": owner, "category": "acceptance", "kind": "manual", "required": True,
             "definition": {"instructions_md": "look", "actor_role": "owner"}}
            for owner, key in (("P1.1", "V1"), ("P1.1", "V2"), ("P1.1", "V3"), ("P1.2", "V1"), ("P1", "V1"))
        ],
        criteria=[
            {"key": "AC1", "owner": "P1.1/U1", "statement": "s", "verification_mode": "review"},
            {"key": "AC2", "owner": "P1.1", "statement": "s", "verification_mode": "review"},
            {"key": "AC3", "owner": "P1.2", "statement": "s", "verification_mode": "review"},
        ],
    )  # fmt: skip
    for n, entity in enumerate([*doc["checks"], *doc["criteria"]]):
        entity["id"] = f"0192f5c4-0000-7000-8000-{0x100 + n:012x}"
    graph = compile_execution_graph(_spec(doc, registry))
    checks = {task.task_key: [c.check_key for c in task.checks] for task in graph.tasks}
    assert checks == {
        "P1.1/U1": ["P1.1:V2"],
        "P1.1/U2": [],
        "P1.1#gate": ["P1.1:V1", "P1.1:V3"],
        "P1.2": ["P1.2:V1"],
        "P1#gate": ["P1:V1"],
    }
    criteria = {task.task_key: list(task.criteria) for task in graph.tasks}
    assert criteria == {
        "P1.1/U1": ["AC1"],
        "P1.1/U2": [],
        "P1.1#gate": ["AC2"],
        "P1.2": ["AC3"],
        "P1#gate": [],
    }
    reviews = {task.task_key: task.review for task in graph.tasks}
    assert reviews == {
        "P1.1/U1": None,
        "P1.1/U2": None,
        "P1.1#gate": ReviewMode.REQUIRED,
        "P1.2": ReviewMode.WAIVED,
        "P1#gate": None,
    }


def test_route_and_authority_come_from_unit_then_item(registry):
    doc = _plan(
        [{"key": "P1"}],
        [
            {
                "key": "P1.1",
                "route": {"class": "economy", "effort": "low"},
                "authority": {"kind": "external_gate", "label": "vendor", "scope": "s"},
            }
        ],
        [{"key": "P1.1/U1", "route": {"class": "frontier", "effort": "max"}}, {"key": "P1.1/U2"}],
    )
    graph = compile_execution_graph(_spec(doc, registry))
    routes = {t.task_key: None if t.route is None else route_to_doc(t.route) for t in graph.tasks}
    assert routes == {
        "P1.1/U1": {"class": "frontier", "effort": "max"},
        "P1.1/U2": {"class": "economy", "effort": "low"},
        "P1.1#gate": None,
        "P1#gate": None,
    }
    authority = {t.task_key: t.authority for t in graph.tasks}
    assert authority == {
        "P1.1/U1": AuthorityKind.EXTERNAL_GATE,
        "P1.1/U2": AuthorityKind.EXTERNAL_GATE,
        "P1.1#gate": AuthorityKind.EXTERNAL_GATE,
        "P1#gate": AuthorityKind.ROUTINE,
    }


# ---------------------------------------------------------------- work policy facts


def test_work_policy_facts_are_raw_and_scoped_to_their_source(registry):
    item_policy = {"role_intensity": {"executor": "heavy"}}
    doc = _plan(
        [{"key": "P1"}],
        [{"key": "P1.1", "work_policy": item_policy}, {"key": "P1.2", "work_policy": {}}, {"key": "P1.3"}],
        [
            {"key": "P1.1/U1", "work_policy": {"verification_intensity": "light"}},
            {"key": "P1.1/U2", "parent": "U1"},
        ],
    )
    spec = _spec(doc, registry)
    before = copy.deepcopy(to_document(spec))
    graph = compile_execution_graph(spec)
    executor_heavy = WorkPolicyOverride({RoleName.EXECUTOR: Intensity.HEAVY})
    unit = _task(graph, "P1.1/U1")
    assert unit.item_work_policy == executor_heavy  # unit inherits its item: the raw item fact travels along
    assert unit.unit_work_policy == WorkPolicyOverride(None, Intensity.LIGHT)
    assert unit.entity_id == spec.by_key("P1.1/U1").id
    child = _task(graph, "P1.1/U2")
    assert child.item_work_policy == executor_heavy
    assert child.unit_work_policy is None  # a parent unit is not a settings layer
    gate = _task(graph, "P1.1#gate")
    assert (gate.item_work_policy, gate.unit_work_policy) == (executor_heavy, None)
    assert gate.entity_id == spec.by_key("P1.1").id
    assert _task(graph, "P1.2").item_work_policy == WorkPolicyOverride()  # explicit {} stays {}, not defaults
    assert _task(graph, "P1.3").item_work_policy is None
    phase_gate = _task(graph, "P1#gate")
    assert (phase_gate.item_work_policy, phase_gate.unit_work_policy) == (None, None)  # settings only
    assert to_document(spec) == before


# ---------------------------------------------------------------- edges


def test_unit_parent_and_sequential_siblings(registry):
    doc = _plan(
        [{"key": "P1"}],
        [{"key": "P1.1", "unit_strategy": "sequential"}],
        [
            {"key": "P1.1/U1"},
            {"key": "P1.1/U2", "parent": "U1"},
            {"key": "P1.1/U3", "parent": "P1.1/U1"},
            {"key": "P1.1/U4"},
        ],
    )
    edges = _edges(compile_execution_graph(_spec(doc, registry)))
    assert edges[("P1.1/U1", "P1.1/U2")] == {"unit_parent"}
    assert edges[("P1.1/U1", "P1.1/U3")] == {"unit_parent"}
    assert edges[("P1.1/U3", "P1.1/U2")] == {"unit_sequential"}  # siblings under U1
    assert edges[("P1.1/U4", "P1.1/U1")] == {"unit_sequential"}  # top-level siblings
    assert ("P1.1/U2", "P1.1/U1") not in edges
    assert {k for k, v in edges.items() if v == {"item_member"}} == {
        ("P1.1#gate", f"P1.1/U{n}") for n in range(1, 5)
    }


def test_item_dependency_links_entries_to_the_prerequisite_sink(registry):
    doc = _plan(
        [{"key": "P1"}],
        [{"key": "P1.1"}, {"key": "P1.2", "depends_on": ["P1.1"]}],
        [
            {"key": "P1.1/U1"},
            {"key": "P1.2/U1"},
            {"key": "P1.2/U2", "depends_on": ["U1"]},
            {"key": "P1.2/U3"},
        ],
    )
    edges = _edges(compile_execution_graph(_spec(doc, registry)))
    dependent = {k for k, v in edges.items() if "item_depends_on" in v}
    assert dependent == {("P1.2/U1", "P1.1#gate"), ("P1.2/U3", "P1.1#gate")}


def test_phase_dependencies_default_to_the_previous_phase(registry):
    doc = _plan(
        [
            {"key": "P1"},
            {"key": "P2"},
            {"key": "P3", "depends_on": []},
            {"key": "P4", "depends_on": ["P1", "P2"]},
        ],
        [{"key": "P1.1"}, {"key": "P2.1"}, {"key": "P3.1"}],
    )
    edges = _edges(compile_execution_graph(_spec(doc, registry)))
    phase = {k for k, v in edges.items() if v == {"phase_depends_on"}}
    assert phase == {("P2.1", "P1#gate"), ("P4#gate", "P1#gate"), ("P4#gate", "P2#gate")}
    assert edges[("P3#gate", "P3.1")] == {"phase_member"}


def test_sequential_phase_and_sequential_plan_chain_items(registry):
    items = [{"key": "P1.1"}, {"key": "P1.2"}, {"key": "P2.1"}, {"key": "P2.2"}]
    phased = _plan([{"key": "P1", "strategy": "sequential"}, {"key": "P2", "depends_on": []}], items)
    edges = _edges(compile_execution_graph(_spec(phased, registry)))
    assert {k for k, v in edges.items() if "phase_sequential" in v} == {("P1.2", "P1.1")}
    planned = _plan(
        [{"key": "P1"}, {"key": "P2", "depends_on": []}],
        items,
        execution_constraints={"strategy": "sequential"},
    )
    edges = _edges(compile_execution_graph(_spec(planned, registry)))
    assert {k for k, v in edges.items() if "plan_sequential" in v} == {
        ("P1.2", "P1.1"),
        ("P2.1", "P1.2"),
        ("P2.2", "P2.1"),
    }


def test_batch_barrier_orders_adjacent_batches_only(registry):
    doc = _plan(
        [
            {
                "key": "P1",
                "batches": [
                    {"key": "B1", "items": ["P1.1"], "mode": "recommended"},
                    {"key": "B2", "items": ["P1.2", "P1.3"], "mode": "required"},
                    {"key": "B3", "items": ["P1.4"], "mode": "recommended"},
                ],
            }
        ],
        [{"key": f"P1.{n}"} for n in range(1, 5)],
        [{"key": "P1.3/U1"}, {"key": "P1.3/U2", "depends_on": ["U1"]}],
    )
    graph = compile_execution_graph(_spec(doc, registry))
    batch = {k for k, v in _edges(graph).items() if "batch_order" in v}
    assert batch == {("P1.2", "P1.1"), ("P1.3/U1", "P1.1"), ("P1.4", "P1.2"), ("P1.4", "P1.3#gate")}
    assert [(g.batch_key, g.mode.value, g.tasks) for g in graph.batch_groups] == [
        ("B1", "recommended", ("P1.1",)),
        ("B2", "required", ("P1.2", "P1.3/U1", "P1.3/U2", "P1.3#gate")),
        ("B3", "recommended", ("P1.4",)),
    ]


def test_merged_reasons_and_edge_order_follow_order_key(registry):
    graph = compile_execution_graph(_spec(_example(), registry))
    edge = next(e for e in graph.edges if (e.dependent, e.prerequisite) == ("P2.3", "P2.1#gate"))
    assert edge.reasons == frozenset({EdgeReason.BATCH_ORDER, EdgeReason.ITEM_DEPENDS_ON})
    position = {t.task_key: n for n, t in enumerate(graph.tasks)}
    keys = [(position[e.dependent], position[e.prerequisite]) for e in graph.edges]
    assert keys == sorted(keys)


def test_natural_order_puts_p1_10_after_p1_9(registry):
    doc = _plan([{"key": "P1"}], [{"key": "P1.9"}, {"key": "P1.10"}])
    graph = compile_execution_graph(_spec(doc, registry))
    assert [t.task_key for t in graph.tasks] == ["P1.9", "P1.10", "P1#gate"]  # document order is the order


# ---------------------------------------------------------------- cycles


def test_cycle_through_a_phase_gate_reports_its_path(registry):
    doc = json.loads((EXAMPLES / "invalid/dependency_cycle--through-phase.json").read_text())
    registry.require_valid(SPECIFICATION, doc)
    with pytest.raises(ValidationFailed) as caught:
        compile_execution_graph(from_document(doc)[0])
    assert caught.value.code is ErrorCode.DEPENDENCY_CYCLE
    assert caught.value.details["cycle"] == [
        "P1.1/U1",
        "P1.1/U2",
        "P1.1#gate",
        "P1.2",
        "P1#gate",
        "P2.1/U1",
        "P2.1/U2",
        "P2.1#gate",
        "P1.1/U1",
    ]


def test_cycle_between_items_is_found(registry):
    doc = json.loads((EXAMPLES / "invalid/dependency_cycle--items.json").read_text())
    registry.require_valid(SPECIFICATION, doc)
    with pytest.raises(ValidationFailed) as caught:
        compile_execution_graph(from_document(doc)[0])
    cycle = caught.value.details["cycle"]
    assert isinstance(cycle, list)
    assert cycle[0] == cycle[-1] == "P1.1/U1"
    assert {"P1.1#gate", "P1.2"} <= set(cycle)


def test_self_dependency_is_a_cycle(registry):
    doc = _plan([{"key": "P1"}], [{"key": "P1.1", "depends_on": ["P1.1"]}])
    with pytest.raises(ValidationFailed) as caught:
        compile_execution_graph(_spec(doc))
    assert caught.value.details["cycle"] == ["P1.1", "P1.1"]


def test_unknown_references_are_left_to_validation(registry):
    doc = _plan(
        [{"key": "P1", "depends_on": ["P9"]}],
        [{"key": "P1.1", "depends_on": ["P1.7"]}],
        [{"key": "P1.1/U1", "depends_on": ["U5"], "checks": ["V9"]}],
    )
    graph = compile_execution_graph(_spec(doc))
    assert _edges(graph) == {
        ("P1.1#gate", "P1.1/U1"): {"item_member"},
        ("P1#gate", "P1.1#gate"): {"phase_member"},
    }
    assert _task(graph, "P1.1/U1").checks == ()


def test_references_to_units_of_an_uncompiled_item_are_skipped(registry):
    doc = _plan(
        [{"key": "P1"}],
        [{"key": "P1.1"}],
        [
            {"key": "P1.1/U1", "depends_on": ["P1.9/U1"]},
            {"key": "P1.1/U2", "parent": "P1.9/U2"},
            {"key": "P1.9/U1"},
            {"key": "P1.9/U2"},
        ],
    )
    spec = _spec(doc, registry)
    before = copy.deepcopy(to_document(spec))
    graph = compile_execution_graph(spec)
    tasks = {task.task_key for task in graph.tasks}
    assert tasks == {"P1.1/U1", "P1.1/U2", "P1.1#gate", "P1#gate"}
    assert all({edge.dependent, edge.prerequisite} <= tasks for edge in graph.edges)
    assert _edges(graph) == {
        ("P1.1#gate", "P1.1/U1"): {"item_member"},
        ("P1.1#gate", "P1.1/U2"): {"item_member"},
        ("P1#gate", "P1.1#gate"): {"phase_member"},
    }
    assert to_document(spec) == before  # the orphan units stay in the specification for validation


# ---------------------------------------------------------------- reachability property


@st.composite
def _acyclic_plans(draw: st.DrawFn) -> tuple[dict[str, Any], dict[str, set[str]]]:
    """One phase of items whose dependencies follow a random topological order, each with 0..3 units."""
    count = draw(st.integers(1, 7))
    rank = draw(st.permutations(list(range(count))))
    items: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    deps: dict[str, set[str]] = {}
    for n in range(count):
        key = f"P1.{n + 1}"
        earlier = [f"P1.{m + 1}" for m in range(count) if rank[m] < rank[n]]
        chosen = draw(st.lists(st.sampled_from(earlier), unique=True)) if earlier else []
        deps[key] = set(chosen)
        items.append({"key": key, **({"depends_on": chosen} if chosen else {})})
        for u in range(draw(st.integers(0, 3))):
            local = [f"U{v + 1}" for v in range(u)]
            unit_deps = draw(st.lists(st.sampled_from(local), unique=True)) if local else []
            units.append({"key": f"{key}/U{u + 1}", **({"depends_on": unit_deps} if unit_deps else {})})
    return _plan([{"key": "P1"}], items, units), deps


def _closure(deps: dict[str, set[str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}

    def visit(key: str) -> set[str]:
        if key not in out:
            out[key] = set()
            for dep in deps[key]:
                out[key] |= {dep, *visit(dep)}
        return out[key]

    for key in deps:
        visit(key)
    return out


def _ancestors(graph: ExecutionGraph) -> dict[str, set[str]]:
    prerequisites: dict[str, set[str]] = {t.task_key: set() for t in graph.tasks}
    for edge in graph.edges:
        prerequisites[edge.dependent].add(edge.prerequisite)
    out: dict[str, set[str]] = {}
    for key in graph.topological_order:
        out[key] = set().union(*({p, *out[p]} for p in prerequisites[key]))
    return out


@given(_acyclic_plans())
def test_acyclic_plans_compile_to_acyclic_graphs_with_the_same_reachability(plan):
    doc, deps = plan
    spec = _spec(doc)
    graph = compile_execution_graph(spec)
    order = graph.topological_order
    assert sorted(order) == sorted(t.task_key for t in graph.tasks)
    position = {key: n for n, key in enumerate(order)}
    assert all(position[e.prerequisite] < position[e.dependent] for e in graph.edges)
    sinks = {item.key: f"{item.key}#gate" if spec.units_of(item.key) else item.key for item in spec.items}
    ancestors = _ancestors(graph)
    expected = _closure(deps)
    for item, sink in sinks.items():
        reached = {other for other, other_sink in sinks.items() if other_sink in ancestors[sink]}
        assert reached == expected[item]
        item_tasks = {t.task_key for t in graph.tasks if t.item_key == item}
        assert item_tasks - {sink} <= ancestors[sink]  # the sink waits for every task of its item
