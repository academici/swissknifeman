"""Local supervisor shutdown against a blocked database and a live synthetic runtime."""

import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from http.client import HTTPConnection, HTTPException
from io import StringIO
from pathlib import Path
from urllib.error import URLError

import psycopg
import pytest

from contracts.execution.harness import PEPPER
from e2e.test_local_lifecycle import _health, _identity, _port, _record, box, scratch
from e2e.test_m1_config_on_postgres import ENTRY, Sandbox, ok, rows
from fixtures.execution.harness import clean_test_database, pg_session, recovery, test_database
from fixtures.execution.m3 import KEYS
from fixtures.execution.processes import scenario, script
from fixtures.execution.single_run import single_run
from skm.adapters.git.environments.worktree import WorktreeManager
from skm.entrypoints.cli.commands.local import _Local
from skm.entrypoints.cli.main import main
from skm.modules.access.public import CreateToken
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.environment import (
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
    attempt_branch,
)
from skm.modules.execution.host.environment import EnvironmentMount, EnvironmentSpec
from skm.modules.execution.ports import AttemptRepository, EnvironmentRepository
from skm.platform.config.bootstrap import BOOTSTRAP_URN
from skm.platform.process.identity import identity_of, is_same_process
from unit.execution.application._support import set_setting

__all__ = ["box", "clean_test_database", "pg_session", "recovery", "scratch", "test_database"]
pytestmark = [pytest.mark.e2e, pytest.mark.pg]


def test_serve_cancels_blocked_request_at_grace_deadline(box: Sandbox) -> None:
    bind = f"127.0.0.1:{_port()}"
    ok(
        box,
        "config",
        "set",
        "api.shutdown.grace_seconds",
        "1",
        "--scope",
        "instance",
        "--reason",
        "shutdown test",
    )
    argv = [sys.executable, "-c", ENTRY, "serve", "--bind", bind]
    process = subprocess.Popen(argv, cwd=box.root, env=box.env(), stdout=subprocess.DEVNULL, stderr=None)  # noqa: TID251
    try:
        deadline = time.monotonic() + 40
        while True:
            try:
                _health("http://" + bind)
                break
            except URLError:
                assert process.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.1)

        def fetch() -> int | None:
            with closing(HTTPConnection(bind, timeout=10)) as client:
                client.request(
                    "GET",
                    "/api/v1/admin/migrations",
                    headers={"Authorization": "Bearer " + box.owner_token.read_text().strip()},
                )
                try:
                    with client.getresponse() as response:
                        return response.status
                except (OSError, HTTPException):
                    return None

        with ThreadPoolExecutor() as executor, psycopg.connect(box.dsn) as lock:
            lock.execute("LOCK skm_core.schema_migrations IN ACCESS EXCLUSIVE MODE")
            response = executor.submit(fetch)
            deadline = time.monotonic() + 5
            while not rows(
                box.dsn,
                "SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
                "AND wait_event_type='Lock' AND query LIKE %s",
                "%schema_migrations%",
            ):
                assert time.monotonic() < deadline
                time.sleep(0.05)
            start = time.monotonic()
            process.send_signal(signal.SIGTERM)
            assert response.result(timeout=1.3) in {None, 500, 503}
            remaining = (
                "SELECT application_name, state, wait_event_type, query = 'LISTEN skm_events' "
                "FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid()"
            )
            while sessions := lock.execute(remaining).fetchall():
                assert time.monotonic() - start < 1.3, sessions
                lock.execute("SELECT pg_stat_clear_snapshot()")
                time.sleep(0.01)
            assert time.monotonic() - start < 1.3
            # Include all teardown in the same elapsed budget measured from the signal.
            assert process.wait(timeout=max(0.0, 1.9 - (time.monotonic() - start))) == 0
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def _profile(side) -> Sandbox:
    sandbox = Sandbox(side.root, side.dsn)
    sandbox.home.mkdir(exist_ok=True)
    sandbox.bootstrap.parent.mkdir(parents=True)
    state = sandbox.owner_token.parents[1]
    secrets = sandbox.owner_token.parent
    secrets.mkdir(mode=0o700, parents=True)
    pepper = secrets / "token-pepper"
    pepper.write_bytes(PEPPER)
    pepper.chmod(0o600)
    sandbox.owner_token.write_text(side.client.dispatch(CreateToken("lifecycle-owner")).secret)
    sandbox.owner_token.chmod(0o600)
    sandbox.bootstrap.write_text(
        f'schema = "{BOOTSTRAP_URN}"\ninstance_id = "{side.app.instance_id}"\n'
        '[access]\nmode = "embedded"\n[database]\nurl = "secret://env/SKM_DATABASE_URL"\n'
        f'[host]\nid = "{side.host1}"\n[secrets]\ntoken_pepper = "secret://file/{pepper}"\n'
        f'[paths]\nstate_dir = "{state}"\nblobs_root = "{side.boot.blobs_root}"\n'
    )
    return sandbox


