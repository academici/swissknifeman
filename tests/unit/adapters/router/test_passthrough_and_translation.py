"""Verify native bytes, upstream credentials and bidirectional protocol translation."""

import json
from typing import Any

import httpx
import pytest

from skm.adapters.runtimes.router.translator import CHAT, RESPONSES, translate_request, translate_response
from skm.entrypoints.api.router.exchange import max_response_bytes

from .conftest import AUTH, upstream


@pytest.mark.parametrize(
    ("path", "raw_reply"),
    [
        ("/messages", b'{ "content": [{"type":"text","text":"native"}], "provider_field": [1] }'),
        ("/v1/messages/count_tokens", b'{"input_tokens":0, "provider_field": true}'),
    ],
)
def test_anthropic_body_and_allowlisted_headers(
    path: str,
    raw_reply: bytes,
    router_factory: Any,
    http_router: Any,
) -> None:
    raw = b'{ "model": "model", "thinking": {"type":"enabled"}, "custom": 1 }'
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return upstream(raw_reply)

    headers = {
        **AUTH,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Anthropic-Version": "2023-06-01",
        "Anthropic-Beta": "feature",
        "Cookie": "secret-cookie",
        "X-Conversation-ID": "private-conversation",
        "x-extra": "private",
    }
    with http_router(router_factory(), handler) as client:
        response = client.post(path, content=raw, headers=headers)
    assert response.status_code == 200
    assert response.content == raw_reply
    (request,) = calls
    assert request.content == raw
    assert request.url.path == (path if path.startswith("/v1") else "/v1" + path)
    assert request.headers["x-api-key"] == "provider-key"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert request.headers["anthropic-beta"] == "feature"
    assert request.headers["accept"] == "application/json"
    assert not {"authorization", "cookie", "x-conversation-id", "x-extra"}.intersection(request.headers)


def test_operator_enforces_openrouter_zdr(router_factory: Any, http_router: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer provider-key"
        assert json.loads(request.content)["provider"] == {
            "zdr": True,
            "allow_fallbacks": False,
            "sort": "price",
        }
        return upstream(b'{"choices":[{"message":{"content":"ok"}}]}')

    state = router_factory(
        ("primary", "openrouter", "model", 1),
        extra="\n[slots.primary.provider_routing]\nzdr = true\nallow_fallbacks = false\n",
    )
    with http_router(state, handler) as client:
        response = client.post(
            CHAT,
            headers=AUTH,
            json={"model": "model", "provider": {"zdr": False, "sort": "price"}},
        )
    assert response.status_code == 200


def test_compat_translation_preserves_thinking_and_native_messages_preserve_bytes() -> None:
    thinking = {"type": "enabled"}
    body = {"model": "m", "input": "hello", "thinking": thinking}
    native = {"model": "m", "thinking": thinking}
    assert translate_request("/v1/messages", "/v1/messages", native, "m", is_compat=False) == native
    assert translate_request(RESPONSES, CHAT, body, "m", is_compat=True)["thinking"] == thinking
    assert "thinking" not in translate_request(RESPONSES, CHAT, body, "m", is_compat=False)


def test_bidirectional_translation_carries_calls_and_schema() -> None:
    body = {
        "model": "m",
        "instructions": "rules",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "hello"}]},
            {"type": "function_call", "call_id": "call_1", "name": "lookup", "arguments": '{"x":1}'},
            {"type": "function_call_output", "call_id": "call_1", "output": "yes"},
        ],
        "tools": [{"type": "function", "name": "lookup", "parameters": {"type": "object"}}],
        "text": {"format": {"type": "json_schema", "name": "answer", "schema": {"type": "object"}}},
        "max_output_tokens": 25,
    }
    chat = translate_request(RESPONSES, CHAT, body, "m", is_compat=False)
    assert chat["messages"][0] == {"role": "developer", "content": "rules"}
    assert chat["messages"][2]["tool_calls"][0]["id"] == "call_1"
    assert chat["messages"][3]["tool_call_id"] == "call_1"
    back = translate_request(CHAT, RESPONSES, chat, "m", is_compat=False)
    assert back["input"][1:] == body["input"]
    assert back["tools"] == body["tools"]
    assert back["text"] == body["text"]
    assert back["max_output_tokens"] == 25


