"""Context port inventory and implemented bus operations (P09.04.d)."""

from __future__ import annotations

from skm.kernel.module_manifest import HostOperationSpec, ModuleManifest
from skm.kernel.ports_uow import Surface

from .application.registry import COMMANDS, QUERIES
from .host.codegraph import run as run_codegraph
from .host.research_query import run as run_research_query
from .permissions import PERMISSIONS
from .ports import (
    CheckoutReader,
    CodeGraphIndex,
    ContextOwnerGuard,
    ContextRepository,
    MemoryRetriever,
    ResearchRepository,
    ResearchSource,
    ResearchSourceRegistry,
    TextStore,
)

RESEARCH_SPEC = HostOperationSpec(
    "context.host.research_query", run_research_query, dict, dict, frozenset({Surface.CLI, Surface.WORKER})
)
CODEGRAPH_SPEC = HostOperationSpec(
    "context.host.codegraph", run_codegraph, dict, dict, frozenset({Surface.CLI})
)

MODULE = ModuleManifest(
    id="context",
    depends_on=("access", "workspace", "planning", "extensions", "artifacts"),
    optional=False,
    db_schema="skm_context",
    settings_sections=("context",),
    permissions=PERMISSIONS,
    repository_ports=(
        ContextRepository,
        TextStore,
        ResearchRepository,
    ),
    gateway_ports=(
        ContextOwnerGuard,
        MemoryRetriever,
        CheckoutReader,
        CodeGraphIndex,
        ResearchSource,
        ResearchSourceRegistry,
    ),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=(),
    host_operations=(RESEARCH_SPEC, CODEGRAPH_SPEC),
    events=(),
)
