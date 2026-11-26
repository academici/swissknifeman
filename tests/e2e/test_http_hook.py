"""Installed hook authentication follows its verified HTTPS origin and scoped credential."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import override
from uuid import UUID

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from e2e.test_instance_profiles import _Databases
from e2e.test_instance_profiles import databases as databases
from e2e.test_p04_workspace import Sandbox, _checkout_hub, _CheckoutTransport, _installed_cli
from e2e.test_projected_hooks import assert_native, install_hook_token
from fixtures.hooks.subprocess.harness import (
    HOOK,
    Invocation,
    installed_daemon,
    native_payload,
    runtime_environment,
)
from skm.bootstrap.hook import hook_context
from skm.kernel.ids import ProjectId
from skm.modules.integrations.host.observe import resolve_checkout_for_mount
from skm.platform.config.sources.bootstrap import ProfileCatalog
from support.git_repo import init_git_repo
from support.http_server import loopback_certificate, loopback_server

pytestmark = [pytest.mark.e2e, pytest.mark.pg]


@dataclass
class _HookTransport(_CheckoutTransport):
    capture: bool = False
    delay: bool = False
    policy_requested: Event = field(default_factory=Event)
    auth_headers: list[bytes] = field(default_factory=list)

    @override
    def wrap(self, app: ASGIApp) -> ASGIApp:
        async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
            if self.capture and scope["type"] == "http":
                headers = dict(scope["headers"])
                self.auth_headers.append(headers.get(b"authorization", b""))
                if scope["path"].endswith("/integrations/hook-policy"):
                    self.policy_requested.set()
                    while self.delay:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        await asyncio.sleep(0.02)
            await app(scope, receive, send)

        return wrapped


def test_installed_https_hook_pin_restricted_bearer_and_deadline(
    tmp_path: Path, databases: _Databases
) -> None:
    hub_root, client_root = tmp_path / "hub", tmp_path / "client"
    hub_root.mkdir()
    client_root.mkdir()
    hub = Sandbox(hub_root, databases.projects[0])
    box = Sandbox(client_root, "", databases.machine_env)
    env = box.env()
    del env["SKM_DATABASE_URL"]
    env.pop("PYTHONPATH", None)
    env["PATH"] = str(HOOK.parent) + os.pathsep + env["PATH"]
    repo = init_git_repo(tmp_path / "checkout")
    repo.commit_file("README.md", "native HTTP\n", message="Init")
    repo.add_remote("origin", "https://repo.example/team/remote-native.git")
    transport = _HookTransport()
    attacked = Event()

    async def trap(request: Request) -> Response:
        attacked.set()
        return Response(status_code=503)

    tls = loopback_certificate(tmp_path / "trap-certs")
    with (
        _checkout_hub(hub, transport) as (endpoint, ca, owner),
        loopback_server(lambda _: Starlette(routes=[Route("/{rest:path}", trap)]), tls=tls) as alternate,
    ):
        env["A03_OWNER_TOKEN"] = owner
        _installed_cli(
            env,
            client_root,
            "instance",
            "add",
            "trusted",
            "--mode",
            "http",
            "--api-endpoint",
            endpoint + "/api/v1",
            "--ca-bundle",
            str(ca),
            "--credential",
            "secret://env/A03_OWNER_TOKEN",
        )
        env["SKM_INSTANCE"] = "trusted"
        _installed_cli(env, client_root, "host", "register", "native-http")
        project = _installed_cli(env, client_root, "project", "create", "remote", "--workspace", "personal")
        _installed_cli(env, client_root, "use", "personal/remote")
        _installed_cli(env, repo.path, "repo", "bind", "--register", "--write-marker", "--yes")
        configuration = ProfileCatalog.read(None, env, box.home).config("trusted")
        token_path = configuration.state_dir / "secrets/hook.token"
        install_hook_token(env, repo.path, token_path, project["workspace_id"])
        hook_token = token_path.read_text().strip()
        del env["A03_OWNER_TOKEN"]
        env.update(SKM_API_TOKEN=owner, SKM_API_ENDPOINT=alternate + "/api/v1", SKM_API_CA_BUNDLE=str(tls[0]))
        assert (
            ProfileCatalog.read(None, env, box.home).config("trusted").api_endpoint == alternate + "/api/v1"
        )
        transport.capture = True
        with runtime_environment(env) as runtime:
            with hook_context(runtime) as context:
                bound = resolve_checkout_for_mount(context, ProjectId(UUID(project["project_id"])), "main")
                assert bound.local_locator == str(repo.path)
            invocation = _call(project["project_id"], repo.path, runtime)
            with installed_daemon(runtime, cwd=repo.path):
                allowed, _ = invocation.execute()
                assert_native(allowed, "cursor", denied=False)
                assert json.loads(allowed.stdout)["permission"] == "allow"
                assert transport.policy_requested.is_set()
                assert transport.auth_headers
                assert set(transport.auth_headers) == {b"Bearer " + hook_token.encode()}
                assert not attacked.is_set()
            assert hook_token not in allowed.stdout + allowed.stderr
            assert owner not in allowed.stdout + allowed.stderr
            _assert_delayed_http_denies(transport, invocation)

    with runtime_environment(env) as runtime, installed_daemon(runtime, cwd=repo.path):
        unavailable, elapsed = _call(project["project_id"], repo.path, runtime).execute()
        assert_native(unavailable, "cursor", denied=True)
        assert "HOOK_BACKEND_UNAVAILABLE" in unavailable.stdout
        assert elapsed < 2800


def _call(project: str, root: Path, runtime: dict[str, str]) -> Invocation:
    event = "beforeShellExecution"
    return Invocation(
        [
            "skm-hook",
            event,
            "--target",
            "cursor",
            "--surface",
            "lifecycle.git_guardrails",
            "--project",
            project,
        ],
        native_payload("cursor", event, root, "git status"),
        runtime,
        root,
    )


def _assert_delayed_http_denies(transport: _HookTransport, invocation: Invocation) -> None:
    transport.policy_requested.clear()
    transport.delay = True
    runtime = {**invocation.environ, "SKM__INTEGRATIONS__HOOK__TIMEOUT_MS": "1400"}
    delayed = _call(invocation.argv[-1], invocation.cwd, runtime)
    try:
        with installed_daemon(runtime, cwd=invocation.cwd):
            result, elapsed = delayed.execute()
        assert transport.policy_requested.is_set()
        assert_native(result, "cursor", denied=True)
        assert "HOOK_BACKEND_UNAVAILABLE" in result.stdout
        assert 1350 <= elapsed < 2100, elapsed
    finally:
        transport.delay = False
