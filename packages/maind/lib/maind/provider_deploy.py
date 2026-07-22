"""Provider-aware, caller-owned MCP deployment planning.

mAInd owns semantic server selection; harness owns provider target, trust validation and
serialization through its immutable MCP projection API.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType
from pathlib import Path
import sys

from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, CapabilityId, CapabilityRequirement, ProviderId,
                  SupportLevel, canonical_json_bytes, apply_plan, load_provider_manifest,
                  plan_artifact_lock, plan_artifact_render, provider_config_catalog,
                  sha256_digest, support_for)
from core.provider_lock import artifact_doctor
from .common import atomic_write_text


class ProviderDeployError(ValueError):
    """Stable no-write deployment planning failure."""


def resolve_effective_providers(config, catalog, project_id, *, operation=None,
                                project_config=None):
    """Resolve P1 provider selection once for a project operation, without I/O."""
    from .config import resolve_provider_config
    result = resolve_provider_config(config, catalog, project_id,
                                     project_config=project_config, operation=operation)
    if result.selection is None:
        codes = ",".join(item.code for item in result.diagnostics)
        raise ProviderDeployError(codes or "MAIND_PROVIDER_RESOLUTION_INVALID")
    providers = tuple(row.provider_id for row in result.selection if row.enabled)
    if len(set(providers)) != len(providers):
        raise ProviderDeployError("MAIND_PROVIDER_DUPLICATE")
    if not providers:
        raise ProviderDeployError("MAIND_PROVIDER_DISABLED")
    return providers


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
                         disabled=(), secret_values=(), manifest_path=None):
    """Project caller-owned descriptors through P5-owned target/serialization records."""
    from harness.mcp import McpProjection, render_mcp_projection
    manifest_path = Path(manifest_path) if manifest_path is not None else (
        Path(__file__).resolve().parents[4] / "configs/provider-capabilities.json")
    try:
        manifest = load_provider_manifest(manifest_path)
        capability_catalog = provider_config_catalog(manifest)
    except ValueError as error:
        raise ProviderDeployError(f"MAIND_CAPABILITY_MANIFEST_INVALID:{error}") from error
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
    forbidden = frozenset(secret_values)
    def scrub(value):
        if isinstance(value, str):
            return "${SECRET_REF}" if value in forbidden else value
        if isinstance(value, list): return [scrub(item) for item in value]
        if isinstance(value, dict): return {key: scrub(item) for key, item in value.items()}
        return value
    entries = tuple((item.id, scrub(dict(item.binding))) for item in servers)
    source_bytes = canonical_json_bytes({"servers": [{"id": item.id, "binding": dict(item.binding)}
                                               for item in servers]})
    source = ArtifactSource("maind.provider-deploy.semantic-inventory",
                            "packages/maind/lib/maind/provider_deploy.py", sha256_digest(source_bytes))
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
        try:
            support = support_for(manifest, "mcp.catalog", provider_id)
        except ValueError as error:
            raise ProviderDeployError(
                f"MAIND_CAPABILITY_MISSING:{provider_id.value}:mcp.catalog") from error
        if support.level is SupportLevel.UNSUPPORTED:
            results.append(ProviderDeployResult(
                provider_id, "", "", b"", (), "failed",
                f"MAIND_CAPABILITY_UNSUPPORTED:{provider_id.value}:mcp.catalog"))
            continue
        projection = McpProjection(base.provider_id, base.target_scope, base.target_path,
                                   entries, tuple())
        rendered = render_mcp_projection(projection)
        artifact = plan_artifact_render(ArtifactRenderRequest(
            "maind.provider-deploy." + provider_id.value,
            (source,), ArtifactTarget(base.target_path, ("whole-file", ())),
            ArtifactAdapterIdentity(
                "maind.provider-deploy", "1.0.0", provider_id,
                capability_catalog.catalog_version,
                (CapabilityRequirement(CapabilityId("mcp.catalog"),
                                       (SupportLevel.ADAPTED, SupportLevel.NATIVE)),)),
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


def generate_conformance_report(harness_configs, output_path):
    """Generate the fixed P6 semantic inventory through P5 projections only."""
    harness_lib = str(Path(harness_configs).parent / "lib")
    if harness_lib not in sys.path:
        sys.path.insert(0, harness_lib)
    from harness.mcp import load_mcp_catalog, plan_mcp_projection
    root = Path(harness_configs)
    catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
    bases = tuple(plan_mcp_projection(
        catalog, provider_id=provider,
        bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
        for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
    plan = plan_provider_deploy(bases, semantic_servers(
        maind={"command": "maind"},
        codegraph={"command": "uvx", "args": ["serena"]},
        perplexity={"command": "pplx"}))
    write_conformance_report(output_path, plan)
    return plan


def plan_provider_artifacts(root, deploy_plan, *, repair=False):
    """Classify all provider targets through one P2 plan without writing them."""
    if not deploy_plan.green:
        return {"mode": "check", "severity": "error", "plan": None,
                "diagnostics": deploy_plan.diagnostics}
    root = Path(root)
    lock_path = root / ".swissknifeman/provider-artifacts.lock.json"
    lock_bytes = lock_path.read_bytes() if lock_path.exists() else None
    artifacts = tuple(row.artifact for row in deploy_plan.results if row.artifact is not None)
    plan = plan_artifact_lock(root, artifacts, lock_bytes=lock_bytes,
                              repair_artifact_ids=tuple(
                                  row.artifact.provenance.artifact_id for row in deploy_plan.results)
                              if repair else ())
    projection = artifact_doctor(plan)
    return {"mode": "repair" if repair else "check", "severity": projection["exit_severity"],
            "plan": plan, "diagnostics": tuple(action["diagnostic"]
                                                   for action in projection["actions"])}


def apply_provider_artifacts(root, deploy_plan, *, repair=False):
    """Apply a preflighted provider deployment only when P2 has no refusal."""
    checked = plan_provider_artifacts(root, deploy_plan, repair=repair)
    if checked["plan"] is None or checked["severity"] == "error":
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED")
    apply_plan(Path(root), checked["plan"])
    return plan_provider_artifacts(root, deploy_plan)
