"""Immutable P5 provider-harness profile catalog and fail-closed resolver."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from core.provider.manifest import default_manifest_path
from core import (DiagnosticSeverity, EffectiveProvider, ProviderCapabilityManifest,
                  ProviderId, load_provider_manifest, support_for)


_PROFILE_IDS = ("observe", "workspace-contained", "trusted-full-access")
_SURFACE_KINDS = frozenset({"settings", "security", "lifecycle", "context", "mcp",
                            "agents", "agent-packs", "workflows", "doctor"})
_SCOPES = frozenset({"project", "user", "managed"})
_ORIGINS = frozenset({"operation", "project", "fleet-project", "fleet-defaults", "legacy"})
_CAPABILITY_MANIFEST_PATH = default_manifest_path()


@dataclass(frozen=True, order=True)
class HarnessDiagnostic:
    severity: DiagnosticSeverity
    code: str
    provider_id: ProviderId
    profile_id: str
    surface_id: str = ""
    target_scope: str = ""
    path: str = ""
    required: bool = True
    observed: str = ""
    provenance: tuple[tuple[str, str], ...] = ()
    message: str = ""
    next_action: str = ""


@dataclass(frozen=True)
class SecurityIntent:
    trust_requirement: str
    approval_intent: str
    sandbox_intent: str
    explicit_operation_id: None
    target_identity: None
    inheritable: bool


@dataclass(frozen=True)
class Profile:
    id: str
    intent: str
    required_surfaces: tuple[str, ...]
    optional_surfaces: tuple[str, ...]
    allowed_target_scopes: tuple[str, ...]
    security: SecurityIntent


@dataclass(frozen=True)
class Surface:
    id: str
    kind: str
    intent: str
    required_capabilities: tuple[tuple[str, tuple[str, ...]], ...]
    secret_refs: tuple[str, ...]
    ownership: str
    required: bool


@dataclass(frozen=True)
class ProfileCatalog:
    contract_version: str
    catalog_version: str
    profiles: tuple[Profile, ...]
    surfaces: tuple[Surface, ...]

    def profile(self, profile_id: str) -> Profile | None:
        return next((item for item in self.profiles if item.id == profile_id), None)


@dataclass(frozen=True)
class ProfileResolution:
    profile: Profile | None
    provider_id: ProviderId
    target_scope: str
    operation_id: str | None
    target_identity: str | None
    diagnostics: tuple[HarnessDiagnostic, ...]

    @property
    def green(self) -> bool:
        return self.profile is not None and not self.diagnostics


def default_catalog_path(env) -> Path:
    return Path(env.root) / "configs" / "common" / "profile-catalog.json"


def load_catalog(path: Path, *, capability_manifest: ProviderCapabilityManifest | None = None
                 ) -> ProfileCatalog:
    """Load an explicit common catalog and validate it against the root manifest."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"contract_version", "catalog_version", "profiles", "surfaces"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    if value["contract_version"] != "1.0.0" or value["catalog_version"] != "1.0.0":
        raise ValueError("HARNESS_VERSION_UNSUPPORTED")
    profiles = tuple(_profile(item) for item in value["profiles"])
    surfaces = tuple(_surface(item) for item in value["surfaces"])
    if tuple(item.id for item in profiles) != _PROFILE_IDS or len({item.id for item in surfaces}) != len(surfaces):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    surface_ids = {item.id for item in surfaces}
    if any(set(profile.required_surfaces + profile.optional_surfaces) - surface_ids
           or set(profile.required_surfaces) & set(profile.optional_surfaces) for profile in profiles):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    catalog = ProfileCatalog(value["contract_version"], value["catalog_version"], profiles, surfaces)
    manifest = (load_provider_manifest(_CAPABILITY_MANIFEST_PATH)
                if capability_manifest is None else capability_manifest)
    _validate_capability_manifest(catalog, manifest)
    return catalog


def resolve_profile(catalog: ProfileCatalog, *, provider_id: ProviderId, profile_id: str,
                    target_scope: str, trusted: bool, operation_id: str | None = None,
                    target_identity: str | None = None, origin: str | None = None,
                    effective_provider: EffectiveProvider | None = None) -> ProfileResolution:
    """Resolve one semantic plan before renderer or artifact planning can occur."""
    if not isinstance(catalog, ProfileCatalog) or not isinstance(provider_id, ProviderId):
        raise TypeError("catalog and provider_id are required")
    if not isinstance(effective_provider, EffectiveProvider):
        raise TypeError("effective_provider is required")
    profile = catalog.profile(profile_id)
    diagnostics = []
    if profile is None:
        diagnostics.append(_diagnostic("HARNESS_ID_INVALID", provider_id, profile_id, "unknown profile"))
    if target_scope not in _SCOPES:
        diagnostics.append(_diagnostic("HARNESS_SCOPE_UNSUPPORTED", provider_id, profile_id, "unknown target scope"))
    if origin not in _ORIGINS:
        diagnostics.append(_diagnostic("HARNESS_MAPPING_MISSING", provider_id, profile_id, "unknown selection origin"))
    if effective_provider.provider_id is not provider_id:
        diagnostics.append(_diagnostic("HARNESS_MAPPING_MISSING", provider_id, profile_id,
                                       "effective provider does not match selection"))
    elif not effective_provider.enabled:
        diagnostics.append(_diagnostic("HARNESS_PROVIDER_DISABLED", provider_id, profile_id,
                                       "effective provider is disabled"))
    if profile is not None and target_scope not in profile.allowed_target_scopes:
        diagnostics.append(_diagnostic("HARNESS_SCOPE_UNSUPPORTED", provider_id, profile_id, "scope is not allowed"))
    if profile is not None and profile.security.trust_requirement != "not-required" and not trusted:
        diagnostics.append(_diagnostic("HARNESS_TRUST_REQUIRED", provider_id, profile_id, "trust prerequisite is unsatisfied"))
    if profile_id == "trusted-full-access":
        if origin != "operation":
            diagnostics.append(_diagnostic("HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN", provider_id, profile_id, "full access cannot be inherited"))
        if operation_id != "self-host-apply" or not target_identity or not target_identity.startswith("repo:"):
            diagnostics.append(_diagnostic("HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED", provider_id, profile_id, "exact operation and target are required"))
    return ProfileResolution(profile if not diagnostics else None, provider_id, target_scope,
                             operation_id, target_identity, tuple(sorted(diagnostics)))


