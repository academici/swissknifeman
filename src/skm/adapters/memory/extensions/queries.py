"""Read rows of the memory tables: the summaries that resolution and the lists consume (extensions §6)."""

from skm.adapters.memory.extensions.mapping import MemoryExtensionsState
from skm.modules.extensions.domain.pack import PackVersion, PackVersionSummary
from skm.modules.extensions.domain.resource import ResourceVersion, ResourceVersionSummary

__all__ = ["pack_summary", "resource_summary"]


def pack_summary(tables: MemoryExtensionsState, version: PackVersion) -> PackVersionSummary:
    pack = tables.packs[version.pack_id]
    return PackVersionSummary(
        version_id=version.id,
        pack_id=pack.id,
        slug=pack.slug,
        title=pack.title,
        trust=pack.trust,
        version=version.version,
        digest=version.digest,
        priority=version.manifest.priority,
        state=version.state,
        installed_at=version.installed_at,
    )


def resource_summary(version: ResourceVersion) -> ResourceVersionSummary:
    return ResourceVersionSummary(
        id=version.id,
        kind=version.kind,
        key=version.key,
        pack_version_id=version.pack_version_id,
        version=version.version,
        digest=version.digest,
        verdict=version.compat.verdict,
    )
