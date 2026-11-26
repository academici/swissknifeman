"""RuntimeObservation and model identity (runtimes §4.7, §4.7.1)."""

from __future__ import annotations

import copy
import dataclasses
import json
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.kernel.json_types import JsonObject
from skm.modules.runtimes.domain.classes import Effort
from skm.modules.runtimes.domain.error_rules import ProcessOutcome, process_failure
from skm.modules.runtimes.domain.genai_semconv import agent_invocation_span
from skm.modules.runtimes.domain.observation import (
    OBSERVATION_MAX_BYTES,
    CaptureObservation,
    ModelIdentity,
    ObservationBinding,
    ObservationTiming,
    RuntimeObservation,
    ToolVisibility,
    canonical_observation_bytes,
    model_identity,
    observation_from_json,
    observation_to_json,
    observed_model_family,
    validate_runtime_observation,
)
from skm.modules.runtimes.domain.result import (
    ExitInfo,
    RuntimeResult,
    result_from_json,
    result_to_json,
    validate_result_observation,
)
from skm.modules.runtimes.domain.usage import SubagentUsage, UsageReport, UsageStatus, unknown_usage
from skm.modules.runtimes.generated.observation import RuntimeObservationDto
from skm.modules.runtimes.generated.result import RuntimeResultDto
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES = ROOT / "tests/fixtures/corpus/examples/runtimes"
FIXTURES = ("minimal", "partial", "restart", "unavailable")
OBSERVATION_URN = "urn:skm:runtimes:runtime-observation:v1"
RESULT_URN = "urn:skm:runtimes:runtime-result:v1"
STEP = UUID("01928f61-3333-7aaa-8bbb-2c3d4e5f6a7c")
OTHER_STEP = UUID("01928f61-3333-7aaa-8bbb-ffffffffffff")
EPOCH = UUID("01928f61-4444-7aaa-8bbb-2c3d4e5f6a7c")
T0 = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def fixture(name: str) -> JsonObject:
    return json.loads((EXAMPLES / f"observation-{name}.json").read_text())


def test_observed_effort_is_nullable_and_round_trips() -> None:
    original = observation(reported="gpt-6-sol", binding={"observed_effort": Effort.MEDIUM})
    raw = observation_to_json(original)
    registry().require_valid(OBSERVATION_URN, raw)
    assert observation_from_json(raw).binding.observed_effort is Effort.MEDIUM
    assert observation_from_json(fixture("minimal")).binding.observed_effort is None
    assert observation().binding.observed_effort is None


@pytest.mark.parametrize(
    ("runtime", "model", "family"),
    [
        ("cursor", "vendor/GPT-6", "gpt"),
        ("codex", "o3-mini", "gpt"),
        ("claude_code", "opus", "claude"),
        ("cursor", "vendor/claude-opus-4", "claude"),
        ("grok", "grok-4.5", "grok"),
        ("cursor", "opus", None),
        ("cursor", None, None),
    ],
)
def test_observed_model_family_uses_model_names_and_runtime_aliases(
    runtime: str, model: str | None, family: str | None
) -> None:
    assert observed_model_family(runtime, model) == family


def observation(
    *,
    reported: str | None = None,
    capture: dict[str, Any] | None = None,
    timing: dict[str, Any] | None = None,
    tools: ToolVisibility | None = None,
    binding: dict[str, Any] | None = None,
) -> RuntimeObservation:
    return RuntimeObservation(
        schema="urn:skm:runtimes:runtime-observation:v1",
        request_id=STEP,
        binding=ObservationBinding(
            **{
                "runtime_id": "fake",
                "runtime_version": "1.2.3",
                "adapter_version": "0.1.0",
                "executable_sha256": DIGEST,
                "verification_key": None,
                "provider_reported_model": reported,
                "model_source": "unavailable" if reported is None else "provider_stream",
            }
            | (binding or {})
        ),
        timing=ObservationTiming(
            **{
                "clock_domain_id": EPOCH,
                "duration_ms": 42,
                "first_observed_at": T0,
                "last_observed_at": T0 + timedelta(milliseconds=42),
            }
            | (timing or {})
        ),
        capture=CaptureObservation(
            **{
                "coverage": "complete",
                "bytes_seen": 128,
                "bytes_retained": 128,
                "bytes_dropped": 0,
                "truncated": False,
                "gaps": (),
                "parser_flags": (),
                "live_events_dropped": None,
            }
            | (capture or {})
        ),
        tools=tools or ToolVisibility("unavailable", None),
    )


