"""Check executions: eight states, their transitions and result classification (execution §4.12).

``failed`` is a negative result, ``error`` a check that could not run correctly, ``manual_pending`` a wait
for a human and ``unknown`` a lost or unprovable outcome; only ``passed`` is green. A check execution is
bound to exactly one output: its result never counts for another output. A passed result is reused only
for the same workspace, check spec and complete fingerprint (output tree, check spec and env manifest)
with its evidence available now; an incomplete manifest, a post-integration recheck and any state other
than ``passed`` (a timeout is ``error``) never make a green receipt.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import AttemptId, EntityId, RunId, TaskId, WorkspaceId
    from skm.modules.execution.domain.ids import CheckExecutionId, OutputId

__all__ = [
    "CHECK_TRANSITIONS",
    "SUMMARY_MAX_CHARS",
    "SUMMARY_MAX_LINES",
    "CheckExecution",
    "CheckKind",
    "CheckState",
    "check_summary",
    "classify_check_result",
    "may_reuse",
    "transition_check",
]

SUMMARY_MAX_CHARS: Final = 4000
SUMMARY_MAX_LINES: Final = 40
_FINGERPRINT: Final = re.compile(r"sha256:[0-9a-f]{64}")


class CheckKind(StrEnum):
    COMMAND = "command"
    SHELL = "shell"
    MANUAL = "manual"
    EXTERNAL = "external"


class CheckState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    MANUAL_PENDING = "manual_pending"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


_RESULTS: Final = frozenset(
    {CheckState.PASSED, CheckState.FAILED, CheckState.ERROR, CheckState.UNKNOWN, CheckState.CANCELLED}
)
# §4.12: from → allowed targets. A manual verdict moves a manual check between passed and failed; a new
# verdict supersedes the previous one, the earlier verdict stays in its history.
CHECK_TRANSITIONS: Final[dict[CheckState, frozenset[CheckState]]] = {
    CheckState.PENDING: _RESULTS | {CheckState.RUNNING, CheckState.MANUAL_PENDING},
    CheckState.RUNNING: _RESULTS,
    CheckState.MANUAL_PENDING: frozenset({CheckState.PASSED, CheckState.FAILED, CheckState.CANCELLED}),
    CheckState.PASSED: frozenset({CheckState.FAILED}),
    CheckState.FAILED: frozenset({CheckState.PASSED}),
    CheckState.ERROR: frozenset(),
    CheckState.CANCELLED: frozenset(),
    CheckState.UNKNOWN: frozenset(),
}


@dataclass(frozen=True, slots=True)
class CheckExecution:
    id: CheckExecutionId
    workspace_id: WorkspaceId
    run_id: RunId
    task_id: TaskId
    attempt_id: AttemptId
    output_id: OutputId
    check_spec_id: EntityId
    check_key: str
    kind: CheckKind
    required: bool
    state: CheckState
    exit_code: int | None
    summary: str
    error_code: str | None
    reused_from_id: CheckExecutionId | None
    fingerprint: str
    started_at: datetime | None
    finished_at: datetime | None
    round_no: int

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.state is CheckState.MANUAL_PENDING and self.kind is not CheckKind.MANUAL:
            problems.append("only a manual check waits in manual_pending")
        if self.reused_from_id is not None and (
            self.reused_from_id == self.id or self.state is not CheckState.PASSED
        ):
            problems.append("a reused result is another passed check execution")
        if len(self.summary) > SUMMARY_MAX_CHARS:
            problems.append(f"summary is at most {SUMMARY_MAX_CHARS} characters")
        if not _FINGERPRINT.fullmatch(self.fingerprint):
            problems.append("fingerprint is sha256:<64 hex>")
        if self.round_no < 1:
            problems.append("round_no >= 1")
        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            problems.append("finished_at is not before started_at")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "check execution invariants violated: " + "; ".join(problems),
                details={"check_execution_id": str(self.id), "violations": list(problems)},
            )


def classify_check_result(
    kind: CheckKind,
    exit_code: int | None,
    timed_out: bool,
    spawn_error: str | None,
    interrupted: bool,
    *,
    expected_exit: int = 0,
) -> tuple[CheckState, str | None]:
    """State and error code of a finished check run; a missing exit code is never a pass."""
    if spawn_error is not None:
        return CheckState.ERROR, ErrorCode.RUNTIME_CRASHED
    if timed_out:
        return CheckState.ERROR, ErrorCode.RUNTIME_TIMEOUT
    if interrupted:
        return CheckState.UNKNOWN, None
    if kind is CheckKind.MANUAL:
        return CheckState.MANUAL_PENDING, ErrorCode.MANUAL_PENDING
    if exit_code is None:
        return CheckState.UNKNOWN, None
    return (CheckState.PASSED, None) if exit_code == expected_exit else (CheckState.FAILED, None)


def transition_check(check: CheckExecution, to: CheckState) -> CheckExecution:
    """One row of §4.12; anything else (and passed/failed of a non-manual check) is ``INVALID_TRANSITION``."""
    allowed = CHECK_TRANSITIONS[check.state]
    verdict_flip = check.state in {CheckState.PASSED, CheckState.FAILED}
    if to not in allowed or (verdict_flip and check.kind is not CheckKind.MANUAL):
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            f"check cannot go from {check.state} to {to}",
            details={"check_execution_id": str(check.id), "from": check.state.value, "to": to.value},
        )
    return dataclasses.replace(check, state=to)


def check_summary(log: str) -> str:
    """The last 40 lines of a check log within 4000 characters, with a marker when something was cut."""
    lines = log.splitlines()
    kept = lines[-SUMMARY_MAX_LINES:]
    text = "\n".join(kept)
    if len(kept) == len(lines) and len(text) <= SUMMARY_MAX_CHARS:
        return text
    marker = f"… [{len(lines) - len(kept)} lines clipped]\n"
    room = SUMMARY_MAX_CHARS - len(marker)
    return marker + text[-room:]


def may_reuse(
    source: CheckExecution,
    *,
    workspace_id: WorkspaceId,
    check_spec_id: EntityId,
    fingerprint: str | None,
    evidence_available: bool,
    post_integration: bool,
    attested: bool = False,
) -> bool:
    """Whether a passed result is an exact receipt for a new check of the same spec.

    ``fingerprint`` is ``None`` when the current env manifest is incomplete (no reuse then). A manual or
    external result also needs its own trusted attestation of the full fingerprint. A post-integration
    recheck is always fresh.
    """
    if fingerprint is None or post_integration or not evidence_available:
        return False
    if source.kind in {CheckKind.MANUAL, CheckKind.EXTERNAL} and not attested:
        return False
    return (
        source.state is CheckState.PASSED
        and source.workspace_id == workspace_id
        and source.check_spec_id == check_spec_id
        and source.fingerprint == fingerprint
    )
