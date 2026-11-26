"""Exercise verified instance profiles through the CLI, HTTPS and real PostgreSQL."""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import tomllib
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, closing, contextmanager, suppress
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from secrets import token_hex
from threading import Event
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route

from fakes.ids import SequentialIds
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.bootstrap.composition_resources import TokenPepper, token_authenticator
from skm.bootstrap.machine import open_machine_store, resolve_machine_profile
from skm.bootstrap.machine_access import SELECTION_KEY
from skm.bootstrap.platform_module import local_migration_runner
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access import public as access
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository, TokenPepperSource
from skm.modules.workspace import public as workspace
from skm.modules.workspace.domain.checkout_marker import MARKER_SCHEMA
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.sources.bootstrap import ProfileCatalog, cli_state_path
from skm.platform.machine import (
    MachineBinding,
    MachineCheckout,
    MachineCheckoutKey,
    MachinePrincipal,
    MachineSession,
    MachineStore,
)
from skm.platform.system_clock import SystemClock
from skm.sdk import connect
from support.git_repo import init_git_repo
from support.http_server import loopback_certificate, loopback_server
from support.pg import check_admin_dsn

pytestmark = [pytest.mark.e2e, pytest.mark.pg]
_PRINCIPAL = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d9"))
_ENTRY = "import sys; from skm.entrypoints.cli.main import main; sys.exit(main())"


@dataclass(frozen=True)
class _Databases:
    projects: tuple[str, str] = field(repr=False)
    machine_env: Mapping[str, str] = field(repr=False)
    machine_admin: str = field(repr=False)


@pytest.fixture
def databases(pg_dsn: str) -> Iterator[_Databases]:
    check_admin_dsn(pg_dsn)
    suffix = uuid4().hex[:10]
    project_names = f"s03_a_{suffix}", f"s03_b_{suffix}"
    machine = f"s03_machine_{suffix}"
    roles: list[str] = []
    dbs: list[str] = []
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        for group in ("skm_host_app", "skm_host_migrator"):
            with suppress(psycopg.errors.DuplicateObject):
                admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(group)))
        try:
            env: dict[str, str] = {}
            for group, variable in (
                ("skm_host_app", "SKM_MACHINE_DATABASE_URL"),
                ("skm_host_migrator", "SKM_MACHINE_DATABASE_MIGRATOR_URL"),
            ):
                role, password = f"{group}_{suffix}", token_hex(24)
                admin.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE {}").format(
                        sql.Identifier(role), sql.Literal(password), sql.Identifier(group)
                    )
                )
                roles.append(role)
                env[variable] = make_conninfo(pg_dsn, user=role, password=password, dbname=machine)
            for name in project_names:
                admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
                dbs.append(name)
            admin.execute(
                sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                    sql.Identifier(machine), sql.Identifier(roles[1])
                )
            )
            dbs.append(machine)
            admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(machine)))
            admin.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO skm_host_app").format(sql.Identifier(machine))
            )
            yield _Databases(
                (
                    make_conninfo(pg_dsn, dbname=project_names[0]),
                    make_conninfo(pg_dsn, dbname=project_names[1]),
                ),
                env,
                make_conninfo(pg_dsn, dbname=machine),
            )
        finally:
            for name in reversed(dbs):
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            for role in reversed(roles):
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def _environment(root: Path, **values: str) -> dict[str, str]:
    home = root / "home"
    home.mkdir(parents=True)
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_STATE_HOME": str(root / "state"),
        "XDG_DATA_HOME": str(root / "data"),
        **values,
    }


