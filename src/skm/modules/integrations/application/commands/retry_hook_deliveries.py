"""Handler for ``integrations.retry_hook_deliveries`` (integrations §7.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.ports import OutboxEntry, OutboxState, OutboxStore
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.pagination import Cursor
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.application.subscribers import (
    default_hookable_event_types,
    read_hook_subscriptions,
    registered_sink_ids,
)
from skm.modules.integrations.generated.commands import RetryHookDeliveries
from skm.modules.integrations.generated.results import RetryHookDeliveriesResult
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]

_PAGE_SIZE = 200


def _scope_of(cmd: RetryHookDeliveries) -> ScopeRef:
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(cmd.workspace_id))


def _workspace_hook_entries(
    outbox: OutboxStore,
    workspace_id: WorkspaceId,
    *,
    destination_prefix: str,
) -> dict[UUID, OutboxEntry]:
    found: dict[UUID, OutboxEntry] = {}
    after: Cursor | None = None
    while True:
        page = outbox.list(
            destination_prefix=destination_prefix,
            state=None,
            workspace_id=workspace_id,
            after=after,
            limit=_PAGE_SIZE,
        )
        for item in page.items:
            found[item.id] = item
        if page.next is None:
            return found
        after = page.next


def handle(
    cmd: RetryHookDeliveries,
    ctx: CommandContext,
    uow: UnitOfWork,
) -> RetryHookDeliveriesResult:
    has_ids = cmd.delivery_ids is not None
    has_sub = cmd.subscription_id is not None
    if has_ids == has_sub:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "exactly one of delivery_ids or subscription_id is required",
        )

    workspace_id = WorkspaceId(cmd.workspace_id)
    workspace.require_active_workspace(uow, workspace_id)
    outbox = uow.repo(OutboxStore)
    now = ctx.clock.now()

    if cmd.delivery_ids is not None:
        owned = _workspace_hook_entries(outbox, workspace_id, destination_prefix="hook:")
        missing: list[JsonValue] = [str(did) for did in cmd.delivery_ids if did not in owned]
        if missing:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "hook delivery not found in workspace",
                details={"kind": "hook_delivery", "missing": missing},
            )
        requeued = 0
        seen: set[UUID] = set()
        for did in cmd.delivery_ids:
            if did in seen:
                continue
            seen.add(did)
            if owned[did].state is OutboxState.DEAD:
                requeued += outbox.retry_dead(outbox_id=did, event_id=None, destination=None, now=now)
        return RetryHookDeliveriesResult(requeued=requeued)

    sub_id = cmd.subscription_id
    if sub_id is None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "subscription_id is required")
    destination = f"hook:{sub_id}"
    owned = _workspace_hook_entries(outbox, workspace_id, destination_prefix=destination)
    exact_entries = [item for item in owned.values() if item.destination == destination]
    if not exact_entries:
        entries, _ = read_hook_subscriptions(
            ctx.config,
            hookable_types=default_hookable_event_types(),
            sink_ids=registered_sink_ids(ctx.config),
        )
        if not any(sub.id == sub_id for sub, _ in entries):
            raise NotFound(
                ErrorCode.NOT_FOUND,
                f"hook subscription {sub_id!r} not found",
                details={"kind": "hook_subscription", "ref": sub_id},
            )
        return RetryHookDeliveriesResult(requeued=0)

    requeued = 0
    for entry in exact_entries:
        if entry.state is OutboxState.DEAD:
            requeued += outbox.retry_dead(outbox_id=entry.id, event_id=None, destination=None, now=now)
    return RetryHookDeliveriesResult(requeued=requeued)


SPEC = CommandSpec(
    name="integrations.retry_hook_deliveries",
    dto=RetryHookDeliveries,
    result=RetryHookDeliveriesResult,
    permission="hook.manage",
    scope_of=_scope_of,
    handler=handle,
    idempotency=IdempotencyMode.OPTIONAL,
)
