"""Worker composition with local binaries, installed plugins and a conflicting project snapshot."""

import json
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest

from skm.adapters.http_client.client import HttpSkmClient
from skm.adapters.runtimes._cli_session.binding import launch_verification_digest
from skm.adapters.runtimes.codex.launch import build_launch_plan
from skm.adapters.runtimes.grok.runtime import grok_account_available
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext, HostServices
from skm.bootstrap import worker, worker_entrypoint
from skm.bootstrap.runtimes import WorkerRuntimeSettings
from skm.bootstrap.worker_runtimes import local_account_available
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound, ValidationFailed
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.host.context import WorkerServices
from skm.modules.runtimes.domain.capability import VerificationContext
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.public import Effort, ProcessOwnership, RuntimeRegistry
from skm.platform.config.bootstrap import BootstrapConfig, load_bootstrap
from skm.platform.machine import MachineStore
from unit.bootstrap.test_plugins import events, install

from .test_codex_argv import _make_request as _codex_request
from .test_gemini_cli import _MODEL, _request
from .test_gemini_cli import native_process_ownership as native_process_ownership
from .test_grok_argv import FIXTURES_DIR, _make_request

_HUB_TOKEN = "synthetic-hub-worker-token"
_PROVIDER_KEY = "synthetic-local-provider-key"
_PROJECT_DSN = "postgresql://test:project-password@project.invalid/project"
_MACHINE_DSN = "postgresql://test:machine-password@machine.invalid/machine"
_UNRELATED_KEY = "synthetic-other-provider-key"
_SECRET_VERSION = "0.83.9876"
_DIGEST = "sha256:" + "0" * 64
_NOW = "2025-11-02T14:00:00Z"


class _OperatorSettings:
    def __init__(self, values: JsonObject) -> None:
        self.installation = uuid4()
        self.values = values

    def get_installation_id(self) -> UUID:
        return self.installation

    def get_operator_setting(self, installation_id: UUID, key: str) -> JsonValue:
        assert installation_id == self.installation
        return self.values.get(key)


def _worker_identity(workspace: str, host: UUID) -> JsonObject:
    principal = str(uuid4())
    unrelated_workspace = str(uuid4())
    return {
        "principal": {
            "principal_id": principal,
            "kind": "worker",
            "display_name": "Test worker",
            "state": "active",
            "created_at": _NOW,
            "row_version": 1,
            "identities": [],
        },
        "token": {
            "token_id": str(uuid4()),
            "kind": "worker",
            "name": "Test worker",
            "prefix": "worker",
            "scope_id": None,
            "permissions": None,
            "scope_grants": [
                {"scope_id": str(host), "permissions": ["worker.claim", "runtime.manage"]},
                {"scope_id": workspace, "permissions": ["worker.claim", "token.own"]},
            ],
            "state": "active",
            "expires_at": "2099-11-02T14:00:00Z",
            "last_used_at": None,
            "created_at": _NOW,
            "superseded_by": None,
            "assignment_id": None,
            "step_id": None,
        },
        "memberships": [
            {
                "scope_id": unrelated_workspace,
                "scope_kind": "workspace",
                "principal_id": principal,
                "display_name": "Worker",
                "role": "worker",
                "granted_at": _NOW,
            },
            {
                "scope_id": workspace,
                "scope_kind": "workspace",
                "principal_id": principal,
                "display_name": "Worker",
                "role": "worker",
                "granted_at": _NOW,
            },
        ],
        "effective_permissions": ["worker.claim"],
        "modules": {},
        "permissions_by_scope": {},
        "events_cursor": None,
    }


def _rotation_report(workspace: str) -> JsonObject:
    return {
        "schema": "urn:skm:config:explain:v1",
        "scope": {"level": "workspace", "scope_id": workspace},
        "chain": [],
        "generation": 1,
        "digest": _DIGEST,
        "keys": [
            {
                "key": f"access.tokens.{key}",
                "present": True,
                "merge": "replace",
                "reload": "live",
                "sensitivity": "public",
                "contributions": [],
                "value": value,
            }
            for key, value in (("worker_rotate_before_hours", 1), ("worker_ttl_hours", 24))
        ],
    }


