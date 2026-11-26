"""R3-6 HTTP authentication, cookie/CSRF, loopback mode, precedence, rate limit, and fail-closed tests."""

from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from fakes.entropy import DeterministicEntropy
from security.api.harness import BASE, NOW, PEPPER, TestClient, make_world
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    uvicorn_proxy_config,
    validate_web_auth_bind,
)
from skm.kernel.actor import ScopeGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed, error_for
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.modules.access import public as access
from skm.modules.access.generated.commands import BootstrapLocalOwner
from skm.modules.workspace import public as workspace
from skm.platform.config.bootstrap import WebAuthConfig
from skm.platform.logging.redaction import MASK, Redactor

ADMIN_PASSWORD = "correct-horse-battery-staple-42"


def _world_with_password(tmp_path: Path):
    world = make_world(tmp_path)
    world.core.bus.dispatch(
        BootstrapLocalOwner(display_name="API owner", password=ADMIN_PASSWORD),
        actor=access.SYSTEM_ACTOR,
        meta=world.meta(),
    )
    return world


def _login(
    client: TestClient,
    *,
    password: str = ADMIN_PASSWORD,
    origin: str = BASE,
    extra_headers: dict[str, str] | None = None,
):
    csrf_resp = client.get("/api/v1/auth/csrf")
    assert csrf_resp.status_code == 200
    csrf_token = csrf_resp.json()["csrf_token"]
    headers = {"Origin": origin, "X-SKM-CSRF": csrf_token, **(extra_headers or {})}
    return client.post("/api/v1/auth/login", json={"password": password}, headers=headers), csrf_token


# --------------------------------------------------------------------------- mode='none' invariants


@pytest.mark.parametrize("bind", ["127.0.0.1:8765", "[::1]:8765", "localhost:8765"])
def test_none_mode_accepts_loopback_binds(bind: str) -> None:
    validate_web_auth_bind(bind, WebAuthConfig(mode="none"))


