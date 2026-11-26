"""Actual relay delivery (memory/PostgreSQL), process limits and host trust regressions."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast, override
from uuid import UUID

import pytest

from security.test_webhook_ssrf import _server
from skm.adapters.event_sinks._pinned_http import PinnedHttpClient
from skm.adapters.event_sinks.webhook import WebhookSink
from skm.adapters.host_commands.subprocess_runner import SubprocessHostCommandRunner
from skm.adapters.secrets.env import EnvSecretResolver
from skm.application_bus.context import SubscriberContext
from skm.application_bus.ports import EventReader, OutboxState, OutboxStore
from skm.application_bus.subscribers import (
    DeliverySettings,
    EventConfigLoader,
    EventSinkRegistry,
    OutboxRelayPass,
)
from skm.kernel.gateways import GatewayTable
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.integrations.application.hook_delivery import HOOK_CONSUMER, HookDeliveryConsumer
from skm.modules.integrations.application.subscribers import CONSUMER_ID
from skm.modules.integrations.domain.events import HookDeliveryFailed
from skm.modules.integrations.domain.hook_events import HookClass
from skm.modules.integrations.domain.hook_rules import HookVerdict
from skm.modules.integrations.domain.hook_subscriptions import parse_subscriptions
from skm.modules.integrations.host.drain_hook_spool import run as drain
from skm.modules.integrations.host.host_subscriptions import SubscriptionState, run_host_subscriptions
from skm.platform.config.secrets import SecretResolvers
from skm.platform.config.store import ConfigStore, ScopeTree

from ._hook_support import _host, _RoutingWorld, _webhook_cfg, configured_host_subscription
from ._hook_support import clean_test_database as clean_test_database
from ._hook_support import pg_session as pg_session
from ._hook_support import test_database as test_database
from ._hook_support import world as world
from .test_hooks import hook_env as hook_env
from .test_host_projection import env as env


def _relay(world: _RoutingWorld, sink: object) -> None:
    from skm.modules.settings.public import SetValue

    with world.uow_factory(world._meta(), readonly=True) as unit:
        instance = unit.repo(ScopeRegistry).instance().id
    for key in ("allow_http_loopback", "allow_private_networks"):
        world.dispatch(
            SetValue.from_json(
                {
                    "scope": {"level": "instance", "scope_id": str(instance)},
                    "key": "hooks.webhook." + key,
                    "value": True,
                    "reason": "local delivery server",
                    "confirmed": True,
                }
            )
        )
    if world.base.pg is not None:
        (row,) = world.base.pg.execute("SELECT clock_timestamp()")
        if row[0] > world.clock.now():
            world.clock.set(row[0])
    gateways = GatewayTable(
        {**world.gateways.entries, EventSinkRegistry: EventSinkRegistry([cast("Any", sink)])},
        "control_plane_gateway",
    )
    OutboxRelayPass(
        registry=world.registry,
        uow_factory=world.uow_factory,
        config=cast("EventConfigLoader", world.loader),
        settings=DeliverySettings,
        clock=world.clock,
        ids=world.ids,
        gateways=gateways,
        log=world.logger,
        relay_id="delivery-test",
        batch_size=200,
        secrets=cast(
            "Any",
            SecretResolvers(
                [EnvSecretResolver({"SKM_HOOK_SECRET": "signing-secret"})], on_reveal=lambda _s: None
            ),
        ),
        dispatcher=world.bus,
        actor=world.system_actor,
    ).run_once()


def _sink(world: _RoutingWorld) -> WebhookSink:
    return WebhookSink(
        http=PinnedHttpClient(),
        settings={"allow_http_loopback": True, "allow_private_networks": True},
        clock=world.clock,
        version="test",
    )


def _entries(world: _RoutingWorld, workspace: Any, event: Any) -> list[Any]:
    with world.uow_factory(world._meta(), readonly=True) as uow:
        rows = uow.repo(OutboxStore).list(
            destination_prefix="hook:", state=None, workspace_id=workspace, after=None, limit=200
        )
        return [item for item in rows.items if item.event_id == event.id]


def test_real_relay_sends_after_uow_closed_and_marks_delivered(world: _RoutingWorld) -> None:
    depth = 0
    original = world.uow_factory

    @contextmanager
    def tracking(*args: Any, **kwargs: Any) -> Iterator[Any]:
        nonlocal depth
        with original(*args, **kwargs) as uow:
            depth += 1
            try:
                yield uow
            finally:
                depth -= 1

    class CheckedHttp(PinnedHttpClient):
        @override
        def post(self, *args: Any, **kwargs: Any) -> Any:
            assert depth == 0, "webhook IO must never hold a UoW"
            return super().post(*args, **kwargs)

    ws = world.create_workspace("delivery")
    with _server() as (url, requests):
        world.set_subscriptions(
            level="workspace", scope_id=ws, subscriptions={"notify": _webhook_cfg(url=url)}
        )
        event = world.emit_hookable(workspace_id=ws)
        world.uow_factory = cast("Any", tracking)
        sink = WebhookSink(
            http=CheckedHttp(),
            settings={"allow_http_loopback": True, "allow_private_networks": True},
            clock=world.clock,
            version="test",
        )
        _relay(world, sink)
        _relay(world, sink)
        (entry,) = _entries(world, ws, event)
        assert entry.state is OutboxState.DELIVERED
        assert len(requests) == 1
        assert json.loads(requests[0]["body"])["delivery_id"] == str(entry.id)
        assert requests[0]["headers"]["SKM-Attempt"] == "1"


def test_relay_retry_backoff_dead_and_failure_event_are_durable(world: _RoutingWorld) -> None:
    ws = world.create_workspace("retry")
    with _server(503, b"backend-down", "2") as (url, requests):
        config = _webhook_cfg(url=url)
        config["retry"] = {"max_attempts": 2, "backoff": {"initial_ms": 100, "factor": 2.0, "max_ms": 5000}}
        world.set_subscriptions(level="workspace", scope_id=ws, subscriptions={"notify": config})
        event = world.emit_hookable(workspace_id=ws)
        sink = _sink(world)
        _relay(world, sink)
        _relay(world, sink)
        (first,) = _entries(world, ws, event)
        assert first.state is OutboxState.FAILED
        assert first.attempts == 1
        assert first.available_at >= world.clock.now() + timedelta(seconds=1)
        assert len(requests) == 1
        world.clock.advance(timedelta(seconds=3))
        _relay(world, sink)
        _relay(world, sink)
        (last,) = _entries(world, ws, event)
        assert last.state is OutboxState.DEAD
        assert last.attempts == 2
        assert last.last_error == "http_503"
        assert len(requests) == 2
        assert requests[0]["headers"]["SKM-Delivery-Id"] == requests[1]["headers"]["SKM-Delivery-Id"]
        with world.uow_factory(world._meta(), readonly=True) as uow:
            events = uow.repo(EventReader).after_workspace_seq(
                ws, 0, types=frozenset({HookDeliveryFailed.event_type}), limit=50
            )
        assert len(events) == 1
        assert events[0].payload["status"] == 503
        assert events[0].payload["blocking"] is False


def test_current_deleted_disabled_or_host_subscription_never_sends(world: _RoutingWorld) -> None:
    ws = world.create_workspace("gone")
    with _server() as (url, requests):
        world.set_subscriptions(
            level="workspace", scope_id=ws, subscriptions={"notify": _webhook_cfg(url=url)}
        )
        event = world.emit_hookable(workspace_id=ws)
        # Route once using the subscriber, then remove before the consumer prepares.
        with world.uow_factory(world._meta()) as uow:
            from skm.kernel.ids import ScopeId
            from skm.modules.integrations.application.subscribers import fan_out_hook_deliveries

            cfg = world.loader.effective(
                uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.WORKSPACE, ScopeId(ws))
            )
            ctx = SubscriberContext(
                CONSUMER_ID, 1, world.clock, world.ids, world.logger, cfg, world.gateways, lambda _scope: cfg
            )
            fan_out_hook_deliveries(event, ctx, uow)
            uow.commit()
        world.set_subscriptions(level="workspace", scope_id=ws, subscriptions={})
        _relay(world, _sink(world))
        assert not requests
        (entry,) = _entries(world, ws, event)
        assert entry.state is OutboxState.DELIVERED
    assert HOOK_CONSUMER.prefix == "hook"
    assert HookDeliveryConsumer is not None


@pytest.mark.parametrize("change", ["untrusted", "argv", "timeout", "environment"])
def test_untrusted_or_changed_digest_command_never_runs(tmp_path: Path, change: str) -> None:
    marker = tmp_path / "executed"
    ctx, policy, event = _host(
        tmp_path, code=f"open({str(marker)!r}, 'w').write('ran')", trusted=change != "untrusted"
    )
    if change != "untrusted":
        # A real reparse recomputes digest for each effective configuration change.
        row = dict(policy["subscriptions"][0])
        raw = {
            "class": row["class"],
            "kind": "command",
            "execution_location": "host",
            "event_types": row["event_types"],
            "target": {key: row[key] for key in ("argv", "cwd", "env_allow", "env_refs")},
            "timeout_ms": row["timeout_ms"],
            "retry": row["retry"],
            "failure_policy": row["failure_policy"],
        }
        if change == "argv":
            raw["target"]["argv"] = [*raw["target"]["argv"], "changed"]
        elif change == "timeout":
            raw["timeout_ms"] += 1
        else:
            raw["target"]["env_allow"] = ["LANG"]
        parsed, errors = parse_subscriptions(cast("Any", {"audit": raw}), {"audit": "project"})
        assert not errors
        row["digest"] = parsed[0].digest
        policy["subscriptions"] = [row]
    decision = run_host_subscriptions(event, HookClass.ENFORCEMENT, policy, ctx, 1000)
    assert decision.verdict is HookVerdict.ASK
    assert not marker.exists()
    audit = json.loads((tmp_path / "hooks/audit.jsonl").read_text())
    assert audit["status"] == "untrusted"
    assert "command" not in audit


@pytest.mark.parametrize(
    "output",
    [
        "not json",
        '{"decision":"none"}',
        '{"schema":"urn:skm:integrations:host-command-output:v1","decision":"allow"}',
        '{"schema":"urn:skm:integrations:host-command-output:v1","decision":"none","extra":1}',
    ],
)
def test_invalid_stdout_is_bounded_denial(tmp_path: Path, output: str) -> None:
    ctx, policy, event = _host(tmp_path, code=f"print({output!r})")
    result = run_host_subscriptions(event, HookClass.ENFORCEMENT, policy, ctx, 1000)
    assert result.verdict is HookVerdict.DENY
    assert result.reason_code == "HOOK_SUBSCRIPTION_FAILED"


def test_real_host_environment_sanitized_and_output_applied(tmp_path: Path) -> None:
    code = (
        "import json,os; print(json.dumps({'schema':'urn:skm:integrations:host-command-output:v1',"
        "'decision':'ask','reason':json.dumps(dict(os.environ))}))"
    )
    ctx, policy, event = _host(tmp_path, code=code, refs={"SAFE_SECRET": "secret://env/USER_SECRET"})
    decision = run_host_subscriptions(event, HookClass.ENFORCEMENT, policy, ctx, 1000)
    assert decision.verdict is HookVerdict.ASK
    env = json.loads(decision.user_message or "{}")
    assert "SKM_API_TOKEN" not in env
    assert env["SAFE_SECRET"] == "allowed"
    assert env["SKM_HOOK_SUBSCRIPTION_ID"] == "audit"
    assert env["CI"] == "yes"
    assert "allowed" not in (tmp_path / "hooks/audit.jsonl").read_text()


def test_process_caps_missing_command_and_timeout_kills_descendants(tmp_path: Path) -> None:
    runner = SubprocessHostCommandRunner()
    result = runner.run(
        [sys.executable, "-c", "import os; os.write(1,b'x'*200000); os.write(2,b'y'*20000)"],
        cwd=tmp_path,
        env={},
        stdin=b"",
        timeout_ms=2000,
    )
    assert result.exit_code == 0
    assert len(result.stdout) == 65536
    assert len(result.stderr) == 8192
    absent = runner.run(["/this/command/does/not/exist"], cwd=tmp_path, env={}, stdin=b"", timeout_ms=100)
    assert absent.exit_code is None
    assert absent.stderr == b"not found"
    code = "import os,time; child=os.fork(); print(child,flush=True); time.sleep(30)"
    timeout = runner.run([sys.executable, "-c", code], cwd=tmp_path, env={}, stdin=b"", timeout_ms=100)
    assert timeout.timed_out
    assert timeout.duration_ms < 1500
    child = next(int(line) for line in timeout.stdout.splitlines() if int(line) > 0)
    status = Path(f"/proc/{child}/stat")
    assert not status.exists() or status.read_text().split()[2] == "Z"


def test_budget_skips_real_command_and_observation_spool_is_bounded(tmp_path: Path) -> None:
    ctx, policy, event = _host(tmp_path, code="raise SystemExit(1)")
    result = run_host_subscriptions(event, HookClass.ENFORCEMENT, policy, ctx, 0)
    assert result.verdict is HookVerdict.DENY
    assert json.loads((tmp_path / "hooks/audit.jsonl").read_text())["status"] == "skipped_budget"
    ctx, policy, event = _host(tmp_path, cls="observation", code="raise SystemExit(1)")
    ctx = replace(ctx, config={**cast("dict", ctx.config), "hooks.host.spool_max_items": 1})
    for _ in range(2):
        assert (
            run_host_subscriptions(event, HookClass.OBSERVATION, policy, ctx, 1000).verdict
            is HookVerdict.NONE
        )
    state = ctx.gateways.get(SubscriptionState)
    pending = state.pending()
    assert len(pending) == 1
    _, entry = pending[0]
    assert entry["attempts"] == 1
    assert entry["digest"] == policy["subscriptions"][0]["digest"]

    # Refresh policy via the actual gateway request path; a changed digest must discard without replay.
    class Client:
        def ask(self, _query: object) -> object:
            return {"subscriptions": [{**policy["subscriptions"][0], "digest": "sha256:" + "0" * 64}]}

    report = drain(replace(ctx, client=cast("Any", Client())), {})
    assert report["dropped"] == 1
    assert report["replayed"] == 0
    assert not state.pending()


def test_host_parallel_limit_is_enforced_for_actual_processes(tmp_path: Path) -> None:
    code = """import fcntl,json,time
