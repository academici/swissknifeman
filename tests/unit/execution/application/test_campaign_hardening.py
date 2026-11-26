"""Campaign interventions survive replay and bind the exact policy, candidate and fence."""

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from contracts.execution.test_live_control import _start
from skm.kernel.errors import SkmError
from skm.modules.execution.application import _incident_gate as gate
from skm.modules.execution.application._state import load_state
from skm.modules.execution.domain.attempt import SelectedStage
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.task import ReviewMode
from skm.modules.execution.domain.workflow.actions import Escalate, RunStage
from skm.modules.execution.domain.workflow.definition import StageType
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import RunRepository, StepRepository
from skm.sdk import GetAutopilotStatus, PauseAutopilot, StartAutopilot

from ._support import _shared_side as _shared_side
from ._support import context, seeded
from ._support import side as side
from .test_autopilot_commands import command, configure, patch_state


def test_incident_replay_seals_policy_and_rejects_changed_candidate(side: Any):
    run, task, _ = seeded(side)
    feedback = FeedbackRefs(fix_brief_id=side.new_id())
    repair = RunStage("execute", StageType.AGENT_STEP, StageMode.REWORK, 1, {}, feedback=feedback)
    with side.uow() as uow:
        ctx = context(side, uow, run)
        state, _ = load_state(uow, task.id)
        state = replace(
            state, run=replace(run, autopilot=True), task=replace(task, review_mode=ReviewMode.REQUIRED)
        )
        retry = replace(repair, mode=StageMode.RETRY)
        assert gate.gate_action(uow, ctx, state, retry) == retry
        marked = gate.gate_action(uow, ctx, state, repair)
        assert marked.params[gate.REPAIR_REVIEW_REQUIRED] is True
        uow.commit()
    with side.uow() as uow:
        ctx = context(side, uow, run)
        assert gate.gate_action(uow, ctx, state, repair) == marked
        selected = SelectedStage(
            "execute",
            "agent_step",
            StageMode.REWORK,
            1,
            marked.params,
            None,
            None,
            feedback,
            state.attempt.current_output_id,
            None,
        )
        assert gate.verify_repair(uow, ctx, state, selected) == selected
        for changed in (
            replace(selected, input_output_id=side.new_id()),
            replace(selected, params={**marked.params, "scope": "*"}),
            replace(selected, params={**marked.params, gate.REPAIR_REVIEW_REQUIRED: False}),
        ):
            with pytest.raises(SkmError) as error:
                gate.verify_repair(uow, ctx, state, changed)
            assert error.value.details["reason"] == gate.REPAIR_ACTION_DIGEST
        changed_repair = replace(repair, round_no=2)
        escalated = gate.gate_action(uow, ctx, state, changed_repair)
        assert isinstance(escalated, Escalate)
        assert escalated.payload["options"]
        assert gate.gate_action(uow, ctx, state, changed_repair) == escalated
        assert [g.details["branch"] for g in uow.repo(StepRepository).incident_gates(task.id)] == [
            "A",
            "B",
            "C",
        ]

        # A new failed stage supplies fresh evidence, while a session restart alone does not.
        def observed_after(stage_id):
            return replace(
                state, history=SimpleNamespace(entries=[SimpleNamespace(record=SimpleNamespace(id=stage_id))])
            )

        newer = observed_after(side.new_id())
        second = gate.gate_action(uow, ctx, newer, changed_repair)
        assert isinstance(second, RunStage)
        third = replace(changed_repair, round_no=3)
        assert isinstance(gate.gate_action(uow, ctx, observed_after(side.new_id()), third), Escalate)
        distinct = replace(
            newer,
            checks=[
                SimpleNamespace(
                    check_spec_id=side.new_id(), required=True, state=SimpleNamespace(value="failed")
                )
            ],
        )
        assert isinstance(gate.gate_action(uow, ctx, distinct, third), RunStage)


def test_stop_after_waits_for_exact_fenced_step(side: Any):
    configure(side)
    command(side, StartAutopilot)
    run, task, _, _, stage, step = _start(side)
    with side.uow() as uow:
        repo = uow.repo(RunRepository)
        repo.save(replace(run, autopilot=True), expected_version=run.row_version)
        uow.commit()
    patch_state(side, current_run_id=run.id)
    command(side, PauseAutopilot, stop_after=str(step.id))
    assert side.client.ask(GetAutopilotStatus(project_id=str(side.proj)))["state"] == "paused"
    with side.uow() as uow:
        run = uow.repo(RunRepository).get(run.id)
        assert run.status is RunStatus.RUNNING
        fenced = SimpleNamespace(run=run, task=task)
        assert uow.repo(StepRepository).incident_gates(task.id)[0].stop_after == step.id
        gate.honor_boundary(uow, fenced, replace(stage, fencing_token=stage.fencing_token + 1), [step])
        assert fenced.run.status is RunStatus.RUNNING
        gate.honor_boundary(uow, fenced, stage, [step])
        assert fenced.run.status is RunStatus.PAUSED
        assert fenced.run.pause_source == "owner"
        uow.commit()


