#!/usr/bin/env python3
"""Тег vX.Y.Z обязан иметь верхний ВЫПУЩЕННЫЙ заголовок `## [X.Y.Z] - YYYY-MM-DD` в CHANGELOG.md.

Носитель версии зонтика — корневой CHANGELOG.md, не package.json (нет корневого); P8.6, перенос
raytsystem verify_tag.py.
"""
import os
import re
import sys

RELEASED_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$")
UNRELEASED_RE = re.compile(r"^## \[Unreleased\]$")
ANY_HEADER_RE = re.compile(r"^## \[")

MALFORMED_MSG = (
    "не найден выпущенный заголовок вида `## [X.Y.Z] - YYYY-MM-DD` в CHANGELOG.md"
)


def parse_changelog(text):
    """Возвращает (released, malformed): released — [(ver, date)] в порядке файла."""
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


def verify(tag, changelog_path):
    if tag.startswith("v"):
        version = tag[1:]
    else:
        version = tag
    if not os.path.isfile(changelog_path):
        return 2, MALFORMED_MSG
    with open(changelog_path, encoding="utf-8") as f:
        text = f.read()
    released, malformed = parse_changelog(text)
    if malformed and not released:
        return 2, MALFORMED_MSG
    if not released:
        return 1, f"тег {tag}: в CHANGELOG.md нет выпущенного заголовка (только [Unreleased])"
    if released[0] == version:
        return 0, f"тег {tag}: верхний выпущенный заголовок совпадает ({version})"
    if version in released:
        return 1, f"тег {tag}: не верхний выпущенный заголовок (верхний — {released[0]})"
    return 1, f"тег {tag}: выпущенный заголовок «{version}» не найден в CHANGELOG.md"


def main(argv):
    if len(argv) != 2:
        print("использование: verify-tag.py <vX.Y.Z>", file=sys.stderr)
        return 2
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code, message = verify(argv[1], os.path.join(repo_root, "CHANGELOG.md"))
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
