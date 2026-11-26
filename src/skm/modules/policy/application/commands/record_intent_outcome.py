"""``policy.record_intent_outcome`` (policy §7) and the facade ``record_outcome``.

``executing`` becomes ``succeeded``, ``failed`` or ``outcome_unknown``; an ``outcome_unknown`` intent is
settled later (``succeeded`` or ``failed``) by reconciliation. The same outcome with the same receipt
repeated is a no-op, so a retry of the recording changes nothing. No scope-open check: an effect that
already ran must be recorded in an archived area too.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import ToolIntentId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.policy.application.commands import SELF_PERMISSION, require_operator
from skm.modules.policy.domain.events import IntentResolved
from skm.modules.policy.domain.tool_intent import (
    OUTCOME_STATES,
    EffectKind,
    IntentState,
    ToolIntent,
    plain_args,
    transition_intent,
)
from skm.modules.policy.generated.commands import RecordIntentOutcome
from skm.modules.policy.generated.results import RecordIntentOutcomeResult
from skm.modules.policy.ports import ToolIntentRepository

__all__ = ["MAX_RECEIPT_BYTES", "SPEC", "handle", "record_in"]

MAX_RECEIPT_BYTES = 16384


def _receipt(receipt: Mapping[str, object]) -> Mapping[str, JsonValue]:
    body = plain_args(receipt)
    size = len(json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    if size > MAX_RECEIPT_BYTES:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "the receipt is too large",
            details={"field": "receipt", "reason": "too_large", "limit": MAX_RECEIPT_BYTES},
        )
    return body


def record_in(
    uow: UnitOfWork,
    ctx: CommandContext,
    *,
    intent_id: ToolIntentId,
    outcome: str,
    receipt: Mapping[str, object],
) -> ToolIntent:
    target = IntentState(outcome)
    if target not in OUTCOME_STATES:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "an outcome is succeeded, failed or outcome_unknown",
            details={"field": "outcome", "reason": "not_an_outcome"},
        )
    body = _receipt(receipt)
    intents = uow.repo(ToolIntentRepository)
    intent = intents.get_for_update(intent_id)
    if intent.kind is EffectKind.FS_WRITE_EXTERNAL and ctx.actor.kind is PrincipalKind.WORKER:
        raise Forbidden(ErrorCode.FORBIDDEN, "unattended workers cannot record external file writes")
    if intent.state is target and intent.receipt == body:
        return intent  # the same outcome again: nothing changes, nothing is recorded
    resolved = transition_intent(intent, target, receipt=body)
    intents.save(resolved, expected_version=intent.row_version)
    uow.record(
        IntentResolved(
            intent_id=resolved.id, workspace_id=resolved.workspace_id, outcome=OUTCOME_STATES[target]
        )
    )
    return resolved


def handle(cmd: RecordIntentOutcome, ctx: CommandContext, uow: UnitOfWork) -> RecordIntentOutcomeResult:
    intent_id = ToolIntentId(cmd.intent_id)
    require_operator(uow, ctx, uow.repo(ToolIntentRepository).get(intent_id).scope_id)
    resolved = record_in(uow, ctx, intent_id=intent_id, outcome=cmd.outcome, receipt=cmd.receipt)
    return RecordIntentOutcomeResult(intent_id=resolved.id, state=resolved.state.value)


SPEC = CommandSpec(
    name="policy.record_intent_outcome",
    dto=RecordIntentOutcome,
    result=RecordIntentOutcomeResult,
    permission=SELF_PERMISSION,
    scope_of=None,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
