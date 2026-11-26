"""Declarative contract; behavior belongs to the owning implementation leaf."""

__all__ = ["EVENT_TYPES"]

EVENT_TYPES = (
    "urn:skm:workspace:event:checkout-binding-verified:v1",
    "urn:skm:workspace:event:checkout-bound:v1",
    "urn:skm:workspace:event:host-registered:v1",
    "urn:skm:workspace:event:project-archived:v1",
    "urn:skm:workspace:event:project-created:v1",
    "urn:skm:workspace:event:repository-attached:v1",
    "urn:skm:workspace:event:repository-detached:v1",
    "urn:skm:workspace:event:repository-registered:v1",
    "urn:skm:workspace:event:worker-registered:v1",
    "urn:skm:workspace:event:worker-state-changed:v1",
    "urn:skm:workspace:event:workspace-archived:v1",
    "urn:skm:workspace:event:workspace-created:v1",
)
