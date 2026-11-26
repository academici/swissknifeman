"""Check local Markdown destinations and GitHub heading fragments without network IO."""

import argparse
import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from urllib.parse import unquote, urlsplit

_LINK = re.compile(
    r"\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]\(\s*(?:<(?P<angle>[^>\n]*)>|"
    r"(?P<bare>(?:\\.|[^()\s\\]|\([^()\n]*\))*))"
    r"(?:[ \t]+[\"'][^\n]*[\"'])?\s*\)"
)
_INLINE_CODE = re.compile(r"(`+).*?\1")
_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _prose(text: str) -> Iterator[tuple[int, str]]:
    fence = ""
    for number, line in enumerate(text.splitlines(), 1):
        match = _FENCE.match(line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = ""
            yield number, ""
        elif match:
            fence = match[1]
            yield number, ""
        else:
            yield number, line


def _anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    previous = ""
    for _, line in _prose(text):
        match = _HEADING.match(line)
        heading = ""
        if match:
            heading = re.sub(r"[ \t]+#+[ \t]*$", "", match[1])
        elif previous.strip() and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", line):
            heading = previous.strip()
        if heading:
            heading = _LINK.sub(lambda link: link[0].split("](", 1)[0][1:], heading)
            slug = "".join(char for char in heading.lower() if char.isalnum() or char in " -_")
            slug = slug.replace(" ", "-")
            candidate = slug
            suffix = 0
            while candidate in anchors:
                suffix += 1
                candidate = f"{slug}-{suffix}"
            anchors.add(candidate)
        previous = line
    return anchors


def check_file(path: Path) -> list[str]:
    """Return path:line diagnostics for missing local files or heading fragments."""
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [f"{path}:1: cannot read Markdown: {error}"]
    anchor_cache: dict[Path, set[str]] = {}
    for number, line in _prose(text):
        for match in _LINK.finditer(_INLINE_CODE.sub("", line)):
            target = match["angle"] if match["angle"] is not None else match["bare"]
            target = re.sub(r"\\([()\\ ])", r"\1", target)
            try:
                parts = urlsplit(target)
            except ValueError:
                errors.append(f"{path}:{number}: broken link {target}")
                continue
            if parts.scheme or parts.netloc:
                continue
            destination = path.parent / unquote(parts.path) if parts.path else path
            valid = destination.exists()
            if valid and parts.fragment:
                try:
                    if destination not in anchor_cache:
                        anchor_cache[destination] = _anchors(destination.read_text(encoding="utf-8"))
                    valid = unquote(parts.fragment) in anchor_cache[destination]
                except (OSError, UnicodeError):
                    valid = False
            if not valid:
                errors.append(f"{path}:{number}: broken link {target}")
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    """Check *.md recursively in each supplied path; exit 1 for any broken link."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    paths: list[Path] = args.paths
    files: set[Path] = set()
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            errors.append(f"{path}:1: broken link {path}")
        elif path.is_dir():
            files.update(path.rglob("*.md"))
        elif path.suffix == ".md":
            files.add(path)
    for path in sorted(files):
        errors.extend(check_file(path))
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
