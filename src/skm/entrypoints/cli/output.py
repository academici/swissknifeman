"""CLI rendering (cli §1.1, §3, §4): human text, tables and the ``urn:skm:cli:envelope:v1`` JSON document.

Every byte that reaches a stream passes redaction first and then the safe terminal renderer, for success and
failure alike. Untrusted text (titles, paths, messages, external output) cannot drive the terminal: C0/C1/DEL,
ESC (hence CSI/OSC introducers), CR/LF/TAB inside a value, bidi controls and line/paragraph separators are
shown escaped (``\\x1b``, ``\\n``, ``\\u202e``). The CLI's own decoration is added after escaping and
``--no-color`` does not replace the escaping. ``--json`` keeps values in valid JSON strings with the same
characters escaped (``\\uXXXX``) and never adds ANSI decoration.

A ``human`` callback returns one line (``str``) or the lines of a block (``Sequence[str]``); a ``str`` is
never split, so a newline inside a value cannot forge a line. ``kv_lines`` and ``render_table`` escape the
values they are given themselves.

A registered credential never appears in what a value contributes, whatever its length or neighbours: after
redaction and escaping, each written block (a human block, a table line, the JSON envelope) is checked once
more as a whole by ``context.seal``, which masks the value characters of any occurrence that crosses a mask,
an escape, another value or the CLI's own framing. Fixed labels, JSON syntax, the envelope's member names,
``schema``, ``ok``, catalog codes and categories are framing and stay as they are.
"""

import json
import math
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from typing import Any, Final, Protocol, cast
from uuid import UUID

from skm.entrypoints.cli.context import Cell, CliContext, frame, seal, untrusted
from skm.kernel.error_codes import CATALOG, ErrorCategory
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.outcomes import Diagnostic, Waiting
from skm.kernel.pagination import Page
from skm.platform.logging.redaction import MASK, Redactor

__all__ = [
    "CLI_EXIT",
    "ENVELOPE_SCHEMA",
    "Column",
    "FindingLike",
    "escape_terminal",
    "kv_lines",
    "render",
    "render_error",
    "render_findings",
    "render_page",
    "render_table",
    "render_waiting",
    "safe_join",
    "safe_text",
    "to_jsonable",
]

ENVELOPE_SCHEMA: Final = "urn:skm:cli:envelope:v1"
# cli §4: the only table of exit codes, derived from the catalog's ``cli_exit`` (one value per category).


def _exit_table() -> Mapping[ErrorCategory, int]:
    table: dict[ErrorCategory, int] = {}
    for info in CATALOG.values():
        if table.setdefault(info.category, info.cli_exit) != info.cli_exit:
            raise RuntimeError(f"error catalog gives category {info.category.value!r} two exit codes")
    return table


CLI_EXIT: Final = _exit_table()
_BIDI: Final = frozenset(
    {0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x2028, 0x2029}
)
_NAMED_ESCAPES: Final = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}
_JSON_UNSAFE: Final = re.compile(
    r"[\u0080-\u009f\u007f\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ud800-\udfff]"
)
_GAP: Final = "  "
_REQUEST_PREFIX: Final = "cli-"  # trusted framing, including when the prefix equals a credential
_MASKED_SCALAR: Final = json.dumps(MASK, ensure_ascii=False)


class _Trust(Enum):
    """Trusted framing (``OWN``), untrusted values (``DATA``), and a request id with its trusted prefix."""

    OWN = "own"
    DATA = "data"
    REQUEST_ID = "request_id"  # the fixed prefix is framing, the generated rest is a value


# A mapping shape names the members the contract fixes (their names are framing); any other member is data.
type _Shape = _Trust | Mapping[str, _Shape] | tuple[_Shape]

_DIAGNOSTIC: Final[_Shape] = {
    "code": _Trust.DATA,  # a catalog code or a module's finding code
    "severity": _Trust.DATA,
    "message": _Trust.DATA,
    "target": _Trust.DATA,
}
_ERROR: Final[_Shape] = {
    "code": _Trust.OWN,
    "category": _Trust.OWN,
    "message": _Trust.DATA,
    "details": _Trust.DATA,
    "retryable": _Trust.OWN,  # trusted boolean status, including caller overrides
}
_OUTCOME: Final[_Shape] = {"kind": _Trust.OWN, "code": _Trust.OWN, "message": _Trust.DATA}
_PAGE: Final[_Shape] = {"items": _Trust.DATA, "next": _Trust.DATA}


