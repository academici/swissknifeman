"""Durable continuation contracts and the immediate PostgreSQL terminal-state backstop."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import psycopg
import pytest
from psycopg.types.json import Jsonb

from skm.kernel.errors import ValidationFailed
from skm.modules.execution.domain.attempt import (
    AdvanceContinuation,
    AttemptState,
    ContinuationCause,
    DeferredTrigger,
    EntityRef,
    SelectedStage,
    StageContinuation,
    continuation_to_json,
)
from skm.modules.execution.domain.ids import DecisionRequestId, FixBriefId, OutputId, StageRecordId, StepId
from skm.modules.execution.domain.session import RouteRef
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import AttemptRepository

from .seed_helpers import seed_attempt, seed_run, seed_task

if TYPE_CHECKING:
    from .harness import ExecSide


def test_continuations_round_trip_and_terminal_clear(exec_side: ExecSide) -> None:
    source_id = exec_side.new_id()
    trigger = DeferredTrigger(
        source_id,
        ContinuationCause(
            "stage_outcome",
            None,
            refs=(EntityRef("stage", exec_side.new_id()),),
            source_event_id=source_id,
        ),
    )
    advance = AdvanceContinuation(1, exec_side.new_id(), "advance", (trigger,))
    selected = SelectedStage(
        "execute",
        "plugin_stage",
        StageMode.RETRY,
        2,
        {"role": "executor"},
        exec_side.clock.now(),
        RouteRef("codex_cli", "gpt-5", "high"),
        FeedbackRefs(
            FixBriefId(exec_side.new_id()),
            StepId(exec_side.new_id()),
            (DecisionRequestId(exec_side.new_id()),),
            StepId(exec_side.new_id()),
            StageRecordId(exec_side.new_id()),
        ),
        OutputId(exec_side.new_id()),
        StageRecordId(exec_side.new_id()),
    )
    stage = StageContinuation(1, exec_side.new_id(), "stage", ContinuationCause("retry", "K5b"), selected)
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        att = seed_attempt(exec_side, uow, run.id, task.id, continuation=advance)
        uow.commit()
    for version, cursor in enumerate((stage, advance), 1):
        with exec_side.uow() as uow:
            repo = uow.repo(AttemptRepository)
            saved = repo.get(att.id).continuation
            assert saved is not None
            assert continuation_to_json(saved) == continuation_to_json(advance if version == 1 else stage)
            repo.save(replace(att, continuation=cursor), expected_version=version)
            uow.commit()
    if exec_side.dsn:
        with psycopg.connect(exec_side.dsn) as conn:
            with pytest.raises(psycopg.errors.CheckViolation) as exc:
                conn.execute(
                    "UPDATE skm_execution.attempts SET state='completed', finished_at=clock_timestamp(), "
                    "end_reason='ACCEPTED' WHERE id=%s",
                    (att.id,),
                )
            assert exc.value.diag.constraint_name == "ck_attempts__continuation"
            conn.rollback()
            oversized = continuation_to_json(stage)
            oversized["stage"]["params"] = {"padding": "x" * 131072}  # type: ignore[index]
            with pytest.raises(psycopg.errors.CheckViolation) as cap_exc:
                conn.execute(
                    "UPDATE skm_execution.attempts SET continuation=%s WHERE id=%s",
                    (Jsonb(oversized), att.id),
                )
            assert cap_exc.value.diag.constraint_name == "ck_attempts__continuation"
            conn.rollback()
            conn.execute(
                "UPDATE skm_execution.attempts SET state='completed', continuation=NULL, "
                "finished_at=clock_timestamp(), end_reason='ACCEPTED' WHERE id=%s",
                (att.id,),
            )
            conn.rollback()
    with exec_side.uow() as uow:
        uow.repo(AttemptRepository).save(
            replace(
                att,
                state=AttemptState.COMPLETED,
                continuation=None,
                finished_at=exec_side.clock.now(),
                end_reason="ACCEPTED",
            ),
            expected_version=3,
        )
        uow.commit()
    with exec_side.uow(readonly=True) as uow:
        assert uow.repo(AttemptRepository).get(att.id).continuation is None
        uow.rollback()


def test_continuation_rejects_malformed_union_caps_and_forbidden_fields(exec_side: ExecSide) -> None:
    source = exec_side.new_id()
    trigger = DeferredTrigger(source, ContinuationCause("retry", None))
    with pytest.raises(ValidationFailed, match="distinct"):
        AdvanceContinuation(1, exec_side.new_id(), "advance", (trigger, trigger))
    with pytest.raises(ValidationFailed, match="128"):
        AdvanceContinuation(1, exec_side.new_id(), "advance", (trigger,) * 129)
    cursor = AdvanceContinuation(1, exec_side.new_id(), "advance", (trigger,))
    raw = continuation_to_json(cursor)
    for patch in ({"kind": "stage"}, {"stage": {}}, {"triggers": []}, {"schema_version": 2}):
        with pytest.raises(ValidationFailed):
            exec_side.app.schemas.require_valid("urn:skm:execution:pending-continuation:v1", {**raw, **patch})
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        uow.commit()
    for field in ("config", "input_digest", "token", "manifest", "locators"):
        params: dict[str, Any] = {"nested": [{field: "forbidden"}]}
        bad = StageContinuation(
            1,
            exec_side.new_id(),
            "stage",
            ContinuationCause("retry", "K5b"),
            SelectedStage(
                "execute", "agent_step", StageMode.NORMAL, 1, params, None, None, FeedbackRefs(), None, None
            ),
        )
        with exec_side.uow() as uow:
            with pytest.raises(ValidationFailed, match="forbidden"):
                seed_attempt(exec_side, uow, run.id, task.id, continuation=bad)
            uow.rollback()
    with pytest.raises(ValidationFailed, match="65536"):
        StageContinuation(
            1,
            exec_side.new_id(),
            "stage",
            ContinuationCause("retry", "K5b"),
            SelectedStage(
                "execute",
                "agent_step",
                StageMode.NORMAL,
                1,
                {"padding": "x" * 65536},
                None,
                None,
                FeedbackRefs(),
                None,
                None,
            ),
        )
