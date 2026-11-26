"""The full ``skm init``: system principal, local owner, owner token, default workspace, recovery.

Every ``skm`` runs as a real subprocess with explicit ``HOME``/``XDG_CONFIG_HOME``/``XDG_STATE_HOME``/
``XDG_DATA_HOME`` under ``tmp_path`` and the production composition (``RbacAuthorizer``, the stored scope
chain, the pepper of the sandbox; no ``CompositionOverrides``). The PostgreSQL cases create their own scratch
database from ``SKM_TEST_DATABASE_URL`` (loopback and ``*_test`` only) and drop it afterwards; cross-process
checks share only that database and the sandbox, never the user's credentials or DSN. In-process checks open
the same production composition through ``open_cli_app`` and ask through its ``EmbeddedClient``.
"""

import argparse
import json
import os
import stat
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from skm.application_bus.client import EmbeddedClient
from skm.bootstrap.composition import App, open_cli_app
from skm.entrypoints.cli.commands import init as init_module
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import Surface
from skm.modules.access.domain.roles import ROLE_PERMISSIONS, Role
from skm.modules.access.generated.commands import BootstrapLocalOwner
from skm.modules.access.generated.results import BootstrapLocalOwnerResult
from skm.modules.access.public import (
    SYSTEM_ACTOR,
    CreatePrincipal,
    CreatePrincipalResult,
    CreateToken,
    CreateTokenResult,
)
from skm.modules.workspace.public import CreateWorkspace, ListProjects
from skm.platform.config.bootstrap import load_bootstrap

ENTRY = "import sys; from skm.entrypoints.cli.main import main; sys.exit(main())"
# Only what the interpreter needs; HOME and XDG always point into the sandbox.
PASSED = ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "TMPDIR")
OWNER_NAME = "init-tester"
ROUNDS = "execution.review.max_rounds"


@dataclass(frozen=True)
class Sandbox:
    root: Path
    dsn: str = ""

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
    def owner_token(self) -> Path:
        return self.secrets / "owner.token"

    @property
    def context(self) -> Path:
        return self.state / "cli-context.json"

    def env(self, **extra: str) -> dict[str, str]:
        env = {name: os.environ[name] for name in PASSED if name in os.environ}
        env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_STATE_HOME=str(self.root / "state"),
            XDG_DATA_HOME=str(self.root / "data"),
            USER=OWNER_NAME,
            PYTHONDONTWRITEBYTECODE="1",
        )
        if self.dsn:
            env["SKM_DATABASE_URL"] = self.dsn  # the profile stores only a reference to it
        env.update(extra)
        return env


def skm(box: Sandbox, *argv: str, entry: str = ENTRY) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", entry, *argv],
        env=box.env(),
        cwd=box.root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def envelope(done: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(done.stdout))


def ok(box: Sandbox, *argv: str) -> dict[str, Any]:
    done = skm(box, "--json", *argv)
    assert done.returncode == 0, done.stdout + done.stderr
    return cast("dict[str, Any]", envelope(done)["result"])


def failed(box: Sandbox, code: int, *argv: str) -> dict[str, Any]:
    done = skm(box, "--json", *argv)
    assert done.returncode == code, done.stdout + done.stderr
    return cast("dict[str, Any]", envelope(done)["error"])


def mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


# --- declarations ----------------------------------------------------------------------------------


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    init_module.register(parser.add_subparsers(dest="group"))
    return parser.parse_args(["init", *argv])


def test_the_default_workspace_flags_share_one_destination() -> None:
    assert _parse().workspace == "personal"
    assert _parse("--workspace", "team").workspace == "team"
    assert _parse("--no-workspace").workspace is None
    assert _parse("--workspace", "team", "--no-workspace").workspace is None  # the last flag wins


def test_init_stays_a_local_group_without_a_backend_actor() -> None:
    assert not init_module.GROUP.requires_backend  # init runs before any principal exists


# --- PostgreSQL ------------------------------------------------------------------------------------


