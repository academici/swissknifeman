"""Draft/final/start boundaries, final budget growth and live policy narrowing."""

from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_worker_protocol import begin, claim, make_case, worker_claim
from skm.kernel.errors import SkmError
from skm.modules.access import public as access
from skm.modules.context import public as context_module
from skm.modules.context.ports import ContextRepository
from skm.modules.execution import public as execution
from skm.modules.execution.application import _stage_agent_helpers
from skm.modules.execution.application.commands import renew_lease
from skm.modules.execution.domain.stage_record import StageState
from skm.modules.execution.ports import StageRepository, StepRepository
from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import side as side


def agent_case(
    side: Any,
    monkeypatch: Any,
    *,
    stage_id: str = "execute",
    stage_type: str = "agent_step",
    params: dict[str, Any] | None = None,
) -> tuple[Any, Any, Any]:
    case = make_case(
        side, stage_id=stage_id, stage_type=stage_type, params=params or {"role": "executor"}, env=True
    )
    with side.uow() as uow:
        if stage_type == "agent_review":
            from contracts.execution.seed_helpers import seed_output
            from skm.modules.execution.domain.attempt import record_output
            from skm.modules.execution.ports import AttemptRepository

            attempt = case[2]
            output = seed_output(side, uow, attempt)
            attempts = uow.repo(AttemptRepository)
            attempts.save(
                record_output(attempt, output, previous=None), expected_version=attempts.version(attempt.id)
            )
        uow.repo(runtimes.HostRuntimeRepository).upsert(
            RuntimeInstallation(
                side.host1,
                "codex_cli",
                "1.0.0",
                "/fake/codex",
                AuthState.OK,
                side.clock.now(),
                {
                    "executable_sha256": "sha256:" + "a" * 64,
                    "verification_key": "sha256:" + "b" * 64,
                    "adapter_version": "1.0.0",
                },
            )
        )
        uow.commit()

    def route(_uow, _gateways, request, *, config, pins, as_of):
        assert pins
        assert request.host_id == side.host1
        return SimpleNamespace(
            runtime_id="codex_cli",
            model="gpt-5",
            effort=runtimes.Effort.HIGH,
            source="role_routing",
            catalog_digest="sha256:" + "c" * 64,
            operation=request.admission.operation,
            admission=request.admission,
            resume_allowance=runtimes.ResumeAllowance(True, False, None, "allowed"),
            context_window_tokens=128000,
            config_mode="isolated",
            self_loads=(),
            degraded=frozenset(),
            requested_route=None,
        )

    monkeypatch.setattr(_stage_agent_helpers, "route_role", route)
    monkeypatch.setattr(renew_lease, "host_route_is_fresh", lambda *args, **kwargs: True)
    claimed = claim(side)
    secret = str(access.generate_secret(lambda n: bytes([17]) * n))
    return case, claimed, secret


def finalize_fixture(side: Any, ready: Any, *, tokens: int = 1200) -> Any:
    step_id = UUID(ready["step"]["step_id"])
    with side.uow() as uow:
        step = uow.repo(StepRepository).get(step_id)
        repo = uow.repo(ContextRepository)
        draft = repo.get(step.context_manifest_id)
        final = replace(
            draft,
            blocks=tuple(
                replace(
                    b,
                    included=b.content_digest is not None,
                    position=i + 1 if b.content_digest is not None else None,
                )
                for i, b in enumerate(draft.blocks)
            ),
            state=context_module.ManifestState.FINAL,
            total_tokens_estimate=tokens,
            prompt_digest="sha256:" + "d" * 64,
            prompt_file_version_id=side.fv1,
            mode="full",
            task_digest="sha256:" + "e" * 64,
            finalized_at=side.clock.now(),
        )
        repo.finalize(final, ())
        uow.commit()
    return final


