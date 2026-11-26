"""Knowledge module registration."""

from __future__ import annotations

from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import Surface

from .application.registry import COMMANDS, QUERIES
from .domain.events import GraphImported, LessonDeprecated, LessonPromoted, MemoryForgotten, MemoryRemembered
from .host.registry import operations
from .permissions import PERMISSIONS
from .ports import (
    CodeGraphReader,
    GraphCheckoutResolver,
    GraphRepository,
    LessonRepository,
    LocalEpisodicMemory,
    ManifestReader,
    MemoryRepository,
)

MODULE = ModuleManifest(
    id="knowledge",
    depends_on=("access", "workspace"),
    optional=True,
    db_schema="skm_knowledge",
    settings_sections=("knowledge",),
    permissions=PERMISSIONS,
    repository_ports=(
        MemoryRepository,
        LessonRepository,
        GraphRepository,
    ),
    gateway_ports=(
        CodeGraphReader,
        GraphCheckoutResolver,
        ManifestReader,
        LocalEpisodicMemory,
    ),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=(),
    host_operations=operations(Surface.CLI),
    events=(MemoryRemembered, MemoryForgotten, LessonPromoted, LessonDeprecated, GraphImported),
)
