"""Skill invocation metadata and compatibility of the P00 schema additions."""

from copy import deepcopy
from pathlib import Path

import pytest
from tools.schema_check import compatibility, entries

from skm.platform.schema.registry import SchemaRegistry

SKILL_MANIFEST_URN = "urn:skm:extensions:skill-manifest:v1"
PLAN_PROJECTION_URN = "urn:skm:integrations:host:plan-projection:v1"
LEGACY_MANIFEST = {"schema": SKILL_MANIFEST_URN, "key": "review", "version": "1.0.0"}


def test_p00_schema_additions_are_backward_compatible() -> None:
    current = entries(Path(__file__).resolve().parents[3])
    previous = deepcopy(current)
    for urn, field in ((SKILL_MANIFEST_URN, "invocation"), (PLAN_PROJECTION_URN, "preset")):
        snapshot = previous[urn]["snapshot"]
        # Reconstruct the pre-P00 input shape even after schema-lock is refreshed.
        del snapshot["properties"][field]
        if field in snapshot["required"]:
            snapshot["required"].remove(field)

    breaking = [change for change in compatibility(previous, current) if change["breaking"]]
    assert breaking == []


def test_legacy_skill_manifest_is_valid() -> None:
    assert SchemaRegistry.load_default().validate(SKILL_MANIFEST_URN, LEGACY_MANIFEST) == ()


@pytest.mark.parametrize(
    "invocation",
    [{}, {"user_only": True, "argument_hint": "<path>", "display_name": "Review"}],
)
def test_skill_manifest_accepts_invocation(invocation: dict[str, object]) -> None:
    manifest = {**LEGACY_MANIFEST, "invocation": invocation}
    assert SchemaRegistry.load_default().validate(SKILL_MANIFEST_URN, manifest) == ()


def test_skill_invocation_rejects_unknown_keys() -> None:
    manifest = {**LEGACY_MANIFEST, "invocation": {"user_only": True, "unknown": "value"}}
    (issue,) = SchemaRegistry.load_default().validate(SKILL_MANIFEST_URN, manifest)
    assert issue.schema_pointer == "/properties/invocation/additionalProperties"
