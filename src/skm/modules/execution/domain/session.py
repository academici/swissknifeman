"""Resume or fresh session of a role step (execution §5.16, decision table SE0-SE10).

``decide_session`` is the only place that decides a resume (RT-01). A session id alone is never enough:
the admission allowance only filters, then the first matching row of the table decides, and every row that
could carry a session across a change of authority, environment, route, scope or after contamination answers
``Fresh``. When admission *requires* a resume, a ``Fresh`` result is impossible: the step is refused
(``ADMISSION_REFUSED``, ``details.reason = resume_required_unavailable``) before it is created.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.step import RoleId, StepState
from skm.modules.execution.domain.workflow.stage_inputs import StageMode

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, ProjectId
    from skm.modules.execution.domain.ids import EnvironmentId, OutputId
    from skm.modules.execution.domain.step import AttemptStep
    from skm.modules.runtimes.public import ResumeAllowance

__all__ = [
    "SESSION_FRESH_REASONS",
    "Fresh",
    "Resume",
    "RouteRef",
    "SessionFacts",
    "SessionFingerprint",
    "decide_session",
    "session_lost",
]

# ``fresh_reason`` values of ``attempt_steps`` (CHECK ck_attempt_steps__fresh_reason in SQL 0014)
SESSION_FRESH_REASONS: Final = frozenset(
    {
        "ADMISSION_NO_RESUME",
        "NO_PREVIOUS_SESSION",
        "AUTHORITY_CHANGED",
        "OPERATOR_LIVE_CONTROL",
        "ENVIRONMENT_CHANGED",
        "ROUTE_CHANGED",
        "RESUME_UNSUPPORTED",
        "SCOPE_CHANGED",
        "SESSION_CONTAMINATED",
        "CONTEXT_BLOATED",
        "NOT_A_CONTINUATION",
        "SESSION_LOST",
    }
)
_RESULT_INVALID: Final = "RESULT_INVALID"
_CONTINUING_MODES: Final = frozenset(
    {
        StageMode.REWORK,
        StageMode.FINAL_CORRECTION,
        StageMode.CONTINUE_WITH_ANSWER,
        StageMode.RETRY,
        StageMode.RESUME_INTERRUPTED,
    }
)


@dataclass(frozen=True, slots=True)
class RouteRef:
    runtime_id: str
    model: str
    effort: str | None


@dataclass(frozen=True, slots=True)
class SessionFingerprint:
    runtime_id: str
    project_id: ProjectId
    environment_id: EnvironmentId
    role: RoleId
    attempt_id: AttemptId
    instruction_digest: str
    authority_digest: str
    route: RouteRef
    last_validated_output_id: OutputId | None


def decide_session(  # noqa: PLR0911
    nxt: SessionFingerprint, facts: SessionFacts, *, force_fresh: bool = False
) -> Resume | Fresh:
    """The first matching row of SE0-SE10; ``nxt`` is the fingerprint the new step would have."""
    prev = facts.previous
    allowance = facts.admission_allows_resume
    required = allowance.required
    if force_fresh:
        return _fresh("OPERATOR_LIVE_CONTROL", prev is not None, required)
    if not allowance.allowed:
        return _fresh("ADMISSION_NO_RESUME", prev is not None, required)
    if prev is None or prev.session_ref is None:
        return _fresh("NO_PREVIOUS_SESSION", False, required)
    before = prev.session_fingerprint
    if before.authority_digest != nxt.authority_digest:
        return _fresh("AUTHORITY_CHANGED", True, required)
    if (before.environment_id, before.project_id, before.attempt_id, before.role) != (
        nxt.environment_id,
        nxt.project_id,
        nxt.attempt_id,
        nxt.role,
    ):
        return _fresh("ENVIRONMENT_CHANGED", True, required)
    if before.runtime_id != nxt.runtime_id or before.route != nxt.route:
        return _fresh("ROUTE_CHANGED", True, required)
    if not facts.runtime_supports_resume:
        return _fresh("RESUME_UNSUPPORTED", True, required)
    if before.instruction_digest != nxt.instruction_digest:
        return _fresh("SCOPE_CHANGED", True, required)
    error = facts.previous_error_code if facts.previous_error_code is not None else prev.error_code
    form_only = prev.state is StepState.FAILED and error == _RESULT_INVALID
    if (prev.state is StepState.FAILED and not form_only) or prev.state is StepState.CANCELLED:
        return _fresh("SESSION_CONTAMINATED", True, required)
    tokens = facts.previous_context_tokens
    if tokens is not None and tokens > facts.max_resume_context_tokens:
        return _fresh("CONTEXT_BLOATED", True, required)
    if facts.stage_mode is StageMode.RETRY and facts.retry_of_previous_stage and form_only:
        return Resume(prev.session_ref)
    if facts.stage_mode in _CONTINUING_MODES and _continues_output(before, nxt, facts):
        return Resume(prev.session_ref)
    return _fresh("NOT_A_CONTINUATION", True, required)


def session_lost(nxt: SessionFingerprint, previous: AttemptStep) -> Fresh:
    """The runtime answered ``session_lost`` to a resume: a fresh start with a handoff in the same step.

    Only while the authority did not change (a changed authority never resumed in the first place).
    """
    if previous.session_fingerprint.authority_digest != nxt.authority_digest:
        return Fresh("AUTHORITY_CHANGED", True)
    return Fresh("SESSION_LOST", True)


def _continues_output(before: SessionFingerprint, nxt: SessionFingerprint, facts: SessionFacts) -> bool:
    """SE9: the previous step last validated the attempt's current output or one that precedes it.

    No validated output on the previous step is no relationship at all: two absent ids never match.
    """
    validated = before.last_validated_output_id
    if validated is None:
        return False
    return validated == nxt.last_validated_output_id or validated in facts.earlier_output_ids


def _fresh(reason: str, handoff: bool, required: bool) -> Fresh:
    if required:
        raise error_for(
            ErrorCode.ADMISSION_REFUSED,
            "admission requires a resume that the session rules do not allow",
            details={"reason": "resume_required_unavailable", "fresh_reason": reason},
        )
    return Fresh(reason, handoff)


@dataclass(frozen=True, slots=True)
class SessionFacts:
    previous: AttemptStep | None
    runtime_supports_resume: bool
    previous_context_tokens: int | None
    max_resume_context_tokens: int
    stage_mode: StageMode
    admission_allows_resume: ResumeAllowance
    retry_of_previous_stage: bool
    previous_error_code: str | None
    # outputs of the attempt that precede its current one (SE9: the previous step validated an earlier one)
    earlier_output_ids: frozenset[OutputId] = frozenset()


@dataclass(frozen=True, slots=True)
class Resume:
    session_ref: str


@dataclass(frozen=True, slots=True)
class Fresh:
    reason: str
    handoff: bool