def test_worktree_preview_and_removal_through_postgres(recovery) -> None:
    side = recovery
    sandbox = _profile(side)
    case = single_run(side)
    root = sandbox.owner_token.parents[1] / "worktrees"
    manager = WorktreeManager(case.git, worktrees_root=root)
    attempt = case.attempt
    branch = attempt_branch(attempt.id)
    prepared = manager.prepare(
        EnvironmentSpec(
            attempt.id,
            EnvironmentKind.GIT_WORKTREE,
            (EnvironmentMount("repo", side.repo_id, str(case.repository), "main"),),
            branch,
            root,
            None,
            None,
        )
    )
    set_setting(side, "worker.environments.retain_days", 0)
    with side.uow() as uow:
        uow.repo(EnvironmentRepository).upsert(
            ExecutionEnvironment(
                prepared.environment_id,
                attempt.id,
                side.host1,
                EnvironmentKind.GIT_WORKTREE,
                prepared.baseline,
                branch,
                prepared.locator,
                EnvironmentState.DISCARDED,
                attempt.started_at,
                attempt.started_at,
                None,
            )
        )
        repo = uow.repo(AttemptRepository)
        repo.save(
            replace(
                attempt,
                state=AttemptState.COMPLETED,
                continuation=None,
                host_id=side.host1,
                finished_at=attempt.started_at,
                end_reason="ACCEPTED",
                environment_id=prepared.environment_id,
            ),
            expected_version=repo.version(attempt.id),
        )
        uow.commit()
    assert ok(sandbox, "local", "clean", "--worktrees", "--dry-run")["targets"]["worktrees"] == [
        prepared.locator
    ]
    assert Path(prepared.locator).is_dir()
    assert ok(sandbox, "local", "clean", "--worktrees", "--yes")["targets"]["worktrees"]["marked"] == 1
    assert not Path(prepared.locator).exists()
    assert rows(
        side.dsn,
        "SELECT state FROM skm_execution.execution_environments WHERE id=%s",
        prepared.environment_id,
    ) == [("removed",)]
    assert ok(sandbox, "local", "clean", "--worktrees", "--yes")["targets"]["worktrees"]["marked"] == 0


def _continuous_fake_worker(path: str) -> int:
    """Use the PostgreSQL fixture's host adapters with the production multi-claim signal loop."""
    from fixtures.execution import worker_process
    from skm.entrypoints.cli.host import host_context_factory
    from skm.entrypoints.cli.main import Backend
    from skm.platform.system_clock import SystemClock

    def run(*, host, client, **_kwargs):
        backend = Backend(client, host_context_factory(host, client), Path(data["state"]))
        return main(sys.argv[2:], backend=lambda _options, _environ: backend)

    worker_process.main = run
    data = json.loads(Path(path).read_text())
    data["now"] = SystemClock().now().isoformat()
    Path(path).write_text(json.dumps(data))
    return worker_process.run(path)


