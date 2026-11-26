"""Session result (runtimes §4.7, ``urn:skm:runtimes:runtime-result:v1``) — the only result shape.

``usage`` is always present (unknown when nothing was reported, never zero). ``observation`` is optional
diagnostics: absent or null means unavailable, and older adapters/results stay valid without it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from .error_rules import ProviderFailure, failure_from_json, failure_to_json
from .observation import (
    RuntimeObservation,
    observation_from_json,
    observation_to_json,
    validate_runtime_observation,
)
from .usage import UsageReport, usage_from_json, usage_to_json

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.runtimes.domain.ids import ModelId, SessionRef
    from skm.modules.runtimes.domain.session_events import Violation

__all__ = [
    "ExitInfo",
    "RuntimeResult",
    "ToolDenial",
    "result_from_json",
    "result_to_json",
    "validate_result_observation",
]


@dataclass(frozen=True, slots=True)
class ExitInfo:
    exit_code: int | None
    signal: str | None
    output_truncated: bool
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ToolDenial:
    tool: str  # tool name and a safe hint, never arguments
    hint: str


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    outcome: Literal["completed", "failed", "cancelled"]
    final_text: str  # raw final answer before repair; "" when failed
    structured: JsonValue | None  # parsed JSON when the runtime returned it structurally
    session_ref: SessionRef | None
    model: ModelId | None  # model reported by the runtime, else None (never the resolved route)
    usage: UsageReport
    failure: ProviderFailure | None  # outcome in {failed, cancelled}
    exit: ExitInfo
    lingered: bool  # stopped after a full answer by result_grace
    denials: tuple[ToolDenial, ...]
    api_retries: int
    transcript_path: str | None
    stderr_path: str | None
    observation: RuntimeObservation | None = None  # §4.7.1; absent/None = unavailable

    def __post_init__(self) -> None:
        if not isinstance(self.usage, UsageReport):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("usage is always a UsageReport (status unknown when nothing was reported)")
        if self.outcome == "completed":
            if self.failure is not None:
                raise ValueError("a completed result has no failure")
        elif self.outcome in ("failed", "cancelled"):
            if self.failure is None:
                raise ValueError(f"a {self.outcome} result carries its failure")
            # cancelled <=> the terminal failed with SESSION_CANCELLED or CANCEL_IGNORED.
            if self.failure.cancelled != (self.outcome == "cancelled"):
                raise ValueError("outcome cancelled goes with exactly SESSION_CANCELLED or CANCEL_IGNORED")
        else:
            raise ValueError(f"unknown outcome {self.outcome!r}")
        if isinstance(self.api_retries, bool) or self.api_retries < 0:
            raise ValueError("api_retries must be a non-negative int")


def validate_result_observation(result: RuntimeResult, *, request_id: UUID) -> tuple[Violation, ...]:
    """Check the optional observation against its step and ``RuntimeResult.model``; absent is fine."""
    if result.observation is None:
        return ()
    return validate_runtime_observation(
        result.observation, request_id=request_id, provider_reported_model=result.model
    )


def result_to_json(result: RuntimeResult) -> JsonObject:
    data: JsonObject = {
        "outcome": result.outcome,
        "final_text": result.final_text,
        "structured": result.structured,
        "session_ref": result.session_ref,
        "model": result.model,
        "usage": usage_to_json(result.usage),
        "failure": None if result.failure is None else failure_to_json(result.failure),
        "exit": {
            "exit_code": result.exit.exit_code,
            "signal": result.exit.signal,
            "output_truncated": result.exit.output_truncated,
            "duration_ms": result.exit.duration_ms,
        },
        "lingered": result.lingered,
        "denials": [{"tool": denial.tool, "hint": denial.hint} for denial in result.denials],
        "api_retries": result.api_retries,
        "transcript_path": result.transcript_path,
        "stderr_path": result.stderr_path,
    }
    if result.observation is not None:
        data["observation"] = observation_to_json(result.observation)
    return data


def _object(value: JsonValue, name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    return value


def result_from_json(data: Mapping[str, JsonValue]) -> RuntimeResult:
    """Decode a schema-shaped result; a missing or null ``observation`` decodes to None (unavailable)."""
    failure = data["failure"]
    exit_info = _object(data["exit"], "exit")
    denials = data["denials"]
    if not isinstance(denials, list):
        raise TypeError("denials must be a list")
    observation = data.get("observation")
    return RuntimeResult(
        outcome=cast("Literal['completed', 'failed', 'cancelled']", data["outcome"]),
        final_text=cast("str", data["final_text"]),
        structured=data["structured"],
        session_ref=cast("str | None", data["session_ref"]),
        model=cast("str | None", data["model"]),
        usage=usage_from_json(_object(data["usage"], "usage")),
        failure=None if failure is None else failure_from_json(_object(failure, "failure")),
        exit=ExitInfo(
            exit_code=cast("int | None", exit_info["exit_code"]),
            signal=cast("str | None", exit_info["signal"]),
            output_truncated=cast("bool", exit_info["output_truncated"]),
            duration_ms=cast("int", exit_info["duration_ms"]),
        ),
        lingered=cast("bool", data["lingered"]),
        denials=tuple(
            ToolDenial(tool=cast("str", item["tool"]), hint=cast("str", item["hint"]))
            for item in (_object(entry, "denial") for entry in denials)
        ),
        api_retries=cast("int", data["api_retries"]),
        transcript_path=cast("str | None", data["transcript_path"]),
        stderr_path=cast("str | None", data["stderr_path"]),
        observation=None
        if observation is None
        else observation_from_json(_object(observation, "observation")),
    )
