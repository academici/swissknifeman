"""Manifest of the planning module (planning §3)."""

from __future__ import annotations

from skm.kernel.module_manifest import ModuleManifest

from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .domain import events
from .permissions import PERMISSIONS
from .ports import (
    DraftRepository,
    PlanCounters,
    PlanningQueries,
    PlanRepository,
    RevisionRepository,
)

__all__ = ["MODULE"]

MODULE = ModuleManifest(
    id="planning",
    depends_on=("access", "workspace", "artifacts", "extensions", "runtimes"),
    optional=False,
    db_schema="skm_planning",
    settings_sections=("planning",),
    permissions=PERMISSIONS,
    repository_ports=(
        PlanRepository,
        PlanCounters,
        DraftRepository,
        RevisionRepository,
        PlanningQueries,
    ),
    gateway_ports=(),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=(),
    events=(
        events.PlanCreated,
        events.DraftOpened,
        events.DraftSaved,
        events.DraftRebased,
        events.DraftAbandoned,
        events.PlanRevisionPublished,
        events.PlanRevisionRestored,
        events.PlanArchived,
    ),
)
