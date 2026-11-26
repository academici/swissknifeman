"""Dual-backend contract tests for execution read facades, ench3, and work policy."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest

from contracts.context.harness import CHK_ID, ITEM_ID, UNIT_ID, core_pack
from contracts.extensions.harness import pack_payload
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import EntityId, RunId
from skm.kernel.json_types import JsonObject
from skm.modules.artifacts.public import BindingRole
from skm.modules.execution import public as execution
from skm.modules.execution.application._start_inputs import prepare_inputs
from skm.modules.execution.application.loaders import (
    derive_synthetic_task_work_policy,
    find_default_work_policy,
    find_task_work_policy,
    load_effective_bundle,
    require_default_work_policy,
    require_task_work_policy,
)
from skm.modules.execution.domain.acceptance import AcceptanceBasis, AcceptanceDecision
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
from skm.modules.execution.domain.ids import AcceptanceDecisionId, CheckExecutionId, ReviewId
from skm.modules.execution.domain.output import OutputSource
from skm.modules.execution.domain.readiness import READINESS_VALIDATOR_VERSION, canonical_digest
from skm.modules.execution.domain.review import (
    Freshness,
    Review,
    ReviewClearance,
    ReviewerKind,
    ReviewState,
    Verdict,
)
from skm.modules.execution.domain.run import RunKind, RunStatus
from skm.modules.execution.domain.stage_record import StageState
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.domain.task import TaskKind, TaskOrigin, TaskStatus
from skm.modules.execution.domain.work_policy import Intensity
from skm.modules.execution.generated.queries import GetAttempt, GetReadinessReport, GetRun, GetTask
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    BudgetRepository,
    BundleRepository,
    CheckRepository,
    EvidenceBindingRepository,
    ReadinessRepository,
    ReconfigurationRecord,
    ReviewRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.runtimes.public import SubagentUsage, UsageReport, UsageStatus
from unit.execution.application._support import context

from .event_helpers import make_readiness, seed_group_review_task, seed_service_review_runs
from .harness import ask
from .seed_helpers import (
    DIGEST_A,
    DIGEST_B,
    make_work_policies,
    record_run_event,
    seed_attempt,
    seed_bundle,
    seed_output,
    seed_run,
    seed_stage,
    seed_step,
    seed_task,
)

if TYPE_CHECKING:
    from contracts.context.harness import MutableBuiltinPacks

    from .harness import ExecSide


def test_latest_run_outcome_filters_ties_and_excludes_service_plans(exec_side: ExecSide) -> None:
    t0 = exec_side.clock.now()
    with exec_side.uow(readonly=True) as uow:
        assert execution.latest_run_outcome(uow, exec_side.proj) is None
        assert execution.latest_run_outcome(uow, exec_side.proj, exec_side.plan1) is None
        uow.rollback()

    raw_ids = sorted([exec_side.new_id(), exec_side.new_id()])
    id_lo, id_hi = RunId(raw_ids[0]), RunId(raw_ids[1])
    with exec_side.uow() as uow:
        seed_run(exec_side, uow, run_id=id_lo, plan_id=exec_side.plan1, rev_id=exec_side.rev1, created_at=t0)
        seed_run(exec_side, uow, run_id=id_hi, plan_id=exec_side.plan1, rev_id=exec_side.rev1, created_at=t0)
        seed_task(exec_side, uow, id_hi, kind=TaskKind.UNIT, display_key="P1.1/U1", status=TaskStatus.READY)
        uow.commit()

    with exec_side.uow(readonly=True) as uow:
        tie_out = execution.latest_run_outcome(uow, exec_side.proj, exec_side.plan1)
        assert tie_out is not None
        assert tie_out["run_id"] == str(id_hi)
        assert (
            execution.latest_run_outcome(uow, exec_side.proj, exec_side.plan1, revision_id=exec_side.rev2)
            is None
        )
        assert (
            execution.latest_run_outcome(uow, exec_side.proj, exec_side.plan2, revision_id=exec_side.rev1)
            is None
        )
        uow.rollback()

    with exec_side.uow() as uow:
        run_r2 = seed_run(
            exec_side,
            uow,
            plan_id=exec_side.plan1,
            rev_id=exec_side.rev2,
            revision_no=2,
            status=RunStatus.SUCCEEDED,
            created_at=t0 + timedelta(seconds=10),
        )
        seed_task(
            exec_side,
            uow,
            run_r2.id,
            kind=TaskKind.UNIT,
            spec_entity_id=UNIT_ID,
            display_key="P1.1/U1",
            status=TaskStatus.ACCEPTED,
            position=0,
        )
        seed_task(
            exec_side,
            uow,
            run_r2.id,
            kind=TaskKind.ITEM,
            spec_entity_id=EntityId(UUID(ITEM_ID)),
            display_key="P1.1",
            status=TaskStatus.EXECUTING,
            position=1,
        )
        seed_task(
            exec_side,
            uow,
            run_r2.id,
            kind=TaskKind.PLAN_ACCEPTANCE,
            spec_entity_id=None,
            display_key="PLAN#accept",
            status=TaskStatus.READY,
            position=2,
        )
        run_p2 = seed_run(
            exec_side,
            uow,
            plan_id=exec_side.plan2,
            rev_id=exec_side.rev_p2,
            created_at=t0 + timedelta(seconds=20),
        )
        rep = make_readiness(exec_side, plan_id=exec_side.plan1, rev_id=exec_side.rev2)
        uow.repo(ReadinessRepository).add(rep)
        seed_run(
            exec_side,
            uow,
            plan_id=exec_side.plan1,
            rev_id=exec_side.rev2,
            kind=RunKind.READINESS_AUDIT,
            audited_report_id=rep.id,
            created_at=t0 + timedelta(seconds=40),
        )
        svc_plan_id = seed_service_review_runs(exec_side, uow, 50)
        uow.commit()

    with exec_side.uow(readonly=True) as uow:
        pinned_r1 = execution.latest_run_outcome(
            uow, exec_side.proj, exec_side.plan1, revision_id=exec_side.rev1
        )
        assert pinned_r1 is not None
        assert pinned_r1["run_id"] == str(id_hi)
        assert pinned_r1["revision_id"] == str(exec_side.rev1)

        out_plan1 = execution.latest_run_outcome(uow, exec_side.proj, exec_side.plan1)
        assert out_plan1 == {
            "run_id": str(run_r2.id),
            "project_id": str(exec_side.proj),
            "plan_id": str(exec_side.plan1),
            "revision_id": str(exec_side.rev2),
            "revision_no": 2,
            "status": "succeeded",
            "items": {"P1.1/U1": "accepted", "P1.1": "executing"},
            "counts": {"accepted": 1, "executing": 1, "ready": 1},
        }

        out_proj = execution.latest_run_outcome(uow, exec_side.proj)
        assert out_proj is not None
        assert out_proj["run_id"] == str(run_p2.id)
        assert execution.latest_run_outcome(uow, exec_side.proj, svc_plan_id) is None
        uow.rollback()


def test_public_facades_summary_report_data_and_learning_activity(exec_side: ExecSide) -> None:
    manifest_id = exec_side.make_final_manifest()
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow, status=RunStatus.SUCCEEDED)
        seed_bundle(exec_side, uow, run.id)
        t_u1 = seed_task(exec_side, uow, run.id, display_key="P1.1/U1", position=0)
        t_cf = seed_task(
            exec_side, uow, run.id, display_key="P1.1/U2", status=TaskStatus.ACCEPTED, position=1
        )
        att = seed_attempt(exec_side, uow, run.id, t_u1.id)
        stg = seed_stage(exec_side, uow, att, state=StageState.COMPLETED)
        step = seed_step(exec_side, uow, att, stg, manifest_id=manifest_id)
        usage = UsageReport(
            input_tokens=120,
            output_tokens=30,
            cache_read_tokens=0,
            cache_write_tokens=0,
            reasoning_tokens=10,
            cost_usd_micros=450,
            status=UsageStatus.REPORTED,
            source="provider",
            subagents=SubagentUsage(used=False, disclosed=True),
        )
        done_step = replace(step, state=StepState.SUCCEEDED, usage=usage, finished_at=exec_side.clock.now())
        uow.repo(StepRepository).save(done_step)
        out = seed_output(exec_side, uow, att, step_id=step.id, source=OutputSource.EXECUTOR)
        done_att = replace(
            att,
            state=AttemptState.COMPLETED,
            current_output_id=out.id,
            finished_at=exec_side.clock.now(),
            end_reason="ACCEPTED",
        )
        uow.repo(AttemptRepository).save(done_att, expected_version=1)
        acc_task = replace(
            t_u1,
            status=TaskStatus.ACCEPTED,
            current_attempt_id=att.id,
            accepted_attempt_id=att.id,
            accepted_output_id=out.id,
            attempt_count=1,
            row_version=2,
        )
        uow.repo(TaskRepository).save(acc_task, expected_version=1)

        chk = CheckExecution(
            id=CheckExecutionId(exec_side.new_id()),
            workspace_id=exec_side.ws,
            run_id=run.id,
            task_id=t_u1.id,
            attempt_id=att.id,
            output_id=out.id,
            check_spec_id=EntityId(UUID(CHK_ID)),
            check_key="pytest",
            kind=CheckKind.COMMAND,
            required=True,
            state=CheckState.PASSED,
            exit_code=0,
            summary="1 passed",
            error_code=None,
            reused_from_id=None,
            fingerprint=DIGEST_A,
            started_at=exec_side.clock.now(),
            finished_at=exec_side.clock.now(),
            round_no=1,
        )
        uow.repo(CheckRepository).add_many((chk,))
        uow.repo(EvidenceBindingRepository).bind(
            "check_execution", UUID(str(chk.id)), (exec_side.fv1,), BindingRole.EVIDENCE
        )

        rev = Review(
            id=ReviewId(exec_side.new_id()),
            workspace_id=exec_side.ws,
            run_id=run.id,
            task_id=t_u1.id,
            attempt_id=att.id,
            output_id=out.id,
            round_no=1,
            reviewer_kind=ReviewerKind.HUMAN,
            reviewer_ref={"principal_id": str(exec_side.owner.principal_id)},
            profile_key="reviewer",
            profile_version_id=exec_side.workflow_rv_id,
            audit_scope="full",
            state=ReviewState.COMPLETED,
            verdict=Verdict.GREEN,
            freshness=Freshness.FRESH,
            base_output_id=None,
            residual_risk="low",
            completed_at=exec_side.clock.now(),
        )
        uow.repo(ReviewRepository).add(rev)
        uow.repo(EvidenceBindingRepository).bind(
            "review", UUID(str(rev.id)), (exec_side.fv2,), BindingRole.REPORT
        )

        dec = AcceptanceDecision(
            id=AcceptanceDecisionId(exec_side.new_id()),
            workspace_id=exec_side.ws,
            run_id=run.id,
            task_id=t_u1.id,
            attempt_id=att.id,
            output_id=out.id,
            decision="accepted",
            actor_id=exec_side.owner.principal_id,
            basis=AcceptanceBasis(ReviewClearance.GREEN, (chk.id,), rev.id, (), (), False, None, None, ()),
            decided_at=exec_side.clock.now(),
        )
        uow.repo(AcceptanceRepository).add_decision(dec)
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    exec_side.new_id(),
                    run.id,
                    "run",
                    None,
                    BudgetDimension.USD,
                    Decimal(10000),
                    Decimal(450),
                    Decimal(0),
                    1,
                ),
                BudgetAccount(
                    exec_side.new_id(),
                    run.id,
                    "run",
                    None,
                    BudgetDimension.TOKENS,
                    Decimal(100000),
                    Decimal(150),
                    Decimal(0),
                    1,
                ),
            )
        )
        record_run_event(
            exec_side,
            uow,
            run.id,
            "run-started",
            {
                "workspace_id": str(exec_side.ws),
                "project_id": str(exec_side.proj),
                "run_id": str(run.id),
                "task_count": 2,
                "ready_count": 2,
                "bundle_digest": DIGEST_A,
                "review_grouping": {"mode": "none"},
            },
        )
        uow.commit()

    attempt_view = ask(exec_side.client, GetAttempt(attempt_id=att.id)).to_json()
    assert {
        section: [(row["output_id"], row["evidence_refs"]) for row in attempt_view[section]]
        for section in ("checks", "reviews")
    } == {
        "checks": [(str(out.id), [{"file_version_id": str(exec_side.fv1), "role": "evidence"}])],
        "reviews": [(str(out.id), [{"file_version_id": str(exec_side.fv2), "role": "report"}])],
    }

    with exec_side.uow(readonly=True) as uow:
        r_sum = execution.get_run_summary(uow, run.id)
        assert r_sum["tasks_total"] == 2
        assert r_sum["tasks_accepted"] == 2
        assert r_sum["work_policy_default"] is not None

        a_sum = execution.get_attempt_summary(uow, att.id)
        assert a_sum["current_output_id"] == str(out.id)
        assert a_sum["latest_tree_digest"] == DIGEST_A

        rep_data = execution.get_run_report_data(uow, run.id)
        assert rep_data["usage"] == {"cost_usd_micros": 450, "tokens_spent": 150, "unmetered": False}
        tasks_list = cast("list[JsonObject]", rep_data["tasks"])
        u1_rep = next(item for item in tasks_list if item["task_id"] == str(t_u1.id))
        chk_items = cast("list[JsonObject]", u1_rep["checks"])
        rev_items = cast("list[JsonObject]", u1_rep["reviews"])
        assert chk_items[0]["evidence_file_version_ids"] == [str(exec_side.fv1)]
        assert rev_items[0]["evidence_file_version_ids"] == [str(exec_side.fv2)]
        assert len(cast("list[object]", rep_data["timeline"])) == 1

        act = execution.get_attempt_activity(uow, att.id)
        assert act["accepted"] is True
        assert act["outcome"] == "SUCCESS"
        assert act["activity_complete"] is True
        assert act["exposure_coverage"] == "complete"
        assert act["changed_paths"] == ["src/target.py"]
        assert act["usage"] == {
            "status": "reported",
            "input_tokens": 120,
            "output_tokens": 30,
            "cost_usd_micros": 450,
        }

        learned = execution.list_task_attempts_for_learning(uow, t_u1.id)
        assert len(learned) == 1
        assert learned[0]["attempt_id"] == str(att.id)
        assert execution.list_task_attempts_for_learning(uow, t_cf.id) == ()
        uow.rollback()


def install_readiness_workflow(exec_side: ExecSide) -> None:
    files = {f.path: f.content.decode() for f in core_pack("1.1.0").files}
    files["workflows/readiness-probe.toml"] = """schema = "urn:skm:execution:workflow:v1"
