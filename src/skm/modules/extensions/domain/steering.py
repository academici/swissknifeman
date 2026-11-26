"""Steering manifests and TOML front matter."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.extensions.domain.keys import SemVer, parse_resource_key

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject
    from skm.modules.extensions.domain.keys import ResourceKey


@dataclass(frozen=True, slots=True)
class SteeringScope:
    is_global: bool
    projects: tuple[str, ...]
    directories: tuple[str, ...]
    languages: tuple[str, ...]
    task_types: tuple[str, ...]
    risk: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SteeringManifest:
    key: ResourceKey
    version: SemVer
    title: str
    applies_to: tuple[str, ...]
    priority: int
    conflicts_with: tuple[ResourceKey, ...]
    scope: SteeringScope


def _invalid(reason: str, *, path: str = "") -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, reason, details={"reason": reason, "path": path})


def parse_toml_front_matter(text: str, *, path: str = "") -> tuple[JsonObject, str]:
    lines = text.split("\n")
    if lines[0].strip() != "+++":
        return {}, text
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == "+++":
            try:
                return cast(
                    "JsonObject",
                    json.loads(json.dumps(_TomlParser("\n".join(lines[1:index])).parse(), allow_nan=False)),
                ), "\n".join(lines[index + 1 :])
            except (ValueError, TypeError) as exc:
                raise _invalid("toml_invalid", path=path) from exc
    raise _invalid("front_matter_unterminated", path=path)


def parse_steering_manifest(data: Mapping[str, object]) -> SteeringManifest:
    def invalid() -> ValidationFailed:
        return _invalid("manifest_invalid")

    def string(value: object) -> str:
        if not isinstance(value, str):
            raise invalid()
        return value

    def array(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise invalid()
        return tuple(string(item) for item in cast("list[object]", value))

    if set(data) - {"schema", "key", "version", "title", "applies_to", "priority", "conflicts_with", "scope"}:
        raise invalid()
    if data.get("schema") != "urn:skm:extensions:steering:v1":
        raise invalid()
    raw_scope = data.get("scope")
    if not isinstance(raw_scope, Mapping):
        raise invalid()
    scope = cast("Mapping[str, object]", raw_scope)
    if set(scope) - {
        "global",
        "projects",
        "directories",
        "languages",
        "task_types",
        "risk",
    }:
        raise invalid()
    global_scope = scope.get("global", False)
    priority = data.get("priority", 0)
    if not isinstance(global_scope, bool) or type(priority) is not int or not 0 <= priority <= 100:
        raise invalid()
    roles = array(data.get("applies_to", []))
    if set(roles) - {"scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar"}:
        raise invalid()
    return SteeringManifest(
        key=parse_resource_key(string(data.get("key")), prompt_block=False),
        version=SemVer.parse(string(data.get("version"))),
        title=string(data.get("title", "")),
        applies_to=roles,
        priority=priority,
        conflicts_with=tuple(
            parse_resource_key(key, prompt_block=False) for key in array(data.get("conflicts_with", []))
        ),
        scope=SteeringScope(
            is_global=global_scope,
            projects=array(scope.get("projects", [])),
            directories=array(scope.get("directories", [])),
            languages=array(scope.get("languages", [])),
            task_types=array(scope.get("task_types", [])),
            risk=array(scope.get("risk", [])),
        ),
    )


# Pure TOML parser shared in design with integrations.domain.merged_toml.
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


def _toml_invalid() -> NoReturn:
    raise ValueError("invalid TOML")


def _is_disallowed_ctrl(ch: str, *, allow_lf: bool) -> bool:
    if ch == "\t" or (allow_lf and ch == "\n"):
        return False
    low_end = "\x08" if allow_lf else "\x1f"
    return ("\x00" <= ch <= low_end) or ("\x0b" <= ch <= "\x1f") or ch == "\x7f"


class _TomlParser:
    """Strict pure-Python TOML 1.0 parser."""

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
                    _toml_invalid()
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
        _toml_invalid()

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
                _toml_invalid()
            else:
                break

    def _read_basic_escape(self) -> str:
        if self.pos >= self.n:
            _toml_invalid()
        esc = self.src[self.pos]
        if esc in _BASIC_ESCAPES:
            self.pos += 1
            return _BASIC_ESCAPES[esc]
        if esc in ("u", "U"):
            self.pos += 1
            digits = 4 if esc == "u" else 8
            hex_part = self.src[self.pos : self.pos + digits]
            if len(hex_part) != digits or _HEX_RE.fullmatch(hex_part) is None:
                _toml_invalid()
            code = int(hex_part, 16)
            if code > 0x10FFFF or 0xD800 <= code <= 0xDFFF:
                _toml_invalid()
            self.pos += digits
            return chr(code)
        _toml_invalid()

    def _skip_line_ending_backslash_ws(self) -> None:
        saw_nl = False
        while self.pos < self.n and self.src[self.pos] in (" ", "\t", "\r", "\n"):
            if self.src[self.pos] == "\r" and not self.src.startswith("\r\n", self.pos):
                _toml_invalid()
            if self.src[self.pos] == "\n":
                saw_nl = True
            self.pos += 1
        if not saw_nl:
            _toml_invalid()

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
                    _toml_invalid()
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
                _toml_invalid()
            else:
                out.append(ch)
                self.pos += 1
        _toml_invalid()

    def _parse_single_str(self, quote: str, *, allow_escapes: bool) -> str:
        self.pos += 1
        out: list[str] = []
        while self.pos < self.n:
            ch = self.src[self.pos]
            if ch == quote:
                self.pos += 1
                return "".join(out)
            if ch in ("\n", "\r") or _is_disallowed_ctrl(ch, allow_lf=False):
                _toml_invalid()
            if allow_escapes and ch == "\\":
                self.pos += 1
                out.append(self._read_basic_escape())
            else:
                out.append(ch)
                self.pos += 1
        _toml_invalid()

    def _parse_key_segment(self) -> str:
        self._skip_ws()
        if self.pos >= self.n:
            _toml_invalid()
        ch = self.src[self.pos]
        if ch in ('"', "'"):
            if self.src.startswith(ch * 3, self.pos):
                _toml_invalid()
            return self._parse_single_str(ch, allow_escapes=(ch == '"'))
        m = _BARE_SEG_RE.match(self.src, self.pos)
        if m is None:
            _toml_invalid()
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
                _toml_invalid()
            if self.src[self.pos] == ",":
                self.pos += 1
                continue
            if self.src[self.pos] == "]":
                self.pos += 1
                return items
            _toml_invalid()

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
                _toml_invalid()
            self.pos += 1
            self._insert_into_mapping(
                table, key_path, self._parse_value(), prefix=(), local_tables=local_tables
            )
            self._skip_ws()
            if self.pos >= self.n:
                _toml_invalid()
            if self.src[self.pos] == "}":
                self.pos += 1
                self._freeze_inline_tree(table)
                return table
            if self.src[self.pos] == ",":
                self.pos += 1
                self._skip_ws()
                if self.pos >= self.n or self.src[self.pos] in ("}", "\n", "\r"):
                    _toml_invalid()
                continue
            _toml_invalid()

    def _read_scalar_token(self) -> str:
        m = _TOKEN_RE.match(self.src, self.pos)
        if m is None:
            _toml_invalid()
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
            _toml_invalid()
        try:
            return int(digits.replace("_", ""), base)
        except ValueError:
            _toml_invalid()

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
            _toml_invalid()
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
        _toml_invalid()

    def _parse_value(self) -> Any:
        self._skip_ws()
        if self.pos >= self.n:
            _toml_invalid()
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
                _toml_invalid()
            if seg not in current:
                new_tbl: dict[str, Any] = {}
                current[seg] = new_tbl
                local_tables.add(cur_path)
                self.dotted_defined_tables.add(cur_path)
                current = new_tbl
            else:
                existing: Any = current[seg]
                if not isinstance(existing, dict):
                    _toml_invalid()
                existing_dict = cast("dict[str, Any]", existing)
                if id(existing_dict) in self.inline_frozen_ids or (
                    cur_path not in local_tables and cur_path not in self.dotted_defined_tables
                ):
                    _toml_invalid()
                current = existing_dict
        leaf = key_path[-1]
        if leaf in current or id(current) in self.inline_frozen_ids:
            _toml_invalid()
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
                    _toml_invalid()
                current = arr[-1]
            elif isinstance(current[seg], dict):
                tbl = cast("dict[str, Any]", current[seg])
                if id(tbl) in self.inline_frozen_ids:
                    _toml_invalid()
                current = tbl
            else:
                _toml_invalid()
        return current

    def _open_array_table(self, parent: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
        last = path[-1]
        if path in (self.explicit_tables | self.implicit_super_tables | self.dotted_defined_tables):
            _toml_invalid()
        if last not in parent:
            arr: list[dict[str, Any]] = [{}]
            parent[last] = arr
            self.array_tables.add(path)
            self._reset_subtables_under(path)
            return arr[0]
        existing: Any = parent[last]
        if not isinstance(existing, list) or path not in self.array_tables:
            _toml_invalid()
        new_elem: dict[str, Any] = {}
        cast("list[dict[str, Any]]", existing).append(new_elem)
        self._reset_subtables_under(path)
        return new_elem

    def _open_std_table(self, parent: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
        last = path[-1]
        if path in (self.explicit_tables | self.dotted_defined_tables | self.array_tables):
            _toml_invalid()
        if last not in parent:
            tbl: dict[str, Any] = {}
            parent[last] = tbl
            self.explicit_tables.add(path)
            return tbl
        existing: Any = parent[last]
        if not isinstance(existing, dict) or path not in self.implicit_super_tables:
            _toml_invalid()
        existing_tbl = cast("dict[str, Any]", existing)
        if id(existing_tbl) in self.inline_frozen_ids:
            _toml_invalid()
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
            _toml_invalid()
        self.pos += len(closer)
        return is_array, tpath, self._consume_newline_or_eof()

    def parse(self) -> dict[str, Any]:
        current_table = self.root
        current_prefix: tuple[str, ...] = ()
        local_dotted: set[tuple[str, ...]] = set()
        while self.pos < self.n:
            self._skip_ws()
            if self.pos >= self.n:
                break
            if self.src[self.pos] in ("\r", "\n", "#"):
                self._consume_newline_or_eof()
                continue
            if self.src[self.pos] == "[":
                is_arr, tpath, _ = self._parse_header_line()
                parent = self._walk_table_parents(tpath)
                current_table = (
                    self._open_array_table(parent, tpath) if is_arr else self._open_std_table(parent, tpath)
                )
                current_prefix = tpath
                local_dotted = set()
                continue
            key_path = self._parse_dotted_key()
            self._skip_ws()
            if self.pos >= self.n or self.src[self.pos] != "=":
                _toml_invalid()
            self.pos += 1
            val = self._parse_value()
            self._consume_newline_or_eof()
            self._insert_into_mapping(
                current_table, key_path, val, prefix=current_prefix, local_tables=local_dotted
            )
        return self.root
