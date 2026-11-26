"""Unit tests for the pure bounded causality history builder v1 (execution §8.1)."""

from __future__ import annotations

import json
import random
from functools import cache
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.execution.application._worker_events import executed_by
from skm.modules.execution.application.stages.acceptance_gate import observed_identity
from skm.modules.execution.domain.history import (
    BUILDER_VERSION,
    MAX_ENTRY_EDGES,
    MAX_ENTRY_NODES,
    MAX_PAGE_BYTES,
    MAX_PAGE_EDGES,
    MAX_PAGE_EVENTS,
    MAX_PAGE_NODES,
    build_history,
)
from skm.platform.schema.registry import SchemaRegistry

HISTORY_URN = "urn:skm:execution:execution-history:v1"
TS = "2026-11-15T07:00:00Z"
DIG = "sha256:" + "a" * 64


@cache
def _registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _uid(n: int) -> str:
    return str(UUID(int=(0x01900000_0000_7000_8000_000000000000 + n)))


def _canonical(doc: object) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _assert_valid_page(page: JsonObject) -> JsonObject:
    _registry().require_valid(HISTORY_URN, page)
    assert len(_canonical(page)) <= MAX_PAGE_BYTES
    if page["next_after"] is None:
        assert page["scanned_through_seq"] == page["through_seq"]
    return page


def _d(**kw: Any) -> JsonObject:
    return kw


def _ev(
    seq: int,
    short: str,
    payload: JsonObject,
    *,
    run_id: str | None = None,
    event_type: str | None = None,
    stream_kind: str = "run",
) -> JsonObject:
    return _d(
        id=_uid(10_000 + seq),
        stream_kind=stream_kind,
        stream_id=run_id or _uid(1),
        stream_seq=seq,
        event_type=event_type or f"urn:skm:execution:event:{short}:v1",
        occurred_at=TS,
        recorded_at=TS,
        payload=payload,
    )


def _cause(tk: str, rule: str | None = None) -> JsonObject:
    return _d(trigger_kind=tk, advance_rule=rule, reason_codes=[], refs=[])


def _route_snapshot(*, host_id: str | None = None, extra: JsonObject | None = None) -> JsonObject:
    req = _d(runtime_id="codex_cli", model="gpt-5", model_class="implementation", effort="high")
    base = _d(
        requested=req,
        resolved=_d(runtime_id="codex_cli", model="gpt-5", effort="high"),
        route_source="plan_route",
        host_id=host_id or _uid(90),
        executable_sha256=DIG,
        verification_key=DIG,
        effective_config_digest=DIG,
        reconfiguration_ids=[_uid(91)],
        route_reason="ROUTE_DEFAULT",
        runtime_version="1.2.3",
        adapter_version="0.4.0",
        catalog_digest=DIG,
        profile_version_id=_uid(92),
    )
    if extra:
        base.update(extra)
    return base


def _observation(
    *,
    req_id: str | None = None,
    cov: str = "complete",
    tool_cov: str = "complete",
    model: str | None = "gpt-5",
    extra: JsonObject | None = None,
) -> JsonObject:
    is_unav, t_unav = (cov == "unavailable"), (tool_cov == "unavailable")
    bind = _d(
        runtime_id="codex_cli",
        runtime_version="1.2.3",
        adapter_version="0.4.0",
        executable_sha256=DIG,
        verification_key=DIG,
        provider_reported_model=model,
        model_source="unavailable" if model is None else "provider_stream",
    )
    tm = _d(
        clock_domain_id=None if is_unav else _uid(81),
        duration_ms=None if is_unav else 420,
        first_observed_at=TS,
        last_observed_at=TS,
    )
    cap = _d(
        coverage=cov,
        bytes_seen=None if is_unav else 1024,
        bytes_retained=None if is_unav else 1024,
        bytes_dropped=None if is_unav else 0,
        truncated=None if is_unav else False,
        gaps=[],
        parser_flags=[],
        live_events_dropped=0,
    )
    base = _d(
        schema="urn:skm:runtimes:runtime-observation:v1",
        request_id=req_id or _uid(80),
        binding=bind,
        timing=tm,
        capture=cap,
        tools=_d(coverage=tool_cov, observed_calls=None if t_unav else 3),
    )
    if extra:
        base.update(extra)
    return base


