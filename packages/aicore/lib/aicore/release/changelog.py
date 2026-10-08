"""The CHANGELOG format: the `[Unreleased]` section, its move under a version heading, the released headings.

Keep a Changelog layout: `## [Unreleased]` on top, then `## [X.Y.Z] - YYYY-MM-DD` per release. stdlib only.
"""
import re
from datetime import date

# Released-heading grammar, shared by the tag check and the release proposal.
RELEASED_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$")
UNRELEASED_RE = re.compile(r"^## \[Unreleased\]$")
ANY_HEADER_RE = re.compile(r"^## \[")

# Lenient forms used while editing the file: spacing and case of the section title are not significant.
UNRELEASED_SECTION_RE = re.compile(r"^##\s*\[Unreleased\]\s*$", re.IGNORECASE)
NEXT_HEADING_RE = re.compile(r"^##\s*\[")


def parse_released(text):
    """Returns (released, malformed): released — [version] in file order."""
    released = []
    malformed = False
    for line in text.splitlines():
        if not ANY_HEADER_RE.match(line):
            continue
        if UNRELEASED_RE.match(line):
            continue
        m = RELEASED_RE.match(line)
        if m:
            released.append(m.group(1))
        else:
            malformed = True
    return released, malformed


def read_unreleased_section(text):
    """(lines, start, end, body) sections `## [Unreleased]` text CHANGELOG.
    `body` — lines between title and next `## [...]` (or end of file),
    WITHOUT the title itself. None — section is not in the file."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if UNRELEASED_SECTION_RE.match(ln):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if NEXT_HEADING_RE.match(lines[j]):
            end = j
            break
    return lines, start, end, lines[start + 1:end]


def unreleased_is_empty(body_lines):
    """Empty = not a single non-empty line, not counting `###`-group subheadings
    Keep a Changelog (`### Added` without entries - also «empty»)."""
    return not any(ln.strip() and not ln.strip().startswith("###") for ln in body_lines)


def release_changelog(text, new_version):
    """Text CHANGELOG after transfer `[Unreleased]` → `[new_version] - <date>`:
    old section is freed (empty `## [Unreleased]`), its contents go under
    new version header. Does not affect other sections of the file."""
    lines, start, end, body = read_unreleased_section(text)
    new_heading = f"## [{new_version.removeprefix('v')}] - {date.today().isoformat()}"
    new_lines = (lines[:start] + ["## [Unreleased]", "", new_heading]
                 + body + lines[end:])
    return "\n".join(new_lines) + "\n"
