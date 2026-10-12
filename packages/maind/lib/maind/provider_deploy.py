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
import re
import sys
import tempfile

from .harness_path import ensure_harness_importable
from .config import (PROJECT_LEGACY_CARRIER, PROJECT_TOML_CARRIER, aicore_schema,
                     toml_project_providers)
from aicore.provider.manifest import default_manifest_path
from aicore.artifacts.artifact import (
    ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource, ArtifactTarget,
    canonical_json_bytes, plan_artifact_render, sha256_digest)
from aicore.artifacts.lock import (
    ArtifactAction, ArtifactActionKind, ArtifactLock, ArtifactPlan, DriftObservation,
    apply_plan, plan_artifact_lock, replace_owner_records, parse_lock,
    plan_bootstrap_transfer, BootstrapTransferAdmission, artifact_dry_run,
    ChainedBootstrapTransferAdmission, plan_chained_bootstrap_transfer)
from aicore.provider.values import (
    CapabilityId, CapabilityRequirement, ProviderId, SupportLevel)
from aicore.provider.manifest import (
    load_provider_manifest, provider_config_catalog, support_for)
from aicore.artifacts.lock import artifact_doctor, rollback_chained_bootstrap_transfer
from aicore.util.io import atomic_write_text
from aicore.util.term import warn
from aicore.config import ConfigError, edit_layer_file
from aicore.config.toml_edit import TomlEditError
from .common import save_backup


_BOOTSTRAP_CANONICAL_PREIMAGE = "sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db"


class ProviderDeployError(ValueError):
    """Stable no-write deployment planning failure."""


_TOML_TABLE_HEADER_RE = re.compile(
    br"(?m)^[ \t]*\[([^\]\r\n]+)\][ \t]*(?:#[^\r\n]*)?\r?$")
_CODEX_MCP_BLOCK_IDS = ("mcp_servers",)


def _codex_mcp_span(raw, block_ids):
    if block_ids != _CODEX_MCP_BLOCK_IDS:
        raise ProviderDeployError("MAIND_CODEX_MCP_BOUNDARY_INVALID")
    headers = tuple(_TOML_TABLE_HEADER_RE.finditer(raw))
    managed = tuple(index for index, match in enumerate(headers)
                    if match.group(1).startswith(b"mcp_servers."))
    if not managed:
        return None
    first, last = managed[0], managed[-1]
    if managed != tuple(range(first, last + 1)):
        raise ProviderDeployError("MAIND_CODEX_MCP_BOUNDARY_INVALID")
    start = headers[first].start()
    end = headers[last + 1].start() if last + 1 < len(headers) else len(raw)
    return start, end


def _extract_codex_mcp_blocks(raw, block_ids):
    span = _codex_mcp_span(raw, block_ids)
    return b"" if span is None else raw[span[0]:span[1]]


def _replace_codex_mcp_blocks(raw, managed, block_ids):
    desired = _extract_codex_mcp_blocks(managed, block_ids)
    if desired != managed:
        raise ProviderDeployError("MAIND_CODEX_MCP_RENDER_INVALID")
    span = _codex_mcp_span(raw, block_ids)
    if span is not None:
        start, end = span
        return raw[:start] + desired + raw[end:]
    body = raw
    if body and not body.endswith(b"\n\n"):
        body = body + (b"\n" if body.endswith(b"\n") else b"\n\n")
    return body + desired


def _provider_managed_block_codecs(artifacts):
    return {
        artifact.provenance.artifact_id:
            (_extract_codex_mcp_blocks, _replace_codex_mcp_blocks)
        for artifact in artifacts
        if artifact.provenance.managed_boundary ==
        ("managed-blocks", _CODEX_MCP_BLOCK_IDS)
    }


def resolve_effective_providers(config, catalog, project_id, *, operation=None,
                                project_config=None, project_carrier=None):
    """Resolve P1 provider selection once for a project operation, without I/O."""
    from .config import PROJECT_LEGACY_CARRIER, resolve_provider_config
    result = resolve_provider_config(config, catalog, project_id,
                                     project_config=project_config, operation=operation,
                                     project_carrier=project_carrier or PROJECT_LEGACY_CARRIER)
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
    managed_post_apply: bool = False


