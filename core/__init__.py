"""Transitional compatibility package, removed together with ``core/``.

The shared primitives moved to ``packages/aicore`` (:mod:`aicore`). This package keeps the old
import names working: every moved module is registered in ``sys.modules`` under its old name
(the very same module object), and the flat facade below keeps its previous ``__all__``.
Run analytics moved to analyst. New code imports ``aicore``.
"""
import importlib
import os
import sys
from pathlib import Path


def _ensure_aicore():
    try:
        import aicore  # noqa: F401
        return
    except ImportError:
        pass
    candidates = []
    if os.environ.get("AICORE_ROOT"):
        candidates.append(Path(os.environ["AICORE_ROOT"]) / "lib")
    candidates.append(Path(__file__).resolve().parent.parent / "packages" / "aicore" / "lib")
    for lib in candidates:
        if (lib / "aicore" / "__init__.py").is_file():
            sys.path.insert(0, str(lib))
            break
    try:
        import aicore  # noqa: F401,F811
    except ImportError:
        raise ImportError("aicore not found: set AICORE_ROOT or run from the monorepo") from None


_ensure_aicore()

_UTIL = ("block", "cli", "env", "http", "io", "paths", "proc", "project", "repo", "term", "text")
_PROVIDER = ("config", "control_plane", "diagnostics", "distribution", "errors", "health", "manifest",
             "models", "projection", "registry", "request_lifecycle", "runtime", "skill_adapter",
             "status", "values")
_ARTIFACTS = ("artifact", "lock", "reconcile")

# old module name -> module that now owns the code
_ALIASES = {
    "core.provider": "aicore.provider",
    "core.usage": "aicore.usage",
    "core.gitignore_policy": "aicore.state.gitignore",
    **{"core." + name: "aicore.util." + name for name in _UTIL},
    **{"core.provider." + name: "aicore.provider." + name for name in _PROVIDER},
    **{"core.provider." + name: "aicore.artifacts." + name for name in _ARTIFACTS},
}


def _install_aliases():
    this = sys.modules[__name__]
    for old, new in _ALIASES.items():
        module = importlib.import_module(new)
        sys.modules[old] = module
        parent, _, leaf = old.rpartition(".")
        if parent == "core":
            setattr(this, leaf, module)
        elif old.startswith("core.provider.") and new.startswith("aicore.artifacts."):
            # ``core.provider.lock`` resolves by attribute access on the provider package
            # (``mock.patch("core.provider.lock.x")``, ``import ... as``): expose it there.
            setattr(sys.modules["aicore.provider"], leaf, module)


_install_aliases()

from aicore.util.block import content_hash, managed_block, upsert_block
from aicore.util.cli import parse_args, parse_flags, run_cmd
from aicore.util.http import http_get_json, http_post_json, ping
from aicore.util.env import HOME, BaseEnv
from aicore.util.io import (atomic_write_json, atomic_write_text, backup_file,
                            load_json_db, read_ndjson, read_ndjson_iter, safe_load_json)
from aicore.util.paths import is_within, is_within_lexical, state_dir
from aicore.util.proc import pid_alive
from aicore.util.project import (DEFAULT_DOCS_VISIBILITY, DOCS_VISIBILITY_BY_TYPE,
                                 LANGUAGE_BY_TYPE, PROJECT_TYPES, detect_project_type,
                                 docs_visibility_for)
from aicore.provider.values import (CapabilityId, CapabilityRequirement, ConfigProvenance,
                                    ConfigSource, DiagnosticSeverity, EffectiveProvider,
                                    NativeExtensionId, ProviderAdapter, ProviderDecision,
                                    ProviderDiagnostic, ProviderId, ProviderSelection,
                                    SupportLevel)
from aicore.provider.config import (CapabilitySupport, NativeExtension,
                                    ProviderConfigCatalog, ProviderConfigLayer,
                                    ResolvedProviderConfig, effective_projection,
                                    resolve_provider_config)
from aicore.provider.control_plane import (CONTROL_PLANE_VERSION, ControlPlaneDiagnostic,
                                           ControlPlaneResolution, DesiredSnapshot,
                                           canonical_desired_bytes, parse_desired_snapshot,
                                           resolve_desired_snapshot)
from aicore.provider.manifest import (ManifestCapability, ManifestEvidence,
                                      ManifestNativeExtension, ManifestSupport,
                                      ProviderCapabilityManifest, ProviderManifestDiagnostic,
                                      ProviderManifestError, load_provider_manifest,
                                      parse_provider_manifest, provider_config_catalog,
                                      provider_manifest_canonical_bytes,
                                      provider_manifest_sha256, provider_support_projection,
                                      support_for)
from aicore.provider.distribution import (ConnectChannelSpec, DistributionCatalog,
                                          VendorChannelSpec, connect_channel,
                                          load_distribution_catalog, provider_distribution,
                                          vendor_channel)
from aicore.provider.projection import (CommandInvocationPolicy, InstructionProjectionPolicy,
                                        ProjectionCatalog, ProviderProjectionSpec,
                                        load_projection_catalog,
                                        projection_spec, project_common_instructions)
