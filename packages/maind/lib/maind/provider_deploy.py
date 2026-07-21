"""Provider-aware, caller-owned MCP deployment planning.

mAInd owns semantic server selection; harness owns provider target, trust validation and
serialization through its immutable MCP projection API.
"""
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType
from pathlib import Path

from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, ProviderId, canonical_json_bytes,
                  plan_artifact_render, sha256_digest)
from .common import atomic_write_text


class ProviderDeployError(ValueError):
    """Stable no-write deployment planning failure."""


@dataclass(frozen=True)
class SemanticServer:
    id: str
    binding: dict
    required: bool = True

    def __post_init__(self):
        if not self.id or not isinstance(self.binding, Mapping):
            raise ProviderDeployError("MAIND_SEMANTIC_SERVER_INVALID")


@dataclass(frozen=True)
class ProviderDeployResult:
    provider_id: ProviderId
    target_scope: str
    target_path: str
    rendered: bytes
    server_ids: tuple[str, ...]
    status: str
    diagnostic: str | None = None
    artifact: object | None = None


@dataclass(frozen=True)
class ProviderDeployPlan:
    results: tuple[ProviderDeployResult, ...]

    @property
    def green(self):
        return bool(self.results) and all(row.status == "planned" for row in self.results)

    @property
    def diagnostics(self):
        return tuple(row.diagnostic for row in self.results if row.diagnostic)


def semantic_servers(*, maind, agentmemory=None, codegraph=None, perplexity=None):
    """Create the caller-owned semantic inventory without provider/path branching."""
    values = [("maind", maind, True), ("agentmemory", agentmemory, False),
              ("codegraph", codegraph, True), ("perplexity", perplexity, True)]
    rows = tuple(SemanticServer(name, MappingProxyType(dict(binding)), required)
                 for name, binding, required in values if binding is not None)
    if len({row.id for row in rows}) != len(rows):
        raise ProviderDeployError("MAIND_SEMANTIC_SERVER_DUPLICATE")
    return rows


def plan_provider_deploy(base_projections, servers, *, selected=None, required_providers=None,
                         disabled=()):
    """Project caller-owned descriptors through P5-owned target/serialization records."""
    from harness.mcp import McpProjection, render_mcp_projection
    base_projections = tuple(base_projections)
    servers = tuple(servers)
    if len({item.provider_id for item in base_projections}) != len(base_projections):
        raise ProviderDeployError("MAIND_PROVIDER_DUPLICATE")
    if len({item.id for item in servers}) != len(servers):
        raise ProviderDeployError("MAIND_SEMANTIC_SERVER_DUPLICATE")
    known = {item.provider_id: item for item in base_projections}
    selected = tuple(selected or known)
    required = frozenset(required_providers or selected)
    disabled = frozenset(disabled)
    if len(set(selected)) != len(selected):
        raise ProviderDeployError("MAIND_PROVIDER_DUPLICATE")
    entries = tuple((item.id, dict(item.binding)) for item in servers)
    source_bytes = canonical_json_bytes({"servers": [{"id": item.id, "binding": dict(item.binding)}
                                               for item in servers]})
    source = ArtifactSource("maind.provider-deploy.semantic-inventory",
                            "packages/maind/provider_deploy.py", sha256_digest(source_bytes))
    results = []
    for provider_id in selected:
        if provider_id in disabled:
            results.append(ProviderDeployResult(provider_id, "", "", b"", (), "disabled",
                                                "MAIND_PROVIDER_DISABLED"))
            continue
        base = known.get(provider_id)
        if base is None:
            results.append(ProviderDeployResult(provider_id, "", "", b"", (), "failed",
                                                "MAIND_PROJECTION_MISSING"))
            continue
        projection = McpProjection(base.provider_id, base.target_scope, base.target_path,
                                   entries, tuple())
        rendered = render_mcp_projection(projection)
        artifact = plan_artifact_render(ArtifactRenderRequest(
            "maind.provider-deploy." + provider_id.value,
            (source,), ArtifactTarget(base.target_path, ("whole-file", ())),
            ArtifactAdapterIdentity("maind.provider-deploy", "1.0.0", provider_id, "1.1.0", ()),
            (), {"target_scope": base.target_scope, "server_ids": [item.id for item in servers]},
            lambda _request, value=rendered: value))
        results.append(ProviderDeployResult(provider_id, base.target_scope, base.target_path,
                                             rendered, tuple(item.id for item in servers), "planned",
                                             artifact=artifact))
    if required - {row.provider_id for row in results}:
        raise ProviderDeployError("MAIND_PROJECTION_MISSING")
    return ProviderDeployPlan(tuple(results))


def conformance_report(plan):
    """Stable, value-free P6 evidence for an already-planned provider deployment."""
    rows = ["# P6 provider deploy conformance", "", "| Provider | Target | Status | Servers |",
            "|:--|:--|:--|:--|"]
    for row in plan.results:
        rows.append(f"| {row.provider_id.value} | {row.target_path or '—'} | {row.status} | "
                    + ", ".join(row.server_ids) + " |")
    rows.extend(["", f"**Aggregate:** {'GREEN' if plan.green else 'RED'}", ""])
    return "\n".join(rows)


def write_conformance_report(path, plan):
    """Persist only generated P6 evidence, never provider target output."""
    atomic_write_text(Path(path), conformance_report(plan))
