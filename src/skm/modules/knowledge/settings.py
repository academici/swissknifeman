"""Settings section of the knowledge module: typed view and section validators (settings spec §B.8.3)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from skm.kernel.json_types import JsonValue
from skm.platform.config.registry import SectionValidatorFn

from .generated.settings import KnowledgeSettings

__all__ = ["SECTION_URN", "SECTION_URNS", "VALIDATORS", "VIEWS", "KnowledgeSettings"]

SECTION_URN = "urn:skm:settings:knowledge:v1"
SECTION_URNS = (SECTION_URN,)


def _ttl_order(values: Mapping[str, JsonValue]) -> str | None:
    """default_ttl_hours <= max_ttl_hours."""
    default = values["knowledge.memory.default_ttl_hours"]
    maximum = values["knowledge.memory.max_ttl_hours"]
    if default is None or maximum is None:
        return None
    if cast("int", default) > cast("int", maximum):
        return "knowledge.memory.default_ttl_hours must not exceed knowledge.memory.max_ttl_hours"
    return None


VIEWS: Mapping[str, type] = {"knowledge": KnowledgeSettings}
VALIDATORS: Mapping[str, SectionValidatorFn] = {"knowledge.ttl_order": _ttl_order}
