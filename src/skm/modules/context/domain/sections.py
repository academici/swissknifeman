"""Select Markdown subtrees or inclusive line ranges while preserving selected bytes."""

from __future__ import annotations

import re
from collections.abc import Sequence

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?)|[ \t]*)$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    headings: list[tuple[int, int, str]] = []
    fence = ""
    length = 0
    for index, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        marker = _FENCE.match(raw)
        if marker:
            run, tail = marker.groups()
            if not fence:
                fence, length = run[0], len(run)
            elif run[0] == fence and len(run) >= length and not tail.strip():
                fence = ""
            continue
        if fence:
            continue
        atx = _ATX.match(raw)
        if atx:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", atx[2] or "").strip()
            headings.append((index, len(atx[1]), title))
        elif index and _SETEXT.match(raw) and lines[index - 1].strip():
            if not (headings and headings[-1][0] == index - 1):
                headings.append(
                    (index - 1, 1 if raw.lstrip().startswith("=") else 2, lines[index - 1].strip())
                )
    return headings


def extract_sections(markdown: str, wanted: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    if "*" in wanted:
        return markdown, ("*",)
    lines = markdown.splitlines(keepends=True)
    headings = _headings(lines)
    targets = {name.strip().casefold() for name in wanted}
    selected: set[int] = set()
    titles: list[str] = []
    ancestors: list[tuple[int, str]] = []
    for number, (start, level, title) in enumerate(headings):
        ancestors = [(depth, name) for depth, name in ancestors if depth < level]
        ancestors.append((level, title.casefold()))
        dotted = ".".join(name for _, name in ancestors)
        if not any(
            title.casefold() == target or dotted == target or dotted.endswith("." + target)
            for target in targets
        ):
            continue
        end = next((pos for pos, depth, _ in headings[number + 1 :] if depth <= level), len(lines))
        selected.update(range(start, end))
        titles.append(title)
    return "".join(line for index, line in enumerate(lines) if index in selected), tuple(titles)


def extract_heading(markdown: str, heading: str) -> str:
    return extract_sections(markdown, (heading,))[0]


def extract_line_range(text: str, line_from: int, line_to: int) -> str:
    if line_from < 1 or line_to < line_from:
        raise ValueError("line range must be 1-based and inclusive")
    return "".join(text.splitlines(keepends=True)[line_from - 1 : line_to])
