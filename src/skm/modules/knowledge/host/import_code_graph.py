"""Import the bound checkout's read-only code graph through the command bus."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.knowledge.contracts import graph_import_size, parse_import_graph, validate_graph_import
from skm.modules.knowledge.domain.graph import NodeType, node_key
from skm.modules.knowledge.generated.settings import KnowledgeCodeGraphSettings
from skm.modules.knowledge.ports import CodeGraphReader, GraphCheckoutResolver
from skm.modules.workspace.public import GetProject, ProjectView
from skm.platform.jsonc.digest import digest

__all__ = ["ImportCodeGraphOperation", "import_code_graph"]


class ImportCodeGraphOperation(Protocol):
    def __call__(self, ctx: HostContext, request: JsonObject) -> JsonObject: ...


class _SnapshotReader(CodeGraphReader, Protocol):
    def read_index(
        self, root: str, settings: KnowledgeCodeGraphSettings
    ) -> tuple[JsonObject, list[JsonObject], list[JsonObject]]: ...


class _Config(Protocol):
    def get(self, key: str) -> JsonValue: ...


@dataclass(frozen=True, slots=True)
class Checkout:
    project_id: str
    workspace_id: str
    repository_id: str
    root: str


def checkout(ctx: HostContext, request: JsonObject) -> Checkout:
    project_id = ProjectId(UUID(str(request["project_id"])))
    if not ctx.gateways.has(GraphCheckoutResolver):
        raise PreconditionFailed(ErrorCode.CHECKOUT_UNBOUND, "Graph import requires a local checkout binding")
    project = cast("ProjectView", ctx.client.ask(GetProject(project_id=project_id)))
    mount = str(request.get("mount") or "main")
    repository_id, root = ctx.gateways.get(GraphCheckoutResolver).resolve_graph(project_id, mount)
    return Checkout(str(project_id), str(project.workspace_id), str(repository_id), root)


def project_config(ctx: HostContext, target: Checkout) -> _Config:
    resolver = getattr(ctx.config, "for_project", None)
    return cast("_Config", resolver(target.project_id) if callable(resolver) else ctx.config)


def graph_limit(config: _Config) -> int:
    if config.get("knowledge.graph.enabled") is not True:
        raise PreconditionFailed(ErrorCode.MODULE_DISABLED, "The knowledge graph is disabled")
    limit = config.get("knowledge.graph.import_max_bytes")
    if type(limit) is not int or limit <= 0:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Graph import byte limit is invalid")
    return limit


def _code_settings(host: _Config, project: _Config) -> KnowledgeCodeGraphSettings:
    keys = (
        "enabled",
        "argv",
        "index_argv",
        "ignores",
        "serena_schema_pin",
        "stale_after_hours",
        "keep_generations",
    )
    return KnowledgeCodeGraphSettings.from_settings(
        {
            "knowledge.code_graph." + key: (
                host if key in {"argv", "index_argv", "serena_schema_pin"} else project
            ).get("knowledge.code_graph." + key)
            for key in keys
        }
    )


def _chunks(
    envelope: JsonObject, nodes: Sequence[JsonObject], edges: Sequence[JsonObject], max_bytes: int
) -> Iterable[JsonObject]:
    current: JsonObject = {**envelope, "replace": True}
    node_items: list[JsonValue] = []
    edge_items: list[JsonValue] = []
    used = graph_import_size({**current, "nodes": [], "edges": []})
    append_size = graph_import_size({**current, "replace": False, "nodes": [], "edges": []})
    if used > max_bytes:
        raise ValidationFailed(ErrorCode.PAYLOAD_TOO_LARGE, "Graph import metadata exceeds the byte limit")

    # Send nodes before any edges that refer to them. Each array and all separators count.
    for field, items, cap in (("nodes", nodes, 20_000), ("edges", edges, 50_000)):
        for item in items:
            size = graph_import_size(item)
            dest = node_items if field == "nodes" else edge_items
            if used + size + bool(dest) > max_bytes or len(dest) == cap:
                if node_items or edge_items:
                    yield {**current, "nodes": node_items, "edges": edge_items}
                    current = {**envelope, "replace": False}
                    node_items, edge_items = [], []
                    dest = node_items if field == "nodes" else edge_items
                    used = append_size
                if used + size > max_bytes:
                    raise ValidationFailed(
                        ErrorCode.PAYLOAD_TOO_LARGE,
                        "One graph record exceeds the import byte limit",
                        details={"field": field},
                    )
            used += size + bool(dest)
            dest.append(item)
    yield {**current, "nodes": node_items, "edges": edge_items}


def import_snapshot(
    ctx: HostContext,
    target: Checkout,
    source: str,
    index: JsonObject,
    nodes: Sequence[JsonObject],
    edges: Sequence[JsonObject],
    max_bytes: int,
) -> JsonObject:
    envelope: JsonObject = {
        "workspace_id": target.workspace_id,
        "project_id": target.project_id,
        "repository_id": target.repository_id,
        "source": source,
        "index": index,
    }
    commands = [parse_import_graph(chunk) for chunk in _chunks(envelope, nodes, edges, max_bytes)]
    for command in commands:
        validate_graph_import(command, max_bytes)
    totals = dict.fromkeys(("nodes_upserted", "nodes_removed", "edges_added", "edges_removed"), 0)
    rejected: list[JsonValue] = []
    result: JsonObject = {}
    for command in commands:
        ctx.cancel.raise_if_cancelled()
        result = cast(
            "JsonObject", ctx.client.dispatch(command, idempotency_key=ctx.client.new_idempotency_key())
        )
        for field in totals:
            totals[field] += cast("int", result[field])
        rejected.extend(cast("list[JsonValue]", result["edges_rejected"]))
    return {
        **totals,
        "edges_rejected": rejected,
        "generation": result["generation"],
        "index_id": result["index_id"],
        "chunks": len(commands),
        "source": source,
    }


def _symbol(record: Mapping[str, JsonValue], repository: str) -> str:
    path, name = record["path"], record["qualified_name"]
    if not isinstance(path, str) or not isinstance(name, str) or not name:
        raise ValueError
    return node_key(NodeType.SYMBOL, f"{repository}:{path}#{name}")


def _code_graph(
    repository: str, symbols: Iterable[JsonObject], references: Iterable[JsonObject]
) -> tuple[list[JsonObject], list[JsonObject]]:
    nodes: dict[str, JsonObject] = {}
    edges: list[JsonObject] = []
    for symbol in symbols:
        key = _symbol(symbol, repository)
        doc = node_key(NodeType.DOC, f"{repository}:{symbol['path']}")
        nodes[doc] = {"node_key": doc, "type": "doc", "attrs": {"path": symbol["path"]}}
        nodes[key] = {"node_key": key, "type": "symbol", "attrs": symbol}
        edges.append({"src_key": key, "dst_key": doc, "type": "belongs_to", "source_key": "", "attrs": {}})
    for reference in references:
        origin = cast("JsonObject", reference["src"])
        src = _symbol(origin, repository)
        dst = _symbol(cast("JsonObject", reference["dst"]), repository)
        if src not in nodes or dst not in nodes:
            raise ValueError
        attrs = reference.get("attrs", {})
        source_key = reference.get("source_key")
        if "source_key" not in reference:
            occurrence = reference.get("location")
            location = {
                **(attrs if isinstance(attrs, dict) else {}),
                **(occurrence if isinstance(occurrence, dict) else {}),
                **reference,
            }
            source_key = digest(
                {
                    "path": location.get("path", location.get("file", origin["path"])),
                    "line": location.get("line"),
                    "column": location.get("column", location.get("col")),
                    "kind": location.get("kind"),
                    "target": dst,
                }
            )
        edges.append(
            {
                "src_key": src,
                "dst_key": dst,
                "type": "references",
                "source_key": source_key,
                "attrs": attrs,
            }
        )
    return list(nodes.values()), edges


def import_code_graph(ctx: HostContext, request: JsonObject) -> JsonObject:
    target = checkout(ctx, request)
    config = project_config(ctx, target)
    max_bytes = graph_limit(config)
    settings = _code_settings(cast("_Config", ctx.config), config)
    reader = cast("_SnapshotReader", ctx.gateways.get(CodeGraphReader))
    index, symbols, references = reader.read_index(target.root, settings)
    try:
        nodes, edges = _code_graph(target.repository_id, symbols, references)
    except (KeyError, TypeError, ValueError) as error:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid Serena symbol or reference") from error
    return import_snapshot(ctx, target, "serena", index, nodes, edges, max_bytes)