def _envelope_shape(result: _Shape) -> _Shape:
    return {
        "schema": _Trust.OWN,
        "ok": _Trust.OWN,
        "command": _Trust.DATA,
        "request_id": _Trust.REQUEST_ID,
        "result": result,
        "diagnostics": (_DIAGNOSTIC,),
        "error": _ERROR,
        "outcome": _OUTCOME,
    }


def _escape_char(char: str) -> str:
    code = ord(char)
    if char in _NAMED_ESCAPES:
        return _NAMED_ESCAPES[char]
    if code in _BIDI or unicodedata.category(char) == "Cs":
        return f"\\u{code:04x}"
    if unicodedata.category(char) == "Cc":
        return f"\\x{code:02x}"
    return char


def escape_terminal(text: str) -> str:
    """``text`` with every character that could act on a terminal replaced by its escape."""
    return "".join(_escape_char(char) for char in text)


def _shown(ctx: CliContext, text: str) -> list[Cell]:
    """Untrusted text as cells: redacted, then escaped (the order that keeps a secret split by controls)."""
    return untrusted(ctx.redactor.text(text), escape_terminal)


def safe_text(ctx: CliContext, text: str) -> str:
    """Redact, then escape, then mask a credential that only the escaped form spells."""
    return seal(ctx.redactor, _shown(ctx, text))


def safe_join(ctx: CliContext, *parts: str | Cell) -> str:
    """Untrusted ``str`` parts joined with the CLI's own ``frame`` parts, checked as a whole.

    A credential is masked across the joins too; only value characters are masked, the framing stays.
    """
    cells: list[Cell] = []
    for part in parts:
        cells.extend([part] if isinstance(part, Cell) else _shown(ctx, part))
    return seal(ctx.redactor, cells)


def _block(ctx: CliContext, lines: Iterable[Sequence[Cell]]) -> str:
    """Lines, each ended by a newline, checked together (a virtual newline stands for the output before)."""
    cells = [frame("\n")]
    for line in lines:
        cells.extend(line)
        cells.append(frame("\n"))
    return seal(ctx.redactor, cells)[1:]


def _line(ctx: CliContext, cells: Sequence[Cell]) -> str:
    """One line handed to a caller that writes it with newlines around it."""
    return seal(ctx.redactor, [frame("\n"), *cells, frame("\n")])[1:-1]


def _lines(ctx: CliContext, lines: Sequence[Sequence[Cell]]) -> list[str]:
    """Seal a complete table or key/value block, including occurrences across its row boundaries."""
    return _block(ctx, lines).removesuffix("\n").split("\n") if lines else []


def _width(cells: Sequence[Cell]) -> int:
    return sum(len(cell.shown) for cell in cells)


def _rstrip(cells: Sequence[Cell]) -> list[Cell]:
    """``str.rstrip`` of the shown line: blanks that escaping keeps as they are (escapes are never blank)."""
    result = list(cells)
    while result:
        last = result[-1]
        if last.own:
            kept = last.shown.rstrip()
            if kept == last.shown:
                break
            if kept:
                result[-1] = frame(kept)
                break
        elif last.encode is not None:
            end = len(last.raw)
            while end and last.raw[end - 1].isspace() and last.encode(last.raw[end - 1]) == last.raw[end - 1]:
                end -= 1
            if end == len(last.raw):
                break
            if end:
                result[-1] = Cell(last.encode(last.raw[:end]), raw=last.raw[:end], encode=last.encode)
                break
        else:
            break
        result.pop()
    return result


def _write(stream: Any, text: str) -> None:
    if text:
        stream.write(text)


def _key(key: object) -> str:
    return str(key.value if isinstance(key, Enum) else key)


