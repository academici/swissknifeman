"""Provider-aware, caller-owned MCP deployment planning.

mAInd owns semantic server selection; harness owns provider target, trust validation and
serialization through its immutable MCP projection API.
"""
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType

from core import ProviderId


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
    status: str = "planned"


@dataclass(frozen=True)
class ProviderDeployPlan:
    results: tuple[ProviderDeployResult, ...]

    @property
    def green(self):
        return bool(self.results) and all(row.status == "planned" for row in self.results)


def semantic_servers(*, maind, agentmemory=None, codegraph=None, perplexity=None):
    """Create the caller-owned semantic inventory without provider/path branching."""
    values = [("maind", maind, True), ("agentmemory", agentmemory, False),
              ("codegraph", codegraph, True), ("perplexity", perplexity, True)]
    rows = tuple(SemanticServer(name, MappingProxyType(dict(binding)), required)
                 for name, binding, required in values if binding is not None)
    if len({row.id for row in rows}) != len(rows):
        raise ProviderDeployError("MAIND_SEMANTIC_SERVER_DUPLICATE")
    return rows


def plan_provider_deploy(base_projections, servers):
    """Project caller-owned descriptors through P5-owned target/serialization records."""
    from harness.mcp import McpProjection, render_mcp_projection
    base_projections = tuple(base_projections)
    servers = tuple(servers)
    if not base_projections or len({item.provider_id for item in base_projections}) != len(base_projections):
        raise ProviderDeployError("MAIND_PROVIDER_DUPLICATE")
    if len({item.id for item in servers}) != len(servers):
        raise ProviderDeployError("MAIND_SEMANTIC_SERVER_DUPLICATE")
    entries = tuple((item.id, dict(item.binding)) for item in servers)
    results = []
    for base in base_projections:
        projection = McpProjection(base.provider_id, base.target_scope, base.target_path,
                                   entries, tuple())
        results.append(ProviderDeployResult(base.provider_id, base.target_scope,
                                             base.target_path, render_mcp_projection(projection),
                                             tuple(item.id for item in servers)))
    return ProviderDeployPlan(tuple(results))
