"""Effective work intensity of a task (execution §4.2.1; contract ``urn:skm:execution:work-policy:v1``).

Pure resolution: settings (with their own locks and provenance) → item override → unit override. The
intensity changes instructions and the depth of investigation; it never selects a model or route effort,
never removes required checks, review, independence, security or authority, and never becomes a timeout.
Soft time warnings come from the pinned ``role_warn_seconds``/``repro_warn_seconds`` matrices; crossing
one is an observation, not a refusal, a pause or an admission ceiling. ``emergency_role_seconds`` are
derived separately from the existing hard ceilings (profile timeout, role wall, step wall) and do not
depend on the intensity. The digest covers requested/effective intensities, warning thresholds and the
emergency ceilings; provenance and elapsed time are excluded, so a clock never changes it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.frozen_json import thaw_json

if TYPE_CHECKING:
    from collections.abc import Iterable

    from skm.kernel.json_types import JsonValue

__all__ = [
    "DEFAULT_POLICY_KEY",
    "DEFAULT_REPRO_WARN_SECONDS",
    "DEFAULT_ROLE_WARN_SECONDS",
    "ROLE_NAMES",
    "EffectiveWorkPolicy",
    "HardCeilings",
    "Intensity",
    "RoleIntensities",
    "SettingSource",
    "WorkPolicyOverride",
    "WorkPolicySettings",
    "WorkWarning",
    "derive_group_policy",
    "policy_digest",
    "remaining_emergency_seconds",
    "resolve_work_policy",
    "soft_warnings",
    "synthetic_work_policy",
    "work_policy_from_json",
    "work_policy_to_json",
]

ROLE_NAMES: Final = ("scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar")
DEFAULT_POLICY_KEY: Final = "@default"
_ROLE_KEY: Final = "execution.work_policy.role_intensity"
_VERIFICATION_KEY: Final = "execution.work_policy.verification_intensity"
_WARN_MAX: Final = 172800
_REPRO_MAX: Final = 3600


class Intensity(StrEnum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


_ORDER: Final = {Intensity.LIGHT: 0, Intensity.MEDIUM: 1, Intensity.HEAVY: 2}

DEFAULT_ROLE_WARN_SECONDS: Final[Mapping[str, Mapping[Intensity, int]]] = MappingProxyType(
    {
        role: MappingProxyType(dict(zip(Intensity, seconds, strict=True)))
        for role, seconds in {
            "executor": (900, 1800, 3600),
            "reviewer": (180, 300, 600),
            "triager": (90, 180, 300),
            "scout": (300, 600, 900),
            "advisor": (180, 300, 600),
            "researcher": (300, 900, 1800),
            "registrar": (30, 60, 90),
        }.items()
    }
)
DEFAULT_REPRO_WARN_SECONDS: Final[Mapping[Intensity, int]] = MappingProxyType(
    {Intensity.LIGHT: 30, Intensity.MEDIUM: 60, Intensity.HEAVY: 90}
)


@dataclass(frozen=True, slots=True)
class RoleIntensities:
    scout: Intensity
    executor: Intensity
    reviewer: Intensity
    triager: Intensity
    advisor: Intensity
    researcher: Intensity
    registrar: Intensity


@dataclass(frozen=True, slots=True)
class SettingSource:
    """Where a settings value came from: ``default`` or ``settings`` and the provenance ref."""

    source: str
    ref: str


@dataclass(frozen=True, slots=True)
class WorkPolicySettings:
    """The resolved ``execution.work_policy.*`` values of the run's settings chain.

    ``sources`` and ``locks`` are keyed by field path: ``role_intensity`` (all roles),
    ``role_intensity.<role>`` or ``verification_intensity``. A locked field ignores item/unit overrides;
    the lock value names the locking level for the clamp note.
    """

    role_intensity: Mapping[str, Intensity]
    verification_intensity: Intensity
    role_warn_seconds: Mapping[str, Mapping[Intensity, int]] = DEFAULT_ROLE_WARN_SECONDS
    repro_warn_seconds: Mapping[Intensity, int] = DEFAULT_REPRO_WARN_SECONDS
    sources: Mapping[str, SettingSource] = field(default_factory=dict[str, SettingSource])
    locks: Mapping[str, str] = field(default_factory=dict[str, str])

    def __post_init__(self) -> None:
        if set(self.role_intensity) != set(ROLE_NAMES):
            _config("execution.work_policy.role_intensity", "every role has an intensity")
        for role in ROLE_NAMES:
            _monotonic(
                self.role_warn_seconds.get(role), f"execution.work_policy.role_warn_seconds.{role}", _WARN_MAX
            )
        if set(self.role_warn_seconds) != set(ROLE_NAMES):
            _config(
                "execution.work_policy.role_warn_seconds", "warning thresholds name exactly the seven roles"
            )
        _monotonic(self.repro_warn_seconds, "execution.work_policy.repro_warn_seconds", _REPRO_MAX)

    @classmethod
    def defaults(cls) -> WorkPolicySettings:
        return cls(dict.fromkeys(ROLE_NAMES, Intensity.MEDIUM), Intensity.MEDIUM)


@dataclass(frozen=True, slots=True)
class WorkPolicyOverride:
    """Partial ``work_policy`` of an item or unit (planning §4.2.1); absent fields inherit."""

    role_intensity: Mapping[str, Intensity] = field(default_factory=dict[str, Intensity])
    verification_intensity: Intensity | None = None

    def __post_init__(self) -> None:
        unknown = set(self.role_intensity) - set(ROLE_NAMES)
        if unknown:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                f"unknown roles {sorted(unknown)}",
                details={"field": "role_intensity"},
            )

    @classmethod
    def from_json(cls, document: JsonValue) -> WorkPolicyOverride | None:
        """The planning document (``urn:skm:planning:specification:v1#/$defs/work_policy``) or ``None``."""
        if document is None:
            return None
        if not isinstance(document, dict) or set(document) - {"role_intensity", "verification_intensity"}:
            raise error_for(
                ErrorCode.SCHEMA_INVALID, "work_policy is a closed object", details={"field": "work_policy"}
            )
        roles = document.get("role_intensity") or {}
        verification = document.get("verification_intensity")
        if not isinstance(roles, dict):
            raise error_for(
                ErrorCode.SCHEMA_INVALID, "role_intensity is an object", details={"field": "role_intensity"}
            )
        return cls(
            {role: Intensity(str(value)) for role, value in roles.items()},
            None if verification is None else Intensity(str(verification)),
        )


@dataclass(frozen=True, slots=True)
class HardCeilings:
    """Existing frozen hard ceilings per role invocation, in seconds; ``None``/``0`` is no ceiling.

    ``profile_timeout_seconds`` — pinned AgentProfile.limits.timeout_seconds per role;
    ``role_wall_seconds`` — ``execution.timeouts.role_wall_seconds``; ``step_wall_seconds`` —
    ``execution.timeouts.step_wall_seconds``.
    """

    profile_timeout_seconds: Mapping[str, int | None] = field(default_factory=dict[str, int | None])
    role_wall_seconds: Mapping[str, int | None] = field(default_factory=dict[str, int | None])
    step_wall_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class EffectiveWorkPolicy:
    """A frozen policy: every nested value is a read-only copy, so its content always matches ``digest``."""

    requested: Mapping[str, JsonValue]
    effective: Mapping[str, JsonValue]
    role_warn_seconds: Mapping[str, int]
    triage_repro_warn_seconds: int
    emergency_role_seconds: Mapping[str, int | None]
    provenance: tuple[Mapping[str, JsonValue], ...]
    clamps: tuple[str, ...]
    digest: str

    def __post_init__(self) -> None:
        for name in ("requested", "effective", "role_warn_seconds", "emergency_role_seconds"):
            object.__setattr__(self, name, _freeze(getattr(self, name)))
        object.__setattr__(self, "provenance", tuple(_freeze(entry) for entry in self.provenance))
        object.__setattr__(self, "clamps", tuple(self.clamps))


@dataclass(frozen=True, slots=True)
class WorkWarning:
    """A soft overrun: report and analyse it; the work goes on."""

    role: str
    kind: str  # "role" or "reproduction"
    expected_seconds: int
    actual_seconds: int


def resolve_work_policy(
    settings: WorkPolicySettings,
    *,
    item: WorkPolicyOverride | None = None,
    unit: WorkPolicyOverride | None = None,
    ceilings: HardCeilings | None = None,
    item_ref: str = "item",
    unit_ref: str = "unit",
) -> EffectiveWorkPolicy:
    """settings → item → unit for each field; locked fields keep the settings value (with a clamp note)."""
    layers = (("item", item_ref, item), ("unit", unit_ref, unit))
    requested_roles: dict[str, Intensity] = {}
    effective_roles: dict[str, Intensity] = {}
    role_sources: dict[str, tuple[str, str]] = {}
    clamps: list[str] = []
    for role in ROLE_NAMES:
        path = f"role_intensity.{role}"
        base = Intensity(settings.role_intensity[role])
        value, source = base, _setting_source(settings, path, "role_intensity", _ROLE_KEY)
        for name, ref, layer in layers:
            if layer is not None and role in layer.role_intensity:
                value, source = Intensity(layer.role_intensity[role]), (name, ref)
        requested_roles[role] = value
        lock = _lock(settings, path, "role_intensity")
        if lock is not None and value is not base:
            clamps.append(f"locked:{path}:{lock}")
            value, source = base, _setting_source(settings, path, "role_intensity", _ROLE_KEY)
        effective_roles[role] = value
        role_sources[role] = source
    base_verification = Intensity(settings.verification_intensity)
    verification = base_verification
    verification_source = _setting_source(settings, "verification_intensity", None, _VERIFICATION_KEY)
    for name, ref, layer in layers:
        if layer is not None and layer.verification_intensity is not None:
            verification, verification_source = Intensity(layer.verification_intensity), (name, ref)
    requested_verification = verification
    lock = _lock(settings, "verification_intensity", None)
    if lock is not None and verification is not base_verification:
        clamps.append(f"locked:verification_intensity:{lock}")
        verification = base_verification
        verification_source = _setting_source(settings, "verification_intensity", None, _VERIFICATION_KEY)
    provenance: list[JsonObject] = [
        *_role_provenance(role_sources),
        {"field": "verification_intensity", "source": verification_source[0], "ref": verification_source[1]},
    ]
    return _build(
        requested=_intensities(requested_roles, requested_verification),
        effective=_intensities(effective_roles, verification),
        warn=_warn(settings, effective_roles),
        emergency=_emergency(ceilings or HardCeilings()),
        provenance=sorted(provenance, key=lambda entry: (str(entry["field"]), str(entry["ref"]))),
        clamps=clamps,
    )


def derive_group_policy(
    members: Mapping[str, EffectiveWorkPolicy], settings: WorkPolicySettings
) -> EffectiveWorkPolicy:
    """Policy of a group review: per role max intensity, verification = max, warnings of that level.

    Requested and effective maps aggregate separately; ``members`` is keyed by stable task id or display
    key, which prefixes their provenance refs. Emergency ceilings are the minimum positive member
    ceilings, independent of the aggregated intensity (``None`` when no member has one).
    """
    if not members:
        _invalid("members", "a group policy needs at least one member")
    ordered = sorted(members.items())
    policies = [policy for _, policy in ordered]
    requested = _max_intensities(policy.requested for policy in policies)
    effective = _max_intensities(policy.effective for policy in policies)
    effective_roles = {role: Intensity(str(_roles(effective)[role])) for role in ROLE_NAMES}
    emergency: dict[str, int | None] = {}
    for role in ROLE_NAMES:
        found = [policy.emergency_role_seconds.get(role) for policy in policies]
        positive = [value for value in found if value is not None and value > 0]
        emergency[role] = min(positive) if positive else None
    provenance = [
        {**entry, "ref": f"{key}:{entry['ref']}"} for key, policy in ordered for entry in policy.provenance
    ]
    return _build(
        requested=requested,
        effective=effective,
        warn=_warn(settings, effective_roles),
        emergency=emergency,
        provenance=sorted(
            provenance, key=lambda entry: (str(entry["ref"]).split(":", 1)[0], str(entry["field"]))
        ),
        clamps=[clamp for policy in policies for clamp in policy.clamps],
    )


_SOURCE_REQUIRED: Final = frozenset({"integration", "followup"})


def synthetic_work_policy(
    kind: str, *, source_key: str | None, policies: Mapping[str, EffectiveWorkPolicy]
) -> EffectiveWorkPolicy:
    """The immutable policy of a synthetic task from the run's frozen ``work_policies``.

    Integration and followup tasks inherit their source task; a missing source or one that is not a
    task of this run is refused (never replaced by ``@default``). Other synthetic tasks without a
    source use ``@default``. Group reviews use ``derive_group_policy``.
    """
    if kind in _SOURCE_REQUIRED:
        if source_key is None or source_key == DEFAULT_POLICY_KEY or source_key not in policies:
            raise error_for(
                ErrorCode.INVALID_REFERENCE,
                f"a {kind} task inherits the policy of its source task of this run",
                details={"kind": kind, "source": source_key},
            )
        return policies[source_key]
    if DEFAULT_POLICY_KEY not in policies:
        _invalid("work_policies", "the frozen policies include @default")
    return policies[DEFAULT_POLICY_KEY]


def soft_warnings(
    policy: EffectiveWorkPolicy, role: str, *, elapsed_seconds: int, repro_seconds: int | None = None
) -> tuple[WorkWarning, ...]:
    """Overruns of the soft thresholds; never an error and never a limit."""
    found: list[WorkWarning] = []
    expected = policy.role_warn_seconds[role]
    if elapsed_seconds > expected:
        found.append(WorkWarning(role, "role", expected, elapsed_seconds))
    if role == "triager" and repro_seconds is not None and repro_seconds > policy.triage_repro_warn_seconds:
        found.append(WorkWarning(role, "reproduction", policy.triage_repro_warn_seconds, repro_seconds))
    return tuple(found)


def remaining_emergency_seconds(
    policy: EffectiveWorkPolicy,
    role: str,
    *,
    started_at: datetime,
    now: datetime,
    extra_ceilings: Sequence[int | None] = (),
) -> int | None:
    """Seconds left before the emergency ceiling of this invocation (``None``: no hard ceiling).

    The minimum of the positive frozen role ceiling and explicit task/run hard ceilings, minus the time
    already spent; the frozen policy and its digest do not change with the clock.
    """
    ceilings = [policy.emergency_role_seconds.get(role), *extra_ceilings]
    positive = [value for value in ceilings if value is not None and value > 0]
    if not positive:
        return None
    spent = int((now - started_at).total_seconds())
    return max(0, min(positive) - spent)


def policy_digest(policy: EffectiveWorkPolicy) -> str:
    return _digest(
        policy.requested,
        policy.effective,
        dict(policy.role_warn_seconds),
        policy.triage_repro_warn_seconds,
        dict(policy.emergency_role_seconds),
    )


def work_policy_to_json(policy: EffectiveWorkPolicy) -> JsonObject:
    """The document of ``urn:skm:execution:work-policy:v1``; a detached copy that never reaches the policy."""
    return {
        "requested": thaw_json(policy.requested),
        "effective": thaw_json(policy.effective),
        "role_warn_seconds": thaw_json(policy.role_warn_seconds),
        "triage_repro_warn_seconds": policy.triage_repro_warn_seconds,
        "provenance": [thaw_json(entry) for entry in policy.provenance],
        "clamps": list(policy.clamps),
        "digest": policy.digest,
        "emergency_role_seconds": thaw_json(policy.emergency_role_seconds),
    }


def work_policy_from_json(document: JsonObject) -> EffectiveWorkPolicy:
    """Read a frozen policy; a digest that does not match its content is ``SCHEMA_INVALID``."""
    try:
        warn = document["role_warn_seconds"]
        emergency = document["emergency_role_seconds"]
        provenance = document["provenance"]
        clamps = document["clamps"]
        if not isinstance(warn, dict) or not isinstance(emergency, dict):
            raise TypeError("role maps are objects")
        if not isinstance(provenance, list) or not isinstance(clamps, list):
            raise TypeError("provenance and clamps are arrays")
        policy = EffectiveWorkPolicy(
            requested=_object(document["requested"]),
            effective=_object(document["effective"]),
            role_warn_seconds=MappingProxyType({str(k): int(str(v)) for k, v in warn.items()}),
            triage_repro_warn_seconds=int(str(document["triage_repro_warn_seconds"])),
            emergency_role_seconds=MappingProxyType(
                {str(k): None if v is None else int(str(v)) for k, v in emergency.items()}
            ),
            provenance=tuple(_object(entry) for entry in provenance),
            clamps=tuple(str(clamp) for clamp in clamps),
            digest=str(document["digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, f"invalid work policy: {exc}") from exc
    if policy_digest(policy) != policy.digest:
        _invalid("digest", "the digest does not match the work policy")
    return policy


# ---------------------------------------------------------------- helpers


def _build(
    *,
    requested: JsonObject,
    effective: JsonObject,
    warn: tuple[dict[str, int], int],
    emergency: Mapping[str, int | None],
    provenance: Sequence[JsonObject],
    clamps: Iterable[str],
) -> EffectiveWorkPolicy:
    role_warn, repro = warn
    emergency_map = {role: emergency.get(role) for role in ROLE_NAMES}
    return EffectiveWorkPolicy(
        requested=requested,
        effective=effective,
        role_warn_seconds=MappingProxyType(role_warn),
        triage_repro_warn_seconds=repro,
        emergency_role_seconds=MappingProxyType(emergency_map),
        provenance=tuple(provenance),
        clamps=tuple(sorted(set(clamps))),
        digest=_digest(requested, effective, role_warn, repro, emergency_map),
    )


def _digest(
    requested: Mapping[str, JsonValue],
    effective: Mapping[str, JsonValue],
    role_warn: Mapping[str, int],
    repro: int,
    emergency: Mapping[str, int | None],
) -> str:
    document = {
        "requested": thaw_json(requested),
        "effective": thaw_json(effective),
        "role_warn_seconds": thaw_json(role_warn),
        "triage_repro_warn_seconds": repro,
        "emergency_role_seconds": thaw_json(emergency),
    }
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _intensities(roles: Mapping[str, Intensity], verification: Intensity) -> JsonObject:
    return {
        "role_intensity": {role: roles[role].value for role in ROLE_NAMES},
        "verification_intensity": verification.value,
    }


def _roles(document: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    roles = document.get("role_intensity")
    if not isinstance(roles, Mapping):
        _invalid("role_intensity", "role_intensity is an object")
    return cast("Mapping[str, JsonValue]", roles)


def _max_intensities(documents: Iterable[Mapping[str, JsonValue]]) -> JsonObject:
    roles: dict[str, Intensity] = {}
    verification: Intensity | None = None
    for document in documents:
        for role, value in _roles(document).items():
            level = Intensity(str(value))
            if role not in roles or _ORDER[level] > _ORDER[roles[role]]:
                roles[role] = level
        level = Intensity(str(document.get("verification_intensity")))
        if verification is None or _ORDER[level] > _ORDER[verification]:
            verification = level
    assert verification is not None  # noqa: S101 - at least one member
    return _intensities(roles, verification)


def _warn(settings: WorkPolicySettings, effective: Mapping[str, Intensity]) -> tuple[dict[str, int], int]:
    role_warn = {role: settings.role_warn_seconds[role][effective[role]] for role in ROLE_NAMES}
    return role_warn, settings.repro_warn_seconds[effective["triager"]]


def _emergency(ceilings: HardCeilings) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for role in ROLE_NAMES:
        found = (
            ceilings.profile_timeout_seconds.get(role),
            ceilings.role_wall_seconds.get(role),
            ceilings.step_wall_seconds,
        )
        positive = [value for value in found if value is not None and value > 0]
        result[role] = min(positive) if positive else None
    return result


def _setting_source(settings: WorkPolicySettings, path: str, parent: str | None, key: str) -> tuple[str, str]:
    for name in (path, parent):
        if name is not None and name in settings.sources:
            found = settings.sources[name]
            return found.source, found.ref
    return "default", key


def _lock(settings: WorkPolicySettings, path: str, parent: str | None) -> str | None:
    for name in (path, parent):
        if name is not None and name in settings.locks:
            return settings.locks[name]
    return None


def _role_provenance(sources: Mapping[str, tuple[str, str]]) -> list[JsonObject]:
    distinct = set(sources.values())
    if len(distinct) == 1:
        source, ref = distinct.pop()
        if source in {"default", "settings"}:
            return [{"field": "role_intensity", "source": source, "ref": ref}]
    return [
        {"field": f"role_intensity.{role}", "source": sources[role][0], "ref": sources[role][1]}
        for role in ROLE_NAMES
    ]


def _monotonic(values: Mapping[Intensity, int] | None, key: str, maximum: int) -> None:
    if values is None or set(values) != set(Intensity):
        _config(key, "thresholds name light, medium and heavy")
    light, medium, heavy = (values[level] for level in Intensity)
    if not 1 <= light <= medium <= heavy <= maximum:
        _config(key, f"thresholds are positive, at most {maximum} and light <= medium <= heavy")


def _object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError("expected an object")
    return value


def _freeze(value: object) -> Any:
    """A deep read-only copy: objects become read-only mappings and arrays tuples at every level."""
    if isinstance(value, Mapping):
        items = cast("Mapping[object, object]", value)
        return MappingProxyType({key: _freeze(item) for key, item in items.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in cast("Sequence[object]", value))
    return value


def _config(key: str, message: str) -> NoReturn:
    raise error_for(
        ErrorCode.CONFIG_INVALID, message, details={"key": key, "validator": "work_policy_bounds"}
    )


def _invalid(field_name: str, message: str) -> NoReturn:
    raise error_for(ErrorCode.SCHEMA_INVALID, message, details={"field": field_name})
