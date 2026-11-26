"""Build a graph answer from the evidence that contributed to it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from operator import attrgetter
from typing import Any, Literal
from uuid import UUID

from skm.kernel.ids import RepositoryId
from skm.kernel.languages import language_for_path
from skm.modules.knowledge.generated import documents

from .contracts import GraphQueryEcho, GraphStats
from .graph import EdgeType, GraphNode, NodeType
from .graph_algorithms import SubgraphView, stats
from .graph_carriers import AnswerEdge, AnswerNode, Freshness, GraphSourceRef
from .graph_index import (
    Completeness,
    FreshnessState,
    GraphBasis,
    GraphIndex,
    GraphIndexId,
    Limitation,
    LimitationCode,
)


@dataclass(frozen=True, slots=True)
class GraphAnswer:
    query: GraphQueryEcho
    repository_id: RepositoryId | None
    revision: str | None
    index_generation: int | None
    sources: tuple[GraphSourceRef, ...]
    languages: tuple[str, ...]
    relation_kind: EdgeType | Literal["mixed", "none"]
    completeness: Completeness
    limitations: tuple[Limitation, ...]
    freshness: Freshness
    basis: GraphBasis | None
    nodes: tuple[AnswerNode, ...]
    edges: tuple[AnswerEdge, ...]
    path: tuple[str, ...] | None
    stats: GraphStats | None

    def to_document(self) -> documents.GraphAnswer:
        def json_fields(fields: list[tuple[str, Any]]) -> dict[str, Any]:
            return {
                key: value.value
                if isinstance(value, StrEnum)
                else value.isoformat()
                if isinstance(value, datetime)
                else str(value)
                if isinstance(value, UUID)
                else value
                for key, value in fields
            }

        result = asdict(self, dict_factory=json_fields)
        result["schema"] = "urn:skm:knowledge:graph-answer:v1"
        for node in result["nodes"]:
            if node["distance"] is None:
                del node["distance"]
        return documents.graph_answer_from_json(result)


type IndexKey = tuple[str, RepositoryId | None]

_LIMIT_MESSAGES = {
    LimitationCode.DEPTH_LIMIT: "Traversal stopped at the configured depth limit",
    LimitationCode.NODE_LIMIT: "Traversal stopped at the configured node limit",
    LimitationCode.LANGUAGE_UNSUPPORTED: "The primary index does not cover the root file's language",
    LimitationCode.CROSS_REPOSITORY_UNRESOLVED: "Cross-repository endpoints are missing from the graph",
    LimitationCode.NO_INDEX: "A contributing graph index is unavailable",
    LimitationCode.INDEX_STALE: "The index revision differs from the requested revision",
    LimitationCode.INDEX_DIRTY: "The index was built from a dirty checkout",
    LimitationCode.INDEX_OLD: "The index exceeds the configured freshness age",
}
_TRAVERSAL_LIMITS = {LimitationCode.DEPTH_LIMIT, LimitationCode.NODE_LIMIT}


def _limit(code: LimitationCode, count: int | None = None) -> Limitation:
    return Limitation(code, _LIMIT_MESSAGES.get(code, code.value.replace("_", " ")), count)


def _freshness(
    index: GraphIndex | None, revision: str | None, now: datetime, stale_after: timedelta
) -> tuple[Freshness, LimitationCode | None]:
    if index is None:
        return Freshness(FreshnessState.UNKNOWN, None, None, revision, None), None
    age = now - index.indexed_at
    state, limitation = FreshnessState.UNKNOWN, None
    if revision is not None and index.revision is not None:
        if index.revision != revision:
            limitation = LimitationCode.INDEX_STALE
        elif index.dirty:
            limitation = LimitationCode.INDEX_DIRTY
        else:
            state = FreshnessState.FRESH
    elif revision is None and age > stale_after:
        limitation = LimitationCode.INDEX_OLD
    if limitation is not None:
        state = FreshnessState.STALE
    return Freshness(
        state, index.indexed_at, index.revision, revision, max(0, int(age.total_seconds()))
    ), limitation


def _language(node: GraphNode) -> str | None:
    language = node.attrs.get("language")
    if isinstance(language, str):
        return language
    if node.type in {NodeType.DOC, NodeType.SYMBOL}:
        _, sep, path = node.node_key.partition(":")[2].partition(":")
        if sep:
            basename = path.partition("#")[0].rsplit("/", 1)[-1]
            stem, dot, _extension = basename.rpartition(".")
            if stem and dot:
                return language_for_path(basename)
    return None


def contributing_index_ids(hits: SubgraphView) -> frozenset[GraphIndexId]:
    return frozenset(item.index_id for item in (*hits.nodes, *hits.edges) if item.index_id is not None)


def _completeness(
    sources: tuple[GraphIndex, ...], limits: frozenset[LimitationCode], unsupported: bool, missing: bool
) -> Completeness:
    if limits & _TRAVERSAL_LIMITS:
        return Completeness.TRUNCATED
    if unsupported or any(source.completeness is Completeness.PARTIAL for source in sources):
        return Completeness.PARTIAL
    if missing or all(source.source == "manual" for source in sources):
        return Completeness.UNKNOWN
    return Completeness.COMPLETE


def build_answer(
    query: GraphQueryEcho,
    hits: SubgraphView,
    indexes: Mapping[GraphIndexId, GraphIndex],
    *,
    now: datetime,
    stale_after: timedelta,
    limits_hit: frozenset[LimitationCode] = frozenset(),
    limit_counts: Mapping[LimitationCode, int] | None = None,
) -> GraphAnswer:
    by_id = {node.id: node for node in hits.nodes}
    root_key = query.get("root", query.get("src"))
    root = next((node for node in hits.nodes if node.node_key == root_key), None)
    primary = indexes.get(root.index_id) if root is not None and root.index_id is not None else None
    sources = tuple(
        sorted(
            (indexes[key] for key in contributing_index_ids(hits) & indexes.keys()),
            key=lambda index: (index.source, str(index.repository_id or ""), index.generation),
        )
    )
    missing = any(
        item.index_id is None or item.index_id not in indexes for item in (*hits.nodes, *hits.edges)
    )
    revisions = query.get("at_revision")
    freshness, stale = _freshness(
        primary, revisions if isinstance(revisions, str) else None, now, stale_after
    )
    language = _language(root) if root is not None else None
    unsupported = language is not None and primary is not None and language not in primary.languages

    codes = set(limits_hit)
    if stale is not None:
        codes.add(stale)
    if freshness.state is FreshnessState.FRESH and primary is not None:
        state = FreshnessState.UNKNOWN if missing else FreshnessState.FRESH
        for source in sources:
            if source.repository_id != primary.repository_id:
                if state is FreshnessState.FRESH:
                    state = FreshnessState.UNKNOWN
                continue
            evidence, limitation = _freshness(source, freshness.at_revision, now, stale_after)
            if limitation is not None:
                codes.add(limitation)
                state = FreshnessState.STALE
            elif evidence.state is FreshnessState.UNKNOWN and state is FreshnessState.FRESH:
                state = FreshnessState.UNKNOWN
        freshness = replace(freshness, state=state)
    if unsupported:
        codes.add(LimitationCode.LANGUAGE_UNSUPPORTED)
    if not sources or missing:
        codes.add(LimitationCode.NO_INDEX)
    counts = dict(limit_counts or {})
    edges: list[AnswerEdge] = []
    unresolved = 0
    for edge in hits.edges:
        src, dst = by_id.get(edge.src_node_id), by_id.get(edge.dst_node_id)
        if src is None or dst is None:
            known = src or dst
            unresolved += int(known is not None and known.repository_id != edge.repository_id)
            continue
        index = indexes.get(edge.index_id) if edge.index_id is not None else None
        basis = edge.basis or (index.basis_default if index else GraphBasis.HEURISTIC)
        edges.append(AnswerEdge(src.node_key, dst.node_key, edge.type, edge.source, basis, dict(edge.attrs)))
    if unresolved:
        codes.add(LimitationCode.CROSS_REPOSITORY_UNRESOLVED)
        counts[LimitationCode.CROSS_REPOSITORY_UNRESOLVED] = unresolved

    limitations = dict.fromkeys(
        [
            *(_limit(code, counts.get(code)) for code in sorted(codes)),
            *(limitation for source in sources for limitation in source.limitations),
        ]
    )
    repositories = {node.repository_id for node in hits.nodes}
    relations = {edge.type for edge in edges}
    summary = query["op"] == "stats"
    return GraphAnswer(
        query=query,
        repository_id=next(iter(repositories)) if len(repositories) == 1 else None,
        revision=primary.revision if primary else None,
        index_generation=primary.generation if primary else None,
        sources=tuple(
            GraphSourceRef(
                idx.source,
                idx.repository_id,
                idx.generation,
                idx.revision,
                idx.dirty,
                idx.indexed_at,
                idx.tool_name,
                idx.tool_version,
            )
            for idx in sources
        ),
        languages=tuple(sorted({language for source in sources for language in source.languages})),
        relation_kind=next(iter(relations)) if len(relations) == 1 else "mixed" if relations else "none",
        completeness=_completeness(sources, limits_hit, unsupported, missing),
        limitations=tuple(limitations),
        freshness=freshness,
        basis=min((edge.basis for edge in edges), key=attrgetter("rank"), default=None),
        nodes=()
        if summary
        else tuple(
            AnswerNode(node.node_key, node.type, dict(node.attrs), node.source, hits.distances.get(node.id))
            for node in hits.nodes
        ),
        edges=() if summary else tuple(edges),
        path=hits.path,
        stats=stats(hits.nodes, hits.edges) if summary else None,
    )
