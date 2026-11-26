"""A command that crashes between state, events, outbox and receipt is all or none (testing spec §8/§11).

The real bus runs over the ``backend`` fixture (memory and PostgreSQL, where every unit of work really
COMMITs). ``faulty_uow_factory`` injects ``UOW_BEFORE_COMMIT`` (nothing may remain) and ``UOW_AFTER_COMMIT``
(everything is committed, only the response is lost: the same key replays the stored result without a second
effect). A handler that crashes after its state write, after its event, or a commit that fails after the
events and outbox rows were written, leaves nothing either; the repeated key then runs the command once.
After every crash the check is the committed tables, the events, the outbox and a safe repeat.
"""

from collections.abc import Callable, Mapping
from dataclasses import replace
from enum import StrEnum
from typing import Any
from uuid import UUID

import pytest

from fakes.demo_module import ECHO, PERMISSIONS, Echo, EchoResult, handle_echo, manifest

# Execution-specific boundaries use the same production Bus and PostgreSQL UoW.
from fixtures.execution.harness import recovery as recovery
from fixtures.execution.protocol import agent, client_with_uow, finalize, handoff, seal_command
from skm.application_bus.context import CommandContext
from skm.application_bus.registry import BusRegistry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound
from skm.kernel.ids import EventId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.execution.ports import AttemptRepository, OutputRepository, StageRepository
from support import backend as backend_support
from support import pg as pg_support
from support.backend import TestBackend
from support.fault_injection import (
    FaultPlan,
    FaultPoint,
    InjectedFault,
    event_fault_factory,
    faulty_uow_factory,
)

# Fixtures by name: pytest finds them through the names this module holds.
backend = backend_support.backend
pg_session = pg_support.pg_session
test_database = pg_support.test_database
clean_test_database = pg_support.clean_test_database

KEY = "crash-key-1"
# What one executed demo.echo with its state write adds to skm_core: a project scope, the event and its two
# outbox rows (demo.on_echoed, sse), the receipt, the allowed audit row and the two counters it starts.
ONE_COMMAND = {
    "scopes": 1,
    "domain_events": 1,
    "outbox": 2,
    "idempotency_receipts": 1,
    "audit_records": 1,
    "event_streams": 1,
    "workspace_event_counters": 1,
}


class Crash(StrEnum):
    AFTER_STATE = "after_state"  # the handler wrote a scope, then failed
    AFTER_EVENT = "after_event"  # the handler wrote a scope and recorded its event, then failed
    IN_COMMIT = "in_commit"  # the commit failed after state, event and outbox rows were written


def counts(backend: TestBackend) -> dict[str, int]:
    return dict(backend.table_counts("skm_core"))


def grown(before: Mapping[str, int], after: Mapping[str, int]) -> dict[str, int]:
    return {table: after[table] - before[table] for table in after if after[table] != before[table]}


def echo(backend: TestBackend, text: str = "crash") -> Echo:
    return Echo(workspace_id=backend.seed.workspace_id, text=text)


def stateful_echo(crash: Crash | None, fired: list[Crash]) -> Callable[..., EchoResult]:
    """``demo.echo`` that first creates a project scope; the first passage crashes at ``crash``."""

    def handler(cmd: Echo, ctx: CommandContext, uow: UnitOfWork) -> EchoResult:
        workspace = WorkspaceId(cmd.workspace_id)
        project = ScopeId(ctx.ids.new_id())
        uow.repo(ScopeRegistry).create(
            project, ScopeKind.PROJECT, parent=ScopeId(workspace), workspace_id=workspace
        )
        first = crash is not None and not fired
        if first and crash is Crash.AFTER_STATE:
            fired.append(crash)
            raise RuntimeError("crash after the state write")
        result = handle_echo(cmd, ctx, uow)
        if first and crash is Crash.AFTER_EVENT:
            fired.append(crash)
            raise RuntimeError("crash after the event")
        if first and crash is Crash.IN_COMMIT:
            fired.append(crash)
            uow.outbox.enqueue(EventId(ctx.ids.new_id()), "hook:lost")  # the writer refuses it inside commit
        return result

    return handler


def registry_with(backend: TestBackend, handler: Callable[..., EchoResult]) -> BusRegistry:
    spec: Any = replace(ECHO, handler=handler)
    return BusRegistry.build(
        (manifest(commands=(spec,)),),
        schemas=backend.schemas,
        permission_catalog=PERMISSIONS,
        disabled_modules=frozenset(),
    )


