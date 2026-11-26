"""Synthetic runtime catalogue and real client commands for execution contract scenarios."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from secrets import token_bytes
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

from contracts.context.harness import MutableBuiltinPacks
from fakes.clock import FakeMonotonic
from fixtures.execution.harness import _pack
from fixtures.execution.protocol import finalize
from integration.artifacts.test_upload_flow import dispatch_new
from integration.git.conftest import make_repo
from skm.adapters.checks.manual import manual_check_runner
from skm.adapters.checks.registry import CheckRunnerRegistry
from skm.adapters.git.commit import GitOutputSealer, git_vcs
from skm.adapters.git.runner import GitRunner
from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.application_bus.client import SkmClient
from skm.bootstrap.host_services import build_host_storage, build_runtime_request
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.cancel import CancelSource
from skm.kernel.ids import AttemptId, RepositoryId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.kernel.tokens import TokenEstimator
from skm.modules.access import public as access
from skm.modules.execution import public as execution
from skm.modules.execution.domain.environment import BaselineEntry, attempt_branch
from skm.modules.execution.domain.ids import EnvironmentId
from skm.modules.execution.domain.output import manifest_to_json
from skm.modules.execution.host.environment import PreparedEnvironment
from skm.modules.execution.host.isolation import IsolationSpec
from skm.modules.execution.host.stages.base import StageCapture, StageRequest
from skm.modules.execution.host.stages.run_checks import RunChecksStage
from skm.modules.execution.host.worker_loop import _instruction
from skm.modules.extensions import public as extensions
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.domain.capability import StaticCapabilityCatalog
from skm.modules.runtimes.ports import CapabilityCatalog
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from skm.platform.logging.logger import get_logger
from skm.platform.tokens.heuristic import HeuristicTokenEstimator

if TYPE_CHECKING:
    from skm.modules.execution.ports import StageDeps
    from support.backend import ClientBackend

ROOT = Path(__file__).resolve().parents[3]


def runtime_gateways(root: Path) -> dict[type[object], object]:
    fake = FakeRuntime(
        state_dir=root,
        scenario=ROOT / "tests/fixtures/runtimes/fake/review-green.toml",
    )
    return {
        BuiltinPacks: MutableBuiltinPacks(_pack()),
        TokenEstimator: HeuristicTokenEstimator(),
        CapabilityCatalog: StaticCapabilityCatalog(
            {"fake": fake.capabilities(), "fake_alt": replace(fake.capabilities(), runtime_id="fake_alt")}, {}
        ),
    }


def configure_execution(side: ClientBackend, owner: SkmClient) -> RepositoryId:
    # Install the fixture catalogue before exercising the requested client transport.
    actor = side.app.authenticate(side.seed.tokens["owner"].secret)
    side.app.client(actor=actor, surface=Surface.API).dispatch(extensions.SyncBuiltinPacks())
    repository = dispatch_new(
        owner,
        workspace.RegisterRepository(
            side.seed.workspace_id,
            "Client fixture repository",
            "https://example.invalid/client-contract.git",
            None,
        ),
    )
    dispatch_new(
        owner,
        workspace.AttachRepository(
            side.seed.project_id, repository.repository_id, mount_name="repo", role="primary"
        ),
    )
    for key, value in {
        "runtimes.allowed": ["fake"],
        "runtimes.preference": ["fake"],
        "runtimes.config_isolation.required": False,
        "runtimes.role_routing": {
            role: {"runtime": "fake"} for role in ("executor", "reviewer", "triager", "registrar")
        },
        "execution.advisor.enabled": False,
        "execution.readiness.required": False,
        "execution.parallel.max_runs_per_project": 2,
    }.items():
        owner.dispatch(
            settings.SetValue.from_json(
                {
                    "scope": {"level": "instance"},
                    "key": key,
                    "value": value,
                    "expected_row_version": 0,
                }
            )
        )
    return RepositoryId(repository.repository_id)


def manual_check(owner: str, title: str, *, key: str = "V1", required: bool = False) -> JsonObject:
    return {
        "owner": owner,
        "key": key,
        "title": title,
        "kind": "manual",
        "category": "acceptance",
        "required": required,
        "definition": {
            "instructions_md": title,
            "actor_role": "owner",
            "allowed_verdicts": ["pass", "fail"],
        },
    }


def start_run_command(plan_id: UUID, revision_id: UUID, *keys: str) -> execution.StartRun:
    return execution.StartRun.from_json(
        {
            "plan_id": str(plan_id),
            "revision_id": str(revision_id),
            "readiness_report_id": None,
            "overrides": {},
            "reason": "Execute the pinned client contract",
            "selection": {"task_keys": list(keys), "phases": []},
        }
    )


def schedule(side: ClientBackend) -> None:
    # Explicitly tick the scheduler while background services are disabled.
    service = side.app.client(
        actor=Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"), surface=Surface.BACKGROUND
    )
    dto = side.app.bus._registry.command_by_name("execution.schedule_ready_tasks").dto
    service.dispatch(dto.from_json({"limit": 100}))


@dataclass(frozen=True)
class ClientWorker:
    client: SkmClient
    worker_id: UUID
    host_id: UUID
    workspace_id: UUID
    token: str

    def claim(self) -> execution.ClaimAssignment:
        return execution.ClaimAssignment(
            worker_id=str(self.worker_id),
            host_id=str(self.host_id),
            workspace_id=str(self.workspace_id),
            offer={
                "capabilities": ["fake"],
                "labels": ["linux"],
                "environment_kinds": ["git_worktree"],
                "isolation_profiles": ["worktree", "landlock"],
            },
        )

    def fence(self, claimed: Any) -> dict[str, Any]:
        return {
            "assignment_id": claimed["assignment_id"],
            "attempt_id": claimed["attempt_id"],
            "worker_id": str(self.worker_id),
            "fencing_token": claimed["fencing_token"],
        }

    def heartbeat(self) -> None:
        self.client.dispatch(workspace.RecordWorkerHeartbeat(self.worker_id, None))


def register_worker(
    side: ClientBackend,
    owner: SkmClient,
    name: str,
    *,
    host_id: UUID | None = None,
    models: tuple[str, ...] = ("fake-a", "fake-b"),
    runtime_ids: tuple[str, ...] = ("fake",),
) -> ClientWorker:
    if host_id is None:
        registered_host = dispatch_new(
            owner,
            workspace.RegisterHost.from_json({"name": name, "platform": {"os": "linux", "arch": "x86_64"}}),
        )
        host_id = cast("UUID", registered_host.host_id)
    registered: Any = owner.dispatch(
        workspace.RegisterWorker.from_json(
            {
                "workspace_id": str(side.seed.workspace_id),
                "host_id": str(host_id),
                "display_name": name,
                "capabilities": {
                    "runtimes": list(runtime_ids),
                    "isolation_profiles": ["landlock", "worktree"],
                    "max_concurrency": 2,
                    "labels": ["linux"],
                    "platform": {"os": "linux", "arch": "x86_64"},
                    "skm_version": "2.0.0",
                },
            }
        )
    )
    worker = ClientWorker(
        side.client(token=registered.token_secret),
        registered.worker_id,
        host_id,
        side.seed.workspace_id,
        registered.token_secret,
    )
    dispatch_new(worker.client, model_snapshot(worker, side.clock.now(), models))
    worker.heartbeat()
    return worker


def model_snapshot(
    worker: ClientWorker,
    observed: datetime,
    models: tuple[str, ...],
    *,
    ttl: timedelta = timedelta(minutes=5),
) -> runtimes.RecordHostRuntimes:
    return runtimes.RecordHostRuntimes.from_json(
        {
            "host_id": str(worker.host_id),
            "installations": [
                {
                    "runtime_id": "fake",
                    "version": "0.1.0",
                    "binary_locator": None,
                    "auth_state": "ok",
                    "detected_at": observed.isoformat(),
                    "details": {
                        "executable_sha256": "sha256:" + "a" * 64,
                        "verification_key": "sha256:" + "b" * 64,
                        "adapter_version": "0.1.0",
                    },
                }
            ],
            "refresh_model_offers": True,
            "model_offers_observed_at": observed.isoformat(),
            "model_offers": [
                {
                    "runtime_id": "fake",
                    "model_id": model,
                    "effort": effort.value,
                    "observed_at": observed.isoformat(),
                    "expires_at": (observed + ttl).isoformat(),
                }
                for model in models
                for effort in runtimes.Effort
            ],
        }
    )


def begin_command(
    worker: ClientWorker, claimed: Any, *, runtime_token_secret: str | None = None
) -> execution.BeginStage:
    instruction = claimed["instruction"]
    return execution.BeginStage(
        claim=worker.fence(claimed),
        stage_id=instruction["stage_id"],
        round_no=instruction["round_no"],
        input_digest=instruction["input_digest"],
        runtime_token_secret=runtime_token_secret,
    )


def prepare_success(
    side: ClientBackend,
    worker: ClientWorker,
    claimed: Any,
    ready: Any,
    repo_id: RepositoryId,
    *,
    commit: str = "1" * 40,
) -> execution.RecordStageResult:
    attempt = AttemptId(UUID(claimed["attempt_id"]))
    locator = side.root / "fake-environments" / str(attempt)
    return execution.RecordStageResult(
        claim=worker.fence(claimed),
        stage_record_id=ready["stage_record_id"],
        outcome_kind="success",
        outcome={
            "environment_id": str(uuid4()),
            "kind": "git_worktree",
            "branch": attempt_branch(attempt),
            "mounts": [
                {"mount": "repo", "environment_locator": str(locator), "local_locator": str(locator / "repo")}
            ],
            "baseline": [
                {
                    "mount": "repo",
                    "repository_id": str(repo_id),
                    "commit_sha": commit,
                    "source_head_sha": commit,
                    "dirty_patch_file_version_id": None,
                }
            ],
        },
    )


@dataclass(frozen=True)
class AgentExecution:
    stage: StageRequest
    request: runtimes.AgentRequest
    environment: PreparedEnvironment


def prepare_agent_request(
    side: ClientBackend,
    worker: ClientWorker,
    claimed: Any,
    ready: Any,
    repo_id: RepositoryId,
    *,
    runtime_token_secret: str | None = None,
) -> AgentExecution:
    locator = side.root / "fake-environments" / str(claimed["attempt_id"])
    locator.mkdir(parents=True)
    mount = locator / "repo"
    _, commit = make_repo(mount)
    report = prepare_success(side, worker, claimed, ready, repo_id, commit=commit)
    prepared = PreparedEnvironment(
        EnvironmentId(UUID(report["outcome"]["environment_id"])),
        str(locator),
        {"repo": mount},
        (BaselineEntry("repo", repo_id, commit, commit, None),),
        report["outcome"]["branch"],
    )
    instruction = dispatch_new(worker.client, report)["next"]
    assert instruction["stage_id"] == "execute"
    secret = runtime_token_secret or str(access.generate_secret(token_bytes))
    begin = dispatch_new(
        worker.client,
        begin_command(
            worker,
            {**claimed, "instruction": instruction},
            runtime_token_secret=secret,
        ),
    )
    assert begin["outcome"] == "ready", begin
    host = SimpleNamespace(
        root=side.root,
        worker1_client=worker.client,
        worker1=worker.worker_id,
        host1=worker.host_id,
        ws=worker.workspace_id,
    )
    finalized = finalize(host, SimpleNamespace(claimed=claimed, ready=begin, prepared=prepared))
    state = side.root / "agent-state" / claimed["attempt_id"]
    state.mkdir(parents=True)
    capture = StageCapture(
        state, build_host_storage(state), owner=claimed["attempt_id"], max_bytes=4096, floor=0
    )
    task = {
        **claimed["task"],
        "host_id": str(worker.host_id),
        "worker_id": str(worker.worker_id),
        "run_id": claimed["run_id"],
        "task_id": claimed["task_id"],
        "attempt_id": claimed["attempt_id"],
        "task_key": claimed["task"]["display_key"],
    }
    try:
        stage = StageRequest(_instruction(instruction), begin, finalized, task)
        request = build_runtime_request(
            replace(stage, capture=capture),
            cast("StageDeps", SimpleNamespace(environment=prepared)),
            runtimes.SecretStr(secret),
            state_dir=state,
        )
    finally:
        capture.close()
    return AgentExecution(stage, request, prepared)


@dataclass(frozen=True)
class ExecutedChecks:
    definitions: list[dict[str, Any]]
    results: list[dict[str, Any]]


def finish_agent_and_run_checks(
    side: ClientBackend, worker: ClientWorker, claimed: Any, agent: AgentExecution, result: JsonObject
) -> ExecutedChecks:
    environment = agent.environment
    root = environment.mounts["repo"]
    (baseline,) = environment.baseline
    git = GitRunner()
    manifest = GitOutputSealer(git, state_dir=side.root / "snapshots").seal(
        root,
        attempt_id=claimed["attempt_id"],
        output_no=1,
        mount="repo",
        repository_id=baseline.repository_id,
        baseline=baseline.commit_sha,
        write_scope=(),
        read_only=True,
    )
    assert manifest.empty
    claim = worker.fence(claimed)
    stage_id = agent.stage.begin["stage_record_id"]
    output = dispatch_new(
        worker.client,
        execution.SealOutput(
            claim=claim,
            stage_record_id=stage_id,
            step_id=agent.request.request_id,
            source="executor",
            manifest=manifest_to_json(manifest),
        ),
    )
    recorded = dispatch_new(
        worker.client,
        execution.RecordStageResult(
            claim=claim,
            stage_record_id=stage_id,
            outcome_kind="success",
            outcome={
                "step_id": agent.request.request_id,
                "role_result": result,
                "output_id": output["output_id"],
            },
        ),
    )
    instruction = recorded["next"]
    assert instruction["stage_id"] == "checks", recorded
    ready = dispatch_new(worker.client, begin_command(worker, {**claimed, "instruction": instruction}))
    assert ready["outcome"] == "ready"
    assert all(not check["reused"] for check in ready["checks"])

    def isolation(raw: JsonObject, cwd: Path, request: StageRequest, _: StageDeps) -> IsolationSpec:
        owner = replace(
            agent.request.process_owner,
            stage_record_id=UUID(str(request.begin["stage_record_id"])),
            unit_kind="check",
            unit_id=UUID(str(raw["check_execution_id"])),
        )
        return IsolationSpec(cwd, (root,), (), (), True, "none", (), {}, None, (), owner)

    def verify(env: PreparedEnvironment) -> None:
        assert env == environment
        assert git.run(root, ["rev-parse", "HEAD"]).stdout.strip() == baseline.commit_sha

    checks = RunChecksStage(
        isolation=isolation,
        read_capture=Path.read_bytes,
        verify_environment=verify,
        candidate_marks=lambda *_: {"repo": {}},  # the sealed candidate has no changed paths
    )
    deps = SimpleNamespace(
        environment=environment,
        vcs=git_vcs(git, state_dir=side.root),
        clock=side.clock,
        monotonic=FakeMonotonic(),
        cancel=CancelSource().token,
        log=get_logger("client.checks"),
        check_runners=CheckRunnerRegistry({"manual": manual_check_runner()}),
        uploader=worker.client,
    )
    outcome = checks.run(
        StageRequest(_instruction(instruction), ready, None, agent.stage.task), cast("StageDeps", deps)
    )
    assert outcome.kind.value == "manual_pending"
    dispatch_new(
        worker.client,
        execution.RecordStageResult(
            claim=claim,
            stage_record_id=ready["stage_record_id"],
            outcome_kind=outcome.kind.value,
            outcome=dict(outcome.payload),
        ),
    )
    dispatch_new(
        worker.client, execution.ReleaseAssignment(claim=claim, reason="done", retain_environment=True)
    )
    return ExecutedChecks(ready["checks"], cast("list[dict[str, Any]]", outcome.payload["results"]))
