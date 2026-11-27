"""Exercise the server Compose deployment through its real CLI, database and HTTP surfaces."""

from __future__ import annotations

import inspect
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import time
from base64 import b64encode
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime
from importlib.metadata import distribution
from io import BytesIO
from pathlib import Path, PurePosixPath
from secrets import token_hex
from types import SimpleNamespace
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest

from e2e.test_http_worker import _worker_subprocess
from fixtures.execution.protocol import AUTHOR
from fixtures.execution.single_run import successful_script
from integration.git.conftest import make_repo

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]
STATE = "/var/lib/skm"
VERSION = {"SKM-Client-Version": "2.0.0"}


@dataclass(frozen=True)
class Stack:
    project: str
    env: dict[str, str] = field(repr=False)
    url: str
    override: Path | None = None

    def compose(
        self, *args: str, input_text: str | None = None, timeout: int = 120
    ) -> subprocess.CompletedProcess[str]:
        return self.docker(
            "compose",
            "-p",
            self.project,
            "-f",
            "deploy/compose.yaml",
            *(("-f", str(self.override)) if self.override else ()),
            *args,
            input_text=input_text,
            timeout=timeout,
        )

    def docker(
        self, *args: str, input_text: str | None = None, timeout: int = 120
    ) -> subprocess.CompletedProcess[str]:
        docker = shutil.which("docker")
        assert docker, "Docker with the Compose plugin is required"
        return subprocess.run(
            [docker, *args],
            cwd=ROOT,
            env=self.env,
            input=input_text,
            capture_output=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )

    def run(self, *args: str, input_text: str | None = None, timeout: int = 120) -> str:
        result = self.compose(*args, input_text=input_text, timeout=timeout)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    def inspect(self, service: str) -> dict[str, Any]:
        containers = self.run("ps", "-a", "-q", service).splitlines()
        assert containers
        result = self.docker("inspect", *containers)
        assert result.returncode == 0, result.stderr
        return next(
            info
            for info in json.loads(result.stdout)
            if info["Config"]["Labels"].get("com.docker.compose.oneoff", "").lower() != "true"
        )


@pytest.fixture
def stack(pytestconfig: pytest.Config) -> Iterator[Stack]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    project = f"skm-compose-{uuid4().hex[:10]}"
    values = {
        "SKM_PG_ADMIN_PASSWORD": token_hex(24),
        "SKM_PG_MIGRATOR_PASSWORD": token_hex(24),
        "SKM_PG_APP_PASSWORD": token_hex(24),
        "SKM_API_PORT": str(port),
        "SKM_API_ALLOWED_HOSTS": json.dumps(["api:8765", "127.0.0.1:8765", f"127.0.0.1:{port}"]),
        "SKM_IMAGE_TAG": project,
        "COMPOSE_PROGRESS": "plain",
    }
    env = {**os.environ, **values}
    # Keep the Docker context available while pytest isolates HOME for SKM.
    controls = pytestconfig.pluginmanager.get_plugin(str(ROOT / "tests/conftest.py"))
    assert controls is not None
    host_home = pytestconfig.stash[controls.CONTROLS].host_home
    docker_config = env.setdefault("DOCKER_CONFIG", str(Path(host_home or env["HOME"]) / ".docker"))
    if (
        not (env.get("DOCKER_HOST") or env.get("DOCKER_CONTEXT"))
        and not (Path(docker_config) / "config.json").is_file()
        and not Path("/var/run/docker.sock").is_socket()
    ):
        socket_path = Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / "docker.sock"
        if socket_path.is_socket():
            env["DOCKER_HOST"] = f"unix://{socket_path}"
    deployment = Stack(project, env, f"http://127.0.0.1:{port}")
    try:
        yield deployment
    finally:
        deployment.run("--profile", "setup", "down", "-v", "--remove-orphans")


def eventually(check: Callable[[], Any], *, timeout: int = 40) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if value := check():
            return value
        time.sleep(0.25)
    pytest.fail("condition did not become true before timeout")


