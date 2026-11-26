"""``extensions.list_packs`` (extensions §8): keyset by slug; one row per pack with its versions."""

from itertools import groupby
from typing import cast

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.extensions.domain.pack import PackState, PackVersionSummary
from skm.modules.extensions.generated.queries import ListPacks
from skm.modules.extensions.generated.views import (
    PacksView,
    PacksViewItemsItem,
    PacksViewItemsItemVersionsItem,
    PackTrust,
)
from skm.modules.extensions.ports import PackRepository

__all__ = ["SPEC", "handle"]


def _newest(rows: list[PackVersionSummary]) -> PackVersionSummary:
    newest = rows[0]
    for row in rows[1:]:
        if row.version > newest.version:
            newest = row
    return newest


def _item(rows: list[PackVersionSummary]) -> PacksViewItemsItem:
    head = _newest(rows)
    return PacksViewItemsItem(
        pack_id=head.pack_id,
        slug=head.slug,
        title=head.title,
        trust=PackTrust(head.trust.value),
        priority=head.priority,
        versions=tuple(
            PacksViewItemsItemVersionsItem(
                version_id=row.version_id,
                version=str(row.version),
                state=cast("object", row.state.value),  # type: ignore[arg-type]
                installed_at=row.installed_at,
            )
            for row in rows
        ),
    )


def handle(query: ListPacks, ctx: QueryContext, uow: UnitOfWork) -> PacksView:
    del ctx
    state = None if query.state is None else PackState(query.state)
    rows = sorted(uow.repo(PackRepository).list_versions(state=state), key=lambda row: row.slug)
    groups = [list(group) for _slug, group in groupby(rows, key=lambda row: row.slug)]
    after = [group for group in groups if query.after is None or group[0].slug > query.after]
    page = after[: query.limit]
    return PacksView(
        items=tuple(_item(group) for group in page),
        next_cursor=page[-1][0].slug if len(after) > query.limit else None,
    )


SPEC = QuerySpec(
    name="extensions.list_packs",
    dto=ListPacks,
    result=PacksView,
    permission="ext.read",
    scope_of=None,
    handler=handle,
)
