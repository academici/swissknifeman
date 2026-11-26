"""Render and recognize the flat frontmatter used by exports."""

from __future__ import annotations

import json
import re

type FrontmatterValue = str | int | bool | tuple[str, ...]
type Fields = tuple[tuple[str, FrontmatterValue], ...]

_KEY = re.compile(r"[a-zA-Z_][a-zA-Z0-9_-]*")
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)")
_QUOTED = r'"(?:[^"\\]|\\.)*"'
_LIST_ITEM = re.compile(rf'({_QUOTED}|[^,\[\]"]+)(?:, |$)')


def _string(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or value in {"true", "false", "null"}
        or "/" in value
        or _INTEGER.fullmatch(value)
        or any(c in value for c in ":#[]\"'\\,")
        or any(ord(c) < 32 or c in "\u0085\u2028\u2029" for c in value)
    ):
        return (
            json.dumps(value, ensure_ascii=False)
            .replace("\u0085", r"\u0085")
            .replace("\u2028", r"\u2028")
            .replace("\u2029", r"\u2029")
        )
    return value


def _encode(value: FrontmatterValue) -> str:
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, tuple):
        return "[" + ", ".join(_string(item) for item in value) + "]"
    return str(value).lower()


def render(fields: Fields) -> str:
    if not fields:
        return ""
    if any(not _KEY.fullmatch(key) for key, _ in fields) or len(dict(fields)) != len(fields):
        raise ValueError("invalid or duplicate frontmatter key")
    return "---\n" + "\n".join(f"{key}: {_encode(value)}" for key, value in fields) + "\n---"


def _decode_string(value: str) -> str:
    if value.startswith('"'):
        decoded = json.loads(value)
        if isinstance(decoded, str):
            decoded.encode("utf-8")
            return decoded
        raise ValueError("expected a string")
    if not value or value != value.strip() or any(c in value for c in ":#[]\"'\\,"):
        raise ValueError("invalid unquoted string")
    return value


def _decode_list(value: str) -> tuple[str, ...]:
    inner = value[1:-1]
    parts: list[str] = []
    pos = 0
    while pos < len(inner):
        match = _LIST_ITEM.match(inner, pos)
        if match is None:
            raise ValueError("malformed list")
        parts.append(_decode_string(match[1]))
        pos = match.end()
    if inner.endswith(", "):
        raise ValueError("trailing list separator")
    return tuple(parts)


def _decode(value: str) -> FrontmatterValue:
    if value == "true" or value == "false":
        return value == "true"
    if _INTEGER.fullmatch(value):
        return int(value)
    if value.startswith("[") and value.endswith("]"):
        return _decode_list(value)
    return _decode_string(value)


def read(text: str, *, max_bytes: int = 8192) -> Fields | None:
    """Require a complete, valid header within the byte bound."""
    try:
        data = text[:max_bytes].encode("utf-8")[:max_bytes]
    except UnicodeError:
        return None
    if not data.startswith(b"---\n"):
        return None
    stop = data.find(b"\n---\n", 3)
    if stop < 0:
        return None
    fields: dict[str, FrontmatterValue] = {}
    try:
        for line in data[4:stop].decode("utf-8").split("\n"):
            key, sep, value = line.partition(": ")
            if not sep or not _KEY.fullmatch(key) or key in fields:
                return None
            fields[key] = _decode(value)
    except ValueError:
        return None
    return tuple(fields.items())
