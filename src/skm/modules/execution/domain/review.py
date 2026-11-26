"""Reviews, their output freshness and the review profile (execution §4.13, §5.4 A5, §5.9).

A review is evidence about exactly one output. ``freshness_of`` says what it proves for another output:
``fresh`` for its own output; ``findings_only`` for a later output of the same attempt when the reviewed
output is known to be an earlier output of that attempt and the later changes stay within the locations
of the confirmed findings (H7, decided by the caller); otherwise ``stale``. A review
of another task or attempt never clears an output. ``stale`` is a computed answer only: a stored review
row keeps ``fresh`` or ``findings_only``.

``choose_review_profile`` takes the revision profile, else ``review_profile`` of the policy (default
``reviewer``); a ``security`` risk feature or a task path matching the security patterns switches to the
``security`` profile while ``security_review_on_risk`` holds. The work intensity is not an input: it
never removes a required review, its independence or the security profile.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.risk import matching, patterns_of

if TYPE_CHECKING:
    from datetime import datetime
    from typing import Literal

    from skm.kernel.ids import AttemptId, ResourceVersionId, RunId, TaskId, WorkspaceId
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.contracts import ExecutionPolicy
    from skm.modules.execution.domain.ids import OutputId, ReviewId
    from skm.modules.execution.domain.output import Output
    from skm.modules.execution.domain.risk import RiskScore
    from skm.modules.execution.domain.task import Task

__all__ = [
    "DEFAULT_PROFILE",
    "SECURITY_PROFILE",
    "Freshness",
    "Review",
    "ReviewClearance",
    "ReviewState",
    "ReviewerKind",
    "Verdict",
    "choose_review_profile",
    "freshness_of",
]

DEFAULT_PROFILE: Final = "reviewer"
SECURITY_PROFILE: Final = "security"


class ReviewState(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class Verdict(StrEnum):
    GREEN = "green"
    ATTENTION = "attention"
    RED = "red"


class Freshness(StrEnum):
    FRESH = "fresh"
    FINDINGS_ONLY = "findings_only"
    STALE = "stale"  # computed only; never stored on a review row


class ReviewerKind(StrEnum):
    AGENT = "agent"
    HUMAN = "human"


@dataclass(frozen=True, slots=True)
class Review:
    id: ReviewId
    workspace_id: WorkspaceId
    run_id: RunId
    task_id: TaskId
    attempt_id: AttemptId
    output_id: OutputId
    round_no: int
    reviewer_kind: ReviewerKind
    reviewer_ref: JsonObject
    profile_key: str
    profile_version_id: ResourceVersionId
    audit_scope: Literal["corrected", "full", "range"]
    state: ReviewState
    verdict: Verdict | None
    freshness: Freshness
    base_output_id: OutputId | None
    residual_risk: str
    completed_at: datetime | None

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.round_no < 1:
            problems.append("round_no >= 1")
        if (self.round_no == 1) != (self.base_output_id is None):
            problems.append("base_output_id is set exactly for round > 1")
        if (self.verdict is not None) != (self.state is ReviewState.COMPLETED):
            problems.append("a verdict exists exactly for a completed review")
        if (self.completed_at is not None) != (self.state is not ReviewState.STARTED):
            problems.append("completed_at is set exactly for a finished review")
        if self.freshness is Freshness.STALE:
            problems.append("a stored review is fresh or findings_only")
        if self.audit_scope not in {"corrected", "full", "range"}:
            problems.append("audit_scope is corrected, full or range")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "review invariants violated: " + "; ".join(problems),
                details={"review_id": str(self.id), "violations": list(problems)},
            )


def freshness_of(
    review: Review, output: Output, *, reviewed: Output | None = None, corrected_only: bool = False
) -> Freshness:
    """What ``review`` proves for ``output``.

    ``reviewed`` is the output the review audited; ``findings_only`` needs it to be a real earlier output
    of the same task and attempt (A5). ``corrected_only`` is the H7 fact that ``output`` changed only the
    locations of the confirmed findings of that output (plus tests and docs of the write scope). Without
    both a later output is stale: an unknown reviewed output never passes.
    """
    if review.task_id != output.task_id or review.attempt_id != output.attempt_id:
        return Freshness.STALE
    if review.run_id != output.run_id:
        return Freshness.STALE
    if review.output_id == output.id:
        return Freshness.FRESH
    earlier = (
        reviewed is not None
        and reviewed.id == review.output_id
        and reviewed.task_id == output.task_id
        and reviewed.attempt_id == output.attempt_id
        and reviewed.run_id == output.run_id
        and reviewed.seq < output.seq
    )
    return Freshness.FINDINGS_ONLY if earlier and corrected_only else Freshness.STALE


def choose_review_profile(
    task: Task,
    policy: ExecutionPolicy,
    risk: RiskScore | None = None,
    paths: Sequence[str] = (),
) -> str:
    profile = task.review_profile or _text(policy.get("review_profile"), DEFAULT_PROFILE)
    if policy.get("security_review_on_risk", True) is False:
        return profile
    security_risk = risk is not None and risk.has("security")
    scope = [pattern.pattern for pattern in task.declared_write_scope or ()]
    security_paths = matching([*paths, *scope], patterns_of(policy.get("risk_patterns"), "security"))
    return SECURITY_PROFILE if security_risk or security_paths else profile


class ReviewClearance(StrEnum):
    GREEN = "green"
    FINDINGS_ONLY = "findings_only"
    CLEARED_BY_TRIAGE = "cleared_by_triage"
    DEVIATION = "deviation"
    SELF = "self"
    WAIVED = "waived"
    REPORT = "report"


def _text(value: JsonValue | None, default: str) -> str:
    return value if isinstance(value, str) and value else default
