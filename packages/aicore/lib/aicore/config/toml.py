"""The single entry to TOML parsing, plus a map from keys to line numbers.

The backend is ``tomllib`` on Python 3.11+ and the vendored ``tomli`` otherwise; both read
TOML 1.0. Configuration files are TOML 1.0: ``tomllib`` of Python 3.15 also accepts TOML 1.1
syntax that the older interpreters reject, so do not use it. Nothing else in the ecosystem
imports ``tomllib`` or ``tomli``; callers use :func:`loads` and :func:`load_file`. stdlib only.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from . import ConfigError

Path_ = Tuple[str, ...]

_BARE = re.compile(r"[A-Za-z0-9_-]+")
_AT_LINE = re.compile(r"\s*\(at line (\d+), column (\d+)\)\s*$")
_WHITESPACE = " \t"
_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}


def default_backend() -> str:
    return "stdlib" if sys.version_info >= (3, 11) else "vendored"


def _parse(text: str, backend: Optional[str] = None) -> Dict[str, Any]:
    """Parse with one backend and raise its own error (``backend``: ``stdlib`` or ``vendored``)."""
    backend = backend or default_backend()
    if backend == "stdlib":
        import tomllib
        return tomllib.loads(text)
    if backend == "vendored":
        from .._vendor import tomli
        return tomli.loads(text)
    raise ValueError(f"unknown TOML backend: {backend!r}")


def _error_position(exc: Exception) -> Tuple[str, Optional[int]]:
    """(message without the position suffix, line) of a backend decoding error."""
    text = str(exc)
    line = getattr(exc, "lineno", None)
    match = _AT_LINE.search(text)
    if match:
        text = text[:match.start()]
        if line is None:
            line = int(match.group(1))
    message = getattr(exc, "msg", None) or text
    return message, line if isinstance(line, int) else None


def loads(text: str, *, source: str = "<string>", backend: Optional[str] = None) -> Dict[str, Any]:
    """Parse TOML text; a syntax error becomes ``ConfigError("CONFIG_FILE_INVALID")``."""
    try:
        return _parse(text, backend)
    except (ValueError, RecursionError) as exc:
        message, line = _error_position(exc)
        raise ConfigError("CONFIG_FILE_INVALID", f"invalid TOML: {message}", file=source,
                          line=line) from None


# ---------------------------------------------------------------------------------------------
# Scanner: statements of a document with positions (used for line numbers and by toml_edit).
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Statement:
    """One header or ``key = value`` statement of a document.

    ``keys`` is the header path or the (dotted) key relative to ``table``; ``table`` is the table
    the statement belongs to (its own path for a header). ``start``/``end`` are text offsets;
    ``end`` of a key statement is the end of its value, before any trailing comment.
    ``value_start`` is -1 for headers. ``in_array`` marks content inside an array of tables.
    """

    kind: str  # "table" | "array-table" | "key"
    keys: Path_
    table: Path_
    in_array: bool
    start: int
    end: int
    value_start: int
    line: int
    end_line: int


def _unescape(raw: str) -> str:
    out: List[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char != "\\" or index + 1 >= len(raw):
            out.append(char)
            index += 1
            continue
        code = raw[index + 1]
        if code in _ESCAPES:
            out.append(_ESCAPES[code])
            index += 2
        elif code in "uU":
            width = 4 if code == "u" else 8
            digits = raw[index + 2:index + 2 + width]
            try:
                out.append(chr(int(digits, 16)))
            except (ValueError, OverflowError):
                out.append(raw[index:index + 2 + width])
            index += 2 + width
        else:
            out.append(raw[index:index + 2])
            index += 2
    return "".join(out)


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.size = len(text)
        self._starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line_of(self, offset: int) -> int:
        low, high = 0, len(self._starts)
        while low < high:
            middle = (low + high) // 2
            if self._starts[middle] <= offset:
                low = middle + 1
            else:
                high = middle
        return low

    def skip_blank(self, pos: int) -> int:
        while pos < self.size and self.text[pos] in " \t\r\n":
            pos += 1
        return pos

    def skip_inline(self, pos: int) -> int:
        while pos < self.size and self.text[pos] in _WHITESPACE:
            pos += 1
        return pos

    def end_of_line(self, pos: int) -> int:
        found = self.text.find("\n", pos)
        return self.size if found < 0 else found

    def key(self, pos: int) -> Tuple[Path_, int]:
        """Parse a (dotted) key at ``pos``; returns the parts and the offset after the key."""
        parts: List[str] = []
        while True:
            pos = self.skip_inline(pos)
            if pos >= self.size:
                break
            char = self.text[pos]
            if char == '"':
                end = pos + 1
                while end < self.size and self.text[end] != '"' and self.text[end] != "\n":
                    end += 2 if self.text[end] == "\\" else 1
                parts.append(_unescape(self.text[pos + 1:end]))
                pos = end + 1
            elif char == "'":
                end = self.text.find("'", pos + 1)
                end = self.size if end < 0 else end
                parts.append(self.text[pos + 1:end])
                pos = end + 1
            else:
                match = _BARE.match(self.text, pos)
                if not match:
                    break
                parts.append(match.group())
                pos = match.end()
            after = self.skip_inline(pos)
            if after < self.size and self.text[after] == ".":
                pos = after + 1
                continue
            pos = after
            break
        return tuple(parts), pos

    def string_end(self, pos: int) -> int:
        """Offset after the string literal starting at ``pos``."""
        quote = self.text[pos]
        if self.text.startswith(quote * 3, pos):
            index = pos + 3
            while index < self.size:
                if quote == '"' and self.text[index] == "\\":
                    index += 2
                elif self.text.startswith(quote * 3, index):
                    index += 3
                    extra = 0
                    while index < self.size and self.text[index] == quote and extra < 2:
                        index += 1
                        extra += 1
                    return index
                else:
                    index += 1
            return self.size
        index = pos + 1
        while index < self.size and self.text[index] != "\n":
            if self.text[index] == quote:
                return index + 1
            index += 2 if (quote == '"' and self.text[index] == "\\") else 1
        return index

    def value_end(self, pos: int) -> int:
        """Offset where the value starting at ``pos`` stops (at a top-level comment or newline)."""
        depth = 0
        while pos < self.size:
            char = self.text[pos]
            if char == "\n" and depth == 0:
                return pos
            if char == "#":
                if depth == 0:
                    return pos
                pos = self.end_of_line(pos)
                continue
            if char in "\"'":
                pos = self.string_end(pos)
                continue
            if char in "[{":
                depth += 1
            elif char in "]}":
                depth -= 1
            pos += 1
        return pos

    def statements(self) -> List[Statement]:
        found: List[Statement] = []
        table: Path_ = ()
        array_paths = set()
        pos = 0
        while True:
            pos = self.skip_blank(pos)
            if pos >= self.size:
                break
            if self.text[pos] == "#":
                pos = self.end_of_line(pos)
                continue
            start = pos
            if self.text[pos] == "[":
                is_array = self.text.startswith("[[", pos)
                keys, pos = self.key(pos + (2 if is_array else 1))
                closing = "]]" if is_array else "]"
                if self.text.startswith(closing, pos):
                    pos += len(closing)
                else:
                    pos = self.end_of_line(pos)
                table = keys
                if is_array:
                    # Nested arrays of tables stay "in array"; the new one is registered below.
                    in_array = any(table[:n] in array_paths for n in range(1, len(table)))
                    array_paths.add(table)
                else:
                    in_array = any(table[:n] in array_paths for n in range(1, len(table) + 1))
                found.append(Statement("array-table" if is_array else "table", keys, keys, in_array,
                                       start, pos, -1, self.line_of(start), self.line_of(pos - 1)))
                continue
            keys, pos = self.key(pos)
            pos = self.skip_inline(pos)
            if not keys or pos >= self.size or self.text[pos] != "=":
                pos = self.end_of_line(pos)  # malformed (the parser rejects it): skip the line
                continue
            value_start = self.skip_inline(pos + 1)
            end = self.value_end(value_start)
            stop = end
            while stop > value_start and self.text[stop - 1] in " \t\r\n":
                stop -= 1
            in_array = any(table[:n] in array_paths for n in range(1, len(table) + 1))
            found.append(Statement("key", keys, table, in_array, start, stop, value_start,
                                   self.line_of(start), self.line_of(max(stop - 1, start))))
            pos = end
        return found


def scan(text: str) -> List[Statement]:
    """Statements of a document in order (headers and ``key = value`` lines)."""
    return _Scanner(text).statements()


class LineIndex:
    """Where a key was written: a map from key paths to 1-based line numbers.

    Built from the text of a document that already parsed. Headers index their own path; a
    ``key = value`` line indexes the table path plus the key parts (every prefix of a dotted key
    too). Content inside an array of tables is not indexed.
    """

    def __init__(self, lines: Optional[Dict[Path_, int]] = None) -> None:
        self._lines: Dict[Path_, int] = dict(lines or {})

    @classmethod
    def from_text(cls, text: str) -> "LineIndex":
        lines: Dict[Path_, int] = {}
        for statement in scan(text):
            if statement.kind == "array-table":
                if not statement.in_array:
                    lines.setdefault(statement.keys, statement.line)
            elif statement.kind == "table":
                if not statement.in_array:
                    lines.setdefault(statement.keys, statement.line)
            elif not statement.in_array:
                for count in range(1, len(statement.keys) + 1):
                    lines.setdefault(statement.table + statement.keys[:count], statement.line)
        return cls(lines)

    def lookup(self, path: Iterable[str]) -> Optional[int]:
        """Line of ``path``, else of its nearest indexed ancestor, else ``None``."""
        key = tuple(path)
        while key:
            if key in self._lines:
                return self._lines[key]
            key = key[:-1]
        return None

    def __contains__(self, path: object) -> bool:
        return isinstance(path, tuple) and path in self._lines

    def __len__(self) -> int:
        return len(self._lines)


def load_file(path: Union[str, Path], *, backend: Optional[str] = None) -> Tuple[Dict[str, Any], LineIndex]:
    """Read a UTF-8 TOML file (a leading BOM is accepted) into ``(data, LineIndex)``."""
    target = Path(path)
    try:
        text = target.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        reason = "not valid UTF-8" if isinstance(exc, UnicodeDecodeError) else exc.strerror or "unreadable"
        raise ConfigError("CONFIG_FILE_INVALID", f"cannot read the file: {reason}",
                          file=str(target)) from None
    return loads(text, source=str(target), backend=backend), LineIndex.from_text(text)
