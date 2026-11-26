"""External consumers, ``outbox.enqueue``, ``config_for`` and dead-row notifications (memory ∥ postgres).

Every case runs over the ``backend`` fixture: the memory backend and ``PostgresUnitOfWork`` on the cleaned
session test database (``pg`` marker; ``SKM_REQUIRE_PG=1`` makes a missing server a failure). External rows
are enqueued for an instance event (``Noted``: no subscriber row, no ``sse`` row), so a pass handles exactly
the rows a test made; the ``config_for`` cases use workspace events. Time is the backend's ``FrozenClock``; a
crash of a relay is a ``BaseException`` that leaves its claim behind, which expires with the clock.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, cast, override
from uuid import UUID

import pytest

from fakes.app import FakeConfig, FakeConfigLoader, FakeGateways
from fakes.demo_module import ON_ECHOED, PERMISSIONS, Echo, Noted, manifest
from skm.application_bus.context import SubscriberContext
from skm.application_bus.ports import (
    ConsumerReceipts,
    DeliveryPlan,
    GiveUp,
    OutboxEntry,
    OutboxItem,
    OutboxStore,
    RetryAt,
    SendResult,
    Sent,
)
from skm.application_bus.registry import BusRegistry, ExternalConsumerSpec
from skm.application_bus.subscribers import (
    DeliveryOutcome,
    DeliverySettings,
    OutboxRelayPass,
    deliver,
)
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.cancel import CancelToken
from skm.kernel.errors import NotFound
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import EventId, ScopeId
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.platform.logging.logger import get_logger
from support import backend as backend_support
from support import pg as pg_support
from support.backend import PostgresTestBackend, TestBackend

# Fixtures by name: pytest finds them through the names this module holds.
backend = backend_support.backend
pg_backend = backend_support.pg_backend
pg_session = pg_support.pg_session
test_database = pg_support.test_database
clean_test_database = pg_support.clean_test_database

NOTE_STREAM = UUID("01900000-0000-7000-8000-0000000000c3")
SYSTEM = Actor(principal_id=SYSTEM_PRINCIPAL_ID, kind=PrincipalKind.SERVICE, display_name="system")
EXPIRED = timedelta(seconds=301)  # past the claim expiry of both adapters (memory 60 s, PostgreSQL 300 s)
SETTINGS = DeliverySettings(
    max_attempts=3,
    backoff_seconds=60,
    backoff_max_seconds=600,
    timeout_seconds=7,
    visibility_timeout_seconds=300,
)
DUE_AGAIN = timedelta(seconds=SETTINGS.backoff_max_seconds * 1.2)
HOOK = "hook:sub1"
IDLE_IN_TRANSACTION = (
    "SELECT count(*) FROM pg_stat_activity "
    "WHERE datname = current_database() AND state = 'idle in transaction'"
)


class Crash(BaseException):
    pass


# -------------------------------------------------------------------------------------------------- doubles


@dataclass
class Probe:
    """A scriptable ``ExternalConsumer``; each ``send`` takes the next step (default ``Sent``)."""

    backend: TestBackend
    script: list[Any] = field(default_factory=lambda: [])
    plan: DeliveryPlan | None = field(default_factory=lambda: DeliveryPlan(payload={"hook": True}))
    sent: list[tuple[int, float]] = field(default_factory=lambda: [])
    prepared: list[tuple[OutboxItem, SubscriberContext, bool]] = field(default_factory=lambda: [])
    prepare_uows: list[UnitOfWork] = field(default_factory=lambda: [])
    on_prepare: Callable[[SubscriberContext, UnitOfWork], None] | None = None

    def prepare(
        self, item: OutboxItem, envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork
    ) -> DeliveryPlan | None:
        self.prepared.append((item, ctx, uow.readonly))
        self.prepare_uows.append(uow)
        if self.on_prepare is not None:
            self.on_prepare(ctx, uow)
        return self.plan

    def send(
        self, plan: DeliveryPlan, *, attempt: int, timeout_seconds: float, cancel: CancelToken
    ) -> SendResult:
        for uow in self.prepare_uows:  # the unit of work of prepare is closed: no connection, no lock
            with pytest.raises(RuntimeError):
                uow.repo(OutboxStore)
        if self.backend.kind == "postgres":
            assert cast("PostgresTestBackend", self.backend).execute(IDLE_IN_TRANSACTION)[0][0] == 0
        self.sent.append((attempt, timeout_seconds))
        step = self.script.pop(0) if self.script else Sent()
        if callable(step):
            step = step()
        if isinstance(step, BaseException):
            raise step
        return cast("SendResult", step)


class Dispatcher:
    """What the relay needs of the bus; remembers every dispatch and can be told to fail or crash."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, Actor, RequestMeta]] = []
        self.failures: list[BaseException] = []

    def dispatch(self, cmd: object, *, actor: Actor, meta: RequestMeta) -> object:
        if self.failures:
            raise self.failures.pop(0)
        self.calls.append((cmd, actor, meta))
        return None

    @property
    def keys(self) -> list[str | None]:
        return [meta.idempotency_key for _, _, meta in self.calls]


