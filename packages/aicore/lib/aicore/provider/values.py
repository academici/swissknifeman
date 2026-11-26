"""Immutable provider-domain values shared by package adapters.

This module deliberately contains no carrier parsing, registry, rendering, or I/O.
Those operations remain owned by the phases and packages that supply their inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Protocol


_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")
_SOURCE_KINDS = frozenset({"operation", "project", "fleet-project", "fleet-defaults", "legacy"})
_SOURCE_CARRIERS = frozenset({"operation", ".swissknife.json", ".swissknifeman/config.toml", "config.json",
                              "legacy"})


class ProviderId(str, Enum):
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    CURSOR = "cursor"
    GROK = "grok"
    ANTIGRAVITY = "antigravity"


class SupportLevel(str, Enum):
    NATIVE = "native"
    ADAPTED = "adapted"
    UNSUPPORTED = "unsupported"


class SupportSource(str, Enum):
    """How a support fact was obtained (capability-support/v1)."""

    DECLARED = "declared"
    PROBED = "probed"
    INFERRED = "inferred"


class AvailabilityDimension(str, Enum):
    """Kind of a support fact: a missing feature, an exhausted resource, a policy ban or a failing dependency."""

    FEATURE = "feature"
    RESOURCE = "resource"
    POLICY = "policy"
    HEALTH = "health"


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, order=True)
class CapabilityId:
    value: str

    def __post_init__(self) -> None:
        _require_identifier(self.value, "capability ID")


@dataclass(frozen=True, order=True)
class NativeExtensionId:
    value: str

    def __post_init__(self) -> None:
        _require_identifier(self.value, "native extension ID")
        provider_prefix = self.value.split(".", 1)[0]
        if provider_prefix not in {provider.value for provider in ProviderId} or "." not in self.value:
            raise ValueError("native extension ID must use a supported provider namespace")


@dataclass(frozen=True, order=True)
class CapabilityRequirement:
    capability_id: CapabilityId
    accepted_levels: tuple[SupportLevel, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.capability_id, CapabilityId):
            raise TypeError("capability_id must be CapabilityId")
        _require_tuple(self.accepted_levels, "accepted_levels")
        if not self.accepted_levels or not all(isinstance(level, SupportLevel) for level in self.accepted_levels):
            raise ValueError("accepted_levels must be a non-empty tuple of SupportLevel")
        if len(set(self.accepted_levels)) != len(self.accepted_levels):
            raise ValueError("accepted_levels must not contain duplicates")
        object.__setattr__(self, "accepted_levels", tuple(sorted(self.accepted_levels, key=str)))


@dataclass(frozen=True, order=True)
class ProviderDecision:
    identifier: CapabilityId | NativeExtensionId
    enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, (CapabilityId, NativeExtensionId)):
            raise TypeError("identifier must be CapabilityId or NativeExtensionId")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be bool")


@dataclass(frozen=True)
class ProviderSelection:
    provider_id: ProviderId
    enabled: bool | None
    capabilities: tuple[ProviderDecision, ...] = ()
    native_extensions: tuple[ProviderDecision, ...] = ()

    def __post_init__(self) -> None:
        _validate_provider_selection(self.provider_id, self.enabled, self.capabilities,
                                     self.native_extensions)
        object.__setattr__(self, "capabilities", _ordered_decisions(self.capabilities, CapabilityId))
        object.__setattr__(self, "native_extensions",
                           _ordered_decisions(self.native_extensions, NativeExtensionId))


@dataclass(frozen=True)
class EffectiveProvider:
    provider_id: ProviderId
    enabled: bool
    capabilities: tuple[ProviderDecision, ...] = ()
    native_extensions: tuple[ProviderDecision, ...] = ()

    def __post_init__(self) -> None:
        _validate_provider_selection(self.provider_id, self.enabled, self.capabilities,
                                     self.native_extensions, allow_missing_enabled=False)
        object.__setattr__(self, "capabilities", _ordered_decisions(self.capabilities, CapabilityId))
        object.__setattr__(self, "native_extensions",
                           _ordered_decisions(self.native_extensions, NativeExtensionId))


@dataclass(frozen=True, order=True)
class ConfigSource:
    kind: str
    id: str
    carrier: str
    path: str

    def __post_init__(self) -> None:
        if self.kind not in _SOURCE_KINDS:
            raise ValueError("unknown config source kind")
        if self.carrier not in _SOURCE_CARRIERS:
            raise ValueError("unknown config source carrier")
        for name, value in (("id", self.id), ("path", self.path)):
            if not isinstance(value, str) or not value:
                raise ValueError(f"config source {name} must be non-empty")
        if not self.path.startswith("/"):
            raise ValueError("config source path must be an RFC6901 pointer")


@dataclass(frozen=True, order=True)
class ConfigProvenance:
    effective_path: str
    source: ConfigSource
    source_path: str
    explicit: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source, ConfigSource):
            raise TypeError("source must be ConfigSource")
        for name, value in (("effective_path", self.effective_path), ("source_path", self.source_path)):
            if not isinstance(value, str) or not value.startswith("/"):
                raise ValueError(f"{name} must be an RFC6901 pointer")
        if not isinstance(self.explicit, bool):
            raise TypeError("explicit must be bool")


@dataclass(frozen=True, order=True)
class ProviderDiagnostic:
    severity: DiagnosticSeverity
    code: str
    path: str
    source: ConfigSource
    message: str = ""
    context: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.severity, DiagnosticSeverity):
            raise TypeError("severity must be DiagnosticSeverity")
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("code must be non-empty")
        if not isinstance(self.path, str) or not self.path.startswith("/"):
            raise ValueError("path must be an RFC6901 pointer")
        if not isinstance(self.source, ConfigSource):
            raise TypeError("source must be ConfigSource")
        if not isinstance(self.message, str):
            raise TypeError("message must be str")
        _require_tuple(self.context, "context")
        if not all(isinstance(pair, tuple) and len(pair) == 2 and
                   all(isinstance(part, str) for part in pair) for pair in self.context):
            raise ValueError("context must be a tuple of string pairs")
        if len({key for key, _ in self.context}) != len(self.context):
            raise ValueError("context keys must not repeat")
        object.__setattr__(self, "context", tuple(sorted(self.context)))


class ProviderAdapter(Protocol):
    @property
    def adapter_id(self) -> str: ...

    @property
    def provider_id(self) -> ProviderId: ...

    @property
    def capability_requirements(self) -> tuple[CapabilityRequirement, ...]: ...


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"invalid {label}")


def _require_tuple(value: object, label: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{label} must be tuple")


def _ordered_decisions(decisions: tuple[ProviderDecision, ...], identifier_type: type) -> tuple[ProviderDecision, ...]:
    _require_tuple(decisions, "decisions")
    if not all(isinstance(decision, ProviderDecision) and
               isinstance(decision.identifier, identifier_type) for decision in decisions):
        raise TypeError("decisions contain an invalid identifier type")
    ordered = tuple(sorted(decisions, key=lambda decision: decision.identifier.value))
    if len({decision.identifier for decision in ordered}) != len(ordered):
        raise ValueError("decisions must not contain duplicate identifiers")
    return ordered


def _validate_provider_selection(provider_id: ProviderId, enabled: bool | None,
                                 capabilities: tuple[ProviderDecision, ...],
                                 native_extensions: tuple[ProviderDecision, ...],
                                 allow_missing_enabled: bool = True) -> None:
    if not isinstance(provider_id, ProviderId):
        raise TypeError("provider_id must be ProviderId")
    if not isinstance(enabled, bool) and (enabled is not None or not allow_missing_enabled):
        raise TypeError("enabled must be bool" + (" or None" if allow_missing_enabled else ""))
    _ordered_decisions(capabilities, CapabilityId)
    _ordered_decisions(native_extensions, NativeExtensionId)