def test_down_interrupts_inflight_fake_unit(recovery, monkeypatch) -> None:
    side = recovery
    sandbox = _profile(side)
    set_setting(side, "worker.disk_min_bytes", 0)
    set_setting(side, "extensions.packs.versions", {"core": "1.3.0"})
    state = sandbox.owner_token.parents[1]
    script_path = script(
        side.root / "script.toml",
        [("executor", KEYS[0], 1, scenario(side.root / "hang.toml", "executor", hang=True, model="fake-a"))],
    )
    worker_input = side.root / "fake-worker.json"
    worker_input.write_text(
        json.dumps(
            {
                "root": str(side.root),
                "state": str(state),
                "repository": str(side.root / "repository"),
                "dsn": side.dsn,
                "blobs_root": str(side.boot.blobs_root),
                "instance_id": str(side.app.instance_id),
                "secret": side.secret,
                "host_id": str(side.host1),
                "worker_id": str(side.worker1),
                "workspace_id": str(side.ws),
                "repository_id": str(side.repo_id),
                "script": str(script_path),
                "owner_id": str(side.owner.principal_id),
            }
        )
    )
    worker_input.chmod(0o600)
    argv = _Local.argv

    def with_fake(local, *args):
        if args[:3] == ("--json", "worker", "start"):
            return [
                sys.executable,
                "-c",
                "import sys; from e2e.test_local_lifecycle_shutdown import "
                "_continuous_fake_worker as run; sys.exit(run(sys.argv[1]))",
                str(worker_input),
                *argv(local, *args)[3:],
            ]
        return argv(local, *args)

    monkeypatch.setattr(_Local, "argv", with_fake)
    env = {
        **sandbox.env(),
        "SKM_WORKSPACE": str(side.ws),
        "PYTHONPATH": os.pathsep.join([str(Path(__file__).resolve().parents[1]), *sys.path]),
    }
    out, err = StringIO(), StringIO()
    port = _port()
    try:
        # Prepare the assignment before the API starts its own scheduler.
        case = single_run(side)
        assert (
            main(
                ["--json", "local", "up", "--port", str(port), "--wait", "35"],
                environ=env,
                stdout=out,
                stderr=err,
            )
            == 0
        ), out.getvalue() + err.getvalue()
        assert _health(f"http://127.0.0.1:{port}")[0]["status"] == "ready"
        worker = _record(sandbox, "worker")
        deadline = time.monotonic() + 35
        work = side.root / "worktrees" / str(case.attempt.id) / "repo/src/target.py"
        while (
            not work.exists()
            or "42" not in work.read_text()
            or not list((state / "ownership-facts").glob("*.json"))
        ):
            assert is_same_process(_identity(worker))
            assert time.monotonic() < deadline, (state / "logs/worker.log").read_text()[-2500:]
            time.sleep(0.1)
        (record,) = (state / "ownership-facts").glob("*.json")
        unit = json.loads(record.read_bytes())
        identity = identity_of(unit["pid"])
        assert identity
        assert identity.start_ticks == unit["start_ticks"]
        assert is_same_process(identity)
        started = time.monotonic()
        assert main(["local", "down", "--keep-db"], environ=env, stdout=out, stderr=err) == 0
        assert time.monotonic() - started < worker["grace"]
        assert not is_same_process(identity)
        assert not is_same_process(_identity(worker))
        summary = json.loads((state / "logs/worker.log").read_text().splitlines()[-1])
        slots = summary["result"]["slots"]
        assert {"outcome": "stopped", "reason": "shutdown", "assignments": 1} in slots
        assert sum(slot["assignments"] for slot in slots) == 1
        assert rows(
            side.dsn, "SELECT accepted_output_id FROM skm_execution.run_tasks WHERE id=%s", case.task.id
        ) == [(None,)]
        assert rows(
            side.dsn,
            "SELECT count(*) FROM skm_execution.attempt_outputs WHERE attempt_id=%s",
            case.attempt.id,
        ) == [(0,)]
    finally:
        ok(sandbox, "local", "down", "--keep-db")
