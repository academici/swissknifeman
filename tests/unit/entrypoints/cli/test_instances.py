"""Exercise selection, profile writes and health through the public CLI."""

import io
import json
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import httpx
import pytest

from skm.entrypoints.cli.context import CliOptions, CliSession
from skm.entrypoints.cli.main import main
from skm.kernel.errors import NotFound
from skm.platform.config.sources.bootstrap import ProfileCatalog, cli_state_path, save_selection
from skm.platform.generated.queries import Doctor
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

EXAMPLES = Path(__file__).resolve().parents[4] / "tests/fixtures/corpus/examples/config"
DSN = "postgresql://skm:private-dsn-password@localhost/skm"
TOKEN = "private-token-value"
REF = "secret://keyring/skm-team/cli-token"


def instance_check(identity, version):
    return {
        "id": "platform.instance",
        "status": "ok",
        "message": "Backend instance",
        "hint": None,
        "details": {
            "target": "instance",
            "detail": json.dumps({"instance_id": str(identity), "schema_version": version}),
            "path": None,
        },
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = tmp_path / "bootstrap.toml"
    path.write_bytes((EXAMPLES / "bootstrap.profiles.toml").read_bytes())
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    monkeypatch.chdir(checkout)
    return {"HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "state"), "SKM_BOOTSTRAP": str(path)}


def cli(env, *argv, json_mode=True, code=0) -> Any:
    out, err = io.StringIO(), io.StringIO()
    flags = ["--json"] if json_mode else []
    actual = main([*flags, *argv], stdout=out, stderr=err, environ=env)
    text = out.getvalue() + err.getvalue()
    assert all(secret not in text for secret in (DSN, "private-dsn-password", TOKEN, REF))
    assert actual == code, text
    if json_mode:
        envelope = json.loads(out.getvalue())
        return envelope["error" if code else "result"]
    return text


def current(env, *global_flags):
    rows = cli(env, *global_flags, "instance", "list")
    return [r["name"] for r in rows if r["current"]]


def test_precedence_nearest_real_checkout_and_clear(setup, monkeypatch):
    from skm.bootstrap import instance_profiles

    monkeypatch.setattr(instance_profiles, "verified_config", lambda config, *_: config)
    parent = Path.cwd()
    child = parent / "nested"
    child.mkdir()
    link = Path(setup["HOME"]) / "linked"
    link.symlink_to(child)
    assert current(setup) == ["personal"]
    cli(setup, "instance", "use", "team")
    assert current(setup) == ["team"]
    cli(setup, "instance", "use", "personal", "--here")
    monkeypatch.chdir(link)
    assert current(setup) == ["personal"]
    cli(setup, "instance", "use", "team", "--here")
    assert current(setup) == ["team"]
    env = {**setup, "SKM_INSTANCE": "personal"}
    assert current(env) == ["personal"]
    assert current(env, "--instance", "team") == ["team"]
    child_state = cli_state_path(setup, Path(setup["HOME"]))
    assert json.loads(child_state.read_text())["checkout_bindings"][str(child)] == "team"
    assert child_state.stat().st_mode & 0o777 == 0o600
    cli(setup, "instance", "use", "team", "--here", "--clear")
    assert current(setup) == ["personal"]
    monkeypatch.chdir(parent)
    cli(setup, "instance", "use", "personal", "--here", "--clear")
    assert current(setup) == ["team"]
    cli(setup, "instance", "use", "team", "--clear")
    assert current(setup) == ["personal"]


@pytest.mark.parametrize("level", ["flag", "env", "parent", "saved", "default"])
def test_unknown_at_selected_level_is_terminal(setup, level, monkeypatch):
    parent = Path.cwd()
    child = parent / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    state: dict[str, object] = {"schema": "urn:skm:cli:state:v1", "current_instance": "team"}
    env, args = dict(setup), []
    if level == "flag":
        env["SKM_INSTANCE"] = "team"
        args = ["--instance", "removed"]
    elif level == "env":
        env["SKM_INSTANCE"] = "removed"
    elif level == "parent":
        state["checkout_bindings"] = {str(parent): "removed"}
    elif level == "saved":
        state["current_instance"] = "removed"
    else:
        state.pop("current_instance")
        bootstrap = Path(env["SKM_BOOTSTRAP"])
        bootstrap.write_text(
            bootstrap.read_text().replace('default_instance = "personal"', 'default_instance = "removed"')
        )
    path = cli_state_path(env, Path(env["HOME"]))
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(state))
    error = cli(env, *args, "instance", "list", code=1)
    assert error["code"] == "INSTANCE_UNKNOWN"
    assert error["details"]["name"] == "removed"


@pytest.mark.parametrize("json_mode", [False, True])
def test_add_embedded_profile_stores_a_private_dsn_reference(setup, json_mode):
    added = cli(
        setup, "instance", "add", "lab", "--mode", "embedded", "--database-url", DSN, json_mode=json_mode
    )
    assert "lab" in str(added)
    path = Path(setup["SKM_BOOTSTRAP"])
    assert path.stat().st_mode & 0o777 == 0o600
    assert DSN not in path.read_text()
    ref = tomllib.loads(path.read_text())["instances"]["lab"]["database"]["url"]
    secret_file = Path(ref.removeprefix("secret://file/"))
    assert secret_file.read_text() == DSN
    assert secret_file.stat().st_mode & 0o777 == 0o600


def test_add_duplicate_or_invalid_is_atomic(setup):
    path = Path(setup["SKM_BOOTSTRAP"])
    before = path.read_bytes()
    assert cli(setup, "instance", "add", "team", code=6)["code"] == "ALREADY_EXISTS"
    for args in (
        ["Invalid", "--database-url", DSN],
        ["lab", "--mode", "http", "--database-url", DSN, "--api-endpoint", "https://work/api/v1"],
        ["lab", "--mode", "embedded", "--credential", REF],
        ["lab", "--mode", "http", "--api-endpoint", "https://work/api/v1", "--credential", TOKEN],
    ):
        assert cli(setup, "instance", "add", *args, code=1)["code"] == "CONFIG_INVALID"
    assert path.read_bytes() == before


def test_legacy_default_and_first_add_preserve_identity_and_directories(setup):
    path = Path(setup["SKM_BOOTSTRAP"])
    path.write_bytes((EXAMPLES / "bootstrap.local.toml").read_bytes())
    assert current(setup, "--instance", "default") == ["default"]
    home = Path(setup["HOME"])
    before = ProfileCatalog.read(str(path), setup, home).config("default")
    cli(setup, "instance", "add", "second")
    after = ProfileCatalog.read(str(path), setup, home).config("default")
    for key in ("instance_id", "state_dir", "blobs_root", "token_pepper", "host_id", "host_name"):
        assert getattr(before, key) == getattr(after, key)
    assert current(setup) == ["default"]
    path.unlink()
    cli(setup, "instance", "add", "first")
    assert current(setup) == ["first"]


@pytest.mark.parametrize("json_mode", [False, True])
def test_embedded_show_uses_platform_doctor_and_closes_app(setup, monkeypatch, json_mode):
    import skm.bootstrap.composition as composition
    from skm.platform.generated.results import DoctorResult

    seen = []
    identity = (
        ProfileCatalog.read(setup["SKM_BOOTSTRAP"], setup, Path(setup["HOME"])).config("personal").instance_id
    )

    def ask(query):
        seen.append(type(query))
        return DoctorResult.from_json({"checks": [instance_check(identity, 19)]})

    def open_app(config, **_kwargs):
        seen.append(config.access_mode)
        return SimpleNamespace(
            client=lambda **_: SimpleNamespace(ask=ask), close=lambda: seen.append("closed")
        ), None

    monkeypatch.setattr(composition, "open_cli_app", open_app)
    result = cli(setup, "instance", "show", "personal", json_mode=json_mode)
    if json_mode:
        assert result["available"]
        assert result["healthy"]
        assert result["schema_version"] == 19
    else:
        assert all(value in result for value in ("personal", "embedded", "schema_version"))
    assert seen == ["embedded", Doctor, "closed"]


def test_profiles_do_not_inherit_workspace_or_project_even_with_a_shared_state_dir(setup):
    home = Path(setup["HOME"])
    catalog = ProfileCatalog.read(setup["SKM_BOOTSTRAP"], setup, home)
    personal, team = (catalog.config(name) for name in ("personal", "team"))
    assert personal.state_dir != team.state_dir
    assert personal.blobs_root != team.blobs_root
    assert personal.api_credential is None
    assert team.database_url is None
    personal.state_dir.mkdir(parents=True)

    def session(instance):
        return CliSession(
            CliOptions(),
            io.StringIO(),
            io.StringIO(),
            Redactor(),
            Uuid7Generator(SystemClock()),
            "test",
            state_dir=personal.state_dir,
            instance_id=instance.instance_id,
        )

    local = session(personal)
    local.save_context(workspace_id=str(UUID(int=1)), project_id=str(UUID(int=2)))
    assert local.resolve_project(None) == UUID(int=2)
    remote = session(team)
    for resolve in (remote.resolve_workspace, remote.resolve_project):
        with pytest.raises(NotFound) as caught:
            resolve(None)
        assert caught.value.details["kind"] in {"workspace", "project"}
    assert "another instance" in cast("io.StringIO", remote.stderr).getvalue()


@pytest.mark.parametrize("renamed", [False, True])
def test_interrupted_bootstrap_write_keeps_dsn_only_if_referenced(setup, monkeypatch, renamed):
    from skm.platform.config.sources import bootstrap as source

    target = Path(setup["SKM_BOOTSTRAP"])
    original = target.read_bytes()
    write = source.atomic_write

    def fail_at_replace(path, content, **kwargs):
        if path != target or renamed:
            write(path, content, **kwargs)
        if path == target:
            raise OSError("interrupted")

    monkeypatch.setattr(source, "atomic_write", fail_at_replace)
    profile = source.NewProfile("lab", UUID(int=42), "embedded", DSN, None, None)
    with pytest.raises(OSError, match="interrupted"):
        source.add_profile(target, profile)
    stored = list((target.parent / "secrets").glob("*.dsn"))
    if renamed:
        ref = tomllib.loads(target.read_text())["instances"]["lab"]["database"]["url"]
        assert stored == [Path(ref.removeprefix("secret://file/"))]
        assert stored[0].read_text() == DSN
    else:
        assert target.read_bytes() == original
        assert not stored


def test_use_alias_can_bind_and_clear_before_connecting(setup, monkeypatch):
    import skm.entrypoints.cli.main as entrypoint

    def unexpected_backend(*_args, **_kwargs):
        pytest.fail("an instance-only selection must work offline")

    monkeypatch.setattr(entrypoint, "production_backend", unexpected_backend)
    cli(setup, "instance", "add", "second")
    cli(setup, "use", "--instance", "second", "--here")
    assert current(setup) == ["second"]
    cli(setup, "use", "--instance", "second", "--here", "--clear")
    assert current(setup) == ["personal"]
    cli(setup, "use", "--instance", "second")
    assert current(setup) == ["second"]


def test_use_alias_does_not_persist_an_unverified_http_profile(setup):
    path = cli_state_path(setup, Path(setup["HOME"]))
    assert cli(setup, "use", "--instance", "team", code=1)["code"] == "CONFIG_INVALID"
    assert not path.exists()
    cli(setup, "use", "--instance", "personal")
    before = path.read_bytes()
    assert cli(setup, "use", "--instance", "team", "--here", code=1)["code"] == "CONFIG_INVALID"
    assert path.read_bytes() == before
    assert current(setup) == ["personal"]


def test_backend_commands_use_the_saved_profile(setup, monkeypatch):
    import skm.entrypoints.cli.main as entrypoint
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import BackendUnavailable

    selected = []

    def capture(config, **_kwargs):
        selected.append(config.instance_profile)
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "offline")

    cli(setup, "instance", "add", "second")
    cli(setup, "instance", "use", "second")
    monkeypatch.setattr(entrypoint, "open_cli_app", capture)
    cli(setup, "whoami", code=3)
    assert selected == ["second"]