@dataclass(frozen=True)
class ProjectCarrierPlan:
    """The closed D108 project-local provider selection mutation.

    ``carrier`` names the active source: the project layer ``.swissknifeman/config.toml``
    (``[aicore.providers]``) or the legacy ``.swissknife.json`` (``/providers``)."""
    path: Path
    before: bytes | None
    after: bytes
    providers: dict
    carrier: str = PROJECT_LEGACY_CARRIER

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
    """Plan the only allowed project provider selection merge, in the ACTIVE source.

    The source is the ``[aicore.providers]`` table of ``.swissknifeman/config.toml`` when the project
    layer sets a selection there; else the legacy ``.swissknife.json#/providers`` while that file
    exists (its bytes keep the form they always had); else the project layer (new file, written
    only by the apply step). ``expected_root`` is supplied by the live facade; disposable-root
    conformance leaves it unset but still uses the canonical project id.  No caller may broaden
    this to another project or carrier.
    """
    root = Path(root)
    if project_id != "swissknifeman" or (expected_root is not None and
                                          root.resolve() != Path(expected_root).resolve()):
        raise ProviderDeployError("MAIND_D108_FOREIGN_PROJECT")
    toml_path = root / PROJECT_TOML_CARRIER
    if toml_path.is_symlink() or (toml_path.exists() and not toml_path.is_file()):
        raise ProviderDeployError("MAIND_D108_CARRIER_UNSAFE")
    try:
        toml_existing = toml_project_providers(root)
    except ConfigError:
        raise ProviderDeployError("MAIND_D108_CARRIER_INVALID") from None
    legacy_path = root / PROJECT_LEGACY_CARRIER
    if toml_existing is not None or (not legacy_path.exists() and not legacy_path.is_symlink()):
        return _plan_toml_carrier(root, config, project_id, toml_path, toml_existing)
    return _plan_legacy_carrier(root, config, project_id, legacy_path)


def _plan_toml_carrier(root, config, project_id, path, existing):
    before = path.read_bytes() if path.exists() else None
    if existing is not None:
        from .config import resolve_provider_config
        resolved = resolve_provider_config(config, None, project_id, project_config=existing,
                                           project_carrier=PROJECT_TOML_CARRIER)
        if resolved.selection is None:
            raise ProviderDeployError("MAIND_D108_CARRIER_INVALID")
    with tempfile.TemporaryDirectory() as scratch:
        scratch_root = Path(scratch)
        scratch_path = scratch_root / PROJECT_TOML_CARRIER
        scratch_path.parent.mkdir(parents=True)
        if before is not None:
            scratch_path.write_bytes(before)
        try:
            for provider_id in ("claude-code", "codex"):
                edit_layer_file(scratch_path, "aicore", f"providers.selection.{provider_id}.enabled",
                                True, schema=aicore_schema(), layer="project", project=scratch_root)
            providers = toml_project_providers(scratch_root)
        except (ConfigError, TomlEditError):
            raise ProviderDeployError("MAIND_D108_CARRIER_INVALID") from None
        after = scratch_path.read_bytes()
    # Validate the fully merged layer before it becomes writable.
    selected = resolve_effective_providers(config, None, project_id, project_config=providers,
                                           project_carrier=PROJECT_TOML_CARRIER)
    if selected != (ProviderId.CLAUDE_CODE, ProviderId.CODEX):
        raise ProviderDeployError("MAIND_D108_SELECTION_INVALID")
    return ProjectCarrierPlan(path, before, after, providers, PROJECT_TOML_CARRIER)


def _plan_legacy_carrier(root, config, project_id, path):
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
        warn_legacy_providers(path)
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
    return ProjectCarrierPlan(path, before, canonical_json_bytes(document), providers,
                              PROJECT_LEGACY_CARRIER)


_warned_legacy_providers = set()


def warn_legacy_providers(path):
    """One MAIND_LEGACY_PROVIDERS warning per process and legacy carrier."""
    if str(path) in _warned_legacy_providers:
        return
    _warned_legacy_providers.add(str(path))
    warn(f"MAIND_LEGACY_PROVIDERS: reading the provider selection from {path}; move it to "
         f"[aicore.providers.selection.<id>] in .swissknifeman/config.toml (swissknifeman upgrade)")


def apply_project_carrier(plan):
    """Apply the explicit carrier plan; callers own cross-plan rollback."""
    if not isinstance(plan, ProjectCarrierPlan):
        raise TypeError("project carrier plan required")
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    from aicore.util.io import atomic_write_text
    if plan.carrier == PROJECT_TOML_CARRIER and plan.before is not None:
        save_backup(plan.path, project=plan.path.parents[1])
    atomic_write_text(plan.path, plan.after.decode("utf-8"))


