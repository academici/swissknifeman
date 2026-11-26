"""Execution protocol regressions against the real bus on memory and PostgreSQL."""

import json
from dataclasses import asdict, replace
from decimal import Decimal

import psycopg

from contracts.execution.event_helpers import emit_core_history
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.seed_helpers import (
    DIGEST_B,
    record_run_event,
    seed_attempt,
    seed_bundle,
    seed_run,
    seed_stage,
    seed_step,
    seed_task,
)
from fixtures.execution.harness import _pack
from integration.api.test_planning import API, ok, problem
from integration.api.test_planning import http as http
from skm.kernel.ids import TaskId
from skm.modules.access.generated.commands import RevokeToken
from skm.modules.access.public import CreateToken
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.budget import BudgetAccount, BudgetDimension
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.ports import BudgetRepository, BundleRepository, StepRepository
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.runtimes.public import SubagentUsage, UsageReport, UsageStatus
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def test_revision_scope_and_selection_on_readiness_and_start(http, exec_side):
    side = exec_side
    path = f"{API}/plans/{side.plan1}"
    selection = {"task_keys": ["P1.1/U1"], "phases": ["P1"], "stop_after": "P1.1/U1"}
    problem(
        http.post(f"{path}/revisions/{side.rev_p2}/readiness", json={"selection": selection}),
        404,
        "NOT_FOUND",
    )
    body = {
        "revision_id": str(side.rev_p2),
        "readiness_report_id": None,
        "overrides": {},
        "reason": "start",
        "selection": selection,
    }
    problem(http.post(path + "/runs", json=body), 404, "NOT_FOUND")
    problem(http.post(path + "/runs", json={**body, "settings": {}}), 422, "SCHEMA_INVALID")

    side.app.gateways.get(BuiltinPacks).current = (_pack(),)
    side.client.dispatch(SyncBuiltinPacks())
    side.client.dispatch(
        SetValue(
            scope=SetValueDefsScopeRef(level="instance"),
            key="execution.readiness.required",
            value=False,
            confirmed=True,
        ),
        idempotency_key="surface-readiness-policy",
    )
    overrides = {"budgets.task.warn_tokens": 1250, "budgets.task.max_tokens": 4500}
    report = ok(
        http.post(
            f"{path}/revisions/{side.rev2}/readiness",
            json={
                "selection": selection,
                "overrides": overrides,
            },
        ),
        201,
    )
    assert report["estimate"]["token_budget"] == {
        "task_warn_tokens": 1250,
        "task_max_tokens": 4500,
        "run_max_tokens": 0,
    }
    stored = ok(http.get(f"{API}/readiness-reports/{report['report_id']}"))
    assert stored["report"]["start_request"]["selection"] == selection
    started = ok(
        http.post(path + "/runs", json={**body, "revision_id": str(side.rev2), "overrides": overrides}), 201
    )
    frozen = ok(http.get(f"{API}/runs/{started['run_id']}"))["selection"]
    for field, value in selection.items():
        assert frozen[field] == value
    detail = ok(http.get(f"{API}/execution/detail", params={"run_id": started["run_id"]}))
    assert (detail["workspace_id"], detail["project_id"], detail["revision_id"]) == (
        str(side.ws),
        str(side.proj),
        str(side.rev2),
    )
    assert detail["workflow"]["key"] == "reviewed-development"
    assert detail["workflow"]["version"]
    assert detail["workflow"]["resource_version_id"]


