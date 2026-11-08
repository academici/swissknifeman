"""Pure MCP projection: a value-free server catalog and per-provider bindings become native files.

The functions take parsed documents and caller-owned artifact sources; nothing here reads a file,
names a catalog location or labels a source. Error codes are stable strings (``HARNESS_*``)
because callers and recorded evidence already depend on them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..artifacts.artifact import (
    ArtifactAdapterIdentity,
    ArtifactRenderRequest,
    ArtifactSource,
    ArtifactTarget,
    plan_artifact_render,
)
from .values import ProviderId

_ARTIFACT_PROVIDERS = (ProviderId.CODEX, ProviderId.CURSOR, ProviderId.GROK, ProviderId.ANTIGRAVITY)


@dataclass(frozen=True)
class McpServer:
    id: str
    transport: str
    capability_id: str
    secret_refs: tuple[str, ...]


@dataclass(frozen=True)
class McpProjection:
    provider_id: ProviderId
    target_scope: str
    target_path: str
    servers: tuple[tuple[str, dict], ...]
    secret_refs: tuple[str, ...]


def parse_mcp_catalog(document: Mapping) -> tuple[McpServer, ...]:
    """Validate the common, value-free MCP inventory and keep its declared order."""
    value = document
    if not isinstance(value, dict) or set(value) != {"catalog_version", "servers"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    rows = value["servers"]
    if value["catalog_version"] != "1.0.0" or not isinstance(rows, list):
        raise ValueError("HARNESS_VERSION_UNSUPPORTED")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "transport", "capability_id", "secret_refs"}:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        if (not isinstance(row["id"], str) or not row["id"]
                or row["transport"] not in {"http", "stdio"}
                or not isinstance(row["capability_id"], str)
                or not isinstance(row["secret_refs"], list)
                or len(set(row["secret_refs"])) != len(row["secret_refs"])):
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        result.append(McpServer(row["id"], row["transport"], row["capability_id"],
                                tuple(row["secret_refs"])))
    if not result or len({item.id for item in result}) != len(result):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return tuple(result)


def plan_mcp_projection(catalog: Sequence[McpServer], *, provider_id: ProviderId, bindings: Mapping,
                        selected: Sequence[str], trusted: bool) -> McpProjection:
    """Return one independent native projection, without writing a target or lock."""
    if not trusted:
        raise ValueError("HARNESS_TRUST_REQUIRED")
    selected = tuple(selected)
    ids = {server.id for server in catalog}
    if len(set(selected)) != len(selected) or set(selected) - ids:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    projection = bindings
    if (not isinstance(projection, dict)
            or set(projection) != {"binding_version", "provider_id", "target_scope",
                                   "target_path", "servers"}
            or projection["binding_version"] != "1.0.0"
            or projection["provider_id"] != provider_id.value):
        raise ValueError("HARNESS_MAPPING_MISSING")
    if (not isinstance(projection["target_scope"], str)
            or not isinstance(projection["target_path"], str)
            or not isinstance(projection["servers"], dict)):
        raise ValueError("HARNESS_MAPPING_MISSING")
    rendered = []
    for server_id in selected:
        record = projection["servers"].get(server_id)
        if not isinstance(record, dict):
            raise ValueError("HARNESS_MAPPING_MISSING")
        server = next(server for server in catalog if server.id == server_id)
        _validate_secret_references(server, record)
        rendered.append((server_id, record))
    refs = tuple(sorted({ref for server_id in selected for server in catalog
                         if server.id == server_id for ref in server.secret_refs}))
    return McpProjection(provider_id, projection["target_scope"], projection["target_path"],
                         tuple(rendered), refs)


def _validate_secret_references(server: McpServer, record: Mapping) -> None:
    """Only declared placeholder references may cross the projection boundary."""
    if "secret_value" in record:
        raise ValueError("HARNESS_SECRET_VALUE_EXPOSED")
    env = record.get("env", {})
    if not isinstance(env, dict):
        raise ValueError("HARNESS_MAPPING_MISSING")
    expected = {"${" + ref.upper().replace("-", "_") + "}" for ref in server.secret_refs}
    observed = set()
    for value in env.values():
        if not isinstance(value, str) or not value.startswith("${") or not value.endswith("}"):
            raise ValueError("HARNESS_SECRET_VALUE_EXPOSED")
        observed.add(value)
    if observed != expected:
        raise ValueError("HARNESS_SECRET_REFERENCE_MISSING")


def render_mcp_projection(plan: McpProjection) -> bytes:
    """Serialize only the named projection; each provider keeps its own native shape."""
    if plan.provider_id in (ProviderId.CLAUDE_CODE, ProviderId.CURSOR):
        return (json.dumps({"mcpServers": dict(plan.servers)}, ensure_ascii=False, indent=2)
                + "\n").encode("utf-8")
    # Codex and Grok share [mcp_servers.<id>] TOML.
    lines = []
    for server_id, binding in plan.servers:
        lines.append(f"[mcp_servers.{server_id}]")
        for field in ("url", "command"):
            if field in binding:
                lines.append(f'{field} = {json.dumps(binding[field], ensure_ascii=False)}')
        if "args" in binding:
            lines.append("args = " + json.dumps(binding["args"], ensure_ascii=False))
        if "env" in binding:
            env = binding["env"]
            lines.append("env = {" + ", ".join(
                f"{json.dumps(key, ensure_ascii=False)} = {json.dumps(value, ensure_ascii=False)}"
                for key, value in sorted(env.items())) + "}")
        lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def plan_mcp_artifact(plan: McpProjection, *, sources: Sequence[ArtifactSource], adapter_id: str,
                      adapter_version: str = "1.0.0"):
    """Plan a whole-file Codex/Cursor/Grok artifact; the caller names sources and adapter.

    ``sources`` are the caller's :class:`ArtifactSource` records (catalog and bindings with their
    digests); ``adapter_id`` is the caller's adapter name, recorded in the lock identity."""
    if plan.provider_id not in _ARTIFACT_PROVIDERS:
        raise ValueError("HARNESS_MAPPING_MISSING")
    sources = tuple(sources)
    if not sources or not all(isinstance(source, ArtifactSource) for source in sources):
        raise TypeError("sources must be a non-empty sequence of ArtifactSource")
    identity = ArtifactAdapterIdentity(adapter_id, adapter_version, plan.provider_id, "1.0.0", ())
    return plan_artifact_render(ArtifactRenderRequest(
        f"{adapter_id}." + ".".join(server_id for server_id, _ in plan.servers),
        sources,
        ArtifactTarget(plan.target_path, ("whole-file", ())), identity, (),
        {"target_scope": plan.target_scope, "server_ids": [server_id for server_id, _ in plan.servers],
         "secret_refs": list(plan.secret_refs)},
        lambda _request: render_mcp_projection(plan)))
