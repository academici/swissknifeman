"""Fenced worker protocol against real memory and PostgreSQL units of work."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

from contracts.context.harness import _profile_toml, core_pack
from contracts.execution.seed_helpers import make_work_policies, seed_attempt, seed_run, seed_task
from contracts.extensions.harness import pack_payload
from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.kernel.errors import NotFound
from skm.modules.execution import public as execution
from skm.modules.execution.domain.assignment import Assignment, AssignmentState, WorkerRequirements
from skm.modules.execution.domain.attempt import AttemptState, ContinuationCause, SelectedStage, select_stage
from skm.modules.execution.domain.environment import (
    BaselineEntry,
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
    attempt_branch,
)
from skm.modules.execution.domain.execution_bundle import ExecutionBundle, ResourcePins
from skm.modules.execution.domain.run import RunKind
from skm.modules.execution.domain.task import TaskKind
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import (
    AssignmentRepository,
    AttemptRepository,
    BundleRepository,
    EnvironmentRepository,
    TaskRepository,
)
from skm.modules.extensions import public as extensions
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.ports import CapabilityCatalog, HostModelAvailabilityRepository
from skm.modules.settings import public as settings
from unit.execution.application._support import context

ROOT = Path(__file__).resolve().parents[3]


def _fixture_catalog() -> str:
    from fixtures.execution.harness import CATALOG

    return CATALOG.replace("runtimes.fake", "runtimes.codex_cli").replace("fake-b", "gpt-5")


def _publish_fixture_offer(side: Any) -> None:
    """Equip a synthetic registered worker while leaving deliberate runtime setups alone."""
    from skm.modules.workspace import public as workspace

    observed = side.clock.now()
    with side.uow(readonly=True) as uow:
        worker = workspace.get_worker(uow, side.worker1)
        if "codex_cli" not in worker.capabilities.runtimes:
            return
        current = uow.repo(HostModelAvailabilityRepository).worker_snapshot(side.worker1)
        if current is not None and current.fresh_at(observed):
            return
        cfg = context(side, uow).config
        if runtimes.catalog(uow, config=cfg).model("codex_cli", "gpt-5") is None:
            return
        allowed = cfg.get("runtimes.allowed")
        preference = cfg.get("runtimes.preference")
        needs_isolation = cfg.get("runtimes.config_isolation.required")

    if "codex_cli" not in allowed:
        side.client.dispatch(
            settings.SetValue.from_json(
                {"scope": {"level": "instance"}, "key": "runtimes.allowed", "value": ["codex_cli"]}
            )
        )
    if "codex_cli" not in preference:
        side.client.dispatch(
            settings.SetValue.from_json(
                {"scope": {"level": "instance"}, "key": "runtimes.preference", "value": ["codex_cli"]}
            )
        )
    if needs_isolation is True:
        side.client.dispatch(
            settings.SetValue.from_json(
                {"scope": {"level": "instance"}, "key": "runtimes.config_isolation.required", "value": False}
            )
        )
    gates = side.app.gateways
    catalog = gates.get(CapabilityCatalog) if gates.has(CapabilityCatalog) else None
    if catalog is None or "codex_cli" not in catalog.registered():
        fake = FakeRuntime(
            state_dir=ROOT,
            scenario=ROOT / "tests/fixtures/runtimes/fake/review-green.toml",
        )
        declarations = {} if catalog is None else {key: catalog.static(key) for key in catalog.registered()}
        declarations["codex_cli"] = replace(
            fake.capabilities(), runtime_id="codex_cli", read_only_network=True
        )
        side.app.gateways.entries[CapabilityCatalog] = runtimes.StaticCapabilityCatalog(declarations, {})
    side.worker1_client.dispatch(
        runtimes.RecordHostRuntimes.from_json(
            {
                "host_id": str(side.host1),
                "installations": [
                    {
                        "runtime_id": "codex_cli",
                        "version": "1.0.0",
                        "binary_locator": None,
                        "auth_state": "ok",
                        "detected_at": observed.isoformat(),
                        "details": {},
                    }
                ],
                "model_offers_observed_at": observed.isoformat(),
                "model_offers": [
                    {
                        "runtime_id": "codex_cli",
                        "model_id": "gpt-5",
                        "effort": "high",
                        "observed_at": observed.isoformat(),
                        "expires_at": (observed + timedelta(minutes=5)).isoformat(),
                    }
                ],
                "refresh_model_offers": True,
            }
        )
    )


def make_case(
    side: Any,
    *,
    stage_id: str = "prepare",
    stage_type: str = "prepare_environment",
    params: Any = None,
    env: bool = False,
    attempt_no: int = 1,
    kind: RunKind = RunKind.PLAN,
) -> Any:
    from skm.modules.workspace import public as workspace

    side.worker1_client.dispatch(workspace.RecordWorkerHeartbeat(side.worker1, None))
    with side.uow(readonly=True) as uow:
        cfg = context(side, uow).config
        try:
            view = extensions.resolve_resource(
                uow, extensions.ResourceKind.WORKFLOW, "reviewed-development", config=cfg
            )
        except NotFound:
            view = None
    if view is None:
        pack = core_pack("1.2.0")
        files = {f.path: f.content.decode() for f in pack.files}
        files["runtimes/models.toml"] = _fixture_catalog()
        for role in ("reviewer", "registrar"):
            files[f"agent-profiles/{role}.toml"] = _profile_toml(role, "1.2.0")
        files["workflows/reviewed-development.toml"] = (
            (ROOT / "tests/fixtures/corpus/examples/execution/workflows/quick-fix.toml")
            .read_text()
            .replace('id = "quick-fix"', 'id = "reviewed-development"')
        )
        side.app.gateways.get(BuiltinPacks).current = (pack_payload("core", "1.2.0", files=files),)
        side.client.dispatch(SyncBuiltinPacks())
    if stage_type in {"agent_step", "agent_review", "advisor_consult"}:
        _publish_fixture_offer(side)
    with side.uow() as uow:
        cfg = context(side, uow).config
        view = extensions.resolve_resource(
            uow, extensions.ResourceKind.WORKFLOW, "reviewed-development", config=cfg
        )
        profile_version = side.workflow_rv_id
        side.workflow_rv_id = view.resource_version_id
        try:
            run = seed_run(
                side,
                uow,
                kind=kind,
                inline_spec_file_version_id=side.fv1 if kind is RunKind.ADHOC else None,
            )
        finally:
            side.workflow_rv_id = profile_version
        cfg = context(side, uow, run).config
        pins = extensions.pinned_pack_versions(uow, config=cfg)
        bundle = ExecutionBundle(
            run.id,
            cfg.freeze(cfg.registry).to_document(),
            cfg.digest,
            "sha256:" + "1" * 64,
            ResourcePins((), pins),
            None,
            make_work_policies("ADHOC-1") if kind is RunKind.ADHOC else make_work_policies(),
            {},
            run.review_grouping,
            side.clock.now(),
        )
        uow.repo(BundleRepository).add(bundle)
        task = (
            seed_task(side, uow, run.id, kind=TaskKind.ADHOC, display_key="ADHOC-1")
            if kind is RunKind.ADHOC
            else seed_task(side, uow, run.id)
        )
        attempt = seed_attempt(
            side,
            uow,
            run.id,
            task.id,
            attempt_no=attempt_no,
            state=AttemptState.RUNNING if env else AttemptState.PREPARING,
        )
        selected = SelectedStage(
            stage_id, stage_type, StageMode.NORMAL, 1, params or {}, None, None, FeedbackRefs(), None, None
        )
        attempt = select_stage(
            attempt, cause=ContinuationCause("run_start", "A1"), stage=selected, continuation_id=side.new_id()
        )
        uow.repo(AttemptRepository).save(attempt, expected_version=1)
        task = replace(task, current_attempt_id=attempt.id, attempt_count=attempt_no, row_version=2)
        uow.repo(TaskRepository).save(task, expected_version=1)
        assignment = Assignment(
            side.new_id(),
            run.id,
            task.id,
            attempt.id,
            side.ws,
            AssignmentState.AVAILABLE,
            side.clock.now(),
            WorkerRequirements(frozenset(), None, frozenset(), EnvironmentKind.GIT_WORKTREE, frozenset()),
            0,
            0,
            None,
            None,
            None,
            side.clock.now(),
            1,
        )
        uow.repo(AssignmentRepository).add(assignment)
        if env:
            environment = ExecutionEnvironment(
                side.new_id(),
                attempt.id,
                side.host1,
                EnvironmentKind.GIT_WORKTREE,
                (BaselineEntry("repo", side.repo_id, "1" * 40, "1" * 40, None),),
                attempt_branch(attempt.id),
                f"/owned/{attempt.id}",
                EnvironmentState.READY,
                side.clock.now(),
                None,
                None,
            )
            uow.repo(EnvironmentRepository).upsert(environment)
            attempt = replace(attempt, environment_id=environment.id)
            uow.repo(AttemptRepository).save(attempt, expected_version=2)
        uow.commit()
    return run, task, attempt, assignment


def claim(side: Any, *, key: str | None = None, runtime_id: str = "codex_cli") -> Any:
    return side.worker1_client.dispatch(
        execution.ClaimAssignment(
            worker_id=str(side.worker1),
            host_id=str(side.host1),
            workspace_id=str(side.ws),
            offer={
                "capabilities": [runtime_id],
                "labels": ["linux"],
                "environment_kinds": ["git_worktree"],
                "isolation_profiles": ["landlock"],
            },
        ),
        idempotency_key=key or f"claim:{side.new_id()}",
    )


def worker_claim(side: Any, claimed: Any) -> dict[str, Any]:
    return {
        "assignment_id": claimed["assignment_id"],
        "attempt_id": claimed["attempt_id"],
        "worker_id": str(side.worker1),
        "fencing_token": claimed["fencing_token"],
    }


def begin(side: Any, claimed: Any, *, secret: str | None = None, key: str | None = None) -> Any:
    inst = claimed["instruction"]
    return side.worker1_client.dispatch(
        execution.BeginStage(
            claim=worker_claim(side, claimed),
            stage_id=inst["stage_id"],
            round_no=inst["round_no"],
            input_digest=inst["input_digest"],
            runtime_token_secret=secret,
        ),
        idempotency_key=key or f"begin:{side.new_id()}",
    )