def _profile(value: object) -> Profile:
    if not isinstance(value, dict) or set(value) != {"id", "intent", "required_surfaces", "optional_surfaces", "allowed_target_scopes", "security"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    profile_id = value["id"]
    if profile_id not in _PROFILE_IDS or not isinstance(value["intent"], str):
        raise ValueError("HARNESS_ID_INVALID")
    required = _ordered_ids(value["required_surfaces"])
    optional = _ordered_ids(value["optional_surfaces"])
    scopes = _ordered_scopes(value["allowed_target_scopes"])
    security = value["security"]
    if (not isinstance(security, dict)
            or set(security) != {"trust_requirement", "approval_intent", "sandbox_intent", "explicit_operation_id", "target_identity", "inheritable"}
            or security["explicit_operation_id"] is not None
            or security["target_identity"] is not None
            or security["inheritable"] is not False):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    if any(token in json.dumps(value, ensure_ascii=False) for token in (".claude", ".codex", "PreToolUse", "approval_policy", "sandbox_mode")):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return Profile(profile_id, value["intent"], required, optional, scopes, SecurityIntent(
        security["trust_requirement"], security["approval_intent"], security["sandbox_intent"],
        security["explicit_operation_id"], security["target_identity"], False))


def _surface(value: object) -> Surface:
    if not isinstance(value, dict) or set(value) != {"id", "kind", "intent", "required_capabilities", "secret_refs", "ownership", "required"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    if not all(isinstance(value[key], str) and value[key] for key in ("id", "kind", "intent")) or value["kind"] not in _SURFACE_KINDS:
        raise ValueError("HARNESS_ID_INVALID")
    capabilities = _capability_requirements(value["required_capabilities"])
    secret_refs = _ordered_ids(value["secret_refs"])
    if not isinstance(value["ownership"], str) or not value["ownership"] or not isinstance(value["required"], bool):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return Surface(value["id"], value["kind"], value["intent"], capabilities, secret_refs,
                   value["ownership"], value["required"])


def _ordered_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value) or len(set(value)) != len(value):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return tuple(value)


def _ordered_scopes(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(item not in _SCOPES for item in value) or len(set(value)) != len(value):
        raise ValueError("HARNESS_SCOPE_UNSUPPORTED")
    return tuple(value)


def _capability_requirements(value: object) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(value, list):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    requirements = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"capability_id", "accepted_levels"}:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        capability_id, accepted_levels = item["capability_id"], item["accepted_levels"]
        if not isinstance(capability_id, str) or not capability_id or not isinstance(accepted_levels, list) or not accepted_levels or not all(isinstance(level, str) and level for level in accepted_levels):
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        requirements.append((capability_id, tuple(accepted_levels)))
    if len({item[0] for item in requirements}) != len(requirements):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return tuple(requirements)


def _diagnostic(code: str, provider_id: ProviderId, profile_id: str, message: str) -> HarnessDiagnostic:
    return HarnessDiagnostic(DiagnosticSeverity.ERROR, code, provider_id, profile_id,
                             path="/profile", message=message, next_action="refuse")


def _validate_capability_manifest(catalog: ProfileCatalog,
                                  manifest: ProviderCapabilityManifest) -> None:
    """Require the manifest matrix before any harness projection is considered."""
    if not isinstance(manifest, ProviderCapabilityManifest):
        raise TypeError("capability_manifest must be ProviderCapabilityManifest")
    required = {surface.id for surface in catalog.surfaces}
    required.update(capability for surface in catalog.surfaces
                    for capability, _levels in surface.required_capabilities)
    for capability_id in sorted(required):
        for provider in ProviderId:
            try:
                support = support_for(manifest, capability_id, provider)
            except ValueError as error:
                raise ValueError(f"HARNESS_CAPABILITY_MANIFEST_INVALID:{provider.value}:"
                                 f"{capability_id}:missing") from error
            declared = next((levels for surface in catalog.surfaces
                             for identifier, levels in surface.required_capabilities
                             if identifier == capability_id), None)
            if declared is not None and support.level.value not in declared:
                raise ValueError(f"HARNESS_CAPABILITY_MANIFEST_INVALID:{provider.value}:"
                                 f"{capability_id}:level-mismatch")
