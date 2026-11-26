"""Quarantine recovery token_id exclusivity and session/pairing revocation tests (R3-6)."""

from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from fakes.entropy import DeterministicEntropy
from security.api.harness import BASE, NOW, PEPPER, TestClient, make_world
from skm.application_bus.middleware import RecoveryGuard
from skm.bootstrap import _quarantine
from skm.bootstrap._quarantine import verify_recovery_actor
from skm.entrypoints.api.app import create_app
from skm.kernel.actor import Actor, PrincipalKind, ScopeGrant, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, Unauthenticated
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.modules.access import public as access
from skm.modules.access.generated.commands import BootstrapLocalOwner
from skm.modules.workspace import public as workspace
from skm.platform.config.bootstrap import WebAuthConfig
from skm.platform.storage.restore import MARKER


def test_verify_recovery_actor_allows_only_exact_issued_token_id() -> None:
    owner_id = PrincipalId(uuid4())
    restore_id = uuid4()
    issued_token_id = uuid4()
    other_token_id = uuid4()
    active_tokens = [(issued_token_id, f"restore-{restore_id}")]

    # Exact recovery token issued by _rotate -> allowed
    recovery_actor = Actor(
        principal_id=owner_id,
        kind=PrincipalKind.HUMAN,
        display_name="Owner",
        grant=TokenGrant(
            token_id=issued_token_id,
            kind="personal",
            scope_id=ScopeId(uuid4()),
            permissions=frozenset({"admin.storage"}),
        ),
    )
    verify_recovery_actor(recovery_actor, issued_token_id, active_tokens, restore_id)

    # Password / web cookie / local_owner of the SAME person (grant is None) MUST NOT substitute
    grantless_actor = Actor(
        principal_id=owner_id,
        kind=PrincipalKind.HUMAN,
        display_name="Owner",
        grant=None,
    )
    with pytest.raises(PreconditionFailed) as caught:
        verify_recovery_actor(grantless_actor, issued_token_id, active_tokens, restore_id)
    assert caught.value.details["reason"] == "restore_recovery_token_required"

    # Another personal token_id of the SAME person MUST NOT substitute (even if active list matches its id!)
    other_token_actor = Actor(
        principal_id=owner_id,
        kind=PrincipalKind.HUMAN,
        display_name="Owner",
        grant=TokenGrant(
            token_id=other_token_id,
            kind="personal",
            scope_id=ScopeId(uuid4()),
            permissions=frozenset({"admin.storage"}),
        ),
    )
    for token_rows in (active_tokens, [(other_token_id, f"restore-{restore_id}")]):
        with pytest.raises(PreconditionFailed) as caught_other:
            verify_recovery_actor(other_token_actor, issued_token_id, token_rows, restore_id)
        assert caught_other.value.details["reason"] == "restore_recovery_token_required"

    # Missing expected_token_id MUST fail closed
    with pytest.raises(PreconditionFailed) as caught_missing:
        verify_recovery_actor(recovery_actor, None, active_tokens, restore_id)
    assert caught_missing.value.details["reason"] == "restore_recovery_token_required"


