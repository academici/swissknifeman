"""Code-owned metadata projections and isolated context (kernel-platform §3.4).

Adding a projection is a source change: never infer it from a DTO, a suffix or a caller's schema.
Unknown events/operations retain only the validated common envelope. Containers and custom scalar
subclasses are never inspected, converted or serialized, including SecretValue and generated DTOs.
"""

import math
import re
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Final, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface

__all__ = ["LOG_FIELDS", "bind", "context_fields", "safe_fields", "source_fields", "valid_name"]

LOG_FIELDS: Final = (
    "ts",
    "level",
    "component",
    "event",
    "message",
    "reason_code",
    "request_id",
    "correlation_id",
    "causation_id",
    "parent_causation_id",
    "surface",
    "actor_id",
    "workspace_id",
    "project_id",
    "plan_id",
    "run_id",
    "task_id",
    "attempt_id",
    "step_id",
    "parent_step_id",
    "pid",
    "host",
)
_NAME = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_REQUEST = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_HOST = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_.-]{0,251}[A-Za-z0-9_])?")
_TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z")
_OBSERVATION_TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z")
_LEVELS = frozenset(("debug", "info", "warning", "error"))
_CODES = frozenset(code.value for code in ErrorCode)
_SURFACES = frozenset(surface.value for surface in Surface)
_IDS = frozenset(LOG_FIELDS[11:20])
_TRACE_IDS = frozenset(("request_id", "correlation_id", "causation_id", "parent_causation_id"))
_CONTEXT_NAMES = _IDS | _TRACE_IDS | {"surface"}
_CONTEXT: ContextVar[JsonObject | None] = ContextVar("skm_logging_context", default=None)
_MAX_NUMBER: Final = (1 << 53) - 1

# Initial source-owned declarations. New emitters extend these closed tables in code; a syntactically
# plausible operation or a schema discovered at runtime cannot authorize additional log metadata.
_OPERATIONS: Final = {
    "workspace.create_project": "urn:skm:workspace:command:create-project:v1",
    "planning.publish_revision": "urn:skm:planning:command:publish-revision:v1",
    "execution.begin_stage": "urn:skm:execution:command:begin-stage:v1",
    "execution.claim_assignment": "urn:skm:execution:command:claim-assignment:v1",
    "execution.renew_lease": "urn:skm:execution:command:renew-lease:v1",
    "workspace.record_worker_heartbeat": "urn:skm:workspace:command:record-worker-heartbeat:v1",
    "settings.get_host_config": "urn:skm:settings:query:get-host-config:v1",
    "settings.set_value": "urn:skm:settings:command:set-value:v1",
    "settings.unset_value": "urn:skm:settings:command:unset-value:v1",
    "settings.remove_value": "urn:skm:settings:command:remove-value:v1",
    "settings.lock_value": "urn:skm:settings:command:lock-value:v1",
    "settings.unlock_value": "urn:skm:settings:command:unlock-value:v1",
    "settings.import_config": "urn:skm:settings:command:import-config:v1",
    "settings.get_value": "urn:skm:settings:query:get-value:v1",
    "settings.get_schema": "urn:skm:settings:query:get-schema:v1",
    "settings.get_generation": "urn:skm:settings:query:get-generation:v1",
    "settings.explain_config": "urn:skm:settings:query:explain-config:v1",
    "settings.list_entries": "urn:skm:settings:query:list-entries:v1",
    "settings.export_config": "urn:skm:settings:query:export-config:v1",
    "settings.get_history": "urn:skm:settings:query:get-history:v1",
    "runtimes.host.detect_runtimes": "urn:skm:runtimes:host:detect-runtimes:v1",
}
_EVENT_FIELDS: Final = {
    "bus.command.started": {"command", "operation", "schema_urn", "duration_ms", "code"},
    "bus.command.completed": {"command", "operation", "duration_ms", "code", "result_digest"},
    "bus.command.failed": {"command", "operation", "duration_ms", "code", "error.type"},
    "bus.query.failed": {"code", "error.type"},
    "api.request.failed": {"code", "error.type"},
    "uow.commit.retry": {"count", "duration_ms", "code", "error.type"},
    "relay.delivery.failed": {"event_id", "count", "duration_ms", "code", "error.type"},
    "worker.stage.failed": {"duration_ms", "code", "error.type"},
    "worker.heartbeat.observed": {"observed_at", "operation", "host_id", "worker_id"},
    "policy.denied": {"code", "error.type"},
    "stage.completed": {"stage", "passed", "duration_ms", "digest", "code"},
    "config.resolved": {"generation", "digest", "keys_count"},
    "adapters.postgres.sql": {"statement", "rows", "duration_ms"},
    "platform.process.run": {"operation", "exit_code", "duration_ms", "timed_out"},
}
_FAILURES: Final = {
    "bus.command.failed": "INTERNAL_ERROR",
    "bus.query.failed": "INTERNAL_ERROR",
    "api.request.failed": "INTERNAL_ERROR",
    "worker.stage.failed": "INTERNAL_ERROR",
    "policy.denied": "FORBIDDEN",
}
_ENUMS: Final = {
    "stage": frozenset(
        (
            "prepare_environment",
            "agent_step",
            "run_checks",
            "agent_review",
            "advisor_consult",
            "human_gate",
            "acceptance_gate",
            "phase_gate",
            "plan_acceptance",
            "integrate",
        )
    ),
    "statement": frozenset(("get", "save", "list")),
    "error.type": frozenset(
        (
            "Exception",
            "SkmError",
            "ValueError",
            "TypeError",
            "RuntimeError",
            "OSError",
            "TimeoutError",
            "KeyError",
            "AssertionError",
        )
    ),
}
_MESSAGES: Final = {
    "bus.command.started": "Command started",
    "bus.command.completed": "Command completed",
    "bus.command.failed": "Command failed",
}
_SENSITIVE = re.compile(
    r"(?i)(secret|password|token|credential|private|content|prompt|payload|argv|cwd|traceback)"
)


