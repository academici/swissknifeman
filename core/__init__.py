"""core — общий stdlib-only фундамент пакетов монорепо.

Здесь живут дословные дубли, которые исторически копировались между
swissknifeman/maind/brain байт-в-байт: вывод (die/warn/now_iso/confirm), slug
(sanitize) и базовый Env (общее ядро root/cmd/home). Плюс примитивы, которые оба
пакета успели скопировать независимо с расходящимся поведением и которые сведены
сюда к одному источнику истины: атомарная запись (atomic_write_text/json), поиск
корня репо/монорепо (find_repo_root/find_monorepo_root), разбор флагов/аргументов
(parse_flags/parse_args) и защищённый запуск подпроцесса (run_cmd), а также единый
разбор YAML-frontmatter (parse_frontmatter/parse_inline_list — superset четырёх
разошедшихся копий skiller/harness/maind). Доменные надстройки — path-property Env,
HTTP — остаются в common.py каждого пакета (они расходятся по контракту и не дословны).

Импортируется как пакет `core` (PYTHONPATH = корень монорепо; см. bin-лаунчеры).
Без сторонних зависимостей."""
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
from .provider import (CapabilityId, CapabilityRequirement, ConfigProvenance,
                       ConfigSource, DiagnosticSeverity, EffectiveProvider,
                       NativeExtensionId, ProviderAdapter, ProviderDecision,
                       ProviderDiagnostic, ProviderId, ProviderSelection,
                       SupportLevel)
from .provider_config import (CapabilitySupport, NativeExtension,
                              ProviderConfigCatalog, ProviderConfigLayer,
                              ResolvedProviderConfig, effective_projection,
                              resolve_provider_config)
from .provider_manifest import (ManifestCapability, ManifestEvidence,
                                ManifestNativeExtension, ManifestSupport,
                                ProviderCapabilityManifest, ProviderManifestDiagnostic,
                                ProviderManifestError, load_provider_manifest,
                                parse_provider_manifest, provider_config_catalog,
                                provider_manifest_canonical_bytes,
                                provider_manifest_sha256, provider_support_projection,
                                support_for)
from .provider_artifact import (ArtifactAdapterIdentity, ArtifactProvenance,
                                ArtifactRenderRequest, ArtifactRenderResult,
                                ArtifactSource, ArtifactTarget,
                                canonical_json_bytes, plan_artifact_render,
                                sha256_digest, validate_target_path)
from .provider_lock import (ArtifactAction, ArtifactActionKind, ArtifactLock, ArtifactPlan,
                            BootstrapTransferAdmission, ChainedBootstrapTransferAdmission,
                            DriftObservation, LOCK_RELATIVE_PATH,
                            LOCK_SCHEMA_VERSION, apply_plan, artifact_dry_run, parse_lock,
                            plan_artifact_lock, plan_bootstrap_transfer,
                            plan_chained_bootstrap_transfer,
                            render_artifact_projection, serialize_lock)
from .provider_registry import (AdapterCatalog, AdapterDescriptor, AdapterSelection,
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
    "render_artifact_projection",
    "RegistrySeverity", "RegistryDiagnostic", "AdapterDescriptor", "AdapterSelection",
    "AdapterSelectionResult", "AdapterCatalog",
]