def test_empty_stream_bounds_and_gaps() -> None:
    rid = _uid(1)
    empty = _assert_valid_page(build_history((), 0, run_id=rid))
    assert empty == _d(
        run_id=rid,
        through_seq=0,
        builder_version=BUILDER_VERSION,
        scanned_through_seq=0,
        entries=[],
        next_after=None,
        coverage="complete",
    )

    bad_bounds: tuple[dict[str, object], ...] = (
        {"through_seq": -1},
        {"through_seq": True},
        {"through_seq": 2, "after_seq": -1},
        {"through_seq": 2, "after_seq": 3},
        {"through_seq": 2, "after_seq": False},
        {"through_seq": 2, "limit": 0},
        {"through_seq": 2, "limit": True},
    )
    for kwargs in bad_bounds:
        with pytest.raises(ValidationFailed) as exc:
            build_history((), **kwargs)  # type: ignore[arg-type]
        assert exc.value.code is ErrorCode.SCHEMA_INVALID

    missing_all = _assert_valid_page(build_history((), 3, run_id=rid))
    assert missing_all["coverage"] == "unavailable"
    assert missing_all["entries"] == []

    evs = [
        _ev(2, "run-started", _d(run_id=rid), run_id=rid),
        _ev(1, "run-started", _d(run_id=_uid(999)), run_id=_uid(999)),
        _ev(1, "run-started", _d(run_id=rid), run_id=rid, stream_kind="plan"),
    ]
    gapped = _assert_valid_page(build_history(evs, 3, run_id=rid))
    assert gapped["coverage"] == "partial"
    assert [e["seq"] for e in gapped["entries"]] == [2]  # type: ignore[index]


