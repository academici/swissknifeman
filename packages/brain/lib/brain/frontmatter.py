"""Plain frontmatter: ``key: value`` lines and ``[a, b]`` lists between two ``---`` lines."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_KEY = re.compile(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*))?$")
_NEEDS_QUOTES = re.compile(r"[:#\[\]\"'\n\r]|^\s|\s$")
_ESCAPES = {"n": "\n", "r": "\r"}


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), text[1:-1])
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    return text


def _split_list(body: str) -> List[str]:
    items: List[str] = []
    current: List[str] = []
    quote: Optional[str] = None
    escaped = False
    for char in body:
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'" and not "".join(current).strip():
            quote = char
            current.append(char)
        elif char == ",":
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return [_unquote(item) for item in items if item.strip()]


def _value(text: str) -> Any:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return _split_list(text[1:-1])
    return _unquote(text)


def parse(text: str) -> Dict[str, Any]:
    """Frontmatter fields of ``text``; ``{}`` when it has none or it is broken."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    fields: Dict[str, Any] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _KEY.match(line)
        if not match:
            return {}
        fields[match.group(1)] = _value(match.group(2) or "")
    return {}


def read(path: Path) -> Dict[str, Any]:
    """Frontmatter fields of a file; ``{}`` when the file is unreadable or has none."""
    try:
        return parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}


def _quote(text: str, *, in_list: bool = False) -> str:
    if text and not _NEEDS_QUOTES.search(text) and not (in_list and "," in text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'


def render(fields: List[Tuple[str, Any]]) -> str:
    """A frontmatter block (with a trailing newline) for ``fields``; the order is kept."""
    lines = ["---"]
    for key, value in fields:
        if isinstance(value, (list, tuple)):
            lines.append(f"{key}: [{', '.join(_quote(str(item), in_list=True) for item in value)}]")
        else:
            lines.append(f"{key}: {_quote(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n"
