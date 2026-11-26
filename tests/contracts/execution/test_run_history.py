"""Dual-backend contract tests for execution.get_run_history and step observation guards (ench5)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, cast
from uuid import UUID

import psycopg
import pytest

from contracts.context.harness import UNIT_ID
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageState
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.domain.task import TaskKind, TaskStatus
from skm.modules.execution.generated.queries import GetRunHistory
from skm.modules.execution.ports import (
    AttemptRepository,
    ExecutionQueries,
    RunRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)

from .event_helpers import emit_core_history, history_cause, make_route_snapshot, make_runtime_obs
from .harness import ask
from .seed_helpers import (
    DIGEST_A,
    DIGEST_B,
    record_run_event,
    seed_attempt,
    seed_bundle,
    seed_run,
    seed_stage,
    seed_step,
    seed_task,
)

if TYPE_CHECKING:
    from .harness import ExecSide

HISTORY_SCHEMA_URN = "urn:skm:execution:execution-history:v1"


def _items(page: JsonObject, key: str) -> list[JsonObject]:
    return [
        item
        for entry in cast("list[JsonObject]", page["entries"])
        for item in cast("list[JsonObject]", entry[key])
    ]


def _reasons(page: JsonObject) -> set[str]:
    return {
        reason
        for entry in cast("list[JsonObject]", page["entries"])
        for reason in cast("list[str]", entry["reason_codes"])
    }


def test_get_run_history_event_purity_under_mutable_row_updates_and_late_events(
    exec_side: ExecSide,
) -> None:
    reg = exec_side.app.schemas
    manifest_id = exec_side.make_final_manifest()
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        seed_bundle(exec_side, uow, run.id)
        task = seed_task(exec_side, uow, run.id)
        att = seed_attempt(exec_side, uow, run.id, task.id)
        stg = seed_stage(exec_side, uow, att)
        step = seed_step(
            exec_side,
            uow,
            att,
            stg,
            manifest_id=manifest_id,
            state=StepState.SUCCEEDED,
            result={"secret_prompt": "Artifact 1", "stdout": "raw stdout leak"},
            route_snapshot=make_route_snapshot(exec_side),
        )
        emit_core_history(
            exec_side,
            uow,
            run.id,
            task.id,
            UUID(str(att.id)),
            UUID(str(stg.id)),
            step.id,
            UUID(str(manifest_id)),
        )
        uow.commit()

    baseline = ask(exec_side.client, GetRunHistory(run_id=UUID(str(run.id)))).to_json()
    reg.require_valid(HISTORY_SCHEMA_URN, baseline)
    assert baseline["through_seq"] == 7
    serialized = json.dumps(baseline)
    for forbidden in ("Artifact 1", "raw stdout leak", "local_locator", "secret://", "/tmp/"):  # noqa: S108
        assert forbidden not in serialized

    p1 = ask(exec_side.client, GetRunHistory(run_id=UUID(str(run.id)), limit=3)).to_json()
    reg.require_valid(HISTORY_SCHEMA_URN, p1)
    assert p1["through_seq"] == 7
    cursor_1 = cast("str", p1["next_after"])
    assert isinstance(cursor_1, str)

    with exec_side.uow() as uow:
        mut_run = replace(
            run,
            status=RunStatus.CANCELLED,
            stop_code=None,
            finished_at=exec_side.clock.now(),
            row_version=2,
        )
        uow.repo(RunRepository).save(mut_run, expected_version=1)
        uow.repo(TaskRepository).save(
            replace(task, status=TaskStatus.FAILED, row_version=2), expected_version=1
        )
        mut_att = replace(
            att, state=AttemptState.ABANDONED, finished_at=exec_side.clock.now(), end_reason="FAILED"
        )
        uow.repo(AttemptRepository).save(mut_att, expected_version=1)
        mut_stg = replace(
            stg,
            state=StageState.FAILED,
            outcome_kind=StageOutcomeKind.RUNTIME_ERROR,
            error_code="RUNTIME_CRASHED",
            finished_at=exec_side.clock.now(),
        )
        uow.repo(StageRepository).save(mut_stg)

        ws_s, pr_s, r_s = str(exec_side.ws), str(exec_side.proj), str(run.id)
        record_run_event(
            exec_side,
            uow,
            run.id,
            "run-reconfigured",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "reconfiguration_id": str(exec_side.new_id()),
                "changes": {"budgets.task.max_attempts": 5},
                "by": str(exec_side.owner.principal_id),
                "reason": "late overlay",
                "effective_config_digest": DIGEST_B,
                "effective_after": "next_stage",
            },
        )
        record_run_event(
            exec_side,
            uow,
            run.id,
            "stage-recovered",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "attempt_id": str(att.id),
                "task_id": str(task.id),
                "stage_record_id": str(stg.id),
                "recovery_record_id": str(exec_side.new_id()),
                "trigger": "worker_restart",
                "outcome": "resumed",
                "steps": [],
            },
        )
        record_run_event(
            exec_side,
            uow,
            run.id,
            "external-effect-recorded",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "effect_id": str(exec_side.new_id()),
                "kind": "git_push",
                "state": "confirmed",
                "ref": "refs/heads/main",
                "attempt_id": str(att.id),
                "stage_record_id": str(stg.id),
                "output_ids": [],
                "intent_id": None,
                "request_digest": DIGEST_A,
                "receipt_digest": DIGEST_B,
                "cause": history_cause("stage_outcome", "K9"),
            },
        )
        uow.commit()

    pinned = ask(exec_side.client, GetRunHistory(run_id=UUID(str(run.id)), through_seq=7)).to_json()
    assert pinned == baseline

    p2 = ask(exec_side.client, GetRunHistory(run_id=UUID(str(run.id)), after=cursor_1, limit=3)).to_json()
    reg.require_valid(HISTORY_SCHEMA_URN, p2)
    assert p2["through_seq"] == 7
    cursor_2 = cast("str", p2["next_after"])
    p3 = ask(exec_side.client, GetRunHistory(run_id=UUID(str(run.id)), after=cursor_2, limit=3)).to_json()
    reg.require_valid(HISTORY_SCHEMA_URN, p3)
    assert p3["through_seq"] == 7
    assert p3["next_after"] is None
    paged_seqs = [
        cast("JsonObject", e)["seq"] for page in (p1, p2, p3) for e in cast("list[object]", page["entries"])
    ]
    assert paged_seqs == [1, 2, 3, 4, 5, 6, 7]

    head = ask(exec_side.client, GetRunHistory(run_id=UUID(str(run.id)))).to_json()
    reg.require_valid(HISTORY_SCHEMA_URN, head)
    assert head["through_seq"] == 10
    node_kinds = {cast("str", cast("JsonObject", n["ref"])["kind"]) for n in _items(head, "nodes")}
    assert {"reconfiguration", "recovery", "effect"} <= node_kinds


def test_get_run_history_cursor_binding_and_foreign_task_redaction(exec_side: ExecSide) -> None:
    reg = exec_side.app.schemas
    with exec_side.uow() as uow:
        sec_run = seed_run(
            exec_side,
            uow,
            ws=exec_side.ws2,
            proj=exec_side.proj2,
            plan_id=exec_side.plan2_ws2,
            rev_id=exec_side.rev_ws2,
        )
        seed_bundle(exec_side, uow, sec_run.id)
        sec_task = seed_task(
            exec_side,
            uow,
            sec_run.id,
            ws=exec_side.ws2,
            spec_entity_id=None,
            kind=TaskKind.INTEGRATION,
            display_key="INT-1",
        )

        main_run = seed_run(exec_side, uow)
        seed_bundle(exec_side, uow, main_run.id)
        main_task = seed_task(exec_side, uow, main_run.id)
        other_run = seed_run(exec_side, uow)
        seed_bundle(exec_side, uow, other_run.id)

        ws_s, pr_s, r_s = str(exec_side.ws), str(exec_side.proj), str(main_run.id)
        record_run_event(
            exec_side,
            uow,
            main_run.id,
            "run-created",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "plan_id": str(exec_side.plan1),
                "revision_id": str(exec_side.rev1),
                "revision_no": 1,
                "kind": "plan",
                "requested_by": str(exec_side.owner.principal_id),
                "bundle_digest": DIGEST_A,
                "cause": history_cause(),
            },
        )
        record_run_event(
            exec_side,
            uow,
            main_run.id,
            "task-created",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "task_id": str(main_task.id),
                "kind": "unit",
                "revision_id": str(exec_side.rev1),
                "entity_id": str(UNIT_ID),
                "origin": {
                    "source_task_id": str(sec_task.id),
                    "finding_ids": [],
                    "reason_code": "CARRY_FORWARD",
                },
                "cause": {
                    "trigger_kind": "carry_forward",
                    "advance_rule": "K14",
                    "reason_codes": [],
                    "refs": [{"kind": "task", "id": str(sec_task.id)}],
                },
                "initial_state": "ready",
                "position": 0,
                "parent_task_id": None,
            },
        )
        record_run_event(
            exec_side,
            uow,
            main_run.id,
            "task-accepted",
            {
                "workspace_id": ws_s,
                "project_id": pr_s,
                "run_id": r_s,
                "task_id": str(main_task.id),
                "attempt_id": None,
                "output_id": None,
                "clearance": {"kind": "carry_forward", "source_task_id": str(sec_task.id)},
                "carried_forward": True,
            },
        )
        uow.commit()

    owner_p1 = ask(exec_side.client, GetRunHistory(run_id=UUID(str(main_run.id)), limit=1)).to_json()
    owner_cur = cast("str", owner_p1["next_after"])

    for bad_call in (
        lambda: ask(exec_side.viewer_client, GetRunHistory(run_id=UUID(str(main_run.id)), after=owner_cur)),
        lambda: ask(exec_side.client, GetRunHistory(run_id=UUID(str(other_run.id)), after=owner_cur)),
        lambda: ask(
            exec_side.client, GetRunHistory(run_id=UUID(str(main_run.id)), after=owner_cur, through_seq=2)
        ),
        lambda: ask(exec_side.client, GetRunHistory(run_id=UUID(str(main_run.id)), through_seq=99)),
        lambda: ask(
            exec_side.client, GetRunHistory(run_id=UUID(str(main_run.id)), after="not-valid-base64!")
        ),
    ):
        with pytest.raises(ValidationFailed) as exc_info:
            bad_call()
        assert exc_info.value.code is ErrorCode.SCHEMA_INVALID

    owner_full = ask(exec_side.client, GetRunHistory(run_id=UUID(str(main_run.id)))).to_json()
    reg.require_valid(HISTORY_SCHEMA_URN, owner_full)
    owner_edges = _items(owner_full, "edges")
    owner_reuses = [e for e in owner_edges if e["kind"] == "reuses"]
    assert len(owner_reuses) == 1
    assert owner_reuses[0]["target"] == {"kind": "task", "id": str(sec_task.id), "visibility": "unloaded"}
    assert "FOREIGN_REFERENCE_RESTRICTED" not in _reasons(owner_full)

    viewer_full = ask(exec_side.viewer_client, GetRunHistory(run_id=UUID(str(main_run.id)))).to_json()
    reg.require_valid(HISTORY_SCHEMA_URN, viewer_full)
    viewer_edges = _items(viewer_full, "edges")
    viewer_reuses = [e for e in viewer_edges if e["kind"] == "reuses"]
    assert len(viewer_reuses) == 1
    assert viewer_reuses[0]["target"] == {"kind": "task", "visibility": "foreign_opaque"}
    assert str(sec_task.id) not in json.dumps(viewer_full)
    assert "FOREIGN_REFERENCE_RESTRICTED" in _reasons(viewer_full)


def test_terminal_step_rejects_late_or_mutated_runtime_observation_without_new_event(
    exec_side: ExecSide,
) -> None:
    manifest_id = exec_side.make_final_manifest()
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        seed_bundle(exec_side, uow, run.id)
        task = seed_task(exec_side, uow, run.id)
        att = seed_attempt(exec_side, uow, run.id, task.id)
        stg = seed_stage(exec_side, uow, att)
        s_started = seed_step(
            exec_side, uow, att, stg, manifest_id=manifest_id, seq=1, state=StepState.STARTED
        )
        s_no_obs = seed_step(
            exec_side, uow, att, stg, manifest_id=manifest_id, seq=2, state=StepState.SUCCEEDED
        )
        obs_1 = make_runtime_obs(exec_side, s_started.id, observed_calls=2)
        s_done = replace(
            s_started,
            state=StepState.SUCCEEDED,
            runtime_observation=obs_1,
            finished_at=exec_side.clock.now(),
        )
        uow.repo(StepRepository).save(s_done)
        record_run_event(
            exec_side,
            uow,
            run.id,
            "step-observation-recorded",
            {
                "workspace_id": str(exec_side.ws),
                "project_id": str(exec_side.proj),
                "run_id": str(run.id),
                "task_id": str(task.id),
                "attempt_id": str(att.id),
                "stage_record_id": str(stg.id),
                "step_id": str(s_started.id),
                "observation": obs_1,
                "observation_digest": DIGEST_A,
                "cause": history_cause("observation", None),
                "route_snapshot": None,
                "role": "executor",
                "purpose": "primary",
                "seq": 1,
                "parent_step_id": None,
                "context_manifest_id": str(manifest_id),
                "binding_consistency": "unavailable",
            },
        )
        uow.commit()

    with exec_side.uow() as uow:
        late_step = replace(s_no_obs, runtime_observation=make_runtime_obs(exec_side, s_no_obs.id))
        with pytest.raises(PreconditionFailed) as late_exc:
            uow.repo(StepRepository).save(late_step)
        assert late_exc.value.code is ErrorCode.INVALID_TRANSITION

        mut_step = replace(
            s_done, runtime_observation=make_runtime_obs(exec_side, s_done.id, observed_calls=9)
        )
        with pytest.raises((PreconditionFailed, ValidationFailed)) as mut_exc:
            uow.repo(StepRepository).save(mut_step)
        assert mut_exc.value.code in {ErrorCode.FIELD_OWNED, ErrorCode.INVALID_TRANSITION}
        uow.rollback()

    if exec_side.dsn is not None:
        obs_late_raw = json.dumps(make_runtime_obs(exec_side, s_no_obs.id))
        with psycopg.connect(exec_side.dsn) as raw_conn, raw_conn.cursor() as cur:
            with pytest.raises(psycopg.Error) as pg_exc:
                cur.execute(
                    "UPDATE skm_execution.attempt_steps SET runtime_observation = %s::jsonb WHERE id = %s",
                    (obs_late_raw, UUID(str(s_no_obs.id))),
                )
            assert "observation" in str(pg_exc.value).lower() or "terminal" in str(pg_exc.value).lower()
            raw_conn.rollback()

    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(ExecutionQueries).head_run_seq(run.id) == 1
        assert uow.repo(StepRepository).get(s_done.id).runtime_observation == s_done.runtime_observation
        assert uow.repo(StepRepository).get(s_no_obs.id).runtime_observation is None
        uow.rollback()


def test_history_rebuild_after_runtime_capture_loss(exec_side: ExecSide, tmp_path) -> None:
    """A fresh transport and a fresh client see the same committed graph after local capture loss."""
    from contextlib import closing
    from shutil import rmtree

    from contracts.runtimes.conftest import build
    from fixtures.execution.protocol import client_with_uow
    from integration.mcp.test_tools import authenticate, client_for
    from security.api.harness import BASE, TestClient
    from skm.adapters.http_client.client import HttpSkmClient
    from skm.adapters.runtimes._cli_session.observation import LiveQueue
    from skm.entrypoints.api.app import create_app
    from skm.entrypoints.api.routes import MODULE_IDS
    from skm.entrypoints.api.routing import build_route_table
    from skm.modules.access.public import CreateToken, CreateTokenResult
    from skm.modules.execution.domain.ids import StepId

    side = exec_side
    streaming = LiveQueue(max_bytes=4096, max_entries=10)
    local = build(tmp_path / "local-capture", live=streaming)
    assert local.session.result().outcome == "completed"
    assert (local.writer.step_dir / "stream.jsonl").stat().st_size > 0
    assert streaming.take() is not None

    manifest = side.make_final_manifest()
    with side.uow() as uow:
        run = seed_run(side, uow)
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
            state=StepState.SUCCEEDED,
            step_id=StepId(UUID(local.writer.step_dir.name)),
        )
        emit_core_history(side, uow, run.id, task.id, attempt.id, stage.id, step.id, manifest)
        uow.commit()

    query = GetRunHistory(run_id=run.id)
    expected = ask(side.client, query).to_json()
    first_page = ask(side.client, GetRunHistory(run_id=run.id, limit=2)).to_json()
    assert expected["builder_version"] > 0
    assert _items(expected, "nodes")
    assert _items(expected, "edges")
    assert first_page["next_after"]

    rmtree(tmp_path / "local-capture")
    local.session.live = LiveQueue(max_bytes=4096, max_entries=10)
    assert local.session.live.take() is None
    assert not local.writer.step_dir.exists()
    fresh = client_with_uow(side, side.client, side.app.uow_factory)
    assert ask(fresh, query).to_json() == expected
    restarted = create_app(
        replace(side.app, bus=fresh._bus, authenticator=lambda secret: authenticate(side, secret)),
        route_table=build_route_table(MODULE_IDS),
        registry=side.app.bus._registry,
        no_background=True,
    )
    token = side.client.dispatch(CreateToken("history-restart-reader"))
    assert isinstance(token, CreateTokenResult)
    with (
        TestClient(restarted, base_url=BASE) as http,
        closing(
            cast("HttpSkmClient", client_for(side, http, tmp_path / "http-restart", "http", token.secret))
        ) as client,
    ):
        assert ask(client, query).to_json() == expected
        assert ask(client, GetRunHistory(run_id=run.id, limit=2)).to_json() == first_page


def test_missing_transcript_content_is_unavailable_without_losing_history(
    exec_side: ExecSide, tmp_path, monkeypatch
):
    from security._security_helpers import bearer, canaries, http_for, seed_private_run, token_for
    from skm.kernel.errors import NotFound
    from skm.modules.artifacts import public as artifacts

    side, values = exec_side, canaries()
    run = seed_private_run(side, tmp_path / "runtime", values)
    token = token_for(side)
    store = side.app.gateways.get(artifacts.BlobStore)
    with http_for(side, values.redactor) as http:
        path = f"/api/v1/file-versions/{run.transcript_version}/content"
        history_path = f"/api/v1/runs/{run.run}/history"
        headers = bearer(token)
        baseline = http.get(history_path, headers=headers)
        assert baseline.status_code == 200
        assert baseline.json()["entries"]
        assert http.get(path, headers=headers).status_code == 200

        def unavailable(_location):
            raise NotFound(ErrorCode.NOT_FOUND, "test volume lost the transcript object")

        monkeypatch.setattr(store, "open", unavailable)
        missing = http.get(path, headers=headers)
        assert missing.json()["code"] == "FILE_VERSION_NOT_READY"
        assert "etag" not in missing.headers
        assert http.get(history_path, headers=headers).json() == baseline.json()
