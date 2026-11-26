"""Material availability and freshness assessment (planning §5.11)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final, cast
from uuid import UUID

from skm.kernel.ids import EntityId
from skm.modules.planning.domain.material import (
    FreshnessPolicy,
    Material,
    MaterialKind,
    MaterialRef,
    MaterialStage,
    must_refresh_expired,
)
from skm.modules.planning.domain.reads import parse_timestamp
from skm.modules.planning.domain.validation.context import FileVersionObservation, FileVersionStatus

if TYPE_CHECKING:
    pass

__all__ = [
    "MaterialAssessment",
    "MaterialObservation",
    "MaterialState",
    "assess_material",
]


@dataclass(frozen=True, slots=True)
class MaterialObservation:
    file_version: FileVersionObservation | None
    checkout_has_path: bool | None


class MaterialState(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    NOT_READY = "not_ready"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MaterialAssessment:
    material_id: EntityId
    state: MaterialState
    age_seconds: int | None
    reason: str
    blocks: frozenset[MaterialStage]


_BLOCKING_STATES: Final = frozenset(
    {
        MaterialState.MISSING,
        MaterialState.NOT_READY,
        MaterialState.STALE,
    }
)


def _extract_fields(
    material: Material | MaterialRef,
) -> tuple[EntityId, MaterialKind, FreshnessPolicy, int | None, frozenset[MaterialStage], datetime | None]:
    if isinstance(material, Material):
        return (
            material.id,
            material.kind,
            material.freshness.policy,
            material.freshness.max_age_seconds,
            frozenset(material.required_for),
            material.retrieved_at,
        )

    # A document entry carries ``id``; a revision material ref carries ``material_id``.
    raw_id = material.get("id") or material.get("material_id")
    if raw_id is None:
        raise ValueError("material id is required")
    material_id = EntityId(UUID(str(raw_id)))
    kind = MaterialKind(str(material["kind"]))

    raw_freshness = material.get("freshness")
    if isinstance(raw_freshness, Mapping):
        policy = FreshnessPolicy(str(raw_freshness.get("policy", "pinned")))
        raw_max = raw_freshness.get("max_age_seconds")
        max_age_seconds = None if raw_max is None else int(cast("int", raw_max))
    else:
        policy = FreshnessPolicy.PINNED
        max_age_seconds = None

    raw_required_for = material.get("required_for")
    required_for = (
        frozenset(MaterialStage(str(stage)) for stage in raw_required_for)
        if isinstance(raw_required_for, list)
        else frozenset[MaterialStage]()
    )

    raw_retrieved = material.get("retrieved_at")
    retrieved_at = parse_timestamp(raw_retrieved) if isinstance(raw_retrieved, str) else None
    return material_id, kind, policy, max_age_seconds, required_for, retrieved_at


def _assess_freshness(
    policy: FreshnessPolicy,
    max_age_seconds: int | None,
    timestamp: datetime | None,
    now: datetime,
) -> tuple[MaterialState, int | None, str]:
    elapsed_seconds = None if timestamp is None else (now - timestamp).total_seconds()
    age_seconds = None if elapsed_seconds is None else int(elapsed_seconds)
    if policy is FreshnessPolicy.PINNED:
        return MaterialState.AVAILABLE, age_seconds, "material is pinned"
    if policy is FreshnessPolicy.LATEST_AT_PUBLISH:
        return MaterialState.AVAILABLE, age_seconds, "material is latest_at_publish"
    if not must_refresh_expired(max_age_seconds, timestamp, now):
        return MaterialState.AVAILABLE, age_seconds, "material is fresh"
    if elapsed_seconds is None or age_seconds is None:
        return MaterialState.STALE, None, "material age is unknown; must be refreshed"
    if max_age_seconds is None:
        return (
            MaterialState.STALE,
            age_seconds,
            f"material age {age_seconds}s exceeds max age {max_age_seconds}s",
        )
    stale_age = max(int(elapsed_seconds), max_age_seconds + 1)
    return (
        MaterialState.STALE,
        stale_age,
        f"material age {stale_age}s exceeds max age {max_age_seconds}s",
    )


def assess_material(
    material: Material | MaterialRef,
    observation: MaterialObservation | None,
    *,
    now: datetime,
) -> MaterialAssessment:
    """Assess availability and freshness of a single material (planning §5.11)."""
    material_id, kind, policy, max_age_seconds, required_for, retrieved_at = _extract_fields(material)

    if kind is MaterialKind.REPOSITORY_PATH:
        has_path = None if observation is None else observation.checkout_has_path
        if has_path is False:
            state = MaterialState.MISSING
            age_seconds = None
            reason = "repository path not found in checkout"
        elif has_path is None:
            state = MaterialState.UNKNOWN
            age_seconds = None
            reason = "checkout path not observed; planning does not inspect checkout filesystem"
        else:
            state = MaterialState.AVAILABLE
            age_seconds = None
            reason = "repository path present in checkout"
    elif kind is MaterialKind.FILE_VERSION:
        fv = None if observation is None else observation.file_version
        if fv is None:
            state = MaterialState.MISSING
            age_seconds = None
            reason = "file version missing"
        elif fv.status in (FileVersionStatus.MISSING, FileVersionStatus.OTHER_WORKSPACE):
            state = MaterialState.MISSING
            age_seconds = None
            reason = f"file version {fv.status.value}"
        elif fv.status is FileVersionStatus.NOT_READY:
            state = MaterialState.NOT_READY
            age_seconds = None
            reason = "file version is not ready"
        else:
            state, age_seconds, reason = _assess_freshness(policy, max_age_seconds, fv.created_at, now)
    else:
        state, age_seconds, reason = _assess_freshness(policy, max_age_seconds, retrieved_at, now)

    blocks: frozenset[MaterialStage] = required_for if state in _BLOCKING_STATES else frozenset()
    return MaterialAssessment(
        material_id=material_id,
        state=state,
        age_seconds=age_seconds,
        reason=reason,
        blocks=blocks,
    )
