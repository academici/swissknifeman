"""Exercise production SKM subprocesses and PostgreSQL with a private local profile."""

import json
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg
import pytest

from e2e.test_m1_config_on_postgres import ENTRY, Sandbox, Scratch, ok, rows, scratch, skm
from skm.platform.process.identity import ProcessIdentity, is_same_process

__all__ = ["scratch"]
pytestmark = [pytest.mark.e2e, pytest.mark.pg]


@pytest.fixture
def box(scratch: Scratch, tmp_path: Path) -> Iterator[Sandbox]:
    sandbox = Sandbox(tmp_path, scratch.dsn)
    sandbox.home.mkdir(exist_ok=True)
    ok(sandbox, "init", "--database-url", scratch.dsn, "--host-name", "local-lifecycle")
    # Test the normal DDL-free serve path. Local up still applies migrations explicitly.
    text = sandbox.bootstrap.read_text()
    assert "migrate_on_start = true" in text
    sandbox.bootstrap.write_text(text.replace("migrate_on_start = true", "migrate_on_start = false"))
    try:
        yield sandbox
    finally:
        result = skm(sandbox, "local", "down", "--keep-db")
        assert result.returncode == 0, result.stdout + result.stderr


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _record(box: Sandbox, role: str) -> dict[str, Any]:
    return json.loads((box.owner_token.parents[1] / "pids" / f"{role}.pid").read_text())


def _identity(record: dict[str, Any]) -> ProcessIdentity:
    return ProcessIdentity(record["pid"], record["start_ticks"], record["boot_id"])


def _health(url: str) -> tuple[dict[str, Any], str | None]:
    with urlopen(url + "/health/ready", timeout=2) as response:
        return json.load(response), response.headers.get("SKM-Background")


