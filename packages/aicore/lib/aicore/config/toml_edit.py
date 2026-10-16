"""A minimal TOML editor: set or remove one leaf value and keep everything else as it is.

The editor works on text. It replaces a single-line ``key = value`` keeping the indentation and
the trailing comment, inserts a missing key into its table or appends a new table, and refuses
every other layout (dotted keys, inline tables, arrays of tables, multi-line values) with a hint
to edit the file by hand. Every result is parsed again and compared with the expected document;
a mismatch raises :class:`TomlEditError` and no text is returned. The editor never writes files.
Files are TOML 1.0: only that subset is written. stdlib only.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any, Dict, Optional, Sequence, Tuple

from . import ConfigError
from .toml import Statement, loads, scan

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}

Value = Any  # str | bool | int | float | list of those


class TomlEditError(ValueError):
    """The edit is not possible in place, or its result did not pass the re-parse check."""


def _quote(text: str) -> str:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("string is not valid Unicode text (lone surrogate)") from None
    out = []
    for char in text:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _render_scalar(value: Value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NaN and infinity cannot be written to a configuration file")
        return repr(value)
    if isinstance(value, str):
        return _quote(value)
    raise ValueError(f"unsupported value type: {type(value).__name__}")


def render_value(value: Value) -> str:
    """TOML text of a str, bool, int, finite float or a flat list of those."""
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_render_scalar(item) for item in value) + "]"
    return _render_scalar(value)


def render_key(key: str) -> str:
    return key if _BARE_KEY.match(key) else _quote(key)


def _header(path: Sequence[str]) -> str:
    return "[" + ".".join(render_key(part) for part in path) + "]"


def _dotted(path: Sequence[str]) -> str:
    return ".".join(path)


def _refuse(path: Sequence[str], reason: str) -> TomlEditError:
    return TomlEditError(f"cannot edit {_dotted(path)} in place: {reason}; edit the file by hand")


def _same(left: Any, right: Any) -> bool:
    """Equality that keeps ``True`` and ``1`` (and ``1`` and ``1.0``) apart."""
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def _check_path(path: Sequence[str]) -> Tuple[str, ...]:
    parts = tuple(path)
    if len(parts) < 2 or not all(isinstance(part, str) and part for part in parts):
        raise ValueError("path must be a tuple of at least two non-empty strings")
    return parts


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _locate(statements: Sequence[Statement], path: Tuple[str, ...]) -> Optional[Statement]:
    """The single-line ``key = value`` statement that defines ``path``; refuse other layouts."""
    table, found = path[:-1], None
    for item in statements:
        if item.kind == "array-table":
            if path[:len(item.keys)] == item.keys:
                raise _refuse(path, "it is inside an array of tables")
            continue
        if item.in_array:
            continue
        if item.kind == "table":
            if item.keys[:len(path)] == path:
                raise _refuse(path, "it is a table, not a value")
            continue
        full = item.table + item.keys
        if full == path:
            if item.table != table or len(item.keys) != 1:
                raise _refuse(path, "it is defined by a dotted key")
            if item.line != item.end_line:
                raise _refuse(path, "its value spans several lines")
            found = item
        elif path[:len(full)] == full:
            raise _refuse(path, "a parent of it is defined by a dotted key or an inline table")
        elif full[:len(path)] == path:
            raise _refuse(path, "it is a table defined by dotted keys")
    return found


def _expected(old: Dict[str, Any], path: Tuple[str, ...], value: Value, *, remove: bool) -> Dict[str, Any]:
    tree = copy.deepcopy(old)
    node = tree
    for part in path[:-1]:
        if remove:
            node = node.get(part)
            if not isinstance(node, dict):
                return tree
        else:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise _refuse(path, f"{part} is not a table")
    if remove:
        node.pop(path[-1], None)
    else:
        node[path[-1]] = copy.deepcopy(list(value) if isinstance(value, tuple) else value)
    return tree


def _verify(old: Dict[str, Any], new_text: str, path: Tuple[str, ...], value: Value, source: str,
            *, remove: bool) -> None:
    expected = _expected(old, path, value, remove=remove)
    try:
        actual = loads(new_text, source=source)
    except ConfigError as exc:
        raise TomlEditError(f"edit of {_dotted(path)} produced invalid TOML ({exc.message}); "
                            "the file was not changed") from None
    if not _same(actual, expected):
        raise TomlEditError(f"edit of {_dotted(path)} did not give the expected document; "
                            "the file was not changed")


def _block(statements: Sequence[Statement], table: Tuple[str, ...]) -> Tuple[Optional[int], list]:
    """(index of the table header, key statements of its block)."""
    for index, item in enumerate(statements):
        if item.kind == "table" and item.keys == table and not item.in_array:
            keys = []
            for later in statements[index + 1:]:
                if later.kind != "key":
                    break
                keys.append(later)
            return index, keys
    return None, []


def set_value(text: str, path: Sequence[str], value: Value, *, source: str = "<string>") -> str:
    """Return ``text`` with the leaf at ``path`` (``('module', ..., 'key')``) set to ``value``."""
    parts = _check_path(path)
    rendered = render_value(value)
    old = loads(text, source=source)
    statements = scan(text)
    existing = _locate(statements, parts)
    newline = _newline(text)
    line = f"{render_key(parts[-1])} = {rendered}"
    if existing is not None:
        new_text = text[:existing.value_start] + rendered + text[existing.end:]
    else:
        header_index, keys = _block(statements, parts[:-1])
        if header_index is None:
            body = text if not text or text.endswith("\n") else text + newline
            lead = newline if body else ""
            new_text = f"{body}{lead}{_header(parts[:-1])}{newline}{line}{newline}"
        else:
            anchor = keys[-1].end if keys else statements[header_index].end
            eol = text.find("\n", anchor)
            if eol < 0:
                new_text = text + newline + line
            else:
                new_text = text[:eol + 1] + line + newline + text[eol + 1:]
    _verify(old, new_text, parts, value, source, remove=False)
    return new_text


def unset_value(text: str, path: Sequence[str], *, source: str = "<string>") -> str:
    """Return ``text`` without the single-line definition of ``path``; unchanged if absent."""
    parts = _check_path(path)
    old = loads(text, source=source)
    existing = _locate(scan(text), parts)
    if existing is None:
        return text
    begin = text.rfind("\n", 0, existing.start) + 1
    eol = text.find("\n", existing.end)
    stop = len(text) if eol < 0 else eol + 1
    new_text = text[:begin] + text[stop:]
    _verify(old, new_text, parts, None, source, remove=True)
    return new_text
