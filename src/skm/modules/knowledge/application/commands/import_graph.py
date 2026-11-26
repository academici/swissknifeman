"""Import a source snapshot or append a chunk in one workspace transaction."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed
from skm.kernel.ids import ProjectId, RepositoryId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRef
from skm.modules.access.public import effective_permissions
from skm.modules.knowledge.application.scopes import project_ref, workspace_ref
from skm.modules.knowledge.contracts import invalid_graph_import, validate_graph_import
from skm.modules.knowledge.domain.contracts import ReplaceStats
from skm.modules.knowledge.domain.events import GraphImported
from skm.modules.knowledge.domain.graph import (
    EdgeType,
    GraphEdge,
    GraphEdgeId,
    GraphNode,
    GraphNodeId,
    NodeType,
    edge_identity,
    project_reference,
)
from skm.modules.knowledge.domain.graph_index import (
    Completeness,
    GraphBasis,
    GraphIndex,
    GraphIndexId,
    Limitation,
    LimitationCode,
    next_generation,
)
from skm.modules.knowledge.domain.graph_namespaces import link_allowed
from skm.modules.knowledge.generated.commands import ImportGraph
from skm.modules.knowledge.generated.events import graph_imported_counts_from_json
from skm.modules.knowledge.generated.results import ImportGraphResult, ImportGraphResultDefsJsonValue
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.ports import GraphRepository
from skm.modules.workspace.public import (
    get_repository,
    require_active_project,
    require_active_workspace,
    require_repository,
    workspace_of_project,
)
from skm.platform.config import ConfigLoader, ConfigStore, PackConfigSource, ScopeTree

type GraphRejection = dict[str, ImportGraphResultDefsJsonValue]


class _GraphWriter(GraphRepository, Protocol):
    """Storage capabilities used by the import handler in addition to the P00 port."""

    def lock_workspace(self, workspace_id: WorkspaceId) -> None: ...

    def nodes_by_keys(self, workspace_id: WorkspaceId, keys: frozenset[str]) -> Mapping[str, GraphNode]: ...

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
    ) -> ReplaceStats: ...


def _scope(cmd: dict[str, Any], uow: UnitOfWork) -> ScopeRef | None:
    if cmd["project_id"] is not None:
        return project_ref(cmd["project_id"])
    if cmd["repository_id"] is not None:
        repository = get_repository(uow, RepositoryId(UUID(cmd["repository_id"])))
        return workspace_ref(str(repository.workspace_id))
    return None


def _nodes(
    cmd: dict[str, Any],
    workspace: WorkspaceId,
    project: ProjectId | None,
    ctx: CommandContext,
    existing: Mapping[str, GraphNode],
    kinds: Mapping[str, NodeType],
) -> dict[str, GraphNode]:
    result: dict[str, GraphNode] = {}
    repository = RepositoryId(UUID(cmd["repository_id"])) if cmd["repository_id"] else None
    for item in cmd["nodes"]:
        key = item["node_key"]
        previous = existing.get(key)
        if previous is not None and previous.project_id != project:
            # A declaration cannot overwrite the owning scope. Edges may reference this node by key.
            raise Forbidden(ErrorCode.FORBIDDEN, "Graph node belongs to a different project")
        result[key] = GraphNode(
            previous.id if previous else GraphNodeId(ctx.ids.new_id()),
            workspace,
            project,
            key,
            kinds[key],
            item["attrs"],
            cmd["source"],
            repository,
        )
    return result


def _edge_rejection(edge: dict[str, Any]) -> GraphRejection:
    return {
        "code": "GRAPH_LINK_NOT_ALLOWED",
        "src_key": edge["src_key"],
        "dst_key": edge["dst_key"],
        "type": edge["type"],
        "source_key": edge["source_key"],
    }


def _edges(
    cmd: dict[str, Any],
    workspace: WorkspaceId,
    nodes: dict[str, GraphNode],
    ctx: CommandContext,
    uow: UnitOfWork,
    existing: Mapping[str, GraphNode],
) -> tuple[tuple[GraphEdge, ...], list[GraphRejection]]:
    known = {**existing, **nodes}
    by_project: dict[ProjectId, frozenset[str]] = {}
    references: dict[ProjectId, bool] = {}
    loader = ConfigLoader(ctx.config.registry, uow.repo(PackConfigSource))
    repository = RepositoryId(UUID(cmd["repository_id"])) if cmd["repository_id"] else None

    def endpoint(key: str) -> GraphNode:
        node = known.get(key)
        if node is None:
            raise NotFound(ErrorCode.NOT_FOUND, "Graph edge endpoint not found", details={"node_key": key})
        return node

    def namespaces(project: ProjectId) -> frozenset[str]:
        if project not in by_project:
            config = loader.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), project_ref(str(project)))
            by_project[project] = frozenset(config.section(KnowledgeSettings).graph.namespaces)
        return by_project[project]

    def reference_allowed(node: GraphNode) -> bool:
        reference = project_reference(node)
        if reference is None:
            return True
        if reference not in references:
            try:
                references[reference] = workspace_of_project(
                    uow, reference
                ) == workspace and "project.read" in effective_permissions(uow, ctx.actor, ScopeId(reference))
            except NotFound:
                references[reference] = False
        return references[reference]

    accepted: list[GraphEdge] = []
    rejected: list[GraphRejection] = []
    for item in cmd["edges"]:
        src, dst = endpoint(item["src_key"]), endpoint(item["dst_key"])
        src_project, dst_project = src.project_id, dst.project_id
        if (
            src.workspace_id != workspace
            or dst.workspace_id != workspace
            or not reference_allowed(src)
            or not reference_allowed(dst)
            or (
                src_project is not None
                and dst_project is not None
                and src_project != dst_project
                and not link_allowed(namespaces(src_project), namespaces(dst_project))
            )
        ):
            rejected.append(_edge_rejection(item))
            continue
        accepted.append(
            GraphEdge(
                GraphEdgeId(ctx.ids.new_id()),
                workspace,
                src.id,
                dst.id,
                EdgeType(item["type"]),
                item["attrs"],
                cmd["source"],
                repository,
                item["source_key"],
                GraphBasis(item["basis"]) if "basis" in item else None,
            )
        )
    return tuple(accepted), rejected


def _index(
    cmd: dict[str, Any],
    ctx: CommandContext,
    workspace: WorkspaceId,
    project: ProjectId | None,
    previous: GraphIndex | None,
    node_count: int,
    edges: tuple[GraphEdge, ...],
) -> GraphIndex:
    data = cmd["index"]
    return GraphIndex(
        id=GraphIndexId(ctx.ids.new_id()),
        workspace_id=workspace,
        project_id=project,
        repository_id=RepositoryId(UUID(cmd["repository_id"])) if cmd["repository_id"] else None,
        source=cmd["source"],
        generation=next_generation(previous),
        revision=data.get("revision"),
        dirty=data["dirty"],
        languages=tuple(data["languages"]),
        basis_default=GraphBasis(data["basis_default"]),
        tool_name=data["tool_name"],
        tool_version=data["tool_version"],
        indexed_at=datetime.fromisoformat(data["indexed_at"]),
        completeness=Completeness(data["completeness"]),
        limitations=tuple(
            Limitation(LimitationCode(item["code"]), item["message"], item["count"])
            for item in data["limitations"]
        ),
        files_indexed=data["files_indexed"],
        files_skipped=data["files_skipped"],
        nodes=node_count,
        edges=len({edge_identity(edge) for edge in edges}),
    )


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> ImportGraphResult:
    settings = ctx.config.section(KnowledgeSettings).graph
    kinds = validate_graph_import(cmd, settings.import_max_bytes)
    if not settings.enabled:
        raise PreconditionFailed(ErrorCode.MODULE_DISABLED, "The knowledge graph is disabled")

    workspace = ctx.scope_chain[-1].workspace_id
    if workspace is None:
        # The DTO has no workspace selector. An unscoped import needs a repository to resolve it.
        if cmd["repository_id"] is not None:
            raise NotFound(ErrorCode.NOT_FOUND, "Graph repository not found")
        raise invalid_graph_import("project_id", "workspace_required")
    project = ProjectId(UUID(cmd["project_id"])) if cmd["project_id"] else None
    repository = RepositoryId(UUID(cmd["repository_id"])) if cmd["repository_id"] else None
    if project is not None:
        require_active_project(uow, project)
    else:
        require_active_workspace(uow, workspace)
    if repository is not None:
        require_repository(uow, workspace, repository)

    repo = cast("_GraphWriter", uow.repo(GraphRepository))
    repo.lock_workspace(workspace)
    previous = repo.latest_index(workspace, cmd["source"], repository)
    if (
        previous is not None
        and previous.project_id != project
        and "memory.write" not in effective_permissions(uow, ctx.actor, workspace_ref(str(workspace)).id)
    ):
        raise Forbidden(ErrorCode.FORBIDDEN, "Graph source belongs to a different scope")
    keys = kinds.keys() | {key for edge in cmd["edges"] for key in (edge["src_key"], edge["dst_key"])}
    existing = repo.nodes_by_keys(workspace, frozenset(keys))
    nodes = _nodes(cmd, workspace, project, ctx, existing, kinds)
    edges, rejected = _edges(cmd, workspace, nodes, ctx, uow, existing)
    replace_existing = cmd.get("replace", True)
    index = _index(cmd, ctx, workspace, project, previous, len(nodes), edges)
    if not replace_existing and previous is not None and not index.same_snapshot(previous):
        raise invalid_graph_import("index", "append_snapshot_mismatch")
    counts = repo.write_source(
        workspace,
        cmd["source"],
        repository,
        tuple(nodes.values()),
        edges,
        replace_existing=replace_existing,
        index=index,
    )
    uow.record(GraphImported(workspace, cmd["source"], graph_imported_counts_from_json(counts)))
    return ImportGraphResult(
        index_id=str(index.id),
        generation=index.generation,
        nodes_upserted=cast("int", counts["nodes_upserted"]),
        nodes_removed=cast("int", counts["nodes_removed"]),
        edges_added=cast("int", counts["edges_added"]),
        edges_removed=cast("int", counts["edges_removed"]),
        edges_rejected=rejected,
    )


SPEC = CommandSpec(
    name="knowledge.import_graph",
    dto=cast("type[dict[str, Any]]", ImportGraph),
    result=ImportGraphResult,
    permission="memory.write",
    scope_of=None,
    scope_resolver=_scope,
    handler=handle,
    idempotency=IdempotencyMode.REQUIRED,
)
