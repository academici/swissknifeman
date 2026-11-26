"""Integration tests for ``integrations`` hook fan-out, K-135 visibility, and dead replay (memory ∥ pg)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from io import StringIO
from typing import cast

import pytest

from skm.application_bus.context import SubscriberContext
from skm.application_bus.ports import EventReader, OutboxState, OutboxStore
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.application.subscribers import CONSUMER_ID, fan_out_hook_deliveries
from skm.modules.integrations.domain.events import HookDeliveryFailed, HookTestRequested
from skm.modules.integrations.generated import (
    commands as int_cmd,
)
from skm.modules.integrations.generated import (
    queries as int_qry,
)
from skm.modules.integrations.generated import (
    results as int_res,
)
from skm.modules.integrations.generated import (
    views as int_views,
)
from skm.modules.settings.ports import ConfigEntryRepository, ConfigGenerationCounter
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.logging import setup as logging_setup
from skm.platform.logging.redaction import Redactor

from ._hook_support import HOOKABLE_EVENT_URN, _host_guard_cfg, _RoutingWorld, _webhook_cfg
from ._hook_support import clean_test_database as clean_test_database
from ._hook_support import pg_session as pg_session
from ._hook_support import test_database as test_database
from ._hook_support import world as world


def test_committed_domain_event_enqueues_hook_outbox_and_deduplicates_repeats(world: _RoutingWorld) -> None:
    ws_id = world.create_workspace("acme")
    world.set_subscriptions(
        level="workspace",
        scope_id=ws_id,
        subscriptions={
            "active-hook": _webhook_cfg(),
            "disabled-hook": _webhook_cfg(enabled=False),
            "host-guard": _host_guard_cfg(),
        },
    )

    before_envelope = world.emit_hookable(workspace_id=ws_id)
    before_json = before_envelope.to_json()
    world.run_relay_pass()
    assert world.hook_destinations_for(before_envelope.id, workspace_id=ws_id) == ["hook:active-hook"]

    with world.uow_factory(world._meta(), readonly=True) as uow:
        (after_envelope,) = uow.repo(EventReader).by_ids([before_envelope.id])
    assert after_envelope.to_json() == before_json

    with world.uow_factory(world._meta(), readonly=False) as uow:
        cfg = world.loader.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.WORKSPACE, ScopeId(ws_id))
        )
        sub_ctx = SubscriberContext(
            consumer_id=CONSUMER_ID,
            attempt=1,
            clock=world.clock,
            ids=world.ids,
            log=world.logger,
            config=cfg,
            gateways=world.gateways,
            config_for=lambda sr: world.loader.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), sr),
        )
        fan_out_hook_deliveries(before_envelope, sub_ctx, uow)
        fan_out_hook_deliveries(before_envelope, sub_ctx, uow)
        uow.commit()
    world.run_relay_pass()
    assert world.hook_destinations_for(before_envelope.id, workspace_id=ws_id) == ["hook:active-hook"]


@pytest.mark.parametrize("project_scope", [False, True])
def test_recursion_prevention_and_test_hook_subscription_routing(
    world: _RoutingWorld, project_scope: bool
) -> None:
    assert world.schemas.get(HookDeliveryFailed.event_type).get("x-skm-hookable") is False
    assert world.schemas.get(HookTestRequested.event_type).get("x-skm-hookable") is False
    assert CONSUMER_ID not in world.registry.subscription_index().get(HookDeliveryFailed.event_type, ())

    ws_id = world.create_workspace("loop-guard")
    project_id = world.create_project(ws_id, "hooks-project") if project_scope else None
    world.set_subscriptions(
        level="project" if project_scope else "workspace",
        scope_id=project_id or ws_id,
        subscriptions={
            "broad-sub": _webhook_cfg(event_types=["urn:skm:policy:event:*"]),
            "disabled-target": _webhook_cfg(enabled=False),
            "host-only": _host_guard_cfg("/opt/skm/check.py"),
        },
    )

    src_env = world.emit_hookable(workspace_id=ws_id)
    world.run_relay_pass()
    fail_cmd = int_cmd.RecordHookDeliveryFailure(
        delivery_id=world.ids.new_id(),
        subscription_id="broad-sub",
        subscription_digest="sha256:" + "1" * 64,
        event_id=src_env.id,
        event_type=src_env.type,
        class_="observation",
        failure_policy="retry",
        attempts=3,
        reason="http_5xx",
        status=502,
        scope=int_cmd.RecordHookDeliveryFailureScope(kind="workspace", id=ws_id),
    )
    fail_res = cast(
        "int_res.RecordHookDeliveryFailureResult", world.dispatch(fail_cmd, actor=world.system_actor)
    )
    assert fail_res.recorded is True
    world.run_relay_pass()

    with world.uow_factory(world._meta(), readonly=True) as uow:
        failed_envs = uow.repo(EventReader).after_workspace_seq(
            ws_id, 0, types=frozenset({HookDeliveryFailed.event_type}), limit=50
        )
        assert len(failed_envs) == 1
    assert world.hook_destinations_for(failed_envs[0].id, workspace_id=ws_id) == []

    with pytest.raises(PreconditionFailed) as host_exc:
        world.dispatch(
            int_cmd.TestHookSubscription(
                workspace_id=ws_id, project_id=project_id, subscription_id="host-only"
            )
        )
    assert host_exc.value.code is ErrorCode.HOOK_SUBSCRIPTION_LOCATION

    with pytest.raises(NotFound):
        world.dispatch(
            int_cmd.TestHookSubscription(workspace_id=ws_id, project_id=project_id, subscription_id="unknown")
        )

    test_res = cast(
        "int_res.TestHookSubscriptionResult",
        world.dispatch(
            int_cmd.TestHookSubscription(
                workspace_id=ws_id, project_id=project_id, subscription_id="disabled-target"
            )
        ),
    )
    world.run_relay_pass()
    with world.uow_factory(world._meta(), readonly=True) as uow:
        test_envs = uow.repo(EventReader).after_workspace_seq(
            ws_id, 0, types=frozenset({HookTestRequested.event_type}), limit=50
        )
        test_env = next(e for e in test_envs if e.stream_id == test_res.test_id)
    assert world.hook_destinations_for(test_env.id, workspace_id=ws_id) == ["hook:disabled-target"]


def test_k135_scope_isolation_between_instance_workspace_and_projects(world: _RoutingWorld) -> None:
    ws1 = world.create_workspace("ws-one")
    ws2 = world.create_workspace("ws-two")
    proj_a = world.create_project(ws1, "proj-a")
    proj_b = world.create_project(ws1, "proj-b")

    world.set_subscriptions(level="instance", scope_id=None, subscriptions={"inst-sub": _webhook_cfg()})
    world.set_subscriptions(level="workspace", scope_id=ws1, subscriptions={"ws1-sub": _webhook_cfg()})
    world.set_subscriptions(level="project", scope_id=proj_a, subscriptions={"proj-a-sub": _webhook_cfg()})
    world.set_subscriptions(level="project", scope_id=proj_b, subscriptions={"proj-b-sub": _webhook_cfg()})

    ev_instance = world.emit_hookable(workspace_id=None)
    ev_ws1_root = world.emit_hookable(workspace_id=ws1)
    ev_proj_a = world.emit_hookable(workspace_id=ws1, extra={"project_id": str(proj_a)})
    ev_proj_b = world.emit_hookable(workspace_id=ws1, extra={"project_id": str(proj_b)})
    ev_ws2 = world.emit_hookable(workspace_id=ws2)
    world.run_relay_pass()

    assert world.hook_destinations_for(ev_instance.id, workspace_id=None) == ["hook:inst-sub"]
    assert world.hook_destinations_for(ev_ws1_root.id, workspace_id=ws1) == ["hook:inst-sub", "hook:ws1-sub"]
    assert world.hook_destinations_for(ev_proj_a.id, workspace_id=ws1) == [
        "hook:inst-sub",
        "hook:proj-a-sub",
        "hook:ws1-sub",
    ]
    assert world.hook_destinations_for(ev_proj_b.id, workspace_id=ws1) == [
        "hook:inst-sub",
        "hook:proj-b-sub",
        "hook:ws1-sub",
    ]
    assert world.hook_destinations_for(ev_ws2.id, workspace_id=ws2) == ["hook:inst-sub"]


def test_fanout_ceiling_caps_at_32_sorted_by_id_and_logs_error(world: _RoutingWorld) -> None:
    ws_id = world.create_workspace("fanout-cap")
    world.set_subscriptions(
        level="workspace",
        scope_id=ws_id,
        subscriptions={f"sub-{idx:02d}": _webhook_cfg() for idx in range(35)},
    )
    world.logger.records.clear()
    ev = world.emit_hookable(workspace_id=ws_id)
    world.run_relay_pass()

    assert world.hook_destinations_for(ev.id, workspace_id=ws_id) == [
        f"hook:sub-{idx:02d}" for idx in range(32)
    ]
    assert any(rec["fields"].get("code") == "HOOK_FANOUT_LIMIT" for rec in world.logger.records)


def test_stale_invalid_stored_subscription_is_skipped_on_fanout_and_redacted_in_list(
    world: _RoutingWorld,
) -> None:
    ws_id = world.create_workspace("graceful-read")
    world.set_subscriptions(
        level="workspace",
        scope_id=ws_id,
        subscriptions={
            "ci-sub": _webhook_cfg(url="https://user:supersecret@hooks.example.com:8443/v1/hook?token=abc"),
            "jira-sub": {
                "class": "observation",
                "kind": "event_sink",
                "execution_location": "control_plane",
                "event_types": [HOOKABLE_EVENT_URN],
                "target": {"sink_id": "jira-sink", "config": {"api_key": "secret://env/JIRA_API_KEY"}},
                "failure_policy": "warn",
            },
        },
    )
    world.rebind_sinks(())
    world.logger.records.clear()

    ev = world.emit_hookable(workspace_id=ws_id)
    world.run_relay_pass()
    assert world.hook_destinations_for(ev.id, workspace_id=ws_id) == ["hook:ci-sub"]
    assert any(rec["fields"].get("code") == "HOOK_SUBSCRIPTION_INVALID" for rec in world.logger.records)

    listed = cast(
        "int_res.ListHookSubscriptionsResult", world.ask(int_qry.ListHookSubscriptions(workspace_id=ws_id))
    )
    by_id = {item.id: item for item in listed.items}
    assert by_id["ci-sub"].valid is True
    assert by_id["ci-sub"].target_summary == "https://hooks.example.com:8443"
    assert "supersecret" not in str(listed.to_json())
    assert "token=abc" not in str(listed.to_json())
    assert by_id["jira-sub"].valid is False
    assert any(v["reason"] == "sink_not_registered" for v in by_id["jira-sub"].violations)


def test_record_failure_list_deliveries_and_retry_dead_with_workspace_isolation(world: _RoutingWorld) -> None:
    ws1 = world.create_workspace("ops-ws-1")
    ws2 = world.create_workspace("ops-ws-2")
    world.set_subscriptions(
        level="workspace",
        scope_id=ws1,
        subscriptions={"wf-gate": _webhook_cfg(class_="workflow", failure_policy="deny")},
    )
    ev = world.emit_hookable(workspace_id=ws1)
    world.run_relay_pass()

    now = world.clock.now()
    due = now + timedelta(minutes=5)
    with world.uow_factory(world._meta(), readonly=False) as uow:
        outbox = uow.repo(OutboxStore)
        claimed = outbox.claim(destination="hook:wf-gate", limit=10, relay_id="relay-1", now=now)
        assert len(claimed) == 1
        item = claimed[0]
        initial_generation = item.delivery_generation
        assert outbox.mark_failed(item.id, relay_id="relay-1", error="http_500", next_at=due, dead=True)
        uow.commit()

    dead_view = cast(
        "int_views.HookDeliveriesView",
        world.ask(int_qry.ListHookDeliveries(workspace_id=ws1, subscription_id="wf-gate", state="dead")),
    )
    assert len(dead_view.items) == 1
    assert dead_view.items[0].delivery_id == item.id
    assert dead_view.items[0].event_type == HOOKABLE_EVENT_URN
    assert dead_view.items[0].available_at == due

    cmd = int_cmd.RecordHookDeliveryFailure(
        delivery_id=item.id,
        subscription_id="wf-gate",
        subscription_digest="sha256:" + "2" * 64,
        event_id=ev.id,
        event_type=ev.type,
        class_="workflow",
        failure_policy="deny",
        attempts=5,
        reason="http_500",
        status=500,
        scope=int_cmd.RecordHookDeliveryFailureScope(kind="workspace", id=ws1),
    )
    first_rec = cast("int_res.RecordHookDeliveryFailureResult", world.dispatch(cmd, actor=world.system_actor))
    dup_rec = cast("int_res.RecordHookDeliveryFailureResult", world.dispatch(cmd, actor=world.system_actor))
    assert first_rec.recorded is True
    assert dup_rec.recorded is False
    assert not world.dispatch(cmd, actor=world.system_actor, idempotency_key="another-key").recorded

    with world.uow_factory(world._meta(), readonly=True) as uow:
        failed_events = uow.repo(EventReader).after_workspace_seq(
            ws1, 0, types=frozenset({HookDeliveryFailed.event_type}), limit=10
        )
    assert len(failed_events) == 1
    assert failed_events[0].payload["blocking"] is True
    assert failed_events[0].payload.get("run_id") is None
    assert failed_events[0].payload.get("task_id") is None

    with pytest.raises(NotFound):
        world.dispatch(int_cmd.RetryHookDeliveries(workspace_id=ws2, delivery_ids=(item.id,)))

    retried = cast(
        "int_res.RetryHookDeliveriesResult",
        world.dispatch(int_cmd.RetryHookDeliveries(workspace_id=ws1, delivery_ids=(item.id,))),
    )
    assert retried.requeued == 1

    with world.uow_factory(world._meta(), readonly=False) as uow:
        reclaimed = uow.repo(OutboxStore).claim(
            destination="hook:wf-gate",
            limit=10,
            relay_id="relay-2",
            now=world.clock.now() + timedelta(seconds=1),
        )
        assert len(reclaimed) == 1
        assert reclaimed[0].delivery_generation == initial_generation + 1


@pytest.mark.parametrize("url", ["https://[bad", "https://hooks.example:bad", "https://hooks.example:70000"])
def test_malformed_stored_url_is_skipped_and_logged_without_breaking_list(
    world: _RoutingWorld,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    # Bus queries use the process logger, while world.logger captures subscriber logs.
    # Own the sink and threshold so earlier logging configuration cannot hide the warning.
    log_stream = StringIO()
    monkeypatch.setattr(logging_setup._state, "settings", logging_setup._state.settings)
    logging_setup.configure_logging(
        level="warning", detail="normal", fmt="json", stream=log_stream, redactor=Redactor(), host="localhost"
    )
    ws = world.create_workspace("corrupt-url")
    world.set_subscriptions(
        level="workspace",
        scope_id=ws,
        subscriptions={"valid": _webhook_cfg(), "broken": _webhook_cfg()},
    )
    # Model restored data written before URL validation existed; bypass only the settings write validator.
    with world.uow_factory(world._meta(), readonly=False) as uow:
        repo = uow.repo(ConfigEntryRepository)
        entry = repo.find(ws, "hooks.subscriptions")
        assert entry is not None
        repo.save(
            replace(
                entry,
                value={"valid": _webhook_cfg(), "broken": _webhook_cfg(url=url)},
                row_version=entry.row_version + 1,
            ),
            expected_version=entry.row_version,
        )
        uow.repo(ConfigGenerationCounter).increment()
        uow.commit()
    log_stream.seek(0)
    log_stream.truncate()
    listed = world.ask(int_qry.ListHookSubscriptions(workspace_id=ws))
    assert [sub.id for sub in listed.items] == ["valid"]
    logs = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    assert any(
        record.get("event") == "integrations.hook_subscription_invalid" and record.get("level") == "warning"
        for record in logs
    )
    event = world.emit_hookable(workspace_id=ws)
    world.run_relay_pass()
    assert world.hook_destinations_for(event.id, workspace_id=ws) == ["hook:valid"]


def test_pending_filter_includes_failed_retries_and_preserves_pagination(world: _RoutingWorld) -> None:
    ws = world.create_workspace("pending-retries")
    names = ("failed", "failed-other", "pending", "dead", "delivered")
    world.set_subscriptions(
        level="workspace",
        scope_id=ws,
        subscriptions={name: _webhook_cfg() for name in names},
    )
    world.emit_hookable(workspace_id=ws)
    world.run_relay_pass()
    due = world.clock.now() + timedelta(minutes=5)
    with world.uow_factory(world._meta(), readonly=False) as uow:
        store = uow.repo(OutboxStore)
        for name in ("failed", "dead", "delivered"):
            (item,) = store.claim(destination=f"hook:{name}", limit=1, relay_id="test", now=world.clock.now())
            if name == "delivered":
                assert store.mark_delivered(item.id, at=world.clock.now(), relay_id="test")
            else:
                assert store.mark_failed(
                    item.id, relay_id="test", error="http_503", next_at=due, dead=name == "dead"
                )
        physical = store.list(
            destination_prefix="hook:", state=OutboxState.FAILED, workspace_id=ws, after=None, limit=200
        )
        assert [item.destination for item in physical.items] == ["hook:failed"]
        uow.commit()
    rows, cursor = [], None
    while True:
        page = world.ask(int_qry.ListHookDeliveries(workspace_id=ws, state="pending", limit=1, after=cursor))
        rows.extend(page.items)
        if not page.has_more:
            break
        assert page.next_cursor is not None
        assert page.next_cursor != cursor
        cursor = page.next_cursor
    assert len(rows) == 3
    assert {row.subscription_id for row in rows} == {"failed", "failed-other", "pending"}
    assert all(row.state == "pending" for row in rows)
    retry = world.ask(int_qry.ListHookDeliveries(workspace_id=ws, subscription_id="failed", state="pending"))
    assert [row.subscription_id for row in retry.items] == ["failed"]
    assert retry.items[0].available_at == due
    for state in ("dead", "delivered"):
        page = world.ask(int_qry.ListHookDeliveries(workspace_id=ws, state=state))
        assert [row.subscription_id for row in page.items] == [state]