def handoff(side: Any, claimed: Any, ready: Any, *, key: str | None = None) -> Any:
    return side.worker1_client.dispatch(
        execution.RenewLease(
            claim=worker_claim(side, claimed),
            progress={
                "stage_record_id": ready["stage_record_id"],
                "step_id": ready["step"]["step_id"],
                "phase": "runtime_started",
            },
        ),
        idempotency_key=key or f"handoff:{side.new_id()}",
    )


@pytest.mark.parametrize("empty", [False, True])
def test_next_begin_accepts_sealed_output_without_patch(side: Any, monkeypatch: Any, empty: bool) -> None:
    import base64

    from skm.modules.execution.domain.output import ChangedPath, OutputMount, output_tree_digest
    from skm.modules.execution.ports import AttemptRepository, OutputRepository

    (_, _, attempt, _), claimed, secret = agent_case(side, monkeypatch)
    first = begin(side, claimed, secret=secret)
    finalize_fixture(side, first)
    handoff(side, claimed, first)
    changed = (
        []
        if empty
        else [
            {
                "mount": "repo",
                "path": "src/target.py",
                "path_bytes": base64.urlsafe_b64encode(b"src/target.py").decode().rstrip("="),
                "change": "modified",
                "fingerprint": "100644 " + "2" * 40,
            }
        ]
    )
    sealed = side.worker1_client.dispatch(
        execution.SealOutput(
            claim=worker_claim(side, claimed),
            stage_record_id=first["stage_record_id"],
            step_id=first["step"]["step_id"],
            source="executor",
            manifest={
                "algorithm": "skm-output-v2",
                "mounts": [
                    {
                        "mount": "repo",
                        "repository_id": str(side.repo_id),
                        "object_format": "sha1",
                        "base_commit": "1" * 40,
                        "head_commit": ("1" if empty else "2") * 40,
                        "tree_sha": "3" * 40,
                    }
                ],
                "changed_paths": changed,
                "outside_write_scope": [],
                "excluded_paths": [],
                "tree_digest": output_tree_digest(
                    (
                        OutputMount(
                            "repo", side.repo_id, "sha1", "1" * 40, ("1" if empty else "2") * 40, "3" * 40
                        ),
                    ),
                    (
                        ChangedPath(
                            p["mount"], p["path"], p["path_bytes"], "modified", None, None, p["fingerprint"]
                        )
                        for p in changed
                    ),
                ),
                "patch_file_version_id": None,
                "diff_stats": {"files": len(changed), "insertions": len(changed), "deletions": 0},
                "empty": empty,
            },
        ),
        idempotency_key=f"seal:{side.new_id()}",
    )
    # A malformed role result retries the agent against the already sealed output.
    result = side.worker1_client.dispatch(
        execution.RecordStageResult(
            claim=worker_claim(side, claimed),
            stage_record_id=first["stage_record_id"],
            outcome_kind="success",
            outcome={"step_id": first["step"]["step_id"], "role_result": {}},
        ),
        idempotency_key=f"result:{side.new_id()}",
    )
    assert result["next"]["mode"] == "retry"
    second = begin(
        side,
        {**claimed, "instruction": result["next"]},
        secret=str(access.generate_secret(lambda n: b"C" * n)),
    )
    assert second["stage_record_id"] != first["stage_record_id"]
    with side.uow(readonly=True) as uow:
        output = uow.repo(OutputRepository).get(UUID(sealed["output_id"]))
        assert output.manifest.patch_file_version_id is None
        assert output.manifest.empty is empty
        assert uow.repo(AttemptRepository).get(attempt.id).current_output_id == output.id
        step = uow.repo(StepRepository).get(UUID(second["step"]["step_id"]))
        draft = context_module.get_manifest(uow, step.context_manifest_id)
        assert draft.state is context_module.ManifestState.DRAFT
        assert all(b.block_type is not context_module.BlockType.CANDIDATE_DIFF for b in draft.blocks)


