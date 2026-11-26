"""CLI identity (security S2) and the identity groups ``whoami``, ``token``, ``principal``, ``member``.

Two layers. The acting principal: ``resolve_cli_actor`` takes ``--as-token`` or the owner token file of the
state directory (private directory, 0600 file), authenticates it with the real ``authenticate_token`` and
never falls back to another identity; a missing, loose, revoked or foreign credential is refused. The
production composition (``build_app`` without ``overrides``) is the PostgreSQL one, real authorizer: it
needs the token pepper before it opens anything. The groups: each command sends the owner module's DTO through
the bus with the real ``RbacAuthorizer`` (the access harness), prints a secret once and never in a list, and
reports a refusal with its exit code.
"""

import json
import os
from collections.abc import Generator
from dataclasses import replace
from io import StringIO
from pathlib import Path
from runpy import run_path
from typing import Any
from uuid import UUID

import pytest

from skm.application_bus.client import EmbeddedClient
from skm.bootstrap import composition, composition_resources
from skm.bootstrap.composition import (
    OWNER_TOKEN_FILE,
    CompositionOverrides,
    StoredScopeChain,
    build_app,
    open_cli_app,
    resolve_cli_actor,
)
from skm.entrypoints.cli.commands import GROUPS
from skm.entrypoints.cli.commands.member import GROUP as MEMBER
from skm.entrypoints.cli.commands.principal import GROUP as PRINCIPAL
from skm.entrypoints.cli.commands.principal import principal_ref
from skm.entrypoints.cli.commands.token import GROUP as TOKEN
from skm.entrypoints.cli.commands.token import duration
from skm.entrypoints.cli.commands.whoami import GROUP as WHOAMI
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    BackendUnavailable,
    CapabilityUnavailable,
    PreconditionFailed,
    SkmError,
    Unauthenticated,
    ValidationFailed,
)
from skm.kernel.ports_uow import Surface
from skm.modules.access.application.authorizer import RbacAuthorizer
from skm.modules.access.domain.roles import Role
from skm.modules.access.domain.token import TokenId
from skm.platform.config.bootstrap import BootstrapConfig, load_bootstrap
from skm.platform.logging import setup

access: dict[str, Any] = run_path(str(Path(__file__).parents[2] / "access/application/test_authorizer.py"))
live: dict[str, Any] = run_path(str(Path(__file__).parents[2] / "access/application/test_live_revocation.py"))
WS, INSTANCE = access["WS"], access["INSTANCE"]
PEPPER_TEXT = "0123456789abcdef" * 4
# nothing listens on port 1 of the loopback: a build that reaches the database is refused at once
ENV = {"SKM_DATABASE_URL": "postgresql://skm@127.0.0.1:1/skm"}


# ------------------------------------------------------------------------------------------ the actor


class Sealed:
    """An instance directory as ``skm init`` leaves it: ``secrets/`` (0700) with a token file (0600)."""

    def __init__(self, root: Path) -> None:
        self.state = root / "state"
        self.directory = self.state / OWNER_TOKEN_FILE.parent
        self.file = self.state / OWNER_TOKEN_FILE
        self.directory.mkdir(parents=True, mode=0o700)
        os.chmod(self.directory, 0o700)

    def write(self, secret: str, mode: int = 0o600) -> None:
        self.file.write_text(secret + "\n")
        os.chmod(self.file, mode)


def bootstrap(root: Path, state: Path | None = None, *, pepper: Path | None = None) -> BootstrapConfig:
    lines = [
        'schema = "urn:skm:config:bootstrap:v1"',
        'instance_id = "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c11"',
        '[access]\nmode = "embedded"',
        '[database]\nurl = "secret://env/SKM_DATABASE_URL"',
        f'[paths]\nstate_dir = "{state or root / "state"}"\nblobs_root = "{root / "blobs"}"',
    ]
    if pepper is not None:
        lines.append(f'[secrets]\ntoken_pepper = "secret://file/{pepper}"')
    path = root / "bootstrap.toml"
    path.write_text("\n".join(lines) + "\n")
    os.chmod(path, 0o600)
    return load_bootstrap(str(path), ENV, root)


