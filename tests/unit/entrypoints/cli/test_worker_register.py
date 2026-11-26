"""CLI unit tests for workspace, project, use, host and worker registration/rotation."""

from __future__ import annotations

import io
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.application_bus.host import HostServices
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.entrypoints.cli.main import app_backend, main
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Unauthenticated
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, ScopeId
from skm.kernel.outcomes import Diagnostic
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access import public as access
from skm.modules.access.generated.commands import BootstrapLocalOwner
from skm.modules.access.generated.results import BootstrapLocalOwnerResult
from skm.modules.settings import public as settings
from skm.modules.workspace.domain.checkout_binding import ObservedCheckout
from skm.modules.workspace.domain.checkout_marker import CheckoutMarker
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.host.registry import HOST_OPERATIONS
from skm.modules.workspace.ports import RepositoryInspector
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.system_clock import SystemClock


class _Pepper:
    def pepper(self) -> bytes:
        return b"0123456789abcdef0123456789abcdef"


class _FakeInspector:
    def __init__(self) -> None:
        self.markers: list[tuple[str, str, CheckoutMarker]] = []

    def observe(
        self, path: str, *, marker_relpath: str = ".skm/project.json", timeout_seconds: float = 60.0
    ) -> ObservedCheckout:
        del marker_relpath, timeout_seconds
        return ObservedCheckout(
            exists=True,
            toplevel=path if path != "." else "/work/payments",
            remotes=(NormalizedRemote("github.com/acme/payments-service"),),
            head="a" * 40,
            marker=None,
            observed_at=datetime(2026, 11, 11, 12, 0, tzinfo=UTC),
            dirty=False,
        )

    def observe_with_diagnostics(
        self, path: str, *, marker_relpath: str = ".skm/project.json", timeout_seconds: float = 60.0
    ) -> tuple[ObservedCheckout, tuple[Diagnostic, ...]]:
        return self.observe(path, marker_relpath=marker_relpath, timeout_seconds=timeout_seconds), ()

    def write_marker(self, toplevel: str, *, marker_relpath: str, marker: CheckoutMarker) -> None:
        self.markers.append((toplevel, marker_relpath, marker))


@pytest.fixture
def cli_env(tmp_path: Path) -> tuple[App, Actor, Path, dict[str, str]]:
    root = Path(__file__).resolve().parents[4]
    state_dir = tmp_path / "state"
    config_home = tmp_path / "config"
    state_home = tmp_path / "local_state"
    home_dir = tmp_path / "home"
    for d in (state_dir, config_home, state_home, home_dir):
        d.mkdir(parents=True, exist_ok=True)

    env = {
        "HOME": str(home_dir),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_STATE_HOME": str(state_home),
        "SKM_DATABASE_URL": "postgresql://unused",
    }
    clock = SystemClock()
    bootstrap = load_bootstrap(None, env, root)
    inspector = _FakeInspector()
    host_services = HostServices(
        host_id=HostId(UUID("0195f1c2-0000-7000-8000-000000000040")),
        surface=Surface.CLI,
        gateways=GatewayTable(entries={RepositoryInspector: inspector}, kind="host_gateway"),
        host_config=object,
        operations={spec.name: spec for spec in HOST_OPERATIONS},
    )
    app = build_app(
        bootstrap,
        surface=Surface.CLI,
        environ=env,
        invocation={},
        overrides=CompositionOverrides(
            authorizer=access.RbacAuthorizer(clock),
            scopes=StoredScopeChain(),
            clock=clock,
            gateways=GatewayTable(
                entries={access.TokenPepperSource: _Pepper()},
                kind="control_plane_gateway",
            ),
            host=host_services,
            instance_id=UUID("0195f1c2-0000-7000-8000-000000000001"),
        ),
    )
    with app.uow_factory(RequestMeta("req_init", Surface.CLI, None, clock.now())) as uow:
        uow.repo(ScopeRegistry).create(
            ScopeId(app.instance_id), ScopeKind.INSTANCE, parent=None, workspace_id=None
        )
        uow.commit()

    def _authenticate(secret_text: str) -> Actor:
        with app.uow_factory(RequestMeta("req_auth", Surface.CLI, None, clock.now()), readonly=True) as uow:
            return access.authenticate_token(uow, secret_text, pepper=_Pepper().pepper(), now=clock.now())

    app = replace(app, authenticator=_authenticate)

    boot = app.client(actor=access.SYSTEM_ACTOR, surface=Surface.CLI).dispatch(
        BootstrapLocalOwner(display_name="Owner", token_name="cli")
    )
    assert isinstance(boot, BootstrapLocalOwnerResult)
    owner = Actor(
        principal_id=PrincipalId(boot.principal_id),
        kind=PrincipalKind.HUMAN,
        display_name="Owner",
    )
    return app, owner, state_dir, env