def test_a_crash_before_commit_changes_nothing_and_the_key_runs_again(backend: TestBackend) -> None:
    plan = FaultPlan({FaultPoint.UOW_BEFORE_COMMIT: 1})
    app = backend.app(
        uow_factory=faulty_uow_factory(backend.uow_factory, plan),
        registry=registry_with(backend, stateful_echo(None, [])),
    )
    before = counts(backend)
    with pytest.raises(InternalError) as err:
        app.dispatch(echo(backend), idempotency_key=KEY)
    assert isinstance(err.value.__cause__, InjectedFault)
    assert err.value.__cause__.point is FaultPoint.UOW_BEFORE_COMMIT
    assert counts(backend) == before  # no scope, event, outbox row, receipt or audit row
    assert backend.envelopes() == []
    assert backend.outbox_rows() == []

    assert app.dispatch(echo(backend), idempotency_key=KEY) == EchoResult(text="crash")  # runs once now
    assert grown(before, counts(backend)) == ONE_COMMAND
    assert app.dispatch(echo(backend), idempotency_key=KEY) == EchoResult(text="crash")  # and replays
    assert grown(before, counts(backend)) == ONE_COMMAND


def test_a_lost_response_after_commit_replays_the_result_without_a_second_effect(
    backend: TestBackend,
) -> None:
    plan = FaultPlan({FaultPoint.UOW_AFTER_COMMIT: 1})
    app = backend.app(
        uow_factory=faulty_uow_factory(backend.uow_factory, plan),
        registry=registry_with(backend, stateful_echo(None, [])),
    )
    before = counts(backend)
    with pytest.raises(InternalError) as err:
        app.dispatch(echo(backend), idempotency_key=KEY)
    assert isinstance(err.value.__cause__, InjectedFault)
    assert err.value.__cause__.point is FaultPoint.UOW_AFTER_COMMIT
    committed = counts(backend)
    assert grown(before, committed) == ONE_COMMAND  # all of it, once
    (event,) = backend.envelopes()
    assert sorted(row.destination for row in backend.outbox_rows()) == ["demo.on_echoed", "sse"]

    assert app.dispatch(echo(backend), idempotency_key=KEY) == EchoResult(text="crash")
    assert counts(backend) == committed  # the replay wrote nothing
    assert [e.id for e in backend.envelopes()] == [event.id]
    assert plan.hits[FaultPoint.UOW_AFTER_COMMIT] == 1  # the replay never reached a commit


def test_another_body_under_the_committed_key_is_refused_after_a_lost_response(backend: TestBackend) -> None:
    plan = FaultPlan({FaultPoint.UOW_AFTER_COMMIT: 1})
    app = backend.app(uow_factory=faulty_uow_factory(backend.uow_factory, plan))
    with pytest.raises(InternalError):
        app.dispatch(echo(backend), idempotency_key=KEY)
    committed = counts(backend)
    with pytest.raises(Conflict) as err:
        app.dispatch(echo(backend, "another body"), idempotency_key=KEY)
    assert err.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert counts(backend) == committed


@pytest.mark.parametrize("crash", list(Crash))
def test_a_crash_between_state_event_and_receipt_leaves_nothing(backend: TestBackend, crash: Crash) -> None:
    fired: list[Crash] = []
    app = backend.app(registry=registry_with(backend, stateful_echo(crash, fired)))
    before = counts(backend)
    with pytest.raises(InternalError):
        app.dispatch(echo(backend), idempotency_key=KEY)
    assert fired == [crash]
    assert counts(backend) == before
    assert backend.envelopes() == []
    assert backend.outbox_rows() == []

    assert app.dispatch(echo(backend), idempotency_key=KEY) == EchoResult(text="crash")  # runs once now
    assert grown(before, counts(backend)) == ONE_COMMAND
    assert app.dispatch(echo(backend), idempotency_key=KEY) == EchoResult(text="crash")  # and replays
    assert grown(before, counts(backend)) == ONE_COMMAND
    (event,) = backend.envelopes()
    assert event.workspace_seq == 1  # the crashed attempt took no number


