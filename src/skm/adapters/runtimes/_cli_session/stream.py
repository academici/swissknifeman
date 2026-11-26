"""Bounded JSONL framing and pre-decode structural limits shared by CLI adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

__all__: list[str] = []

LINE_BYTES = 1024 * 1024


class MalformedStructure(ValueError):
    """Unbalanced closing delimiters are syntax errors, not resource limits."""


def check_structure(line: bytes, *, max_depth: int = 64, max_members: int = 4096) -> str:
    """Validate UTF-8, then bound structure before JSON decode of a bounded line."""
    text = line.decode("utf-8", "strict")
    stack: list[tuple[int, bool]] = []
    quoted = escaped = False
    members = 0
    for byte in line:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
            continue
        if byte in b" \t\r\n":
            continue
        if stack and stack[-1][1] and byte not in b"}]":
            kind, _ = stack[-1]
            # Each object key or array element counts once, including nested containers.
            members += 1
            stack[-1] = kind, False
            if members > max_members:
                raise ValueError("JSON member ceiling")
        if byte == 34:
            quoted = True
        elif byte in b"{[":
            stack.append((byte, True))
            if len(stack) > max_depth:
                raise ValueError("JSON depth ceiling")
        elif byte in b"}]":
            if not stack or (stack.pop()[0], byte) not in ((123, 125), (91, 93)):
                raise MalformedStructure("JSON nesting")
        elif byte == 44 and stack:
            stack[-1] = stack[-1][0], True
    return text


@dataclass
class StreamTail:
    max_stream_bytes: int
    max_records: int = 100_000
    pending: bytearray = field(default_factory=bytearray)
    flags: set[str] = field(default_factory=set[str])
    records: int = 0
    _discard_line: bool = False

    def __post_init__(self) -> None:
        if self.max_stream_bytes <= 0 or not 1 <= self.max_records <= 100_000:
            raise ValueError("stream and record ceilings must be positive and bounded")

    @property
    def buffer_limit(self) -> int:
        return min(LINE_BYTES, self.max_stream_bytes)

    def _line(self, line: bytes, *, final: bool = False) -> bytes | None:
        self.records = min(self.records + 1, self.max_records + 1)
        if self.records > self.max_records:
            self.flags.add("parser_limit")
        if self.flags:
            return None
        if not line.strip():
            return None
        try:
            text = check_structure(line)
        except UnicodeError:
            self.flags.add("invalid_utf8")
            return None
        except MalformedStructure:
            self.flags.add("malformed_json")
            return None
        except ValueError:
            self.flags.add("parser_limit")
            return None
        try:
            json.loads(text, parse_constant=_invalid_constant)
        except (ValueError, RecursionError):
            self.flags.add("incomplete_tail" if final else "malformed_json")
            return None
        return line

    def advance(self, chunk: bytes = b"", *, final: bool = False) -> list[bytes]:
        ready: list[bytes] = []
        offset = 0
        while offset < len(chunk):
            newline = chunk.find(b"\n", offset)
            end = len(chunk) if newline < 0 else newline
            size = end - offset
            if not self._discard_line and len(self.pending) + size <= self.buffer_limit:
                self.pending.extend(memoryview(chunk)[offset:end])
            else:
                self.flags.add("parser_limit")
                self.pending.clear()
                self._discard_line = True
            if newline < 0:
                break
            if (line := self._line(bytes(self.pending))) is not None:
                ready.append(line)
            self.pending.clear()
            self._discard_line = False
            offset = newline + 1
        if final and self.pending:
            if (line := self._line(bytes(self.pending), final=True)) is not None:
                ready.append(line)
            self.pending.clear()
        return ready


def _invalid_constant(value: str) -> None:
    raise ValueError(f"non-JSON constant {value}")