def test_rotate_records_recovery_token_id_and_revokes_web_sessions_and_pairings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    restore_id = uuid4()
    owner_id = uuid4()
    instance_id = ScopeId(uuid4())
    issued_token_id = uuid4()
    executed: list[tuple[str, Any]] = []

    class FakeCursor:
        def __init__(self, rows: list[Any]) -> None:
            self._rows = rows

        def fetchone(self) -> Any:
            return self._rows[0] if self._rows else None

        def __iter__(self):
            return iter(self._rows)

    class FakeConn:
        def execute(self, sql: str, params: Any = None) -> FakeCursor:
            executed.append((sql.strip(), params))
            if "FROM skm_access.api_tokens" in sql:
                return FakeCursor([])
            if "FROM skm_access.principals" in sql:
                return FakeCursor([(owner_id,)])
            return FakeCursor([])

    class FakeScopeRegistry:
        def instance(self) -> Any:
            return type("Scope", (), {"id": instance_id})()

    class FakeUoW:
        connection = FakeConn()

        def repo(self, _port: Any) -> Any:
            return FakeScopeRegistry()

        def commit(self) -> None:
            pass

    @contextmanager
    def uow_factory(_meta: Any, *, readonly: bool = False):
        del readonly
        yield FakeUoW()

    class FakeResult:
        token_id = issued_token_id
        secret = "skm_live_abcdefgh_" + "A" * 43 + "_01234567"

    monkeypatch.setattr(_quarantine.Bus, "dispatch", lambda *_args, **_kwargs: FakeResult())

    paths = cast("Any", type("Paths", (), {"state_dir": tmp_path})())
    app = cast("Any", type("FakeApp", (), {"uow_factory": staticmethod(uow_factory), "bus": object()})())
    returned_id = _quarantine._rotate(app, paths, {"restore_id": str(restore_id)})

    assert returned_id == issued_token_id
    assert any("UPDATE skm_access.web_sessions SET revoked_at" in sql for sql, _ in executed)
    assert any("UPDATE skm_access.pairing_tokens SET revoked_at" in sql for sql, _ in executed)
    assert any(
        "UPDATE public.skm_restore_control SET recovery_token_id" in sql
        and params == (issued_token_id, str(restore_id))
        for sql, params in executed
    )
    assert (tmp_path / "secrets/owner.token").read_text(encoding="utf-8").strip() == FakeResult.secret