def test_manual_pending_and_waiting_remain_readable(http, exec_side):
    side = exec_side
    task_id = TaskId(side.new_id())
    reason = blocking_reason(
        BlockingCode.WAITING_MANUAL_CHECK,
        task_id=task_id,
        refs={"check_execution_id": str(side.new_id()), "check_key": "P1.1:V1"},
        now=side.clock.now(),
        message="Await the manual check",
    )
    with side.uow() as uow:
        run = seed_run(side, uow, status=RunStatus.WAITING)
        seed_bundle(side, uow, run.id)
        task = seed_task(
            side, uow, run.id, task_id=task_id, status=TaskStatus.MANUAL_PENDING, blocking_reason=reason
        )
        attempt = seed_attempt(side, uow, run.id, task.id)
        uow.commit()
    view = http.get(f"{API}/runs/{run.id}")
    assert ok(view)["status"] == "waiting"
    assert view.headers["ETag"] == 'W/"v1"'
    view = http.get(f"{API}/tasks/{task.id}")
    assert ok(view)["status"] == "manual_pending"
    assert view.headers["ETag"] == 'W/"v1"'
    assert ok(http.get(f"{API}/attempts/{attempt.id}"))["attempt_id"] == str(attempt.id)
    for key, identifier in (("task_id", task.id), ("attempt_id", attempt.id)):
        result = http.get(f"{API}/execution/detail", params={key: str(identifier)})
        detail = ok(result)
        assert detail["run_id"] == str(run.id)
        assert detail["workspace_id"] == str(side.ws)
        assert result.headers["SKM-Events-Cursor"].isdigit()
    assert ok(http.get(f"{API}/execution/detail", params={"task_id": str(task.id)}))["restart"] == {
        "eligible": True,
        "requires_attempts_override": False,
    }
    problem(
        http.get(f"{API}/execution/detail", params={"run_id": str(run.id), "task_id": str(task.id)}),
        422,
        "SCHEMA_INVALID",
    )
    tasks = ok(http.get(f"{API}/runs/{run.id}/tasks", params={"statuses": "manual_pending", "kinds": "unit"}))
    assert [row["task_id"] for row in tasks["tasks"]] == [str(task.id)]
    assert (
        ok(http.get(API + "/inbox", params={"scope": f"project:{side.proj}", "state": "open"}))["items"] == []
    )


def test_reconfigure_conflict_keeps_frozen_config_and_budget(http, exec_side):
    side = exec_side
    with side.uow() as uow:
        run = seed_run(side, uow, status=RunStatus.PAUSED)
        seed_bundle(side, uow, run.id)
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id)
        seed_stage(side, uow, attempt)
        account = BudgetAccount(
            side.new_id(),
            run.id,
            "task",
            task.id,
            BudgetDimension.ATTEMPTS,
            Decimal(5),
            Decimal(1),
            Decimal(0),
            1,
        )
        uow.repo(BudgetRepository).add_accounts((account,))
        uow.commit()

    def snapshot():
        with side.uow(readonly=True) as uow:
            bundles = uow.repo(BundleRepository)
            return (
                bundles.get(run.id),
                bundles.reconfigurations(run.id),
                uow.repo(BudgetRepository).accounts_for(run.id, task.id, BudgetDimension.ATTEMPTS),
            )

    before = snapshot()
    checkpoint_view = ok(http.get(f"{API}/execution/detail", params={"run_id": str(run.id)}))["checkpoint"]
    assert checkpoint_view["unfinished_stage"] is True
    assert checkpoint_view["open_recovery"] is checkpoint_view["leased_claim"] is False
    assert {entry["key"] for entry in checkpoint_view["changes"]} >= {"budgets.task.max_attempts"}
    path = f"{API}/runs/{run.id}/reconfigure"
    body = {"changes": {"budgets.task.max_attempts": 2}, "reason": "reduce ceiling"}
    problem(http.post(path, json=body), 428, "PRECONDITION_REQUIRED")
    problem(http.post(path, headers={"If-Match": 'W/"v2"'}, json=body), 409, "VERSION_CONFLICT")
    checkpoint = http.post(path, headers={"If-Match": 'W/"v1"'}, json=body)
    problem(checkpoint, 409, "INVALID_TRANSITION")
    assert checkpoint.json()["details"]["reason"] == "reconfiguration_checkpoint_required"
    assert snapshot() == before
    assert http.get(f"{API}/runs/{run.id}").headers["ETag"] == 'W/"v1"'


