"""Route previews honor worker offers and review independence."""

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.application import _stage_agent_helpers as routing
from skm.modules.execution.domain.step import RoleId, StepState
from skm.modules.execution.ports import OutputRepository, StageRepository
from skm.modules.planning import public as planning
from skm.modules.runtimes.public import HostRoute, HostRuntimeRepository
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import context
from unit.execution.application._support import side as side
from unit.execution.application.test_context_two_phase import agent_case


def test_stage_route_available_considers_fallback_in_worker_offer(side: Any, monkeypatch: Any) -> None:
    (run, task, attempt, _), _, _ = agent_case(side, monkeypatch)
    primary_route = vars(routing)["route_role"]  # Capture the fake installed by agent_case.

    def route_role(uow, gateways, request, **kwargs):
        result = cast(SimpleNamespace, primary_route(uow, gateways, request, **kwargs))
        installs = uow.repo(HostRuntimeRepository)
        (primary,) = installs.list_for_host(side.host1)
        for runtime_id in ("codex_cli", "fallback"):
            if runtime_id in request.worker_runtimes:
                return HostRoute(
                    **{**vars(result), "runtime_id": runtime_id},
                    model_class=request.model_class,
                    effort_flag=request.effort.value,
                    rejected=(),
                    degraded_details=(),
                    installation=replace(primary, runtime_id=runtime_id),
                    verification_context=None,
                )
        raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "no offered route")

    monkeypatch.setattr(routing, "route_role", route_role)
    worker = SimpleNamespace(
        worker_id=side.worker1,
        host_id=side.host1,
        capabilities=SimpleNamespace(runtimes=("codex_cli", "fallback")),
    )
    with side.uow() as uow:
        ctx = context(side, uow, run, actor=side.worker1_client._actor)

        assert routing.stage_route_available(
            uow, ctx, run, task, attempt, worker, offered_runtimes=frozenset({"fallback"})
        )
        assert not routing.stage_route_available(
            uow, ctx, run, task, attempt, worker, offered_runtimes=frozenset()
        )


def test_review_routing_includes_the_current_output_producer_among_executor_authors(monkeypatch) -> None:
    def step(step_id, state, runtime, model):
        return SimpleNamespace(
            id=step_id,
            role=RoleId.EXECUTOR,
            state=state,
            route_snapshot={"resolved": {"runtime_id": runtime}},
            runtime_observation={
                "binding": {
                    "runtime_id": runtime,
                    "provider_reported_model": model,
                    "model_source": "provider_stream",
                }
            },
        )

    steps = (
        step("previous", StepState.SUCCEEDED, "cursor", "vendor/gpt-6-sol"),
        step("producer", StepState.FAILED, "claude_code", "sonnet"),
        step("unrelated", StepState.FAILED, "grok", "grok-4.5"),
    )
    spec = SimpleNamespace(review_requirement_for=lambda _: SimpleNamespace(independence="separate_runtime"))
    monkeypatch.setattr(planning, "get_revision_specification", lambda *_: spec)
    history = SimpleNamespace(entries=[SimpleNamespace(steps=steps)])
    repos = {
        StageRepository: SimpleNamespace(history=lambda _: history),
        OutputRepository: SimpleNamespace(get=lambda _: SimpleNamespace(produced_by_step_id="producer")),
    }
    uow = SimpleNamespace(repo=repos.__getitem__)
    fenced = SimpleNamespace(
        run=SimpleNamespace(revision_id="revision"),
        task=SimpleNamespace(spec_entity_id="entity"),
        attempt=SimpleNamespace(id="attempt", current_output_id="output"),
    )

    assert routing.observed_executor_routes(cast(Any, uow), fenced, RoleId.REVIEWER) == (
        frozenset({"cursor", "claude_code"}),
        frozenset({"gpt", "claude"}),
    )
