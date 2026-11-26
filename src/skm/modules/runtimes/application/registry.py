"""Registered commands and queries of the ``runtimes`` module (runtimes §7, §8)."""

from __future__ import annotations

from skm.application_bus.registry import AnyCommandSpec, AnyQuerySpec
from skm.modules.runtimes.application.commands import (
    record_capability_verification,
    record_host_runtimes,
)
from skm.modules.runtimes.application.queries import (
    explain_routing,
    get_capabilities,
    list_models,
    list_runtimes,
)

__all__ = ["COMMANDS", "QUERIES"]

COMMANDS: tuple[AnyCommandSpec, ...] = (
    record_host_runtimes.SPEC,
    record_capability_verification.SPEC,
)

QUERIES: tuple[AnyQuerySpec, ...] = (
    list_runtimes.SPEC,
    get_capabilities.SPEC,
    list_models.SPEC,
    explain_routing.SPEC,
)