@pytest.mark.parametrize("bind", ["0.0.0.0:8765", "[::]:8765", "192.168.1.5:8765", "skm.example.org:8765"])
def test_none_mode_rejects_non_loopback_binds(bind: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        validate_web_auth_bind(bind, WebAuthConfig(mode="none"))
    assert caught.value.code is ErrorCode.CONFIG_INVALID


def test_none_mode_strictly_disables_proxy_headers() -> None:
    cfg = WebAuthConfig(mode="none", forwarded_allow_ips=("127.0.0.1", "10.0.0.0/8"))
    assert uvicorn_proxy_config(cfg, {"api.proxy.trusted": True}) == (False, None)


@pytest.mark.parametrize(
    ("peer", "host", "expected_status"),
    [
        (("127.0.0.1", 50000), "127.0.0.1:8765", 200),
        (("::1", 50000), "[::1]:8765", 200),
        (("::ffff:127.0.0.1", 50000), "localhost:8765", 200),
        (("192.168.1.10", 50000), "127.0.0.1:8765", 403),
        (("2001:db8::1", 50000), "[::1]:8765", 403),
        (("testclient", 50000), "127.0.0.1:8765", 403),
    ],
)
def test_none_mode_enforces_ipv4_ipv6_loopback_peer_and_host(
    tmp_path: Path, peer: tuple[str, int], host: str, expected_status: int
) -> None:
    world = make_world(tmp_path)
    api = create_app(
        world.core,
        web_auth=WebAuthConfig(mode="none"),
        settings={
            "api.bind": "127.0.0.1:8765",
            "api.allowed_hosts": ["127.0.0.1:8765", "localhost:8765", "[::1]:8765", "evil.example:8765"],
        },
    )
    with TestClient(api, base_url=BASE, client=peer) as client:
        res = client.get("/api/v1/auth/session", headers={"Host": host})
        assert res.status_code == expected_status
        if expected_status == 200:
            body = res.json()
            assert body["mode"] == "none"
            assert body["auth_method"] == "none"
            assert body["principal_id"] == str(world.owner.principal_id)
        else:
            assert res.json()["details"]["reason"] == "non_loopback_peer"


def test_none_mode_rejects_non_loopback_host_even_if_configured_in_allowed_hosts(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    api = create_app(
        world.core,
        web_auth=WebAuthConfig(mode="none"),
        settings={"api.allowed_hosts": ["127.0.0.1:8765", "skm.example.org"]},
    )
    with TestClient(api, base_url=BASE, client=("127.0.0.1", 50000)) as client:
        rejected = client.get("/api/v1/auth/session", headers={"Host": "skm.example.org"})
        assert rejected.status_code == 403
        assert rejected.json()["code"] == "HOST_REJECTED"


# --------------------------------------------------------------------------- mode='admin_login' invariants


def test_admin_login_uvicorn_proxy_config_uses_forwarded_allow_ips() -> None:
    explicit = WebAuthConfig(mode="admin_login", forwarded_allow_ips=("127.0.0.1", "10.1.0.0/16"))
    assert uvicorn_proxy_config(explicit, {}) == (True, ["127.0.0.1", "10.1.0.0/16"])
    # DB-backed api.proxy.trusted must NEVER widen proxy trust when [web_auth].forwarded_allow_ips is empty.
    empty_bootstrap = WebAuthConfig(mode="admin_login")
    assert uvicorn_proxy_config(empty_bootstrap, {"api.proxy.trusted": True}) == (False, None)
    assert uvicorn_proxy_config(empty_bootstrap, {"api.proxy.trusted": False}) == (False, None)


def test_admin_login_cookie_csrf_same_origin_reload_and_logout(tmp_path: Path) -> None:
    world = _world_with_password(tmp_path)
    with world.client(web_auth=WebAuthConfig(mode="admin_login", cookie_samesite="strict")) as client:
        # Unauthenticated protected calls fail closed
        assert client.get("/api/v1/auth/session").status_code == 401
        assert client.post("/api/v1/auth/logout").status_code == 401

        # Login succeeds with CSRF + same-origin
        login_res, _pre_csrf = _login(client)
        assert login_res.status_code == 200
        set_cookies = login_res.headers.get_list("set-cookie")
        session_hdr = next(h for h in set_cookies if h.startswith(f"{SESSION_COOKIE_NAME}="))
        assert "HttpOnly" in session_hdr
        assert "SameSite=strict" in session_hdr
        assert "Secure" not in session_hdr  # normalized scheme is http

        first_session_id = login_res.json()["session_id"]
        first_csrf = login_res.json()["csrf_token"]
        first_session_cookie = client.cookies.get(SESSION_COOKIE_NAME)
        assert first_session_cookie is not None

        # Safe GET works with session cookie alone
        sess = client.get("/api/v1/auth/session")
        assert sess.status_code == 200
        assert sess.json()["auth_method"] == "session"
        assert sess.json()["session_id"] == first_session_id
        assert client.get("/api/v1/me").status_code == 200

        # Mutating call without CSRF fails with 403
        no_csrf = client.post("/api/v1/tokens", json={"name": "no-csrf"}, headers={"Origin": BASE})
        assert no_csrf.status_code == 403
        assert no_csrf.json()["details"]["reason"] == "csrf_invalid"

        # Mutating call with wrong CSRF fails with 403
        bad_csrf = client.post(
            "/api/v1/tokens",
            json={"name": "bad-csrf"},
            headers={"Origin": BASE, "X-SKM-CSRF": "skm_csrf_invalid"},
        )
        assert bad_csrf.status_code == 403

        # Mutating call with missing Origin & Referer fails with 403 ORIGIN_REJECTED
        no_origin = client.post(
            "/api/v1/tokens",
            json={"name": "no-origin"},
            headers={"X-SKM-CSRF": first_csrf},
        )
        assert no_origin.status_code == 403
        assert no_origin.json()["code"] == "ORIGIN_REJECTED"

        # Mutating call with same-origin + valid CSRF succeeds
        ok_mut = client.post(
            "/api/v1/tokens",
            json={"name": "cookie-token"},
            headers={"Origin": BASE, "X-SKM-CSRF": first_csrf},
        )
        assert ok_mut.status_code == 200

        # Reload session rotates session + CSRF and invalidates the old session cookie
        reloaded = client.post(
            "/api/v1/auth/session/reload",
            headers={"Origin": BASE, "X-SKM-CSRF": first_csrf},
        )
        assert reloaded.status_code == 200
        second_session_id = reloaded.json()["session_id"]
        second_csrf = reloaded.json()["csrf_token"]
        assert second_session_id != first_session_id
        assert second_csrf != first_csrf

        # Old session cookie is revoked immediately
        stale_res = client.get(
            "/api/v1/auth/session", headers={"Cookie": f"{SESSION_COOKIE_NAME}={first_session_cookie}"}
        )
        assert stale_res.status_code == 401

        # Logout without CSRF fails with 403
        bad_logout = client.post("/api/v1/auth/logout", headers={"Origin": BASE})
        assert bad_logout.status_code == 403

        # Logout with active session + CSRF + same-origin revokes session & clears cookies
        logout_res = client.post(
            "/api/v1/auth/logout",
            headers={"Origin": BASE, "X-SKM-CSRF": second_csrf},
        )
        assert logout_res.status_code == 200
        assert logout_res.json() == {"status": "logged_out"}
        assert client.get("/api/v1/auth/session").status_code == 401


def test_admin_login_normalized_https_scheme_sets_secure_cookie_and_ignores_raw_forwarded_proto(
    tmp_path: Path,
) -> None:
    world = _world_with_password(tmp_path)
    api = create_app(
        world.core,
        settings={"api.allowed_hosts": ["skm.example.org"]},
        web_auth=WebAuthConfig(mode="admin_login"),
    )
    # Untrusted raw X-Forwarded-Proto over HTTP must NOT spoof https scheme
    with TestClient(api, base_url="http://skm.example.org") as http_client:
        csrf = http_client.get("/api/v1/auth/csrf").json()["csrf_token"]
        spoofed = http_client.post(
            "/api/v1/auth/login",
            json={"password": ADMIN_PASSWORD},
            headers={
                "Origin": "https://skm.example.org",
                "X-Forwarded-Proto": "https",
                "X-SKM-CSRF": csrf,
            },
        )
        assert spoofed.status_code == 403
        assert spoofed.json()["code"] == "ORIGIN_REJECTED"

    # Normalized HTTPS scheme (as rewritten by Uvicorn once via forwarded_allow_ips) sets Secure cookie
    with TestClient(api, base_url="https://skm.example.org") as https_client:
        login_res, _ = _login(https_client, origin="https://skm.example.org")
        assert login_res.status_code == 200
        set_cookies = login_res.headers.get_list("set-cookie")
        session_hdr = next(h for h in set_cookies if h.startswith(f"{SESSION_COOKIE_NAME}="))
        csrf_hdr = next(h for h in set_cookies if h.startswith(f"{CSRF_COOKIE_NAME}="))
        assert "Secure" in session_hdr
        assert "Secure" in csrf_hdr


def test_admin_login_rejects_cross_origin_even_if_in_cors_allowlist(tmp_path: Path) -> None:
    world = _world_with_password(tmp_path)
    with world.client(settings={"api.cors.origins": ["https://other.example"]}) as client:
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        cross = client.post(
            "/api/v1/auth/login",
            json={"password": ADMIN_PASSWORD},
            headers={"Origin": "https://other.example", "X-SKM-CSRF": csrf},
        )
        assert cross.status_code == 403
        assert cross.json()["code"] == "ORIGIN_REJECTED"


def test_login_and_pairing_rate_limit_and_window_recovery(tmp_path: Path) -> None:
    world = _world_with_password(tmp_path)
    now = [100.0]
    cfg = WebAuthConfig(mode="admin_login", login_rate_limit_max=2, login_rate_limit_window_seconds=30)
    with world.client(web_auth=cfg, rate_limit_clock=lambda: now[0]) as client:
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        headers = {"Origin": BASE, "X-SKM-CSRF": csrf}
        assert (
            client.post(
                "/api/v1/auth/login", json={"password": "wrong-password-123"}, headers=headers
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/login", json={"password": "wrong-password-123"}, headers=headers
            ).status_code
            == 401
        )
        limited = client.post("/api/v1/auth/login", json={"password": ADMIN_PASSWORD}, headers=headers)
        assert limited.status_code == 429
        assert limited.json()["code"] == "AUTH_RATE_LIMITED"
        assert int(limited.headers["Retry-After"]) >= 1

        # Pairing endpoint shares peer rate limiting
        pair_limited = client.post(
            "/api/v1/auth/pairing/exchange",
            json={
                "workspace_id": "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c11",
                "pairing_id": "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c12",
                "pairing_secret": "skm_pair_" + "A" * 43,
            },
        )
        assert pair_limited.status_code == 429

        # Window expires -> login succeeds
        now[0] += 31.0
        recovered = client.post("/api/v1/auth/login", json={"password": ADMIN_PASSWORD}, headers=headers)
        assert recovered.status_code == 200


# --------------------------------------------------------------------------- Public table & pairing exchange


def test_public_table_and_one_time_pairing_exchange(tmp_path: Path) -> None:
    world = _world_with_password(tmp_path)
    actor = world.core.authenticate(world.secret)
    ws_result = cast(
        "Any",
        world.core.bus.dispatch(
            workspace.CreateWorkspace(slug="pair-ws", title="Pair WS"), actor=actor, meta=world.meta()
        ),
    )
    ws_id = WorkspaceId(ws_result.workspace_id)
    pairing_id = world.core.bus._ids.new_id()
    with world.core.uow_factory(world.meta(), readonly=False) as uow:
        pairing_secret = access.issue_pairing_token(
            uow,
            issuer=actor,
            workspace_id=ws_id,
            pairing_id=pairing_id,
            now=NOW,
            expires_at=NOW + timedelta(minutes=5),
            entropy=DeterministicEntropy(pairing_id.bytes).bytes,
            pepper=PEPPER,
            principal_id=actor.principal_id,
            scope_grants=(ScopeGrant(ScopeId(ws_id), frozenset({"workspace.read"})),),
        )
        uow.commit()

    with world.client() as client:
        # Public endpoints
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get("/api/v1/openapi.json").status_code == 200
        assert client.get("/api/v1/auth/csrf").status_code == 200

        # Non-public HTTP methods on public paths must NOT bypass auth
        assert client.post("/health/live", json={}).status_code == 401
        assert (
            client.delete("/api/v1/openapi.json", headers={"Content-Type": "application/json"}).status_code
            == 401
        )

        # Logout requires active session (Bearer alone is refused)
        assert client.post("/api/v1/auth/logout", headers=world.headers).status_code == 401

        # One-time pairing exchange works unauthenticated and reveals token_secret once
        first = client.post(
            "/api/v1/auth/pairing/exchange",
            json={
                "workspace_id": str(ws_id),
                "pairing_id": str(pairing_id),
                "pairing_secret": pairing_secret,
            },
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["status"] == "exchanged"
        assert first_body["token_secret"].startswith("skm_live_")

        # Replaying the same pairing code never re-issues the secret
        replay = client.post(
            "/api/v1/auth/pairing/exchange",
            json={
                "workspace_id": str(ws_id),
                "pairing_id": str(pairing_id),
                "pairing_secret": pairing_secret,
            },
        )
        assert replay.status_code == 200
        assert replay.json().get("token_secret") is None
        assert replay.json()["token_id"] == first_body["token_id"]

        # Bad pairing secret returns 401
        bad_pair = client.post(
            "/api/v1/auth/pairing/exchange",
            json={
                "workspace_id": str(ws_id),
                "pairing_id": str(pairing_id),
                "pairing_secret": "skm_pair_" + "Z" * 43,
            },
        )
        assert bad_pair.status_code == 401


# --------------------------------------------------------------------------- Credential precedence


def test_credential_precedence_same_vs_different_subject_and_invalid_bearer(tmp_path: Path) -> None:
    world = _world_with_password(tmp_path)
    owner_actor = world.core.authenticate(world.secret)

    # Create a narrowed Bearer token for the SAME owner (lacks admin.storage)
    narrow_owner_tok = cast(
        "Any",
        world.core.bus.dispatch(
            access.CreateToken(name="owner-narrow", permissions=("token.own",)),
            actor=owner_actor,
            meta=world.meta(),
        ),
    )

    # Create a DIFFERENT human principal + personal token
    other_principal = cast(
        "Any",
        world.core.bus.dispatch(
            access.CreatePrincipal.from_json({"kind": "human", "display_name": "Other Human"}),
            actor=owner_actor,
            meta=world.meta(),
        ),
    )
    other_tok = cast(
        "Any",
        world.core.bus.dispatch(
            access.CreateToken(
                name="other-token",
                principal_id=PrincipalId(other_principal.principal_id),
                permissions=("token.own",),
            ),
            actor=owner_actor,
            meta=world.meta(),
        ),
    )

    with world.client() as client:
        login_res, _ = _login(client)
        assert login_res.status_code == 200
        # Owner cookie alone CAN access /api/v1/admin/migrations (owner has admin.storage)
        assert client.get("/api/v1/admin/migrations").status_code == 200

        # 1. Bearer + cookie of SAME subject -> Bearer permission ceiling (403 on admin/migrations!)
        same_me = client.get(
            "/api/v1/auth/session", headers={"Authorization": f"Bearer {narrow_owner_tok.secret}"}
        )
        assert same_me.status_code == 200
        assert same_me.json()["auth_method"] == "bearer"
        same_mig = client.get(
            "/api/v1/admin/migrations",
            headers={"Authorization": f"Bearer {narrow_owner_tok.secret}"},
        )
        assert same_mig.status_code == 403
        assert same_mig.json()["code"] == "FORBIDDEN"

        # 2. Bearer + cookie of DIFFERENT subjects -> 401 AMBIGUOUS_CREDENTIALS
        ambiguous = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {other_tok.secret}"},
        )
        assert ambiguous.status_code == 401
        assert ambiguous.json()["code"] == "AMBIGUOUS_CREDENTIALS"

        # 3. Malformed or invalid Bearer EVEN WITH valid cookie -> 401 UNAUTHENTICATED
        for bad_header in ("Bearer invalid-token", "Basic dXNlcjpwYXNz", "Bearer"):
            invalid = client.get("/api/v1/me", headers={"Authorization": bad_header})
            assert invalid.status_code == 401
            assert invalid.json()["code"] == "UNAUTHENTICATED"


def test_public_auth_routes_enforce_bearer_validation_and_precedence_when_authorization_present(
    tmp_path: Path,
) -> None:
    world = _world_with_password(tmp_path)
    owner_actor = world.core.authenticate(world.secret)
    other_principal = cast(
        "Any",
        world.core.bus.dispatch(
            access.CreatePrincipal.from_json({"kind": "human", "display_name": "Other Public Human"}),
            actor=owner_actor,
            meta=world.meta(),
        ),
    )
    other_tok = cast(
        "Any",
        world.core.bus.dispatch(
            access.CreateToken(
                name="other-public-token",
                principal_id=PrincipalId(other_principal.principal_id),
                permissions=("token.own",),
            ),
            actor=owner_actor,
            meta=world.meta(),
        ),
    )

    with world.client() as client:
        login_res, _ = _login(client)
        assert login_res.status_code == 200
        csrf_token = login_res.json()["csrf_token"]

        # Malformed or invalid Bearer on public auth routes -> 401 UNAUTHENTICATED
        for bad_auth in ("Basic abc", "Bearer", "Bearer invalid-token"):
            assert client.get("/api/v1/auth/csrf", headers={"Authorization": bad_auth}).status_code == 401
            assert (
                client.post(
                    "/api/v1/auth/login",
                    json={"password": ADMIN_PASSWORD},
                    headers={"Origin": BASE, "X-SKM-CSRF": csrf_token, "Authorization": bad_auth},
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/api/v1/auth/pairing/exchange",
                    json={
                        "workspace_id": "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c11",
                        "pairing_id": "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c12",
                        "pairing_secret": "skm_pair_" + "A" * 43,
                    },
                    headers={"Authorization": bad_auth},
                ).status_code
                == 401
            )

        # Conflicting valid Bearer + valid session cookie of different subjects -> 401 AMBIGUOUS_CREDENTIALS
        conflict_headers = {"Authorization": f"Bearer {other_tok.secret}"}
        csrf_conflict = client.get("/api/v1/auth/csrf", headers=conflict_headers)
        assert (csrf_conflict.status_code, csrf_conflict.json()["code"]) == (401, "AMBIGUOUS_CREDENTIALS")

        login_conflict = client.post(
            "/api/v1/auth/login",
            json={"password": ADMIN_PASSWORD},
            headers={"Origin": BASE, "X-SKM-CSRF": csrf_token, **conflict_headers},
        )
        assert (login_conflict.status_code, login_conflict.json()["code"]) == (401, "AMBIGUOUS_CREDENTIALS")

        pair_conflict = client.post(
            "/api/v1/auth/pairing/exchange",
            json={
                "workspace_id": "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c11",
                "pairing_id": "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c12",
                "pairing_secret": "skm_pair_" + "A" * 43,
            },
            headers=conflict_headers,
        )
        assert (pair_conflict.status_code, pair_conflict.json()["code"]) == (401, "AMBIGUOUS_CREDENTIALS")


def test_session_reload_aborts_on_concurrent_revoke_race_without_issuing_second_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import skm.entrypoints.api.routes.auth as auth_routes_mod

    world = _world_with_password(tmp_path)
    with world.client() as client:
        login_res, _ = _login(client)
        assert login_res.status_code == 200
        csrf_token = login_res.json()["csrf_token"]
        before_sessions = dict(world.backend.committed.modules["access"].web_sessions)
        assert len(before_sessions) == 1

        # Simulate concurrent reload/logout winning the conditional UPDATE first.
        monkeypatch.setattr(auth_routes_mod, "revoke_web_session", lambda *_args, **_kwargs: False)
        raced = client.post(
            "/api/v1/auth/session/reload",
            headers={"Origin": BASE, "X-SKM-CSRF": csrf_token},
        )
        assert raced.status_code == 401
        assert raced.json()["code"] == "UNAUTHENTICATED"
        after_sessions = dict(world.backend.committed.modules["access"].web_sessions)
        assert set(after_sessions) == set(before_sessions)


# ----------------------------------------------------------------- Fail-closed DB & admin/migrations


def test_admin_migrations_and_auth_fail_closed_when_db_or_permission_check_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world_with_password(tmp_path)
    with world.client() as client:
        # 1. Database unavailable -> /api/v1/admin/migrations and /api/v1/me fail closed with 503
        health = cast("Any", client.app).state.health
        health.database_ok = False
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        mig_down = client.get("/api/v1/admin/migrations", headers=world.headers)
        assert mig_down.status_code == 503
        assert mig_down.json()["code"] == "BACKEND_UNAVAILABLE"
        login_down = client.post(
            "/api/v1/auth/login", json={"password": ADMIN_PASSWORD}, headers={"Origin": BASE}
        )
        assert login_down.status_code == 503

        # 2. DB health ok, but permission check unavailable -> /api/v1/admin/migrations fails closed
        health.database_ok = True

        def broken_authorize(*_args: Any, **_kwargs: Any) -> Any:
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "permission store unavailable")

        monkeypatch.setattr(world.core.bus._authorizer, "authorize", broken_authorize)
        mig_no_authz = client.get("/api/v1/admin/migrations", headers=world.headers)
        assert mig_no_authz.status_code == 503
        assert mig_no_authz.json()["code"] == "BACKEND_UNAVAILABLE"


def test_none_mode_fails_closed_when_db_unavailable(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    api = create_app(world.core, web_auth=WebAuthConfig(mode="none"))
    with TestClient(api, base_url=BASE, client=("127.0.0.1", 50000)) as client:
        cast("Any", client.app).state.health.database_ok = False
        assert client.get("/api/v1/auth/session").status_code == 503
        assert client.get("/api/v1/admin/migrations").status_code == 503


# ----------------------------------------------------------------- Redaction of cookies, session, CSRF, pwd


def test_redactor_masks_sessions_csrf_cookies_and_passwords() -> None:
    redactor = Redactor()
    session_tok = "skm_sess_" + "A" * 43
    csrf_tok = "skm_csrf_" + "B" * 32 + "." + "a" * 64
    assert redactor.text(f"session={session_tok}") == f"session={MASK}"
    assert redactor.text(f"csrf={csrf_tok}") == f"csrf={MASK}"
    assert redactor.text(f"Cookie: skm_session={session_tok}; skm_csrf={csrf_tok}") == f"Cookie: {MASK}"
    assert (
        redactor.text(f"Set-Cookie: skm_session={session_tok}; HttpOnly; SameSite=Lax")
        == f"Set-Cookie: {MASK}"
    )
    assert redactor.text(f"X-SKM-CSRF: {csrf_tok}") == f"X-SKM-CSRF: {MASK}"
    assert redactor.text("skm_session=shortval next") == f"skm_session={MASK} next"
    assert redactor.text(f"SKM_FIRST_ADMIN_PASSWORD={ADMIN_PASSWORD}") == f"SKM_FIRST_ADMIN_PASSWORD={MASK}"
    assert redactor.text("passphrase=my-super-secret-phrase") == f"passphrase={MASK}"
    assert redactor.text("credential=my-super-secret-cred") == f"credential={MASK}"


def test_presented_session_cookie_and_csrf_never_leak_in_problem_responses(tmp_path: Path) -> None:
    world = _world_with_password(tmp_path)
    secret_cookie = "custom-cookie-secret-12345"
    secret_csrf = "custom-csrf-secret-67890"

    async def boom(request: Request) -> JSONResponse:
        raise error_for(
            ErrorCode.BACKEND_UNAVAILABLE,
            f"leaked {secret_cookie} and {secret_csrf}",
            details={"cookie": secret_cookie, "csrf": secret_csrf},
            retryable=True,
        )

    with world.client(routes=[Route("/api/v1/boom", boom)]) as client:
        res = client.get(
            "/api/v1/boom",
            headers={
                **world.headers,
                "X-SKM-CSRF": secret_csrf,
                "Cookie": f"{SESSION_COOKIE_NAME}={secret_cookie}",
            },
        )
        assert res.status_code == 503
        assert secret_cookie not in res.text
        assert secret_csrf not in res.text
