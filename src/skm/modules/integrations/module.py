"""Manifest of the ``integrations`` module (integrations §3)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from skm.kernel.module_manifest import ModuleManifest

from .application.hook_delivery import HOOK_CONSUMER
from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS, default_hookable_event_types, subscriber_for
from .domain.events import EVENTS
from .host.registry import HOST_OPERATIONS
from .permissions import PERMISSIONS
from .ports import (
    CheckoutFs,
    CheckoutGitExcludes,
    HostCommandRunner,
    IntegrationTarget,
    IntegrationTargetRegistry,
    LocalCheckoutProjections,
    ProjectionConfig,
    ProjectionRepository,
    UserHomeReader,
)

__all__ = ["MODULE", "bind_hook_subscribers"]


def bind_hook_subscribers(manifests: Sequence[ModuleManifest]) -> tuple[ModuleManifest, ...]:
    """Freeze fan-out against the events actually declared by the selected modules."""
    declared = {event.event_type for manifest in manifests for event in manifest.events}
    spec = subscriber_for(default_hookable_event_types() & declared)
    return tuple(
        replace(manifest, subscribers=(spec,)) if manifest.id == "integrations" else manifest
        for manifest in manifests
    )


MODULE = ModuleManifest(
    id="integrations",
    depends_on=("workspace", "artifacts", "extensions", "policy", "runtimes"),
    optional=False,
    db_schema="skm_integrations",
    settings_sections=("integrations", "hooks"),
    permissions=PERMISSIONS,
    repository_ports=(ProjectionRepository,),
    gateway_ports=(
        IntegrationTarget,
        IntegrationTargetRegistry,
        CheckoutFs,
        CheckoutGitExcludes,
        ProjectionConfig,
        LocalCheckoutProjections,
        UserHomeReader,
        HostCommandRunner,
    ),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    external_consumers=(HOOK_CONSUMER,),
    host_operations=HOST_OPERATIONS,
    events=EVENTS,
)