def _run(
    app: App,
    actor: Actor,
    state_dir: Path,
    env: dict[str, str],
    argv: list[str],
) -> tuple[int, dict[str, Any], str]:
    out, err = io.StringIO(), io.StringIO()

    def factory(_opts: object, _env: object) -> Any:
        host_name = None
        written = state_dir / "bootstrap.toml"
        if written.is_file():
            for line in written.read_text(encoding="utf-8").splitlines():
                if line.startswith("name = "):
                    host_name = line.split("=", 1)[1].strip().strip('"')
        return replace(app_backend(app, actor), state_dir=state_dir, host_name=host_name, close=None)

    code = main(["--json", *argv], environ=env, stdout=out, stderr=err, backend=factory)
    payload = json.loads(out.getvalue()) if out.getvalue().strip() else {}
    return code, payload, err.getvalue()


def test_workspace_project_use_host_and_worker_register_and_rotate(  # noqa: PLR0915
    cli_env: tuple[App, Actor, Path, dict[str, str]],
) -> None:
    app, owner, state_dir, env = cli_env

    code, ws_env, err_ws = _run(
        app, owner, state_dir, env, ["workspace", "create", "alpha", "--title", "Alpha"]
    )
    assert code == 0, err_ws
    ws_id = ws_env["result"]["workspace_id"]

    code, proj_env, err_proj = _run(
        app,
        owner,
        state_dir,
        env,
        ["project", "create", "payments", "--title", "Payments", "--workspace", "ws:alpha"],
    )
    assert code == 0, err_proj
    proj_id = proj_env["result"]["project_id"]

    code, use_env, err_use = _run(app, owner, state_dir, env, ["use", "alpha/payments"])
    assert code == 0, err_use
    assert use_env["result"]["workspace_id"] == ws_id
    assert use_env["result"]["project_id"] == proj_id
    ctx_file = state_dir / "cli-context.json"
    xdg_config_ctx = Path(env["XDG_CONFIG_HOME"]) / "skm/cli-context.json"
    state_file = Path(env["XDG_STATE_HOME"]) / "skm/cli-state.json"
    assert ctx_file.is_file()
    assert not xdg_config_ctx.exists()
    assert state_file.is_file()

    # skm use --instance NAME --here and skm use --here --clear manage checkout_bindings in cli-state.json
    code, _here_env, err_here = _run(app, owner, state_dir, env, ["use", "--instance", "local-dev", "--here"])
    assert code == 0, err_here
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert "local-dev" in state_data["checkout_bindings"].values()

    code, clear_here_env, err_clear_here = _run(app, owner, state_dir, env, ["use", "--here", "--clear"])
    assert code == 0, err_clear_here
    assert clear_here_env["result"]["checkout_bindings"] == {}
    assert json.loads(ctx_file.read_text(encoding="utf-8"))["project_id"] == proj_id

    # workspace.default_project is applied when selecting only a workspace
    app.client(actor=owner, surface=Surface.CLI).dispatch(
        settings.SetValue.from_json(
            {
                "key": "workspace.default_project",
                "value": "payments",
                "scope": {"level": "workspace", "scope_id": ws_id},
            }
        )
    )
    code, use_ws_env, err_use_ws = _run(app, owner, state_dir, env, ["use", "alpha"])
    assert code == 0, err_use_ws
    assert use_ws_env["result"]["workspace_id"] == ws_id
    assert use_ws_env["result"]["project_id"] == proj_id

    # Positional host register NAME
    code, host_env, err_host = _run(
        app,
        owner,
        state_dir,
        env,
        ["host", "register", "devbox", "--os", "linux", "--arch", "x86_64"],
    )
    assert code == 0, err_host
    host_id = host_env["result"]["host_id"]
    assert json.loads((state_dir / "host.json").read_text())["host_id"] == host_id

    # Positional worker register NAME (saves token by default to 0700 dir / 0600 file)
    code, worker_env, err_text = _run(
        app,
        owner,
        state_dir,
        env,
        [
            "worker",
            "register",
            "devbox-w1",
            "--runtime",
            "claude_code",
            "--runtime",
            "codex",
            "--isolation",
            "worktree",
            "--max-concurrency",
            "2",
            "--label",
            "gpu:none",
        ],
    )
    assert code == 0, err_text
    worker_id = worker_env["result"]["worker_id"]
    worker_principal_id = worker_env["result"]["principal_id"]
    token_path = Path(worker_env["result"]["token_file"])
    assert token_path == state_dir / "secrets" / "workers" / f"{worker_id}.token"
    assert token_path.is_file()
    assert ((state_dir / "secrets").stat().st_mode & 0o777) == 0o700
    assert ((state_dir / "secrets" / "workers").stat().st_mode & 0o777) == 0o700
    assert (token_path.stat().st_mode & 0o777) == 0o600
    initial_secret = token_path.read_text(encoding="utf-8").strip()
    assert initial_secret.startswith("skm_")
    assert initial_secret not in json.dumps(worker_env)
    assert initial_secret not in err_text

    # Verify exactly ONE worker principal was created by worker register
    principals_view = cast(
        "access.ListPrincipalsView",
        app.client(actor=owner, surface=Surface.CLI).ask(
            access.ListPrincipals.from_json({"kind": "worker", "limit": 50})
        ),
    )
    assert len(principals_view.items) == 1
    assert str(principals_view.items[0].principal_id) == worker_principal_id

    # Authenticate with initial worker token and perform self-rotation
    worker_actor = app.authenticate(initial_secret)
    assert str(worker_actor.principal_id) == worker_principal_id
    code, self_rot_env, self_rot_err = _run(
        app,
        worker_actor,
        state_dir,
        env,
        ["worker", "register", "--rotate", "--force"],
    )
    assert code == 0, self_rot_err
    assert self_rot_env["result"]["rotated"] is True
    assert self_rot_env["result"]["worker_id"] == worker_id
    self_rotated_secret = token_path.read_text(encoding="utf-8").strip()
    assert self_rotated_secret != initial_secret
    assert app.authenticate(self_rotated_secret).principal_id == PrincipalId(UUID(worker_principal_id))

    # Loose permissions on secrets/workers directory are refused with SECRET_PERMISSIONS before RotateToken
    os.chmod(state_dir / "secrets" / "workers", 0o755)  # noqa: S103
    try:
        code_perm, perm_env, _ = _run(
            app,
            owner,
            state_dir,
            env,
            ["worker", "register", "devbox-w1", "--rotate"],
        )
        assert code_perm != 0
        assert perm_env["error"]["code"] == ErrorCode.SECRET_PERMISSIONS.value
        assert token_path.read_text(encoding="utf-8").strip() == self_rotated_secret
    finally:
        os.chmod(state_dir / "secrets" / "workers", 0o700)

    # Positional operator rotation: skm worker register devbox-w1 --rotate
    code, rot_env, rot_err = _run(
        app,
        owner,
        state_dir,
        env,
        ["worker", "register", "devbox-w1", "--rotate"],
    )
    assert code == 0, rot_err
    assert rot_env["result"]["rotated"] is True
    rotated_secret = token_path.read_text(encoding="utf-8").strip()
    assert rotated_secret.startswith("skm_")
    assert rotated_secret != self_rotated_secret
    assert rotated_secret not in json.dumps(rot_env)
    assert rotated_secret not in rot_err
    assert app.authenticate(rotated_secret).principal_id == PrincipalId(UUID(worker_principal_id))

    with pytest.raises(Unauthenticated) as auth_exc:
        app.authenticate("skm_invalid_token_000000000000000000000000")
    assert auth_exc.value.code is ErrorCode.UNAUTHENTICATED

    code, show_env, err_show = _run(app, owner, state_dir, env, ["worker", "show", "devbox-w1"])
    assert code == 0, err_show
    assert show_env["result"]["capabilities"]["runtimes"] == ["claude_code", "codex"]
    assert show_env["result"]["capabilities"]["max_concurrency"] == 2
    assert show_env["result"]["capabilities"]["labels"] == ["gpu:none"]

    code, drain_env, err_drain = _run(app, owner, state_dir, env, ["worker", "drain", "devbox-w1"])
    assert code == 0, err_drain
    assert drain_env["result"]["state"] == "draining"

    code, retire_env, err_retire = _run(app, owner, state_dir, env, ["worker", "retire", "devbox-w1"])
    assert code == 0, err_retire
    assert retire_env["result"]["state"] == "retired"
    assert SYSTEM_PRINCIPAL_ID is not None


