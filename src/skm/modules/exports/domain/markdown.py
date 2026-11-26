"""Deterministic Markdown primitives and byte-bounded table projections."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from . import frontmatter

type FrontmatterValue = frontmatter.FrontmatterValue
type Row = tuple[object, ...]

NOTE_BODY_MAX_BYTES = 262_144
_TERMINAL_CONTROLS = re.compile(
    r"[\x00-\x09\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u2028-\u202e\u2066-\u2069\ud800-\udfff]"
)


def _escape_controls(text: str) -> str:
    def escape(match: re.Match[str]) -> str:
        code = ord(match[0])
        return f"\\x{code:02x}" if code < 256 else f"\\u{code:04x}"

    return _TERMINAL_CONTROLS.sub(escape, text)


def _safe_field(value: FrontmatterValue) -> FrontmatterValue:
    if isinstance(value, str):
        return _escape_controls(value)
    if isinstance(value, tuple):
        return tuple(map(_escape_controls, value))
    return value


def digest(text: str) -> str:
    return "sha256:" + sha256(text.encode("utf-8")).hexdigest()


def one_line(text: object) -> str:
    return " ".join(str(text).replace("\x00", "�").split())


def cell(text: object) -> str:
    # Escape an existing backslash so it cannot cancel the escape before a pipe.
    return one_line(text).replace("\\", "\\\\").replace("|", "\\|")


def _row(values: Row) -> str:
    return "| " + " | ".join(_escape_controls(cell(value)) for value in values) + " |\n"


def table(columns: Row, rows: Iterable[Row]) -> str:
    return _row(columns) + _row(("---",) * len(columns)) + "".join(map(_row, rows))


def quote(text: str) -> str:
    return "\n".join(f"> {line}".rstrip() for line in text.replace("\x00", "�").splitlines())


def heading(title: str, level: int = 1) -> str:
    return f"{'#' * level} {one_line(title)}"


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def utf8_prefix(value: str, limit: int) -> str:
    return value.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


@dataclass(frozen=True, slots=True)
class MarkdownDoc:
    frontmatter: frontmatter.Fields
    body: str

    def __post_init__(self) -> None:
        body = _escape_controls(self.body)
        object.__setattr__(self, "body", body if body.endswith("\n") else body + "\n")

    def text(self) -> str:
        header = frontmatter.render(tuple((key, _safe_field(value)) for key, value in self.frontmatter))
        return f"{header}\n{self.body}" if header else self.body

    def digest(self) -> str:
        return digest(self.text())


def bounded_table(
    doc: MarkdownDoc, columns: Row, rows: Iterable[Row], *, total: int, ref: str, tail: str = ""
) -> MarkdownDoc:
    """Keep a stable prefix of whole rows and leave room for provenance and exact counts."""

    def marker(included: int) -> str:
        return (
            f"\ntruncated: true, total: {total}, included: {included}, omitted: {total - included}. "
            f"Full report: {ref}.\n"
        )

    table_head = table(columns, ())
    tail = _escape_controls(tail)
    fixed_size = len((doc.text() + table_head + tail).encode("utf-8"))
    available = NOTE_BODY_MAX_BYTES - fixed_size
    # Reserve enough digits for either count. The reservation has no effect on a full table that fits.
    reserve = len(marker(total).encode("utf-8")) + len(str(total))
    included: list[str] = []
    for values in rows:
        row = _row(values)
        size = len(row.encode("utf-8"))
        if size > available:
            break
        available -= size
        included.append(row)
    if len(included) < total:
        while included and available < reserve:
            available += len(included.pop().encode("utf-8"))
        tail = marker(len(included)) + tail
    result = MarkdownDoc(doc.frontmatter, doc.body + table_head + "".join(included) + tail)
    if len(result.text().encode("utf-8")) > NOTE_BODY_MAX_BYTES:
        raise ValueError("bounded projection requires a smaller fixed header")
    return result
