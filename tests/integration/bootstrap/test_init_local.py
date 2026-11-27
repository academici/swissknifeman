"""``skm init`` and ``skm local`` as real subprocesses in an isolated sandbox.

Every subprocess gets explicit ``HOME``/``XDG_CONFIG_HOME``/``XDG_STATE_HOME``/``XDG_DATA_HOME`` under
``tmp_path``: the user's bootstrap is never read and no real owner or pepper file is written; the secrets go
away with the sandbox directory. Docker is never called: ``skm local`` runs either with no ``docker`` on
``PATH`` or with a fake ``docker`` script that records its argv. The PostgreSQL cases create their own scratch
database from ``SKM_TEST_DATABASE_URL`` (loopback and ``*_test`` only) and drop it afterwards.
"""

import json
import os
import socket
import stat
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from skm.adapters.postgres.migrations.runner import discover_migrations
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.adapters.secrets.file import FileSecretResolver
from skm.bootstrap.local_postgres import (
    ManagedPostgres,
    managed_postgres,
    mark_managed_postgres,
    provision_local_postgres,
)
from skm.entrypoints.cli.commands import GROUPS
from skm.entrypoints.cli.commands import init as init_module
from skm.entrypoints.cli.commands import local as local_module
from skm.platform.config.bootstrap import load_bootstrap

ROOT = Path(__file__).resolve().parents[3]
ENTRY = "import sys; from skm.entrypoints.cli.main import main; sys.exit(main())"
# Only what the interpreter needs; HOME and XDG always point into the sandbox.
PASSED = ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "TMPDIR")
PASSWORD = "hunter2-init-secret"