def test_budget_warning_uses_frozen_threshold_and_reported_fresh_tokens(http, exec_side):
    side = exec_side
    manifest = side.make_final_manifest()
    with side.uow() as uow:
        run = seed_run(side, uow)
        seed_bundle(side, uow, run.id, config_snapshot={"values": {"budgets.task.warn_tokens": 100}})
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id)
        stage = seed_stage(side, uow, attempt)
        step = seed_step(side, uow, attempt, stage, manifest_id=manifest)
        seed_step(side, uow, attempt, stage, manifest_id=manifest, seq=2, state=StepState.SUCCEEDED)
        usage = UsageReport(
            input_tokens=90,
            output_tokens=30,
            cache_read_tokens=900,
            cache_write_tokens=10,
            reasoning_tokens=0,
            cost_usd_micros=0,
            status=UsageStatus.REPORTED,
            source="provider",
            subagents=SubagentUsage(used=False, disclosed=True),
        )
        uow.repo(StepRepository).save(
            replace(step, state=StepState.SUCCEEDED, usage=usage, finished_at=side.clock.now())
        )
        uow.repo(BudgetRepository).add_accounts(
            (
                BudgetAccount(
                    side.new_id(),
                    run.id,
                    "task",
                    task.id,
                    BudgetDimension.TOKENS,
                    Decimal(400),
                    Decimal(200),
                    Decimal(0),
                    1,
                ),
            )
        )
        uow.commit()
    view = ok(http.get(f"{API}/runs/{run.id}/budget"))
    assert view["unknown_usage_steps"] == 1
    (account,) = view["accounts"]
    assert account["limit"] == "400"
    assert account["warn_tokens"] == 100
    assert account["actual_tokens"] is None
    assert account["soft_overrun"] == {"measured_tokens": "130", "expected_tokens": 100, "partial": True}


def test_history_cutoff_reauthorization_and_private_payloads(http, exec_side):
    side = exec_side
    private = "confidential-step-output-42"
    manifest = side.make_final_manifest()
    with side.uow() as uow:
        run = seed_run(side, uow)
        other = seed_run(side, uow)
        seed_bundle(side, uow, run.id)
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id)
        stage = seed_stage(side, uow, attempt)
        step = seed_step(
            side,
            uow,
            attempt,
            stage,
            manifest_id=manifest,
            result={"stdout": private},
            raw_fv_id=side.fv1,
            state=StepState.SUCCEEDED,
        )
        emit_core_history(side, uow, run.id, task.id, attempt.id, stage.id, step.id, manifest)
        uow.commit()

    token = side.client.dispatch(
        CreateToken(
            name="history-reader",
            principal_id=side.viewer.principal_id,
            scope_id=side.ws,
            permissions=("run.read",),
        )
    )
    headers = {"Authorization": f"Bearer {token.secret}"}
    step_view = ok(http.get(f"{API}/steps/{step.id}", headers=headers))
    assert step_view["payload_visibility"] == "restricted"
    assert "result" not in step_view
    assert ok(http.get(f"{API}/steps/{step.id}"))["result"]["stdout"] == private
    history = f"{API}/runs/{run.id}/history"
    first = ok(http.get(history, params={"limit": 2}, headers=headers))
    cursor, cutoff = first["next_after"], first["through_seq"]
    assert cursor
    assert cutoff == 7
    with side.uow() as uow:
        record_run_event(
            side,
            uow,
            run.id,
            "run-reconfigured",
            {
                "workspace_id": str(side.ws),
                "project_id": str(side.proj),
                "run_id": str(run.id),
                "reconfiguration_id": str(side.new_id()),
                "changes": {"budgets.task.max_attempts": 2},
                "by": str(side.owner.principal_id),
                "reason": private,
                "effective_config_digest": DIGEST_B,
                "effective_after": "next_stage",
            },
        )
        uow.commit()
    head = ok(http.get(history, headers=headers))
    assert head["through_seq"] == cutoff + 1
    second = ok(http.get(history, params={"after": cursor}, headers=headers))
    assert second["through_seq"] == cutoff
    assert [row["seq"] for row in first["entries"] + second["entries"]] == list(range(1, cutoff + 1))
    assert private not in json.dumps([head, first, second, step_view])
    problem(http.get(history, params={"after": cursor}), 422, "SCHEMA_INVALID")
    problem(
        http.get(f"{API}/runs/{other.id}/history", params={"after": cursor}, headers=headers),
        422,
        "SCHEMA_INVALID",
    )
    side.client.dispatch(RevokeToken(token.token_id))
    denied = http.get(history, params={"after": cursor}, headers=headers)
    assert denied.status_code == 401
    assert private not in denied.text


