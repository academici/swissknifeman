"""The worker runs local stages over the real API with PostgreSQL confined to the control plane."""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from contracts.execution.harness import PEPPER
from fixtures.execution.harness import (
    RecoverySide,
    clean_test_database,
    pg_session,
    recovery,
    test_database,
)
from fixtures.execution.processes import scenario, script
from fixtures.execution.single_run import single_run, successful_script
from skm.bootstrap.composition_resources import token_authenticator
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.blobs import mount_blobs
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import RevokeToken
from skm.modules.artifacts.application.upload import bind_embedded_upload
from skm.modules.execution.ports import RunRepository, StageRepository
from skm.modules.workspace.public import CreateWorkspace, CreateWorkspaceResult
from skm.platform.config.bootstrap import BOOTSTRAP_URN
from skm.platform.process.identity import identity_of
from skm.platform.system_clock import SystemClock
from support.http_server import loopback_server
from unit.execution.application._support import set_setting

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = [pytest.mark.pg, pytest.mark.e2e]


def _worker_subprocess(input_path: str) -> int:  # noqa: PLR0915 - bind the existing local stage adapters
    import json
    import os
    from dataclasses import replace
    from pathlib import Path
    from types import SimpleNamespace
    from typing import cast
    from uuid import UUID, uuid4

    from fixtures.execution.runtime import RecordedRuntime
    from skm.adapters.checks.registry import build_check_registry
    from skm.adapters.git.environments.worktree import git_worktree_environments
    from skm.adapters.git.integration import git_integration_vcs
    from skm.adapters.git.runner import GitRunner
    from skm.adapters.runtimes.fake.runtime import FakeRuntime
    from skm.adapters.sandbox.registry import build_isolation_registry
    from skm.application_bus.host import HostServices
    from skm.bootstrap.host_services import (
        build_context_inputs,
        build_host_storage,
        build_worker_services,
        read_runtime_transcript,
        worker_concurrency,
        worker_schema_issues,
    )
    from skm.bootstrap.worker_stages import seal_worker_snapshot
    from skm.entrypoints.worker.main import main
    from skm.kernel.errors import SkmError
    from skm.kernel.gateways import GatewayTable
    from skm.kernel.ids import AttemptId, HostId, RepositoryId
    from skm.kernel.ports_uow import Surface
    from skm.modules.execution.domain.environment import EnvironmentKind, attempt_branch
    from skm.modules.execution.host.environment import EnvironmentMount, EnvironmentSpec
    from skm.modules.execution.host.isolation import IsolationSpec
    from skm.modules.execution.host.stages.agent_review import AgentReviewStage
    from skm.modules.execution.host.stages.agent_step import AgentStepStage
    from skm.modules.execution.host.stages.integrate import IntegrateStage
    from skm.modules.execution.host.stages.prepare_environment import PrepareEnvironmentStage
    from skm.modules.execution.host.stages.registry import StageRegistry
    from skm.modules.execution.host.stages.run_checks import RunChecksStage
    from skm.modules.execution.ports import (
        CheckRunnerRegistry,
        ExecutionEnvironmentManager,
        IsolationRegistry,
        Vcs,
    )
    from skm.modules.runtimes.domain.installation import AuthState
    from skm.modules.runtimes.public import AgentRuntime, ProcessOwner, RuntimeRegistry
    from skm.platform.config.bootstrap import load_bootstrap
    from skm.platform.machine import MachineStore
    from skm.platform.system_clock import SystemClock, SystemMonotonic
    from support.fault_injection import StageDiagnostics
    from support.runtime_bootstrap import TestRuntimeRegistry

    data = json.loads(Path(input_path).read_text())
    state = Path(data["state"])
    boot = load_bootstrap(None, os.environ, Path.home())
    assert boot.database_url is None
    assert "SKM_DATABASE_URL" not in os.environ

    def emit(result):
        print(json.dumps(result), flush=True)

    class FixtureMachineStore:
        def get_installation_id(self):
            return UUID(data["request"]["host_id"])

        def get_operator_setting(self, installation_id, key):
            assert installation_id == self.get_installation_id()
            return {
                "runtimes.allowed": ["fake"],
                "runtimes.models.allowed": {"fake": {"fake-a": ["high"], "fake-b": ["high"]}},
            }.get(key)

    def run(host=None):
        try:
            return main(
                bootstrap=boot,
                host=host,
                request=data["request"],
                on_result=emit,
                machine_store=cast("MachineStore", FixtureMachineStore()),
            )
        except SkmError as error:
            print(error.message, file=sys.stderr)
            emit({"code": error.code.value, "details": dict(error.details)})
            return 6

    if data.get("script") is None:
        return run()
    repository = Path(data["repository"])
    repository_id = RepositoryId(UUID(data["repository_id"]))
    host_id = HostId(UUID(data["request"]["host_id"]))
    worker_id = UUID(data["request"]["worker_id"])
    git, storage = GitRunner(), build_host_storage(state)
    manager = git_worktree_environments(git, worktrees_root=boot.worktrees_root)
    isolation = build_isolation_registry(allow_unconfined=True)
    target_branch = "skm/integration/" + data["run_id"]

    class SyntheticRuntime(RecordedRuntime):
        def detect(self, probe):
            info = self.inner.detect(probe)
            return replace(
                info,
                version="0.1.0",
                binary_locator="/synthetic/fake",
                auth_state=AuthState.OK,
                details={
                    **info.details,
                    "executable_sha256": "sha256:" + "a" * 64,
                    "verification_key": "sha256:" + "b" * 64,
                    "adapter_version": "0.1.0",
                },
            )

    runtime = SyntheticRuntime(
        FakeRuntime(state_dir=state, script=Path(data["script"]), allow_pgroup_best_effort=True),
        state,
        storage,
    )

    def environment(request, _deps):
        attempt = AttemptId(UUID(request.task["attempt_id"]))
        return EnvironmentSpec(
            attempt,
            EnvironmentKind.GIT_WORKTREE,
            (EnvironmentMount("repo", repository_id, str(repository), target_branch),),
            attempt_branch(attempt),
            boot.worktrees_root,
            None,
            None,
        )

    def output(request, deps):
        return seal_worker_snapshot(git, state, manager, request, deps)

    def owner(request, kind, unit_id):
        return ProcessOwner(
            host_id,
            worker_id,
            UUID(request.task["attempt_id"]),
            UUID(request.begin["stage_record_id"]),
            kind,
            UUID(str(unit_id)),
            uuid4().hex,
            str(state / "identities"),
        )

    def check_isolation(raw, cwd, request, _deps):
        unit = owner(request, "check", raw["check_execution_id"])
        return IsolationSpec(cwd, (cwd,), (cwd,), (), False, "full", (), {}, None, (), unit)

    def ownership(effect, request, _deps):
        unit = owner(request, "git_effect", effect)
        return {
            "kind": "pgroup_best_effort",
            "ref": f"pgroup:{effect}",
            "owner": {
                "host_id": str(unit.host_id),
                "worker_id": str(unit.worker_id),
                "attempt_id": str(unit.attempt_id),
                "stage_record_id": str(unit.stage_record_id),
                "unit_kind": unit.unit_kind,
                "unit_id": str(unit.unit_id),
                "owner_nonce": unit.owner_nonce,
                "identity_dir": unit.identity_dir,
            },
        }

    def checks_runner():
        runners = build_check_registry(
            storage=storage,
            capture_floor_bytes=0,
            state_dir=state,
            isolation_registry=isolation,
            profile="none",
            host=host_id,
            sanitized_env={"PATH": os.defpath},
            allow_pgroup_best_effort=True,
        )
        return runners

    def verify_environment(env):
        manager.reopen(env.environment_id, env.locator)

    kwargs = {
        "concurrency": worker_concurrency(),
        "validate_result": worker_schema_issues,
        "read_transcript": read_runtime_transcript,
    }
    stages = (
        PrepareEnvironmentStage(manager, spec=environment, patch_files=lambda _: ()),
        AgentStepStage(**kwargs, seal_snapshot=output),
        AgentReviewStage(**kwargs),
        RunChecksStage(
            isolation=check_isolation,
            read_capture=Path.read_bytes,
            verify_environment=verify_environment,
            candidate_marks=lambda request, _deps: {
                "repo": {
                    p["path_bytes"]: p["fingerprint"]
                    for p in json.loads(
                        (state / "sealed-outputs" / f"{request.task['attempt_id']}.json").read_bytes()
                    )["manifest"]["changed_paths"]
                }
            },
            environment_manager=manager,
            current_tips=lambda *_: {
                "repo": git.run(repository, ["rev-parse", target_branch]).stdout.strip()
            },
        ),
        IntegrateStage(ownership=ownership),
    )
    services = build_worker_services(
        state,
        stages=StageRegistry(StageDiagnostics(stage) for stage in stages),
        context_inputs=build_context_inputs(),
        resolve=lambda _: None,
        storage=storage,
    )
    gateways = GatewayTable(
        {
            type(services): services,
            RuntimeRegistry: TestRuntimeRegistry(cast("AgentRuntime", runtime)),
            ExecutionEnvironmentManager: manager,
            IsolationRegistry: isolation,
            CheckRunnerRegistry: checks_runner(),
            Vcs: git_integration_vcs(
                git,
                worktrees_root=state / "integration",
                now=SystemClock().now,
                monotonic=SystemMonotonic().monotonic,
                repositories={str(repository_id): repository},
            ),
        },
        "host_gateway",
    )
    return run(HostServices(host_id, Surface.WORKER, gateways, SimpleNamespace, {}))


