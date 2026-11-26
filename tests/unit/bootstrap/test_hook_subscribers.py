"""P10.08.a: bootstrap freezes hook routes after selecting the enabled event producers."""

from dataclasses import replace

import pytest

from skm.application_bus.registry import BusRegistry, SubscriberSpec
from skm.bootstrap.modules import MANIFESTS, select_modules
from skm.modules.integrations.application.subscribers import CONSUMER_ID, HOOK_TEST_REQUESTED_URN
from skm.modules.integrations.domain.events import HookDeliveryFailed
from skm.modules.planning.domain.events import PlanCreated
from skm.platform.schema.registry import SchemaRegistry


@pytest.fixture(scope="module")
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def test_bootstrap_registers_fanout_for_other_modules(schemas: SchemaRegistry) -> None:
    selection = select_modules(MANIFESTS, frozenset())
    registry = BusRegistry.build(
        selection.manifests,
        schemas=schemas,
        permission_catalog=frozenset().union(*(m.permissions for m in MANIFESTS)),
        disabled_modules=selection.disabled,
    )
    assert CONSUMER_ID in registry.subscription_index()[PlanCreated.event_type]
    assert CONSUMER_ID in registry.subscription_index()[HOOK_TEST_REQUESTED_URN]
    assert CONSUMER_ID not in registry.subscription_index().get(HookDeliveryFailed.event_type, ())
    original = next(m for m in MANIFESTS if m.id == "integrations")
    for spec in original.subscribers:
        assert isinstance(spec, SubscriberSpec)
        assert PlanCreated.event_type not in spec.event_types


@pytest.mark.parametrize("disabled", [frozenset(), frozenset({"planning"})])
def test_bootstrap_binds_only_selected_event_producers(
    schemas: SchemaRegistry, disabled: frozenset[str]
) -> None:
    # Model an optional producer using its real events, independently of the required module graph.
    manifests = tuple(
        replace(m, depends_on=(), optional=True) for m in MANIFESTS if m.id in {"integrations", "planning"}
    )
    selection = select_modules(manifests, disabled)
    registry = BusRegistry.build(
        selection.manifests,
        schemas=schemas,
        permission_catalog=frozenset().union(*(m.permissions for m in MANIFESTS)),
        disabled_modules=selection.disabled,
    )
    routed = CONSUMER_ID in registry.subscription_index().get(PlanCreated.event_type, ())
    assert routed == ("planning" not in disabled)
    assert CONSUMER_ID in registry.subscription_index()[HOOK_TEST_REQUESTED_URN]