def test_full_lifecycle_permutation_determinism_and_rule_suffixes() -> None:
    rid, rev_id, tid, tid2, aid, srid = _uid(1), _uid(2), _uid(3), _uid(4), _uid(5), _uid(6)
    step1, step2, out_id, chk_id, revw_id, f_id = _uid(7), _uid(8), _uid(9), _uid(10), _uid(11), _uid(12)
    fb_id, dr_id, drec_id, acc_id, dev_id, eff_id = _uid(13), _uid(14), _uid(15), _uid(16), _uid(17), _uid(18)
    rec_id, mv_id, reconf_id = _uid(19), _uid(20), _uid(21)
    frefs = _d(
        fix_brief_id=fb_id,
        advice_step_id=_uid(41),
        schema_errors_step_id=_uid(42),
        interrupted_stage_record_id=_uid(43),
        answer_request_ids=[dr_id],
    )
    srefs = [
        _d(step_id=step1, role="executor", route_snapshot=_route_snapshot()),
        _d(step_id=step2, parent_step_id=step1, role="advisor"),
    ]
    stg_start = _d(
        task_id=tid,
        attempt_id=aid,
        stage_record_id=srid,
        mode="rework",
        round_no=2,
        input_digest=DIG,
        reconfiguration_ids=[reconf_id],
        feedback_refs=frefs,
        step_refs=srefs,
    )
    obs_p = _d(
        task_id=tid,
        attempt_id=aid,
        stage_record_id=srid,
        step_id=step2,
        parent_step_id=step1,
        role="advisor",
        binding_consistency="matched",
        route_snapshot=_route_snapshot(),
        observation=_observation(),
    )
    stg_done = _d(
        task_id=tid,
        attempt_id=aid,
        stage_record_id=srid,
        mode="rework",
        round_no=2,
        outcome_kind="success",
        output_id=out_id,
        check_execution_ids=[chk_id],
        review_ids=[revw_id],
        effect_ids=[eff_id],
        timing=_d(started_at=TS, finished_at=TS, duration_ms=150, basis="db_transition"),
        step_states={step1: "succeeded", step2: "cancelled"},
    )
    t_init = _d(
        task_id=tid,
        kind="unit",
        initial_state="blocked",
        revision_id=rev_id,
        entity_id=_uid(30),
        cause=_cause("run_start", "SE8r"),
    )
    rework_p = _d(
        task_id=tid,
        attempt_id=aid,
        round=1,
        reason="REVIEW_NOT_GREEN",
        fix_brief_id=fb_id,
        input_output_id=out_id,
    )
    wait_p = _d(
        task_id=tid,
        attempt_id=aid,
        state="awaiting_decision",
        previous_code="MANUAL_PENDING",
        code="DEVIATION_REQUIRED",
        started_at=TS,
        finished_at=None,
    )
    rec_p = _d(
        task_id=tid,
        attempt_id=aid,
        stage_record_id=srid,
        recovery_record_id=rec_id,
        state="completed",
        reason_code="LEASE_LOST",
    )

    stream: list[JsonObject] = [
        _ev(1, "run-created", _d(revision_id=rev_id, status="created", cause=_cause("manual_start", "K5b"))),
        _ev(2, "run-started", _d(cause=_cause("run_start", "L2i"))),
        _ev(3, "run-reconfigured", _d(reconfiguration_id=reconf_id)),
        _ev(4, "task-created", t_init),
        _ev(5, "task-ready", _d(task_id=tid)),
        _ev(6, "task-assigned", _d(task_id=tid, attempt_id=aid, attempt_state="preparing")),
        _ev(7, "attempt-started", _d(task_id=tid, attempt_id=aid)),
        _ev(8, "stage-started", stg_start),
        _ev(
            9,
            "runtime-start-admitted",
            _d(task_id=tid, attempt_id=aid, stage_record_id=srid, step_bindings=[_d(step_id=step2)]),
        ),
        _ev(10, "step-observation-recorded", obs_p),
        _ev(
            11,
            "output-sealed",
            _d(
                task_id=tid,
                attempt_id=aid,
                stage_record_id=srid,
                step_id=step1,
                output_id=out_id,
                manifest_digest=DIG,
            ),
        ),
        _ev(12, "stage-completed", stg_done),
        _ev(
            13,
            "check-completed",
            _d(task_id=tid, check_execution_id=chk_id, output_id=out_id, state="failed"),
        ),
        _ev(
            14,
            "manual-verdict-recorded",
            _d(task_id=tid, check_execution_id=chk_id, output_id=out_id, verdict="pass", verdict_id=mv_id),
        ),
        _ev(
            15,
            "review-completed",
            _d(task_id=tid, review_id=revw_id, output_id=out_id, round_no=1, finding_ids=[f_id]),
        ),
        _ev(16, "task-rework-required", rework_p),
        _ev(
            17,
            "decision-requested",
            _d(task_id=tid, request_id=dr_id, state="open", code="DEVIATION_REQUIRED"),
        ),
        _ev(
            18,
            "decision-answered",
            _d(task_id=tid, request_id=dr_id, state="answered", decision_record_id=drec_id),
        ),
        _ev(19, "deviation-accepted", _d(task_id=tid, deviation_id=dev_id, finding_id=f_id)),
        _ev(
            20,
            "acceptance-decided",
            _d(task_id=tid, attempt_id=aid, acceptance_decision_id=acc_id, output_id=out_id),
        ),
        _ev(
            21,
            "external-effect-recorded",
            _d(task_id=tid, attempt_id=aid, stage_record_id=srid, effect_id=eff_id, state="intended"),
        ),
        _ev(
            22,
            "external-effect-outcome-unknown",
            _d(task_id=tid, attempt_id=aid, stage_record_id=srid, effect_id=eff_id),
        ),
        _ev(
            23,
            "integration-completed",
            _d(
                task_id=tid, attempt_id=aid, stage_record_id=srid, integration_receipts=[_d(effect_id=eff_id)]
            ),
        ),
        _ev(24, "stage-recovered", rec_p),
        _ev(25, "task-wait-changed", wait_p),
        _ev(26, "followups-created", _d(task_id=tid, followup_task_ids=[tid2])),
        _ev(27, "task-accepted", _d(task_id=tid, attempt_id=aid, output_id=out_id)),
        _ev(28, "run-waiting", _d(stop_code="MANUAL_PENDING")),
        _ev(29, "run-paused", _d(stop_code="BUDGET_EXHAUSTED")),
        _ev(30, "run-resumed", _d(previous_stop_code="BUDGET_EXHAUSTED")),
        _ev(31, "run-finished", _d(outcome="succeeded")),
    ]

    baseline = _assert_valid_page(build_history(stream, 31, run_id=rid))
    baseline_bytes = _canonical(baseline)
    entries: list[Any] = baseline["entries"]  # type: ignore[assignment]
    assert len(entries) == 31
    assert entries[0]["cause"]["advance_rule"] == "K5b"
    assert entries[0]["nodes"][0]["advance_rule"] == "K5b"
    assert entries[1]["cause"]["advance_rule"] == "L2i"
    assert entries[3]["nodes"][0]["advance_rule"] == "SE8r"

    stg_nodes = entries[7]["nodes"]
    assert stg_nodes[2]["ref"]["id"] == step2
    assert stg_nodes[2]["parent"] == _d(kind="step", id=step1, visibility="local")
    dr_edges = [e for e in entries[7]["edges"] if e["target"].get("id") == dr_id]
    assert dr_edges[0]["target"]["visibility"] == "unloaded"
    done_steps = {n["ref"]["id"]: n["state"] for n in entries[11]["nodes"] if n["ref"]["kind"] == "step"}
    assert done_steps == {step1: "succeeded", step2: "cancelled"}
    assert entries[24]["wait"] == _d(
        previous_code="MANUAL_PENDING",
        code="DEVIATION_REQUIRED",
        started_at=TS,
        finished_at=None,
    )

    rng = random.Random(20261115)
    for _ in range(5):
        shuffled = list(stream)
        rng.shuffle(shuffled)
        assert _canonical(_assert_valid_page(build_history(shuffled, 31, run_id=rid))) == baseline_bytes


