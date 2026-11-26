"""``extensions.list_resources`` (extensions §8): keyset by ``kind:key:version id``.

Without a scope: every resource of an active pack version. With a scope: only what ``extensions.packs.*`` of
that scope selects.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.extensions.application.resolving import selected_packs
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import PackState
from skm.modules.extensions.generated.queries import ListResources
from skm.modules.extensions.generated.views import ResourceKind as ViewKind
from skm.modules.extensions.generated.views import ResourcesView, ResourcesViewItemsItem
from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository

__all__ = ["SPEC", "handle"]


def _scope_of(query: ListResources) -> ScopeRef | None:
    return None if query.scope is None else ScopeRef(ScopeKind(query.scope.kind), ScopeId(query.scope.id))


def handle(query: ListResources, ctx: QueryContext, uow: UnitOfWork) -> ResourcesView:
    summaries = uow.repo(PackRepository).list_versions(state=PackState.ACTIVE)
    if query.scope is None:
        selected = {row.version_id for row in summaries}
    else:
        selected = {choice.version_id for choice in selected_packs(uow, ctx.config, None)[0]}
    packs = {row.version_id: row for row in summaries if row.version_id in selected}
    kind = None if query.kind is None else ResourceKind(query.kind.value)
    rows = uow.repo(ResourceRepository).list_in_pack_versions(list(packs), kind=kind)
    quarantined = uow.repo(QuarantineRepository).quarantined_ids([row.id for row in rows])
    listed = sorted(
        (row for row in rows if query.include_quarantined or row.id not in quarantined),
        key=lambda row: (row.kind.value, row.key, str(row.pack_version_id)),
    )
    keyed = [(f"{row.kind.value}:{row.key}:{row.pack_version_id}", row) for row in listed]
    after = [pair for pair in keyed if query.after is None or pair[0] > query.after]
    page = after[: query.limit]
    return ResourcesView(
        items=tuple(
            ResourcesViewItemsItem(
                kind=ViewKind(row.kind.value),
                key=row.key,
                version=str(row.version),
                digest=row.digest,
                pack_slug=packs[row.pack_version_id].slug,
                pack_version=str(packs[row.pack_version_id].version),
                verdict=row.verdict.value,
                quarantined=row.id in quarantined,
            )
            for _cursor, row in page
        ),
        next_cursor=page[-1][0] if len(after) > query.limit else None,
    )


SPEC = QuerySpec(
    name="extensions.list_resources",
    dto=ListResources,
    result=ResourcesView,
    permission="ext.read",
    scope_of=_scope_of,  # None is the instance
    handler=handle,
)
