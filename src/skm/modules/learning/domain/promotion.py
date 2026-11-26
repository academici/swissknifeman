"""Human permission and state prerequisites for lesson promotion."""

from typing import Literal

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed

from .candidate import CANDIDATE_TRANSITIONS, Candidate, CandidateState


def require_human(actor: Actor) -> None:
    if actor.kind is not PrincipalKind.HUMAN:
        raise Forbidden(
            ErrorCode.FORBIDDEN, "A human principal is required", details={"reason": "human_gate"}
        )


def validate_promotion(
    candidate: Candidate,
    actor: Actor,
    *,
    override_low_confidence: bool = False,
    override_reason: str | None = None,
    resolve_conflict: Literal["supersede", "keep_both"] | None = None,
) -> None:
    require_human(actor)
    reason: str | None = None
    if CandidateState.PROMOTED not in CANDIDATE_TRANSITIONS[candidate.state]:
        reason = "candidate_state"
    elif candidate.state is CandidateState.OBSERVED and not override_low_confidence:
        reason = "override_required"
    elif override_low_confidence and (override_reason is None or len(override_reason.strip()) < 10):
        reason = "override_reason_required"
    elif candidate.conflicts_with_id is not None and resolve_conflict not in ("supersede", "keep_both"):
        reason = "conflict_unresolved"
    if reason is not None:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "Candidate cannot be promoted",
            details={"from": candidate.state.value, "to": CandidateState.PROMOTED.value, "reason": reason},
        )
