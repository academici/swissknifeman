"""Explicit test host composition in an external OS process; every handler is production code."""

import json
import os
import secrets
import sys
import traceback
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from contracts.execution.harness import PEPPER, _FixedPepper
from fakes.clock import FrozenClock
from fixtures.execution.pause_result import with_result_pause
from fixtures.execution.runtime import RecordedRuntime
from skm.adapters.checks.registry import build_check_registry
from skm.adapters.git.environments.worktree import git_worktree_environments
from skm.adapters.git.integration import GitIntegrator
from skm.adapters.git.runner import GitRunner
from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.adapters.sandbox.registry import build_isolation_registry
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostServices
from skm.bootstrap.composition import CompositionOverrides, StoredScopeChain, build_app
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
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import AttemptId, HostId, RepositoryId, ScopeId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.public import RbacAuthorizer, TokenPepperSource, authenticate_token
from skm.modules.execution.domain.environment import EnvironmentKind, attempt_branch
from skm.modules.execution.host.environment import EnvironmentMount, EnvironmentSpec
from skm.modules.execution.host.isolation import IsolationSpec
from skm.modules.execution.host.stages.agent_review import AgentReviewStage
from skm.modules.execution.host.stages.agent_step import AgentStepStage
from skm.modules.execution.host.stages.base import StageRequest
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
from skm.modules.runtimes.domain.capability import StaticCapabilityCatalog
from skm.modules.runtimes.ports import AgentRuntime, CapabilityCatalog
from skm.modules.runtimes.public import ProcessOwner, RuntimeRegistry
from skm.modules.workspace.public import RecordWorkerHeartbeat
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.system_clock import SystemClock, SystemMonotonic
from skm.platform.tokens.heuristic import HeuristicTokenEstimator
from support.fault_injection import FaultPlan, FaultyClient, MissingRuntimeVisibility, StageDiagnostics
from support.runtime_bootstrap import TestRuntimeRegistry


def _stage_target_ref(request: StageRequest) -> str:
    run_id = request.task["run_id"]
    assert isinstance(run_id, str)
    return "refs/heads/skm/integration/" + run_id


def _runtime(data, state: Path) -> AgentRuntime:
    fake = FakeRuntime(state_dir=state, script=Path(data["script"]), allow_pgroup_best_effort=True)
    recorded = RecordedRuntime(fake, state, build_host_storage(state))
    return cast(
        "AgentRuntime", MissingRuntimeVisibility(recorded) if data.get("missing_visibility") else recorded
    )