def test_workspace_list_allows_an_explicit_stateless_http_profile_and_actor(setup, monkeypatch):
    seen = []

    def send(_self, request, **_kwargs):
        seen.append((request.method, request.url.host, request.url.path, request.headers["Authorization"]))
        if request.url.path == "/api/v1/me":
            return httpx.Response(
                200,
                json={
                    "principal": {
                        "principal_id": str(UUID(int=1)),
                        "kind": "human",
                        "display_name": "Owner",
                        "state": "active",
                        "created_at": "2026-10-29T12:00:00Z",
                        "row_version": 1,
                        "identities": [],
                    },
                    "token": None,
                    "memberships": [],
                    "effective_permissions": ["workspace.read"],
                    "modules": {"knowledge": True, "learning": True, "exports": True},
                    "permissions_by_scope": {},
                    "events_cursor": None,
                },
                headers={"SKM-Instance-Id": request.headers["SKM-Instance-Id"]},
                request=request,
            )
        return httpx.Response(
            200,
            json={"items": [], "next": None},
            headers={"SKM-Instance-Id": request.headers["SKM-Instance-Id"]},
            request=request,
        )

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=lambda *_: TOKEN))
    child = Path.cwd() / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    assert cli(setup, "--instance", "team", "workspace", "list")["items"] == []
    assert cli(setup, "--instance", "team", "--as-token", "other-actor", "workspace", "list")["items"] == []
    assert seen == [
        ("GET", "skm.example.com", path, f"Bearer {token}")
        for token in (TOKEN, "other-actor")
        for path in ("/api/v1/me", "/api/v1/workspaces")
    ]
    error = cli({**setup, "SKM_INSTANCE": "removed"}, "workspace", "list", code=1)
    assert error["code"] == "INSTANCE_UNKNOWN"
    error = cli(setup, "use", "--instance", "removed", "--here", code=1)
    assert error["code"] == "INSTANCE_UNKNOWN"
    assert current(setup) == ["personal"]