def test_local_up_is_idempotent_and_down_gracefully_stops_serve_and_worker(box: Sandbox) -> None:
    port = _port()
    opts = ("--port", str(port), "--wait", "30")
    up = ok(box, "local", "up", *opts)
    assert [row["state"] for row in up["components"]] == ["running", "ready", "running"]
    records = {role: _record(box, role) for role in ("serve", "worker")}
    assert len({record["instance_id"] for record in records.values()}) == 1
    assert all(is_same_process(_identity(record)) for record in records.values())
    url = f"http://127.0.0.1:{port}"
    assert _health(url)[0]["status"] == "ready"
    assert ok(box, "local", "open", "--print")["url"] == url
    assert ok(box, "local", "token") == {"path": str(box.owner_token)}
    ok(box, "local", "up", *opts)
    assert {role: _record(box, role) for role in records} == records
    assert rows(box.dsn, "SELECT count(*) FROM skm_workspace.workers") == [(1,)]

    status = ok(box, "local", "status")
    assert [row["state"] for row in status["components"]] == ["running", "ready", "running"]
    human = subprocess.run(
        [sys.executable, "-c", ENTRY, "local", "status"],
        cwd=box.root,
        env=box.env(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert human.returncode == 0
    assert "component" in human.stdout
    assert url in human.stdout
    assert box.owner_token.read_text().strip() not in human.stdout

    down = ok(box, "local", "down", "--keep-db")
    assert down["stopped"] == ["serve", "worker"]
    assert all(not is_same_process(_identity(record)) for record in records.values())
    logs = box.owner_token.parents[1] / "logs"
    assert "Finished server process" in (logs / "serve.log").read_text()
    assert "slots" in (logs / "worker.log").read_text()
    assert rows(
        box.dsn,
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
        "AND pid <> pg_backend_pid()",
    ) == [(0,)]
    ok(box, "local", "down")
    assert [row["state"] for row in ok(box, "local", "status")["components"]] == [
        "running",
        "stopped",
        "stopped",
    ]


def test_api_only_shuts_down_cleanly_after_sigterm(box: Sandbox) -> None:
    port = _port()
    bind = f"127.0.0.1:{port}"
    process = subprocess.Popen(  # noqa: TID251 -- run production signal handling in a separate process
        [sys.executable, "-c", ENTRY, "serve", "--bind", bind, "--no-background", "--json"],
        cwd=box.root,
        env=box.env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and process.poll() is None:
            try:
                health, background = _health(f"http://{bind}")
            except (URLError, HTTPError):
                time.sleep(0.05)
                continue
            assert health["checks"]["schema"] == "ok"
            assert background == "disabled"
            break
        else:
            pytest.fail("serve did not start")
        _drain_request(box, lambda: process.send_signal(signal.SIGTERM), bind)
        out, err = process.communicate(timeout=12)
        assert process.returncode == 0, out + err
        assert json.loads(out)["result"] == {"status": "stopped", "bind": bind, "background": False}
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def _drain_request(box: Sandbox, stop: Callable[[], None], bind: str) -> None:
    request = Request(
        f"http://{bind}/api/v1/admin/migrations",
        headers={"Authorization": "Bearer " + box.owner_token.read_text().strip()},
    )

    def fetch() -> int:
        with urlopen(request, timeout=10) as response:
            return response.status

    waiting = (
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
        "AND wait_event_type = 'Lock' AND query LIKE %s"
    )
    with ThreadPoolExecutor(max_workers=1) as executor, psycopg.connect(box.dsn) as lock:
        lock.execute("LOCK skm_core.schema_migrations IN ACCESS EXCLUSIVE MODE")
        response = executor.submit(fetch)
        deadline = time.monotonic() + 5
        while rows(box.dsn, waiting, "%schema_migrations%") == [(0,)]:
            assert time.monotonic() < deadline, "HTTP request never reached the locked database table"
            time.sleep(0.05)
        stop()
        # The listening socket is drained while the admitted request is still blocked.
        time.sleep(0.25)
        assert not response.done()
        lock.rollback()
        assert response.result(timeout=5) == 200


def test_clean_dry_run_preserves_staging_files_and_database(box: Sandbox) -> None:
    from datetime import timedelta
    from os import utime
    from uuid import uuid4

    from skm.platform.config.bootstrap import load_bootstrap
    from skm.platform.system_clock import SystemClock

    config = load_bootstrap(str(box.bootstrap), box.env(), box.home)
    staged = config.blobs_root / "staging" / str(uuid4()) / f"{uuid4()}.part"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"incomplete upload")
    old = (SystemClock().now() - timedelta(days=3)).timestamp()
    utime(staged, (old, old))
    final = config.blobs_root / str(uuid4()) / "objects" / "aa" / ("aa" * 32)
    final.parent.mkdir(parents=True)
    final.write_bytes(b"final object")
    before = [(path, path.stat().st_mtime_ns) for path in box.root.rglob("*")]
    history = "SELECT count(*) FROM skm_core.domain_events"
    stored = rows(box.dsn, history)

    assert ok(box, "local", "clean", "--dry-run", "--staging")["targets"] == {"staging": [str(staged)]}
    assert [(path, path.stat().st_mtime_ns) for path in box.root.rglob("*")] == before
    assert rows(box.dsn, history) == stored

    assert ok(box, "local", "clean", "--yes", "--staging")["targets"] == {"staging": [str(staged)]}
    assert not staged.exists()
    assert final.read_bytes() == b"final object"


def test_serve_admits_health_without_migrating_empty_database(scratch: Scratch, tmp_path: Path) -> None:
    from uuid import uuid4

    from skm.platform.config.bootstrap import BOOTSTRAP_URN

    box = Sandbox(tmp_path, scratch.dsn)
    box.bootstrap.parent.mkdir(parents=True, exist_ok=True)
    pepper = tmp_path / "pepper"
    pepper.write_text("local-test-credential-pepper-length")
    pepper.chmod(0o600)
    box.bootstrap.write_text(
        f'schema = "{BOOTSTRAP_URN}"\ninstance_id = "{uuid4()}"\n'
        '[access]\nmode = "embedded"\n'
        '[database]\nurl = "secret://env/SKM_DATABASE_URL"\nmigrate_on_start = false\n'
        f'[secrets]\ntoken_pepper = "secret://file/{pepper}"\n'
    )
    bind = f"127.0.0.1:{_port()}"
    process = subprocess.Popen(  # noqa: TID251 -- production schema admission and signal handling
        [sys.executable, "-c", ENTRY, "serve", "--bind", bind],
        cwd=box.root,
        env=box.env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and process.poll() is None:
            try:
                _health(f"http://{bind}")
            except HTTPError as error:
                with error:
                    status, health = error.code, json.load(error)
                break
            except URLError:
                time.sleep(0.05)
        else:
            pytest.fail("restricted serve did not start")
        assert status == 503
        assert health["checks"]["schema"] == "not_migrated"
        assert rows(box.dsn, "SELECT to_regclass('skm_core.schema_migrations')") == [(None,)]
        process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=12)
        assert process.returncode == 0, out + err
        assert "serve stopped" in out
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_foreign_http_listener_receives_no_owner_token(box: Sandbox) -> None:
    from dataclasses import asdict
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from skm.platform.config.bootstrap import load_bootstrap
    from skm.platform.process.identity import identity_of

    credentials = []

    class Foreign(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            credentials.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    config = load_bootstrap(str(box.bootstrap), box.env(), box.home)
    with ThreadingHTTPServer(("127.0.0.1", 0), Foreign) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        record = config.state_dir / "pids/serve.pid"
        try:
            result = skm(box, "local", "up", "--no-worker", "--port", str(server.server_port))
            assert result.returncode
            assert json.loads(result.stdout)["error"]["code"] == "BACKEND_UNAVAILABLE"
            assert not record.exists()
            # A live PID at the recorded URL still has to own the TCP peer.
            with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]) as other:  # noqa: TID251
                try:
                    identity = identity_of(other.pid)
                    assert identity is not None
                    record.write_text(
                        json.dumps(
                            {
                                **asdict(identity),
                                "role": "serve",
                                "instance_id": str(config.instance_id),
                                "url": f"http://127.0.0.1:{server.server_port}",
                            }
                        )
                    )
                    for args in (("open",), ("open", "--print")):
                        result = skm(box, "local", *args)
                        assert result.returncode
                        assert json.loads(result.stdout)["error"]["code"] == "BACKEND_UNAVAILABLE"
                        assert box.owner_token.read_text().strip() not in result.stdout + result.stderr
                finally:
                    other.terminate()
            assert credentials
            assert all(value is None for value in credentials)
        finally:
            record.unlink(missing_ok=True)
            server.shutdown()
            thread.join()
