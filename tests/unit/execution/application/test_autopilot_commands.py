"""Persisted bus campaigns, transaction guards and the thin follow surface."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from skm.application_bus.client import new_request_id
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.execution.application.commands import autopilot_tick, resume_run
from skm.modules.execution.application.commands.drain_autopilot import DrainAutopilot
from skm.modules.execution.application.commands.pause_autopilot import PauseAutopilot
from skm.modules.execution.application.commands.start_autopilot import StartAutopilot
from skm.modules.execution.application.commands.stop_autopilot import StopAutopilot
from skm.modules.execution.application.queries.explain_autopilot import ExplainAutopilot
from skm.modules.execution.application.queries.get_autopilot_status import GetAutopilotStatus
from skm.modules.execution.domain.autopilot import AutopilotStateKind
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.generated.commands import ValidateForExecution
from skm.modules.execution.ports import (
    AutopilotRepository,
    ExecutionQueries,
    RunRepository,
)
from skm.modules.settings import public as settings

from ._support import _shared_side as _shared_side
from ._support import seeded
from ._support import side as side


def configure(side: Any, **changes: Any) -> None:
    for key, val in {"allowed": True, "enabled": True, **changes}.items():
        scope = (
            {"level": "instance"}
            if key in {"allowed", "accept_advisories"}
            else {"level": "project", "scope_id": str(side.proj)}
        )
        side.client.dispatch(
            settings.SetValue.from_json(
                {
                    "scope": scope,
                    "key": "execution.autopilot." + key,
                    "value": val,
                    "reason": "Autopilot test",
                    "confirmed": True,
                }
            )
        )


def command(side: Any, cls: Any, **changes: Any) -> Any:
    return side.client.dispatch(cls(project_id=str(side.proj), reason="campaign", **changes))


def tick(side: Any) -> Any:
    return side.app.bus.dispatch(
        autopilot_tick.AutopilotTick(project_id=str(side.proj)),
        actor=Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"),
        meta=RequestMeta(new_request_id(side.ids), Surface.BACKGROUND, None, side.clock.now()),
    )


def state_of(side: Any) -> Any:
    with side.uow(readonly=True) as uow:
        return uow.repo(AutopilotRepository).get(side.proj)


def patch_state(side: Any, **changes: Any) -> None:
    with side.uow() as uow:
        old = uow.repo(AutopilotRepository).get(side.proj)
        uow.repo(AutopilotRepository).save(replace(old, **changes), expected_version=old.row_version)
        uow.commit()


def autopilot_run(side: Any, *, code: str | None = None, owner: bool = False) -> Any:
    run, _, _ = seeded(side, run_status=RunStatus.PAUSED if code or owner else RunStatus.RUNNING)
    with side.uow() as uow:
        run = replace(
            run, autopilot=True, stop_code=code, pause_source="owner" if owner else "system" if code else None
        )
        uow.repo(RunRepository).save(run, expected_version=run.row_version)
        uow.commit()
    patch_state(side, current_run_id=run.id)
    return run


def test_disabled_start_and_readonly_status(side: Any):
    initial = side.client.ask(GetAutopilotStatus(project_id=str(side.proj)))
    assert initial["effective_state"] == "disabled"
    assert initial["state"] == "idle"
    assert state_of(side) is None
    with pytest.raises(SkmError) as caught:
        command(side, StartAutopilot)
    assert caught.value.code.value == "AUTOPILOT_NOT_ENABLED"
    assert state_of(side) is None


def test_session_continue_new_session_and_project_event(side: Any):
    configure(side)
    command(side, StartAutopilot, limits={"max_runs": 5, "max_wall_seconds": 120})
    original = state_of(side)
    counters = {**original.counters, "runs_started": 3, "last_blocker": {"task_key": "P1/U1", "code": "X"}}
    patch_state(side, counters=counters)
    for cls in (PauseAutopilot, StopAutopilot):
        command(side, cls)
        side.clock.advance(timedelta(seconds=10))
        command(side, StartAutopilot, limits={"max_runs": 99})
        current = state_of(side)
        assert current.session_started_at == original.session_started_at
        assert current.counters == counters
        assert current.session_limits["max_runs"] == 5
        assert current.stop_code is None
    command(side, StopAutopilot)
    with pytest.raises(SkmError):
        side.client.dispatch(StartAutopilot(project_id=str(side.proj), new_session=True, reason=" "))
    command(side, StartAutopilot, new_session=True)
    assert state_of(side).counters["last_blocker"] is None
    backend = side.app.uow_factory._backend.committed
    events = [e for e in backend.core.events if ":autopilot-state-changed:" in e.type]
    assert events[-1].stream_kind == "project"
    assert events[-1].stream_id == side.proj
    assert events[-1].payload["session_reset"] is True
    assert events[-1].payload["previous_counters"] == counters


def test_fresh_approved_alias_queue_starts_once_and_restart_keeps_run(side: Any):
    from skm.modules.planning.public import get_plan_ref

    with side.uow(readonly=True) as uow:
        alias = get_plan_ref(uow, side.plan1).alias
    configure(side, queue=[alias], accept_advisories=True)
    side.client.dispatch(ValidateForExecution(side.plan1, side.rev2))
    command(side, StartAutopilot)
    started = tick(side)
    assert started["action"] == "started"
    current = state_of(side)
    assert current.current_run_id is not None
    assert current.counters["runs_started"] == 1
    assert tick(side)["action"] == "waiting"
    assert state_of(side).current_run_id == current.current_run_id
    with side.uow(readonly=True) as uow:
        run = uow.repo(RunRepository).get(current.current_run_id)
        assert run.autopilot
        assert run.revision_id == side.rev2


def test_readiness_stale_is_never_started(side: Any):
    configure(side, queue=[str(side.plan1)], accept_advisories=True)
    side.client.dispatch(ValidateForExecution(side.plan1, side.rev2))
    command(side, StartAutopilot)
    side.client.dispatch(
        settings.SetValue.from_json(
            {
                "scope": {"level": "project", "scope_id": str(side.proj)},
                "key": "execution.readiness.max_age_seconds",
                "value": 60,
                "reason": "Expiry test",
            }
        )
    )
    side.clock.advance(timedelta(seconds=61))
    result = tick(side)
    assert result["stop_code"] == "AUTOPILOT_NOT_READY"
    assert state_of(side).counters["runs_started"] == 0


def test_no_work_and_drain_do_not_dispatch(side: Any):
    configure(side)
    command(side, StartAutopilot)
    assert tick(side)["stop_code"] == "AUTOPILOT_NO_WORK"
    command(side, StartAutopilot)
    command(side, DrainAutopilot)
    assert tick(side)["action"] == "drained"
    assert state_of(side).state is AutopilotStateKind.IDLE


def test_drain_and_pause_leave_current_run_and_do_not_start_next(side: Any):
    configure(side, queue=[str(side.plan1)])
    command(side, StartAutopilot)
    run = autopilot_run(side)
    command(side, PauseAutopilot)
    assert tick(side)["action"] == "waiting"
    command(side, DrainAutopilot)
    assert tick(side)["action"] == "waiting"
    with side.uow() as uow:
        old = uow.repo(RunRepository).get(run.id)
        uow.repo(RunRepository).save(
            replace(old, status=RunStatus.SUCCEEDED, finished_at=side.clock.now()),
            expected_version=old.row_version,
        )
        uow.commit()
    assert tick(side)["action"] == "drained"
    assert state_of(side).counters["runs_started"] == 0


def test_restart_after_deadline_fires_before_resume(side: Any):
    configure(side)
    command(side, StartAutopilot, limits={"max_wall_seconds": 60})
    autopilot_run(side, code="RUNTIME_TIMEOUT")
    command(side, PauseAutopilot)
    side.clock.advance(timedelta(seconds=60))
    command(side, StartAutopilot)
    assert tick(side)["stop_code"] == "AUTOPILOT_MAX_WALL"


@pytest.mark.parametrize(
    ("code", "owner", "expected"),
    [
        ("RUNTIME_TIMEOUT", False, "resume"),
        ("MODEL_UNAVAILABLE", False, "resume"),
        ("RUNTIME_TRANSPORT", False, "resume"),
        ("RUNTIME_OVERLOADED", False, "resume"),
        ("RUNTIME_TIMEOUT", True, "waiting"),
        ("RESULT_INVALID", False, "stop"),
        ("BUDGET_EXHAUSTED", False, "stop"),
        ("QUOTA_EXHAUSTED", False, "stop"),
    ],
)
def test_paused_outcomes_and_owner_escalation(side: Any, code: str, owner: bool, expected: str):
    configure(side)
    command(side, StartAutopilot)
    run = autopilot_run(side, code=code, owner=owner)
    result = tick(side)
    assert result["action"] == expected
    with side.uow(readonly=True) as uow:
        current = uow.repo(RunRepository).get(run.id)
        if expected == "resume":
            assert current.status is RunStatus.RUNNING
            assert current.stop_code is None
        elif expected == "stop":
            requests = uow.repo(ExecutionQueries).inbox_page((side.proj,), None, 200, frozenset())["items"]
            assert any(r["audience"] == "owner" and r["kind"] == "escalation" for r in requests)


def test_stale_system_resume_is_noop_and_keeps_observed_version(side: Any, monkeypatch: pytest.MonkeyPatch):
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import error_for

    configure(side)
    command(side, StartAutopilot)
    run = autopilot_run(side, code="RUNTIME_TIMEOUT")
    before = state_of(side)
    with side.uow(readonly=True) as uow:
        version = uow.repo(RunRepository).get(run.id).row_version

    def stale(cmd: Any, _ctx: Any, _uow: Any) -> Any:
        assert cmd.expected_row_version == version
        raise error_for(ErrorCode.VERSION_CONFLICT, "concurrent owner pause")

    monkeypatch.setattr(resume_run, "handle", stale)
    assert tick(side)["code"] == "VERSION_CONFLICT"
    assert state_of(side) == before


def test_emergency_cancels_all_project_runs_and_clear_needs_both_permissions(side: Any):
    configure(side)
    command(side, StartAutopilot)
    auto = autopilot_run(side)
    manual, _, _ = seeded(side)
    result = command(side, StopAutopilot, emergency=True)
    assert set(result["cancelled_run_ids"]) >= {str(auto.id), str(manual.id)}
    with pytest.raises(SkmError) as caught:
        command(side, StartAutopilot)
    assert caught.value.code.value == "EMERGENCY_STOPPED"
    command(side, StartAutopilot, clear_emergency=True)
    assert not state_of(side).emergency


def test_status_explain_share_effective_config_and_ordered_conditions(side: Any):
    configure(side, queue=[str(side.plan1)])
    command(side, StartAutopilot)
    status = side.client.ask(GetAutopilotStatus(project_id=str(side.proj)))
    explanation = side.client.ask(ExplainAutopilot(project_id=str(side.proj)))
    assert status["queue"]
    assert explanation["status"]["state"] == status["state"]
    assert [c["id"] for c in explanation["stop_conditions"]] == [f"AP{i}" for i in range(1, 21)]
    assert all(key["provenance"] for key in explanation["keys"])
    assert explanation["status"]["nearest_limit"]["id"] in {"AP4", "AP5", "AP17", "AP18"}


def test_service_review_plans_are_excluded(side: Any, monkeypatch: pytest.MonkeyPatch):
    from skm.modules.planning import public as planning

    configure(side, queue=[str(side.plan1)])
    command(side, StartAutopilot)
    original = planning.get_plan_ref
    monkeypatch.setattr(
        planning,
        "get_plan_ref",
        lambda uow, pid: replace(original(uow, pid), purpose=planning.PlanPurpose.REVIEW_REQUESTS),
    )
    assert side.client.ask(GetAutopilotStatus(project_id=str(side.proj)))["queue"] == []
    assert tick(side)["stop_code"] == "AUTOPILOT_NO_WORK"


def test_campaign_lock_precedes_run_locks_and_cas_rejects_stale_write(
    side: Any, monkeypatch: pytest.MonkeyPatch
):
    configure(side)
    command(side, StartAutopilot)
    autopilot_run(side)
    with side.uow(readonly=True) as uow:
        auto_type, run_type = type(uow.repo(AutopilotRepository)), type(uow.repo(RunRepository))
    locks: list[str] = []
    for cls, label in ((auto_type, "autopilot_states"), (run_type, "runs")):
        original = cls.get

        def get(self: Any, key: Any, *, for_update: bool = False, fn: Any = original, name: str = label):
            if for_update:
                locks.append(name)
            return fn(self, key, for_update=for_update)

        monkeypatch.setattr(cls, "get", get)
    tick(side)
    assert locks[0] == "autopilot_states"
    assert "runs" in locks
    before = state_of(side)
    patch_state(side, counters={**before.counters, "runs_started": 2})
    with side.uow() as uow, pytest.raises(SkmError) as caught:
        uow.repo(AutopilotRepository).save(before, expected_version=before.row_version)
    assert caught.value.code.value == "VERSION_CONFLICT"


def test_emergency_rolls_back_state_and_earlier_cancellation(side: Any, monkeypatch: pytest.MonkeyPatch):
    from skm.modules.execution.application.commands import cancel_run

    configure(side)
    command(side, StartAutopilot)
    autopilot_run(side)
    seeded(side)
    before = state_of(side)
    original = cancel_run.handle
    calls: list[Any] = []

    def fail_second(cmd: Any, ctx: Any, uow: Any):
        calls.append(cmd.run_id)
        if len(calls) == 2:
            raise RuntimeError("cancellation fault")
        return original(cmd, ctx, uow)

    monkeypatch.setattr(cancel_run, "handle", fail_second)
    with pytest.raises(SkmError, match="unexpected error"):
        command(side, StopAutopilot, emergency=True)
    assert len(calls) == 2
    assert state_of(side) == before
    with side.uow(readonly=True) as uow:
        assert all(uow.repo(RunRepository).get(rid).status is RunStatus.RUNNING for rid in calls)


def test_follow_switches_streams_discards_old_events_and_returns_terminal_code(
    monkeypatch: pytest.MonkeyPatch,
):
    import io
    from uuid import UUID

    from skm.entrypoints.cli.commands import autopilot as cli

    project, first, second, workspace = (UUID(int=n) for n in (1, 2, 3, 4))
    statuses = iter(
        [
            {"effective_state": "running", "current_run_id": str(second)},
            {"effective_state": "running", "current_run_id": str(second)},
            {"effective_state": "stopped", "current_run_id": str(second), "stop_code": "AUTOPILOT_NO_WORK"},
        ]
    )
    monkeypatch.setattr(cli, "ask", lambda *_a, **_kw: next(statuses))
    monkeypatch.setattr(cli, "_finish", lambda _ctx, s: 0 if s["effective_state"] == "stopped" else None)
    monkeypatch.setattr(cli, "named_query", lambda *_a, **_kw: SimpleNamespace(workspace_id=workspace))
    lines: list[Any] = []
    monkeypatch.setattr(cli, "_line", lambda _ctx, text, data: lines.append((text, data)))
    initial = {"effective_state": "running", "current_run_id": str(first)}

    def events(**kwargs: Any):
        assert kwargs["project_id"] == project
        assert kwargs["workspace_id"] == workspace
        assert kwargs["after"] == 10
        for seq, rid, name in [(11, first, "old-event"), (12, second, "new-event")]:
            yield SimpleNamespace(workspace_seq=seq, stream_kind="run", stream_id=rid, type=name)

    ctx: Any = SimpleNamespace(
        stdout=io.StringIO(),
        client=SimpleNamespace(
            ask_with_meta=lambda _: (initial, SimpleNamespace(events_cursor=10)), project_events=events
        ),
    )
    assert cli.follow(ctx, project) == 0
    assert any(str(second) in text and "switched" in text for text, _ in lines)
    assert not any("old-event" in text for text, _ in lines)
    assert any("new-event" in text for text, _ in lines)


def test_follow_project_read_only_campaign_resumes_at_project_event(side: Any, tmp_path, monkeypatch):
    import json

    from skm.entrypoints.cli.commands import autopilot as cli

    configure(side)
    command(side, StartAutopilot)
    reader = side.restricted_client(["project.read"], scope_id=side.proj, owner_token=True)
    ctx: Any = SimpleNamespace(client=reader)
    lines = []
    monkeypatch.setattr(cli, "_line", lambda _, text, data: lines.append(data))
    cursor = tmp_path / "cursor.json"
    assert cli.follow(ctx, side.proj, cursor_file=cursor, seconds=0) == 0
    head = json.loads(cursor.read_text())["after"]
    command(side, PauseAutopilot)
    assert cli.follow(ctx, side.proj, cursor_file=cursor, seconds=2) == 4
    assert lines == [
        {
            "type": "urn:skm:execution:event:autopilot-state-changed:v1",
            "stream_kind": "project",
            "stream_id": str(side.proj),
        }
    ]
    assert json.loads(cursor.read_text())["after"] > head


@pytest.mark.parametrize(
    ("state", "code", "expected"),
    [
        ("paused", None, 4),
        ("idle", None, 0),
        ("stopped", "AUTOPILOT_OWNER_NEEDED", 6),
        ("stopped", "AUTOPILOT_MAX_WALL", 0),
    ],
)
def test_follow_exit_codes(state: str, code: str | None, expected: int):
    from skm.entrypoints.cli.commands.autopilot import _finish

    assert _finish(cast("Any", None), {"effective_state": state, "stop_code": code}) == expected


def test_background_only_dispatches_system_ticks(side: Any):
    from skm.background.autopilot import Autopilot

    calls: list[Any] = []
    service = Autopilot(
        SimpleNamespace(dispatch=lambda cmd, **kw: calls.append((cmd, kw))),
        registry=SimpleNamespace(command_by_name=lambda _: autopilot_tick.SPEC),
        clock=side.clock,
        ids=side.ids,
        projects=lambda: [side.proj],
    )
    assert service.tick().processed == 1
    cmd, kwargs = calls[0]
    assert cmd == {"project_id": str(side.proj)}
    assert kwargs["actor"].principal_id == SYSTEM_PRINCIPAL_ID
    assert kwargs["meta"].surface is Surface.BACKGROUND


@pytest.mark.parametrize("clean_between", [False, True])
def test_blocker_survives_stop_start_and_repeats_in_next_run(side: Any, clean_between: bool):
    from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
    from skm.modules.execution.domain.task import TaskStatus
    from skm.modules.execution.ports import TaskRepository

    configure(side)
    command(side, StartAutopilot)
    run, task, _ = seeded(side)
    with side.uow() as uow:
        uow.repo(RunRepository).save(replace(run, autopilot=True), expected_version=run.row_version)
        task = replace(
            task,
            status=TaskStatus.BLOCKED,
            blocking_reason=blocking_reason(
                BlockingCode.BLOCKED_BY_DEPENDENCY,
                task_id=task.id,
                refs={"prerequisite_task_ids": []},
                now=side.clock.now(),
                message="dependency",
            ),
        )
        uow.repo(TaskRepository).save(task, expected_version=task.row_version)
        uow.commit()
    patch_state(
        side,
        current_run_id=run.id,
        counters={
            "last_blocker": {"task_key": task.display_key, "code": task.blocking_reason.code.value},
            "last_blocker_run_id": "previous-run",
        },
    )
    if clean_between:
        from skm.modules.execution.domain.autopilot import AutopilotFacts

        middle, _, _ = seeded(side)
        with side.uow(readonly=True) as uow:
            clean = autopilot_tick.fold_counters(
                uow.repo(AutopilotRepository).get(side.proj),
                replace(middle, status=RunStatus.SUCCEEDED, autopilot=True, finished_at=side.clock.now()),
                [],
                None,
                AutopilotFacts(),
                uow,
            )
        patch_state(side, counters=clean.counters)
    command(side, StopAutopilot)
    command(side, StartAutopilot)
    result = tick(side)
    assert (result.get("stop_code") == "AUTOPILOT_REPEATED_BLOCKER") is not clean_between


def test_session_event_counters_are_replayed_once_and_acceptance_resets_decisions(side: Any):
    from skm.modules.execution.application._events import cause, emit

    configure(side)
    command(side, StartAutopilot)
    run = autopilot_run(side)
    with side.uow() as uow:
        for kind in ("advisor", "policy"):
            emit(
                uow,
                run,
                "decision-answered",
                {
                    "request_id": str(side.new_id()),
                    "kind": "question",
                    "answered_by_kind": kind,
                    "record_as_plan_decision": False,
                },
                cause("wait_changed"),
            )
        uow.commit()
    tick(side)
    assert state_of(side).counters["auto_decisions"] == 2
    tick(side)
    assert state_of(side).counters["auto_decisions"] == 2
    from skm.modules.execution.ports import TaskRepository

    with side.uow() as uow:
        task = uow.repo(TaskRepository).list_for_run(run.id)[0]
        emit(
            uow,
            run,
            "task-accepted",
            {"task_id": str(task.id), "clearance": {}, "carried_forward": False},
            cause("wait_changed"),
        )
        uow.commit()
    tick(side)
    assert state_of(side).counters["auto_decisions"] == 0


@pytest.mark.parametrize("seconds", [300, 0, -1])
def test_quota_wait_preserves_run_and_returns_next_check(
    side: Any, monkeypatch: pytest.MonkeyPatch, seconds: int
):
    from skm.modules.execution.application.queries import explain_autopilot

    configure(side)
    command(side, StartAutopilot)
    run = autopilot_run(side, code="QUOTA_EXHAUSTED")
    original = explain_autopilot.observe
    reset = side.clock.now() + timedelta(seconds=seconds)

    def observed(*args: Any):
        facts, blocker, events = original(*args)
        return replace(facts, quota_reset_at=reset), blocker, events

    monkeypatch.setattr(autopilot_tick, "observe", observed)
    result = tick(side)
    assert result["action"] == ("wait_quota" if seconds > 0 else "resume")
    assert result.get("next_check_at") == (reset.isoformat() if seconds > 0 else None)
    with side.uow(readonly=True) as uow:
        expected = RunStatus.PAUSED if seconds > 0 else RunStatus.RUNNING
        assert uow.repo(RunRepository).get(run.id).status is expected


def test_new_session_anchors_current_run_history_instead_of_recounting(side: Any):
    configure(side)
    command(side, StartAutopilot)
    run = autopilot_run(side)
    patch_state(side, counters={"auto_decisions": 9})
    command(side, StopAutopilot)
    command(side, StartAutopilot, new_session=True)
    assert state_of(side).counters["event_run_id"] == str(run.id)
    tick(side)
    assert state_of(side).counters["auto_decisions"] == 0


def test_review_and_check_stagnation_uses_round_history():
    from skm.modules.execution.application.queries.explain_autopilot import stagnant_rounds

    assert stagnant_rounds([3, 3, 4]) == 2
    assert stagnant_rounds([3, 2, 2]) == 1
    assert stagnant_rounds([3, 0, 0]) == 0


@pytest.mark.parametrize("missing", ["run.control", "deviation.accept"])
def test_clear_emergency_requires_each_permission_on_project(
    side: Any, monkeypatch: pytest.MonkeyPatch, missing: str
):
    from skm.application_bus.ports import AuthzDecision

    configure(side)
    command(side, StartAutopilot)
    command(side, StopAutopilot, emergency=True)
    before = state_of(side)
    cls = type(side.app.bus._authorizer)
    original = cls.authorize_basis

    def authorize(self: Any, uow: Any, actor: Any, permission: str, chain: Any):
        if permission == missing:
            assert chain[-1].id == side.proj
            return AuthzDecision(False, "ROLE_LACKS_PERMISSION")
        return original(self, uow, actor, permission, chain)

    monkeypatch.setattr(cls, "authorize_basis", authorize)
    with pytest.raises(SkmError) as caught:
        command(side, StartAutopilot, clear_emergency=True)
    assert caught.value.code.value == "FORBIDDEN"
    assert state_of(side) == before