def test_follow_resumes_terminal_feed_and_preserves_cursor_on_failed_output(tmp_path, monkeypatch):
    import json
    from concurrent.futures import ThreadPoolExecutor

    from skm.entrypoints.cli.commands import autopilot as cli

    path = tmp_path / "cursor.json"
    status = {"effective_state": "running"}
    workspace, project = "ws", "proj"
    head = 10
    monkeypatch.setattr(cli, "named_query", lambda *_, **__: SimpleNamespace(workspace_id=workspace))
    monkeypatch.setattr(cli, "ask", lambda *_, **__: status)

    def events(*, after, **_):
        assert after == 10
        yield SimpleNamespace(workspace_seq=11, stream_kind="project", stream_id=project, type="finished")

    client = SimpleNamespace(
        ask_with_meta=lambda _: (status, SimpleNamespace(events_cursor=head)), events=events
    )
    ctx: Any = SimpleNamespace(client=client)
    assert cli.follow(ctx, project, cursor_file=path, seconds=0, lock="") == 0
    assert json.loads(path.read_text()) == {"workspace_id": workspace, "project_id": project, "after": 10}
    with cli.FileLock(tmp_path / "cursor.json.lock").hold(timeout_seconds=0), ThreadPoolExecutor(1) as pool:
        with pytest.raises(SkmError) as busy:
            pool.submit(cli.follow, ctx, project, cursor_file=path, seconds=0, lock="").result()
        assert busy.value.code.value == "CHECKOUT_BUSY"
    with pytest.raises(SkmError, match="another feed"):
        cli.follow(ctx, "other", cursor_file=path, seconds=0)
    head = 11
    status["effective_state"] = "idle"

    def broken(*_):
        raise BrokenPipeError

    monkeypatch.setattr(cli, "_line", broken)
    with pytest.raises(SkmError):
        cli.follow(ctx, project, cursor_file=path, seconds=1)
    assert json.loads(path.read_text())["after"] == 10
    seen = []
    monkeypatch.setattr(cli, "_line", lambda _, text, data: seen.append(data["type"]))
    assert cli.follow(ctx, project, cursor_file=path, seconds=1) == 0
    assert seen == ["finished"]
    assert json.loads(path.read_text())["after"] == 11
    assert cli.follow(ctx, project, cursor_file=path, seconds=1) == 0
    assert seen == ["finished"]


def test_export_alias_uses_same_operation_and_doctor_strict_warning(monkeypatch):
    from skm.entrypoints.cli.commands import doctor
    from skm.entrypoints.cli.parser import build_parser

    parser = build_parser()
    short = parser.parse_args(["run", "export", "ref", "--summary", "-o", "report.md"])
    original = parser.parse_args(["export", "run", "ref", "--summary", "-o", "report.md"])
    assert (short.run, short.command_name, short.summary, short.ref, short.output) == (
        original.run,
        original.command_name,
        True,
        "ref",
        "report.md",
    )
    values = []
    monkeypatch.setattr(doctor, "render", lambda _, value, **kw: values.append(value))
    status = {"effective_state": "running", "emergency": False, "queue": [{"ref": "p", "status": "stale"}]}
    ctx: Any = SimpleNamespace(
        client=SimpleNamespace(ask=lambda _: {"status": status, "stop_conditions": []})
    )
    assert doctor._campaign(ctx, "p", strict=False) == 0
    assert doctor._campaign(ctx, "p", strict=True) == 1
    status["emergency"] = True
    assert doctor._campaign(ctx, "p", strict=False) == 1
    assert values[-1]["checks"][0]["check_id"] == "autopilot.emergency"


def test_checks_follow_binding_order_and_nonzero_expected_exit(monkeypatch):
    from skm.modules.execution.application.stages import gate_facts
    from skm.modules.execution.domain.check_execution import CheckKind, CheckState, classify_check_result
    from skm.modules.execution.domain.task import TaskKind
    from skm.modules.planning.domain import check_spec

    first, second = SimpleNamespace(id="first"), SimpleNamespace(id="second")
    monkeypatch.setattr(
        gate_facts.planning, "get_revision_specification", lambda *_: SimpleNamespace(checks=[first, second])
    )
    node = SimpleNamespace(task_key="item", checks=[SimpleNamespace(check_id=c.id) for c in (second, first)])
    monkeypatch.setattr(
        gate_facts.planning, "compile_execution_graph", lambda *_: SimpleNamespace(tasks=[node])
    )
    assert gate_facts.check_definitions(
        cast("Any", None),
        SimpleNamespace(revision_id="rev"),
        SimpleNamespace(kind=TaskKind.ITEM, display_key="item"),
    ) == (second, first)
    for kind, fields in (
        (check_spec.CheckKind.COMMAND, {"argv": ["cmd"]}),
        (check_spec.CheckKind.SHELL, {"script": "cmd", "risk_ack": "owner"}),
    ):
        source = {**fields, "cwd": {"mount": "main"}}
        assert "expected_exit" not in check_spec.definition_to_doc(
            check_spec.definition_from_doc(kind, source)
        )
        pinned = check_spec.definition_from_doc(kind, {**source, "expected_exit": 7})
        assert check_spec.definition_to_doc(pinned)["expected_exit"] == 7
    for actual, expected_state in (
        (7, CheckState.PASSED),
        (0, CheckState.FAILED),
        (None, CheckState.UNKNOWN),
    ):
        assert (
            classify_check_result(CheckKind.COMMAND, actual, False, None, False, expected_exit=7)[0]
            is expected_state
        )


