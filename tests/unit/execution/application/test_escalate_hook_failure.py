"""Unit tests for ``execution.escalate_blocking_hook_failure`` subscriber and manifest wiring (P10.08.a)."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast, override
from uuid import UUID

import pytest

from skm.application_bus.ports import EventReader
from skm.application_bus.registry import SubscriberSpec
from skm.bootstrap.modules import MANIFESTS
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.modules.execution.application import subscribers
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.decision_request import Audience, DecisionKind, DecisionState
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.module import MODULE as EXECUTION_MODULE
from skm.modules.execution.ports import (
    AttemptRepository,
    DecisionRepository,
    ExecutionQueries,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.modules.integrations.application.commands.record_hook_delivery_failure import (
    handle as record_failure,
)
from skm.modules.integrations.application.subscribers import default_hookable_event_types
from skm.modules.integrations.domain.events import HookDeliveryFailed
from skm.modules.integrations.generated.commands import (
    RecordHookDeliveryFailure,
    RecordHookDeliveryFailureScope,
)
from skm.modules.integrations.module import bind_hook_subscribers
from skm.platform.logging.logger import StructLogger

from ._support import _shared_side as _shared_side
from ._support import context, seed_stage, seed_task, seeded
from ._support import side as side

HOOK_FAILED_URN = "urn:skm:integrations:event:hook-delivery-failed:v1"


class _CaptureLogger(StructLogger):
    def __init__(self) -> None:
        super().__init__("execution.test")
        self.records: list[dict[str, Any]] = []

    @override
    def info(self, event: str, /, **fields: object) -> None:
        self.records.append({"level": "info", "event": event, "fields": dict(fields)})

    @override
    def warning(self, event: str, /, **fields: object) -> None:
        self.records.append({"level": "warning", "event": event, "fields": dict(fields)})

    @override
    def error(self, event: str, /, *, exc: BaseException | None = None, **fields: object) -> None:
        self.records.append({"level": "error", "event": event, "fields": dict(fields)})


def _subctx(side: Any, uow: Any, run: Any) -> tuple[Any, _CaptureLogger]:
    ctx = context(side, uow, run)
    sink = _CaptureLogger()
    return (
        SimpleNamespace(
            clock=ctx.clock,
            ids=ctx.ids,
            gateways=ctx.gateways,
            log=sink,
            consumer_id="execution.escalate_blocking_hook_failure",
            config_for=lambda _scope: ctx.config,
        ),
        sink,
    )


def _hook_failed_event(
    side: Any,
    *,
    event_id: UUID | None = None,
    workspace_id: WorkspaceId | None = None,
    blocking: bool = True,
    run_id: str | None = None,
    task_id: str | None = None,
    subscription_id: str = "wf-gate",
    delivery_id: UUID | None = None,
    source_hook_event_id: UUID | None = None,
) -> Any:
    did = delivery_id or side.new_id()
    src_eid = source_hook_event_id or side.new_id()
    return SimpleNamespace(
        id=event_id or side.new_id(),
        workspace_id=side.ws if workspace_id is None else workspace_id,
        type=HOOK_FAILED_URN,
        payload={
            "delivery_id": str(did),
            "subscription_id": subscription_id,
            "subscription_digest": "sha256:" + "a" * 64,
            "event_id": str(src_eid),
            "event_type": "urn:skm:execution:event:task-started:v1",
            "class": "workflow" if blocking else "observation",
            "failure_policy": "deny" if blocking else "warn",
            "blocking": blocking,
            "attempts": 5,
            "reason": "http_500",
            "status": 500,
            "run_id": run_id,
            "task_id": task_id,
            "project_id": str(side.proj),
        },
    )


def test_execution_manifest_registers_subscriber_with_zero_integrations_import_leaks() -> None:
    by_id = {
        spec.consumer_id: spec for spec in EXECUTION_MODULE.subscribers if isinstance(spec, SubscriberSpec)
    }
    assert "execution.escalate_blocking_hook_failure" in by_id
    spec = by_id["execution.escalate_blocking_hook_failure"]
    assert spec.event_types == frozenset({HOOK_FAILED_URN})
    assert spec.handler is subscribers.escalate_blocking_hook_failure

    for rel in ("application/subscribers.py", "module.py"):
        path = Path(subscribers.__file__).resolve().parents[1] / rel
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "integrations" not in alias.name
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                assert "integrations" not in node.module


def test_blocking_workflow_hook_failure_creates_single_owner_escalation_and_deduplicates_redelivery(
    side: Any,
) -> None:
    paused_run, paused_task, paused_attempt = seeded(side, run_status=RunStatus.PAUSED)
    delivery_id = side.new_id()
    hook_event_id = side.new_id()
    received = _hook_failed_event(
        side,
        blocking=True,
        run_id=str(paused_run.id),
        task_id=str(paused_task.id),
        subscription_id="release-gate",
        delivery_id=delivery_id,
        source_hook_event_id=hook_event_id,
    )

    with side.uow() as uow:
        ctx, sink = _subctx(side, uow, paused_run)
        subscribers.escalate_blocking_hook_failure(received, ctx, uow)
        assert not sink.records

        requests = uow.repo(DecisionRepository).open_for_task(paused_task.id)
        assert len(requests) == 1
        req = requests[0]
        assert req.kind is DecisionKind.ESCALATION
        assert req.audience is Audience.OWNER
        assert req.state is DecisionState.OPEN
        assert req.payload["code"] == "HOOK_DELIVERY_FAILED"
        assert req.payload["options"] == ["retry", "ignore", "cancel_run"]
        assert req.payload["subscription_id"] == "release-gate"
        assert req.payload["delivery_id"] == str(delivery_id)
        assert req.payload["hook_event_id"] == str(hook_event_id)

        updated_task = uow.repo(TaskRepository).get(paused_task.id)
        assert updated_task.status is TaskStatus.AWAITING_DECISION
        assert updated_task.blocking_reason is not None
        assert updated_task.blocking_reason.code is BlockingCode.WAITING_OWNER

        cursor = uow.repo(AttemptRepository).get(paused_attempt.id).continuation
        assert cursor is not None
        assert len(cursor.triggers) == 1
        assert cursor.triggers[0].source_event_id == received.id

        subscribers.escalate_blocking_hook_failure(received, ctx, uow)
        redelivered = _hook_failed_event(
            side,
            event_id=side.new_id(),
            blocking=True,
            run_id=str(paused_run.id),
            task_id=str(paused_task.id),
            subscription_id="release-gate",
            delivery_id=delivery_id,
            source_hook_event_id=hook_event_id,
        )
        subscribers.escalate_blocking_hook_failure(redelivered, ctx, uow)

        assert len(uow.repo(DecisionRepository).open_for_task(paused_task.id)) == 1
        after_cursor = uow.repo(AttemptRepository).get(paused_attempt.id).continuation
        assert after_cursor is not None
        assert len(after_cursor.triggers) == 1
        uow.commit()

    with side.uow() as uow:
        repo = uow.repo(DecisionRepository)
        repo.save(replace(repo.get(req.id), state=DecisionState.CANCELLED))
        finished = uow.repo(TaskRepository).get(paused_task.id)
        uow.repo(TaskRepository).save(
            replace(
                finished,
                status=TaskStatus.CANCELLED,
                blocking_reason=None,
                row_version=finished.row_version + 1,
            ),
            expected_version=finished.row_version,
        )
        ctx, _ = _subctx(side, uow, paused_run)
        subscribers.escalate_blocking_hook_failure(redelivered, ctx, uow)
        page = uow.repo(ExecutionQueries).inbox_page([ScopeId(paused_run.id)], None, 200, frozenset())
        assert len(page["items"]) == 1
        assert repo.get(req.id).state is DecisionState.CANCELLED
        uow.commit()

    active_run, active_task, _ = seeded(side, run_status=RunStatus.RUNNING)
    active_ev = _hook_failed_event(
        side,
        blocking=True,
        run_id=str(active_run.id),
        task_id=str(active_task.id),
        subscription_id="live-gate",
    )
    with side.uow() as uow:
        ctx, _ = _subctx(side, uow, active_run)
        subscribers.escalate_blocking_hook_failure(active_ev, ctx, uow)
        subscribers.escalate_blocking_hook_failure(active_ev, ctx, uow)
        assert uow.repo(TaskRepository).get(active_task.id).status is TaskStatus.AWAITING_DECISION
        assert len(uow.repo(DecisionRepository).open_for_task(active_task.id)) == 1
        uow.commit()


def test_blocking_hook_failure_targets_named_task_and_supports_run_level_escalation(side: Any) -> None:
    run, first_task, _ = seeded(side, run_status=RunStatus.PAUSED)
    with side.uow() as uow:
        second_task = seed_task(side, uow, run.id, status=TaskStatus.READY, display_key="P1.1/U2")
        ctx, _ = _subctx(side, uow, run)
        received = _hook_failed_event(
            side,
            blocking=True,
            run_id=str(run.id),
            task_id=str(second_task.id),
            subscription_id="gate-task-2",
        )
        subscribers.escalate_blocking_hook_failure(received, ctx, uow)
        assert not uow.repo(DecisionRepository).open_for_task(first_task.id)
        reqs = uow.repo(DecisionRepository).open_for_task(second_task.id)
        assert len(reqs) == 1
        assert reqs[0].task_id == second_task.id

        for t in (first_task, uow.repo(TaskRepository).get(second_task.id)):
            uow.repo(TaskRepository).save(
                replace(
                    t,
                    status=TaskStatus.CANCELLED,
                    blocking_reason=None,
                    row_version=t.row_version + 1,
                ),
                expected_version=t.row_version,
            )
        run_level_event = _hook_failed_event(
            side,
            blocking=True,
            run_id=str(run.id),
            subscription_id="gate-run-level",
        )
        subscribers.escalate_blocking_hook_failure(run_level_event, ctx, uow)
        subscribers.escalate_blocking_hook_failure(run_level_event, ctx, uow)

        inbox = uow.repo(ExecutionQueries).inbox_page(
            [ScopeId(run.id)], None, 50, frozenset({DecisionKind.ESCALATION})
        )
        run_reqs = [item for item in inbox["items"] if item["task_id"] is None]
        assert len(run_reqs) == 1
        assert isinstance(run_reqs[0]["payload"], dict)
        assert run_reqs[0]["payload"]["options"] == ["retry", "ignore", "cancel_run"]
        uow.commit()


def test_observation_non_blocking_missing_and_terminal_runs_emit_audit_only_without_mutation(
    side: Any,
) -> None:
    run, task, _ = seeded(side, run_status=RunStatus.RUNNING)
    foreign_ws = WorkspaceId(UUID(int=99999))

    with side.uow() as uow:
        ctx, sink = _subctx(side, uow, run)

        subscribers.escalate_blocking_hook_failure(
            _hook_failed_event(side, blocking=False, run_id=str(run.id)), ctx, uow
        )
        subscribers.escalate_blocking_hook_failure(
            _hook_failed_event(side, blocking=True, run_id=None), ctx, uow
        )
        subscribers.escalate_blocking_hook_failure(
            _hook_failed_event(side, blocking=True, run_id=str(side.new_id())), ctx, uow
        )
        subscribers.escalate_blocking_hook_failure(
            _hook_failed_event(side, workspace_id=foreign_ws, blocking=True, run_id=str(run.id)), ctx, uow
        )

        current_run = uow.repo(RunRepository).get(run.id)
        uow.repo(RunRepository).save(
            replace(
                current_run,
                status=RunStatus.CANCELLED,
                finished_at=side.clock.now(),
                pause_source=None,
                pause_reason=None,
                stop_code=None,
                row_version=current_run.row_version + 1,
            ),
            expected_version=current_run.row_version,
        )
        subscribers.escalate_blocking_hook_failure(
            _hook_failed_event(side, blocking=True, run_id=str(run.id)), ctx, uow
        )

        assert not uow.repo(DecisionRepository).open_for_task(task.id)
        assert uow.repo(TaskRepository).get(task.id).status == task.status
        reasons = [rec["fields"]["reason"] for rec in sink.records]
        assert reasons == [
            "non_blocking",
            "missing_run_id",
            "run_not_found",
            "workspace_mismatch",
            "terminal_run",
        ]


def test_fanout_binding_covers_every_declared_hookable_type() -> None:
    manifests = bind_hook_subscribers(MANIFESTS)
    module = next(m for m in manifests if m.id == "integrations")
    (fanout,) = module.subscribers
    assert isinstance(fanout, SubscriberSpec)
    declared = {event.event_type for m in manifests for event in m.events}
    assert fanout.event_types == (default_hookable_event_types() & declared) | {
        "urn:skm:integrations:event:hook-test-requested:v1"
    }
    assert "urn:skm:planning:event:plan-created:v1" in fanout.event_types


@pytest.mark.parametrize(
    "phase", ["selected", *(state.value for state in sorted(ACTIVE_STAGE_STATES)), "terminal"]
)
def test_busy_or_terminal_attempt_preserves_one_durable_escalation(side: Any, phase: str) -> None:
    run, task, attempt = seeded(
        side,
        cursor=phase == "selected",
        attempt_state=AttemptState.COMPLETED if phase == "terminal" else AttemptState.RUNNING,
    )
    received = _hook_failed_event(side, run_id=str(run.id), task_id=str(task.id))
    with side.uow() as uow:
        if phase not in {"selected", "terminal"}:
            from skm.modules.execution.domain.stage_record import StageState

            seed_stage(side, uow, attempt, state=StageState(phase))
        before = uow.repo(AttemptRepository).get(attempt.id)
        history = uow.repo(StageRepository).history(attempt.id)
        ctx, log = _subctx(side, uow, run)
        subscribers.escalate_blocking_hook_failure(received, ctx, uow)
        requests = uow.repo(DecisionRepository).open_for_task(task.id)
        assert len(requests) == 1
        request_id = requests[0].id
        assert requests[0].payload["code"] == "HOOK_DELIVERY_FAILED"
        assert uow.repo(AttemptRepository).get(attempt.id) == before
        assert uow.repo(StageRepository).history(attempt.id) == history
        assert log.records[0]["event"] == "execution.hook_delivery_failure.advance_deferred"
        uow.commit()
    with side.uow() as uow:
        ctx, _ = _subctx(side, uow, run)
        subscribers.escalate_blocking_hook_failure(received, ctx, uow)
        assert [r.id for r in uow.repo(DecisionRepository).open_for_task(task.id)] == [request_id]
        assert uow.repo(TaskRepository).get(task.id).status is TaskStatus.AWAITING_DECISION
        uow.commit()


@pytest.mark.parametrize("payload_run", [True, False])
def test_failure_command_extracts_execution_refs_from_source_envelope(payload_run: bool) -> None:
    ws, rid, tid, eid, did = (UUID(int=i) for i in range(1, 6))
    source = SimpleNamespace(
        workspace_id=ws,
        stream_kind="run",
        stream_id=rid,
        payload={"task_id": str(tid), **({"run_id": str(rid)} if payload_run else {})},
    )
    reader = SimpleNamespace(by_ids=lambda ids: [source], after_workspace_seq=lambda *args, **kw: ())
    recorded = []

    def repo(port: object) -> Any:
        assert port is EventReader
        return reader

    result = record_failure(
        RecordHookDeliveryFailure(
            delivery_id=did,
            subscription_id="gate",
            subscription_digest="sha256:" + "a" * 64,
            event_id=eid,
            event_type="urn:skm:execution:event:run-finished:v1",
            class_="workflow",
            failure_policy="deny",
            attempts=5,
            reason="http_500",
            status=500,
            scope=RecordHookDeliveryFailureScope(kind="workspace", id=ws),
        ),
        cast("Any", SimpleNamespace()),
        cast("Any", SimpleNamespace(repo=repo, record=recorded.append)),
    )
    assert result.recorded
    assert len(recorded) == 1
    event = recorded[0]
    assert isinstance(event, HookDeliveryFailed)
    assert event.payload()["run_id"] == str(rid)
    assert event.payload()["task_id"] == str(tid)
    assert event.blocking is True
