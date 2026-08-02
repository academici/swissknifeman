"""Explicit immutable capability-aware catalog for provider artifact adapters.

The catalog receives adapter descriptors from an owning package.  It performs no
module discovery, environment lookup, provider-name branching, or global
registration; a caller supplies both the catalog and effective provider state.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Callable

from .values import (CapabilityId, CapabilityRequirement, EffectiveProvider,
                     NativeExtensionId, ProviderId, SupportLevel)
from .artifact import (ArtifactAdapterIdentity, ArtifactRenderRequest,
                       ArtifactRenderResult, plan_artifact_render)
from .config import ProviderConfigCatalog


_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")


class RegistrySeverity(str, Enum):
    ERROR = "error"


@dataclass(frozen=True, order=True)
class RegistryDiagnostic:
    """Stable machine-readable refusal data for a catalog selection."""

    severity: RegistrySeverity
    code: str
    provider_id: ProviderId
    artifact_kind: str
    subject_id: str = ""


@dataclass(frozen=True)
class AdapterDescriptor:
    """One package-supplied adapter and the capabilities it may consume."""

    artifact_kind: str
    identity: ArtifactAdapterIdentity
    renderer: Callable[[ArtifactRenderRequest], bytes]
    optional_capability_requirements: tuple[CapabilityRequirement, ...] = ()
    native_extensions: tuple[NativeExtensionId, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.artifact_kind, "artifact_kind")
        if not isinstance(self.identity, ArtifactAdapterIdentity):
            raise TypeError("identity must be ArtifactAdapterIdentity")
        if not callable(self.renderer):
            raise TypeError("renderer must be callable")
        _requirements(self.optional_capability_requirements, "optional_capability_requirements")
        if not isinstance(self.native_extensions, tuple) or not all(
                isinstance(item, NativeExtensionId) for item in self.native_extensions):
            raise TypeError("native_extensions must be a tuple of NativeExtensionId")
        if len(set(self.native_extensions)) != len(self.native_extensions):
            raise ValueError("native_extensions must not repeat IDs")
        object.__setattr__(self, "optional_capability_requirements", _ordered_requirements(
            self.optional_capability_requirements))
        object.__setattr__(self, "native_extensions", tuple(sorted(self.native_extensions)))

    @property
    def key(self) -> tuple[ProviderId, str]:
        return self.identity.provider_id, self.artifact_kind


@dataclass(frozen=True)
class AdapterSelection:
    """A successful descriptor selection and its effective capability inputs."""

    descriptor: AdapterDescriptor
    effective_capabilities: tuple[CapabilityRequirement, ...]
    enabled_native_extensions: tuple[NativeExtensionId, ...]
    diagnostics: tuple[RegistryDiagnostic, ...] = ()


@dataclass(frozen=True)
class AdapterSelectionResult:
    """Exactly one selected adapter or stable refusal diagnostics, never both."""

    selection: AdapterSelection | None
    diagnostics: tuple[RegistryDiagnostic, ...]

    def __post_init__(self) -> None:
        if self.selection is not None and self.diagnostics:
            raise ValueError("selection result cannot contain both selection and diagnostics")
        if self.selection is None and not self.diagnostics:
            raise ValueError("selection result must contain selection or diagnostics")


@dataclass(frozen=True)
class AdapterCatalog:
    """A caller-built immutable descriptor sequence with deterministic selection."""

    descriptors: tuple[AdapterDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.descriptors, tuple) or not all(
                isinstance(item, AdapterDescriptor) for item in self.descriptors):
            raise TypeError("descriptors must be a tuple of AdapterDescriptor")
        object.__setattr__(self, "descriptors", tuple(sorted(
            self.descriptors, key=lambda item: (item.identity.provider_id.value, item.artifact_kind,
                                                 item.identity.adapter_id))))

    def select(self, *, provider_id: ProviderId, artifact_kind: str,
               capability_catalog: ProviderConfigCatalog,
               effective_provider: EffectiveProvider) -> AdapterSelectionResult:
        """Gate one adapter before rendering using supplied frozen catalog data."""
        if not isinstance(provider_id, ProviderId):
            raise TypeError("provider_id must be ProviderId")
        _require_identifier(artifact_kind, "artifact_kind")
        if not isinstance(capability_catalog, ProviderConfigCatalog):
            raise TypeError("capability_catalog must be ProviderConfigCatalog")
        if not isinstance(effective_provider, EffectiveProvider):
            raise TypeError("effective_provider must be EffectiveProvider")

        matches = tuple(item for item in self.descriptors
                        if item.identity.provider_id is provider_id and item.artifact_kind == artifact_kind)
        if len(matches) > 1:
            return _refusal(provider_id, artifact_kind, "REGISTRY_DUPLICATE_ADAPTER",
                            f"{provider_id.value}:{artifact_kind}")
        if not matches:
            if provider_id not in capability_catalog.providers:
                return _refusal(provider_id, artifact_kind, "REGISTRY_UNKNOWN_PROVIDER", provider_id.value)
            return _refusal(provider_id, artifact_kind, "REGISTRY_UNKNOWN_ARTIFACT_KIND", artifact_kind)
        descriptor = matches[0]
        if effective_provider.provider_id is not provider_id:
            return _refusal(provider_id, artifact_kind, "REGISTRY_PROVIDER_MISMATCH",
                            effective_provider.provider_id.value)
        if descriptor.identity.capability_catalog_version != capability_catalog.catalog_version:
            return _refusal(provider_id, artifact_kind, "REGISTRY_CATALOG_VERSION_MISMATCH",
                            descriptor.identity.capability_catalog_version)
        if not effective_provider.enabled:
            return _refusal(provider_id, artifact_kind, "REGISTRY_PROVIDER_DISABLED", provider_id.value)

        supports = {(record.provider_id, record.capability_id): record.level
                    for record in capability_catalog.capability_support}
        decisions = {decision.identifier: decision.enabled for decision in effective_provider.capabilities}
        required_diagnostics = _requirement_diagnostics(
            descriptor.identity.capability_requirements, supports, decisions, provider_id, artifact_kind)
        if required_diagnostics:
            return AdapterSelectionResult(None, required_diagnostics)
        optional = tuple(requirement for requirement in descriptor.optional_capability_requirements
                         if not _requirement_diagnostics((requirement,), supports, decisions,
                                                         provider_id, artifact_kind))
        extensions = {item.extension_id: item.provider_id for item in capability_catalog.native_extensions}
        enabled = {decision.identifier for decision in effective_provider.native_extensions
                   if decision.enabled and isinstance(decision.identifier, NativeExtensionId)}
        selected_extensions = tuple(extension for extension in descriptor.native_extensions
                                    if extensions.get(extension) is provider_id and extension in enabled)
        return AdapterSelectionResult(AdapterSelection(
            descriptor, descriptor.identity.capability_requirements + optional, selected_extensions), ())

    def plan_render(self, selection: AdapterSelectionResult,
                    request: ArtifactRenderRequest) -> ArtifactRenderResult:
        """Render only a successful selection with its catalog-owned identity."""
        if not isinstance(selection, AdapterSelectionResult):
            raise TypeError("selection must be AdapterSelectionResult")
        if selection.selection is None:
            raise ValueError("cannot render a refused adapter selection")
        if not isinstance(request, ArtifactRenderRequest):
            raise TypeError("request must be ArtifactRenderRequest")
        descriptor = selection.selection.descriptor
        return plan_artifact_render(ArtifactRenderRequest(
            request.artifact_id, request.canonical_sources, request.target,
            descriptor.identity, tuple(dict(layer) for layer in request.override_layers),
            dict(request.semantic_parameters), descriptor.renderer))


def _refusal(provider_id: ProviderId, artifact_kind: str, code: str,
             subject_id: str) -> AdapterSelectionResult:
    return AdapterSelectionResult(None, (RegistryDiagnostic(
        RegistrySeverity.ERROR, code, provider_id, artifact_kind, subject_id),))


def _requirement_diagnostics(requirements: tuple[CapabilityRequirement, ...],
                             supports: dict[tuple[ProviderId, CapabilityId], SupportLevel],
                             decisions: dict[CapabilityId, bool], provider_id: ProviderId,
                             artifact_kind: str) -> tuple[RegistryDiagnostic, ...]:
    diagnostics = []
    for requirement in requirements:
        capability_id = requirement.capability_id
        level = supports.get((provider_id, capability_id))
        if decisions.get(capability_id) is False:
            diagnostics.append(RegistryDiagnostic(RegistrySeverity.ERROR,
                               "REGISTRY_CAPABILITY_DENIED", provider_id, artifact_kind,
                               capability_id.value))
        elif level is None:
            diagnostics.append(RegistryDiagnostic(RegistrySeverity.ERROR,
                               "REGISTRY_CAPABILITY_MISSING", provider_id, artifact_kind,
                               capability_id.value))
        elif level is SupportLevel.UNSUPPORTED:
            diagnostics.append(RegistryDiagnostic(RegistrySeverity.ERROR,
                               "REGISTRY_CAPABILITY_UNSUPPORTED", provider_id, artifact_kind,
                               capability_id.value))
        elif level not in requirement.accepted_levels:
            diagnostics.append(RegistryDiagnostic(RegistrySeverity.ERROR,
                               "REGISTRY_CAPABILITY_LEVEL_REJECTED", provider_id, artifact_kind,
                               capability_id.value))
    return tuple(sorted(diagnostics))


def _requirements(value: object, label: str) -> None:
    if not isinstance(value, tuple) or not all(isinstance(item, CapabilityRequirement) for item in value):
        raise TypeError(f"{label} must be a tuple of CapabilityRequirement")
    if len({item.capability_id for item in value}) != len(value):
        raise ValueError(f"{label} must not repeat capability IDs")


def _ordered_requirements(value: tuple[CapabilityRequirement, ...]) -> tuple[CapabilityRequirement, ...]:
    return tuple(sorted(value, key=lambda item: item.capability_id.value))


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"invalid {label}")
