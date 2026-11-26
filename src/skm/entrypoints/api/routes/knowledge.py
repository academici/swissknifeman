"""Knowledge routes for project memory, workspace lessons and graph queries."""

from collections.abc import Mapping
from typing import Any, override

from skm.application_bus.registry import IdempotencyMode
from skm.entrypoints.api.routing import Route
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.knowledge import contracts as knowledge

__all__ = ["ROUTES"]

_MEMORY = "/api/v1/projects/{project_id}/memory"
_LESSONS = "/api/v1/workspaces/{workspace_id}/lessons"
_GRAPH = "/api/v1/workspaces/{workspace_id}/graph"
_PROJECT = {"project_id": "project_id"}
_WORKSPACE = {"workspace_id": "workspace_id"}
_LESSON = {**_WORKSPACE, "lesson_id": "lesson_id"}
_SCOPE = {"scope": "scope.kind", "namespace": "scope.namespace"}
_TAGS = ("knowledge",)

_TRAVERSAL = {key: key for key in ("direction", "edge_types", "at_revision")}


class _GraphQueryRoute(Route):
    __slots__ = ()

    @override
    def bind(
        self, body: Mapping[str, Any], path: Mapping[str, str], query: Mapping[str, str], **kwargs: Any
    ) -> Any:
        fields = dict(body)
        scalars = dict(query)
        getlist = getattr(query, "getlist", None) or getattr(query, "get_list", None)
        for field in ("roots", "edge_types"):
            if field not in self.query_params or field not in scalars:
                continue
            raw = scalars.pop(field)
            values = [raw] if getlist is None else getlist(field)
            if field == "edge_types" and values == [""]:
                values = []
            if fields.setdefault(field, values) != values:
                raise ValidationFailed(ErrorCode.SCHEMA_INVALID, f"Conflicting values for {field}")
        return super().bind(fields, path, scalars, **kwargs)


class _HttpGraphNeighbors:
    SCHEMA_URN = "urn:skm:knowledge:query:graph-neighbors-http:v1"
    from_json = staticmethod(knowledge.GraphNeighbors.from_json)


class _GraphNeighborsRoute(_GraphQueryRoute):
    __slots__ = ()

    @property
    @override
    def dto_type(self) -> type[_HttpGraphNeighbors]:
        return _HttpGraphNeighbors

    @property
    @override
    def bus_name(self) -> str:
        return "knowledge.graph_neighbors"


class _HttpGraphIndexes:
    SCHEMA_URN = "urn:skm:knowledge:view:graph-indexes:v1"

    @staticmethod
    def from_json(data: Any) -> Any:
        return knowledge.GraphIndexesView.from_json({"items": data})


class _GraphIndexesRoute(Route):
    __slots__ = ()
    bus_result_type = knowledge.GraphIndexesView

    @staticmethod
    def response_body(payload: Mapping[str, Any]) -> Any:
        return payload["items"]


ROUTES = (
    Route(
        "GET",
        _MEMORY,
        knowledge.MemorySearchView,
        query=knowledge.SearchMemory,
        path_params=_PROJECT,
        query_params={**_SCOPE, "q": "query", "include_shared": "include_shared", "limit": "limit"},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "GET",
        _MEMORY + "/entries",
        knowledge.MemoryView,
        query=knowledge.ListMemory,
        path_params=_PROJECT,
        query_params={**_SCOPE, "include_expired": "include_expired", "after": "after", "limit": "limit"},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "POST",
        _MEMORY,
        knowledge.RememberResult,
        command=knowledge.Remember,
        path_params=_PROJECT,
        success_status=201,
        idempotency=IdempotencyMode.REQUIRED,
        tags=_TAGS,
    ),
    Route(
        "POST",
        _MEMORY + "/{entry_id}/forget",
        knowledge.ForgetResult,
        command=knowledge.Forget,
        path_params={**_PROJECT, "entry_id": "entry_id"},
        idempotency=IdempotencyMode.REQUIRED,
        tags=_TAGS,
    ),
    Route(
        "GET",
        _LESSONS,
        knowledge.LessonsView,
        query=knowledge.ListLessons,
        path_params=_WORKSPACE,
        query_params={key: key for key in ("project_id", "kind", "state", "after", "limit")},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "GET",
        _LESSONS + "/{lesson_id}",
        knowledge.GetLessonView,
        query=knowledge.GetLesson,
        path_params=_LESSON,
        body="none",
        etag_from="row_version",
        tags=_TAGS,
    ),
    Route(
        "POST",
        _LESSONS + "/{lesson_id}/deprecate",
        knowledge.DeprecateLessonResult,
        command=knowledge.DeprecateLesson,
        path_params=_LESSON,
        if_match_to="expected_row_version",
        idempotency=IdempotencyMode.REQUIRED,
        tags=_TAGS,
    ),
    _GraphNeighborsRoute(
        "GET",
        _GRAPH + "/neighbors",
        knowledge.GraphAnswer,
        query=knowledge.GraphNeighbors,
        path_params=_WORKSPACE,
        query_params={"node": "node_key", "depth": "depth", "project_id": "project_id", **_TRAVERSAL},
        body="none",
        tags=_TAGS,
    ),
    _GraphQueryRoute(
        "GET",
        _GRAPH + "/path",
        knowledge.GraphAnswer,
        query=knowledge.GraphPath,
        path_params=_WORKSPACE,
        query_params={"from": "src_key", "to": "dst_key", "project_id": "project_id", **_TRAVERSAL},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "GET",
        _GRAPH + "/stats",
        knowledge.GraphAnswer,
        query=knowledge.GraphStats,
        path_params=_WORKSPACE,
        query_params={"project_id": "project_id"},
        body="none",
        tags=_TAGS,
    ),
    _GraphQueryRoute(
        "GET",
        _GRAPH + "/subgraph",
        knowledge.GraphAnswer,
        query=knowledge.GraphSubgraph,
        path_params=_WORKSPACE,
        query_params={"roots": "roots", "depth": "depth", **_TRAVERSAL},
        body="none",
        tags=_TAGS,
    ),
    _GraphIndexesRoute(
        "GET",
        _GRAPH + "/indexes",
        _HttpGraphIndexes,
        query=knowledge.ListGraphIndexes,
        path_params=_WORKSPACE,
        query_params={"repository_id": "repository_id", "source": "source"},
        body="none",
        tags=_TAGS,
    ),
    Route(
        "POST",
        _GRAPH + "/import",
        knowledge.ImportGraphResult,
        command=knowledge.ImportGraph,
        path_params=_WORKSPACE,
        idempotency=IdempotencyMode.REQUIRED,
        body_limit_key="knowledge.graph.import_max_bytes",
        tags=_TAGS,
    ),
)
