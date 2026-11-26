"""Command and query registrations of the ``integrations`` module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.modules.integrations.application.commands import (
    record_drift,
    record_hook_delivery_failure,
    record_projection_applied,
    remove_projection,
    retry_hook_deliveries,
    test_hook_subscription,
)
from skm.modules.integrations.application.queries import (
    get_applied_state,
    get_desired_projection,
    get_hook_policy,
    list_hook_deliveries,
    list_hook_subscriptions,
    list_projections,
)

if TYPE_CHECKING:
    from skm.application_bus.registry import AnyCommandSpec, AnyQuerySpec

__all__ = ["COMMANDS", "QUERIES"]

COMMANDS: tuple[AnyCommandSpec, ...] = (
    record_projection_applied.SPEC,
    record_drift.SPEC,
    remove_projection.SPEC,
    record_hook_delivery_failure.SPEC,
    test_hook_subscription.SPEC,
    retry_hook_deliveries.SPEC,
)

QUERIES: tuple[AnyQuerySpec, ...] = (
    get_desired_projection.SPEC,
    get_applied_state.SPEC,
    list_projections.SPEC,
    list_hook_subscriptions.SPEC,
    list_hook_deliveries.SPEC,
    get_hook_policy.SPEC,
)