@dataclass(frozen=True)
class Sandbox:
    root: Path

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def bootstrap(self) -> Path:
        return self.root / "config/skm/bootstrap.toml"

    @property
    def state(self) -> Path:
        return self.root / "state/skm"

    @property
    def secrets(self) -> Path:
        return self.state / "secrets"

    @property
    def pepper(self) -> Path:
        return self.secrets / "token-pepper"

    def env(self, **extra: str) -> dict[str, str]:
        env = {name: os.environ[name] for name in PASSED if name in os.environ}
        env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_STATE_HOME=str(self.root / "state"),
            XDG_DATA_HOME=str(self.root / "data"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        env.update(extra)
        return env


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    box = Sandbox(tmp_path / "sandbox")
    box.home.mkdir(parents=True)
    return box


def skm(box: Sandbox, *argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", ENTRY, *argv],
        env=box.env() if env is None else env,
        cwd=box.root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def envelope(done: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(done.stdout))


def unreachable_dsn() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"postgresql://skm:{PASSWORD}@127.0.0.1:{port}/nodb?connect_timeout=2"


def mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def files_under(path: Path) -> list[Path]:
    return sorted(item for item in path.rglob("*")) if path.exists() else []


# --- declarations ----------------------------------------------------------------------------------


def test_init_and_local_are_discovered_local_groups() -> None:
    groups = {group.name: group for group in GROUPS}
    assert groups["init"] is init_module.GROUP
    assert groups["local"] is local_module.GROUP
    assert not groups["init"].requires_backend  # no fake authorization: init runs before any principal exists
    assert not groups["local"].requires_backend


def test_the_compose_file_is_packaged_self_contained_and_loopback_only() -> None:
    compose = local_module.compose_file()
    assert compose == ROOT / "deploy/compose.local.yaml"
    text = compose.read_text(encoding="utf-8")
    assert "name: skm-local" in text
    assert '"127.0.0.1:${SKM_LOCAL_PG_PORT:?}:5432"' in text
    assert "pg_isready" in text
    assert "./" not in text  # no bind mount: the wheel ships this one file
    wheel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]
    assert "deploy/compose.local.yaml" in wheel["targets"]["wheel"]["only-include"]
    assert wheel["targets"]["wheel"]["sources"]["deploy"] == "skm/_deploy"


# --- skm init without a database -------------------------------------------------------------------


def test_managed_init_without_docker_fails_before_writing_secrets(sandbox: Sandbox, tmp_path: Path) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    done = skm(sandbox, "--json", "init", env=sandbox.env(PATH=str(empty)))
    assert done.returncode == 3, done.stderr
    assert envelope(done)["error"]["code"] == "BACKEND_UNAVAILABLE"
    assert files_under(sandbox.root / "config") == []
    assert files_under(sandbox.root / "state") == []


def test_an_unreachable_database_writes_nothing_and_hides_the_password(sandbox: Sandbox) -> None:
    done = skm(sandbox, "--json", "init", "--database-url", unreachable_dsn())
    assert done.returncode == 3, done.stderr
    assert envelope(done)["error"]["code"] == "BACKEND_UNAVAILABLE"
    assert PASSWORD not in done.stdout + done.stderr
    assert files_under(sandbox.root / "config") == []
    assert files_under(sandbox.root / "state") == []  # the database is asked before anything is created


def _bad_pepper_mode(box: Sandbox) -> None:
    box.secrets.mkdir(parents=True, mode=0o700)
    box.pepper.write_text("ab" * 32 + "\n", encoding="ascii")
    box.pepper.chmod(0o644)


def _group_readable_pepper(box: Sandbox) -> None:
    box.secrets.mkdir(parents=True, mode=0o700)
    box.pepper.write_text("ab" * 32 + "\n", encoding="ascii")
    box.pepper.chmod(0o640)


def _open_secrets_dir(box: Sandbox) -> None:
    box.secrets.mkdir(parents=True)
    box.secrets.chmod(0o755)


def _symlinked_pepper(box: Sandbox) -> None:
    box.secrets.mkdir(parents=True, mode=0o700)
    target = box.root / "elsewhere"
    target.write_text("ab" * 32 + "\n", encoding="ascii")
    target.chmod(0o600)
    box.pepper.symlink_to(target)


def _short_pepper(box: Sandbox) -> None:
    box.secrets.mkdir(parents=True, mode=0o700)
    box.pepper.write_text("short\n", encoding="ascii")
    box.pepper.chmod(0o600)


@pytest.mark.parametrize(
    ("prepare", "code", "reason"),
    [
        (_bad_pepper_mode, "SECRET_PERMISSIONS", "mode"),
        (_group_readable_pepper, "SECRET_PERMISSIONS", "mode"),
        (_open_secrets_dir, "SECRET_PERMISSIONS", "mode"),
        (_symlinked_pepper, "SECRET_PERMISSIONS", "symlink"),
        (_short_pepper, "SECRET_UNAVAILABLE", "too_short"),
    ],
)
def test_wrong_secret_storage_is_refused_and_left_untouched(
    sandbox: Sandbox, prepare: Any, code: str, reason: str
) -> None:
    prepare(sandbox)
    before = {
        path: (mode(path), path.read_bytes() if path.is_file() else b"")
        for path in files_under(sandbox.state)
    }
    secrets_mode = mode(sandbox.secrets)
    done = skm(sandbox, "--json", "init", "--database-url", unreachable_dsn())
    assert done.returncode == 6, done.stdout + done.stderr  # refused before the database is contacted
    error = envelope(done)["error"]
    assert (error["code"], error["details"]["reason"]) == (code, reason)
    after = {
        path: (mode(path), path.read_bytes() if path.is_file() else b"")
        for path in files_under(sandbox.state)
    }
    assert after == before  # never repaired, replaced or chmod-ed
    assert mode(sandbox.secrets) == secrets_mode
    assert not sandbox.bootstrap.exists()


def _write_profile(box: Sandbox, state: Path) -> bytes:
    text = (
        'schema = "urn:skm:config:bootstrap:v1"\n'
        f'instance_id = "{uuid4()}"\n\n'
        '[access]\nmode = "embedded"\n\n'
        '[database]\nurl = "secret://env/SKM_DATABASE_URL"\n\n'
        f'[secrets]\ntoken_pepper = "secret://file/{state}/secrets/token-pepper"\n\n'
        f'[paths]\nstate_dir = "{state}"\n'
    )
    box.bootstrap.parent.mkdir(parents=True)
    box.bootstrap.write_text(text, encoding="utf-8")
    return box.bootstrap.read_bytes()


def test_an_existing_profile_keeps_its_state_dir(sandbox: Sandbox) -> None:
    original = _write_profile(sandbox, sandbox.state)
    other = sandbox.root / "other-state"
    done = skm(sandbox, "--json", "init", "--database-url", unreachable_dsn(), "--state-dir", str(other))
    assert done.returncode == 1, done.stderr
    error = envelope(done)["error"]
    assert (error["code"], error["details"]["reason"]) == ("CONFIG_INVALID", "differs_from_bootstrap")
    assert sandbox.bootstrap.read_bytes() == original
    assert not other.exists()


# --- skm local without Docker ----------------------------------------------------------------------


@pytest.mark.parametrize("verb", ["status", "up", "down"])
def test_local_without_docker_is_a_clear_backend_error(sandbox: Sandbox, tmp_path: Path, verb: str) -> None:
    folder, _ = fake_docker(tmp_path)
    managed_fixture(sandbox, folder)
    empty = tmp_path / "no-docker-bin"
    empty.mkdir()
    done = skm(sandbox, "local", verb, env=sandbox.env(PATH=str(empty)))
    assert done.returncode == 3, done.stdout + done.stderr
    assert "BACKEND_UNAVAILABLE" in done.stderr
    assert "Docker is not available" in done.stderr
    assert "hint: install Docker" in done.stderr
    assert done.stdout == ""
    data = envelope(skm(sandbox, "--json", "local", verb, env=sandbox.env(PATH=str(empty))))
    assert data["command"] == f"cli.local.{verb}"
    assert data["error"]["code"] == "BACKEND_UNAVAILABLE"
    assert data["error"]["details"]["component"] == "postgres"


PS_JSON = (
    '{"Service":"postgres","State":"running","Health":"healthy",'
    '"Publishers":[{"URL":"127.0.0.1","TargetPort":5432,"PublishedPort":54329,"Protocol":"tcp"}]}'
)


def fake_docker(tmp_path: Path, *, exit_code: int = 0, ps: str = PS_JSON) -> tuple[Path, Path]:
    """A ``docker`` that records its argv (one line per call) and answers ``ps`` with canned JSON."""
    folder = tmp_path / "fake-bin"
    folder.mkdir(exist_ok=True)
    log = tmp_path / "docker.argv"
    script = folder / "docker"
    script.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        f"if [ {exit_code} -ne 0 ]; then\n"
        f"  echo 'Cannot connect to the Docker daemon' >&2; exit {exit_code}\n"
        "fi\n"
        f"case \"$*\" in *' ps '*) printf '%s\\n' '{ps}' ;; esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return folder, log


def managed_fixture(sandbox: Sandbox, folder: Path) -> ManagedPostgres:
    server = provision_local_postgres(
        sandbox.state, "standalone", None, sandbox.env(PATH=str(folder)), on_secret=lambda _: None
    )
    sandbox.bootstrap.parent.mkdir(parents=True)
    sandbox.bootstrap.write_text(
        f'schema = "urn:skm:config:bootstrap:v1"\ninstance_id = "{uuid4()}"\n'
        f'installation_id = "{server.installation_id}"\n[access]\nmode = "embedded"\n'
        f'[database]\nurl = "{server.reference("PROJECT_APP")}"\n'
        f'migrator_url = "{server.reference("PROJECT_MIGRATOR")}"\n'
        f'[paths]\nstate_dir = "{sandbox.state}"\n'
    )
    mark_managed_postgres(sandbox.state, server)
    return server


def test_client_postgres_keeps_identity_and_omits_project_dsn_files(sandbox: Sandbox, tmp_path: Path) -> None:
    folder, log = fake_docker(tmp_path)
    env = sandbox.env(PATH=str(folder), SKM_LOCAL_PG_PROJECT_APP="unrelated-project-secret")
    first = provision_local_postgres(sandbox.state, "client", None, env, on_secret=lambda _: None)
    paths = sorted(sandbox.secrets.glob("postgres-*.dsn"))
    before = {path: (path.stat().st_ino, mode(path), path.read_bytes()) for path in paths}
    repeat = provision_local_postgres(
        sandbox.state, "client", first.installation_id, env, on_secret=lambda _: None
    )
    assert (repeat.installation_id, repeat.port) == (first.installation_id, first.port)
    assert [path.name for path in paths] == ["postgres-machine-app.dsn", "postgres-machine-migrator.dsn"]
    assert {path: (path.stat().st_ino, mode(path), path.read_bytes()) for path in paths} == before
    assert all(permissions == 0o600 for _, permissions, _ in before.values())
    assert "SKM_LOCAL_PG_PROJECT_APP" not in repeat.environment(env, lambda _: None)
    assert all(f"skm-local-{first.installation_id.hex}" in line for line in log.read_text().splitlines())


def test_http_profile_is_refused_before_machine_provisioning(sandbox: Sandbox, tmp_path: Path) -> None:
    sandbox.bootstrap.parent.mkdir(parents=True)
    original = (
        f'schema = "urn:skm:config:bootstrap:v1"\ninstance_id = "{uuid4()}"\n'
        '[access]\nmode = "http"\n[api]\nendpoint = "http://127.0.0.1:1/api/v1"\n'
        'credential = "secret://env/FIXTURE_TOKEN"\n'
    )
    sandbox.bootstrap.write_text(original)
    folder, log = fake_docker(tmp_path)
    result = skm(sandbox, "--json", "init", env=sandbox.env(PATH=str(folder)))
    assert result.returncode == 1
    assert envelope(result)["error"]["code"] == "CONFIG_INVALID"
    assert sandbox.bootstrap.read_text() == original
    assert not sandbox.state.exists()
    assert not log.exists()


def test_local_status_reads_the_packaged_compose_service(sandbox: Sandbox, tmp_path: Path) -> None:
    folder, log = fake_docker(tmp_path)
    server = managed_fixture(sandbox, folder)
    log.write_text("")
    done = skm(sandbox, "local", "status", env=sandbox.env(PATH=str(folder)))
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[1].split() == ["postgres", "running", "127.0.0.1:54329,", "healthy"]
    compose = str(ROOT / "deploy/compose.local.yaml")
    project = f"skm-local-{server.installation_id.hex}"
    assert log.read_text().splitlines() == [
        f"compose --project-name {project} -f {compose} ps --all --format json postgres"
    ]
    data = envelope(skm(sandbox, "--json", "local", "status", env=sandbox.env(PATH=str(folder))))
    assert data["result"]["components"][0] == {
        "component": "postgres",
        "state": "running",
        "detail": "127.0.0.1:54329, healthy",
    }


def test_local_status_of_a_service_never_started(sandbox: Sandbox, tmp_path: Path) -> None:
    folder, _ = fake_docker(tmp_path, ps="")
    data = envelope(skm(sandbox, "--json", "local", "status", env=sandbox.env(PATH=str(folder))))
    assert data["result"]["components"][0]["state"] == "absent"


def test_a_failing_docker_daemon_is_a_backend_error(sandbox: Sandbox, tmp_path: Path) -> None:
    folder, _ = fake_docker(tmp_path)
    managed_fixture(sandbox, folder)
    fake_docker(tmp_path, exit_code=1)
    done = skm(sandbox, "--json", "local", "status", env=sandbox.env(PATH=str(folder)))
    assert done.returncode == 3
    error = envelope(done)["error"]
    assert error["code"] == "BACKEND_UNAVAILABLE"
    assert "Cannot connect to the Docker daemon" in error["details"]["stderr"]


def test_local_up_before_init_selects_only_its_own_compose_project(sandbox: Sandbox, tmp_path: Path) -> None:
    folder, log = fake_docker(tmp_path)
    env = sandbox.env(PATH=str(folder), SKM_LOCAL_PG_PROJECT="global-unrelated")
    result = skm(sandbox, "--json", "local", "up", "--wait", "5", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert envelope(result)["result"]["postgres"]["state"] == "running"
    server = managed_postgres(sandbox.state)
    assert server is not None
    project = f"skm-local-{server.installation_id.hex}"
    compose = str(ROOT / "deploy/compose.local.yaml")
    assert log.read_text().splitlines()[0] == (
        f"compose --project-name {project} -f {compose} up --detach --wait --wait-timeout 5 postgres"
    )
    assert not sandbox.bootstrap.exists()
    status = skm(sandbox, "--json", "local", "status", env=env)
    assert envelope(status)["result"]["components"][0]["state"] == "running"
    stopped = skm(sandbox, "--json", "local", "down", env=env)
    assert stopped.returncode == 0
    assert f"compose --project-name {project} -f {compose} stop postgres" in log.read_text().splitlines()


def test_local_down_stops_only_the_service(sandbox: Sandbox, tmp_path: Path) -> None:
    folder, log = fake_docker(tmp_path)
    server = managed_fixture(sandbox, folder)
    log.write_text("")
    done = skm(sandbox, "local", "down", env=sandbox.env(PATH=str(folder)))
    assert done.returncode == 0, done.stderr
    compose = str(ROOT / "deploy/compose.local.yaml")
    assert log.read_text().splitlines()[0] == (
        f"compose --project-name skm-local-{server.installation_id.hex} -f {compose} stop postgres"
    )


# --- skm init on PostgreSQL ------------------------------------------------------------------------


def _checked_admin(dsn: str) -> None:
    """CREATE/DROP DATABASE only on a loopback or socket test server through '*_test' (testing spec 1.11)."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail("init tests create databases only on a local server through '*_test'", pytrace=False)


@contextmanager
def _scratch_database(pg_dsn: str) -> Iterator[str]:
    _checked_admin(pg_dsn)
    name = f"skm_t_init_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield make_conninfo(pg_dsn, dbname=name)
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def scratch(pg_dsn: str) -> Iterator[str]:
    with _scratch_database(pg_dsn) as dsn:
        yield dsn


def _instance_rows(dsn: str) -> list[tuple[UUID, str]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        rows = conn.execute("SELECT id, kind FROM skm_core.scopes WHERE kind = 'instance'").fetchall()
    return [(cast("UUID", row[0]), cast("str", row[1])) for row in rows]


def _applied(dsn: str) -> list[int]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        rows = conn.execute("SELECT version FROM skm_core.schema_migrations ORDER BY version").fetchall()
    return [cast("int", row[0]) for row in rows]


def _init(box: Sandbox, dsn: str, *extra: str) -> dict[str, Any]:
    done = skm(box, "--json", "init", "--database-url", dsn, *extra)
    assert done.returncode == 0, done.stdout + done.stderr
    return cast("dict[str, Any]", envelope(done)["result"])


@pytest.mark.pg
def test_init_creates_the_core_prerequisites_and_a_rerun_keeps_them(sandbox: Sandbox, scratch: str) -> None:
    first = _init(sandbox, scratch, "--host-name", "laptop")
    instance_id = UUID(first["instance_id"])
    chain = [item.version for item in discover_migrations()]
    assert first["already_initialized"] is False
    assert first["migrations"] == {"applied": chain, "current": chain[-1]}
    assert first["instance_scope_created"] is True
    assert first["token_pepper_created"] is True
    assert Path(first["bootstrap_path"]) == sandbox.bootstrap
    assert Path(first["state_dir"]) == sandbox.state

    # files: private, complete, nothing secret in the profile
    assert (mode(sandbox.bootstrap), mode(sandbox.state), mode(sandbox.secrets), mode(sandbox.pepper)) == (
        0o600,
        0o700,
        0o700,
        0o600,
    )
    pepper = sandbox.pepper.read_bytes()
    assert len(bytes.fromhex(pepper.decode("ascii").strip())) == 32
    profile = tomllib.loads(sandbox.bootstrap.read_text(encoding="utf-8"))
    assert profile["instance_id"] == str(instance_id)
    assert profile["database"]["url"] == "secret://env/SKM_DATABASE_URL"
    assert profile["secrets"]["token_pepper"] == f"secret://file/{sandbox.pepper}"
    assert profile["paths"] == {
        "state_dir": str(sandbox.state),
        "blobs_root": str(sandbox.root / "data/skm/blobs"),
    }
    assert profile["host"] == {"id": "auto", "name": "laptop"}
    assert str(conninfo_to_dict(scratch)["dbname"]) not in sandbox.bootstrap.read_text(encoding="utf-8")
    loaded = load_bootstrap(str(sandbox.bootstrap), {}, sandbox.home)  # the product loader accepts it
    assert (loaded.instance_id, loaded.state_dir, loaded.access_mode) == (
        instance_id,
        sandbox.state,
        "embedded",
    )
    assert loaded.token_pepper is not None
    assert FileSecretResolver().resolve(loaded.token_pepper) == pepper.decode("ascii").strip()
    assert not list(sandbox.secrets.glob(".*.tmp"))
    assert _instance_rows(scratch) == [(instance_id, "instance")]
    assert _applied(scratch) == chain

    # rerun: the DSN comes from SKM_DATABASE_URL through the profile's reference
    profile_bytes = sandbox.bootstrap.read_bytes()
    done = skm(sandbox, "--json", "init", env=sandbox.env(SKM_DATABASE_URL=scratch))
    assert done.returncode == 0, done.stdout + done.stderr
    again = envelope(done)["result"]
    assert again["instance_id"] == str(instance_id)
    assert again["already_initialized"] is True
    assert again["migrations"] == {"applied": [], "current": chain[-1]}
    assert (again["instance_scope_created"], again["token_pepper_created"]) == (False, False)
    assert sandbox.bootstrap.read_bytes() == profile_bytes
    assert sandbox.pepper.read_bytes() == pepper
    assert _instance_rows(scratch) == [(instance_id, "instance")]

    human = skm(sandbox, "init", env=sandbox.env(SKM_DATABASE_URL=scratch))
    assert human.returncode == 0, human.stderr
    assert human.stdout.splitlines()[0] == f"already initialized: instance {instance_id}"
    assert f"up to date ({chain[-1]:04d})" in human.stdout


@pytest.mark.pg
def test_init_refuses_prior_schema_and_leaves_local_state_absent(sandbox: Sandbox, scratch: str) -> None:
    with psycopg.connect(scratch) as conn:
        conn.execute("CREATE TABLE public.prior (value integer)")
        conn.execute("INSERT INTO public.prior VALUES (42)")
        before = conn.execute("SELECT value, xmin::text FROM public.prior").fetchone()
    done = skm(sandbox, "--json", "init", "--database-url", scratch)
    assert done.returncode == 6
    assert envelope(done)["error"]["details"]["reason"] == "schema_baseline_missing"
    assert not sandbox.bootstrap.exists()
    assert not sandbox.state.exists()
    with psycopg.connect(scratch) as conn:
        assert conn.execute("SELECT value, xmin::text FROM public.prior").fetchone() == before
        assert conn.execute("SELECT to_regnamespace('skm_core')").fetchone() == (None,)


@pytest.mark.pg
def test_init_checks_project_app_and_migrator_database_before_writing(
    sandbox: Sandbox, pg_dsn: str, scratch: str
) -> None:
    with _scratch_database(pg_dsn) as baseline_dsn, psycopg.connect(pg_dsn, autocommit=True) as admin:
        migrated = skm(sandbox, "--json", "db", "migrate", env=sandbox.env(SKM_DATABASE_URL=baseline_dsn))
        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        login = f"skm_t_init_app_{uuid4().hex[:12]}"
        login_identifier = sql.Identifier(login)
        password = token_hex(24)
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE skm_app").format(
                login_identifier, sql.Literal(password)
            )
        )
        try:
            baseline_app = make_conninfo(baseline_dsn, user=login, password=password)
            mismatched = sandbox.env(SKM_DATABASE_URL=baseline_app, SKM_DATABASE_MIGRATOR_URL=scratch)
            refused = skm(sandbox, "--json", "init", env=mismatched)
            assert refused.returncode == 1, refused.stdout + refused.stderr
            assert envelope(refused)["error"]["code"] == "CONFIG_INVALID"
            assert password not in refused.stdout + refused.stderr
            assert not sandbox.bootstrap.exists()
            assert not sandbox.state.exists()
            with psycopg.connect(scratch) as conn:
                assert conn.execute("SELECT to_regnamespace('skm_core')").fetchone() == (None,)
            with psycopg.connect(baseline_app) as conn:
                assert conn.execute("SELECT count(*) FROM skm_core.scopes").fetchone() == (0,)
                assert conn.execute("SELECT count(*) FROM skm_extensions.pack_versions").fetchone() == (0,)

            matching = sandbox.env(SKM_DATABASE_URL=baseline_app, SKM_DATABASE_MIGRATOR_URL=baseline_dsn)
            initialized = skm(sandbox, "--json", "init", env=matching)
            assert initialized.returncode == 0, initialized.stdout + initialized.stderr
            assert sandbox.bootstrap.is_file()
            assert sandbox.pepper.is_file()
            with psycopg.connect(baseline_app) as conn:
                assert conn.execute("SELECT current_user").fetchone() == (login,)
                assert conn.execute("SELECT count(*) FROM skm_core.scopes").fetchone() == (2,)
                assert conn.execute("SELECT count(*) FROM skm_extensions.pack_versions").fetchone() == (
                    len(PackagedBuiltinPacks(ROOT / "resources/packs").payloads()),
                )
        finally:
            admin.execute(sql.SQL("DROP ROLE {}").format(login_identifier))


@pytest.mark.pg
def test_an_interrupted_init_reuses_the_pepper_it_left(sandbox: Sandbox, scratch: str) -> None:
    sandbox.secrets.mkdir(parents=True, mode=0o700)
    left = ("cd" * 32 + "\n").encode("ascii")
    sandbox.pepper.write_bytes(left)
    sandbox.pepper.chmod(0o600)
    result = _init(sandbox, scratch)
    assert result["token_pepper_created"] is False
    assert sandbox.pepper.read_bytes() == left
    assert sandbox.bootstrap.exists()


@pytest.mark.pg
def test_a_database_of_another_instance_is_refused_before_anything_is_written(
    sandbox: Sandbox, scratch: str, tmp_path: Path
) -> None:
    first = _init(sandbox, scratch)
    other = Sandbox(tmp_path / "other")
    other.home.mkdir(parents=True)
    done = skm(other, "--json", "init", "--database-url", scratch)
    assert done.returncode == 6, done.stdout + done.stderr
    error = envelope(done)["error"]
    assert (error["code"], error["details"]["instance_id"]) == ("ALREADY_EXISTS", first["instance_id"])
    assert files_under(other.root / "config") == []
    assert files_under(other.root / "state") == []


@pytest.mark.pg
def test_an_initialized_instance_never_gets_a_new_pepper(sandbox: Sandbox, scratch: str) -> None:
    _init(sandbox, scratch)
    sandbox.pepper.unlink()
    done = skm(sandbox, "--json", "init", "--database-url", scratch)
    assert done.returncode == 6, done.stdout + done.stderr
    error = envelope(done)["error"]
    assert (error["code"], error["details"]["reason"]) == ("SECRET_UNAVAILABLE", "missing")
    assert not sandbox.pepper.exists()


@pytest.mark.pg
def test_a_rerun_refuses_a_pepper_whose_permissions_were_widened(sandbox: Sandbox, scratch: str) -> None:
    _init(sandbox, scratch)
    pepper = sandbox.pepper.read_bytes()
    sandbox.pepper.chmod(0o644)
    done = skm(sandbox, "--json", "init", "--database-url", scratch)
    assert done.returncode == 6, done.stdout + done.stderr
    assert envelope(done)["error"]["code"] == "SECRET_PERMISSIONS"
    assert (mode(sandbox.pepper), sandbox.pepper.read_bytes()) == (0o644, pepper)