def test_draft_cannot_start_then_final_manifest_admits_once(side: Any, monkeypatch: Any) -> None:
    _, claimed, secret = agent_case(side, monkeypatch)
    ready = begin(side, claimed, secret=secret)
    assert ready["step"]["context"]["draft"] is not None
    assert secret not in str(ready)
    with pytest.raises(SkmError) as caught:
        handoff(side, claimed, ready)
    assert caught.value.code.value == "CONTEXT_NOT_FINALIZED"
    finalize_fixture(side, ready)
    key = f"handoff:{side.new_id()}"
    admitted = handoff(side, claimed, ready, key=key)
    assert "refusal" not in admitted
    assert handoff(side, claimed, ready, key=key) == admitted
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(UUID(ready["stage_record_id"])).state is StageState.RUNNING


@pytest.mark.parametrize(
    ("stage_id", "stage_type", "params", "profile_key"),
    [
        ("review", "agent_review", {"reviewer_with_fix": True}, "reviewer"),
        ("audit", "advisor_consult", {"profile": "plan-auditor"}, "plan-auditor"),
    ],
)
def test_final_context_handoff_uses_stage_authority(
    side: Any,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    stage_id: str,
    stage_type: str,
    params: dict[str, Any],
    profile_key: str,
) -> None:
    from fixtures.execution.protocol import finalize
    from skm.bootstrap.host_services import worker_concurrency
    from skm.kernel.cancel import CancelSource
    from skm.modules.execution.application._worker_protocol import parse_worker_claim
    from skm.modules.execution.host.stage_client import BoundStageClient
    from skm.modules.execution.ports import EnvironmentRepository

    (_, _, attempt, _), claimed, secret = agent_case(
        side, monkeypatch, stage_id=stage_id, stage_type=stage_type, params=params
    )
    monkeypatch.setattr(side, "root", tmp_path, raising=False)
    with side.uow(readonly=True) as uow:
        environment = uow.repo(EnvironmentRepository).for_attempt(attempt.id)
    prepared = SimpleNamespace(mounts={"repo": tmp_path}, baseline=environment.baseline)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/target.py").write_text("answer = 42\n")
    ready = begin(side, claimed, secret=secret)
    finalize(side, SimpleNamespace(claimed=claimed, ready=ready, prepared=prepared))
    selected = []
    resolve = renew_lease.live_step_profile_and_permissions

    def observe(*args):
        view, profile, permissions = resolve(*args)
        selected.append(view.key)
        return view, profile, permissions

    monkeypatch.setattr(renew_lease, "live_step_profile_and_permissions", observe)
    worker = BoundStageClient(
        side.worker1_client,
        parse_worker_claim(worker_claim(side, claimed)),
        {"renew_lease": execution.RenewLease},
        CancelSource().token,
        concurrency=worker_concurrency(),
    )
    worker.set_stage(ready["stage_record_id"], ready["step"]["step_id"])
    assert "refusal" not in worker.report_progress({"phase": "runtime_started"})
    worker.report_progress(
        {
            "tool_calls": {
                "coverage": "partial",
                "calls": [
                    {"call_id": "c1", "tool": "Edit", "duration_ms": None},
                ],
            }
        }
    )
    assert selected == [profile_key]
    with side.uow(readonly=True) as uow:
        calls = uow.repo(StepRepository).tool_calls(UUID(ready["step"]["step_id"]), after="", limit=10)
        assert [row.call.call_id for row in calls] == ["c1"]
        assert uow.repo(StageRepository).get(UUID(ready["stage_record_id"])).state is StageState.RUNNING


