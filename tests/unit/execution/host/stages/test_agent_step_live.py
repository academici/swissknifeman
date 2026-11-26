"""Forward normalized runtime events and usage while a stage owns its lease."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event
from unittest.mock import Mock

import pytest

from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.modules.execution.host.stages.agent_step import _collect
from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.domain.session_events import StopReason, ToolCallStatus

AT = datetime(2026, 11, 18, 12, tzinfo=UTC)
DIGEST = "sha256:" + "1" * 64


@pytest.mark.parametrize("lease_lost", [False, True])
def test_collect_offers_each_session_event_and_reports_usage(lease_lost):
    usage = replace(runtimes.unknown_usage(), input_tokens=7, status=runtimes.UsageStatus.REPORTED)
    failure = runtimes.ProviderFailure(
        runtimes.ErrorClass.CANCELLED,
        ErrorCode.CANCEL_IGNORED,
        False,
        "runtime ignored cancel",
        None,
        None,
        "process",
    )
    sessions = (
        (
            runtimes.SessionStarted(1, AT, "executor", None, None),
            runtimes.TextDelta(2, AT, "assistant", "working"),
            runtimes.ToolRequested(3, AT, "read-1", "read", "README.md", DIGEST),
            runtimes.ToolCompleted(4, AT, "read-1", ToolCallStatus.OK, 10),
            runtimes.UsageReported(5, AT, usage, cumulative=True),
            runtimes.CheckpointAvailable(6, AT, "executor"),
            runtimes.SessionCompleted(7, AT, StopReason.END_TURN, DIGEST),
        ),
        (
            runtimes.SessionStarted(1, AT, "reviewer", None, None),
            runtimes.UsageReported(2, AT, usage, cumulative=True),
            runtimes.CancelIgnored(3, AT, "SIGTERM"),
            runtimes.SessionFailed(4, AT, failure),
        ),
    )
    cancel = CancelSource()
    if lease_lost:
        cancel.cancel("lease_lost")
    deps = Mock(cancel=cancel.token)
    request = Mock(begin={"stage_record_id": "stage"}, capture=None)
    handle = Mock(request_id="step")

    for events in sessions:
        # A generator also verifies the collector drains the stream after lease loss.
        runtime = Mock(events=Mock(return_value=iter(events)))
        done = Event()
        results, failures = [], []
        _collect(runtime, handle, request, deps, done, results, failures)
        assert done.is_set()
        assert not failures
        assert results == [runtime.result.return_value]
        assert list(runtime.events.return_value) == []

    offered = [json.loads(call.args[0]) for call in request.offer_live.call_args_list]
    progress = [call.args[0] for call in deps.worker.report_progress.call_args_list]
    if lease_lost:
        assert offered == progress == []
    else:
        assert offered == [runtimes.session_event_to_json(event) for events in sessions for event in events]
        assert [item["usage_so_far"]["input_tokens"] for item in progress if "usage_so_far" in item] == [7, 7]
