"""Advisor runtime lifecycle, isolated panel calls and held advice (§5.10)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast, override

from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.consilium import aggregate, held
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.host.stages.agent_step import AgentStepStage
from skm.modules.execution.host.stages.base import StageOutcome

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from skm.modules.execution.host.stages.base import StageRequest
    from skm.modules.execution.ports import StageDeps


class AdvisorConsultStage(AgentStepStage):
    stage_type = "advisor_consult"

    @override
    def run(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        agent = request.runtime_request
        if agent is None or agent.role.value != "advisor":
            raise ValueError("advisor requires its own admitted advisor step")
        # No implicit primary-step credentials. A separately scoped credential binding must
        # be admitted by a future explicit integration, not copied from another role here.
        if (
            agent.secret_env
            or agent.mcp_servers
            or "SKM_TOKEN" in agent.extra_env
            or "SKM_TOKEN" in agent.env_allowlist
        ):
            raise ValueError("advisor cannot inherit primary secrets or MCP authority")
        if int(str(request.task.get("advisor_rounds_used", 0))) >= int(
            str(deps.config.get("execution.advisor.max_rounds"))
        ):
            return StageOutcome(
                StageOutcomeKind.HELD, {"advice": None, "held": True, "held_reason": "QUESTION_NO_ADVISOR"}
            )
        result = super().run(request, deps)
        advice = result.payload.get("role_result")
        if not isinstance(advice, dict):
            return result
        policy: JsonObject = {
            "human_gate": deps.config.get("execution.advisor.human_gate") or [],
            "min_confidence": deps.config.get("execution.advisor.min_confidence") or "medium",
            "gate_categories": request.task.get("gate_categories", []),
            "options": request.task.get("question_options", []),
        }
        is_held = held(advice, policy)
        return replace(
            result,
            kind=StageOutcomeKind.HELD if is_held else StageOutcomeKind.SUCCESS,
            payload={"advice": advice, "held": is_held},
        )

    def panel(
        self,
        requests: Sequence[StageRequest],
        deps: StageDeps,
        *,
        critic: Callable[[int, JsonObject], StageRequest],
        run_member: Callable[[StageRequest], StageOutcome] | None = None,
        policy: JsonObject,
    ) -> StageOutcome:
        if len(requests) < 2:
            raise ValueError("panel requires at least two independently admitted steps")
        ids = [r.runtime_request.request_id for r in requests if r.runtime_request is not None]
        if len(ids) != len(requests) or len(set(ids)) != len(ids):
            raise ValueError("panel participants must have distinct step reservations")
        if any(
            r.runtime_request is not None and r.runtime_request.resume_session_ref is not None
            for r in requests
        ):
            raise ValueError("panel members require fresh isolated sessions")
        votes: list[JsonObject] = []
        positions: list[int] = []

        def run(member: StageRequest) -> StageOutcome:
            agent = member.runtime_request
            if (
                agent is None
                or agent.role.value != "advisor"
                or agent.secret_env
                or agent.mcp_servers
                or "SKM_TOKEN" in agent.extra_env
                or "SKM_TOKEN" in agent.env_allowlist
            ):
                raise ValueError("panel members require independent advisor authority")
            return run_member(member) if run_member is not None else self.run(member, deps)

        outcomes = [run(r) for r in requests]
        for position, outcome in enumerate(outcomes):
            advice = outcome.payload.get("advice")
            if isinstance(advice, dict):
                votes.append(cast("JsonObject", advice))
                positions.append(position)
        result = aggregate(votes, policy)
        if result["kind"] == "majority":
            index = int(str(result["minority_first"]))
            anonymous: JsonObject = {"variants": result["variants"], "advice": result["advice"]}
            critic_request = critic(positions[index], anonymous)
            agent = critic_request.runtime_request
            if (
                agent is None
                or agent.request_id in ids
                or agent.resume_session_ref is not None
                or (critic_request.instruction.params or {}).get("profile") != "advisor-critic"
            ):
                raise ValueError("critic requires a separate admitted step")
            answer = run(critic_request)
            advice: Any = answer.payload.get("advice")
            result = aggregate(votes, {**policy, "critic": advice})
        # Each member's ordinary stage result must be committed by its owning dispatcher;
        # this aggregate is advice, never an owner answer or a decision record.
        is_held = result.get("held") is not False
        return StageOutcome(
            StageOutcomeKind.HELD if is_held else StageOutcomeKind.SUCCESS,
            {"advice": result.get("advice"), "held": is_held, "panel": result},
        )
