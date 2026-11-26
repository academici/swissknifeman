"""Anonymous majority aggregation and non-weakenable advisor gates."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.autonomy import AuthorityEnvelope, effective_human_gate
from skm.modules.execution.domain.decision_record import make_decision_record
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionState,
    answer_request,
    apply_answer,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from skm.kernel.ids import ProjectId
    from skm.modules.execution.domain.contracts import ExecutionPolicy, Vote
    from skm.modules.execution.domain.decision_record import DecisionRecord
    from skm.modules.execution.domain.decision_request import DecisionAnswer, DecisionRequest
    from skm.modules.execution.domain.ids import DecisionAnswerId, DecisionRecordId


def _object(value: JsonValue) -> JsonObject:
    """A nested advice object; anything else reads as an empty one, which never satisfies a gate."""
    return value if isinstance(value, dict) else {}


def _list(value: JsonValue) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def held(advice: JsonObject, policy: ExecutionPolicy) -> bool:
    gates = effective_human_gate(policy.get("human_gate"))
    computed = policy.get("gate_categories", [])
    confidence = {"low": 0, "medium": 1, "high": 2}
    recommendation = advice.get("recommendation")
    options = policy.get("options")
    return (
        advice.get("needs_owner") is not False
        or str(advice.get("category")) in gates
        or (isinstance(computed, list) and bool(set(map(str, computed)) & gates))
        or confidence.get(str(advice.get("confidence")), -1)
        < max(1, confidence.get(str(policy.get("min_confidence", "medium")), 2))
        or not isinstance(recommendation, dict)
        or (not str(recommendation.get("text", "")).strip() and not options)
        or (isinstance(options, list) and bool(options) and recommendation.get("option_id") not in options)
    )


def _key(vote: JsonObject, options: bool) -> tuple[str, str]:
    recommendation = _object(vote.get("recommendation"))
    return (
        str(recommendation.get("option_id", "")),
        "" if options else " ".join(str(recommendation.get("text", "")).casefold().split()),
    )


def aggregate(votes: Sequence[Vote], policy: ExecutionPolicy) -> JsonObject:
    if policy.get("aggregation", "majority") != "majority":
        raise ValueError("only majority aggregation is supported")
    if not votes:
        return {"kind": "split", "held": True, "reason_code": "ADVISOR_PANEL_FAILED", "variants": []}
    if len(votes) == 1:
        return {"kind": "single", "held": held(votes[0], policy), "advice": votes[0]}
    keys = [_key(v, bool(policy.get("options"))) for v in votes]
    winner, count = Counter(keys).most_common(1)[0]
    supporters = [v for v, key in zip(votes, keys, strict=True) if key == winner]
    if count * 2 <= len(votes) or any(held(v, policy) for v in supporters):
        return {"kind": "split", "held": True, "variants": list(votes)}
    result: JsonObject = {
        "kind": "agreement",
        "held": False,
        "advice": supporters[0],
        "variants": list(votes),
    }
    if count != len(votes):
        minority = next(i for i, key in enumerate(keys) if key != winner)
        result.update(kind="majority", minority_first=minority, held=True)
        critic = policy.get("critic")
        if isinstance(critic, dict):
            if (
                _key(critic, bool(policy.get("options"))) == winner
                and not held(critic, policy)
                and critic.get("sources")
            ):
                result.update(kind="agreement", held=False)
            else:
                result.update(kind="split")
        elif "critic" in policy:
            result.update(kind="split")
    return result


@dataclass(frozen=True, slots=True)
class AppliedAdvice:
    """Values to persist together with advance in the owning application transaction."""

    request: DecisionRequest
    answer: DecisionAnswer | None
    record: DecisionRecord | None
    held: bool


def apply_advice(  # noqa: PLR0913 -- request, frozen policy and caller-allocated record identities
    request: DecisionRequest,
    advice: JsonObject,
    policy: ExecutionPolicy,
    *,
    binding: JsonObject,
    answer_id: DecisionAnswerId,
    record_id: DecisionRecordId,
    project_id: ProjectId,
    now: datetime,
    panel: bool = False,
) -> AppliedAdvice:
    """Gates and stale input are checked before a recommendation becomes an applied record."""
    if request.audience is Audience.CONSILIUM:
        votes = policy.get("votes")
        if (
            not panel
            or not isinstance(votes, list)
            or len(votes) < 2
            or not all(isinstance(v, dict) for v in votes)
        ):
            return AppliedAdvice(request, None, None, True)
        consensus = aggregate(cast("list[JsonObject]", votes), policy)
        if consensus.get("held") is not False or consensus.get("advice") != advice:
            return AppliedAdvice(request, None, None, True)
    effective: ExecutionPolicy = dict(policy)
    computed = policy.get("gate_categories", [])
    effective["gate_categories"] = cast(
        "JsonValue",
        sorted(
            request.gate_categories | frozenset(map(str, computed))
            if isinstance(computed, list)
            else request.gate_categories
        ),
    )
    options = request.payload.get("options")
    if isinstance(options, list) and options:
        effective["options"] = [str(o.get("id")) if isinstance(o, dict) else str(o) for o in options]
    if request.audience is Audience.OWNER or held(advice, effective):
        return AppliedAdvice(request, None, None, True)
    if request.deadline_at is not None and now >= request.deadline_at:
        return AppliedAdvice(request, None, None, True)
    recommendation = advice["recommendation"]
    if not isinstance(recommendation, dict):  # held() already refused it; keeps the type explicit
        return AppliedAdvice(request, None, None, True)
    kind = "consilium" if panel else "advisor"
    answered, answer = answer_request(
        request,
        answered_by={"kind": kind},
        actor=None,
        value=recommendation,
        authority=AuthorityEnvelope(
            kind, tuple(sorted(request.gate_categories)), str(advice.get("confidence"))
        ),
        expected_revision=request.revision,
        answer_id=answer_id,
        now=now,
    )
    applied = apply_answer(answered, answer, binding=binding)
    if applied.state is not DecisionState.APPLIED:
        return AppliedAdvice(applied, answer, None, True)
    refs = tuple(
        str(source.get("kind", "source")) + ":" + str(source.get("ref", ""))
        for source in _list(advice.get("sources"))
        if isinstance(source, dict)
    )
    option = recommendation.get("option_id")
    record = make_decision_record(
        applied,
        answer,
        question_kind=str(request.payload.get("kind", "decision")),
        record_id=record_id,
        project_id=project_id,
        rationale=str(advice.get("rationale", "")),
        evidence_refs=refs,
        assumptions=tuple(str(item) for item in _list(advice.get("assumptions"))),
        selected_option=option if isinstance(option, str) else None,
        now=now,
    )
    return AppliedAdvice(applied, answer, record, False)