def _checked_admin(dsn: str) -> None:
    """CREATE/DROP DATABASE only on a loopback or socket test server through '*_test' (testing spec 1.11)."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail("init tests create databases only on a local server through '*_test'", pytrace=False)


@pytest.fixture
def scratch(pg_dsn: str) -> Iterator[str]:
    _checked_admin(pg_dsn)
    name = f"skm_t_initr_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield make_conninfo(pg_dsn, dbname=name)
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def box(tmp_path: Path, scratch: str) -> Sandbox:
    sandbox = Sandbox(tmp_path / "sandbox", scratch)
    sandbox.home.mkdir(parents=True)
    return sandbox


def rows(dsn: str, query: str, *params: object) -> list[tuple[Any, ...]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        return [tuple(row) for row in conn.execute(query, params).fetchall()]  # pyright: ignore[reportArgumentType]


def count(dsn: str, table: str) -> int:
    return cast("int", rows(dsn, f"SELECT count(*) FROM {table}")[0][0])  # noqa: S608 - fixed table names


def identity_counts(dsn: str) -> tuple[int, int, int, int]:
    return (
        count(dsn, "skm_access.principals"),
        count(dsn, "skm_access.api_tokens"),
        count(dsn, "skm_access.memberships"),
        count(dsn, "skm_workspace.workspaces"),
    )


class Embedded:
    """The production composition of the sandbox profile in this process (no overrides)."""

    def __init__(self, box: Sandbox) -> None:
        env = box.env()
        bootstrap = load_bootstrap(str(box.bootstrap), env, box.home)
        self.app: App
        self.app, self.owner = open_cli_app(bootstrap, environ=env, invocation={}, as_token=None)

    def client(self, actor: Actor) -> EmbeddedClient:
        client = self.app.client(actor=actor, surface=Surface.CLI)
        assert isinstance(client, EmbeddedClient)
        return client

    def close(self) -> None:
        self.app.close()


@pytest.fixture
def embedded() -> Iterator[list[Embedded]]:
    opened: list[Embedded] = []
    yield opened
    for item in opened:
        item.close()


def _open(opened: list[Embedded], box: Sandbox) -> Embedded:
    item = Embedded(box)
    opened.append(item)
    return item


def _assert_identities(dsn: str, instance_id: UUID, owner_id: UUID, workspace_id: UUID) -> None:
    """The canonical system principal and the human local owner, both owners of the instance."""
    principals = {
        row[0]: row[1:]
        for row in rows(dsn, "SELECT id, kind, display_name, state FROM skm_access.principals")
    }
    assert principals == {
        SYSTEM_PRINCIPAL_ID: ("service", "system", "active"),
        owner_id: ("human", OWNER_NAME, "active"),
    }
    memberships = set(rows(dsn, "SELECT scope_id, principal_id, role FROM skm_access.memberships"))
    assert memberships == {
        (instance_id, SYSTEM_PRINCIPAL_ID, "owner"),
        (instance_id, owner_id, "owner"),
        (workspace_id, owner_id, "owner"),
    }
    tokens = rows(
        dsn,
        "SELECT principal_id, name, scope_id, permissions, expires_at, revoked_at FROM skm_access.api_tokens",
    )
    assert tokens == [
        (owner_id, "local-owner-cli", instance_id, sorted(ROLE_PERMISSIONS[Role.OWNER]), None, None)
    ]  # the system gets no token
    identities = rows(dsn, "SELECT principal_id, issuer, subject FROM skm_access.principal_identities")
    assert identities == [(owner_id, "local", "owner")]


def _assert_embedded_and_rights(world: Embedded, owner_id: UUID, workspace_id: UUID) -> None:
    """``workspace.list_projects`` through ``EmbeddedClient``; system internal rights are not user rights."""
    assert world.owner.principal_id == owner_id
    owner = world.client(world.owner)
    projects = owner.ask(ListProjects(workspace_id=workspace_id))
    assert projects.items == ()  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(SkmError) as denied:
        owner.dispatch(BootstrapLocalOwner(display_name="intruder"))
    assert denied.value.code.value == "FORBIDDEN"
    again = cast(
        "BootstrapLocalOwnerResult",
        world.client(SYSTEM_ACTOR).dispatch(BootstrapLocalOwner(display_name="second")),
    )
    assert (again.principal_id, again.created, again.token_secret) == (owner_id, False, None)


@pytest.mark.pg
def test_init_creates_system_owner_token_and_workspace_and_the_cli_works_across_processes(
    box: Sandbox, embedded: list[Embedded]
) -> None:
    done = skm(box, "--json", "init", "--database-url", box.dsn)
    assert done.returncode == 0, done.stdout + done.stderr
    first = envelope(done)["result"]
    secret = box.owner_token.read_text(encoding="utf-8").strip()
    assert secret
    assert secret not in done.stdout + done.stderr  # the secret is never printed
    owner_id = UUID(first["owner_principal_id"])
    assert first["system_principal_created"] is True
    assert first["owner"] == {
        "principal_id": str(owner_id),
        "created": True,
        "token_path": str(box.owner_token),
    }
    workspace = first["workspace"]
    assert (workspace["slug"], workspace["created"]) == ("personal", True)
    workspace_id = UUID(workspace["workspace_id"])

    # credentials: only the 0600 file holds the plaintext; the database holds a hash
    assert (mode(box.secrets), mode(box.owner_token)) == (0o700, 0o600)
    assert not list(box.secrets.glob(".*.tmp"))
    dumped = rows(
        box.dsn,
        "SELECT coalesce(string_agg(payload::text, ''), '') FROM skm_core.domain_events "
        "UNION ALL SELECT coalesce(string_agg(target::text, ''), '') FROM skm_core.audit_records",
    )
    assert all(secret not in cast("str", text) for (text,) in dumped)

    instance_id = UUID(first["instance_id"])
    _assert_identities(box.dsn, instance_id, owner_id, workspace_id)

    # the default workspace is selected like `skm use personal`
    context = json.loads(box.context.read_text(encoding="utf-8"))
    assert (context["workspace_id"], context["workspace_slug"]) == (str(workspace_id), "personal")
    assert context["instance_id"] == str(instance_id)
    assert mode(box.context) == 0o600

    # whoami and config through the owner token, each a separate process over the committed state
    who = ok(box, "whoami")
    assert who["principal"]["principal_id"] == str(owner_id)
    assert not any(permission.startswith("system.") for permission in who["effective_permissions"])
    assert "config.write" in who["effective_permissions"]
    ok(box, "config", "set", ROUNDS, "4", "--scope", "instance", "--reason", "init test")
    assert ok(box, "config", "get", ROUNDS, "--scope", "instance")["value"] == 4
    assert ok(box, "config", "get", ROUNDS)["value"] == 4  # the selected workspace inherits it

    _assert_embedded_and_rights(_open(embedded, box), owner_id, workspace_id)

    # a rerun is a no-op: same instance, owner, token file, workspace, selection and profile
    before = (box.bootstrap.read_bytes(), box.owner_token.read_bytes(), box.context.read_bytes())
    counts = identity_counts(box.dsn)
    rerun = ok(box, "init")
    assert rerun["already_initialized"] is True
    assert (rerun["instance_id"], rerun["owner_principal_id"]) == (str(instance_id), str(owner_id))
    assert rerun["system_principal_created"] is False
    assert rerun["owner"]["created"] is False
    assert rerun["workspace"] == {"workspace_id": str(workspace_id), "slug": "personal", "created": False}
    assert (box.bootstrap.read_bytes(), box.owner_token.read_bytes(), box.context.read_bytes()) == before
    assert identity_counts(box.dsn) == counts
    assert ok(box, "whoami")["principal"]["principal_id"] == str(owner_id)
    assert list(box.root.joinpath("config/skm").iterdir()) == [box.bootstrap]  # one profile, the same one

    human = skm(box, "init")
    assert human.returncode == 0, human.stderr
    assert human.stdout.splitlines()[0] == f"already initialized: instance {instance_id}"
    assert secret not in human.stdout + human.stderr


@pytest.mark.pg
def test_no_workspace_creates_none_and_a_later_init_adds_only_it(box: Sandbox) -> None:
    first = ok(box, "init", "--database-url", box.dsn, "--no-workspace")
    assert first["workspace"] is None
    assert count(box.dsn, "skm_workspace.workspaces") == 0
    assert not box.context.exists()
    token = box.owner_token.read_bytes()

    second = ok(box, "init")
    assert (second["owner"]["created"], second["system_principal_created"]) == (False, False)
    assert (second["workspace"]["slug"], second["workspace"]["created"]) == ("personal", True)
    assert box.owner_token.read_bytes() == token
    assert json.loads(box.context.read_text(encoding="utf-8"))["workspace_slug"] == "personal"


@pytest.mark.pg
def test_an_init_interrupted_before_the_instance_row_completes_everything_with_the_profile_id(
    box: Sandbox,
) -> None:
    # A crash right after the profile was written leaves the pepper, the schema, the profile, no instance row.
    box.secrets.mkdir(parents=True, mode=0o700)
    pepper = box.secrets / "token-pepper"
    pepper.write_text("ab" * 32 + "\n", encoding="ascii")
    pepper.chmod(0o600)
    ok(box, "db", "migrate", "--database-url", box.dsn)
    instance_id = uuid4()
    box.bootstrap.parent.mkdir(parents=True)
    box.bootstrap.write_text(
        'schema = "urn:skm:config:bootstrap:v1"\n'
        f'instance_id = "{instance_id}"\n\n'
        '[access]\nmode = "embedded"\n\n'
        '[database]\nurl = "secret://env/SKM_DATABASE_URL"\n\n'
        f'[secrets]\ntoken_pepper = "secret://file/{pepper}"\n\n'
        f'[paths]\nstate_dir = "{box.state}"\n',
        encoding="utf-8",
    )
    profile = box.bootstrap.read_bytes()

    done = ok(box, "init")
    assert (done["instance_id"], done["instance_scope_created"]) == (str(instance_id), True)
    assert (done["token_pepper_created"], done["system_principal_created"]) == (False, True)
    assert (done["owner"]["created"], done["workspace"]["created"]) == (True, True)
    assert box.bootstrap.read_bytes() == profile
    assert rows(box.dsn, "SELECT id FROM skm_core.scopes WHERE kind = 'instance'") == [(instance_id,)]
    assert ok(box, "whoami")["principal"]["principal_id"] == done["owner_principal_id"]


@pytest.mark.pg
def test_an_init_interrupted_after_the_owner_completes_only_the_workspace(box: Sandbox) -> None:
    error = failed(box, 1, "init", "--database-url", box.dsn, "--workspace", "Not A Slug")
    assert error["code"] == "SCHEMA_INVALID"  # the workspace slug pattern of the query DTO
    token = box.owner_token.read_bytes()  # the owner step finished before the workspace step failed
    counts = identity_counts(box.dsn)
    assert counts == (2, 1, 2, 0)

    done = ok(box, "init")
    assert done["already_initialized"] is True
    assert (done["system_principal_created"], done["owner"]["created"]) == (False, False)
    assert done["workspace"]["created"] is True
    assert box.owner_token.read_bytes() == token
    assert identity_counts(box.dsn) == (2, 1, 3, 1)


@pytest.mark.pg
def test_an_init_interrupted_after_the_core_steps_creates_the_identities_on_rerun(box: Sandbox) -> None:
    entry = """
