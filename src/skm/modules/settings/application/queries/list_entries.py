"""``settings.list_entries`` (settings §A.8): stored entries, keyset pages by ``(key, scope_id)``.

``scope`` selects the scope whose entries are listed and where ``config.read`` is checked; without it the
check is on the instance scope and entries of every scope are listed (optionally by ``level``).
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind
from skm.modules.settings.application.project_keys import MACHINE_ONLY_KEYS
from skm.modules.settings.application.scopes import bus_scope_of, resolve_target_scope
from skm.modules.settings.application.write_flow import entry_view
from skm.modules.settings.generated.queries import ListEntries
from skm.modules.settings.generated.views import ListEntriesView
from skm.modules.settings.ports import ConfigEntryRepository
from skm.platform.config.keys import Level
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.store import ScopeTree

__all__ = ["SPEC", "handle"]


def handle(query: ListEntries, ctx: QueryContext, uow: UnitOfWork) -> ListEntriesView:
    scope_id = None
    if query.scope is not None:
        scope_id = resolve_target_scope(uow, query.scope, ctx.scope_chain).scope.id
    page = uow.repo(ConfigEntryRepository).list(
        scope_id=scope_id,
        level=None if query.level is None else ScopeKind(query.level),
        key_prefix=query.key_prefix,
        after=query.after,
        limit=query.limit,
        exclude_keys=MACHINE_ONLY_KEYS,
    )
    tree, registry = uow.repo(ScopeTree), ctx.config.registry
    items = tuple(
        entry_view(
            entry,
            tree.label(ConfigScopeRef(Level(entry.scope.kind.value), entry.scope.id)),
            registry.find(entry.key),
        )
        for entry in page.items
    )
    return ListEntriesView(items=items, next=page.next)


SPEC = QuerySpec(
    name="settings.list_entries",
    dto=ListEntries,
    result=ListEntriesView,
    permission="config.read",
    scope_of=bus_scope_of(lambda query: query.scope),
    handler=handle,
)
