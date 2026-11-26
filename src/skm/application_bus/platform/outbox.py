"""``platform.list_dead_outbox`` and ``platform.retry_outbox`` (kernel-platform §5.6, adapters §1.4).

The operator's view of dead outbox rows and the manual requeue of them (``skm events dead``/``skm events
retry``, ``GET /admin/outbox/dead``, ``POST /admin/outbox/{outbox_id}/retry``); both need ``admin.events`` on
the instance scope. Requeueing resets the send attempts and the claim, and increments the delivery generation,
so the next death of the row is a new one; it never touches delivered, pending or failed rows. The handlers
work through the ``OutboxStore`` repository port of their unit of work only.
"""

from typing import Final

from skm.application_bus.context import CommandContext, QueryContext
from skm.application_bus.ports import OutboxEntry, OutboxStore
from skm.application_bus.registry import CommandSpec, IdempotencyMode, QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import EventId
from skm.kernel.ports_uow import Isolation, UnitOfWork
from skm.platform.generated.commands import RetryOutbox
from skm.platform.generated.queries import ListDeadOutbox
from skm.platform.generated.results import (
    ListDeadOutboxResult,
    ListDeadOutboxResultItemsItem,
    RetryOutboxResult,
)

__all__ = ["LIST_DEAD_OUTBOX", "RETRY_OUTBOX", "handle_list_dead_outbox", "handle_retry_outbox"]

_PERMISSION: Final = "admin.events"


def _item(entry: OutboxEntry) -> ListDeadOutboxResultItemsItem:
    return ListDeadOutboxResultItemsItem(
        outbox_id=entry.id,
        event_id=entry.event_id,
        destination=entry.destination,
        attempts=entry.attempts,
        last_error=entry.last_error,
        created_at=entry.created_at,
    )


def handle_list_dead_outbox(
    query: ListDeadOutbox, ctx: QueryContext, uow: UnitOfWork
) -> ListDeadOutboxResult:
    del ctx  # authorization happened before the handler
    page = uow.repo(OutboxStore).list_dead(after=query.after, limit=query.limit)
    return ListDeadOutboxResult(items=tuple(_item(entry) for entry in page.items), next=page.next)


def handle_retry_outbox(cmd: RetryOutbox, ctx: CommandContext, uow: UnitOfWork) -> RetryOutboxResult:
    """Dead rows matching every given selector go back to ``pending``; at least one selector is required."""
    if cmd.outbox_id is None and cmd.event_id is None and cmd.destination is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "platform.retry_outbox needs outbox_id, event_id or destination",
            details={"fields": ["outbox_id", "event_id", "destination"]},
        )
    requeued = uow.repo(OutboxStore).retry_dead(
        outbox_id=cmd.outbox_id,
        event_id=None if cmd.event_id is None else EventId(cmd.event_id),
        destination=cmd.destination,
        now=ctx.clock.now(),
    )
    return RetryOutboxResult(requeued=requeued)


LIST_DEAD_OUTBOX: Final = QuerySpec(
    name="platform.list_dead_outbox",
    dto=ListDeadOutbox,
    result=ListDeadOutboxResult,
    permission=_PERMISSION,
    scope_of=None,  # instance: the outbox belongs to the whole installation
    handler=handle_list_dead_outbox,
)
RETRY_OUTBOX: Final = CommandSpec(
    name="platform.retry_outbox",
    dto=RetryOutbox,
    result=RetryOutboxResult,
    permission=_PERMISSION,
    scope_of=None,
    handler=handle_retry_outbox,
    idempotency=IdempotencyMode.OPTIONAL,
    isolation=Isolation.READ_COMMITTED,
)
