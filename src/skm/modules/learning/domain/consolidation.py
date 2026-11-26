"""Consolidate exact wording and rank similar rules for human review."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict

from .activity import DEFAULT_SETTINGS, ConsolidationSettings, digest
from .candidate import Candidate, CandidateId, CandidateState
from .detectors import Observation
from .tokens import jaccard, norm


class ConsolidationAction(StrEnum):
    ADD = "add"
    UPDATE = "update"
    NOOP = "noop"
    CONFLICT = "conflict"


def rule_identity(rule: Observation | Candidate) -> tuple[str, str, str]:
    return rule.kind, norm(rule.trigger), norm(rule.action)


def fingerprint(kind: str, trigger: str, action: str) -> str:
    return digest([kind, norm(trigger), norm(action)])


@dataclass(frozen=True, slots=True)
class ShortlistMatch:
    candidate: Candidate
    tsim: float
    asim: float


def shortlist(
    obs: Observation,
    existing: Iterable[Candidate],
    *,
    threshold: float = 0.4,
) -> tuple[ShortlistMatch, ...]:
    matches = [
        ShortlistMatch(
            candidate, jaccard(obs.trigger, candidate.trigger), jaccard(obs.action, candidate.action)
        )
        for candidate in existing
        if jaccard(f"{obs.trigger} {obs.action}", f"{candidate.trigger} {candidate.action}") >= threshold
    ]
    return tuple(sorted(matches, key=lambda match: (-match.tsim, -match.asim, match.candidate.fingerprint)))


@dataclass(frozen=True, slots=True)
class ConsolidationDecision:
    action: ConsolidationAction
    target_id: CandidateId | None
    reason: str
    state: CandidateState = CandidateState.OBSERVED

    @property
    def conflicts_with_id(self) -> CandidateId | None:
        if self.action in (ConsolidationAction.UPDATE, ConsolidationAction.CONFLICT):
            return self.target_id
        return None


def classify_consolidation(
    obs: Observation,
    matches: tuple[ShortlistMatch, ...],
    *,
    exact: Candidate | None = None,
    settings: ConsolidationSettings = DEFAULT_SETTINGS.consolidation,
) -> ConsolidationDecision:
    """Pass the scope's fingerprint lookup separately from the bounded shortlist."""
    identity = rule_identity(obs)
    hashed = fingerprint(*identity)
    if exact is None:
        exact = next((match.candidate for match in matches if match.candidate.fingerprint == hashed), None)
    if exact is not None:
        if rule_identity(exact) != identity:
            raise Conflict(
                ErrorCode.ID_CONFLICT, "Candidate fingerprint collision", details={"fingerprint": hashed}
            )
        state = CandidateState.OBSERVED if exact.state is CandidateState.DEPRECATED else exact.state
        return ConsolidationDecision(ConsolidationAction.NOOP, exact.id, "exact_wording", state)

    target = next((match for match in matches if match.tsim >= settings.trigger_high), None)
    if target is None:
        return ConsolidationDecision(ConsolidationAction.ADD, None, "no_similar_trigger")
    if target.asim < settings.action_low:
        return ConsolidationDecision(ConsolidationAction.CONFLICT, target.candidate.id, "dissimilar_action")
    return ConsolidationDecision(ConsolidationAction.UPDATE, target.candidate.id, "similar_trigger")
