"""Worker commands and reads (workspace §4.3, §7, §8): state changes, heartbeat, listing."""

from datetime import timedelta
from typing import Literal

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.access.domain.principal import PrincipalState
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import ApiToken, TokenId, TokenKind, generate_secret, hash_secret
from skm.modules.access.ports import PrincipalRepository, TokenRepository
from skm.modules.workspace.application.views import capabilities_document
from skm.modules.workspace.public import ListWorkers, RecordWorkerHeartbeat, SetWorkerState

PEPPER = bytes(range(32))


class Setup:
    def __init__(self, world, state: str = "offline") -> None:
        self.world = world
        self.ws = world.workspace()
        self.host = world.host()
        self.actor, self.worker = world.worker(self.ws, self.host, state=state)

    def state(self, to: Literal["online", "draining", "retired"], version: int, actor="owner"):
        return self.world.run(
            SetWorkerState(worker_id=self.worker, state=to, expected_row_version=version), actor
        )

    def beat(self, actor=None, **fields):
        return self.world.run(
            RecordWorkerHeartbeat(worker_id=self.worker, capabilities=None, **fields), actor or self.actor
        )

    def row(self):
        return self.world.tables().workers[self.worker]


def seed_token(world, setup: Setup) -> TokenId:
    secret = generate_secret(lambda n: bytes(range(n)))
    token_id = TokenId(world.ids.new_id())
    with world.uow() as uow:
        uow.repo(TokenRepository).add(
            ApiToken(
                id=token_id,
                principal_id=setup.actor.principal_id,
                kind=TokenKind.WORKER,
                name="worker",
                prefix=secret.prefix,
                secret_hash=hash_secret(secret, PEPPER),
                scope_id=None,
                permissions=None,
                expires_at=world.clock.now() + timedelta(days=7),
                created_at=world.clock.now(),
                created_by=setup.actor.principal_id,
                last_used_at=None,
                revoked_at=None,
                revoked_by=None,
                assignment_id=None,
                step_id=None,
                superseded_by=None,
            )
        )
        uow.commit()
    return token_id


def test_the_first_heartbeat_brings_the_worker_online_with_one_event(world) -> None:
    setup = Setup(world)
    first = setup.beat()
    assert (first.state, first.last_heartbeat_at) == ("online", world.clock.now())
    [event] = world.events("worker-state-changed")
    assert event.payload == {"worker_id": str(setup.worker), "from_state": "offline", "to_state": "online"}
    assert (event.stream_kind, event.workspace_id) == ("workspace", setup.ws)
    world.clock.advance(timedelta(seconds=30))
    setup.beat()
    assert len(world.events("worker-state-changed")) == 1  # a heartbeat that changes nothing is no event
    assert setup.row().last_heartbeat_at == world.clock.now()
    assert world.tables().hosts[setup.host].last_seen_at == world.clock.now()


def test_a_draining_worker_stays_draining_on_heartbeat(world) -> None:
    setup = Setup(world, "draining")
    assert setup.beat().state == "draining"
    assert world.events("worker-state-changed") == []


def test_only_the_principal_of_the_worker_sends_its_heartbeat(world) -> None:
    setup = Setup(world)
    other, _ = world.worker(setup.ws, setup.host, "w2")
    for stranger in ("owner", other):
        with pytest.raises(SkmError) as caught:
            setup.beat(stranger)
        assert caught.value.code is ErrorCode.FORBIDDEN
    assert setup.row().last_heartbeat_at is None


def test_a_retired_worker_cannot_send_a_heartbeat(world) -> None:
    setup = Setup(world, "retired")
    with pytest.raises(SkmError) as caught:
        setup.beat()
    assert caught.value.code is ErrorCode.INVALID_TRANSITION


