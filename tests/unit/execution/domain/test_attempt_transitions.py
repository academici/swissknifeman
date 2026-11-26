"""Attempts, their outputs and the continuation cursor (execution §4.6, §4.6.1, §4.11)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from functools import cache
from itertools import product
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.attempt import (
    ATTEMPT_TRANSITIONS,
    CONTINUATION_MAX_BYTES,
    MAX_TRIGGERS,
    TERMINAL_ATTEMPT_STATES,
    AdvanceContinuation,
    Attempt,
    AttemptEndReason,
    AttemptState,
    ContinuationCause,
    DeferredTrigger,
    EntityRef,
    SelectedStage,
    StageContinuation,
    acceptable,
    consume_stage,
    continuation_to_json,
    defer_trigger,
    record_output,
    select_stage,
    settle_advance,
    transition_attempt,
)
from skm.modules.execution.domain.output import (
    ChangedPath,
    DiffStats,
    Output,
    OutputManifest,
    OutputMount,
    OutputSource,
    manifest_digest,
)
from skm.modules.execution.domain.session import RouteRef
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.platform.schema.registry import SchemaRegistry

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=10)
CONTINUATION = "urn:skm:execution:pending-continuation:v1"


def uid(n: int) -> Any:
    return UUID(int=n)


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def make_attempt(state: AttemptState = AttemptState.RUNNING, **changes: Any) -> Attempt:
    terminal = state in TERMINAL_ATTEMPT_STATES
    values: dict[str, Any] = {
        "id": uid(200),
        "run_id": uid(1),
        "task_id": uid(100),
        "workspace_id": uid(2),
        "attempt_no": 1,
        "state": state,
        "worker_id": uid(4),
        "host_id": uid(5),
        "environment_id": uid(6),
        "current_output_id": None,
        "executor_route": None,
        "continuation": None,
        "started_at": NOW,
        "finished_at": LATER if terminal else None,
        "end_reason": "FAILED" if terminal else None,
    }
    values.update(changes)
    return Attempt(**values)


def cause(kind: str = "stage_outcome", rule: str | None = None, **changes: Any) -> ContinuationCause:
    return ContinuationCause(kind, rule, **changes)


def trigger(n: int, kind: str = "manual_verdict") -> DeferredTrigger:
    return DeferredTrigger(uid(10_000 + n), cause(kind, refs=(EntityRef("check", uid(n)),)))


def stage(**changes: Any) -> SelectedStage:
    values: dict[str, Any] = {
        "stage_id": "execute",
        "stage_type": "agent_step",
        "mode": StageMode.REWORK,
        "round_no": 2,
        "params": {"role": "executor"},
        "not_before": None,
        "route_override": RouteRef("claude_code", "claude-implementation-class", "high"),
        "feedback_refs": FeedbackRefs(fix_brief_id=uid(70), answer_request_ids=(uid(71),)),
        "input_output_id": uid(300),
        "retry_of_id": None,
    }
    values.update(changes)
    return SelectedStage(**values)


# --- the table ---------------------------------------------------------------------------------------------

ALLOWED = {(source, rule.target) for rule in ATTEMPT_TRANSITIONS for source in rule.sources}


@pytest.mark.parametrize(
    ("source", "target"), list(product(AttemptState, AttemptState)), ids=lambda s: s.value
)
def test_every_pair_is_a_row_or_invalid(source: AttemptState, target: AttemptState) -> None:
    attempt = make_attempt(source)
    end = AttemptEndReason.FAILED if target in TERMINAL_ATTEMPT_STATES else None
    if (source, target) in ALLOWED:
        moved = transition_attempt(attempt, target, now=LATER, end_reason=end)
        assert moved.state is target
        assert (moved.finished_at is not None) == (target in TERMINAL_ATTEMPT_STATES)
        return
    with pytest.raises(SkmError) as caught:
        transition_attempt(attempt, target, now=LATER, end_reason=end)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION


def test_the_rows_of_section_4_6() -> None:
    assert {
        (AttemptState.PREPARING, AttemptState.RUNNING),
        (AttemptState.RUNNING, AttemptState.WAITING),
        (AttemptState.WAITING, AttemptState.RUNNING),
        (AttemptState.RUNNING, AttemptState.SUBMITTED),
        (AttemptState.SUBMITTED, AttemptState.COMPLETED),
        *((source, AttemptState.OWNERSHIP_LOST) for source in (
            AttemptState.PREPARING, AttemptState.RUNNING, AttemptState.WAITING, AttemptState.SUBMITTED)),
        *((source, AttemptState.ABANDONED) for source in (
            AttemptState.PREPARING, AttemptState.RUNNING, AttemptState.WAITING)),
        (AttemptState.RUNNING, AttemptState.COMPLETED),
        (AttemptState.WAITING, AttemptState.COMPLETED),
    } == ALLOWED  # fmt: skip


def test_finishing_needs_time_and_reason_and_only_then() -> None:
    with pytest.raises(SkmError, match="when and why"):
        transition_attempt(make_attempt(), AttemptState.ABANDONED)
    with pytest.raises(SkmError, match="end reason"):
        transition_attempt(make_attempt(), AttemptState.WAITING, end_reason=AttemptEndReason.FAILED)
    done = transition_attempt(
        make_attempt(AttemptState.SUBMITTED),
        AttemptState.COMPLETED,
        now=LATER,
        end_reason=AttemptEndReason.ACCEPTED,
    )
    assert (done.finished_at, done.end_reason) == (LATER, "ACCEPTED")


@pytest.mark.parametrize("state", list(AttemptState))
def test_results_of_lost_or_abandoned_attempts_are_never_acceptable(state: AttemptState) -> None:
    assert acceptable(make_attempt(state)) is (
        state not in {AttemptState.OWNERSHIP_LOST, AttemptState.ABANDONED}
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"attempt_no": 0},
        {"state": AttemptState.COMPLETED, "finished_at": None, "end_reason": None},
        {"finished_at": LATER, "end_reason": "FAILED"},
        {"state": AttemptState.ABANDONED, "finished_at": LATER, "end_reason": "GUESSED"},
        {"state": AttemptState.ABANDONED, "finished_at": NOW - timedelta(1), "end_reason": "FAILED"},
    ],
)
def test_attempt_invariants(changes: dict[str, Any]) -> None:
    with pytest.raises(SkmError) as caught:
        make_attempt(**changes)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


# --- outputs


def make_output(seq: int, output_id: Any, **changes: Any) -> Output:
    path = ChangedPath("app", "src/a.py", "c3JjL2EucHk", "modified", None, None, "100644 " + "1" * 40)
    manifest = OutputManifest(
        algorithm="skm-output-v2",
        mounts=(OutputMount("app", uid(7), "sha1", "a" * 40, "b" * 40, "c" * 40),),
        changed_paths=(path,),
        tree_digest="sha256:" + "d" * 64,
        outside_write_scope=(),
        excluded_paths=(),
        patch_file_version_id=None,
        diff_stats=DiffStats(1, 2, 1),
        empty=False,
    )
    values: dict[str, Any] = {
        "id": output_id,
        "attempt_id": uid(200),
        "task_id": uid(100),
        "run_id": uid(1),
        "seq": seq,
        "source": OutputSource.EXECUTOR,
        "manifest": manifest,
        "manifest_digest": manifest_digest(manifest),
        "sealed_at": NOW,
        "produced_by_step_id": uid(80),
    }
    values.update(changes)
    return Output(**values)


def test_outputs_form_an_append_only_sequence() -> None:
    first, second = make_output(1, uid(301)), make_output(2, uid(302))
    attempt = record_output(make_attempt(), first, previous=None)
    attempt = record_output(attempt, second, previous=first)
    assert attempt.current_output_id == second.id
    assert first.seq == 1  # the earlier output is untouched
    with pytest.raises(SkmError, match="seq 3"):
        record_output(attempt, make_output(2, uid(303)), previous=second)
    with pytest.raises(SkmError, match="current output"):
        record_output(attempt, make_output(2, uid(303)), previous=first)
    with pytest.raises(SkmError, match="belongs to this attempt"):
        record_output(attempt, make_output(3, uid(303), attempt_id=uid(201)), previous=second)
    finished = transition_attempt(
        attempt, AttemptState.ABANDONED, now=LATER, end_reason=AttemptEndReason.RESTARTED
    )
    with pytest.raises(SkmError, match="seals no output"):
        record_output(finished, make_output(3, uid(303)), previous=second)


def test_an_output_is_immutable_and_self_describing() -> None:
    output = make_output(1, uid(301))
    with pytest.raises(AttributeError):
        output.seq = 2  # type: ignore[misc]
    with pytest.raises(SkmError, match="manifest_digest"):
        make_output(1, uid(301), manifest_digest="sha256:" + "0" * 64)
    with pytest.raises(SkmError, match="names its step"):
        make_output(1, uid(301), produced_by_step_id=None)
    with pytest.raises(SkmError, match="names its step"):
        make_output(1, uid(301), source=OutputSource.RANGE)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("app", "a", "YQ==", "added", None, None, "100644 " + "1" * 40), "base64url"),
        (("app", "a", "Lw", "added", None, None, "100644 " + "1" * 40), "relative"),
        (("app", "a", "YQ", "renamed", None, None, "100644 " + "1" * 40), "rename"),
        (("app", "a", "YQ", "added", None, None, "absent"), "only a deleted"),
        (("app", "a", "YQ", "deleted", None, None, "100644 " + "1" * 40), "only a deleted"),
        (("app", "a", "YQ", "added", None, None, "other"), "fingerprint"),
    ],
)
def test_changed_paths_keep_exact_bytes(arguments: tuple[Any, ...], message: str) -> None:
    with pytest.raises(SkmError, match=message):
        ChangedPath(*arguments)


# --- continuation


def test_triggers_accumulate_in_order_and_repeat_as_noop() -> None:
    attempt = defer_trigger(make_attempt(), trigger(1), continuation_id=uid(500))
    attempt = defer_trigger(attempt, trigger(2), continuation_id=uid(501))
    cursor = attempt.continuation
    assert isinstance(cursor, AdvanceContinuation)
    assert [found.source_event_id for found in cursor.triggers] == [uid(10_001), uid(10_002)]
    assert cursor.continuation_id == uid(501)
    assert defer_trigger(attempt, trigger(1), continuation_id=uid(502)) is attempt
    assert registry().validate(CONTINUATION, continuation_to_json(cursor)) == ()


def test_the_trigger_cap_refuses_before_any_change() -> None:
    attempt = make_attempt()
    for n in range(MAX_TRIGGERS):
        attempt = defer_trigger(attempt, trigger(n), continuation_id=uid(500 + n))
    with pytest.raises(SkmError) as caught:
        defer_trigger(attempt, trigger(MAX_TRIGGERS), continuation_id=uid(9999))
    assert caught.value.details["reason"] == "continuation_full"
    assert isinstance(attempt.continuation, AdvanceContinuation)
    assert len(attempt.continuation.triggers) == MAX_TRIGGERS


def test_a_selected_stage_is_not_selected_again_nor_absorbs_triggers() -> None:
    selected = select_stage(
        make_attempt(), cause=cause("check_failed", "D3"), stage=stage(), continuation_id=uid(500)
    )
    assert isinstance(selected.continuation, StageContinuation)
    assert registry().validate(CONTINUATION, continuation_to_json(selected.continuation)) == ()
    for action in (
        lambda: select_stage(
            selected, cause=cause("check_failed", "D3"), stage=stage(), continuation_id=uid(501)
        ),
        lambda: defer_trigger(selected, trigger(1), continuation_id=uid(501)),
    ):
        with pytest.raises(SkmError) as caught:
            action()
        assert caught.value.code is ErrorCode.INVALID_TRANSITION
        assert caught.value.details["reason"] == "continuation_already_selected"


def test_begin_stage_consumes_exactly_the_materialized_cursor() -> None:
    selected = select_stage(make_attempt(), cause=cause(), stage=stage(), continuation_id=uid(500))
    with pytest.raises(SkmError, match="continuation_changed"):
        consume_stage(selected, continuation_id=uid(501))
    consumed, template = consume_stage(selected, continuation_id=uid(500))
    assert consumed.continuation is None
    assert template == stage()
    with pytest.raises(SkmError, match="no_selected_stage"):
        consume_stage(consumed, continuation_id=uid(500))


def test_advance_is_settled_once_for_a_wait() -> None:
    pending = defer_trigger(make_attempt(), trigger(1), continuation_id=uid(500))
    assert settle_advance(pending).continuation is None
    with pytest.raises(SkmError, match="no_pending_triggers"):
        settle_advance(make_attempt())


def test_pause_and_waits_between_stages_keep_the_cursor() -> None:
    pending = defer_trigger(make_attempt(), trigger(1), continuation_id=uid(500))
    waiting = transition_attempt(pending, AttemptState.WAITING)
    resumed = transition_attempt(waiting, AttemptState.RUNNING)
    assert resumed.continuation == pending.continuation


@pytest.mark.parametrize("terminal", sorted(TERMINAL_ATTEMPT_STATES - {AttemptState.COMPLETED}))
def test_terminal_states_clear_the_cursor_in_the_same_transition(terminal: AttemptState) -> None:
    pending = select_stage(make_attempt(), cause=cause(), stage=stage(), continuation_id=uid(500))
    finished = transition_attempt(pending, terminal, now=LATER, end_reason=AttemptEndReason.LEASE_LOST)
    assert finished.continuation is None
    with pytest.raises(SkmError, match="no continuation"):
        make_attempt(terminal, continuation=pending.continuation)
    with pytest.raises(SkmError, match="attempt_finished"):
        defer_trigger(finished, trigger(1), continuation_id=uid(501))


def test_a_legacy_null_cursor_stays_null() -> None:
    attempt = make_attempt(continuation=None)
    assert transition_attempt(attempt, AttemptState.WAITING).continuation is None
    with pytest.raises(SkmError, match="no_selected_stage"):
        consume_stage(attempt, continuation_id=uid(500))


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: cause("observation"), "observation"),
        (lambda: cause("guessing"), "unknown trigger"),
        (lambda: DeferredTrigger(uid(1), cause(rule="D3")), "not fired"),
        (lambda: DeferredTrigger(uid(1), cause(source_event_id=uid(2))), "equals the trigger"),
        (lambda: stage(stage_type="plan_acceptance"), "control-plane"),
        (lambda: stage(retry_of_id=uid(3)), "mode retry"),
        (lambda: stage(round_no=0), "round_no"),
        (lambda: stage(params={str(n): n for n in range(129)}), "params"),
        (lambda: stage(feedback_refs=FeedbackRefs(answer_request_ids=(uid(1), uid(1)))), "distinct"),
        (lambda: AdvanceContinuation(1, uid(1), "advance", ()), "1..128"),
        (lambda: AdvanceContinuation(1, uid(1), "advance", (trigger(1), trigger(1))), "distinct"),
        (lambda: AdvanceContinuation(2, uid(1), "advance", (trigger(1),)), "schema_version"),  # type: ignore[arg-type]
    ],
)
def test_cursor_shapes_are_closed(build: Any, message: str) -> None:
    with pytest.raises(SkmError, match=message):
        build()


def test_the_cursor_is_bounded_in_bytes() -> None:
    big = {f"k{n}": "x" * 600 for n in range(120)}
    with pytest.raises(SkmError, match="at most 65536 bytes"):
        select_stage(make_attempt(), cause=cause(), stage=stage(params=big), continuation_id=uid(500))


def _cursor_bytes(cursor: Any) -> int:
    text = json.dumps(continuation_to_json(cursor), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return len(text.encode("utf-8"))


def test_a_selected_template_is_deeply_immutable_and_stays_bounded() -> None:
    params: dict[str, Any] = {"nested": {"value": "safe", "items": [1, {"k": "v"}]}}
    selected = select_stage(
        make_attempt(), cause=cause(), stage=stage(params=params), continuation_id=uid(500)
    )
    cursor = selected.continuation
    assert isinstance(cursor, StageContinuation)
    expected = continuation_to_json(cursor)
    size = _cursor_bytes(cursor)
    # the caller's nested source and a returned document are detached from the selected template
    params["nested"]["value"] = "x" * 70000
    params["nested"]["items"].append(2)
    returned = continuation_to_json(cursor)
    returned["stage"]["params"]["nested"]["value"] = "y" * 70000  # type: ignore[index,call-overload]
    returned["stage"]["params"]["nested"]["items"].append(3)  # type: ignore[index,call-overload,union-attr]
    assert continuation_to_json(cursor) == expected
    assert _cursor_bytes(cursor) == size <= CONTINUATION_MAX_BYTES
    nested = cursor.stage.params["nested"]
    assert nested["value"] == "safe"  # type: ignore[index,call-overload]
    assert nested["items"] == (1, {"k": "v"})  # type: ignore[index,call-overload]
    with pytest.raises(TypeError):
        nested["value"] = "x"  # type: ignore[index]
    with pytest.raises(TypeError):
        nested["items"][1]["k"] = "w"  # type: ignore[index]
    with pytest.raises(AttributeError):
        nested["items"].append(3)  # type: ignore[union-attr]
    document = continuation_to_json(cursor)
    assert document["stage"]["params"] == {"nested": {"value": "safe", "items": [1, {"k": "v"}]}}  # type: ignore[index,call-overload]
    assert registry().validate(CONTINUATION, document) == ()
    # the cursor is still bounded at construction, nested values included
    with pytest.raises(SkmError, match="at most 65536 bytes"):
        select_stage(
            make_attempt(),
            cause=cause(),
            stage=stage(params={"nested": {"value": "x" * 70000}}),
            continuation_id=uid(501),
        )


@pytest.mark.parametrize(
    "value",
    [{1}, object(), {"k": {2: "v"}}, float("nan")],
    ids=["set", "object", "non-string-key", "nan"],
)
def test_selected_params_are_json(value: Any) -> None:
    with pytest.raises(SkmError) as caught:
        stage(params={"p": value})
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_retry_stage_and_feedback_serialize_to_the_schema() -> None:
    retry = stage(mode=StageMode.RETRY, retry_of_id=uid(90), route_override=None, not_before=LATER)
    selected = select_stage(make_attempt(), cause=cause("retry", "C1"), stage=retry, continuation_id=uid(500))
    assert isinstance(selected.continuation, StageContinuation)
    document = continuation_to_json(selected.continuation)
    assert registry().validate(CONTINUATION, document) == ()
    assert document["stage"]["retry_of_id"] == str(uid(90))  # type: ignore[index,call-overload]