@pytest.mark.parametrize("finalized", [False, True])
def test_paused_handoff_interrupts_without_start_and_resume_selects_l1(
    side: Any, monkeypatch: Any, finalized: bool
) -> None:
    from skm.modules.execution.generated.commands import PauseRun, ResumeRun
    from skm.modules.execution.ports import AssignmentRepository, AttemptRepository

    (run, _, attempt, assignment), claimed, secret = agent_case(side, monkeypatch)
    ready = begin(side, claimed, secret=secret)
    if finalized:
        finalize_fixture(side, ready)
    side.client.dispatch(PauseRun(run.id, "pause before spawn"))
    refused = handoff(side, claimed, ready)
    assert refused["refusal"]["code"] == "RUN_NOT_ACTIVE"
    with side.uow(readonly=True) as uow:
        stage = uow.repo(StageRepository).get(UUID(ready["stage_record_id"]))
        assert stage.state is StageState.INTERRUPTED
        assert stage.runtime_started_at is None
        assert stage.outcome_kind is None
        assert uow.repo(AssignmentRepository).lease(assignment.id) is not None
    side.worker1_client.dispatch(
        execution.ReleaseAssignment(
            claim=worker_claim(side, claimed), reason="paused", retain_environment=True
        ),
        idempotency_key=f"release:{side.new_id()}",
    )
    side.client.dispatch(ResumeRun(run.id))
    with side.uow(readonly=True) as uow:
        cursor = uow.repo(AttemptRepository).get(attempt.id).continuation
        assert cursor.kind == "stage"
        assert cursor.cause.advance_rule == "L1"
        assert cursor.stage.stage_id == "execute"


def test_transport_retry_preserves_emergency_origin(side: Any, monkeypatch: Any) -> None:
    from datetime import timedelta

    _, claimed, secret = agent_case(side, monkeypatch)
    first = begin(side, claimed, secret=secret)
    side.clock.advance(timedelta(seconds=20))
    failed = side.worker1_client.dispatch(
        execution.ReportAttemptFailure(
            claim=worker_claim(side, claimed),
            stage_record_id=first["stage_record_id"],
            error_class="transport",
            detail="connection lost",
            worktree_dirty=False,
        ),
        idempotency_key=f"failure:{side.new_id()}",
    )
    second = begin(
        side,
        {**claimed, "instruction": failed["next"]},
        secret=str(access.generate_secret(lambda n: b"C" * n)),
    )
    assert second["step"]["limits"]["timeout_seconds"] == first["step"]["limits"]["timeout_seconds"] - 20
    assert second["step"]["admission"]["emergency_origin"] == first["step"]["admission"]["emergency_origin"]


def test_final_prompt_growth_commits_budget_refusal_and_releases_draft(side: Any, monkeypatch: Any) -> None:
    from decimal import Decimal

    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
    from skm.modules.execution.ports import BudgetRepository, DecisionRepository, RunRepository

    (run, task, _, _), claimed, secret = agent_case(side, monkeypatch)
    ready = begin(side, claimed, secret=secret)
    with side.uow() as uow:
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    "run",
                    None,
                    BudgetDimension.TOKENS,
                    Decimal(1000),
                    Decimal(0),
                    Decimal(0),
                    1,
                ),
            )
        )
        uow.commit()
    finalize_fixture(side, ready, tokens=5000)
    refused = handoff(side, claimed, ready)
    assert refused["refusal"]["code"] == "BUDGET_EXHAUSTED"
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(UUID(ready["stage_record_id"])).runtime_started_at is None
        assert uow.repo(StageRepository).get(UUID(ready["stage_record_id"])).state is StageState.FAILED
        assert not uow.repo(BudgetRepository).open_for_steps((UUID(ready["step"]["step_id"]),))
        assert uow.repo(DecisionRepository).open_for_task(task.id)
        assert uow.repo(RunRepository).get(run.id).status.value == "paused"


def test_live_authority_narrowing_blocks_old_final_context(side: Any, monkeypatch: Any) -> None:
    from unit.execution.application._support import set_setting

    _, claimed, secret = agent_case(side, monkeypatch)
    ready = begin(side, claimed, secret=secret)
    finalize_fixture(side, ready)
    set_setting(side, "policy.ceiling.shell", False)
    refused = handoff(side, claimed, ready)
    assert refused["refusal"]["code"] == "POLICY_DENIES"
    with side.uow(readonly=True) as uow:
        assert uow.repo(StageRepository).get(UUID(ready["stage_record_id"])).runtime_started_at is None


