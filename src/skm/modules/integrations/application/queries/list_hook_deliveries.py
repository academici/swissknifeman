"""Handler for ``integrations.list_hook_deliveries`` (integrations §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from skm.application_bus.ports import EventReader, OutboxEntry, OutboxState, OutboxStore
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.pagination import DEFAULT_PAGE_LIMIT, Cursor, validate_page_limit
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.generated.queries import ListHookDeliveries
from skm.modules.integrations.generated.views import HookDeliveriesView, HookDeliveryView
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]

_HOOK_PREFIX = "hook:"


def _scope_of(query: ListHookDeliveries) -> ScopeRef:
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(query.workspace_id))


def _view_state(state: OutboxState) -> Literal["pending", "delivered", "dead"]:
    if state is OutboxState.DELIVERED:
        return "delivered"
    if state is OutboxState.DEAD:
        return "dead"
    return "pending"


def _matches_subscription(entry: OutboxEntry, subscription_id: str | None) -> bool:
    if subscription_id is None:
        return entry.destination.startswith(_HOOK_PREFIX)
    return entry.destination == f"{_HOOK_PREFIX}{subscription_id}"


def handle(query: ListHookDeliveries, _ctx: QueryContext, uow: UnitOfWork) -> HookDeliveriesView:
    workspace_id = WorkspaceId(query.workspace_id)
    limit = validate_page_limit(DEFAULT_PAGE_LIMIT if query.limit is None else query.limit)
    workspace.require_active_workspace(uow, workspace_id)

    prefix = f"{_HOOK_PREFIX}{query.subscription_id}" if query.subscription_id is not None else _HOOK_PREFIX
    state_filter = None if query.state is None else OutboxState(query.state)
    cursor = None if query.after is None else Cursor(query.after)

    outbox = uow.repo(OutboxStore)
    page = outbox.list(
        destination_prefix=prefix,
        state=state_filter,
        workspace_id=workspace_id,
        after=cursor,
        limit=limit,
    )
    filtered = [entry for entry in page.items if _matches_subscription(entry, query.subscription_id)]
    event_ids = list({entry.event_id for entry in filtered})
    envelopes = uow.repo(EventReader).by_ids(event_ids) if event_ids else ()
    type_by_id = {env.id: env.type for env in envelopes}

    items = tuple(
        HookDeliveryView(
            delivery_id=entry.id,
            subscription_id=entry.destination.removeprefix(_HOOK_PREFIX),
            event_id=entry.event_id,
            event_type=type_by_id.get(entry.event_id, "urn:skm:integrations:event:unknown:v1"),
            state=_view_state(entry.state),
            attempts=entry.attempts,
            available_at=entry.available_at,
            last_error=entry.last_error,
        )
        for entry in filtered
    )
    return HookDeliveriesView(
        items=items,
        next_cursor=None if page.next is None else str(page.next),
        has_more=page.next is not None,
    )


SPEC = QuerySpec(
    name="integrations.list_hook_deliveries",
    dto=ListHookDeliveries,
    result=HookDeliveriesView,
    permission="integration.read",
    scope_of=_scope_of,
    handler=handle,
)
