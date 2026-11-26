"""Pure deterministic MDC frontmatter + markdown body codec for Cursor ``.mdc`` rules (integrations §4.8)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, cast

__all__ = [
    "dumps",
    "dumps_bytes",
    "parse_frontmatter",
    "validate_frontmatter",
]

_ALLOWED_FRONTMATTER_KEYS: Final[frozenset[str]] = frozenset({"description", "globs", "alwaysApply"})


def _escape_double_quoted(value: str) -> str:
    cleaned = " ".join(value.replace("\r\n", "\n").splitlines()).strip()
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_globs(globs: str | Sequence[str]) -> str | None:
    if isinstance(globs, str):
        cleaned = globs.strip()
        return _escape_double_quoted(cleaned) if cleaned else None
    items = [_escape_double_quoted(str(item).strip()) for item in globs if str(item).strip()]
    if not items:
        return None
    return "[" + ", ".join(items) + "]"


def dumps(
    *,
    description: str,
    body: str,
    always_apply: bool | None = True,
    globs: str | Sequence[str] | None = None,
) -> str:
    """Render deterministic ``.mdc`` YAML frontmatter and normalized markdown body."""
    lines: list[str] = ["---", f"description: {_escape_double_quoted(description)}"]
    if globs is not None:
        formatted_globs = _format_globs(globs)
        if formatted_globs is not None:
            lines.append(f"globs: {formatted_globs}")
    if always_apply is not None:
        lines.append(f"alwaysApply: {'true' if always_apply else 'false'}")
    lines.append("---")

    frontmatter = "\n".join(lines) + "\n"
    normalized_body = body.replace("\r\n", "\n").strip("\n")
    if not normalized_body:
        return frontmatter
    return f"{frontmatter}\n{normalized_body}\n"


def dumps_bytes(
    *,
    description: str,
    body: str,
    always_apply: bool | None = True,
    globs: str | Sequence[str] | None = None,
) -> bytes:
    """Render UTF-8 encoded ``.mdc`` document bytes."""
    return dumps(
        description=description,
        body=body,
        always_apply=always_apply,
        globs=globs,
    ).encode("utf-8")


def _unquote_scalar(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        inner = text[1:-1]
        out: list[str] = []
        idx = 0
        while idx < len(inner):
            if inner[idx] == "\\" and idx + 1 < len(inner):
                out.append(inner[idx + 1])
                idx += 2
            else:
                out.append(inner[idx])
                idx += 1
        return "".join(out)
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1]
    return text


def _parse_inline_list(raw: str) -> list[str]:
    inner = raw[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    current: list[str] = []
    in_quotes = False
    quote_char = ""
    escaped = False
    for ch in inner:
        if in_quotes:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote_char:
                in_quotes = False
            continue
        if ch in ('"', "'"):
            in_quotes = True
            quote_char = ch
            current.append(ch)
            continue
        if ch == ",":
            token = "".join(current).strip()
            if not token:
                raise ValueError("empty item in MDC frontmatter list")
            items.append(_unquote_scalar(token))
            current = []
            continue
        current.append(ch)
    if in_quotes:
        raise ValueError("unterminated string in MDC frontmatter list")
    tail = "".join(current).strip()
    if not tail:
        raise ValueError("trailing comma in MDC frontmatter list")
    items.append(_unquote_scalar(tail))
    return items


def _parse_value(key: str, raw_val: str) -> object:
    trimmed = raw_val.strip()
    if key == "alwaysApply":
        if trimmed == "true":
            return True
        if trimmed == "false":
            return False
        raise ValueError(f"MDC frontmatter 'alwaysApply' must be boolean, got {raw_val!r}")
    if trimmed.startswith("[") and trimmed.endswith("]"):
        return _parse_inline_list(trimmed)
    return _unquote_scalar(trimmed)


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Parse ``---`` delimited MDC frontmatter and return ``(metadata, body)``."""
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError("MDC document must start with '---\\n' frontmatter delimiter")
    end_idx = normalized.find("\n---\n", 4)
    if end_idx == -1:
        if normalized.endswith("\n---"):
            end_idx = len(normalized) - 4
            body = ""
        else:
            raise ValueError("MDC document is missing closing '---' frontmatter delimiter")
    else:
        body = normalized[end_idx + 5 :]

    header_block = normalized[4:end_idx]
    metadata: dict[str, object] = {}
    for line in header_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid MDC frontmatter line {line!r}")
        raw_key, _, raw_val = line.partition(":")
        key = raw_key.strip()
        if not key:
            raise ValueError(f"empty key in MDC frontmatter line {line!r}")
        if key in metadata:
            raise ValueError(f"duplicate MDC frontmatter key {key!r}")
        metadata[key] = _parse_value(key, raw_val)

    return metadata, body


def validate_frontmatter(text: str, *, require_always_apply: bool = False) -> dict[str, object]:
    """Validate Cursor ``.mdc`` frontmatter keys and types; return parsed metadata."""
    metadata, _ = parse_frontmatter(text)
    unknown = set(metadata) - _ALLOWED_FRONTMATTER_KEYS
    if unknown:
        raise ValueError(f"unsupported MDC frontmatter keys: {sorted(unknown)!r}")

    desc = metadata.get("description")
    if not isinstance(desc, str) or not desc.strip():
        raise ValueError("MDC frontmatter requires a non-empty 'description' string")

    if "globs" in metadata:
        globs_val = metadata["globs"]
        if isinstance(globs_val, str):
            if not globs_val.strip():
                raise ValueError("MDC frontmatter 'globs' string must not be empty")
        elif isinstance(globs_val, list):
            seq_val = cast("list[object]", globs_val)
            if not all(isinstance(x, str) and bool(x.strip()) for x in seq_val):
                raise ValueError("MDC frontmatter 'globs' list items must be non-empty strings")
        else:
            raise ValueError("MDC frontmatter 'globs' must be a non-empty string or list of strings")

    if "alwaysApply" in metadata and not isinstance(metadata["alwaysApply"], bool):
        raise ValueError("MDC frontmatter 'alwaysApply' must be boolean")

    if require_always_apply and metadata.get("alwaysApply") is not True:
        raise ValueError("MDC frontmatter requires 'alwaysApply: true'")

    return metadata
