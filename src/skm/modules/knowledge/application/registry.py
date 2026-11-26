"""Bind generated JSON-mode records to the bus's nominal DTO interface."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import AnyCommandSpec, AnyQuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, NotFound, PreconditionFailed
from skm.kernel.ids import ProjectId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRef
from skm.modules.knowledge import contracts
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.workspace.public import workspace_of_project

from .commands.deprecate_lesson import SPEC as DEPRECATE_LESSON
from .commands.expire_memory import SPEC as EXPIRE_MEMORY
from .commands.forget import SPEC as FORGET
from .commands.import_graph import SPEC as IMPORT_GRAPH
from .commands.remember import SPEC as REMEMBER
from .queries.get_lesson import SPEC as GET_LESSON
from .queries.graph_indexes import SPEC as GRAPH_INDEXES
from .queries.graph_neighbors import SPEC as GRAPH_NEIGHBORS
from .queries.graph_path import SPEC as GRAPH_PATH
from .queries.graph_stats import SPEC as GRAPH_STATS
from .queries.graph_subgraph import SPEC as GRAPH_SUBGRAPH
from .queries.graph_subgraph import project_graph
from .queries.list_lessons import SPEC as LIST_LESSONS
from .queries.list_memory import SPEC as LIST_MEMORY
from .queries.search_memory import SPEC as SEARCH_MEMORY
from .scopes import project_ref, workspace_ref


def _bind[S: (AnyCommandSpec, AnyQuerySpec)](spec: S, dto: type[Any], result: type[Any]) -> S:
    def handle(cmd: Any, ctx: Any, uow: Any) -> Any:
        return result.from_json(spec.handler(cmd, ctx, uow))

    return replace(spec, dto=dto, result=result, handler=handle)


def _import_scope(cmd: dict[str, Any], uow: UnitOfWork) -> ScopeRef | None:
    resolve = IMPORT_GRAPH.scope_resolver
    if resolve is None:
        raise InternalError(ErrorCode.INTERNAL_ERROR, "Graph import scope resolver is unavailable")
    if "workspace_id" not in cmd:
        return resolve(cmd, uow)
    workspace = workspace_ref(cmd["workspace_id"])
    if (project := cmd["project_id"]) is None:
        return workspace
    if workspace_of_project(uow, ProjectId(UUID(project))) != workspace.id:
        raise NotFound(ErrorCode.NOT_FOUND, "Graph project not found in this workspace")
    return resolve(cmd, uow)


def _project_graph(spec: AnyQuerySpec, dto: type[Any]) -> AnyQuerySpec:
    def handle(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> Any:
        return project_graph(query, ctx, uow) if "project_id" in query else spec.handler(query, ctx, uow)

    return _bind(
        _guard_graph(replace(spec, handler=handle, scope_of=_graph_scope)), dto, contracts.GraphAnswer
    )


def _graph_scope(query: dict[str, Any]) -> ScopeRef:
    return project_ref(query.get("project_id")) or workspace_ref(query["workspace_id"])


def _guard_graph(spec: AnyQuerySpec) -> AnyQuerySpec:
    def handle(query: dict[str, Any], ctx: QueryContext, uow: UnitOfWork) -> Any:
        if not ctx.config.section(KnowledgeSettings).graph.enabled:
            raise PreconditionFailed(ErrorCode.MODULE_DISABLED, "The knowledge graph is disabled")
        return spec.handler(query, ctx, uow)

    return replace(spec, handler=handle)


COMMANDS = (
    _bind(
        replace(IMPORT_GRAPH, scope_resolver=_import_scope),
        contracts.ImportGraph,
        contracts.ImportGraphResult,
    ),
    _bind(REMEMBER, contracts.Remember, contracts.RememberResult),
    _bind(FORGET, contracts.Forget, contracts.ForgetResult),
    _bind(EXPIRE_MEMORY, contracts.ExpireMemory, contracts.ExpireMemoryResult),
    _bind(DEPRECATE_LESSON, contracts.DeprecateLesson, contracts.DeprecateLessonResult),
)
QUERIES = (
    _bind(SEARCH_MEMORY, contracts.SearchMemory, contracts.MemorySearchView),
    _bind(LIST_MEMORY, contracts.ListMemory, contracts.MemoryView),
    _bind(LIST_LESSONS, contracts.ListLessons, contracts.LessonsView),
    _bind(GET_LESSON, contracts.GetLesson, contracts.GetLessonView),
    _project_graph(GRAPH_NEIGHBORS, contracts.GraphNeighbors),
    _project_graph(GRAPH_PATH, contracts.GraphPath),
    _bind(
        _guard_graph(replace(GRAPH_STATS, scope_of=_graph_scope)), contracts.GraphStats, contracts.GraphAnswer
    ),
    _bind(_guard_graph(GRAPH_SUBGRAPH), contracts.GraphSubgraph, contracts.GraphAnswer),
    _guard_graph(GRAPH_INDEXES),
)