def inspect_layers(stack: Stack, tmp_path: Path) -> None:
    archive = tmp_path / "images.tar"
    tag = stack.env["SKM_IMAGE_TAG"]
    builds = (f"skm-api:{tag}", f"skm-worker:{tag}")
    result = stack.docker(
        "image",
        "save",
        "-o",
        str(archive),
        *builds,
    )
    assert result.returncode == 0, result.stderr
    # The pinned Bookworm worker base ships these Debian package examples and tests.
    base_tests = (
        "usr/share/doc/git/contrib/coccinelle/tests",
        "usr/share/doc/ucf/examples/ucf_helper_functions/tests",
        "usr/share/mercurial/tests",
    )
    with tarfile.open(archive) as images:
        entries = json.load(images.extractfile("manifest.json"))  # type: ignore[arg-type]
        for name in {layer for entry in entries for layer in entry["Layers"]}:
            content = images.extractfile(name)
            assert content is not None
            with tarfile.open(fileobj=content, mode="r|*") as layer:
                for member in layer:
                    path = PurePosixPath(member.name)
                    forbidden = {".git", ".env", ".codex", ".pgpass", "working"}
                    assert not forbidden.intersection(path.parts), member.name
                    assert "tests" not in path.parts or any(path.is_relative_to(p) for p in base_tests), path
                    assert path.name not in {"owner.token", "worker.token", "token-pepper"}, member.name
    for image in builds:
        history = stack.docker("image", "history", "--no-trunc", image)
        assert history.returncode == 0, history.stderr
        assert all(
            secret not in history.stdout for key, secret in stack.env.items() if key.endswith("_PASSWORD")
        )


def check_topology(stack: Stack) -> None:
    postgres, migrate, api, worker = (
        stack.inspect(name) for name in ("postgres", "migrate", "api", "worker")
    )
    assert not postgres["HostConfig"]["PortBindings"]
    assert not worker["HostConfig"]["PortBindings"]
    assert set(postgres["NetworkSettings"]["Networks"]).isdisjoint(worker["NetworkSettings"]["Networks"])
    assert migrate["State"]["ExitCode"] == 0
    assert migrate["State"]["FinishedAt"] < api["State"]["StartedAt"]
    assert migrate["HostConfig"]["RestartPolicy"]["Name"] == "no"
    assert {"127.0.0.1"} == {port["HostIp"] for port in api["HostConfig"]["PortBindings"]["8765/tcp"]}
    for service in ("postgres", "api", "worker"):
        assert int(stack.run("exec", "-T", service, "id", "-u")) != 0
    assert all(mount["Type"] == "volume" for mount in api["Mounts"])
    assert [mount["Destination"] for mount in api["Mounts"]] == [STATE]
    assert [mount["Destination"] for mount in worker["Mounts"]] == [STATE]
    assert api["Mounts"][0]["Name"] != worker["Mounts"][0]["Name"]
    assert stack.env["SKM_PG_MIGRATOR_PASSWORD"] not in str(api["Config"])
    assert {item.split("=")[0] for item in worker["Config"]["Env"] if item.startswith(("SKM_", "PG"))} == {
        "SKM_BOOTSTRAP",
        "SKM_WORKSPACE",
    }
    stack.run("exec", "-T", "worker", "sh", "-ec", 'test "$(stat -c %a worker.token)" = 600')
    # Check actual sockets in the worker namespace, including IPv6. 0A is TCP_LISTEN.
    stack.run(
        "exec",
        "-T",
        "worker",
        "python",
        "-c",
        "import os; from pathlib import Path; assert not any("
        "row.split()[3] == '0A' and int(row.split()[7]) == os.getuid() "
        "for file in Path('/proc/net').glob('tcp*') "
        "for row in file.read_text().splitlines()[1:])",
    )