def test_revoked_runtime_binding_cannot_spawn_with_cached_ready(side: Any, monkeypatch: Any) -> None:
    _, claimed, secret = agent_case(side, monkeypatch)
    key = f"begin:{side.new_id()}"
    ready = begin(side, claimed, secret=secret, key=key)
    finalize_fixture(side, ready)
    with side.uow() as uow:
        access.revoke_assignment_tokens(
            uow,
            assignment_id=UUID(claimed["assignment_id"]),
            by=side.owner.principal_id,
            now=side.clock.now(),
        )
        uow.commit()
    assert begin(side, claimed, secret=secret, key=key) == ready
    refused = handoff(side, claimed, ready)
    assert refused["refusal"]["code"] == "POLICY_DENIES"


def test_changed_secret_under_same_begin_key_is_rejected(side: Any, monkeypatch: Any) -> None:
    _, claimed, secret = agent_case(side, monkeypatch)
    key = f"begin:{side.new_id()}"
    begin(side, claimed, secret=secret, key=key)
    changed = str(access.generate_secret(lambda n: b"Z" * n))
    with pytest.raises(SkmError) as caught:
        begin(side, claimed, secret=changed, key=key)
    assert caught.value.code.value == "IDEMPOTENCY_KEY_REUSED"


def test_result_retry_has_schema_feedback_and_old_secret_cannot_note_either_step(
    side: Any, monkeypatch: Any
) -> None:
    from datetime import timedelta

    from contracts.execution.harness import PEPPER
    from skm.kernel.ports_uow import Surface

    _, claimed, secret = agent_case(side, monkeypatch)
    first = begin(side, claimed, secret=secret)
    finalize_fixture(side, first)
    with side.uow(readonly=True) as uow:
        actor = access.authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())
    runtime = side.app.client(actor=actor, surface=Surface.MCP)
    terminal = side.worker1_client.dispatch(
        execution.RecordStageResult(
            claim=worker_claim(side, claimed),
            stage_record_id=first["stage_record_id"],
            outcome_kind="success",
            outcome={"step_id": first["step"]["step_id"], "role_result": {}},
        ),
        idempotency_key=f"result:{side.new_id()}",
    )
    side.clock.advance(timedelta(seconds=30))
    second = begin(
        side,
        {**claimed, "instruction": terminal["next"]},
        secret=str(access.generate_secret(lambda n: b"B" * n)),
    )
    assert second["step"]["step_id"] != first["step"]["step_id"]
    assert second["step"]["result_contract"]["schema_errors"]
    assert second["step"]["limits"]["timeout_seconds"] == first["step"]["limits"]["timeout_seconds"] - 30
    for ready in (first, second):
        with pytest.raises(SkmError):
            runtime.dispatch(
                execution.RecordStepNote(
                    step_id=ready["step"]["step_id"], kind="progress", text="old authority"
                ),
                idempotency_key=f"note:{side.new_id()}",
            )


@pytest.mark.parametrize("intensity", ["light", "medium", "heavy"])
def test_reviewer_emergency_limit_is_independent_of_soft_intensity(side: Any, intensity: str) -> None:
    from datetime import timedelta

    from skm.modules.execution.application._stage_agent_helpers import runtime_limits
    from skm.modules.execution.application._worker_protocol import lock_fenced_context
    from skm.modules.execution.domain.step import RoleId
    from unit.execution.application._support import context

    run, _, _, _ = make_case(side)
    claimed = claim(side)
    with side.uow() as uow:
        ctx = context(side, uow, run, actor=side.worker1_client._actor)
        fenced = lock_fenced_context(uow, ctx, worker_claim(side, claimed))
        profile = SimpleNamespace(
            limits=SimpleNamespace(
                timeout_seconds=3600, idle_timeout_seconds=600, max_turns=None, max_output_tokens=1000
            )
        )
        limits = runtime_limits(uow, ctx, fenced, RoleId.REVIEWER, profile, started_at=fenced.now)
        assert limits["timeout_seconds"] == 1800
        warnings = {"light": 180, "medium": 300, "heavy": 600}
        elapsed = warnings[intensity]
        remaining = runtime_limits(
            uow, ctx, fenced, RoleId.REVIEWER, profile, started_at=fenced.now - timedelta(seconds=elapsed)
        )
        assert remaining["timeout_seconds"] == 1800 - elapsed


