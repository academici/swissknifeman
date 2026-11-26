"""Knowledge wire DTOs and results for clients and route discovery."""

import json
import re
from collections.abc import Callable
from typing import Any, Self, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.schema.registry import SchemaRegistry

from .domain.graph import NodeType, parse_node_key
from .generated import commands, documents, queries, results, views

_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_LANGUAGE = re.compile(r"[a-z][a-z0-9+#-]{0,31}")


def _model(name: str, schema: str, parse: Callable[[Any], Any]) -> type[Any]:
    class JsonRecord(dict[str, Any]):
        SCHEMA_URN = f"urn:skm:knowledge:{schema}:v1"

        @classmethod
        def from_json(cls, data: Any) -> Self:
            return cls(parse(data))

        def to_json(self) -> Any:
            return parse(self)

    JsonRecord.__name__ = name
    return JsonRecord


DeprecateLesson = _model("DeprecateLesson", "command:deprecate-lesson", commands.deprecate_lesson_from_json)
DeprecateLessonResult = _model(
    "DeprecateLessonResult", "result:deprecate-lesson", results.deprecate_lesson_result_from_json
)
ExpireMemory = _model("ExpireMemory", "command:expire-memory", commands.expire_memory_from_json)
ExpireMemoryResult = _model(
    "ExpireMemoryResult", "result:expire-memory", results.expire_memory_result_from_json
)
Forget = _model("Forget", "command:forget", commands.forget_from_json)
ForgetResult = _model("ForgetResult", "result:forget", results.forget_result_from_json)
ImportGraph = _model("ImportGraph", "command:import-graph", commands.import_graph_from_json)
ImportGraphResult = _model("ImportGraphResult", "result:import-graph", results.import_graph_result_from_json)
Remember = _model("Remember", "command:remember", commands.remember_from_json)
RememberResult = _model("RememberResult", "result:remember", results.remember_result_from_json)

GetLesson = _model("GetLesson", "query:get-lesson", queries.get_lesson_from_json)
GetLessonView = _model(views.LessonViewDefsLessonView.__name__, "view:lesson", views.lesson_view_from_json)
GraphNeighbors = _model("GraphNeighbors", "query:graph-neighbors", queries.graph_neighbors_from_json)
GraphPath = _model("GraphPath", "query:graph-path", queries.graph_path_from_json)
GraphStats = _model("GraphStats", "query:graph-stats", queries.graph_stats_from_json)
GraphSubgraph = _model("GraphSubgraph", "query:graph-subgraph", queries.graph_subgraph_from_json)
ListGraphIndexes = _model(
    "ListGraphIndexes", "query:list-graph-indexes", queries.list_graph_indexes_from_json
)
GraphAnswer = _model("GraphAnswer", "graph-answer", documents.graph_answer_from_json)
ListLessons = _model("ListLessons", "query:list-lessons", queries.list_lessons_from_json)
LessonsView = _model("LessonsView", "view:lessons", views.lessons_view_from_json)
ListMemory = _model("ListMemory", "query:list-memory", queries.list_memory_from_json)
MemoryView = _model("MemoryView", "view:memory", views.memory_view_from_json)
SearchMemory = _model("SearchMemory", "query:search-memory", queries.search_memory_from_json)
MemorySearchView = _model("MemorySearchView", "view:memory-search", views.memory_search_view_from_json)


class GraphIndexesView(dict[str, list[views.GraphIndexView]]):
    SCHEMA_URN = "urn:skm:knowledge:view:graph-indexes-result:v1"

    @classmethod
    def from_json(cls, data: Any) -> Self:
        items = data["items"]
        if not isinstance(items, list):
            raise ValueError("Expected a list of graph indexes")
        return cls(items=[views.graph_index_view_from_json(item) for item in cast("list[Any]", items)])

    def to_json(self) -> dict[str, list[views.GraphIndexView]]:
        return dict(self)


def invalid_graph_import(field: str, reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID, "Invalid graph import", details={"field": field, "reason": reason}
    )


def _attrs(value: JsonValue, *, limit: int) -> None:
    # The storage ceiling is measured on jsonb's spaced representation.
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) >= limit:
        raise invalid_graph_import("attrs", "too_large")
    if "\\u0000" in encoded:
        # PostgreSQL jsonb cannot represent a NUL in keys or values. A literal backslash-u is allowed.
        def has_nul(item: JsonValue) -> bool:
            if isinstance(item, str):
                return "\x00" in item
            if isinstance(item, dict):
                return any(has_nul(key) or has_nul(child) for key, child in item.items())
            if isinstance(item, list):
                return any(map(has_nul, item))
            return False

        if has_nul(value):
            raise invalid_graph_import("attrs", "nul_character")


def graph_import_size(value: object) -> int:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        return len(encoded.encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise invalid_graph_import("import_graph", "invalid_json") from error


def validate_graph_import(cmd: dict[str, Any], max_bytes: int) -> dict[str, NodeType]:
    """Check the deterministic constraints shared by the command and host preflight."""
    if graph_import_size(cmd) > max_bytes:
        raise invalid_graph_import("import_graph", "too_large")
    kinds: dict[str, NodeType] = {}
    for item in cmd["nodes"]:
        key = item["node_key"]
        if "\x00" in key:
            raise invalid_graph_import("node_key", "nul_character")
        try:
            kind, _ = parse_node_key(key)
        except ValueError:
            raise invalid_graph_import("node_key", "invalid_key") from None
        if kind != item["type"]:
            raise invalid_graph_import("node_key", "type_mismatch")
        _attrs(item["attrs"], limit=16384)
        kinds[key] = kind
    for item in cmd["edges"]:
        if "\x00" in item["src_key"] or "\x00" in item["dst_key"]:
            raise invalid_graph_import("node_key", "nul_character")
        if len(item["source_key"]) > 300 or "\x00" in item["source_key"]:
            raise invalid_graph_import("source_key", "invalid_key")
        _attrs(item["attrs"], limit=8192)

    data = cmd["index"]
    revision = data.get("revision")
    if revision is not None and _REVISION.fullmatch(revision) is None:
        raise invalid_graph_import("index.revision", "invalid_revision")
    if any(_LANGUAGE.fullmatch(language) is None for language in data["languages"]):
        raise invalid_graph_import("index.languages", "invalid_language")
    if any("\x00" in data[key] for key in ("tool_name", "tool_version")) or any(
        "\x00" in limit["message"] for limit in data["limitations"]
    ):
        raise invalid_graph_import("index", "nul_character")
    return kinds


def parse_import_graph(payload: JsonObject) -> Any:
    """Preflight the complete command before changing any active graph generation."""
    SchemaRegistry.load_default().require_valid(ImportGraph.SCHEMA_URN, payload)
    return ImportGraph.from_json(payload)
