"""Question categories and records of applied decisions (execution §4.23, §5.10; G27).

``classify_question`` is deterministic from the question's autonomy facts (the model's self-assessed
confidence is not an input): the first matching row of the §5.10 table wins. An absent fact counts as its
most cautious value, so a question without facts goes to the owner as ``architectural``.

A ``DecisionRecord`` is written for an applied answer to a ``decision``/``clarification`` question, and for
applied advice on checks or findings, when an owner, advisor or consilium decided; policy defaults and
reused decisions write none. A new answer to the same ``question_key`` supersedes the applied record.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.decision_request import DecisionState

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import ProjectId, RunId, TaskId, WorkspaceId
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.decision_request import DecisionAnswer, DecisionRequest
    from skm.modules.execution.domain.ids import DecisionRecordId, DecisionRequestId

__all__ = [
    "RATIONALE_MAX_CHARS",
    "RECORDED_KINDS",
    "SCHEMA_URN",
    "DecisionRecord",
    "QuestionCategory",
    "classify_question",
    "decision_record_to_json",
    "make_decision_record",
    "supersede_records",
]

SCHEMA_URN: Final = "urn:skm:execution:decision-record:v1"
RATIONALE_MAX_CHARS: Final = 2000
# question kinds whose applied answer is recorded; "advice" is applied advice on checks or findings
RECORDED_KINDS: Final = frozenset({"decision", "clarification", "advice"})
_AUTHORITIES: Final = frozenset({"owner", "advisor", "consilium"})
_QUESTION_KEY: Final = re.compile(r"qk-[0-9a-f]{16}")
_DIGEST: Final = re.compile(r"sha256:[0-9a-f]{64}")


class QuestionCategory(StrEnum):
    AUTHORITY_REQUIRED = "authority_required"
    ARCHITECTURAL = "architectural"
    EXTERNAL_FACT = "external_fact"
    CROSS_MODULE = "cross_module"
    BOUNDED_AMBIGUITY = "bounded_ambiguity"
    LOCAL_REVERSIBLE = "local_reversible"


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    id: DecisionRecordId
    workspace_id: WorkspaceId
    project_id: ProjectId
    run_id: RunId
    task_id: TaskId
    request_id: DecisionRequestId
    category: QuestionCategory
    gate_categories: tuple[str, ...]
    authority: Literal["owner", "advisor", "consilium"]
    status: Literal["applied", "superseded"]
    selected_option: str | None
    value: JsonValue
    rationale: str
    evidence_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    requires_owner: bool
    question_key: str
    question_input_digest: str
    created_at: datetime

    def __post_init__(self) -> None:
        problems: list[str] = []
        if self.authority not in _AUTHORITIES:
            problems.append("authority is owner, advisor or consilium")
        if self.requires_owner and self.authority != "owner":
            problems.append("a decision that requires the owner was taken by the owner")
        if self.status not in {"applied", "superseded"}:
            problems.append("status is applied or superseded")
        if not _QUESTION_KEY.fullmatch(self.question_key):
            problems.append("question_key is qk-<16 hex>")
        if not _DIGEST.fullmatch(self.question_input_digest):
            problems.append("question_input_digest is sha256:<64 hex>")
        if not self.rationale.strip() or len(self.rationale) > RATIONALE_MAX_CHARS:
            problems.append(f"rationale is 1..{RATIONALE_MAX_CHARS} characters")
        if problems:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "decision record invariants violated: " + "; ".join(problems),
                details={"decision_record_id": str(self.id), "violations": list(problems)},
            )


def classify_question(
    facts: JsonObject, kind: str, changed_paths: Sequence[str], write_scope: Sequence[str], config: JsonObject
) -> QuestionCategory:
    """The first row of §5.10 that matches; paths and config feed the gate categories, not this table."""
    del changed_paths, write_scope, config  # gate categories: autonomy.gate_categories
    reversibility = _fact(facts, "reversibility", "irreversible")
    scope_impact = _fact(facts, "scope_impact", "plan")
    contract_change = _fact(facts, "contract_change", "public")
    if kind in {"approval", "credential"} or facts.get("needs_authority") is True:
        return QuestionCategory.AUTHORITY_REQUIRED
    if contract_change == "public" or scope_impact == "plan" or reversibility == "irreversible":
        return QuestionCategory.ARCHITECTURAL
    if facts.get("needs_external_fact") is True:
        return QuestionCategory.EXTERNAL_FACT
    if scope_impact == "cross_module" or contract_change == "internal":
        return QuestionCategory.CROSS_MODULE
    if scope_impact == "task" or reversibility == "costly":
        return QuestionCategory.BOUNDED_AMBIGUITY
    return QuestionCategory.LOCAL_REVERSIBLE


def make_decision_record(  # noqa: PLR0913 -- the record copies its request, answer and advice
    request: DecisionRequest,
    answer: DecisionAnswer,
    *,
    question_kind: str,
    record_id: DecisionRecordId,
    project_id: ProjectId,
    rationale: str,
    evidence_refs: Sequence[str] = (),
    assumptions: Sequence[str] = (),
    selected_option: str | None = None,
    now: datetime,
) -> DecisionRecord | None:
    """The record of an applied answer, or ``None`` when §5.10 writes none (policy, reuse, other kinds).

    ``INVALID_TRANSITION`` unless ``request`` is ``applied`` and ``answer`` is its own: an answered,
    stale, reopened or foreign answer never becomes a decision record.
    """
    if (
        request.state is not DecisionState.APPLIED
        or answer.request_id != request.id
        or request.answer_id != answer.id
    ):
        raise error_for(
            ErrorCode.INVALID_TRANSITION,
            "a decision record is written only for the applied answer of its request",
            details={
                "decision_request_id": str(request.id),
                "state": request.state.value,
                "answer_request_id": str(answer.request_id),
            },
        )
    authority = answer.answered_by.get("kind")
    if question_kind not in RECORDED_KINDS or authority not in _AUTHORITIES:
        return None
    if request.task_id is None or request.category is None:
        raise error_for(
            ErrorCode.SCHEMA_INVALID,
            "a decision record belongs to a task question with a category",
            details={"decision_request_id": str(request.id)},
        )
    if request.question_key is None:
        raise error_for(
            ErrorCode.SCHEMA_INVALID,
            "a recorded question has a question_key",
            details={"decision_request_id": str(request.id)},
        )
    digest = request.binding.get("input_part_digest")
    text = rationale.strip() or "(no rationale was given)"
    return DecisionRecord(
        id=record_id,
        workspace_id=request.workspace_id,
        project_id=project_id,
        run_id=request.run_id,
        task_id=request.task_id,
        request_id=request.id,
        category=request.category,
        gate_categories=tuple(sorted(request.gate_categories)),
        authority=cast("Literal['owner', 'advisor', 'consilium']", authority),
        status="applied",
        selected_option=selected_option,
        value=answer.value,
        rationale=text[:RATIONALE_MAX_CHARS],
        evidence_refs=tuple(evidence_refs),
        assumptions=tuple(assumptions),
        requires_owner=request.audience.value == "owner",
        question_key=request.question_key,
        question_input_digest=digest if isinstance(digest, str) else "",
        created_at=now,
    )


def supersede_records(records: Sequence[DecisionRecord], new: DecisionRecord) -> tuple[DecisionRecord, ...]:
    """Applied records of the same project and ``question_key`` become ``superseded``; others stay."""
    return tuple(
        dataclasses.replace(record, status="superseded")
        if record.id != new.id
        and record.status == "applied"
        and record.project_id == new.project_id
        and record.question_key == new.question_key
        else record
        for record in records
    )


def decision_record_to_json(record: DecisionRecord) -> JsonObject:
    """The ``urn:skm:execution:decision-record:v1`` document.

    ``selected_option`` (an option id or ``None``) and ``value`` (any JSON) are exported as authored, as
    §4.23 declares them: a free-text answer keeps ``None``, and no option is derived from the value.
    """
    return {
        "schema": SCHEMA_URN,
        "id": str(record.id),
        "workspace_id": str(record.workspace_id),
        "project_id": str(record.project_id),
        "run_id": str(record.run_id),
        "task_id": str(record.task_id),
        "request_id": str(record.request_id),
        "category": record.category.value,
        "gate_categories": list(record.gate_categories),
        "authority": record.authority,
        "status": record.status,
        "selected_option": record.selected_option,
        "value": record.value,
        "rationale": record.rationale,
        "evidence_refs": list(record.evidence_refs),
        "assumptions": list(record.assumptions),
        "requires_owner": record.requires_owner,
        "question_key": record.question_key,
        "question_input_digest": record.question_input_digest,
        "created_at": record.created_at.isoformat().replace("+00:00", "Z"),
    }


def _fact(facts: Mapping[str, JsonValue], name: str, cautious: str) -> str:
    value = facts.get(name)
    return value if isinstance(value, str) and value else cautious