class ScopedLoader(FakeConfigLoader):
    """``effective`` returns the values of the scope asked for and remembers the scopes."""

    def __init__(self, by_scope: dict[Any, dict[str, Any]]) -> None:
        super().__init__()
        self.by_scope = by_scope
        self.asked: list[Any] = []

    @override
    def effective(self, store: Any, scopes: Any, scope: Any, kind: str = "work", **_: Any) -> FakeConfig:
        self.asked.append(scope)
        key = None if scope is None else scope.id
        return FakeConfig(self.by_scope.get(key, {}))


def nothing(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    pass


# -------------------------------------------------------------------------------------------------- helpers


def start(backend: TestBackend) -> None:
    """On PostgreSQL the test clock starts at the database clock (the adapter never lets time go back)."""
    if backend.kind == "postgres":
        (row,) = cast("PostgresTestBackend", backend).execute("SELECT clock_timestamp()")
        backend.clock.set(cast("datetime", row[0]))


def noted(backend: TestBackend, text: str = "n") -> EventId:
    """An instance event: no subscriber row and no ``sse`` row, so only enqueued rows exist."""
    with backend.uow() as uow:
        uow.record(Noted(stream=NOTE_STREAM, text=text))
        uow.commit()
    return backend.envelopes()[-1].id


def enqueue(
    backend: TestBackend, event_id: EventId, destination: str = HOOK, *, at: datetime | None = None
) -> None:
    with backend.uow() as uow:
        uow.outbox.enqueue(event_id, destination, available_at=at)
        uow.commit()


def build_registry(
    backend: TestBackend, probe: Probe | None, *, handler: Callable[..., None] = nothing, **spec: Any
) -> BusRegistry:
    external = (
        () if probe is None else (ExternalConsumerSpec(prefix="hook", factory=lambda ctx: probe, **spec),)
    )
    subscribers: Any = (replace(ON_ECHOED, handler=handler),)
    return BusRegistry.build(
        (manifest(subscribers=subscribers, external_consumers=external),),
        schemas=backend.schemas,
        permission_catalog=PERMISSIONS,
        disabled_modules=frozenset(),
    )


def relay(
    backend: TestBackend,
    probe: Probe | None,
    *,
    relay_id: str = "relay-1",
    config: Any = None,
    dispatcher: Dispatcher | None = None,
    handler: Callable[..., None] = nothing,
    on_dead: Callable[..., object] | None = None,
    max_attempts: int | None = None,
    secrets: bool = True,
) -> OutboxRelayPass:
    return OutboxRelayPass(
        registry=build_registry(backend, probe, handler=handler, on_dead=on_dead, max_attempts=max_attempts),
        uow_factory=backend.uow_factory,
        config=config or cast("Any", FakeConfigLoader()),
        settings=lambda: SETTINGS,
        clock=backend.clock,
        ids=backend.ids,
        gateways=cast("Any", FakeGateways()),
        log=get_logger("tests.outbox_external"),
        relay_id=relay_id,
        batch_size=100,
        jitter=lambda: 0.5,  # no jitter: back-off assertions are exact
        secrets=cast("Any", object()) if secrets else None,
        dispatcher=dispatcher,
        actor=SYSTEM if dispatcher is not None else None,
    )


def entries(backend: TestBackend, destination: str = HOOK) -> list[OutboxEntry]:
    with backend.uow(readonly=True) as uow:
        page = uow.repo(OutboxStore).list(
            destination_prefix=destination, state=None, workspace_id=None, after=None, limit=100
        )
    return list(page.items)


def state_of(backend: TestBackend, destination: str = HOOK) -> list[tuple[str, int, str | None]]:
    return [(e.state.value, e.attempts, e.last_error) for e in entries(backend, destination)]


def receipts(backend: TestBackend) -> int:
    return backend.table_counts("skm_core")["consumer_receipts"]


def seen(backend: TestBackend, event_id: EventId, destination: str = HOOK) -> bool:
    with backend.uow(readonly=True) as uow:
        return uow.repo(ConsumerReceipts).seen(destination, event_id)


def counts(result: dict[DeliveryOutcome, int]) -> dict[str, int]:
    return {outcome.value: n for outcome, n in result.items()}


def pending_notifications(backend: TestBackend) -> int:
    """Dead rows still waiting for their announcement (probing claims them for a moment; it is idempotent)."""
    with backend.uow() as uow:
        found = uow.repo(OutboxStore).claim_dead_notifications(
            prefixes=frozenset({"hook"}), relay_id="probe", now=backend.clock.now(), limit=10
        )
        uow.commit()
    return len(found)


def retry_dead(backend: TestBackend, destination: str = HOOK) -> int:
    with backend.uow() as uow:
        retried = uow.repo(OutboxStore).retry_dead(
            outbox_id=None, event_id=None, destination=destination, now=backend.clock.now()
        )
        uow.commit()
    return retried


def project_scope(backend: TestBackend, workspace: Any) -> ScopeId:
    scope = ScopeId(backend.ids.new_id())
    with backend.uow() as uow:
        uow.repo(ScopeRegistry).create(
            scope, ScopeKind.PROJECT, parent=ScopeId(workspace), workspace_id=workspace
        )
        uow.commit()
    return scope


# -------------------------------------------------------------------------------------------------- enqueue


def test_enqueue_is_refused_in_a_readonly_unit_of_work_and_needs_an_aware_time(backend: TestBackend) -> None:
    event_id = noted(backend)
    with backend.uow(readonly=True) as uow, pytest.raises(RuntimeError, match="readonly"):
        uow.outbox.enqueue(event_id, HOOK)
    naive = datetime(2030, 1, 1)  # noqa: DTZ001 - the point of the case
    with backend.uow() as uow, pytest.raises(ValueError, match="naive"):
        uow.outbox.enqueue(event_id, HOOK, available_at=naive)
    assert backend.outbox_rows() == []


def test_a_delayed_row_waits_for_its_time_across_a_relay_restart(backend: TestBackend) -> None:
    start(backend)
    event_id = noted(backend)
    enqueue(backend, event_id, at=backend.clock.now() + timedelta(hours=1))
    probe = Probe(backend)
    assert relay(backend, probe).run_once() == {}
    assert relay(backend, probe, relay_id="relay-2").run_once() == {}  # a new process: the delay is durable
    assert state_of(backend) == [("pending", 0, None)]
    backend.clock.advance(timedelta(hours=1, seconds=1))
    assert counts(relay(backend, probe, relay_id="relay-3").run_once()) == {"delivered": 1}
    assert probe.sent == [(1, 7)]


# ----------------------------------------------------------------------------------------- the consumer


def test_a_prefixed_row_goes_prepare_send_receipt_and_delivered(backend: TestBackend) -> None:
    start(backend)
    event_id = noted(backend)
    enqueue(backend, event_id)
    probe = Probe(backend)
    assert counts(relay(backend, probe).run_once()) == {"delivered": 1}
    ((item, ctx, readonly),) = probe.prepared
    assert (item.destination, item.attempts, ctx.consumer_id, ctx.attempt, readonly) == (
        HOOK,
        1,
        HOOK,
        1,
        True,
    )
    assert probe.sent == [(1, 7)]  # events.delivery.timeout_seconds: the plan named none
    assert state_of(backend) == [("delivered", 1, None)]
    assert seen(backend, event_id)
    assert relay(backend, probe).run_once() == {}  # nothing is delivered twice
    assert len(probe.sent) == 1


def test_the_plan_timeout_wins_and_a_missing_plan_closes_the_row_with_a_receipt(backend: TestBackend) -> None:
    start(backend)
    first, second = noted(backend, "a"), noted(backend, "b")
    enqueue(backend, first, "hook:a")
    probe = Probe(backend, plan=DeliveryPlan(payload=1, timeout_seconds=2.5))
    assert counts(relay(backend, probe).run_once()) == {"delivered": 1}
    assert probe.sent == [(1, 2.5)]
    enqueue(backend, second, "hook:b")
    probe.plan = None  # the subscription is gone: nothing to send
    assert counts(relay(backend, probe).run_once()) == {"delivered": 1}
    assert len(probe.sent) == 1
    assert state_of(backend, "hook:b") == [("delivered", 1, None)]
    assert seen(backend, second, "hook:b")


def test_a_receipt_turns_a_redelivery_into_a_skipped_duplicate(backend: TestBackend) -> None:
    start(backend)
    event_id = noted(backend)
    enqueue(backend, event_id)
    with backend.uow() as uow:
        uow.repo(ConsumerReceipts).add(HOOK, event_id, backend.clock.now())
        uow.commit()
    probe = Probe(backend)
    assert counts(relay(backend, probe).run_once()) == {"skipped_duplicate": 1}
    assert probe.sent == []
    assert state_of(backend) == [("delivered", 1, None)]
    assert receipts(backend) == 1


def test_an_unregistered_prefix_is_never_claimed(backend: TestBackend) -> None:
    start(backend)
    enqueue(backend, noted(backend))
    assert relay(backend, None, secrets=False).run_once() == {}
    assert state_of(backend) == [("pending", 0, None)]


def test_the_relay_refuses_an_incomplete_composition(backend: TestBackend) -> None:
    probe = Probe(backend)
    with pytest.raises(ValueError, match="SecretResolver"):
        relay(backend, probe, secrets=False)
    with pytest.raises(ValueError, match="dispatcher"):
        relay(backend, probe, on_dead=lambda item, plan, error: object())


# ------------------------------------------------------------------------------- results of ``send``


def test_retry_at_keeps_the_consumers_time_and_the_plan_limit_makes_it_dead(backend: TestBackend) -> None:
    start(backend)
    enqueue(backend, noted(backend))
    later = backend.clock.now() + timedelta(minutes=10)
    probe = Probe(
        backend,
        script=[RetryAt(later, "http_503"), RetryAt(later + timedelta(hours=1), "http_503")],
        plan=DeliveryPlan(payload=1, max_attempts=2),
    )
    consumer = relay(backend, probe)
    assert counts(consumer.run_once()) == {"failed": 1}
    assert state_of(backend) == [("failed", 1, "http_503")]
    assert consumer.run_once() == {}  # not due before the consumer's own time
    backend.clock.set(later + timedelta(seconds=1))
    assert counts(consumer.run_once()) == {"dead": 1}  # attempt 2 == plan.max_attempts
    assert state_of(backend) == [("dead", 2, "http_503")]
    backend.clock.advance(timedelta(days=1))
    assert consumer.run_once() == {}
    assert len(probe.sent) == 2


def test_give_up_is_dead_at_once(backend: TestBackend) -> None:
    start(backend)
    enqueue(backend, noted(backend))
    probe = Probe(backend, script=[GiveUp("CAPABILITY_UNAVAILABLE")])
    assert counts(relay(backend, probe).run_once()) == {"dead": 1}
    assert state_of(backend) == [("dead", 1, "CAPABILITY_UNAVAILABLE")]
    assert receipts(backend) == 0


def test_an_exception_is_retried_with_backoff_and_stores_no_message(backend: TestBackend) -> None:
    start(backend)
    event_id = noted(backend)
    enqueue(backend, event_id)
    probe = Probe(backend, script=[RuntimeError("sink failed: secret-token-1234")])
    consumer = relay(backend, probe)
    assert counts(consumer.run_once()) == {"failed": 1}
    assert state_of(backend) == [("failed", 1, "RuntimeError")]
    assert consumer.run_once() == {}  # backoff_seconds=60
    backend.clock.advance(timedelta(seconds=61))
    assert counts(consumer.run_once()) == {"delivered": 1}
    assert [attempt for attempt, _ in probe.sent] == [1, 2]
    assert seen(backend, event_id)


def test_the_spec_limit_narrows_the_attempts_of_an_exception(backend: TestBackend) -> None:
    start(backend)
    enqueue(backend, noted(backend))
    probe = Probe(backend, script=[RuntimeError("x")])
    assert counts(relay(backend, probe, max_attempts=1).run_once()) == {"dead": 1}
    assert state_of(backend) == [("dead", 1, "RuntimeError")]


def test_a_failing_prepare_is_a_delivery_failure_and_the_connection_is_released(backend: TestBackend) -> None:
    start(backend)
    enqueue(backend, noted(backend))

    def broken(ctx: SubscriberContext, uow: UnitOfWork) -> None:
        raise LookupError("subscription lookup failed")

    probe = Probe(backend, on_prepare=broken)
    assert counts(relay(backend, probe).run_once()) == {"failed": 1}
    assert probe.sent == []
    assert state_of(backend) == [("failed", 1, "LookupError")]


def test_a_crash_between_send_and_the_mark_repeats_the_delivery_with_one_receipt(
    backend: TestBackend,
) -> None:
    start(backend)
    event_id = noted(backend)
    enqueue(backend, event_id)
    probe = Probe(backend, script=[Crash("killed after the external call")])
    with pytest.raises(Crash):
        relay(backend, probe).run_once()
    assert state_of(backend) == [("pending", 1, None)]  # claimed, nothing marked
    assert receipts(backend) == 0
    assert relay(backend, probe, relay_id="relay-2").run_once() == {}  # the claim is still live
    backend.clock.advance(EXPIRED)
    assert counts(relay(backend, probe, relay_id="relay-2").run_once()) == {"delivered": 1}
    assert [attempt for attempt, _ in probe.sent] == [1, 2]  # at-least-once: the send happened twice
    assert state_of(backend) == [("delivered", 2, None)]
    assert receipts(backend) == 1  # ... and the receipt once


@pytest.mark.parametrize("late", ["sent", "give_up", "retry_at", "error"])
def test_a_stale_claim_changes_nothing_not_even_a_delivered_row(backend: TestBackend, late: str) -> None:
    start(backend)
    event_id = noted(backend)
    enqueue(backend, event_id)
    takeover = relay(backend, Probe(backend), relay_id="relay-2")
    taken: list[dict[DeliveryOutcome, int]] = []
    results: dict[str, Callable[[], Any]] = {
        "sent": Sent,
        "give_up": lambda: GiveUp("late"),
        "retry_at": lambda: RetryAt(backend.clock.now(), "late"),
        "error": lambda: RuntimeError("late"),
    }

    def slow_send() -> Any:
        backend.clock.advance(EXPIRED)  # relay-1 hangs; its claim expires and relay-2 delivers the row
        taken.append(takeover.run_once())
        return results[late]()

    probe = Probe(backend, script=[slow_send])
    assert counts(relay(backend, probe).run_once()) == {"stale": 1}
    assert counts(taken[0]) == {"delivered": 1}
    assert state_of(backend) == [("delivered", 2, None)]  # the late claimant marked nothing
    assert receipts(backend) == 1


def test_an_unrouted_destination_is_dead_with_destination_unrouted(backend: TestBackend) -> None:
    start(backend)
    enqueue(backend, noted(backend))
    with backend.uow() as uow:
        (claimed,) = uow.repo(OutboxStore).claim(
            destination=HOOK, relay_id="relay-1", now=backend.clock.now(), limit=1
        )
        uow.commit()
    outcome = deliver(
        replace(claimed, destination="nope:x"),  # the row is the real one; its destination routes nowhere
        registry=build_registry(backend, Probe(backend)),
        uow_factory=backend.uow_factory,
        config=cast("Any", FakeConfigLoader()),
        delivery=SETTINGS,
        clock=backend.clock,
        ids=backend.ids,
        gateways=cast("Any", FakeGateways()),
        log=get_logger("tests.outbox_external"),
        relay_id="relay-1",
    )
    assert outcome is DeliveryOutcome.DEAD
    assert state_of(backend) == [("dead", 1, "destination_unrouted")]


# -------------------------------------------------------------------------------------------- config_for


def echo(backend: TestBackend) -> EventId:
    backend.app().dispatch(Echo(workspace_id=backend.seed.workspace_id, text="cfg"))
    return backend.envelopes(workspace_id=backend.seed.workspace_id)[-1].id


def test_config_for_reads_the_config_of_any_scope_of_the_event_workspace(backend: TestBackend) -> None:
    workspace, other = backend.seed.workspace_id, backend.seed.other_workspace_id
    project = project_scope(backend, workspace)
    foreign = project_scope(backend, other)
    instance = {"where": "instance"}
    loader = ScopedLoader(
        {
            None: instance,
            backend.seed.instance_id: instance,
            workspace: {"where": "workspace"},
            project: {"where": "project"},
        }
    )
    asked: dict[str, Any] = {}

    def handler(envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
        asked["event"] = ctx.config.get("where")
        asked["project"] = ctx.config_for(ScopeRef(kind=ScopeKind.PROJECT, id=project)).get("where")
        asked["workspace"] = ctx.config_for(ScopeRef(kind=ScopeKind.WORKSPACE, id=ScopeId(workspace))).get(
            "where"
        )
        asked["instance"] = ctx.config_for(
            ScopeRef(kind=ScopeKind.INSTANCE, id=backend.seed.instance_id)
        ).get("where")
        for name, scope in {
            "foreign_project": ScopeRef(kind=ScopeKind.PROJECT, id=foreign),
            "foreign_workspace": ScopeRef(kind=ScopeKind.WORKSPACE, id=ScopeId(other)),
            "unknown": ScopeRef(kind=ScopeKind.PROJECT, id=ScopeId(backend.ids.new_id())),
            "wrong_kind": ScopeRef(kind=ScopeKind.WORKSPACE, id=project),
        }.items():
            with pytest.raises(NotFound):
                ctx.config_for(scope)
            asked[name] = "NotFound"

    echo(backend)
    result = relay(backend, None, config=loader, handler=handler, secrets=False).run_once()
    assert counts(result) == {"delivered": 2}  # the subscriber and the sse row
    assert asked == {
        "event": "workspace",
        "project": "project",
        "workspace": "workspace",
        "instance": "instance",
        "foreign_project": "NotFound",
        "foreign_workspace": "NotFound",
        "unknown": "NotFound",
        "wrong_kind": "NotFound",
    }
    assert backend.table_counts("skm_core")["consumer_receipts"] == 1


def test_an_instance_event_cannot_read_a_workspace_scope(backend: TestBackend) -> None:
    start(backend)
    enqueue(backend, noted(backend))
    project = project_scope(backend, backend.seed.workspace_id)
    instance = {"where": "instance"}
    loader = ScopedLoader({None: instance, backend.seed.instance_id: instance, project: {"where": "project"}})
    seen_by_prepare: dict[str, Any] = {}

    def prepare(ctx: SubscriberContext, uow: UnitOfWork) -> None:
        seen_by_prepare["event"] = ctx.config.get("where")
        seen_by_prepare["instance"] = ctx.config_for(
            ScopeRef(kind=ScopeKind.INSTANCE, id=backend.seed.instance_id)
        ).get("where")
        with pytest.raises(NotFound):
            ctx.config_for(ScopeRef(kind=ScopeKind.PROJECT, id=project))
        seen_by_prepare["project"] = "NotFound"

    probe = Probe(backend, on_prepare=prepare)
    assert counts(relay(backend, probe, config=loader).run_once()) == {"delivered": 1}
    assert seen_by_prepare == {"event": "instance", "instance": "instance", "project": "NotFound"}


# ------------------------------------------------------------------------------------ dead notifications


def on_dead_recorder(
    log: list[tuple[OutboxItem, DeliveryPlan | None, str]],
) -> Callable[[OutboxItem, DeliveryPlan | None, str], object]:
    def build(item: OutboxItem, plan: DeliveryPlan | None, error: str) -> object:
        log.append((item, plan, error))
        return ("record_failure", item.id, error)

    return build


def test_a_dead_row_is_announced_once_with_the_generation_key_and_the_system_actor(
    backend: TestBackend,
) -> None:
    start(backend)
    event_id = noted(backend)
    enqueue(backend, event_id)
    built: list[tuple[OutboxItem, DeliveryPlan | None, str]] = []
    probe = Probe(backend, script=[GiveUp("http_410")])
    dispatcher = Dispatcher()
    consumer = relay(backend, probe, dispatcher=dispatcher, on_dead=on_dead_recorder(built))
    assert counts(consumer.run_once()) == {"dead": 1, "dead_notified": 1}
    ((command, actor, meta),) = dispatcher.calls
    ((item, plan, error),) = built
    assert command == ("record_failure", item.id, "http_410")
    assert error == "http_410"  # the stored delivery error
    assert plan == probe.plan  # the plan the consumer prepares now
    assert item.attempts == 1  # the generation starts at 0 (memory) or 1 (the DDL default)
    assert dispatcher.keys == [f"dead:{item.id}:{item.delivery_generation}:1"]
    assert actor == SYSTEM
    assert (meta.surface, meta.causation_id) == (Surface.BACKGROUND, str(event_id))
    assert meta.correlation_id == backend.envelopes()[-1].correlation_id
    assert pending_notifications(backend) == 0
    assert consumer.run_once() == {}  # announced: no second dispatch, no second send
    assert len(dispatcher.calls) == 1
    assert len(probe.sent) == 1


def test_a_relay_that_dies_before_the_dispatch_leaves_one_announcement_for_the_next(
    backend: TestBackend,
) -> None:
    start(backend)
    enqueue(backend, noted(backend))
    probe = Probe(backend, script=[GiveUp("http_410")])
    dispatcher = Dispatcher()
    dispatcher.failures.append(Crash("killed after the dead mark committed"))
    built: list[tuple[OutboxItem, DeliveryPlan | None, str]] = []
    with pytest.raises(Crash):
        relay(backend, probe, dispatcher=dispatcher, on_dead=on_dead_recorder(built)).run_once()
    assert state_of(backend)[0][0] == "dead"  # the death is committed
    assert dispatcher.calls == []
    second = relay(backend, probe, relay_id="relay-2", dispatcher=dispatcher, on_dead=on_dead_recorder(built))
    assert second.run_once() == {}  # the dead claim of relay-1 is still live
    backend.clock.advance(EXPIRED)
    assert counts(second.run_once()) == {"dead_notified": 1}
    assert len(dispatcher.calls) == 1
    assert len(probe.sent) == 1  # no hidden resend
    assert second.run_once() == {}


def test_after_retry_dead_the_next_death_is_announced_once_more_under_a_new_key(backend: TestBackend) -> None:
    start(backend)
    enqueue(backend, noted(backend))
    probe = Probe(backend, script=[GiveUp("first"), GiveUp("second")])
    dispatcher = Dispatcher()
    built: list[tuple[OutboxItem, DeliveryPlan | None, str]] = []
    consumer = relay(backend, probe, dispatcher=dispatcher, on_dead=on_dead_recorder(built))
    assert counts(consumer.run_once()) == {"dead": 1, "dead_notified": 1}
    assert retry_dead(backend) == 1
    assert state_of(backend) == [("pending", 0, "first")]  # attempts reset
    assert counts(consumer.run_once()) == {"dead": 1, "dead_notified": 1}
    assert consumer.run_once() == {}
    first, second = (item for item, _, _ in built)
    assert second.delivery_generation == first.delivery_generation + 1
    assert (first.attempts, second.attempts) == (1, 1)  # the send attempts restarted
    assert dispatcher.keys == [
        f"dead:{first.id}:{first.delivery_generation}:1",
        f"dead:{first.id}:{second.delivery_generation}:1",
    ]
    assert [error for _, _, error in built] == ["first", "second"]
    assert len(set(dispatcher.keys)) == 2


def test_a_notifier_of_an_older_generation_changes_nothing(backend: TestBackend) -> None:
    start(backend)
    enqueue(backend, noted(backend))
    probe = Probe(backend, script=[GiveUp("first"), Sent()])
    dispatcher = Dispatcher()

    def operator_retries_meanwhile(item: OutboxItem, plan: DeliveryPlan | None, error: str) -> object:
        assert retry_dead(backend) == 1  # between the claim and the closing CAS of this notifier
        return ("record_failure", item.id)

    consumer = relay(backend, probe, dispatcher=dispatcher, on_dead=operator_retries_meanwhile)
    assert counts(consumer.run_once()) == {
        "dead": 1,
        "stale": 1,
    }  # the late close of the old generation is refused
    assert state_of(backend) == [("pending", 0, "first")]
    assert len(dispatcher.calls) == 1  # the old generation keeps its own idempotency key
    # The retried row delivers normally; the old notifier left nothing behind.
    assert counts(consumer.run_once()) == {"delivered": 1}
    assert state_of(backend) == [("delivered", 1, None)]
    assert pending_notifications(backend) == 0


def test_a_failing_on_dead_defers_the_notification_and_keeps_the_healthy_consumer_running(
    backend: TestBackend,
) -> None:
    start(backend)
    enqueue(backend, noted(backend), "hook:sick")
    echo(backend)
    probe = Probe(backend, script=[GiveUp("http_500")])
    dispatcher = Dispatcher()
    dispatcher.failures.append(RuntimeError("bus failed: secret-token-1234"))
    built: list[tuple[OutboxItem, DeliveryPlan | None, str]] = []
    consumer = relay(backend, probe, dispatcher=dispatcher, on_dead=on_dead_recorder(built))
    assert counts(consumer.run_once()) == {"dead": 1, "delivered": 2, "dead_notification_deferred": 1}
    assert state_of(backend, "demo.on_echoed") == [("delivered", 1, None)]  # the healthy consumer went on
    (sick,) = state_of(backend, "hook:sick")
    assert sick == ("dead", 1, "http_500 | on_dead_failed: RuntimeError")  # both errors, no message
    assert pending_notifications(backend) == 0  # deferred: not due, not claimable
    assert consumer.run_once() == {}
    restarted = relay(
        backend, probe, relay_id="relay-2", dispatcher=dispatcher, on_dead=on_dead_recorder(built)
    )
    assert restarted.run_once() == {}  # the delay survives a restart
    assert dispatcher.calls == []
    backend.clock.advance(DUE_AGAIN)
    assert counts(restarted.run_once()) == {"dead_notified": 1}
    assert [error for _, _, error in built] == ["http_500", "http_500"]  # the delivery error, not the note
    assert len(dispatcher.calls) == 1
    assert len(probe.sent) == 1  # a failed announcement never resends
    assert restarted.run_once() == {}
