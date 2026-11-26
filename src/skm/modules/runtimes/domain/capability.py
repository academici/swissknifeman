"""Runtime capabilities (runtimes §4.3, ``urn:skm:runtimes:capabilities:v1``) and effective merging.

The static declaration of an adapter is data (``capabilities.toml`` + ``error_rules.toml``); this module
parses it without importing any runtime implementation. ``StaticCapabilityCatalog`` is the pure
``CapabilityCatalog`` gateway over such parsed data: immutable, no IO, valid in both gateway tables.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import HostId
from skm.kernel.isolation import IsolationProfile, PluginIsolationProfile, parse_isolation_profile
from skm.kernel.outcomes import Diagnostic, Severity

from .ids import Digest, RuntimeId, is_digest, is_runtime_id

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonValue
    from skm.modules.runtimes.domain.detection import VerificationRecord
    from skm.modules.runtimes.domain.error_rules import ErrorRule

__all__ = [
    "ENFORCING_CAPABILITIES",
    "Capability",
    "CapabilityRecord",
    "CapabilityStatus",
    "ConfigIsolationSpec",
    "CredentialMount",
    "RuntimeCapabilities",
    "SelfLoad",
    "SelfLoadKind",
    "SelfLoadView",
    "SelfLoadedSource",
    "StaticCapabilityCatalog",
    "VerificationContext",
    "config_mode_for",
    "effective_capabilities",
    "explain_self_loads",
    "parse_capabilities",
    "self_loaded_instruction_files",
    "validate_verification_record",
    "verification_context_key",
]

_VERSION_RE: Final = re.compile(r"[0-9]+(?:\.[0-9]+)*")


class Capability(StrEnum):
    HEADLESS_EXECUTION = "headless_execution"
    STRUCTURED_RESULT = "structured_result"
    STREAM_EVENTS = "stream_events"
    SESSION_RESUME = "session_resume"
    TOOL_INTERCEPTION = "tool_interception"
    RELIABLE_CANCELLATION = "reliable_cancellation"
    USAGE_REPORTING = "usage_reporting"
    WORKSPACE_BINDING = "workspace_binding"
    NATIVE_SUBAGENTS = "native_subagents"
    MCP_SUPPORT = "mcp_support"
    PERMISSION_FLAGS = "permission_flags"
    SANDBOX_NATIVE = "sandbox_native"
    EFFORT_CONTROL = "effort_control"
    MODEL_SELECTION = "model_selection"
    CONFIG_ISOLATION = "config_isolation"


ENFORCING_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {
        Capability.CONFIG_ISOLATION,
        Capability.SANDBOX_NATIVE,
        Capability.PERMISSION_FLAGS,
        Capability.WORKSPACE_BINDING,
        Capability.RELIABLE_CANCELLATION,
    }
)


class CapabilityStatus(StrEnum):
    NATIVE = "native"
    ADAPTED = "adapted"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class VerificationContext:
    """Exact installation/launch evidence; secret values are never part of it."""

    host_id: HostId
    binary_sha256: Digest
    os: str
    kernel: str
    adapter_version: str
    isolation_profile: IsolationProfile | PluginIsolationProfile
    launch_config_digest: Digest  # canonical verified launch template, without per-step entropy

    def __post_init__(self) -> None:
        if not isinstance(self.host_id, UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("verification_context.host_id must be a UUID")
        if not is_digest(self.binary_sha256):
            raise ValueError(f"invalid binary_sha256 digest: {self.binary_sha256!r}")
        if not is_digest(self.launch_config_digest):
            raise ValueError(f"invalid launch_config_digest: {self.launch_config_digest!r}")
        for field_name in ("os", "kernel", "adapter_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not (1 <= len(value) <= 100):
                raise ValueError(f"verification_context.{field_name} must be 1..100 characters")
        if not isinstance(self.isolation_profile, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("invalid verification_context.isolation_profile")
        object.__setattr__(self, "isolation_profile", parse_isolation_profile(str(self.isolation_profile)))


def verification_context_key(ctx: VerificationContext) -> Digest:
    """Canonical SHA-256 digest of ``VerificationContext`` (§4.3, §7.2)."""
    payload = {
        "adapter_version": ctx.adapter_version,
        "binary_sha256": ctx.binary_sha256,
        "host_id": str(ctx.host_id),
        "isolation_profile": str(ctx.isolation_profile),
        "kernel": ctx.kernel,
        "launch_config_digest": ctx.launch_config_digest,
        "os": ctx.os,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    capability: Capability
    status: CapabilityStatus
    evidence: str  # "fixture:claude_code/stream_basic.jsonl", "live-eval 2026-11-02", "docs:<url>"
    tested_runtime_version: str | None
    limitations: str
    last_verified_at: date | None
    verification_context: VerificationContext | None = None  # static declarations: None


class SelfLoadKind(StrEnum):
    USER_CONFIG = "user_config"
    PLUGINS = "plugins"
    SKILLS = "skills"
    PROJECT_INSTRUCTIONS = "project_instructions"
    PROJECT_SETTINGS = "project_settings"


@dataclass(frozen=True, slots=True)
class SelfLoad:
    """``[[self_loads]]`` of ``capabilities.toml``: the static (worst-case) declaration."""

    kind: SelfLoadKind
    locator: str
    files: tuple[str, ...]
    when: Literal["start", "on_access"]
    suppressed_by: Literal["config_isolation", "never"]
    note: str


@dataclass(frozen=True, slots=True)
class SelfLoadedSource:
    """What the CLI will actually load by itself (``AgentRuntime.self_loaded_context``, adapters §5.11).

    Goes to ``context.finalize_manifest`` as ``runtime_self_loaded``; never a prompt block, always untrusted.
    """

    kind: SelfLoadKind
    locator: str
    files: tuple[str, ...]
    when: Literal["start", "on_access"]
    trust: Literal["untrusted"] = "untrusted"


@dataclass(frozen=True, slots=True)
class CredentialMount:
    source: str  # an auth file of the client, never settings/plugins/skills/hooks
    target: str  # relative to client_home
    required: bool


@dataclass(frozen=True, slots=True)
class ConfigIsolationSpec:
    env: Mapping[str, str]  # {"CODEX_HOME": "{client_home}"}
    args: tuple[str, ...]
    credential_mounts: tuple[CredentialMount, ...]
    writable_home_dirs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    runtime_id: RuntimeId
    adapter_version: str
    records: Mapping[Capability, CapabilityRecord]
    self_loads: tuple[SelfLoad, ...]
    read_only_network: bool  # network available with an empty fs_write
    config_isolation: ConfigIsolationSpec | None

    def __post_init__(self) -> None:
        if not is_runtime_id(self.runtime_id):
            raise ValueError(f"not a runtime id: {self.runtime_id!r}")
        for capability, record in self.records.items():
            if record.capability != capability:
                raise ValueError(f"record of {record.capability} filed under {capability}")
        object.__setattr__(self, "records", MappingProxyType(dict(self.records)))

    def status(self, cap: Capability) -> CapabilityStatus:
        """A missing record is ``unknown``, never a silent success."""
        record = self.records.get(cap)
        return CapabilityStatus.UNKNOWN if record is None else record.status

    def supports(self, cap: Capability) -> bool:
        return self.status(cap) in (CapabilityStatus.NATIVE, CapabilityStatus.ADAPTED)


def _parse_version(version: str | None) -> tuple[int, ...] | None:
    if version is None or _VERSION_RE.fullmatch(version) is None:
        return None
    parts = [int(part) for part in version.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _append_limitation(limitations: str, note: str) -> str:
    if not note or note in limitations:
        return limitations
    return f"{limitations}; {note}" if limitations else note


def _is_stale(verified_at: date | None, *, now: date, stale_after_days: int) -> bool:
    if verified_at is None:
        return True
    return (now - verified_at).days > stale_after_days


def _merge_enforcing(
    cap: Capability,
    static: RuntimeCapabilities,
    verified: Sequence[CapabilityRecord],
    *,
    host_version: str | None,
    verification_context: VerificationContext | None,
    now: date,
    stale_after_days: int,
) -> CapabilityRecord:
    static_rec = static.records.get(cap)
    exact_candidates: list[tuple[date, int, CapabilityRecord]] = []
    if (
        verification_context is not None
        and verification_context.adapter_version == static.adapter_version
        and host_version is not None
        and _parse_version(host_version) is not None
    ):
        for index, rec in enumerate(verified):
            if (
                rec.capability is cap
                and rec.verification_context == verification_context
                and rec.tested_runtime_version == host_version
            ):
                exact_candidates.append((rec.last_verified_at or date.min, index, rec))

    if exact_candidates:
        _, _, best = max(exact_candidates, key=lambda item: (item[0], item[1]))
        if _is_stale(best.last_verified_at, now=now, stale_after_days=stale_after_days):
            if best.status is CapabilityStatus.UNSUPPORTED:
                return best
            return replace(
                best,
                status=CapabilityStatus.UNKNOWN,
                limitations=_append_limitation(best.limitations, "stale=age"),
            )
        return best

    if static_rec is not None and static_rec.status is CapabilityStatus.UNSUPPORTED:
        return static_rec

    if static_rec is not None:
        return replace(
            static_rec,
            status=CapabilityStatus.UNKNOWN,
            limitations=_append_limitation(static_rec.limitations, "unverified_enforcing"),
            verification_context=None,
        )
    return CapabilityRecord(
        capability=cap,
        status=CapabilityStatus.UNKNOWN,
        evidence="unverified",
        tested_runtime_version=None,
        limitations="unverified_enforcing",
        last_verified_at=None,
        verification_context=None,
    )


def _merge_functional(
    cap: Capability,
    static_rec: CapabilityRecord | None,
    verified: Sequence[CapabilityRecord],
    *,
    host_version: str | None,
    verification_context: VerificationContext | None,
    now: date,
    stale_after_days: int,
    stale_policy: Literal["warn", "refuse"],
) -> CapabilityRecord | None:
    candidates: list[tuple[date, int, CapabilityRecord]] = []
    for index, rec in enumerate(verified):
        if rec.capability is not cap:
            continue
        if (
            verification_context is not None
            and rec.verification_context is not None
            and rec.verification_context != verification_context
        ):
            continue
        candidates.append((rec.last_verified_at or date.min, index, rec))

    chosen = static_rec
    if candidates:
        _, _, newest = max(candidates, key=lambda item: (item[0], item[1]))
        if (
            chosen is None
            or chosen.last_verified_at is None
            or (newest.last_verified_at is not None and newest.last_verified_at >= chosen.last_verified_at)
        ):
            chosen = newest

    if chosen is None:
        return None
    if chosen.status in (CapabilityStatus.UNSUPPORTED, CapabilityStatus.UNKNOWN):
        return chosen

    if host_version is not None:
        parsed_host = _parse_version(host_version)
        parsed_tested = _parse_version(chosen.tested_runtime_version)
        if parsed_host is None or parsed_tested is None:
            return replace(
                chosen,
                status=CapabilityStatus.UNKNOWN,
                limitations=_append_limitation(chosen.limitations, "invalid_version"),
            )
        if parsed_host > parsed_tested:
            return replace(
                chosen,
                status=CapabilityStatus.UNKNOWN,
                limitations=_append_limitation(chosen.limitations, "stale=version"),
            )
    elif chosen.tested_runtime_version is not None and _parse_version(chosen.tested_runtime_version) is None:
        return replace(
            chosen,
            status=CapabilityStatus.UNKNOWN,
            limitations=_append_limitation(chosen.limitations, "invalid_version"),
        )

    if _is_stale(chosen.last_verified_at, now=now, stale_after_days=stale_after_days):
        if stale_policy == "refuse":
            return replace(
                chosen,
                status=CapabilityStatus.UNKNOWN,
                limitations=_append_limitation(chosen.limitations, "stale=age"),
            )
        return replace(chosen, limitations=_append_limitation(chosen.limitations, "stale=age"))

    return chosen


def effective_capabilities(
    static: RuntimeCapabilities,
    verified: Sequence[CapabilityRecord],
    *,
    host_version: str | None = None,
    verification_context: VerificationContext | None = None,
    now: date,
    stale_after_days: int = 30,
    stale_policy: Literal["warn", "refuse"] = "warn",
) -> RuntimeCapabilities:
    """Compute effective capabilities from static claims and recorded verifications (§4.3).

    Enforcing capabilities never become positive without fresh verification matching the exact
    ``verification_context`` and ``host_version``. Functional capabilities prefer newer verifications,
    downgrade to ``unknown`` when ``host_version`` exceeds ``tested_runtime_version`` or fails version
    parsing, and apply ``stale_policy`` past ``stale_after_days``.
    """
    if stale_policy not in ("warn", "refuse"):
        raise ValueError(f"unknown stale_policy {stale_policy!r}")
    if stale_after_days < 1:
        raise ValueError("stale_after_days must be >= 1")

    merged: dict[Capability, CapabilityRecord] = {}
    for cap in Capability:
        if cap in ENFORCING_CAPABILITIES:
            merged[cap] = _merge_enforcing(
                cap,
                static,
                verified,
                host_version=host_version,
                verification_context=verification_context,
                now=now,
                stale_after_days=stale_after_days,
            )
        else:
            record = _merge_functional(
                cap,
                static.records.get(cap),
                verified,
                host_version=host_version,
                verification_context=verification_context,
                now=now,
                stale_after_days=stale_after_days,
                stale_policy=stale_policy,
            )
            if record is not None:
                merged[cap] = record

    return RuntimeCapabilities(
        runtime_id=static.runtime_id,
        adapter_version=static.adapter_version,
        records=merged,
        self_loads=static.self_loads,
        read_only_network=static.read_only_network,
        config_isolation=static.config_isolation,
    )


@dataclass(frozen=True, slots=True)
class SelfLoadView:
    kind: SelfLoadKind
    locator: str
    when: str
    active: bool
    reason: str


def _self_load_view(load: SelfLoad, *, isolated: bool, isolates: bool) -> SelfLoadView:
    # A runtime that cannot (or did not prove it can) isolate still loads what it declares suppressible.
    if load.suppressed_by == "never":
        active, reason = True, "cannot_suppress"  # e.g. Codex reads AGENTS.md upwards even with CODEX_HOME
    elif load.kind is SelfLoadKind.PROJECT_SETTINGS:  # §4.3.1 rule 7: suppressed in both modes
        active, reason = (False, "untrusted_suppressed") if isolates else (True, "not_isolated")
    elif isolated:
        active, reason = (False, "isolated") if isolates else (True, "not_isolated")
    else:
        active, reason = True, "inherited"
    return SelfLoadView(kind=load.kind, locator=load.locator, when=load.when, active=active, reason=reason)


def explain_self_loads(
    caps: RuntimeCapabilities, config_mode: Literal["isolated", "inherit"]
) -> tuple[SelfLoadView, ...]:
    """What the CLI loads by itself under ``config_mode`` (§4.3.1 rule 5), in declaration order.

    ``caps`` are effective capabilities: suppression by ``config_isolation`` counts only when the runtime
    supports it; otherwise the loads stay active (``not_isolated``), the worst case. Project settings of the
    worktree are suppressed in both modes; the ``trusted-full-access`` exception is not an input here, so the
    view never claims them active because of it.
    """
    if config_mode not in ("isolated", "inherit"):
        raise ValueError(f"unknown config mode {config_mode!r}")
    isolated = config_mode == "isolated"
    isolates = caps.supports(Capability.CONFIG_ISOLATION)
    return tuple(_self_load_view(load, isolated=isolated, isolates=isolates) for load in caps.self_loads)


def self_loaded_instruction_files(
    views: Sequence[SelfLoadView], caps: RuntimeCapabilities
) -> tuple[str, ...]:
    """Instruction filenames actively self-loaded by the runtime at start (§4.3.1 rule 4/5)."""
    active_locators = {
        (view.locator, view.when)
        for view in views
        if view.active and view.kind is SelfLoadKind.PROJECT_INSTRUCTIONS and view.when == "start"
    }
    found: list[str] = []
    seen: set[str] = set()
    for load in caps.self_loads:
        if (
            load.kind is SelfLoadKind.PROJECT_INSTRUCTIONS
            and load.when == "start"
            and (load.locator, load.when) in active_locators
        ):
            for filename in load.files:
                if filename not in seen:
                    seen.add(filename)
                    found.append(filename)
    return tuple(found)


def config_mode_for(
    profile_inherit: bool, *, scope_inherit: bool
) -> tuple[Literal["isolated", "inherit"], tuple[Diagnostic, ...]]:
    """Resolve ``config_mode`` from profile and scope ``context.inherit_user_global`` (§4.3.1 rule 1)."""
    if profile_inherit and scope_inherit:
        return "inherit", ()
    if profile_inherit and not scope_inherit:
        return (
            "isolated",
            (
                Diagnostic(
                    code="INHERIT_USER_GLOBAL_NARROWED",
                    message=(
                        "profile requested context.inherit_user_global, narrowed to isolated by scope config"
                    ),
                    severity=Severity.WARNING,
                    target="context.inherit_user_global",
                ),
            ),
        )
    return "isolated", ()


def _invalid(message: str) -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, message, details={"reason": "capabilities_invalid"})


def _items(value: JsonValue, name: str) -> list[Mapping[str, JsonValue]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise _invalid(f"{name} must be a list of objects")
    return cast("list[Mapping[str, JsonValue]]", value)


def _strings(value: JsonValue, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _invalid(f"{name} must be a list of strings")
    return tuple(cast("list[str]", value))


def _context(value: JsonValue) -> VerificationContext | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _invalid("verification_context must be an object or null")
    return VerificationContext(
        host_id=HostId(UUID(cast("str", value["host_id"]))),
        binary_sha256=cast("str", value["binary_sha256"]),
        os=cast("str", value["os"]),
        kernel=cast("str", value["kernel"]),
        adapter_version=cast("str", value["adapter_version"]),
        isolation_profile=parse_isolation_profile(cast("str", value["isolation_profile"])),
        launch_config_digest=cast("str", value["launch_config_digest"]),
    )


def _record(item: Mapping[str, JsonValue]) -> CapabilityRecord:
    verified = item["last_verified_at"]
    return CapabilityRecord(
        capability=Capability(cast("str", item["capability"])),
        status=CapabilityStatus(cast("str", item["status"])),
        evidence=cast("str", item["evidence"]),
        tested_runtime_version=cast("str | None", item["tested_runtime_version"]),
        limitations=cast("str", item["limitations"]),
        last_verified_at=None if verified is None else date.fromisoformat(cast("str", verified)),
        verification_context=_context(item.get("verification_context")),
    )


def _isolation(value: JsonValue) -> ConfigIsolationSpec | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _invalid("config_isolation must be an object or null")
    env = value["env"]
    if not isinstance(env, Mapping) or not all(isinstance(item, str) for item in env.values()):
        raise _invalid("config_isolation.env must map names to strings")
    return ConfigIsolationSpec(
        env=MappingProxyType(dict(cast("Mapping[str, str]", env))),
        args=_strings(value["args"], "config_isolation.args"),
        credential_mounts=tuple(
            CredentialMount(
                source=cast("str", mount["source"]),
                target=cast("str", mount["target"]),
                required=cast("bool", mount["required"]),
            )
            for mount in _items(value["credential_mounts"], "config_isolation.credential_mounts")
        ),
        writable_home_dirs=_strings(value["writable_home_dirs"], "config_isolation.writable_home_dirs"),
    )


def parse_capabilities(document: Mapping[str, JsonValue]) -> RuntimeCapabilities:
    """A schema-valid ``capabilities.v1`` document (one adapter); a capability listed twice is refused."""
    records: dict[Capability, CapabilityRecord] = {}
    for item in _items(document["records"], "records"):
        record = _record(item)
        if record.capability in records:
            raise _invalid(f"capability {record.capability} is declared twice")
        records[record.capability] = record
    read_only_network = document["read_only_network"]
    if not isinstance(read_only_network, bool):
        raise _invalid("read_only_network must be a boolean")
    return RuntimeCapabilities(
        runtime_id=cast("str", document["runtime_id"]),
        adapter_version=cast("str", document["adapter_version"]),
        records=records,
        self_loads=tuple(
            SelfLoad(
                kind=SelfLoadKind(cast("str", item["kind"])),
                locator=cast("str", item["locator"]),
                files=_strings(item["files"], "self_loads.files"),
                when=cast("Literal['start', 'on_access']", item["when"]),
                suppressed_by=cast("Literal['config_isolation', 'never']", item["suppressed_by"]),
                note=cast("str", item["note"]),
            )
            for item in _items(document["self_loads"], "self_loads")
        ),
        read_only_network=read_only_network,
        config_isolation=_isolation(document["config_isolation"]),
    )


@dataclass(frozen=True, slots=True)
class StaticCapabilityCatalog:
    """``CapabilityCatalog`` over parsed static declarations of built-in adapters and allowed plugins.

    Built from data only: no adapter class is imported or constructed. Unknown runtime -> ``NOT_FOUND``.
    """

    declarations: Mapping[RuntimeId, RuntimeCapabilities]
    rules: Mapping[RuntimeId, tuple[ErrorRule, ...]]  # error_rules.toml next to capabilities.toml

    def __post_init__(self) -> None:
        for runtime_id, caps in self.declarations.items():
            if caps.runtime_id != runtime_id:
                raise ValueError(f"capabilities of {caps.runtime_id} filed under {runtime_id}")
        for runtime_id, rules in self.rules.items():
            if runtime_id not in self.declarations:
                raise ValueError(f"error rules of unregistered runtime {runtime_id}")
            if any(rule.runtime_id != runtime_id for rule in rules):
                raise ValueError(f"error rules filed under {runtime_id} name another runtime")
        object.__setattr__(self, "declarations", MappingProxyType(dict(self.declarations)))
        object.__setattr__(
            self, "rules", MappingProxyType({key: tuple(value) for key, value in self.rules.items()})
        )

    def static(self, runtime_id: RuntimeId) -> RuntimeCapabilities:
        caps = self.declarations.get(runtime_id)
        if caps is None:
            raise NotFound(
                ErrorCode.NOT_FOUND, f"runtime {runtime_id!r} is not registered", details={"kind": "runtime"}
            )
        return caps

    def error_rules(self, runtime_id: RuntimeId) -> tuple[ErrorRule, ...]:
        self.static(runtime_id)
        return self.rules.get(runtime_id, ())

    def registered(self) -> frozenset[RuntimeId]:
        return frozenset(self.declarations)


def validate_verification_record(record: VerificationRecord) -> None:
    """Column rules of a stored capability verification, as both stores enforce them."""
    if not is_runtime_id(record.runtime_id):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"invalid runtime_id {record.runtime_id!r}",
            details={"constraint": "ck_capability_verifications__runtime_id"},
        )
    if record.runtime_version is not None and not (1 <= len(record.runtime_version) <= 100):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "runtime_version must be 1..100 characters",
            details={"field": "runtime_version"},
        )
    cap_rec = record.record
    Capability(cap_rec.capability)
    CapabilityStatus(cap_rec.status)
    if not (1 <= len(cap_rec.evidence) <= 500):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "evidence must be 1..500 characters",
            details={"constraint": "ck_capability_verifications__evidence"},
        )
    if len(cap_rec.limitations) > 2000:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "limitations must be at most 2000 characters",
            details={"constraint": "ck_capability_verifications__limitations"},
        )
    if cap_rec.last_verified_at is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "verified_at is required for capability verifications",
            details={"field": "verified_at"},
        )
    ctx = record.verification_context
    key = record.verification_key
    if (ctx is None) != (key is None):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "verification_context and verification_key must both be null or both be set",
            details={"constraint": "ck_capability_verifications__context"},
        )
    if ctx is not None and key is not None and (not is_digest(key) or key != verification_context_key(ctx)):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "verification_key does not match canonical verification_context",
            details={"constraint": "ck_capability_verifications__context"},
        )