def test_repo_cli_register_add_remote_bind_verify_and_archived_use_refusal(
    cli_env: tuple[App, Actor, Path, dict[str, str]],
) -> None:
    app, owner, state_dir, env = cli_env

    _run(app, owner, state_dir, env, ["workspace", "create", "alpha", "--title", "Alpha"])
    _run(app, owner, state_dir, env, ["project", "create", "payments", "--workspace", "alpha"])
    _run(app, owner, state_dir, env, ["use", "alpha/payments"])
    _run(app, owner, state_dir, env, ["host", "register", "devbox", "--os", "linux", "--arch", "x86_64"])

    # skm repo register REMOTE (positional)
    code, reg_env, err_reg = _run(
        app,
        owner,
        state_dir,
        env,
        ["repo", "register", "https://github.com/acme/payments-service.git"],
    )
    assert code == 0, err_reg
    repo_id = reg_env["result"]["repository_id"]

    # skm repo add-remote REPO_REF URL (no extra remote_name positional)
    code, _rem_env, err_rem = _run(
        app,
        owner,
        state_dir,
        env,
        ["repo", "add-remote", repo_id, "git@github.com:acme/payments-mirror.git"],
    )
    assert code == 0, err_rem

    # skm repo bind --path ... --write-marker --yes (human output includes git commit hint)
    out_human, err_human = io.StringIO(), io.StringIO()

    def factory(_opts: object, _env: object) -> Any:
        return replace(app_backend(app, owner), state_dir=state_dir, close=None)

    code_bind = main(
        ["repo", "bind", "--path", "/work/payments", "--project", "payments", "--write-marker", "--yes"],
        environ=env,
        stdout=out_human,
        stderr=err_human,
        backend=factory,
    )
    assert code_bind == 0, err_human.getvalue()
    assert "git add .skm/project.json && git commit" in out_human.getvalue()

    # skm project show includes mounted repositories and binding state via ListProjectRepositories
    code, pshow_env, err_pshow = _run(app, owner, state_dir, env, ["project", "show", "payments"])
    assert code == 0, err_pshow
    assert len(pshow_env["result"]["repositories"]) == 1
    assert pshow_env["result"]["repositories"][0]["binding"]["state"] == "active"

    # skm repo verify
    code, ver_env, err_ver = _run(app, owner, state_dir, env, ["repo", "verify", "--project", "payments"])
    assert code == 0, err_ver
    assert ver_env["result"]["items"][0]["state"] == "active"

    # Archive project without --yes fails requiring confirmation; with --yes succeeds
    code_no_yes, no_yes_env, _ = _run(app, owner, state_dir, env, ["project", "archive", "payments"])
    assert code_no_yes != 0
    assert no_yes_env["error"]["code"] == ErrorCode.SCHEMA_INVALID.value

    # Archive project with --yes and verify skm use refuses archived project with PROJECT_ARCHIVED
    code, arch_env, err_arch = _run(app, owner, state_dir, env, ["project", "archive", "payments", "--yes"])
    assert code == 0, err_arch
    assert arch_env["result"]["project_id"] is not None

    code_list, plist_env, _ = _run(app, owner, state_dir, env, ["project", "list", "--state", "archived"])
    assert code_list == 0
    assert len(plist_env["result"]["items"]) == 1

    code_use_arch, use_arch_env, _ = _run(app, owner, state_dir, env, ["use", "alpha/payments"])
    assert code_use_arch != 0
    assert use_arch_env["error"]["code"] == ErrorCode.PROJECT_ARCHIVED.value