def check_database_roles(stack: Stack) -> None:
    stack.run(
        "exec",
        "-T",
        "api",
        "python",
        "-",
        input_text="""
import os
import psycopg
from psycopg.errors import InsufficientPrivilege

with psycopg.connect(os.environ["SKM_DATABASE_URL"], autocommit=True) as conn:
    assert conn.execute("SELECT current_user, current_database()").fetchone() == (
        "skm_app_login", "skm_projects"
    )
    assert conn.execute(
        "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='skm_core.schema_migrations'::regclass"
    ).fetchone() == ("skm_migrator_login",)
    assert conn.execute("SELECT pg_has_role(current_user, 'skm_app', 'USAGE'), "
                        "pg_has_role(current_user, 'skm_migrator', 'MEMBER')").fetchone() == (True, False)
    assert conn.execute("SELECT rolname, rolcanlogin FROM pg_roles "
                        "WHERE rolname IN ('skm_app', 'skm_migrator', 'skm_migrator_login') "
                        "ORDER BY rolname").fetchall() == [
        ("skm_app", False), ("skm_migrator", False), ("skm_migrator_login", True)
    ]
    assert conn.execute("SELECT pg_has_role('skm_migrator_login', 'skm_migrator', 'USAGE'), "
                        "pg_has_role('skm_migrator_login', 'skm_app', 'MEMBER')").fetchone() == (True, False)
    assert conn.execute(
        "SELECT NOT EXISTS (SELECT FROM pg_database WHERE datname = 'skm_host'), "
        "NOT EXISTS (SELECT FROM pg_roles WHERE rolname LIKE 'skm_host%')"
    ).fetchone() == (True, True)
    assert conn.execute("SELECT count(*) FROM skm_core.schema_migrations").fetchone()[0] > 0
    for statement in (
        "CREATE TABLE public.forbidden (id int)",
        "CREATE TABLE skm_core.forbidden (id int)",
        "CREATE TEMP TABLE forbidden (id int)",
        "CREATE SCHEMA forbidden",
        "INSERT INTO skm_core.schema_migrations SELECT * FROM skm_core.schema_migrations WHERE false",
        "UPDATE skm_core.schema_migrations SET name = name",
        "DELETE FROM skm_core.schema_migrations",
        "TRUNCATE skm_core.schema_migrations",
    ):
        try:
            conn.execute(statement)
        except InsufficientPrivilege:
            continue
        raise AssertionError(statement)
""",
    )


def register_worker(http: httpx.Client, workspace: str) -> tuple[str, str, str]:
    host = http.post(
        "/api/v1/hosts", json={"name": "compose-worker", "platform": {"os": "linux", "arch": "x86_64"}}
    )
    assert host.status_code == 201, host.text
    host_id = host.json()["host_id"]
    result = http.post(
        f"/api/v1/workspaces/{workspace}/workers",
        json={
            "host_id": host_id,
            "display_name": "compose-worker",
            "capabilities": {
                "runtimes": [],
                "isolation_profiles": ["worktree"],
                "labels": [],
                "max_concurrency": 1,
                "platform": {"os": "linux", "arch": "x86_64"},
                "skm_version": "2.0.0",
            },
        },
    )
    assert result.status_code == 201, result.text
    return host_id, result.json()["worker_id"], result.json()["token_secret"]


def provision_worker(stack: Stack, instance: str, workspace: str, http: httpx.Client) -> str:
    host, worker, token = register_worker(http, workspace)
    stack.env["SKM_WORKER_WORKSPACE"] = workspace
    bootstrap = f'''schema = "urn:skm:config:bootstrap:v1"
instance_id = "{instance}"
[access]
mode = "http"
[api]
endpoint = "http://api:8765/api/v1"
credential = "secret://file/{STATE}/worker.token"
[host]
id = "{host}"
[paths]
state_dir = "{STATE}"
'''
    stack.run(
        "run",
        "--no-deps",
        "-T",
        "--entrypoint",
        "python",
        "worker",
        "-c",
        "import json, sys; from pathlib import Path; "
        "files = json.load(sys.stdin); "
        "[(Path(name).write_text(text), Path(name).chmod(0o600)) for name, text in files.items()]",
        input_text=json.dumps({"bootstrap.toml": bootstrap, "worker.token": token + "\n"}),
    )
    stack.run("up", "-d", "--no-deps", "worker")
    return worker


