"""Failover and in-flight sharing must preserve protocol and conversation boundaries."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from skm.adapters.runtimes.pool.failover import FailoverPolicy
from skm.adapters.runtimes.pool.provider_pool import ProviderSlot, SlotModel
from skm.adapters.runtimes.router.cli_bridge import CliRequest, CliResult
from skm.adapters.runtimes.router.dedup import Inflight, dedup_key
from skm.adapters.runtimes.router.scheduler import Route, Scheduler
from skm.bootstrap.router import CHAT, COUNT, MESSAGES, RESPONSES, RouterGeneration
from skm.entrypoints.api.router.exchange import max_response_bytes, max_sse_event_bytes

from .conftest import AUTH, asgi_client, upstream

_HOT_POOL_SLOT = """
[slots.cli]
runtime_id = "claude_code"
transport = "cli_subprocess"
tier = 1
worker_mode = "hot_pool"
models = [{name = "m", is_compat = false}]
"""


def test_claude_code_model_suffix_identifies_the_hot_pool_conversation(
    router_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = router_factory(extra=_HOT_POOL_SLOT)
    work: list[CliRequest] = []

    def run(request: CliRequest, _: Event) -> CliResult:
        work.append(request)
        return CliResult("hot pool")

    with state.lease() as generation:
        assert generation.cli is not None
        monkeypatch.setattr(generation.cli, "run", run)
    messages = [{"role": "user", "content": "hello"}]
    with asgi_client(state) as client:
        aliased = client.post(CHAT, headers=AUTH, json={"model": "claude-code:turn-23", "messages": messages})
        named = client.post(
            CHAT, headers={**AUTH, "X-Conversation-ID": "turn-23"}, json={"model": "m", "messages": messages}
        )
    assert aliased.status_code == named.status_code == 200
    assert [(call.hot, call.model, call.conversation_id) for call in work] == [(True, "m", "turn-23")] * 2


def test_stateless_request_skips_tier_one_hot_pool(router_factory: Any, http_router: Any) -> None:
    state = router_factory(("remote", "anthropic", "m", 2), extra=_HOT_POOL_SLOT)
    calls: list[str] = []
    body = b'{"content":[{"type":"text","text":"HTTP backup"}]}'

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return upstream(body)

    with http_router(state, handler) as client:
        response = client.post(MESSAGES, headers=AUTH, json={"model": "m"})
    assert response.status_code == 200
    assert response.content == body
    assert calls == ["remote.example"]


@pytest.mark.parametrize(
    ("path", "provider", "bad", "good"),
    [
        (CHAT, "openai", b'{"choices":[]}', b'{"choices":[{"message":{"content":"ok"}}]}'),
        (
            CHAT,
            "openai",
            b'{"choices":[{"message":{"content":""}}]}',
            b'{"choices":[{"message":{"content":null,"tool_calls":[{"id":"call"}]}}]}',
        ),
        (MESSAGES, "anthropic", b'{"content":[]}', b'{"content":[{"type":"text","text":"ok"}]}'),
        (RESPONSES, "openai", b'{"output":[]}', b'{"output":[{"type":"message"}]}'),
        (COUNT, "anthropic", b'{"input_tokens":true}', b'{"input_tokens":0}'),
        (COUNT, "anthropic", b'{"input_tokens":-1}', b'{"input_tokens":0}'),
        (COUNT, "anthropic", b'{"input_tokens":1.0}', b'{"input_tokens":0}'),
        (COUNT, "anthropic", b"{}", b'{"input_tokens":0}'),
        (RESPONSES, "openai", b"{oops", b'{"output":[{"type":"message"}]}'),
    ],
)
def test_invalid_200_falls_through_all_four_protocols(
    path: str,
    provider: str,
    bad: bytes,
    good: bytes,
    router_factory: Any,
    http_router: Any,
) -> None:
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.host)
        return upstream(bad if len(calls) == 1 else good)

    state = router_factory(("z-first", provider, "m", 1), ("a-second", provider, "m", 2))
    with http_router(state, handler) as client:
        result = client.post(path, headers=AUTH, json={"model": "m"})
    assert result.content == good
    assert result.status_code == 200
    assert calls == ["z-first.example", "a-second.example"]


FIRST = b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
LAST = b"data: [DONE]\n\n"


@pytest.mark.parametrize(
    ("bad", "committed"),
    [
        (b"data: [DONE]\n\n", False),
        (b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n' + LAST, False),
        (b":" + b"x" * max_sse_event_bytes + b"\n\n", False),
        ((b":" + b"x" * (max_sse_event_bytes // 2) + b"\n") * 2 + b"\n", False),
        (FIRST + b"data: {broken\n\n", True),
        (FIRST + b":" + b"x" * max_sse_event_bytes + b"\n\n", True),
    ],
    ids=["empty", "role-only", "line-limit", "event-limit", "committed-malformed", "committed-large"],
)
def test_sse_fallback_only_before_a_valid_event(
    bad: bytes,
    committed: bool,
    router_factory: Any,
    http_router: Any,
) -> None:
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.host)
        return upstream(bad if len(calls) == 1 else FIRST + LAST, media="text/event-stream")

    state = router_factory(("one", "chat", "m", 1), ("two", "chat", "m", 2))
    with http_router(state, handler) as client:
        result = client.post(CHAT, headers=AUTH, json={"model": "m", "stream": True})
    assert result.status_code == 200
    assert result.content == (FIRST if committed else FIRST + LAST)
    assert calls == (["one.example"] if committed else ["one.example", "two.example"])


def test_nonstream_buffer_limit(router_factory: Any, http_router: Any) -> None:
    count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return upstream(b" " * (max_response_bytes + 1) if count == 1 else b'{"input_tokens":4}')

    state = router_factory(("one", "anthropic", "m", 1), ("two", "anthropic", "m", 2))
    with http_router(state, handler) as client:
        result = client.post(COUNT, headers=AUTH, json={"model": "m"})
    assert result.json() == {"input_tokens": 4}
    assert count == 2


def test_signed_hop_excludes_all_cli_choices() -> None:
    model = SlotModel("m")
    cli = Route(ProviderSlot("claude_code", "cli"), model)
    http = Route(ProviderSlot("codex", "http", tier=2, transport="http_api"), model)
    scheduler = Scheduler(FailoverPolicy(), 0)
    scheduler.pin(("one", "conversation"), cli)
    assert scheduler.candidates((http, cli), ("one", "conversation"), internal=False) == (cli, http)
    assert scheduler.candidates((http, cli), ("one", "conversation"), internal=True) == (http,)


def test_retry_does_not_record_a_cooldown_for_a_burst_and_quota_does() -> None:
    route = Route(ProviderSlot("codex", "one", transport="http_api"), SlotModel("m"))
    scheduler = Scheduler(FailoverPolicy(), 2)
    assert scheduler.retry_delay(route, {"retry-after": "1"}, "", 1, 0) == 1
    assert scheduler.cooldowns() == {}
    assert scheduler.retry_delay(route, {"retry-after": "1"}, "weekly limit", 2, 1) is None
    assert not scheduler.eligible(route)
    assert tuple(scheduler.cooldowns()) == ("one",)


def test_dedup_key_and_independent_subscriber_release() -> None:
    first = dedup_key("client", "POST", CHAT, "m", {"stream": True, "model": "m"}, {})
    assert first == dedup_key("client", "POST", CHAT, "m", {"model": "m", "stream": True}, {})
    assert first != dedup_key("other", "POST", CHAT, "m", {"model": "m", "stream": True}, {})
    assert dedup_key("client", "POST", CHAT, "m", {}, {"x-conversation-id": "one"}) is None
    assert dedup_key("client", "POST", CHAT, "m", {}, {"x-conversation-id": "two"}) is None
    assert dedup_key("client", "POST", CHAT, "claude-code:abc", {}, {}) is None
    assert dedup_key("client", "POST", CHAT, "m", {}, {}, hot_pool=True) is None
    flights: Inflight[object] = Inflight()
    one, leave_one = flights.acquire(first, object, bool)
    two, leave_two = flights.acquire(first, object, bool)
    assert one is two
    assert not leave_one()
    assert leave_two()


def test_two_conversations_with_same_body_launch_two_requests(
    router_factory: Any,
    http_router: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = RouterGeneration.upstream
    barrier = Barrier(2)
    calls: list[str] = []

    def delayed(generation: RouterGeneration, route: Route) -> Any:
        barrier.wait(timeout=4)
        return original(generation, route)

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.host)
        return upstream(b'{"content":[{"type":"text","text":"ok"}]}')

    monkeypatch.setattr(RouterGeneration, "upstream", delayed)
    with http_router(router_factory(), handler) as client, ThreadPoolExecutor(max_workers=2) as pool:
        pending = [
            pool.submit(
                client.post, MESSAGES, json={"model": "model"}, headers={**AUTH, "x-conversation-id": name}
            )
            for name in ("first", "second")
        ]
        assert [item.result(timeout=6).status_code for item in pending] == [200, 200]
    assert len(calls) == 2


def test_concurrent_stateless_requests_share_upstream(
    router_factory: Any,
    http_router: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = RouterGeneration.upstream
    release = Event()
    entered = Event()
    joined = Event()
    lock = Lock()
    active = 0
    calls = 0
    original_acquire = Inflight.acquire

    def delayed(generation: RouterGeneration, route: Route) -> Any:
        entered.set()
        assert release.wait(4)
        return original(generation, route)

    def acquire(inflight: Inflight[Any], *args: Any) -> Any:
        nonlocal active
        result = original_acquire(inflight, *args)
        with lock:
            active += 1
            if active == 2:
                joined.set()
        return result

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return upstream(b'{"content":[{"type":"text","text":"ok"}]}')

    monkeypatch.setattr(RouterGeneration, "upstream", delayed)
    monkeypatch.setattr(Inflight, "acquire", acquire)
    with http_router(router_factory(), handler) as client, ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(client.post, MESSAGES, headers=AUTH, json={"model": "model", "stream": False})
        assert entered.wait(4)
        two = pool.submit(client.post, MESSAGES, headers=AUTH, json={"stream": False, "model": "model"})
        try:
            assert joined.wait(4)
        finally:
            release.set()
        assert one.result(timeout=4).content == two.result(timeout=4).content
    assert calls == 1


def test_one_retry_holder_per_slot() -> None:
    route = Route(ProviderSlot("codex", "one", transport="http_api"), SlotModel("m"))
    scheduler = Scheduler(FailoverPolicy(), 2)
    first, other = object(), object()
    assert scheduler.retry_delay(route, {"retry-after": "2"}, "", 1, 0, first) == 2
    assert scheduler.eligible(route, first)
    assert not scheduler.eligible(route, other)
    assert scheduler.candidates((route,), None, internal=False) == ()
    assert scheduler.retry_delay(route, {"retry-after": "2"}, "", 1, 0, other) is None
    scheduler.release_hold(route, other)
    assert not scheduler.eligible(route)
    scheduler.release_hold(route, first)
    assert scheduler.eligible(route, other)


@pytest.mark.parametrize(("consent", "status"), [(True, 200), (False, 502)])
def test_floor_model_requires_configured_failover_policy(
    consent: bool,
    status: int,
    router_factory: Any,
    http_router: Any,
) -> None:
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.host)
        if len(calls) < 3:
            return upstream(b'{"choices":[]}')
        assert req.url.host == "floor.example"
        assert json.loads(req.content)["model"] == "floor-model"
        return upstream(b'{"choices":[{"message":{"content":"floor"}}]}')

    state = router_factory(
        ("first", "chat", "original", 1),
        ("second", "chat", "original", 2),
        ("floor", "chat", "floor-model", 2),
        overrides='floor_model = "floor-model"\n',
        extra=f"""