def rules(value: RuntimeObservation, *, reported: str | None = None, request_id: UUID = STEP) -> list[str]:
    found = validate_runtime_observation(value, request_id=request_id, provider_reported_model=reported)
    return [violation.rule for violation in found]


def test_genai_span_maps_only_observed_and_trusted_metadata() -> None:
    usage = UsageReport(
        20, 12, 7, 3, 2, 100, UsageStatus.REPORTED, "stream:result", SubagentUsage(None, False)
    )
    span = agent_invocation_span(
        observation(reported="gpt-5", tools=ToolVisibility("complete", 0)),
        provider="openai",
        agent_name="reviewer",
        request_model="gpt-5-pinned",
        usage=usage,
        error_type="RUNTIME_CRASHED",
    )
    assert (span.name, span.kind) == ("invoke_agent reviewer", "CLIENT")
    assert span.attributes == {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": "openai",
        "gen_ai.agent.name": "reviewer",
        "gen_ai.request.model": "gpt-5-pinned",
        "gen_ai.response.model": "gpt-5",
        "gen_ai.usage.input_tokens": 30,
        "gen_ai.usage.output_tokens": 12,
        "gen_ai.usage.cache_read.input_tokens": 7,
        "gen_ai.usage.cache_write.input_tokens": 3,
        "error.type": "RUNTIME_CRASHED",
        "skm.runtime.id": "fake",
        "skm.capture.coverage": "complete",
        "skm.capture.duration_ms": 42,
        "skm.tools.observed_calls": 0,
    }


def test_genai_span_omits_unknown_observation_and_estimated_usage() -> None:
    usage = UsageReport(
        20, 12, None, None, None, None, UsageStatus.ESTIMATED, "estimate", SubagentUsage(None, False)
    )
    span = agent_invocation_span(
        observation_from_json(fixture("unavailable")),
        provider="openai",
        request_model="gpt-5",
        usage=usage,
    )
    assert span.name == "invoke_agent"
    assert span.attributes["gen_ai.request.model"] == "gpt-5"
    assert "gen_ai.response.model" not in span.attributes
    assert "skm.capture.duration_ms" not in span.attributes
    assert "skm.tools.observed_calls" not in span.attributes
    assert not any(key.startswith("gen_ai.usage.") for key in span.attributes)


def result(*, model: str | None, value: RuntimeObservation | None) -> RuntimeResult:
    return RuntimeResult(
        outcome="completed",
        final_text="done",
        structured=None,
        session_ref=None,
        model=model,
        usage=unknown_usage(),
        failure=None,
        exit=ExitInfo(0, None, False, 42),
        lingered=False,
        denials=(),
        api_retries=0,
        transcript_path=None,
        stderr_path=None,
        observation=value,
    )


@pytest.mark.parametrize("name", FIXTURES)
def test_every_fixture_passes_its_urn_and_the_semantic_boundary(name: str) -> None:
    data = fixture(name)
    assert registry().validate(OBSERVATION_URN, data) == ()
    value = observation_from_json(data)
    reported = data["binding"]["provider_reported_model"]  # type: ignore[index]
    assert rules(value, reported=reported) == []  # type: ignore[arg-type]
    encoded = observation_to_json(value)
    assert registry().validate(OBSERVATION_URN, encoded) == ()
    assert observation_from_json(encoded) == value  # same instants; RFC 3339 text may differ in precision
    assert RuntimeObservationDto.from_json(data).request_id == STEP  # generated DTO of the same URN


def test_old_result_without_observation_stays_valid() -> None:
    old = result_to_json(result(model="opus", value=None))
    assert "observation" not in old
    assert registry().validate(RESULT_URN, old) == ()
    assert registry().validate(RESULT_URN, old | {"observation": None}) == ()
    decoded = result_from_json(old)
    assert decoded.observation is None  # absent = unavailable, no invented zeros or versions
    assert result_from_json(old | {"observation": None}).observation is None
    assert validate_result_observation(decoded, request_id=STEP) == ()
    assert RuntimeResultDto.from_json(old).observation is None


