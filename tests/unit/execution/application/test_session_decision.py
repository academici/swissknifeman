"""RT-01 session decisions retain authority and only resume an allowed result retry."""

from dataclasses import replace
from typing import Any

import pytest

from contracts.execution.test_step_notes import owned_agent
from skm.modules.execution.domain.session import Fresh, Resume, SessionFacts, decide_session
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.runtimes.public import ResumeAllowance
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import side as side


@pytest.mark.parametrize(("allowed", "session"), [(True, "session-1"), (False, "session-1"), (True, None)])
def test_form_retry_uses_resume_only_with_admission_and_session(
    side: Any, allowed: bool, session: str | None
) -> None:
    _, _, _, _, _, step, _, _, _ = owned_agent(side)
    previous = replace(
        step,
        state=StepState.FAILED,
        finished_at=side.clock.now(),
        error_code="RESULT_INVALID",
        session_ref=session,
    )
    facts = SessionFacts(
        previous,
        True,
        100,
        120000,
        StageMode.RETRY,
        ResumeAllowance(allowed, False, session, "allowed" if allowed else "resume_disabled"),
        True,
        "RESULT_INVALID",
        frozenset(),
    )
    decision = decide_session(step.session_fingerprint, facts)
    assert isinstance(decision, Resume if allowed and session else Fresh)
    if isinstance(decision, Fresh):
        assert decision.reason in {"ADMISSION_NO_RESUME", "NO_PREVIOUS_SESSION"}


def test_authority_change_forces_fresh_despite_result_only_error(side: Any) -> None:
    _, _, _, _, _, step, _, _, _ = owned_agent(side)
    previous = replace(
        step, state=StepState.FAILED, finished_at=side.clock.now(), error_code="RESULT_INVALID"
    )
    fingerprint = replace(step.session_fingerprint, authority_digest="sha256:" + "f" * 64)
    facts = SessionFacts(
        previous,
        True,
        100,
        120000,
        StageMode.RETRY,
        ResumeAllowance(True, False, step.session_ref, "allowed"),
        True,
        "RESULT_INVALID",
        frozenset(),
    )
    assert decide_session(fingerprint, facts) == Fresh("AUTHORITY_CHANGED", True)


def test_rt01_uses_pinned_task_route_and_persisted_fix_brief(side: Any, monkeypatch: Any) -> None:
    from contracts.execution.test_worker_protocol import worker_claim
    from skm.modules.execution.application import _stage_agent_helpers as routing
    from skm.modules.execution.application import _worker_inputs
    from skm.modules.execution.application._worker_protocol import lock_fenced_context
    from skm.modules.execution.domain.finding import Severity
    from skm.modules.execution.domain.fix_brief import FixBrief, FixBriefItem
    from skm.modules.execution.domain.step import RoleId
    from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs
    from skm.modules.execution.ports import AttemptRepository, ReviewRepository
    from skm.modules.planning import public as planning
    from skm.modules.planning.domain.item import Effort, ModelClass, Route
    from unit.execution.application._support import context
    from unit.execution.application.test_context_two_phase import agent_case

    (run, task, attempt, _), claimed, _ = agent_case(side, monkeypatch)
    calls = []
    captured = {}
    with side.uow() as uow:
        selected = uow.repo(AttemptRepository).get(attempt.id).continuation.stage
        brief = FixBrief(
            side.new_id(),
            task.id,
            attempt.id,
            None,
            1,
            (
                FixBriefItem(
                    "fk-" + "1" * 16,
                    "F1",
                    Severity.MAJOR,
                    "logic",
                    {"mount": "repo", "path": "src/target.py"},
                    "Bug",
                    "Fix it",
                    "Observed",
                    "Reproduce",
                ),
            ),
            False,
            side.fv1,
            {},
            "sha256:" + "1" * 64,
        )
        uow.repo(ReviewRepository).add_fix_brief(brief)
        selected = replace(selected, feedback_refs=FeedbackRefs(fix_brief_id=brief.id))
        graph = planning.compile_execution_graph(
            planning.get_revision_specification(uow, run.revision_id), run.revision_id
        )
        planned = Route(ModelClass.FRONTIER, Effort.XHIGH, "codex_cli", "gpt-5", None)
        graph = replace(
            graph,
            tasks=tuple(
                replace(n, route=planned) if n.entity_id == task.spec_entity_id else n for n in graph.tasks
            ),
        )
        monkeypatch.setattr(_worker_inputs.planning, "compile_execution_graph", lambda *_args: graph)
        for name in ("classify_operation", "admit", "route_role", "decide_session"):
            original = getattr(routing, name)

            def observed(*args, _name=name, _original=original, **kwargs):
                calls.append(_name)
                captured[_name] = args[0] if _name == "admit" else args[-1]
                return _original(*args, **kwargs)

            monkeypatch.setattr(routing, name, observed)
        ctx = context(side, uow, run, actor=side.worker1_client._actor)
        fenced = lock_fenced_context(uow, ctx, worker_claim(side, claimed))
        _, profile, perms = routing.profile_and_permissions(uow, ctx, fenced, selected, RoleId.EXECUTOR)
        route, _, _ = routing.route_agent(uow, ctx, fenced, selected, RoleId.EXECUTOR, profile, perms)
        routing.session_decision(uow, ctx, fenced, selected, RoleId.EXECUTOR, route, perms)
    assert calls == ["classify_operation", "admit", "route_role", "decide_session"]
    facts = captured["admit"]
    assert captured["route_role"].explicit_runtime == "codex_cli"
    assert captured["route_role"].explicit_model == "gpt-5"
    assert facts.task_min_class.value == "frontier"
    assert facts.task_min_effort.value == "xhigh"
    assert facts.fix_brief.items == 1
    assert facts.fix_brief.unconfirmed == 0
    assert facts.fix_brief.finding_paths == ("src/target.py",)
