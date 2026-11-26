"""Manual check verdicts: an append-only supersedes chain (execution §4.12, §7.1 ``record_manual_verdict``).

A correction (``pass`` → ``fail`` or back) never rewrites a verdict: the new verdict supersedes the
previous one and both stay. The check state is a projection of the current verdict. Only a trusted human
principal records a verdict, with the role the check spec names (``actor_role``); a service or worker never
becomes human through a role or a DTO field. A verdict is recorded only on a check of the attempt's
current output, so a verdict about output A never decides output B.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.check_execution import CheckKind, CheckState, transition_check

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from datetime import datetime
    from typing import Literal

    from skm.kernel.actor import Actor
    from skm.kernel.ids import PrincipalId
    from skm.modules.execution.domain.check_execution import CheckExecution
    from skm.modules.execution.domain.ids import CheckExecutionId, ManualVerdictId, OutputId

__all__ = ["COMMENT_MAX_CHARS", "ManualVerdict", "current_verdict", "record_manual_verdict"]

COMMENT_MAX_CHARS: Final = 4000


@dataclass(frozen=True, slots=True)
class ManualVerdict:
    id: ManualVerdictId
    check_execution_id: CheckExecutionId
    principal_id: PrincipalId
    verdict: Literal["pass", "fail"]
    comment: str
    recorded_at: datetime
    supersedes_id: ManualVerdictId | None

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.verdict not in {"pass", "fail"}:
            problems.append("verdict is pass or fail")
        if self.supersedes_id == self.id:
            problems.append("a verdict does not supersede itself")
        if len(self.comment) > COMMENT_MAX_CHARS:
            problems.append(f"comment is at most {COMMENT_MAX_CHARS} characters")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "manual verdict invariants violated: " + "; ".join(problems),
                details={"manual_verdict_id": str(self.id), "violations": list(problems)},
            )


def current_verdict(verdicts: Sequence[ManualVerdict]) -> ManualVerdict | None:
    """The head of the one linear supersedes chain, which is also the latest by ``recorded_at``.

    The chain is checked: one check execution, one root, every verdict superseded at most once, no
    dangling or cyclic link, and no verdict recorded before the one it supersedes. A broken history is
    ``SCHEMA_INVALID``, never a guessed current verdict.
    """
    if not verdicts:
        return None
    by_id = {verdict.id: verdict for verdict in verdicts}
    problems: list[str] = []
    if len(by_id) != len(verdicts):
        problems.append("verdict ids are unique")
    if len({verdict.check_execution_id for verdict in verdicts}) != 1:
        problems.append("the verdicts belong to one check execution")
    successor: dict[ManualVerdictId, ManualVerdict] = {}
    roots = [verdict for verdict in verdicts if verdict.supersedes_id is None]
    for verdict in verdicts:
        previous = verdict.supersedes_id
        if previous is None:
            continue
        if previous not in by_id:
            problems.append(f"{verdict.id} supersedes an unknown verdict")
        elif previous in successor:
            problems.append(f"{previous} is superseded more than once")
        else:
            successor[previous] = verdict
            if verdict.recorded_at < by_id[previous].recorded_at:
                problems.append(f"{verdict.id} is recorded before the verdict it supersedes")
    if len(roots) != 1:
        problems.append("the chain has exactly one first verdict")
    if problems:
        raise _broken(verdicts, problems)
    head, walked = roots[0], 1
    while head.id in successor:
        head, walked = successor[head.id], walked + 1
    if walked != len(verdicts):
        raise _broken(verdicts, ["every verdict is on the one chain"])
    return head


def record_manual_verdict(  # noqa: PLR0913 -- exact command inputs of §7.1
    check: CheckExecution,
    history: Sequence[ManualVerdict],
    *,
    actor: Actor,
    actor_roles: Collection[str],
    required_role: str | None,
    current_output_id: OutputId | None,
    verdict: Literal["pass", "fail"],
    comment: str,
    supersedes_id: ManualVerdictId | None,
    verdict_id: ManualVerdictId,
    now: datetime,
) -> tuple[ManualVerdict, CheckExecution]:
    """A new verdict and the check state it projects; the history is only appended to.

    ``FORBIDDEN``: the actor is not a trusted human, or lacks the check spec's ``actor_role``.
    ``INVALID_TRANSITION``: not a manual check, the check is not on the current output, the check is
    not waiting (``manual_pending``) or decided (``passed``/``failed`` with a verdict to supersede).
    ``VERSION_CONFLICT``: ``supersedes_id`` is not the current verdict.

    The command ``execution.record_manual_verdict`` (§7.1) must authorize ``check.verdict`` on the
    stored check's run scope before calling this domain rule; the human/actor-role checks here are
    additional invariants, not evidence of that permission.
    """
    if actor.kind is not PrincipalKind.HUMAN:
        raise error_for(
            ErrorCode.FORBIDDEN,
            "a manual verdict is recorded only by a human principal",
            details={"reason": "not_human", "principal_kind": actor.kind.value},
        )
    if required_role is not None and required_role not in actor_roles:
        raise error_for(
            ErrorCode.FORBIDDEN,
            f"the check needs the role {required_role}",
            details={"reason": "actor_role", "required_role": required_role},
        )
    details = {"check_execution_id": str(check.id), "state": check.state.value}
    if check.kind is not CheckKind.MANUAL:
        raise error_for(ErrorCode.INVALID_TRANSITION, "only a manual check takes a verdict", details=details)
    if check.output_id != current_output_id:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "a verdict is recorded only on a check of the current output",
            details={**details, "reason": "OUTPUT_NOT_CURRENT"},
        )
    if any(item.check_execution_id != check.id for item in history):
        raise _broken(history, ["the history belongs to this check execution"])
    current = current_verdict(history)
    expected_state = CheckState.MANUAL_PENDING
    if current is not None:
        expected_state = CheckState.PASSED if current.verdict == "pass" else CheckState.FAILED
    if check.state is not expected_state:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            f"a {check.state} check does not take a verdict here",
            details={**details, "expected_state": expected_state.value},
        )
    expected_id = None if current is None else current.id
    if supersedes_id != expected_id:
        raise error_for(
            ErrorCode.VERSION_CONFLICT,
            "a verdict supersedes exactly the current verdict",
            details={
                **details,
                "supersedes_id": None if supersedes_id is None else str(supersedes_id),
                "current_verdict_id": None if expected_id is None else str(expected_id),
            },
        )
    if current is not None and now < current.recorded_at:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "a verdict is not recorded before the one it supersedes",
            details=details,
        )
    recorded = ManualVerdict(
        id=verdict_id,
        check_execution_id=check.id,
        principal_id=actor.principal_id,
        verdict=verdict,
        comment=comment,
        recorded_at=now,
        supersedes_id=supersedes_id,
    )
    target = CheckState.PASSED if verdict == "pass" else CheckState.FAILED
    return recorded, check if target is check.state else transition_check(check, target)


def _broken(verdicts: Sequence[ManualVerdict], problems: list[str]) -> Exception:
    return error_for(
        ErrorCode.SCHEMA_INVALID,
        "manual verdict history is broken: " + "; ".join(problems),
        details={"verdict_ids": [str(verdict.id) for verdict in verdicts], "violations": list(problems)},
    )
