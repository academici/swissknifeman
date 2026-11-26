import json
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from skm.adapters.runtimes._cli_session.observation import ObservationCapture
from skm.adapters.runtimes.antigravity.stream_parser import AntigravityStreamParser
from skm.adapters.runtimes.claude_code.stream_parser import ClaudeStreamParser
from skm.adapters.runtimes.pool import ProviderSlot, QuotaGroup, QuotaProber, QuotaReply
from skm.modules.execution.application._worker_events import executed_by
from skm.modules.runtimes.domain.observation import (
    ObservationBinding,
    observation_from_json,
    observation_to_json,
)

_SLOT = ProviderSlot("claude_code", "primary")
_GROUPS = tuple(QuotaGroup(str(i), "opus" if i == 1 else "") for i in range(6))


def test_independent_group_probes_preserve_balances_and_failure_reasons() -> None:
    replies = (
        QuotaReply(200, 15),
        QuotaReply(200, 0),
        None,
        QuotaReply(402),
        QuotaReply(429),
        QuotaReply(529),
    )
    called = []

    def transport(slot: ProviderSlot, group: QuotaGroup) -> QuotaReply:
        called.append((slot, group))
        reply = replies[_GROUPS.index(group)]
        if reply is None:
            raise TimeoutError
        return reply

    readings = QuotaProber(_GROUPS, transport).probe(_SLOT)
    assert called == [(_SLOT, group) for group in _GROUPS]
    assert [(r.state, r.remaining) for r in readings] == [
        ("available", 15),
        ("exhausted", 0),
        ("unknown", None),
        ("payment_required", None),
        ("rate_limited", None),
        ("overloaded", None),
    ]


@pytest.mark.parametrize(
    "reply", [None, QuotaReply(204), QuotaReply(503, 0), QuotaReply(200, -1), QuotaReply(200, False)]
)
def test_unavailable_or_invalid_counter_stays_unknown(reply: QuotaReply | None) -> None:
    readings = QuotaProber(_GROUPS, lambda slot, group: reply).probe(_SLOT)
    assert len(readings) == 6
    assert all(reading.state == "unknown" and reading.remaining is None for reading in readings)


@pytest.mark.parametrize("groups", [_GROUPS[:5], (*_GROUPS, QuotaGroup("7")), (*_GROUPS[:5], _GROUPS[0])])
def test_six_distinct_groups_required(groups: tuple[QuotaGroup, ...]) -> None:
    with pytest.raises(ValueError, match="six distinct"):
        QuotaProber(groups, lambda slot, group: None)


@pytest.mark.parametrize(
    ("reported", "downgraded"),
    [
        ("claude-sonnet-4-5", True),
        ("another-provider/model", True),
        ("not-opus", True),
        ("opus-labs/claude-sonnet-5", True),
        ("latest", None),
        ("claude-opus-4-1-20250805", False),
        ("vendor/claude-3-opus-20240229", False),
        ("opus", False),
        (None, None),
    ],
)
def test_fallback_and_attribution_follow_the_provider_observation(
    reported: str | None, downgraded: bool | None
) -> None:
    sample = (
        Path(__file__).resolve().parents[3] / "fixtures/corpus/examples/runtimes/observation-minimal.json"
    )
    observation = observation_from_json(json.loads(sample.read_bytes()))
    binding = replace(
        observation.binding,
        runtime_id=_SLOT.runtime_id,
        provider_reported_model=reported,
        model_source="unavailable" if reported is None else "provider_stream",
    )
    observation = replace(observation, binding=binding)
    reply = QuotaReply(200, 5, observation)
    reading = QuotaProber(_GROUPS, lambda slot, group: reply).probe(_SLOT)[1]
    assert reading.opus_fallback is downgraded
    assert reading.reported_model == reported
    route = {"resolved": {"runtime_id": _SLOT.runtime_id, "model": "opus", "effort": "high"}}
    assert executed_by(route, observation_to_json(observation)) == (
        _SLOT.runtime_id if reported is None else f"{_SLOT.runtime_id}/{reported}"
    )
    assert executed_by(route, None) is None
    other = ProviderSlot("other", "secondary")
    rejected = QuotaProber(_GROUPS, lambda slot, group: reply).probe(other)[1]
    assert (rejected.state, rejected.reported_model, rejected.opus_fallback) == ("unknown", None, None)


def test_rejected_antigravity_fallback_keeps_the_actual_model() -> None:
    parser = AntigravityStreamParser(
        models=frozenset({"claude-opus-5"}), version=None, workdir="/work", redact=str
    )
    with pytest.raises(ValueError, match="unexpected Antigravity session or model"):
        parser.feed(
            b'{"event":"init","conversation_id":"s","init":{"model":"claude-sonnet-5","cwd":"/work"}}'
        )
    assert parser.finish(0).model == "claude-sonnet-5"
    assert not parser.saw_terminal()


@pytest.mark.parametrize(
    ("parent_model", "child_model", "fallback"),
    [("claude-sonnet-5", "claude-opus-5", True), ("claude-opus-5", "claude-sonnet-5", False)],
)
def test_probe_attributes_the_parent_execution_from_the_native_stream(
    parent_model: str,
    child_model: str,
    fallback: bool,
) -> None:
    parser = ClaudeStreamParser()
    for event in (
        {"type": "system", "subtype": "init", "session_id": "primary", "model": "opus"},
        {"type": "assistant", "message": {"model": parent_model, "content": []}},
        {
            "type": "assistant",
            "parent_tool_use_id": "task-1",
            "message": {"model": child_model, "content": []},
        },
        {"type": "result", "subtype": "success", "result": "done"},
    ):
        tuple(parser.feed(json.dumps(event).encode()))
    result = parser.finish(0)
    capture = ObservationCapture(
        UUID("01928f61-3333-7aaa-8bbb-2c3d4e5f6a7c"),
        ObservationBinding(_SLOT.runtime_id, None, None, None, None, None, "unavailable"),
        started=0,
    )
    observation = capture.freeze(ended=1, model=result.model)
    reading = QuotaProber(_GROUPS, lambda slot, group: QuotaReply(200, 10, observation)).probe(_SLOT)[1]
    assert reading.reported_model == parent_model
    assert reading.opus_fallback is fallback
