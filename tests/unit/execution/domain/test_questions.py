"""Question identity, audience, answer authority and answer freshness (execution §4.16, §5.10)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from functools import cache
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import PrincipalId
from skm.modules.execution.domain.autonomy import (
    AudienceRoute,
    AuthorityEnvelope,
    Denied,
    PolicyDefault,
    ReusableDecision,
    Reused,
    decide_audience,
)
from skm.modules.execution.domain.decision_record import QuestionCategory
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
    answer_request,
    apply_answer,
    question_digest,
    question_key,
)
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
HUMAN = Actor(PrincipalId(UUID(int=900)), PrincipalKind.HUMAN, "Ann")
OWNER = {"kind": "owner", "principal_id": str(HUMAN.principal_id)}
ADVISOR = {"kind": "advisor", "step_id": str(UUID(int=77))}
ENVELOPE = AuthorityEnvelope("answer", (), None)
QUESTION: dict[str, Any] = {
    "kind": "decision",
    "text": "Revoke  the whole\n token family?",
    "options": [{"id": "b", "label": "Only this token"}, {"id": "a", "label": "Whole family"}],
    "answer_schema": None,
    "default": "a",
    "blocking": True,
}


def uid(n: int) -> Any:
    return UUID(int=n)


def test_question_key_and_digest_are_stable() -> None:
    digest = question_digest("P2.2", QUESTION)
    assert len(digest) == 64
    assert question_key("P2.2", QUESTION) == "qk-" + digest[:16]
    reordered = {
        **QUESTION,
        "options": list(reversed(QUESTION["options"])),
        "text": "Revoke the whole token family?",
    }
    assert question_digest("P2.2", reordered) == digest
    assert question_digest("P2.2", {**QUESTION, "default": "b", "blocking": False}) == digest


@pytest.mark.parametrize(
    "change",
    [
        {"options": [{"id": "a", "label": "Whole family"}]},
        {
            "options": [
                {"id": "a", "label": "Whole family (all devices)"},
                {"id": "b", "label": "Only this token"},
            ]
        },
        {"answer_schema": {"type": "string"}},
        {"kind": "clarification"},
        {"text": "Revoke one token?"},
    ],
)
def test_question_digest_is_sensitive_to_options_schema_kind_and_text(change: dict[str, Any]) -> None:
    assert question_digest("P2.2", {**QUESTION, **change}) != question_digest("P2.2", QUESTION)
    assert question_digest("P2.3", QUESTION) != question_digest("P2.2", QUESTION)


def audience(**changes: Any) -> Any:
    values: dict[str, Any] = {
        "q": QUESTION,
        "category": QuestionCategory.BOUNDED_AMBIGUITY,
        "gates": frozenset(),
        "policy": {},
        "reusable": None,
        "advisor_rounds_used": 0,
        "questions_opened": 0,
        "task_key": "P2.2",
    }
    values.update(changes)
    return decide_audience(**values)


def reusable(question: dict[str, Any] = QUESTION, **changes: Any) -> ReusableDecision:
    values: dict[str, Any] = {
        "question_key": question_key("P2.2", question),
        "question_digest": question_digest("P2.2", question),
        "value": {"option_id": "a"},
        "selected_option": "a",
    }
    values.update(changes)
    return ReusableDecision(**values)


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def validate_answer(schema: dict[str, Any], value: Any) -> bool:
    return registry().is_valid_schema(schema) and not SchemaValidator(schema, registry().registry).issues(
        value
    )


def test_rules_in_order() -> None:
    assert audience(category=QuestionCategory.AUTHORITY_REQUIRED, reusable=reusable()) == AudienceRoute(
        Audience.OWNER, "QUESTION_OWNER_ONLY"
    )
    assert audience(gates=frozenset({"security"}), reusable=reusable()) == AudienceRoute(
        Audience.OWNER, "QUESTION_GATED"
    )
    assert audience(questions_opened=5, reusable=reusable()) == AudienceRoute(
        Audience.OWNER, "QUESTION_LIMIT"
    )
    assert audience(questions_opened=1, policy={"max_questions_per_task": 1}).code == "QUESTION_LIMIT"
    assert audience(reusable=reusable()) == Reused({"option_id": "a"}, "a")
    assert audience(policy={"question_policy": "deny"}) == Denied("QUESTION_DENIED")
    assert audience(policy={"question_policy": "queue"}) == AudienceRoute(Audience.OWNER, "QUESTION_QUEUED")
    assert audience(policy={"question_policy": "defaults"}) == PolicyDefault("a")
    assert audience(category=QuestionCategory.ARCHITECTURAL).code == "QUESTION_CATEGORY_OWNER"
    assert audience() == AudienceRoute(Audience.ADVISOR, None)
    assert audience(advisor_rounds_used=2) == AudienceRoute(Audience.OWNER, "QUESTION_NO_ADVISOR")
    assert audience(policy={"advisor_enabled": False}).audience is Audience.OWNER
    panel = {"consilium": {"members": ["a", "b/m"], "trigger": "always"}}
    assert audience(policy=panel) == AudienceRoute(Audience.CONSILIUM, None)
    assert (
        audience(policy={"consilium": {"members": ["a"], "trigger": "always"}}).audience is Audience.ADVISOR
    )
    assert audience(policy={"consilium": {"members": ["a", "b"], "trigger": "low_confidence"}}).audience is (
        Audience.ADVISOR
    )


def test_policy_default_is_used_once() -> None:
    assert audience(policy={"question_policy": "defaults"}, answered_by_policy_before=True) == AudienceRoute(
        Audience.OWNER, "QUESTION_DEFAULT_USED"
    )
    no_default = {**QUESTION, "default": None}
    assert audience(q=no_default, policy={"question_policy": "defaults"}).audience is Audience.OWNER


def test_reuse_needs_key_and_digest_a_recordable_kind_and_a_fitting_value() -> None:
    assert isinstance(audience(reusable=reusable()), Reused)
    assert not isinstance(audience(reusable=reusable(question_digest="0" * 64)), Reused)
    assert not isinstance(audience(reusable=reusable(question_key="qk-0000000000000000")), Reused)
    approval = {**QUESTION, "kind": "approval"}
    assert not isinstance(audience(q=approval, reusable=reusable(approval)), Reused)
    assert not isinstance(audience(reusable=reusable(value="c", selected_option=None)), Reused)
    assert isinstance(audience(reusable=reusable(value="a: Whole family", selected_option=None)), Reused)
    schema_q = {**QUESTION, "options": [], "answer_schema": {"type": "integer"}}
    assert not isinstance(audience(q=schema_q, reusable=reusable(schema_q, value=3)), Reused)
    assert not isinstance(audience(q=schema_q, reusable=reusable(schema_q, value=3, schema_ok=True)), Reused)
    assert isinstance(
        audience(q=schema_q, reusable=reusable(schema_q, value=3), validate_answer=validate_answer), Reused
    )


def test_a_reused_value_satisfies_the_options_and_the_schema_of_the_question() -> None:
    # a recorded option that the value does not name, or that disagrees with it, is no fitting answer
    assert not isinstance(audience(reusable=reusable(value={"note": "x"}, selected_option="a")), Reused)
    assert not isinstance(audience(reusable=reusable(value={"option_id": "b"}, selected_option="a")), Reused)
    assert not isinstance(audience(reusable=reusable(value="a", selected_option="z")), Reused)
    assert isinstance(audience(reusable=reusable(value="b", selected_option="b")), Reused)
    # options and an answer schema: both must hold
    both = {**QUESTION, "answer_schema": {"type": "object"}}
    assert not isinstance(audience(q=both, reusable=reusable(both)), Reused)
    assert not isinstance(audience(q=both, reusable=reusable(both, schema_ok=True)), Reused)
    assert isinstance(audience(q=both, reusable=reusable(both), validate_answer=validate_answer), Reused)
    assert not isinstance(
        audience(q=both, reusable=reusable(both, value={"option_id": "c"}), validate_answer=validate_answer),
        Reused,
    )
    # The actual value must fit the actual schema, even when it names an offered option.
    assert not isinstance(
        audience(q=both, reusable=reusable(both, value="a", schema_ok=True), validate_answer=validate_answer),
        Reused,
    )


@pytest.mark.parametrize(
    ("schema", "value"),
    [
        ({"type": "integer"}, "3"),
        ({"type": "integer"}, True),
        ({"type": "string", "enum": ["a"]}, "b"),
        ({"type": "string", "minLength": 2}, "a"),
        ({"type": "not-a-type"}, "a"),
        ({"$ref": "urn:missing:schema:v1"}, "a"),
    ],
)
def test_reuse_rejects_schema_invalid_values_and_unresolved_schemas(
    schema: dict[str, Any], value: Any
) -> None:
    q = {**QUESTION, "options": [], "answer_schema": schema}
    assert not isinstance(
        audience(
            q=q,
            reusable=reusable(q, value=value, selected_option=None, schema_ok=True),
            validate_answer=validate_answer,
        ),
        Reused,
    )


def test_an_offered_option_must_also_satisfy_the_schema() -> None:
    q = {**QUESTION, "answer_schema": {"type": "object", "properties": {"option_id": {"const": "a"}}}}
    assert isinstance(audience(q=q, reusable=reusable(q), validate_answer=validate_answer), Reused)
    assert not isinstance(
        audience(
            q=q,
            reusable=reusable(q, value={"option_id": "b"}, selected_option="b", schema_ok=True),
            validate_answer=validate_answer,
        ),
        Reused,
    )


# --- answers ----------------------------------------------------------------------------------------------


def request(**changes: Any) -> DecisionRequest:
    values: dict[str, Any] = {
        "id": uid(130001),
        "workspace_id": uid(2),
        "run_id": uid(1),
        "task_id": uid(100),
        "kind": DecisionKind.QUESTION,
        "audience": Audience.OWNER,
        "category": QuestionCategory.ARCHITECTURAL,
        "gate_categories": frozenset(),
        "question_key": question_key("P2.2", QUESTION),
        "question_digest": question_digest("P2.2", QUESTION),
        "revision": 1,
        "payload": {"text": QUESTION["text"], "options": QUESTION["options"], "blocking": True},
        "asked_by_step_id": uid(55),
        "binding": {
            "attempt_id": str(uid(200)),
            "output_id": "out-a",
            "input_part_digest": "sha256:" + "a" * 64,
        },
        "state": DecisionState.OPEN,
        "stale_answer": None,
        "deadline_at": None,
        "created_at": NOW,
    }
    values.update(changes)
    return DecisionRequest(**values)


def answer(
    req: DecisionRequest, answered_by: dict[str, Any] = OWNER, actor: Actor | None = HUMAN, **changes: Any
) -> Any:
    values: dict[str, Any] = {
        "answered_by": answered_by,
        "actor": actor,
        "value": {"option_id": "a"},
        "authority": ENVELOPE,
        "expected_revision": req.revision,
        "answer_id": uid(140001),
        "now": NOW,
    }
    values.update(changes)
    return answer_request(req, **values)


def test_owner_answer_needs_the_trusted_human_it_names() -> None:
    answered, recorded = answer(request())
    assert answered.state is DecisionState.ANSWERED
    assert recorded.value == {"option_id": "a"}
    for actor in (
        Actor(uid(900), PrincipalKind.SERVICE, "owner"),
        Actor(uid(900), PrincipalKind.WORKER, "owner"),
        Actor(uid(901), PrincipalKind.HUMAN, "Bob"),
        None,
    ):
        with pytest.raises(SkmError) as caught:
            answer(request(), actor=actor)
        assert caught.value.code is ErrorCode.FORBIDDEN


@pytest.mark.parametrize("kind", ["advisor", "consilium", "policy", "reuse"])
def test_other_answer_paths_never_decide_an_owner_request(kind: str) -> None:
    with pytest.raises(SkmError) as caught:
        answer(request(), {"kind": kind, "step_id": "s"}, None)
    assert caught.value.code is ErrorCode.FORBIDDEN
    answered, _ = answer(
        request(audience=Audience.ADVISOR, category=QuestionCategory.CROSS_MODULE), {"kind": kind}, None
    )
    assert answered.state is DecisionState.ANSWERED


def test_answer_needs_an_open_request_of_the_expected_revision() -> None:
    with pytest.raises(SkmError) as caught:
        answer(request(), expected_revision=2)
    assert caught.value.code is ErrorCode.VERSION_CONFLICT
    with pytest.raises(SkmError) as caught:
        answer(request(state=DecisionState.EXPIRED))
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    with pytest.raises(SkmError) as caught:
        answer(request(), {"kind": "god"}, None)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_answer_applies_only_to_the_same_input_and_output() -> None:
    answered, recorded = answer(request())
    current = dict(answered.binding)
    assert apply_answer(answered, recorded, binding=current).state is DecisionState.APPLIED
    for change in (
        {"input_part_digest": "sha256:" + "b" * 64},
        {"output_id": "out-b"},
        {"attempt_id": str(uid(201))},
        {"input_part_digest": None},
    ):
        stale = apply_answer(answered, recorded, binding={**current, **change})
        assert (stale.state, stale.revision, stale.stale_answer) == (
            DecisionState.OPEN,
            2,
            {"option_id": "a"},
        ), change
    unbound = dataclasses.replace(answered, binding={"attempt_id": str(uid(200))})
    assert apply_answer(unbound, recorded, binding={"attempt_id": str(uid(200))}).state is DecisionState.OPEN
    with pytest.raises(SkmError):
        apply_answer(request(), recorded, binding=current)


def test_the_stale_question_is_asked_again_with_a_new_revision() -> None:
    answered, recorded = answer(request())
    stale = apply_answer(answered, recorded, binding={**answered.binding, "output_id": "out-b"})
    with pytest.raises(SkmError) as caught:
        answer(stale, expected_revision=1)
    assert caught.value.code is ErrorCode.VERSION_CONFLICT
    again, _ = answer(stale, expected_revision=2)
    assert (again.state, again.revision) == (DecisionState.ANSWERED, 2)


def test_the_reopened_question_binds_the_current_facts() -> None:
    answered, recorded = answer(request())
    old = dict(answered.binding)
    current = {**old, "output_id": "out-b", "input_part_digest": "sha256:" + "b" * 64}
    reopened = apply_answer(answered, recorded, binding=current)
    assert reopened.binding == current
    # the new answer is given for the current facts: it applies to them and goes stale on the old ones
    again, second = answer(reopened, expected_revision=2)
    assert apply_answer(again, second, binding=current).state is DecisionState.APPLIED
    back = apply_answer(again, second, binding=old)
    assert (back.state, back.revision, back.binding) == (DecisionState.OPEN, 3, old)


def test_an_old_answer_cannot_be_applied_to_a_reanswered_revision() -> None:
    first, old_answer = answer(request())
    current = {**first.binding, "output_id": "out-b"}
    reopened = apply_answer(first, old_answer, binding=current)
    assert reopened.answer_id is None
    second, new_answer = answer(reopened, answer_id=uid(140002), value={"option_id": "b"})
    with pytest.raises(SkmError) as caught:
        apply_answer(second, old_answer, binding=current)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    assert apply_answer(second, new_answer, binding=current).state is DecisionState.APPLIED