@pytest.fixture
def world(tmp_path: Path) -> Generator[dict[str, Any]]:
    made = live["world"]()["h"]
    config = bootstrap(tmp_path)
    app = build_app(
        config,
        surface=Surface.CLI,
        environ=ENV,
        invocation={},
        overrides=CompositionOverrides(authorizer=RbacAuthorizer(made.clock), scopes=StoredScopeChain()),
    )
    app = replace(app, authenticator=made.actor)  # the real authenticate_token
    yield {"made": made, "app": app, "config": config, "tmp": tmp_path, "secrets": made.secrets}
    app.close()


def test_the_owner_token_file_is_the_acting_identity(world: dict[str, Any]) -> None:
    sealed = Sealed(world["tmp"])
    sealed.write(world["secrets"]["owner"])
    seen: list[str] = []
    actor = resolve_cli_actor(world["app"], world["config"], as_token=None, on_secret=seen.append)
    assert actor.display_name == "owner"
    assert actor.grant is not None
    assert seen == [world["secrets"]["owner"]]  # the surface can register it for redaction


def test_as_token_wins_over_the_owner_file_and_is_never_replaced_by_it(world: dict[str, Any]) -> None:
    sealed = Sealed(world["tmp"])
    sealed.write(world["secrets"]["owner"])
    actor = resolve_cli_actor(world["app"], world["config"], as_token=world["secrets"]["alice"])
    assert actor.display_name == "alice"
    with pytest.raises(Unauthenticated):  # a wrong --as-token does not fall back to the owner file
        resolve_cli_actor(world["app"], world["config"], as_token="skm_aaaaaaaa_" + "A" * 43)


def test_no_owner_token_is_unauthenticated_with_a_hint_not_an_anonymous_actor(world: dict[str, Any]) -> None:
    with pytest.raises(Unauthenticated) as caught:  # no secrets directory at all
        resolve_cli_actor(world["app"], world["config"], as_token=None)
    assert caught.value.details["reason"] == "owner_token_missing"
    assert "skm init" in str(caught.value.details["hint"])
    Sealed(world["tmp"])  # the directory exists, the file does not
    with pytest.raises(Unauthenticated) as caught:
        resolve_cli_actor(world["app"], world["config"], as_token=None)
    assert caught.value.details["reason"] == "owner_token_missing"


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o666, 0o604])
def test_a_token_file_with_loose_permissions_is_refused_before_it_is_read(
    world: dict[str, Any], mode: int
) -> None:
    sealed = Sealed(world["tmp"])
    sealed.write(world["secrets"]["owner"], mode)
    seen: list[str] = []
    with pytest.raises(SkmError) as caught:
        resolve_cli_actor(world["app"], world["config"], as_token=None, on_secret=seen.append)
    assert caught.value.details.get("reason") == "secret_file_permissions"
    assert seen == []


@pytest.mark.parametrize("mode", [0o755, 0o750, 0o707])
def test_a_secrets_directory_that_is_not_private_is_refused(world: dict[str, Any], mode: int) -> None:
    sealed = Sealed(world["tmp"])
    sealed.write(world["secrets"]["owner"])
    os.chmod(sealed.directory, mode)
    with pytest.raises(PreconditionFailed) as caught:
        resolve_cli_actor(world["app"], world["config"], as_token=None)
    assert caught.value.code is ErrorCode.SECRET_PERMISSIONS
    assert caught.value.details["reason"] == "mode"


def test_a_symlinked_secrets_directory_is_refused(world: dict[str, Any]) -> None:
    real = world["tmp"] / "elsewhere"
    real.mkdir(mode=0o700)
    (real / "owner.token").write_text(world["secrets"]["owner"])
    os.chmod(real / "owner.token", 0o600)
    state = world["tmp"] / "state"
    state.mkdir()
    (state / "secrets").symlink_to(real)
    with pytest.raises(PreconditionFailed) as caught:
        resolve_cli_actor(world["app"], world["config"], as_token=None)
    assert caught.value.details["reason"] == "not_a_directory"


