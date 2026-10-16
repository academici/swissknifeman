"""Pure deterministic render plans for provider-managed artifacts.

This module owns neither filesystem state nor provider render semantics.  Callers
provide immutable semantic input and a renderer; P2.2 owns all target writes,
locks, drift classification, and repair.
"""
from dataclasses import dataclass
import re
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Callable, Mapping

from ..provider.values import CapabilityRequirement, ProviderId
from ..util.digest import canonical_json_bytes, canonical_value, sha256_tagged


_DEFAULT_CONTRACT_VERSION = "1.0.0"
_SUPPORTED_CONTRACT_VERSIONS = frozenset({"1.0.0", "1.1.0"})
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_BOUNDARY_MODES = frozenset({"whole-file", "managed-blocks"})


@dataclass(frozen=True, order=True)
class ArtifactSource:
    """One canonical source identity, normalized path, and exact content digest."""

    source_id: str
    path: str
    content_hash: str

    def __post_init__(self) -> None:
        _require_identifier(self.source_id, "source_id")
        object.__setattr__(self, "path", validate_target_path(self.path))
        _require_digest(self.content_hash, "content_hash")


@dataclass(frozen=True)
class ArtifactTarget:
    """A target-relative path and its immutable managed-boundary descriptor.

    ``managed_boundary`` is ``(mode, block_ids)``.  ``block_ids`` is empty for
    ``whole-file`` and is a non-empty ordered tuple for ``managed-blocks``.
    """

    path: str
    managed_boundary: tuple[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", validate_target_path(self.path))
        object.__setattr__(self, "managed_boundary", _validate_boundary(self.managed_boundary))


@dataclass(frozen=True)
class ArtifactAdapterIdentity:
    """Explicit adapter identity and immutable capability provenance."""

    adapter_id: str
    adapter_version: str
    provider_id: ProviderId
    capability_catalog_version: str
    capability_requirements: tuple[CapabilityRequirement, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.adapter_id, "adapter_id")
        _require_semver(self.adapter_version, "adapter_version")
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be ProviderId")
        _require_semver(self.capability_catalog_version, "capability_catalog_version")
        if not isinstance(self.capability_requirements, tuple):
            raise TypeError("capability_requirements must be tuple")
        if not all(isinstance(item, CapabilityRequirement) for item in self.capability_requirements):
            raise TypeError("capability_requirements must contain CapabilityRequirement")
        if len({item.capability_id for item in self.capability_requirements}) != len(self.capability_requirements):
            raise ValueError("capability_requirements must not repeat capability IDs")
        object.__setattr__(self, "capability_requirements", tuple(sorted(
            self.capability_requirements, key=lambda item: item.capability_id.value)))


@dataclass(frozen=True)
class ArtifactRenderRequest:
    """All semantic input for one pure render operation.

    Mappings supplied for semantic parameters are captured as sorted immutable
    pairs; override layers intentionally retain caller-declared precedence order.
    """

    artifact_id: str
    canonical_sources: tuple[ArtifactSource, ...]
    target: ArtifactTarget
    adapter: ArtifactAdapterIdentity
    override_layers: tuple[Mapping[str, object], ...]
    semantic_parameters: Mapping[str, object]
    renderer: Callable[["ArtifactRenderRequest"], bytes]
    contract_version: str = _DEFAULT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.artifact_id, "artifact_id")
        if not isinstance(self.canonical_sources, tuple) or not self.canonical_sources:
            raise ValueError("canonical_sources must be a non-empty tuple")
        if not all(isinstance(source, ArtifactSource) for source in self.canonical_sources):
            raise TypeError("canonical_sources must contain ArtifactSource")
        sources = tuple(sorted(self.canonical_sources))
        if len({(source.source_id, source.path) for source in sources}) != len(sources):
            raise ValueError("canonical_sources must not repeat source_id/path")
        object.__setattr__(self, "canonical_sources", sources)
        if not isinstance(self.target, ArtifactTarget):
            raise TypeError("target must be ArtifactTarget")
        if not isinstance(self.adapter, ArtifactAdapterIdentity):
            raise TypeError("adapter must be ArtifactAdapterIdentity")
        object.__setattr__(self, "override_layers", _validate_override_layers(
            self.override_layers, "override_layers"))
        object.__setattr__(self, "semantic_parameters", _immutable_mapping(
            self.semantic_parameters, "semantic_parameters"))
        if not callable(self.renderer):
            raise TypeError("renderer must be callable")
        _require_supported_contract_version(self.contract_version)


