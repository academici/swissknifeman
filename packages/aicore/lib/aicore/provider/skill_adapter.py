"""Immutable, additive Skill Core adapter descriptors.

This module deliberately keeps provider registration open: provider IDs are
validated descriptor data, not a shared Claude/Codex enum.  It validates the
seams that a package adapter contributes while preserving the supplied Skill
Core as an opaque immutable value.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping


_DOTTED_ID = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")
_SKILL_ID = re.compile(r"^[a-z][a-z0-9-]*/[a-z][a-z0-9-]*$")
_SEMVER = re.compile(r"^1\.0\.[0-9]+$")
_FORBIDDEN_SEMANTIC_KEYS = frozenset({
    "semantic_replacement", "job_override", "trigger_override", "invariant_override",
    "semantic_copy", "core", "skill_core", "job", "trigger", "invariants", "outputs",
})
_SEAM_KEYS = {
    "discovery": frozenset({"unit", "budget_unit", "degradation"}),
    "renderer": frozenset({"id", "version", "target_roots"}),
    "invocation": frozenset({"mode", "unsupported"}),
    "measurement": frozenset({"unit", "method", "bounds", "version"}),
    "replay": frozenset({"fixture_set", "unavailable"}),
}


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _dotted(value: object, label: str) -> str:
    value = _nonempty(value, label)
    if not _DOTTED_ID.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _tuple_of_ids(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{label} must be a non-empty tuple")
    result = tuple(_dotted(item, label) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must not repeat IDs")
    return result


def _seam(name: str, value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must contain its exact contract keys")
    _reject_semantic_replacement(value)
    if frozenset(value) != _SEAM_KEYS[name]:
        raise ValueError(f"{name} must contain its exact contract keys")
    if name == "renderer":
        _dotted(value["id"], "renderer.id")
        _nonempty(value["version"], "renderer.version")
        roots = value["target_roots"]
        if not isinstance(roots, tuple) or not roots or not all(
            isinstance(root, str) and root and not root.startswith("/") and ".." not in root.split("/")
            for root in roots
        ):
            raise ValueError("renderer.target_roots must be non-empty relative roots")
    elif name == "invocation":
        _nonempty(value["mode"], "invocation.mode")
        if not isinstance(value["unsupported"], bool):
            raise TypeError("invocation.unsupported must be bool")
    elif name == "measurement":
        for key in ("unit", "method", "version"):
            _nonempty(value[key], f"measurement.{key}")
        if not isinstance(value["bounds"], Mapping) or not value["bounds"]:
            raise ValueError("measurement.bounds must be non-empty")
    elif name == "replay":
        _nonempty(value["fixture_set"], "replay.fixture_set")
        if not isinstance(value["unavailable"], bool):
            raise TypeError("replay.unavailable must be bool")
    else:
        for key in _SEAM_KEYS[name]:
            _nonempty(value[key], f"discovery.{key}")
    return MappingProxyType(dict(value))


def _reject_semantic_replacement(value: object) -> None:
    if isinstance(value, Mapping):
        forbidden = _FORBIDDEN_SEMANTIC_KEYS.intersection(value)
        if forbidden:
            raise ValueError("ADAPTER_SEMANTIC_REPLACEMENT")
        for nested in value.values():
            _reject_semantic_replacement(nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _reject_semantic_replacement(nested)


@dataclass(frozen=True)
class SkillCoreRef:
    """Validated immutable semantic input, identified without provider metadata."""

    skill_id: str
    capability_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.skill_id, str) or not _SKILL_ID.fullmatch(self.skill_id):
            raise ValueError("invalid skill_id")
        object.__setattr__(self, "capability_ids", _tuple_of_ids(self.capability_ids, "capability_ids"))


@dataclass(frozen=True)
class SkillAdapterDescriptor:
    """Provider-owned additive seams for exactly one validated Skill Core."""

    contract_version: str
    adapter_id: str
    adapter_version: str
    provider_id: str
    core: SkillCoreRef
    required_capabilities: tuple[str, ...]
    optional_capabilities: tuple[str, ...]
    native_extensions: tuple[str, ...]
    discovery: Mapping[str, object]
    renderer: Mapping[str, object]
    invocation: Mapping[str, object]
    measurement: Mapping[str, object]
    replay: Mapping[str, object]
    status_namespace: str

    def __post_init__(self) -> None:
        if not isinstance(self.contract_version, str) or not _SEMVER.fullmatch(self.contract_version):
            raise ValueError("unsupported adapter contract version")
        _dotted(self.adapter_id, "adapter_id")
        _nonempty(self.adapter_version, "adapter_version")
        _dotted(self.provider_id, "provider_id")
        if not isinstance(self.core, SkillCoreRef):
            raise TypeError("core must be SkillCoreRef")
        required = _tuple_of_ids(self.required_capabilities, "required_capabilities")
        optional = self.optional_capabilities
        if not isinstance(optional, tuple):
            raise TypeError("optional_capabilities must be tuple")
        optional = tuple(_dotted(item, "optional_capabilities") for item in optional)
        if len(set(optional)) != len(optional) or set(required).intersection(optional):
            raise ValueError("capability requirements must be unique")
        if set(required).union(optional) != set(self.core.capability_ids):
            raise ValueError("adapter capability contract must equal Skill Core")
        extensions = self.native_extensions
        if not isinstance(extensions, tuple):
            raise TypeError("native_extensions must be tuple")
        extensions = tuple(_dotted(item, "native_extensions") for item in extensions)
        if len(set(extensions)) != len(extensions) or any(
            not extension.startswith(f"{self.provider_id}.") for extension in extensions
        ):
            raise ValueError("native extensions must be unique and provider-owned")
        object.__setattr__(self, "required_capabilities", required)
        object.__setattr__(self, "optional_capabilities", optional)
        object.__setattr__(self, "native_extensions", extensions)
        for name in _SEAM_KEYS:
            object.__setattr__(self, name, _seam(name, getattr(self, name)))
        _dotted(self.status_namespace, "status_namespace")
        if not self.status_namespace.startswith(f"{self.provider_id}."):
            raise ValueError("status_namespace must be provider-scoped")


@dataclass(frozen=True)
class SkillAdapterRegistry:
    """A deterministic open-provider registry of package-supplied descriptors."""

    descriptors: tuple[SkillAdapterDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.descriptors, tuple) or not all(
            isinstance(descriptor, SkillAdapterDescriptor) for descriptor in self.descriptors
        ):
            raise TypeError("descriptors must be a tuple of SkillAdapterDescriptor")
        ordered = tuple(sorted(self.descriptors, key=lambda item: (item.provider_id, item.core.skill_id, item.adapter_id)))
        keys = {(item.provider_id, item.core.skill_id) for item in ordered}
        if len(keys) != len(ordered):
            raise ValueError("duplicate provider skill adapter")
        object.__setattr__(self, "descriptors", ordered)

    def select(self, *, provider_id: str, skill_id: str) -> SkillAdapterDescriptor | None:
        _dotted(provider_id, "provider_id")
        if not isinstance(skill_id, str) or not _SKILL_ID.fullmatch(skill_id):
            raise ValueError("invalid skill_id")
        return next((item for item in self.descriptors
                     if item.provider_id == provider_id and item.core.skill_id == skill_id), None)
