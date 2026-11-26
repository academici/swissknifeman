"""Review findings, their stable key and the logical finding of a task (execution §4.13, §5.8).

``finding_key`` recognises the same defect between rounds: severity, confidence, the line and the ``F<n>``
id are not part of it (D-EX-4), so a reviewer that lowers the severity of a defect keeps its key and the
drift check sees the lowering. A repeated key in a later review is a new row of that review; the logical
finding of a task is the row of the latest review round for each key, and acceptance (A6/A7) and the fix
brief read only logical findings.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Literal

    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.ids import FindingId, ReviewId

__all__ = [
    "OPEN_FINDING_STATES",
    "SEVERITY_RANK",
    "Finding",
    "FindingState",
    "Severity",
    "finding_key",
    "logical_findings",
    "normalize",
    "place",
]


class Severity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    NIT = "nit"


class FindingState(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    WAIVED = "waived"
    DEFERRED = "deferred"


# caution order of §5.7: higher is more severe
SEVERITY_RANK: Final[Mapping[Severity, int]] = {
    Severity.NIT: 0,
    Severity.MINOR: 1,
    Severity.MAJOR: 2,
    Severity.BLOCKER: 3,
}
# a finding in one of these states still asks for a fix or a decision
OPEN_FINDING_STATES: Final = frozenset({FindingState.OPEN, FindingState.CONFIRMED, FindingState.DEFERRED})

_KEY: Final = re.compile(r"fk-[0-9a-f]{16}")
_LOCAL_ID: Final = re.compile(r"F[0-9]{1,3}")
_DIGITS: Final = re.compile(r"\d")
_SEPARATORS: Final = re.compile(r"[\W_]+")


@dataclass(frozen=True, slots=True)
class Finding:
    id: FindingId
    review_id: ReviewId
    local_id: str
    finding_key: str
    severity: Severity
    confidence: Literal["high", "medium", "low"]
    basis: str
    category: str
    message: str
    failure_scenario: str
    location: JsonObject
    reproduction: JsonObject | None
    first_seen_review_id: ReviewId
    state: FindingState

    def __post_init__(self) -> None:
        problems: list[str] = []
        if not _KEY.fullmatch(self.finding_key):
            problems.append("finding_key is fk-<16 hex>")
        if not _LOCAL_ID.fullmatch(self.local_id):
            problems.append("local_id is F<n>")
        if not isinstance(self.location.get("path"), str):
            problems.append("location names a path")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "finding invariants violated: " + "; ".join(problems),
                details={"finding_id": str(self.id), "violations": list(problems)},
            )


def place(path: str) -> str:
    """``strip``, ``\\`` → ``/``, no leading ``./``; an empty place is ``-`` (§5.7)."""
    text = path.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text or "-"


def normalize(text: str) -> str:
    """casefold, drop digits, collapse whitespace and punctuation into one space, first 160 characters."""
    folded = _DIGITS.sub("", text.casefold())
    return _SEPARATORS.sub(" ", folded).strip()[:160]


def finding_key(location: Mapping[str, JsonValue], category: str, failure_scenario: str, message: str) -> str:
    """``fk-`` + 16 hex of the location (mount and place), the category and the normalized scenario.

    The message stands in only for an empty scenario. Lines are not part of the location key.
    """
    core = failure_scenario if failure_scenario.strip() else message
    mount = location.get("mount")
    path = location.get("path")
    material = (
        f"{mount if isinstance(mount, str) else ''}:{place(path if isinstance(path, str) else '')}\n"
        f"{category.strip().casefold() or '-'}\n{normalize(core)}"
    )
    return "fk-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def logical_findings(findings: Sequence[Finding], rounds: Mapping[ReviewId, int]) -> tuple[Finding, ...]:
    """The latest row of each ``finding_key`` by review round, ordered by key.

    ``rounds`` maps every review of the task to its round. A finding of a review outside it does not
    belong to the task: ``SCHEMA_INVALID`` rather than a silently ignored (possibly open) blocker. Two
    rows of one key in one review contradict ``UNIQUE(review_id, finding_key)`` and are refused too.
    """
    latest: dict[str, tuple[int, Finding]] = {}
    for finding in findings:
        round_no = rounds.get(finding.review_id)
        if round_no is None:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "a finding belongs to a review of the task",
                details={"finding_id": str(finding.id), "review_id": str(finding.review_id)},
            )
        seen = latest.get(finding.finding_key)
        if seen is not None and seen[0] == round_no:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "one review has one row per finding_key",
                details={"finding_key": finding.finding_key, "review_id": str(finding.review_id)},
            )
        if seen is None or seen[0] < round_no:
            latest[finding.finding_key] = (round_no, finding)
    return tuple(latest[key][1] for key in sorted(latest))