def _mon_payload(srid: str, *, cov: str = "partial", pad_len: int = 0) -> JsonObject:
    th = [_d(key="pad", value="y" * pad_len)] if pad_len else [_d(key="worker.stall_seconds", value=300)]
    return _d(
        evaluation_id="eval-1",
        monitor_id="stall_detector",
        rule_id="R.stall",
        rule_version="1.0",
        target_stage_record_id=srid,
        fencing_token=2,
        thresholds=th,
        config_digest=DIG,
        input_watermark=1,
        input_coverage=cov,
        last_signal_at=TS,
        scheduled_at=TS,
        started_at=TS,
        finished_at=TS,
        verdict="healthy",
        action="none",
        action_request_id=None,
        recovery_record_id=None,
        reason_code="OK",
        config_generation=0,
        recovery_mode="notify",
    )


def test_all_seven_reason_codes_and_foreign_visibility() -> None:
    rid, tid, aid, srid, step_id = _uid(1), _uid(3), _uid(5), _uid(6), _uid(7)
    foreign_unauth, foreign_auth = _uid(501), _uid(502)
    mon_p = _mon_payload(srid, cov="partial")
    obs_mis = _d(
        task_id=tid,
        attempt_id=aid,
        stage_record_id=srid,
        step_id=step_id,
        role="executor",
        binding_consistency="mismatch",
        route_snapshot=_route_snapshot(),
        observation=_observation(cov="unavailable", tool_cov="partial"),
    )
    events: list[JsonObject] = [
        _ev(1, "assignment-leased", _d(assignment_id=_uid(60))),
        _ev(2, "monitor-evaluated", mon_p),
        _ev(
            3,
            "runtime-start-admitted",
            _d(task_id=tid, attempt_id=aid, stage_record_id=srid, step_bindings=[]),
        ),
        _ev(4, "run-created", _d(status="created")),
        _ev(5, "unknown", {}, event_type="urn:skm:execution:event:future-op:v1"),
        _ev(6, "run-started", "not-a-dict"),  # type: ignore[arg-type]
        _ev(7, "task-accepted", _d(task_id=tid, carried_forward=True, source_task_id=foreign_unauth)),
        _ev(8, "task-accepted", _d(task_id=tid, carried_forward=True, source_task_id=foreign_auth)),
        _ev(9, "step-observation-recorded", obs_mis),
    ]
    page = _assert_valid_page(
        build_history(
            events,
            9,
            run_id=rid,
            authorized_foreign_ids=frozenset({("task", foreign_auth)}),
            explicit_foreign_ids=frozenset({("task", foreign_unauth), ("task", foreign_auth)}),
        )
    )
    entries: list[Any] = page["entries"]  # type: ignore[assignment]
    assert [entries[i]["reason_codes"] for i in range(6)] == [
        ["NO_HISTORY_DELTA"],
        ["NO_HISTORY_DELTA"],
        ["NO_HISTORY_DELTA"],
        ["LEGACY_FIELDS_MISSING"],
        ["UNSUPPORTED_EVENT_TYPE"],
        ["PAYLOAD_UNREPRESENTABLE"],
    ]
    assert entries[1]["coverage"] == "partial"
    assert entries[1]["monitor_evaluation"]["monitor_id"] == "stall_detector"

    assert entries[6]["reason_codes"] == ["FOREIGN_REFERENCE_RESTRICTED"]
    assert entries[6]["edges"][0]["target"] == _d(kind="task", visibility="foreign_opaque")
    assert "FOREIGN_REFERENCE_RESTRICTED" not in entries[7]["reason_codes"]
    assert entries[7]["edges"][0]["target"] == _d(kind="task", id=foreign_auth, visibility="unloaded")

    assert set(entries[8]["reason_codes"]) == {"OBSERVATION_UNAVAILABLE", "BINDING_MISMATCH"}
    obs_node = entries[8]["nodes"][0]
    assert obs_node["binding_consistency"] == "mismatch"
    assert obs_node["route_snapshot"]["resolved"]["model"] == "gpt-5"
    assert obs_node["runtime_observation"]["capture"]["coverage"] == "unavailable"