def test_result_observation_resolves_through_its_ref_and_round_trips() -> None:
    value = observation_from_json(fixture("partial"))
    encoded = result_to_json(result(model="fake-provider-reported", value=value))
    assert registry().validate(RESULT_URN, encoded) == ()
    assert result_from_json(encoded).observation == value
    dto = RuntimeResultDto.from_json(encoded)
    assert isinstance(dto.observation, RuntimeObservationDto)
    broken = copy.deepcopy(encoded)
    broken["observation"]["capture"]["extra"] = 1  # type: ignore[index]
    assert registry().validate(RESULT_URN, broken) != ()  # the referenced schema stays closed


def test_reported_model_null_stays_null_when_the_resolved_model_is_known() -> None:
    # Resolved route model "opus" is known, the provider reported nothing.
    honest = observation(reported=None)
    assert validate_result_observation(result(model=None, value=honest), request_id=STEP) == ()
    filled = observation(reported="opus")
    found = validate_result_observation(result(model=None, value=filled), request_id=STEP)
    assert [violation.rule for violation in found] == ["reported_model_mismatch"]


def test_model_source_follows_the_reported_value() -> None:
    claimed = observation(reported=None, binding={"model_source": "provider_stream"})
    assert rules(claimed) == ["model_source_mismatch"]
    assert registry().validate(OBSERVATION_URN, observation_to_json(claimed)) != ()


@pytest.mark.parametrize("reported", ["claude-opus-5-5", None, "latest"], ids=["exact", "null", "alias"])
def test_requested_resolved_and_reported_models_stay_three_facts(reported: str | None) -> None:
    identity = model_identity(requested="latest", resolved="opus", reported=reported)
    assert identity == ModelIdentity(
        "latest", "opus", reported, "unavailable" if reported is None else "provider_stream"
    )
    value = observation(reported=reported)
    res = result(model=reported, value=value)
    # A reported model unlike the resolved one is a recorded fact, not a violation; nothing is rerouted.
    assert validate_result_observation(res, request_id=STEP) == ()
    assert res.model == reported
    assert value.binding.provider_reported_model == reported  # an alias is not upgraded to an exact revision
    assert identity.resolved == "opus"


def test_mismatched_report_does_not_mutate_request_facts_or_reserve() -> None:
    value = observation(reported="claude-sonnet-5-5")
    res = result(model="claude-opus-5-5", value=value)
    before = (dataclasses.astuple(res.usage), res.model, observation_to_json(value))
    found = validate_result_observation(res, request_id=STEP)
    assert [violation.rule for violation in found] == ["reported_model_mismatch"]
    assert (dataclasses.astuple(res.usage), res.model, observation_to_json(value)) == before


def test_request_id_is_the_step_id() -> None:
    assert rules(observation(), request_id=OTHER_STEP) == ["request_id_mismatch"]


def test_unavailable_tools_have_null_calls_and_capture_coverage_is_separate() -> None:
    zero = observation(tools=ToolVisibility("unavailable", 0))
    assert rules(zero) == ["unavailable_with_counters"]
    assert registry().validate(OBSERVATION_URN, observation_to_json(zero)) != ()
    # Complete local capture does not prove complete native tool visibility.
    assert rules(observation(tools=ToolVisibility("unavailable", None))) == []
    assert rules(observation(tools=ToolVisibility("partial", 2))) == []
    assert rules(observation(tools=ToolVisibility("complete", 0))) == []


@pytest.mark.parametrize(
    ("capture", "expected"),
    [
        ({"bytes_seen": 100, "bytes_retained": 60, "bytes_dropped": 30}, "bytes_mismatch"),
        ({"bytes_seen": 10, "bytes_retained": 60, "bytes_dropped": None}, "bytes_mismatch"),
        ({"coverage": "unavailable", "gaps": ("capture_gap",)}, "unavailable_with_counters"),
        ({"truncated": True, "bytes_dropped": 0}, "complete_with_loss"),
        ({"bytes_retained": 100, "bytes_dropped": 28}, "complete_with_loss"),
        ({"gaps": ("capture_gap",)}, "complete_with_loss"),
        ({"parser_flags": ("parser_limit",)}, "complete_with_loss"),
        ({"live_events_dropped": 3}, "live_loss_without_gap"),
        ({"gaps": ("capture_gap", "capture_gap"), "coverage": "partial"}, "invalid_flags"),
        ({"gaps": ("lost_everything",), "coverage": "partial"}, "invalid_flags"),
        ({"bytes_seen": -1}, "invalid_counter"),
    ],
)
def test_inconsistent_capture_is_rejected(capture: dict[str, Any], expected: str) -> None:
    assert expected in rules(observation(capture=capture))