@pytest.mark.pg
@pytest.mark.parametrize("point", [FaultPoint.UOW_BEFORE_COMMIT, FaultPoint.UOW_AFTER_COMMIT])
def test_execution_begin_cursor_and_stage_commit_together(recovery, point):
    from contracts.execution._worker_protocol_support import make_case, worker_claim
    from fixtures.execution.harness import recovery_claim
    from skm.modules.execution import public as execution

    side = recovery
    _, _, attempt, _ = make_case(side)
    claimed = recovery_claim(side)
    command = execution.BeginStage(
        claim=worker_claim(side, claimed),
        stage_id="prepare",
        round_no=1,
        input_digest=claimed["instruction"]["input_digest"],
    )
    client = client_with_uow(
        side, side.worker1_client, faulty_uow_factory(side.app.uow_factory, FaultPlan({point: 1}))
    )
    key = f"begin-atomic:{side.new_id()}"
    with pytest.raises(InternalError) as caught:
        client.dispatch(command, idempotency_key=key)
    assert isinstance(caught.value.__cause__, InjectedFault)
    with side.uow(readonly=True) as uow:
        committed = point is FaultPoint.UOW_AFTER_COMMIT
        assert len(uow.repo(StageRepository).history(attempt.id).entries) == int(committed)
        assert (uow.repo(AttemptRepository).get(attempt.id).continuation is None) is committed
    first = side.worker1_client.dispatch(command, idempotency_key=key)
    assert side.worker1_client.dispatch(command, idempotency_key=key) == first
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(StageRepository).history(attempt.id).entries) == 1


@pytest.mark.pg
@pytest.mark.parametrize("point", ["event", "before_commit", "after_commit"])
def test_output_seal_event_state_and_receipt_are_atomic(recovery, point):
    side = recovery
    case = agent(side)
    finalize(side, case)
    handoff(side, case)
    command = seal_command(side, case)
    factory = (
        event_fault_factory(side.app.uow_factory, "output-sealed")
        if point == "event"
        else faulty_uow_factory(
            side.app.uow_factory,
            FaultPlan(
                {FaultPoint.UOW_BEFORE_COMMIT if point == "before_commit" else FaultPoint.UOW_AFTER_COMMIT: 1}
            ),
        )
    )
    client = client_with_uow(side, side.worker1_client, factory)
    key = f"seal-atomic:{side.new_id()}"
    with pytest.raises(InternalError) as caught:
        client.dispatch(command, idempotency_key=key)
    assert isinstance(caught.value.__cause__, InjectedFault)
    with side.uow(readonly=True) as uow:
        assert (uow.repo(OutputRepository).latest(case.attempt.id) is not None) is (point == "after_commit")
    first = side.worker1_client.dispatch(command, idempotency_key=key)
    assert side.worker1_client.dispatch(command, idempotency_key=key) == first


@pytest.mark.pg
@pytest.mark.parametrize("event", ["acceptance-decided", "external-effect-recorded"])
def test_required_execution_event_failure_rolls_back_its_domain_mutation(recovery, event):
    from skm.modules.execution.ports import AcceptanceRepository, EffectRepository
    from support.fault_injection import event_fault_factory

    side = recovery
    factory = event_fault_factory(side.app.uow_factory, event)
    if event == "acceptance-decided":
        from fixtures.execution.acceptance import acceptance_case
        from skm.modules.execution.application._state import load_state
        from skm.modules.execution.application.stages.acceptance_gate import decide
        from skm.modules.execution.domain.review import ReviewClearance
        from unit.execution.application._support import context

        run, task, _ = acceptance_case(side)
        with factory(side.worker1_client._meta(None)) as uow:
            state, _ = load_state(uow, task.id)
            with pytest.raises(InjectedFault):
                decide(
                    state,
                    ReviewClearance.SELF,
                    context(side, uow, run),
                    uow,
                    {"trigger_kind": "stage_outcome", "advance_rule": "K3", "reason_codes": [], "refs": []},
                )
        with side.uow(readonly=True) as uow:
            assert not uow.repo(AcceptanceRepository).decisions_for_task(task.id)
    else:
        from contracts.execution._worker_protocol_support import worker_claim
        from skm.modules.execution import public as execution
        from unit.execution.application._integration_case import integrated_case, local_request

        claimed, ready, _, _ = integrated_case(side)
        target, _slot, request, envelope = local_request(side, claimed, ready)
        command = execution.RecordExternalEffect(
            claim=worker_claim(side, claimed), **envelope, phase="intended", request=request
        )
        client = client_with_uow(side, side.worker1_client, factory)
        with pytest.raises(InternalError) as caught:
            client.dispatch(command, idempotency_key=f"effect-event:{side.new_id()}")
        assert isinstance(caught.value.__cause__, InjectedFault)
        with side.uow(readonly=True) as uow:
            with pytest.raises(NotFound) as missing:
                uow.repo(EffectRepository).get(UUID(target["effect_id"]))
            assert getattr(missing.value, "code", None) is ErrorCode.NOT_FOUND
