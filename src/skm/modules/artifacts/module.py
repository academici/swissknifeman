"""Manifest of the artifacts module (artifacts §3)."""

from skm.kernel.module_manifest import ModuleManifest

from .application import events
from .application.registry import COMMANDS, QUERIES
from .application.subscribers import SUBSCRIBERS
from .host.materialize_files import SPEC as MATERIALIZE_FILES_SPEC
from .host.upload_file import SPEC as UPLOAD_FILE_SPEC
from .permissions import PERMISSIONS
from .ports import (
    AccessGrantRepository,
    BlobContentReader,
    BlobCoordination,
    BlobRepository,
    BlobStore,
    FileRepository,
    FileVersionRepository,
    MaterialWriter,
    StagedBlobRepository,
)

__all__ = ["MODULE"]

MODULE = ModuleManifest(
    id="artifacts",
    depends_on=("access", "workspace"),
    optional=False,
    db_schema="skm_artifacts",
    settings_sections=("artifacts",),
    permissions=PERMISSIONS,
    repository_ports=(
        StagedBlobRepository,
        BlobRepository,
        FileRepository,
        FileVersionRepository,
        AccessGrantRepository,
        BlobContentReader,
    ),
    gateway_ports=(BlobStore, BlobCoordination, MaterialWriter),
    commands=COMMANDS,
    queries=QUERIES,
    subscribers=SUBSCRIBERS,
    host_operations=(UPLOAD_FILE_SPEC, MATERIALIZE_FILES_SPEC),
    events=(
        events.FileAdded,
        events.FileVersionAdded,
        events.FileTrashed,
        events.FileRestored,
    ),
)
