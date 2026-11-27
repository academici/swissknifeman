"""Immutable host observations and pure settings helpers for integrations §5.6."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.contracts import ClientLayer
from skm.modules.integrations.domain.hook_events import HookEventKind
from skm.modules.integrations.domain.hook_subscriptions import HookSubscription, Violation
from skm.modules.integrations.domain.reports import CheckResult
from skm.modules.integrations.domain.target import TargetId

__all__ = [
    "DoctorContext",
    "HygieneObservation",
    "ScriptObservation",
    "effective_settings",
    "finding",
    "mapping",
    "strings",
]


def mapping(value: object) -> JsonObject:
    """A JSON object, or an empty object for an absent/malformed native section."""
    return cast("JsonObject", value) if isinstance(value, Mapping) else {}


def strings(value: object) -> tuple[str, ...]:
    return (
        tuple(v for v in cast("Iterable[object]", value) if isinstance(v, str))
        if isinstance(value, list | tuple)
        else ()
    )


def _merge(base: JsonObject, overlay: JsonObject) -> JsonObject:
    out = dict(base)
    for key, value in overlay.items():
        out[key] = _merge(mapping(out[key]), value) if key in out and isinstance(value, dict) else value
    return out


def effective_settings(layers: Iterable[ClientLayer]) -> JsonObject:
    """Resolve user → project → local → managed; editor settings are a separate client."""
    indexed = {str(layer.get("layer")): layer for layer in layers}
    result: JsonObject = {}
    for name in ("user", "project", "local", "managed", "cli", "ide_permissions"):
        layer = indexed.get(name, {})
        if layer.get("valid") is True:
            result = _merge(result, mapping(layer.get("data")))
    return result


@dataclass(frozen=True, slots=True)
class ScriptObservation:
    path: str
    executable: bool
    checkout_file: bool
    subscription_id: str | None
    trusted: bool


@dataclass(frozen=True, slots=True)
class HygieneObservation:
    files: Mapping[str, str] = field(default_factory=dict[str, str])
    skills: tuple[str, ...] = ()
    scripts: tuple[ScriptObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class DoctorContext:
    target: TargetId
    layers: tuple[ClientLayer, ...] = ()
    expected: Mapping[str, JsonValue] = field(default_factory=dict[str, JsonValue])
    directories: Mapping[str, bool | None] = field(default_factory=dict[str, bool | None])
    commands: frozenset[str] = frozenset()
    known_hook_events: frozenset[str] = frozenset()
    drift_paths: tuple[str, ...] = ()
    marker_files: Mapping[str, bytes] = field(default_factory=dict[str, bytes])
    subscriptions: tuple[HookSubscription, ...] = ()
    subscription_facts: tuple[JsonObject, ...] = ()
    subscription_violations: tuple[Violation, ...] = ()
    hookable_types: frozenset[str] = frozenset()
    sink_ids: frozenset[str] = frozenset()
    trusted: Mapping[str, str] = field(default_factory=dict[str, str])
    supported_kinds: frozenset[HookEventKind] = frozenset()
    enforcement_enabled: bool = False
    checkout_marker: str | None = None  # present | missing | mismatch; None: not observed
    hygiene: HygieneObservation = field(default_factory=HygieneObservation)

    @property
    def effective(self) -> JsonObject:
        return effective_settings(self.layers)


def finding(
    ctx: DoctorContext,
    check_id: str,
    level: str,
    title: str,
    problems: Iterable[tuple[str | None, str]],
    hint: str | None = None,
) -> tuple[CheckResult, ...]:
    """Emit one fact per affected path, or one explicit successful check."""
    bad = tuple(problems)
    return tuple(
        CheckResult(check_id, ctx.target, level, title, detail, path, hint) for path, detail in bad
    ) or (CheckResult(check_id, ctx.target, "ok", title, "No findings", None, None),)