def test_a_revoked_owner_token_is_unauthenticated_at_the_next_invocation(world: dict[str, Any]) -> None:
    made = world["made"]
    sealed = Sealed(world["tmp"])
    sealed.write(world["secrets"]["owner"])
    token_id = made.actor("owner").grant.token_id
    made.run(access["commands"].RevokeToken(token_id=token_id), made.actor("owner"))
    with pytest.raises(Unauthenticated):
        resolve_cli_actor(world["app"], world["config"], as_token=None)
    assert TokenId(token_id) in made.tokens


def test_an_app_without_an_authenticator_refuses_to_pick_an_actor(tmp_path: Path) -> None:
    app = build_app(
        bootstrap(tmp_path),
        surface=Surface.CLI,
        environ=ENV,
        invocation={},
        overrides=CompositionOverrides(
            authorizer=RbacAuthorizer(access["rbac_harness"]().clock), scopes=StoredScopeChain()
        ),
    )
    try:
        with pytest.raises(CapabilityUnavailable):
            app.authenticate("skm_aaaaaaaa_" + "A" * 43)
    finally:
        app.close()


@pytest.mark.parametrize("damaged_host_record", [False, True])
def test_open_cli_app_returns_the_app_with_its_actor_and_closes_it_on_a_refusal(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch, damaged_host_record: bool
) -> None:
    app = world["app"]
    monkeypatch.setattr(composition, "build_cli_app", lambda *_a, **_k: app)
    sealed = Sealed(world["tmp"])
    sealed.write(world["secrets"]["owner"])
    if damaged_host_record:
        (world["config"].state_dir / "host.json").write_text("{")
    opened, actor = open_cli_app(world["config"], environ=ENV, invocation={}, as_token=None)
    assert opened.bus is app.bus
    assert opened.uow_factory is app.uow_factory
    assert opened.closed is app.closed
    assert actor.display_name == "owner"
    assert app.closed == [False]
    os.chmod(sealed.file, 0o644)  # a loose token file: the App must not outlive the refusal
    with pytest.raises(SkmError):
        open_cli_app(world["config"], environ=ENV, invocation={}, as_token=None)
    assert app.closed == [True]


