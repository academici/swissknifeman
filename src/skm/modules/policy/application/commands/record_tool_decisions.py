"""``policy.record_tool_decisions`` (policy §7): the append-only audit of tool decisions of hooks and workers.

High-volume and without domain events. The records are validated before the repository sees them (the
database repeats the checks as constraints): a ``deny`` carries a decision code and nothing else does, the
code and the operation are members of the closed vocabularies. A record claiming ``source=worker`` is
accepted only from a worker principal, so a user cannot write the risk signals the reviews read.
"""

from __future__ import annotations

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.policy.application.commands import chain_of
from skm.modules.policy.domain.operations import OperationName
from skm.modules.policy.domain.tool_call import DECISION_CODES, DecisionOutcome
from skm.modules.policy.domain.tool_intent import DecisionSource, ToolDecisionRecord
from skm.modules.policy.generated.commands import RecordToolDecisions, RecordToolDecisionsRecordsItem
from skm.modules.policy.generated.results import RecordToolDecisionsResult
from skm.modules.policy.ports import DecisionAuditRepository

__all__ = ["SPEC", "handle"]

_OPERATIONS = frozenset(item.value for item in OperationName)
_MAX_TOOL = 200


def _invalid(index: int, field: str, reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        f"records[{index}].{field} is invalid: {reason}",
        details={"field": f"records[{index}].{field}", "reason": reason},
    )


def _check(index: int, item: RecordToolDecisionsRecordsItem) -> None:
    if not 1 <= len(item.tool) <= _MAX_TOOL:
        raise _invalid(index, "tool", "length")
    outcome = DecisionOutcome(item.outcome)
    if (outcome is DecisionOutcome.DENY) != (item.code is not None):
        raise _invalid(index, "code", "present_exactly_for_deny")
    if item.code is not None and item.code not in DECISION_CODES:
        raise _invalid(index, "code", "unknown_code")
    if item.operation is not None and item.operation not in _OPERATIONS:
        raise _invalid(index, "operation", "unknown_operation")
    if item.at.tzinfo is None:
        raise _invalid(index, "at", "needs_offset")


def handle(cmd: RecordToolDecisions, ctx: CommandContext, uow: UnitOfWork) -> RecordToolDecisionsResult:
    scope_id = ScopeId(cmd.scope_id)
    worker_scope_ok = ctx.actor.kind is PrincipalKind.WORKER
    for index, item in enumerate(cmd.records):
        _check(index, item)
        if item.source == DecisionSource.WORKER.value and not worker_scope_ok:
            raise Forbidden(
                ErrorCode.FORBIDDEN,
                "only a worker records worker decisions",
                details={"reason": "source_not_worker", "field": f"records[{index}].source"},
            )
    chain = chain_of(uow, scope_id)
    workspace_id = next(
        (WorkspaceId(record.workspace_id) for record in reversed(chain) if record.workspace_id is not None),
        None,
    )
    now = ctx.clock.now()
    uow.repo(DecisionAuditRepository).add_many(
        [
            ToolDecisionRecord(
                id=ctx.ids.new_id(),
                workspace_id=workspace_id,
                scope_id=scope_id,
                principal_id=ctx.actor.principal_id,
                source=DecisionSource(item.source),
                at=item.at,
                tool=item.tool,
                call_summary=item.call_summary,
                outcome=item.outcome,
                code=item.code,
                rule=item.rule,
                operation=item.operation,
                recorded_at=now,
            )
            for item in cmd.records
        ]
    )
    return RecordToolDecisionsResult(recorded=len(cmd.records))


SPEC = CommandSpec(
    name="policy.record_tool_decisions",
    dto=RecordToolDecisions,
    result=RecordToolDecisionsResult,
    permission="policy.read",
    scope_of=lambda cmd: ScopeRef(ScopeKind.RUN, ScopeId(cmd.scope_id)),
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
