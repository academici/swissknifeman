"""A relay that crashes around a subscriber never runs its effect twice (testing §8, kernel-platform §4.5).

The real relay pass runs over the ``backend`` fixture (memory and PostgreSQL). The subscriber's effect is a
project scope written in the delivery unit of work. ``OUTBOX_AFTER_HANDLER`` fails after the effect, before
the receipt and the ``delivered`` mark: everything rolls back and the next due delivery runs the effect once.
``faulty_uow_factory`` crashes the relay after a commit: after the claim (the rows stay claimed until the
claim expires, then another relay delivers them) and after the delivery (the effect, the receipt and the mark
are committed together, so nothing is delivered again). After every crash the check is the committed effects,
receipts and outbox rows, and that a later pass adds nothing.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, cast

import pytest

from fakes.app import FakeConfigLoader, FakeGateways
from fakes.demo_module import ON_ECHOED, PERMISSIONS, Echo, manifest
from skm.application_bus.context import SubscriberContext
from skm.application_bus.registry import BusRegistry
from skm.application_bus.subscribers import DeliveryOutcome, DeliverySettings, OutboxRelayPass
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import ScopeId
from skm.kernel.ports_uow import UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.platform.logging.logger import get_logger
from support import backend as backend_support
from support import pg as pg_support
from support.backend import PostgresTestBackend, TestBackend
from support.fault_injection import FaultPlan, FaultPoint, InjectedFault, faulty_uow_factory

# Fixtures by name: pytest finds them through the names this module holds.
backend = backend_support.backend
pg_session = pg_support.pg_session
test_database = pg_support.test_database
clean_test_database = pg_support.clean_test_database

CONSUMER = ON_ECHOED.consumer_id
SETTINGS = DeliverySettings(max_attempts=5, backoff_seconds=60, backoff_max_seconds=600)
DUE_AGAIN = timedelta(seconds=720)
EXPIRED = timedelta(seconds=301)  # past the claim expiry of both adapters


def start(backend: TestBackend) -> None:
    if backend.kind == "postgres":
        (row,) = cast("PostgresTestBackend", backend).execute("SELECT clock_timestamp()")
        backend.clock.set(cast("datetime", row[0]))
    backend.app().dispatch(Echo(workspace_id=backend.seed.workspace_id, text="crash"))


def subscriber(plan: FaultPlan, calls: list[int]) -> Callable[..., None]:
    def handler(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
        workspace = envelope.workspace_id
        assert workspace is not None
        calls.append(ctx.attempt)
        uow.repo(ScopeRegistry).create(
            ScopeId(ctx.ids.new_id()), ScopeKind.PROJECT, parent=ScopeId(workspace), workspace_id=workspace
        )
        plan.maybe_fail(FaultPoint.OUTBOX_AFTER_HANDLER)

    return handler


def relay(
    backend: TestBackend,
    handler: Callable[..., None],
    *,
    uow_factory: UnitOfWorkFactory | None = None,
    relay_id: str = "relay-1",
) -> OutboxRelayPass:
    spec: Any = replace(ON_ECHOED, handler=handler)
    registry = BusRegistry.build(
        (manifest(subscribers=(spec,)),),
        schemas=backend.schemas,
        permission_catalog=PERMISSIONS,
        disabled_modules=frozenset(),
    )
    return OutboxRelayPass(
        registry=registry,
        uow_factory=uow_factory or backend.uow_factory,
        config=cast("Any", FakeConfigLoader()),
        settings=lambda: SETTINGS,
        clock=backend.clock,
        ids=backend.ids,
        gateways=cast("Any", FakeGateways()),
        log=get_logger("tests.recovery.outbox"),
        relay_id=relay_id,
        batch_size=10,
    )


def committed(backend: TestBackend) -> tuple[int, int, list[tuple[str, int]]]:
    """Effects (project scopes beyond the seed), receipts and the subscriber's outbox rows."""
    counts = backend.table_counts("skm_core")
    rows = [(row.state, row.attempts) for row in backend.outbox_rows() if row.destination == CONSUMER]
    return counts["scopes"] - 3, counts["consumer_receipts"], rows