def test_hard_caps_pagination_and_oversized_entry_degradation() -> None:
    rid, tid, aid, srid = _uid(1), _uid(3), _uid(5), _uid(6)
    many_events = [_ev(i, "assignment-leased", {}) for i in range(1, MAX_PAGE_EVENTS + 6)]
    p1 = _assert_valid_page(build_history(many_events, MAX_PAGE_EVENTS + 5, run_id=rid))
    assert len(p1["entries"]) == MAX_PAGE_EVENTS  # type: ignore[arg-type]
    assert p1["scanned_through_seq"] == MAX_PAGE_EVENTS
    assert p1["next_after"] is not None
    p2 = _assert_valid_page(
        build_history(many_events, MAX_PAGE_EVENTS + 5, run_id=rid, after_seq=MAX_PAGE_EVENTS)
    )
    assert len(p2["entries"]) == 5  # type: ignore[arg-type]
    assert p2["next_after"] is None

    fids = lambda i: [_uid(20_000 + i * 32 + j) for j in range(MAX_ENTRY_NODES - 3)]  # noqa: E731
    node_events = [
        _ev(i, "review-completed", _d(task_id=tid, review_id=_uid(1000 + i), round_no=1, finding_ids=fids(i)))
        for i in range(1, 61)
    ]
    pn = _assert_valid_page(build_history(node_events, 60, run_id=rid))
    assert sum(len(e["nodes"]) for e in pn["entries"]) <= MAX_PAGE_NODES  # type: ignore[index,misc]
    assert pn["next_after"] is not None

    eids = lambda i: [_uid(50_000 + i * 250 + j) for j in range(MAX_ENTRY_EDGES)]  # noqa: E731
    edge_events = [
        _ev(i, "followups-created", _d(task_id=tid, followup_task_ids=eids(i))) for i in range(1, 21)
    ]
    pe = _assert_valid_page(build_history(edge_events, 20, run_id=rid))
    assert sum(len(e["edges"]) for e in pe["entries"]) <= MAX_PAGE_EDGES  # type: ignore[index,misc]
    assert pe["next_after"] is not None

    huge_obs = _observation(extra=_d(pad="x" * 20_000))
    bad_obs = _ev(
        1,
        "step-observation-recorded",
        _d(task_id=tid, attempt_id=aid, stage_record_id=srid, step_id=_uid(77), observation=huge_obs),
    )
    huge_raw = _ev(2, "monitor-evaluated", _mon_payload(srid, cov="complete", pad_len=270_000))
    p_bad = _assert_valid_page(build_history([bad_obs, huge_raw], 2, run_id=rid))
    for entry in p_bad["entries"]:  # type: ignore[union-attr]
        assert entry["coverage"] == "unavailable"
        assert entry["reason_codes"] == ["PAYLOAD_UNREPRESENTABLE"]


