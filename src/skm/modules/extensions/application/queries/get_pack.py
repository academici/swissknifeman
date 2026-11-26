"""``extensions.get_pack`` (extensions §8): a pack by slug or id, the manifest of its newest version."""

from collections import Counter
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.extensions.domain.keys import PackId
from skm.modules.extensions.domain.pack import Pack, manifest_to_json
from skm.modules.extensions.generated.pack import PackManifestDoc
from skm.modules.extensions.generated.queries import GetPack
from skm.modules.extensions.generated.views import PackTrust, PackView, PackViewVersionsItem
from skm.modules.extensions.ports import PackRepository, ResourceRepository

__all__ = ["SPEC", "handle"]


def _find(uow: UnitOfWork, ref: str) -> Pack:
    packs = uow.repo(PackRepository)
    try:
        return packs.get(PackId(UUID(ref)))
    except ValueError:
        found = packs.find_by_slug(ref)
    if found is None:
        raise NotFound(ErrorCode.NOT_FOUND, "pack not found", details={"kind": "pack", "ref": ref})
    return found


def handle(query: GetPack, ctx: QueryContext, uow: UnitOfWork) -> PackView:
    del ctx
    pack = _find(uow, query.pack)
    packs = uow.repo(PackRepository)
    rows = packs.list_versions(pack.id)
    if not rows:
        raise NotFound(
            ErrorCode.NOT_FOUND, "pack has no versions", details={"kind": "pack", "ref": query.pack}
        )
    newest = rows[0]
    for row in rows[1:]:
        if row.version > newest.version:
            newest = row
    manifest = packs.get_version(newest.version_id).manifest
    counted = Counter(
        row.kind.value
        for row in uow.repo(ResourceRepository).list_in_pack_versions([newest.version_id], kind=None)
    )
    return PackView(
        pack_id=pack.id,
        slug=pack.slug,
        title=pack.title,
        trust=PackTrust(pack.trust.value),
        priority=newest.priority,
        versions=tuple(
            PackViewVersionsItem(
                version_id=row.version_id,
                version=str(row.version),
                state=row.state.value,
                installed_at=row.installed_at,
            )
            for row in rows
        ),
        manifest=PackManifestDoc.from_json(manifest_to_json(manifest)),
        resources_by_kind=dict(counted),
    )


SPEC = QuerySpec(
    name="extensions.get_pack",
    dto=GetPack,
    result=PackView,
    permission="ext.read",
    scope_of=None,
    handler=handle,
)