def test_runtime_reserve_savepoint_rolls_back_partial_accounts_and_dimensions(
    exec_side: Any, monkeypatch: Any
) -> None:
    from decimal import Decimal

    from skm.modules.execution.application import _stage_preparation
    from skm.modules.execution.application.commands import renew_lease
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
    from skm.modules.execution.ports import BudgetRepository

    side = exec_side
    (run, task, _, _), claimed, secret = agent_case(side, monkeypatch)

    def priced(_uow, _ctx, _fenced, _step, tokens, output):
        return replace(runtimes.estimate_from_prompt(tokens, output), cost_usd_micros=tokens + output)

    monkeypatch.setattr(_stage_preparation, "estimate", priced)
    monkeypatch.setattr(renew_lease, "estimate", priced)
    with side.uow() as uow:
        uow.repo(BudgetRepository).add_accounts(
            tuple(
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    scope,
                    task.id if scope == "task" else None,
                    dimension,
                    None,
                    Decimal(0),
                    Decimal(0),
                    1,
                )
                for dimension in (BudgetDimension.TOKENS, BudgetDimension.USD)
                for scope in ("run", "task")
            )
        )
        uow.commit()
    ready = begin(side, claimed, secret=secret)
    step_id = UUID(ready["step"]["step_id"])
    finalize_fixture(side, ready, tokens=5000)
    with side.uow(readonly=True) as uow:
        repo = uow.repo(BudgetRepository)
        draft_ids = {r.id for r in repo.open_for_steps((step_id,))}
        draft_balances = {
            a.id: a.reserved
            for dimension in (BudgetDimension.TOKENS, BudgetDimension.USD)
            for a in repo.accounts_for(run.id, task.id, dimension)
        }
        implementation = type(repo)
    original_reserve = implementation.reserve
    calls = []

    def partial(self, account_ids, amount):
        calls.append(tuple(account_ids))
        if len(calls) == 2:
            assert original_reserve(self, account_ids[:1], amount)
            return False  # fail after the first account UPDATE in the second dimension
        return original_reserve(self, account_ids, amount)

    monkeypatch.setattr(implementation, "reserve", partial)
    original_refusal = renew_lease.committed_refusal
    observed = []

    def check_rollback(uow, ctx, fenced, stage, *, code):
        repo = uow.repo(BudgetRepository)
        assert {r.id for r in repo.open_for_steps((step_id,))} == draft_ids
        assert {
            a.id: a.reserved
            for dimension in (BudgetDimension.TOKENS, BudgetDimension.USD)
            for a in repo.accounts_for(run.id, task.id, dimension)
        } == draft_balances
        observed.append(code)
        original_refusal(uow, ctx, fenced, stage, code=code)

    monkeypatch.setattr(renew_lease, "committed_refusal", check_rollback)
    refused = handoff(side, claimed, ready)
    assert refused["refusal"]["code"] == "BUDGET_EXHAUSTED"
    assert observed == ["BUDGET_EXHAUSTED"]
    assert len(calls) == 2
    with side.uow(readonly=True) as uow:
        repo = uow.repo(BudgetRepository)
        assert not repo.open_for_steps((step_id,))
        assert all(
            a.reserved == 0 and a.spent == 0
            for dimension in (BudgetDimension.TOKENS, BudgetDimension.USD)
            for a in repo.accounts_for(run.id, task.id, dimension)
        )
        assert uow.repo(StageRepository).get(UUID(ready["stage_record_id"])).runtime_started_at is None
