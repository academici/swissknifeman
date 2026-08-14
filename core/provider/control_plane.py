"""Pure, versioned provider control-plane desired-state resolution.

This module composes already-resolved provider configuration with the capability
catalog.  It deliberately has no filesystem, environment, provider-output, or
write dependencies: adapter reconciliation and status evidence belong to later
control-plane layers.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping

from .config import ProviderConfigCatalog, ResolvedProviderConfig, effective_projection
from .values import ConfigProvenance, ConfigSource, ProviderId


CONTROL_PLANE_VERSION = "1.0.0"
_SEMVER_RE = re.compile(r"^1\.0\.\d+$")
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, order=True)
class ControlPlaneDiagnostic:
    """A stable, value-free diagnostic emitted by the desired-state boundary."""

    code: str
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.startswith("PCP_"):
            raise ValueError("control-plane diagnostic code must start with PCP_")
        if not isinstance(self.message, str):
            raise TypeError("control-plane diagnostic message must be str")


@dataclass(frozen=True)
class DesiredSnapshot:
    """Immutable canonical intent composed from frozen, already-read inputs."""

    provider_config_contract_version: str
    capability_catalog_version: str
    selection: tuple[tuple[str, tuple[tuple[str, object], ...]], ...]
    provenance: tuple[ConfigProvenance, ...]
    semantic_digest: str

    def __post_init__(self) -> None:
        _require_v1(self.provider_config_contract_version)
        _require_v1(self.capability_catalog_version)
        if not self.selection:
            raise ValueError("selection must not be empty")
        if tuple(key for key, _ in self.selection) != tuple(sorted(key for key, _ in self.selection)):
            raise ValueError("selection must be sorted by provider ID")
        if len({key for key, _ in self.selection}) != len(self.selection):
            raise ValueError("selection must not contain duplicate providers")
        if not all(isinstance(item, ConfigProvenance) for item in self.provenance):
            raise TypeError("provenance must contain ConfigProvenance")
        if tuple(item.effective_path for item in self.provenance) != tuple(
                sorted(item.effective_path for item in self.provenance)):
            raise ValueError("provenance must be sorted by effective path")
        if not _is_digest(self.semantic_digest):
            raise ValueError("semantic_digest must be a sha256 digest")
        if self.semantic_digest != _digest(self._unsigned_value()):
            raise ValueError("semantic_digest does not match canonical desired state")

    def _unsigned_value(self) -> dict[str, object]:
        return {
            "provider_config_contract_version": self.provider_config_contract_version,
            "capability_catalog_version": self.capability_catalog_version,
            "selection": {provider: _thaw_selection(value) for provider, value in self.selection},
            "provenance": [_provenance_value(item) for item in self.provenance],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_value(), "semantic_digest": self.semantic_digest}


@dataclass(frozen=True)
class ControlPlaneResolution:
    """No-write desired-state resolution result; errors never carry a snapshot."""

    desired: DesiredSnapshot | None
    diagnostics: tuple[ControlPlaneDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if self.desired is None and not self.diagnostics:
            raise ValueError("failed resolution must have diagnostics")
        if self.desired is not None and any(item.code == "PCP_SCHEMA_INVALID" for item in self.diagnostics):
            raise ValueError("schema errors cannot coexist with desired state")


def resolve_desired_snapshot(*, project_id: str, config: ResolvedProviderConfig,
                             catalog: ProviderConfigCatalog,
                             locale_policy: Mapping[str, object] | None = None) -> ControlPlaneResolution:
    """Compose an immutable desired snapshot from already-read, typed inputs.

    ``locale_policy`` is intentionally accepted only as a separately owned
    canonical input.  It is never rendered, persisted, or folded into provider
    semantic identity.
    """
    if not isinstance(project_id, str) or not _PROJECT_ID_RE.fullmatch(project_id):
        return _failure("PCP_IDENTITY_INVALID", "project identity is invalid")
    if not isinstance(config, ResolvedProviderConfig) or not isinstance(catalog, ProviderConfigCatalog):
        return _failure("PCP_SCHEMA_INVALID", "typed configuration and catalog are required")
    if locale_policy is not None and not isinstance(locale_policy, Mapping):
        return _failure("PCP_SCHEMA_INVALID", "locale policy must be an already-read mapping")
    if not _is_v1(config.contract_version) or not _is_v1(config.catalog_version) or not _is_v1(catalog.catalog_version):
        return _failure("PCP_VERSION_UNSUPPORTED", "provider configuration or catalog version is unsupported")
    if config.catalog_version != catalog.catalog_version:
        return _failure("PCP_VERSION_UNSUPPORTED", "provider configuration and catalog versions differ")
    if config.effective is None or any(item.severity.value == "error" for item in config.diagnostics):
        return _failure("PCP_SCHEMA_INVALID", "provider configuration did not resolve")

    projection = effective_projection(config)
    if projection is None:
        return _failure("PCP_SCHEMA_INVALID", "provider configuration has no effective selection")
    provider_ids = tuple(sorted(provider.value for provider in catalog.providers))
    if tuple(sorted(projection)) != provider_ids:
        return _failure("PCP_PROVIDER_SET_MISMATCH", "selection does not match the capability catalog")
    try:
        selection = tuple((provider_id, _freeze_selection(projection[provider_id]))
                          for provider_id in provider_ids)
        provenance = tuple(sorted(config.provenance, key=lambda item: item.effective_path))
        _validate_provenance(selection, provenance)
        unsigned = {
            "provider_config_contract_version": config.contract_version,
            "capability_catalog_version": catalog.catalog_version,
            "selection": {provider: _thaw_selection(value) for provider, value in selection},
            "provenance": [_provenance_value(item) for item in provenance],
        }
        return ControlPlaneResolution(DesiredSnapshot(
            provider_config_contract_version=config.contract_version,
            capability_catalog_version=catalog.catalog_version,
            selection=selection,
            provenance=provenance,
            semantic_digest=_digest(unsigned),
        ), ())
    except (TypeError, ValueError) as error:
        return _failure("PCP_PROVENANCE_INVALID", str(error))


def parse_desired_snapshot(value: Mapping[str, object], *, providers: tuple[ProviderId, ...]) -> DesiredSnapshot:
    """Parse a serialized desired snapshot without accepting legacy shapes."""
    if not isinstance(value, Mapping):
        raise ValueError("desired snapshot must be an object")
    expected = {"provider_config_contract_version", "capability_catalog_version", "selection",
                "provenance", "semantic_digest"}
    if set(value) != expected:
        raise ValueError("desired snapshot fields are invalid")
    selection_value = value["selection"]
    if not isinstance(selection_value, Mapping):
        raise ValueError("selection must be an object")
    expected_providers = tuple(sorted(provider.value for provider in providers))
    if tuple(sorted(selection_value)) != expected_providers:
        raise ValueError("selection provider set is invalid")
    selection = tuple((provider, _freeze_selection(selection_value[provider])) for provider in expected_providers)
    provenance_value = value["provenance"]
    if not isinstance(provenance_value, list):
        raise ValueError("provenance must be an array")
    provenance = tuple(_parse_provenance(item) for item in provenance_value)
    return DesiredSnapshot(
        provider_config_contract_version=_string(value["provider_config_contract_version"]),
        capability_catalog_version=_string(value["capability_catalog_version"]),
        selection=selection,
        provenance=provenance,
        semantic_digest=_string(value["semantic_digest"]),
    )


def canonical_desired_bytes(snapshot: DesiredSnapshot) -> bytes:
    """Return the canonical serialized desired-state snapshot."""
    if not isinstance(snapshot, DesiredSnapshot):
        raise TypeError("snapshot must be DesiredSnapshot")
    return _canonical_bytes(snapshot.to_dict())


def _failure(code: str, message: str) -> ControlPlaneResolution:
    return ControlPlaneResolution(None, (ControlPlaneDiagnostic(code, message),))


def _freeze_selection(value: object) -> tuple[tuple[str, object], ...]:
    if not isinstance(value, Mapping) or set(value) != {"enabled", "capabilities", "native_extensions"}:
        raise ValueError("provider selection fields are invalid")
    if not isinstance(value["enabled"], bool):
        raise ValueError("provider enabled flag must be bool")
    result: list[tuple[str, object]] = [("enabled", value["enabled"])]
    for field in ("capabilities", "native_extensions"):
        leaves = value[field]
        if not isinstance(leaves, Mapping) or not all(isinstance(key, str) and isinstance(item, bool)
                                                      for key, item in leaves.items()):
            raise ValueError(f"{field} must be a boolean map")
        result.append((field, tuple(sorted(leaves.items()))))
    return tuple(result)


def _thaw_selection(value: tuple[tuple[str, object], ...]) -> dict[str, object]:
    return {key: dict(item) if key != "enabled" else item for key, item in value}


def _validate_provenance(selection: tuple[tuple[str, tuple[tuple[str, object], ...]], ...],
                         provenance: tuple[ConfigProvenance, ...]) -> None:
    expected = set()
    for provider, selection_value in selection:
        values = dict(selection_value)
        expected.add(f"/selection/{provider}/enabled")
        for field in ("capabilities", "native_extensions"):
            expected.update(f"/selection/{provider}/{field}/{key}" for key, _ in values[field])
    actual = {item.effective_path for item in provenance}
    if len(actual) != len(provenance) or actual != expected:
        raise ValueError("provenance must contain exactly one record per desired leaf")


def _provenance_value(item: ConfigProvenance) -> dict[str, object]:
    return {
        "effective_path": item.effective_path,
        "source": {"kind": item.source.kind, "id": item.source.id,
                   "carrier": item.source.carrier, "path": item.source.path},
        "source_path": item.source_path,
        "explicit": item.explicit,
    }


def _parse_provenance(value: object) -> ConfigProvenance:
    if not isinstance(value, Mapping) or set(value) != {"effective_path", "source", "source_path", "explicit"}:
        raise ValueError("provenance record fields are invalid")
    source = value["source"]
    if not isinstance(source, Mapping) or set(source) != {"kind", "id", "carrier", "path"}:
        raise ValueError("provenance source fields are invalid")
    return ConfigProvenance(
        _string(value["effective_path"]),
        ConfigSource(_string(source["kind"]), _string(source["id"]),
                     _string(source["carrier"]), _string(source["path"])),
        _string(value["source_path"]), _bool(value["explicit"]),
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _is_v1(value: object) -> bool:
    return isinstance(value, str) and bool(_SEMVER_RE.fullmatch(value))


def _require_v1(value: object) -> None:
    if not _is_v1(value):
        raise ValueError("version must be a supported v1 SemVer")


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("value must be str")
    return value


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("value must be bool")
    return value
