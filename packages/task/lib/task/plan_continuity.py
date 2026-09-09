"""Provider-neutral continuation decision for executable plan handoffs."""
from __future__ import annotations

from dataclasses import asdict, dataclass


OUTCOMES = ("continue-root", "isolated-child-return", "cold-start-root", "waiting-owner")
HARD_BOUNDARIES = frozenset(("design-boundary", "audit-boundary", "context-insufficient"))


class ContinuityError(ValueError):
    pass


@dataclass(frozen=True)
class ContinuityDecision:
    outcome: str
    reason: str
    evidence: tuple[str, ...]
    runnable: bool

    def as_dict(self):
        return asdict(self)


def evaluate(*, route_attested: bool, context_attested: bool | None,
             batch_receipt_valid: bool, waiting_owner: bool = False,
             isolated_review: bool = False, boundary: str | None = None,
             checkpoint: str | None = None) -> ContinuityDecision:
    """Choose only from durable evidence; ordinary work remains in the root."""
    if waiting_owner:
        return ContinuityDecision("waiting-owner", "owner-wait", (), False)
    if isolated_review:
        return ContinuityDecision("isolated-child-return", "independent-review", (), True)
    if boundary is not None:
        if boundary not in HARD_BOUNDARIES or not checkpoint:
            raise ContinuityError("CONTINUITY_EVIDENCE_MISSING")
        return ContinuityDecision("cold-start-root", boundary, (checkpoint,), True)
    if not route_attested or not batch_receipt_valid:
        raise ContinuityError("CONTINUITY_EVIDENCE_MISSING")
    # Missing telemetry is explicitly not a cold-start signal.
    return ContinuityDecision("continue-root", "compatible-active-work" if context_attested else
                              "context-telemetry-unavailable", (), True)