def worker_heartbeat(http: httpx.Client, workspace: str, worker: str) -> datetime | None:
    response = http.get(f"/api/v1/workspaces/{workspace}/workers")
    response.raise_for_status()
    timestamp = next(
        item["last_heartbeat_at"] for item in response.json()["items"] if item["worker_id"] == worker
    )
    return datetime.fromisoformat(timestamp) if timestamp else None


def with_fake_catalog(stack: Stack, tmp_path: Path) -> Stack:
    # The default API deliberately advertises only real runtime adapters.
    # Add the fixture's capability data to the real CLI server for the synthetic run.
    serve = """
from pathlib import Path

from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.bootstrap import composition
from skm.bootstrap.plugin_distribution import RuntimeDataFiles
from skm.entrypoints.cli.main import main

fake = FakeRuntime(state_dir=Path("/tmp"), scenario=Path("/tmp/unused"))
data = RuntimeDataFiles("fake", fake.capabilities(), (), "compose-test", "compose-test")
catalog = (*composition.builtin_runtime_data(), data)
composition.builtin_runtime_data = lambda: catalog
raise SystemExit(main(["serve", "--bind", "0.0.0.0:8765"]))
"""
    override = tmp_path / "fake-runtime.yaml"
    override.write_text(
        json.dumps({"services": {"api": {"entrypoint": ["python", "-c", serve], "command": []}}})
    )
    return replace(stack, override=override)


_SEED_FAKE_RUN = """
import json
import os
import sys
import tomllib
from base64 import b64decode
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from zipfile import ZipFile

from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.bootstrap.composition_resources import token_pepper
from skm.kernel.ids import ScopeId
from skm.platform.config.bootstrap import load_bootstrap


def seed(root, owner, worker_python):
    from contracts.execution import harness as contracts
    from fixtures.execution import harness, m3
    from skm.modules.execution.ports import TaskRepository
    from unit.execution.application._support import set_setting

    boot = load_bootstrap(None, os.environ, Path.home())
    harness.load_bootstrap = lambda *args: boot
    harness.SEED = replace(harness.SEED, instance_id=ScopeId(boot.instance_id))
    contracts.PEPPER = harness.PEPPER = token_pepper(boot, os.environ)
    m3.sys = SimpleNamespace(executable=worker_python)

    def existing_owner(app, *args, **kwargs):
        now = harness._Cache.value.clock.now()
        meta = harness.RequestMeta("compose-fixture-owner", harness.Surface.CLI, None, now)
        with app.uow_factory(meta, readonly=True) as uow:
            return harness.authenticate_token(uow, owner, pepper=harness.PEPPER, now=now)

    harness.seed_principals = existing_owner

    pack = harness._pack()
    # The live stack already installed its built-in core. Give the fake workflow a newer version.
    builtin_manifests = [
        tomllib.loads(payload.manifest_text) for payload in PackagedBuiltinPacks().payloads()
    ]
    core_major = max(
        int(manifest["version"].split(".")[0])
        for manifest in builtin_manifests
        if manifest["slug"] == "core"
    )
    fixture_version = f"{core_major + 1}.0.0"
    harness._pack = lambda: harness.pack_payload(
        "core", fixture_version,
        files={file.path: file.content.decode().replace("1.3.0", fixture_version) for file in pack.files},
    )
    side = harness.recovery.__wrapped__(
        SimpleNamespace(session=SimpleNamespace(addfinalizer=lambda _: None)),
        root, SimpleNamespace(getbasetemp=lambda: root),
        SimpleNamespace(dsn=os.environ["SKM_DATABASE_URL"]),
    )
    try:
        set_setting(side, "worker.disk_min_bytes", 0)
        run = m3.start(side, m3.dag(side), keys=("P1.1",))
        harness.system_dispatch(side, "schedule_ready_tasks")
        with side.uow(readonly=True) as uow:
            (task,) = uow.repo(TaskRepository).list_for_run(run.run_id)
        return {
            "app": {"instance_id": str(side.app.instance_id)},
            "run_id": str(run.run_id), "key": task.display_key,
            "host1": str(side.host1), "worker1": str(side.worker1), "ws": str(side.ws),
            "repo_id": str(side.repo_id), "secret": side.secret,
        }
    finally:
        side.app.close()


fixture = json.load(sys.stdin)
with TemporaryDirectory() as folder:
    root = Path(folder)
    with ZipFile(BytesIO(b64decode(fixture["archive"]))) as archive:
        archive.extractall(root)
    sys.path.insert(0, str(root / "tests"))
    print(json.dumps(seed(root, fixture["owner"], fixture["worker_python"])))
"""


