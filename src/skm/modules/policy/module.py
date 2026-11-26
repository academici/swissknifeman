"""Manifest of the policy module (policy §3)."""

from __future__ import annotations

from skm.kernel.module_manifest import ModuleManifest

from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .domain import events
from .permissions import PERMISSIONS
from .ports import (
    ApprovalRepository,
    DecisionAuditRepository,
    ExternalFileWriter,
    PathFacts,
    ToolIntentRepository,
)

__all__ = ["MODULE"]

MODULE = ModuleManifest(
    id="policy",
    depends_on=("access", "workspace"),
    optional=False,
    db_schema="skm_policy",
    settings_sections=("policy",),
    permissions=PERMISSIONS,
    repository_ports=(
        ToolIntentRepository,
        ApprovalRepository,
        DecisionAuditRepository,
    ),
    gateway_ports=(PathFacts, ExternalFileWriter),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=(),
    events=(
        events.IntentProposed,
        events.IntentApproved,
        events.IntentDenied,
        events.IntentExecutionStarted,
        events.IntentResolved,
    ),
)
