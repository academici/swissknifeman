"""Exercise the production HTTP worker and CLI with a PostgreSQL control plane."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import cast, override
from uuid import UUID, uuid4

import httpx
import pytest

from contracts.execution.harness import _publish_revision
from e2e.test_http_worker import _api, _Wire
from fixtures.execution.harness import (
    clean_test_database,
    pg_session,
    recovery,
    system_dispatch,
    test_database,
)
from fixtures.execution.m3 import KEYS, dag, start
from fixtures.execution.runtime import RecordedRuntime
from fixtures.execution.single_run import successful_script
from integration.git.conftest import AUTHOR, make_repo
from integration.postgres.test_machine_store import Databases, databases, migrated_databases
from skm.adapters.postgres.machine import PostgresMachineStore
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.bootstrap import worker_runtimes
from skm.bootstrap.host_services import build_host_storage
from skm.bootstrap.machine import https_origin
from skm.bootstrap.plugins import LoadedPlugin, PluginStatus
from skm.bootstrap.worker import build_http_worker
from skm.bootstrap.worker_runtimes import WorkerRuntimes
from skm.entrypoints.cli.main import main as cli
from skm.entrypoints.worker.main import main as standalone
from skm.kernel.json_types import JsonObject
from skm.modules.execution.host.context import WorkerServices
from skm.modules.execution.ports import RunRepository
from skm.modules.planning import public as planning
from skm.modules.planning.domain.specification import to_document
from skm.modules.runtimes.domain.installation import AuthState
from skm.modules.runtimes.public import RuntimeRegistry
from skm.modules.workspace.public import BindCheckout, checkout_locator
from skm.platform.config.bootstrap import BOOTSTRAP_URN, load_bootstrap
from skm.platform.config.secrets import SecretRef
from skm.platform.logging import setup
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.machine import MachineCheckout, MachineCheckoutKey, MachineProfile
from skm.plugin_api.manifest import ComponentKind
from support.http_server import loopback_certificate, loopback_server
from support.machine import machine_operator, set_machine_setting
from unit.execution.application._support import set_setting

__all__ = [
    "clean_test_database",
    "databases",
    "migrated_databases",
    "pg_session",
    "recovery",
    "test_database",
]
pytestmark = [pytest.mark.pg, pytest.mark.e2e]


def _bootstrap(side, endpoint, *, auto=False, ca_bundle: Path | None = None):
    remote = side.root / "remote"
    remote.mkdir(mode=0o700, exist_ok=True)
    path = remote / "worker.token"
    path.write_text(side.secret)
    path.chmod(0o600)
    config = remote / "bootstrap.toml"
    tls = f'ca_bundle = "{ca_bundle}"\n' if ca_bundle is not None else ""
    config.write_text(
        f'schema = "{BOOTSTRAP_URN}"\ninstance_id = "{side.app.instance_id}"\n'
        f'[access]\nmode = "http"\n[api]\nendpoint = "{endpoint}/api/v1"\n'
        f'credential = "secret://file/{path}"\n{tls}[host]\nid = "{("auto" if auto else side.host1)}"\n'
        f'[paths]\nstate_dir = "{remote / "state"}"\n'
    )
    env = {"SKM_BOOTSTRAP": str(config), "SKM_WORKSPACE": str(side.ws), "HOME": str(remote)}
    return load_bootstrap(None, env, remote), env, path


class _SlowConfig(_Wire):
    """Hold the first between-stage refresh until two real lease renewals have completed."""

    renewed_during_refresh = 0

    @override
    def wrap(self, app):
        observed = super().wrap(app)
        renewed = asyncio.Event()
        held = False
        waiting = False

        async def delay(scope, receive, send):
            nonlocal held, waiting
            path = scope.get("path", "")
            claimed = any(route.endswith("/claim") for route, _, _ in self.calls)
            if not held and claimed and path.endswith("/config"):
                held = True
                waiting = True
                try:
                    await asyncio.wait_for(renewed.wait(), timeout=20)
                finally:
                    waiting = False
            await observed(scope, receive, send)
            if waiting and not renewed.is_set() and "/assignments/" in path and path.endswith("/heartbeat"):
                self.renewed_during_refresh += 1
                if self.renewed_during_refresh == 2:
                    renewed.set()

        return delay


def test_cli_once_runs_default_stages_with_workspace_credential(
    recovery, migrated_databases: Databases, monkeypatch
):
    side = recovery
    set_setting(side, "worker.disk_min_bytes", 0)
    set_setting(side, "plugins.allowed", ["tests.recorded"])
    monkeypatch.setattr(WorkerRuntimes, "now", lambda _: side.clock.now())
    revision = dag(side)
    with side.uow(readonly=True) as uow:
        doc = to_document(planning.get_revision_specification(uow, revision))
    # This task uses a required independent review to verify its criteria.
    doc["checks"] = []
    for criterion in cast("list[JsonObject]", doc["criteria"]):
        criterion.update(verification_mode="review", checks=[])
    revision = _publish_revision(side.app, side.client, side.owner, side.clock, side.plan1, doc, "current")
    run = start(side, revision, keys=(KEYS[0],))
    repo = side.root / "repository"
    git, _ = make_repo(repo)
    (repo / "src").mkdir()
    (repo / "src/target.py").write_text("answer = 0\n")
    git.run(repo, ["add", "."])
    git.run_bytes(repo, ["commit", "-m", "baseline"], env=AUTHOR)
    branch = f"skm/integration/{run.run_id}"
    git.run(repo, ["branch", branch])
    remote = "https://example.invalid/m3.git"
    git.run(repo, ["remote", "add", "origin", remote])
    checkout_id = uuid4()
    locator = checkout_locator(checkout_id)
    side.client.dispatch(
        BindCheckout(
            side.repo_id,
            side.host1,
            locator,
            locator,
            ("example.invalid/m3",),
            git.run(repo, ["rev-parse", "HEAD"]).stdout.strip(),
            False,
            side.clock.now(),
        )
    )
    system_dispatch(side, "schedule_ready_tasks")
    script = successful_script(side, KEYS[0])

    class InstalledFake(RecordedRuntime):
        def detect(self, probe):
            info = self.inner.detect(probe)
            return replace(
                info,
                version="0.1.0",
                binary_locator="/synthetic/fake",
                auth_state=AuthState.OK,
                details={
                    "executable_sha256": "sha256:" + "a" * 64,
                    "verification_key": "sha256:" + "b" * 64,
                    "adapter_version": "0.1.0",
                },
            )

    wire = _SlowConfig(side.root / "remote" / "state")

    def load_recorded_runtime(_local, allowed, _required):
        if "tests.recorded" not in allowed:
            return ()
        runtime = InstalledFake(
            FakeRuntime(state_dir=wire.state, script=script, allow_pgroup_best_effort=True),
            wire.state,
            build_host_storage(wire.state),
        )
        return (
            LoadedPlugin(
                None,
                "recorded-runtime",
                "0.1.0",
                "unknown",
                (),
                {},
                (),
                plugin_id="tests.recorded",
                status=PluginStatus.LOADED,
                instances={(ComponentKind.RUNTIME, "fake"): runtime},
            ),
        )

    monkeypatch.setattr(worker_runtimes, "_load_host_plugins", load_recorded_runtime)
    cert, keyfile = loopback_certificate(side.root / "tls")
    with loopback_server(_api(side, wire), tls=(cert, keyfile)) as endpoint:
        _, env, token_path = _bootstrap(side, endpoint, auto=True, ca_bundle=cert)
        out, err = StringIO(), StringIO()
        args = ["worker", "start", "--once", "--worker", str(side.worker1)]
        assert cli(args, environ=env, stdout=out, stderr=err) == 1
        assert "CONFIG_INVALID" in err.getvalue()
        assert not wire.calls
        wire.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        (wire.state / "host.json").write_text(json.dumps({"host_id": str(side.host1)}))
        env = machine_operator(env, migrated_databases.machine)
        installation = UUID(env["SKM_INSTALLATION_ID"])
        store = PostgresMachineStore(migrated_databases.machine)
        profile = MachineProfile(
            installation,
            "default",
            side.app.instance_id,
            https_origin(endpoint),
            endpoint + "/api/v1",
            credential_ref=SecretRef.parse("secret://file/" + str(token_path)),
            ca_bundle=cert,
        )
        assert store.put_profile(profile)
        key = MachineCheckoutKey(installation, side.app.instance_id, side.host1, checkout_id)
        store.reserve_checkout(MachineCheckout(key, repo.resolve()))
        set_machine_setting(env, "plugins.allowed", ["tests.recorded"])
        set_machine_setting(env, "runtimes.allowed", ["fake"])
        set_machine_setting(
            env, "runtimes.models.allowed", {"fake": {"fake-a": ["high"], "fake-b": ["high"]}}
        )
        out, err = StringIO(), StringIO()
        code = cli(args, environ=env, stdout=out, stderr=err)
        assert code == 0, (out.getvalue(), err.getvalue(), wire.errors)
    assert wire.renewed_during_refresh == 2
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(run.run_id).status.value == "succeeded"
    assert git.run(repo, ["show", branch + ":src/target.py"]).stdout.strip() == "answer = 42"


def test_refreshed_runtime_options(recovery, migrated_databases: Databases, monkeypatch):
    side = recovery
    monkeypatch.setattr(WorkerRuntimes, "now", lambda _: side.clock.now())
    wire = _Wire(side.root / "remote" / "state")
    with loopback_server(_api(side, wire)) as endpoint:
        _, env, _ = _bootstrap(side, endpoint)
        env = machine_operator(env, migrated_databases.machine)
        set_setting(side, "runtimes.allowed", ["codex"])
        set_machine_setting(env, "runtimes.allowed", ["codex"])
        bootstrap = load_bootstrap(None, env, side.root / "remote")
        host, _ = build_http_worker(bootstrap, environ=env)
        try:
            registry = host.gateways.get(RuntimeRegistry)
            initial = registry.get("codex")
            set_machine_setting(env, "runtimes.codex.allow_full_access", True)
            set_machine_setting(env, "runtimes.binaries", {"codex": "/configured/codex"})
            host.gateways.get(WorkerServices).refresh_config()
            refreshed = registry.get("codex")
            assert refreshed is not initial
            assert isinstance(refreshed, CodexRuntime)
            assert isinstance(initial, CodexRuntime)
            assert refreshed.launch_config_digest != initial.launch_config_digest
            assert refreshed._allow_full_access
            assert not initial._allow_full_access
            assert refreshed._binary == "/configured/codex"
        finally:
            host.close()


def test_standalone_rotation_respects_zero_grace_and_masks_successor(recovery, monkeypatch):
    side = recovery
    # The registered token has the original 168-hour lifetime. Only the effective
    # policy (increased after registration) puts it inside the rotation window.
    set_setting(side, "access.tokens.worker_ttl_hours", 720)
    set_setting(side, "access.tokens.worker_rotate_before_hours", 300)
    set_setting(side, "access.tokens.rotation_grace_minutes", 0)
    wire = _Wire(side.root / "remote" / "state")
    redactor = Redactor(patterns=())
    monkeypatch.setattr(setup._state, "settings", replace(setup._state.settings, redactor=redactor))
    with loopback_server(_api(side, wire)) as endpoint:
        bootstrap, env, path = _bootstrap(side, endpoint)
        side.clock.advance(timedelta(seconds=1))
        request: JsonObject = {
            "workspace_id": str(side.ws),
            "worker_id": str(side.worker1),
            "once": True,
            "max_wait_seconds": 0,
            "offer": {
                "capabilities": [],
                "labels": [],
                "environment_kinds": ["git_worktree"],
                "isolation_profiles": ["worktree"],
            },
        }
        assert standalone(bootstrap=bootstrap, environ=env, request=request) == 0
        replacement = path.read_text().strip()
        assert replacement != side.secret
        assert path.stat().st_mode & 0o777 == 0o600
        for credential, expected in ((side.secret, 401), (replacement, 200)):
            assert redactor.text(credential) == MASK
            response = httpx.get(
                endpoint + "/api/v1/me",
                headers={"Authorization": f"Bearer {credential}", "SKM-Client-Version": "2.0.0"},
            )
            assert response.status_code == expected
