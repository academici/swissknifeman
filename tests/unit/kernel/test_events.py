"""Event metadata, both feeds and pre-commit payload validation."""

import json
from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, ClassVar, cast, override
from uuid import UUID

import pytest

from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.events import STREAM_KINDS, DomainEvent, EventEnvelope
from skm.kernel.generated.events import event_envelope_doc_from_json, event_envelope_doc_to_json
from skm.kernel.ids import EventId, PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.integrations.generated.documents import (
    webhook_delivery_from_json,
    webhook_delivery_to_json,
)
from skm.modules.workspace.generated.events import WorkspaceCreated as WorkspaceCreatedPayload
from skm.platform.schema.registry import SchemaRegistry

ID = UUID("0191e2a4-7c3f-7b21-8a54-3f6d2c1b9e07")
NOW = datetime(2026, 10, 27, 15, 0, 1, 123456, tzinfo=UTC)
WORKSPACE_ID = WorkspaceId(ID)
URN = "urn:skm:workspace:event:workspace-created:v1"
ENVELOPE = "urn:skm:kernel:event-envelope:v1"


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


@dataclass(frozen=True, slots=True)
class WorkspaceCreated(DomainEvent):
    event_type: ClassVar[str] = URN
    stream_kind: ClassVar[str] = "workspace"
    workspace_id: WorkspaceId = WORKSPACE_ID

    @override
    def stream_id(self) -> UUID:
        return self.workspace_id

    @override
    def scope_workspace_id(self) -> WorkspaceId | None:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return WorkspaceCreatedPayload(self.workspace_id, "demo", "Demo").to_json()


def envelope(**changes: Any) -> EventEnvelope:
    values: dict[str, Any] = {
        "id": EventId(ID),
        "type": URN,
        "schema_version": 1,
        "workspace_id": WorkspaceId(ID),
        "stream_kind": "workspace",
        "stream_id": ID,
        "stream_seq": 3,
        "workspace_seq": 7,
        "global_position": None,
        "actor_id": PrincipalId(ID),
        "request_id": "req_child",
        "correlation_id": "req_root",
        "causation_id": "req_child",
        "parent_causation_id": "parent_event_or_request",
        "occurred_at": NOW,
        "recorded_at": NOW + timedelta(seconds=1),
        "payload": WorkspaceCreated().payload(),
    }
    values.update(changes)
    return EventEnvelope(**values)


def test_round_trip_preserves_independent_causal_metadata(registry: SchemaRegistry) -> None:
    event = envelope()
    document = event.to_json()
    assert document["causation_id"] == document["request_id"] == "req_child"
    assert document["parent_causation_id"] == "parent_event_or_request"
    assert document["correlation_id"] == "req_root"
    assert document["occurred_at"] == "2026-10-27T15:00:01.123456Z"
    assert document["actor_id"] == str(ID)
    assert EventEnvelope.from_json(json.loads(json.dumps(document))) == event
    event.validate(registry)
    assert registry.validate(ENVELOPE, document) == ()
    with pytest.raises(FrozenInstanceError):
        event.correlation_id = "replacement"  # type: ignore[misc]


@pytest.mark.parametrize("parent", [None, "", "p" * 64])
def test_parent_is_nullable_and_bounded(parent: str | None, registry: SchemaRegistry) -> None:
    event = envelope(parent_causation_id=parent)
    assert EventEnvelope.from_json(event.to_json()).parent_causation_id == parent
    assert registry.validate(ENVELOPE, event.to_json()) == ()
    assert event_envelope_doc_to_json(event_envelope_doc_from_json(event.to_json())) == event.to_json()


def test_omitted_parent_reads_as_none_without_reconstructing_it(registry: SchemaRegistry) -> None:
    document = envelope().to_json()
    del document["parent_causation_id"]
    assert registry.validate(ENVELOPE, document) == ()
    assert event_envelope_doc_to_json(event_envelope_doc_from_json(document)) == document
    assert "parent_causation_id" not in cast("list[str]", registry.get(ENVELOPE)["required"])
    event = EventEnvelope.from_json(document)
    assert event.parent_causation_id is None
    assert event.causation_id == "req_child"
    assert replace(event, parent_causation_id=None) == event


@pytest.mark.parametrize("name", ["request_id", "correlation_id", "causation_id", "parent_causation_id"])
def test_causal_id_length_boundary(name: str, registry: SchemaRegistry) -> None:
    document = envelope(**{name: "x" * 64}).to_json()
    assert registry.validate(ENVELOPE, document) == ()
    document[name] = "x" * 65
    assert registry.validate(ENVELOPE, document)
    with pytest.raises(ValueError, match=name):
        EventEnvelope.from_json(document)
    with pytest.raises(ValueError, match=name):
        envelope(**{name: "x" * 65})


@pytest.mark.parametrize("kind", sorted(STREAM_KINDS))
def test_canonical_stream_kinds_match_schema(kind: str, registry: SchemaRegistry) -> None:
    assert registry.validate(ENVELOPE, envelope(stream_kind=kind).to_json()) == ()
    assert (
        set(cast("dict[str, Any]", registry.get(ENVELOPE)["properties"])["stream_kind"]["enum"])
        == STREAM_KINDS
    )


