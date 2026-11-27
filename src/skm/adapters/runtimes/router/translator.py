"""Translate OpenAI request and response shapes while preserving native wire bodies."""

from __future__ import annotations

import json
from typing import Any, TypeGuard, cast

__all__ = [
    "CHAT",
    "COUNT",
    "MESSAGES",
    "RESPONSES",
    "cli_prompt",
    "cli_result",
    "json_schema",
    "translate_request",
    "translate_response",
    "upstream_path",
]

CHAT = "/v1/chat/completions"
RESPONSES = "/v1/responses"
MESSAGES = "/v1/messages"
COUNT = "/v1/messages/count_tokens"
_THINKING = ("thinking", "reasoning_content", "reasoning_details")


def upstream_path(protocol: str, path: str) -> str | None:
    if protocol == "anthropic":
        return path if path in (MESSAGES, COUNT) else None
    if protocol == "openrouter" and path == MESSAGES:
        return path
    if path not in (CHAT, RESPONSES):
        return None
    return {"chat": CHAT, "responses": RESPONSES}.get(protocol, path)


def _object(value: object) -> TypeGuard[dict[str, Any]]:
    return isinstance(value, dict)


def _items(value: object) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def _parts(value: Any, *, to_chat: bool, assistant: bool = False) -> Any:
    if not isinstance(value, list):
        return value
    parts: list[dict[str, Any]] = []
    for item in cast("list[Any]", value):
        match item:
            case {"type": "input_text" | "output_text", "text": str(text)} if to_chat:
                parts.append({"type": "text", "text": text})
            case {"type": "input_image", "image_url": str(url)} if to_chat:
                parts.append(
                    {"type": "image_url", "image_url": {"url": url, "detail": item.get("detail", "auto")}}
                )
            case {"type": "text", "text": str(text)} if not to_chat:
                parts.append(
                    {
                        "type": "output_text" if assistant else "input_text",
                        "text": text,
                        **({"annotations": []} if assistant else {}),
                    }
                )
            case {"type": "image_url", "image_url": {"url": str(url)} as image} if not to_chat:
                parts.append({"type": "input_image", "image_url": url, "detail": image.get("detail", "auto")})
            case _:
                raise ValueError("unsupported message content part")
    return parts


def _thinking(fields: dict[str, Any], is_compat: bool) -> dict[str, Any]:
    return {key: fields[key] for key in _THINKING if key in fields} if is_compat else {}


def _chat_messages(body: dict[str, Any], *, is_compat: bool = False) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if isinstance(body.get("instructions"), str):
        messages.append({"role": "developer", "content": body["instructions"]})
    inputs = body.get("input")
    if isinstance(inputs, str):
        return [*messages, {"role": "user", "content": inputs}]
    if not isinstance(inputs, list):
        raise ValueError("invalid Responses input")
    for item in cast("list[Any]", inputs):
        match item:
            case {"type": "function_call_output", "call_id": str(call), "output": output}:
                messages.append({"role": "tool", "tool_call_id": call, "content": output})
            case {"type": "function_call", "call_id": str(call), "name": str(name), "arguments": str(args)}:
                tool = {"id": call, "type": "function", "function": {"name": name, "arguments": args}}
                if messages and messages[-1].get("role") == "assistant" and messages[-1].get("tool_calls"):
                    messages[-1]["tool_calls"].append(tool)
                else:
                    messages.append({"role": "assistant", "tool_calls": [tool]})
            case {"role": str(role), "content": content}:
                messages.append(
                    {"role": role, "content": _parts(content, to_chat=True), **_thinking(item, is_compat)}
                )
            case _:
                raise ValueError("unsupported Responses input item")
    return messages


def _response_items(messages: object, *, is_compat: bool) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        raise ValueError("invalid Chat messages")
    result: list[dict[str, Any]] = []
    for message in cast("list[Any]", messages):
        match message:
            case {"role": "tool", "tool_call_id": str(call), "content": content}:
                result.append({"type": "function_call_output", "call_id": call, "output": content})
            case {"role": str(role)}:
                if message.get("content") is not None:
                    parts = _parts(message["content"], to_chat=False, assistant=role == "assistant")
                    result.append({"role": role, "content": parts, **_thinking(message, is_compat)})
                for tool in _items(message.get("tool_calls")):
                    if not _object(tool) or not _object(tool.get("function")):
                        raise ValueError("unsupported Chat tool call")
                    result.append({"type": "function_call", "call_id": tool["id"], **tool["function"]})
            case _:
                raise ValueError("unsupported Chat message")
    return result


