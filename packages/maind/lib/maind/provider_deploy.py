"""Provider-aware, caller-owned MCP deployment planning.

mAInd owns semantic server selection; harness owns provider target, trust validation and
serialization through its immutable MCP projection API.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Mapping
from types import MappingProxyType
from pathlib import Path
import json
import sys

from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, CapabilityId, CapabilityRequirement, ProviderId,
                  SupportLevel, canonical_json_bytes, apply_plan, load_provider_manifest,
                  plan_artifact_lock, plan_artifact_render, provider_config_catalog,
                  plan_bootstrap_transfer, BootstrapTransferAdmission, artifact_dry_run, sha256_digest,
                  ChainedBootstrapTransferAdmission, plan_chained_bootstrap_transfer,
                  support_for)
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


@dataclass(frozen=True)
class BootstrapTransferPlan:
    """The sole P6-owned D104 composition and its already-admitted P2 plan."""
    artifacts: tuple
    plan: object


@dataclass(frozen=True)
class ProjectCarrierPlan:
    """The closed D108 project-local provider selection mutation."""
    path: Path
    before: bytes | None
    after: bytes
    providers: dict

    @property
    def changed(self):
        return self.before != self.after


@dataclass(frozen=True)
class D108OperationPlan:
    """All writer inputs for the one D108 operation, prepared before mutation."""
    carrier: ProjectCarrierPlan
    deploy: ProviderDeployPlan
    transfer: BootstrapTransferPlan
    chained_plan: object


def plan_project_carrier(root, config, project_id, *, expected_root=None):
    """Plan the only allowed `.swissknife.json#/providers` selection merge.

    ``expected_root`` is supplied by the live facade; disposable-root conformance leaves it
    unset but still uses the canonical project id.  No caller may broaden this to another
    project or carrier.
    """
    root = Path(root)
    if project_id != "swissknifeman" or (expected_root is not None and
                                          root.resolve() != Path(expected_root).resolve()):
        raise ProviderDeployError("MAIND_D108_FOREIGN_PROJECT")
    path = root / ".swissknife.json"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ProviderDeployError("MAIND_D108_CARRIER_UNSAFE")
    before = path.read_bytes() if path.exists() else None
    try:
        document = {} if before is None else json.loads(before.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderDeployError("MAIND_D108_CARRIER_INVALID") from None
    if not isinstance(document, dict):
        raise ProviderDeployError("MAIND_D108_CARRIER_INVALID")
    existing = document.get("providers")
    if existing is not None:
        # The frozen P1 parser owns the provider schema; a bad existing layer refuses.
        from .config import resolve_provider_config
        resolved = resolve_provider_config(config, None, project_id,
                                           project_config=existing)
        if resolved.selection is None:
            raise ProviderDeployError("MAIND_D108_CARRIER_INVALID")
    providers = dict(existing or {})
    providers["contract_version"] = "1.0.0"
    selection = dict(providers.get("selection") or {})
    for provider_id in ("claude-code", "codex"):
        row = dict(selection.get(provider_id) or {})
        row["enabled"] = True
        selection[provider_id] = row
    providers["selection"] = selection
    # Validate the fully merged layer before it becomes writable.
    selected = resolve_effective_providers(config, None, project_id,
                                           project_config=providers)
    if selected != (ProviderId.CLAUDE_CODE, ProviderId.CODEX):
        raise ProviderDeployError("MAIND_D108_SELECTION_INVALID")
    document["providers"] = providers
    return ProjectCarrierPlan(path, before, canonical_json_bytes(document), providers)


def apply_project_carrier(plan):
    """Apply the explicit carrier plan; callers own cross-plan rollback."""
    if not isinstance(plan, ProjectCarrierPlan):
        raise TypeError("project carrier plan required")
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    from core import atomic_write_text
    atomic_write_text(plan.path, plan.after.decode("utf-8"))


def _rollback_project_carrier(plan):
    if plan.before is None:
        if plan.path.exists() and not plan.path.is_symlink() and plan.path.read_bytes() == plan.after:
            plan.path.unlink()
    elif plan.path.exists() and not plan.path.is_symlink() and plan.path.read_bytes() == plan.after:
        from core import atomic_write_text
        atomic_write_text(plan.path, plan.before.decode("utf-8"))


def _d108_planned_projections(config, project_id, carrier, harness_configs):
    """Render the one closed D108 Claude+Codex P5 base tuple from its carrier."""
    selected = resolve_effective_providers(config, None, project_id,
                                           project_config=carrier.providers)
    expected = (ProviderId.CLAUDE_CODE, ProviderId.CODEX)
    if selected != expected:
        raise ProviderDeployError("MAIND_D108_SELECTION_INVALID")
    harness_configs = Path(harness_configs)
    harness_lib = str(harness_configs.parent / "lib")
    if harness_lib not in sys.path:
        sys.path.insert(0, harness_lib)
    from harness.mcp import load_mcp_catalog, plan_mcp_projection
    catalog = load_mcp_catalog(harness_configs / "common/mcp/catalog.json")
    return tuple(plan_mcp_projection(
        catalog, provider_id=provider,
        bindings_path=harness_configs / provider.value / "mcp/bindings.json",
        selected=(), trusted=True) for provider in expected)


def plan_d108_operation(root, config, project_id, servers, *, harness_configs,
                        expected_root=None):
    """Construct every D108 component before returning any writer-capable plan."""
    carrier = plan_project_carrier(root, config, project_id, expected_root=expected_root)
    selected = resolve_effective_providers(config, None, project_id,
                                           project_config=carrier.providers)
    deploy = plan_provider_deploy(
        _d108_planned_projections(config, project_id, carrier, harness_configs),
        servers, selected=selected)
    if not deploy.green:
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED")
    mcp = next((row.artifact for row in deploy.results
                if row.provider_id is ProviderId.CLAUDE_CODE and row.target_path == ".mcp.json"), None)
    if mcp is None:
        raise ProviderDeployError("MAIND_D108_MCP_PLAN_MISSING")
    transfer = plan_d104_bootstrap_transfer(root, harness_configs=harness_configs)
    admission = ChainedBootstrapTransferAdmission(
        BootstrapTransferAdmission("D104", ".codex/hooks.json",
            "sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db",
            ".codex/hooks/lifecycle.py", "harness.codex.lifecycle.hooks",
            "harness.codex.lifecycle.handler"), transfer.plan, "D108", ".mcp.json",
        "sha256:cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283",
        "maind.provider-deploy.claude-code", ("whole-file", ()),
        ("maind", "perplexity-web", "serena"))
    lock = Path(root) / ".swissknifeman/provider-artifacts.lock.json"
    chained = plan_chained_bootstrap_transfer(Path(root), transfer.artifacts + (mcp,),
                                               lock_bytes=lock.read_bytes() if lock.exists() else None,
                                               admission=admission)
    if any(getattr(action.action, "value", action.action) == "refuse" for action in chained.actions):
        raise ProviderDeployError("MAIND_D108_CHAIN_REFUSED")
    return D108OperationPlan(carrier, deploy, transfer, chained)


def apply_d108_operation(root, operation):
    """Apply carrier then P2 transaction, restoring carrier if the latter refuses/fails."""
    if not isinstance(operation, D108OperationPlan):
        raise TypeError("D108 operation plan required")
    try:
        if operation.carrier.changed:
            apply_project_carrier(operation.carrier)
        apply_plan(Path(root), operation.chained_plan)
    except BaseException:
        _rollback_project_carrier(operation.carrier)
        raise
    return operation


def bootstrap_transfer_projection(status, transfer=None, diagnostic=None):
    """Return the P6-owned no-write D104 result without reclassifying P2 actions."""
    if status not in {"not-selected", "admitted", "refused"}:
        raise ValueError("MAIND_BOOTSTRAP_TRANSFER_STATUS_INVALID")
    actions = ()
    if transfer is not None:
        actions = tuple(artifact_dry_run(transfer.plan)["actions"])
    return {"status": status, "actions": actions, "diagnostic": diagnostic}


def project_provider_preflight(deploy_plan, checked):
    """Keep ordinary-provider rows distinct while reflecting a P2 refusal in their result."""
    if checked["plan"] is None:
        return deploy_plan
    actions = {action["target_path"]: action
               for action in artifact_doctor(checked["plan"])["actions"]}
    rows = []
    for row in deploy_plan.results:
        action = actions.get(row.target_path)
        if action and action["action"] == "refuse":
            rows.append(replace(row, status="failed", diagnostic=action["diagnostic"]))
        else:
            rows.append(row)
    return ProviderDeployPlan(tuple(rows))


def _d104_memory_registration(preimage):
    """Read exactly one caller-owned native memory SessionStart registration."""
    try:
        value = json.loads(preimage.decode("utf-8"))
        hooks = value["hooks"]
        groups = hooks["SessionStart"]
        group = groups[0]
        hook = group["hooks"][0]
    except (AttributeError, IndexError, KeyError, TypeError, UnicodeDecodeError,
            json.JSONDecodeError):
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED") from None
    if (not isinstance(value, dict) or set(value) != {"hooks"}
            or not isinstance(hooks, dict) or set(hooks) != {"SessionStart"}
            or not isinstance(groups, list) or len(groups) != 1
            or not isinstance(group, dict) or set(group) - {"hooks", "matcher"}
            or not isinstance(group.get("hooks"), list) or len(group["hooks"]) != 1
            or not isinstance(hook, dict) or set(hook) != {"type", "command"}
            or hook["type"] != "command" or not isinstance(hook["command"], str)
            or not hook["command"] or "matcher" in group and not isinstance(group["matcher"], str)):
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED")
    return group, hook["command"]


def _d104_observer_fragment(harness_configs):
    """Obtain P5's public native fragment without importing its implementation details."""
    harness_configs = Path(harness_configs)
    harness_lib = str(harness_configs.parent / "lib")
    if harness_lib not in sys.path:
        sys.path.insert(0, harness_lib)
    from harness.hooks import (LifecycleRequest, codex_d104_observer_fragment,
                               plan_lifecycle)
    from harness.profiles import load_catalog

    lifecycle = plan_lifecycle(
        load_catalog(harness_configs / "common/profile-catalog.json"),
        provider_id=ProviderId.CODEX,
        requests=(LifecycleRequest("context.observer", True),), trusted=True,
        codex_bindings_path=harness_configs / "codex/hooks/lifecycle-context-bindings.json")
    try:
        return codex_d104_observer_fragment(lifecycle)
    except ValueError as error:
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED") from error


