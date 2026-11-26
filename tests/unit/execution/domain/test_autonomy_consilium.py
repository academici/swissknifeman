"""Panel gates, option identity and a hostile minority critic."""

from typing import Any

import pytest

from skm.modules.execution.domain.consilium import aggregate, held


def advice(option="a", **changes: Any) -> Any:
    return {
        "recommendation": {"option_id": option, "text": option},
        "needs_owner": False,
        "confidence": "high",
        "category": "local_reversible",
        "sources": ["source:one"],
        **changes,
    }


def test_agreement_majority_critic_and_split():
    a, b = advice(), advice("b")
    assert aggregate([a, a], {})["kind"] == "agreement"
    assert aggregate([a, b], {})["kind"] == "split"
    majority = aggregate([a, a, b], {})
    assert majority["kind"] == "majority"
    assert majority["held"]
    assert majority["minority_first"] == 2
    assert aggregate([a, a, b], {"critic": a})["held"] is False
    assert aggregate([a, a, b], {"critic": b})["kind"] == "split"


@pytest.mark.parametrize("changes", [{"needs_owner": True}, {"category": "security"}, {"confidence": "low"}])
def test_panel_never_weakens_human_gate(changes):
    assert held(advice(**changes), {"human_gate": []})
    assert aggregate([advice(**changes), advice(**changes)], {})["held"]


def test_option_id_comparison_and_free_text_normalization():
    a = advice()
    b = advice(recommendation={"option_id": "a", "text": " different "})
    assert aggregate([a, b], {"options": ["a", "b"]})["kind"] == "agreement"
    assert aggregate([a, b], {})["kind"] == "split"
    assert held(a, {"options": ["b"]})
    assert held(a, {"gate_categories": ["public_api"], "human_gate": []})
    assert aggregate([a], {})["kind"] == "single"


def test_advice_record_and_stale_revision_and_timeout():
    from datetime import timedelta

    from skm.modules.execution.domain.consilium import apply_advice
    from skm.modules.execution.domain.decision_request import DecisionState
    from unit.execution.domain.test_decision_record import DIGEST, NOW, request, uid

    req = request(state=DecisionState.OPEN, answer_id=None)
    doc = advice(
        rationale="Grounded advice", sources=[{"kind": "source", "ref": "one"}], assumptions=["bounded"]
    )
    arguments = {
        "binding": {"input_part_digest": DIGEST},
        "answer_id": uid(10),
        "record_id": uid(11),
        "project_id": uid(3),
        "now": NOW,
    }
    applied = apply_advice(req, doc, {}, **arguments)
    assert applied.record is not None
    assert applied.record.rationale == "Grounded advice"
    assert applied.record.assumptions == ("bounded",)
    assert applied.record.evidence_refs == ("source:one",)
    assert applied.request.state is DecisionState.APPLIED
    scalar = apply_advice(req, {**doc, "assumptions": "bounded", "sources": "one"}, {}, **arguments)
    assert scalar.record is not None
    assert scalar.record.assumptions == ()  # a bare string is not split into one assumption per character
    assert scalar.record.evidence_refs == ()
    stale = apply_advice(
        req, doc, {}, **{**arguments, "binding": {"input_part_digest": "sha256:" + "a" * 64}}
    )
    assert stale.request.revision == 2
    assert stale.request.state is DecisionState.OPEN
    assert stale.record is None
    from dataclasses import replace

    timed_out = apply_advice(replace(req, deadline_at=NOW - timedelta(seconds=1)), doc, {}, **arguments)
    assert timed_out.answer is None
    assert timed_out.record is None


def test_advisor_stage_holds_gates_and_refuses_inherited_secrets(monkeypatch, tmp_path):
    from dataclasses import replace
    from types import SimpleNamespace

    from fakes.runtimes import runtime_request
    from skm.modules.execution.domain.stage_record import StageOutcomeKind
    from skm.modules.execution.host.stages.advisor_consult import AdvisorConsultStage
    from skm.modules.execution.host.stages.agent_step import AgentStepStage
    from skm.modules.execution.host.stages.base import StageOutcome
    from skm.modules.runtimes.public import RoleId

    stage = object.__new__(AdvisorConsultStage)
    agent = runtime_request(tmp_path, role=RoleId.ADVISOR)
    request: Any = SimpleNamespace(runtime_request=agent, task={})
    settings = {"execution.advisor.max_rounds": 2, "execution.advisor.min_confidence": "medium"}
    deps: Any = SimpleNamespace(config=SimpleNamespace(get=settings.get))
    monkeypatch.setattr(
        AgentStepStage,
        "run",
        lambda *args: StageOutcome(StageOutcomeKind.SUCCESS, {"role_result": advice(category="security")}),
    )
    assert stage.run(request, deps).payload["held"] is True
    from skm.platform.schema.registry import SchemaRegistry

    result = stage.run(request, deps)
    SchemaRegistry.load_default().require_valid(
        "urn:skm:execution:stage-outcome-advisor-consult:v1", dict(result.payload)
    )
    settings["execution.advisor.max_rounds"] = 0
    exhausted = stage.run(request, deps)
    assert exhausted.kind is StageOutcomeKind.HELD
    SchemaRegistry.load_default().require_valid(
        "urn:skm:execution:stage-outcome-advisor-consult:v1", dict(exhausted.payload)
    )
    request.runtime_request = replace(agent, extra_env={"SKM_TOKEN": "primary"})
    with pytest.raises(ValueError, match="inherit"):
        stage.run(request, deps)


def test_consilium_request_requires_verified_panel():
    from skm.modules.execution.domain.consilium import apply_advice
    from skm.modules.execution.domain.decision_request import Audience, DecisionState
    from unit.execution.domain.test_decision_record import DIGEST, NOW, request, uid

    req = request(state=DecisionState.OPEN, answer_id=None, audience=Audience.CONSILIUM)
    doc = advice()
    arguments: Any = {
        "binding": {"input_part_digest": DIGEST},
        "answer_id": uid(10),
        "record_id": uid(11),
        "project_id": uid(3),
        "now": NOW,
    }
    assert apply_advice(req, doc, {}, **arguments).held
    assert apply_advice(req, doc, {}, panel=True, **arguments).held
    result = apply_advice(req, doc, {"votes": [doc, doc]}, panel=True, **arguments)
    assert result.record is not None
    assert result.record.authority == "consilium"