@dataclass(frozen=True)
class ArtifactProvenance:
    """A supported artifact-contract sidecar/lock record."""

    contract_version: str
    artifact_id: str
    canonical_sources: tuple[ArtifactSource, ...]
    adapter_id: str
    adapter_version: str
    provider_id: ProviderId
    target_path: str
    source_hash: str
    rendered_hash: str
    managed_boundary: tuple[str, tuple[str, ...]]
    override_layers: tuple[tuple[tuple[str, object], ...], ...]
    capability_requirements: tuple[CapabilityRequirement, ...]
    semantic_metadata: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        _require_supported_contract_version(self.contract_version)
        _require_identifier(self.artifact_id, "artifact_id")
        if not isinstance(self.canonical_sources, tuple) or not self.canonical_sources:
            raise ValueError("canonical_sources must be a non-empty tuple")
        if not all(isinstance(source, ArtifactSource) for source in self.canonical_sources):
            raise TypeError("canonical_sources must contain ArtifactSource")
        ordered_sources = tuple(sorted(self.canonical_sources))
        if self.canonical_sources != ordered_sources:
            raise ValueError("canonical_sources must be canonically ordered")
        if len({(source.source_id, source.path) for source in ordered_sources}) != len(ordered_sources):
            raise ValueError("canonical_sources must not repeat source_id/path")
        _require_identifier(self.adapter_id, "adapter_id")
        _require_semver(self.adapter_version, "adapter_version")
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be ProviderId")
        object.__setattr__(self, "target_path", validate_target_path(self.target_path))
        _require_digest(self.source_hash, "source_hash")
        _require_digest(self.rendered_hash, "rendered_hash")
        object.__setattr__(self, "managed_boundary", _validate_boundary(self.managed_boundary))
        object.__setattr__(self, "override_layers", _validate_override_layers(
            self.override_layers, "override_layers"))
        if not isinstance(self.capability_requirements, tuple):
            raise TypeError("capability_requirements must be tuple")
        if not all(isinstance(item, CapabilityRequirement) for item in self.capability_requirements):
            raise TypeError("capability_requirements must contain CapabilityRequirement")
        ordered_requirements = tuple(sorted(
            self.capability_requirements, key=lambda item: item.capability_id.value))
        if self.capability_requirements != ordered_requirements:
            raise ValueError("capability_requirements must be canonically ordered")
        if len({item.capability_id for item in ordered_requirements}) != len(ordered_requirements):
            raise ValueError("capability_requirements must not repeat capability IDs")
        metadata = _validate_semantic_metadata(self.semantic_metadata)
        if self.contract_version == "1.0.0" and metadata:
            raise ValueError("semantic_metadata requires artifact contract v1.1.0")
        object.__setattr__(self, "semantic_metadata", metadata)


@dataclass(frozen=True)
class ArtifactRenderResult:
    """Managed bytes and their provenance; this value never writes a target."""

    managed_bytes: bytes
    target: ArtifactTarget
    provenance: ArtifactProvenance


sha256_digest = sha256_tagged  # public name kept for the artifact contract


def validate_target_path(path: str) -> str:
    """Return a normalized project-relative POSIX path or reject it fail-closed."""
    if not isinstance(path, str) or not path or "\\" in path:
        raise ValueError("target path must be a non-empty relative POSIX path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or path in {".", ".."} or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError("target path must not be absolute or escaping")
    normalized = pure.as_posix()
    if path != normalized:
        raise ValueError("target path must be normalized")
    return normalized


def plan_artifact_render(request: ArtifactRenderRequest) -> ArtifactRenderResult:
    """Construct one deterministic render plan and its complete sidecar provenance."""
    if not isinstance(request, ArtifactRenderRequest):
        raise TypeError("request must be ArtifactRenderRequest")
    rendered = request.renderer(request)
    if not isinstance(rendered, bytes):
        raise TypeError("renderer must return bytes")
    source_hash = sha256_digest(canonical_json_bytes(_source_envelope(request)))
    provenance = ArtifactProvenance(
        contract_version=request.contract_version,
        artifact_id=request.artifact_id,
        canonical_sources=request.canonical_sources,
        adapter_id=request.adapter.adapter_id,
        adapter_version=request.adapter.adapter_version,
        provider_id=request.adapter.provider_id,
        target_path=request.target.path,
        source_hash=source_hash,
        rendered_hash=sha256_digest(rendered),
        managed_boundary=request.target.managed_boundary,
        override_layers=request.override_layers,
        capability_requirements=request.adapter.capability_requirements,
        semantic_metadata=(request.semantic_parameters
                           if request.contract_version == "1.1.0" else ()),
    )
    return ArtifactRenderResult(rendered, request.target, provenance)


def _source_envelope(request: ArtifactRenderRequest) -> dict[str, object]:
    return {
        "contract_version": request.contract_version,
        "canonical_sources": [
            {"source_id": source.source_id, "path": source.path, "hash": source.content_hash}
            for source in request.canonical_sources
        ],
        "capability_catalog_version": request.adapter.capability_catalog_version,
        "provider_id": request.adapter.provider_id.value,
        "adapter_id": request.adapter.adapter_id,
        "adapter_version": request.adapter.adapter_version,
        "override_layers": [_mapping_from_pairs(layer) for layer in request.override_layers],
        "capability_requirements": [
            {"id": requirement.capability_id.value,
             "accepted_levels": [level.value for level in requirement.accepted_levels]}
            for requirement in request.adapter.capability_requirements
        ],
        "semantic_parameters": _mapping_from_pairs(request.semantic_parameters),
    }


def _validate_boundary(value: object) -> tuple[str, tuple[str, ...]]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError("managed_boundary must be a (mode, block_ids) tuple")
    mode, block_ids = value
    if mode not in _BOUNDARY_MODES or not isinstance(block_ids, tuple):
        raise ValueError("managed_boundary is invalid")
    if not all(isinstance(block_id, str) and block_id for block_id in block_ids):
        raise ValueError("managed block IDs must be non-empty strings")
    if len(set(block_ids)) != len(block_ids):
        raise ValueError("managed block IDs must not repeat")
    if (mode == "whole-file" and block_ids) or (mode == "managed-blocks" and not block_ids):
        raise ValueError("managed boundary mode and block IDs disagree")
    return mode, block_ids


def _immutable_mapping(value: object, label: str) -> tuple[tuple[str, object], ...]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"{label} keys must be strings")
    return tuple((key, canonical_value(item)) for key, item in sorted(value.items()))


