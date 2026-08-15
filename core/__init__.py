"""Shared stdlib-only monorepo primitives.

The package centralizes common terminal, filesystem, process, parsing, and provider
helpers while domain-specific extensions remain in their owning packages.
"""
from .block import content_hash, managed_block, upsert_block
from .cli import parse_args, parse_flags, run_cmd
from .http import http_get_json, http_post_json, ping
from .env import HOME, BaseEnv
from .io import (atomic_write_json, atomic_write_text, backup_file,
                 load_json_db, read_ndjson, read_ndjson_iter, safe_load_json)
from .paths import is_within, is_within_lexical, state_dir
from .proc import pid_alive
from .project import (DEFAULT_DOCS_VISIBILITY, DOCS_VISIBILITY_BY_TYPE,
                      LANGUAGE_BY_TYPE, PROJECT_TYPES, detect_project_type,
                      docs_visibility_for)
from .provider.values import (CapabilityId, CapabilityRequirement, ConfigProvenance,
                              ConfigSource, DiagnosticSeverity, EffectiveProvider,
                              NativeExtensionId, ProviderAdapter, ProviderDecision,
                              ProviderDiagnostic, ProviderId, ProviderSelection,
                              SupportLevel)
from .provider.config import (CapabilitySupport, NativeExtension,
                              ProviderConfigCatalog, ProviderConfigLayer,
                              ResolvedProviderConfig, effective_projection,
                              resolve_provider_config)
from .provider.control_plane import (CONTROL_PLANE_VERSION, ControlPlaneDiagnostic,
                                     ControlPlaneResolution, DesiredSnapshot,
                                     canonical_desired_bytes, parse_desired_snapshot,
                                     resolve_desired_snapshot)
from .provider.manifest import (ManifestCapability, ManifestEvidence,
                                ManifestNativeExtension, ManifestSupport,
                                ProviderCapabilityManifest, ProviderManifestDiagnostic,
                                ProviderManifestError, load_provider_manifest,
                                parse_provider_manifest, provider_config_catalog,
                                provider_manifest_canonical_bytes,
                                provider_manifest_sha256, provider_support_projection,
                                support_for)
from .provider.artifact import (ArtifactAdapterIdentity, ArtifactProvenance,
                                ArtifactRenderRequest, ArtifactRenderResult,
                                ArtifactSource, ArtifactTarget,
                                canonical_json_bytes, plan_artifact_render,
                                sha256_digest, validate_target_path)
from .provider.lock import (ArtifactAction, ArtifactActionKind, ArtifactLock, ArtifactPlan,
                            BootstrapTransferAdmission, ChainedBootstrapTransferAdmission,
                            DriftObservation, LOCK_RELATIVE_PATH,
                            LOCK_SCHEMA_VERSION, apply_plan, artifact_dry_run, parse_lock,
                            plan_artifact_lock, plan_bootstrap_transfer,
                            plan_chained_bootstrap_transfer,
                            render_artifact_projection, rollback_chained_bootstrap_transfer,
                            serialize_lock)
from .provider.registry import (AdapterCatalog, AdapterDescriptor, AdapterSelection,
                                AdapterSelectionResult, RegistryDiagnostic, RegistrySeverity)
from .repo import find_monorepo_root, find_repo_root, sibling_bin
from .runs import find_run_report
from .term import confirm, die, now_iso, parse_iso, warn
from .text import parse_frontmatter, parse_inline_list, sanitize

__all__ = [
    "HOME", "BaseEnv", "die", "warn", "now_iso", "parse_iso", "confirm", "sanitize",
    "parse_frontmatter", "parse_inline_list",
    "atomic_write_text", "atomic_write_json", "safe_load_json", "load_json_db",
    "backup_file",
    "read_ndjson", "read_ndjson_iter", "pid_alive", "find_run_report",
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
    "ArtifactSource", "ArtifactTarget", "ArtifactAdapterIdentity",
    "ArtifactRenderRequest", "ArtifactProvenance", "ArtifactRenderResult",
    "canonical_json_bytes", "sha256_digest", "validate_target_path",
    "plan_artifact_render",
    "ArtifactLock", "ArtifactAction", "ArtifactPlan", "BootstrapTransferAdmission",
    "ChainedBootstrapTransferAdmission", "DriftObservation",
    "ArtifactActionKind", "LOCK_SCHEMA_VERSION", "LOCK_RELATIVE_PATH", "serialize_lock",
    "parse_lock", "plan_artifact_lock", "plan_bootstrap_transfer",
    "plan_chained_bootstrap_transfer", "apply_plan", "artifact_dry_run",
    "render_artifact_projection", "rollback_chained_bootstrap_transfer",
    "RegistrySeverity", "RegistryDiagnostic", "AdapterDescriptor", "AdapterSelection",
    "AdapterSelectionResult", "AdapterCatalog",
]
