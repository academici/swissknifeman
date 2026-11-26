"""Two releases of the shipped CLI, with an isolated migration package for release N."""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import tomllib
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile, copytree
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from starlette.routing import Route

from skm.adapters.postgres.core.schema_version import SchemaCompatibility, SchemaVersionReader
from skm.adapters.postgres.migrations import runner
from skm.kernel.json_types import JsonObject
from skm.platform.config.bootstrap import BOOTSTRAP_URN
from skm.platform.system_clock import SystemClock

if TYPE_CHECKING:
    from support.processes import Instance, ManagedProcess

__all__ = ["CURRENT", "FIXTURES", "PREVIOUS", "Release", "Upgrade", "wait_for"]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "upgrade"
_VERSIONS = tomllib.loads((FIXTURES / "versions.toml").read_text())
_ENTRY = "from support.upgrade import release_cli; raise SystemExit(release_cli())"


@dataclass(frozen=True)
class Release:
    version: str
    schema: int
    compiler: int


PREVIOUS = Release(**_VERSIONS["previous"])
CURRENT = Release(**_VERSIONS["current"])


def wait_for[T](probe: Callable[[], T | None], description: str, *, timeout: float = 25) -> T:
    deadline = monotonic() + timeout
    while True:
        value = probe()
        if value is not None:
            return value
        if monotonic() >= deadline:
            raise AssertionError(f"Timed out waiting for {description}")
        sleep(0.08)


@dataclass
class Service:
    process: ManagedProcess
    stdout: Path
    stderr: Path
    trace: Path

    def logs(self) -> str:
        return self.stdout.read_text(errors="replace") + self.stderr.read_text(errors="replace")

    def stop(self) -> None:
        code = self.process.stop(signal.SIGTERM)
        assert code == 0, self.logs()

    def cleanup(self) -> None:
        self.process.stop(signal.SIGTERM)

    def events(self) -> list[str]:
        return self.trace.read_text().splitlines() if self.trace.exists() else []

    def compiled_runs(self) -> list[str]:
        return [
            event.removeprefix("compile_run_tasks ")
            for event in self.events()
            if event.startswith("compile_run_tasks ")
        ]


