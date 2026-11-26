"""Synchronous MCP stdio research with one bounded, cancellable process session."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from time import monotonic
from typing import Any, override

from skm.adapters.research.command import (
    CommandResearchSource,
    ProcessSession,
    admit_reply,
    array_value,
    decode_reply,
    object_value,
)
from skm.adapters.research.retry import SourceFailed
from skm.kernel.cancel import CancelToken
from skm.modules.context.domain.research import RawSourceReply, ResearchSourceConfig, SourceQuery

__all__ = ["McpStdioResearchSource"]


class McpStdioResearchSource(CommandResearchSource):
    kind = "mcp_stdio"

    @override
    def validate_config(self, config: ResearchSourceConfig) -> tuple[str, ...]:
        return super().validate_config(config) + (() if config.tool else ("tool",))

    @override
    def search(
        self, config: ResearchSourceConfig, query: SourceQuery, *, cancel: CancelToken
    ) -> RawSourceReply:
        session = ProcessSession(config.argv, self.environment(config), cancel, config.timeout_seconds)
        try:

            def send(message: dict[str, Any]) -> None:
                session.send(json.dumps({"jsonrpc": "2.0", **message}).encode() + b"\n")

            def response(request_id: int) -> dict[str, Any]:
                while True:
                    while b"\n" in session.stdout:
                        line, _, rest = session.stdout.partition(b"\n")
                        session.stdout[:] = rest
                        value = object_value(json.loads(line))
                        if value.get("jsonrpc") != "2.0":
                            raise SourceFailed()
                        if "id" not in value:
                            if not isinstance(value.get("method"), str):
                                raise SourceFailed()
                            continue
                        if (
                            type(value["id"]) is not int
                            or value["id"] != request_id
                            or "error" in value
                            or "result" not in value
                        ):
                            raise SourceFailed()
                        return object_value(value["result"])
                    if session.owned.exit_code() is not None and not session.selector.get_map():
                        raise SourceFailed()
                    session.pump()

            send(
                {
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "skm", "version": "2.0"},
                    },
                }
            )
            initialized = response(1)
            if initialized.get("protocolVersion") != "2024-11-05":
                raise SourceFailed()
            send({"method": "notifications/initialized"})
            send(
                {
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": config.tool, "arguments": {"query": query.text}},
                }
            )
            result = response(2)
            if result.get("isError"):
                raise SourceFailed()
            content = [object_value(item) for item in array_value(result["content"])]
            if not all(item.get("type") == "text" and isinstance(item.get("text"), str) for item in content):
                raise SourceFailed()
            text = "\n".join(item["text"] for item in content)
            try:
                candidate = json.loads(text)
            except ValueError:
                candidate = None
            if isinstance(candidate, dict) and ("documents" in candidate or "sources" in candidate):
                reply = decode_reply(text.encode(), "json-v1" if "documents" in candidate else "text-v0")
            else:
                reply = decode_reply(
                    json.dumps(
                        {"text": text, "sources": re.findall(r'https?://[^\s<>"\x27]+', text)}
                    ).encode(),
                    "text-v0",
                )
            reply = RawSourceReply(
                reply.documents,
                reply.answer_text,
                reply.claims,
                reply.usage,
                "sha256:" + sha256(text.encode()).hexdigest(),
            )
            return admit_reply(
                reply, config, query, cancel=cancel, timeout=max(0.001, session.deadline - monotonic())
            )
        except (ValueError, TypeError, KeyError, RecursionError):
            raise SourceFailed() from None
        finally:
            session.close()
