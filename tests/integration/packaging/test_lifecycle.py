"""Exercise the installed CLI, server and worker against a newly created PostgreSQL database."""

import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from e2e._plan_authoring import baseline_revision, upload_guide, verify_barrier_runtime
from e2e.test_local_lifecycle import _port
from e2e.test_m1_config_on_postgres import Sandbox, Scratch, rows, scratch
from e2e.test_plan_authoring import A, Barrier, ControlPlane, _configure, _run_status, barrier
from fakes.clock import FrozenClock
from integration.artifacts.test_upload_flow import dispatch_new
from integration.postgres.test_machine_store import Databases, databases, migrated_databases
from skm.application_bus.client import SkmClient
from skm.modules.execution import public as execution
from skm.modules.workspace import public as workspace
from support.client_transport import http_client
from support.service_runner import Instance

__all__ = ["barrier", "databases", "migrated_databases", "scratch"]
pytestmark = [pytest.mark.e2e, pytest.mark.pg]


def _env(box: Sandbox, installed_bin: Path) -> dict[str, str]:
    env = box.env()
    env.pop("PYTHONPATH", None)
    env["PATH"] = str(installed_bin) + os.pathsep + os.defpath
    return env


def _cli(cwd: Path, env: dict[str, str], *args: str) -> dict[str, Any]:
    cli = shutil.which("skm", path=env["PATH"])
    assert cli is not None
    result = subprocess.run(
        [cli, "--json", *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)["result"]


def test_installed_local_up_uses_machine_workspace(
    installed_bin: Path, databases: Databases, tmp_path: Path
) -> None:
    box = Sandbox(tmp_path, databases.project)
    env = {
        **_env(box, installed_bin),
        "SKM_DATABASE_MIGRATOR_URL": databases.project_migrator,
        "SKM_MACHINE_DATABASE_URL": databases.machine,
        "SKM_MACHINE_DATABASE_MIGRATOR_URL": databases.machine_migrator,
    }
    init = _cli(box.root, env, "init", "--host-name", "wheel-local")
    with ExitStack() as stack:
        stack.callback(_cli, box.root, env, "local", "down", "--keep-db")
        up = _cli(box.root, env, "local", "up", "--port", str(_port()), "--wait", "60")
        assert [row["state"] for row in up["components"]] == ["running", "ready", "running"]
        assert rows(databases.project, "SELECT workspace_id FROM skm_workspace.workers") == [
            (UUID(init["workspace"]["workspace_id"]),)
        ]
        assert not (box.owner_token.parents[1] / "cli-context.json").exists()


@pytest.fixture
def control_plane(scratch: Scratch, installed_bin: Path, tmp_path: Path) -> Iterator[ControlPlane]:
    box = Sandbox(tmp_path, scratch.dsn)
    env = _env(box, installed_bin)
    cwd = box.root / "empty"
    cwd.mkdir()
    init = _cli(cwd, env, "init", "--database-url", scratch.dsn, "--host-name", "wheel")
    port = _port()
    endpoint = f"http://127.0.0.1:{port}"
    with ExitStack() as stack:
        stack.callback(_cli, cwd, env, "local", "down", "--keep-db")
        # The test registers its worker with the synthetic runtime after configuring the project.
        _cli(cwd, env, "local", "up", "--port", str(port), "--no-worker", "--wait", "30")
        response = httpx.get(endpoint + "/health/ready", trust_env=False)
        assert response.json()["status"] == "ready"

        def connect(token: str) -> SkmClient:
            return http_client(stack, endpoint, tmp_path, token, FrozenClock())

        owner = connect(box.owner_token.read_text().strip())
        ws = UUID(init["workspace"]["workspace_id"])
        project = dispatch_new(owner, workspace.CreateProject(ws, "wheel", "Wheel")).project_id
        yield ControlPlane(box, stack, connect, owner, ws, project, UUID(init["instance_id"]), endpoint)


def _assert_ui(engine: ControlPlane) -> None:
    with httpx.Client(base_url=engine.endpoint, trust_env=False) as http:
        index = http.get("/")
        assert index.status_code == 200
        assert index.headers["content-type"].startswith("text/html")
        (script,) = re.findall(r'<script[^>]+src="(/assets/[^"]+\.js)"', index.text)
        asset = http.get(script)
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]
        assert len(asset.content) == int(http.head(script).headers["content-length"])
        assert http.get("/w/wheel/plans/123").content == index.content
        head = http.head("/login")
        assert head.status_code == 200
        assert not head.content
        assert head.headers["content-length"] == str(len(index.content))
        assert http.get("/assets/missing.js").status_code == 404
        auth = {"Authorization": "Bearer " + engine.box.owner_token.read_text().strip()}
        for path in ("/api", "/api/v1/missing", "/health", "/health/missing"):
            assert http.get(path, headers=auth).status_code == 404