@pytest.mark.parametrize(("path", "provider"), [(CHAT, "responses"), (RESPONSES, "chat")])
def test_translated_requests_use_the_selected_upstream_protocol(
    path: str,
    provider: str,
    router_factory: Any,
    http_router: Any,
) -> None:
    reply = {
        "id": "id",
        "model": "model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        request_data = json.loads(request.content)
        target = RESPONSES if path == CHAT else CHAT
        assert request.url.path == target
        assert ("input" if target == RESPONSES else "messages") in request_data
        return upstream(json.dumps(translate_response(CHAT, target, reply)).encode())

    state = router_factory(("primary", provider, "model", 1))
    body = (
        {"model": "model", "messages": [{"role": "user", "content": "hello"}]}
        if path == CHAT
        else {
            "model": "model",
            "input": "hello",
        }
    )
    with http_router(state, handler) as client:
        response = client.post(path, headers=AUTH, json=body)
    assert response.status_code == 200
    assert response.json()["id"] == "id"
    assert response.json()["usage"]["total_tokens"] == 5


def test_serialized_chat_to_responses_body_must_fit_response_limit(
    router_factory: Any, http_router: Any
) -> None:
    prefix = b'{"id":"primary","choices":[{"message":{"content":"'
    suffix = b'"}}]}'
    chat = prefix + b"x" * (max_response_bytes - len(prefix) - len(suffix)) + suffix
    backup = b'{"id":"backup","output":[{"type":"message"}]}'
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return upstream(chat if request.url.host == "one.example" else backup)

    state = router_factory(("one", "chat", "m", 1), ("two", "responses", "m", 2))
    with http_router(state, handler) as client:
        result = client.post(RESPONSES, headers=AUTH, json={"model": "m", "input": "hi"})
    assert result.status_code == 200
    assert result.content == backup
    assert calls == ["one.example", "two.example"]


@pytest.mark.parametrize(("path", "provider"), [(CHAT, "responses"), (RESPONSES, "chat")])
def test_translated_sse_emits_the_requested_protocol(
    path: str,
    provider: str,
    router_factory: Any,
    http_router: Any,
) -> None:
    chat = b'data: {"id":"id","model":"model","choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n'
    responses = (
        b'event: response.created\ndata: {"type":"response.created","response":'
        b'{"id":"id","model":"model"}}\n\n'
        b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
        b'data: {"type":"response.completed","response":{"id":"id","model":"model","output":[{}]}}\n\n'
    )
    state = router_factory(("primary", provider, "model", 1))
    body: dict[str, object] = {"model": "model", "stream": True}
    body.update({"messages": [{"role": "user", "content": "hi"}]} if path == CHAT else {"input": "hi"})
    with http_router(
        state, lambda _: upstream(responses if path == CHAT else chat, media="text/event-stream")
    ) as client:
        result = client.post(path, headers=AUTH, json=body)
    assert result.status_code == 200
    assert b"hello" in result.content
    assert (b"data: [DONE]" if path == CHAT else b"event: response.completed") in result.content


def test_untranslated_function_call_and_bookkeeping_frames_do_not_commit_sse(
    router_factory: Any, http_router: Any
) -> None:
    empty = (
        b'data: {"id":"primary","choices":[{"delta":{"function_call":{"name":"ignored"}}}]}\n\n'
        b'data: {"choices":[],"usage":{"total_tokens":1}}\n\n'
        b"data: [DONE]\n\n"
    )
    backup = b'data: {"id":"backup","choices":[{"delta":{"content":"backup text"}}]}\n\ndata: [DONE]\n\n'
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return upstream(empty if request.url.host == "one.example" else backup, media="text/event-stream")

    state = router_factory(("one", "chat", "m", 1), ("two", "chat", "m", 2))
    with http_router(state, handler) as client:
        result = client.post(RESPONSES, headers=AUTH, json={"model": "m", "input": "hi", "stream": True})
    assert result.status_code == 200
    assert b'"delta":"backup text"' in result.content
    assert b'"id":"primary"' not in result.content
    assert calls == ["one.example", "two.example"]


def test_oauth_token_file_is_reread_after_rotation(
    router_factory: Any, http_router: Any, tmp_path: Any
) -> None:
    token_file = tmp_path / "oauth.json"
    token_file.write_text('{"access_token":"first-token"}')
    token_file.chmod(0o600)
    state = router_factory(
        extra=f"""
[slots.oauth]
runtime_id = "codex"
transport = "oauth_gateway"
provider = "anthropic"
base_url = "https://oauth.example/"
token_file = "{token_file}"
models = [{{name = "oauth-model", is_compat = false}}]
"""
    )
    auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth.append(request.headers["authorization"])
        return upstream(b'{"input_tokens":3}')

    with http_router(state, handler) as client:
        for secret in ("first-token", "second-token"):
            token_file.write_text(json.dumps({"access_token": secret}))
            response = client.post("/v1/messages/count_tokens", headers=AUTH, json={"model": "oauth-model"})
            assert response.json() == {"input_tokens": 3}
    assert auth == ["Bearer first-token", "Bearer second-token"]
