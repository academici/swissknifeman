from __future__ import annotations

import base64
import io
import json
import os
import socket
import sys
import tomllib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from email.message import Message
from pathlib import Path
from queue import SimpleQueue
from typing import override
from urllib.request import BaseHandler, HTTPSHandler, Request, build_opener
from urllib.response import addinfourl

import pytest

from integration.runtimes.test_codex_argv import _make_request
from integration.runtimes.test_grok_argv import _make_request as _make_grok_request
from skm.adapters.runtimes._cli_session import proxy_bridge
from skm.adapters.runtimes._cli_session.launch import PROXY_ENV_KEYS, apply_proxy_env
from skm.adapters.runtimes._cli_session.probe import ProbeCacheKey
from skm.adapters.runtimes._cli_session.proxy_bridge import LocalProxyBridge, ProxyEndpoint
from skm.adapters.runtimes.codex.launch import build_launch_plan
from skm.adapters.runtimes.codex.permissions import render_codex_config_toml
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.adapters.runtimes.grok.detect import ProbedBinary as GrokBinary
from skm.adapters.runtimes.grok.runtime import GrokRuntime
from skm.bootstrap import provider_accounts
from skm.entrypoints.cli.main import main
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.modules.runtimes.domain.request import McpServerSpec, ProcessOwnership, SecretStr
from skm.platform.fs.atomic_write import atomic_write

_CANARY = "p01-proxy-canary@example"