def test_required_repair_keeps_review_requirement_at_acceptance(side: Any):
    from skm.modules.execution.application.stages import acceptance_gate
    from skm.modules.execution.domain.review import ReviewClearance

    run, task, _ = seeded(side)
    with side.uow() as uow:
        ctx = context(side, uow, run)
        state, _ = load_state(uow, task.id)
        state = replace(
            state, run=replace(run, autopilot=True), task=replace(task, review_mode=ReviewMode.REQUIRED)
        )
        marked = gate.gate_action(
            uow, ctx, state, RunStage("execute", StageType.AGENT_STEP, StageMode.REWORK, 1, {})
        )
        downgraded = replace(state, task=replace(task, review_mode=ReviewMode.SELF))
        outcome = acceptance_gate.decide(downgraded, ReviewClearance.SELF, ctx, uow, {})
        reasons: Any = outcome.payload["reasons"]
        assert any(
            r["code"] == gate.REPAIR_REVIEW_REQUIRED
            and r["refs"]["action_digest"] == marked.params[gate.REPAIR_ACTION_DIGEST]
            for r in reasons
        )

        from skm.modules.execution.domain.acceptance import AcceptanceBasis, Accepted, NotAcceptable

        from ._support import seed_stage, seed_step

        stage = seed_stage(side, uow, state.attempt)
        step = seed_step(side, uow, state.attempt, stage, manifest_id=side.new_id(), admission=marked.params)
        repaired = SimpleNamespace(id=side.new_id(), produced_by_step_id=step.id)
        candidate = replace(state, output=repaired)
        green = Accepted(ReviewClearance.GREEN, AcceptanceBasis.empty(ReviewClearance.GREEN))
        stale = acceptance_gate.repair_acceptance(uow, candidate, ReviewClearance.GREEN, green)
        assert isinstance(stale, NotAcceptable)
        assert stale.codes == (gate.REPAIR_ACTION_DIGEST,)
        gate.bind_repair_output(uow, ctx, state, repaired, None, False)
        assert acceptance_gate.repair_acceptance(uow, candidate, ReviewClearance.GREEN, green) == green
        other = replace(state, output=SimpleNamespace(id=side.new_id()))
        assert isinstance(
            acceptance_gate.repair_acceptance(uow, other, ReviewClearance.GREEN, green), NotAcceptable
        )


def test_service_cannot_release_owner_or_emergency_hold(side: Any):
    from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
    from skm.modules.execution.application.commands.start_autopilot import (
        hold_authority,
        require_release_authority,
    )
    from skm.modules.execution.domain.autopilot import AutopilotStateKind

    from .test_autopilot_commands import state_of

    configure(side)
    command(side, StartAutopilot)
    running = state_of(side)
    coordinator = SimpleNamespace(actor=Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"))
    paused = replace(running, state=AutopilotStateKind.PAUSED, counters=hold_authority(running, coordinator))
    require_release_authority(paused, coordinator)
    command(side, PauseAutopilot)
    owner_pause = state_of(side)
    with pytest.raises(SkmError, match="owner"):
        require_release_authority(
            replace(owner_pause, counters=hold_authority(owner_pause, coordinator)), coordinator
        )
    with pytest.raises(SkmError, match="owner"):
        require_release_authority(replace(paused, emergency=True), coordinator)


def test_sdk_closes_selected_http_profile_on_error(tmp_path, monkeypatch):
    from skm.bootstrap import sdk as bootstrap
    from skm.sdk import connect

    selected = []
    closed = []

    def load(path, env, home, *, instance):
        selected.append((path, instance))
        return SimpleNamespace(access_mode="http", installation_id=None, machine_database_url=None)

    client = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(bootstrap, "load_bootstrap", load)
    monkeypatch.setattr(bootstrap, "open_http_client", lambda *_: client)
    config = tmp_path / "hub.toml"

    def interrupted():
        with connect(profile="hub", config=config) as remote:
            assert remote is client
            raise ValueError("interrupted")

    with pytest.raises(ValueError, match="interrupted"):
        interrupted()
    assert selected == [(str(config), "hub")]
    assert closed == [True]
