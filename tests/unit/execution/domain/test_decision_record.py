"""Records of applied decisions (execution §4.23, §5.10 G27)."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.errors import SkmError
from skm.modules.execution.domain.autonomy import AuthorityEnvelope
from skm.modules.execution.domain.decision_record import (
    DecisionRecord,
    QuestionCategory,
    decision_record_to_json,
    make_decision_record,
    supersede_records,
)
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionAnswer,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.generated import documents as generated
from skm.platform.schema.registry import SchemaRegistry

URN = "urn:skm:execution:decision-record:v1"
NOW = datetime(2026, 10, 25, 12, 20, 44, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[4]
DIGEST = "sha256:" + "6a8c0e2a4c" * 6 + "6a8c"


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def uid(n: int) -> Any:
    return UUID(int=n)


def request(**changes: Any) -> DecisionRequest:
    values: dict[str, Any] = {
        "id": uid(130001),
        "workspace_id": uid(2),
        "run_id": uid(1),
        "task_id": uid(12),
        "kind": DecisionKind.QUESTION,
        "audience": Audience.ADVISOR,
        "category": QuestionCategory.BOUNDED_AMBIGUITY,
        "gate_categories": frozenset(),
        "question_key": "qk-5d2a9e0c4b7f1361",
        "question_digest": "d" * 64,
        "revision": 1,
        "payload": {"text": "Which family?", "blocking": True},
        "asked_by_step_id": None,
        "binding": {"input_part_digest": DIGEST},
        "state": DecisionState.APPLIED,
        "stale_answer": None,
        "deadline_at": None,
        "created_at": NOW,
        "answer_id": uid(140001),
    }
    values.update(changes)
    return DecisionRequest(**values)


OPTION_ANSWER: Any = object()


def answer(kind: str = "advisor", value: Any = OPTION_ANSWER) -> DecisionAnswer:
    return DecisionAnswer(
        id=uid(140001),
        request_id=uid(130001),
        answered_by={"kind": kind, "step_id": str(uid(5))},
        value={"option_id": "revoke-family"} if value is OPTION_ANSWER else value,
        authority=AuthorityEnvelope("answer", (), "high"),
        answered_at=NOW,
    )


def record(req: DecisionRequest | None = None, ans: DecisionAnswer | None = None, **changes: Any) -> Any:
    values: dict[str, Any] = {
        "question_kind": "decision",
        "record_id": uid(1001),
        "project_id": uid(3),
        "rationale": "The recorded decision settles the question.",
        "evidence_refs": ("decision:D1", "material:material/storage-design#rotation"),
        "assumptions": ("P2.2 implements single-flight refresh as planned.",),
        "selected_option": "revoke-family",
        "now": NOW,
    }
    values.update(changes)
    return make_decision_record(req or request(), ans or answer(), **values)


@pytest.mark.parametrize("kind", ["owner", "advisor", "consilium"])
def test_a_record_for_owner_advisor_and_consilium(kind: str) -> None:
    audience = Audience.OWNER if kind == "owner" else Audience.ADVISOR
    made = record(request(audience=audience), answer(kind))
    assert isinstance(made, DecisionRecord)
    assert (made.authority, made.status) == (kind, "applied")
    assert made.requires_owner is (kind == "owner")
    assert made.question_input_digest == DIGEST


@pytest.mark.parametrize("kind", ["policy", "reuse"])
def test_no_record_for_policy_defaults_or_reuse(kind: str) -> None:
    assert record(ans=answer(kind)) is None


def test_records_only_for_decision_clarification_and_applied_advice() -> None:
    assert record(question_kind="clarification") is not None
    assert record(question_kind="advice") is not None
    assert record(question_kind="approval") is None
    assert record(question_kind="credential") is None


def test_fields_come_from_the_advice_and_the_document_validates() -> None:
    made = record()
    assert made.evidence_refs == ("decision:D1", "material:material/storage-design#rotation")
    assert made.assumptions == ("P2.2 implements single-flight refresh as planned.",)
    assert (made.selected_option, made.value) == ("revoke-family", {"option_id": "revoke-family"})
    document = decision_record_to_json(made)
    assert registry().validate(URN, document) == ()
    example = json.loads(
        (ROOT / "tests/fixtures/corpus/examples/execution/examples/decision-record.json").read_text()
    )
    assert set(document) == set(example)
    assert registry().validate(URN, example) == ()


def round_trip(made: DecisionRecord) -> dict[str, Any]:
    document = decision_record_to_json(made)
    assert registry().validate(URN, document) == ()
    assert generated.decision_record_to_json(generated.decision_record_from_json(document)) == document
    assert json.loads(json.dumps(document)) == document
    return document


@pytest.mark.parametrize(
    ("selected_option", "value"),
    [
        ("revoke-family", {"option_id": "revoke-family"}),  # an answer by option
        (None, {"text": "use the database clock"}),  # a free-text answer has no option
        (None, "use the database clock"),
        (None, None),  # a JSON null answer is kept, not dropped
        (None, [1, 2.5, True, None, {"nested": ["deep", {"x": None}]}]),
        ("revoke-family", {"option_id": "revoke-family", "text": "and rotate weekly", "extra": {"k": 1}}),
        ("other", {"option_id": "revoke-family"}),  # §4.23 asks no agreement; both are kept as authored
        ("not-offered", 7),  # nor that the option was offered: the request is the authority for options
    ],
)
def test_option_and_free_form_answers_round_trip_as_authored(selected_option: str | None, value: Any) -> None:
    made = record(ans=answer(value=value), selected_option=selected_option)
    assert (made.selected_option, made.value) == (selected_option, value)
    document = round_trip(made)
    assert (document["selected_option"], document["value"]) == (selected_option, value)
    assert (made.authority, made.requires_owner) == ("advisor", False)


def test_the_answer_value_reaches_the_record_unchanged() -> None:
    value = {"text": "use the database clock", "unknown_key": [None, {"a": 1}]}
    made = record(ans=answer(value=value), selected_option=None)
    assert (made.selected_option, made.value) == (None, value)
    assert round_trip(made)["value"] == value


def test_the_schema_keeps_its_closed_shape_and_required_members() -> None:
    document = decision_record_to_json(record())
    assert registry().validate(URN, {**document, "unknown": 1}) != ()
    for member in ("selected_option", "value"):
        assert registry().validate(URN, {k: v for k, v in document.items() if k != member}) != ()
    assert registry().validate(URN, {**document, "selected_option": 3}) != ()
    assert registry().validate(URN, {**document, "selected_option": {"option_id": "x"}}) != ()
    with pytest.raises(ValueError, match="expected str; expected null"):
        generated.decision_record_from_json({**document, "selected_option": 3})


def test_a_new_answer_to_the_same_key_supersedes_the_applied_record() -> None:
    first = record()
    unrelated = record(request(question_key="qk-0000000000000001"), record_id=uid(1002))
    other_project = record(record_id=uid(1003), project_id=uid(4))
    second = record(record_id=uid(1004))
    updated = supersede_records((first, unrelated, other_project, second), second)
    assert [item.status for item in updated] == ["superseded", "applied", "applied", "applied"]
    assert updated[0] == dataclasses.replace(first, status="superseded")


@pytest.mark.parametrize(
    "state", [state for state in DecisionState if state is not DecisionState.APPLIED], ids=str
)
def test_only_an_applied_request_writes_a_record(state: DecisionState) -> None:
    with pytest.raises(SkmError) as caught:
        record(request(state=state))
    assert caught.value.code.value == "INVALID_TRANSITION"


def test_only_the_answer_of_the_request_writes_its_record() -> None:
    foreign = dataclasses.replace(answer(), request_id=uid(130002))
    with pytest.raises(SkmError) as caught:
        record(ans=foreign)
    assert caught.value.code.value == "INVALID_TRANSITION"
    # policy and reuse answers are refused the same way when they are not the applied answer
    with pytest.raises(SkmError):
        record(request(state=DecisionState.ANSWERED), answer("reuse"))


@pytest.mark.parametrize("answer_id", [None, uid(140002)])
def test_record_needs_the_exact_applied_answer_even_with_the_same_request_id(answer_id: Any) -> None:
    with pytest.raises(SkmError) as caught:
        record(request(answer_id=answer_id))
    assert caught.value.code.value == "INVALID_TRANSITION"


def test_advice_without_a_categorized_question_identity_fails_closed() -> None:
    # No identity or category is invented for an escalation about checks/findings.
    req = request(kind=DecisionKind.ESCALATION, category=None, question_key=None, question_digest=None)
    with pytest.raises(SkmError) as caught:
        record(req, question_kind="advice")
    assert caught.value.code.value == "SCHEMA_INVALID"


def test_record_invariants() -> None:
    with pytest.raises(SkmError):
        dataclasses.replace(record(), requires_owner=True)  # an advisor never takes an owner decision
    with pytest.raises(SkmError):
        dataclasses.replace(record(), rationale="x" * 2001)
    with pytest.raises(SkmError):
        dataclasses.replace(record(), question_key="question-1")
    assert record(rationale="  ").rationale == "(no rationale was given)"
    with pytest.raises(SkmError):
        record(request(binding={}))
    with pytest.raises(SkmError):
        record(request(task_id=None))
