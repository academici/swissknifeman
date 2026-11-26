"""ENCH4 through the PostgreSQL-backed serve, worker, CLI and stdio MCP processes."""

import json
import os
import ssl
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from shutil import which
from subprocess import Popen  # noqa: TID251 -- process types used by the E2E harness
from textwrap import dedent
from typing import Any
from uuid import UUID

import httpx
import pytest

from contracts.planning._authoring_support import BASE_GUIDE, BASE_TEXT, EDITED_TEXT, NEW_GUIDE, A
from e2e._plan_authoring import (
    AUTHORED_CHECK,
    baseline_revision,
    edit_drafts,
    issue_editor,
    mcp_tools,
    publish_repaired,
    upload_guide,
    verify_barrier_runtime,
)
from e2e.test_local_lifecycle import _port
from e2e.test_m1_config_on_postgres import ENTRY, Sandbox, Scratch, ok, rows, scratch
from fakes.clock import FrozenClock
from integration.artifacts.test_upload_flow import dispatch_new
from integration.postgres.test_machine_store import Databases, databases, migrated_databases
from integration.runtimes.test_codex_argv import ALL_SUPPORTED_EXEC_HELP, ALL_SUPPORTED_ROOT_HELP
from skm.adapters.postgres.machine import PostgresMachineStore
from skm.application_bus.client import SkmClient
from skm.bootstrap.machine import https_origin
from skm.modules.execution import public as execution
from skm.modules.extensions import public as extensions
from skm.modules.planning import public as planning
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from skm.platform.config.bootstrap import BOOTSTRAP_URN
from skm.platform.config.secrets import SecretRef
from skm.platform.machine import MachineProfile
from support.client_transport import http_client
from support.git_repo import init_git_repo
from support.machine import machine_operator, set_machine_setting
from support.service_runner import Instance

__all__ = ["databases", "migrated_databases", "scratch"]
pytestmark = [pytest.mark.e2e, pytest.mark.pg]
ROUTE_BASE, ROUTE_EDITED = "gpt-6-sol", "gpt-6-astra"
TLS_ENTRY = (
    """
import os
from functools import partial
from skm.entrypoints.api import app

app.Config = partial(
    app.Config, ssl_certfile=os.environ["TEST_TLS_CERT"], ssl_keyfile=os.environ["TEST_TLS_KEY"]
)
"""
    + ENTRY
)


@dataclass(frozen=True)
class Barrier:
    root: Path
    executable: Path
    release_fd: int

    def arrivals(self) -> list[Path]:
        return sorted(self.root.parent.rglob("ench4-arrival-*.json"))

    def release(self) -> None:
        os.write(self.release_fd, b"+")


