"""Preset validation for projection planning and desired projection requests."""

import pytest

from skm.platform.schema.registry import SchemaRegistry

PROJECT_ID = "018f2ad0-625d-7c15-8f54-06579b062ae2"


@pytest.mark.parametrize(
    ("schema_urn", "payload"),
    [
        pytest.param(
            "urn:skm:integrations:host:plan-projection:v1",
            {"project_id": PROJECT_ID},
            id="PlanProjectionRequest",
        ),
        pytest.param(
            "urn:skm:integrations:query:get-desired-projection:v1",
            {
                "project_id": PROJECT_ID,
                "checkout_binding_id": "018f2ad0-625d-7c15-8f54-06579b062ae3",
                "target": "codex",
            },
            id="GetDesiredProjection",
        ),
    ],
)
class TestProjectionPreset:
    def test_accepts_request_without_preset(self, schema_urn: str, payload: dict[str, str]) -> None:
        assert SchemaRegistry.load_default().validate(schema_urn, payload) == ()

    @pytest.mark.parametrize("preset", ["php-project", "php-package", "dart-project", "dart-package", None])
    def test_accepts_presets(self, schema_urn: str, payload: dict[str, str], preset: str | None) -> None:
        request = {**payload, "preset": preset}
        assert SchemaRegistry.load_default().validate(schema_urn, request) == ()

    def test_rejects_unknown_preset(self, schema_urn: str, payload: dict[str, str]) -> None:
        request = {**payload, "preset": "unknown"}
        (issue,) = SchemaRegistry.load_default().validate(schema_urn, request)
        assert issue.pointer == "/preset"
        assert issue.schema_pointer == "/properties/preset/enum"
