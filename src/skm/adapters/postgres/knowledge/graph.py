"""PostgreSQL graph storage over 0021 with a bounded breadth-first recursive CTE."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Final, cast

import psycopg
from psycopg.types.json import Jsonb

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.knowledge.domain.contracts import Adjacency, ReplaceStats
from skm.modules.knowledge.domain.graph import (
    EdgeIdentity,
    GraphEdge,
    GraphNode,
    GraphNodeId,
    edge_identity,
    project_key_reference,
    source_payload_matches,
)
from skm.modules.knowledge.domain.graph_algorithms import (
    DEFAULT_TRAVERSAL,
    Neighborhood,
    Traversal,
    node_from_row,
)
from skm.modules.knowledge.domain.graph_answer import IndexKey
from skm.modules.knowledge.domain.graph_index import (
    Completeness,
    GraphBasis,
    GraphIndex,
    GraphIndexId,
    Limitation,
    LimitationCode,
)

from .mapping import Row, run

__all__ = ["PostgresGraphRepository"]

_LOCK_WORKSPACE: Final = "SELECT pg_advisory_xact_lock(hashtextextended('skm-knowledge-graph:' || %s, 0))"
# Index creation time identifies the graph evidence written in that batch. Reserve a stamp under
# the workspace lock so retained rows keep their provenance even if the database clock moves back.
_WRITE_TIME: Final = """
WITH partition AS (SELECT %s::uuid AS workspace_id, %s::text AS source, %s::uuid AS repository_id)
SELECT greatest(clock_timestamp(), max(recorded_at) + interval '1 microsecond') FROM (
    SELECT max(i.created_at) FROM skm_knowledge.graph_indexes i JOIN partition p USING (workspace_id, source)
    WHERE i.repository_id IS NOT DISTINCT FROM p.repository_id
    UNION ALL
    SELECT max(n.updated_at) FROM skm_knowledge.graph_nodes n JOIN partition p USING (workspace_id, source)
    WHERE n.repository_id IS NOT DISTINCT FROM p.repository_id
    UNION ALL
    SELECT max(e.created_at) FROM skm_knowledge.graph_edges e JOIN partition p USING (workspace_id, source)
    WHERE e.repository_id IS NOT DISTINCT FROM p.repository_id
) AS stamps(recorded_at)
"""
_UPSERT_NODES: Final = """
WITH batch AS (SELECT %s::timestamptz AS recorded_at)
INSERT INTO skm_knowledge.graph_nodes AS n
    (id, workspace_id, project_id, repository_id, node_key, type, attrs, source, created_at, updated_at)
SELECT id, workspace_id, project_id, repository_id, node_key, type, attrs, source,
       recorded_at, recorded_at
FROM jsonb_to_recordset(%s) AS incoming(
    id uuid, workspace_id uuid, project_id uuid, repository_id uuid,
    node_key text, type text, attrs jsonb, source text
) CROSS JOIN LATERAL (
    SELECT coalesce(batch.recorded_at, greatest(statement_timestamp(), (
        SELECT max(i.created_at) + interval '1 microsecond' FROM skm_knowledge.graph_indexes i
        WHERE i.workspace_id = incoming.workspace_id AND i.source = incoming.source
          AND i.repository_id IS NOT DISTINCT FROM incoming.repository_id
    ))) AS recorded_at FROM batch
) stamp
ON CONFLICT (workspace_id, node_key) DO UPDATE SET
    (attrs, updated_at) = (
        SELECT CASE WHEN same_owner THEN excluded.attrs ELSE n.attrs END,
               CASE WHEN same_owner THEN excluded.updated_at ELSE n.updated_at END
        FROM (SELECT n.project_id IS NOT DISTINCT FROM excluded.project_id
                     AND n.repository_id IS NOT DISTINCT FROM excluded.repository_id
                     AND n.source = excluded.source AS same_owner) AS ownership
    )