@pytest.fixture
def barrier(control_plane: "ControlPlane", tmp_path: Path) -> Barrier:
    """Run a synthetic runtime driver using the worker's regular executable setting."""
    root = tmp_path / "barrier"
    root.mkdir()
    fifo = root / "release"
    os.mkfifo(fifo)
    executable = root / "codex"
    executable.write_text(
        dedent(
            f"""\
            #!{sys.executable}
            import json
            import os
            import sys
            from pathlib import Path
            from uuid import uuid4

            argv = sys.argv[1:]
            if argv == ["--version"]:
                print("codex-cli 0.165.0")
                sys.exit(0)
            if argv == ["exec", "--help"]:
                print({ALL_SUPPORTED_EXEC_HELP!r})
                sys.exit(0)
            if argv == ["--help"]:
                print({ALL_SUPPORTED_ROOT_HELP!r})
                sys.exit(0)
            if argv == ["login", "status"]:
                print("Logged in using ChatGPT")
                sys.exit(0)

            prompt = sys.stdin.read()
            model = argv[argv.index("--model") + 1]
            root = Path({str(root)!r})
            # The isolated adapter allows writes in its own client home.
            signals = Path(os.environ.get("CODEX_HOME", root))
            receipt = signals / ("ench4-arrival-" + str(uuid4()) + ".json")
            temporary = receipt.with_suffix(".tmp")
            temporary.write_text(json.dumps({{"model": model, "prompt": prompt, "executable": __file__}}))
            temporary.rename(receipt)
            fd = os.open(root / "release", os.O_RDONLY)
            try:
                assert os.read(fd, 1) == b"+"
            finally:
                os.close(fd)

            Path("src/authored.txt").write_text(model + "\\n")
            result = {{
                "schema": "urn:skm:execution:role-result:executor:v1",
                "status": "done",
                "summary": "Executed the pinned authoring fixture.",
                "changed_paths": [{{"mount": "repo", "path": "src/authored.txt", "change": "modified"}}],
                "checks_run": [],
                "open_issues": [],
                "self_check": {{"performed": True}},
            }}
            records = [
                {{"type": "thread.started", "thread_id": str(uuid4())}},
                {{"type": "turn.started"}},
                {{"type": "item.completed", "item": {{
                    "id": "result", "type": "agent_message", "text": json.dumps(result)
                }}}},
                {{"type": "turn.completed", "usage": {{"input_tokens": 120, "output_tokens": 45}}}},
            ]
            for record in records:
                print(json.dumps(record), flush=True)
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o700)
    fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    control_plane.stack.callback(os.close, fd)
    return Barrier(root, executable, fd)


@contextmanager
def _process(
    box: Sandbox, name: str, args: tuple[str, ...], *, env: dict[str, str], stdio: bool = False
) -> Iterator[Popen[str]]:
    entry = TLS_ENTRY if "TEST_TLS_CERT" in env else ENTRY

    with (box.root / f"{name}.log").open("w+") as log:
        process = subprocess.Popen(  # noqa: TID251 -- test exercises real SKM subprocesses
            [sys.executable, "-c", entry, *args],
            cwd=box.root,
            env=env,
            stdin=subprocess.PIPE if stdio else subprocess.DEVNULL,
            stdout=subprocess.PIPE if stdio else log,
            stderr=log,
            text=True,
        )
        try:
            yield process
        except AssertionError as error:
            log.seek(0)
            error.add_note(f"{name} log:\n{log.read()}")
            raise
        finally:
            if process.stdin is not None:
                process.stdin.close()
            Instance.stop(process)
            if process.stdout is not None:
                process.stdout.close()


def _ready(process: Popen[str], endpoint: str, tls: ssl.SSLContext) -> bool:
    assert process.poll() is None, "skm serve exited during startup"
    try:
        return httpx.get(f"{endpoint}/health/ready", timeout=1, trust_env=False, verify=tls).is_success
    except httpx.TransportError:
        return False


def _configure(
    owner: SkmClient, box: Sandbox, ws: UUID, project: UUID, bind: Callable[[Path, UUID], None]
) -> Path:
    synced = dispatch_new(owner, extensions.SyncBuiltinPacks())
    assert "core" in {item.slug for item in (*synced.installed, *synced.already_installed)}
    checkout = init_git_repo(box.root / "checkout")
    checkout.commit_file("src/authored.txt", "baseline\n")
    checkout.create_branch("ench4-integration")
    remote = "https://example.invalid/ench4.git"
    checkout.add_remote("origin", remote)
    repository = dispatch_new(owner, workspace.RegisterRepository(ws, "ENCH4 repository", remote, None))
    dispatch_new(owner, workspace.AttachRepository(project, repository.repository_id, "repo", "primary"))
    bind(checkout.path, repository.repository_id)
    for key, value in {
        "runtimes.allowed": ["codex"],
        "runtimes.preference": ["codex"],
        # Both models are exercised by the offline runtime and have no catalog prices.
        "budgets.run.max_usd": 0,
        "policy.ceiling.network": "none",
        "execution.readiness.required": False,
        "execution.advisor.enabled": False,
        "execution.review.strategy": "per_task",
        "execution.integration.branch": "ench4-integration",
        "execution.lease.renew_every_seconds": 5,
        "worker.disk_min_bytes": 0,
    }.items():
        dispatch_new(
            owner,
            settings.SetValue.from_json(
                {"scope": {"level": "instance"}, "key": key, "value": value, "expected_row_version": 0}
            ),
        )
    return checkout.path


@dataclass(frozen=True)
class Binding:
    revision_id: UUID
    entity_id: UUID
    instruction_digest: str
    task_contract_digest: str
    prompt_digest: str
    model: str
    bundle_digest: str
    material_ref: str
    material_digest: str


def _binding(box: Sandbox, run: UUID) -> Binding:
    (data,) = rows(
        box.dsn,
        "SELECT r.revision_id, t.spec_entity_id, s.input_digest, st.admission->>'contract_digest', "
        "m.prompt_digest, st.model, b.config_digest, mb.source_ref, mb.source_version "
        "FROM skm_execution.runs r JOIN skm_execution.run_tasks t ON t.run_id = r.id "
        "JOIN skm_execution.attempt_stages s ON s.task_id = t.id AND s.stage_id = 'execute' "
        "JOIN skm_execution.attempt_steps st ON st.stage_record_id = s.id "
        "JOIN skm_execution.execution_bundles b ON b.run_id = r.id "
        "JOIN skm_context.context_manifests m ON m.id = st.context_manifest_id "
        "JOIN skm_context.context_blocks mb ON mb.manifest_id = m.id AND mb.block_type = 'materials' "
        "AND mb.included "
        "WHERE r.id = %s AND t.display_key = %s AND m.state = 'final' "
        "AND m.revision_id = r.revision_id AND m.entity_id = t.spec_entity_id",
        run,
        A,
    )
    return Binding(*data)


def _heartbeat(box: Sandbox, run: UUID) -> datetime:
    ((value,),) = rows(
        box.dsn,
        "SELECT l.last_heartbeat_at FROM skm_execution.assignment_leases l "
        "JOIN skm_execution.assignments a ON a.id = l.assignment_id WHERE a.run_id = %s",
        run,
    )
    return value


def _run_status(owner: SkmClient, run: UUID) -> Any:
    return owner.ask(execution.GetRun(run))


def _arrived(barrier: Barrier, seen: set[Path], worker: Popen[str]) -> tuple[Path, dict[str, Any]]:
    def arrivals() -> set[Path]:
        assert worker.poll() is None, (barrier.root.parent / "worker.log").read_text()
        return set(barrier.arrivals()) - seen

    (path,) = Instance.wait_until(arrivals, timeout=30, description="fake runtime to receive the prompt")
    return path, json.loads(path.read_text())


@dataclass(frozen=True)
class ControlPlane:
    box: Sandbox
    stack: ExitStack
    connect: Callable[[str], SkmClient]
    owner: SkmClient
    workspace_id: UUID
    project_id: UUID
    instance_id: UUID
    endpoint: str
    ca_bundle: Path | None = None

    def remote_env(self, host: UUID | None = None) -> dict[str, str]:
        env = self.box.env()
        del env["SKM_DATABASE_URL"]
        remote = self.box.root / "remote.toml"
        tls = f'ca_bundle = "{self.ca_bundle}"\n' if self.ca_bundle is not None else ""
        remote.write_text(
            f'schema = "{BOOTSTRAP_URN}"\ninstance_id = "{self.instance_id}"\n'
            f'[access]\nmode = "http"\n[api]\nendpoint = "{self.endpoint}/api/v1"\n'
            'credential = "secret://env/SKM_API_TOKEN"\n'
            f"{tls}"
            f'[host]\nid = "{host or "auto"}"\n[paths]\nstate_dir = "{self.box.root / "remote-state"}"\n'
        )
        return {
            **env,
            "SKM_BOOTSTRAP": str(remote),
            "SKM_API_TOKEN": self.box.owner_token.read_text().strip(),
            "SKM_WORKSPACE": str(self.workspace_id),
            "SKM_PROJECT": str(self.project_id),
        }

    def worker_env(
        self,
        environ: Mapping[str, str],
        machine_dsn: str,
        binary: Path,
        *,
        remote: bool,
    ) -> dict[str, str]:
        env = machine_operator(environ, machine_dsn)
        installation = UUID(env["SKM_INSTALLATION_ID"])
        if remote:
            profile = MachineProfile(
                installation,
                "default",
                self.instance_id,
                https_origin(self.endpoint),
                self.endpoint + "/api/v1",
                credential_ref=SecretRef.parse("secret://env/SKM_API_TOKEN"),
                ca_bundle=self.ca_bundle,
            )
        else:
            profile = MachineProfile(
                installation, "default", self.instance_id, f"embedded:{self.instance_id}", None
            )
        assert PostgresMachineStore(machine_dsn).put_profile(profile)
        set_machine_setting(env, "runtimes.binaries", {"codex": str(binary)})
        set_machine_setting(env, "runtimes.credentials.copy", {"codex": True})
        set_machine_setting(
            env,
            "runtimes.models.allowed",
            {"codex": {ROUTE_BASE: ["high"], ROUTE_EDITED: ["high"]}},
        )
        return env


@pytest.fixture
def control_plane(scratch: Scratch, tmp_path: Path) -> Iterator[ControlPlane]:
    box = Sandbox(tmp_path, scratch.dsn)
    box.home.mkdir(exist_ok=True)
    init = ok(box, "init", "--database-url", scratch.dsn, "--host-name", "ench4")
    # The instance was already migrated by init.
    profile = box.bootstrap.read_text()
    box.bootstrap.write_text(profile.replace("migrate_on_start = true", "migrate_on_start = false"))
    bind = f"127.0.0.1:{_port()}"
    endpoint = f"https://{bind}"
    cert, key = box.root / "localhost.pem", box.root / "localhost.key"
    openssl = which("openssl")
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
            "-out",
            str(cert),
            "-keyout",
            str(key),
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    tls = ssl.create_default_context(cafile=str(cert))
    serve_env = {**box.env(), "TEST_TLS_CERT": str(cert), "TEST_TLS_KEY": str(key)}
    with ExitStack() as stack:
        serve = stack.enter_context(_process(box, "serve", ("serve", "--bind", bind), env=serve_env))
        Instance.wait_until(lambda: _ready(serve, endpoint, tls), timeout=30, description="serve readiness")

        def connect(token: str) -> SkmClient:
            return http_client(stack, endpoint, tmp_path, token, FrozenClock(), verify=tls)

        owner = connect(box.owner_token.read_text().strip())
        ws = UUID(init["workspace"]["workspace_id"])
        project = dispatch_new(owner, workspace.CreateProject(ws, "ench4", "ENCH4")).project_id
        yield ControlPlane(box, stack, connect, owner, ws, project, UUID(init["instance_id"]), endpoint, cert)


def _author(
    engine: ControlPlane, env: dict[str, str], plan: UUID, baseline: UUID, added: Any
) -> tuple[Any, Any]:
    box, owner, connect = engine.box, engine.owner, engine.connect
    ws, project = engine.workspace_id, engine.project_id
    first_token, second_token = (issue_editor(owner, ws, name) for name in ("Editor One", "Editor Two"))
    first, second = connect(first_token.secret), connect(second_token.secret)
    mcp = mcp_tools(
        engine.stack.enter_context(
            _process(
                box,
                "mcp",
                ("mcp", "--project", str(project), "--token-env", "SKM_API_TOKEN"),
                env={**env, "SKM_API_TOKEN": second_token.secret},
                stdio=True,
            )
        )
    )
    draft = edit_drafts(first, second, mcp, plan, baseline)
    return publish_repaired(box, owner, second, second_token, connect, ws, project, plan, draft, added)


def test_concurrent_authoring_and_publish_replay(control_plane: ControlPlane) -> None:
    engine = control_plane
    added = upload_guide(engine.owner, engine.workspace_id, engine.project_id)
    plan, baseline = baseline_revision(engine.owner, engine.project_id, added.file_version_id)
    _author(engine, engine.remote_env(), plan, baseline.revision_id, added)


def test_authoring_publication_keeps_an_active_run_pinned(  # noqa: PLR0915 -- one ordered acceptance scenario
    migrated_databases: Databases, control_plane: ControlPlane, barrier: Barrier
) -> None:
    engine = control_plane
    box, owner, stack = engine.box, engine.owner, engine.stack
    ws, project = engine.workspace_id, engine.project_id
    host = UUID(ok(box, "host", "register", "ench4")["host_id"])
    env = engine.remote_env(host)
    worker_env = engine.worker_env(
        {**env, "PATH": os.defpath}, migrated_databases.machine, barrier.executable, remote=True
    )

    def bind(checkout: Path, repository_id: UUID) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                ENTRY,
                "--json",
                "repo",
                "bind",
                "--repo",
                str(repository_id),
                "--mount",
                "repo",
                "--yes",
            ],
            cwd=checkout,
            env=worker_env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    checkout = _configure(owner, box, ws, project, bind)
    added = upload_guide(owner, ws, project)
    plan, baseline = baseline_revision(owner, project, added.file_version_id, output_path="src/authored.txt")
    # The adapter isolates the runtime's home and checks that its auth fixture is present.
    auth = box.home / ".codex" / "auth.json"
    auth.parent.mkdir(mode=0o700)
    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures/runtimes/config-isolation/credentials/codex_valid.json"
    )
    auth.write_bytes(fixture.read_bytes())
    auth.chmod(0o600)
    worker = ok(
        box,
        "worker",
        "register",
        "ench4-worker",
        "--skm-version",
        "2.0.0",
        "--runtime",
        "codex",
        "--isolation",
        "worktree",
        "--isolation",
        "landlock",
    )
    token_ref = "secret://file/" + worker["token_file"]
    proc = stack.enter_context(
        _process(
            box,
            "worker",
            ("-vv", "worker", "start", "--worker", worker["worker_id"], "--token", token_ref),
            env=worker_env,
        )
    )
    stack.callback(barrier.release)

    def start(revision: UUID) -> UUID:
        cli = subprocess.run(
            [
                sys.executable,
                "-c",
                ENTRY,
                "--json",
                "run",
                "start",
                str(plan),
                "--revision",
                str(revision),
                "--tasks",
                A,
                "--skip-readiness",
                "--yes",
            ],
            cwd=box.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert cli.returncode == 0, cli.stdout + cli.stderr
        return UUID(json.loads(cli.stdout)["result"]["run_id"])

    verify_barrier_runtime(owner, box, host, proc, worker_env, barrier.executable)
    old = start(baseline.revision_id)
    try:
        arrival, request = _arrived(barrier, set(), proc)
    except AssertionError as error:
        stages = rows(
            box.dsn,
            "SELECT s.stage_id, s.state, s.error_code, s.outcome_kind, st.state, st.runtime_id, st.model, "
            "s.runtime_started_at IS NOT NULL "
            "FROM skm_execution.attempt_stages s LEFT JOIN skm_execution.attempt_steps st "
            "ON st.stage_record_id = s.id WHERE s.run_id = %s ORDER BY s.seq",
            old,
        )
        error.add_note(f"run status {_run_status(owner, old).status}, stages {stages!r}")
        raise
    original, initial = _binding(box, old), _run_status(owner, old)
    assert initial.status == "running"
    assert original.revision_id == baseline.revision_id
    assert original.model == request["model"] == ROUTE_BASE
    assert Path(request["executable"]).parent.name == ".pinned-bin"
    assert original.bundle_digest == initial.bundle_digest
    assert original.material_ref == f"file_version:{added.file_version_id}"
    assert original.material_digest == "sha256:" + sha256(BASE_GUIDE).hexdigest()
    assert original.prompt_digest == "sha256:" + sha256(request["prompt"].encode()).hexdigest()
    assert BASE_TEXT in request["prompt"]
    assert BASE_GUIDE.decode().strip() in request["prompt"]
    heartbeat = _heartbeat(box, old)
    final, updated = _author(engine, env, plan, baseline.revision_id, added)
    assert proc.poll() is None
    held_heartbeat = _heartbeat(box, old)
    assert held_heartbeat >= heartbeat
    Instance.wait_until(
        lambda: _heartbeat(box, old) > held_heartbeat,
        description="blocked assignment heartbeat after publish",
    )
    assert _binding(box, old) == original
    held = _run_status(owner, old)
    assert (held.status, held.bundle_digest) == ("running", initial.bundle_digest)
    assert barrier.arrivals() == [arrival]
    assert (checkout / "src/authored.txt").read_text() == "baseline\n"

    barrier.release()
    ((original_check,),) = Instance.wait_until(
        lambda: rows(
            box.dsn,
            "SELECT c.id FROM skm_execution.check_executions c "
            "JOIN skm_execution.run_tasks t ON t.id = c.task_id "
            "WHERE c.run_id = %s AND c.check_key = %s AND c.state = 'manual_pending' "
            "AND t.status = 'manual_pending'",
            old,
            f"{A}:V1",
        ),
        timeout=30,
        description="the old revision's manual check",
    )
    dispatch_new(owner, execution.RecordManualVerdict(original_check, "pass", "Verified the old run output"))
    Instance.wait_until(
        lambda: _run_status(owner, old).status == "succeeded", timeout=45, description="old run"
    )
    assert _binding(box, old) == original
    assert _run_status(owner, old).bundle_digest == initial.bundle_digest
    new = start(final.revision_id)
    _, request = _arrived(barrier, {arrival}, proc)
    rebound, next_run = _binding(box, new), _run_status(owner, new)
    assert rebound.revision_id == final.revision_id
    assert rebound.entity_id == original.entity_id
    assert rebound.task_contract_digest != original.task_contract_digest
    assert rebound.instruction_digest != original.instruction_digest
    assert rebound.model == request["model"] == ROUTE_EDITED
    assert Path(request["executable"]).parent.name == ".pinned-bin"
    assert rebound.bundle_digest == next_run.bundle_digest
    assert rebound.material_ref == f"file_version:{updated.file_version_id}"
    assert rebound.material_digest == "sha256:" + sha256(NEW_GUIDE).hexdigest()
    assert EDITED_TEXT in request["prompt"]
    assert AUTHORED_CHECK in request["prompt"]
    assert NEW_GUIDE.decode().strip() in request["prompt"]
    assert BASE_TEXT not in request["prompt"]
    assert BASE_GUIDE.decode().strip() not in request["prompt"]
    assert rebound.prompt_digest == "sha256:" + sha256(request["prompt"].encode()).hexdigest()
    revised: Any = owner.ask(planning.GetRevision(plan, revision_id=final.revision_id, include_document=True))
    assert revised.document["materials"][0]["file_version_id"] == str(updated.file_version_id)
    assert next_run.selection is not None
    assert not next_run.selection["satisfied"]
    barrier.release()
    task = Instance.wait_until(
        lambda: rows(
            box.dsn,
            "SELECT status, accepted_attempt_id, accepted_output_id FROM skm_execution.run_tasks "
            "WHERE run_id = %s AND display_key = %s AND status = 'manual_pending'",
            new,
            A,
        ),
        timeout=30,
        description="the new run to evaluate its manual checks",
    )
    assert task == [("manual_pending", None, None)]
    checks = rows(
        box.dsn,
        "SELECT check_key, revision_id, state, required, summary, reused_from_id "
        "FROM skm_execution.check_executions WHERE run_id = %s AND check_key IN (%s, %s) ORDER BY check_key",
        new,
        f"{A}:V1",
        f"{A}:V2",
    )
    assert [(key, revision, state, reused) for key, revision, state, _, _, reused in checks] == [
        (f"{A}:V1", final.revision_id, "manual_pending", None),
        (f"{A}:V2", final.revision_id, "manual_pending", None),
    ]
    assert checks[1][3:5] == (True, f"MANUAL_PENDING: {AUTHORED_CHECK}")