def _validate_semantic_metadata(value: object) -> tuple[tuple[str, object], ...]:
    if not _is_pairs(value):
        raise TypeError("semantic_metadata must be an immutable mapping")
    if len({key for key, _ in value}) != len(value):
        raise ValueError("semantic_metadata must not repeat keys")
    if tuple(key for key, _ in value) != tuple(sorted(key for key, _ in value)):
        raise ValueError("semantic_metadata must be canonically ordered")
    return tuple((key, _immutable_json_value(item)) for key, item in value)


def _immutable_json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise TypeError("canonical JSON values must not use floats")
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        return MappingProxyType({
            key: _immutable_json_value(item) for key, item in sorted(value.items())
        })
    if isinstance(value, (tuple, list)):
        return tuple(_immutable_json_value(item) for item in value)
    raise TypeError("value is not canonical JSON data")


def _validate_override_layers(value: object, label: str) -> tuple[tuple[tuple[str, object], ...], ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{label} must be tuple")
    layers = []
    ids = set()
    owners = set()
    orders = set()
    for layer in value:
        if _is_pairs(layer) and len({item[0] for item in layer}) != len(layer):
            raise ValueError("override layer must not repeat keys")
        mapping = _mapping_from_pairs(layer) if _is_pairs(layer) else layer
        canonical = _immutable_mapping(mapping, "override layer")
        keys = {key for key, _ in canonical}
        if keys != {"id", "owner", "order", "provenance"}:
            raise ValueError("override layer has an unsupported shape")
        data = _mapping_from_pairs(canonical)
        _require_identifier(data["id"], "override id")
        _require_identifier(data["owner"], "override owner")
        order = data["order"]
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise ValueError("override order must be a non-negative integer")
        provenance = data["provenance"]
        if provenance in ({}, (), [], None, ""):
            raise ValueError("override provenance must be non-empty")
        canonical_value(provenance)
        if data["id"] in ids or data["owner"] in owners or order in orders:
            raise ValueError("override layers must have unique IDs, owners, and orders")
        ids.add(data["id"])
        owners.add(data["owner"])
        orders.add(order)
        layers.append(canonical)
    return tuple(layers)


def _is_pairs(value: object) -> bool:
    return (isinstance(value, tuple) and all(isinstance(item, tuple) and len(item) == 2
                                              and isinstance(item[0], str) for item in value))


def _mapping_from_pairs(value: tuple[tuple[str, object], ...]) -> dict[str, object]:
    return {key: item for key, item in value}


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"invalid {label}")


def _require_digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{label} must be a SHA-256 digest")


def _require_semver(value: object, label: str) -> None:
    if not isinstance(value, str) or not _SEMVER_RE.fullmatch(value):
        raise ValueError(f"{label} must be SemVer")


def _require_supported_contract_version(value: object) -> None:
    _require_semver(value, "contract_version")
    if value not in _SUPPORTED_CONTRACT_VERSIONS:
        raise ValueError("unsupported artifact contract version")