def run(path):
    data = json.loads(Path(path).read_text())
    root, state, repository = (Path(data[k]) for k in ("root", "state", "repository"))
    clock = FrozenClock(datetime.fromisoformat(data["now"]))
    boot = replace(
        load_bootstrap(None, {"SKM_DATABASE_URL": data["dsn"]}, root),
        instance_id=UUID(data["instance_id"]),
        host_id=UUID(data["host_id"]),
        blobs_root=Path(data["blobs_root"]),
        database_pool_min_size=0,
        database_pool_max_size=8,
    )
    runtime = _runtime(data, state)
    app = build_app(
        boot,
        surface=Surface.WORKER,
        environ={},
        invocation={},
        backend="postgres",
        overrides=CompositionOverrides(
            RbacAuthorizer(clock),
            StoredScopeChain(),
            clock=clock,
            instance_id=UUID(data["instance_id"]),
            gateways=GatewayTable(
                {
                    TokenPepperSource: _FixedPepper(),
                    TokenEstimator: HeuristicTokenEstimator(),
                    CapabilityCatalog: StaticCapabilityCatalog({"fake": runtime.capabilities()}, {}),
                },
                "control_plane_gateway",
            ),
        ),
    )
    try:
        with app.uow_factory(RequestMeta("req_" + "a" * 26, Surface.WORKER, None, clock.now())) as uow:
            actor = authenticate_token(uow, data["secret"], pepper=PEPPER, now=clock.now())
            config = app.config.effective_host(
                uow.repo(ConfigStore),
                uow.repo(ScopeTree),
                ScopeRef(ScopeKind.HOST, ScopeId(UUID(data["host_id"]))),
            )
            uow.commit()
        client = FaultyClient(
            app.client(actor=actor, surface=Surface.WORKER), FaultPlan({}), diagnostics=True
        )
        client.dispatch(RecordWorkerHeartbeat(UUID(data["worker_id"]), None))
        client = with_result_pause(client, app, data, state)
        if data.get("heartbeat_fault"):
            client = FaultyClient(client, FaultPlan({}), heartbeat_losses=2, heartbeat_after_process=True)
        git, concurrency = GitRunner(), worker_concurrency()
        manager = git_worktree_environments(git, worktrees_root=root / "worktrees")
        repository_id = RepositoryId(UUID(data["repository_id"]))
        mono = SystemMonotonic()
        vcs = GitIntegrator(
            git,
            worktrees_root=root / "integration",
            now=SystemClock().now,
            monotonic=mono.monotonic,
            repositories={data["repository_id"]: repository},
        )
        isolation = build_isolation_registry(allow_unconfined=True)
        stages = []

        def spec(request, _deps):
            attempt = AttemptId(UUID(request.task["attempt_id"]))
            result = git.run(repository, ["rev-parse", "--verify", _stage_target_ref(request)], check=False)
            baseline = result.stdout.strip() if result.exit_code == 0 else "main"
            return EnvironmentSpec(
                attempt,
                EnvironmentKind.GIT_WORKTREE,
                (EnvironmentMount("repo", repository_id, str(repository), baseline),),
                attempt_branch(attempt),
                root / "worktrees",
                None,
                None,
            )

        def output(request, deps):
            return seal_worker_snapshot(git, state, manager, request, deps)

        def marks(request, _deps):
            raw = json.loads((state / "sealed-outputs" / f"{request.task['attempt_id']}.json").read_text())
            return {"repo": {p["path_bytes"]: p["fingerprint"] for p in raw["manifest"]["changed_paths"]}}

        def check_isolation(raw, cwd, request, _deps):
            owner = ProcessOwner(
                UUID(data["host_id"]),
                UUID(data["worker_id"]),
                UUID(request.task["attempt_id"]),
                UUID(request.begin["stage_record_id"]),
                "check",
                UUID(raw["check_execution_id"]),
                secrets.token_hex(24),
                str(state / "identities"),
            )
            return IsolationSpec(cwd, (cwd,), (cwd,), (), False, "full", (), {}, None, (), owner)

        def ownership(effect, request, _deps):
            return {
                "kind": "pgroup_best_effort",
                "ref": f"pgroup:{effect}",
                "owner": {
                    "host_id": data["host_id"],
                    "worker_id": data["worker_id"],
                    "attempt_id": request.task["attempt_id"],
                    "stage_record_id": request.begin["stage_record_id"],
                    "unit_kind": "git_effect",
                    "unit_id": str(effect),
                    "owner_nonce": secrets.token_hex(24),
                    "identity_dir": str(state / "identities"),
                },
            }

        def verify_environment(env):
            manager.reopen(env.environment_id, env.locator)

        stages.extend(
            (
                PrepareEnvironmentStage(manager, spec=spec, patch_files=lambda _env: ()),
                AgentStepStage(
                    concurrency=concurrency,
                    validate_result=worker_schema_issues,
                    seal_snapshot=output,
                    read_transcript=read_runtime_transcript,
                ),
                AgentReviewStage(
                    concurrency=concurrency,
                    validate_result=worker_schema_issues,
                    read_transcript=read_runtime_transcript,
                ),
                RunChecksStage(
                    isolation=check_isolation,
                    read_capture=Path.read_bytes,
                    verify_environment=verify_environment,
                    candidate_marks=marks,
                    environment_manager=manager,
                    current_tips=lambda request, deps: {
                        "repo": git.run(repository, ["rev-parse", _stage_target_ref(request)]).stdout.strip()
                    },
                ),
                IntegrateStage(ownership=ownership),
            )
        )
        services = build_worker_services(
            state,
            stages=StageRegistry(StageDiagnostics(stage) for stage in stages),
            context_inputs=build_context_inputs(),
            resolve=lambda _ownership: None,
        )
        admitted_request = services.runtime_request

        def diagnosed_request(*args):
            try:
                return admitted_request(*args)
            except Exception:
                traceback.print_exc()  # test-only port diagnostics, then retain the real failure
                raise

        services = replace(services, runtime_request=diagnosed_request)
        runners = build_check_registry(
            storage=services.storage,
            capture_floor_bytes=0,
            state_dir=state,
            isolation_registry=isolation,
            profile="none",
            host=UUID(data["host_id"]),
            sanitized_env={"PATH": os.defpath},
            allow_pgroup_best_effort=True,
        )
        table = GatewayTable(
            {
                type(services): services,
                RuntimeRegistry: TestRuntimeRegistry(runtime),
                CheckRunnerRegistry: runners,
                IsolationRegistry: isolation,
                Vcs: vcs,
                ExecutionEnvironmentManager: manager,
            },
            "host_gateway",
        )
        host = HostServices(HostId(UUID(data["host_id"])), Surface.WORKER, table, lambda: config, {})
        request = {
            "worker_id": data["worker_id"],
            "host_id": data["host_id"],
            "workspace_id": data["workspace_id"],
            "offer": {
                "capabilities": ["fake", "codex_cli"],
                "labels": ["linux"],
                "environment_kinds": ["git_worktree"],
                "isolation_profiles": ["worktree", "landlock"],
            },
            "once": True,
            "max_assignments": 1,
        }
        return main(
            host=host,
            client=cast("SkmClient", client),
            request=request,
            capacity=1,
            on_result=lambda result: print(json.dumps(result), flush=True),
        )
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1]))
