"""Mark only inactive host-owned environments removed; explicit owner release preserves K13."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, override
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import AttemptId, HostId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import effective_permissions
from skm.modules.execution.application._worker_dtos import WireRecord
from skm.modules.execution.domain.attempt import TERMINAL_ATTEMPT_STATES
from skm.modules.execution.domain.environment import EnvironmentState
from skm.modules.execution.domain.ids import EnvironmentId
from skm.modules.execution.generated.commands import (
    MarkEnvironmentsRemoved,
    mark_environments_removed_from_json,
    mark_environments_removed_to_json,
)
from skm.modules.execution.generated.results import (
    MarkEnvironmentsRemovedResult,
    mark_environments_removed_result_from_json,
    mark_environments_removed_result_to_json,
)
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    EffectRepository,
    EnvironmentRepository,
    ExecutionQueries,
    StageRepository,
)
from skm.modules.workspace.public import get_host, worker_for_principal

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = [
    "SPEC",
    "MarkEnvironmentsRemovedCommand",
    "MarkEnvironmentsRemovedReceipt",
    "command_spec",
    "handle",
]


class MarkEnvironmentsRemovedCommand(WireRecord):
    """Bus identity around the generated JSON-mode codec; fields remain schema-owned."""

    SCHEMA_URN = "urn:skm:execution:command:mark-environments-removed:v1"

    @classmethod
    @override
    def from_json(cls, data: Any) -> MarkEnvironmentsRemovedCommand:
        return cls(mark_environments_removed_from_json(data))

    @override
    def to_json(self) -> Any:
        return mark_environments_removed_to_json(cast("MarkEnvironmentsRemoved", self))


class MarkEnvironmentsRemovedReceipt(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:mark-environments-removed:v1"

    @classmethod
    @override
    def from_json(cls, data: Any) -> MarkEnvironmentsRemovedReceipt:
        return cls(mark_environments_removed_result_from_json(data))

    @override
    def to_json(self) -> Any:
        return mark_environments_removed_result_to_json(cast("MarkEnvironmentsRemovedResult", self))


def _host_rows(uow: UnitOfWork, host_id: HostId) -> dict[EnvironmentId, AttemptId]:
    rows: dict[EnvironmentId, AttemptId] = {}
    cursor = None
    while True:
        page = uow.repo(ExecutionQueries).environments_page(host_id, False, cursor, 500)
        for item in cast("list[dict[str, Any]]", page["items"]):
            rows[EnvironmentId(UUID(item["environment_id"]))] = AttemptId(UUID(item["attempt_id"]))
        cursor = cast("str | None", page.get("next_after"))
        if cursor is None:
            return rows


def handle(
    cmd: MarkEnvironmentsRemoved, ctx: CommandContext, uow: UnitOfWork
) -> MarkEnvironmentsRemovedResult:
    data = cast("dict[str, Any]", cmd)
    host_id = HostId(UUID(data["host_id"]))
    get_host(uow, host_id)
    permissions = effective_permissions(uow, ctx.actor, ScopeId(host_id))
    if ctx.actor.kind is PrincipalKind.WORKER:
        worker = worker_for_principal(uow, ctx.actor.principal_id)
        if (
            worker is None
            or worker.host_id != host_id
            or "worker.claim" not in permissions
            or ctx.actor.grant is None
            or ctx.actor.grant.kind != "worker"
        ):
            raise error_for(ErrorCode.FORBIDDEN, "worker cleanup is limited to its registered host")
    elif "run.control" not in permissions:
        raise error_for(ErrorCode.FORBIDDEN, "environment cleanup requires run.control")
    ids = tuple(EnvironmentId(UUID(value)) for value in data["environment_ids"])
    freed = data.get("freed_bytes", 0)
    if len(ids) > 500 or len(set(ids)) != len(ids) or isinstance(freed, bool) or freed < 0:
        raise error_for(ErrorCode.SCHEMA_INVALID, "invalid environment removal batch")
    rows = _host_rows(uow, host_id)
    now = ctx.clock.now()
    unresolved = uow.repo(EffectRepository).unresolved(limit=10000)
    blocked = {effect.attempt_id for effect in unresolved}
    selected: list[EnvironmentId] = []
    for environment_id in ids:
        attempt_id = rows.get(environment_id)
        if attempt_id is None:
            continue
        attempt = uow.repo(AttemptRepository).get(attempt_id, for_update=True)
        environment = uow.repo(EnvironmentRepository).for_attempt(attempt_id)
        if environment is None or environment.id != environment_id or environment.host_id != host_id:
            continue
        if environment.state is EnvironmentState.REMOVED:
            continue
        if attempt.state not in TERMINAL_ATTEMPT_STATES or attempt_id in blocked or len(unresolved) == 10000:
            continue
        assignments = uow.repo(AssignmentRepository)
        if any(
            (lease := assignments.lease(a.id, for_update=True)) is not None and lease.expires_at > now
            for a in assignments.for_attempt(attempt_id)
        ):
            continue
        if uow.repo(StageRepository).started_without_result(attempt_id) is not None:
            continue
        selected.append(environment_id)
    marked = uow.repo(EnvironmentRepository).mark_removed(selected, host_id, now)
    ctx.log.info("execution.environments_removed", host_id=str(host_id), marked=marked, freed_bytes=freed)
    return MarkEnvironmentsRemovedResult(marked=marked)


def _dispatch(
    cmd: MarkEnvironmentsRemovedCommand, ctx: CommandContext, uow: UnitOfWork
) -> MarkEnvironmentsRemovedReceipt:
    return MarkEnvironmentsRemovedReceipt(handle(cast("MarkEnvironmentsRemoved", cmd), ctx, uow))


SPEC = CommandSpec(
    name="execution.mark_environments_removed",
    dto=MarkEnvironmentsRemovedCommand,
    result=MarkEnvironmentsRemovedReceipt,
    permission="worker.claim",
    permission_alternatives=("run.control",),
    scope_of=lambda cmd: ScopeRef(ScopeKind.HOST, ScopeId(UUID(cast("str", cmd["host_id"])))),
    handler=_dispatch,
    allowed_kinds=frozenset({PrincipalKind.WORKER, PrincipalKind.HUMAN}),
    idempotency=IdempotencyMode.REQUIRED,
)


def command_spec() -> CommandSpec[MarkEnvironmentsRemovedCommand, MarkEnvironmentsRemovedReceipt]:
    """The completed registration, ready for its owning integration slice."""
    return SPEC
