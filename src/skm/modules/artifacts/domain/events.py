"""Declarative contract; behavior belongs to the owning implementation leaf."""

__all__ = ["EVENT_TYPES"]

EVENT_TYPES = (
    "urn:skm:artifacts:event:file-added:v1",
    "urn:skm:artifacts:event:file-restored:v1",
    "urn:skm:artifacts:event:file-trashed:v1",
    "urn:skm:artifacts:event:file-version-added:v1",
)
