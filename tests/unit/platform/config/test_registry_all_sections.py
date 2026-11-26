"""The complete packaged registry with real owner callbacks, no permissive stubs.

``registry_inputs`` composes the same declarations bootstrap passes to the engine:
module manifests, generated views, owner validators, permissions and hookable
event schemas. An installation without event-sink plugins has an empty sink
registry; its hook callback still rejects unknown sinks and events.
"""

import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import Any, cast

import pytest

from skm.application_bus.subscribers import EventSinkRegistry
from skm.bootstrap.modules import MODULE_CATALOG
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.modules.integrations.application.subscribers import HookSubscriptionsValidator
from skm.modules.integrations.settings import validators_for
from skm.platform.config.keys import MISSING
from skm.platform.config.registry import SectionValidatorFn, SettingsRegistry
from skm.platform.config.validators import SECTION_URNS, VALIDATORS, VIEWS
from skm.platform.schema.registry import SchemaRegistry


@dataclass(frozen=True)
class RegistryInputs:
    schemas: SchemaRegistry
    urns: tuple[str, ...]
    views: Mapping[str, type]
    validators: Mapping[str, SectionValidatorFn]
    permissions: frozenset[str]

    def build(self, **changes: Any) -> SettingsRegistry:
        kwargs: dict[str, Any] = {
            "views": self.views,
            "validators": self.validators,
            "known_permissions": self.permissions,
        }
        kwargs.update(changes)
        return SettingsRegistry.build(self.schemas, self.urns, **kwargs)


@cache
def registry_inputs() -> RegistryInputs:
    schemas = SchemaRegistry.load_default()
    urn_by_section = {
        cast("Mapping[str, Any]", schemas.get(urn)["x-skm-section"])["id"]: urn
        for urn in schemas.urns()
        if "x-skm-section" in schemas.get(urn)
    }
    views, callbacks = dict(VIEWS), dict(VALIDATORS)
    urns = list(SECTION_URNS)
    permissions: set[str] = set()
    for entry in MODULE_CATALOG:
        manifest = importlib.import_module(f"skm.modules.{entry.id}.module").MODULE
        assert manifest.settings_sections == entry.settings_sections
        permissions.update(importlib.import_module(f"skm.modules.{entry.id}.permissions").PERMISSIONS)
        if not manifest.settings_sections:
            continue
        settings = importlib.import_module(f"skm.modules.{entry.id}.settings")
        assert set(settings.VIEWS) == set(manifest.settings_sections)
        assert not set(views) & set(settings.VIEWS), entry.id
        assert not set(callbacks) & set(settings.VALIDATORS), entry.id
        views.update(settings.VIEWS)
        callbacks.update(settings.VALIDATORS)
        urns.extend(urn_by_section[section] for section in manifest.settings_sections)
    hooks = validators_for(
        hookable_types={urn for urn in schemas.urns() if schemas.get(urn).get("x-skm-hookable") is True},
        sink_ids=EventSinkRegistry(()).ids(),
    )
    assert callbacks["integrations.budget_order"] is hooks["integrations.budget_order"]
    callbacks.update(hooks)
    assert len(urns) == len(set(urns))
    assert set(urns) == set(urn_by_section.values())
    return RegistryInputs(schemas, tuple(urns), views, callbacks, frozenset(permissions))


@cache
def real_registry() -> SettingsRegistry:
    return registry_inputs().build()


def test_full_registry_builds_with_real_callbacks_and_generated_views() -> None:
    inputs = registry_inputs()
    registry = real_registry()
    assert len(registry.sections()) == 26
    assert len(registry.keys()) == len({spec.key for spec in registry.keys(chain=None)})
    expected_validators = {v.id for info in registry.sections() for v in info.validators}
    assert set(inputs.validators) == expected_validators
    for info in registry.sections():
        generated = importlib.import_module(info.view.__module__)
        assert getattr(generated, info.view.__name__) is info.view
        assert info.schema_urn == cast("Any", info.view).SCHEMA_URN
        assert info.id == cast("Any", info.view).SECTION
        assert registry.section_of_view(info.view) is info
        for validator in info.validators:
            callback = registry.validator(validator.id)
            assert callable(callback)
            owner_module = (
                "skm.platform.config.validators"
                if info.owner == "platform"
                else f"skm.modules.{info.owner}.settings"
            )
            if validator.id == "integrations.hook_subscriptions":
                assert isinstance(callback, HookSubscriptionsValidator)
                assert callback.hookable_types == frozenset(
                    urn
                    for urn in inputs.schemas.urns()
                    if inputs.schemas.get(urn).get("x-skm-hookable") is True
                )
                assert callback.sink_ids == frozenset()
            else:
                assert callback.__module__ == owner_module
            assert callback is inputs.validators[validator.id]


def test_all_defaults_validate_and_construct_all_views() -> None:
    registry = real_registry()
    values: dict[str, JsonValue] = {
        spec.key: cast("JsonValue", spec.default)
        for spec in registry.keys(chain=None)
        if spec.default is not MISSING
    }
    for spec in registry.keys(chain=None):
        if spec.default is MISSING:
            assert spec.nullable
        else:
            assert not registry.value_issues(spec.key, spec.default), spec.key
    for info in registry.sections():
        view = cast("Any", info.view).from_settings(values)
        assert isinstance(view, info.view)
        for validator in info.validators:
            own_values = {key: values.get(key) for key in validator.keys}
            assert registry.validator(validator.id)(own_values) is None, validator.id