@pytest.mark.parametrize(
    "command",
    [
        ("use", "--here", "--clear"),
        ("use", "--instance", "team", "--here", "--clear"),
        ("instance", "use", "team", "--here", "--clear"),
    ],
)
def test_clear_only_current_checkout(setup, command):
    cli(setup, "instance", "use", "personal")
    path = cli_state_path(setup, Path(setup["HOME"]))
    save_selection(path, name="team", directory=Path.cwd())
    cli(setup, *command)
    state = json.loads(path.read_text())
    assert state["current_instance"] == "personal"
    assert state["checkout_bindings"] == {}


@pytest.mark.parametrize("flags", [(), ("--here",), ("--instance", "team"), ("--instance", "team", "--here")])
def test_clear_conflicting_ref_preserves_state(setup, flags):
    cli(setup, "instance", "use", "personal")
    path = cli_state_path(setup, Path(setup["HOME"]))
    save_selection(path, name="team", directory=Path.cwd())
    before = path.read_bytes()
    assert cli(setup, "use", "personal/demo", *flags, "--clear", code=1)["code"] == "SCHEMA_INVALID"
    assert path.read_bytes() == before


def test_http_add_verifies_explicit_identity_and_missing_details_are_atomic(setup, monkeypatch):
    identifier = UUID(int=32)
    args = ("--mode", "http", "--api-endpoint", "https://work.example/api/v1", "--credential", REF)
    calls = []

    def missing_identity(_client, request, **_kwargs):
        requested = request.headers.get("SKM-Instance-Id")
        calls.append((request.url.path, requested))
        headers = {"SKM-Instance-Id": requested} if requested else {}
        return httpx.Response(200, json={"checks": []}, headers=headers, request=request)

    monkeypatch.setattr(httpx.Client, "send", missing_identity)
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=lambda *_: TOKEN))
    path = Path(setup["SKM_BOOTSTRAP"])
    before = path.read_bytes()
    assert (
        cli(setup, "instance", "add", "expected", "--instance-id", str(identifier), *args, code=1)["code"]
        == "CONFIG_INVALID"
    )
    assert cli(setup, "instance", "add", "undiscovered", *args, code=1)["code"] == "CONFIG_INVALID"
    assert path.read_bytes() == before
    assert calls == [("/api/v1/doctor", str(identifier)), ("/api/v1/doctor", None)]


