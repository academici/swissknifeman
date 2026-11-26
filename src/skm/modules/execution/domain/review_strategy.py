"""Whether and how a task output is reviewed (execution §4.2.1, §5.1 D2/D3, §5.9).

``decide_review`` keeps the plan's decision and only adds to it: ``required`` stays required, a ``self``
task gets a dynamic review when ``review_strategy = risk_scored`` and the risk passes the threshold (or a
critical feature is present), the security profile follows a security risk while
``security_review_on_risk`` holds, and ``waived`` (a human decision) is never overridden. The verification
intensity is reported as ``investigation`` and changes nothing else: never the requirement, its
independence, the required checks or the security profile.

``rereview_scope`` keeps a re-review of corrected findings on those findings: ``corrected`` unless the
correction proved a widening (a change outside the findings' locations and the allowed extra paths).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.finding import OPEN_FINDING_STATES, SEVERITY_RANK, FindingState, Severity
from skm.modules.execution.domain.review import SECURITY_PROFILE, choose_review_profile
from skm.modules.execution.domain.risk import DEFAULT_THRESHOLD, matching, review_triggered
from skm.modules.execution.domain.task import ReviewMode

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.contracts import ExecutionPolicy
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.domain.risk import RiskScore
    from skm.modules.execution.domain.task import Task

__all__ = [
    "DEFAULT_FOLLOWUPS_MAX",
    "INTENSITIES",
    "ReviewDecision",
    "decide_review",
    "followup_findings",
    "rereview_scope",
]

DEFAULT_FOLLOWUPS_MAX: Final = 3
INTENSITIES: Final = ("light", "medium", "heavy")
_INDEPENDENCE: Final = frozenset({"separate_session", "separate_runtime", "human"})


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    required: bool
    profile: str | None
    independence: str
    dynamic: bool
    investigation: str
    reason: str
    diagnostics: tuple[str, ...]


def decide_review(
    task: Task,
    policy: ExecutionPolicy,
    *,
    risk: RiskScore | None,
    review_req: Mapping[str, JsonValue] | None = None,
    paths: Sequence[str] = (),
    verification_intensity: str = "medium",
) -> ReviewDecision:
    """The review of ``task``'s output after the first executor round.

    ``policy`` keys: ``review_strategy`` (``risk_scored``), ``risk_threshold`` (60),
    ``security_review_on_risk`` (true), ``review_profile`` and ``risk_patterns``. ``review_req`` is the
    revision requirement (``independence``).
    """
    investigation = verification_intensity if verification_intensity in INTENSITIES else "medium"
    requirement = review_req or {}
    stated = requirement.get("independence")
    independence = stated if isinstance(stated, str) and stated in _INDEPENDENCE else "separate_session"
    if task.review_mode is ReviewMode.WAIVED:
        return ReviewDecision(False, None, independence, False, investigation, "waived by a human", ())
    profile = choose_review_profile(task, policy, risk, paths)
    if task.review_mode is ReviewMode.REQUIRED:
        return ReviewDecision(True, profile, independence, False, investigation, "required by the plan", ())
    threshold = policy.get("risk_threshold", DEFAULT_THRESHOLD)
    limit = threshold if isinstance(threshold, int) and not isinstance(threshold, bool) else DEFAULT_THRESHOLD
    risky = (
        policy.get("review_strategy", "risk_scored") == "risk_scored"
        and risk is not None
        and review_triggered(risk, limit)
    )
    security = profile == SECURITY_PROFILE
    if risky or security:
        reason = f"risk score {risk.score}" if risky and risk is not None else "security risk"
        return ReviewDecision(
            True, profile, independence, True, investigation, reason, ("DYNAMIC_REVIEW_ADDED",)
        )
    return ReviewDecision(False, None, independence, False, investigation, "self-check is enough", ())


def rereview_scope(
    round_no: int,
    *,
    configured: Literal["corrected", "full"],
    is_range: bool,
    changed_paths: Sequence[str],
    finding_paths: Sequence[str],
    allowed: Sequence[str] = (),
) -> tuple[Literal["corrected", "full", "range"], tuple[str, ...]]:
    """Audit scope of a review round and the paths it covers.

    Round 1 and ``full`` audit the whole diff (no path list); ``range`` is a gate or review request. A
    later ``corrected`` round covers the changed paths and every confirmed finding location; it becomes
    ``full`` only when a changed path is outside those locations and outside ``allowed`` globs.
    """
    if is_range:
        return "range", ()
    if round_no <= 1 or configured == "full":
        return "full", ()
    locations = set(finding_paths)
    widened = [path for path in changed_paths if path not in locations and not matching([path], allowed)]
    if widened:
        return "full", ()
    return "corrected", tuple(sorted(locations | set(changed_paths)))


def followup_findings(findings: Sequence[Finding], policy: JsonObject) -> tuple[Finding, ...]:
    """H1g: confirmed ``blocker``/``major`` findings of a gate review, at most ``followups_max`` (3)."""
    value = policy.get("followups_max", DEFAULT_FOLLOWUPS_MAX)
    limit = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 3
    major = SEVERITY_RANK[Severity.MAJOR]
    chosen = [
        finding
        for finding in findings
        if finding.state in OPEN_FINDING_STATES - {FindingState.OPEN}
        and SEVERITY_RANK[finding.severity] >= major
    ]
    chosen.sort(key=lambda finding: (-SEVERITY_RANK[finding.severity], finding.finding_key))
    return tuple(chosen[:limit])
