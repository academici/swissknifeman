"""The ``filesystem`` research source: the lines of local files that answer a query, each cited by path and line.

Only what :mod:`orch.research.local_files` allows is read; every returned line is redacted before it can reach a
prompt. The walk stops once the best matches fill the answer or after :data:`MAX_FILES` files.
"""
from __future__ import annotations

import os
from pathlib import Path

from aicore.util.redact import redact_text
from orch.research import local_files
from orch.research.matching import line_score, terms_of

MAX_MATCHES = 50
MAX_FILES = 5000          # files looked at in one query: a root that is a whole disk does not run for ever


def inside(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return False
    return True


def _tops(roots: tuple, base: Path) -> list:
    """The roots as absolute folders; a relative root that links out of the project is dropped."""
    tops = []
    for root in roots:
        top = Path(os.path.expanduser(root))
        relative = not top.is_absolute() and not root.startswith("~")
        top = top if top.is_absolute() else base / top
        if not relative or inside(top, base):
            tops.append(top)
    return tops


class _Collector:
    """The matches of one query, best first when chosen, in the order found otherwise."""

    def __init__(self, text: str, base: Path):
        self.needle, self.terms, self.base = text.strip().lower(), terms_of(text), base
        self.top_score = len(self.terms) + 1
        self.found: list = []  # (score, order, row, file)
        self.looked = 0

    def full(self) -> bool:  # nothing found later can rank above what is already collected
        best = sum(1 for hit in self.found if hit[0] == self.top_score)
        return self.looked >= MAX_FILES or best >= MAX_MATCHES

    def add(self, path: Path, lines: list) -> None:
        try:
            shown = str(path.relative_to(self.base))
        except ValueError:
            shown = str(path)
        for number, line in enumerate(lines, 1):
            score = line_score(line, self.needle, self.terms)
            if score:
                self.found.append((score, len(self.found), f"{shown}:{number}: {redact_text(line.strip())}", shown))

    def chosen(self) -> list:
        return sorted(sorted(self.found, key=lambda hit: (-hit[0], hit[1]))[:MAX_MATCHES], key=lambda hit: hit[1])


def _files(top: Path):
    """The readable candidates under ``top``: symlinked folders are not followed, skipped and secret names never seen."""
    visible = local_files.git_visible(top)
    for folder, dirs, names in os.walk(top):
        dirs[:] = sorted(name for name in dirs if name not in local_files.SKIPPED_DIRS)
        for name in sorted(names):
            path = Path(folder) / name
            if local_files.is_secret_name(name):
                continue
            if visible is not None and str(path.resolve()) not in visible:
                continue  # git ignores it: build output, caches and local secrets stay out
            yield path


def search(roots: tuple, text: str, base: Path) -> dict:
    """``{text, sources}``: the matching lines (``path:line: text``) and the files they come from."""
    collector = _Collector(text, base)
    for top in _tops(roots, base):
        for path in _files(top):
            if collector.full():
                break
            collector.looked += 1
            content = local_files.read_text(path)
            if content is not None:
                collector.add(path, content.splitlines())
        if collector.full():
            break
    chosen = collector.chosen()
    return {"text": "\n".join(hit[2] for hit in chosen), "sources": list(dict.fromkeys(hit[3] for hit in chosen))}
