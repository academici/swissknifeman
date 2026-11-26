import asyncio
from dataclasses import replace
from typing import Any, cast

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from security.api.harness import BASE, make_world
from skm.entrypoints.api.middleware import BodyPolicy
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.access.public import CreateToken, RevokeToken
from skm.platform.logging.redaction import Redactor


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ({"Host": "evil.example:8765"}, "HOST_REJECTED"),
        ({"Host": "[broken"}, "HOST_REJECTED"),
        ([("Host", "127.0.0.1:8765"), ("Host", "evil.example")], "HOST_REJECTED"),
        ({"Origin": "null"}, "ORIGIN_REJECTED"),
        ({"Origin": "http://evil.example"}, "ORIGIN_REJECTED"),
        ([("Origin", "http://127.0.0.1:8765"), ("Origin", "http://evil.example")], "ORIGIN_REJECTED"),
    ],
)
def test_rebinding_and_origins_rejected_before_auth(tmp_path, headers, code):
    world = make_world(tmp_path)

    def forbidden(_secret):
        pytest.fail("authentication ran before host/origin admission")

    world.core = replace(world.core, authenticator=forbidden)
    with world.client() as client:
        response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == code
    assert response.headers["Content-Type"] == "application/problem+json"
    assert response.headers["SKM-Api-Version"] == "1.0"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "[::1]:8765"])
def test_loopback_hosts_are_derived(tmp_path, host):
    with make_world(tmp_path).client() as client:
        assert client.get("/health/live", headers={"Host": host}).status_code == 200


def test_cors_preflight_and_errors(tmp_path):
    settings = {"api.cors.origins": ["https://web.example"]}
    with make_world(tmp_path).client(settings=settings) as client:
        response = client.options(
            "/api/v1/me", headers={"Origin": "https://web.example", "Access-Control-Request-Method": "POST"}
        )
        assert response.status_code == 204
        assert response.headers["Access-Control-Allow-Origin"] == "https://web.example"
        assert response.headers["Access-Control-Max-Age"] == "600"
        assert "SKM-Client-Version" in response.headers["Access-Control-Allow-Headers"]
        assert "SKM-Expected-Digest" in response.headers["Access-Control-Allow-Headers"]
        response = client.get("/api/v1/me", headers={"Origin": "https://web.example"})
        assert response.status_code == 401
        assert response.headers["Access-Control-Allow-Origin"] == "https://web.example"
        assert "Origin" in response.headers["Vary"]
        assert "Idempotency-Replayed" in response.headers["Access-Control-Expose-Headers"]
        same = client.get("/health/live", headers={"Origin": BASE})
        assert "Access-Control-Allow-Origin" not in same.headers


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic abc"},
        {"Cookie": "token=anything"},
        {"Authorization": "Bearer invalid"},
        [("Authorization", "Bearer a"), ("Authorization", "Bearer b")],
    ],
)
def test_bearer_required_and_cookies_ignored(tmp_path, headers):
    with make_world(tmp_path).client() as client:
        result = client.get("/api/v1/me", headers=headers)
    assert result.status_code == 401
    assert result.json()["code"] == "UNAUTHENTICATED"
    assert result.headers["WWW-Authenticate"] == "Bearer"


