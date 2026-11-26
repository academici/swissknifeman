"""Unit tests for unified AuthBasis propagation, invariants, and live credential checks."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from security.api.harness import NOW, PEPPER, make_world
from skm.application_bus.context import AuthBasis, AuthBasisKind, CommandContext, QueryContext
from skm.application_bus.middleware import kind_allowed
from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import Actor, PrincipalKind, ScopeGrant, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, Unauthenticated
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access import public as access
from skm.modules.access.domain.principal import Principal, PrincipalState
from skm.modules.access.ports import PrincipalRepository
from skm.modules.workspace import public as workspace


def _human_actor(grant: TokenGrant | None = None) -> Actor:
    return Actor(PrincipalId(uuid4()), PrincipalKind.HUMAN, "Human", grant=grant)


def _worker_actor(grant: TokenGrant | None = None) -> Actor:
    return Actor(PrincipalId(uuid4()), PrincipalKind.WORKER, "Worker", grant=grant)


def _service_actor(grant: TokenGrant | None = None) -> Actor:
    return Actor(PrincipalId(uuid4()), PrincipalKind.SERVICE, "Service", grant=grant)


def test_auth_basis_invariants_and_properties() -> None:
    token_id = uuid4()
    session_id = uuid4()
    personal_grant = TokenGrant(token_id=token_id, kind="personal", scope_id=None, permissions=None)
    worker_grant = TokenGrant(token_id=uuid4(), kind="worker", scope_id=None, permissions=None)
    assignment_grant = TokenGrant(
        token_id=uuid4(),
        kind="assignment",
        scope_id=ScopeId(uuid4()),
        permissions=frozenset({"step.note"}),
        assignment_id=uuid4(),
        step_id=uuid4(),
    )

    human = _human_actor(personal_grant)
    bearer_basis = AuthBasis.bearer(human, session_id=session_id, session_expires_at=NOW)
    assert bearer_basis.kind is AuthBasisKind.BEARER
    assert bearer_basis.token_id == token_id
    assert bearer_basis.session_id == session_id
    assert bearer_basis.grant == personal_grant
    assert bearer_basis.auth_method == "bearer"
    assert bearer_basis.stream_quota_key == ("token", token_id)
    assert not bearer_basis.is_worker_token

    worker_basis = AuthBasis.bearer(_worker_actor(worker_grant))
    assert worker_basis.is_worker_token

    assignment_basis = AuthBasis.bearer(_worker_actor(assignment_grant))
    assert not assignment_basis.is_worker_token

    human_plain = _human_actor()
    session_basis = AuthBasis.session(human_plain, session_id=session_id, expires_at=NOW)
    assert session_basis.kind is AuthBasisKind.SESSION
    assert session_basis.auth_method == "session"
    assert session_basis.stream_quota_key == ("session", session_id)
    assert not session_basis.is_worker_token

    local_basis = AuthBasis.local_owner(human_plain)
    assert local_basis.kind is AuthBasisKind.LOCAL_OWNER
    assert local_basis.auth_method == "none"
    assert local_basis.stream_quota_key == ("local_owner", human_plain.principal_id)
    assert not local_basis.is_worker_token

    sys_basis = AuthBasis.system(access.SYSTEM_ACTOR)
    assert sys_basis.kind is AuthBasisKind.SYSTEM
    assert sys_basis.auth_method == "none"
    assert not sys_basis.is_worker_token

    assert AuthBasis.from_actor(human) == AuthBasis.bearer(human)
    assert AuthBasis.from_actor(human_plain) == local_basis
    assert AuthBasis.from_actor(access.SYSTEM_ACTOR) == sys_basis

    with pytest.raises(ValueError, match=r"requires Actor\.grant"):
        AuthBasis.bearer(human_plain)
    with pytest.raises(ValueError, match="token_id must match"):
        AuthBasis(kind=AuthBasisKind.BEARER, actor=human, token_id=uuid4())
    with pytest.raises(ValueError, match="cannot carry a TokenGrant"):
        AuthBasis.session(human, session_id=session_id)
    with pytest.raises(ValueError, match="requires a human principal"):
        AuthBasis.session(_worker_actor(), session_id=session_id)
    with pytest.raises(ValueError, match="requires session_id"):
        AuthBasis(kind=AuthBasisKind.SESSION, actor=human_plain)
    with pytest.raises(ValueError, match="cannot carry a TokenGrant"):
        AuthBasis.local_owner(human)
    with pytest.raises(ValueError, match="requires a human principal"):
        AuthBasis.local_owner(_service_actor())


def test_kind_allowed_rejects_session_and_local_owner_on_worker_only_specs() -> None:
    worker_spec = cast(
        "Any",
        CommandSpec(
            name="test.worker_op",
            dto=object,
            result=object,
            permission="worker.claim",
            scope_of=None,
            handler=lambda _c, _ctx, _uow: None,
            allowed_kinds=frozenset({PrincipalKind.WORKER}),
        ),
    )
    human = _human_actor()
    session_basis = AuthBasis.session(human, session_id=uuid4())
    local_basis = AuthBasis.local_owner(human)
    worker_grant = TokenGrant(token_id=uuid4(), kind="worker", scope_id=None, permissions=None)
    worker_basis = AuthBasis.bearer(_worker_actor(worker_grant))

    assert not kind_allowed(worker_spec, session_basis)
    assert not kind_allowed(worker_spec, local_basis)
    assert kind_allowed(worker_spec, worker_basis)


def test_bus_and_authorizer_enforce_live_session_bearer_and_local_owner_revocation(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    bus = world.core.bus
    owner_bearer = world.core.authenticate(world.secret)
    owner_plain = Actor(owner_bearer.principal_id, owner_bearer.kind, owner_bearer.display_name)
    meta = world.meta()

    ws_res = cast(
        "Any",
        bus.dispatch(workspace.CreateWorkspace(slug="ab-ws", title="AB WS"), actor=owner_bearer, meta=meta),
    )
    ws_id = WorkspaceId(ws_res.workspace_id)

    # Create an active web session for the owner.
    session_id = uuid4()
    with world.core.uow_factory(meta, readonly=False) as uow:
        session, _secret = access.create_web_session(
            uow,
            principal_id=owner_plain.principal_id,
            session_id=session_id,
            now=world.core.clock.now(),
            ttl_seconds=600,
            entropy=os.urandom,
            pepper=PEPPER,
        )
        uow.commit()

    session_basis = AuthBasis.session(owner_plain, session_id=session.id, expires_at=session.expires_at)

    # EmbeddedClient carries AuthBasis cleanly into bus ask and dispatch.
    client = world.core.client(actor=owner_plain, surface=Surface.API)
    bound = cast("Any", client).for_request(meta, auth_basis=session_basis)
    assert bound.auth_basis == session_basis
    whoami = bound.ask(access.WhoAmI())
    assert whoami.principal.principal_id == owner_plain.principal_id

    # Revoking the web session immediately blocks BOTH permissionless WhoAmI and permissioned queries.
    with world.core.uow_factory(meta, readonly=False) as uow:
        assert access.revoke_web_session(uow, session.id, now=world.core.clock.now())
        uow.commit()

    with pytest.raises(Unauthenticated) as exc_whoami:
        bound.ask(access.WhoAmI())
    assert exc_whoami.value.code is ErrorCode.UNAUTHENTICATED

    with pytest.raises(Unauthenticated) as exc_ws:
        bound.ask(workspace.GetWorkspace(workspace_id=ws_id))
    assert exc_ws.value.code is ErrorCode.UNAUTHENTICATED

    # Expiring a fresh session via clock advance also fails closed inside the bus UoW.
    expiring_id = uuid4()
    with world.core.uow_factory(meta, readonly=False) as uow:
        expiring, _ = access.create_web_session(
            uow,
            principal_id=owner_plain.principal_id,
            session_id=expiring_id,
            now=world.core.clock.now(),
            ttl_seconds=60,
            entropy=os.urandom,
            pepper=PEPPER,
        )
        uow.commit()
    expiring_basis = AuthBasis.session(owner_plain, session_id=expiring.id, expires_at=expiring.expires_at)
    assert bus.ask(access.WhoAmI(), actor=owner_plain, meta=meta, auth_basis=expiring_basis) is not None
    cast("Any", world.core.clock).advance(timedelta(seconds=61))
    with pytest.raises(Unauthenticated):
        bus.ask(access.WhoAmI(), actor=owner_plain, meta=meta, auth_basis=expiring_basis)

    # Bearer with narrow ceiling retains ceiling even when session_id metadata is attached.
    p_narrow = cast(
        "Any",
        bus.dispatch(
            workspace.CreateProject(workspace_id=ws_id, slug="narrow-p", title="Narrow P"),
            actor=owner_bearer,
            meta=meta,
        ),
    )
    narrow = cast(
        "access.CreateTokenResult",
        bus.dispatch(
            access.CreateToken(name="narrow-basis", scope_id=ws_id, permissions=("project.read",)),
            actor=owner_bearer,
            meta=meta,
        ),
    )
    narrow_actor = world.core.authenticate(narrow.secret)
    narrow_basis = AuthBasis.bearer(narrow_actor, session_id=session.id)
    assert (
        bus.ask(
            workspace.GetProject(project_id=p_narrow.project_id),
            actor=narrow_actor,
            meta=meta,
            auth_basis=narrow_basis,
        )
        is not None
    )
    with pytest.raises(Forbidden):
        bus.dispatch(
            workspace.CreateProject(workspace_id=ws_id, slug="denied", title="Denied"),
            actor=narrow_actor,
            meta=meta,
            auth_basis=narrow_basis,
        )

    # Revoking the Bearer token immediately rejects further bus calls with AuthBasis.bearer.
    bus.dispatch(access.RevokeToken(narrow.token_id), actor=owner_bearer, meta=meta)
    with pytest.raises(Unauthenticated):
        bus.ask(
            workspace.GetProject(project_id=p_narrow.project_id),
            actor=narrow_actor,
            meta=meta,
            auth_basis=narrow_basis,
        )

    # Local owner basis rejects disabled principals immediately.
    other_id = PrincipalId(uuid4())
    with world.core.uow_factory(meta, readonly=False) as uow:
        uow.repo(PrincipalRepository).add(
            Principal(
                id=other_id,
                kind=PrincipalKind.HUMAN,
                display_name="Other",
                state=PrincipalState.ACTIVE,
                row_version=1,
                created_at=world.core.clock.now(),
                created_by=owner_plain.principal_id,
            )
        )
        uow.commit()
    other_actor = Actor(other_id, PrincipalKind.HUMAN, "Other")
    other_basis = AuthBasis.local_owner(other_actor)
    assert bus.ask(access.WhoAmI(), actor=other_actor, meta=meta, auth_basis=other_basis) is not None
    bus.dispatch(
        access.DisablePrincipal(other_id, expected_row_version=1, reason="revoked"),
        actor=owner_bearer,
        meta=meta,
    )
    with pytest.raises(Unauthenticated):
        bus.ask(access.WhoAmI(), actor=other_actor, meta=meta, auth_basis=other_basis)


def test_context_populates_and_validates_auth_basis(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    actor = world.core.authenticate(world.secret)
    other = _human_actor()
    meta = world.meta()
    with world.core.uow_factory(meta, readonly=True) as uow:
        chain = world.core.bus._scopes.chain(uow, None)
        cfg = world.core.bus._effective(uow, chain)
    scope = ScopeRef(ScopeKind.INSTANCE, chain[-1].id)

    cmd_ctx = CommandContext(
        actor=actor,
        meta=meta,
        scope=scope,
        scope_chain=chain,
        clock=world.core.clock,
        ids=world.core.bus._ids,
        entropy=world.core.bus._entropy,
        config=cfg,
        log=cast("Any", None),
        gateways=world.core.gateways,
    )
    assert cmd_ctx.auth_basis == AuthBasis.bearer(actor)

    q_ctx = QueryContext(
        actor=actor,
        meta=meta,
        scope=scope,
        scope_chain=chain,
        clock=world.core.clock,
        config=cfg,
        log=cast("Any", None),
        gateways=world.core.gateways,
    )
    assert q_ctx.auth_basis == AuthBasis.bearer(actor)

    with pytest.raises(ValueError, match="must match actor"):
        QueryContext(
            actor=actor,
            meta=meta,
            scope=scope,
            scope_chain=chain,
            clock=world.core.clock,
            config=cfg,
            log=cast("Any", None),
            gateways=world.core.gateways,
            auth_basis=AuthBasis.local_owner(other),
        )

    with pytest.raises(ValueError, match="must match actor"):
        world.core.bus.ask(access.WhoAmI(), actor=actor, meta=meta, auth_basis=AuthBasis.local_owner(other))


def test_bearer_scope_grant_ceiling_preserved_through_auth_basis(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    bus = world.core.bus
    owner = world.core.authenticate(world.secret)
    meta = world.meta()

    ws = cast(
        "Any",
        bus.dispatch(workspace.CreateWorkspace(slug="sg-ws", title="SG WS"), actor=owner, meta=meta),
    )
    ws_id = WorkspaceId(ws.workspace_id)
    p1 = cast(
        "Any",
        bus.dispatch(
            workspace.CreateProject(workspace_id=ws_id, slug="p1", title="P1"), actor=owner, meta=meta
        ),
    )
    p2 = cast(
        "Any",
        bus.dispatch(
            workspace.CreateProject(workspace_id=ws_id, slug="p2", title="P2"), actor=owner, meta=meta
        ),
    )

    pairing_id = world.core.bus._ids.new_id()
    with world.core.uow_factory(meta, readonly=False) as uow:
        pairing_secret = access.issue_pairing_token(
            uow,
            issuer=owner,
            workspace_id=ws_id,
            pairing_id=pairing_id,
            now=world.core.clock.now(),
            expires_at=world.core.clock.now() + timedelta(minutes=10),
            entropy=os.urandom,
            pepper=PEPPER,
            principal_id=owner.principal_id,
            scope_grants=(ScopeGrant(ScopeId(p1.project_id), frozenset({"project.read"})),),
        )
        uow.commit()

    exchanged = cast(
        "workspace.ExchangePairingTokenResult",
        bus.dispatch(
            workspace.ExchangePairingToken(
                workspace_id=ws_id,
                pairing_id=pairing_id,
                pairing_secret=pairing_secret,
            ),
            actor=access.SYSTEM_ACTOR,
            meta=meta,
        ),
    )
    assert exchanged.token_secret is not None
    paired_actor = world.core.authenticate(exchanged.token_secret)
    paired_basis = AuthBasis.bearer(paired_actor)
    assert paired_basis.grant is not None
    assert paired_basis.grant.scope_grants == (
        ScopeGrant(ScopeId(p1.project_id), frozenset({"project.read"})),
    )
    assert (
        bus.ask(
            workspace.GetProject(project_id=p1.project_id),
            actor=paired_actor,
            meta=meta,
            auth_basis=paired_basis,
        )
        is not None
    )
    with pytest.raises(Forbidden):
        bus.ask(
            workspace.GetProject(project_id=p2.project_id),
            actor=paired_actor,
            meta=meta,
            auth_basis=paired_basis,
        )
