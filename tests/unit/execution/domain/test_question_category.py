"""Question category, gate categories and audience narrowing (execution §5.10 S-11)."""

from __future__ import annotations

from typing import Any

import pytest

from skm.modules.execution.domain.autonomy import (
    DEFAULT_HUMAN_GATE,
    AudienceRoute,
    decide_audience,
    effective_category_audience,
    effective_human_gate,
    gate_categories,
)
from skm.modules.execution.domain.decision_record import QuestionCategory, classify_question
from skm.modules.execution.domain.decision_request import Audience

LOCAL: dict[str, Any] = {
    "reversibility": "reversible",
    "scope_impact": "local",
    "contract_change": "none",
    "cost_class": "low",
    "needs_external_fact": False,
    "needs_authority": False,
}


def classify(kind: str = "decision", **facts: Any) -> QuestionCategory:
    return classify_question({**LOCAL, **facts}, kind, ["src/app/x.py"], ["src/app/**"], {})


ROWS: list[tuple[str, dict[str, Any], QuestionCategory]] = [
    ("approval", {}, QuestionCategory.AUTHORITY_REQUIRED),
    ("credential", {}, QuestionCategory.AUTHORITY_REQUIRED),
    ("decision", {"needs_authority": True}, QuestionCategory.AUTHORITY_REQUIRED),
    ("decision", {"contract_change": "public"}, QuestionCategory.ARCHITECTURAL),
    ("decision", {"scope_impact": "plan"}, QuestionCategory.ARCHITECTURAL),
    ("decision", {"reversibility": "irreversible"}, QuestionCategory.ARCHITECTURAL),
    ("clarification", {"needs_external_fact": True}, QuestionCategory.EXTERNAL_FACT),
    ("decision", {"scope_impact": "cross_module"}, QuestionCategory.CROSS_MODULE),
    ("decision", {"contract_change": "internal"}, QuestionCategory.CROSS_MODULE),
    ("decision", {"scope_impact": "task"}, QuestionCategory.BOUNDED_AMBIGUITY),
    ("decision", {"reversibility": "costly"}, QuestionCategory.BOUNDED_AMBIGUITY),
    ("decision", {}, QuestionCategory.LOCAL_REVERSIBLE),
]


@pytest.mark.parametrize(("kind", "facts", "expected"), ROWS)
def test_each_row_of_the_table(kind: str, facts: dict[str, Any], expected: QuestionCategory) -> None:
    assert classify(kind, **facts) is expected


def test_first_matching_row_wins_and_missing_facts_are_cautious() -> None:
    assert classify("approval", contract_change="public") is QuestionCategory.AUTHORITY_REQUIRED
    assert classify(needs_external_fact=True, scope_impact="plan") is QuestionCategory.ARCHITECTURAL
    assert classify(needs_external_fact=True, scope_impact="cross_module") is QuestionCategory.EXTERNAL_FACT
    assert classify_question({}, "decision", [], [], {}) is QuestionCategory.ARCHITECTURAL
    assert (
        classify_question({"confidence": "high", **LOCAL}, "decision", [], [], {})
        is QuestionCategory.LOCAL_REVERSIBLE
    )


def test_gate_categories_from_paths_and_facts() -> None:
    scope = ["src/app/**"]
    assert gate_categories(LOCAL, ["src/app/x.py"], scope) == frozenset()
    assert gate_categories(LOCAL, ["src/app/auth/login.py"], scope) == {"security"}
    assert gate_categories(LOCAL, ["src/app/cli.py"], scope) == {"public_api"}
    assert gate_categories(LOCAL, ["src/app/schemas/a.json"], scope) == {"public_api"}
    assert gate_categories({**LOCAL, "contract_change": "public"}, [], scope) == {"public_api"}
    assert gate_categories(LOCAL, ["lib/other.py"], scope) == {"scope_expansion"}
    assert gate_categories({**LOCAL, "scope_impact": "plan"}, [], scope) == {"scope_expansion"}
    assert gate_categories(LOCAL, ["src/app/x.py"], None) == {"scope_expansion"}
    destructive = {**LOCAL, "reversibility": "irreversible"}
    assert gate_categories(destructive, ["src/app/migrations/0004_drop.sql"], scope) == {
        "public_api",
        "destructive",
    }
    assert "destructive" not in gate_categories(LOCAL, ["src/app/migrations/0004_drop.sql"], scope)
    custom: dict[str, Any] = {"security": ["src/app/vault/**"]}
    assert gate_categories(LOCAL, ["src/app/vault/k.py"], scope, custom) == {"security"}


def test_human_gate_union_cannot_remove_a_default_category() -> None:
    assert effective_human_gate(None) == DEFAULT_HUMAN_GATE
    assert effective_human_gate([]) == DEFAULT_HUMAN_GATE
    assert effective_human_gate([["product"], ["legal"]]) == DEFAULT_HUMAN_GATE | {"product", "legal"}
    local = QuestionCategory.LOCAL_REVERSIBLE
    for gate in DEFAULT_HUMAN_GATE:
        assert route(local, {gate}, {"human_gate": []}) == AudienceRoute(Audience.OWNER, "QUESTION_GATED")
    assert route(local, {"product"}, {"human_gate": ["product"]}).audience is Audience.OWNER
    assert route(local, {"product"}, {}).audience is Audience.ADVISOR


def route(category: QuestionCategory, gates: set[str], policy: dict[str, Any]) -> AudienceRoute:
    found = decide_audience(
        {"kind": "decision"}, category, frozenset(gates), policy, None, 0, 0, task_key="P1"
    )
    assert isinstance(found, AudienceRoute)
    return found


def test_category_audience_only_narrows_advisor_to_owner() -> None:
    defaults = effective_category_audience(None)
    assert defaults[QuestionCategory.ARCHITECTURAL] is Audience.OWNER
    assert defaults[QuestionCategory.CROSS_MODULE] is Audience.ADVISOR
    widened = effective_category_audience({"architectural": "advisor", "authority_required": "advisor"})
    assert widened[QuestionCategory.ARCHITECTURAL] is Audience.OWNER
    assert widened[QuestionCategory.AUTHORITY_REQUIRED] is Audience.OWNER
    narrowed = effective_category_audience({"cross_module": "owner"})
    assert narrowed[QuestionCategory.CROSS_MODULE] is Audience.OWNER
    narrowing = {"category_audience": {"cross_module": "owner"}}
    expected = AudienceRoute(Audience.OWNER, "QUESTION_CATEGORY_OWNER")
    assert route(QuestionCategory.CROSS_MODULE, set(), narrowing) == expected