def test_host_register_keeps_the_recorded_host_unless_replace_is_given(
    cli_env: tuple[App, Actor, Path, dict[str, str]],
) -> None:
    app, owner, state_dir, env = cli_env
    register = ["host", "register", "--os", "linux", "--arch", "x86_64"]

    code, first, err = _run(app, owner, state_dir, env, [*register, "devbox"])
    assert code == 0, err
    host_id = first["result"]["host_id"]

    # Before: another name created a second host and silently repointed host.json at it.
    for name in (["laptop"], ["devbox"], []):
        code, refused, _ = _run(app, owner, state_dir, env, [*register, *name])
        assert code != 0
        assert refused["error"]["details"]["reason"] == "host_already_registered"
        assert refused["error"]["details"]["host_id"] == host_id
    assert json.loads((state_dir / "host.json").read_text())["host_id"] == host_id
    listed = _run(app, owner, state_dir, env, ["host", "list"])[1]["result"]["items"]
    assert [item["name"] for item in listed] == ["devbox"]

    code, replaced, err = _run(app, owner, state_dir, env, [*register, "--replace", "laptop"])
    assert code == 0, err
    assert replaced["result"]["host_id"] != host_id
    assert json.loads((state_dir / "host.json").read_text())["host_id"] == replaced["result"]["host_id"]