with open('counts','a+') as f:
    fcntl.flock(f,fcntl.LOCK_EX)
    f.seek(0)
    data=json.loads(f.read() or '[0,0]')
    data=[data[0]+1,max(data[1],data[0]+1)]
    f.seek(0); f.truncate(); f.write(json.dumps(data)); f.flush()
    fcntl.flock(f,fcntl.LOCK_UN)
    time.sleep(.05)
    fcntl.flock(f,fcntl.LOCK_EX)
    f.seek(0); data=json.loads(f.read()); data[0]-=1
    f.seek(0); f.truncate(); f.write(json.dumps(data)); f.flush()
"""
    ctx, policy, event = _host(tmp_path, cls="observation", code=code)
    row = policy["subscriptions"][0]
    policy["subscriptions"] = [{**row, "id": f"audit-{index}"} for index in range(4)]
    ctx = replace(
        ctx,
        config={
            "hooks.host.max_parallel": 2,
            "hooks.host.trusted": {sub["id"]: sub["digest"] for sub in policy["subscriptions"]},
        },
    )
    run_host_subscriptions(event, HookClass.OBSERVATION, policy, ctx, 1000)
    assert json.loads((tmp_path / "counts").read_text()) == [0, 2]


def test_registered_host_chain_policy_trust_revoke_retrust_and_changed_command(hook_env: Any) -> None:

    from skm.modules.integrations.host.evaluate_hook import run
    from skm.modules.integrations.host.hook_state import HookState
    from skm.modules.integrations.host.trust_hook_subscription import run as trust

    from .test_hooks import request

    prepared = configured_host_subscription(hook_env)
    env, ctx, marker = hook_env, prepared.ctx, prepared.marker
    subscription, configure, policy = prepared.subscription, prepared.configure, prepared.policy
    assert policy["subscriptions"][0]["argv"] == subscription["target"]["argv"]
    req = {**request(env, surface="custom.subscriptions"), "class": "enforcement"}
    assert run(ctx, req)["verdict"] == "ask"
    assert not marker.exists()
    payload = {"project_id": str(env.project_id), "subscription_id": "audit"}
    assert (
        trust(ctx, cast("Any", {**payload, "expected_digest": policy["subscriptions"][0]["digest"]}))[
            "trusted"
        ]
        is True
    )
    assert run(ctx, req)["verdict"] == "deny"
    assert marker.exists()
    marker.unlink()
    assert trust(ctx, cast("Any", {**payload, "revoke": True}))["trusted"] is False
    assert run(ctx, req)["verdict"] == "ask"
    assert not marker.exists()
    assert trust(ctx, cast("Any", payload))["trusted"] is True
    assert run(ctx, req)["verdict"] == "deny"
    marker.unlink()
    subscription["target"]["argv"].append("changed")
    configure()
    cached_state = ctx.gateways.get(HookState)
    (cached_state.folder / f"{env.project_id}-claude_code.json").unlink()
    assert run(ctx, req)["verdict"] == "ask"
    assert not marker.exists()


def test_spool_retries_real_process_to_exhaustion_with_backoff(tmp_path: Path) -> None:
    ctx, policy, event = _host(tmp_path, cls="observation", code="raise SystemExit(1)")
    run_host_subscriptions(event, HookClass.OBSERVATION, policy, ctx, 1000)

    class Client:
        def ask(self, _query: object) -> object:
            return policy

    report = drain(replace(ctx, client=cast("Any", Client())), {})
    assert report == {"replayed": 1, "dead": 1, "dropped": 0}
    assert not ctx.gateways.get(SubscriptionState).pending()
    audits = [json.loads(line) for line in (tmp_path / "hooks/audit.jsonl").read_text().splitlines()]
    assert [entry["status"] for entry in audits] == ["failed", "failed", "dead"]


@pytest.mark.parametrize(
    ("cls", "verdict"), [("enforcement", "deny"), ("workflow", "none"), ("observation", "none")]
)
def test_native_subscription_class_and_backend_outage(cls: str, verdict: str, tmp_path: Path) -> None:
    import io

    from skm.bootstrap.hook import evaluate, unavailable_context
    from skm.entrypoints.hook.main import _fast_parse

    tokens = [
        "PreToolUse",
        "--target",
        "claude_code",
        "--surface",
        "custom.subscriptions",
        "--project",
        str(UUID(int=3)),
        "--class",
        cls,
    ]
    args = _fast_parse(tokens)
    assert args is not None
    payload = {
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo test"},
    }
    from skm.modules.integrations.generated.host import evaluate_hook_request_from_json

    wire = {
        "target": args.target,
        "surface": args.surface,
        "project_id": args.project,
        "event_name": args.event_name,
        "payload": payload,
        "class": cls,
    }
    assert evaluate_hook_request_from_json(wire).get("class") == cls
    result = evaluate(args, io.BytesIO(json.dumps(payload).encode()), unavailable_context())
    assert result["verdict"] == verdict
    assert result["reason_code"] == "HOOK_BACKEND_UNAVAILABLE"
    assert _fast_parse([*tokens[:-1], "invalid"]) is None
    ordinary = tokens[:-2]
    ordinary[ordinary.index("custom.subscriptions")] = "lifecycle.git_guardrails"
    ordinary_args = _fast_parse(ordinary)
    assert ordinary_args is not None
    assert ordinary_args.hook_class is None


@pytest.mark.parametrize("route", ["host_operation", "cli_confirm", "cli_yes"])
def test_trust_refuses_changed_reviewed_digest_without_host_write(hook_env: Any, route: str) -> None:
    import io

    from skm.entrypoints.cli.main import Backend, main
    from skm.kernel.errors import Conflict
    from skm.kernel.generated.error_codes import ErrorCode
    from skm.modules.integrations.host.host_subscriptions import load_policy, setting
    from skm.modules.integrations.host.trust_hook_subscription import run as trust

    prepared = configured_host_subscription(hook_env)
    ctx = prepared.ctx
    reviewed = prepared.policy["subscriptions"][0]["digest"]
    before = dict(setting(ctx, "hooks.host.trusted", {}))

    def change_subscription() -> None:
        prepared.subscription["target"]["argv"].append("changed-after-preview")
        prepared.configure()

    if route == "host_operation":
        change_subscription()
        with pytest.raises(Conflict) as caught:
            trust(
                ctx,
                {
                    "project_id": str(hook_env.project_id),
                    "subscription_id": "audit",
                    "expected_digest": reviewed,
                },
            )
        assert caught.value.code is ErrorCode.VERSION_CONFLICT
    else:

        class Preview(io.StringIO):
            changed = False

            @override
            def write(self, text: str) -> int:
                if reviewed in text and not self.changed:
                    self.changed = True
                    change_subscription()
                return super().write(text)

        class TerminalInput(io.StringIO):
            @override
            def isatty(self) -> bool:
                return True

        output, errors = Preview(), io.StringIO()
        args = [
            "hooks",
            "trust",
            "audit",
            "--workspace",
            str(hook_env.ws_id),
            "--project",
            str(hook_env.project_id),
        ]
        if route == "cli_yes":
            args.append("--yes")
        code = main(
            args,
            environ={},
            stdout=output,
            stderr=errors,
            stdin=TerminalInput("yes\n"),
            backend=lambda *_args: Backend(client=ctx.client, host_factory=lambda: ctx),
        )
        assert output.changed
        assert reviewed in output.getvalue()
        assert code == 6
        assert "VERSION_CONFLICT" in errors.getvalue()
        assert ("Trust this exact host command digest?" in errors.getvalue()) == (route == "cli_confirm")
    assert load_policy(ctx, str(hook_env.project_id))["subscriptions"][0]["digest"] != reviewed
    assert dict(setting(ctx, "hooks.host.trusted", {})) == before
    assert "audit" not in setting(ctx, "hooks.host.trusted", {})
    assert not prepared.marker.exists()
