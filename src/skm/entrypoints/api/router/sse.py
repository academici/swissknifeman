"""Bound, validate and translate inference server-sent events."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeGuard, cast

from skm.bootstrap.router import CHAT, MESSAGES, RESPONSES, translate_response

from .exchange import max_sse_event_bytes

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Iterator

__all__ = [
    "Event",
    "StreamTranslation",
    "cli_frames",
    "events",
    "frame",
    "meaningful",
    "parse_event",
    "terminal",
]

_LINE_END = re.compile(rb"\r\n|[\r\n]")


@dataclass(frozen=True, slots=True)
class Event:
    wire: bytes
    data: dict[str, Any] | None
    terminal: bool = False


def parse_event(wire: bytes) -> Event:
    data = b"\n".join(
        line[5:].removeprefix(b" ") if line.startswith(b"data:") else b""
        for line in _LINE_END.split(wire)
        if line.startswith(b"data:") or line == b"data"
    )
    if not data:
        return Event(wire, None)
    if data == b"[DONE]":
        return Event(wire, None, terminal=True)
    document: object = json.loads(data.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("invalid SSE data object")
    return Event(wire, cast("dict[str, Any]", document))


async def events(chunks: AsyncIterator[bytes]) -> AsyncGenerator[Event]:
    pending = bytearray()
    event = bytearray()
    for_final_cr = False
    async for incoming in chunks:
        chunk = b"\r" + incoming if for_final_cr else incoming
        for_final_cr = chunk.endswith(b"\r")
        end = len(chunk) - int(for_final_cr)
        start = 0
        for match in _LINE_END.finditer(chunk, 0, end):
            line_limit = match.end() - start
            if len(pending) + len(event) + line_limit > max_sse_event_bytes:
                raise ValueError("upstream SSE event exceeds its limit")
            pending.extend(chunk[start : match.end()])
            event.extend(pending)
            blank = len(pending) == len(match.group())
            pending.clear()
            start = match.end()
            if blank:
                yield parse_event(bytes(event))
                event.clear()
        if len(event) + len(pending) + end - start > max_sse_event_bytes:
            raise ValueError("upstream SSE line exceeds its limit")
        pending.extend(chunk[start:end])
    if for_final_cr:
        if len(event) + len(pending) >= max_sse_event_bytes:
            raise ValueError("upstream SSE event exceeds its limit")
        if not pending and event:
            yield parse_event(bytes(event) + b"\r")
            event.clear()
        elif pending:
            event.extend(pending)
    if pending or event:
        raise ValueError("upstream SSE event is incomplete")


def _object(value: object) -> TypeGuard[dict[str, Any]]:
    return isinstance(value, dict)


def _items(value: object) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def meaningful(path: str, event: Event) -> bool:
    data = event.data or {}
    kind = data.get("type")
    if "error" in data or kind in ("error", "response.failed", "response.cancelled"):
        raise ValueError("upstream SSE reported a failure")
    if path == CHAT:
        choices = data.get("choices")
        return any(
            _object(choice)
            and _object(delta := choice.get("delta"))
            and any(delta.get(key) for key in ("content", "tool_calls", "function_call", "refusal"))
            for choice in _items(choices)
        )
    if path == MESSAGES:
        if kind == "content_block_delta":
            delta = data.get("delta")
            return _object(delta) and any(delta.get(key) for key in ("text", "partial_json", "thinking"))
        block = data.get("content_block")
        return (
            kind == "content_block_start"
            and _object(block)
            and (block.get("type") == "tool_use" or bool(block.get("text") or block.get("thinking")))
        )
    if kind == "response.output_item.added":
        return _object(item := data.get("item")) and item.get("type") == "function_call"
    if kind in ("response.completed", "response.incomplete"):
        return _object(response := data.get("response")) and bool(response.get("output"))
    return kind in (
        "response.output_text.delta",
        "response.refusal.delta",
        "response.function_call_arguments.delta",
    ) and bool(data.get("delta"))


def terminal(path: str, event: Event) -> bool:
    kind = (event.data or {}).get("type")
    return (
        event.terminal
        or (path == MESSAGES and kind == "message_stop")
        or (path == RESPONSES and kind in ("response.completed", "response.incomplete"))
    )


def frame(data: dict[str, Any], *, named: bool = False) -> bytes:
    line = f"event: {data['type']}\n" if named else ""
    return f"{line}data: {json.dumps(data, ensure_ascii=True, separators=(',', ':'))}\n\n".encode()


class StreamTranslation:
    """Convert OpenAI deltas and terminal events between their two wire protocols."""

    def __init__(self, target: str) -> None:
        self.target = target
        self.model: str | None = None
        self.identifier: str | None = None
        self.created = 0
        self.message: dict[str, Any] | None = None
        self.tools: dict[int, dict[str, Any]] = {}
        self.usage: dict[str, Any] | None = None
        self.finish_reason: str | None = None
        self.sequence = 0
        self.started = False
        self.finished = False
        self.delivered = False
        self.parts: dict[tuple[int, int], list[str]] = {}
        self.arguments: dict[int, list[str]] = {}
        self.total_bytes = self.fragments = 0

    def convert(self, event: Event) -> Iterator[bytes]:
        if self.finished:
            return
        if self.target == CHAT:
            yield from self._as_chat(event)
        else:
            yield from self._as_responses(event)

    def _chat(self, delta: dict[str, Any], finish: str | None = None) -> bytes:
        return frame(
            {
                "object": "chat.completion.chunk",
                "id": self.identifier,
                "model": self.model,
                "created": self.created,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
        )

    def _as_chat(self, event: Event) -> Iterator[bytes]:
        data = event.data or {}
        if _object(response := data.get("response")):
            self.identifier, self.model, self.created = (
                response.get("id"),
                response.get("model"),
                response.get("created_at", 0),
            )
        kind = data.get("type")
        if kind == "response.created":
            yield self._chat({"role": "assistant"})
        elif kind in ("response.output_text.delta", "response.refusal.delta"):
            self.delivered = True
            yield self._chat(
                {"content" if kind == "response.output_text.delta" else "refusal": data["delta"]}
            )
        elif (
            kind == "response.output_item.added"
            and _object(item := data.get("item"))
            and item.get("type") == "function_call"
        ):
            self.delivered = True
            index = self.tools.setdefault(data["output_index"], {"index": len(self.tools)})["index"]
            yield self._chat(
                {
                    "tool_calls": [
                        {
                            "index": index,
                            "id": item["call_id"],
                            "type": "function",
                            "function": {"name": item["name"], "arguments": item.get("arguments", "")},
                        }
                    ]
                }
            )
        elif kind == "response.function_call_arguments.delta":
            tool = self.tools.get(data["output_index"])
            if tool is not None:
                yield self._chat(
                    {"tool_calls": [{"index": tool["index"], "function": {"arguments": data["delta"]}}]}
                )
        elif kind in ("response.completed", "response.incomplete") or event.terminal:
            if not self.delivered and _object(response) and response.get("output"):
                choice = translate_response(RESPONSES, CHAT, response)["choices"][0]
                message = choice["message"]
                if not any(message.get(field) for field in ("content", "tool_calls", "refusal")):
                    return
                yield self._chat(message)
            reason = "tool_calls" if self.tools else "length" if kind == "response.incomplete" else "stop"
            yield self._chat({}, reason)
            yield b"data: [DONE]\n\n"
            self.finished = True

    def _event(self, kind: str, **values: Any) -> bytes:
        self.sequence += 1
        return frame({"type": f"response.{kind}", "sequence_number": self.sequence - 1, **values}, named=True)

    def _response(self, status: str, output: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "object": "response",
            "model": self.model,
            "created_at": self.created,
            "status": status,
            "output": output,
            "usage": self.usage,
        }

    def _as_responses(self, event: Event) -> Iterator[bytes]:
        data = event.data or {}
        if not self.started and data.get("id"):
            self.started = True
            self.identifier, self.model, self.created = (
                data.get("id"),
                data.get("model"),
                data.get("created", 0),
            )
            yield self._event("created", response=self._response("in_progress", []))
            yield self._event("in_progress", response=self._response("in_progress", []))
        if _object(usage := data.get("usage")):
            self.usage = {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        if event.terminal:
            yield from self._complete_responses()
            return
        for choice in _items(data.get("choices")):
            self.finish_reason = choice.get("finish_reason") or self.finish_reason
            delta: dict[str, Any] = choice.get("delta") or {}
            for key in ("content", "refusal"):
                if isinstance(text := delta.get(key), str) and text:
                    yield from self._text_delta(key, text)
            for tool in _items(delta.get("tool_calls")):
                yield from self._tool_delta(tool)

    def _text_delta(self, key: str, text: str) -> Iterator[bytes]:
        if self.message is None:
            self.message = {
                "id": f"{self.identifier}_message",
                "type": "message",
                "role": "assistant",
                "status": "in_progress",
                "content": [],
                "index": len(self.tools),
            }
            yield self._event(
                "output_item.added", output_index=self.message["index"], item=self._message_item()
            )
        message = self.message
        content = message["content"]
        field = "text" if key == "content" else "refusal"
        kind = "output_text" if key == "content" else "refusal"
        index = next((i for i, part in enumerate(content) if part["type"] == kind), len(content))
        values = {"output_index": message["index"], "item_id": message["id"], "content_index": index}
        if index == len(content):
            part: dict[str, Any] = {"type": kind, field: ""}
            if key == "content":
                part["annotations"] = []
            content.append(part)
            yield self._event("content_part.added", **values, part=part)
        self._accumulate(self.parts.setdefault((message["index"], index), []), text)
        yield self._event(f"{kind}.delta", **values, delta=text)

    def _accumulate(self, parts: list[str], text: str) -> None:
        self.total_bytes += len(text.encode("utf-8"))
        self.fragments += 1
        # A translated terminal frame carries the complete output.
        if self.total_bytes > max_sse_event_bytes or self.fragments > 16_384:
            raise ValueError("translated SSE output exceeds its terminal event limit")
        parts.append(text)

    def _message_item(self) -> dict[str, Any]:
        return {k: v for k, v in (self.message or {}).items() if k != "index"}

    def _tool_delta(self, tool: dict[str, Any]) -> Iterator[bytes]:
        index = tool["index"]
        function: dict[str, Any] = tool.get("function") or {}
        if index not in self.tools:
            call = tool["id"]
            output_index = len(self.tools) + int(self.message is not None)
            item = {
                "type": "function_call",
                "id": f"fc_{call}",
                "call_id": call,
                "status": "in_progress",
                "name": function.get("name", ""),
                "arguments": "",
            }
            self.tools[index] = {"index": output_index, "item": item}
            yield self._event("output_item.added", output_index=output_index, item=item)
        entry = self.tools[index]
        if argument := function.get("arguments"):
            self._accumulate(self.arguments.setdefault(index, []), argument)
            yield self._event(
                "function_call_arguments.delta",
                output_index=entry["index"],
                item_id=entry["item"]["id"],
                delta=argument,
            )

    def _complete_responses(self) -> Iterator[bytes]:
        self.finished = True
        status = "incomplete" if self.finish_reason == "length" else "completed"
        output: dict[int, dict[str, Any]] = {}
        if (message := self.message) is not None:
            message["status"] = status
            for index, part in enumerate(message["content"]):
                key = "text" if part["type"] == "output_text" else "refusal"
                part[key] = "".join(self.parts.get((message["index"], index), ()))
                values = {"output_index": message["index"], "item_id": message["id"], "content_index": index}
                yield self._event(f"{part['type']}.done", **values, **{key: part[key]})
                yield self._event("content_part.done", **values, part=part)
            output[message["index"]] = self._message_item()
        for index, entry in self.tools.items():
            item = entry["item"]
            item["arguments"] = "".join(self.arguments.get(index, ()))
            item["status"] = status
            yield self._event(
                "function_call_arguments.done",
                output_index=entry["index"],
                item_id=item["id"],
                arguments=item["arguments"],
                name=item["name"],
            )
            output[entry["index"]] = item
        for index, item in sorted(output.items()):
            yield self._event("output_item.done", output_index=index, item=item)
        yield self._event(
            status, response=self._response(status, [output[index] for index in sorted(output)])
        )


def _text_chunks(text: str) -> Iterator[str]:
    # Keep even escaped Unicode text comfortably below the SSE event ceiling.
    for start in range(0, len(text), 16_384):
        yield text[start : start + 16_384]


def cli_frames(path: str, result: dict[str, Any]) -> Iterator[bytes]:
    if path == MESSAGES:

        def event(kind: str, **values: Any) -> bytes:
            return frame({"type": kind, **values}, named=True)

        yield event("message_start", message={**result, "content": [], "stop_reason": None})
        yield event("content_block_start", index=0, content_block={"type": "text", "text": ""})
        for text in _text_chunks(result["content"][0]["text"]):
            yield event("content_block_delta", index=0, delta={"type": "text_delta", "text": text})
        yield event("content_block_stop", index=0)
        yield event("message_delta", delta={"stop_reason": result["stop_reason"]}, usage=result["usage"])
        yield event("message_stop")
        return
    if path == RESPONSES:
        part = result["output"][0]["content"][0]
        key = "text" if part["type"] == "output_text" else "refusal"
        chat_message, base = {key: part[key]}, result
        translate = StreamTranslation(RESPONSES)
    else:
        chat_message, base = result["choices"][0]["message"], result
        translate = None
    key = "refusal" if "refusal" in chat_message else ("text" if "text" in chat_message else "content")
    base = {"id": base["id"], "object": "chat.completion.chunk", "model": base["model"]}
    deltas = [{"role": "assistant"}]
    deltas.extend({("content" if key == "text" else key): text} for text in _text_chunks(chat_message[key]))
    for delta in [*deltas, {}]:
        data = {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None if delta else "stop"}]}
        if translate is None:
            yield frame(data)
        else:
            yield from translate.convert(Event(b"", data))
    if translate is None:
        yield b"data: [DONE]\n\n"
    else:
        yield from translate.convert(Event(b"", None, terminal=True))