def _write_init_host_name(state_dir: Path, name: str) -> None:
    (state_dir / "bootstrap.toml").write_text(
        f'''schema = "urn:skm:config:bootstrap:v1"\n[host]\nname = "{name}"\n''',
        encoding="utf-8",
    )


def test_host_register_without_a_name_uses_the_init_host_name(
    cli_env: tuple[App, Actor, Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, owner, state_dir, env = cli_env
    _write_init_host_name(state_dir, "from-init")
    monkeypatch.setattr(
        "skm.modules.workspace.host.register_this_host.std_platform.node", lambda: "from-uname"
    )
    code, payload, err = _run(
        app, owner, state_dir, env, ["host", "register", "--os", "linux", "--arch", "x86_64"]
    )
    assert code == 0, err
    # Before: platform.node() ("from-uname") was used, ignoring skm init --host-name.
    assert payload["result"]["name"] == "from-init"


def test_host_register_defaults_to_the_recorded_name(
    cli_env: tuple[App, Actor, Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, owner, state_dir, env = cli_env
    register = ["host", "register", "--os", "linux", "--arch", "x86_64"]
    code, first, err = _run(app, owner, state_dir, env, [*register, "devbox"])
    assert code == 0, err
    host_id = first["result"]["host_id"]
    # A later edit of bootstrap host.name must not become the default on --replace.
    _write_init_host_name(state_dir, "from-init")
    monkeypatch.setattr(
        "skm.modules.workspace.host.register_this_host.std_platform.node", lambda: "from-uname"
    )

    code, kept, err = _run(app, owner, state_dir, env, [*register, "--replace"])
    assert code == 0, err
    assert kept["result"]["host_id"] == host_id
    assert kept["result"]["name"] == "devbox"
    assert json.loads((state_dir / "host.json").read_text())["host_id"] == host_id
    listed = _run(app, owner, state_dir, env, ["host", "list"])[1]["result"]["items"]
    assert [item["name"] for item in listed] == ["devbox"]


def test_host_register_refuses_a_conflicting_platform_on_reuse(
    cli_env: tuple[App, Actor, Path, dict[str, str]],
) -> None:
    app, owner, state_dir, env = cli_env
    args = ["host", "register", "devbox"]
    assert _run(app, owner, state_dir, env, [*args, "--os", "linux"])[0] == 0
    before = (state_dir / "host.json").read_bytes()
    code, reply, _ = _run(app, owner, state_dir, env, [*args, "--replace", "--os", "windows"])
    assert code != 0
    assert reply["error"]["details"]["reason"] == "host_platform_mismatch"
    assert (state_dir / "host.json").read_bytes() == before