RETURNING node_key, id
"""
_WRITE_EDGES: Final = """
WITH stamp AS (SELECT %s::timestamptz AS recorded_at), incoming AS MATERIALIZED (
    SELECT * FROM jsonb_to_recordset(%s) AS batch(
        id uuid, workspace_id uuid, src_node_id uuid, dst_node_id uuid,
        type text, attrs jsonb, source text, source_key text, repository_id uuid, basis text
    )
), matched AS (
    SELECT e.id AS stored_id, e.repository_id AS stored_repository, i.*
    FROM incoming i JOIN skm_knowledge.graph_edges e
      USING (workspace_id, src_node_id, dst_node_id, type, source, source_key)
), updated AS (
    UPDATE skm_knowledge.graph_edges e SET attrs = m.attrs, basis = m.basis, created_at = stamp.recorded_at
    FROM matched m CROSS JOIN stamp
    WHERE e.id = m.stored_id AND m.stored_repository IS NOT DISTINCT FROM m.repository_id
    RETURNING e.id
), inserted AS (
    INSERT INTO skm_knowledge.graph_edges
        (id, workspace_id, src_node_id, dst_node_id, type, attrs, source,
         source_key, repository_id, basis, created_at)
    SELECT id, workspace_id, src_node_id, dst_node_id, type, attrs, source,
           source_key, repository_id, basis, stamp.recorded_at
    FROM incoming i CROSS JOIN stamp WHERE NOT EXISTS (SELECT 1 FROM matched m WHERE m.id = i.id)
    RETURNING id
)
SELECT id, false FROM updated UNION ALL SELECT id, true FROM inserted
"""
_REMOVE_EDGES: Final = """
DELETE FROM skm_knowledge.graph_edges
WHERE workspace_id = %s AND source = %s AND repository_id IS NOT DISTINCT FROM %s::uuid
  AND id <> ALL(%s::uuid[])
"""
_REMOVE_NODES: Final = """
DELETE FROM skm_knowledge.graph_nodes n
WHERE n.workspace_id = %s AND n.source = %s AND n.repository_id IS NOT DISTINCT FROM %s::uuid
  AND n.id <> ALL(%s::uuid[])
  AND NOT EXISTS (
      SELECT 1 FROM skm_knowledge.graph_edges e WHERE e.workspace_id = n.workspace_id AND e.src_node_id = n.id
  )
  AND NOT EXISTS (
      SELECT 1 FROM skm_knowledge.graph_edges e WHERE e.workspace_id = n.workspace_id AND e.dst_node_id = n.id
  )
"""
_ADD_INDEX: Final = """
INSERT INTO skm_knowledge.graph_indexes
    (id, workspace_id, project_id, repository_id, source, generation, revision, dirty, languages,
     basis_default, tool_name, tool_version, indexed_at, completeness, limitations,
     files_indexed, files_skipped, nodes, edges, created_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        coalesce(%s::timestamptz, statement_timestamp()))
"""
_INDEXES_FOR: Final = """
SELECT i.id, i.workspace_id, i.project_id, i.repository_id, i.source, i.generation, i.revision, i.dirty,
       i.languages, i.basis_default, i.tool_name, i.tool_version, i.indexed_at,
       i.completeness, i.limitations, i.files_indexed, i.files_skipped, i.nodes, i.edges
FROM jsonb_to_recordset(%s) AS keys(source text, repository_id uuid)
CROSS JOIN LATERAL (
    SELECT * FROM skm_knowledge.graph_indexes i
    WHERE i.workspace_id = %s AND i.source = keys.source
      AND i.repository_id IS NOT DISTINCT FROM keys.repository_id
    ORDER BY i.generation DESC LIMIT 1
) i
"""
_INDEXES_BY_ID: Final = """
SELECT i.id, i.workspace_id, i.project_id, i.repository_id, i.source, i.generation, i.revision, i.dirty,
       i.languages, i.basis_default, i.tool_name, i.tool_version, i.indexed_at,
       i.completeness, i.limitations, i.files_indexed, i.files_skipped, i.nodes, i.edges
FROM skm_knowledge.graph_indexes i WHERE i.workspace_id = %s AND i.id = ANY(%s::uuid[])
"""
_LATEST_INDEXES: Final = """
SELECT DISTINCT ON (source, repository_id)
       id, workspace_id, project_id, repository_id, source, generation, revision, dirty,
       languages, basis_default, tool_name, tool_version, indexed_at,
       completeness, limitations, files_indexed, files_skipped, nodes, edges