def test_whitelist_never_exposes_prompts_tool_args_logs_paths_or_secrets() -> None:
    rid, tid, aid, srid, step_id = _uid(1), _uid(3), _uid(5), _uid(6), _uid(7)
    toxic = (
        "TOP_SECRET_SYSTEM_PROMPT",
        "RAW_TOOL_ARGUMENTS_PAYLOAD",
        "CAPTURED_STDOUT_CHUNK",
        "CAPTURED_STDERR_STACKTRACE",
        "/home/vostrikov/private/worktree/main.py",
        "secret://prod/openai_api_key",
    )
    srefs = [
        _d(step_id=step_id, role="executor", route_snapshot=_route_snapshot(extra=_d(secret_ref=toxic[5])))
    ]
    stg_p = _d(
        task_id=tid,
        attempt_id=aid,
        stage_record_id=srid,
        mode="normal",
        round_no=1,
        input_digest=DIG,
        prompt=toxic[0],
        local_locator=toxic[4],
        step_refs=srefs,
    )
    obs_p = _d(
        task_id=tid,
        attempt_id=aid,
        stage_record_id=srid,
        step_id=step_id,
        role="executor",
        binding_consistency="matched",
        tool_arguments=toxic[1],
        stdout=toxic[2],
        stderr=toxic[3],
        observation=_observation(extra=_d(stdout=toxic[2], stderr=toxic[3], local_path=toxic[4])),
    )
    sec_p = _d(
        task_id=tid,
        attempt_id=aid,
        stage_record_id=srid,
        step_id=step_id,
        observation=_observation(model=toxic[5]),
    )
    page = _assert_valid_page(
        build_history(
            [
                _ev(1, "stage-started", stg_p),
                _ev(2, "step-observation-recorded", obs_p),
                _ev(3, "step-observation-recorded", sec_p),
            ],
            3,
            run_id=rid,
        )
    )
    serialized = _canonical(page).decode("utf-8")
    for marker in toxic:
        assert marker not in serialized
    assert page["entries"][2]["reason_codes"] == ["PAYLOAD_UNREPRESENTABLE"]  # type: ignore[index]


def test_execution_attribution_and_family_use_the_provider_observation() -> None:
    snapshot = _route_snapshot()
    step = SimpleNamespace(route_snapshot=snapshot, runtime_observation=None)
    assert executed_by(snapshot, None) is None
    assert observed_identity(step) is None

    step.runtime_observation = _observation(model=None)
    assert executed_by(snapshot, step.runtime_observation) == "codex_cli"
    assert observed_identity(step) == {"runtime": "codex_cli", "family": None}

    step.runtime_observation = _observation(model="anthropic/claude-opus-5")
    binding = step.runtime_observation["binding"]
    assert isinstance(binding, dict)
    binding["observed_effort"] = "medium"
    assert executed_by(snapshot, step.runtime_observation) == "codex_cli/anthropic/claude-opus-5/medium"
    assert observed_identity(step) == {"runtime": "codex_cli", "family": "claude"}