def fixture_archive() -> str:
    """Send test-side helpers over stdin for seeding, outside the shipped image and state volumes."""
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for directory in ("contracts", "fixtures", "fakes", "integration", "security", "support", "unit"):
            for file in (ROOT / "tests" / directory).rglob("*.py"):
                archive.write(file, file.relative_to(ROOT))
        for file in (
            "tests/fixtures/corpus/examples/execution/workflows/quick-fix.toml",
            "tests/fixtures/runtimes/fake/review-green.toml",
        ):
            archive.write(ROOT / file, file)
        for name in ("pytest", "pluggy", "iniconfig", "packaging", "pygments"):
            package = distribution(name)
            for entry in package.files or ():
                if entry.suffix == ".py" and ".." not in entry.parts:
                    archive.write(str(package.locate_file(entry)), "tests" / entry)
    return b64encode(buffer.getvalue()).decode()


def run_laptop_worker(
    side: Any, endpoint: str, repository: Path, scenario: Path
) -> subprocess.CompletedProcess[str]:
    remote = side.root / "laptop"
    state = remote / "state"
    state.mkdir(mode=0o700, parents=True)
    token = remote / "worker.token"
    token.write_text(side.secret + "\n")
    token.chmod(0o600)
    profile = remote / "bootstrap.toml"
    profile.write_text(f'''schema = "urn:skm:config:bootstrap:v1"
instance_id = "{side.app.instance_id}"
[access]
mode = "http"
[api]
endpoint = "{endpoint}/api/v1"
credential = "secret://file/{token}"
[host]
id = "{side.host1}"
[paths]
state_dir = "{state}"
''')
    data = remote / "assignment.json"
    data.write_text(
        json.dumps(
            {
                "state": str(state),
                "repository": str(repository),
                "script": str(scenario),
                "repository_id": side.repo_id,
                "run_id": side.run_id,
                "request": {
                    "workspace_id": side.ws,
                    "host_id": side.host1,
                    "worker_id": side.worker1,
                    "offer": {
                        "capabilities": ["fake"],
                        "labels": ["linux"],
                        "environment_kinds": ["git_worktree"],
                        "isolation_profiles": ["worktree", "landlock"],
                    },
                    "once": True,
                    "max_assignments": 1,
                    "max_wait_seconds": 15,
                },
            }
        )
    )
    env = {key: value for key, value in os.environ.items() if not key.startswith(("SKM_", "PG"))}
    env.update(HOME=str(remote), PYTHONPATH=str(ROOT / "tests"), SKM_BOOTSTRAP=str(profile))
    code = (
        "import sys\n"
        + inspect.getsource(_worker_subprocess)
        + "\nraise SystemExit(_worker_subprocess(sys.argv[1]))"
    )
    return subprocess.run(
        [sys.executable, "-c", code, str(data)],
        cwd=remote,
        env=env,
        text=True,
        capture_output=True,
        timeout=100,
        check=False,
    )