def _rollback_project_carrier(plan):
    if (not plan.path.is_file() or plan.path.is_symlink() or
            plan.path.read_bytes() != plan.after):
        raise ProviderDeployError("MAIND_D108_ROLLBACK_CARRIER_CHANGED")
    if plan.before is None:
        plan.path.unlink()
        if plan.carrier == PROJECT_TOML_CARRIER:
            try:
                plan.path.parent.rmdir()   # only if the apply step created it and it is empty
            except OSError:
                pass
    elif plan.changed:
        from aicore.util.io import atomic_write_text
        atomic_write_text(plan.path, plan.before.decode("utf-8"))


def _d108_planned_projections(config, project_id, carrier, harness_configs):
    """Render the one closed D108 Claude+Codex P5 base tuple from its carrier."""
    selected = resolve_effective_providers(config, None, project_id,
                                           project_config=carrier.providers,
                                           project_carrier=carrier.carrier)
    expected = (ProviderId.CLAUDE_CODE, ProviderId.CODEX)
    if selected != expected:
        raise ProviderDeployError("MAIND_D108_SELECTION_INVALID")
    harness_configs = Path(harness_configs)
    harness_lib = str(harness_configs.parent / "lib")
    ensure_harness_importable(harness_lib)
    from harness.mcp import load_mcp_catalog, plan_mcp_projection
    catalog = load_mcp_catalog(harness_configs / "common/mcp/catalog.json")
    return tuple(plan_mcp_projection(
        catalog, provider_id=provider,
        bindings_path=harness_configs / provider.value / "mcp/bindings.json",
        selected=(), trusted=True) for provider in expected)


def _d108_unchanged_mcp_artifact(root, deploy):
    """Project the sealed existing MCP bytes as D108's explicit NOOP artifact."""
    rows = []
    mcp = None
    for row in deploy.results:
        if row.provider_id is ProviderId.CLAUDE_CODE and row.target_path == ".mcp.json":
            if row.artifact is None:
                raise ProviderDeployError("MAIND_D108_MCP_PLAN_MISSING")
            path = Path(root) / row.target_path
            if path.is_file() and not path.is_symlink():
                managed = path.read_bytes()
                provenance = replace(row.artifact.provenance,
                                     rendered_hash=sha256_digest(managed))
                artifact = replace(row.artifact, managed_bytes=managed,
                                   provenance=provenance)
                row = replace(row, rendered=managed, artifact=artifact)
            mcp = row.artifact
        rows.append(row)
    if mcp is None:
        raise ProviderDeployError("MAIND_D108_MCP_PLAN_MISSING")
    return ProviderDeployPlan(tuple(rows)), mcp


