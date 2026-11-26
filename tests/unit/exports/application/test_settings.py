"""Validate effective export delivery windows from stored settings and overlays."""

from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonValue
from skm.modules.exports.application.queries.list_pending_notes import load_note_settings
from skm.modules.exports.settings import SECTION_URNS, VALIDATORS, VIEWS
from skm.platform.config.keys import Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.sources.defaults import defaults_layer
from skm.platform.config.sources.packs import PackFragment, pack_layers
from skm.platform.schema.registry import SchemaRegistry


@pytest.mark.parametrize("overlay", [False, True], ids=["stored", "overlay"])
def test_pending_ttl_beyond_retention_is_invalid_in_effective_config(*, overlay: bool) -> None:
    registry = SettingsRegistry.build(
        SchemaRegistry.load_default(),
        SECTION_URNS,
        validators=VALIDATORS,
        views=VIEWS,
        known_permissions=frozenset(),
    )
    instance = LayerRef(Level.INSTANCE, UUID(int=1))
    scopes = ScopeChain(Chain.WORK, (ScopeRef(Level.INSTANCE, UUID(int=1)),))
    values: dict[str, JsonValue] = {"exports.notes.pending_ttl_days": 365, "exports.notes.retention_days": 7}
    if overlay:
        packs = pack_layers((PackFragment("test-overlay", 1, values),), registry, Chain.WORK)
        layers = [*packs, Layer(instance, {})]
    else:
        layers = [
            Layer(instance, {key: Contribution(instance, "set", value) for key, value in values.items()})
        ]
    config = resolve(
        registry,
        scopes,
        [defaults_layer(registry, Chain.WORK), *layers],
        generation=1,
        pack_generation=0,
    )
    with pytest.raises(SkmError) as invalid:
        load_note_settings(config)
    assert invalid.value.code == ErrorCode.SCHEMA_INVALID
    assert invalid.value.details["validator"] == "exports.notes_ttl_order"
    assert set(config.invalid_keys()).issuperset(values)
