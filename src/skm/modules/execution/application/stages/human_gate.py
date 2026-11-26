"""Control-plane human gate: current open requests determine waiting, never a timer answer."""

from __future__ import annotations

from typing import Any

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._state import load_state
from skm.modules.execution.domain.check_execution import CheckState
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
)
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.ports import DecisionRepository
from skm.modules.execution.public import StageOutcome
from skm.modules.planning import public as planning


class HumanGate:
    stage_type = "human_gate"
    side = "control_plane"
    params_schema_urn = "urn:skm:execution:workflow:v1"

    def decide(self, request: Any, ctx: Any, uow: UnitOfWork) -> StageOutcome:
        state, _ = load_state(uow, request.task["task_id"])
        return decide(state, ctx, uow)

    def run(self, _request: Any, _deps: Any) -> Any:
        raise error_for(ErrorCode.INVALID_TRANSITION, "human gate belongs to the control plane")


def open_manual_requests(state: Any, ctx: Any, uow: UnitOfWork, why: JsonObject) -> list[JsonValue]:
    pending = [c for c in state.checks if c.required and c.state is CheckState.MANUAL_PENDING]
    if not pending:
        return []
    repo = uow.repo(DecisionRepository)
    existing = repo.open_for_task(state.task.id)
    spec = planning.get_revision_specification(uow, state.run.revision_id)
    roles = {check.id: getattr(check.definition, "actor_role", None) for check in spec.checks}
    for check in pending:
        if any(
            r.kind is DecisionKind.MANUAL_CHECK and r.payload.get("check_execution_id") == str(check.id)
            for r in existing
        ):
            continue
        request = DecisionRequest(
            ctx.ids.new_id(),
            state.run.workspace_id,
            state.run.id,
            state.task.id,
            DecisionKind.MANUAL_CHECK,
            Audience.OWNER,
            None,
            frozenset(),
            None,
            None,
            1,
            {
                "check_execution_id": str(check.id),
                "check_key": check.check_key,
                "actor_role": roles.get(check.check_spec_id),
            },
            None,
            {
                "attempt_id": str(state.attempt.id),
                "output_id": str(check.output_id),
                "input_part_digest": check.fingerprint,
            },
            DecisionState.OPEN,
            None,
            None,
            ctx.clock.now(),
        )
        repo.add(request)
        emit(
            uow,
            state.run,
            "decision-requested",
            {
                "request_id": str(request.id),
                "task_id": str(state.task.id),
                "kind": request.kind.value,
                "audience": "owner",
                "blocking_code": "WAITING_MANUAL_CHECK",
            },
            why,
        )
    return [str(check.id) for check in pending]


def decide(state: Any, ctx: Any, uow: UnitOfWork, why: Any = None) -> StageOutcome:
    pending = open_manual_requests(state, ctx, uow, why or cause("stage_outcome"))
    if pending or uow.repo(DecisionRepository).open_for_task(state.task.id):
        return StageOutcome(StageOutcomeKind.MANUAL_PENDING, {"pending_check_ids": pending})
    return StageOutcome(StageOutcomeKind.SUCCESS, {})
