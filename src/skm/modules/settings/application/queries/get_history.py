"""``settings.get_history`` (settings §A.8): history records, ``changed_at DESC, id DESC`` keyset pages.

``scope`` selects the scope and where ``config.read`` is checked; without it the check is on the instance
scope and the history of every scope is listed. Values keep SecretRef strings and mask rejected literals.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.project_keys import MACHINE_ONLY_KEYS, require_project_key
from skm.modules.settings.application.scopes import bus_scope_of, resolve_target_scope
from skm.modules.settings.application.write_flow import safe_value
from skm.modules.settings.domain.history import HistoryRecord
from skm.modules.settings.generated.queries import GetHistory
from skm.modules.settings.generated.views import GetHistoryView, HistoryView
from skm.modules.settings.ports import ConfigHistoryRepository
from skm.platform.config.registry import SettingsRegistry

__all__ = ["SPEC", "handle"]


def _view(record: HistoryRecord, registry: SettingsRegistry) -> HistoryView:
    spec = registry.find(record.key)
    return HistoryView(
        id=record.id,
        entry_id=record.entry_id,
        scope_id=record.scope_id,
        key=record.key,
        change_kind=record.change_kind.value,
        old_op=None if record.old_op is None else record.old_op.value,
        old_value=safe_value(spec, record.old_value),
        old_locked=record.old_locked,
        new_op=None if record.new_op is None else record.new_op.value,
        new_value=safe_value(spec, record.new_value),
        new_locked=record.new_locked,
        actor_id=record.actor_id,
        request_id=record.request_id,
        reason=record.reason,
        generation=record.generation,
        changed_at=record.changed_at,
    )


def handle(query: GetHistory, ctx: QueryContext, uow: UnitOfWork) -> GetHistoryView:
    scope_id = None
    if query.scope is not None:
        scope_id = resolve_target_scope(uow, query.scope, ctx.scope_chain).scope.id
    if query.key is not None:
        require_project_key(query.key)
    page = uow.repo(ConfigHistoryRepository).list(
        scope_id=scope_id, key=query.key, after=query.after, limit=query.limit, exclude_keys=MACHINE_ONLY_KEYS
    )
    registry = ctx.config.registry
    return GetHistoryView(items=tuple(_view(record, registry) for record in page.items), next=page.next)


SPEC = QuerySpec(
    name="settings.get_history",
    dto=GetHistory,
    result=GetHistoryView,
    permission="config.read",
    scope_of=bus_scope_of(lambda query: query.scope),
    handler=handle,
)
