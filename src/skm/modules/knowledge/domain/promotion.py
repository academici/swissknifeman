"""P00 declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from skm.kernel.ids import ScopeId, WorkspaceId

from .evidence import EvidenceRef
from .lesson import ConfidenceTier, LessonId, LessonKind


@dataclass(frozen=True, slots=True)
class CandidateForPromotion:
    candidate_id: UUID
    workspace_id: WorkspaceId
    scope_id: ScopeId
    kind: LessonKind
    trigger: str
    action: str
    evidence: tuple[EvidenceRef, ...]
    confidence: float
    tier: ConfidenceTier


@dataclass(frozen=True, slots=True)
class LessonRef:
    lesson_id: LessonId