def _cli(cwd: Path, env: Mapping[str, str], *args: str, error: str | None = None) -> Any:
    result = subprocess.run(
        (sys.executable, "-c", _ENTRY, "--json", *args),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    for key, value in env.items():
        if key.endswith(("_TOKEN", "DATABASE_URL", "MIGRATOR_URL")):
            assert value not in result.stdout + result.stderr
    body = json.loads(result.stdout)
    if error is None:
        assert result.returncode == 0, body
        return body["result"]
    assert result.returncode != 0, body
    assert body["error"]["code"] == error, body
    return body["error"]


@dataclass(frozen=True)
class _Hub:
    app: App
    token: str = field(repr=False)
    workspace_id: UUID
    project_id: UUID

    def serve(self, tls: tuple[Path, Path] | None = None, *, port: int = 0):
        return loopback_server(
            lambda address: create_app(
                self.app,
                route_table=build_route_table(MODULE_IDS),
                registry=self.app.bus._registry,
                no_background=True,
                settings={"api.bind": address},
            ),
            tls=tls,
            port=port,
        )


@contextmanager
def _hub(dsn: str, root: Path, name: str) -> Iterator[_Hub]:
    local_migration_runner(dsn).migrate()
    clock, ids = SystemClock(), SequentialIds()
    identity = ScopeId(uuid4())
    with psycopg.connect(dsn) as conn:
        conn.execute("INSERT INTO skm_core.scopes (id, kind) VALUES (%s, 'instance')", (identity,))
    boot = replace(
        load_bootstrap(None, {"SKM_DATABASE_URL": dsn}, root),
        instance_id=identity,
        state_dir=root,
        database_pool_min_size=0,
    )
    pepper = bytes.fromhex(token_hex(32))
    ov = CompositionOverrides(
        authorizer=access.RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        ids=ids,
        instance_id=identity,
        gateways=GatewayTable({TokenPepperSource: TokenPepper(pepper)}, "control_plane_gateway"),
    )
    with closing(
        build_app(boot, surface=Surface.CLI, environ={}, invocation={}, backend="postgres", overrides=ov)
    ) as app:
        now = clock.now()
        with app.uow_factory(RequestMeta("req_" + "1" * 26, Surface.CLI, None, now)) as uow:
            uow.repo(PrincipalRepository).add(
                new_principal(
                    principal_id=_PRINCIPAL,
                    kind=PrincipalKind.HUMAN,
                    display_name=name,
                    now=now,
                    created_by=None,
                )
            )
            uow.repo(MembershipRepository).upsert(
                Membership(identity, _PRINCIPAL, access.Role.OWNER, None, now)
            )
            uow.commit()
        client = app.client(actor=Actor(_PRINCIPAL, PrincipalKind.HUMAN, name), surface=Surface.CLI)
        ws = cast(
            "workspace.CreateWorkspaceResult",
            client.dispatch(workspace.CreateWorkspace(slug="personal", title="Personal")),
        )
        project = cast(
            "workspace.CreateProjectResult",
            client.dispatch(workspace.CreateProject(workspace_id=ws.workspace_id, slug="demo", title=name)),
        )
        minted = cast(
            "access.CreateTokenResult",
            client.dispatch(
                access.CreateToken(
                    "Viewer",
                    _PRINCIPAL,
                    permissions=("token.own", "workspace.read", "project.read", "config.read"),
                )
            ),
        )
        authenticate = token_authenticator(app.uow_factory, pepper, Surface.API, ids, clock)
        yield _Hub(
            replace(app, authenticator=authenticate), minted.secret, ws.workspace_id, project.project_id
        )


def _remote(endpoint: str, cert: Path, variable: str) -> tuple[str, ...]:
    return (
        "--api-endpoint",
        endpoint + "/api/v1",
        "--credential",
        f"secret://env/{variable}",
        "--ca-bundle",
        str(cert),
    )


def _checkout(path: Path, instance: UUID, hub: _Hub) -> Path:
    init_git_repo(path)
    marker = path / ".skm/project.json"
    marker.parent.mkdir()
    marker.write_text(
        json.dumps(
            {
                "schema": MARKER_SCHEMA,
                "instance_id": str(instance),
                "workspace_id": str(hub.workspace_id),
                "project_id": str(hub.project_id),
                "repository_id": str(uuid4()),
                "mount_name": "main",
            }
        )
    )
    nested = path / "lib" / "inner"
    nested.mkdir(parents=True)
    return nested


def test_embedded_init_pins_project_and_selects_machine_context(
    databases: _Databases, tmp_path: Path
) -> None:
    env = _environment(
        tmp_path / "standalone", SKM_DATABASE_URL=databases.projects[0], **databases.machine_env
    )
    first = _cli(tmp_path, env, "init")
    standalone = ProfileCatalog.read(None, env, Path(env["HOME"])).config("default")
    store = open_machine_store(standalone, env)
    installation = standalone.installation_id
    assert installation is not None
    pin = resolve_machine_profile(store, installation, "default")
    assert (str(pin.instance_id), pin.origin, pin.endpoint) == (
        first["instance_id"],
        f"embedded:{first['instance_id']}",
        None,
    )
    assert _cli(tmp_path, env, "whoami")["principal"]["principal_id"] == first["owner_principal_id"]
    assert _cli(tmp_path, env, "use")["workspace_id"] == first["workspace"]["workspace_id"]
    assert not (standalone.state_dir / "cli-context.json").exists()
    assert _cli(tmp_path, env, "init")["instance_id"] == first["instance_id"]
    assert resolve_machine_profile(store, installation, "default") == pin


def _assert_checkout_contexts(
    tmp_path: Path, env: Mapping[str, str], store: MachineStore, installation: UUID, hubs: tuple[_Hub, _Hub]
) -> Path:
    hub_a, hub_b = hubs
    a, b = hub_a.app.instance_id, hub_b.app.instance_id
    home = Path(env["HOME"])
    alpha = MachinePrincipal(installation, a, _PRINCIPAL)
    beta = MachinePrincipal(installation, b, _PRINCIPAL)
    store.set_user_setting(alpha, "ui.theme", "dark")
    store.set_user_setting(beta, "ui.theme", "light")
    alpha_root, beta_root = tmp_path / "alpha", tmp_path / "beta"
    alpha_nested = _checkout(alpha_root, a, hub_a)
    beta_nested = _checkout(beta_root, b, hub_b)
    host, checkout = uuid4(), uuid4()
    repository = uuid4()
    for scope, selected_hub, root in ((alpha, hub_a, alpha_root), (beta, hub_b, beta_root)):
        key = MachineCheckoutKey(installation, scope.instance_id, host, checkout)
        store.reserve_checkout(MachineCheckout(key, root))
        binding = MachineBinding(scope, key, selected_hub.workspace_id, selected_hub.project_id, repository)
        store.put_binding(binding)
        assert store.get_binding(scope, key) == binding
        recorded = store.get_checkout(key)
        assert recorded is not None
        assert recorded.root == root
    _cli(tmp_path, env, "instance", "use", "alpha")
    _cli(beta_root, env, "instance", "use", "beta", "--here")
    assert _cli(alpha_nested, env, "whoami")["principal"]["principal_id"] == str(_PRINCIPAL)
    assert _cli(beta_nested, env, "whoami")["principal"]["principal_id"] == str(_PRINCIPAL)
    assert _cli(alpha_nested, env, "instance", "show")["instance_id"] == str(a)
    assert _cli(beta_nested, env, "instance", "show")["instance_id"] == str(b)
    assert _cli(alpha_nested, env, "use", "--here")["project_id"] == str(hub_a.project_id)
    assert _cli(beta_nested, env, "use")["project_id"] is None
    assert _cli(beta_nested, env, "use", "--here")["project_id"] == str(hub_b.project_id)
    assert _cli(beta_nested, env, "--instance", "alpha", "use", "--here", error="CONFIG_INVALID")
    assert _cli(beta_nested, env, "use", "personal")["project_id"] is None
    assert _cli(alpha_nested, env, "use")["project_id"] == str(hub_a.project_id)
    assert store.get_user_setting(alpha, "ui.theme") == "dark"
    assert store.get_user_setting(beta, "ui.theme") == "light"
    assert not list(Path(env["XDG_STATE_HOME"]).rglob("cli-context.json"))
    assert "last_project_id" not in cli_state_path(env, home).read_text()
    return alpha_nested


def _assert_unmanaged_context(tmp_path: Path, hub_a: _Hub, ep_a: str, cert: Path) -> None:
    a = hub_a.app.instance_id
    legacy = _environment(tmp_path / "legacy", A_TOKEN=hub_a.token)
    legacy_path = Path(legacy["XDG_CONFIG_HOME"]) / "skm/bootstrap.toml"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(f'''schema = "urn:skm:config:bootstrap:v1"
instance_id = "{a}"
[access]
mode = "http"
[api]
endpoint = "{ep_a}/api/v1"
credential = "secret://env/A_TOKEN"
ca_bundle = "{cert}"
''')
    legacy_config = load_bootstrap(None, legacy, Path(legacy["HOME"]))
    context = legacy_config.state_dir / "cli-context.json"
    context.parent.mkdir(parents=True)
    context.write_text(
        json.dumps(
            {
                "schema": "urn:skm:cli:context:v1",
                "instance_id": str(a),
                "project_id": str(hub_a.project_id),
            }
        )
    )
    stale = context.read_text()
    assert _cli(tmp_path, legacy, "use")["project_id"] is None
    _cli(tmp_path, legacy, "use", "personal/demo", error="CONFIG_INVALID")
    assert context.read_text() == stale


def _assert_viewer_scope(
    tmp_path: Path, env: Mapping[str, str], hub_a: _Hub, ep_a: str, cert: Path, dsn: str
) -> None:
    shown = _cli(tmp_path, env, "instance", "show", "alpha")
    assert shown["instance_id"] == str(hub_a.app.instance_id)
    expected_version = local_migration_runner(dsn).status()[-1][1]
    assert shown["schema_version"] == expected_version
    denied = httpx.get(
        ep_a + "/api/v1/admin/migrations",
        headers={"Authorization": "Bearer " + hub_a.token},
        verify=ssl.create_default_context(cafile=str(cert)),
    )
    assert denied.status_code == 403


def _assert_refusal_is_clean(
    tmp_path: Path,
    env: Mapping[str, str],
    endpoints: tuple[str, str],
    cert: Path,
    unexpected_id: UUID,
    machine_dsn: str,
) -> None:
    plain, ep_a = endpoints
    a_args = _remote(ep_a, cert, "A_TOKEN")
    bootstrap = Path(env["XDG_CONFIG_HOME"]) / "skm/bootstrap.toml"
    _cli(
        tmp_path,
        env,
        "instance",
        "add",
        "plain",
        "--mode",
        "http",
        *_remote(plain, cert, "A_TOKEN"),
        error="CONFIG_INVALID",
    )
    _cli(
        tmp_path,
        env,
        "instance",
        "add",
        "wrong",
        "--mode",
        "http",
        *a_args,
        "--instance-id",
        str(unexpected_id),
        error="CONFIG_INVALID",
    )
    _cli(
        tmp_path,
        env,
        "instance",
        "add",
        "invalid-token",
        "--mode",
        "http",
        *_remote(ep_a, cert, "BAD_TOKEN"),
        error="UNAUTHENTICATED",
    )
    assert not bootstrap.exists()
    with psycopg.connect(machine_dsn) as conn:
        assert conn.execute("SELECT to_regnamespace('skm_host')").fetchone() == (None,)


def _assert_no_redirect(tmp_path: Path, env: Mapping[str, str], tls: tuple[Path, Path]) -> None:
    reached = Event()

    async def sink(_request: Request) -> Response:
        reached.set()
        return Response(status_code=403)

    with loopback_server(lambda _: Starlette(routes=[Route("/api/v1/doctor", sink)]), tls=tls) as target:

        async def redirect(_request: Request) -> RedirectResponse:
            return RedirectResponse(target + "/api/v1/doctor")

        with loopback_server(
            lambda _: Starlette(routes=[Route("/api/v1/doctor", redirect)]), tls=tls
        ) as endpoint:
            _cli(
                tmp_path,
                env,
                "instance",
                "add",
                "redirect",
                "--mode",
                "http",
                *_remote(endpoint, tls[0], "A_TOKEN"),
                error="CONFIG_INVALID",
            )
    assert not reached.is_set()


def _assert_rebind(
    cwd: Path,
    env: Mapping[str, str],
    store: MachineStore,
    installation: UUID,
    origin: tuple[_Hub, tuple[Path, Path]],
    other: tuple[str, ...],
) -> None:
    hub_a, tls = origin
    a = hub_a.app.instance_id
    alpha = MachinePrincipal(installation, a, _PRINCIPAL)
    bootstrap = Path(env["XDG_CONFIG_HOME"]) / "skm/bootstrap.toml"
    with hub_a.serve(tls) as re_endpoint:
        re_args = _remote(re_endpoint, tls[0], "A_TOKEN")
        initial = bootstrap.read_text()
        _cli(cwd, env, "instance", "add", "other", "--mode", "http", *re_args, error="CONFIG_INVALID")
        _cli(cwd, env, "instance", "rebind", "alpha", *other, error="CONFIG_INVALID")
        assert bootstrap.read_text() == initial
        pinned = resolve_machine_profile(store, installation, "alpha")
        expiry = SystemClock().now() + timedelta(minutes=5)
        handle = "a" * 64
        assert store.put_session(MachineSession(pinned, _PRINCIPAL, handle, expiry))
        assert store.get_session(installation, handle, SystemClock().now()) == alpha
        _cli(cwd, env, "instance", "rebind", "alpha", *re_args)
        rebound = resolve_machine_profile(store, installation, "alpha")
        assert (rebound.instance_id, rebound.origin) == (a, re_endpoint)
        assert rebound.revision != pinned.revision
        assert store.get_session(installation, handle, SystemClock().now()) is None
        selection = store.get_user_setting(alpha, SELECTION_KEY)
        assert isinstance(selection, dict)
        assert selection["project_id"] == str(hub_a.project_id)
        assert _cli(cwd, env, "instance", "show")["target"] == re_endpoint
        assert _cli(cwd, env, "use")["project_id"] == str(hub_a.project_id)

        good = bootstrap.read_text()
        bootstrap.write_text(good.replace(str(a), str(uuid4())))
        _cli(cwd, env, "use", error="CONFIG_INVALID")
        bootstrap.write_text(good)
        assert _cli(cwd, env, "use")["project_id"] == str(hub_a.project_id)
        # A bootstrap edit alone cannot change the active HTTPS origin.
        bootstrap.write_text(good.replace(re_endpoint, other[1].removesuffix("/api/v1")))
        assert _cli(cwd, env, "instance", "show")["target"] == re_endpoint
        bootstrap.write_text(good)
    _cli(cwd, env, "instance", "show", error="BACKEND_UNAVAILABLE")
    port = urlsplit(re_endpoint).port
    assert port is not None
    with hub_a.serve(tls, port=port) as restarted:
        assert restarted == re_endpoint
        assert _cli(cwd, env, "instance", "show")["target"] == re_endpoint
        assert _cli(cwd, env, "use")["project_id"] == str(hub_a.project_id)


def test_https_profiles_isolate_equal_ids_and_require_verified_rebind(
    databases: _Databases, tmp_path: Path
) -> None:
    tls_a = loopback_certificate(tmp_path / "tls-a")
    tls_b = loopback_certificate(tmp_path / "tls-b")
    with ExitStack() as stack:
        hub_a = stack.enter_context(_hub(databases.projects[0], tmp_path / "hub-a", "Hub A"))
        hub_b = stack.enter_context(_hub(databases.projects[1], tmp_path / "hub-b", "Hub B"))
        a, b = hub_a.app.instance_id, hub_b.app.instance_id
        assert a != b
        assert hub_a.project_id == hub_b.project_id
        env = _environment(
            tmp_path / "client",
            A_TOKEN=hub_a.token,
            B_TOKEN=hub_b.token,
            BAD_TOKEN="unrecognized-fixture-secret",
            **databases.machine_env,
        )
        home = Path(env["HOME"])
        bootstrap = Path(env["XDG_CONFIG_HOME"]) / "skm/bootstrap.toml"
        ep_a = stack.enter_context(hub_a.serve(tls_a))
        ep_b = stack.enter_context(hub_b.serve(tls_b))
        a_args = _remote(ep_a, tls_a[0], "A_TOKEN")
        b_args = _remote(ep_b, tls_b[0], "B_TOKEN")
        plain = stack.enter_context(hub_a.serve())
        _assert_refusal_is_clean(tmp_path, env, (plain, ep_a), tls_a[0], b, databases.machine_admin)
        _assert_no_redirect(tmp_path, env, tls_a)

        _cli(tmp_path, env, "instance", "add", "alpha", "--mode", "http", *a_args)
        _cli(tmp_path, env, "instance", "add", "beta", "--mode", "http", *b_args, "--instance-id", str(b))
        catalog = ProfileCatalog.read(None, env, home)
        setup = catalog.config("alpha")
        installation = setup.installation_id
        assert installation is not None
        store = open_machine_store(setup, env)
        pins = store.list_profiles(installation)
        assert {(p.name, p.instance_id, p.origin) for p in pins} == {("alpha", a, ep_a), ("beta", b, ep_b)}
        assert "machine_database" in tomllib.loads(bootstrap.read_text())
        _assert_viewer_scope(tmp_path, env, hub_a, ep_a, tls_a[0], databases.projects[0])

        alpha_nested = _assert_checkout_contexts(tmp_path, env, store, installation, (hub_a, hub_b))
        _assert_rebind(alpha_nested, env, store, installation, (hub_a, tls_a), b_args)
        _assert_unmanaged_context(tmp_path, hub_a, ep_a, tls_a[0])


def test_sdk_and_use_alias_honor_the_verified_https_pin(
    databases: _Databases, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = loopback_certificate(tmp_path / "trusted")
    untrusted = loopback_certificate(tmp_path / "untrusted")
    sent_to_other = Event()
    expected_ids: list[str | None] = []

    async def trap(_request: Request) -> Response:
        sent_to_other.set()
        return Response(status_code=403)

    async def without_confirmation(request: Request) -> Response:
        expected_ids.append(request.headers.get("SKM-Instance-Id"))
        return Response(status_code=200)

    with _hub(databases.projects[0], tmp_path / "hub", "Trusted") as hub:
        env = _environment(tmp_path / "client", A_TOKEN=hub.token, **databases.machine_env)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        bootstrap = Path(env["XDG_CONFIG_HOME"]) / "skm/bootstrap.toml"
        with hub.serve(trusted) as endpoint:
            _cli(
                tmp_path,
                env,
                "instance",
                "add",
                "alpha",
                "--mode",
                "http",
                *_remote(endpoint, trusted[0], "A_TOKEN"),
            )
            nested = tmp_path / "checkout" / "nested"
            nested.mkdir(parents=True)
            _cli(tmp_path, env, "use", "--instance", "alpha")
            _cli(nested.parent, env, "use", "--instance", "alpha", "--here")
            cli_state = json.loads(cli_state_path(env, Path(env["HOME"])).read_text())
            assert cli_state["current_instance"] == "alpha"
            assert cli_state["checkout_bindings"] == {str(nested.parent): "alpha"}
            assert _cli(nested, env, "whoami")["principal"]["principal_id"] == str(_PRINCIPAL)

            original = bootstrap.read_text()
            with loopback_server(
                lambda _: Starlette(routes=[Route("/api/v1/me", trap)]), tls=untrusted
            ) as other:
                monkeypatch.setenv("TRAP_TOKEN", token_hex(24))
                changed = original.replace(endpoint, other).replace(str(trusted[0]), str(untrusted[0]))
                bootstrap.write_text(changed.replace("secret://env/A_TOKEN", "secret://env/TRAP_TOKEN"))
                with connect(profile="alpha", config=bootstrap) as client:
                    identity = client.ask(access.WhoAmI())
                    assert isinstance(identity, access.WhoAmIView)
                    assert identity.principal.principal_id == _PRINCIPAL
                monkeypatch.setenv("SKM_API_ENDPOINT", other + "/api/v1")
                monkeypatch.setenv("SKM_API_TOKEN", token_hex(24))
                with connect(profile="alpha", config=bootstrap) as client:
                    identity = client.ask(access.WhoAmI())
                    assert isinstance(identity, access.WhoAmIView)
                    assert identity.principal.principal_id == _PRINCIPAL
                assert not sent_to_other.is_set()
            bootstrap.write_text(original)
            monkeypatch.delenv("SKM_API_ENDPOINT")
            monkeypatch.delenv("SKM_API_TOKEN")

        port = urlsplit(endpoint).port
        assert port is not None
        with (
            loopback_server(
                lambda _: Starlette(routes=[Route("/api/v1/me", without_confirmation)]),
                tls=trusted,
                port=port,
            ),
            connect(profile="alpha", config=bootstrap) as client,
        ):
            with pytest.raises(ValidationFailed, match="did not confirm") as refused:
                client.ask(access.WhoAmI())
            assert refused.value.code is ErrorCode.CONFIG_INVALID
        assert expected_ids == [str(hub.app.instance_id)]
