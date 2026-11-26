"""Settings section of the access module: typed view and section validators (settings spec §B.8.3)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from skm.kernel.json_types import JsonValue
from skm.platform.config.registry import SectionValidatorFn

from .generated.settings import AccessSettings

__all__ = ["SECTION_URN", "SECTION_URNS", "VALIDATORS", "VIEWS", "AccessSettings"]

SECTION_URN = "urn:skm:settings:access:v1"
SECTION_URNS = (SECTION_URN,)


def _ttl_bounds(values: Mapping[str, JsonValue]) -> str | None:
    """max_ttl_days == 0 or (default_ttl_days != 0 and default_ttl_days <= max_ttl_days)."""
    default = values["access.tokens.default_ttl_days"]
    maximum = values["access.tokens.max_ttl_days"]
    if default is None or maximum is None:
        return None
    if cast("int", maximum) == 0:
        return None
    if cast("int", default) == 0:
        return "access.tokens.default_ttl_days must not be 0 (no expiry) while max_ttl_days limits tokens"
    if cast("int", default) > cast("int", maximum):
        return "access.tokens.default_ttl_days must not exceed access.tokens.max_ttl_days"
    return None


def _worker_rotation(values: Mapping[str, JsonValue]) -> str | None:
    """worker_rotate_before_hours * 2 <= worker_ttl_hours."""
    ttl = values["access.tokens.worker_ttl_hours"]
    rotate = values["access.tokens.worker_rotate_before_hours"]
    if ttl is None or rotate is None:
        return None
    if cast("int", rotate) * 2 > cast("int", ttl):
        return (
            "access.tokens.worker_rotate_before_hours must be at most half of access.tokens.worker_ttl_hours"
        )
    return None


VIEWS: Mapping[str, type] = {"access": AccessSettings}
VALIDATORS: Mapping[str, SectionValidatorFn] = {
    "access.ttl_bounds": _ttl_bounds,
    "access.worker_rotation": _worker_rotation,
}
