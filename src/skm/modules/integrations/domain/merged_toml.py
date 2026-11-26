"""Pure TOML 1.0 codec for owned keys and tables with verbatim foreign-section preservation (§4.6)."""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from typing import Any, Final, NamedTuple, NoReturn, cast

from .merged_json import (
    OwnedKeyPath,
    ensure_mapping,
    extract_owned,
    is_tagged_item,
    lookup_owned_path,
)

__all__ = [
    "dumps_merged_toml",
    "dumps_merged_toml_bytes",
    "extract_owned_toml",
    "format_toml_document",
    "format_toml_inline_table",
    "format_toml_key",
    "format_toml_table",
    "format_toml_value",
    "merge_owned_toml",
    "parse_toml",
]

_BARE_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]+$")
_BARE_SEG_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_-]+")
_WS_RE: Final[re.Pattern[str]] = re.compile(r"[ \t]*")
_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]+$")
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[^ \t\n\r#,\]\}]+")
_BASIC_ESCAPES: Final[Mapping[str, str]] = dict(zip('btnfr"\\', '\b\t\n\f\r"\\', strict=True))
_STR_OUT_ESCAPES: Final[Mapping[str, str]] = {v: f"\\{k}" for k, v in _BASIC_ESCAPES.items()}
_DATE_ONLY_RE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_ONLY_RE: Final[re.Pattern[str]] = re.compile(r"^\d{2}:\d{2}:\d{2}(?:\.\d+)?$")
_DATETIME_START_RE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]")
_INT_DEC_RE: Final[re.Pattern[str]] = re.compile(r"^[+-]?(?:0|[1-9](?:_?[0-9])*)$")
_FLOAT_RE: Final[re.Pattern[str]] = re.compile(
    r"^[+-]?(?:0|[1-9](?:_?[0-9])*)(?:\.[0-9](?:_?[0-9])*(?:[eE][+-]?[0-9](?:_?[0-9])*)?|"
    r"[eE][+-]?[0-9](?:_?[0-9])*)$"
)


def _invalid() -> NoReturn:
    raise ValueError("INTEGRATION_BOUNDARY_INVALID")


def _is_disallowed_ctrl(ch: str, *, allow_lf: bool) -> bool:
    if ch == "\t" or (allow_lf and ch == "\n"):
        return False
    low_end = "\x08" if allow_lf else "\x1f"
    return ("\x00" <= ch <= low_end) or ("\x0b" <= ch <= "\x1f") or ch == "\x7f"


class _StmtSpan(NamedTuple):
    key_path: tuple[str, ...]
    line_start: int
    line_end: int


class _TableSpan(NamedTuple):
    is_array: bool
    path: tuple[str, ...]
    header_start: int
    body_end: int


class _TomlLayout(NamedTuple):
    first_table_start: int
    top_stmts: tuple[_StmtSpan, ...]
    tables: tuple[_TableSpan, ...]


