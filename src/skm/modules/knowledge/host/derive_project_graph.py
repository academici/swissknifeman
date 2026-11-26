"""Derive declared package relationships using a checkout's manifest reader."""

from hashlib import sha256
from typing import Protocol, cast

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.languages import language_for_ecosystem
from skm.modules.knowledge.domain.graph import NodeType, node_key
from skm.modules.knowledge.ports import ManifestReader

from .import_code_graph import checkout, graph_limit, import_snapshot, project_config

__all__ = ["DeriveProjectGraphOperation", "derive_project_graph"]


class DeriveProjectGraphOperation(Protocol):
    def __call__(self, ctx: HostContext, request: JsonObject) -> JsonObject: ...


class _ManifestSnapshotReader(ManifestReader, Protocol):
    def read_snapshot(self, root: str) -> tuple[str, tuple[JsonObject, ...]]: ...


def derive_project_graph(ctx: HostContext, request: JsonObject) -> JsonObject:
    target = checkout(ctx, request)
    max_bytes = graph_limit(project_config(ctx, target))
    reader = cast("_ManifestSnapshotReader", ctx.gateways.get(ManifestReader))
    indexed_at, records = reader.read_snapshot(target.root)
    project = node_key(NodeType.PROJECT, target.project_id)
    nodes: dict[str, JsonObject] = {project: {"node_key": project, "type": "project", "attrs": {}}}
    edges: list[JsonObject] = []
    languages: set[str] = set()
    files: set[str] = set()
    for record in records:
        ecosystem, name, path = (str(record[key]) for key in ("ecosystem", "package", "path"))
        language = language_for_ecosystem(ecosystem)
        if language is not None:
            languages.add(language)
        files.add(path)
        # Package declarations from different projects have independent graph ownership.
        try:
            package = node_key(NodeType.PACKAGE, f"{target.repository_id}:{ecosystem}:{name}")
        except ValueError as error:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid manifest package name") from error
        nodes[package] = {
            "node_key": package,
            "type": "package",
            "attrs": {"name": name, "ecosystem": ecosystem},
        }
        relation = record["relationship"]
        src, dst = (package, project) if relation == "provided_by" else (project, package)
        version = record["version"]
        occurrence = sha256(f"{path}\0{version}".encode()).hexdigest()
        edges.append(
            {
                "src_key": src,
                "dst_key": dst,
                "type": relation,
                "source_key": occurrence,
                "attrs": {"manifest": path, "version": version},
            }
        )
    index: JsonObject = {
        "revision": None,
        "dirty": False,
        "languages": list[JsonValue](sorted(languages)),
        "basis_default": "declared",
        "tool_name": "skm",
        "tool_version": "1",
        "indexed_at": indexed_at,
        "completeness": "partial",
        "limitations": [],
        "files_indexed": len(files),
        "files_skipped": 0,
    }
    return import_snapshot(ctx, target, "manifests", index, list(nodes.values()), edges, max_bytes)
