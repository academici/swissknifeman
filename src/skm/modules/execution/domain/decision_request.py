"""Decision requests and answers (execution §4.16, §5.10).

``question_digest``/``question_key`` identify a question for reuse: the item, the kind, the text with
collapsed whitespace, the complete options sorted by id and the answer schema. An answer is recorded only
on an open request of the expected revision, and an ``owner`` answer only by a trusted human principal;
advisor, consilium, policy and reuse answers are separate paths that never answer an owner request and
never become owner approval. An answer applies to the next step only while every binding fact
(``input_part_digest``, attempt, stage, output) is unchanged; otherwise the request becomes stale: its
revision grows, the answer is kept in ``stale_answer`` and the request is open again. Nothing is ever
answered by a timeout.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject, JsonValue

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.actor import Actor
    from skm.kernel.ids import RunId, TaskId, WorkspaceId
    from skm.modules.execution.domain.autonomy import AuthorityEnvelope
    from skm.modules.execution.domain.contracts import DecisionPayload
    from skm.modules.execution.domain.decision_record import QuestionCategory
    from skm.modules.execution.domain.ids import DecisionAnswerId, DecisionRequestId, StepId

__all__ = [
    "ANSWER_KINDS",
    "BINDING_KEYS",
    "Audience",
    "DecisionAnswer",
    "DecisionKind",
    "DecisionRequest",
    "DecisionState",
    "answer_is_current",
    "answer_request",
    "apply_answer",
    "question_digest",
    "question_key",
]

ANSWER_KINDS: Final = frozenset({"owner", "advisor", "consilium", "policy", "reuse"})
# facts of a request binding compared before an answer is applied; any change makes the answer stale
BINDING_KEYS: Final = ("input_part_digest", "attempt_id", "stage_record_id", "output_id")
_SPACES: Final = re.compile(r"\s+")


class DecisionKind(StrEnum):
    QUESTION = "question"
    APPROVAL = "approval"
    MANUAL_CHECK = "manual_check"
    ESCALATION = "escalation"
    BUDGET = "budget"
    READINESS = "readiness"


class Audience(StrEnum):
    OWNER = "owner"
    ADVISOR = "advisor"
    CONSILIUM = "consilium"


class DecisionState(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    APPLIED = "applied"
    ASSUMED = "assumed"
    DENIED = "denied"
    STALE = "stale"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    id: DecisionRequestId
    workspace_id: WorkspaceId
    run_id: RunId
    task_id: TaskId | None
    kind: DecisionKind
    audience: Audience
    category: QuestionCategory | None
    gate_categories: frozenset[str]
    question_key: str | None
    question_digest: str | None
    revision: int
    payload: DecisionPayload
    asked_by_step_id: StepId | None
    binding: JsonObject
    state: DecisionState
    stale_answer: JsonValue
    deadline_at: datetime | None
    created_at: datetime
    # Domain linkage to the authoritative answer row, restored with the request by the caller.
    # It is cleared on reopen; an answer of an older revision cannot be applied or recorded.
    answer_id: DecisionAnswerId | None = None

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.revision < 1:
            problems.append("revision >= 1")
        if (self.kind is DecisionKind.QUESTION) != (self.category is not None):
            problems.append("a category is set exactly for a question")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "decision request invariants violated: " + "; ".join(problems),
                details={"decision_request_id": str(self.id), "violations": list(problems)},
            )


@dataclass(frozen=True, slots=True)
class DecisionAnswer:
    id: DecisionAnswerId
    request_id: DecisionRequestId
    answered_by: JsonObject
    value: JsonValue
    authority: AuthorityEnvelope
    answered_at: datetime


def question_key(task_key: str, q: JsonObject) -> str:
    return "qk-" + question_digest(task_key, q)[:16]


def question_digest(task_key: str, q: JsonObject) -> str:
    """sha256 hex of ``{item, kind, text, options, answer_schema}`` in canonical JSON."""
    options = q.get("options")
    listed: list[JsonObject] = (
        [cast("JsonObject", option) for option in options if isinstance(option, Mapping)]
        if isinstance(options, list)
        else []
    )
    listed.sort(key=lambda option: str(option.get("id", "")))
    text = q.get("text")
    material: JsonObject = {
        "item": task_key,
        "kind": q.get("kind"),
        "text": _SPACES.sub(" ", text).strip() if isinstance(text, str) else None,
        "options": list[JsonValue](listed),
        "answer_schema": q.get("answer_schema"),
    }
    canonical = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def answer_request(
    request: DecisionRequest,
    *,
    answered_by: JsonObject,
    actor: Actor | None,
    value: JsonValue,
    authority: AuthorityEnvelope,
    expected_revision: int,
    answer_id: DecisionAnswerId,
    now: datetime,
) -> tuple[DecisionRequest, DecisionAnswer]:
    """Record an answer: the request becomes ``answered``.

    ``INVALID_TRANSITION``: the request is not open. ``VERSION_CONFLICT``: another revision.
    ``FORBIDDEN``: an owner answer from anyone but the trusted human ``actor`` it names, or a non-owner
    answer to a request whose audience is the owner (gated, owner-only or queued questions).

    The domain keeps only these invariants. The permission ``inbox.answer`` (scope run) and the check of
    the value against the request's options and ``answer_schema`` (through ``platform.schema``) belong to
    the command ``execution.answer_decision_request`` (§7.1) that calls this function; an approval intent
    is answered by ``policy.approve_intent`` instead.
    """
    if request.state is not DecisionState.OPEN:
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            f"a {request.state} decision request takes no answer",
            details={"decision_request_id": str(request.id), "state": request.state.value},
        )
    if expected_revision != request.revision:
        raise error_for(
            ErrorCode.VERSION_CONFLICT,
            "the answer is for another revision of the question",
            details={"expected_revision": expected_revision, "revision": request.revision},
        )
    kind = answered_by.get("kind")
    if kind not in ANSWER_KINDS:
        raise error_for(
            ErrorCode.SCHEMA_INVALID, "answered_by.kind is owner, advisor, consilium, policy or reuse"
        )
    if kind == "owner":
        principal = answered_by.get("principal_id")
        if actor is None or actor.kind is not PrincipalKind.HUMAN or principal != str(actor.principal_id):
            raise error_for(
                ErrorCode.FORBIDDEN,
                "an owner answer is given only by the trusted human principal it names",
                details={
                    "reason": "not_human",
                    "principal_kind": None if actor is None else actor.kind.value,
                },
            )
    elif request.audience is Audience.OWNER:
        raise error_for(
            ErrorCode.FORBIDDEN,
            f"a {kind} answer does not decide a request for the owner",
            details={"reason": "owner_required", "answered_by": kind},
        )
    answer = DecisionAnswer(
        id=answer_id,
        request_id=request.id,
        answered_by=dict(answered_by),
        value=value,
        authority=authority,
        answered_at=now,
    )
    return dataclasses.replace(request, state=DecisionState.ANSWERED, answer_id=answer.id), answer


def apply_answer(request: DecisionRequest, answer: DecisionAnswer, *, binding: JsonObject) -> DecisionRequest:
    """``answered → applied`` when ``binding`` (the current facts) matches the request binding.

    Every key of ``BINDING_KEYS`` that the request binds must be present and equal now; the
    ``input_part_digest`` is always required. Otherwise ``answered → stale → open`` in one step:
    ``revision + 1``, the answer value moves to ``stale_answer`` and the reopened request binds the
    current facts, so the next answer is checked against the input it was given for, not the old one.
    """
    if (
        request.state is not DecisionState.ANSWERED
        or answer.request_id != request.id
        or request.answer_id != answer.id
    ):
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "only an answered request applies its own answer",
            details={"decision_request_id": str(request.id), "state": request.state.value},
        )
    if answer_is_current(request.binding, binding):
        return dataclasses.replace(request, state=DecisionState.APPLIED)
    return dataclasses.replace(
        request,
        state=DecisionState.OPEN,
        revision=request.revision + 1,
        stale_answer=answer.value,
        binding=dict(binding),
        answer_id=None,
    )


def answer_is_current(bound: Mapping[str, JsonValue], current: Mapping[str, JsonValue]) -> bool:
    digest = bound.get("input_part_digest")
    if not isinstance(digest, str) or not digest or current.get("input_part_digest") != digest:
        return False
    return all(bound[key] == current.get(key) for key in BINDING_KEYS if bound.get(key) is not None)
