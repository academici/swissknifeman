"""PARITY-12 through main(), a real App and committed interleaved execution events."""

from typing import Any

import pytest

from e2e.test_execution_cli import invoke, result
from skm.modules.execution.domain.run import RunStatus
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import seeded
from unit.execution.application._support import side as side


class ObservedClient:
    """Instrument reads while preserving the real client, bus, authorizer and persisted transitions."""

    def __init__(self, client: Any, tick: Any = None) -> None:
        self.client, self.tick = client, tick
        self.polls: list[int] = []
        self.snapshot_cursor: int | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    def ask_with_meta(self, query: Any) -> Any:
        view, meta = self.client.ask_with_meta(query)
        self.snapshot_cursor = meta.events_cursor
        return view, meta

    def ask(self, query: Any) -> Any:
        from skm.modules.execution.generated.queries import GetRunTimeline

        if isinstance(query, GetRunTimeline):
            assert query.after_seq is not None
            self.polls.append(query.after_seq)
            if self.tick is not None:
                callback, self.tick = self.tick, None
                callback()
        return self.client.ask(query)

    def events(self, **kwargs: Any) -> Any:
        pytest.fail("follow must never read the workspace event stream")


def test_follow_only_target_run_and_starts_at_get_run_cursor(side: Any) -> None:
    a, _, _ = seeded(side)
    b, _, _ = seeded(side)
    previous, _, _ = seeded(side)
    result(side, "run", "cancel", str(previous.id), "--yes", "--reason", "old-plan-run")

    def interleave() -> None:
        result(side, "run", "cancel", str(b.id), "--yes", "--reason", "foreign-live-run")
        result(side, "run", "pause", str(a.id), "--reason", "only-target-event")
        result(side, "run", "cancel", str(a.id), "--yes", "--reason", "target-finished")

    client = ObservedClient(side.client, interleave)
    code, out, err = invoke(side, "run", "follow", str(a.id), client=client, human=True)
    assert code == 6, (out, err)
    assert "RunPaused" in out
    assert "finished: cancelled" in out
    assert "foreign-live-run" not in out
    assert "old-plan-run" not in out
    assert str(b.id) not in out
    assert out.count("RunCancelled") == 1
    assert client.snapshot_cursor is not None
    assert client.snapshot_cursor > 0
    assert client.polls[0] == 0


def test_finished_run_summary_does_not_open_events_or_replay(side: Any) -> None:
    run, _, _ = seeded(side)
    result(side, "run", "cancel", str(run.id), "--yes", "--reason", "never-replay-this")
    client = ObservedClient(side.client, lambda: pytest.fail("terminal follow opened event iterator"))
    code, out, err = invoke(side, "run", "follow", str(run.id), client=client, human=True)
    assert code == 6, (out, err)
    assert out.startswith(f"run {run.id} finished: cancelled at ")
    assert "never-replay-this" not in out
    assert "RunCancelled" not in out
    assert not client.polls


def test_explicit_history_is_marked_and_new_events_are_live(side: Any) -> None:
    run, _, _ = seeded(side)
    result(side, "run", "pause", str(run.id), "--reason", "earlier")
    result(side, "run", "resume", str(run.id))
    client = ObservedClient(
        side.client, lambda: result(side, "run", "cancel", str(run.id), "--yes", "--reason", "live-stop")
    )
    code, out, err = invoke(side, "run", "follow", str(run.id), "--history", client=client, human=True)
    assert code == 6, (out, err)
    lines = out.splitlines()
    assert any(line.startswith("history ") and "RunPaused" in line for line in lines)
    assert any(not line.startswith("history ") and "RunCancelled" in line for line in lines)
    assert not any(line.startswith("history ") and "RunCancelled" in line for line in lines)
    assert client.polls[0] == 0
    assert client.polls[1] > 0


def test_waiting_outcome_has_inbox_guidance_and_single_json_envelope(side: Any) -> None:
    run, _, _ = seeded(side, run_status=RunStatus.WAITING)
    code, out, err = invoke(side, "run", "follow", str(run.id), human=True)
    assert code == 4, err
    assert f"skm inbox list --run {run.id}" in out, err
    code, out, _ = invoke(side, "run", "show", str(run.id))
    import json

    assert code == 4
    assert json.loads(out)["outcome"]["kind"] == "waiting"


def test_types_filter_is_applied_without_hiding_terminal_status(side: Any) -> None:
    run, _, _ = seeded(side)

    def finish() -> None:
        result(side, "run", "pause", str(run.id), "--reason", "filter-this")
        result(side, "run", "cancel", str(run.id), "--yes", "--reason", "selected-event")

    code, out, err = invoke(
        side,
        "run",
        "follow",
        str(run.id),
        "--types",
        "RunCancelled",
        client=ObservedClient(side.client, finish),
        human=True,
    )
    assert code == 6, err
    assert "RunCancelled" in out, err
    assert "RunPaused" not in out, err


@pytest.mark.parametrize(("status", "expected"), [(RunStatus.SUCCEEDED, 0), (RunStatus.FAILED, 6)])
def test_terminal_status_exit_codes(side: Any, status: RunStatus, expected: int) -> None:
    from contracts.execution.seed_helpers import seed_bundle, seed_run

    with side.uow() as uow:
        run = seed_run(side, uow, status=status)
        seed_bundle(side, uow, run.id)
        uow.commit()
    code, out, _ = invoke(side, "run", "follow", str(run.id), human=True)
    assert code == expected
    assert f"finished: {status.value}" in out