def test_a_crash_after_the_handler_rolls_back_and_the_redelivery_runs_the_effect_once(
    backend: TestBackend,
) -> None:
    start(backend)
    plan = FaultPlan({FaultPoint.OUTBOX_AFTER_HANDLER: 1})
    calls: list[int] = []
    worker = relay(backend, subscriber(plan, calls))
    assert worker.run_once() == {DeliveryOutcome.FAILED: 1, DeliveryOutcome.DELIVERED: 1}
    assert committed(backend) == (0, 0, [("failed", 1)])  # effect, receipt and mark rolled back together
    backend.clock.advance(DUE_AGAIN)
    assert worker.run_once() == {DeliveryOutcome.DELIVERED: 1}
    assert committed(backend) == (1, 1, [("delivered", 2)])
    backend.clock.advance(DUE_AGAIN + EXPIRED)
    assert worker.run_once() == {}
    assert calls == [1, 2]
    assert committed(backend) == (1, 1, [("delivered", 2)])


def test_a_crash_after_the_claim_is_reclaimed_by_another_relay_after_expiry(backend: TestBackend) -> None:
    start(backend)
    plan = FaultPlan({FaultPoint.UOW_AFTER_COMMIT: 1})  # the first commit of the pass is the claim
    calls: list[int] = []
    handler = subscriber(FaultPlan({}), calls)
    crashed = relay(backend, handler, uow_factory=faulty_uow_factory(backend.uow_factory, plan))
    with pytest.raises(InjectedFault):
        crashed.run_once()
    assert committed(backend) == (0, 0, [("pending", 1)])  # claimed, nothing delivered
    survivor = relay(backend, handler, relay_id="relay-2")
    assert survivor.run_once() == {DeliveryOutcome.DELIVERED: 1}  # only sse: the claim is still live
    backend.clock.advance(EXPIRED)
    assert survivor.run_once() == {DeliveryOutcome.DELIVERED: 1}
    assert calls == [2]
    assert committed(backend) == (1, 1, [("delivered", 2)])


def test_a_crash_after_the_delivery_commit_never_delivers_again(backend: TestBackend) -> None:
    start(backend)
    plan = FaultPlan({FaultPoint.UOW_AFTER_COMMIT: 2})  # claim, then the delivery of demo.on_echoed
    calls: list[int] = []
    handler = subscriber(FaultPlan({}), calls)
    worker = relay(backend, handler, uow_factory=faulty_uow_factory(backend.uow_factory, plan))
    outcomes = worker.run_once()
    assert outcomes == {
        DeliveryOutcome.STALE: 1,
        DeliveryOutcome.DELIVERED: 1,
    }  # the late failure marks nothing
    assert committed(backend) == (1, 1, [("delivered", 1)])
    backend.clock.advance(DUE_AGAIN + EXPIRED)
    assert relay(backend, handler, relay_id="relay-2").run_once() == {}
    assert calls == [1]
    assert committed(backend) == (1, 1, [("delivered", 1)])


def test_a_failed_delivery_commit_leaves_nothing_and_is_retried(backend: TestBackend) -> None:
    start(backend)
    plan = FaultPlan({FaultPoint.UOW_BEFORE_COMMIT: 2})  # the delivery commit itself fails
    calls: list[int] = []
    handler = subscriber(FaultPlan({}), calls)
    worker = relay(backend, handler, uow_factory=faulty_uow_factory(backend.uow_factory, plan))
    assert worker.run_once() == {DeliveryOutcome.FAILED: 1, DeliveryOutcome.DELIVERED: 1}
    assert committed(backend) == (0, 0, [("failed", 1)])
    backend.clock.advance(DUE_AGAIN)
    assert worker.run_once() == {DeliveryOutcome.DELIVERED: 1}
    assert calls == [1, 2]
    assert committed(backend) == (1, 1, [("delivered", 2)])
