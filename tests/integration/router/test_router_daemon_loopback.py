"""Exercise the installed CLI, a real TCP daemon and a TLS fake upstream."""

import json
import os
import shutil
import socket
import ssl
import stat
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import override

import httpx
import pytest

from skm.platform.process.identity import ProcessIdentity, is_same_process

pytestmark = pytest.mark.integration

CLIENT = {"authorization": "Bearer local-client"}
ADMIN = {"authorization": "Bearer local-admin"}


def _cert(tmp: Path) -> tuple[Path, Path]:
    cert, key = tmp / "localhost.pem", tmp / "localhost.key"
    openssl = shutil.which("openssl")
    assert openssl is not None
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-nodes",
            "-newkey",
            "rsa:2048",
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    return cert, key


def test_daemon_inference_disconnect_reload_and_verified_stop(tmp_path: Path) -> None:
    disconnected = Event()

    class Upstream(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        @override
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            assert self.path == "/v1/messages"
            assert self.headers["x-api-key"] == "remote-credential"
            request = json.loads(self.rfile.read(int(self.headers["content-length"])))
            if request.get("stream"):
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("transfer-encoding", "chunked")
                self.end_headers()
                chunk = (
                    b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"first"}}\n\n'
                )
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
                self.connection.settimeout(6)
                if self.rfile.read(1) == b"":
                    disconnected.set()
                self.close_connection = True
                return
            answer = b'{"content":[{"type":"text","text":"loopback upstream"}]}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(answer)))
            self.end_headers()
            self.wfile.write(answer)

    with ThreadingHTTPServer(("127.0.0.1", 0), Upstream) as upstream:
        cert, key = _cert(tmp_path)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, key)
        upstream.socket = tls.wrap_socket(upstream.socket, server_side=True)
        thread = Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        try:
            _exercise(tmp_path, upstream.server_port, cert, disconnected)
        finally:
            upstream.shutdown()
            thread.join(timeout=5)


def _exercise(tmp: Path, remote: int, cert: Path, disconnected: Event) -> None:
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]

    env = {
        **os.environ,
        "HOME": str(tmp),
        "XDG_STATE_HOME": str(tmp / "state"),
        "ROUTER_UPSTREAM_KEY": "remote-credential",
    }
    source = tmp / "provider-pool.toml"
    config = f"""
schema_version = 2
[router]
client_keys = {{local = "local-client"}}
management_key = "local-admin"
ca_file = "{cert}"

[slots.account]
runtime_id = "claude_code"
transport = "http_api"
provider = "anthropic"
base_url = "https://127.0.0.1:{remote}"
api_key_ref = "secret://env/ROUTER_UPSTREAM_KEY"
models = [{{name = "m", is_compat = false}}]
"""
    source.touch(mode=0o600)
    source.write_text(config, encoding="utf-8")

    def cli(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "skm.entrypoints.cli.main", "router", *args],
            env=env,
            text=True,
            capture_output=True,
            check=check,
            timeout=25,
        )

    started = cli("start", "--daemon", "--port", str(port), "--config", str(source), check=False)
    assert started.returncode == 0, started.stderr
    pid_file = tmp / "state" / "skm" / "router" / "router.pid"
    try:
        record = json.loads(pid_file.read_text(encoding="utf-8"))
        facts = ProcessIdentity(**record["identity"])
        status = json.loads(cli("status", "--json").stdout)["result"]
        assert status == {"status": "running", "host": "127.0.0.1", "port": port, "pid": facts.pid}
        assert stat.S_IMODE(pid_file.stat().st_mode) == 0o600
        assert is_same_process(facts)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=6) as client:
            response = client.post("/v1/messages", headers=CLIENT, json={"model": "m"})
            assert response.status_code == 200
            assert response.json()["content"][0]["text"] == "loopback upstream"
            with client.stream(
                "POST", "/messages", headers=CLIENT, json={"model": "m", "stream": True}
            ) as stream:
                assert stream.status_code == 200
                assert "first" in next(stream.iter_lines())
            assert disconnected.wait(6)
            source.write_text("invalid = [", encoding="utf-8")
            assert cli("reload", check=False).returncode != 0
            assert client.get("/admin/status", headers=ADMIN).json()["generation"] == 1
            assert client.get("/models", headers=CLIENT).status_code == 200
            source.write_text(config.replace('name = "m"', 'name = "m2"'), encoding="utf-8")
            cli("reload")
            assert client.get("/admin/status", headers=ADMIN).json()["generation"] == 2
            assert [item["id"] for item in client.get("/models", headers=CLIENT).json()["data"]] == ["m2"]
        current = pid_file.read_text(encoding="utf-8")
        stale = json.loads(current)
        stale["identity"]["start_ticks"] += 1
        pid_file.write_text(json.dumps(stale), encoding="utf-8")
        try:
            cli("stop")
            assert is_same_process(facts)
        finally:
            pid_file.write_text(current, encoding="utf-8")
    finally:
        cli("stop", check=False)
    assert not is_same_process(facts)
    assert not pid_file.exists()
