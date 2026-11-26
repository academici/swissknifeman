"""Execution events must pass the kernel's unchanged secret-field admission guard."""

from skm.kernel.events import DomainEvent
from skm.platform.schema.registry import SchemaRegistry


def test_execution_event_schemas_have_no_secret_bearing_reference_closure() -> None:
    registry = SchemaRegistry.load_default()
    event_urns = [urn for urn in registry.urns() if urn.startswith("urn:skm:execution:event:")]
    assert event_urns
    for urn in event_urns:
        declaration = type(
            "ExecutionEventContract", (DomainEvent,), {"event_type": urn, "stream_kind": "run"}
        )
        declaration.validate_registration(registry)
