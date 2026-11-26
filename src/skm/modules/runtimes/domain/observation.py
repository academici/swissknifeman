"""Bounded wrapper-owned runtime observation (runtimes §4.7.1, ``urn:skm:runtimes:runtime-observation:v1``).

Diagnostics, not authority: an observation never proves start/kill/ownership/acceptance and never heals a
missing terminal or a parser failure. Unknown stays ``None`` (never 0/false); the reported model is the
provider's claim, never filled from the requested or resolved model.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final, Literal, cast
from uuid import UUID

from .classes import Effort
from .ids import format_utc, is_digest, is_runtime_id, parse_utc
from .session_events import Violation

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.runtimes.domain.ids import Digest, ModelId, RuntimeId

__all__ = [
    "CAPTURE_GAPS",
    "OBSERVATION_MAX_BYTES",
    "OBSERVATION_SCHEMA",
    "PARSER_FLAGS",
    "CaptureObservation",
    "Coverage",
    "ModelIdentity",
    "ObservationBinding",
    "ObservationTiming",
    "RuntimeObservation",
    "ToolVisibility",
    "canonical_observation_bytes",
    "model_identity",
    "observation_from_json",
    "observation_to_json",
    "observed_model_family",
    "validate_runtime_observation",
]

OBSERVATION_SCHEMA: Final = "urn:skm:runtimes:runtime-observation:v1"
OBSERVATION_MAX_BYTES: Final = 16384  # canonical UTF-8 JSON; SQL keeps a 32 KiB defensive backstop
CAPTURE_GAPS: Final = ("capture_gap", "live_delivery_gap", "provider_sequence_gap", "process_epoch_changed")
PARSER_FLAGS: Final = ("invalid_utf8", "malformed_json", "incomplete_tail", "parser_limit")
_COVERAGE: Final = ("complete", "partial", "unavailable")
_MAX_COUNTER: Final = 2**63 - 1
_VERSION: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+()-]{0,99}")
_MODEL: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}")
_MODEL_FAMILY_PREFIXES: Final = {
    "gpt-": (),
    "claude-": ("haiku", "sonnet", "opus"),
    "gemini-": (),
    "grok-": (),
    "composer-": (),
}
# A gap of the local capture/parser scope; live loss is a separate channel and keeps capture complete.
_LOCAL_GAPS: Final = frozenset({"capture_gap", "provider_sequence_gap", "process_epoch_changed"})

type Coverage = Literal["complete", "partial", "unavailable"]


@dataclass(frozen=True, slots=True)
class ObservationBinding:
    runtime_id: RuntimeId  # from the pinned request
    runtime_version: str | None  # of the immutable installation actually used, else None
    adapter_version: str | None
    executable_sha256: Digest | None  # bound executable (§4.3); never re-detected from a mutable locator
    verification_key: Digest | None  # existing exact VerificationContext key; metadata, not new evidence
    provider_reported_model: ModelId | None  # == RuntimeResult.model, including None
    model_source: Literal["provider_stream", "unavailable"]
    observed_effort: Effort | None = None


@dataclass(frozen=True, slots=True)
class ObservationTiming:
    clock_domain_id: UUID | None  # capture-process epoch, renewed on restart; not a StepId
    duration_ms: int | None  # monotonic capture start -> final drain within one epoch
    first_observed_at: datetime | None  # observer UTC in observation order, not min/max provider time
    last_observed_at: datetime | None  # may be earlier than first after a clock jump
    provider_first_at: datetime | None = None  # provider claims, separate from observer UTC
    provider_last_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CaptureObservation:
    coverage: Coverage  # local stdout/stderr capture and parser scope
    bytes_seen: int | None  # raw ingress counted once
    bytes_retained: int | None  # admitted to the primary capture before redaction
    bytes_dropped: int | None  # observed but not retained
    truncated: bool | None
    gaps: tuple[str, ...]  # closed CAPTURE_GAPS
    parser_flags: tuple[str, ...]  # closed PARSER_FLAGS
    live_events_dropped: int | None  # bounded live-enqueue failures; not proof of remote delivery


@dataclass(frozen=True, slots=True)
class ToolVisibility:
    coverage: Coverage  # provider-native tool visibility, independent of capture coverage
    observed_calls: int | None  # known observations, possibly partial; None when unavailable


@dataclass(frozen=True, slots=True)
class RuntimeObservation:
    schema: Literal["urn:skm:runtimes:runtime-observation:v1"]
    request_id: UUID  # the existing StepId (AgentRequest.request_id)
    binding: ObservationBinding
    timing: ObservationTiming
    capture: CaptureObservation
    tools: ToolVisibility


def _utc_or_none(value: datetime | None) -> str | None:
    return None if value is None else format_utc(value)


def observation_to_json(value: RuntimeObservation) -> JsonObject:
    timing: JsonObject = {
        "clock_domain_id": None
        if value.timing.clock_domain_id is None
        else str(value.timing.clock_domain_id),
        "duration_ms": value.timing.duration_ms,
        "first_observed_at": _utc_or_none(value.timing.first_observed_at),
        "last_observed_at": _utc_or_none(value.timing.last_observed_at),
    }
    # Optional provider claims: an unknown time is absent, not invented.
    if value.timing.provider_first_at is not None:
        timing["provider_first_at"] = format_utc(value.timing.provider_first_at)
    if value.timing.provider_last_at is not None:
        timing["provider_last_at"] = format_utc(value.timing.provider_last_at)
    binding = value.binding
    capture = value.capture
    return {
        "schema": value.schema,
        "request_id": str(value.request_id),
        "binding": {
            "runtime_id": binding.runtime_id,
            "runtime_version": binding.runtime_version,
            "adapter_version": binding.adapter_version,
            "executable_sha256": binding.executable_sha256,
            "verification_key": binding.verification_key,
            "provider_reported_model": binding.provider_reported_model,
            "model_source": binding.model_source,
            "observed_effort": binding.observed_effort,
        },
        "timing": timing,
        "capture": {
            "coverage": capture.coverage,
            "bytes_seen": capture.bytes_seen,
            "bytes_retained": capture.bytes_retained,
            "bytes_dropped": capture.bytes_dropped,
            "truncated": capture.truncated,
            "gaps": list(capture.gaps),
            "parser_flags": list(capture.parser_flags),
            "live_events_dropped": capture.live_events_dropped,
        },
        "tools": {"coverage": value.tools.coverage, "observed_calls": value.tools.observed_calls},
    }


def canonical_observation_bytes(value: RuntimeObservation) -> bytes:
    """Sorted keys, no insignificant whitespace, UTF-8: the form the 16 KiB cap measures."""
    text = json.dumps(observation_to_json(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def _section(data: Mapping[str, JsonValue], name: str) -> Mapping[str, JsonValue]:
    value = data[name]
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    return value


def _utc_field(data: Mapping[str, JsonValue], name: str) -> datetime | None:
    value = data.get(name)
    return None if value is None else parse_utc(value, name)


def _strings(value: JsonValue, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{name} must be a list of strings")
    return tuple(cast("list[str]", value))


def observation_from_json(data: Mapping[str, JsonValue]) -> RuntimeObservation:
    """Decode a schema-shaped document; semantic checks are ``validate_runtime_observation``."""
    binding = _section(data, "binding")
    timing = _section(data, "timing")
    capture = _section(data, "capture")
    tools = _section(data, "tools")
    clock = timing["clock_domain_id"]
    return RuntimeObservation(
        schema=cast("Literal['urn:skm:runtimes:runtime-observation:v1']", data["schema"]),
        request_id=UUID(cast("str", data["request_id"])),
        binding=ObservationBinding(
            runtime_id=cast("str", binding["runtime_id"]),
            runtime_version=cast("str | None", binding["runtime_version"]),
            adapter_version=cast("str | None", binding["adapter_version"]),
            executable_sha256=cast("str | None", binding["executable_sha256"]),
            verification_key=cast("str | None", binding["verification_key"]),
            provider_reported_model=cast("str | None", binding["provider_reported_model"]),
            model_source=cast("Literal['provider_stream', 'unavailable']", binding["model_source"]),
            observed_effort=None
            if binding.get("observed_effort") is None
            else Effort(cast("str", binding["observed_effort"])),
        ),
        timing=ObservationTiming(
            clock_domain_id=None if clock is None else UUID(cast("str", clock)),
            duration_ms=cast("int | None", timing["duration_ms"]),
            first_observed_at=_utc_field(timing, "first_observed_at"),
            last_observed_at=_utc_field(timing, "last_observed_at"),
            provider_first_at=_utc_field(timing, "provider_first_at"),
            provider_last_at=_utc_field(timing, "provider_last_at"),
        ),
        capture=CaptureObservation(
            coverage=cast("Coverage", capture["coverage"]),
            bytes_seen=cast("int | None", capture["bytes_seen"]),
            bytes_retained=cast("int | None", capture["bytes_retained"]),
            bytes_dropped=cast("int | None", capture["bytes_dropped"]),
            truncated=cast("bool | None", capture["truncated"]),
            gaps=_strings(capture["gaps"], "gaps"),
            parser_flags=_strings(capture["parser_flags"], "parser_flags"),
            live_events_dropped=cast("int | None", capture["live_events_dropped"]),
        ),
        tools=ToolVisibility(
            coverage=cast("Coverage", tools["coverage"]),
            observed_calls=cast("int | None", tools["observed_calls"]),
        ),
    )


def _is_counter(value: object) -> bool:
    return value is None or (
        not isinstance(value, bool) and isinstance(value, int) and 0 <= value <= _MAX_COUNTER
    )


def _is_utc(value: object) -> bool:
    return value is None or (
        isinstance(value, datetime) and value.utcoffset() is not None and not value.utcoffset()
    )


def _valid_model(value: object) -> bool:
    return (
        isinstance(value, str) and _MODEL.fullmatch(value) is not None and not value.startswith("secret://")
    )


def _string_sequence(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, (tuple, list)):
        return None
    items = cast("tuple[object, ...] | list[object]", value)
    strings: list[str] = []
    for item in items:
        if not isinstance(item, str):
            return None
        strings.append(item)
    return tuple(strings)


def _valid_flags(values: object, allowed: tuple[str, ...]) -> bool:
    strings = _string_sequence(values)
    return (
        strings is not None
        and len(strings) <= len(allowed)
        and len(set(strings)) == len(strings)
        and set(strings) <= set(allowed)
    )


def _safe_gaps(value: object) -> tuple[str, ...]:
    return _string_sequence(value) or ()


def _binding_violations(binding: ObservationBinding, reported: ModelId | None) -> list[Violation]:
    found: list[Violation] = []
    if not is_runtime_id(binding.runtime_id):
        found.append(Violation("invalid_runtime_id", "binding.runtime_id is not a runtime id", "binding"))
    for name in ("runtime_version", "adapter_version"):
        version = getattr(binding, name)
        if version is not None and (not isinstance(version, str) or _VERSION.fullmatch(version) is None):
            found.append(
                Violation("invalid_version", f"{name} is not a bounded version string", f"binding.{name}")
            )
    for name in ("executable_sha256", "verification_key"):
        digest = getattr(binding, name)
        if digest is not None and not is_digest(digest):
            found.append(Violation("invalid_digest", f"{name} is not a sha256 digest", f"binding.{name}"))
    model = binding.provider_reported_model
    if model is not None and not _valid_model(model):
        found.append(Violation("invalid_model", "provider_reported_model is not a model id", "binding"))
    # The claim mirrors RuntimeResult.model exactly; requested/resolved never fill a missing report.
    if model != reported:
        found.append(
            Violation(
                "reported_model_mismatch",
                "provider_reported_model differs from RuntimeResult.model",
                "binding",
            )
        )
    expected_source = "unavailable" if model is None else "provider_stream"
    if binding.model_source != expected_source:
        found.append(Violation("model_source_mismatch", f"model_source must be {expected_source}", "binding"))
    if binding.observed_effort is not None and binding.observed_effort not in tuple(Effort):
        found.append(Violation("invalid_effort", "observed_effort is not a runtime effort", "binding"))
    return found


def _timing_violations(timing: ObservationTiming, gaps: tuple[str, ...]) -> list[Violation]:
    found: list[Violation] = []
    if timing.clock_domain_id is not None and not isinstance(timing.clock_domain_id, UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
        found.append(
            Violation(
                "invalid_clock_domain_id", "clock_domain_id must be a UUID or None", "timing.clock_domain_id"
            )
        )
    if not _is_counter(timing.duration_ms):
        found.append(Violation("invalid_counter", "duration_ms must be a non-negative int or None", "timing"))
    names = ("first_observed_at", "last_observed_at", "provider_first_at", "provider_last_at")
    found.extend(
        Violation("invalid_timestamp", f"{name} must be tz-aware UTC", f"timing.{name}")
        for name in names
        if not _is_utc(getattr(timing, name))
    )
    if timing.duration_ms is not None and timing.clock_domain_id is None:
        found.append(
            Violation("duration_without_epoch", "a monotonic duration needs its clock domain", "timing")
        )
    if "process_epoch_changed" in gaps and (
        timing.duration_ms is not None or timing.clock_domain_id is not None
    ):
        found.append(
            Violation(
                "cross_epoch_duration", "a summary across process epochs has no single duration", "timing"
            )
        )
    return found


def _capture_violations(capture: CaptureObservation) -> list[Violation]:
    found: list[Violation] = []
    if capture.coverage not in _COVERAGE:
        found.append(
            Violation("invalid_coverage", f"unknown capture coverage {capture.coverage!r}", "capture")
        )
    counters = (
        capture.bytes_seen,
        capture.bytes_retained,
        capture.bytes_dropped,
        capture.live_events_dropped,
    )
    if not all(_is_counter(value) for value in counters):
        found.append(
            Violation("invalid_counter", "capture counters are non-negative ints or None", "capture")
        )
        return found
    # Strict bool: a string "true" or an int 1 is not coerced; the schema allows boolean/null only.
    if capture.truncated is not None and not isinstance(capture.truncated, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
        found.append(Violation("invalid_truncated", "capture.truncated is a boolean or None", "capture"))
        return found
    for name, allowed, values in (
        ("gaps", CAPTURE_GAPS, capture.gaps),
        ("parser_flags", PARSER_FLAGS, capture.parser_flags),
    ):
        if not _valid_flags(values, allowed):
            found.append(
                Violation(
                    "invalid_flags", f"{name} must be unique values of the closed set", f"capture.{name}"
                )
            )
    if any(item.rule == "invalid_flags" for item in found):
        return found
    seen, retained, dropped = capture.bytes_seen, capture.bytes_retained, capture.bytes_dropped
    if capture.coverage == "unavailable" and (
        seen is not None or retained is not None or dropped is not None or capture.truncated is not None
    ):
        found.append(
            Violation("unavailable_with_counters", "unavailable capture has null bytes/truncated", "capture")
        )
    if seen is not None and retained is not None and dropped is not None and seen != retained + dropped:
        found.append(
            Violation("bytes_mismatch", "bytes_seen must equal bytes_retained + bytes_dropped", "capture")
        )
    elif seen is not None and any(part is not None and part > seen for part in (retained, dropped)):
        found.append(
            Violation("bytes_mismatch", "retained/dropped bytes cannot exceed bytes_seen", "capture")
        )
    if capture.coverage == "complete" and (
        capture.truncated is True
        or bool(dropped)
        or bool(_LOCAL_GAPS & set(capture.gaps))
        or bool(capture.parser_flags)
    ):
        found.append(
            Violation(
                "complete_with_loss", "truncation, dropped bytes, local gaps or parser flags", "capture"
            )
        )
    if "process_epoch_changed" in capture.gaps and capture.coverage != "partial":
        found.append(
            Violation("cross_epoch_coverage", "a summary across process epochs is partial", "capture")
        )
    if capture.live_events_dropped and "live_delivery_gap" not in capture.gaps:
        found.append(
            Violation("live_loss_without_gap", "dropped live events need live_delivery_gap", "capture")
        )
    return found


def validate_runtime_observation(
    value: RuntimeObservation, *, request_id: UUID, provider_reported_model: ModelId | None
) -> tuple[Violation, ...]:
    """Semantic boundary of §4.7.1 rule 5: closed values, the 16 KiB cap, ``request_id`` = StepId, the
    reported model equal to ``RuntimeResult.model``, counters, duration/epoch and coverage invariants."""
    found: list[Violation] = []
    if not isinstance(value, RuntimeObservation):  # pyright: ignore[reportUnnecessaryIsInstance]
        return (Violation("invalid_observation", "observation must be a RuntimeObservation"),)
    for name, expected in (
        ("binding", ObservationBinding),
        ("timing", ObservationTiming),
        ("capture", CaptureObservation),
        ("tools", ToolVisibility),
    ):
        if not isinstance(getattr(value, name), expected):
            found.append(Violation("invalid_section", f"{name} must be {expected.__name__}", name))
    if found:
        return tuple(found)
    if value.schema != OBSERVATION_SCHEMA:
        found.append(Violation("invalid_schema", "schema must be the runtime-observation URN", "schema"))
    if not isinstance(value.request_id, UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
        found.append(Violation("invalid_request_id", "request_id must be a UUID", "request_id"))
    if value.request_id != request_id:
        found.append(
            Violation("request_id_mismatch", "request_id must be the StepId of the request", "request_id")
        )
    found += _binding_violations(value.binding, provider_reported_model)
    found += _capture_violations(value.capture)
    found += _timing_violations(value.timing, _safe_gaps(value.capture.gaps))
    tools = value.tools
    if tools.coverage not in _COVERAGE or not _is_counter(tools.observed_calls):
        found.append(Violation("invalid_tools", "tools coverage/observed_calls out of range", "tools"))
    elif tools.coverage == "unavailable" and tools.observed_calls is not None:
        found.append(
            Violation("unavailable_with_counters", "unavailable tool visibility has null calls", "tools")
        )
    try:
        size = len(canonical_observation_bytes(value))
    except (TypeError, ValueError, AttributeError, OverflowError, UnicodeError):
        found.append(Violation("not_serializable", "observation has no canonical JSON form"))
    else:
        if size > OBSERVATION_MAX_BYTES:
            found.append(Violation("too_large", f"{size} bytes exceed the 16384-byte cap"))
    return tuple(found)


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    """Three separate model facts of one step (§4.7.1): none of them fills or replaces another.

    ``requested`` is the trusted route intent (an alias such as ``latest`` stays literal), ``resolved`` the
    admission/catalog choice passed as ``AgentRequest.model``, ``reported`` the nullable provider claim with
    its source. A difference grants no hidden reroute, no policy bypass and no new budget.
    """

    requested: ModelId | None
    resolved: ModelId
    reported: ModelId | None
    reported_source: Literal["provider_stream", "unavailable"]


def model_identity(
    *, requested: ModelId | None, resolved: ModelId, reported: ModelId | None
) -> ModelIdentity:
    return ModelIdentity(
        requested=requested,
        resolved=resolved,
        reported=reported,
        reported_source="unavailable" if reported is None else "provider_stream",
    )


def observed_model_family(runtime_id: RuntimeId, model: ModelId | None) -> str | None:
    """Recognize model families across runtimes by model name, with runtime-scoped short aliases."""
    if model is None:
        return None
    suffix = model.lower().rsplit("/", 1)[-1]
    if re.match(r"^o\d(?:-|$)", suffix):
        return "gpt"
    runtime_family = runtime_id.partition("_")[0]
    for prefix, aliases in _MODEL_FAMILY_PREFIXES.items():
        family = prefix.removesuffix("-")
        if suffix.startswith(prefix) or (runtime_family == family and suffix in aliases):
            return family
    return None
