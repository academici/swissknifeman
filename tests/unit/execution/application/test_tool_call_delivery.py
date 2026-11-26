"""Tool metering runs before live delivery and retains unacknowledged IDs."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable
from skm.modules.execution.host.stage_client import BoundStageClient
from skm.modules.execution.host.stages.agent_step import _collect
from skm.modules.runtimes.domain.session_events import ToolCallStatus
from skm.modules.runtimes.public import ToolCompleted, ToolRequested


def test_capture_reports_tool_calls_even_when_sse_delivery_drops() -> None:
    order: list[tuple[str, Any]] = []
    now = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        ToolRequested(1, now, "call-1", "read", "private preview", "sha256:" + "a" * 64),
        ToolCompleted(2, now, "call-1", ToolCallStatus.OK, None),
    ]
    result = Mock()
    runtime = Mock()
    runtime.events.return_value = events
    runtime.result.return_value = result

    def lose_live(_payload: bytes) -> bool:
        order.append(("live", None))
        return False

    request: Any = SimpleNamespace(begin={"stage_record_id": "stage"}, offer_live=lose_live, capture=None)
    deps: Any = SimpleNamespace(
        cancel=SimpleNamespace(cancelled=False),
        worker=SimpleNamespace(report_progress=lambda data: order.append(("meter", data["tool_calls"]))),
    )
    done, results, failures = Mock(), [], []
    _collect(runtime, SimpleNamespace(request_id="step"), request, deps, done, results, failures)
    assert failures == []
    assert results == [result]
    assert order == [
        (
            "meter",
            {"coverage": "partial", "calls": [{"call_id": "call-1", "duration_ms": None, "tool": "read"}]},
        ),
        ("live", None),
        ("meter", {"coverage": "partial", "calls": [{"call_id": "call-1", "duration_ms": None}]}),
        ("live", None),
    ]
    done.set.assert_called_once()


def test_bound_client_retries_unacknowledged_calls_through_heartbeat() -> None:
    from contextlib import nullcontext

    import pytest

    claim = Mock(assignment_id="assignment", attempt_id="attempt", worker_id="worker", fencing_token=7)
    client = Mock()
    client.dispatch.side_effect = [BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "response lost"), {}, {}]
    concurrency: Any = SimpleNamespace(lock=nullcontext)
    stage = BoundStageClient(
        client, claim, {"renew_lease": lambda data: data}, Mock(), concurrency=concurrency
    )
    stage.set_stage("stage", "step")
    calls = {"coverage": "partial", "calls": [{"call_id": "c1", "duration_ms": None}]}
    with pytest.raises(BackendUnavailable):
        stage.report_progress({"tool_calls": calls})
    stage.heartbeat()
    stage.heartbeat()
    expected = {"stage_record_id": "stage", "step_id": "step"}
    payloads = [call.args[0]["progress"] for call in client.dispatch.call_args_list]
    assert payloads == [{**expected, "tool_calls": calls}, {**expected, "tool_calls": calls}, expected]


def test_tool_batches_after_handoff_retry_only_unacknowledged_calls() -> None:
    from contextlib import nullcontext

    import pytest

    claim = Mock(assignment_id="assignment", attempt_id="attempt", worker_id="worker", fencing_token=7)
    client = Mock()
    lost = BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "response lost")
    client.dispatch.side_effect = [{}, {}, lost, {}, {}, {}]
    concurrency: Any = SimpleNamespace(lock=nullcontext)
    stage = BoundStageClient(
        client, claim, {"renew_lease": lambda data: data}, Mock(), concurrency=concurrency
    )
    stage.set_stage("stage", "step")
    stage.report_progress({"phase": "runtime_started"})
    with pytest.raises(BackendUnavailable):
        stage.report_progress(
            {"tool_calls": {"calls": [{"call_id": str(n), "duration_ms": None} for n in range(201)]}}
        )
    stage.flush_tool_calls()
    stage.heartbeat()
    handoff, *reports, heartbeat = [call.args[0]["progress"] for call in client.dispatch.call_args_list]
    assert handoff["phase"] == "runtime_started"
    assert heartbeat == {"stage_record_id": "stage", "step_id": "step"}
    assert all("phase" not in report for report in reports)
    assert [[int(call["call_id"]) for call in report["tool_calls"]["calls"]] for report in reports] == [
        list(range(100)),
        list(range(100, 200)),
        list(range(100, 200)),
        [200],
    ]
