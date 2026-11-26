"""Create ephemeral memory, serializing admission and handoff replacement."""

from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.knowledge.application.scopes import (
    project_memory_scope,
    project_ref,
    requested_scope,
    require_instance_write,
)
from skm.modules.knowledge.domain.events import MemoryRemembered
from skm.modules.knowledge.domain.memory_entry import MemoryEntryId, new_entry, supersede
from skm.modules.knowledge.domain.memory_kind import MemoryKind
from skm.modules.knowledge.domain.memory_policy import (
    check_handoff_replacement,
    check_limits,
    ttl_for,
    validate_memory_write,
)
from skm.modules.knowledge.domain.memory_scope import allowed_scopes, ensure_scope_allowed
from skm.modules.knowledge.generated.commands import Remember, RememberScope
from skm.modules.knowledge.generated.results import RememberResult
from skm.modules.knowledge.generated.settings import KnowledgeSettings
from skm.modules.knowledge.ports import MemoryRepository

_UNCAPPED = frozenset({MemoryKind.ACTIVE_HANDOFF, MemoryKind.HEALTH_PROBE})


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> RememberResult:
    settings = ctx.config.section(KnowledgeSettings).memory
    validate_memory_write(cmd["kind"], cmd["body"], max_chars=settings.max_chars)
    kind = MemoryKind(cmd["kind"])
    project = None if cmd["project_id"] is None else project_memory_scope(uow, cmd["project_id"])
    target = cmd.get("scope", RememberScope(kind="project"))
    scope = requested_scope(target["kind"], target.get("namespace"), project)
    if project is not None:
        ensure_scope_allowed(scope, allowed_scopes(project, settings.namespaces))
    require_instance_write(scope, project, ctx, uow)
    ttl = ttl_for(kind, cmd["ttl_hours"], settings)

    repo = uow.repo(MemoryRepository)
    repo.lock_scope(scope)
    now = ctx.clock.now()
    predecessor = repo.live_handoff(scope, now=now) if kind is MemoryKind.ACTIVE_HANDOFF else None
    expected = cmd.get("expected_handoff_id")
    check_handoff_replacement(
        scope, kind, predecessor, MemoryEntryId(UUID(expected)) if expected is not None else None
    )
    if kind not in _UNCAPPED:
        count = repo.count_live(
            scope,
            now=now,
            exclude_kinds=_UNCAPPED,
            created_after=now - timedelta(hours=settings.max_ttl_hours),
        )
        check_limits(count, kind, settings)
    if predecessor is not None:
        repo.save(supersede(predecessor, now), expected_version=predecessor.row_version)
    entry = new_entry(
        entry_id=MemoryEntryId(ctx.ids.new_id()),
        scope=scope,
        kind=kind,
        body=cmd["body"],
        created_at=now,
        expires_at=now + ttl,
        created_by=ctx.actor.principal_id,
        writer=ctx.actor.kind.value,
        source=cmd["source"],
        max_chars=settings.max_chars,
        supersedes_id=None if predecessor is None else predecessor.id,
    )
    try:
        repo.add(entry)
    except Conflict as error:
        if (
            error.code is ErrorCode.ALREADY_EXISTS
            and error.details.get("constraint") == "uq_memory_entries__live_handoff"
        ):
            raise Conflict(
                ErrorCode.VERSION_CONFLICT,
                "The active handoff changed",
                details={"reason": "handoff_changed"},
            ) from error
        raise
    uow.record(MemoryRemembered(scope, entry.id, kind, entry.expires_at))
    return RememberResult(
        entry_id=str(entry.id),
        expires_at=entry.expires_at.isoformat(),
        superseded_id=None if predecessor is None else str(predecessor.id),
    )


SPEC = CommandSpec(
    name="knowledge.remember",
    dto=cast("type[dict[str, Any]]", Remember),
    result=RememberResult,
    permission="memory.write",
    scope_of=lambda cmd: project_ref(cmd["project_id"]),
    handler=handle,
    idempotency=IdempotencyMode.REQUIRED,
)