@pytest.mark.parametrize("truncated", ["true", "false", 1, 0, 1.0, [True], {"value": True}], ids=repr)
@pytest.mark.parametrize("coverage", ["complete", "partial"])
def test_truncated_is_a_strict_bool_at_every_boundary(truncated: object, coverage: str) -> None:
    value = observation(capture={"coverage": coverage, "truncated": truncated})
    assert "invalid_truncated" in rules(value)
    found = validate_result_observation(result(model=None, value=value), request_id=STEP)
    assert "invalid_truncated" in [violation.rule for violation in found]
    data = observation_to_json(value)
    assert registry().validate(OBSERVATION_URN, data) != ()  # the schema allows boolean/null only
    assert "invalid_truncated" in rules(observation_from_json(data))  # no coercion while decoding


@pytest.mark.parametrize("truncated", [True, False, None])
def test_truncated_bool_or_null_round_trips(truncated: bool | None) -> None:
    value = observation(capture={"coverage": "partial", "truncated": truncated})
    assert rules(value) == []
    decoded = observation_from_json(observation_to_json(value))
    assert decoded.capture.truncated is truncated
    assert rules(decoded) == []


def test_truncated_true_breaks_complete_coverage() -> None:
    assert rules(observation(capture={"truncated": True})) == ["complete_with_loss"]


def test_unknown_counters_are_null_not_zero() -> None:
    unknown = observation(
        capture={
            "coverage": "partial",
            "bytes_seen": None,
            "bytes_retained": None,
            "bytes_dropped": None,
            "truncated": None,
        }
    )
    assert rules(unknown) == []
    data = observation_to_json(unknown)
    assert data["capture"]["bytes_seen"] is None  # type: ignore[index]
    assert registry().validate(OBSERVATION_URN, data) == ()


def test_live_delivery_gap_does_not_make_local_capture_partial() -> None:
    live = observation(capture={"gaps": ("live_delivery_gap",), "live_events_dropped": 2})
    assert rules(live) == []
    assert registry().validate(OBSERVATION_URN, observation_to_json(live)) == ()


def test_utc_clock_jump_does_not_change_the_monotonic_duration() -> None:
    jumped = observation(timing={"last_observed_at": T0 - timedelta(minutes=1), "duration_ms": 142})
    assert rules(jumped) == []
    assert jumped.timing.duration_ms == 142
    assert registry().validate(OBSERVATION_URN, observation_to_json(jumped)) == ()


def test_process_epoch_change_is_never_one_duration() -> None:
    crossed = observation(capture={"coverage": "partial", "gaps": ("capture_gap", "process_epoch_changed")})
    assert rules(crossed) == ["cross_epoch_duration"]
    assert registry().validate(OBSERVATION_URN, observation_to_json(crossed)) != ()
    complete = observation(
        capture={"gaps": ("process_epoch_changed",)}, timing={"duration_ms": None, "clock_domain_id": None}
    )
    assert set(rules(complete)) == {"complete_with_loss", "cross_epoch_coverage"}
    honest = observation(
        capture={"coverage": "partial", "gaps": ("process_epoch_changed",)},
        timing={"duration_ms": None, "clock_domain_id": None},
    )
    assert rules(honest) == []


def test_duration_needs_its_clock_domain() -> None:
    assert rules(observation(timing={"clock_domain_id": None})) == ["duration_without_epoch"]


def test_provider_times_are_separate_claims() -> None:
    plain = observation_to_json(observation())
    assert "provider_first_at" not in plain["timing"]  # type: ignore[operator]
    claimed = observation(timing={"provider_first_at": T0 - timedelta(hours=1), "provider_last_at": T0})
    assert rules(claimed) == []
    timing = observation_to_json(claimed)["timing"]
    assert timing["first_observed_at"] == "2026-10-26T10:00:00Z"  # type: ignore[index]
    assert timing["provider_first_at"] == "2026-10-26T09:00:00Z"  # type: ignore[index]
    naive = observation(timing={"first_observed_at": datetime(2026, 1, 1)})  # noqa: DTZ001
    assert "invalid_timestamp" in rules(naive)


