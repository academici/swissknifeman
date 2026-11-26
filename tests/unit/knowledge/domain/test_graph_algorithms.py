"""Pure multigraph and graph answer rules."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.kernel.ids import RepositoryId, WorkspaceId
from skm.modules.knowledge.domain.contracts import GraphQueryEcho
from skm.modules.knowledge.domain.graph import (
    EdgeType,
    GraphEdge,
    GraphEdgeId,
    GraphNode,
    GraphNodeId,
    NodeType,
    edge_identity,
    node_key,
    parse_node_key,
)
from skm.modules.knowledge.domain.graph_algorithms import (
    SubgraphView,
    Traversal,
    bounded_neighborhood,
    components,
    neighbors,
    shortest_path,
    stats,
    subgraph,
)
from skm.modules.knowledge.domain.graph_answer import GraphAnswer, build_answer
from skm.modules.knowledge.domain.graph_index import (
    Completeness,
    FreshnessState,
    GraphBasis,
    GraphIndex,
    GraphIndexId,
    Limitation,
    LimitationCode,
    next_generation,
)
from skm.modules.knowledge.domain.graph_namespaces import link_allowed, shares

_WORKSPACE = WorkspaceId(UUID(int=10))
_REPO = RepositoryId(UUID(int=11))
_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_REVISION = "a" * 40
_INDEX = GraphIndexId(UUID(int=12))


def _node(number: int, *, source: str = "serena") -> GraphNode:
    return GraphNode(
        GraphNodeId(UUID(int=number)),
        _WORKSPACE,
        None,
        f"symbol:{_REPO}:app.py#{number}",
        NodeType.SYMBOL,
        {},
        source,
        _REPO,
        _INDEX,
    )


def _edge(number: int, src: GraphNode, dst: GraphNode, kind: EdgeType = EdgeType.REFERENCES) -> GraphEdge:
    return GraphEdge(
        GraphEdgeId(UUID(int=number)),
        _WORKSPACE,
        src.id,
        dst.id,
        kind,
        {},
        "serena",
        _REPO,
        str(number),
        None,
        _INDEX,
    )


def _index() -> GraphIndex:
    return GraphIndex(
        _INDEX,
        _WORKSPACE,
        None,
        _REPO,
        "serena",
        7,
        _REVISION,
        False,
        ("python",),
        GraphBasis.LSP,
        "serena",
        "1",
        _NOW,
        Completeness.COMPLETE,
        (),
        1,
        0,
        2,
        1,
    )


def test_directed_multigraph_paths_and_induced_subgraph() -> None:
    a, b, c, isolated = map(_node, range(1, 5))
    first, parallel = _edge(101, a, b), _edge(102, a, b)
    onward, cycle = _edge(103, b, c, EdgeType.USES), _edge(104, c, a)
    graph = SubgraphView((a, b, c, isolated), (first, parallel, onward, cycle))

    assert edge_identity(first) != edge_identity(parallel)
    hits = neighbors(graph, a.id, depth=2)
    assert [(hit.node_id, hit.distance, hit.via_edge_ids) for hit in hits] == [
        (a.id, 0, ()),
        (b.id, 1, (first.id, parallel.id)),
        (c.id, 2, (onward.id,)),
    ]
    assert [hit.node_id for hit in neighbors(graph, a.id, depth=1, direction="in")] == [a.id, c.id]
    assert shortest_path(graph, c.id, b.id, direction="in") == (onward.id,)
    assert shortest_path(graph, a.id, c.id, direction="both") == (cycle.id,)
    assert shortest_path(graph, a.id, c.id, edge_types=frozenset({EdgeType.REFERENCES})) is None
    assert shortest_path(graph, a.id, isolated.id) is None
    assert shortest_path(graph, a.id, a.id) == ()
    induced = subgraph(graph, (a.id, b.id), depth=0, direction="in")
    assert induced.nodes == (a, b)
    assert induced.edges == (first, parallel)
    assert components(graph.nodes, graph.edges) == (frozenset({a.id, b.id, c.id}), frozenset({isolated.id}))
    assert stats(graph.nodes, graph.edges) == {
        "nodes_by_type": {"symbol": 4},
        "edges_by_type": {"references": 3, "uses": 1},
        "components": 2,
        "isolated": 1,
    }


def test_node_key_and_namespace_rules() -> None:
    assert parse_node_key(node_key(NodeType.SYMBOL, f"{_REPO}:app.py#Main")) == (
        NodeType.SYMBOL,
        f"{_REPO}:app.py#Main",
    )
    for bad in ("symbol", "symbol:", "unknown:value", "symbol:" + "x" * 301):
        with pytest.raises(ValueError, match=r"Graph node key|valid NodeType"):
            parse_node_key(bad)
    assert link_allowed(frozenset({"one"}), None)
    assert shares(frozenset({"one"}), frozenset({"one", "two"}))
    assert link_allowed(frozenset({"one"}), frozenset({"*"}))
    assert not link_allowed(frozenset({"one"}), frozenset({"two"}))
    assert [basis.rank for basis in GraphBasis] == [4, 3, 2, 1, 0]
    assert next_generation(None) == 1
    assert next_generation(_index()) == 8


def test_bounded_frontier_keeps_seeds_and_counts_the_omitted_level() -> None:
    a, b, c, d = map(_node, range(1, 5))
    graph = SubgraphView((a, b, c, d), (_edge(1, a, b), _edge(2, a, c), _edge(3, b, d)))
    out = Traversal("out")
    bounded = bounded_neighborhood(graph, (a.id,), depth=8, max_nodes=2, traversal=out)
    assert bounded.nodes == (a, b)
    assert bounded.omitted_nodes == 1
    assert bounded.beyond_depth == 0
    depth = bounded_neighborhood(graph, (a.id,), depth=1, max_nodes=4, traversal=out)
    assert depth.nodes == (a, b, c)
    assert depth.beyond_depth == 1


def test_build_answer_combines_basis_and_reports_index_provenance() -> None:
    a, b = _node(1), _node(2)
    lsp = _edge(1, a, b)
    text = replace(_edge(2, a, b, EdgeType.USES), basis=GraphBasis.TEXT)
    index = _index()
    query: GraphQueryEcho = {"op": "neighbors", "root": a.node_key, "at_revision": _REVISION}
    graph = SubgraphView((a, b), (lsp, text))
    view = build_answer(query, graph, {_INDEX: index}, now=_NOW, stale_after=timedelta(days=1))
    assert view.repository_id == _REPO
    assert view.index_generation == 7
    assert view.revision == _REVISION
    assert view.languages == ("python",)
    assert view.relation_kind == "mixed"
    assert view.basis is GraphBasis.TEXT
    assert [edge.basis for edge in view.edges] == [GraphBasis.LSP, GraphBasis.TEXT]
    assert view.completeness is Completeness.COMPLETE
    assert view.freshness.state is FreshnessState.FRESH
    assert view.to_document()["sources"][0]["repository_id"] == str(_REPO)


@pytest.mark.parametrize(
    ("revision", "dirty", "age", "state", "code"),
    [
        (_REVISION, True, 0, FreshnessState.STALE, LimitationCode.INDEX_DIRTY),
        ("b" * 40, False, 0, FreshnessState.STALE, LimitationCode.INDEX_STALE),
        (None, False, 25, FreshnessState.STALE, LimitationCode.INDEX_OLD),
        (None, False, 24, FreshnessState.UNKNOWN, None),
    ],
)
def test_freshness(
    revision: str | None, dirty: bool, age: int, state: FreshnessState, code: LimitationCode | None
) -> None:
    root = _node(1)
    query: GraphQueryEcho = {"op": "neighbors", "root": root.node_key}
    if revision is not None:
        query["at_revision"] = revision
    view = build_answer(
        query,
        SubgraphView((root,), ()),
        {_INDEX: replace(_index(), dirty=dirty)},
        now=_NOW + timedelta(hours=age),
        stale_after=timedelta(days=1),
    )
    assert view.freshness.state is state
    assert view.freshness.age_seconds == age * 3600
    assert {limit.code for limit in view.limitations} == ({code} if code else set())


def test_answer_completeness_priority_and_missing_cross_repository_endpoint() -> None:
    a, b = _node(1), _node(2)
    incomplete = Limitation(LimitationCode.PARSE_ERRORS, "parse error", 2)
    index = replace(_index(), completeness=Completeness.PARTIAL, limitations=(incomplete,))
    query: GraphQueryEcho = {"op": "neighbors", "root": a.node_key}
    edge = replace(_edge(1, a, b), repository_id=RepositoryId(UUID(int=99)), index_id=None)
    graph = SubgraphView((a,), (edge,))

    def view(
        indexes: Mapping[GraphIndexId, GraphIndex], *, limits: frozenset[LimitationCode] = frozenset()
    ) -> GraphAnswer:
        return build_answer(
            query,
            graph,
            indexes,
            now=_NOW,
            stale_after=timedelta(days=1),
            limits_hit=limits,
            limit_counts={LimitationCode.NODE_LIMIT: 3},
        )

    unknown = view({})
    assert unknown.completeness is Completeness.UNKNOWN
    assert {limit.code: limit.count for limit in unknown.limitations} == {
        LimitationCode.NO_INDEX: None,
        LimitationCode.CROSS_REPOSITORY_UNRESOLVED: 1,
    }
    partial = view({_INDEX: index})
    assert partial.completeness is Completeness.PARTIAL
    assert incomplete in partial.limitations
    truncated = view({_INDEX: index}, limits=frozenset({LimitationCode.NODE_LIMIT}))
    assert truncated.completeness is Completeness.TRUNCATED
    assert (
        next(limit for limit in truncated.limitations if limit.code is LimitationCode.NODE_LIMIT).count == 3
    )

    unsupported = build_answer(
        query,
        SubgraphView((a,), ()),
        {_INDEX: replace(_index(), languages=("php",))},
        now=_NOW,
        stale_after=timedelta(days=1),
    )
    assert unsupported.completeness is Completeness.PARTIAL
    manual = build_answer(
        query,
        SubgraphView((replace(a, source="manual"),), ()),
        {_INDEX: replace(_index(), source="manual")},
        now=_NOW,
        stale_after=timedelta(days=1),
    )
    assert manual.completeness is Completeness.UNKNOWN


def test_answer_is_unknown_when_a_contributing_edge_has_no_index() -> None:
    a, b = _node(1), _node(2)
    index = _index()
    view = build_answer(
        {"op": "neighbors", "root": a.node_key, "at_revision": _REVISION},
        SubgraphView((a, b), (replace(_edge(1, a, b), index_id=None),)),
        {_INDEX: index},
        now=_NOW,
        stale_after=timedelta(days=1),
    )
    assert view.freshness.state is FreshnessState.UNKNOWN
    assert view.basis is GraphBasis.HEURISTIC
    assert {limit.code for limit in view.limitations} == {LimitationCode.NO_INDEX}