_ISOLATION = """
import sys

_FORBIDDEN = ("psycopg", "starlette", "uvicorn", "skm.entrypoints.api.app", "skm.application_bus.bus")

class BlockControlPlane:
    def find_spec(self, fullname, *args):
        if fullname.startswith(_FORBIDDEN):
            raise AssertionError(f"Control plane import in worker: {fullname}")

sys.meta_path.insert(0, BlockControlPlane())
"""


@dataclass
class _Wire:
    state: Path
    loss: str = ""
    calls: list[tuple[str, str | None, bytes]] = field(default_factory=list)
    replayed: list[str] = field(default_factory=list)
    uploaded_at: dict[str, int] = field(default_factory=dict)
    errors: list[tuple[str, int, bytes]] = field(default_factory=list)
    renewals_failed: int = 0

    def wrap(self, app: ASGIApp) -> ASGIApp:
        async def observe(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await app(scope, receive, send)
                return
            request = Request(scope, receive)
            path, key = request.url.path, request.headers.get("idempotency-key")
            body = await request.body()
            first = not any(previous == path for previous, _, _ in self.calls)
            logged_body = b"" if path.endswith("/stages") else body
            self.calls.append((path, key, logged_body))
            if path.endswith("/heartbeat") and "/assignments/" in path and self._fail_renewal():
                error = ErrorCode.LEASE_LOST if self.loss == "lease" else ErrorCode.BACKEND_UNAVAILABLE
                status = 409 if self.loss == "lease" else 503
                await JSONResponse(
                    {"code": error.value},
                    status_code=status,
                    headers={"SKM-Instance-Id": request.headers["SKM-Instance-Id"]},
                    media_type="application/problem+json",
                )(scope, receive, send)
                return
            drop = (
                first
                and self.loss == "responses"
                and (path.endswith("/finalize") or (path.endswith("/result") and b'"evidence":[{' in body))
                and not any(p.endswith("/result") for p in self.replayed if path.endswith("/result"))
            )

            status = 0

            async def relay(message: Message) -> None:
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                    assert not drop or message["status"] in (200, 201), (path, message)
                if status == 201 and path.endswith("/blobs") and message["type"] == "http.response.body":
                    blob = json.loads(message["body"])["staged_blob_id"]
                    self.uploaded_at[blob] = len(self.calls)
                if status >= 400 and message["type"] == "http.response.body":
                    self.errors.append((path, status, message.get("body", b"")))
                if drop and message["type"] == "http.response.body":
                    self.replayed.append(path)
                    # The real API committed. End the connection after sending the response headers.
                    raise ConnectionError("simulated response loss")
                await send(message)

            await app(scope, _request_body(body, receive), relay)

        return observe

    def _fail_renewal(self) -> bool:
        if self.loss in {"lease", "network"} and (self.state / "executor-starts.jsonl").exists():
            self.renewals_failed += 1
            return True
        return False


def _request_body(body: bytes | None, receive: Receive) -> Receive:
    async def next_message() -> Message:
        nonlocal body
        if body is not None:
            current, body = body, None
            return {"type": "http.request", "body": current, "more_body": False}
        return await receive()

    return next_message


def _api(side: RecoverySide, wire: _Wire) -> Callable[[str], ASGIApp]:
    app = side.app
    authenticate = token_authenticator(app.uow_factory, PEPPER, Surface.API, app.bus._ids, side.clock)
    routes = build_route_table(MODULE_IDS)
    bus = app.bus

    def start(address: str) -> ASGIApp:
        api = create_app(
            replace(app, authenticator=authenticate),
            route_table=routes,
            registry=bus._registry,
            schema_check=lambda: None,
            no_background=True,
            settings={"api.bind": address},
        )
        upload, _ = bind_embedded_upload(
            app.uow_factory,
            bus._authorizer,
            bus._scopes,
            app.config,
            app.gateways,
            bus._clock,
            bus._ids,
            bus.dispatch,
            bus.ask,
        )
        mount_blobs(api, upload)
        observed = wire.wrap(api)

        async def request_with_current_clock(scope, receive, send):
            side.clock.set(SystemClock().now())
            await observed(scope, receive, send)

        return request_with_current_clock

    return start


def _run_remote(
    side: RecoverySide,
    endpoint: str,
    wire: _Wire,
    *,
    case: Any = None,
    scenario_path: Path | None = None,
    auto: bool = False,
    max_assignments: int = 1,
) -> subprocess.CompletedProcess[str]:
    remote = wire.state.parent
    remote.mkdir(mode=0o700, exist_ok=True)
    credential = remote / "worker.token"
    credential.write_text(side.secret, encoding="utf-8")
    credential.chmod(0o600)
    bootstrap = remote / "bootstrap.toml"
    bootstrap.write_text(
        f'schema = "{BOOTSTRAP_URN}"\ninstance_id = "{side.app.instance_id}"\n'
        f'[access]\nmode = "http"\n[api]\nendpoint = "{endpoint}/api/v1"\n'
        f'credential = "secret://file/{credential}"\ntimeout_seconds = 2\n'
        f'[host]\nid = "{"auto" if auto else side.host1}"\n'
        f'[paths]\nstate_dir = "{wire.state}"\n',
        encoding="utf-8",
    )
    data = remote / "input.json"
    data.write_text(
        json.dumps(
            {
                "state": str(wire.state),
                "repository": str(case.repository) if case else None,
                "repository_id": str(side.repo_id),
                "run_id": str(case.run.id) if case else None,
                "script": str(scenario_path) if scenario_path else None,
                "request": {
                    "worker_id": str(side.worker1),
                    "workspace_id": str(side.ws),
                    "host_id": str(side.host1),
                    "offer": {
                        "capabilities": ["fake", "codex_cli"],
                        "labels": ["linux"],
                        "environment_kinds": ["git_worktree"],
                        "isolation_profiles": ["worktree", "landlock"],
                    },
                    "once": True,
                    "max_assignments": max_assignments,
                    "max_wait_seconds": 0,
                },
            }
        )
    )
    env = {key: val for key, val in os.environ.items() if not key.startswith(("SKM_", "PG"))}
    env.update(SKM_BOOTSTRAP=str(bootstrap), PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    code = (
        _ISOLATION
        + inspect.getsource(_worker_subprocess)
        + "\nraise SystemExit(_worker_subprocess(sys.argv[1]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(data)],
        cwd=remote,
        env=env,
        check=False,
        text=True,
        capture_output=True,
        timeout=100,
    )
    assert side.secret not in result.stdout + result.stderr
    return result


def test_workspace_worker_recovers_lost_finalize_and_result_responses(recovery: RecoverySide) -> None:
    side = recovery
    set_setting(side, "worker.disk_min_bytes", 0)
    case = single_run(side)
    path = successful_script(side, case.task.display_key)
    wire = _Wire(side.root / "remote" / "state", "responses")
    wire.state.mkdir(mode=0o700, parents=True)
    (wire.state / "host.json").write_text(json.dumps({"host_id": str(side.host1)}))
    with loopback_server(_api(side, wire)) as endpoint:
        headers = {"Authorization": f"Bearer {side.secret}", "SKM-Client-Version": "2.0.0"}
        identity = httpx.get(endpoint + "/api/v1/me", headers=headers).json()
        assert {entry["scope_kind"] for entry in identity["memberships"]} == {"workspace"}
        result = _run_remote(side, endpoint, wire, case=case, scenario_path=path, auto=True)
    assert result.returncode == 0, (
        result.stderr + result.stdout + repr([(path, key) for path, key, _ in wire.calls]) + repr(wire.errors)
    )
    if json.loads(result.stdout)["slots"] != [{"outcome": "stopped", "assignments": 1}]:
        pytest.fail(f"{result.stdout} {result.stderr} {wire.errors!r}", pytrace=False)
    calls = [path for path, _, _ in wire.calls]
    assert f"/api/v1/worker/hosts/{side.host1}/config" in calls
    assert f"/api/v1/hosts/{side.host1}/runtimes" in calls
    assert len(wire.replayed) >= 2
    for route in wire.replayed:
        attempts = [(key, body) for path, key, body in wire.calls if path == route]
        assert len(attempts) == 2
        assert attempts[0] == attempts[1]
        key, body = attempts[0]
        if route.endswith("/finalize"):
            assert key is None
            blob = json.loads(body)["prompt_staged_blob"]["staged_blob_id"]
            assert wire.uploaded_at[blob] <= calls.index(route)
        else:
            assert key
            assert b'"staged_blob"' in body
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(case.run.id).status.value == "succeeded"
        history = uow.repo(StageRepository).history(case.attempt.id)
        assert len(history.of_stage("execute")) == 1


@pytest.mark.parametrize("loss", ["lease", "network"])
def test_lost_heartbeat_reaps_runtime_without_recording_stale_result(
    recovery: RecoverySide, loss: str
) -> None:
    side = recovery
    set_setting(side, "worker.disk_min_bytes", 0)
    case = single_run(side)
    key = case.task.display_key
    hang = scenario(side.root / "hang.toml", "executor", model="fake-a", hang=True)
    path = script(side.root / "hang-script.toml", [("executor", key, 1, hang)])
    wire = _Wire(side.root / "remote" / "state", loss)
    with loopback_server(_api(side, wire)) as endpoint:
        result = _run_remote(side, endpoint, wire, case=case, scenario_path=path, max_assignments=2)
    assert result.returncode == 1, result.stderr + result.stdout
    assert json.loads(result.stdout)["slots"] == [
        {
            "outcome": "stopped",
            "reason": "lease_lost",
            "assignments": 1,
        }
    ]
    assert wire.renewals_failed == (1 if loss == "lease" else 8)
    assert len([path for path, _, _ in wire.calls if path.endswith("/claim")]) == 1
    assert len([path for path, _, _ in wire.calls if path.endswith("/result")]) == 1  # environment only
    (facts,) = (wire.state / "ownership-facts").glob("*.json")
    process = json.loads(facts.read_text())
    current = identity_of(process["pid"])
    assert current is None or current.start_ticks != process["start_ticks"]


@pytest.mark.parametrize("host_record", [None, "null", '{"host_id":"invalid"}'])
def test_http_auto_host_is_validated_before_contacting_server(
    recovery: RecoverySide,
    host_record: str | None,
) -> None:
    wire = _Wire(recovery.root / "remote" / "state")
    if host_record is not None:
        wire.state.mkdir(mode=0o700, parents=True)
        (wire.state / "host.json").write_text(host_record)
    with loopback_server(_api(recovery, wire)) as endpoint:
        result = _run_remote(recovery, endpoint, wire, auto=True)
    assert result.returncode == 6, result.stderr + result.stdout
    assert json.loads(result.stdout) == {
        "code": "CONFIG_INVALID",
        "details": {"field": "host.id", "reason": "auto_forbidden_in_http"},
    }
    assert not wire.calls


def test_foreign_scopes_and_revoked_worker_credential_are_rejected(recovery: RecoverySide) -> None:
    side = recovery
    foreign = cast("CreateWorkspaceResult", side.client.dispatch(CreateWorkspace("other", "Other")))
    wire = _Wire(side.root / "remote" / "state")
    with loopback_server(_api(side, wire)) as endpoint, httpx.Client(base_url=endpoint) as client:
        client.headers.update({"Authorization": f"Bearer {side.secret}", "SKM-Client-Version": "2.0.0"})
        own_config = f"/api/v1/worker/hosts/{side.host1}/config"
        assert client.get(own_config).status_code == 200
        assert client.get(f"/api/v1/worker/hosts/{side.host2}/config").status_code == 403
        denied = client.post(
            "/api/v1/worker/assignments/claim",
            headers={"Idempotency-Key": "foreign-claim"},
            json={
                "worker_id": str(side.worker1),
                "workspace_id": str(foreign.workspace_id),
                "host_id": str(side.host1),
                "max_wait_seconds": 0,
                "reaped_steps": [],
                "offer": {
                    "capabilities": [],
                    "labels": [],
                    "environment_kinds": [],
                    "isolation_profiles": [],
                },
            },
        )
        assert denied.status_code == 403, denied.text
        assert denied.json()["details"]["reason_code"] == "TOKEN_SCOPE"
        identity = client.get("/api/v1/me").json()
        side.client.dispatch(RevokeToken(UUID(identity["token"]["token_id"])))
        assert client.get(own_config).status_code == 401
        result = _run_remote(side, endpoint, wire)
    assert result.returncode == 6, result.stderr + result.stdout
    assert json.loads(result.stdout)["code"] == "UNAUTHENTICATED"