def test_real_token_revocation_and_denied_audit(tmp_path):
    world = make_world(tmp_path)
    with world.client() as client:
        actor = world.core.authenticate(world.secret)
        narrowed = cast(
            "Any",
            world.core.bus.dispatch(
                CreateToken(name="narrow", permissions=("token.own",)), actor=actor, meta=world.meta()
            ),
        )
        denied = client.get(
            "/api/v1/admin/migrations", headers={"Authorization": f"Bearer {narrowed.secret}"}
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "FORBIDDEN"
        assert any(record.decision == "denied" for record in world.audits)
        world.core.bus.dispatch(RevokeToken(token_id=narrowed.token_id), actor=actor, meta=world.meta())
        revoked = client.get("/api/v1/me", headers={"Authorization": f"Bearer {narrowed.secret}"})
        assert revoked.status_code == 401
        assert narrowed.secret not in revoked.text


@pytest.mark.parametrize(("method", "media"), [("POST", "text/plain"), ("PATCH", "application/json")])
def test_content_type_before_version_and_auth(tmp_path, method, media):
    with make_world(tmp_path).client() as client:
        result = client.request(
            method,
            "/api/v1/tokens",
            content=b"{}",
            headers={"Content-Type": media, "SKM-Client-Version": "1.0.0"},
        )
    assert result.status_code == 415
    assert result.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_error_secrets_and_internal_details_are_hidden(tmp_path):
    world = make_world(tmp_path)
    secret = "environment-secret-do-not-leak"
    redactor = Redactor()
    redactor.register_secret(secret)

    async def failure(request: Request):
        if request.query_params.get("internal"):
            raise RuntimeError(secret)
        raise error_for(
            ErrorCode.BACKEND_UNAVAILABLE,
            f"backend {secret} {world.secret}",
            details={"password": secret, "credential": world.secret},
            retryable=True,
        )

    with world.client(routes=[Route("/api/v1/failure", failure)], redactor=redactor) as client:
        result = client.get("/api/v1/failure", headers=world.headers)
        assert result.status_code == 503
        assert result.headers["Retry-After"] == "2"
        assert secret not in result.text
        assert world.secret not in result.text
        result = client.get("/api/v1/failure?internal=1", headers=world.headers)
        assert result.status_code == 500
        assert result.json()["details"] == {}
        assert secret not in result.text


@pytest.mark.parametrize("bearer", ["UNAUTHENTICATED", "SCHEMA_INVALID"])
def test_untrusted_bearer_cannot_poison_redactor_or_problem_fields(tmp_path, bearer):
    world = make_world(tmp_path)
    # Without issuer patterns only a registered value is masked, so a masked secret proves poisoning.
    base = Redactor(patterns=())
    with world.client(redactor=base) as client:
        response = client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {bearer}", "X-Request-Id": bearer}
        )
        assert response.status_code == 401
        problem = response.json()
        assert not world.core.schemas.validate("urn:skm:api:problem:v1", problem)
        assert {
            key: problem[key]
            for key in ("type", "title", "status", "code", "category", "retryable", "request_id", "instance")
        } == {
            "type": "urn:skm:error:UNAUTHENTICATED",
            "title": "Unauthenticated",
            "status": 401,
            "code": "UNAUTHENTICATED",
            "category": "unauthenticated",
            "retryable": False,
            "request_id": bearer,
            "instance": "/api/v1/me",
        }
        invalid = client.get(
            "/api/v1/me",
            headers={"Authorization": "Bearer SCHEMA_INVALID", "SKM-Client-Version": "invalid/version"},
        )
        assert invalid.json()["code"] == "SCHEMA_INVALID"
        assert not world.core.schemas.validate("urn:skm:api:problem:v1", invalid.json())
        following = client.get("/api/v1/me")
        assert following.status_code == 401
        assert following.json()["code"] == "UNAUTHENTICATED"
        assert not world.core.schemas.validate("urn:skm:api:problem:v1", following.json())
    assert base.text(bearer) == bearer
    assert base.text(world.secret) == world.secret


def test_body_limit_rejects_stream_before_auth_and_handler(tmp_path):
    world = make_world(tmp_path)
    with world.client(settings={"api.limits.max_body_bytes": 4}) as client:
        result = client.post(
            "/api/v1/tokens", content=iter([b"123", b"456"]), headers={"Content-Type": "application/json"}
        )
        assert (result.status_code, result.json()["code"]) == (413, "PAYLOAD_TOO_LARGE")
        result = client.post("/api/v1/tokens", content=b"12345", headers={"Content-Type": "text/plain"})
        assert result.status_code == 413


def test_body_header_oversize_is_rejected_without_receiving(tmp_path):
    world = make_world(tmp_path)
    api = world.client(settings={"api.limits.max_body_bytes": 4}).app
    messages = []

    async def receive():
        pytest.fail("oversized Content-Length must fail before receiving")

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/tokens",
        "raw_path": b"/api/v1/tokens",
        "query_string": b"",
        "headers": [(b"host", b"127.0.0.1:8765"), (b"content-length", b"5")],
        "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 1),
    }

    async def exercise():
        await api(scope, receive, send)

    asyncio.run(exercise())
    assert messages[0]["status"] == 413


def test_route_limit_and_blob_length_media_policy(tmp_path):
    world = make_world(tmp_path)

    async def echo(request: Request):
        return JSONResponse({"length": len(await request.body())})

    policy = BodyPolicy(
        "POST", "/api/v1/upload", "artifacts.upload.max_bytes", "application/octet-stream", True
    )
    with world.client(
        routes=[Route("/api/v1/upload", echo, methods=["POST"])],
        body_policies=[policy],
        settings={"api.limits.max_body_bytes": 2, "artifacts.upload.max_bytes": 8},
    ) as client:
        result = client.post(
            "/api/v1/upload",
            content=b"123456",
            headers={**world.headers, "Content-Type": "application/octet-stream"},
        )
        assert result.json() == {"length": 6}
        result = client.post(
            "/api/v1/upload", content=iter([b"1"]), headers={"Content-Type": "application/octet-stream"}
        )
        assert result.status_code == 411