def valid_name(value: object) -> bool:
    return type(value) is str and len(value) <= 128 and _NAME.fullmatch(value) is not None


def source_fields(fields: Mapping[str, object], *, schema: Mapping[str, JsonValue]) -> dict[str, object]:
    """Mask schema-marked properties before passing keyword fields to a logger.

    This is not a schema-driven projection: safe_fields still applies the code-owned allowlist. Direct
    property declarations are accepted here; referenced/composed schemas must first be resolved by their
    owner. Unresolved declarations fail closed, including the entire source root.
    """

    def hidden(declaration: Mapping[str, JsonValue]) -> bool:
        return declaration.get("x-skm-secret") is True or any(
            key in declaration for key in ("$ref", "allOf", "anyOf", "oneOf", "if", "then", "else")
        )

    if hidden(schema):
        return {}
    properties = schema.get("properties")
    if type(properties) is not dict:
        return {}
    result: dict[str, object] = {}
    for name, value in fields.items():
        declaration = properties.get(name)
        if type(declaration) is dict and not hidden(declaration) and not _SENSITIVE.search(name):
            result[name] = value
    return result


def _string(value: object) -> str | None:
    if type(value) is str:
        return value
    if type(value) in (ErrorCode, Surface):
        return cast(ErrorCode | Surface, value).value
    return None


def _common(name: str, value: object) -> JsonValue:
    text = _string(value)
    if name in _IDS | _TRACE_IDS:
        return _identifier(value, request=name in _TRACE_IDS)
    if name in {"component", "event"} and valid_name(value):
        return text
    if name == "level" and text in _LEVELS:
        return text
    if name == "surface" and text in _SURFACES:
        return text
    if name == "pid" and type(value) is int and 0 < value < (1 << 31):
        return value
    if name == "host" and text is not None and _HOST.fullmatch(text):
        return text
    if name == "ts":
        return _timestamp(text)
    return None


def _timestamp(text: str | None, pattern: re.Pattern[str] = _TS) -> str | None:
    if text is not None and pattern.fullmatch(text):
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return text
    return None


def _identifier(value: object, *, request: bool = False) -> str | None:
    if type(value) is UUID:
        return str(value)
    if type(value) is str:
        if _UUID.fullmatch(value):
            return value.lower()
        if request and _REQUEST.fullmatch(value):
            return value
    return None


def _extra(name: str, value: object, operation: str | None) -> JsonValue:
    text = _string(value)
    if name in {"command", "operation"} and text in _OPERATIONS:
        return text
    if name == "schema_urn" and operation is not None and text == _OPERATIONS[operation]:
        return text
    if name in {"code", "reason_code"} and text in _CODES:
        return text
    if name in _ENUMS and text in _ENUMS[name]:
        return text
    if name in {"digest", "result_digest"} and text is not None and _DIGEST.fullmatch(text):
        return text
    if name in {"event_id", "host_id", "worker_id"}:
        return _identifier(value)
    if name == "observed_at":
        return _timestamp(text, _OBSERVATION_TS)
    return _number(name, value)


def _number(name: str, value: object) -> JsonValue:
    if name in {"count", "passed", "rows", "generation", "keys_count"} and type(value) is int:
        return value if 0 <= value <= _MAX_NUMBER else None
    if name == "duration_ms" and type(value) in (int, float):
        number = cast(int | float, value)
        if 0 <= number <= _MAX_NUMBER and math.isfinite(number):
            return number
    if name == "exit_code" and type(value) is int and -(1 << 31) <= value < (1 << 31):
        return value
    if name == "timed_out" and type(value) is bool:
        return value
    return None


def safe_fields(event: str, fields: Mapping[str, object]) -> JsonObject:
    """Project scalars only; no DTO conversion, recursion into content or arbitrary string coercion."""
    result: JsonObject = {}
    for name in LOG_FIELDS:
        if name in fields:
            value = _common(name, fields[name])
            if value is not None or (name in _CONTEXT_NAMES and fields[name] is None):
                result[name] = value
    allowed: set[str] = _EVENT_FIELDS.get(event, set()) if valid_name(event) else set()
    operation = _string(fields.get("operation", fields.get("command")))
    if ("operation" in fields or "command" in fields) and (
        operation not in _OPERATIONS or ("command" in fields and _string(fields["command"]) != operation)
    ):
        allowed = set()
    for name in sorted(allowed):
        if name in fields and not _SENSITIVE.search(name):
            value = _extra(name, fields[name], operation)
            if value is not None:
                result[name] = value
    if event in _FAILURES:
        result["reason_code"] = (
            _extra("reason_code", fields.get("reason_code"), operation)
            or result.get("code")
            or _FAILURES[event]
        )
    if event in _MESSAGES and type(fields.get("message")) is str and fields["message"] == _MESSAGES[event]:
        result["message"] = _MESSAGES[event]
    return {
        name: result[name]
        for name in (*LOG_FIELDS, *sorted(result.keys() - set(LOG_FIELDS)))
        if name in result
    }


def context_fields() -> JsonObject:
    """Return a copy, so callers cannot mutate another task's inherited context."""
    return dict(_CONTEXT.get() or {})


@contextmanager
def bind(**fields: str | None) -> Generator[None]:
    merged = context_fields()
    for name, value in fields.items():
        if name in _CONTEXT_NAMES:
            merged[name] = _common(name, value)
    token = _CONTEXT.set(merged)
    try:
        yield
    finally:
        _CONTEXT.reset(token)
