"""Single-use exchange through the real bus and memory repositories."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import pytest

from fakes.entropy import DeterministicEntropy
from skm.kernel.actor import Actor, ScopeGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, Unauthenticated
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.modules.access import public as access
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import hash_secret
from skm.modules.access.ports import MembershipRepository, TokenRepository
from skm.modules.workspace import public as workspace
from skm.modules.workspace.application.views import capabilities_document

from .conftest import PEPPER, World


def issue(world: World, ws: WorkspaceId, issuer: Actor, **binding: object) -> workspace.ExchangePairingToken:
    pairing_id = world.ids.new_id()
    now = world.clock.now()
    with world.uow() as uow:
        secret = access.issue_pairing_token(
            uow,
            issuer=issuer,
            workspace_id=ws,
            pairing_id=pairing_id,
            now=now,
            expires_at=now + timedelta(minutes=5),
            pepper=PEPPER,
            entropy=DeterministicEntropy(pairing_id.bytes).bytes,
            **binding,  # pyright: ignore[reportArgumentType]
        )
        uow.commit()
    return workspace.ExchangePairingToken(workspace_id=ws, pairing_id=pairing_id, pairing_secret=secret)


def worker_registration(world: World, ws: WorkspaceId) -> workspace.RegisterWorker:
    return workspace.RegisterWorker(
        workspace_id=ws,
        host_id=world.host(),
        display_name="paired-worker",
        capabilities=capabilities_document(world.capabilities()),
    )


def bearer(world: World, secret: str) -> Actor:
    with world.uow(readonly=True) as uow:
        return access.authenticate_token(uow, secret, pepper=PEPPER, now=world.clock.now())


@pytest.mark.parametrize("paired_operator", [False, True], ids=["single-scope", "paired"])
def test_owner_api_token_can_rotate_a_paired_personal_token(world: World, paired_operator: bool) -> None:
    ws = world.workspace()
    permissions = ("token.own", "token.any", "plan.read")
    if paired_operator:
        command = access.CreateToken.from_json(
            {
                "name": "operator",
                "scope_grants": [{"scope_id": str(world.instance), "permissions": list(permissions)}],
            }
        )
    else:
        command = access.CreateToken(name="operator", scope_id=world.instance, permissions=permissions)
    operator_token = world.run(command)
    operator = bearer(world, operator_token.secret)
    recipient = world.person("recipient", {ScopeId(ws): Role.VIEWER})
    pairing = issue(
        world,
        ws,
        operator,
        principal_id=recipient.principal_id,
        scope_grants=(ScopeGrant(ScopeId(ws), frozenset({"plan.read"})),),
    )
    original = world.run(pairing, access.SYSTEM_ACTOR)
    original_actor = bearer(world, original.token_secret)

    rotated = world.run(access.RotateToken(token_id=original.token_id, grace_minutes=0), operator)

    with pytest.raises(Unauthenticated):
        bearer(world, original.token_secret)
    successor = bearer(world, rotated.secret)
    assert successor.principal_id == recipient.principal_id
    assert original_actor.grant is not None
    assert successor.grant is not None
    assert successor.grant.scope_grants == original_actor.grant.scope_grants


@pytest.mark.parametrize("legacy", [False, True], ids=["paired", "legacy"])
def test_worker_rotation_requires_worker_register_from_the_operator_api_token(
    world: World, legacy: bool
) -> None:
    ws = world.workspace()
    registration = world.run(worker_registration(world, ws))
    registered = bearer(world, registration.token_secret)
    assert registered.grant is not None
    token_id = access.TokenId(registered.grant.token_id)
    secret = registration.token_secret
    if legacy:
        token_id = access.TokenId(world.ids.new_id())
        legacy_secret = access.generate_secret(DeterministicEntropy(token_id.bytes).bytes)
        secret = str(legacy_secret)
        with world.uow() as uow:
            tokens = uow.repo(TokenRepository)
            tokens.add(
                replace(
                    tokens.get(access.TokenId(registered.grant.token_id)),
                    id=token_id,
                    name="legacy-worker",
                    prefix=legacy_secret.prefix,
                    secret_hash=hash_secret(legacy_secret, PEPPER),
                    scope_grants=None,
                    worker_id=None,
                )
            )
            uow.commit()

    denied = world.run(
        access.CreateToken(
            name="no-worker-register", scope_id=world.instance, permissions=("token.own", "token.any")
        )
    )
    command = access.RotateToken(token_id=token_id, grace_minutes=0)
    with pytest.raises(SkmError) as caught:
        world.run(command, bearer(world, denied.secret))
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert caught.value.details["permission"] == "worker.register"

    allowed = world.run(
        access.CreateToken(
            name="operator",
            scope_id=world.instance,
            permissions=("token.own", "token.any", "worker.register"),
        )
    )
    rotated = world.run(command, bearer(world, allowed.secret))

    with pytest.raises(Unauthenticated):
        bearer(world, secret)
    successor = bearer(world, rotated.secret)
    assert successor.principal_id == registered.principal_id
    assert successor.grant is not None
    assert successor.grant.worker_id == (None if legacy else registration.worker_id)
    with world.uow(readonly=True) as uow:
        assert "worker.claim" in access.effective_permissions(uow, successor, ScopeId(ws))


def test_concurrent_exchange_returns_one_secret_and_replacement_keeps_the_worker(world: World) -> None:
    ws = world.workspace()
    issuer = world.person("maintainer", {ScopeId(ws): Role.MAINTAINER})
    registration = worker_registration(world, ws)
    command = issue(world, ws, issuer, worker_registration=registration.to_json())
    barrier = Barrier(2)

    def exchange(key: str) -> workspace.ExchangePairingTokenResult:
        barrier.wait(timeout=5)
        return world.run(command, access.SYSTEM_ACTOR, key=key)

    with ThreadPoolExecutor(max_workers=2) as callers:
        results = tuple(callers.map(exchange, ("pairing-race-a", "pairing-race-b")))
    original, replay = sorted(results, key=lambda item: item.token_secret is None)
    assert original.token_secret is not None
    assert replay.token_secret is None
    assert original.token_id == replay.token_id
    assert original.worker_id == replay.worker_id
    assert len(world.tables().workers) == 1
    assert world.backend.peak_active == 1
    receipts = world.backend.committed.core.idempotency.values()
    assert len(receipts) == 2
    assert all(
        set(row.result) == {"pairing_id", "principal_id", "worker_id", "token_id", "status"}
        for row in receipts
    )
    same_key = world.run(command, access.SYSTEM_ACTOR, key="pairing-race-a")
    assert same_key == replay
    assert command.pairing_secret not in str(world.backend.committed)
    assert original.token_secret not in str(world.backend.committed)
    assert bearer(world, original.token_secret).principal_id == original.principal_id
    replacement = issue(world, ws, issuer, replaces=command.pairing_id)
    replaced = world.run(replacement, access.SYSTEM_ACTOR, key="replace-pairing")
    assert replaced.worker_id == original.worker_id
    assert replaced.principal_id == original.principal_id
    assert replaced.token_id != original.token_id
    assert len(world.tables().workers) == 1
    with pytest.raises(Unauthenticated):
        bearer(world, original.token_secret)
    assert bearer(world, replaced.token_secret).principal_id == original.principal_id


def test_worker_pairing_replacement_revokes_the_expired_prior_token(world: World) -> None:
    ws = world.workspace()
    issuer = world.person("maintainer", {ScopeId(ws): Role.MAINTAINER})
    command = issue(world, ws, issuer, worker_registration=worker_registration(world, ws).to_json())
    original = world.run(command, access.SYSTEM_ACTOR)
    with world.uow(readonly=True) as uow:
        prior = uow.repo(TokenRepository).get(access.TokenId(original.token_id))
    assert prior.expires_at is not None
    assert prior.revoked_at is None
    world.clock.set(prior.expires_at)
    with pytest.raises(Unauthenticated):
        bearer(world, original.token_secret)

    replacement = issue(world, ws, issuer, replaces=command.pairing_id)
    result = world.run(replacement, access.SYSTEM_ACTOR)

    assert result.worker_id == original.worker_id
    assert result.token_id != original.token_id
    assert bearer(world, result.token_secret).principal_id == original.principal_id
    with world.uow(readonly=True) as uow:
        tokens = uow.repo(TokenRepository)
        assert tokens.get(prior.id).revoked_at == world.clock.now()
        assert tokens.get(access.TokenId(result.token_id)).name == prior.name


@pytest.mark.parametrize("revoke_credential", [True, False])
def test_issuer_revocation_before_exchange_blocks_worker_creation(
    world: World, revoke_credential: bool
) -> None:
    ws = world.workspace()
    maintainer = world.person("maintainer", {ScopeId(ws): Role.MAINTAINER})
    token = world.run(
        access.CreateToken(name="issuer", scope_id=ws, permissions=("worker.register", "token.own")),
        maintainer,
    )
    owner = bearer(world, token.secret)
    command = issue(world, ws, owner, worker_registration=worker_registration(world, ws).to_json())
    if revoke_credential:
        world.run(access.RevokeToken(token_id=token.token_id), owner)
    else:
        with world.uow() as uow:
            uow.repo(MembershipRepository).delete(ScopeId(ws), maintainer.principal_id)
            uow.commit()
    with pytest.raises(SkmError) as caught:
        world.run(command, access.SYSTEM_ACTOR, key="dead-issuer")
    assert caught.value.code is (ErrorCode.UNAUTHENTICATED if revoke_credential else ErrorCode.FORBIDDEN)
    assert not world.tables().workers


def test_personal_exchange_checks_each_pair_against_live_roles_and_credential(world: World) -> None:
    a = world.workspace("alpha", "Alpha")
    b = world.workspace("beta", "Beta")
    owner = world.actor("owner")
    first = world.run(
        access.CreateToken.from_json(
            {
                "name": "issuer",
                "scope_grants": [
                    {"scope_id": str(a), "permissions": ["token.own", "plan.read", "plan.edit"]},
                    {"scope_id": str(b), "permissions": ["token.own", "plan.read"]},
                ],
            }
        )
    )
    issuer = bearer(world, first.secret)
    with pytest.raises(SkmError, match=r"token cannot exceed|requires plan\.edit"):
        issue(
            world,
            a,
            issuer,
            principal_id=owner.principal_id,
            scope_grants=(ScopeGrant(ScopeId(b), frozenset({"plan.edit"})),),
        )
    command = issue(
        world,
        a,
        issuer,
        principal_id=owner.principal_id,
        scope_grants=(
            ScopeGrant(ScopeId(a), frozenset({"plan.edit"})),
            ScopeGrant(ScopeId(b), frozenset({"plan.read"})),
        ),
    )
    result = world.run(command, access.SYSTEM_ACTOR)
    paired = bearer(world, result.token_secret)
    with world.uow(readonly=True) as uow:
        assert "plan.edit" in access.effective_permissions(uow, paired, ScopeId(a))
        assert "plan.edit" not in access.effective_permissions(uow, paired, ScopeId(b))
        assert "plan.read" in access.effective_permissions(uow, paired, ScopeId(b))
        assert "plan.read" not in access.effective_permissions(uow, paired, ScopeId(a))


def test_personal_pairing_cannot_use_roles_lost_before_exchange(world: World) -> None:
    ws = world.workspace()
    scope = ScopeId(ws)
    issuer = world.person("member", {scope: Role.MEMBER})
    command = issue(
        world,
        ws,
        issuer,
        principal_id=issuer.principal_id,
        scope_grants=(ScopeGrant(scope, frozenset({"plan.edit"})),),
    )
    with world.uow() as uow:
        uow.repo(MembershipRepository).delete(scope, issuer.principal_id)
        uow.commit()
    with pytest.raises(SkmError) as denied:
        world.run(command, access.SYSTEM_ACTOR)
    assert denied.value.code is ErrorCode.FORBIDDEN
