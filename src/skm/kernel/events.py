"""Pure event contracts (kernel-platform §2.9, conventions §4.0.1).

Validation receives a schema registry explicitly; counters, clocks and causal metadata assignment
belong to the UoW. Diagnostic identifiers never establish authority or a verified causal edge.
"""

import math
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Final, Protocol, Self, cast
from uuid import UUID

from skm.kernel.ids import EventId, PrincipalId, WorkspaceId, parse_uuid
from skm.kernel.json_types import JsonObject, JsonValue

__all__ = ["STREAM_KINDS", "DomainEvent", "EventEnvelope"]

# Closed set of ``stream_kind`` values (conventions §4.0.1).
STREAM_KINDS: Final = frozenset(
    {
        "principal",
        "config",
        "workspace",
        "project",
        "host",
        "file",
        "pack",
        "intent",
        "runtime",
        "plan",
        "run",
        "projection",
        "hook_delivery",
        "memory",
        "lesson",
        "candidate",
        "vault_note",
    }
)

_EVENT_TYPE: Final = re.compile(r"urn:skm:[a-z][a-z0-9-]*:event:[a-z][a-z0-9-]*:v([1-9][0-9]*)")
_TIMESTAMP: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt](?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


class _EventSchemas(Protocol):
    def get(self, urn: str) -> Mapping[str, JsonValue]: ...
    def require_valid(self, urn: str, instance: object) -> None: ...


def _metadata(event_type: object, version: object, stream_kind: object) -> None:
    match = _EVENT_TYPE.fullmatch(event_type) if isinstance(event_type, str) else None
    if match is None:
        raise ValueError("event type must be a canonical event URN")
    _positive(version, "schema_version")
    if version != int(match[1]):
        raise ValueError("schema_version must match the event URN major")
    if not isinstance(stream_kind, str) or stream_kind not in STREAM_KINDS:
        raise ValueError("unknown stream_kind")


def _positive(value: object, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _uuid(value: object, name: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, UUID):
        raise ValueError(f"{name} must be a UUID")


def _json(value: object) -> None:
    """Reject non-JSON values without including potentially sensitive contents in the error."""
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, list):
        for child in cast("list[object]", value):
            _json(child)
        return
    if isinstance(value, dict):
        for key, child in cast("dict[object, object]", value).items():
            if not isinstance(key, str):
                raise ValueError("payload keys must be strings")
            _json(child)
        return
    raise ValueError("payload must contain only finite JSON values")


def _payload(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("payload must be a JSON object")
    _json(cast("dict[str, object]", value))


def _payload_schema(registry: _EventSchemas, urn: str) -> None:
    """Event schemas must not declare secret-bearing fields, including through references.

    Reject the declaration before validating values, so a secret never appears in an error or event.
    A secret reference without x-skm-secret is ordinary JSON, not a resolved secret value.
    """
    seen: set[str] = set()

    def reference(ref: str, base: str) -> None:
        target = ref.partition("#")[0]
        target = target or base
        if target in seen:
            return
        seen.add(target)
        # The registry owns reference/fragment validation. Inspect the entire schema document,
        # including definitions, so secret-bearing declarations cannot enter the event contract.
        visit(registry.get(target), target)

    def visit(node: Any, base: str) -> None:
        if not isinstance(node, Mapping):
            return
        schema = cast("Mapping[str, Any]", node)
        if schema.get("x-skm-secret") is True:
            raise ValueError("event payload schemas must not contain secret fields")
        for keyword in ("$ref", "$dynamicRef"):
            if keyword in schema:
                reference(schema[keyword], base)
        for keyword in ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas"):
            for child in schema.get(keyword, {}).values():
                visit(child, base)
        for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
            for child in schema.get(keyword, []):
                visit(child, base)
        for keyword in (
            "items",
            "contains",
            "additionalProperties",
            "unevaluatedProperties",
            "unevaluatedItems",
            "propertyNames",
            "not",
            "if",
            "then",
            "else",
        ):
            if keyword in schema:
                visit(schema[keyword], base)

    reference(urn, urn)


class DomainEvent(ABC):
    """Base of module events. Subclasses are ``@dataclass(frozen=True, slots=True)``."""

    __slots__ = ()

    event_type: ClassVar[str]  # "urn:skm:<module>:event:<noun-verbed>:v1"
    stream_kind: ClassVar[str]  # one of STREAM_KINDS
    schema_version: ClassVar[int] = 1

    @abstractmethod
    def stream_id(self) -> UUID: ...

    @abstractmethod
    def scope_workspace_id(self) -> WorkspaceId | None: ...

    @abstractmethod
    def payload(self) -> JsonObject:
        """Payload shaped by ``event_type``; validate before recording and before commit."""
        ...

    @classmethod
    def validate_registration(cls, registry: _EventSchemas) -> None:
        """Fail at registry build time for missing/malformed metadata or unsafe payload schemas."""
        _metadata(getattr(cls, "event_type", None), cls.schema_version, getattr(cls, "stream_kind", None))
        _payload_schema(registry, cls.event_type)

    def validate(self, registry: _EventSchemas) -> None:
        """Reusable pre-commit validation for UoW implementations."""
        self.validate_registration(registry)
        _uuid(self.stream_id(), "stream_id")
        _uuid(self.scope_workspace_id(), "workspace_id", nullable=True)
        payload = self.payload()
        _payload(payload)
        registry.require_valid(self.event_type, payload)


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Committed event as stored in ``skm_core.domain_events`` (``urn:skm:kernel:event-envelope:v1``)."""

    id: EventId
    type: str
    schema_version: int
    workspace_id: WorkspaceId | None
    stream_kind: str
    stream_id: UUID
    stream_seq: int
    workspace_seq: int | None  # workspace feed only
    global_position: int | None  # instance feed only
    actor_id: PrincipalId | None
    request_id: str | None  # request that produced the event
    correlation_id: str  # = meta.correlation_id of the command (root of the chain)
    causation_id: str | None  # = meta.request_id of the command (immediate cause)
    occurred_at: datetime  # command clock
    recorded_at: datetime  # database now() at insert
    payload: JsonObject
    parent_causation_id: str | None = None  # = meta.causation_id; old envelopes omit it

    def __post_init__(self) -> None:
        _metadata(self.type, self.schema_version, self.stream_kind)
        for name in ("id", "stream_id", "workspace_id", "actor_id"):
            _uuid(getattr(self, name), name, nullable=name in ("workspace_id", "actor_id"))
        _positive(self.stream_seq, "stream_seq")
        if self.workspace_id is None:
            if self.workspace_seq is not None:
                raise ValueError("instance events cannot have workspace_seq")
            _positive(self.global_position, "global_position")
        else:
            if self.global_position is not None:
                raise ValueError("workspace events cannot have global_position")
            _positive(self.workspace_seq, "workspace_seq")
        for name in ("request_id", "correlation_id", "causation_id", "parent_causation_id"):
            value = getattr(self, name)
            if value is None and name != "correlation_id":
                continue
            if not isinstance(value, str) or len(value) > 64 or (name == "correlation_id" and not value):
                raise ValueError(f"{name} must be a string of at most 64 characters")
        for name in ("occurred_at", "recorded_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must be an aware UTC datetime")
        _payload(self.payload)

    def validate(self, registry: _EventSchemas) -> None:
        """Validate the stored shape and registered payload before persistence/delivery."""
        _payload_schema(registry, self.type)
        registry.require_valid("urn:skm:kernel:event-envelope:v1", self.to_json())
        registry.require_valid(self.type, self.payload)

    def to_json(self) -> JsonObject:
        self.__post_init__()
        result: JsonObject = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, UUID):
                value = str(value)
            elif isinstance(value, datetime):
                value = value.isoformat().replace("+00:00", "Z")
            result[field.name] = deepcopy(value)
        return result

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        """Read historical envelopes without synthesizing causal metadata or feed positions."""
        known = {field.name for field in fields(cls)}
        required = {
            "id",
            "type",
            "schema_version",
            "stream_kind",
            "stream_id",
            "stream_seq",
            "correlation_id",
            "occurred_at",
            "recorded_at",
            "payload",
        }
        if set(data) - known or required - set(data):
            raise ValueError("invalid envelope fields")
        values: dict[str, Any] = dict.fromkeys(known)
        values.update(deepcopy(data))
        for name in ("id", "stream_id", "workspace_id", "actor_id"):
            value = values[name]
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(f"{name} must be UUID text")
                values[name] = parse_uuid(value)
        for name in ("occurred_at", "recorded_at"):
            value = values[name]
            if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
                raise ValueError(f"{name} must be an RFC 3339 timestamp")
            values[name] = datetime.fromisoformat(value.upper()).astimezone(UTC)
        return cls(**values)
