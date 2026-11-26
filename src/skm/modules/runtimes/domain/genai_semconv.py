"""Metadata projection for an out-of-process agent invocation, using GenAI semconv v0.1.0."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from .observation import RuntimeObservation
from .usage import UsageReport, UsageStatus

GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_CACHE_READ_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_CACHE_WRITE_TOKENS = "gen_ai.usage.cache_write.input_tokens"
INVOKE_AGENT = "invoke_agent"


@dataclass(frozen=True, slots=True)
class GenAIInvocationSpan:
    name: str
    kind: Literal["CLIENT"]
    attributes: Mapping[str, str | int]


def agent_invocation_span(
    observation: RuntimeObservation,
    *,
    provider: str,
    agent_name: str | None = None,
    request_model: str | None = None,
    usage: UsageReport | None = None,
    error_type: str | None = None,
) -> GenAIInvocationSpan:
    """Map captured facts; the caller supplies the provider and any trusted request metadata."""
    attrs: dict[str, str | int] = {
        GEN_AI_OPERATION_NAME: INVOKE_AGENT,
        GEN_AI_PROVIDER_NAME: provider,
        "skm.runtime.id": observation.binding.runtime_id,
        "skm.capture.coverage": observation.capture.coverage,
    }
    optional = (
        (GEN_AI_AGENT_NAME, agent_name),
        (GEN_AI_REQUEST_MODEL, request_model),
        (GEN_AI_RESPONSE_MODEL, observation.binding.provider_reported_model),
        ("error.type", error_type),
        ("skm.capture.duration_ms", observation.timing.duration_ms),
        ("skm.tools.observed_calls", observation.tools.observed_calls),
    )
    attrs.update({key: value for key, value in optional if value is not None})
    if usage is not None and usage.status is UsageStatus.REPORTED:
        if usage.input_tokens is not None:
            # SKM tracks fresh input and cache buckets separately; OTel input includes all three.
            attrs[GEN_AI_INPUT_TOKENS] = min(
                2**63 - 1,
                usage.input_tokens + (usage.cache_read_tokens or 0) + (usage.cache_write_tokens or 0),
            )
        if usage.output_tokens is not None:
            attrs[GEN_AI_OUTPUT_TOKENS] = usage.output_tokens
        if usage.cache_read_tokens:
            attrs[GEN_AI_CACHE_READ_TOKENS] = usage.cache_read_tokens
        if usage.cache_write_tokens:
            attrs[GEN_AI_CACHE_WRITE_TOKENS] = usage.cache_write_tokens
    name = f"{INVOKE_AGENT} {agent_name}" if agent_name else INVOKE_AGENT
    return GenAIInvocationSpan(name, "CLIENT", MappingProxyType(attrs))