def to_jsonable(value: object) -> JsonValue:  # noqa: PLR0911 - one branch per JSON-able kind
    """A JSON value for a result. Finite decimals use strings to preserve precision.

    Every scalar comes back as its exact JSON type: a ``StrEnum``/``IntEnum`` member (or another
    ``str``/``int`` subclass) becomes a plain ``str``/``int``, because redaction accepts only exact JSON
    primitives.
    """
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite float is not JSON")
        return float(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError("non-finite Decimal is not JSON")
        return str(value)
    if isinstance(value, UUID | PurePath):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    to_json = getattr(value, "to_json", None)
    if callable(to_json) and not isinstance(value, type):
        return to_jsonable(to_json())
    if isinstance(value, Mapping):
        return {_key(key): to_jsonable(item) for key, item in cast("Mapping[object, object]", value).items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Iterable) and not isinstance(value, bytes | bytearray):
        return [to_jsonable(item) for item in cast("Iterable[object]", value)]
    raise TypeError(f"{type(cast('object', value)).__name__} is not a JSON value")


def _json_text(text: str) -> str:
    """The body of a JSON string: ``json.dumps`` escaping, control/bidi characters as ``\\uXXXX``."""
    body = json.dumps(text, ensure_ascii=False)[1:-1]
    return _JSON_UNSAFE.sub(lambda match: f"\\u{ord(match.group()):04x}", body)


def _emit_text(redactor: Redactor, text: str, shape: _Shape, cells: list[Cell]) -> None:
    cells.append(frame('"'))
    if shape is _Trust.OWN:
        cells.append(frame(_json_text(text)))
    else:
        if shape is _Trust.REQUEST_ID and text.startswith(_REQUEST_PREFIX):
            cells.append(frame(_REQUEST_PREFIX))
            text = text.removeprefix(_REQUEST_PREFIX)
        cells.extend(untrusted(redactor.text(text), _json_text))
    cells.append(frame('"'))


def _emit(redactor: Redactor, value: JsonValue, shape: _Shape, cells: list[Cell]) -> None:
    """Compact JSON cells, preserving framing and checking redacted values with ``seal`` later."""
    if type(value) is dict:
        cells.append(frame("{"))
        for index, (key, item) in enumerate(value.items()):
            member = shape.get(key) if isinstance(shape, Mapping) else None
            member = _Trust.OWN if shape is _Trust.OWN else member
            if index:
                cells.append(frame(","))
            _emit_text(redactor, key, _Trust.DATA if member is None else _Trust.OWN, cells)
            cells.append(frame(":"))
            _emit(redactor, item, _Trust.DATA if member is None else member, cells)
        cells.append(frame("}"))
    elif type(value) is list:
        each: _Shape = (
            shape[0] if isinstance(shape, tuple) else (shape if shape is _Trust.OWN else _Trust.DATA)
        )
        cells.append(frame("["))
        for index, item in enumerate(value):
            if index:
                cells.append(frame(","))
            _emit(redactor, item, each, cells)
        cells.append(frame("]"))
    elif type(value) is str:
        _emit_text(redactor, value, shape, cells)
    else:
        shown = json.dumps(value, allow_nan=False)
        if shape is _Trust.OWN:
            cells.append(frame(shown))
        elif isinstance(redactor.document(value), str):
            cells.append(frame(_MASKED_SCALAR))
        else:
            cells.append(Cell(shown, masked=_MASKED_SCALAR))


def _dump(ctx: CliContext, document: JsonObject, result: _Shape = _Trust.DATA) -> str:
    """The redacted document as one compact JSON line, with control/bidi characters escaped.

    The whole envelope is normalized first (result, diagnostics, outcome and error details alike), so an enum
    anywhere in it reaches redaction as its exact primitive value. Trusted framing (member names, ``schema``,
    ``ok``, catalog codes and categories, the ``cli-`` prefix of the request id) stays intact. The boolean
    ``retryable`` is also trusted, including caller overrides, even when its literal equals a credential.
    Other strings (including ``command`` and the request id suffix), keys and scalars remain data, and the
    whole line is sealed.
    """
    cells: list[Cell] = []
    _emit(ctx.redactor, to_jsonable(document), _envelope_shape(result), cells)
    return _line(ctx, cells)


def _envelope(ctx: CliContext, command: str, ok: bool, **parts: JsonValue) -> JsonObject:
    return {"schema": ENVELOPE_SCHEMA, "ok": ok, "command": command, "request_id": ctx.request_id, **parts}


def _diagnostics(items: Sequence[Diagnostic]) -> list[JsonValue]:
    return [
        {
            "code": to_jsonable(item.code),  # an ErrorCode member as well as a module finding code
            "severity": item.severity.value,
            "message": item.message,
            "target": item.target,
        }
        for item in items
    ]


def _paint(ctx: CliContext, stream: Any, text: str, sgr: str) -> str:
    """Own decoration (after escaping); only on a terminal and never when colour is off."""
    isatty = getattr(stream, "isatty", None)
    if ctx.color and callable(isatty) and isatty():
        return f"\x1b[{sgr}m{text}\x1b[0m"
    return text


def _human_lines(ctx: CliContext, text: str | Sequence[str]) -> list[list[Cell]]:
    lines = [text] if isinstance(text, str) else list(text)
    return [_shown(ctx, line) for line in lines]


def render(
    ctx: CliContext,
    result: object,
    *,
    human: Callable[[Any], str | Sequence[str]],
    command: str,
    diagnostics: Sequence[Diagnostic] = (),
    essential: Callable[[Any], str] | None = None,
) -> int:
    """Print ``result`` (envelope in ``--json``, ``human(result)`` otherwise) and return exit ``0``.

    ``--quiet`` prints only ``essential(result)`` (for example the id of a created object), or nothing.
    Diagnostics go to stderr in human mode and into the envelope in ``--json``.
    """
    if ctx.json:
        document = _envelope(
            ctx, command, True, result=to_jsonable(result), diagnostics=_diagnostics(diagnostics)
        )
        ctx.stdout.write(_dump(ctx, document) + "\n")
        return 0
    if ctx.quiet:
        if essential is not None:
            ctx.stdout.write(_block(ctx, [_shown(ctx, essential(result))]))
    else:
        _write(ctx.stdout, _block(ctx, _human_lines(ctx, human(result))))
        notes = (_shown(ctx, f"{item.severity.value}: {item.code}: {item.message}") for item in diagnostics)
        _write(ctx.stderr, _block(ctx, notes))
    return 0


@dataclass(frozen=True, slots=True)
class Column[T]:
    header: str
    value: Callable[[T], object]


def render_table(ctx: CliContext, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    """Aligned columns without borders; each cell is redacted and escaped, so a cell is always one line."""
    return _table(ctx, [_shown(ctx, header) for header in headers], rows)


def _table(ctx: CliContext, head: Sequence[Sequence[Cell]], rows: Sequence[Sequence[object]]) -> list[str]:
    cells = [[_shown(ctx, "" if item is None else str(item)) for item in row] for row in rows]
    widths = [max([_width(head[i]), *(_width(row[i]) for row in cells)]) for i in range(len(head))]
    lines: list[list[Cell]] = []
    for row in [head, *cells]:
        line: list[Cell] = []
        for i, cell in enumerate(row):
            pad = widths[i] - _width(cell)
            line.extend([*([frame(_GAP)] if i else []), *cell, *([frame(" " * pad)] if pad else [])])
        lines.append(_rstrip(line))
    return _lines(ctx, lines)


def kv_lines(ctx: CliContext, pairs: Sequence[tuple[str, object]]) -> list[str]:
    """``KEY  VALUE`` block for ``show`` commands; keys and values are redacted and escaped."""
    keys = [_shown(ctx, key) for key, _ in pairs]
    width = max((_width(key) for key in keys), default=0)
    return _lines(
        ctx,
        [
            _rstrip(
                [
                    *key,
                    frame(" " * (width - _width(key)) + _GAP),
                    *_shown(ctx, "" if value is None else str(value)),
                ]
            )
            for key, (_, value) in zip(keys, pairs, strict=True)
        ],
    )


def render_page[T](ctx: CliContext, page: Page[T], *, columns: Sequence[Column[T]], command: str) -> int:
    """A list result: ``{"items": [...], "next": cursor|null}`` in JSON, a table in human mode."""
    if ctx.json:
        result: JsonValue = {"items": [to_jsonable(item) for item in page.items], "next": page.next}
        ctx.stdout.write(
            _dump(ctx, _envelope(ctx, command, True, result=result, diagnostics=[]), _PAGE) + "\n"
        )
        return 0
    if not ctx.quiet:
        headers = [column.header for column in columns]
        rows = [[column.value(item) for column in columns] for item in page.items]
        for line in render_table(ctx, headers, rows):
            ctx.stdout.write(line + "\n")
        if page.next is not None:
            ctx.stderr.write("more results are available (use --all)\n")
    return 0


class FindingLike(Protocol):
    """The fields of ``FindingView`` the table shows (cli §1.1)."""

    @property
    def code(self) -> str: ...
    @property
    def severity(self) -> str: ...
    @property
    def entity(self) -> str | None: ...
    @property
    def message(self) -> str: ...


def render_findings(ctx: CliContext, findings: Sequence[FindingLike]) -> None:
    """Table ``code | severity | entity | message`` on stderr (``--json`` has them in the envelope)."""
    if not findings or ctx.json:
        return
    rows = [[f.code, f.severity, f.entity or "-", f.message] for f in findings]
    headers = [[frame(label)] for label in ("code", "severity", "entity", "message")]
    for line in _table(ctx, headers, rows):
        ctx.stderr.write(line + "\n")


def render_waiting(ctx: CliContext, waiting: Waiting, *, command: str) -> int:
    """A waiting outcome is not a failure: exit ``4`` with ``outcome.kind = waiting`` (cli §3, §4)."""
    outcome: JsonObject = {"kind": "waiting", "code": waiting.code.value, "message": waiting.message}
    if ctx.json:
        document = _envelope(ctx, command, True, outcome=outcome, result=None)
        ctx.stdout.write(_dump(ctx, document, _Trust.OWN) + "\n")
    elif not ctx.quiet:
        ctx.stdout.write(
            _block(ctx, [[frame(f"waiting: {waiting.code.value}: "), *_shown(ctx, waiting.message)]])
        )
    return CLI_EXIT[ErrorCategory.WAITING]


_REASON_CODE: Final = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")


def _reason_suffix(error: SkmError) -> str:
    """`` (reason: <code>)`` for an error whose ``details.reason`` is shaped like a code, else empty.

    Many errors share one message and differ only by that code (every backup and restore precondition is
    "Backup or recovery precondition failed"). Free-text reasons stay in ``--json`` only.
    """
    reason = error.details.get("reason")
    return f" (reason: {reason})" if isinstance(reason, str) and _REASON_CODE.fullmatch(reason) else ""


def _hints(error: SkmError) -> list[str]:
    hint = error.details.get("hint")
    if isinstance(hint, str):
        return [hint]
    if isinstance(hint, list):
        return [item for item in hint if isinstance(item, str)]
    return []


def _detail_rows(error: SkmError) -> list[str]:
    """``candidates:`` and schema ``issues`` blocks of the human error (example 09)."""
    rows: list[str] = []
    candidates = error.details.get("candidates")
    if isinstance(candidates, list) and candidates:
        rows.append("candidates:")
        for item in candidates:
            parts = item.values() if isinstance(item, dict) else [item]
            rows.append("  " + _GAP.join(str(part) for part in parts))
    issues = error.details.get("issues")
    if isinstance(issues, list):
        for item in issues:
            if isinstance(item, dict):
                code = item.get("code") or item.get("keyword") or ""
                rows.append(f"  {item.get('pointer', '')}   {code}   {item.get('message', '')}".rstrip())
    return rows


def render_error(ctx: CliContext, error: SkmError, *, command: str, extra: Sequence[str] = ()) -> int:
    """Print a structured error (envelope on stdout with --json, else ``error:`` lines on stderr)."""
    category = CATALOG[error.code].category
    if ctx.json:
        problem = error.to_problem()
        problem["category"] = category.value
        document = _envelope(ctx, command, False, error=problem)
        ctx.stdout.write(_dump(ctx, document) + "\n")
    else:
        prefix = _paint(ctx, ctx.stderr, "error:", "1;31")
        lines = [
            [frame(f"{prefix} {error.code.value}: "), *_shown(ctx, error.message + _reason_suffix(error))],
            *(_shown(ctx, row) for row in _detail_rows(error)),
            *([frame("hint: "), *_shown(ctx, hint)] for hint in _hints(error)),
            *(_shown(ctx, line) for line in extra),
        ]
        ctx.stderr.write(_block(ctx, lines))
    return CLI_EXIT[category]