import sys
from unittest.mock import patch
from skm.entrypoints.cli.main import main
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError

error = InternalError(ErrorCode.INTERNAL_ERROR, "fixture interrupted before identities")
with patch("skm.bootstrap.instance._identities", side_effect=error):
    sys.exit(main())
"""
    interrupted = skm(box, "--json", "init", "--database-url", box.dsn, "--no-workspace", entry=entry)
    assert interrupted.returncode != 0
    assert envelope(interrupted)["error"]["code"] == "INTERNAL_ERROR"
    instance_id = tomllib.loads(box.bootstrap.read_text())["instance_id"]
    assert identity_counts(box.dsn) == (0, 0, 0, 0)
    assert rows(box.dsn, "SELECT count(*) FROM skm_extensions.pack_versions") == [(0,)]

    again = ok(box, "init", "--no-workspace")
    assert again["instance_id"] == instance_id
    assert (again["system_principal_created"], again["owner"]["created"]) == (True, True)
    assert rows(box.dsn, "SELECT count(*) FROM skm_extensions.pack_versions") == [(29,)]
    assert mode(box.owner_token) == 0o600
    assert ok(box, "whoami")["principal"]["principal_id"] == again["owner_principal_id"]


@pytest.mark.pg
def test_a_lost_owner_token_is_refused_and_never_regenerated(box: Sandbox) -> None:
    ok(box, "init", "--database-url", box.dsn)
    counts = identity_counts(box.dsn)
    box.owner_token.unlink()

    error = failed(box, 6, "init")
    assert (error["code"], error["details"]["reason"]) == ("SECRET_UNAVAILABLE", "missing")
    assert "never issues another" in error["details"]["hint"]
    assert not box.owner_token.exists()
    assert identity_counts(box.dsn) == counts  # no second owner, no second token


@pytest.mark.pg
def test_a_token_file_with_widened_permissions_is_refused_and_left_alone(box: Sandbox) -> None:
    ok(box, "init", "--database-url", box.dsn)
    token = box.owner_token.read_bytes()
    box.owner_token.chmod(0o644)
    error = failed(box, 6, "init")
    assert (error["code"], error["details"]["reason"]) == ("SECRET_PERMISSIONS", "mode")
    assert error["details"]["path"] == str(box.owner_token)
    assert (mode(box.owner_token), box.owner_token.read_bytes()) == (0o644, token)


@pytest.mark.pg
def test_a_token_file_before_any_owner_is_foreign_and_nothing_is_written(box: Sandbox) -> None:
    box.secrets.mkdir(parents=True, mode=0o700)
    box.owner_token.write_text("somebody-elses-token\n", encoding="utf-8")
    box.owner_token.chmod(0o600)
    error = failed(box, 6, "init", "--database-url", box.dsn)
    assert (error["code"], error["details"]["kind"], error["details"]["reason"]) == (
        "ALREADY_EXISTS",
        "owner_token",
        "no_local_owner",
    )
    assert box.owner_token.read_text(encoding="utf-8") == "somebody-elses-token\n"
    assert not box.bootstrap.exists()
    assert rows(box.dsn, "SELECT to_regclass('skm_core.scopes') IS NULL") == [(True,)]  # not even migrated


@pytest.mark.pg
def test_a_token_file_of_another_principal_or_garbage_is_refused_not_replaced(
    box: Sandbox, embedded: list[Embedded]
) -> None:
    ok(box, "init", "--database-url", box.dsn, "--no-workspace")
    world = _open(embedded, box)
    owner = world.client(world.owner)
    alice = cast(
        "CreatePrincipalResult",
        owner.dispatch(CreatePrincipal.from_json({"kind": "human", "display_name": "alice"})),
    )
    issued = cast(
        "CreateTokenResult",
        owner.dispatch(CreateToken.from_json({"name": "alice-cli", "principal_id": str(alice.principal_id)})),
    )
    original = box.owner_token.read_bytes()

    box.owner_token.write_text(issued.secret + "\n", encoding="utf-8")
    error = failed(box, 6, "init")
    assert (error["code"], error["details"]["reason"]) == ("ALREADY_EXISTS", "other_principal")
    assert box.owner_token.read_text(encoding="utf-8") == issued.secret + "\n"

    box.owner_token.write_text("skm_not_a_token\n", encoding="utf-8")
    error = failed(box, 6, "init")
    assert (error["code"], error["details"]["reason"]) == ("SECRET_UNAVAILABLE", "rejected")
    assert box.owner_token.read_text(encoding="utf-8") == "skm_not_a_token\n"

    box.owner_token.write_bytes(original)
    assert ok(box, "init", "--no-workspace")["owner"]["created"] is False


@pytest.mark.pg
def test_another_principals_personal_workspace_is_not_taken_over(
    box: Sandbox, embedded: list[Embedded]
) -> None:
    first = ok(box, "init", "--database-url", box.dsn, "--no-workspace")
    owner_id = UUID(first["owner_principal_id"])
    world = _open(embedded, box)
    world.client(SYSTEM_ACTOR).dispatch(CreateWorkspace(slug="personal", title="Not yours"))
    world.close()
    embedded.remove(world)

    error = failed(box, 6, "init")
    assert (error["code"], error["details"]["kind"], error["details"]["slug"]) == (
        "ALREADY_EXISTS",
        "workspace",
        "personal",
    )
    assert "--workspace OTHER" in error["details"]["hint"]
    personal = rows(box.dsn, "SELECT id FROM skm_workspace.workspaces WHERE slug = 'personal'")[0][0]
    assert (
        rows(
            box.dsn,
            "SELECT role FROM skm_access.memberships WHERE scope_id = %s AND principal_id = %s",
            personal,
            owner_id,
        )
        == []
    )
    assert not box.context.exists()

    mine = ok(box, "init", "--workspace", "mine")
    assert (mine["workspace"]["slug"], mine["workspace"]["created"]) == ("mine", True)