@pytest.mark.parametrize(
    "missing", ["plugins.subsets", "integrations.hook_subscriptions", "exports.notes_ttl_order"]
)
def test_full_registry_rejects_missing_owner_callback_reg08(missing: str) -> None:
    inputs = registry_inputs()
    callbacks = {key: fn for key, fn in inputs.validators.items() if key != missing}
    with pytest.raises(InternalError) as caught:
        inputs.build(validators=callbacks)
    assert caught.value.code is ErrorCode.CONFIG_REGISTRY_INVALID
    problems = cast("list[dict[str, Any]]", caught.value.details["problems"])
    assert {item["code"] for item in problems} == {"REG-08"}
    assert any(missing in item["message"] for item in problems)


@pytest.mark.parametrize("missing", ["storage", "access", "hooks"])
def test_full_registry_requires_every_generated_view_reg15(missing: str) -> None:
    inputs = registry_inputs()
    views = {section: view for section, view in inputs.views.items() if section != missing}
    with pytest.raises(InternalError) as caught:
        inputs.build(views=views)
    problems = cast("list[dict[str, Any]]", caught.value.details["problems"])
    assert {item["code"] for item in problems} == {"REG-15"}
    assert any(item["section"] == missing for item in problems)


def test_permissions_come_from_owner_catalogs_and_are_enforced_reg19() -> None:
    registry = real_registry()
    restricted = {
        spec.key: spec.write_permission for spec in registry.keys(chain=None) if spec.write_permission
    }
    assert restricted == {"hooks.subscriptions": "hook.manage", "hooks.host.trusted": "hook.manage"}
    with pytest.raises(InternalError) as caught:
        registry_inputs().build(known_permissions=registry_inputs().permissions - {"hook.manage"})
    problems = cast("list[dict[str, Any]]", caught.value.details["problems"])
    assert {item["code"] for item in problems} == {"REG-19"}
    assert {item["key"] for item in problems} == {"hooks.subscriptions", "hooks.host.trusted"}


@pytest.mark.parametrize(
    "key",
    [
        "unknown.dead_key",
        "modules.access.enabled",
        "storage.pool.max_size",
        "api.idempotency.ttl_hours",
        "execution.scheduler.interval_ms",
    ],
)
def test_unknown_and_retired_key_fixture_is_rejected(key: str) -> None:
    registry = real_registry()
    assert registry.find(key) is None
    with pytest.raises(ValidationFailed) as caught:
        registry.value_issues(key, 1)
    assert caught.value.code is ErrorCode.CONFIG_UNKNOWN_KEY
    assert caught.value.details["key"] == key


def test_full_registry_callbacks_reject_invalid_effective_candidates() -> None:
    registry = real_registry()
    assert registry.validator("plugins.subsets")(
        {"plugins.allowed": [], "plugins.required": ["acme.kiro"], "plugins.control_plane_allowed": []}
    )
    assert registry.validator("integrations.budget_order")(
        {"integrations.budget.first_turn.target": 101, "integrations.budget.first_turn.warn": 100}
    )
    assert registry.validator("exports.notes_ttl_order")(
        {"exports.notes.pending_ttl_days": 8, "exports.notes.retention_days": 7}
    )


def test_hook_callback_uses_packaged_events_and_rejects_unknown_events_and_sinks() -> None:
    callback = real_registry().validator("integrations.hook_subscriptions")
    hook: dict[str, JsonValue] = {
        "class": "workflow",
        "kind": "webhook",
        "execution_location": "control_plane",
        "event_types": ["urn:skm:planning:event:plan-created:v1"],
        "target": {"url": "https://example.test/hook", "secret": "secret://env/HOOK_SECRET"},
    }
    assert callback({"hooks.subscriptions": {"notify": hook}}) is None
    hook["event_types"] = ["urn:skm:planning:event:unknown:v1"]
    message = callback({"hooks.subscriptions": {"notify": hook}})
    assert message
    assert "unknown_event_type" in message
    hook["event_types"] = ["urn:skm:planning:event:plan-created:v1"]
    hook["kind"] = "event_sink"
    hook["target"] = {"sink_id": "unregistered", "config": {}}
    message = callback({"hooks.subscriptions": {"notify": hook}})
    assert message
    assert "sink_not_registered" in message


def test_all_schema_refs_resolve_and_pack_view_urns_are_canonical() -> None:
    schemas = registry_inputs().schemas
    for info in real_registry().sections():
        # Loading the schema registry checks every $ref and its JSON Pointer offline.
        assert schemas.get(info.schema_urn)["$id"] == info.schema_urn
        assert info.schema_urn == f"urn:skm:settings:{info.id}:v1"
    pack_views = importlib.import_module("skm.modules.extensions.generated.views")
    assert pack_views.PackView.SCHEMA_URN == "urn:skm:extensions:view:pack:v1"
    assert pack_views.PacksView.SCHEMA_URN == "urn:skm:extensions:view:packs:v1"
    assert schemas.get(pack_views.PackView.SCHEMA_URN)
    assert schemas.get(pack_views.PacksView.SCHEMA_URN)
