"""Pure provider-configuration resolution for provider-neutral carriers."""
from dataclasses import dataclass
from typing import Mapping

from .provider import (CapabilityId, ConfigProvenance, ConfigSource,
                       DiagnosticSeverity, EffectiveProvider, NativeExtensionId,
                       ProviderDecision, ProviderDiagnostic, ProviderId, SupportLevel)


_RANKS = ("operation", "project", "fleet-project", "fleet-defaults")
_SEVERITY_ORDER = {DiagnosticSeverity.ERROR: 0, DiagnosticSeverity.WARNING: 1,
                   DiagnosticSeverity.INFO: 2}


@dataclass(frozen=True, order=True)
class CapabilitySupport:
    capability_id: CapabilityId
    provider_id: ProviderId
    level: SupportLevel


@dataclass(frozen=True, order=True)
class NativeExtension:
    extension_id: NativeExtensionId
    provider_id: ProviderId


@dataclass(frozen=True)
class ProviderConfigCatalog:
    catalog_version: str
    providers: tuple[ProviderId, ...]
    capability_support: tuple[CapabilitySupport, ...]
    native_extensions: tuple[NativeExtension, ...]

    def __post_init__(self) -> None:
        if not _is_v1_version(self.catalog_version):
            raise ValueError("catalog_version must be a supported SemVer")
        if not self.providers or len(set(self.providers)) != len(self.providers):
            raise ValueError("providers must be a non-empty unique tuple")
        if not all(isinstance(provider, ProviderId) for provider in self.providers):
            raise TypeError("providers must contain ProviderId")
        if len({(x.capability_id, x.provider_id) for x in self.capability_support}) != len(self.capability_support):
            raise ValueError("capability support records must be unique")
        if len({x.extension_id for x in self.native_extensions}) != len(self.native_extensions):
            raise ValueError("native extensions must be unique")


@dataclass(frozen=True)
class ProviderConfigLayer:
    source: ConfigSource
    value: Mapping[str, object]


@dataclass(frozen=True)
class ResolvedProviderConfig:
    contract_version: str
    catalog_version: str
    effective: tuple[EffectiveProvider, ...] | None
    provenance: tuple[ConfigProvenance, ...]
    diagnostics: tuple[ProviderDiagnostic, ...]

    @property
    def selection(self) -> tuple[EffectiveProvider, ...] | None:
        return self.effective


def resolve_provider_config(*, catalog: ProviderConfigCatalog,
                            operation: ProviderConfigLayer | tuple[ProviderConfigLayer, ...] | None = None,
                            project: ProviderConfigLayer | tuple[ProviderConfigLayer, ...] | None = None,
                            fleet_project: ProviderConfigLayer | tuple[ProviderConfigLayer, ...] | None = None,
                            fleet_defaults: ProviderConfigLayer | tuple[ProviderConfigLayer, ...] | None = None) -> ResolvedProviderConfig:
    """Resolve already-read layers; this function has no filesystem or environment I/O."""
    supplied = {"operation": operation, "project": project,
                "fleet-project": fleet_project, "fleet-defaults": fleet_defaults}
    diagnostics: list[ProviderDiagnostic] = []
    layers: dict[str, ProviderConfigLayer] = {}
    for rank in _RANKS:
        candidate = supplied[rank]
        if isinstance(candidate, tuple):
            if not candidate:
                continue
            if len(candidate) != 1:
                source = candidate[0].source if candidate else _synthetic_source(rank)
                code = "PCFG_DUPLICATE_FLEET_PROJECT" if rank == "fleet-project" else "PCFG_LAYER_CONFLICT"
                diagnostics.append(_diagnostic(code, source.path, source))
                continue
            candidate = candidate[0]
        if candidate is not None:
            if candidate.source.kind != rank:
                diagnostics.append(_diagnostic("PCFG_LAYER_CONFLICT", candidate.source.path, candidate.source))
            else:
                layers[rank] = candidate
                diagnostics.extend(_validate_layer(candidate, catalog))
    if diagnostics:
        return _result(catalog, None, (), diagnostics)

    selections: dict[ProviderId, dict[str, dict[str, tuple[bool, ConfigSource, str, bool]] | tuple[bool, ConfigSource, str, bool]]] = {}
    legacy = ConfigSource("legacy", "legacy:claude-code-compat", "legacy", "/")
    for provider in catalog.providers:
        selections[provider] = {"enabled": (provider is ProviderId.CLAUDE_CODE, legacy, "/", False),
                                "capabilities": {}, "native_extensions": {}}
    for rank in reversed(_RANKS):
        layer = layers.get(rank)
        if layer is None:
            continue
        source = layer.source
        selection = layer.value["selection"]
        for provider_text, provider_value in selection.items():
            provider = ProviderId(provider_text)
            target = selections[provider]
            for field in ("enabled", "capabilities", "native_extensions"):
                if field not in provider_value:
                    continue
                source_path = f"{source.path}/selection/{provider_text}/{field}"
                if field == "enabled":
                    target[field] = (provider_value[field], source, source_path, True)
                else:
                    for key, value in provider_value[field].items():
                        target[field][key] = (value, source, f"{source_path}/{key}", True)
    effective, provenance = [], []
    for provider in sorted(catalog.providers, key=lambda item: item.value):
        record = selections[provider]
        enabled, source, path, explicit = record["enabled"]
        provenance.append(ConfigProvenance(f"/selection/{provider.value}/enabled", source, path, explicit))
        decisions = []
        extensions = []
        for key, (value, source, path, explicit) in record["capabilities"].items():
            decisions.append(ProviderDecision(CapabilityId(key), value))
            provenance.append(ConfigProvenance(f"/selection/{provider.value}/capabilities/{key}", source, path, explicit))
        for key, (value, source, path, explicit) in record["native_extensions"].items():
            extensions.append(ProviderDecision(NativeExtensionId(key), value))
            provenance.append(ConfigProvenance(f"/selection/{provider.value}/native_extensions/{key}", source, path, explicit))
        effective.append(EffectiveProvider(provider, enabled, tuple(decisions), tuple(extensions)))
    if not layers:
        diagnostics.append(_diagnostic("PCFG_LEGACY_DEFAULT_APPLIED", "/", legacy))
    return _result(catalog, tuple(effective), tuple(sorted(provenance)), diagnostics)