def test_review_roi_http_requires_run_read(http, exec_side) -> None:
    side = exec_side
    with side.uow() as uow:
        run = seed_run(side, uow)
        uow.commit()

    path = f"{API}/runs/{run.id}/analytics/review-roi"
    allowed = side.client.dispatch(CreateToken(name="analytics-reader", permissions=("run.read",)))
    data = ok(http.get(path, headers={"Authorization": f"Bearer {allowed.secret}"}))
    assert data["run_id"] == str(run.id)
    assert data["finished_reviewer_steps"] == 0
    assert data["observed_cost_usd"] is None
    denied = side.client.dispatch(CreateToken(name="analytics-denied", permissions=("config.read",)))
    problem(http.get(path, headers={"Authorization": f"Bearer {denied.secret}"}), 403, "FORBIDDEN")


def test_rejected_write_keeps_audit_free_of_command_body(http, exec_side):
    side = exec_side
    with side.uow() as uow:
        run = seed_run(side, uow)
        uow.commit()
    token = side.client.dispatch(CreateToken(name="audit-reader", permissions=("run.read",)))
    sentinel = "private-operator-message-87"
    request_id = f"surface-denial-{side.new_id()}"
    failure = http.post(
        f"{API}/runs/{run.id}/pause",
        headers={"Authorization": f"Bearer {token.secret}", "X-Request-Id": request_id},
        json={"reason": sentinel},
    )
    problem(failure, 403, "FORBIDDEN")
    assert sentinel not in failure.text
    if side.dsn:
        with psycopg.connect(side.dsn) as conn:
            records = conn.execute(
                "SELECT action, decision, target FROM skm_core.audit_records WHERE request_id=%s",
                (request_id,),
            ).fetchall()
    else:
        records = [
            asdict(row)
            for row in side.app.uow_factory._backend.committed.core.audit
            if row.request_id == request_id
        ]
    assert records
    audit = json.dumps(records, default=str)
    assert "execution.pause_run" in audit
    assert "denied" in audit
    assert sentinel not in audit


def test_live_control_http_binds_task_path_and_etag(http, exec_side) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        uow.commit()
    path = f"{API}/runs/{run.id}/tasks/{task.id}"
    view = ok(http.get(path + "/live-control"))
    assert view["assignment_id"] is None
    assert view["pending_controls"] == []
    etag = f'W/"v{view["row_version"]}"'
    request = {
        "expected_assignment_id": None,
        "expected_fencing_token": None,
        "expected_step_id": None,
        "reason": "Update next step",
        "instructions": "Use the local fixture.",
    }

    changed = http.post(path + "/steer", json=request, headers={"If-Match": etag})
    assert ok(changed)["effective"] == "next_step"
    assert changed.headers["ETag"] == f'W/"v{view["row_version"] + 1}"'
    assert ok(http.get(path + "/live-control"))["pending_controls"] == ["steer_task"]
    problem(http.post(path + "/steer", json=request, headers={"If-Match": etag}), 409, "VERSION_CONFLICT")
