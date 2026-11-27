"""Pure codec for HTML-comment managed blocks in markdown/text files (integrations §4.5)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Final, Literal

__all__ = [
    "BlockMarker",
    "extract_blocks",
    "is_valid_block_id",
    "parse_markers",
    "render_block",
    "replace_blocks",
]

_BLOCK_ID_PATTERN: Final[str] = r"[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*"
_BLOCK_ID_RE: Final[re.Pattern[str]] = re.compile(rf"^{_BLOCK_ID_PATTERN}$")
_BEGIN_LINE_RE: Final[re.Pattern[bytes]] = re.compile(
    rf"^<!-- skm:begin id=({_BLOCK_ID_PATTERN}) digest=([0-9a-f]{{12}}) -->\r?\n$".encode("ascii")
)
_END_LINE_WITH_NL_RE: Final[re.Pattern[bytes]] = re.compile(
    rf"^<!-- skm:end id=({_BLOCK_ID_PATTERN}) -->\r?\n$".encode("ascii")
)
_END_LINE_EOF_RE: Final[re.Pattern[bytes]] = re.compile(
    rf"^<!-- skm:end id=({_BLOCK_ID_PATTERN}) -->$".encode("ascii")
)
_LOCAL_MARKER_RE = re.compile(rb"<!-- skm:local:(?:start|end) -->[ \t]*(?:\r?\n)?")
_SKM_COMMENT_HINT_RE: Final[re.Pattern[bytes]] = re.compile(rb"<!--\s*skm(?::|\b)")


@dataclass(frozen=True, slots=True)
class BlockMarker:
    kind: Literal["begin", "end"]
    block_id: str
    digest: str | None
    start: int
    end: int


def is_valid_block_id(block_id: str) -> bool:
    """Return True when ``block_id`` matches the canonical dotted identifier syntax."""
    return _BLOCK_ID_RE.fullmatch(block_id) is not None


def _iter_byte_lines(raw: bytes) -> list[tuple[bytes, int, int]]:
    """Split ``raw`` strictly on ``\\n`` preserving exact byte offsets."""
    lines: list[tuple[bytes, int, int]] = []
    pos = 0
    total = len(raw)
    while pos < total:
        nl = raw.find(b"\n", pos)
        end = total if nl == -1 else nl + 1
        lines.append((raw[pos:end], pos, end))
        pos = end
    return lines


def parse_markers(raw: bytes) -> tuple[BlockMarker, ...] | None:
    """Scan ``raw`` for SKM block markers; return ``None`` if any SKM marker line is malformed."""
    markers: list[BlockMarker] = []
    total = len(raw)
    for line, start, end in _iter_byte_lines(raw):
        begin_match = _BEGIN_LINE_RE.fullmatch(line)
        if begin_match is not None:
            markers.append(
                BlockMarker(
                    kind="begin",
                    block_id=begin_match.group(1).decode("ascii"),
                    digest=begin_match.group(2).decode("ascii"),
                    start=start,
                    end=end,
                )
            )
            continue
        end_match = _END_LINE_WITH_NL_RE.fullmatch(line)
        if end_match is None and end == total:
            end_match = _END_LINE_EOF_RE.fullmatch(line)
        if end_match is not None:
            markers.append(
                BlockMarker(
                    kind="end",
                    block_id=end_match.group(1).decode("ascii"),
                    digest=None,
                    start=start,
                    end=end,
                )
            )
            continue
        if _LOCAL_MARKER_RE.fullmatch(line.lstrip(b" \t")):
            continue
        if _SKM_COMMENT_HINT_RE.search(line) is not None:
            return None
    return tuple(markers)


def _valid_block_id_sequence(block_ids: tuple[str, ...]) -> bool:
    return len(set(block_ids)) == len(block_ids) and all(is_valid_block_id(bid) for bid in block_ids)


def _extract_spans(raw: bytes, block_ids: tuple[str, ...]) -> list[tuple[int, int]] | None:
    if not _valid_block_id_sequence(block_ids):
        return None
    markers = parse_markers(raw)
    if markers is None:
        return None
    if not markers:
        return []

    spans: list[tuple[str, int, int]] = []
    seen_ids: set[str] = set()
    open_begin: BlockMarker | None = None
    for marker in markers:
        if marker.kind == "begin":
            if open_begin is not None or marker.block_id in seen_ids:
                return None
            open_begin = marker
            seen_ids.add(marker.block_id)
        else:
            if open_begin is None or open_begin.block_id != marker.block_id:
                return None
            spans.append((open_begin.block_id, open_begin.start, marker.end))
            open_begin = None

    if open_begin is not None:
        return None

    found_ids = tuple(bid for bid, _, _ in spans)
    if found_ids != block_ids:
        return None
    return [(start, end) for _, start, end in spans]


def render_block(block_id: str, body: str) -> bytes:
    """Render a single managed block with begin/end markers and 12-hex SHA-256 digest."""
    if not is_valid_block_id(block_id):
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")
    normalized_lines = body.replace("\r\n", "\n").rstrip("\n")
    normalized_body = f"{normalized_lines}\n" if normalized_lines else ""
    digest12 = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()[:12]
    rendered = (
        f"<!-- skm:begin id={block_id} digest={digest12} -->\n"
        f"{normalized_body}"
        f"<!-- skm:end id={block_id} -->\n"
    )
    return rendered.encode("utf-8")


def extract_blocks(raw: bytes, block_ids: tuple[str, ...]) -> bytes | None:
    """Extract concatenated rendered blocks in ``block_ids`` order, ``b''`` if absent, or ``None``."""
    spans = _extract_spans(raw, block_ids)
    if spans is None:
        return None
    if not spans:
        return b""
    return b"".join(raw[start:end] for start, end in spans)


def _apply_replace(raw: bytes, managed: bytes, block_ids: tuple[str, ...]) -> bytes:
    raw_spans = _extract_spans(raw, block_ids)
    if raw_spans is None:
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")

    if managed == b"":
        if not raw_spans:
            return raw
        replacement_spans = [b"" for _ in block_ids]
    else:
        if not block_ids:
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")
        managed_spans = _extract_spans(managed, block_ids)
        if managed_spans is None or len(managed_spans) != len(block_ids):
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")
        replacement_spans = [managed[start:end] for start, end in managed_spans]
        if b"".join(replacement_spans) != managed:
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")

    if not raw_spans:
        if not raw or raw.endswith(b"\n"):
            return raw + managed
        return raw + b"\n" + managed

    chunks: list[bytes] = []
    cursor = 0
    for (start, end), new_span in zip(raw_spans, replacement_spans, strict=True):
        chunks.append(raw[cursor:start])
        chunks.append(new_span)
        cursor = end
    chunks.append(raw[cursor:])
    return b"".join(chunks)


def replace_blocks(raw: bytes, managed: bytes, block_ids: tuple[str, ...]) -> bytes:
    """Replace or append managed blocks in ``raw`` while preserving outside bytes verbatim."""
    old_extracted = extract_blocks(raw, block_ids)
    if old_extracted is None:
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")

    result = _apply_replace(raw, managed, block_ids)
    if extract_blocks(result, block_ids) != managed:
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")

    expected_roundtrip = (
        raw + b"\n" if (old_extracted == b"" and managed != b"" and raw and not raw.endswith(b"\n")) else raw
    )
    # Removal preserves the unowned slices in place. Re-inserting into a document
    # with no managed markers would append after any user-written suffix.
    if managed and _apply_replace(result, old_extracted, block_ids) != expected_roundtrip:
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")
    return result