def test_instance_feed_round_trip_and_generated_consumers(registry: SchemaRegistry) -> None:
    event = envelope(workspace_id=None, workspace_seq=None, global_position=19, stream_kind="host")
    document = event.to_json()
    assert registry.validate(ENVELOPE, document) == ()
    assert EventEnvelope.from_json(document) == event
    assert event_envelope_doc_to_json(event_envelope_doc_from_json(document)) == document
    delivery = {
        "schema": "urn:skm:integrations:webhook-delivery:v1",
        "delivery_id": str(ID),
        "subscription_id": "hook_demo",
        "attempt": 1,
        "sent_at": document["recorded_at"],
        "event": document,
    }
    registry.require_valid("urn:skm:integrations:webhook-delivery:v1", delivery)
    assert webhook_delivery_to_json(webhook_delivery_from_json(delivery)) == delivery


@pytest.mark.parametrize(
    "changes",
    [
        {"workspace_id": None},
        {"workspace_seq": None},
        {"workspace_seq": 0},
        {"global_position": 1},
        {"stream_seq": 0},
        {"stream_seq": True},
        {"workspace_id": None, "workspace_seq": None, "global_position": None},
        {"workspace_id": None, "workspace_seq": 1, "global_position": 1},
        {"workspace_id": None, "workspace_seq": None, "global_position": 0},
        {"workspace_id": None, "workspace_seq": None, "global_position": True},
    ],
)
def test_feed_positions_are_positive_and_never_mixed(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"seq|position"):
        envelope(**changes)
    document = envelope().to_json()
    document.update(changes)
    with pytest.raises(ValueError, match=r"seq|position"):
        EventEnvelope.from_json(document)


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "workspace.created"},
        {"type": "urn:skm:workspace:event:created:v0"},
        {"schema_version": 2},
        {"schema_version": True},
        {"stream_kind": "instance_feed"},
        {"stream_id": str(ID)},
        {"workspace_id": str(ID)},
        {"id": "bad"},
        {"actor_id": "bad"},
        {"correlation_id": ""},
        {"correlation_id": None},
        {"request_id": 1},
        {"occurred_at": NOW.replace(tzinfo=None)},
        {"recorded_at": NOW.astimezone(timezone(timedelta(hours=1)))},
        {"payload": []},
        {"payload": {"bad": float("nan")}},
        {"payload": {1: "bad"}},
        {"payload": {"nested": [{"secret": object()}]}},
    ],
)
def test_constructor_rejects_malformed_metadata_and_payload(changes: dict[str, Any]) -> None:
    with pytest.raises(
        ValueError, match=r"URN|schema_version|stream_kind|UUID|correlation_id|request_id|datetime|payload"
    ):
        envelope(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": ID},
        {"id": "invalid"},
        {"stream_id": ID.hex},
        {"actor_id": 1},
        {"occurred_at": "2026-10-27"},
        {"occurred_at": "2026-10-27T15:00:01"},
        {"recorded_at": "2026-13-27T15:00:01Z"},
        {"recorded_at": "2026-10-27T15:00:01+00:60"},
        {"recorded_at": "2026-10-27T15:00:01+24:00"},
        {"recorded_at": 1},
        {"unknown": None},
    ],
)
def test_reader_rejects_invalid_wire_documents(changes: dict[str, Any]) -> None:
    document = envelope().to_json()
    document.update(changes)
    with pytest.raises((TypeError, ValueError)):
        EventEnvelope.from_json(document)


def test_reader_checks_required_fields_and_normalizes_rfc3339_offsets() -> None:
    document = envelope().to_json()
    del document["occurred_at"]
    with pytest.raises(ValueError, match="fields"):
        EventEnvelope.from_json(document)
    document["occurred_at"] = "2026-10-27T16:00:01.123456+01:00"
    assert EventEnvelope.from_json(document).occurred_at == NOW


def test_json_conversion_does_not_alias_payload() -> None:
    event = envelope(payload={"nested": [{"key": "value"}]})
    document = cast("dict[str, Any]", event.to_json())
    document["payload"]["nested"][0]["key"] = "changed"
    assert event.payload == {"nested": [{"key": "value"}]}
    loaded = EventEnvelope.from_json(document)
    document["payload"]["nested"][0]["key"] = "changed again"
    assert loaded.payload == {"nested": [{"key": "changed"}]}