FROM skm_knowledge.graph_indexes
WHERE workspace_id = %s
  AND (%s::text IS NULL OR source = %s)
  AND (%s::uuid IS NULL OR repository_id = %s)
ORDER BY source, repository_id, generation DESC
"""
_PROJECT_SCOPES: Final = """
SELECT DISTINCT project_id, CASE WHEN type = 'project' THEN node_key END
FROM skm_knowledge.graph_nodes
WHERE workspace_id = %s AND (project_id IS NOT NULL OR type = 'project')
"""
_ALL_NODES: Final = """
WITH params AS (
    SELECT %s::uuid AS workspace_id, %s::uuid AS project_id,
           %s::uuid[] AS projects, %s::text[] AS project_keys
)
SELECT n.id, count(*) OVER ()
FROM params p JOIN skm_knowledge.graph_nodes n USING (workspace_id)
WHERE (p.project_id IS NULL OR n.project_id = p.project_id)
  AND (p.projects IS NULL OR n.project_id IS NULL OR n.project_id = ANY(p.projects))
  AND (p.project_keys IS NULL OR n.type <> 'project' OR n.node_key = ANY(p.project_keys))
ORDER BY n.id LIMIT %s
"""
# Each level retains at most the remaining budget. The final probe measures the frontier
# at the depth boundary without appending it or following any of its edges.
_REACHABLE: Final = """
WITH RECURSIVE params AS (
    SELECT %s::uuid AS workspace_id, %s::uuid[] AS roots, %s::int AS depth,
           %s::int AS cap, %s::text AS direction, %s::text[] AS types, %s::uuid AS project_id,
           %s::uuid[] AS projects, %s::text[] AS project_keys
), seeds AS (
    SELECT n.id, count(*) OVER () AS total
    FROM params p JOIN skm_knowledge.graph_nodes n ON n.workspace_id = p.workspace_id
    WHERE n.id = ANY(p.roots) AND (p.project_id IS NULL OR n.project_id = p.project_id)
      AND (p.projects IS NULL OR n.project_id IS NULL OR n.project_id = ANY(p.projects))
      AND (p.project_keys IS NULL OR n.type <> 'project' OR n.node_key = ANY(p.project_keys))
    ORDER BY n.id LIMIT (SELECT cap FROM params)
), bfs(level, seen, frontier, omitted, beyond_depth) AS (
    SELECT 0, ids, ids, total - cardinality(ids), 0::bigint
    FROM (
        SELECT coalesce(array_agg(id ORDER BY id), '{}'::uuid[]) AS ids,
               coalesce(max(total), 0) AS total FROM seeds
    ) seed
    UNION ALL
    SELECT b.level + 1,
           CASE WHEN b.level < p.depth THEN b.seen || step.ids ELSE b.seen END,
           step.ids,
           CASE WHEN b.level < p.depth THEN step.total - cardinality(step.ids) ELSE 0 END,
           CASE WHEN b.level = p.depth THEN step.total ELSE 0 END
    FROM bfs b CROSS JOIN params p
    CROSS JOIN LATERAL (
        SELECT coalesce(array_agg(id ORDER BY id), '{}'::uuid[]) AS ids,
               coalesce(max(total), 0) AS total
        FROM (
            SELECT n.id, count(*) OVER () AS total
            FROM (
                SELECT e.dst_node_id AS id FROM skm_knowledge.graph_edges e
                WHERE e.workspace_id = p.workspace_id AND p.direction <> 'in'
                  AND e.src_node_id = ANY(b.frontier) AND (p.types IS NULL OR e.type = ANY(p.types))
                UNION
                SELECT e.src_node_id AS id FROM skm_knowledge.graph_edges e
                WHERE e.workspace_id = p.workspace_id AND p.direction <> 'out'
                  AND e.dst_node_id = ANY(b.frontier) AND (p.types IS NULL OR e.type = ANY(p.types))
            ) adjacent JOIN skm_knowledge.graph_nodes n USING (id)
            WHERE n.id <> ALL(b.seen) AND (p.project_id IS NULL OR n.project_id = p.project_id)
              AND (p.projects IS NULL OR n.project_id IS NULL OR n.project_id = ANY(p.projects))
              AND (p.project_keys IS NULL OR n.type <> 'project' OR n.node_key = ANY(p.project_keys))
            ORDER BY n.id
            LIMIT greatest(1, CASE WHEN b.level = p.depth THEN 1 ELSE p.cap - cardinality(b.seen) + 1 END)
        ) remaining
    ) measured
    CROSS JOIN LATERAL (
        SELECT measured.ids[1:greatest(0, p.cap - cardinality(b.seen))] AS ids, measured.total
    ) step
    WHERE b.level <= p.depth AND cardinality(b.frontier) > 0 AND b.omitted = 0
)
SELECT seen, omitted, beyond_depth FROM bfs ORDER BY level DESC LIMIT 1
"""
_NODE_ROWS: Final = """
SELECT to_jsonb(n) - 'created_at' - 'updated_at' || jsonb_build_object('index_id', (
    SELECT i.id FROM skm_knowledge.graph_indexes i
    WHERE i.workspace_id = n.workspace_id AND i.source = n.source
      AND i.repository_id IS NOT DISTINCT FROM n.repository_id AND i.created_at = n.updated_at
      AND i.limitations @> '[{"tracked_rows": true}]'::jsonb
)) FROM skm_knowledge.graph_nodes n
WHERE n.workspace_id = %s AND (n.id = ANY(%s::uuid[]) OR n.node_key = ANY(%s::text[]))
ORDER BY n.id
"""
_NEIGHBOR_EDGES: Final = """
SELECT to_jsonb(e) - 'created_at' || jsonb_build_object('index_id', (
    SELECT i.id FROM skm_knowledge.graph_indexes i
    WHERE i.workspace_id = e.workspace_id AND i.source = e.source
      AND i.repository_id IS NOT DISTINCT FROM e.repository_id AND i.created_at = e.created_at
      AND i.limitations @> '[{"tracked_rows": true}]'::jsonb
)) FROM skm_knowledge.graph_edges e
WHERE workspace_id = %s AND src_node_id = ANY(%s::uuid[]) AND dst_node_id = ANY(%s::uuid[])
  AND (%s::text[] IS NULL OR type = ANY(%s::text[]))
