"""Settings section of the exports module: typed view and section validators (settings spec §B.8.3)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from skm.kernel.json_types import JsonValue
from skm.platform.config.registry import SectionValidatorFn

from .generated.settings import ExportsSettings

__all__ = ["SECTION_URN", "SECTION_URNS", "VALIDATORS", "VIEWS", "ExportsSettings"]

SECTION_URN = "urn:skm:settings:exports:v1"
SECTION_URNS = (SECTION_URN,)


def _notes_ttl_order(values: Mapping[str, JsonValue]) -> str | None:
    """pending_ttl_days <= retention_days."""
    pending = values["exports.notes.pending_ttl_days"]
    retention = values["exports.notes.retention_days"]
    if pending is None or retention is None:
        return None
    if cast("int", pending) > cast("int", retention):
        return "exports.notes.pending_ttl_days must not exceed exports.notes.retention_days"
    return None


VIEWS: Mapping[str, type] = {"exports": ExportsSettings}
VALIDATORS: Mapping[str, SectionValidatorFn] = {"exports.notes_ttl_order": _notes_ttl_order}
