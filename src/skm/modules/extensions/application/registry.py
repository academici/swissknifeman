"""Bus operations of the extensions module (extensions §7, §8)."""

from skm.modules.extensions.application.commands import (
    install_pack,
    quarantine_resource,
    release_quarantine,
    sync_builtin_packs,
    uninstall_pack_version,
)
from skm.modules.extensions.application.queries import (
    get_pack,
    get_resource_version,
    list_packs,
    list_resources,
    resolve_resource,
)

__all__ = ["COMMANDS", "QUERIES"]

COMMANDS = (
    install_pack.SPEC,
    sync_builtin_packs.SPEC,
    quarantine_resource.SPEC,
    release_quarantine.SPEC,
    uninstall_pack_version.SPEC,
)
QUERIES = (
    list_packs.SPEC,
    get_pack.SPEC,
    list_resources.SPEC,
    get_resource_version.SPEC,
    resolve_resource.SPEC,
)
