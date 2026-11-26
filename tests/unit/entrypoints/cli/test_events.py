"""Outbox inspection and requeue exercise the real CLI, App and platform command handlers."""

import json
from typing import Any

from e2e.test_execution_cli import invoke, result
from skm.application_bus.ports import OutboxStore
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import seeded
from unit.execution.application._support import side as side


def test_dead_retry_only_selected_event_and_destination(side: Any) -> None:
    run, _, _ = seeded(side)
    result(side, "run", "pause", str(run.id), "--reason", "create outbox event")
    with side.uow() as uow:
        store = uow.repo(OutboxStore)
        claimed = store.claim(destination="sse", relay_id="cli-test", now=side.clock.now(), limit=200)
        assert claimed
        for item in claimed:
            assert store.mark_failed(
                item.id, relay_id="cli-test", error="IOError", next_at=side.clock.now(), dead=True
            )
        uow.commit()
    dead = result(side, "events", "dead", "--limit", "1")
    assert len(dead["items"]) == 1
    event = dead["items"][0]["event_id"]
    before = result(side, "events", "dead", "--limit", "200")
    assert result(side, "events", "retry", event, "--destination", "not-this-destination")["requeued"] == 0
    assert result(side, "events", "retry", event, "--destination", "sse")["requeued"] == 1
    assert len(result(side, "events", "dead", "--limit", "200")["items"]) == len(before["items"]) - 1
    assert result(side, "events", "retry", event, "--destination", "sse")["requeued"] == 0


def test_events_permissions_and_bad_identifiers_use_standard_errors(side: Any) -> None:
    denied = side.restricted_client(["run.read"], scope_id=side.proj)
    code, out, _ = invoke(side, "events", "dead", client=denied)
    assert code == 5
    assert json.loads(out)["error"]["code"] == "FORBIDDEN"
    assert invoke(side, "events", "retry", "bad-event-id")[0] == 1
    assert invoke(side, "events", "dead", "--limit", "not-a-number")[0] == 2