def plan_d104_bootstrap_transfer(root, *, harness_configs):
    """Compose the exact D104 native Codex pair and ask P2 for its closed admission.

    This is intentionally separate from ordinary provider deployment: callers use it only
    for the single absent-lock bootstrap candidate, then return to the existing P2 plan.
    It plans only; callers choose whether a disposable-root apply is permitted.
    """
    root = Path(root)
    existing_path = root / ".codex/hooks.json"
    preimage = existing_path.read_bytes()
    memory_group, memory_command = _d104_memory_registration(preimage)
    fragment = _d104_observer_fragment(harness_configs)
    from harness.hooks import validate_d104_codex_lifecycle_composition
    document = (json.dumps({"hooks": {"SessionStart": [memory_group, fragment.group]}},
                           ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        validate_d104_codex_lifecycle_composition(
            document, memory_command=memory_command, fragment=fragment)
    except ValueError as error:
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED") from error

    sources = (
        ArtifactSource("maind.d104.memory-preimage", ".codex/hooks.json",
                       sha256_digest(preimage)),
        ArtifactSource("harness.d104.observer-fragment",
                       "packages/harness/lib/harness/hooks.py",
                       sha256_digest(canonical_json_bytes({
                           "event": fragment.event, "group": fragment.group,
                           "handler_sha256": sha256_digest(fragment.handler_bytes)}))),
    )
    identity = ArtifactAdapterIdentity("maind.d104.bootstrap-transfer", "1.0.0",
                                       ProviderId.CODEX, "1.0.0", ())
    hooks = plan_artifact_render(ArtifactRenderRequest(
        "harness.codex.lifecycle.hooks", sources,
        ArtifactTarget(".codex/hooks.json", ("whole-file", ())), identity, (),
        {"decision_id": "D104", "component": "composed-session-start"},
        lambda _request: document))
    handler = plan_artifact_render(ArtifactRenderRequest(
        "harness.codex.lifecycle.handler", sources,
        ArtifactTarget(".codex/hooks/lifecycle.py", ("whole-file", ())), identity, (),
        {"decision_id": "D104", "component": "lifecycle-handler"},
        lambda _request: fragment.handler_bytes))
    admission = BootstrapTransferAdmission(
        "D104", ".codex/hooks.json",
        "sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db",
        ".codex/hooks/lifecycle.py", "harness.codex.lifecycle.hooks",
        "harness.codex.lifecycle.handler")
    lock_path = root / ".swissknifeman/provider-artifacts.lock.json"
    plan = plan_bootstrap_transfer(root, (hooks, handler),
                                   lock_bytes=lock_path.read_bytes() if lock_path.exists() else None,
                                   admission=admission)
    return BootstrapTransferPlan((hooks, handler), plan)


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


def plan_provider_artifacts(root, deploy_plan, *, repair=False, extra_artifacts=()):
    """Classify all provider targets through one P2 plan without writing them."""
    if not deploy_plan.green:
        return {"mode": "check", "severity": "error", "plan": None,
                "diagnostics": deploy_plan.diagnostics}
    root = Path(root)
    lock_path = root / ".swissknifeman/provider-artifacts.lock.json"
    lock_bytes = lock_path.read_bytes() if lock_path.exists() else None
    artifacts = tuple(row.artifact for row in deploy_plan.results if row.artifact is not None)
    artifacts += tuple(extra_artifacts)
    plan = plan_artifact_lock(root, artifacts, lock_bytes=lock_bytes,
                              repair_artifact_ids=tuple(
                                  artifact.provenance.artifact_id for artifact in artifacts)
                              if repair else ())
    projection = artifact_doctor(plan)
    return {"mode": "repair" if repair else "check", "severity": projection["exit_severity"],
            "plan": plan, "diagnostics": tuple(action["diagnostic"]
                                                   for action in projection["actions"])}


def apply_provider_artifacts(root, deploy_plan, *, repair=False, extra_artifacts=()):
    """Apply a preflighted provider deployment only when P2 has no refusal."""
    checked = plan_provider_artifacts(root, deploy_plan, repair=repair,
                                      extra_artifacts=extra_artifacts)
    if checked["plan"] is None or checked["severity"] == "error":
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED")
    apply_plan(Path(root), checked["plan"])
    return plan_provider_artifacts(root, deploy_plan, extra_artifacts=extra_artifacts)
