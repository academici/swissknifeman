"""Bus operations of the artifacts module (artifacts §7, §8)."""

from skm.modules.artifacts.application.commands import (
    add_file,
    add_file_version,
    expire_staged_blobs,
    prune_orphan_objects,
    record_staged_blob,
    restore_file,
    trash_file,
)
from skm.modules.artifacts.application.queries import (
    find_orphan_blobs,
    get_file,
    get_file_version,
    list_file_versions,
    list_files,
    open_file_version_content,
)

__all__ = ["COMMANDS", "QUERIES"]

COMMANDS = (
    record_staged_blob.SPEC,
    expire_staged_blobs.SPEC,
    add_file.SPEC,
    add_file_version.SPEC,
    trash_file.SPEC,
    restore_file.SPEC,
    prune_orphan_objects.SPEC,
)
QUERIES = (
    get_file.SPEC,
    list_files.SPEC,
    list_file_versions.SPEC,
    get_file_version.SPEC,
    open_file_version_content.SPEC,
    find_orphan_blobs.SPEC,
)