class _Hub:
    def __init__(self, host: UUID, binary: Path) -> None:
        self.host = host
        self.workspace = str(uuid4())
        self.identity = _worker_identity(self.workspace, host)
        self.binary = binary
        self.allowed = ["gemini_cli", "fixture_rt", "grok"]
        self.grok_account_home = binary.parent
        self.observations: list[JsonObject] = []
        self.requests: list[httpx.Request] = []

    def receive(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["Authorization"] == f"Bearer {_HUB_TOKEN}"
        path = request.url.path
        if path == "/api/v1/me":
            assert request.url.params.get("scope_id") in (None, self.workspace)
            result = self.identity
        elif path == "/api/v1/config/effective":
            result = _rotation_report(self.workspace)
        elif path == "/api/v1/runtimes/models":
            assert request.url.params["host_id"] == str(self.host)
            result = {
                "catalog_version": "1.0.0",
                "catalog_digest": _DIGEST,
                "stale": False,
                "models": [
                    {"runtime_id": "gemini_cli", "id": _MODEL, "efforts": [], "status": "confirmed"},
                    {
                        "runtime_id": "gemini_cli",
                        "id": "unapproved-model",
                        "efforts": [],
                        "status": "confirmed",
                    },
                    {"runtime_id": "grok", "id": "grok-4.7", "efforts": ["high"], "status": "confirmed"},
                    {
                        "runtime_id": "codex",
                        "id": "gpt-5.3-codex",
                        "efforts": ["high"],
                        "status": "confirmed",
                    },
                ],
            }
        elif path == f"/api/v1/worker/hosts/{self.host}/config":
            result = {
                "host_id": str(self.host),
                "generation": 1,
                "pack_generation": 1,
                "digest": _DIGEST,
                "values": {
                    "worker.capacity": 3,
                    "worker.disk_min_bytes": 0,
                    "runtimes.allowed": self.allowed,
                    "runtimes.binaries": {"gemini_cli": str(self.binary), "grok": str(self.binary)},
                    "runtimes.grok.account_home": str(self.grok_account_home),
                    "runtimes.extra_env_allow": {"gemini_cli": ["SKM_MACHINE_DATABASE_URL"]},
                    "runtimes.accounts": {"gemini_cli": {"GEMINI_API_KEY": self.binary.as_posix()}},
                    "plugins.acme.fixture.secret": "secret://env/HUB_PLUGIN_SECRET",
                },
                "invalid": ["runtimes.credentials.copy"],
                "plugins": {"allowed": ["acme.hub", "acme.fixture"], "required": []},
            }
        else:
            assert path == f"/api/v1/hosts/{self.host}/runtimes"
            payload = cast("JsonObject", json.loads(request.content))
            self.observations.append(payload)
            result = {"host_id": str(self.host), "runtimes": [], "removed": []}
        return httpx.Response(
            200, json=result, headers={"SKM-Instance-Id": request.headers["SKM-Instance-Id"]}
        )


def _binary(root: Path, *, name: str, version: str, final: str) -> Path:
    path = root / name
    path.write_text(
        f"""#!{sys.executable}
import json
import os
import sys

assert all(name not in os.environ for name in (
    'SKM_DATABASE_URL', 'SKM_MACHINE_DATABASE_URL', 'SKM_API_TOKEN', 'SKM_TOKEN',
    'ANTHROPIC_API_KEY', 'LOCAL_PROVIDER_SECRET', 'UNRELATED_TOKEN', 'LC_DIAGNOSTIC',
))
if sys.argv[1:] == ['--version']:
    assert 'GEMINI_API_KEY' not in os.environ
    print({version!r})
elif sys.argv[1:] == ['--help']:
    print('--model --output-format (text, json, stream-json) --approval-mode --prompt')
else:
    assert os.environ['GEMINI_API_KEY'] == {_PROVIDER_KEY!r}
    sys.stdin.read()
    print(json.dumps({{'type': 'init', 'session_id': 'worker-fixture', 'model': {_MODEL!r}}}))
    print(json.dumps({{'type': 'message', 'role': 'assistant', 'content': {final!r}, 'delta': True}}))
    stats = {{'input_tokens': 1, 'output_tokens': 1}}
    print(json.dumps({{'type': 'result', 'status': 'success', 'stats': stats}}))
    print(os.environ['GEMINI_API_KEY'], file=sys.stderr)
""",
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


def _install_plugins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    site = tmp_path / "site"
    site.mkdir()
    monkeypatch.syspath_prepend(str(site))
    for name, package in (
        ("acme.fixture", "skm_plugin_worker_local"),
        ("acme.hub", "skm_plugin_worker_hub"),
        ("acme.excluded", "skm_plugin_worker_excluded"),
    ):
        install(site, package=package, plugin_id=name, rename={">=2.0.0.dev0,<3": ">=0.1.0.dev0,<3"})


def _environment() -> Mapping[str, str]:
    return {
        "PATH": os.defpath,
        "SKM_DATABASE_URL": _PROJECT_DSN,
        "SKM_MACHINE_DATABASE_URL": _MACHINE_DSN,
        "SKM_API_TOKEN": _HUB_TOKEN,
        "UNRELATED_TOKEN": _UNRELATED_KEY,
        "ANTHROPIC_API_KEY": _UNRELATED_KEY,
        "GEMINI_API_KEY": _UNRELATED_KEY,
        "LOCAL_PROVIDER_SECRET": _PROVIDER_KEY,
        "LC_DIAGNOSTIC": _HUB_TOKEN,
        "SYNTHETIC_VERSION_TOKEN": _SECRET_VERSION,
    }


def _worker_for_hub(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hub: _Hub,
    operator: _OperatorSettings,
    environ: Mapping[str, str],
    revealed: list[str],
) -> tuple[HostServices, SkmClient, BootstrapConfig]:
    connection = httpx.Client(transport=httpx.MockTransport(hub.receive))

    def with_transport(*args: Any, **kwargs: Any) -> HttpSkmClient:
        return HttpSkmClient(*args, http=connection, **kwargs)

    monkeypatch.setattr(worker, "HttpSkmClient", with_transport)
    bootstrap = replace(
        load_bootstrap(
            None,
            environ={
                "SKM_API_ENDPOINT": "https://hub.invalid/api/v1",
                "SKM_API_TOKEN": _HUB_TOKEN,
                "SKM_INSTANCE_ID": str(uuid4()),
            },
            home=tmp_path,
        ),
        host_id=hub.host,
        installation_id=operator.installation,
    )
    host, client = worker.build_http_worker(
        bootstrap,
        environ=environ,
        machine_store=cast("MachineStore", operator),
        on_secret=revealed.append,
    )
    return host, client, bootstrap


def _repeat_probe(monkeypatch: pytest.MonkeyPatch, host: HostServices, client: SkmClient) -> None:
    def probe_slot(contexts: Sequence[HostContext], _request: JsonObject) -> JsonObject:
        contexts[0].gateways.get(WorkerServices).refresh_offers()
        return {"slots": [{"assignments": 0}]}

    monkeypatch.setattr(worker_entrypoint, "run_worker_contexts", probe_slot)
    assert worker_entrypoint.main(host=host, client=client, request={"once": True}, capacity=1) == 0


@pytest.mark.usefixtures("native_process_ownership")
def test_http_worker_uses_machine_runtime_and_local_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = _binary(tmp_path, name="machine-gemini", version="0.68.0", final="local executable")
    wrong = _binary(tmp_path, name="hub-gemini", version="0.99.0", final="hub executable")
    _install_plugins(tmp_path, monkeypatch)
    host_id = uuid4()
    hub = _Hub(host_id, wrong)
    operator = _OperatorSettings(
        {
            "runtimes.allowed": ["gemini_cli", "fixture_rt", "codex"],
            "runtimes.binaries": {"gemini_cli": str(good)},
            "plugins.allowed": ["acme.excluded", "acme.fixture"],
            "runtimes.accounts": {"gemini_cli": {"GEMINI_API_KEY": "secret://env/LOCAL_PROVIDER_SECRET"}},
            "runtimes.models.allowed": {"gemini_cli": {_MODEL: ["high"]}},
        }
    )
    machine_store = cast("MachineStore", operator)
    revealed: list[str] = []
    host, client, bootstrap = _worker_for_hub(tmp_path, monkeypatch, hub, operator, _environment(), revealed)
    with closing(host):
        assert cast("Mapping[str, object]", host.host_config()).get("worker.capacity") == 3
        registry = host.gateways.get(RuntimeRegistry)
        assert registry.ids() == {"fixture_rt", "gemini_cli"}
        assert events("skm_plugin_worker_local") == [
            "import:acme.fixture",
            "factory:runtime",
            "factory:isolation",
        ]
        assert not events("skm_plugin_worker_hub")
        assert not events("skm_plugin_worker_excluded")
        settings = WorkerRuntimeSettings.read(machine_store)
        assert settings.allows_model("gemini_cli", _MODEL, Effort.HIGH)
        assert not settings.allows_model("gemini_cli", _MODEL, Effort.LOW)
        before_launch = revealed.count(_PROVIDER_KEY)

        request = _request(tmp_path)
        (Path(request.workdir) / ".git").touch()
        request = replace(request, env_allowlist=tuple(_environment()))
        runtime = registry.get("gemini_cli")
        handle = runtime.start(request)
        list(runtime.events(handle))
        assert runtime.result(handle).final_text == "local executable"
        transcript = bootstrap.state_dir / "steps" / request.request_id / "stream.jsonl"
        assert _PROVIDER_KEY not in transcript.read_text(encoding="utf-8")

        _binary(tmp_path, name=good.name, version=_SECRET_VERSION, final="local executable")
        _repeat_probe(monkeypatch, host, client)

    assert revealed.count(_PROVIDER_KEY) == before_launch + 1
    assert len(hub.observations) == 2
    wire = json.dumps(hub.observations)
    assert "0.68.0" in json.dumps(hub.observations[0])
    assert "0.68.0" not in json.dumps(hub.observations[1])
    assert "gemini_cli" in json.dumps(hub.observations[1])
    for private in (
        str(good),
        str(wrong),
        _HUB_TOKEN,
        _PROVIDER_KEY,
        _PROJECT_DSN,
        _MACHINE_DSN,
        _UNRELATED_KEY,
        _SECRET_VERSION,
    ):
        assert private not in wire
        assert all(private not in str(req.url) for req in hub.requests)
    assert "NotImplementedError" not in wire
    assert "binary_sha256" in wire
    assert hub.observations[0]["model_offers"] == []
    assert hub.observations[1]["model_offers"] == []
    assert "unapproved-model" not in wire


def test_worker_model_policy_denies_missing_empty_and_revoked_grants() -> None:
    operator = _OperatorSettings({"runtimes.allowed": ["gemini_cli"]})
    store = cast("MachineStore", operator)
    assert not WorkerRuntimeSettings.read(store).allows_model("gemini_cli", _MODEL, Effort.HIGH)
    operator.values["runtimes.models.allowed"] = {}
    assert not WorkerRuntimeSettings.read(store).allows_model("gemini_cli", _MODEL, Effort.HIGH)
    operator.values["runtimes.models.allowed"] = {"gemini_cli": {_MODEL: ["high"]}}
    assert WorkerRuntimeSettings.read(store).allows_model("gemini_cli", _MODEL, Effort.HIGH)
    assert not WorkerRuntimeSettings.read(store).allows_model("gemini_cli", _MODEL, None)
    operator.values["runtimes.models.allowed"] = {"gemini_cli": {_MODEL: []}}
    assert not WorkerRuntimeSettings.read(store).allows_model("gemini_cli", _MODEL, Effort.HIGH)


def _grok_home(root: Path, name: str) -> Path:
    home = root / name
    home.mkdir(mode=0o700)
    state = home / ".grok"
    state.mkdir(mode=0o700)
    credential = state / "auth.json"
    credential.write_text(
        json.dumps(
            {
                "xai::api_key": {
                    "key": name,
                    "auth_mode": "api_key",
                    "user_id": "synthetic-account",
                    "create_time": "2026-01-01T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    credential.chmod(0o600)
    return home


def _grok_binary(root: Path, selected: Path, ambient: Path) -> Path:
    path = root / "machine-grok"
    stream = (FIXTURES_DIR / "streaming-messages-json.jsonl").read_text(encoding="utf-8")
    path.write_text(
        f"""#!{sys.executable}
import json
import os
from pathlib import Path
import sys

home = Path(os.environ["HOME"])
assert home == Path({str(selected)!r})
assert all({str(ambient)!r} not in value for value in os.environ.values())
assert all(name not in os.environ for name in (
    'SKM_DATABASE_URL', 'SKM_MACHINE_DATABASE_URL', 'SKM_API_TOKEN', 'SKM_TOKEN',
    'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'LOCAL_PROVIDER_SECRET', 'UNRELATED_TOKEN',
))
if sys.argv[1:] == ["--version"]:
    print("grok 0.1.0")
elif sys.argv[1:] == ["--help"]:
    print("--cwd --prompt-file --model --effort --permission-mode --output-format")
else:
    sys.stdin.read()
    account = json.loads((home / ".grok" / "auth.json").read_text())
    assert account["xai::api_key"]["key"] == "selected-account"
    sys.stdout.write({stream!r})
""",
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


@pytest.mark.usefixtures("native_process_ownership")
def test_worker_grok_uses_machine_account_home_and_revokes_invalid_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chosen = _grok_home(tmp_path, "selected-account")
    ambient = _grok_home(tmp_path, "ambient-account")
    binary = _grok_binary(tmp_path, chosen, ambient)
    hub = _Hub(uuid4(), tmp_path / "hub-grok")
    hub.grok_account_home = ambient
    operator = _OperatorSettings(
        {
            "runtimes.binaries": {"grok": str(binary)},
            "runtimes.models.allowed": {"grok": {"grok-4.7": ["high", "medium"]}},
        }
    )
    environ = {**_environment(), "HOME": str(ambient)}
    host, client, _bootstrap = _worker_for_hub(tmp_path, monkeypatch, hub, operator, environ, [])
    with closing(host):
        registry = host.gateways.get(RuntimeRegistry)
        services = host.gateways.get(WorkerServices)
        assert registry.ids() == set()
        with pytest.raises(NotFound):
            registry.get("grok")
        with pytest.raises(ValidationFailed):
            WorkerRuntimeSettings.validate_setting("runtimes.grok.account_home", "./relative")

        operator.values["runtimes.grok.account_home"] = str(chosen)
        services.refresh_config()
        runtime = registry.get("grok")
        _repeat_probe(monkeypatch, host, client)
        assert hub.observations[0]["installations"] == []
        assert '"version": "0.1.0"' in json.dumps(hub.observations[1])
        offers = cast("list[JsonObject]", hub.observations[1]["model_offers"])
        assert [item["effort"] for item in offers] == ["high"]
        request = _make_request(tmp_path, secret_token=None)
        request = replace(request, env_allowlist=tuple(environ))
        handle = runtime.start(request)
        list(runtime.events(handle))
        assert runtime.result(handle).final_text == "checked"

        state = chosen / ".grok"
        (state / "auth.json").unlink()
        unrelated = state / "config.toml"
        unrelated.write_text("# local preferences", encoding="utf-8")
        unrelated.chmod(0o600)
        _repeat_probe(monkeypatch, host, client)
        assert hub.observations[-1]["model_offers"] == []
        assert registry.ids() == set()
        with pytest.raises(CapabilityUnavailable, match="Local Grok account is unavailable"):
            runtime.start(_make_request(tmp_path, secret_token=None))

    wire = "".join(request.content.decode() for request in hub.requests)
    for private in (
        str(binary),
        str(ambient),
        str(chosen),
        _HUB_TOKEN,
        _PROJECT_DSN,
        _MACHINE_DSN,
        _UNRELATED_KEY,
    ):
        assert private not in wire


def test_explicit_codex_login_failure_cannot_be_rescued_by_a_stale_wallet(tmp_path: Path) -> None:
    state = tmp_path / ".codex"
    state.mkdir(mode=0o700)
    wallet = state / "auth.json"
    wallet.write_text('{"synthetic": "old-wallet"}', encoding="utf-8")
    wallet.chmod(0o600)
    local = WorkerRuntimeSettings.read(
        cast("MachineStore", _OperatorSettings({"runtimes.credentials.copy": {"codex": True}}))
    )
    instance = RuntimeInstallation(
        HostId(uuid4()), "codex", "0.1.0", None, AuthState.OK, datetime.fromisoformat(_NOW), {}
    )
    environ = {"HOME": str(tmp_path)}
    assert local_account_available(local, instance, environ)
    assert not local_account_available(local, replace(instance, auth_state=AuthState.UNKNOWN), environ)
    assert not local_account_available(local, replace(instance, auth_state=AuthState.MISSING), environ)
    assert not local_account_available(local, replace(instance, auth_state=AuthState.EXPIRED), environ)

    explicit = WorkerRuntimeSettings.read(
        cast(
            "MachineStore",
            _OperatorSettings(
                {"runtimes.accounts": {"codex": {"OPENAI_API_KEY": "secret://env/OPERATOR_KEY"}}}
            ),
        )
    )
    missing = replace(instance, auth_state=AuthState.MISSING)
    assert not local_account_available(explicit, missing, environ)
    assert local_account_available(explicit, missing, {**environ, "OPERATOR_KEY": _PROVIDER_KEY})


def test_grok_checks_the_selected_native_issuer_and_client(tmp_path: Path) -> None:
    home = _grok_home(tmp_path, "tenant-wallet")
    native = home / ".grok"
    auth = native / "auth.json"
    credential = {
        "key": "synthetic-session",
        "auth_mode": "oidc",
        "user_id": "synthetic-user",
        "create_time": "2026-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
    }
    auth.write_text(json.dumps({"https://old.example.invalid::retired-client": credential}))
    assert not grok_account_available(home)
    config = native / "config.toml"
    config.write_text(
        '[auth.oidc]\nissuer = "https://login.example.invalid/"\nclient_id = "active-client"\n',
        encoding="utf-8",
    )
    config.chmod(0o600)
    assert not grok_account_available(home)
    auth.write_text(
        json.dumps(
            {
                "https://old.example.invalid::retired-client": credential,
                "https://login.example.invalid::active-client": credential,
            }
        )
    )
    assert grok_account_available(home)
    auth.write_text(
        json.dumps(
            {
                "https://login.example.invalid::active-client": {
                    **credential,
                    "expires_at": "2026-01-02T00:00:00Z",
                },
            }
        )
    )
    assert not grok_account_available(home)


@pytest.mark.usefixtures("native_process_ownership")
def test_codex_logout_with_unchanged_binary_and_wallet_revokes_offer_and_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "native-home"
    account = home / ".codex"
    account.mkdir(mode=0o700, parents=True)
    wallet = account / "auth.json"
    wallet.write_text('{"synthetic": "native-wallet"}', encoding="utf-8")
    wallet.chmod(0o600)
    login = account / "login-on"
    login.touch()
    started = tmp_path / "ran-agent"
    invoked = tmp_path / "cli-invocations"
    binary = tmp_path / "selected-codex"
    binary.write_text(
        f"""#!{sys.executable}
import os
from pathlib import Path
import sys
assert not set(os.environ).intersection(('SKM_TOKEN', 'SKM_API_TOKEN', 'SKM_DATABASE_URL', 'UNRELATED_TOKEN'))
args = sys.argv[1:]
with Path({str(invoked)!r}).open("a") as log:
    log.write("run\\n")
if args == ['--version']:
    print('codex-cli 0.165.0')
elif '--help' in args:
    print('--json --sandbox --model -c --ephemeral resume -a --cd')
elif args == ['login', 'status']:
    selected_wallet = Path(os.environ['CODEX_HOME']) / "auth.json"
    assert selected_wallet.read_bytes() == Path({str(wallet)!r}).read_bytes()
    if Path({str(login)!r}).exists():
        print('Logged in using ChatGPT')
    else:
        print('Not logged in')
        raise SystemExit(1)
else:
    Path({str(started)!r}).touch()
""",
        encoding="utf-8",
    )
    binary.chmod(0o700)
    hub = _Hub(uuid4(), binary)
    hub.allowed = ["codex"]
    operator = _OperatorSettings(
        {
            "runtimes.allowed": ["codex"],
            "runtimes.binaries": {"codex": str(binary)},
            "runtimes.credentials.copy": {"codex": True},
            "runtimes.models.allowed": {"codex": {"gpt-5.3-codex": ["high"]}},
        }
    )
    host, client, _ = _worker_for_hub(
        tmp_path, monkeypatch, hub, operator, {**_environment(), "HOME": str(home)}, []
    )
    with closing(host):
        registry = host.gateways.get(RuntimeRegistry)
        runtime = registry.get("codex")
        assert hub.observations[0]["model_offers"]
        probe = DetectProbe(HostId(hub.host), str(binary), (), 5)
        installation = runtime.detect(probe)
        assert installation.auth_state is AuthState.OK
        request = _codex_request(tmp_path / "execution")
        plan = build_launch_plan(
            request,
            binary_path=str(binary),
            step_dir=tmp_path / "canary-step",
            ownership=ProcessOwnership(request.process_owner, "pgroup_best_effort", "canary"),
            host_environ={"PATH": os.defpath, "HOME": str(home)},
            user_home=home,
        )
        os_name, kernel = installation.details["os_kernel"].split(":", 1)
        context = VerificationContext(
            host_id=HostId(hub.host),
            binary_sha256=installation.details["binary_sha256"],
            os=os_name,
            kernel=kernel,
            adapter_version=installation.details["adapter_version"],
            isolation_profile=request.isolation_profile,
            launch_config_digest=launch_verification_digest(plan.command.as_wrapped(), str(binary)),
        )
        bound = replace(
            request,
            process_owner=replace(request.process_owner, host_id=hub.host),
            verification_context=context,
            expected_runtime_version=installation.version,
        )
        service = host.gateways.get(WorkerServices)
        observed_calls = invoked.read_bytes()
        service.verify_runtime(bound, context.binary_sha256)
        assert invoked.read_bytes() == observed_calls
        original_binary = binary.read_bytes()
        binary.write_bytes(original_binary + b"\n# replaced fixture bytes\n")
        with pytest.raises(CapabilityUnavailable) as changed:
            service.verify_runtime(bound, context.binary_sha256)
        assert changed.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
        assert invoked.read_bytes() == observed_calls
        binary.write_bytes(original_binary)
        # The accepted detection and cached executable identity predate logout.
        login.unlink()
        with pytest.raises(CapabilityUnavailable) as denied:
            runtime.start(bound)
        assert denied.value.code is ErrorCode.RUNTIME_AUTH_EXPIRED
        assert wallet.is_file()
        assert not started.exists()
        assert not list(tmp_path.rglob(".pinned-bin"))
        assert registry.get("codex") is runtime
        _repeat_probe(monkeypatch, host, client)
        assert hub.observations[1]["model_offers"] == []
        fresh = runtime.detect(probe)
        assert fresh.auth_state is AuthState.MISSING
        assert fresh.details["binary_sha256"] == installation.details["binary_sha256"]
        assert str(account) not in json.dumps(hub.observations)
        assert "native-wallet" not in json.dumps(hub.observations)