def test_open_cli_app_binds_subscriptions_for_recorded_auto_host(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    app = world["app"]
    config = world["config"]
    monkeypatch.setattr(composition, "build_cli_app", lambda *_a, **_k: app)
    Sealed(world["tmp"]).write(world["secrets"]["owner"])
    host_id = UUID(int=42)
    (config.state_dir / "host.json").write_text(json.dumps({"host_id": str(host_id)}))

    opened, actor = open_cli_app(config, environ=ENV, invocation={}, as_token=None)

    assert actor.display_name == "owner"
    assert opened.host is not None
    assert opened.host.host_id == host_id
    assert opened.host_id == host_id


# ------------------------------------------------------------------------------------ the production path


def test_production_composition_needs_a_pepper_and_touches_nothing_before_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_connection(*_a: object, **_k: object) -> None:
        raise AssertionError("the database must not be contacted without a token pepper")

    monkeypatch.setattr(composition_resources, "connect_single", no_connection)
    monkeypatch.setattr(composition, "create_pool", no_connection)
    with pytest.raises(PreconditionFailed) as caught:
        build_app(bootstrap(tmp_path), surface=Surface.CLI, environ=ENV, invocation={})
    assert caught.value.code is ErrorCode.SECRET_UNAVAILABLE
    short = tmp_path / "short-pepper"
    short.write_text("tiny\n")
    os.chmod(short, 0o600)
    with pytest.raises(PreconditionFailed) as caught:
        build_app(bootstrap(tmp_path, pepper=short), surface=Surface.CLI, environ=ENV, invocation={})
    assert caught.value.details["reason"] == "too_short"


def test_production_composition_is_the_real_one_not_a_refusal(tmp_path: Path) -> None:
    pepper = tmp_path / "pepper"
    pepper.write_text(PEPPER_TEXT + "\n")
    os.chmod(pepper, 0o600)
    # With a pepper the build goes on to the database (nothing listens on port 1): the earlier answer,
    # CAPABILITY_UNAVAILABLE "not available in this build", is gone and no fallback authorizer exists.
    with pytest.raises(BackendUnavailable):
        build_app(bootstrap(tmp_path, pepper=pepper), surface=Surface.CLI, environ=ENV, invocation={})


def test_production_stays_embedded_and_postgres_only(tmp_path: Path) -> None:
    pepper = tmp_path / "pepper"
    pepper.write_text(PEPPER_TEXT + "\n")
    os.chmod(pepper, 0o600)
    config = bootstrap(tmp_path, pepper=pepper)
    with pytest.raises(CapabilityUnavailable):
        build_app(config, surface=Surface.CLI, environ=ENV, invocation={}, backend="memory")
    http = load_bootstrap(
        None,
        {"SKM_API_ENDPOINT": "https://skm.example.com/api/v1", "SKM_API_TOKEN": "fixture-token-value"},
        tmp_path,
    )
    with pytest.raises(CapabilityUnavailable) as caught:
        build_app(http, surface=Surface.CLI, environ=ENV, invocation={})
    assert "P11.04.a" in str(caught.value.details["owner"])


def test_no_allow_all_authorizer_is_reachable_from_the_composition_module() -> None:
    source = Path(composition.__file__).read_text()
    assert "AllowAll" not in source
    assert "SingleOwner" not in source
    assert "RbacAuthorizer(clock)" in source


# ----------------------------------------------------------------------------------------------- groups


def test_the_identity_groups_are_discovered_and_belong_to_access() -> None:
    for group in (WHOAMI, TOKEN, PRINCIPAL, MEMBER):
        assert group in GROUPS
        assert group.requires_backend is True
        assert group.module == "access"


def test_duration_and_principal_references_are_strict() -> None:
    assert duration("30d").days == 30
    assert duration("12h").total_seconds() == 12 * 3600
    for bad in ("", "0d", "-1d", "1w", "10", "1d2h", "d"):
        with pytest.raises(ValidationFailed):
            duration(bad)
    assert principal_ref("principal:" + str(UUID(int=3))) == UUID(int=3)
    assert principal_ref(str(UUID(int=4))) == UUID(int=4)
    with pytest.raises(ValidationFailed) as caught:
        principal_ref("alice")
    assert caught.value.code is ErrorCode.INVALID_REFERENCE


class Cli:
    """``main`` over the access harness bus: the real ``RbacAuthorizer``, one acting credential per call."""

    def __init__(self, made: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup._state, "settings", setup._state.settings)
        self.made = made

    def client(self, actor: Actor) -> EmbeddedClient:
        def no_events() -> Any:
            raise AssertionError("no event reader is used here")

        return EmbeddedClient(
            self.made.bus,
            actor=actor,
            surface=Surface.CLI,
            events=no_events,
            clock=self.made.clock,
            ids=self.made.ids,
            client_label="cli/memory",
        )

    def run(self, label: str, *args: str, json_mode: bool = True) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        actor = self.made.actor(label)

        def backend(_options: object, _environ: object) -> Backend:
            return Backend(client=self.client(actor))

        code = main(
            [*(["--json"] if json_mode else []), *args], environ={}, stdout=out, stderr=err, backend=backend
        )
        return code, out.getvalue(), err.getvalue()

    def result(self, label: str, *args: str) -> Any:
        code, out, err = self.run(label, *args)
        assert code == 0, (out, err)
        envelope = json.loads(out)
        assert envelope["ok"] is True
        return envelope["result"]


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> Cli:
    made = live["world"]()["h"]
    return Cli(made, monkeypatch)


def test_whoami_reports_the_live_identity(cli: Cli) -> None:
    result = cli.result("owner", "whoami")
    assert result["principal"]["display_name"] == "owner"
    assert result["token"]["kind"] == "personal"
    assert "principal.manage" in result["effective_permissions"]
    code, out, _ = cli.run("owner", "whoami", json_mode=False)
    assert code == 0
    assert "owner (human)" in out


def test_a_revoked_credential_is_exit_5_unauthenticated_for_every_identity_command(cli: Cli) -> None:
    made = cli.made
    actor = made.actor("alice")
    made.run(access["commands"].RevokeToken(token_id=actor.grant.token_id), made.actor("owner"))

    def stale(_options: object, _environ: object) -> Backend:
        return Backend(client=cli.client(actor))

    for argv in (
        ["whoami"],
        ["token", "list"],
        ["principal", "list"],
        ["member", "list", "--principal", str(UUID(int=1))],
    ):
        out, err = StringIO(), StringIO()
        code = main(argv, environ={}, stdout=out, stderr=err, backend=stale)
        assert code == 5, argv
        assert err.getvalue().startswith("error: UNAUTHENTICATED: ")


def test_token_create_prints_the_secret_once_with_a_warning_and_lists_never_show_it(cli: Cli) -> None:
    code, out, err = cli.run("alice", "token", "create", "laptop", json_mode=False)
    assert code == 0, err
    secret = next(line.split()[1] for line in out.splitlines() if line.startswith("secret  "))
    assert secret.startswith("skm_")
    assert "shown once" in out
    code, listing, _ = cli.run("alice", "token", "list", json_mode=False)
    assert code == 0
    assert "laptop" in listing
    assert secret not in listing
    assert secret not in json.dumps(cli.result("alice", "token", "list"))
    created = cli.result("alice", "token", "create", "second")
    assert created["secret"].startswith("skm_")


def test_token_create_save_writes_a_private_file_and_prints_no_secret(cli: Cli, tmp_path: Path) -> None:
    target = tmp_path / "out" / "new.token"
    code, out, err = cli.run("alice", "token", "create", "saved", "--save", str(target), json_mode=False)
    assert code == 0, err
    secret = target.read_text().strip()
    assert secret.startswith("skm_")
    assert secret not in out
    assert oct(target.stat().st_mode & 0o777) == "0o600"
    assert str(target) in out
    again = cli.run("alice", "token", "create", "saved-again", "--save", str(target))
    assert again[0] == 0  # the token exists, the file is kept and the secret is shown instead of lost
    assert json.loads(again[1])["result"]["secret"].startswith("skm_")
    assert "cannot save" in again[2]
    assert target.read_text().strip() == secret


@pytest.mark.parametrize("command", ["create", "rotate"])
def test_an_unsafe_save_target_keeps_the_issued_secret_on_stdout(
    cli: Cli, tmp_path: Path, command: str
) -> None:
    # The token exists once the bus answered: a refused --save target must not lose its only copy.
    cli.result("alice", "token", "create", "unsafe")
    link = tmp_path / "link.token"
    link.symlink_to(tmp_path / "elsewhere")
    args = ("create", "unsafe-2") if command == "create" else ("rotate", "unsafe")
    code, out, err = cli.run("alice", "token", *args, "--save", str(link))
    assert code == 0, err
    assert json.loads(out)["result"]["secret"].startswith("skm_")
    assert "cannot save" in err
    assert not (tmp_path / "elsewhere").exists()


def test_token_rotate_and_revoke_by_name_and_by_id(cli: Cli) -> None:
    made = cli.made
    created = cli.result("alice", "token", "create", "rot")
    rotated = cli.result("alice", "token", "rotate", "rot", "--grace-minutes", "0")
    assert rotated["token_id"] != created["token_id"]
    assert rotated["previous_token_id"] == created["token_id"]
    assert made.actor(rotated["secret"]).display_name == "alice"
    with pytest.raises(Unauthenticated):
        made.actor(created["secret"])  # grace 0: the old secret is dead at once
    revoked = cli.result("alice", "token", "revoke", f"token:{rotated['token_id']}")
    assert revoked["token_id"] == rotated["token_id"]
    code, out, _ = cli.run("alice", "token", "revoke", "no-such-name")
    assert (code, json.loads(out)["error"]["code"]) == (1, "NOT_FOUND")


def test_a_token_for_another_principal_needs_token_any(cli: Cli) -> None:
    bob = cli.made.actor("bob").principal_id
    code, out, _ = cli.run("alice", "token", "create", "stolen", "--principal", str(bob))
    assert (code, json.loads(out)["error"]["code"]) == (5, "FORBIDDEN")
    assert cli.result("owner", "token", "create", "for-bob", "--principal", str(bob))["secret"]


def test_principal_create_list_show_disable(cli: Cli) -> None:
    created = cli.result("owner", "principal", "create", "robot", "--kind", "service")
    listing = cli.result("owner", "principal", "list", "--kind", "service")
    assert created["principal_id"] in {item["principal_id"] for item in listing["items"]}
    shown = cli.result("owner", "principal", "show", created["principal_id"])
    assert (shown["display_name"], shown["kind"], shown["state"]) == ("robot", "service", "active")
    disabled = cli.result(
        "owner", "principal", "disable", f"principal:{created['principal_id']}", "--reason", "gone"
    )
    assert disabled["row_version"] == shown["row_version"] + 1
    assert cli.result("owner", "principal", "show", created["principal_id"])["state"] == "disabled"


def test_a_member_cannot_manage_principals_and_the_refusal_is_exit_5_with_audit(cli: Cli) -> None:
    code, out, _ = cli.run("alice", "principal", "create", "intruder")
    error = json.loads(out)["error"]
    assert (code, error["code"], error["details"]["reason_code"]) == (5, "FORBIDDEN", "NO_MEMBERSHIP")
    assert [row.decision for row in cli.made.audits][-1] == "denied"
    assert all(
        item.display_name != "intruder"
        for item in cli.made.ask(access["queries"].ListPrincipals(), cli.made.actor("owner")).items
    )


def test_member_grant_list_revoke(cli: Cli) -> None:
    bob = str(cli.made.actor("bob").principal_id)
    granted = cli.result("alice", "member", "grant", bob, "viewer", "--scope", f"workspace:{WS}")
    assert granted["role"] == "viewer"
    listing = cli.result("alice", "member", "list", "--scope", f"workspace:{WS}")
    assert bob in {item["principal_id"] for item in listing["items"]}
    own = cli.result("alice", "member", "list", "--principal", str(cli.made.actor("alice").principal_id))
    assert {item["role"] for item in own["items"]} == {"maintainer"}
    assert cli.result("alice", "member", "revoke", bob, "--scope", f"workspace:{WS}")["removed"] is True
    code, out, _ = cli.run("alice", "member", "grant", bob, "owner", "--scope", f"workspace:{WS}")
    assert code != 0
    assert json.loads(out)["error"]["code"] == "FORBIDDEN"  # no escalation beyond the granter's own rights


def test_the_instance_owner_grants_on_the_instance_scope_found_through_its_membership(cli: Cli) -> None:
    bob = str(cli.made.actor("bob").principal_id)
    granted = cli.result("owner", "member", "grant", bob, "viewer", "--scope", "instance")
    assert granted["scope_id"] == str(INSTANCE)
    assert role_of(cli, "bob", INSTANCE) is Role.VIEWER


def role_of(cli: Cli, label: str, scope: UUID) -> Role | None:
    page = cli.made.ask(access["queries"].ListMemberships(scope_id=scope), cli.made.actor("owner"))
    found = {item.display_name: item.role for item in page.items}
    return None if label not in found else Role(found[label].value)


def test_command_modules_use_only_the_access_public_facade() -> None:
    root = Path(composition.__file__).parents[1] / "entrypoints/cli/commands"
    for name in ("token", "principal", "member", "whoami"):
        text = (root / f"{name}.py").read_text()
        imported = [line for line in text.splitlines() if line.startswith("from skm.modules.")]
        assert all(line.startswith("from skm.modules.access import public") for line in imported), name
