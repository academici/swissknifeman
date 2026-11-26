"""Settings section of the artifacts module: typed view and section validators (settings spec §B.8.3)."""

from __future__ import annotations

from collections.abc import Mapping

from skm.platform.config.registry import SectionValidatorFn

from .generated.settings import ArtifactsSettings

__all__ = ["SECTION_URN", "SECTION_URNS", "VALIDATORS", "VIEWS", "ArtifactsSettings"]

SECTION_URN = "urn:skm:settings:artifacts:v1"
SECTION_URNS = (SECTION_URN,)
VIEWS: Mapping[str, type] = {"artifacts": ArtifactsSettings}
VALIDATORS: Mapping[str, SectionValidatorFn] = {}  # the section declares no cross-key validator
