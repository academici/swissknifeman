"""Closed predicate set of workflow stage conditions: types, evaluation and parsing (execution §5.3)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, cast

from skm.modules.execution.domain.check_execution import CheckState
from skm.modules.execution.domain.decision_request import (
    DecisionKind,
    DecisionState,
)
from skm.modules.execution.domain.review import Verdict
from skm.modules.execution.domain.run import RunKind
from skm.modules.execution.domain.task import ReviewMode, TaskKind

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.review import Review
    from skm.modules.execution.domain.workflow.actions import TaskState

ROUTE_FLAG_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,31}")
RISK_MAX = 100
_OPEN_CHECK_STATES = frozenset({CheckState.PENDING, CheckState.RUNNING, CheckState.MANUAL_PENDING})
_ERROR_CHECK_STATES = frozenset({CheckState.ERROR, CheckState.UNKNOWN, CheckState.CANCELLED})


class WorkKind(StrEnum):
    CODE = "code"
    DOCS = "docs"
    RESEARCH = "research"
    CONFIG = "config"
    TEST = "test"
    REVIEW = "review"
    OPS = "ops"


class PredicateKind(StrEnum):
    ROUTE_FLAG = "route_flag"
    REVIEW_MODE = "review_mode"
    REVIEW_VERDICT = "review_verdict"
    WORK_KIND = "work_kind"
    CHECK_OUTCOME = "check_outcome"
    ROUNDS_BELOW = "rounds_below"
    HAS_OPEN_QUESTIONS = "has_open_questions"
    TASK_KIND = "task_kind"
    RISK_AT_LEAST = "risk_at_least"
    RUN_KIND = "run_kind"


class CheckOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class RoundsCounter(StrEnum):
    REVIEW_ROUNDS = "review_rounds"
    CHECK_FIX_ROUNDS = "check_fix_rounds"


@dataclass(frozen=True, slots=True)
class RouteFlag:
    kind: ClassVar[PredicateKind] = PredicateKind.ROUTE_FLAG
    flag: str


@dataclass(frozen=True, slots=True)
class ReviewModeIs:
    kind: ClassVar[PredicateKind] = PredicateKind.REVIEW_MODE
    mode: ReviewMode


@dataclass(frozen=True, slots=True)
class ReviewVerdictIs:
    kind: ClassVar[PredicateKind] = PredicateKind.REVIEW_VERDICT
    verdict: Verdict


@dataclass(frozen=True, slots=True)
class WorkKindIn:
    kind: ClassVar[PredicateKind] = PredicateKind.WORK_KIND
    kinds: frozenset[WorkKind]


@dataclass(frozen=True, slots=True)
class CheckOutcomeIs:
    kind: ClassVar[PredicateKind] = PredicateKind.CHECK_OUTCOME
    outcome: CheckOutcome


@dataclass(frozen=True, slots=True)
class RoundsBelow:
    kind: ClassVar[PredicateKind] = PredicateKind.ROUNDS_BELOW
    counter: RoundsCounter
    limit: int


@dataclass(frozen=True, slots=True)
class HasOpenQuestions:
    kind: ClassVar[PredicateKind] = PredicateKind.HAS_OPEN_QUESTIONS
    value: bool


@dataclass(frozen=True, slots=True)
class TaskKindIn:
    kind: ClassVar[PredicateKind] = PredicateKind.TASK_KIND
    kinds: frozenset[TaskKind]


@dataclass(frozen=True, slots=True)
class RiskAtLeast:
    kind: ClassVar[PredicateKind] = PredicateKind.RISK_AT_LEAST
    score: int


@dataclass(frozen=True, slots=True)
class RunKindIn:
    kind: ClassVar[PredicateKind] = PredicateKind.RUN_KIND
    kinds: frozenset[RunKind]


type Predicate = (
    RouteFlag
    | ReviewModeIs
    | ReviewVerdictIs
    | WorkKindIn
    | CheckOutcomeIs
    | RoundsBelow
    | HasOpenQuestions
    | TaskKindIn
    | RiskAtLeast
    | RunKindIn
)

PREDICATE_TYPES: Mapping[PredicateKind, type[Predicate]] = {
    item.kind: item
    for item in (
        RouteFlag,
        ReviewModeIs,
        ReviewVerdictIs,
        WorkKindIn,
        CheckOutcomeIs,
        RoundsBelow,
        HasOpenQuestions,
        TaskKindIn,
        RiskAtLeast,
        RunKindIn,
    )
}


def check_outcome(state: TaskState) -> CheckOutcome | None:
    states = [check.state for check in state.checks if check.required]
    if any(item in _OPEN_CHECK_STATES for item in states):
        return None
    if any(item in _ERROR_CHECK_STATES for item in states):
        return CheckOutcome.ERROR
    return CheckOutcome.FAILED if any(item is CheckState.FAILED for item in states) else CheckOutcome.PASSED


def evaluate(predicate: Predicate, state: TaskState) -> bool:  # noqa: PLR0911
    match predicate:
        case RouteFlag("research"):
            policy = state.effective_policy.get("research_policy", "conditional")
            return policy == "required" or (policy == "conditional" and "research" in state.route_flags)
        case RouteFlag(flag):
            return flag in state.route_flags or (
                flag == "scout" and state.effective_policy.get("scout_mode") == "always"
            )
        case ReviewModeIs(mode):
            return state.task.review_mode is mode
        case ReviewVerdictIs(verdict):
            review = _latest_review(state)
            return review is not None and review.verdict is verdict
        case WorkKindIn(kinds):
            return state.task.work_kind in {kind.value for kind in kinds}
        case CheckOutcomeIs(outcome):
            return check_outcome(state) is outcome
        case RoundsBelow(counter, limit):
            is_rev = counter is RoundsCounter.REVIEW_ROUNDS
            return (state.task.review_rounds if is_rev else state.task.check_fix_rounds) < limit
        case HasOpenQuestions(value):
            open_q = any(
                r.kind is DecisionKind.QUESTION and r.state is DecisionState.OPEN for r in state.open_requests
            )
            return open_q is value
        case TaskKindIn(kinds):
            return state.task.kind in kinds
        case RiskAtLeast(score):
            return state.risk is not None and state.risk.score >= score
        case RunKindIn(kinds):
            return state.run.kind in kinds


def holds(condition: Condition, state: TaskState) -> bool:
    if isinstance(condition, AllPredicates):
        return all(evaluate(item, state) for item in condition.predicates)
    if isinstance(condition, AnyPredicates):
        return any(evaluate(item, state) for item in condition.predicates)
    return evaluate(condition, state)


def _latest_review(state: TaskState) -> Review | None:
    out = state.output
    revs = [r for r in state.reviews if out is not None and r.output_id == out.id and r.verdict is not None]
    return max(revs, key=lambda r: r.round_no, default=None)


@dataclass(frozen=True, slots=True)
class AllPredicates:
    predicates: tuple[Predicate, ...]


@dataclass(frozen=True, slots=True)
class AnyPredicates:
    predicates: tuple[Predicate, ...]


type Condition = Predicate | AllPredicates | AnyPredicates


class ConditionDefect(Exception):
    """The first defect of a condition document: JSON Pointer, stable reason code and message."""

    def __init__(self, pointer: str, reason: str, message: str) -> None:
        super().__init__(f"{pointer}: {message}")
        self.pointer = pointer
        self.reason = reason
        self.message = message


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _members[E: StrEnum](kind: type[E], value: object, pointer: str) -> frozenset[E]:
    if not isinstance(value, list) or not value:
        raise ConditionDefect(pointer, "invalid_shape", "must be a non-empty array")
    items = cast("list[object]", value)
    return frozenset(_member(kind, item, f"{pointer}/{index}") for index, item in enumerate(items))


def _member[E: StrEnum](kind: type[E], value: object, pointer: str) -> E:
    if isinstance(value, str):
        try:
            return kind(value)
        except ValueError:
            pass
    allowed = ", ".join(member.value for member in kind)
    raise ConditionDefect(pointer, "invalid_value", f"{value!r} is not one of {allowed}")


def _predicate(name: str, value: object, pointer: str) -> Predicate:  # noqa: PLR0911
    match name:
        case PredicateKind.ROUTE_FLAG:
            if not isinstance(value, str) or ROUTE_FLAG_PATTERN.fullmatch(value) is None:
                raise ConditionDefect(
                    pointer, "invalid_value", "route flag must match ^[a-z][a-z0-9_]{0,31}$"
                )
            return RouteFlag(value)
        case PredicateKind.REVIEW_MODE:
            return ReviewModeIs(_member(ReviewMode, value, pointer))
        case PredicateKind.REVIEW_VERDICT:
            return ReviewVerdictIs(_member(Verdict, value, pointer))
        case PredicateKind.WORK_KIND:
            return WorkKindIn(_members(WorkKind, value, pointer))
        case PredicateKind.CHECK_OUTCOME:
            return CheckOutcomeIs(_member(CheckOutcome, value, pointer))
        case PredicateKind.ROUNDS_BELOW:
            return _rounds_below(value, pointer)
        case PredicateKind.HAS_OPEN_QUESTIONS:
            if not isinstance(value, bool):
                raise ConditionDefect(pointer, "invalid_shape", "must be a boolean")
            return HasOpenQuestions(value)
        case PredicateKind.TASK_KIND:
            return TaskKindIn(_members(TaskKind, value, pointer))
        case PredicateKind.RISK_AT_LEAST:
            if not _is_int(value) or not 0 <= cast("int", value) <= RISK_MAX:
                raise ConditionDefect(pointer, "invalid_value", f"must be an integer 0..{RISK_MAX}")
            return RiskAtLeast(cast("int", value))
        case PredicateKind.RUN_KIND:
            return RunKindIn(_members(RunKind, value, pointer))
        case _:
            known = ", ".join(PredicateKind)
            raise ConditionDefect(pointer, "unknown_predicate", f"unknown predicate {name!r}; known: {known}")


def _rounds_below(value: object, pointer: str) -> RoundsBelow:
    if not isinstance(value, Mapping):
        raise ConditionDefect(pointer, "invalid_shape", "must be an object {counter, limit}")
    fields = cast("Mapping[str, object]", value)
    unknown = sorted(set(fields) - {"counter", "limit"})
    if unknown:
        raise ConditionDefect(f"{pointer}/{unknown[0]}", "unknown_field", f"unknown field {unknown[0]!r}")
    if "counter" not in fields or "limit" not in fields:
        raise ConditionDefect(pointer, "invalid_shape", "counter and limit are required")
    counter = _member(RoundsCounter, fields["counter"], f"{pointer}/counter")
    limit = fields["limit"]
    if not _is_int(limit) or cast("int", limit) < 0:
        raise ConditionDefect(f"{pointer}/limit", "invalid_value", "must be a non-negative integer")
    return RoundsBelow(counter, cast("int", limit))


def _single(value: object, pointer: str) -> Predicate:
    if not isinstance(value, Mapping):
        raise ConditionDefect(pointer, "invalid_shape", "a predicate must be an object")
    fields = cast("Mapping[str, object]", value)
    if len(fields) != 1:
        raise ConditionDefect(pointer, "invalid_shape", "a predicate has exactly one key")
    ((name, argument),) = fields.items()
    return _predicate(name, argument, f"{pointer}/{name}")


def parse_condition(value: JsonValue, pointer: str = "") -> Condition:
    """Typed condition of a ``when``/``skip_when`` document, or ``ConditionDefect`` for the first defect."""
    if isinstance(value, Mapping) and len(value) == 1:
        ((name, argument),) = value.items()
        if name in {"all", "any"}:
            group = f"{pointer}/{name}"
            if not isinstance(argument, list) or not argument:
                raise ConditionDefect(group, "invalid_shape", "must be a non-empty array of predicates")
            items = tuple(_single(item, f"{group}/{index}") for index, item in enumerate(argument))
            return AllPredicates(items) if name == "all" else AnyPredicates(items)
    return _single(value, pointer)
