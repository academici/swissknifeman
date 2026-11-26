"""Execution scenarios use real commands, checkout snapshots and context finalization."""

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from contracts.execution._worker_protocol_support import begin, make_case, worker_claim
from fixtures.execution.harness import recovery_claim
from skm.adapters.git.commit import GitOutputSealer
from skm.adapters.git.environments.worktree import WorktreeManager
from skm.adapters.git.runner import GitRunner
from skm.application_bus.bus import Bus
from skm.application_bus.client import EmbeddedClient
from skm.application_bus.host import HostContext
from skm.bootstrap.host_services import build_context_inputs, build_host_storage
from skm.kernel.cancel import CancelSource
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import AttemptId
from skm.modules.access.public import generate_secret
from skm.modules.execution import public as execution
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
from skm.modules.execution.domain.environment import (
    BaselineEntry,
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
    attempt_branch,
)
from skm.modules.execution.domain.ids import AssignmentId
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.domain.output import manifest_to_json
from skm.modules.execution.host.context import WorkerServices
from skm.modules.execution.host.context_inputs import finalize_stage_context
from skm.modules.execution.host.environment import EnvironmentMount, EnvironmentSpec
from skm.modules.execution.ports import AttemptRepository, BudgetRepository, EnvironmentRepository
from skm.platform.logging.logger import get_logger

AUTHOR = {
    "GIT_AUTHOR_NAME": "M3",
    "GIT_AUTHOR_EMAIL": "m3@example.invalid",
    "GIT_COMMITTER_NAME": "M3",
    "GIT_COMMITTER_EMAIL": "m3@example.invalid",
}


def real_environment(side, attempt):
    git = GitRunner()
    root = side.root / f"repository-{attempt.id}"
    root.mkdir()
    git.run(root, ["init", "--initial-branch=main"])
    (root / "src").mkdir()
    (root / "src/target.py").write_text("answer = 0\n")
    git.run(root, ["add", "."])
    git.run_bytes(root, ["commit", "-m", "baseline"], env=AUTHOR)
    head = git.run(root, ["rev-parse", "HEAD"]).stdout.strip()
    manager = WorktreeManager(git, worktrees_root=side.root / "worktrees")
    prepared = manager.prepare(
        EnvironmentSpec(
            attempt.id,
            EnvironmentKind.GIT_WORKTREE,
            (EnvironmentMount("repo", side.repo_id, str(root), head),),
            attempt_branch(attempt.id),
            side.root / "worktrees",
            None,
            None,
        )
    )
    with side.uow() as uow:
        repo = uow.repo(EnvironmentRepository)
        repo.upsert(
            ExecutionEnvironment(
                prepared.environment_id,
                attempt.id,
                side.host1,
                EnvironmentKind.GIT_WORKTREE,
                (BaselineEntry("repo", side.repo_id, head, head, None),),
                attempt_branch(attempt.id),
                prepared.locator,
                EnvironmentState.READY,
                side.clock.now(),
                None,
                None,
            )
        )
        attempts = uow.repo(AttemptRepository)
        current = attempts.get(attempt.id)
        attempts.save(
            replace(current, environment_id=prepared.environment_id, state=AttemptState.RUNNING),
            expected_version=attempts.version(attempt.id),
        )
        uow.commit()
    return prepared, git, manager


def agent(side, *, role="executor"):
    run, task, attempt, assignment = make_case(
        side,
        stage_id="execute",
        stage_type="agent_step",
        params={"role": role},
        env=False,
    )
    add_budget(side, run)
    prepared, git, manager = real_environment(side, attempt)
    claimed = recovery_claim(side)
    secret = str(generate_secret(lambda n: b"Q" * n))
    begin_key = f"begin:{side.new_id()}"
    ready = begin(side, claimed, secret=secret, key=begin_key)
    assert "step" in ready, ready
    return SimpleNamespace(
        run=run,
        task=task,
        attempt=attempt,
        assignment=assignment,
        claimed=claimed,
        ready=ready,
        secret=secret,
        begin_key=begin_key,
        prepared=prepared,
        git=git,
        manager=manager,
    )


def finalize(side, case):
    state = side.root / "state"
    storage = build_host_storage(state)
    services = SimpleNamespace(storage=storage, state_dir=state)
    ctx = HostContext(
        side.worker1_client,
        GatewayTable({WorkerServices: services}, "host_gateway"),
        side.host1,
        SimpleNamespace(get=lambda _key: 0),
        get_logger("m3.context"),
        CancelSource().token,
    )
    raw = worker_claim(side, case.claimed)
    owner = WorkerClaim(
        AssignmentId(UUID(raw["assignment_id"])),
        AttemptId(UUID(raw["attempt_id"])),
        side.worker1,
        raw["fencing_token"],
    )
    return finalize_stage_context(
        ctx, owner, case.ready, case.prepared, build_context_inputs(), workspace_id=side.ws
    )


def handoff(side, case, **extra):
    return side.worker1_client.dispatch(
        execution.RenewLease(
            claim=worker_claim(side, case.claimed),
            progress={
                "stage_record_id": case.ready["stage_record_id"],
                "step_id": case.ready["step"]["step_id"],
                "phase": "runtime_started",
                **extra,
            },
        ),
        idempotency_key=f"handoff:{side.new_id()}",
    )


def manifest(side, case, *, number=1):
    value = GitOutputSealer(case.git, state_dir=side.root / "snapshots").seal(
        case.prepared.mounts["repo"],
        attempt_id=str(case.attempt.id),
        output_no=number,
        mount="repo",
        repository_id=side.repo_id,
        baseline=case.prepared.baseline[0].commit_sha,
        write_scope=("src/**",),
    )
    return manifest_to_json(value)


def seal_command(side, case):
    return execution.SealOutput(
        claim=worker_claim(side, case.claimed),
        stage_record_id=case.ready["stage_record_id"],
        step_id=case.ready["step"]["step_id"],
        source="executor",
        manifest=manifest(side, case),
    )


def dispatch_result(side, claimed, ready, *, outcome=None, kind="runtime_error", client=None, key=None):
    return (client or side.worker1_client).dispatch(
        execution.RecordStageResult(
            claim=worker_claim(side, claimed),
            stage_record_id=ready["stage_record_id"],
            outcome_kind=kind,
            outcome=outcome or {"error_code": "RUNTIME_TRANSPORT"},
        ),
        idempotency_key=key or f"result:{side.new_id()}",
    )


def client_with_uow(side, client, factory):
    """Construct a bus around an injected UoW port; preserve every production collaborator."""
    base = side.app.bus
    bus = Bus(
        registry=base._registry,
        schemas=base._schemas,
        uow_factory=factory,
        authorizer=base._authorizer,
        scopes=base._scopes,
        config=base._config,
        clock=base._clock,
        ids=base._ids,
        entropy=base._entropy,
        gateways=base._gateways,
        retry=base._retry,
        idempotency_ttl=base._ttl,
    )
    return EmbeddedClient(
        bus,
        actor=client._actor,
        surface=client._surface,
        events=client._events,
        clock=client._clock,
        ids=client._ids,
        client_label=client._client_label,
        blob_uploader=client._blob_uploader,
        content_opener=client._content_opener,
    )


def add_budget(side, run):
    with side.uow() as uow:
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    "run",
                    None,
                    BudgetDimension.TOKENS,
                    Decimal(1_000_000),
                    Decimal(0),
                    Decimal(0),
                    1,
                ),
            )
        )
        uow.commit()