def test_a_heartbeat_replaces_capabilities_and_refuses_unconfined(world) -> None:
    setup = Setup(world)
    fresh = capabilities_document(world.capabilities(profiles=("worktree", "container")))
    world.run(RecordWorkerHeartbeat(worker_id=setup.worker, capabilities=fresh), setup.actor)
    assert setup.row().capabilities.isolation_profiles == ("worktree", "container")
    before = world.snapshot()
    unconfined = capabilities_document(world.capabilities(profiles=("none",)))
    with pytest.raises(SkmError) as caught:
        world.run(RecordWorkerHeartbeat(worker_id=setup.worker, capabilities=unconfined), setup.actor)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["reason"] == "unconfined_not_allowed"
    assert world.snapshot() == before


def test_set_state_follows_the_transition_table_and_records_each_change(world) -> None:
    setup = Setup(world, "online")
    draining = setup.state("draining", 1)
    assert (draining.state, draining.row_version) == ("draining", 2)
    back = setup.state("online", 2)
    assert back.row_version == 3
    same = setup.state("online", 3)  # the same state again: nothing changes, nothing is recorded
    assert same.row_version == 3
    assert [
        (e.payload["from_state"], e.payload["to_state"]) for e in world.events("worker-state-changed")
    ] == [
        ("online", "draining"),
        ("draining", "online"),
    ]


def test_set_state_needs_the_current_row_version_and_worker_register(world) -> None:
    setup = Setup(world, "online")
    with pytest.raises(SkmError) as caught:
        setup.state("draining", 7)
    assert caught.value.code is ErrorCode.VERSION_CONFLICT
    member = world.person("member", {setup.ws: Role.MEMBER})
    with pytest.raises(SkmError) as caught:
        setup.state("draining", 1, member)
    assert caught.value.code is ErrorCode.FORBIDDEN
    maintainer = world.person("maintainer", {setup.ws: Role.MAINTAINER})
    assert setup.state("draining", 1, maintainer).state == "draining"


def test_retiring_revokes_the_tokens_and_disables_the_principal_and_is_final(world) -> None:
    setup = Setup(world, "online")
    token_id = seed_token(world, setup)
    retired = setup.state("retired", 1)
    assert retired.state == "retired"
    with world.uow(readonly=True) as uow:
        assert uow.repo(TokenRepository).get(token_id).revoked_at is not None
        assert uow.repo(PrincipalRepository).get(setup.actor.principal_id).state is PrincipalState.DISABLED
    with pytest.raises(SkmError) as caught:
        setup.state("online", 2)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    assert setup.state("retired", 2).row_version == 2  # retiring again is a no-op
    assert len(world.events("worker-state-changed")) == 1


def test_list_workers_filters_by_state_and_pages(world) -> None:
    setup = Setup(world, "online")
    for name, state in (("w2", "offline"), ("w3", "online")):
        world.clock.advance(timedelta(seconds=1))
        world.worker(setup.ws, setup.host, name, state=state)
    viewer = world.person("viewer", {setup.ws: Role.VIEWER})
    everyone = world.ask(ListWorkers(workspace_id=setup.ws), viewer)
    assert [w.display_name for w in everyone.items] == ["w1", "w2", "w3"]
    assert everyone.items[0].capabilities.isolation_profiles == ("worktree",)
    assert (everyone.items[0].workspace_id, everyone.items[0].row_version) == (setup.ws, 1)
    online = world.ask(ListWorkers(workspace_id=setup.ws, state="online"), viewer)
    assert [w.display_name for w in online.items] == ["w1", "w3"]
    first = world.ask(ListWorkers(workspace_id=setup.ws, limit=2), viewer)
    rest = world.ask(ListWorkers(workspace_id=setup.ws, limit=2, after=first.next), viewer)
    assert [w.display_name for w in first.items + rest.items] == ["w1", "w2", "w3"]
    assert rest.next is None
    outsider = world.person("outsider")
    with pytest.raises(SkmError) as caught:
        world.ask(ListWorkers(workspace_id=setup.ws), outsider)
    assert caught.value.code is ErrorCode.FORBIDDEN