id = "readiness-probe"
version = "1.0.0"
applies_to = ["code"]
[[stage]]
id = "prepare"
type = "prepare_environment"
[[stage]]
id = "execute"
type = "agent_step"
role = "executor"
"""
    builtin = cast("MutableBuiltinPacks", exec_side.app.gateways.get(BuiltinPacks))
    builtin.current = (pack_payload("core", "1.1.0", files=files),)
    exec_side.client.dispatch(SyncBuiltinPacks())


def test_work_policy_persistence_redaction_and_synthetic_derivation(exec_side: ExecSide) -> None:
    install_readiness_workflow(exec_side)
    sr: JsonObject = {
        "overrides": {"budgets.task.max_attempts": 2, "execution.workflow.profile": "readiness-probe"},
        "selection": None,
    }
    fresh_rep = make_readiness(exec_side, rev_id=exec_side.rev2, start_request=sr)
    hist_rep = make_readiness(
        exec_side, rev_id=exec_side.rev1, work_policies_present=False, start_request=None
    )
    with exec_side.uow() as uow:
        prepared = prepare_inputs(
            uow,
            context(exec_side, uow),
            exec_side.plan1,
            exec_side.rev2,
            sr["overrides"],
            None,
            read_only=True,
        )
        fresh_rep = replace(
            fresh_rep,
            validator_version=READINESS_VALIDATOR_VERSION,
            inputs=prepared.inputs,
            inputs_digest=canonical_digest(asdict(prepared.inputs)),
            work_policies=prepared.policies,
        )
        uow.repo(ReadinessRepository).add(fresh_rep)
        uow.repo(ReadinessRepository).add(hist_rep)
        uow.commit()

    owner_view = ask(exec_side.client, GetReadinessReport(revision_id=exec_side.rev2)).to_json()
    assert owner_view["effective_status"] == "ready", owner_view["stale_parts"]
    assert owner_view["stale_parts"] == []
    owner_sr = cast("JsonObject", cast("JsonObject", owner_view["report"])["start_request"])
    assert owner_sr["overrides"] == sr["overrides"]

    run_read_only = exec_side.restricted_client(("run.read",))
    redacted_view = ask(run_read_only, GetReadinessReport(revision_id=exec_side.rev2)).to_json()
    red_sr = cast("JsonObject", cast("JsonObject", redacted_view["report"])["start_request"])
    assert red_sr["overrides"] == {
        "budgets.task.max_attempts": "[REDACTED]",
        "execution.workflow.profile": "[REDACTED]",
    }

    stale_view = ask(exec_side.client, GetReadinessReport(report_id=UUID(str(hist_rep.id)))).to_json()
    assert stale_view["effective_status"] == "stale"
    assert set(cast("list[str]", stale_view["stale_parts"])) == {"work_policies", "start_request"}

    with exec_side.uow() as uow:
        run_wp = seed_run(exec_side, uow)
        wp_map = make_work_policies("P1.1/U1", executor_intensity=Intensity.HEAVY)
        seed_bundle(exec_side, uow, run_wp.id, work_policies=wp_map)
        t_u1 = seed_task(exec_side, uow, run_wp.id, display_key="P1.1/U1", position=0)
        t_fu = seed_task(
            exec_side,
            uow,
            run_wp.id,
            kind=TaskKind.FOLLOWUP,
            spec_entity_id=None,
            display_key="FU-1",
            origin=TaskOrigin(source_task_id=t_u1.id, finding_ids=(), reason="FOLLOWUP"),
            position=1,
        )
        t_int = seed_task(
            exec_side,
            uow,
            run_wp.id,
            kind=TaskKind.INTEGRATION,
            spec_entity_id=None,
            display_key="INT-1",
            origin=TaskOrigin(t_u1.id, (), "INTEGRATION"),
            position=2,
        )
        t_gr = seed_group_review_task(exec_side, uow, run_wp.id, t_u1.id)

        rec_early_ts = ReconfigurationRecord(
            id=UUID("01900000-0000-7000-8000-000000000999"),
            run_id=run_wp.id,
            changes={"budgets.task.max_attempts": {"old": 5, "new": 7}},
            changed_by=exec_side.owner.principal_id,
            reason="raise attempts second in stream",
            changed_at=exec_side.clock.now(),
        )
        rec_late_ts = ReconfigurationRecord(
            id=UUID("01900000-0000-7000-8000-000000000111"),
            run_id=run_wp.id,
            changes={"budgets.task.max_attempts": {"old": 3, "new": 5}},
            changed_by=exec_side.owner.principal_id,
            reason="raise attempts first in stream",
            changed_at=exec_side.clock.now() + timedelta(seconds=30),
        )
        b_repo = uow.repo(BundleRepository)
        b_repo.add_reconfiguration(rec_early_ts)
        b_repo.add_reconfiguration(rec_late_ts)
        for rec in (rec_late_ts, rec_early_ts):
            record_run_event(
                exec_side,
                uow,
                run_wp.id,
                "run-reconfigured",
                {
                    "workspace_id": str(exec_side.ws),
                    "project_id": str(exec_side.proj),
                    "run_id": str(run_wp.id),
                    "reconfiguration_id": str(rec.id),
                    "changes": dict(rec.changes),
                    "by": str(exec_side.owner.principal_id),
                    "reason": rec.reason,
                    "effective_config_digest": DIGEST_B,
                    "effective_after": "next_stage",
                },
            )

        run_legacy = seed_run(exec_side, uow)
        seed_bundle(exec_side, uow, run_legacy.id, omit_work_policies=True)
        t_legacy = seed_task(exec_side, uow, run_legacy.id, display_key="P1.1/U1", position=0)
        uow.commit()

    run_dto = ask(exec_side.client, GetRun(run_id=UUID(str(run_wp.id)))).to_json()
    assert run_dto["work_policy_default"] is not None
    fu_dto = ask(exec_side.client, GetTask(task_id=UUID(str(t_fu.id)))).to_json()
    fu_wp = cast("JsonObject", fu_dto["work_policy"])
    fu_roles = cast("JsonObject", cast("JsonObject", fu_wp["effective"])["role_intensity"])
    assert fu_roles["executor"] == "heavy"
    assert ask(exec_side.client, GetTask(task_id=UUID(str(t_int.id)))).to_json()["work_policy"]
    assert ask(exec_side.client, GetTask(task_id=UUID(str(t_gr.id)))).to_json()["work_policy"]

    with exec_side.uow(readonly=True) as uow:
        loaded = load_effective_bundle(uow, run_wp.id)
        assert loaded.budget_limits[("task", BudgetDimension.ATTEMPTS)] == Decimal(7)
        assert loaded.reconfiguration_ids == (rec_early_ts.id,)
        assert loaded.effective_config_digest != DIGEST_A

        assert find_default_work_policy(uow, run_legacy.id) is None
        assert find_task_work_policy(uow, t_legacy.id) is None
        for fn in (
            lambda: require_default_work_policy(uow, run_legacy.id),
            lambda: require_task_work_policy(uow, t_legacy.id),
            lambda: derive_synthetic_task_work_policy(uow, run_legacy.id, kind=TaskKind.INTEGRATION),
        ):
            with pytest.raises(PreconditionFailed) as exc_info:
                fn()
            assert exc_info.value.code is ErrorCode.READINESS_REQUIRED
            assert exc_info.value.details["reason"] == "work_policy_missing"
        uow.rollback()