def _tool(tool: Any, *, to_chat: bool) -> dict[str, Any]:
    if not _object(tool) or tool.get("type") != "function":
        raise ValueError("only function tools can be translated")
    if to_chat:
        return {"type": "function", "function": {key: val for key, val in tool.items() if key != "type"}}
    if not _object(tool.get("function")):
        raise ValueError("invalid function tool")
    return {"type": "function", **tool["function"]}


def translate_request(
    source: str,
    target: str,
    body: dict[str, Any],
    model: str,
    *,
    is_compat: bool,
) -> dict[str, Any]:
    if source == target:
        return {**body, "model": model}
    return {**_openai_request(body, to_chat=target == CHAT, is_compat=is_compat), "model": model}


def _openai_request(body: dict[str, Any], *, to_chat: bool, is_compat: bool) -> dict[str, Any]:
    if (
        body.get("previous_response_id")
        or body.get("conversation")
        or (not to_chat and body.get("n", 1) != 1)
    ):
        raise ValueError("stateful or multi-choice request requires its native protocol")
    output = {
        key: body[key]
        for key in (
            "model",
            "stream",
            "temperature",
            "top_p",
            "metadata",
            "store",
            "parallel_tool_calls",
            "service_tier",
            "user",
            "provider",
        )
        if key in body
    }
    output.update(_thinking(body, is_compat))
    if to_chat:
        output["messages"] = _chat_messages(body, is_compat=is_compat)
        if "max_output_tokens" in body:
            output["max_completion_tokens"] = body["max_output_tokens"]
        if _object(body.get("text")) and _object(fmt := body["text"].get("format")):
            output["response_format"] = (
                {"type": "json_schema", "json_schema": {k: v for k, v in fmt.items() if k != "type"}}
                if fmt.get("type") == "json_schema"
                else fmt
            )
    else:
        output["input"] = _response_items(body.get("messages"), is_compat=is_compat)
        if "max_completion_tokens" in body or "max_tokens" in body:
            output["max_output_tokens"] = body.get("max_completion_tokens", body.get("max_tokens"))
        if _object(fmt := body.get("response_format")):
            output["text"] = {
                "format": (
                    {"type": "json_schema", **fmt["json_schema"]} if _object(fmt.get("json_schema")) else fmt
                )
            }
    if "tools" in body:
        output["tools"] = [_tool(tool, to_chat=to_chat) for tool in _items(body["tools"])]
    if "tool_choice" in body:
        choice = body["tool_choice"]
        output["tool_choice"] = _tool(choice, to_chat=to_chat) if _object(choice) else choice
    return output


