"""Packaged schema and settings registries for application tests, built once per session.

``settings_registry`` composes every module section with its owner views and validators, the
platform sections and the integrations hook validators, with the access permission catalog as the
known permissions (as ``test_registry_all_sections`` composes it).
"""

import importlib
from collections.abc import Mapping
from functools import cache
from typing import Any, cast

from skm.application_bus.subscribers import EventSinkRegistry
from skm.bootstrap.modules import MODULE_CATALOG
from skm.modules.access.permissions import PERMISSIONS
from skm.modules.integrations.settings import validators_for
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.validators import SECTION_URNS, VALIDATORS, VIEWS
from skm.platform.schema.registry import SchemaRegistry

__all__ = ["schemas", "settings_registry"]


@cache
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


@cache
def settings_registry() -> SettingsRegistry:
    registry = schemas()
    by_section = {
        cast("Mapping[str, Any]", registry.get(urn)["x-skm-section"])["id"]: urn
        for urn in registry.urns()
        if "x-skm-section" in registry.get(urn)
    }
    views, callbacks, urns = dict(VIEWS), dict(VALIDATORS), list(SECTION_URNS)
    for entry in MODULE_CATALOG:
        if entry.settings_sections:
            module = importlib.import_module(f"skm.modules.{entry.id}.settings")
            views.update(module.VIEWS)
            callbacks.update(module.VALIDATORS)
            urns.extend(by_section[section] for section in entry.settings_sections)
    hookable = {urn for urn in registry.urns() if registry.get(urn).get("x-skm-hookable") is True}
    callbacks.update(validators_for(hookable_types=hookable, sink_ids=EventSinkRegistry(()).ids()))
    return SettingsRegistry.build(
        registry, urns, views=views, validators=callbacks, known_permissions=frozenset(PERMISSIONS)
    )