def test_installed_local_fake_run(
    installed_bin: Path,
    control_plane: ControlPlane,
    barrier: Barrier,
    migrated_databases: Databases,
) -> None:
    engine = control_plane
    box, owner, ws, project = engine.box, engine.owner, engine.workspace_id, engine.project_id
    _assert_ui(engine)
    cwd = box.root / "empty"
    env = _env(box, installed_bin)
    host = UUID(_cli(cwd, env, "host", "register", "wheel")["host_id"])
    worker_env = engine.worker_env(
        {**env, "SKM_HOST_ID": str(host)}, migrated_databases.machine, barrier.executable, remote=False
    )

    def bind(checkout: Path, repository_id: UUID) -> None:
        _cli(
            checkout,
            {**worker_env, "SKM_WORKSPACE": str(ws), "SKM_PROJECT": str(project)},
            "repo",
            "bind",
            "--repo",
            str(repository_id),
            "--mount",
            "repo",
            "--yes",
        )

    _configure(owner, box, ws, project, bind)
    added = upload_guide(owner, ws, project)
    plan, revision = baseline_revision(owner, project, added.file_version_id, output_path="src/authored.txt")
    auth = box.home / ".codex/auth.json"
    auth.parent.mkdir(mode=0o700)
    fixture = Path(__file__).resolve().parents[2] / "fixtures/runtimes/config-isolation/credentials"
    auth.write_bytes((fixture / "codex_valid.json").read_bytes())
    auth.chmod(0o600)
    worker = _cli(
        cwd,
        env,
        "worker",
        "register",
        "wheel-worker",
        "--runtime",
        "codex",
        "--isolation",
        "worktree",
        "--isolation",
        "landlock",
    )
    remote = engine.remote_env(host)
    remote.pop("PYTHONPATH", None)
    remote["PATH"] = env["PATH"]
    args = [
        "skm",
        "worker",
        "start",
        "--worker",
        worker["worker_id"],
        "--token",
        "secret://file/" + worker["token_file"],
    ]
    with (box.root / "worker.log").open("w+") as log:
        process = subprocess.Popen(  # noqa: TID251 -- exercise the installed worker subprocess
            args, env=worker_env, cwd=cwd, stdout=log, stderr=log, text=True
        )
        try:
            verify_barrier_runtime(
                owner,
                box,
                host,
                process,
                worker_env,
                barrier.executable,
                worker_python=str(installed_bin / "python"),
            )
            started = _cli(
                cwd,
                remote,
                "run",
                "start",
                str(plan),
                "--revision",
                str(revision.revision_id),
                "--tasks",
                A,
                "--skip-readiness",
                "--yes",
            )
            rid = started["run_id"]
            barrier.release()
            ((check,),) = Instance.wait_until(
                lambda: rows(
                    box.dsn,
                    "SELECT id FROM skm_execution.check_executions "
                    "WHERE run_id = %s AND state = 'manual_pending'",
                    rid,
                ),
                timeout=45,
                description="synthetic executor output accepted for manual verification",
            )
            dispatch_new(owner, execution.RecordManualVerdict(check, "pass", "Verified synthetic output"))
            Instance.wait_until(
                lambda: _run_status(owner, UUID(rid)).status == "succeeded",
                timeout=45,
                description="installed worker completes the run",
            )
        finally:
            Instance.stop(process)