def plan_d108_operation(root, config, project_id, servers, *, harness_configs,
                        expected_root=None):
    """Construct every D108 component before returning any writer-capable plan."""
    carrier = plan_project_carrier(root, config, project_id, expected_root=expected_root)
    selected = resolve_effective_providers(config, None, project_id,
                                           project_config=carrier.providers,
                                           project_carrier=carrier.carrier)
    deploy = plan_provider_deploy(
        _d108_planned_projections(config, project_id, carrier, harness_configs),
        servers, selected=selected)
    if not deploy.green:
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED")
    deploy, mcp = _d108_unchanged_mcp_artifact(root, deploy)
    transfer = plan_d104_bootstrap_transfer(root, harness_configs=harness_configs)
    lock = Path(root) / ".swissknifeman/provider-artifacts.lock.json"
    lock_bytes = lock.read_bytes() if lock.exists() else None
    artifacts = transfer.artifacts + (mcp,)
    if transfer.managed_post_apply:
        chained = plan_artifact_lock(
            Path(root), artifacts, lock_bytes=lock_bytes,
            owner_namespace=("maind.provider-deploy", "harness.codex.lifecycle"))
    else:
        admission = ChainedBootstrapTransferAdmission(
            transfer.plan.bootstrap_transfer, transfer.plan, "D108", ".mcp.json",
            "sha256:cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283",
            "maind.provider-deploy.claude-code", ("whole-file", ()),
            ("maind", "perplexity-web", "serena"))
        chained = plan_chained_bootstrap_transfer(Path(root), artifacts,
                                                   lock_bytes=lock_bytes,
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
        if any(getattr(action.action, "value", action.action) != "noop"
               for action in operation.chained_plan.actions):
            apply_plan(Path(root), operation.chained_plan)
    except BaseException:
        _rollback_project_carrier(operation.carrier)
        raise
    return operation


def rollback_d108_operation(root, operation):
    """Reverse only the exact, already-applied D108 operation and its carrier."""
    if not isinstance(operation, D108OperationPlan):
        raise TypeError("D108 operation plan required")
    root = Path(root)
    error = _d108_rollback_operation_error(root, operation)
    if error is not None:
        raise ProviderDeployError(error)
    try:
        rollback_chained_bootstrap_transfer(root, operation.chained_plan)
        _rollback_project_carrier(operation.carrier)
    except ValueError as error:
        raise ProviderDeployError("MAIND_D108_ROLLBACK_REFUSED") from error
    return operation


def _d108_rollback_operation_error(root, operation):
    """Validate the recorded P6 carrier before the core rollback can write."""
    if not root.is_absolute() or root != root.resolve():
        return "MAIND_D108_ROLLBACK_ROOT_INVALID"
    carrier = operation.carrier
    if (not isinstance(carrier, ProjectCarrierPlan) or
            carrier.path != root / carrier.carrier or
            carrier.path.is_symlink() or not carrier.path.is_file() or
            carrier.path.read_bytes() != carrier.after):
        return "MAIND_D108_ROLLBACK_CARRIER_CHANGED"
    transfer = operation.transfer
    chained = operation.chained_plan
    admission = getattr(chained, "chained_bootstrap_transfer", None)
    if (not isinstance(transfer, BootstrapTransferPlan) or admission is None or
            transfer.plan != admission.predecessor_plan):
        return "MAIND_D108_ROLLBACK_OPERATION_INVALID"
    expected = tuple(action.expected for action in transfer.plan.actions)
    chained_expected = {action.target_path: action.expected for action in chained.actions}
    if (set(chained_expected) != {".codex/hooks.json", ".codex/hooks/lifecycle.py", ".mcp.json"} or
            any(chained_expected[path] != artifact for path, artifact in
                zip((".codex/hooks.json", ".codex/hooks/lifecycle.py"), expected))):
        return "MAIND_D108_ROLLBACK_OPERATION_INVALID"
    return None


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


def _d104_memory_registration(preimage, *, observer_group=None):
    """Read the frozen D104 memory registration or its exact managed successor."""
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
            or not isinstance(hooks, dict) or "SessionStart" not in hooks
            or not isinstance(groups, list) or len(groups) not in {1, 2}
            or not isinstance(group, dict) or set(group) - {"hooks", "matcher"}
            or not isinstance(group.get("hooks"), list) or len(group["hooks"]) != 1
            or not isinstance(hook, dict) or set(hook) != {"type", "command"}
            or hook["type"] != "command" or not isinstance(hook["command"], str)
            or not hook["command"] or "maind-memory" not in hook["command"]
            or "matcher" in group and not isinstance(group["matcher"], str)):
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED")
    if len(groups) == 2:
        merged_hooks = dict(hooks)
        merged_hooks["SessionStart"] = [group, observer_group]
        document = (json.dumps({"hooks": merged_hooks},
                               ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if not isinstance(observer_group, dict) or groups[1] != observer_group or preimage != document:
            raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED")
    return group, hook["command"], len(groups) == 2


def _d104_observer_fragment(harness_configs):
    """Obtain P5's public native fragment without importing its implementation details."""
    harness_configs = Path(harness_configs)
    harness_lib = str(harness_configs.parent / "lib")
    ensure_harness_importable(harness_lib)
    from harness.hooks import (LifecycleRequest, codex_d104_observer_fragment,
                               plan_lifecycle)
    from harness.profiles import load_catalog

    lifecycle = plan_lifecycle(
        load_catalog(harness_configs / "common" / "profile-catalog.json"),
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
    fragment = _d104_observer_fragment(harness_configs)
    memory_group, memory_command, managed_post_apply = _d104_memory_registration(
        preimage, observer_group=fragment.group)
    from harness.hooks import validate_d104_codex_lifecycle_composition
    preimage_value = json.loads(preimage.decode("utf-8"))
    merged_hooks = dict(preimage_value["hooks"])
    merged_hooks["SessionStart"] = [memory_group, fragment.group]
    document = (json.dumps({"hooks": merged_hooks},
                           ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        validate_d104_codex_lifecycle_composition(
            document, memory_command=memory_command, fragment=fragment)
    except ValueError as error:
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED") from error

    preimage_hash = sha256_digest(preimage)
    sources = (
        ArtifactSource("maind.d104.memory-preimage", ".codex/hooks.json",
                       _BOOTSTRAP_CANONICAL_PREIMAGE if managed_post_apply else preimage_hash),
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
        preimage_hash,
        ".codex/hooks/lifecycle.py", "harness.codex.lifecycle.hooks",
        "harness.codex.lifecycle.handler")
    lock_path = root / ".swissknifeman/provider-artifacts.lock.json"
    plan = plan_bootstrap_transfer(root, (hooks, handler),
                                   lock_bytes=lock_path.read_bytes() if lock_path.exists() else None,
                                   admission=admission)
    return BootstrapTransferPlan((hooks, handler), plan, managed_post_apply)


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
                         disabled=(), secret_values=(), manifest_path=None,
                         excluded_server_ids_by_provider=None):
    """Project caller-owned descriptors through P5-owned target/serialization records."""
    from harness.mcp import McpProjection, render_mcp_projection
    manifest_path = Path(manifest_path) if manifest_path is not None else (
        default_manifest_path())
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
    excluded_server_ids_by_provider = excluded_server_ids_by_provider or {}
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
        excluded_ids = set(excluded_server_ids_by_provider.get(provider_id.value, ()))
        provider_servers = tuple(item for item in servers if item.id not in excluded_ids)
        entries = tuple((item.id, scrub(dict(item.binding))) for item in provider_servers)
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
            (), {"target_scope": base.target_scope,
                 "server_ids": [item.id for item in provider_servers]},
            lambda _request, value=rendered: value))
        if provider_id is ProviderId.CODEX:
            provenance = replace(
                artifact.provenance,
                managed_boundary=("managed-blocks", _CODEX_MCP_BLOCK_IDS))
            artifact = replace(artifact, provenance=provenance)
        results.append(ProviderDeployResult(provider_id, base.target_scope, base.target_path,
                                             rendered, tuple(item.id for item in provider_servers),
                                             "planned",
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
    ensure_harness_importable(harness_lib)
    from harness.mcp import load_mcp_catalog, plan_mcp_projection
    root = Path(harness_configs)
    catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
    bases = tuple(plan_mcp_projection(
        catalog, provider_id=provider,
        bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
        for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX, ProviderId.CURSOR))
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
    extra_artifacts = tuple(extra_artifacts)
    artifacts += extra_artifacts
    codecs = _provider_managed_block_codecs(artifacts)
    plan = plan_artifact_lock(root, artifacts, lock_bytes=lock_bytes,
                              owner_namespace=("maind.provider-deploy",) + tuple(
                                  artifact.provenance.artifact_id for artifact in extra_artifacts),
                              repair_artifact_ids=tuple(
                                  artifact.provenance.artifact_id for artifact in artifacts)
                              if repair else (),
                              managed_block_codecs=codecs)
    projection = artifact_doctor(plan)
    return {"mode": "repair" if repair else "check", "severity": projection["exit_severity"],
            "plan": plan, "diagnostics": tuple(action["diagnostic"]
                                                   for action in projection["actions"])}


def plan_exact_artifact_adoption(root, artifacts, *, preimage_hashes,
                                 managed_block_codecs=None):
    """Admit exact unmanaged targets and preserve unrelated lock records.

    Every existing target is pinned by its full-file SHA-256 preimage. Managed
    block codecs may then update only their declared boundary while unrelated
    bytes and unrelated existing lock records survive.
    """
    root = Path(root)
    if not root.is_absolute() or root != root.resolve() or not root.is_dir():
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_ROOT_INVALID")
    lock_path = root / ".swissknifeman/provider-artifacts.lock.json"
    if lock_path.is_symlink() or lock_path.exists() and not lock_path.is_file():
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_LOCK_UNSAFE")
    lock_bytes = lock_path.read_bytes() if lock_path.exists() else None
    try:
        existing_lock = ArtifactLock(1, ()) if lock_bytes is None else parse_lock(lock_bytes)
    except ValueError as error:
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_LOCK_INVALID") from error
    artifacts = tuple(artifacts)
    if not artifacts or any(artifact is None for artifact in artifacts):
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_PLAN_INVALID")
    if not isinstance(preimage_hashes, Mapping):
        raise TypeError("preimage_hashes must be a mapping")
    targets = {artifact.target.path: artifact for artifact in artifacts}
    if len(targets) != len(artifacts):
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_PLAN_INVALID")
    artifact_ids = {artifact.provenance.artifact_id for artifact in artifacts}
    if len(artifact_ids) != len(artifacts):
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_PLAN_INVALID")
    if any(record.artifact_id in artifact_ids or record.target_path in targets
           for record in existing_lock.records):
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_ALREADY_MANAGED")
    existing_targets = set()
    observed = {}
    for target_path in targets:
        target = root / target_path
        if target.is_symlink() or target.exists() and not target.is_file():
            raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_TARGET_UNSAFE")
        if target.exists():
            existing_targets.add(target_path)
            observed[target_path] = sha256_digest(target.read_bytes())
    if set(preimage_hashes) != existing_targets:
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_PREIMAGE_SET_INVALID")
    for target_path, expected_hash in preimage_hashes.items():
        if not isinstance(expected_hash, str) or observed[target_path] != expected_hash:
            raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_PREIMAGE_MISMATCH")
    codecs = dict(managed_block_codecs or {})
    managed_ids = {artifact.provenance.artifact_id for artifact in artifacts
                   if artifact.provenance.managed_boundary[0] == "managed-blocks"}
    if set(codecs) != managed_ids:
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_CODEC_SET_INVALID")
    actions = []
    for target_path, artifact in targets.items():
        current_preimage_hash = observed.get(target_path)
        codec = codecs.get(artifact.provenance.artifact_id)
        if current_preimage_hash is None:
            current_hash = None
            observation = DriftObservation.MISSING
            action = ArtifactActionKind.CREATE
            diagnostic = "explicit-adoption-create"
        else:
            current = (root / target_path).read_bytes()
            current_hash = (sha256_digest(codec[0](
                current, artifact.provenance.managed_boundary[1]))
                            if codec is not None else current_preimage_hash)
            # The caller's exact hash admission is the ownership handoff.  From
            # this immutable plan onward the admitted bytes are the stale source,
            # so ordinary provider rendering can replace them without repair.
            # Adoption itself must remain a write even when the rendered bytes
            # already match: apply_plan skips the lock when every action is NOOP.
            observation = DriftObservation.STALE_SOURCE
            action = ArtifactActionKind.UPDATE
            diagnostic = "explicit-adoption"
        actions.append(ArtifactAction(
            artifact.provenance.artifact_id, target_path, observation, action,
            artifact, current_hash, diagnostic, codec))
    namespaces = tuple(artifact.provenance.artifact_id for artifact in artifacts)
    return ArtifactPlan(
        tuple(actions), replace_owner_records(
            existing_lock, namespaces,
            (artifact.provenance for artifact in artifacts)),
        owner_namespace=namespaces, observed_lock=existing_lock)


def plan_provider_artifact_adoption(root, deploy_plan, *, preimage_hashes):
    """Adopt exact unmanaged provider targets into the ordinary artifact lock."""
    if not deploy_plan.green:
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED")
    artifacts = tuple(row.artifact for row in deploy_plan.results
                      if row.artifact is not None)
    if len(artifacts) != len(deploy_plan.results):
        raise ProviderDeployError("MAIND_PROVIDER_ADOPTION_PLAN_INVALID")
    return plan_exact_artifact_adoption(
        root, artifacts, preimage_hashes=preimage_hashes,
        managed_block_codecs=_provider_managed_block_codecs(artifacts))


def apply_provider_artifacts(root, deploy_plan, *, repair=False, extra_artifacts=()):
    """Apply a preflighted provider deployment only when P2 has no refusal."""
    checked = plan_provider_artifacts(root, deploy_plan, repair=repair,
                                      extra_artifacts=extra_artifacts)
    if checked["plan"] is None or checked["severity"] == "error":
        raise ProviderDeployError("MAIND_PROVIDER_DEPLOY_REFUSED")
    apply_plan(Path(root), checked["plan"])
    return plan_provider_artifacts(root, deploy_plan, extra_artifacts=extra_artifacts)
