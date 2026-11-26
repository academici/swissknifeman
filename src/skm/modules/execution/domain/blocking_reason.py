"""Task wait and block reasons (execution §4.19, G9; conventions §6.1).

A blocking reason is a value, not an error: the code, when the wait began, when the system looks again,
who resolves it, which actions a surface may offer and the deadline. The catalog below is the single
domain owner of the closed ``BlockingCode`` set; the DDL CHECK ``ck_run_tasks__blocking_code`` and the
schema ``urn:skm:execution:blocking-reason:v1`` repeat the same codes. Pure code: the caller passes the
time and every settings-derived instant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NoReturn, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import TaskId

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "BLOCKING_CATALOG",
    "LEGACY_BLOCKING_CODES",
    "MESSAGE_MAX",
    "AllowedAction",
    "BlockingCode",
    "BlockingCodeSpec",
    "BlockingReason",
    "DeadlineSource",
    "NextCheckSource",
    "ResolverRole",
    "blocking_reason",
    "blocking_reason_from_json",
    "blocking_reason_to_json",
    "migrate_legacy_code",
]

MESSAGE_MAX: Final = 300


class BlockingCode(StrEnum):
    WAITING_OWNER = "WAITING_OWNER"
    WAITING_ANSWER = "WAITING_ANSWER"
    WAITING_ADVISOR = "WAITING_ADVISOR"
    WAITING_MANUAL_CHECK = "WAITING_MANUAL_CHECK"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_PROVIDER = "WAITING_PROVIDER"
    WAITING_BUDGET_RESET = "WAITING_BUDGET_RESET"
    BLOCKED_BY_DEPENDENCY = "BLOCKED_BY_DEPENDENCY"
    BLOCKED_BY_MATERIAL = "BLOCKED_BY_MATERIAL"
    BLOCKED_BY_BUDGET = "BLOCKED_BY_BUDGET"
    BLOCKED_BY_CAPABILITY = "BLOCKED_BY_CAPABILITY"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    BLOCKED_BY_INTEGRATION = "BLOCKED_BY_INTEGRATION"
    SUSPECTED_STALL = "SUSPECTED_STALL"
    RECOVERING = "RECOVERING"


class ResolverRole(StrEnum):
    OWNER = "owner"
    MAINTAINER = "maintainer"
    MEMBER = "member"
    ADVISOR = "advisor"
    SYSTEM = "system"


class AllowedAction(StrEnum):
    WAIT = "wait"
    ANSWER_QUESTION = "answer_question"
    RECORD_VERDICT = "record_verdict"
    APPROVE_INTENT = "approve_intent"
    DECIDE_ESCALATION = "decide_escalation"
    RAISE_BUDGET = "raise_budget"
    RESTART_TASK = "restart_task"
    SKIP_TASK = "skip_task"
    START_WORKER = "start_worker"
    RESUME_RUN = "resume_run"
    CANCEL_RUN = "cancel_run"
    RETRY_NOW = "retry_now"
    PROVIDE_MATERIAL = "provide_material"
    ACCEPT_DEVIATION = "accept_deviation"


class NextCheckSource(StrEnum):
    """Where ``next_check_at`` comes from; ``NONE`` forbids it, the others require it."""

    NONE = "none"
    NOT_BEFORE = "not_before"  # provider retry_after / quota reset of the stage
    RESET_AT = "reset_at"  # budget window reset
    MATERIAL_RECHECK = "material_recheck"  # now + execution.materials.recheck_seconds
    CAPABILITY_WAIT = "capability_wait"  # now + execution.scheduler.capability_wait_seconds
    GRACE = "grace"  # now + execution.supervisor.grace_seconds (L2: execution.lease.reap_wait_seconds)


class DeadlineSource(StrEnum):
    """Where ``deadline_at`` comes from; ``NONE`` forbids it."""

    NONE = "none"
    REQUEST = "request"  # decision_request.deadline_at, optional
    INTENT_EXPIRY = "intent_expiry"  # optional
    PROVIDER_WAIT_MAX = "provider_wait_max"  # required: now + execution.retry.provider_wait_max_seconds
    QUOTA_WAIT_MAX = "quota_wait_max"  # required: now + execution.autopilot.quota_wait_max_seconds


_REQUIRED_DEADLINES = frozenset({DeadlineSource.PROVIDER_WAIT_MAX, DeadlineSource.QUOTA_WAIT_MAX})

_WORKING = frozenset({"executing", "checking", "reviewing", "integrating"})


@dataclass(frozen=True, slots=True)
class BlockingCodeSpec:
    """One row of the §4.19 table.

    ``resolver_role`` and ``allowed_actions`` are the defaults; ``BLOCKED_BY_DEPENDENCY`` with failed
    prerequisites, ``WAITING_ANSWER`` and ``WAITING_MANUAL_CHECK`` adjust them (see ``blocking_reason``).
    """

    code: BlockingCode
    task_statuses: frozenset[str]
    refs: tuple[str, ...]
    required_refs: tuple[str, ...]
    resolver_role: ResolverRole | None
    allowed_actions: tuple[AllowedAction, ...]
    next_check: NextCheckSource
    deadline: DeadlineSource


def _spec(
    code: BlockingCode,
    statuses: frozenset[str] | str,
    refs: tuple[str, ...],
    required: tuple[str, ...],
    role: ResolverRole | None,
    actions: tuple[AllowedAction, ...],
    next_check: NextCheckSource = NextCheckSource.NONE,
    deadline: DeadlineSource = DeadlineSource.NONE,
) -> BlockingCodeSpec:
    status_set = frozenset({statuses}) if isinstance(statuses, str) else statuses
    return BlockingCodeSpec(code, status_set, refs, required, role, actions, next_check, deadline)


_A = AllowedAction
_R = ResolverRole
_C = BlockingCode

BLOCKING_CATALOG: Final[Mapping[BlockingCode, BlockingCodeSpec]] = MappingProxyType(
    {
        spec.code: spec
        for spec in (
            _spec(
                _C.WAITING_OWNER,
                "awaiting_decision",
                ("decision_request_id", "stop_code"),
                ("decision_request_id", "stop_code"),
                _R.OWNER,
                (_A.DECIDE_ESCALATION, _A.SKIP_TASK, _A.CANCEL_RUN),
                deadline=DeadlineSource.REQUEST,
            ),
            _spec(
                _C.WAITING_ANSWER,
                "awaiting_decision",
                ("decision_request_id", "question_key"),
                ("decision_request_id", "question_key"),
                _R.OWNER,
                (_A.ANSWER_QUESTION, _A.SKIP_TASK),
                deadline=DeadlineSource.REQUEST,
            ),
            _spec(
                _C.WAITING_ADVISOR,
                frozenset({"executing", "checking", "reviewing"}),
                ("decision_request_id", "stage_record_id"),
                ("decision_request_id", "stage_record_id"),
                _R.ADVISOR,
                (_A.WAIT, _A.CANCEL_RUN),
            ),
            _spec(
                _C.WAITING_MANUAL_CHECK,
                "manual_pending",
                ("check_execution_id", "check_key"),
                ("check_execution_id", "check_key"),
                _R.MEMBER,
                (_A.RECORD_VERDICT,),
            ),
            _spec(
                _C.WAITING_APPROVAL,
                "awaiting_decision",
                ("intent_id", "decision_request_id"),
                ("intent_id", "decision_request_id"),
                _R.MAINTAINER,
                (_A.APPROVE_INTENT, _A.CANCEL_RUN),
                deadline=DeadlineSource.INTENT_EXPIRY,
            ),
            _spec(
                _C.WAITING_PROVIDER,
                _WORKING,
                ("stage_record_id", "error_class", "route"),
                ("stage_record_id", "error_class", "route"),
                _R.SYSTEM,
                (_A.WAIT, _A.RETRY_NOW),
                NextCheckSource.NOT_BEFORE,
                DeadlineSource.PROVIDER_WAIT_MAX,
            ),
            _spec(
                _C.WAITING_BUDGET_RESET,
                "awaiting_decision",
                ("stop_code", "reset_at"),
                ("stop_code", "reset_at"),
                _R.SYSTEM,
                (_A.WAIT, _A.RAISE_BUDGET, _A.CANCEL_RUN),
                NextCheckSource.RESET_AT,
                DeadlineSource.QUOTA_WAIT_MAX,
            ),
            _spec(
                _C.BLOCKED_BY_DEPENDENCY,
                "blocked",
                ("prerequisite_task_ids", "failed_task_ids"),
                ("prerequisite_task_ids",),
                None,
                (_A.WAIT,),
            ),
            _spec(
                _C.BLOCKED_BY_MATERIAL,
                "blocked",
                ("material_ids", "file_version_ids", "required_for"),
                ("material_ids", "required_for"),
                _R.MEMBER,
                (_A.PROVIDE_MATERIAL, _A.SKIP_TASK),
                NextCheckSource.MATERIAL_RECHECK,
            ),
            _spec(
                _C.BLOCKED_BY_BUDGET,
                "awaiting_decision",
                ("decision_request_id", "dimension", "scope", "limit", "spent", "reason"),
                ("decision_request_id", "dimension", "scope", "limit", "spent"),
                _R.OWNER,
                (_A.RAISE_BUDGET, _A.CANCEL_RUN),
            ),
            _spec(
                _C.BLOCKED_BY_CAPABILITY,
                "ready",
                (
                    "capabilities",
                    "required_host_id",
                    "required_labels",
                    "environment_kind",
                    "isolation_profiles",
                ),
                ("capabilities", "required_labels", "environment_kind", "isolation_profiles"),
                _R.MAINTAINER,
                (_A.START_WORKER, _A.CANCEL_RUN),
                NextCheckSource.CAPABILITY_WAIT,
            ),
            _spec(
                _C.BLOCKED_BY_POLICY,
                "awaiting_decision",
                ("reason", "decision_request_id"),
                ("reason",),
                _R.OWNER,
                (_A.RESUME_RUN, _A.CANCEL_RUN),
            ),
            _spec(
                _C.BLOCKED_BY_INTEGRATION,
                "integrating",
                ("integration_task_id",),
                ("integration_task_id",),
                None,
                (_A.WAIT,),
            ),
            _spec(
                _C.SUSPECTED_STALL,
                _WORKING,
                ("stage_record_id", "step_id", "silent_seconds", "health_reason"),
                ("stage_record_id", "silent_seconds", "health_reason"),
                _R.SYSTEM,
                (_A.WAIT, _A.RESTART_TASK),
                NextCheckSource.GRACE,
            ),
            _spec(
                _C.RECOVERING,
                _WORKING,
                (
                    "stage_record_id",
                    "recovery_record_id",
                    "reap_stage_record_id",
                    "reap_step_id",
                    "recovery_step",
                ),
                ("stage_record_id", "recovery_step"),
                _R.SYSTEM,
                (_A.WAIT,),
                NextCheckSource.GRACE,
            ),
        )
    }
)

# Codes of the legacy runner and of earlier drafts, mapped onto the closed set (§4.19).
# ``RUN_PAUSED`` is a run state (pause_reason/stop_code), never a task code.
LEGACY_BLOCKING_CODES: Final[Mapping[str, BlockingCode | None]] = MappingProxyType(
    {
        "WAITING_DEPENDENCIES": BlockingCode.BLOCKED_BY_DEPENDENCY,
        "PREREQUISITE_FAILED": BlockingCode.BLOCKED_BY_DEPENDENCY,
        "WAITING_GROUP_REVIEW": BlockingCode.BLOCKED_BY_DEPENDENCY,
        "WAITING_ESCALATION": BlockingCode.WAITING_OWNER,
        "REWORK_LIMIT_REACHED": BlockingCode.WAITING_OWNER,
        "WAITING_INTEGRATION_TASK": BlockingCode.BLOCKED_BY_INTEGRATION,
        "WAITING_HOST": BlockingCode.BLOCKED_BY_CAPABILITY,
        "WAITING_CAPABILITY": BlockingCode.BLOCKED_BY_CAPABILITY,
        "BUDGET_EXHAUSTED": BlockingCode.BLOCKED_BY_BUDGET,
        "RUN_PAUSED": None,
    }
)

_PROVIDER_ERROR_CLASSES = frozenset({"rate_limit", "quota"})
_POLICY_REASONS = frozenset({"kill_switch", "emergency_stop", "policy_denies"})
_HUMAN_RESOLVERS = frozenset({ResolverRole.OWNER, ResolverRole.MAINTAINER, ResolverRole.MEMBER})
# codes whose resolver is the human audience of the check (actor_role) or of the question (answer_schema)
_AUDIENCE_CODES = frozenset({BlockingCode.WAITING_MANUAL_CHECK, BlockingCode.WAITING_ANSWER})
# BLOCKED_BY_DEPENDENCY once a prerequisite failed: the owner restarts or skips
_FAILED_DEPENDENCY: Final = (ResolverRole.OWNER, (AllowedAction.RESTART_TASK, AllowedAction.SKIP_TASK))
_STOP_CODE = re.compile(r"[A-Z][A-Z0-9_]{1,63}")


@dataclass(frozen=True, slots=True)
class BlockingReason:
    code: BlockingCode
    task_id: TaskId
    refs: Mapping[str, JsonValue]
    since: datetime
    next_check_at: datetime | None
    resolver_role: ResolverRole | None
    allowed_actions: tuple[AllowedAction, ...]
    deadline_at: datetime | None
    message: str

    def __post_init__(self) -> None:
        spec = BLOCKING_CATALOG[BlockingCode(self.code)]
        _check_refs(spec, self.refs)
        if len(self.message) > MESSAGE_MAX:
            _invalid("message", f"blocking message is longer than {MESSAGE_MAX} characters")
        for name, value in (
            ("since", self.since),
            ("next_check_at", self.next_check_at),
            ("deadline_at", self.deadline_at),
        ):
            if value is not None and value.utcoffset() is None:
                _invalid(name, "blocking reason times are aware UTC datetimes")
        if spec.next_check is NextCheckSource.NONE and self.next_check_at is not None:
            _invalid("next_check_at", f"{spec.code} is never rechecked by the system")
        if spec.next_check is not NextCheckSource.NONE and self.next_check_at is None:
            _invalid("next_check_at", f"{spec.code} needs next_check_at ({spec.next_check})")
        if spec.deadline is DeadlineSource.NONE and self.deadline_at is not None:
            _invalid("deadline_at", f"{spec.code} has no deadline")
        if spec.deadline in _REQUIRED_DEADLINES and self.deadline_at is None:
            _invalid("deadline_at", f"{spec.code} needs deadline_at ({spec.deadline})")
        if len(set(self.allowed_actions)) != len(self.allowed_actions):
            _invalid("allowed_actions", "allowed actions repeat")
        _check_resolution(spec, self.refs, self.resolver_role, self.allowed_actions)
        object.__setattr__(self, "refs", MappingProxyType(dict(self.refs)))


def blocking_reason(  # noqa: PLR0913
    code: BlockingCode,
    *,
    task_id: TaskId,
    refs: Mapping[str, JsonValue],
    now: datetime,
    message: str,
    previous: BlockingReason | None = None,
    next_check_at: datetime | None = None,
    deadline_at: datetime | None = None,
    resolver_role: ResolverRole | None = None,
) -> BlockingReason:
    """Build the reason of the §4.19 table for ``code``.

    ``since`` stays the one of ``previous`` when the same task is still blocked by the same code, so a
    rewrite (a new ``next_check_at``, refreshed refs) does not restart the wait. ``resolver_role`` may only
    name the human role a check (``WAITING_MANUAL_CHECK``: check spec ``actor_role``) or a question
    audience (``WAITING_ANSWER``) asks for; other codes keep the table value. A message over 300
    characters is cut with an ellipsis.
    """
    code = BlockingCode(code)
    spec = BLOCKING_CATALOG[code]
    role = spec.resolver_role
    actions = spec.allowed_actions
    if resolver_role is not None:
        if code not in _AUDIENCE_CODES:
            _invalid("resolver_role", f"{code} is always resolved by {spec.resolver_role}")
        if resolver_role not in _HUMAN_RESOLVERS:
            _invalid("resolver_role", "a check or question audience is a human role")
        role = resolver_role
    if code is BlockingCode.BLOCKED_BY_DEPENDENCY and refs.get("failed_task_ids"):
        role, actions = _FAILED_DEPENDENCY
    since = now
    if previous is not None and previous.code is code and previous.task_id == task_id:
        since = previous.since
    text = message if len(message) <= MESSAGE_MAX else message[: MESSAGE_MAX - 1] + "…"
    return BlockingReason(
        code=code,
        task_id=task_id,
        refs=refs,
        since=since,
        next_check_at=next_check_at,
        resolver_role=role,
        allowed_actions=actions,
        deadline_at=deadline_at,
        message=text,
    )


def migrate_legacy_code(code: str) -> BlockingCode | None:
    """The closed code of a legacy wait code; ``None`` for run-level ``RUN_PAUSED``.

    A current code maps to itself; anything else is ``SCHEMA_INVALID`` rather than a guess.
    """
    if code in BlockingCode.__members__:
        return BlockingCode(code)
    if code in LEGACY_BLOCKING_CODES:
        return LEGACY_BLOCKING_CODES[code]
    raise error_for(
        ErrorCode.SCHEMA_INVALID, f"unknown blocking code {code!r}", details={"field": "code", "code": code}
    )


def blocking_reason_to_json(reason: BlockingReason) -> JsonObject:
    """The stored form (``run_tasks.blocking_reason``, schema ``urn:skm:execution:blocking-reason:v1``)."""
    return {
        "code": reason.code.value,
        "task_id": str(reason.task_id),
        "refs": dict(reason.refs),
        "since": _utc(reason.since),
        "next_check_at": None if reason.next_check_at is None else _utc(reason.next_check_at),
        "resolver_role": None if reason.resolver_role is None else reason.resolver_role.value,
        "allowed_actions": [action.value for action in reason.allowed_actions],
        "deadline_at": None if reason.deadline_at is None else _utc(reason.deadline_at),
        "message": reason.message,
    }


def blocking_reason_from_json(document: JsonObject) -> BlockingReason:
    """Read a stored reason; the invariants of ``BlockingReason`` apply again."""
    try:
        role = document.get("resolver_role")
        refs = document.get("refs") or {}
        if not isinstance(refs, dict):
            _invalid("refs", "refs is an object")
        actions = document.get("allowed_actions") or []
        if not isinstance(actions, list):
            _invalid("allowed_actions", "allowed_actions is an array")
        return BlockingReason(
            code=BlockingCode(cast("str", document["code"])),
            task_id=TaskId(UUID(cast("str", document["task_id"]))),
            refs=refs,
            since=_parse_utc(document["since"]),
            next_check_at=_parse_optional_utc(document.get("next_check_at")),
            resolver_role=None if role is None else ResolverRole(cast("str", role)),
            allowed_actions=tuple(AllowedAction(cast("str", action)) for action in actions),
            deadline_at=_parse_optional_utc(document.get("deadline_at")),
            message=cast("str", document.get("message", "")),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, f"invalid blocking reason: {exc}") from exc


def _check_refs(spec: BlockingCodeSpec, refs: Mapping[str, JsonValue]) -> None:
    unknown = sorted(set(refs) - set(spec.refs))
    if unknown:
        _invalid("refs", f"{spec.code} does not carry refs {unknown}")
    # a list ref may be empty (a freshly compiled task waits before its first readiness check)
    missing = sorted(name for name in spec.required_refs if refs.get(name) is None or refs.get(name) == "")
    if missing:
        _invalid("refs", f"{spec.code} needs refs {missing}")
    code = spec.code
    if code is BlockingCode.WAITING_PROVIDER and refs["error_class"] not in _PROVIDER_ERROR_CLASSES:
        _invalid("refs.error_class", "error_class is rate_limit or quota")
    if code is BlockingCode.WAITING_BUDGET_RESET and refs["stop_code"] != "QUOTA_EXHAUSTED":
        _invalid("refs.stop_code", "WAITING_BUDGET_RESET waits for a QUOTA_EXHAUSTED reset")
    if code is BlockingCode.WAITING_OWNER and not _STOP_CODE.fullmatch(str(refs["stop_code"])):
        _invalid("refs.stop_code", "stop_code is an UPPER_SNAKE code")
    if code is BlockingCode.BLOCKED_BY_POLICY and refs["reason"] not in _POLICY_REASONS:
        _invalid("refs.reason", "policy reason is kill_switch, emergency_stop or policy_denies")
    if code is BlockingCode.BLOCKED_BY_BUDGET and refs.get("reason") not in (None, "unmetered"):
        _invalid("refs.reason", "the only budget reason is unmetered")
    if code is BlockingCode.RECOVERING:
        # either a supervisor procedure (§5.17) or the L2 reap barrier; reap_step_id is agent-only
        if (refs.get("recovery_record_id") is None) == (refs.get("reap_stage_record_id") is None):
            _invalid("refs", "RECOVERING names exactly one of recovery_record_id and reap_stage_record_id")
        if refs.get("reap_step_id") is not None and refs.get("reap_stage_record_id") is None:
            _invalid("refs.reap_step_id", "reap_step_id belongs to an L2 reap barrier")


def _check_resolution(
    spec: BlockingCodeSpec,
    refs: Mapping[str, JsonValue],
    role: ResolverRole | None,
    actions: tuple[AllowedAction, ...],
) -> None:
    """The resolver and the surface actions are the ones of the §4.19 row, for every way of building.

    The only variants are the human audience of ``WAITING_MANUAL_CHECK``/``WAITING_ANSWER`` and the
    failed-prerequisite form of ``BLOCKED_BY_DEPENDENCY``; the order of the actions is not significant.
    """
    expected_role, expected_actions = spec.resolver_role, spec.allowed_actions
    if spec.code is BlockingCode.BLOCKED_BY_DEPENDENCY and refs.get("failed_task_ids"):
        expected_role, expected_actions = _FAILED_DEPENDENCY
    if spec.code in _AUDIENCE_CODES:
        if role not in _HUMAN_RESOLVERS:
            _invalid("resolver_role", f"{spec.code} is resolved by a human role")
    elif role is not expected_role:
        _invalid("resolver_role", f"{spec.code} is resolved by {expected_role}")
    if set(actions) != set(expected_actions):
        allowed = ", ".join(action.value for action in expected_actions)
        _invalid("allowed_actions", f"{spec.code} offers exactly {allowed}")


def _invalid(field: str, message: str) -> NoReturn:
    raise error_for(ErrorCode.SCHEMA_INVALID, message, details={"field": field})


def _utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("timestamp is a string")
    return datetime.fromisoformat(value)


def _parse_optional_utc(value: object) -> datetime | None:
    return None if value is None else _parse_utc(value)