@pytest.mark.parametrize(
    ("binding", "expected"),
    [
        ({"executable_sha256": "/usr/local/bin/claude"}, "invalid_digest"),
        ({"verification_key": "sha256:XYZ"}, "invalid_digest"),
        ({"runtime_version": "/home/dev/.local/bin/claude 1.0"}, "invalid_version"),
        ({"runtime_id": "Claude-Code"}, "invalid_runtime_id"),
    ],
)
def test_binding_carries_safe_digests_and_versions_without_paths(
    binding: dict[str, Any], expected: str
) -> None:
    assert expected in rules(observation(binding=binding))


def test_secret_reference_is_not_a_model() -> None:
    value = observation(reported="secret://vault/token")
    assert "invalid_model" in rules(value, reported="secret://vault/token")


def test_metadata_above_16_kib_is_rejected() -> None:
    huge = observation(binding={"adapter_version": "v" * (OBSERVATION_MAX_BYTES + 1)})
    assert len(canonical_observation_bytes(huge)) > OBSERVATION_MAX_BYTES
    assert "too_large" in rules(huge)
    assert registry().validate(OBSERVATION_URN, observation_to_json(huge)) != ()
    assert len(canonical_observation_bytes(observation())) < OBSERVATION_MAX_BYTES


def test_observation_is_closed() -> None:
    data = observation_to_json(observation())
    assert registry().validate(OBSERVATION_URN, data | {"prompt": "x"}) != ()
    tools = dict(data["tools"])  # type: ignore[arg-type]
    assert registry().validate(OBSERVATION_URN, data | {"tools": tools | {"names": ["Bash"]}}) != ()


def test_observation_is_not_lifecycle_authority() -> None:
    # A clean observation does not turn a failed session into a success.
    failure = process_failure(ProcessOutcome.STREAM_INCOMPLETE)
    failed = dataclasses.replace(
        result(model=None, value=observation()), outcome="failed", final_text="", failure=failure
    )
    assert validate_result_observation(failed, request_id=STEP) == ()
    assert failed.outcome == "failed"
    with pytest.raises(ValueError, match="completed result has no failure"):
        dataclasses.replace(failed, outcome="completed")


def test_outcome_cancelled_iff_cancel_codes() -> None:
    base = result(model=None, value=None)
    cancelled = dataclasses.replace(
        base, outcome="cancelled", final_text="", failure=process_failure(ProcessOutcome.CANCELLED)
    )
    assert cancelled.failure is not None
    with pytest.raises(ValueError, match="cancelled"):
        dataclasses.replace(cancelled, outcome="failed")
    with pytest.raises(ValueError, match="cancelled"):
        dataclasses.replace(base, outcome="cancelled", failure=process_failure(ProcessOutcome.WALL_TIMEOUT))
    with pytest.raises(ValueError, match="carries its failure"):
        dataclasses.replace(base, outcome="failed")
    assert registry().validate(RESULT_URN, result_to_json(cancelled)) == ()


@pytest.mark.parametrize(
    ("section", "field", "bad_value"),
    [
        ("timing", "clock_domain_id", "invalid-uuid"),
        ("binding", "runtime_id", "Invalid-Runtime"),
        ("binding", "adapter_version", "v" * 101),
        ("binding", "verification_key", "sha256:xyz"),
        ("binding", "provider_reported_model", "secret://token"),
        ("timing", "duration_ms", -1),
        ("capture", "bytes_seen", 2**63),
        ("capture", "gaps", ("live_delivery_gap", "live_delivery_gap")),
        ("capture", "parser_flags", ("unknown",)),
        ("tools", "observed_calls", True),
    ],
)
def test_schema_refusal_is_also_a_semantic_boundary_refusal(
    section: str, field: str, bad_value: object
) -> None:
    base = observation()
    value = dataclasses.replace(
        base, **{section: dataclasses.replace(getattr(base, section), **{field: bad_value})}
    )
    assert registry().validate(OBSERVATION_URN, observation_to_json(value)) != ()
    reported = cast("str | None", bad_value if field == "provider_reported_model" else None)
    assert rules(value, reported=reported)


def test_invalid_request_uuid_is_refused_at_semantic_boundary() -> None:
    value = dataclasses.replace(observation(), request_id=cast("UUID", "not-a-uuid"))
    assert registry().validate(OBSERVATION_URN, observation_to_json(value)) != ()
    assert "invalid_request_id" in rules(value)


@pytest.mark.parametrize("bad_flags", [None, ([],), (1,), "capture_gap"])
def test_invalid_flag_shapes_are_refused_without_raising(bad_flags: object) -> None:
    value = observation(capture={"gaps": bad_flags})
    assert "invalid_flags" in rules(value)
