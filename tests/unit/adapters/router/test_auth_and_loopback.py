"""The listener binds literally to loopback and roles stay on their own surfaces."""

from contextlib import ExitStack
from pathlib import Path
from typing import Any

import pytest

from skm.bootstrap.router import RouterState, validate_bind
from skm.kernel.errors import ValidationFailed

from .conftest import AUTH, MANAGEMENT, asgi_client, slot_toml


@pytest.mark.parametrize("host", ["localhost", "127.0.0.2", "0.0.0.0", "::1", "127.0.0.1 "])
def test_nonliteral_loopback_is_rejected(host: str, router_factory: Any) -> None:
    with pytest.raises(ValueError, match="literal"):
        validate_bind(host, 8317)
    with pytest.raises(ValidationFailed, match="invalid router configuration"):
        router_factory(overrides=f'bind = "{host}"\n')


@pytest.mark.parametrize("port", [0, 65536, True])
def test_invalid_ports_are_rejected(port: int) -> None:
    with pytest.raises(ValueError, match="port"):
        validate_bind("127.0.0.1", port)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        (method, prefix + path)
        for prefix in ("/v1", "")
        for method, path in (
            ("POST", "/messages"),
            ("POST", "/messages/count_tokens"),
            ("POST", "/chat/completions"),
            ("POST", "/responses"),
            ("GET", "/models"),
        )
    ],
)
def test_inference_role_matrix(method: str, path: str, router_factory: Any) -> None:
    state: RouterState = router_factory()
    assert state.binding == ("127.0.0.1", 8317)
    with asgi_client(state) as client:
        assert client.request(method, path).status_code == 401
        assert client.request(method, path, headers={"x-api-key": "wrong"}).status_code == 401
        assert client.request(method, path, headers=MANAGEMENT).status_code == 403
        # POST bodies are deliberately malformed to verify authorization before body parsing.
        assert client.request(method, path, headers=AUTH).status_code == (200 if method == "GET" else 400)


@pytest.mark.parametrize(("method", "leaf"), [("GET", "status"), ("GET", "cooldowns"), ("POST", "reload")])
def test_management_role_matrix(method: str, leaf: str, router_factory: Any) -> None:
    with asgi_client(router_factory()) as client:
        path = "/admin/" + leaf
        assert client.request(method, path).status_code == 401
        assert client.request(method, path, headers=AUTH).status_code == 403
        assert client.request(method, path, headers=MANAGEMENT).status_code == 200


def test_forged_hop_cannot_bypass_auth_and_internal_key_is_not_admin(router_factory: Any) -> None:
    state: RouterState = router_factory()
    with ExitStack() as lease, asgi_client(state) as client:
        issued = state.hop.issue("one", lease)
        marker, signature = issued["ANTHROPIC_CUSTOM_HEADERS"].splitlines()
        headers = dict([item.split(": ", 1) for item in (marker, signature)])
        headers["x-api-key"] = issued["ANTHROPIC_API_KEY"]
        assert client.get("/models", headers={**AUTH, "X-SKM-Internal-Hop": "1"}).status_code == 401
        assert client.get("/models", headers=headers).status_code == 200
        assert client.get("/admin/status", headers=headers).status_code == 403
        lease.close()
        assert client.get("/models", headers=headers).status_code == 401


def test_invalid_reload_keeps_models_and_credentials(router_factory: Any) -> None:
    state: RouterState = router_factory()
    with asgi_client(state) as client:
        state.path.write_text("[router\n", encoding="utf-8")
        assert client.post("/admin/reload", headers=MANAGEMENT).status_code == 400
        assert client.get("/admin/status", headers=MANAGEMENT).json()["generation"] == 1
        assert [item["id"] for item in client.get("/models", headers=AUTH).json()["data"]] == ["model"]


@pytest.mark.parametrize(
    ("client_key", "management_key", "literal"),
    [
        ("client-one", "secret://env/ADMIN_KEY", True),
        ("secret://env/CLIENT_KEY", "router-admin", True),
        ("secret://env/CLIENT_KEY", "secret://env/ADMIN_KEY", False),
    ],
    ids=["literal-client", "literal-management", "references-only"],
)
def test_config_with_literal_keys_requires_owner_only_permissions(
    tmp_path: Path, client_key: str, management_key: str, literal: bool
) -> None:
    config = tmp_path / "provider-pool.toml"
    config.touch(mode=0o600)
    config.write_text(
        f'schema_version = 2\n[router]\nclient_keys = {{one = "{client_key}"}}\n'
        f'management_key = "{management_key}"\n' + slot_toml(("remote", "anthropic", "m", 1)),
        encoding="utf-8",
    )
    env = {"CLIENT_KEY": "client-one", "ADMIN_KEY": "router-admin", "ROUTER_UPSTREAM_KEY": "provider-key"}
    with ExitStack() as cleanup:
        state = RouterState(config, tmp_path, env, tmp_path)
        cleanup.callback(state.close)
        config.chmod(0o644)
        if literal:
            with pytest.raises(ValidationFailed, match="invalid router configuration"):
                state.reload()
            with pytest.raises(ValidationFailed, match="invalid router configuration"):
                RouterState(config, tmp_path, env, tmp_path)
        else:
            assert state.reload() == 2

        config.chmod(0o600)
        link = tmp_path / "linked-pool.toml"
        link.symlink_to(config)
        with pytest.raises(ValidationFailed, match="invalid router configuration"):
            RouterState(link, tmp_path, env, tmp_path)


def test_internal_inference_bypasses_tier_one_cli(router_factory: Any, http_router: Any) -> None:
    import httpx

    from .conftest import upstream

    state: RouterState = router_factory(
        ("remote", "anthropic", "model", 2),
        extra="""
[slots.cli]
runtime_id = "claude_code"
transport = "cli_subprocess"
worker_mode = "hot_pool"
models = [{name = "model", is_compat = false}]
""",
    )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        assert request.headers.get("x-skm-internal-hop") is None
        assert request.headers.get("x-skm-internal-signature") is None
        return upstream(b'{"content":[{"type":"text","text":"backend"}]}')

    with ExitStack() as lease, http_router(state, handler) as client:
        keys = state.hop.issue("one", lease)
        headers = dict([header.split(": ", 1) for header in keys["ANTHROPIC_CUSTOM_HEADERS"].splitlines()])
        headers["x-api-key"] = keys["ANTHROPIC_API_KEY"]
        result = client.post("/v1/messages", headers=headers, json={"model": "model"})
        assert result.status_code == 200
        assert calls == ["remote.example"]
