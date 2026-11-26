"""History source bounds, rollback visibility and live authorization across pages."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from skm.kernel.errors import Forbidden
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.modules.access.ports import MembershipRepository
from skm.modules.execution.generated.queries import GetRunHistory
from skm.modules.execution.ports import ExecutionQueries

from .harness import ask
from .seed_helpers import record_run_event, seed_run

if TYPE_CHECKING:
    from .harness import ExecSide


def _no_delta(side: ExecSide, run_id: object) -> JsonObject:
    return {
        "workspace_id": str(side.ws),
        "project_id": str(side.proj),
        "run_id": str(run_id),
        "assignment_id": str(side.new_id()),
        "task_id": str(side.new_id()),
        "attempt_id": str(side.new_id()),
        "worker_id": str(side.worker1),
        "host_id": str(side.host1),
        "fencing_token": 1,
    }


def test_bounded_history_scan_keeps_cursor_until_cutoff_and_ignores_rollback(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        for _ in range(205):
            record_run_event(exec_side, uow, run.id, "assignment-leased", _no_delta(exec_side, run.id))
        uow.commit()
    with exec_side.uow() as uow:
        record_run_event(exec_side, uow, run.id, "assignment-leased", _no_delta(exec_side, run.id))
        uow.rollback()
    with exec_side.uow(readonly=True) as uow:
        queries = uow.repo(ExecutionQueries)
        assert queries.head_run_seq(run.id) == 205
        assert len(queries.run_events(run.id, 0, 205, 1000)) == 200
        assert len(queries.run_events(run.id, 0, 4, 200)) == 4
        assert queries.run_events(run.id, 0, 0, 200) == ()
        uow.rollback()
    first = ask(exec_side.client, GetRunHistory(run_id=run.id, limit=200)).to_json()
    entries = cast("list[JsonObject]", first["entries"])
    assert len(entries) == 200
    assert first["scanned_through_seq"] == 200
    assert first["through_seq"] == 205
    assert all(e["reason_codes"] == ["NO_HISTORY_DELTA"] for e in entries)
    after = first["next_after"]
    assert isinstance(after, str)
    second = ask(exec_side.client, GetRunHistory(run_id=run.id, after=after)).to_json()
    assert len(cast("list[object]", second["entries"])) == 5
    assert second["next_after"] is None
    assert second["scanned_through_seq"] == second["through_seq"] == 205
    zero = ask(exec_side.client, GetRunHistory(run_id=run.id, through_seq=0)).to_json()
    assert zero["entries"] == []
    assert zero["next_after"] is None
    assert zero["scanned_through_seq"] == zero["through_seq"] == 0


def test_history_cursor_rechecks_current_permissions(exec_side: ExecSide) -> None:
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        for _ in range(2):
            record_run_event(exec_side, uow, run.id, "assignment-leased", _no_delta(exec_side, run.id))
        uow.commit()
    page = ask(exec_side.viewer_client, GetRunHistory(run_id=run.id, limit=1)).to_json()
    after = page["next_after"]
    assert isinstance(after, str)
    with exec_side.uow() as uow:
        uow.repo(MembershipRepository).delete(ScopeId(exec_side.ws), exec_side.viewer.principal_id)
        uow.commit()
    with pytest.raises(Forbidden):
        ask(exec_side.viewer_client, GetRunHistory(run_id=run.id, after=after))