def test_bulk_revoke_web_sessions_and_pairing_tokens_in_memory_backend(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    actor = world.core.authenticate(world.secret)
    ws = workspace.CreateWorkspace(slug="q-ws", title="Q WS")
    ws_id = WorkspaceId(cast("Any", world.core.bus.dispatch(ws, actor=actor, meta=world.meta())).workspace_id)
    session_id = uuid4()
    pairing_id = uuid4()
    with world.core.uow_factory(world.meta(), readonly=False) as uow:
        _session, session_secret = access.create_web_session(
            uow,
            principal_id=actor.principal_id,
            session_id=session_id,
            now=NOW,
            ttl_seconds=3600,
            entropy=DeterministicEntropy(session_id.bytes).bytes,
            pepper=PEPPER,
        )
        pairing_secret = access.issue_pairing_token(
            uow,
            issuer=actor,
            workspace_id=ws_id,
            pairing_id=pairing_id,
            now=NOW,
            expires_at=NOW + timedelta(minutes=10),
            entropy=DeterministicEntropy(pairing_id.bytes).bytes,
            pepper=PEPPER,
            principal_id=actor.principal_id,
            scope_grants=(ScopeGrant(ScopeId(ws_id), frozenset({"workspace.read"})),),
        )
        uow.commit()

    # Revoke all web sessions and pairing tokens
    later = NOW + timedelta(seconds=5)
    with world.core.uow_factory(world.meta(), readonly=False) as uow:
        assert access.revoke_all_web_sessions(uow, now=later) == 1
        assert access.revoke_all_pairing_tokens(uow, now=later) == 1
        uow.commit()

    with world.core.uow_factory(world.meta(), readonly=True) as uow:
        with pytest.raises(Unauthenticated) as sess_err:
            access.authenticate_web_session(uow, session_secret, pepper=PEPPER, now=later)
        assert sess_err.value.code is ErrorCode.UNAUTHENTICATED
        with pytest.raises(Unauthenticated) as pair_err:
            access.lock_pairing_token(
                uow, pairing_id, pairing_secret, workspace_id=ws_id, now=later, pepper=PEPPER
            )
        assert pair_err.value.code is ErrorCode.UNAUTHENTICATED


def test_active_quarantine_blocks_web_login_and_pairing_exchange(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    world.core.bus.dispatch(
        BootstrapLocalOwner(display_name="Owner", password="quarantine-password-123"),
        actor=access.SYSTEM_ACTOR,
        meta=world.meta(),
    )
    (tmp_path / MARKER).write_text("{}", encoding="utf-8")
    guard = RecoveryGuard(tmp_path, uuid4(), "sha256:abc", lambda: None, lambda _n, _i: False)
    world.core.bus.guard = guard  # type: ignore[attr-defined]

    with world.client() as client:
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        login = client.post(
            "/api/v1/auth/login",
            json={"password": "quarantine-password-123"},
            headers={"Origin": BASE, "X-SKM-CSRF": csrf},
        )
        assert login.status_code == 409
        assert login.json()["details"]["reason"] == "restore_quarantine"

        pair = client.post(
            "/api/v1/auth/pairing/exchange",
            json={
                "workspace_id": str(uuid4()),
                "pairing_id": str(uuid4()),
                "pairing_secret": "skm_pair_" + "A" * 43,
            },
        )
        assert pair.status_code == 409
        assert pair.json()["details"]["reason"] == "restore_quarantine"


def test_active_quarantine_blocks_none_mode_and_enforces_exact_recovery_token_at_http_admission(
    tmp_path: Path,
) -> None:
    world = make_world(tmp_path)
    owner_actor = world.core.authenticate(world.secret)
    assert owner_actor.grant is not None
    # Issue a second personal token for the SAME owner; treat it as the recovery token issued by _rotate.
    recovery_tok = cast(
        "Any",
        world.core.bus.dispatch(
            access.CreateToken(name="restore-recovery"), actor=owner_actor, meta=world.meta()
        ),
    )
    # Create a valid web session cookie for the owner before quarantine takes effect.
    session_id = uuid4()
    with world.core.uow_factory(world.meta(), readonly=False) as uow:
        _session, session_secret = access.create_web_session(
            uow,
            principal_id=owner_actor.principal_id,
            session_id=session_id,
            now=NOW,
            ttl_seconds=3600,
            entropy=DeterministicEntropy(session_id.bytes).bytes,
            pepper=PEPPER,
        )
        uow.commit()

    (tmp_path / MARKER).write_text("{}", encoding="utf-8")
    guard = RecoveryGuard(
        tmp_path,
        uuid4(),
        "sha256:abc",
        lambda: None,
        lambda _n, _i: False,
        recovery_token_id=lambda: recovery_tok.token_id,
    )
    world.core.bus.guard = guard  # type: ignore[attr-defined]

    api = create_app(world.core, web_auth=WebAuthConfig(mode="none"))
    with TestClient(api, base_url=BASE, client=("127.0.0.1", 50000)) as client:
        # 1. 'none' mode MUST NOT resolve local_owner while quarantine is active
        none_res = client.get("/api/v1/auth/session")
        assert none_res.status_code == 409
        assert none_res.json()["details"]["reason"] == "restore_recovery_token_required"

        # 2. Web session cookie MUST NOT substitute during quarantine
        cookie_res = client.get("/api/v1/auth/session", headers={"Cookie": f"skm_session={session_secret}"})
        assert cookie_res.status_code == 409
        assert cookie_res.json()["details"]["reason"] == "restore_recovery_token_required"

        # 3. A DIFFERENT personal Bearer token of the SAME owner MUST NOT substitute during quarantine
        other_res = client.get("/api/v1/auth/session", headers=world.headers)
        assert other_res.status_code == 409
        assert other_res.json()["details"]["reason"] == "restore_recovery_token_required"

        # 4. ONLY the exact recovery token_id issued by _rotate is admitted
        ok_res = client.get(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {recovery_tok.secret}"},
        )
        assert ok_res.status_code == 200
        assert ok_res.json()["auth_method"] == "bearer"
        assert ok_res.json()["principal_id"] == str(owner_actor.principal_id)
