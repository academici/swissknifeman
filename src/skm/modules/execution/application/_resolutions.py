"""Translate persisted policy resolutions and explicit owner resume answers."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.domain.decision_request import DecisionState
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.domain.workflow import actions as act
from skm.modules.execution.domain.workflow.engine import decide_advance
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.ports import DecisionRepository

from ._control import current_binding_digest
from ._events import cause


def resolved_action(uow: UnitOfWork, state: Any, workflow: Any, cursor: Any, now: Any) -> Any:
    for trigger in cursor.triggers:
        for ref in trigger.cause.refs:
            if ref.kind != "decision_request":
                continue
            request = uow.repo(DecisionRepository).get(ref.id)
            if request.state is not DecisionState.APPLIED or request.binding.get(
                "input_part_digest"
            ) != current_binding_digest(uow, state.attempt):
                continue
            last = state.history.last()
            if (
                request.payload.get("policy_resolution") == "approved"
                and last is not None
                and last.record.stage_type == "integrate"
            ):
                definition = next(s for s in workflow.stages if s.id == last.record.stage_id)
                outcome: Any = last.record.outcome or {}
                effect_id: Any = outcome.get("effect_id")
                if not effect_id:
                    refs: Any = request.payload.get("refs") or {}
                    effect_id = refs.get("effect_id")
                if effect_id:
                    return act.ActionDecision(
                        act.RunStage(
                            definition.id,
                            definition.type,
                            StageMode.NORMAL,
                            1,
                            {**definition.params.as_json(), "effect_id": effect_id},
                        ),
                        cause("policy_resolved", refs=[{"kind": "decision_request", "id": str(request.id)}]),
                    )
            answers = uow.repo(DecisionRepository).answers_for(request.id)
            answer = next((a for a in answers if a.id == request.answer_id), None)
            if (
                answer is not None
                and isinstance(answer.value, Mapping)
                and answer.value.get("option_id") == "resume_run"
            ):
                status = {
                    "run_checks": TaskStatus.CHECKING,
                    "agent_review": TaskStatus.REVIEWING,
                    "integrate": TaskStatus.INTEGRATING,
                }.get(last.record.stage_type if last else "", TaskStatus.EXECUTING)
                restored = replace(
                    state, task=replace(state.task, status=status, blocking_reason=None), decisions=()
                )
                return decide_advance(restored, workflow, state.effective_policy, now)
    return None