def test_domain_event_registration_and_payload_validation(registry: SchemaRegistry) -> None:
    WorkspaceCreated.validate_registration(registry)
    WorkspaceCreated().validate(registry)
    envelope().validate(registry)
    with pytest.raises(ValidationFailed):
        envelope(payload={"workspace_id": "bad", "slug": "demo", "title": "Demo"}).validate(registry)


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("event_type", None),
        ("event_type", "malformed"),
        ("event_type", "urn:skm:workspace:command:create-workspace:v1"),
        ("event_type", "urn:skm:workspace:event:workspace-created:v2"),
        ("schema_version", True),
        ("stream_kind", "unknown"),
    ],
)
def test_registration_rejects_bad_metadata_before_commit(
    attribute: str,
    value: object,
    registry: SchemaRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(WorkspaceCreated, attribute, value)
    with pytest.raises(ValueError, match=r"URN|schema_version|stream_kind"):
        WorkspaceCreated.validate_registration(registry)


def test_registration_requires_a_registered_payload_schema(
    registry: SchemaRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(WorkspaceCreated, "event_type", "urn:skm:workspace:event:unknown:v1")
    with pytest.raises(InternalError, match="unknown schema"):
        WorkspaceCreated.validate_registration(registry)


@pytest.mark.parametrize(
    ("method", "value"),
    [
        ("stream_id", "invalid"),
        ("scope_workspace_id", "invalid"),
        ("payload", {"wrong": "shape"}),
    ],
)
def test_domain_event_validation_catches_invalid_values(
    method: str,
    value: object,
    registry: SchemaRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(WorkspaceCreated, method, lambda self: value)
    with pytest.raises((ValueError, ValidationFailed)):
        WorkspaceCreated().validate(registry)


@pytest.mark.parametrize("reference_kind", ["direct", "local", "external"])
def test_secret_payload_schema_is_rejected_before_values_can_leak(
    reference_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urn = "urn:skm:demo:event:created:v1"
    secret = {"type": "string", "x-skm-secret": True}
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": urn,
        "type": "object",
        "properties": {"token": secret},
    }
    if reference_kind == "local":
        document["properties"] = {"nested": {"type": "array", "items": {"$ref": "#/$defs/value"}}}
        document["$defs"] = {"value": {"allOf": [secret]}}
    elif reference_kind == "external":
        target = "urn:skm:demo:defs:v1"
        definitions = {"$schema": document["$schema"], "$id": target, "$defs": {"value": secret}}
        (tmp_path / "demo").mkdir()
        (tmp_path / "demo/defs.v1.json").write_text(json.dumps(definitions))
        document["properties"] = {"token": {"$ref": target + "#/$defs/value"}}
    (tmp_path / "demo").mkdir(exist_ok=True)
    (tmp_path / "demo/created.v1.json").write_text(json.dumps(document))
    registry = SchemaRegistry.load(tmp_path)
    monkeypatch.setattr(WorkspaceCreated, "event_type", urn)
    with pytest.raises(ValueError, match="secret fields"):
        WorkspaceCreated.validate_registration(registry)
    with pytest.raises(ValueError, match="secret fields"):
        envelope(type=urn, payload={"token": "never-emit-this-secret"}).validate(registry)


def test_client_ids_are_preserved_as_diagnostics_without_authority() -> None:
    event = envelope(correlation_id=str(ID), causation_id="unverified", parent_causation_id=str(ID))
    assert EventEnvelope.from_json(event.to_json()) == event
    assert not hasattr(event, "verified")


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("secret", [False, True])
def test_definitions_payloads_reject_secrets_at_every_validation_entry_point(
    external: bool,
    secret: bool,
    tmp_path: Path,
    registry: SchemaRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urn = "urn:skm:demo:event:created:v1"
    target = "urn:skm:demo:defs:v1" if external else urn
    token = "plaintext-secret" if secret else "public-value"
    payload: JsonObject = {"token": token}
    definitions = {"token": {"type": "string", "x-skm-secret": secret}}
    document: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": urn,
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "token": {"$ref": (target if external else "") + "#/definitions/token"},
            "next": {"$ref": urn},  # Recursive properties must not loop during registration.
        },
        "required": ["token"],
    }
    (tmp_path / "demo").mkdir()
    if external:
        owner = {"$schema": document["$schema"], "$id": target, "definitions": definitions}
        (tmp_path / "demo/defs.v1.json").write_text(json.dumps(owner))
    else:
        document["definitions"] = definitions
    (tmp_path / "demo/created.v1.json").write_text(json.dumps(document))
    (tmp_path / "kernel").mkdir()
    for name in ("defs", "event-envelope"):
        schema = dict(registry.get(f"urn:skm:kernel:{name}:v1"))
        (tmp_path / f"kernel/{name}.v1.json").write_text(json.dumps(schema))
    schemas = SchemaRegistry.load(tmp_path)
    assert schemas.validate(urn, payload) == ()  # x-skm-secret is an annotation, not a type error.
    monkeypatch.setattr(WorkspaceCreated, "event_type", urn)
    monkeypatch.setattr(WorkspaceCreated, "payload", lambda self: payload)
    stored = envelope(type=urn)
    validators = (
        WorkspaceCreated.validate_registration,
        WorkspaceCreated().validate,
        stored.validate,
    )
    for validate in validators:
        if secret:
            with pytest.raises(ValueError, match="secret fields") as raised:
                validate(schemas)
            assert token not in str(raised.value)
        else:
            validate(schemas)
    if not secret:
        assert stored.to_json()["payload"] == payload
