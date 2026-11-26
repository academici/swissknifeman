"""``workspace.register_worker`` (workspace §7): principal, membership, token and Worker row in one step."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import PrincipalId, ScopeId
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import TokenKind
from skm.modules.access.ports import MembershipRepository, PrincipalRepository, TokenRepository
from skm.modules.access.public import authenticate_token
from skm.modules.workspace.application.views import capabilities_document
from skm.modules.workspace.domain.host import HostState
from skm.modules.workspace.ports import HostRepository
from skm.modules.workspace.public import ArchiveWorkspace, RecordWorkerHeartbeat, RegisterWorker

from .conftest import PEPPER


def register(world, ws, host, *, profiles=("worktree",), name="build-1", actor="owner", key=None):
    dto = RegisterWorker(
        workspace_id=ws,
        host_id=host,
        display_name=name,
        capabilities=capabilities_document(world.capabilities(profiles=profiles)),
    )
    return world.run(dto, actor, key=key)


def test_registration_creates_principal_membership_token_row_and_event(world) -> None:
    ws, host = world.workspace(), world.host()
    result = register(world, ws, host)
    row = world.tables().workers[result.worker_id]
    assert (row.state.value, row.last_heartbeat_at, row.row_version) == ("offline", None, 1)
    assert (row.workspace_id, row.host_id, row.principal_id) == (ws, host, result.principal_id)
    assert row.display_name == "build-1"
    principal_id = PrincipalId(result.principal_id)
    with world.uow(readonly=True) as uow:
        principal = uow.repo(PrincipalRepository).get(principal_id)
        assert principal.display_name == "build-1"
        assert principal.kind is PrincipalKind.WORKER
        membership = uow.repo(MembershipRepository).get(ScopeId(ws), principal_id)
        assert membership is not None
        assert membership.role is Role.WORKER
        [token] = (
            uow.repo(TokenRepository)
            .list_for(principal_id, include_inactive=True, after=None, limit=10)
            .items
        )
        assert token.kind is TokenKind.WORKER
        assert token.expires_at == world.clock.now() + timedelta(hours=168)
        actor = authenticate_token(uow, result.token_secret, pepper=PEPPER, now=world.clock.now())
        assert actor.principal_id == principal_id
    [event] = world.events("worker-registered")
    assert event.payload["worker_id"] == str(result.worker_id)
    assert event.payload["principal_id"] == str(principal_id)
    assert event.payload["host_id"] == str(host)
    assert (event.stream_kind, event.workspace_id) == ("workspace", ws)
    assert "token_secret" not in str(event.payload)


def test_a_registered_worker_sends_its_first_heartbeat_with_the_issued_secret(world) -> None:
    ws, host = world.workspace(), world.host()
    result = register(world, ws, host)
    with world.uow(readonly=True) as uow:
        actor = authenticate_token(uow, result.token_secret, pepper=PEPPER, now=world.clock.now())
    beat = world.run(RecordWorkerHeartbeat(worker_id=result.worker_id, capabilities=None), actor)
    assert beat.state == "online"


def test_an_idempotency_key_is_refused_and_leaves_nothing(world) -> None:
    ws, host = world.workspace(), world.host()
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        register(world, ws, host, key="register-worker-1")
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["reason"] == "not_idempotent"
    assert world.snapshot() == before


def test_two_registrations_make_two_workers_with_distinct_secrets(world) -> None:
    ws, host = world.workspace(), world.host()
    first, second = register(world, ws, host), register(world, ws, host, name="build-2")
    assert first.worker_id != second.worker_id
    assert first.principal_id != second.principal_id
    assert first.token_secret != second.token_secret


def test_registration_needs_worker_register_on_the_workspace(world) -> None:
    ws, host = world.workspace(), world.host()
    world.person("member", {ws: Role.MEMBER})
    other = world.workspace("other", "Other")
    world.person("elsewhere", {other: Role.OWNER})
    before = world.snapshot()
    for who in ("member", "elsewhere"):
        with pytest.raises(SkmError) as caught:
            register(world, ws, host, actor=who)
        assert caught.value.code is ErrorCode.FORBIDDEN
    worker_actor, _ = world.worker(ws, host)
    with pytest.raises(SkmError) as caught:
        register(world, ws, host, actor=worker_actor)
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert world.snapshot() != before  # the seeded worker row only
    assert len(world.tables().workers) == 1
    maintainer = world.person("maintainer", {ws: Role.MAINTAINER})
    assert register(world, ws, host, actor=maintainer).worker_id in world.tables().workers


def test_an_archived_workspace_refuses_and_leaves_nothing(world) -> None:
    ws, host = world.workspace(), world.host()
    world.run(ArchiveWorkspace(workspace_id=ws, expected_row_version=1, reason="closed"))
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        register(world, ws, host)
    assert caught.value.code is ErrorCode.PROJECT_ARCHIVED
    assert world.snapshot() == before


def test_a_retired_host_refuses_and_leaves_nothing(world) -> None:
    ws, host = world.workspace(), world.host()
    with world.uow() as uow:
        hosts = uow.repo(HostRepository)
        current = hosts.get(host)
        hosts.save(replace(current, state=HostState.RETIRED, row_version=2), expected_version=1)
        uow.commit()
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        register(world, ws, host)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    assert caught.value.details["reason"] == "host_retired"
    assert world.snapshot() == before


def test_an_unknown_host_or_workspace_is_not_found(world) -> None:
    ws, host = world.workspace(), world.host()
    for target_ws, target_host in ((ws, uuid4()), (uuid4(), host)):
        with pytest.raises(SkmError) as caught:
            register(world, target_ws, target_host)
        assert caught.value.code in (ErrorCode.NOT_FOUND, ErrorCode.FORBIDDEN)
    assert not world.tables().workers


def test_unconfined_capabilities_are_refused_before_any_principal_exists(world) -> None:
    ws, host = world.workspace(), world.host()
    before = world.snapshot()
    with world.uow(readonly=True) as uow:
        principals = uow.repo(PrincipalRepository).list(kind=PrincipalKind.WORKER, after=None, limit=10).items
    with pytest.raises(SkmError) as caught:
        register(world, ws, host, profiles=("none",))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["reason"] == "unconfined_not_allowed"
    assert world.snapshot() == before
    with world.uow(readonly=True) as uow:
        after = uow.repo(PrincipalRepository).list(kind=PrincipalKind.WORKER, after=None, limit=10).items
    assert after == principals


def test_an_overlong_display_name_is_refused_as_a_whole(world) -> None:
    ws, host = world.workspace(), world.host()
    before = world.snapshot()
    with pytest.raises(SkmError) as caught:
        register(world, ws, host, name="x" * 101)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert world.snapshot() == before
