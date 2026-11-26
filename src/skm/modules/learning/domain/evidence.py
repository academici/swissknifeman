"""P00 declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from skm.kernel.json_types import JsonObject


@dataclass(frozen=True, slots=True)
class ExposedLessonRef:
    id: UUID
    version: str
    content_digest: str


@dataclass(frozen=True, slots=True)
class DetectorEvidence:
    detector_version: str
    input_schema_version: str
    relevant_metrics: JsonObject
    thresholds: JsonObject
    source_refs: tuple[JsonObject, ...]
    coverage: JsonObject
    decision: str
    severity: str | None
    population: JsonObject
    exclusions: JsonObject
    alternative_explanations: tuple[str, ...]
    suggested_investigation: str