class _TomlParser:
    """Strict pure-Python TOML 1.0 parser recording top-level statement and table spans."""

    def __init__(self, src: str) -> None:
        self.src = src
        self.n = len(src)
        self.pos = 0
        self.root: dict[str, Any] = {}
        self.explicit_tables: set[tuple[str, ...]] = set()
        self.implicit_super_tables: set[tuple[str, ...]] = set()
        self.dotted_defined_tables: set[tuple[str, ...]] = set()
        self.inline_frozen_ids: set[int] = set()
        self.array_tables: set[tuple[str, ...]] = set()

    def _skip_ws(self) -> None:
        m = _WS_RE.match(self.src, self.pos)
        if m is not None:
            self.pos = m.end()

    def _skip_comment(self) -> None:
        if self.pos < self.n and self.src[self.pos] == "#":
            while self.pos < self.n and self.src[self.pos] not in ("\n", "\r"):
                if _is_disallowed_ctrl(self.src[self.pos], allow_lf=True):
                    _invalid()
                self.pos += 1

    def _consume_newline_or_eof(self) -> int:
        self._skip_ws()
        self._skip_comment()
        if self.pos >= self.n:
            return self.pos
        if self.src.startswith("\r\n", self.pos):
            self.pos += 2
            return self.pos
        if self.src[self.pos] == "\n":
            self.pos += 1
            return self.pos
        _invalid()

    def _skip_ws_comments_newlines(self) -> None:
        while self.pos < self.n:
            ch = self.src[self.pos]
            if ch in (" ", "\t", "\n"):
                self.pos += 1
            elif self.src.startswith("\r\n", self.pos):
                self.pos += 2
            elif ch == "#":
                self._skip_comment()
            elif ch == "\r":
                _invalid()
            else:
                break

    def _read_basic_escape(self) -> str:
        if self.pos >= self.n:
            _invalid()
        esc = self.src[self.pos]
        if esc in _BASIC_ESCAPES:
            self.pos += 1
            return _BASIC_ESCAPES[esc]
        if esc in ("u", "U"):
            self.pos += 1
            digits = 4 if esc == "u" else 8
            hex_part = self.src[self.pos : self.pos + digits]
            if len(hex_part) != digits or _HEX_RE.fullmatch(hex_part) is None:
                _invalid()
            code = int(hex_part, 16)
            if code > 0x10FFFF or 0xD800 <= code <= 0xDFFF:
                _invalid()
            self.pos += digits
            return chr(code)
        _invalid()

    def _skip_line_ending_backslash_ws(self) -> None:
        saw_nl = False
        while self.pos < self.n and self.src[self.pos] in (" ", "\t", "\r", "\n"):
            if self.src[self.pos] == "\r" and not self.src.startswith("\r\n", self.pos):
                _invalid()
            if self.src[self.pos] == "\n":
                saw_nl = True
            self.pos += 1
        if not saw_nl:
            _invalid()

    def _parse_multiline_str(self, quote: str, *, allow_escapes: bool) -> str:
        delim = quote * 3
        self.pos += 3
        if self.src.startswith("\r\n", self.pos):
            self.pos += 2
        elif self.pos < self.n and self.src[self.pos] == "\n":
            self.pos += 1
        out: list[str] = []
        while self.pos < self.n:
            if self.src.startswith(delim, self.pos):
                run = 0
                while self.pos + run < self.n and self.src[self.pos + run] == quote:
                    run += 1
                if run > 5:
                    _invalid()
                self.pos += run
                out.append(quote * (run - 3))
                return "".join(out)
            ch = self.src[self.pos]
            if allow_escapes and ch == "\\":
                self.pos += 1
                if self.pos < self.n and self.src[self.pos] in (" ", "\t", "\r", "\n"):
                    self._skip_line_ending_backslash_ws()
                else:
                    out.append(self._read_basic_escape())
            elif self.src.startswith("\r\n", self.pos):
                out.append("\n")
                self.pos += 2
            elif ch == "\r" or _is_disallowed_ctrl(ch, allow_lf=True):
                _invalid()
            else:
                out.append(ch)
                self.pos += 1
        _invalid()

    def _parse_single_str(self, quote: str, *, allow_escapes: bool) -> str:
        self.pos += 1
        out: list[str] = []
        while self.pos < self.n:
            ch = self.src[self.pos]
            if ch == quote:
                self.pos += 1
                return "".join(out)
            if ch in ("\n", "\r") or _is_disallowed_ctrl(ch, allow_lf=False):
                _invalid()
            if allow_escapes and ch == "\\":
                self.pos += 1
                out.append(self._read_basic_escape())
            else:
                out.append(ch)
                self.pos += 1
        _invalid()

    def _parse_key_segment(self) -> str:
        self._skip_ws()
        if self.pos >= self.n:
            _invalid()
        ch = self.src[self.pos]
        if ch in ('"', "'"):
            if self.src.startswith(ch * 3, self.pos):
                _invalid()
            return self._parse_single_str(ch, allow_escapes=(ch == '"'))
        m = _BARE_SEG_RE.match(self.src, self.pos)
        if m is None:
            _invalid()
        self.pos = m.end()
        return m.group(0)

    def _parse_dotted_key(self) -> tuple[str, ...]:
        parts = [self._parse_key_segment()]
        while True:
            self._skip_ws()
            if self.pos < self.n and self.src[self.pos] == ".":
                self.pos += 1
                parts.append(self._parse_key_segment())
            else:
                return tuple(parts)

    def _parse_array(self) -> list[Any]:
        self.pos += 1
        items: list[Any] = []
        while True:
            self._skip_ws_comments_newlines()
            if self.pos < self.n and self.src[self.pos] == "]":
                self.pos += 1
                return items
            items.append(self._parse_value())
            self._skip_ws_comments_newlines()
            if self.pos >= self.n:
                _invalid()
            if self.src[self.pos] == ",":
                self.pos += 1
                continue
            if self.src[self.pos] == "]":
                self.pos += 1
                return items
            _invalid()

    def _freeze_inline_tree(self, mapping: dict[str, Any]) -> None:
        self.inline_frozen_ids.add(id(mapping))
        for val in mapping.values():
            if isinstance(val, dict):
                self._freeze_inline_tree(cast("dict[str, Any]", val))

    def _parse_inline_table(self) -> dict[str, Any]:
        self.pos += 1
        table: dict[str, Any] = {}
        local_tables: set[tuple[str, ...]] = set()
        self._skip_ws()
        if self.pos < self.n and self.src[self.pos] == "}":
            self.pos += 1
            self.inline_frozen_ids.add(id(table))
            return table
        while True:
            key_path = self._parse_dotted_key()
            self._skip_ws()
            if self.pos >= self.n or self.src[self.pos] != "=":
                _invalid()
            self.pos += 1
            self._insert_into_mapping(
                table, key_path, self._parse_value(), prefix=(), local_tables=local_tables
            )
            self._skip_ws()
            if self.pos >= self.n:
                _invalid()
            if self.src[self.pos] == "}":
                self.pos += 1
                self._freeze_inline_tree(table)
                return table
            if self.src[self.pos] == ",":
                self.pos += 1
                self._skip_ws()
                if self.pos >= self.n or self.src[self.pos] in ("}", "\n", "\r"):
                    _invalid()
                continue
            _invalid()

    def _read_scalar_token(self) -> str:
        m = _TOKEN_RE.match(self.src, self.pos)
        if m is None:
            _invalid()
        token = m.group(0)
        self.pos = m.end()
        if (
            _DATE_ONLY_RE.fullmatch(token)
            and self.pos + 3 < self.n
            and self.src[self.pos] == " "
            and self.src[self.pos + 1].isdigit()
            and self.src[self.pos + 3] == ":"
        ):
            tm = _TOKEN_RE.match(self.src, self.pos + 1)
            if tm is not None:
                self.pos = tm.end()
                token = f"{token}T{tm.group(0)}"
        return token

    def _parse_radix_int(self, token: str) -> int:
        base = {"x": 16, "o": 8, "b": 2}[token[1].lower()]
        digits = token[2:]
        if not digits or digits.startswith("_") or digits.endswith("_") or "__" in digits:
            _invalid()
        try:
            return int(digits.replace("_", ""), base)
        except ValueError:
            _invalid()

    def _parse_temporal(self, token: str) -> datetime | date | time | None:
        try:
            if _DATETIME_START_RE.match(token):
                iso = token[:-1] + "+00:00" if token.endswith(("Z", "z")) else token
                return datetime.fromisoformat(iso)
            if _DATE_ONLY_RE.fullmatch(token):
                return date.fromisoformat(token)
            if _TIME_ONLY_RE.fullmatch(token):
                return time.fromisoformat(token)
        except ValueError:
            _invalid()
        return None

    def _parse_scalar(self) -> Any:
        token = self._read_scalar_token()
        if token in ("true", "false"):
            return token == "true"
        if token in ("inf", "+inf", "-inf", "nan", "+nan", "-nan"):
            return float(token)
        if token.startswith(("0x", "0X", "0o", "0O", "0b", "0B")):
            return self._parse_radix_int(token)
        temporal = self._parse_temporal(token)
        if temporal is not None:
            return temporal
        if _INT_DEC_RE.fullmatch(token):
            return int(token.replace("_", ""), 10)
        if _FLOAT_RE.fullmatch(token):
            return float(token.replace("_", ""))
        _invalid()

    def _parse_value(self) -> Any:
        self._skip_ws()
        if self.pos >= self.n:
            _invalid()
        ch = self.src[self.pos]
        if ch in ('"', "'"):
            esc = ch == '"'
            if self.src.startswith(ch * 3, self.pos):
                return self._parse_multiline_str(ch, allow_escapes=esc)
            return self._parse_single_str(ch, allow_escapes=esc)
        if ch == "[":
            return self._parse_array()
        if ch == "{":
            return self._parse_inline_table()
        return self._parse_scalar()

    def _insert_into_mapping(
        self,
        target: dict[str, Any],
        key_path: tuple[str, ...],
        value: Any,
        *,
        prefix: tuple[str, ...],
        local_tables: set[tuple[str, ...]],
    ) -> None:
        current = target
        cur_path = prefix
        for seg in key_path[:-1]:
            cur_path = (*cur_path, seg)
            if cur_path in self.explicit_tables and prefix != cur_path:
                _invalid()
            if seg not in current:
                new_tbl: dict[str, Any] = {}
                current[seg] = new_tbl
                local_tables.add(cur_path)
                self.dotted_defined_tables.add(cur_path)
                current = new_tbl
            else:
                existing: Any = current[seg]
                if not isinstance(existing, dict):
                    _invalid()
                existing_dict = cast("dict[str, Any]", existing)
                if id(existing_dict) in self.inline_frozen_ids or (
                    cur_path not in local_tables and cur_path not in self.dotted_defined_tables
                ):
                    _invalid()
                current = existing_dict
        leaf = key_path[-1]
        if leaf in current or id(current) in self.inline_frozen_ids:
            _invalid()
        current[leaf] = value

    def _reset_subtables_under(self, prefix: tuple[str, ...]) -> None:
        plen = len(prefix)
        for group in (
            self.explicit_tables,
            self.implicit_super_tables,
            self.dotted_defined_tables,
            self.array_tables,
        ):
            for item in [p for p in group if len(p) > plen and p[:plen] == prefix]:
                group.discard(item)

    def _walk_table_parents(self, path: tuple[str, ...]) -> dict[str, Any]:
        current: dict[str, Any] = self.root
        for idx, seg in enumerate(path[:-1]):
            sub_path = path[: idx + 1]
            if seg not in current:
                new_tbl: dict[str, Any] = {}
                current[seg] = new_tbl
                self.implicit_super_tables.add(sub_path)
                current = new_tbl
            elif isinstance(current[seg], list):
                arr = cast("list[dict[str, Any]]", current[seg])
                if sub_path not in self.array_tables or not arr:
                    _invalid()
                current = arr[-1]
            elif isinstance(current[seg], dict):
                tbl = cast("dict[str, Any]", current[seg])
                if id(tbl) in self.inline_frozen_ids:
                    _invalid()
                current = tbl
            else:
                _invalid()
        return current

    def _open_array_table(self, parent: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
        last = path[-1]
        if path in (self.explicit_tables | self.implicit_super_tables | self.dotted_defined_tables):
            _invalid()
        if last not in parent:
            arr: list[dict[str, Any]] = [{}]
            parent[last] = arr
            self.array_tables.add(path)
            self._reset_subtables_under(path)
            return arr[0]
        existing: Any = parent[last]
        if not isinstance(existing, list) or path not in self.array_tables:
            _invalid()
        new_elem: dict[str, Any] = {}
        cast("list[dict[str, Any]]", existing).append(new_elem)
        self._reset_subtables_under(path)
        return new_elem

    def _open_std_table(self, parent: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
        last = path[-1]
        if path in (self.explicit_tables | self.dotted_defined_tables | self.array_tables):
            _invalid()
        if last not in parent:
            tbl: dict[str, Any] = {}
            parent[last] = tbl
            self.explicit_tables.add(path)
            return tbl
        existing: Any = parent[last]
        if not isinstance(existing, dict) or path not in self.implicit_super_tables:
            _invalid()
        existing_tbl = cast("dict[str, Any]", existing)
        if id(existing_tbl) in self.inline_frozen_ids:
            _invalid()
        self.implicit_super_tables.discard(path)
        self.explicit_tables.add(path)
        return existing_tbl

    def _parse_header_line(self) -> tuple[bool, tuple[str, ...], int]:
        is_array = self.src.startswith("[[", self.pos)
        self.pos += 2 if is_array else 1
        tpath = self._parse_dotted_key()
        self._skip_ws()
        closer = "]]" if is_array else "]"
        if not self.src.startswith(closer, self.pos):
            _invalid()
        self.pos += len(closer)
        return is_array, tpath, self._consume_newline_or_eof()

    def parse(self) -> tuple[dict[str, Any], _TomlLayout]:
        top_stmts: list[_StmtSpan] = []
        tables: list[_TableSpan] = []
        first_table_start: int | None = None
        current_table = self.root
        current_prefix: tuple[str, ...] = ()
        local_dotted: set[tuple[str, ...]] = set()
        active_hdr: tuple[bool, tuple[str, ...], int, int] | None = None

        while self.pos < self.n:
            line_start = self.pos
            self._skip_ws()
            if self.pos >= self.n:
                break
            if self.src[self.pos] in ("\r", "\n", "#"):
                self._consume_newline_or_eof()
                continue
            if self.src[self.pos] == "[":
                if active_hdr is not None:
                    tables.append(_TableSpan(*active_hdr))
                if first_table_start is None:
                    first_table_start = line_start
                is_arr, tpath, hdr_end = self._parse_header_line()
                parent = self._walk_table_parents(tpath)
                current_table = (
                    self._open_array_table(parent, tpath) if is_arr else self._open_std_table(parent, tpath)
                )
                current_prefix = tpath
                local_dotted = set()
                active_hdr = (is_arr, tpath, line_start, hdr_end)
                continue
            key_path = self._parse_dotted_key()
            self._skip_ws()
            if self.pos >= self.n or self.src[self.pos] != "=":
                _invalid()
            self.pos += 1
            val = self._parse_value()
            stmt_end = self._consume_newline_or_eof()
            self._insert_into_mapping(
                current_table, key_path, val, prefix=current_prefix, local_tables=local_dotted
            )
            if active_hdr is None:
                top_stmts.append(_StmtSpan(key_path, line_start, stmt_end))
            else:
                active_hdr = (active_hdr[0], active_hdr[1], active_hdr[2], stmt_end)

        if active_hdr is not None:
            tables.append(_TableSpan(*active_hdr))
        f_start = self.n if first_table_start is None else first_table_start
        return self.root, _TomlLayout(f_start, tuple(top_stmts), tuple(tables))


def parse_toml(raw_toml: str) -> dict[str, Any]:
    """Parse ``raw_toml`` into a dictionary; raise ``ValueError('INTEGRATION_BOUNDARY_INVALID')``."""
    return _TomlParser(raw_toml).parse()[0]


def _escape_toml_basic_str(value: str) -> str:
    pieces = ['"']
    for ch in value:
        mapped = _STR_OUT_ESCAPES.get(ch)
        if mapped is not None:
            pieces.append(mapped)
        elif ("\x00" <= ch <= "\x1f") or ch == "\x7f":
            pieces.append(f"\\u{ord(ch):04x}")
        else:
            pieces.append(ch)
    pieces.append('"')
    return "".join(pieces)


def format_toml_key(key: str) -> str:
    """Format a single TOML key segment as bare if safe, else double-quoted."""
    return key if (key and _BARE_KEY_RE.fullmatch(key) is not None) else _escape_toml_basic_str(key)


def format_toml_inline_table(mapping: Mapping[str, Any]) -> str:
    """Format ``mapping`` as a TOML inline table ``{ k = v, ... }``."""
    if not mapping:
        return "{}"
    return (
        "{ "
        + ", ".join(f"{format_toml_key(str(k))} = {format_toml_value(v)}" for k, v in mapping.items())
        + " }"
    )


def _format_float(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return repr(value)


def format_toml_value(value: Any) -> str:
    """Format a TOML scalar, array, or inline table value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, str):
        return _escape_toml_basic_str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return format_toml_inline_table(cast("Mapping[str, Any]", value))
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return "[" + ", ".join(format_toml_value(item) for item in cast("Sequence[Any]", value)) + "]"
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def format_toml_table(path: Sequence[str], mapping: Mapping[str, Any]) -> str:
    """Format ``[path]`` table section with trailing newline."""
    if not path:
        raise ValueError("table path must not be empty")
    header = ".".join(format_toml_key(seg) for seg in path)
    body = "".join(f"{format_toml_key(str(k))} = {format_toml_value(v)}\n" for k, v in mapping.items())
    return f"[{header}]\n{body}"


def _collect_document_tables(prefix: tuple[str, ...], mapping: Mapping[str, Any], out: list[str]) -> None:
    if mapping and len(prefix) == 1 and all(isinstance(v, Mapping) for v in mapping.values()):
        for child_key, child_val in mapping.items():
            _collect_document_tables((*prefix, str(child_key)), cast("Mapping[str, Any]", child_val), out)
        return
    out.append(format_toml_table(prefix, mapping))


def format_toml_document(document: Mapping[str, Any]) -> str:
    """Serialize a TOML mapping with top-level keys before ``[table]`` sections."""
    if not document:
        return ""
    top_lines: list[str] = []
    table_blocks: list[str] = []
    for key, val in document.items():
        str_key = str(key)
        if isinstance(val, Mapping):
            _collect_document_tables((str_key,), cast("Mapping[str, Any]", val), table_blocks)
        else:
            top_lines.append(f"{format_toml_key(str_key)} = {format_toml_value(val)}\n")
    return "\n".join((["".join(top_lines)] if top_lines else []) + table_blocks)


def dumps_merged_toml(document: Mapping[str, Any]) -> str:
    """Canonical TOML string serializer for owned/merged documents."""
    return format_toml_document(document)


def dumps_merged_toml_bytes(document: Mapping[str, Any]) -> bytes:
    """Canonical UTF-8 bytes of ``dumps_merged_toml(document)``."""
    return format_toml_document(document).encode("utf-8")


def extract_owned_toml(raw_toml: str, owned: tuple[OwnedKeyPath, ...]) -> dict[str, Any]:
    """Parse ``raw_toml`` and return only owned top-level keys and owned tables."""
    return extract_owned(parse_toml(raw_toml), owned)


def _trailing_attached_comment_index(section0: str) -> int:
    lines = section0.splitlines(keepends=True)
    idx = len(lines)
    while idx > 0 and lines[idx - 1].lstrip(" \t").startswith("#"):
        idx -= 1
    return sum(len(line) for line in lines[:idx])


def _classify_list_spec(
    parsed_doc: Mapping[str, Any], path: tuple[str, ...], *, has_managed: bool, managed_val: Any
) -> tuple[str, bool, Any]:
    if len(path) != 1:
        _invalid()
    existing_found, existing_val = lookup_owned_path(parsed_doc, path, strict_containers=True)
    foreign: list[Any] = []
    had_tagged = False
    if existing_found:
        if not isinstance(existing_val, list):
            _invalid()
        ex_list = cast("list[Any]", existing_val)
        foreign = [copy.deepcopy(x) for x in ex_list if not is_tagged_item(x)]
        had_tagged = len(foreign) != len(ex_list)
    new_tagged: list[Any] = []
    if has_managed:
        if not isinstance(managed_val, Sequence) or isinstance(managed_val, (str, bytes)):
            _invalid()
        for item in cast("Sequence[Any]", managed_val):
            if not is_tagged_item(item):
                _invalid()
            new_tagged.append(copy.deepcopy(item))
    combined = foreign + new_tagged
    keep = bool(combined) or (existing_found and not had_tagged)
    return (path[0], keep, combined if keep else None)


_TableSpec = tuple[tuple[str, ...], bool, Mapping[str, Any] | None]


def _classify_owned_specs(
    parsed_doc: Mapping[str, Any],
    layout: _TomlLayout,
    managed: Mapping[str, Any],
    owned: tuple[OwnedKeyPath, ...],
) -> tuple[list[tuple[str, bool, Any]], list[_TableSpec]]:
    top_specs: list[tuple[str, bool, Any]] = []
    tbl_specs: list[_TableSpec] = []
    for spec in owned:
        if not spec.path or spec.mode not in ("replace", "list_union_tagged"):
            _invalid()
        lookup_owned_path(parsed_doc, spec.path, strict_containers=True)
        has_mg, mg_val = lookup_owned_path(managed, spec.path, strict_containers=True)
        if spec.mode == "list_union_tagged":
            top_specs.append(
                _classify_list_spec(parsed_doc, spec.path, has_managed=has_mg, managed_val=mg_val)
            )
        elif len(spec.path) >= 2:
            if has_mg and not isinstance(mg_val, Mapping):
                _invalid()
            tbl_specs.append((spec.path, has_mg, cast("Mapping[str, Any]", mg_val) if has_mg else None))
        elif len(spec.path) == 1:
            key = spec.path[0]
            has_tbl = any(t.path[:1] == (key,) for t in layout.tables)
            if has_mg and isinstance(mg_val, Mapping):
                tbl_specs.append((spec.path, True, cast("Mapping[str, Any]", mg_val)))
            elif has_mg:
                if has_tbl:
                    _invalid()
                top_specs.append((key, True, mg_val))
            elif has_tbl:
                tbl_specs.append((spec.path, False, None))
            else:
                top_specs.append((key, False, None))
    return top_specs, tbl_specs


def _collect_sec0_edits(
    raw_toml: str,
    layout: _TomlLayout,
    top_specs: list[tuple[str, bool, Any]],
    tbl_specs: list[_TableSpec],
) -> tuple[dict[int, tuple[int, str]], list[str]]:
    edits: dict[int, tuple[int, str]] = {}
    for tpath, _, _ in tbl_specs:
        plen = len(tpath)
        for idx, stmt in enumerate(layout.top_stmts):
            if len(stmt.key_path) >= plen and stmt.key_path[:plen] == tpath:
                edits[idx] = (stmt.line_end, "")
            elif len(stmt.key_path) < plen and tpath[: len(stmt.key_path)] == stmt.key_path:
                _invalid()
    new_lines: list[str] = []
    for key, present, val in top_specs:
        matches = [i for i, s in enumerate(layout.top_stmts) if s.key_path[:1] == (key,)]
        if matches:
            if present and any(len(layout.top_stmts[i].key_path) != 1 for i in matches):
                _invalid()
            first = layout.top_stmts[matches[0]]
            nl = "\r\n" if raw_toml[first.line_start : first.line_end].endswith("\r\n") else "\n"
            repl = f"{format_toml_key(key)} = {format_toml_value(val)}{nl}" if present else ""
            edits[matches[0]] = (first.line_end, repl)
            for extra in matches[1:]:
                edits[extra] = (layout.top_stmts[extra].line_end, "")
        elif present:
            new_lines.append(f"{format_toml_key(key)} = {format_toml_value(val)}\n")
    return edits, new_lines


def _insert_new_top_lines(
    sec0_parts: list[str], sec0_tail: str, last_kept: int | None, inserted: str, *, has_tables: bool
) -> str:
    if last_kept is not None:
        prefix = "".join(sec0_parts[:last_kept])
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        suffix = "".join(sec0_parts[last_kept:]) + sec0_tail
        return prefix + inserted + ("\n" if (has_tables and not suffix) else suffix)
    combined = "".join(sec0_parts) + sec0_tail
    if not combined:
        return inserted + ("\n" if has_tables else "")
    if not has_tables:
        return (combined if combined.endswith("\n") else combined + "\n") + inserted
    split_idx = _trailing_attached_comment_index(combined)
    before, attached = combined[:split_idx], combined[split_idx:]
    if before and not before.endswith("\n"):
        before += "\n"
    return before + inserted + ("" if inserted.endswith("\n\n") else "\n") + attached


def _rebuild_sec0(
    raw_toml: str,
    layout: _TomlLayout,
    edits: dict[int, tuple[int, str]],
    new_lines: list[str],
    *,
    has_tables: bool,
) -> str:
    sec0_raw = raw_toml[: layout.first_table_start]
    parts: list[str] = []
    cursor = 0
    last_kept: int | None = None
    for idx, stmt in enumerate(layout.top_stmts):
        parts.append(sec0_raw[cursor : stmt.line_start])
        if idx in edits:
            end_pos, repl = edits[idx]
            if repl:
                if parts and parts[-1] and not parts[-1].endswith("\n"):
                    parts.append("\n")
                parts.append(repl)
                last_kept = len(parts)
            cursor = end_pos
        else:
            parts.append(sec0_raw[stmt.line_start : stmt.line_end])
            last_kept = len(parts)
            cursor = stmt.line_end
    tail = sec0_raw[cursor:]
    if not new_lines:
        return "".join(parts) + tail
    return _insert_new_top_lines(parts, tail, last_kept, "".join(new_lines), has_tables=has_tables)


def _compute_table_edits(
    raw_toml: str, layout: _TomlLayout, tbl_specs: list[_TableSpec]
) -> tuple[list[tuple[int, int, str]], set[tuple[str, ...]]]:
    placed: set[tuple[str, ...]] = set()
    edits: list[tuple[int, int, str]] = []
    for tbl in layout.tables:
        matched = next(
            ((p, pr, tv) for p, pr, tv in tbl_specs if len(tbl.path) >= len(p) and tbl.path[: len(p)] == p),
            None,
        )
        if matched is None:
            continue
        tpath, present, tval = matched
        if present and tval is not None and tpath not in placed:
            placed.add(tpath)
            edits.append((tbl.header_start, tbl.body_end, format_toml_table(tpath, tval)))
            continue
        del_start = tbl.header_start
        nl_skip = (
            2 if raw_toml.startswith("\r\n", tbl.body_end) else int(raw_toml.startswith("\n", tbl.body_end))
        )
        del_end = tbl.body_end + nl_skip
        if del_end == tbl.body_end and del_end == len(raw_toml):
            if del_start >= 4 and raw_toml[del_start - 4 : del_start] == "\r\n\r\n":
                del_start -= 2
            elif del_start >= 2 and raw_toml[del_start - 2 : del_start] == "\n\n":
                del_start -= 1
        edits.append((del_start, del_end, ""))
    return edits, placed


def merge_owned_toml(raw_toml: str, managed: Mapping[str, Any], owned: tuple[OwnedKeyPath, ...]) -> str:
    """Merge ``managed`` into ``raw_toml`` at ``owned`` paths, preserving foreign comments verbatim."""
    ensure_mapping(managed)
    parsed_doc, layout = _TomlParser(raw_toml).parse()
    top_specs, tbl_specs = _classify_owned_specs(parsed_doc, layout, managed, owned)
    sec0_edits, new_top_lines = _collect_sec0_edits(raw_toml, layout, top_specs, tbl_specs)
    has_tables = any(
        not any(len(t.path) >= len(p) and t.path[: len(p)] == p for p, _, _ in tbl_specs)
        for t in layout.tables
    ) or any(present for _, present, _ in tbl_specs)
    sec0 = _rebuild_sec0(raw_toml, layout, sec0_edits, new_top_lines, has_tables=has_tables)
    tbl_edits, placed = _compute_table_edits(raw_toml, layout, tbl_specs)

    t_cursor = layout.first_table_start
    if tbl_edits and tbl_edits[0][0] < t_cursor:
        trim = t_cursor - tbl_edits[0][0]
        sec0 = sec0[:-trim] if len(sec0) >= trim else sec0
        tbl_edits[0] = (t_cursor, tbl_edits[0][1], tbl_edits[0][2])

    t_parts: list[str] = []
    for e_start, e_end, repl in tbl_edits:
        if e_start > t_cursor:
            t_parts.append(raw_toml[t_cursor:e_start])
        if repl:
            if t_parts and t_parts[-1] and not t_parts[-1].endswith("\n"):
                t_parts.append("\n")
            t_parts.append(repl)
        t_cursor = max(t_cursor, e_end)
    t_parts.append(raw_toml[t_cursor:])
    result = sec0 + "".join(t_parts)

    for tpath, present, tval in tbl_specs:
        if present and tval is not None and tpath not in placed:
            placed.add(tpath)
            rendered = format_toml_table(tpath, tval)
            if not result or result.endswith(("\n\n", "\r\n\r\n")):
                sep = ""
            else:
                sep = "\n" if result.endswith("\n") else "\n\n"
            result += sep + rendered
    return result