from aicore.artifacts.artifact import (ArtifactAdapterIdentity, ArtifactProvenance,
                                       ArtifactRenderRequest, ArtifactRenderResult,
                                       ArtifactSource, ArtifactTarget,
                                       canonical_json_bytes, plan_artifact_render,
                                       sha256_digest, validate_target_path)
from aicore.artifacts.lock import (ArtifactAction, ArtifactActionKind, ArtifactLock, ArtifactPlan,
                                   BootstrapTransferAdmission, ChainedBootstrapTransferAdmission,
                                   DriftObservation, LOCK_RELATIVE_PATH,
                                   LOCK_SCHEMA_VERSION, apply_plan, artifact_dry_run, parse_lock,
                                   plan_artifact_lock, plan_bootstrap_transfer, replace_owner_records,
                                   plan_chained_bootstrap_transfer,
                                   render_artifact_projection, rollback_chained_bootstrap_transfer,
                                   serialize_lock)
from aicore.provider.registry import (AdapterCatalog, AdapterDescriptor, AdapterSelection,
                                      AdapterSelectionResult, RegistryDiagnostic, RegistrySeverity)
from aicore.util.repo import find_monorepo_root, find_repo_root, sibling_bin
from aicore.util.term import confirm, die, now_iso, parse_iso, warn
from aicore.util.text import parse_frontmatter, parse_inline_list, sanitize

__all__ = [
    "HOME", "BaseEnv", "die", "warn", "now_iso", "parse_iso", "confirm", "sanitize",
    "parse_frontmatter", "parse_inline_list",
    "atomic_write_text", "atomic_write_json", "safe_load_json", "load_json_db",
    "backup_file",
    "read_ndjson", "read_ndjson_iter", "pid_alive",
    "is_within", "is_within_lexical", "state_dir",
    "find_repo_root", "find_monorepo_root", "sibling_bin",
    "detect_project_type", "PROJECT_TYPES", "LANGUAGE_BY_TYPE",
    "docs_visibility_for", "DOCS_VISIBILITY_BY_TYPE", "DEFAULT_DOCS_VISIBILITY",
    "parse_flags", "parse_args", "run_cmd",
    "content_hash", "managed_block", "upsert_block",
    "http_get_json", "http_post_json", "ping",
    "ProviderId", "SupportLevel", "DiagnosticSeverity", "CapabilityId",
    "NativeExtensionId", "CapabilityRequirement", "ProviderDecision",
    "ProviderSelection", "EffectiveProvider", "ConfigSource", "ConfigProvenance",
    "ProviderDiagnostic", "ProviderAdapter",
    "CapabilitySupport", "NativeExtension", "ProviderConfigCatalog",
    "ProviderConfigLayer", "ResolvedProviderConfig", "resolve_provider_config",
    "effective_projection",
    "CONTROL_PLANE_VERSION", "ControlPlaneDiagnostic", "ControlPlaneResolution",
    "DesiredSnapshot", "resolve_desired_snapshot", "parse_desired_snapshot",
    "canonical_desired_bytes",
    "ManifestEvidence", "ManifestSupport", "ManifestCapability",
    "ManifestNativeExtension", "ProviderCapabilityManifest",
    "ProviderManifestDiagnostic", "ProviderManifestError",
    "parse_provider_manifest", "load_provider_manifest", "provider_config_catalog",
    "provider_support_projection", "provider_manifest_canonical_bytes",
    "provider_manifest_sha256", "support_for",
    "DistributionCatalog", "ConnectChannelSpec", "VendorChannelSpec",
    "load_distribution_catalog", "provider_distribution", "connect_channel",
    "vendor_channel",
    "ProjectionCatalog", "ProviderProjectionSpec", "InstructionProjectionPolicy",
    "CommandInvocationPolicy", "load_projection_catalog",
    "projection_spec", "project_common_instructions",
    "ArtifactSource", "ArtifactTarget", "ArtifactAdapterIdentity",
    "ArtifactRenderRequest", "ArtifactProvenance", "ArtifactRenderResult",
    "canonical_json_bytes", "sha256_digest", "validate_target_path",
    "plan_artifact_render",
    "ArtifactLock", "ArtifactAction", "ArtifactPlan", "BootstrapTransferAdmission",
    "ChainedBootstrapTransferAdmission", "DriftObservation",
    "ArtifactActionKind", "LOCK_SCHEMA_VERSION", "LOCK_RELATIVE_PATH", "serialize_lock",
    "parse_lock", "plan_artifact_lock", "plan_bootstrap_transfer", "replace_owner_records",
    "plan_chained_bootstrap_transfer", "apply_plan", "artifact_dry_run",
    "render_artifact_projection", "rollback_chained_bootstrap_transfer",
    "RegistrySeverity", "RegistryDiagnostic", "AdapterDescriptor", "AdapterSelection",
    "AdapterSelectionResult", "AdapterCatalog",
]