def effective_projection(result: ResolvedProviderConfig) -> dict[str, object] | None:
    if result.effective is None:
        return None
    return {provider.provider_id.value: {"enabled": provider.enabled,
            "capabilities": {item.identifier.value: item.enabled for item in provider.capabilities},
            "native_extensions": {item.identifier.value: item.enabled for item in provider.native_extensions}}
            for provider in result.effective}


def _validate_layer(layer: ProviderConfigLayer, catalog: ProviderConfigCatalog) -> list[ProviderDiagnostic]:
    value, source, out = layer.value, layer.source, []
    if not isinstance(value, Mapping):
        return [_diagnostic("PCFG_SCHEMA_INVALID", source.path, source)]
    unknown = set(value) - {"contract_version", "selection"}
    for key in sorted(unknown): out.append(_diagnostic("PCFG_UNKNOWN_FIELD", f"{source.path}/{key}", source))
    version = value.get("contract_version")
    if version is None: out.append(_diagnostic("PCFG_VERSION_REQUIRED", f"{source.path}/contract_version", source))
    elif not _is_v1_version(version): out.append(_diagnostic("PCFG_VERSION_UNSUPPORTED", f"{source.path}/contract_version", source))
    selection = value.get("selection")
    if not isinstance(selection, Mapping) or not selection:
        out.append(_diagnostic("PCFG_SCHEMA_INVALID", f"{source.path}/selection", source)); return out
    extensions = {item.extension_id.value: item for item in catalog.native_extensions}
    supports = {(item.provider_id, item.capability_id.value): item.level for item in catalog.capability_support}
    for provider_text in sorted(selection):
        path = f"{source.path}/selection/{provider_text}"
        if provider_text not in {item.value for item in catalog.providers}:
            out.append(_diagnostic("PCFG_UNKNOWN_PROVIDER", path, source)); continue
        provider = ProviderId(provider_text); record = selection[provider_text]
        if not isinstance(record, Mapping) or not record:
            out.append(_diagnostic("PCFG_SCHEMA_INVALID", path, source)); continue
        for field in sorted(set(record) - {"enabled", "capabilities", "native_extensions"}):
            out.append(_diagnostic("PCFG_UNKNOWN_FIELD", f"{path}/{field}", source))
        if "enabled" in record and not isinstance(record["enabled"], bool):
            out.append(_diagnostic("PCFG_SCHEMA_INVALID", f"{path}/enabled", source))
        for field, extension in (("capabilities", False), ("native_extensions", True)):
            if field not in record: continue
            values = record[field]
            if not isinstance(values, Mapping) or not values:
                out.append(_diagnostic("PCFG_SCHEMA_INVALID", f"{path}/{field}", source)); continue
            for key in sorted(values):
                item_path = f"{path}/{field}/{key}"
                if not isinstance(values[key], bool): out.append(_diagnostic("PCFG_SCHEMA_INVALID", item_path, source)); continue
                if extension:
                    item = extensions.get(key)
                    if item is None: out.append(_diagnostic("PCFG_UNKNOWN_NATIVE_EXTENSION", item_path, source))
                    elif item.provider_id is not provider: out.append(_diagnostic("PCFG_EXTENSION_PROVIDER_MISMATCH", item_path, source))
                elif (provider, key) not in supports:
                    out.append(_diagnostic("PCFG_UNKNOWN_CAPABILITY", item_path, source))
                elif values[key] and supports[(provider, key)] is SupportLevel.UNSUPPORTED:
                    out.append(_diagnostic("PCFG_CAPABILITY_UNSUPPORTED", item_path, source))
    return out


def _diagnostic(code: str, path: str, source: ConfigSource) -> ProviderDiagnostic:
    severity = DiagnosticSeverity.INFO if code == "PCFG_LEGACY_DEFAULT_APPLIED" else DiagnosticSeverity.ERROR
    return ProviderDiagnostic(severity, code, path, source, code)


def _result(catalog, effective, provenance, diagnostics):
    rank = {name: index for index, name in enumerate(_RANKS + ("legacy",))}
    ordered = tuple(sorted(diagnostics, key=lambda item: (_SEVERITY_ORDER[item.severity], rank[item.source.kind], item.source.id, item.path, item.code)))
    return ResolvedProviderConfig("1.0.0", catalog.catalog_version, effective, tuple(provenance), ordered)


def _synthetic_source(kind: str) -> ConfigSource:
    carrier = "operation" if kind == "operation" else "config.json"
    return ConfigSource(kind, f"{kind}:ambiguous", carrier, "/")


def _is_v1_version(value: object) -> bool:
    if not isinstance(value, str): return False
    parts = value.split(".")
    return len(parts) == 3 and parts[0] == "1" and all(part.isdigit() for part in parts)
