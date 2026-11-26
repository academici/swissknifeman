"""Handler for ``integrations.record_hook_delivery_failure`` (integrations §5.8.6, §7.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.ports import EventReader
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.errors import NotFound
from skm.kernel.ids import EventId, ProjectId, WorkspaceId, parse_uuid
from skm.kernel.ports_uow import Isolation
from skm.modules.integrations.domain.events import HookDeliveryFailed
from skm.modules.integrations.generated.commands import RecordHookDeliveryFailure
from skm.modules.integrations.generated.results import RecordHookDeliveryFailureResult
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.events import EventEnvelope
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]

_SCAN_PAGE_SIZE = 500


def _uuid_field(envelope: EventEnvelope | None, field: str) -> UUID | None:
    if envelope is None:
        return None
    raw = envelope.payload.get(field)
    if isinstance(raw, str):
        return parse_uuid(raw)
    return None


def _resolve_workspace_id(
    cmd: RecordHookDeliveryFailure,
    envelope: EventEnvelope | None,
    uow: UnitOfWork,
) -> WorkspaceId | None:
    if envelope is not None:
        return envelope.workspace_id
    if cmd.scope.kind == "workspace":
        return WorkspaceId(cmd.scope.id)
    if cmd.scope.kind == "project":
        try:
            return workspace.workspace_of_project(uow, ProjectId(cmd.scope.id))
        except NotFound:
            return None
    return None


def _already_recorded(
    reader: EventReader,
    *,
    workspace_id: WorkspaceId | None,
    delivery_id: UUID,
) -> bool:
    target_types = frozenset({HookDeliveryFailed.event_type})
    if workspace_id is not None:
        cursor = 0
        while True:
            batch = reader.after_workspace_seq(
                workspace_id,
                cursor,
                types=target_types,
                limit=_SCAN_PAGE_SIZE,
            )
            if not batch:
                return False
            for item in batch:
                if item.stream_id == delivery_id:
                    return True
            if len(batch) < _SCAN_PAGE_SIZE or batch[-1].workspace_seq is None:
                return False
            cursor = batch[-1].workspace_seq
    cursor = 0
    while True:
        batch = reader.after_global_position(cursor, limit=_SCAN_PAGE_SIZE)
        if not batch:
            return False
        for item in batch:
            if item.type == HookDeliveryFailed.event_type and item.stream_id == delivery_id:
                return True
        if len(batch) < _SCAN_PAGE_SIZE or batch[-1].global_position is None:
            return False
        cursor = batch[-1].global_position


def handle(
    cmd: RecordHookDeliveryFailure,
    _ctx: CommandContext,
    uow: UnitOfWork,
) -> RecordHookDeliveryFailureResult:
    reader = uow.repo(EventReader)
    found = reader.by_ids([EventId(cmd.event_id)])
    envelope = found[0] if found else None
    workspace_id = _resolve_workspace_id(cmd, envelope, uow)

    # The delivery identity is authoritative even when callers use different receipt keys.
    if _already_recorded(
        reader,
        workspace_id=workspace_id,
        delivery_id=cmd.delivery_id,
    ):
        return RecordHookDeliveryFailureResult(recorded=False)

    blocking = cmd.class_ == "workflow" and cmd.failure_policy == "deny"
    run_id = _uuid_field(envelope, "run_id")
    if run_id is None and envelope is not None and envelope.stream_kind == "run":
        run_id = envelope.stream_id
    task_id = _uuid_field(envelope, "task_id")
    project_uuid = _uuid_field(envelope, "project_id")
    project_id: ProjectId | None = None
    if project_uuid is not None:
        project_id = ProjectId(project_uuid)
    elif cmd.scope.kind == "project":
        project_id = ProjectId(cmd.scope.id)

    uow.record(
        HookDeliveryFailed(
            delivery_id=cmd.delivery_id,
            workspace_id=workspace_id,
            subscription_id=cmd.subscription_id,
            subscription_digest=cmd.subscription_digest,
            event_id=EventId(cmd.event_id),
            failed_event_type=cmd.event_type,
            hook_class=cmd.class_,
            failure_policy=cmd.failure_policy,
            blocking=blocking,
            attempts=cmd.attempts,
            reason=cmd.reason,
            status=cmd.status,
            run_id=run_id,
            task_id=task_id,
            project_id=project_id,
        )
    )
    return RecordHookDeliveryFailureResult(recorded=True)


SPEC = CommandSpec(
    name="integrations.record_hook_delivery_failure",
    dto=RecordHookDeliveryFailure,
    result=RecordHookDeliveryFailureResult,
    permission="system.internal",
    scope_of=None,
    handler=handle,
    idempotency=IdempotencyMode.OPTIONAL,
    isolation=Isolation.SERIALIZABLE,
    internal=True,
    allowed_kinds=frozenset({PrincipalKind.SERVICE}),
)