def test_http_slug_resolution_follows_both_cursors(setup, monkeypatch):
    workspace_id, project_id = str(UUID(int=31)), str(UUID(int=32))
    workspace = {"workspace_id": workspace_id, "slug": "personal", "title": "Personal", "state": "active"}
    project = {"project_id": project_id, "slug": "demo", "title": "Demo", "state": "active"}
    workspaces = "/api/v1/workspaces"
    projects = f"{workspaces}/{workspace_id}/projects"
    pages = []

    def send(_client, request, **_kwargs):
        path = request.url.path
        if path in (workspaces, projects):
            after = request.url.params.get("after")
            pages.append((path, after))
            summary = workspace if path == workspaces else project
            body = {"items": [], "next": "page2"} if after is None else {"items": [summary], "next": None}
        elif path == f"{workspaces}/{workspace_id}":
            body = {**workspace, "row_version": 1, "project_count": 1}
        elif path == f"/api/v1/projects/{project_id}":
            body = {
                **project,
                "workspace_id": workspace_id,
                "row_version": 1,
                "description": "",
                "mounts": [],
            }
        else:
            pytest.fail(f"unexpected request to {path}")
        return httpx.Response(
            200, json=body, headers={"SKM-Instance-Id": request.headers["SKM-Instance-Id"]}, request=request
        )

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=lambda *_: TOKEN))
    # A project without a host binding still resolves its complete project view.
    from skm.bootstrap.instance_secrets import open_http_client
    from skm.entrypoints.cli.commands.project import resolve_project_view

    session = CliSession(
        CliOptions(), io.StringIO(), io.StringIO(), Redactor(), Uuid7Generator(SystemClock()), "test"
    )
    config = ProfileCatalog.read(setup["SKM_BOOTSTRAP"], setup, Path(setup["HOME"])).config("team")
    client = open_http_client(config, setup, as_token=None, on_secret=lambda _: None)
    try:
        session.client_ = client
        assert str(resolve_project_view(session, "personal/demo").project_id) == project_id
    finally:
        client.close()
    assert pages == [(workspaces, None), (workspaces, "page2"), (projects, None), (projects, "page2")]