def _usage(body: dict[str, Any], *, to_chat: bool) -> dict[str, Any]:
    usage = body.get("usage")
    if not _object(usage):
        return {}
    if to_chat:
        names = (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"))
    else:
        names = (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens"))
    mapped = {target: usage.get(source, 0) for source, target in names}
    mapped["total_tokens"] = usage.get("total_tokens", sum(mapped.values()))
    return mapped


def _to_chat(body: dict[str, Any], *, is_compat: bool) -> dict[str, Any]:
    text: list[str] = []
    refusal: list[str] = []
    tools: list[dict[str, Any]] = []
    thinking: dict[str, Any] = {}
    for item in _items(body.get("output")):
        match item:
            case {"type": "message", "content": parts}:
                thinking.update(_thinking(item, is_compat))
                for part in _items(parts):
                    match part:
                        case {"type": "output_text", "text": str(piece)}:
                            text.append(piece)
                        case {"type": "refusal", "refusal": str(piece)}:
                            refusal.append(piece)
                        case _:
                            pass
            case {"type": "function_call", "call_id": str(call), "name": str(name), "arguments": str(args)}:
                tools.append({"id": call, "type": "function", "function": {"name": name, "arguments": args}})
            case {"type": "reasoning"} if is_compat:
                thinking.setdefault("reasoning_details", []).append(item)
            case _:
                pass
    message: dict[str, Any] = {"role": "assistant", "content": "".join(text) or None, **thinking}
    if refusal:
        message["refusal"] = "".join(refusal)
    if tools:
        message["tool_calls"] = tools
    finish = "tool_calls" if tools else "length" if body.get("status") == "incomplete" else "stop"
    return {
        "id": body.get("id"),
        "object": "chat.completion",
        "model": body.get("model"),
        "created": body.get("created_at", 0),
        "usage": _usage(body, to_chat=True),
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
    }


def _to_responses(body: dict[str, Any], *, is_compat: bool) -> dict[str, Any]:
    output: list[dict[str, Any]] = []
    status = "completed"
    for choice in _items(body.get("choices")):
        if not _object(choice) or not _object(message := choice.get("message")):
            continue
        if choice.get("finish_reason") == "length":
            status = "incomplete"
        content: list[dict[str, Any]] = []
        if isinstance(text := message.get("content"), str) and text:
            content.append({"type": "output_text", "text": text, "annotations": []})
        if isinstance(refusal := message.get("refusal"), str) and refusal:
            content.append({"type": "refusal", "refusal": refusal})
        if content:
            output.append(
                {
                    "id": f"{body.get('id')}_message_{choice.get('index', 0)}",
                    "type": "message",
                    "role": "assistant",
                    "status": status,
                    "content": content,
                    **_thinking(message, is_compat),
                }
            )
        output.extend(
            {
                "type": "function_call",
                "id": tool.get("id"),
                "call_id": tool.get("id"),
                "status": status,
                **tool["function"],
            }
            for tool in _items(message.get("tool_calls"))
            if _object(tool) and _object(tool.get("function"))
        )
    return {
        "id": body.get("id"),
        "object": "response",
        "model": body.get("model"),
        "status": status,
        "created_at": body.get("created", 0),
        "output": output,
        "usage": _usage(body, to_chat=False),
    }


def translate_response(
    source: str, target: str, body: dict[str, Any], *, is_compat: bool = False
) -> dict[str, Any]:
    if source == target:
        return body
    return _to_chat(body, is_compat=is_compat) if target == CHAT else _to_responses(body, is_compat=is_compat)


def json_schema(path: str, body: dict[str, Any]) -> dict[str, Any] | bool | None:
    fmt: object = body.get("response_format")
    if path == RESPONSES and _object(body.get("text")):
        fmt = body["text"].get("format")
    elif path == MESSAGES and _object(body.get("output_config")):
        fmt = body["output_config"].get("format")
    if not _object(fmt) or fmt.get("type") != "json_schema":
        return None
    wrapped = fmt.get("json_schema")
    schema: object = wrapped.get("schema") if _object(wrapped) else fmt.get("schema")
    if _object(schema) or isinstance(schema, bool):
        return schema
    raise ValueError("missing JSON Schema")


def cli_prompt(path: str, body: dict[str, Any], *, latest_only: bool) -> tuple[str, str]:
    messages = _chat_messages(body) if path == RESPONSES else body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("invalid CLI request messages")
    system = body.get("system", "")
    if not isinstance(system, str):
        system = json.dumps(system, ensure_ascii=False)
    turns: list[tuple[str, Any]] = []
    for message in cast("list[Any]", messages):
        match message:
            case {"role": "system" | "developer", "content": str(text)}:
                system = f"{system}\n{text}".strip()
            case {"role": str(role), "content": content}:
                turns.append((role, content))
            case _:
                raise ValueError("invalid CLI message")
    if not turns or turns[-1][0] != "user":
        raise ValueError("CLI request requires a user turn")
    last = turns[-1][1]
    if isinstance(last, str) and (latest_only or len(turns) == 1):
        return system, last
    return system, json.dumps(turns[-1:] if latest_only else turns, ensure_ascii=False)


def cli_result(
    path: str,
    model: str,
    identifier: str,
    text: str,
    refusal: bool,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    if path == MESSAGES:
        return {
            "id": identifier,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": text}],
            "stop_reason": "refusal" if refusal else "end_turn",
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        }
    message = {"role": "assistant", "content": text}
    if refusal:
        message["refusal"] = text
    chat = {
        "id": identifier,
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }
    if path == RESPONSES and refusal:
        message["content"] = ""
    return translate_response(CHAT, path, chat)