class Upgrade:
    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        self.root = instance.root
        self.dsn = instance.dsn
        profile = instance.bootstrap_path.read_text()
        assert "migrate_on_start = true" in profile
        instance.bootstrap_path.write_text(
            profile.replace("migrate_on_start = true", "migrate_on_start = false")
        )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        self.package = self.root / "release-n-migrations"
        copytree(Path(str(runner._package_root())), self.package)
        (self.migration,) = FIXTURES.glob("0031_*.sql")
        copyfile(self.migration, self.package / self.migration.name)
        assert runner.known_version(runner.discover_migrations()) == PREVIOUS.schema
        assert runner.known_version(runner.discover_migrations(self.package)) == CURRENT.schema
        self.gate = self.root / "hold-after-prepare"
        self.env = {
            "PATH": os.defpath,
            "HOME": str(self.root / "home"),
            "GIT_ALLOW_PROTOCOL": "file",
            "SKM_BOOTSTRAP": str(instance.bootstrap_path),
            "SKM_TEST_FAKE_STATE": str(instance.state_dir),
            "SKM_DATABASE_URL": self.dsn,
            "SKM_WORKSPACE": instance.workspace_id,
        }
        self.app_dsn, self.migrator_dsn = self._database_roles()

    def _database_roles(self) -> tuple[str, str]:
        # Test roles are NOLOGIN. Use libpq's startup role on the disposable clone only.
        database = str(conninfo_to_dict(self.dsn)["dbname"])
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                sql.SQL("GRANT CREATE ON DATABASE {} TO skm_migrator").format(sql.Identifier(database))
            )
            conn.execute("GRANT USAGE, CREATE ON SCHEMA skm_core, skm_execution TO skm_migrator")
            conn.execute("GRANT SELECT, INSERT ON skm_core.schema_migrations TO skm_migrator")
            conn.execute("GRANT SELECT ON skm_core.schema_baseline TO skm_migrator")
        return (
            make_conninfo(self.dsn, options="-c role=skm_app"),
            make_conninfo(self.dsn, options="-c role=skm_migrator"),
        )

    def launch(self, release: Release, *args: str, env: dict[str, str] | None = None) -> Service:
        from support.processes import ManagedProcess

        path = self.root / "logs" / f"{args[0]}-{release.version}-{uuid4().hex[:8]}"
        out, err, trace = (path.with_name(f"{path.name}.{ext}") for ext in ("stdout", "stderr", "trace"))
        variables = dict(self.env if env is None else env)
        variables.update(SKM_UPGRADE_VERSION=release.version, SKM_UPGRADE_TRACE=str(trace))
        if release == CURRENT:
            variables["SKM_UPGRADE_PACKAGE"] = str(self.package)
        proc = ManagedProcess.launch(
            (sys.executable, "-c", _ENTRY, "--json", *args), self.root, variables, out, err
        )
        return Service(proc, out, err, trace)

    def cli(self, release: Release, *args: str, status: int = 0, env: dict[str, str] | None = None) -> Any:
        service = self.launch(release, *args, env=env)
        try:
            wait_for(lambda: True if service.process.exited() else None, f"skm {args[0]}", timeout=60)
        finally:
            code = service.process.stop()
        assert code == status, service.logs()
        return json.loads(service.stdout.read_text())["error" if status else "result"]

    @contextmanager
    def serve(self, release: Release, *, schema: str = "ok") -> Iterator[Service]:
        env = {**self.env, "SKM_DATABASE_URL": self.app_dsn}
        service = self.launch(
            release,
            "--set",
            "api.schema_check_interval_seconds=1",
            "serve",
            "--bind",
            self.url.removeprefix("http://"),
            env=env,
        )
        try:
            with httpx.Client(base_url=self.url, timeout=2, trust_env=False) as client:

                def ready() -> httpx.Response | None:
                    assert not service.process.exited(), service.logs()
                    try:
                        return client.get("/health/ready")
                    except httpx.TransportError:
                        return None

                response = wait_for(ready, "serve readiness")
                assert response.status_code == (200 if schema == "ok" else 503), response.text
                assert response.json()["checks"]["schema"] == schema
            yield service
        finally:
            service.cleanup()

    def raise_minimum_versions(self) -> None:
        config = self.root / "release-n-settings.json"
        config.write_text(json.dumps({"schema": "urn:skm:settings:document:v1", **_VERSIONS["settings"]}))
        self.cli(CURRENT, "config", "import", str(config), "--scope", "instance", "--yes")

    def http_env(self, *, worker_id: str | None = None) -> dict[str, str]:
        if worker_id is None:
            profile = self.root / "owner-http.toml"
            token = self.instance.state_dir / "secrets" / "owner.token"
        else:
            profile = self.root / f"worker-{worker_id}.toml"
            token = self.worker_token(worker_id)
        profile.write_text(
            f'schema = "{BOOTSTRAP_URN}"\ninstance_id = "{self.instance.instance_id}"\n'
            '[access]\nmode = "http"\n[api]\n'
            f'endpoint = "{self.url}/api/v1"\ncredential = "secret://file/{token}"\n'
            f'[paths]\nstate_dir = "{self.instance.state_dir}"\n'
            f'[host]\nid = "{self.instance.host_id}"\nname = "m5"\n'
        )
        env = {**self.env, "SKM_BOOTSTRAP": str(profile)}
        del env["SKM_DATABASE_URL"]
        return env

    def worker_token(self, worker_id: str) -> Path:
        return self.instance.state_dir / "secrets" / "workers" / f"{worker_id}.token"

    @contextmanager
    def worker(self, release: Release, worker_id: str, *, gate: bool = False) -> Iterator[Service]:
        env = self.http_env(worker_id=worker_id)
        if gate:
            env["SKM_UPGRADE_GATE"] = str(self.gate)
        started = SystemClock().now()
        service = self.launch(release, "worker", "start", "--worker", worker_id, "--capacity", "1", env=env)
        try:

            def heartbeat() -> bool | None:
                assert not service.process.exited(), service.logs()
                rows = self.rows(
                    "SELECT 1 FROM skm_workspace.workers WHERE id=%s AND last_heartbeat_at >= %s",
                    worker_id,
                    started,
                )
                return True if rows else None

            wait_for(heartbeat, "worker heartbeat", timeout=45)
            yield service
        finally:
            self.gate.unlink(missing_ok=True)
            service.cleanup()

    def migrate(self) -> None:
        with psycopg.connect(self.dsn) as conn:
            baseline = runner.read_baseline(conn)
            assert baseline == runner.packaged_baseline()
            assert SchemaVersionReader(PREVIOUS.schema).compatibility(conn) is SchemaCompatibility.COMPATIBLE
            assert SchemaVersionReader(CURRENT.schema).compatibility(conn) is SchemaCompatibility.NOT_MIGRATED
        with psycopg.connect(self.migrator_dsn) as conn:
            assert conn.execute("SELECT current_user").fetchone() == ("skm_migrator",)
        result = self.cli(CURRENT, "db", "migrate", "--database-url", self.migrator_dsn)
        assert result["applied"] == [CURRENT.schema]
        assert result["pending"] == []
        with psycopg.connect(self.dsn) as conn:
            assert SchemaVersionReader(PREVIOUS.schema).compatibility(conn) is SchemaCompatibility.TOO_NEW
            current = SchemaVersionReader(CURRENT.schema, files=runner.discover_migrations(self.package))
            assert current.compatibility(conn) is SchemaCompatibility.COMPATIBLE
            assert runner.read_baseline(conn) == baseline
            assert conn.execute(
                "SELECT tableowner FROM pg_tables WHERE schemaname='skm_execution' "
                "AND tablename='upgrade_rehearsal'"
            ).fetchone() == ("skm_migrator",)

    @contextmanager
    def http(self, release: Release, *, worker_id: str | None = None) -> Iterator[httpx.Client]:
        token = (
            self.instance.owner_token
            if worker_id is None
            else self.worker_token(worker_id).read_text().strip()
        )
        with httpx.Client(
            base_url=f"{self.url}/api/v1",
            timeout=8,
            trust_env=False,
            headers={"Authorization": f"Bearer {token}", "SKM-Client-Version": release.version},
        ) as client:
            yield client

    def rows(self, statement: str, *params: object) -> list[tuple[Any, ...]]:
        with psycopg.connect(self.dsn) as conn:
            return conn.execute(statement, params or None).fetchall()  # pyright: ignore[reportArgumentType]

    def database_contents(self) -> dict[str, str]:
        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            tables = conn.execute(
                "SELECT schemaname, tablename FROM pg_tables WHERE schemaname LIKE 'skm\\_%' ORDER BY 1, 2"
            ).fetchall()
            contents = {}
            for schema, table in tables:
                row = conn.execute(
                    sql.SQL(
                        "SELECT md5(coalesce(string_agg(r::text, '' ORDER BY r::text), '')) FROM {} AS r"
                    ).format(sql.Identifier(schema, table))
                ).fetchone()
                assert row is not None
                contents[f"{schema}.{table}"] = row[0]
            return contents


