"""Settings section of the learning module: typed view and section validators (settings spec §B.8.3)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from skm.kernel.json_types import JsonValue
from skm.platform.config.registry import SectionValidatorFn

from .generated.settings import LearningSettings

__all__ = ["SECTION_URN", "SECTION_URNS", "VALIDATORS", "VIEWS", "LearningSettings"]

SECTION_URN = "urn:skm:settings:learning:v1"
SECTION_URNS = (SECTION_URN,)


def _thresholds_order(values: Mapping[str, JsonValue]) -> str | None:
    """deprecate < candidate_min_conf <= curated_min_conf; min_n_floor <= candidate_min_n <= curated_min_n."""
    prefix = "learning.thresholds."
    names = (
        "deprecate_conf",
        "candidate_min_conf",
        "curated_min_conf",
        "candidate_min_n_floor",
        "candidate_min_n",
        "curated_min_n",
    )
    found = {name: values[prefix + name] for name in names}
    if any(value is None for value in found.values()):
        return None
    number = {name: cast("float", value) for name, value in found.items()}
    if not number["deprecate_conf"] < number["candidate_min_conf"]:
        return "learning.thresholds.deprecate_conf must be below candidate_min_conf"
    if not number["candidate_min_conf"] <= number["curated_min_conf"]:
        return "learning.thresholds.candidate_min_conf must not exceed curated_min_conf"
    if not number["candidate_min_n_floor"] <= number["candidate_min_n"]:
        return "learning.thresholds.candidate_min_n_floor must not exceed candidate_min_n"
    if not number["candidate_min_n"] <= number["curated_min_n"]:
        return "learning.thresholds.candidate_min_n must not exceed curated_min_n"
    return None


def _pathology_order(values: Mapping[str, JsonValue]) -> str | None:
    """pathology_min_hits <= pathology_window."""
    hits = values["learning.detectors.pathology_min_hits"]
    window = values["learning.detectors.pathology_window"]
    if hits is None or window is None:
        return None
    if cast("int", hits) > cast("int", window):
        return "learning.detectors.pathology_min_hits must not exceed pathology_window"
    return None


VIEWS: Mapping[str, type] = {"learning": LearningSettings}
VALIDATORS: Mapping[str, SectionValidatorFn] = {
    "learning.thresholds_order": _thresholds_order,
    "learning.pathology_order": _pathology_order,
}