@pytest.fixture
def connect_bridge(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], socket.socket]:
    """Exercise the actual server and handler over socketpairs if listeners are denied."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_socket:
            test_socket.bind(("127.0.0.1", 0))
    except PermissionError:
        listeners: dict[int, tuple[socket.socket, SimpleQueue[socket.socket]]] = {}

        def sendall(peer: socket.socket, data: bytes) -> None:
            assert peer.family == socket.AF_UNIX
            # The runner permits byte-stream writes on socketpair descriptors, but blocks sendto.
            offset = 0
            while offset < len(data):
                offset += os.write(peer.fileno(), data[offset:])

        monkeypatch.setattr(socket.socket, "sendall", sendall)

        def bind(server: proxy_bridge._BridgeServer) -> None:
            assert server.server_address == ("127.0.0.1", 0)
            port = 10_000 + len(listeners)
            listener, signal = socket.socketpair()
            server.socket.close()
            server.socket = listener
            listeners[port] = signal, SimpleQueue()
            server.server_address = ("127.0.0.1", port)

        def accept(server: proxy_bridge._BridgeServer) -> tuple[socket.socket, tuple[str, int]]:
            server.socket.recv(1)
            return listeners[server.server_address[1]][1].get_nowait(), ("127.0.0.1", 0)

        def close(server: proxy_bridge._BridgeServer) -> None:
            server.socket.close()
            peer = listeners.pop(server.server_address[1], None)
            if peer is not None:
                signal, pending = peer
                signal.close()
                while not pending.empty():
                    pending.get_nowait().close()

        monkeypatch.setattr(proxy_bridge._BridgeServer, "address_family", socket.AF_UNIX)
        monkeypatch.setattr(proxy_bridge._BridgeServer, "server_bind", bind)
        monkeypatch.setattr(proxy_bridge._BridgeServer, "server_activate", lambda self: None)
        monkeypatch.setattr(proxy_bridge._BridgeServer, "get_request", accept)
        monkeypatch.setattr(proxy_bridge._BridgeServer, "server_close", close)

        def pair_connect(url: str) -> socket.socket:
            client, server = socket.socketpair()
            client.settimeout(2)
            signal, pending = listeners[int(url.rsplit(":", 1)[1])]
            pending.put(server)
            signal.sendall(b"x")
            return client

        return pair_connect

    def tcp_connect(url: str) -> socket.socket:
        return socket.create_connection(("127.0.0.1", int(url.rsplit(":", 1)[1])), timeout=2)

    return tcp_connect


def _headers(client: socket.socket) -> bytes:
    result = bytearray()
    while not result.endswith(b"\r\n\r\n"):
        chunk = client.recv(1)
        assert chunk
        result.extend(chunk)
    return bytes(result)


def _through(connect: Callable[[str], socket.socket], bridge: LocalProxyBridge, request: bytes) -> bytes:
    assert bridge.url is not None
    with connect(bridge.url) as client:
        client.sendall(request)
        return _headers(client)


@pytest.mark.parametrize("encoded", [True, False])
def test_connect_http_proxy_and_scrub_final_environment(
    connect_bridge: Callable[[str], socket.socket], monkeypatch: pytest.MonkeyPatch, encoded: bool
) -> None:
    password = _CANARY.replace("@", "%40") if encoded else _CANARY
    endpoint = ProxyEndpoint.parse(f"http://user:{password}@127.0.0.1:12345")
    assert endpoint is not None
    assert _CANARY not in repr(endpoint)
    bridge_side, upstream = socket.socketpair()
    upstream.settimeout(2)

    def serve_upstream() -> None:
        with upstream:
            received = _headers(upstream)
            basic = base64.b64encode(f"user:{_CANARY}".encode())
            assert received.startswith(b"CONNECT allowed.test:443 HTTP/1.1\r\n")
            assert b"Proxy-Authorization: Basic " + basic in received
            assert b"client-secret" not in received
            upstream.sendall(b"HTTP/1.1 200 Connected\r\n\r\n")
            assert upstream.recv(4) == b"ping"
            upstream.sendall(b"pong")

    def dial(host: str, port: int) -> socket.socket:
        assert (host, port) == ("127.0.0.1", 12345)
        return bridge_side

    monkeypatch.setattr(proxy_bridge, "_dial", dial)
    with (
        ThreadPoolExecutor(max_workers=1) as worker,
        LocalProxyBridge(endpoint, allowed_hosts=frozenset({"allowed.test:443"})) as bridge,
    ):
        env = dict.fromkeys((*PROXY_ENV_KEYS, "HtTp_PrOxY"), _CANARY)
        apply_proxy_env(env, bridge)
        assert env == {
            "HTTP_PROXY": bridge.url,
            "HTTPS_PROXY": bridge.url,
            "http_proxy": bridge.url,
            "https_proxy": bridge.url,
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "no_proxy": "127.0.0.1,localhost,::1",
        }
        for blocked in (
            b"CONNECT denied.test:443 HTTP/1.1\r\n\r\n",
            b"CONNECT allowed.test:80 HTTP/1.1\r\n\r\n",
            b"GET http://denied.test HTTP/1.1\r\nHost: allowed.test\r\n\r\n",
        ):
            assert _through(connect_bridge, bridge, blocked).startswith(b"HTTP/1.1 403 Forbidden")
        served = worker.submit(serve_upstream)
        assert bridge.url is not None
        with connect_bridge(bridge.url) as client:
            client.sendall(b"CONNECT allowed.test:443 HTTP/1.1\r\nProxy-Authorization: client-secret\r\n\r\n")
            assert _headers(client).startswith(b"HTTP/1.1 200")
            client.sendall(b"ping")
            assert client.recv(4) == b"pong"
        served.result(timeout=3)
    assert bridge.url is None
    apply_proxy_env(env)
    assert not env


@pytest.mark.parametrize(
    ("scheme", "host", "address"),
    [
        ("socks5", "127.0.0.1", b"\x01\x7f\x00\x00\x01"),
        ("socks5h", "allowed.test", b"\x03\x0callowed.test"),
    ],
)
def test_socks5_authentication_and_http_requests(
    connect_bridge: Callable[[str], socket.socket],
    monkeypatch: pytest.MonkeyPatch,
    scheme: str,
    host: str,
    address: bytes,
) -> None:
    endpoint = ProxyEndpoint.parse(f"{scheme}://user:{_CANARY}@127.0.0.1:12345")
    proxy, upstream = socket.socketpair()
    upstream.settimeout(2)
    monkeypatch.setattr(proxy_bridge, "_dial", lambda host, port: proxy)

    def serve_upstream() -> None:
        def read(size: int) -> bytes:
            return proxy_bridge._recv_exact(upstream, size)

        with upstream:
            assert read(3) == b"\x05\x01\x02"
            upstream.sendall(b"\x05\x02")
            password = _CANARY.encode()
            assert read(7 + len(password)) == b"\x01\x04user" + bytes((len(password),)) + password
            upstream.sendall(b"\x01\x00")
            assert read(5 + len(address)) == b"\x05\x01\x00" + address + b"\x00\x50"
            upstream.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            headers = _headers(upstream)
            assert headers.startswith(b"POST /path?x=1 HTTP/1.1\r\n")
            assert f"Host: {host}:80\r\n".encode() in headers
            assert b"unexpected.test" not in headers
            assert b"Proxy-Authorization" not in headers
            assert read(2) == b"ok"
            upstream.sendall(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")

    with (
        ThreadPoolExecutor(max_workers=1) as worker,
        LocalProxyBridge(endpoint, allowed_hosts=frozenset({host})) as bridge,
    ):
        served = worker.submit(serve_upstream)
        result = _through(
            connect_bridge,
            bridge,
            f"POST http://{host}/path?x=1 HTTP/1.1\r\nHost: unexpected.test\r\n"
            "Proxy-Authorization: client-secret\r\nContent-Length: 2\r\n\r\nok".encode(),
        )
        assert result.startswith(b"HTTP/1.1 204")
        served.result(timeout=3)


def test_bridge_rejects_a_connect_loop(connect_bridge: Callable[[str], socket.socket]) -> None:
    with LocalProxyBridge(ProxyEndpoint.parse("http://upstream.example.test")) as bridge:
        assert bridge.url is not None
        authority = bridge.url.removeprefix("http://")
        request = f"CONNECT {authority} HTTP/1.1\r\n\r\n".encode()
        assert _through(connect_bridge, bridge, request).startswith(b"HTTP/1.1 502 Bad Gateway")


def test_codex_allowlist_needs_matching_active_bridge_and_uses_only_its_url(
    tmp_path: Path, connect_bridge: Callable[[str], socket.socket]
) -> None:
    request = _make_request(
        tmp_path,
        network_mode="allowlist",
        network_hosts=("api.example.test:443",),
        mcp_servers=(McpServerSpec("local", ("/bin/true",), {"ALL_PROXY": _CANARY}, ()),),
        extra_env={"HTTPS_PROXY": _CANARY, "HTTP_PROXY": _CANARY, "OPENAI_API_KEY": "local-key"},
    )
    endpoint = ProxyEndpoint.parse(f"http://user:{_CANARY}@127.0.0.1:12345")
    bridge = LocalProxyBridge(endpoint, allowed_hosts=frozenset(request.permissions.network.hosts))
    with pytest.raises(CapabilityUnavailable, match="active bridge"):
        render_codex_config_toml(request)
    with pytest.raises(CapabilityUnavailable, match="active bridge"):
        render_codex_config_toml(request, proxy_bridge=bridge)
    with (
        LocalProxyBridge(endpoint, allowed_hosts=frozenset({"wrong.example.test"})) as wrong,
        pytest.raises(CapabilityUnavailable, match="same hosts"),
    ):
        render_codex_config_toml(request, proxy_bridge=wrong)

    with bridge:
        plan = build_launch_plan(
            request,
            binary_path="/bin/true",
            step_dir=tmp_path / "step",
            ownership=ProcessOwnership(request.process_owner, "pgroup_best_effort", "test"),
            host_environ={"ALL_PROXY": _CANARY},
            copy_credentials=False,
            proxy_bridge=bridge,
        )
        content = plan.permissions.config_path.read_text(encoding="utf-8")
        config = tomllib.loads(content)
        assert config["sandbox_workspace_write"]["network_access"] is True
        assert config["features"]["network_proxy"] == {
            "enabled": True,
            "allow_upstream_proxy": True,
            "allow_local_binding": False,
            "enable_socks5": False,
            "domains": {"api.example.test": "allow"},
        }
        assert "--strict-config" in plan.command.argv
        env = config["mcp_servers"]["local"]["env"]
        assert env["HTTPS_PROXY"] == plan.command.env["HTTPS_PROXY"] == bridge.url
        assert "ALL_PROXY" not in env
        assert any(arg.startswith("shell_environment_policy.set.HTTPS_PROXY=") for arg in plan.command.argv)
        assert all(
            _CANARY not in value for value in (content, *plan.command.argv, *plan.command.env.values())
        )


def test_required_egress_proxy_refuses_a_network_disabled_request(tmp_path: Path) -> None:
    runtime = CodexRuntime(
        binary=str(tmp_path / "missing-codex"),
        egress_proxy=ProxyEndpoint.parse(f"http://user:{_CANARY}@127.0.0.1:12345"),
    )

    with pytest.raises(CapabilityUnavailable, match="configured egress proxy requires network access") as e:
        runtime.start(_make_request(tmp_path, network_mode="none"))

    assert _CANARY not in str(e.value)


def test_grok_scrubs_all_proxy_keys_from_the_child_environment(tmp_path: Path) -> None:
    request = replace(
        _make_grok_request(tmp_path),
        env_allowlist=tuple(PROXY_ENV_KEYS),
        extra_env={"HTTP_PROXY": _CANARY, "GROK_TEST_VAR": "preserved"},
        secret_env={"https_proxy": SecretStr(_CANARY)},
    )
    runtime = GrokRuntime(environ=dict.fromkeys(PROXY_ENV_KEYS, _CANARY))
    digest = "sha256:" + "0" * 64
    binary = GrokBinary(
        ProbeCacheKey("/bin/true", digest, "1.0.0", "test", "1", digest),
        "/bin/true",
        "1.0.0",
        frozenset(),
        (),
    )

    command, _ = runtime._build_launch(
        request,
        binary,
        step_dir=tmp_path / "step",
        ownership=ProcessOwnership(request.process_owner, "pgroup_best_effort", "test"),
    )

    assert PROXY_ENV_KEYS.isdisjoint(command.env)
    assert _CANARY not in command.env.values()
    assert command.env["GROK_TEST_VAR"] == "preserved"


def _registry(home: Path) -> Path:
    path = home / ".config/skm/provider-pool.toml"
    atomic_write(
        path,
        (
            'schema_version = 2\n[groups]\nprimary = "codex-model"\n'
            '[slots.account]\nruntime_id = "codex"\ntransport = "cli_subprocess"\ntier = 1\n'
            f'egress_proxy = "socks5h://user:{_CANARY}@127.0.0.1:12345"\n'
            'write_back = false\nsymlink_host_files = [".ssh"]\n'
            'models = [{name = "codex-model", is_compat = false}]\n'
            '[slots.account.quota_urls]\nprimary = "https://quota.example.test/remaining"\n'
            '[slots.api]\nruntime_id = "openrouter"\ntransport = "http_api"\n'
            'provider = "openrouter"\nbase_url = "https://api.example.test/"\n'
            'api_key_ref = "secret://env/OPENROUTER_KEY"\negress_proxy = "direct"\n'
            "[slots.api.provider_routing]\nallow_fallbacks = true\nzdr = true\n"
            '[slots.oauth]\nruntime_id = "claude_code"\ntransport = "oauth_gateway"\n'
            'provider = "anthropic"\nbase_url = "https://api.example.test/"\n'
            'token_file = "~/tokens/claude.token"\n'
        ).encode(),
        mode=0o600,
        private=True,
    )
    return path


def test_proxy_registry_refuses_a_symlink_to_an_owner_only_file(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    symlink = tmp_path / "registry.toml"
    symlink.symlink_to(registry)
    assert provider_accounts.load_provider_accounts(registry, {}, tmp_path).slots

    with pytest.raises(ValidationFailed, match="cannot read provider pool registry"):
        provider_accounts.load_provider_accounts(symlink, {}, tmp_path)


def test_account_registry_doctor_active_probe_and_exec_without_leakage(
    tmp_path: Path,
    connect_bridge: Callable[[str], socket.socket],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    host, work = tmp_path / "host", tmp_path / "checkout"
    work.mkdir()
    (host / ".ssh").mkdir(parents=True)
    registry = _registry(host)
    environ = {"HOME": str(host), "PATH": "/bin:/usr/bin", "NO_PROXY": "*", "HTTP_PROXY": _CANARY}
    registry.chmod(0o644)
    with pytest.raises(ValidationFailed, match="0600") as error:
        provider_accounts.load_provider_accounts(registry, environ, host)
    assert _CANARY not in repr(error.value)
    assert error.value.__cause__ is None
    registry.chmod(0o600)

    seen: list[str] = []

    class QuotaFetcher:
        def __init__(self, *, handlers: tuple[BaseHandler, ...]) -> None:
            self.handlers = handlers

        def fetch(self, url: str, *, max_bytes: int, timeout_seconds: int) -> bytes:
            class Response(addinfourl):
                msg = "OK"

            class Handler(HTTPSHandler):
                @override
                def https_open(self, request: Request) -> addinfourl:
                    seen.append(request.host)
                    return Response(io.BytesIO(b'{"remaining":7}'), Message(), request.full_url, 200)

            opener = build_opener(*self.handlers, Handler())
            with opener.open(url, timeout=timeout_seconds) as response:
                return response.read(max_bytes)

    monkeypatch.setattr(provider_accounts, "HttpUpstreamFetcher", QuotaFetcher)
    monkeypatch.setenv("NO_PROXY", "*")
    arguments = ["--registry", str(registry)]

    def run(command: list[str]) -> str:
        out, err = io.StringIO(), io.StringIO()
        assert main(["--json", *command], environ=environ, stdout=out, stderr=err) == 0
        content = out.getvalue()
        assert _CANARY not in content + err.getvalue()
        return content

    listing = json.loads(run(["accounts", *arguments]))["result"]
    assert {entry["transport"] for entry in listing} == {"cli_subprocess", "http_api", "oauth_gateway"}
    assert listing[0] == {
        "runtime_id": "codex",
        "slot_id": "account",
        "host_dispatches_tools": False,
        "tier": 1,
        "transport": "cli_subprocess",
        "models": [{"name": "codex-model", "is_compat": False}],
        "has_egress_proxy": True,
        "proxy_scheme": "socks5h",
    }
    doctor = json.loads(run(["accounts", "doctor", "account", *arguments]))["result"]
    assert any(".ssh" in warning for warning in doctor["warnings"])
    probed = json.loads(run(["providers", "probe", *arguments]))["result"]
    assert probed[0]["remaining"] == 7
    assert len(seen) == 1
    assert seen[0].startswith("127.0.0.1:")
    accounts = provider_accounts.load_provider_accounts(registry, environ, host)
    pool = accounts.pool()
    lease = pool.acquire("account", "test", ttl_seconds=60)
    assert lease is not None
    assert json.loads(run(["accounts", "active", *arguments]))["result"] == [listing[0]]
    assert pool.release(lease)

    status = main(
        [
            "accounts",
            *arguments,
            "exec",
            "account",
            "--cwd",
            str(work),
            "--",
            sys.executable,
            "-c",
            "import json, os, sys; print(json.dumps([os.getcwd(), os.environ['HOME'], "
            "os.environ['HTTPS_PROXY'], sys.argv[1:]])); sys.exit(17)",
            "--literal-argument",
        ],
        environ=environ,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert status == 17
    out, err = capfd.readouterr()
    assert _CANARY not in out + err
    cwd, home, proxy, argv = json.loads(out)
    assert cwd == str(work)
    assert home == str(lease.client_home)
    assert proxy.startswith("http://127.0.0.1:")
    assert argv == ["--literal-argument"]
    assert not pool.active_slots()


def test_invalid_proxy_inputs_do_not_reappear_in_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ValidationFailed) as failure:
        ProxyEndpoint.parse(f"http://user:{_CANARY}@localhost:bad")
    assert _CANARY not in repr(failure.value) + str(failure.value) + caplog.text
    assert failure.value.__cause__ is None