def release_cli() -> int:
    """Install only release resources and observation hooks before loading the entrypoint."""
    import skm

    version = os.environ["SKM_UPGRADE_VERSION"]
    skm.__version__ = version
    trace = Path(os.environ["SKM_UPGRADE_TRACE"])

    def record(event: str) -> None:
        with trace.open("a") as stream:
            stream.write(event + "\n")

    from skm.modules.execution.domain import task_graph

    real_compile = task_graph.compile_run_tasks

    def compile_run_tasks(*args: Any, **kwargs: Any) -> task_graph.CompiledRunTasks:
        record(f"compile_run_tasks {kwargs['run_id']}")
        return real_compile(*args, **kwargs)

    with ExitStack() as seams:
        # Install before the CLI loads the handlers that import the run-task compiler directly.
        seams.enter_context(patch.object(task_graph, "compile_run_tasks", compile_run_tasks))
        if package := os.environ.get("SKM_UPGRADE_PACKAGE"):
            seams.enter_context(patch.object(runner, "_package_root", return_value=Path(package)))
            from skm.modules.planning.domain import compile_graph

            seams.enter_context(patch.object(compile_graph, "COMPILER_VERSION", CURRENT.compiler))
        from skm.adapters.http_client.client import HttpSkmClient
        from skm.background.service_runner import ServiceRunner, _State
        from skm.entrypoints.api import app as api_app
        from skm.modules.execution.application._worker_dtos import RecordStageResult
        from support.processes import _cli_main

        real_start, real_run, real_app = ServiceRunner.start, ServiceRunner._run, api_app.create_app
        dispatch = HttpSkmClient.dispatch

        def start(service: ServiceRunner) -> None:
            real_start(service)
            record("background started")
            for name in service.health():
                record(f"background service {name}")

        def run_service(service: ServiceRunner, name: str, state: _State) -> None:
            try:
                real_run(service, name, state)
            finally:
                record(f"background exited {name}")

        def create_app(*args: Any, **kwargs: Any) -> Any:
            app = real_app(*args, **kwargs)
            for route in app.routes:
                assert isinstance(route, Route), route
                record(f"route {route.path}")
            return app

        def after_prepare(
            client: HttpSkmClient, command: object, *, idempotency_key: str | None = None
        ) -> object:
            result = dispatch(client, command, idempotency_key=idempotency_key)
            if isinstance(command, RecordStageResult) and gate.exists():
                next_stage = cast("JsonObject", result)["next"]
                if isinstance(next_stage, dict) and next_stage.get("stage_type") == "agent_step":
                    record("prepare committed")
                    wait_for(lambda: True if not gate.exists() else None, "operator release", timeout=180)
            return result

        seams.enter_context(patch.object(ServiceRunner, "start", start))
        seams.enter_context(patch.object(ServiceRunner, "_run", run_service))
        seams.enter_context(patch.object(api_app, "create_app", create_app))
        if hold := os.environ.get("SKM_UPGRADE_GATE"):
            gate = Path(hold)
            seams.enter_context(patch.object(HttpSkmClient, "dispatch", after_prepare))
        return _cli_main()