def complete_fake_run(stack: Stack, http: httpx.Client, tmp_path: Path, owner: str) -> dict[str, Any]:
    fixture = stack.run(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        _SEED_FAKE_RUN,
        input_text=json.dumps(
            {"archive": fixture_archive(), "owner": owner, "worker_python": sys.executable}
        ),
    )
    data = json.loads(fixture)
    side = SimpleNamespace(**{**data, "app": SimpleNamespace(**data["app"]), "root": tmp_path})
    repository = tmp_path / "fake-repository"
    git, _ = make_repo(repository)
    (repository / "src").mkdir()
    (repository / "src/target.py").write_text("answer = 0\n")
    git.run(repository, ["add", "."])
    git.run_bytes(repository, ["commit", "-m", "fake-run baseline"], env=AUTHOR)
    git.run(repository, ["branch", f"skm/integration/{side.run_id}", "main"])
    before = http.get(f"/api/v1/runs/{side.run_id}").raise_for_status().json()
    assert before["status"] == "running"
    result = run_laptop_worker(side, stack.url, repository, successful_script(side, side.key))
    assert side.secret not in result.stdout + result.stderr
    assert owner not in result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    after = http.get(f"/api/v1/runs/{side.run_id}").raise_for_status().json()
    assert after["status"] == "succeeded", (after, result.stdout, result.stderr)
    assert after["bundle_digest"] == before["bundle_digest"]
    assert (
        git.run(repository, ["show", f"skm/integration/{side.run_id}:src/target.py"]).stdout.strip()
        == "answer = 42"
    )
    return after


def test_server_compose(stack: Stack, tmp_path: Path) -> None:
    config = json.loads(stack.run("config", "--format", "json"))
    services = config["services"]
    assert services["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert not services["postgres"].get("ports")
    assert not services["worker"].get("ports")
    worker_dockerfile = (ROOT / services["worker"]["build"]["dockerfile"]).read_text()
    worker_base = worker_dockerfile.splitlines()[0].split()[1]
    inventory = (ROOT / "docs/guides/server-mode.md").read_text()
    assert "@sha256:" in worker_base
    assert f"`{worker_base}`" in inventory
    assert all(
        line.startswith("RUN --network=none ")
        for line in worker_dockerfile.splitlines()
        if line.startswith("RUN ")
    )
    stack.run("build", timeout=900)
    inspect_layers(stack, tmp_path)
    stack.run("up", "-d", "init")
    stack.run("wait", "init")
    owner_file = tmp_path / "owner.token"
    stack.run("cp", f"init:{STATE}/secrets/owner.token", str(owner_file))
    owner = owner_file.read_text().strip()
    with httpx.Client(base_url=stack.url, headers={**VERSION, "Authorization": f"Bearer {owner}"}) as http:
        stack.run("up", "-d", "--wait", "api")
        workspace = http.get("/api/v1/workspaces").json()["items"][0]["workspace_id"]
        instance = stack.run(
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import tomllib; print(tomllib.load(open('bootstrap.toml','rb'))['instance_id'])",
        ).strip()
        check_database_roles(stack)
        worker = provision_worker(stack, instance, workspace, http)
        eventually(lambda: worker_heartbeat(http, workspace, worker))
        check_topology(stack)
        stack.run("exec", "-T", "worker", "git", "--version")
        git_package = stack.run("exec", "-T", "worker", "dpkg-query", "-W", "-f=${Package} ${Version}", "git")
        assert f"`{git_package}`" in inventory
        fake_stack = with_fake_catalog(stack, tmp_path)
        fake_stack.run("up", "-d", "--no-deps", "--wait", "api")
        completed = complete_fake_run(fake_stack, http, tmp_path, owner)
        fake_stack.run("restart", "api")
        fake_stack.run("up", "-d", "--no-deps", "--wait", "api")
        fake_stack.run("restart", "worker")
        started_at = datetime.fromisoformat(fake_stack.inspect("worker")["State"]["StartedAt"])
        eventually(
            lambda: (
                (heartbeat := worker_heartbeat(http, workspace, worker)) is not None
                and heartbeat > started_at
            )
        )
        run = http.get(f"/api/v1/runs/{completed['run_id']}").raise_for_status().json()
        assert run["status"] == "succeeded"
        assert run["bundle_digest"] == completed["bundle_digest"]
        assert run["row_version"] == completed["row_version"]