[router.floor_pricing]
input_per_mtok_usd = "1"
output_per_mtok_usd = "1"
currency = "USD"
verified_at = "2026-11-01"
source = "operator"
[router.failover]
enabled = true
explicit_consent = {str(consent).lower()}
tos_acknowledged = true
fresh_session = true
cost_ceiling_usd_micros = 10000
""",
    )
    with http_router(state, handler) as client:
        response = client.post(CHAT, headers=AUTH, json={"model": "original", "max_tokens": 20})
    assert response.status_code == status
    assert calls == ["first.example", "second.example"] + (["floor.example"] if consent else [])


def test_disconnected_subscriber_leaves_shared_upstream_running(
    router_factory: Any,
    http_router: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allow_upstream = Event()
    both_subscribed = Event()
    first_subscribed = Event()
    subscriptions = calls = 0
    original_upstream, original_acquire = RouterGeneration.upstream, Inflight.acquire

    def delayed(generation: RouterGeneration, route: Route) -> Any:
        assert allow_upstream.wait(4)
        return original_upstream(generation, route)

    def acquire(inflight: Inflight[Any], *args: Any) -> Any:
        nonlocal subscriptions
        result = original_acquire(inflight, *args)
        subscriptions += 1
        (first_subscribed if subscriptions == 1 else both_subscribed).set()
        return result

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return upstream(FIRST + LAST, media="text/event-stream")

    monkeypatch.setattr(RouterGeneration, "upstream", delayed)
    monkeypatch.setattr(Inflight, "acquire", acquire)
    state = router_factory(("primary", "chat", "m", 1))
    with http_router(state, handler) as client:
        portal = client.portal
        assert portal is not None
        scope = {
            "type": "http",
            "method": "POST",
            "path": CHAT,
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [(b"authorization", b"Bearer client-one")],
        }

        def begin() -> tuple[Any, Any, list[dict[str, Any]]]:
            inbox = portal.call(asyncio.Queue)
            portal.call(
                inbox.put_nowait,
                {
                    "type": "http.request",
                    "body": b'{"model":"m","stream":true}',
                    "more_body": False,
                },
            )
            received: list[dict[str, Any]] = []
            task = portal.start_task_soon(
                client.app, scope.copy(), inbox.get, AsyncMock(side_effect=received.append)
            )
            return task, inbox, received

        try:
            first, disconnected, _ = begin()
            assert first_subscribed.wait(3)
            second, _, messages = begin()
            assert both_subscribed.wait(3)
            portal.call(disconnected.put_nowait, {"type": "http.disconnect"})
            first.result(timeout=3)
            assert not second.done()
        finally:
            allow_upstream.set()
        second.result(timeout=3)
        assert b"".join(item.get("body", b"") for item in messages) == FIRST + LAST
    assert calls == 1