ORDER BY id
"""


def _index(row: Row) -> GraphIndex:
    return GraphIndex(
        id=cast("GraphIndexId", row[0]),
        workspace_id=cast("WorkspaceId", row[1]),
        project_id=cast("ProjectId | None", row[2]),
        repository_id=cast("RepositoryId | None", row[3]),
        source=cast("str", row[4]),
        generation=cast("int", row[5]),
        revision=cast("str | None", row[6]),
        dirty=cast("bool", row[7]),
        languages=tuple(cast("list[str]", row[8])),
        basis_default=GraphBasis(row[9]),
        tool_name=cast("str", row[10]),
        tool_version=cast("str", row[11]),
        indexed_at=cast("datetime", row[12]),
        completeness=Completeness(row[13]),
        limitations=tuple(
            Limitation(
                LimitationCode(item["code"]), cast("str", item["message"]), cast("int | None", item["count"])
            )
            for item in cast("list[JsonObject]", row[14])
            if item.get("tracked_rows") is not True
        ),
        files_indexed=cast("int", row[15]),
        files_skipped=cast("int", row[16]),
        nodes=cast("int", row[17]),
        edges=cast("int", row[18]),
    )


class PostgresGraphRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def lock_workspace(self, workspace_id: WorkspaceId) -> None:
        run(lambda: self._conn.execute(_LOCK_WORKSPACE, (str(workspace_id),)))

    def upsert_nodes(self, nodes: tuple[GraphNode, ...]) -> Mapping[str, GraphNodeId]:
        for workspace_id in sorted({node.workspace_id for node in nodes}):
            self.lock_workspace(workspace_id)
        return self._upsert_nodes(nodes)

    def _upsert_nodes(
        self, nodes: tuple[GraphNode, ...], recorded_at: datetime | None = None
    ) -> Mapping[str, GraphNodeId]:
        rows = Neighborhood(tuple({(node.workspace_id, node.node_key): node for node in nodes}.values()), ())
        result = run(
            lambda: self._conn.execute(
                _UPSERT_NODES, (recorded_at, Jsonb(rows.to_adjacency()["nodes"]))
            ).fetchall()
        )
        return {cast("str", key): cast("GraphNodeId", node_id) for key, node_id in result}

    def replace_from_source(
        self,
        workspace_id: WorkspaceId,
        source: str,
        repository_id: RepositoryId | None,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
    ) -> ReplaceStats:
        return self.write_source(workspace_id, source, repository_id, nodes, edges, replace_existing=True)

    def write_source(
        self,
        workspace_id: WorkspaceId,
        source: str,
        repository_id: RepositoryId | None,
        nodes: tuple[GraphNode, ...],
        edges: tuple[GraphEdge, ...],
        *,
        replace_existing: bool,
        index: GraphIndex | None = None,
    ) -> ReplaceStats:
        if not source_payload_matches(workspace_id, source, repository_id, nodes, edges):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Graph payload is outside its source partition")
        self.lock_workspace(workspace_id)
        partition = workspace_id, source, repository_id
        with self._conn.transaction():
            stamps = run(lambda: self._conn.execute(_WRITE_TIME, partition).fetchall())
            recorded_at = cast("datetime", stamps[0][0])
            ids = self._upsert_nodes(nodes, recorded_at)
            remapped = {node.id: ids[node.node_key] for node in nodes}
            incoming: dict[EdgeIdentity, GraphEdge] = {}
            for draft in edges:
                edge = replace(
                    draft,
                    src_node_id=remapped.get(draft.src_node_id, draft.src_node_id),
                    dst_node_id=remapped.get(draft.dst_node_id, draft.dst_node_id),
                )
                incoming[edge_identity(edge)] = edge
            payload = Neighborhood((), tuple(incoming.values())).to_adjacency()
            try:
                stored = self._conn.execute(_WRITE_EDGES, (recorded_at, Jsonb(payload["edges"]))).fetchall()
            except psycopg.errors.ForeignKeyViolation as exc:
                if exc.diag.constraint_name in {"fk_graph_edges__src", "fk_graph_edges__dst"}:
                    raise NotFound(ErrorCode.NOT_FOUND, "Graph edge endpoint not found in workspace") from exc
                raise translate_pg_error(exc) from exc
            except psycopg.Error as exc:
                raise translate_pg_error(exc) from exc
            if len(stored) != len(incoming):
                raise Conflict(ErrorCode.ALREADY_EXISTS, "Graph edge identity belongs to another repository")
            removed_edges = removed_nodes = 0
            if replace_existing:
                removed_edges = run(
                    lambda: (
                        self._conn.execute(_REMOVE_EDGES, (*partition, [row[0] for row in stored])).rowcount
                    )
                )
                removed_nodes = run(
                    lambda: self._conn.execute(_REMOVE_NODES, (*partition, list(ids.values()))).rowcount
                )
            if index is not None:
                self._add_index(index, recorded_at)
        return {
            "nodes_upserted": len(ids),
            "nodes_removed": removed_nodes,
            "edges_added": sum(bool(row[1]) for row in stored),
            "edges_removed": removed_edges,
        }

    def add_index(self, index: GraphIndex) -> None:
        self.lock_workspace(index.workspace_id)
        self._add_index(index)

    def _add_index(self, index: GraphIndex, recorded_at: datetime | None = None) -> None:
        limitations: list[JsonObject] = [
            {"code": item.code.value, "message": item.message, "count": item.count}
            for item in index.limitations
        ]
        if recorded_at is not None:
            # Opt in to timestamp matching only for indexes created by this adapter's batch writer.
            limitations.append({"tracked_rows": True})
        params = (
            index.id,
            index.workspace_id,
            index.project_id,
            index.repository_id,
            index.source,
            index.generation,
            index.revision,
            index.dirty,
            list(index.languages),
            index.basis_default.value,
            index.tool_name,
            index.tool_version,
            index.indexed_at,
            index.completeness.value,
            Jsonb(limitations),
            index.files_indexed,
            index.files_skipped,
            index.nodes,
            index.edges,
            recorded_at,
        )
        run(lambda: self._conn.execute(_ADD_INDEX, params))

    def latest_index(
        self, workspace_id: WorkspaceId, source: str, repository_id: RepositoryId | None
    ) -> GraphIndex | None:
        return self.indexes_for(workspace_id, frozenset({(source, repository_id)})).get(
            (source, repository_id)
        )

    def indexes_for(
        self, workspace_id: WorkspaceId, keys: frozenset[IndexKey]
    ) -> Mapping[IndexKey, GraphIndex]:
        if not keys:
            return {}
        wanted = Jsonb(
            [
                {"source": source, "repository_id": str(repo) if repo is not None else None}
                for source, repo in keys
            ]
        )
        rows = run(lambda: self._conn.execute(_INDEXES_FOR, (wanted, workspace_id)).fetchall())
        return {(item.source, item.repository_id): item for item in map(_index, rows)}

    def indexes_by_id(
        self, workspace_id: WorkspaceId, ids: frozenset[GraphIndexId]
    ) -> Mapping[GraphIndexId, GraphIndex]:
        if not ids:
            return {}
        rows = run(lambda: self._conn.execute(_INDEXES_BY_ID, (workspace_id, list(ids))).fetchall())
        return {item.id: item for item in map(_index, rows)}

    def latest_indexes(
        self, workspace_id: WorkspaceId, *, source: str | None, repository_id: RepositoryId | None
    ) -> tuple[GraphIndex, ...]:
        if source is not None and "\x00" in source:
            return ()
        params = (workspace_id, source, source, repository_id, repository_id)
        rows = run(lambda: self._conn.execute(_LATEST_INDEXES, params).fetchall())
        return tuple(map(_index, rows))

    def _visible_scopes(
        self, workspace_id: WorkspaceId, traversal: Traversal
    ) -> tuple[list[ProjectId] | None, list[str] | None]:
        visible = traversal.project_visible
        if visible is None:
            return None, None
        scopes = run(lambda: self._conn.execute(_PROJECT_SCOPES, (workspace_id,)).fetchall())
        projects = {cast("ProjectId", project) for project, _ in scopes if project is not None}
        keys = {cast("str", key) for _, key in scopes if key is not None}
        return (
            [project for project in projects if visible(project)],
            [key for key in keys if (reference := project_key_reference(key)) is None or visible(reference)],
        )

    def neighborhood(
        self,
        workspace_id: WorkspaceId,
        roots: tuple[GraphNodeId, ...],
        *,
        depth: int,
        max_nodes: int,
        traversal: Traversal = DEFAULT_TRAVERSAL,
    ) -> Adjacency:
        types = None if traversal.edge_types is None else [kind.value for kind in traversal.edge_types]
        projects, project_keys = self._visible_scopes(workspace_id, traversal)
        if roots:
            params = (
                workspace_id,
                list(roots),
                depth,
                max_nodes,
                traversal.direction,
                types,
                traversal.project_id,
                projects,
                project_keys,
            )
            found = run(lambda: self._conn.execute(_REACHABLE, params).fetchone())

            if found is None:
                return Neighborhood((), ()).to_adjacency()
            ids, omitted, beyond_depth = found
        else:
            params = workspace_id, traversal.project_id, projects, project_keys, max_nodes
            rows = run(lambda: self._conn.execute(_ALL_NODES, params).fetchall())
            ids = [row[0] for row in rows]
            omitted = rows[0][1] - len(rows) if rows else 0
            beyond_depth = 0
        nodes = run(lambda: self._conn.execute(_NODE_ROWS, (workspace_id, ids, [])).fetchall())
        edges = run(
            lambda: self._conn.execute(_NEIGHBOR_EDGES, (workspace_id, ids, ids, types, types)).fetchall()
        )
        return {
            "nodes": [row[0] for row in nodes],
            "edges": [row[0] for row in edges],
            "omitted_nodes": omitted,
            "beyond_depth": beyond_depth,
            "truncated": bool(omitted),
        }

    def nodes_by_keys(self, workspace_id: WorkspaceId, keys: frozenset[str]) -> Mapping[str, GraphNode]:
        if not keys:
            return {}
        rows = run(lambda: self._conn.execute(_NODE_ROWS, (workspace_id, [], list(keys))).fetchall())
        nodes = (node_from_row(row) for (row,) in rows)
        return {node.node_key: node for node in nodes}

    def node_by_key(self, workspace_id: WorkspaceId, node_key: str) -> GraphNode | None:
        return self.nodes_by_keys(workspace_id, frozenset({node_key})).get(node_key)
