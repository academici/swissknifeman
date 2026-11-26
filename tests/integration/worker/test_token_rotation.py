"""Frozen time crosses rotation windows, hourly ticks and grace; in-flight client calls stay pinned."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from typing import cast
from uuid import uuid4

import pytest

from fakes.clock import FrozenClock
from skm.application_bus.client import SkmClient
from skm.entrypoints.worker.token_rotation import (
    RotatingClient,
    TokenRotation,
    WorkerCredential,
    rotation_due,
)
from skm.modules.access.public import RotateToken, RotateTokenResult
from skm.modules.runtimes.public import SecretStr


class Monotonic:
    value = 0.0

    def monotonic(self):
        return self.value


class Client:
    def __init__(self, name, on_rotate=None):
        self.name, self.on_rotate = name, on_rotate
        self.started, self.finish = Event(), Event()

    def as_client(self) -> SkmClient:
        # Rotation exercises only dispatch and idempotency. Other calls still fail on this stub.
        return cast("SkmClient", self)

    def new_idempotency_key(self):
        return "idem_" + uuid4().hex

    def dispatch(self, command, **kwargs):
        if isinstance(command, RotateToken):
            assert self.on_rotate is not None
            return self.on_rotate(command)
        if command == "in-flight":
            self.started.set()
            assert self.finish.wait(10)
        return self.name


@pytest.mark.parametrize(("ttl", "before", "window"), [(720, 168, 168), (24, 168, 12), (24, 2, 2)])
def test_rotation_due_uses_the_smaller_window(ttl, before, window):
    clock = FrozenClock()
    credential = WorkerCredential(
        uuid4(), clock.now() + timedelta(hours=window), SecretStr("old-worker-secret")
    )
    assert rotation_due(credential, clock.now(), rotate_before_hours=before, ttl_hours=ttl)
    assert not rotation_due(
        credential, clock.now() - timedelta(microseconds=1), rotate_before_hours=before, ttl_hours=ttl
    )
    assignment = WorkerCredential(credential.token_id, credential.expires_at, credential.secret, "assignment")
    assert not rotation_due(assignment, clock.now(), rotate_before_hours=before, ttl_hours=ttl)


def test_hourly_rotation_reconstitutes_client_without_interrupting_request(tmp_path, caplog):
    clock, monotonic = FrozenClock(), Monotonic()
    old_id, new_id = uuid4(), uuid4()
    old = WorkerCredential(old_id, clock.now() + timedelta(hours=13), SecretStr("old-worker-secret"))
    expiry = clock.now() + timedelta(hours=24)
    grace = []
    rotations, persisted = [], []

    def rotate(command):
        rotations.append(command)
        grace.append(clock.now() + timedelta(minutes=5))
        return RotateTokenResult(new_id, "prefix", "new-worker-secret", expiry, old_id, grace[-1])

    original = Client("old", rotate)
    client = RotatingClient(original.as_client())
    replacement = Client("new")
    settings = {
        "access.tokens.worker_rotate_before_hours": 168,
        "access.tokens.worker_ttl_hours": 24,
        "access.tokens.rotation_grace_minutes": 5,
    }
    controller = TokenRotation(
        old,
        client,
        clock=clock,
        monotonic=monotonic,
        config=settings.get,
        save=persisted.append,
        make_client=lambda secret: replacement.as_client(),
    )
    controller.tick()
    assert not rotations
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.dispatch, "in-flight")
        assert original.started.wait(10)
        clock.advance(timedelta(hours=1))
        monotonic.value = 3599
        controller.tick()
        assert not rotations
        monotonic.value = 3600
        controller.tick()
        assert client.dispatch("heartbeat") == "new"
        assert client.dispatch("claim") == "new"
        assert not pending.done()
        original.finish.set()
        assert pending.result(timeout=10) == "old"
    assert len(rotations) == len(persisted) == 1
    assert grace[0] == clock.now() + timedelta(minutes=5)
    assert "new-worker-secret" not in caplog.text
    assert "new-worker-secret" not in repr(persisted)


def test_persist_failure_retries_same_rotation_receipt_without_second_issue():
    clock, monotonic = FrozenClock(), Monotonic()
    old_id = uuid4()
    calls = []
    result = RotateTokenResult(
        uuid4(),
        "prefix",
        "replacement-secret",
        clock.now() + timedelta(days=1),
        old_id,
        clock.now() + timedelta(minutes=5),
    )
    client = RotatingClient(Client("old", lambda cmd: calls.append(cmd) or result).as_client())
    writes = []

    def save(credential):
        writes.append(credential)
        if len(writes) == 1:
            raise OSError("storage unavailable")

    settings = {
        "access.tokens.worker_rotate_before_hours": 12,
        "access.tokens.worker_ttl_hours": 24,
        "access.tokens.rotation_grace_minutes": 5,
    }
    controller = TokenRotation(
        WorkerCredential(old_id, clock.now(), SecretStr("old-worker-secret")),
        client,
        clock=clock,
        monotonic=monotonic,
        config=settings.get,
        save=save,
        make_client=lambda secret: Client("new").as_client(),
    )
    with pytest.raises(OSError, match="storage unavailable"):
        controller.tick()
    assert client.dispatch("heartbeat") == "old"
    controller.tick()
    assert len(calls) == 1
    assert len(writes) == 2
    assert writes[0] is writes[1]
    assert client.dispatch("claim") == "new"


def test_unknown_rotation_outcome_is_never_retried_blindly():
    clock, monotonic = FrozenClock(), Monotonic()
    attempts = []

    def lost(command):
        attempts.append(command)
        raise OSError("response lost after commit")

    settings = {
        "access.tokens.worker_rotate_before_hours": 12,
        "access.tokens.worker_ttl_hours": 24,
        "access.tokens.rotation_grace_minutes": 5,
    }
    client = RotatingClient(Client("old", lost).as_client())
    controller = TokenRotation(
        WorkerCredential(uuid4(), clock.now(), SecretStr("old-worker-secret")),
        client,
        clock=clock,
        monotonic=monotonic,
        config=settings.get,
        save=lambda _: None,
        make_client=lambda _: Client("new").as_client(),
    )
    with pytest.raises(OSError, match="response lost"):
        controller.tick()
    with pytest.raises(RuntimeError, match="unknown outcome"):
        controller.tick()
    assert len(attempts) == 1


def test_real_worker_rotation_grace_and_new_client_authority(exec_side):
    from skm.kernel.errors import SkmError
    from skm.kernel.ports_uow import Surface
    from skm.modules.access import public as access
    from skm.modules.workspace import public as workspace

    side = exec_side
    old_client = side.worker1_client
    old_id = old_client._actor.grant.token_id
    rotated = old_client.dispatch(RotateToken(old_id, 5))  # FORBIDDEN generic idempotency, secret once
    with side.uow() as uow:
        from contracts.execution.harness import PEPPER

        actor = access.authenticate_token(uow, rotated.secret, pepper=PEPPER, now=side.clock.now())
    new_client = side.app.client(actor=actor, surface=Surface.WORKER)
    old_client.dispatch(workspace.RecordWorkerHeartbeat(side.worker1, None))
    new_client.dispatch(workspace.RecordWorkerHeartbeat(side.worker1, None))
    side.clock.advance(timedelta(minutes=5, seconds=1))
    with pytest.raises(SkmError) as caught:
        old_client.dispatch(workspace.RecordWorkerHeartbeat(side.worker1, None))
    assert caught.value.code.value == "UNAUTHENTICATED"
    new_client.dispatch(workspace.RecordWorkerHeartbeat(side.worker1, None))
