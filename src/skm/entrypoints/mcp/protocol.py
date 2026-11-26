"""Stdio framing and JSON-RPC 2.0 envelopes for MCP."""

import json
from dataclasses import dataclass
from io import TextIOWrapper
from typing import BinaryIO, Final, TextIO, cast

from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "Request",
    "RpcError",
    "json_text",
    "negotiate_version",
    "read_message",
    "result",
    "write_message",
]

SUPPORTED_PROTOCOL_VERSIONS: Final = ("2025-06-18", "2024-11-05")
INVALID_REQUEST: Final = -32600
METHOD_NOT_FOUND: Final = -32601
INVALID_PARAMS: Final = -32602
INTERNAL_ERROR: Final = -32603

type RequestId = str | int | float | None


class RpcError(Exception):
    def __init__(self, code: int, message: str, *, data: JsonObject | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def response(self, request_id: RequestId) -> JsonObject:
        error: JsonObject = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}


@dataclass(frozen=True, slots=True)
class Request:
    method: str
    request_id: RequestId
    notification: bool
    params: JsonValue

    @classmethod
    def parse(cls, message: JsonValue) -> "Request":
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise RpcError(INVALID_REQUEST, "Invalid Request")
        method, request_id = message.get("method"), message.get("id")
        if not isinstance(method, str) or (
            request_id is not None and type(request_id) not in (str, int, float)
        ):
            raise RpcError(INVALID_REQUEST, "Invalid Request")
        return cls(method, cast("RequestId", request_id), "id" not in message, message.get("params", {}))


def negotiate_version(requested: JsonValue) -> str:
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return SUPPORTED_PROTOCOL_VERSIONS[0]


def json_text(value: JsonValue) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"))


def read_message(stream: TextIO) -> JsonValue:
    """Read one JSON value, skipping blank lines. EOF and invalid JSON are distinct."""
    while True:
        if isinstance(raw := cast("object", stream), TextIOWrapper):
            line = cast("TextIOWrapper[BinaryIO]", raw).buffer.readline().decode("utf-8")
        else:
            line = stream.readline()
        if not line:
            raise EOFError
        if line.strip():
            value = cast("JsonValue", json.loads(line))
            # Reject non-finite numbers and unpaired surrogates before reflecting any request fields.
            json_text(value).encode("utf-8")
            return value


def result(request_id: RequestId, payload: JsonObject) -> JsonObject:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def write_message(stream: TextIO, message: JsonObject) -> None:
    line = json_text(message) + "\n"
    if isinstance(raw := cast("object", stream), TextIOWrapper):
        buffer = cast("TextIOWrapper[BinaryIO]", raw).buffer
        buffer.write(line.encode("utf-8"))
        buffer.flush()
    else:
        stream.write(line)
        stream.flush()
