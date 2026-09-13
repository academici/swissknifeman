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
    if not code and os.path.isfile(os.path.join(repo_root, ".agents/plugins/marketplace.json")):
        from pathlib import Path
        import json
        import subprocess
        sys.path[:0] = [repo_root, os.path.join(repo_root, "packages/skiller/lib")]
        from skiller.release_attestation import check
        try:
            path = Path(repo_root) / "releases" / ("v" + argv[1].removeprefix("v") + ".json")
            value = json.loads(path.read_text())
            tags = subprocess.run(["git", "tag", "--list", "v[0-9]*", "--sort=-version:refname"],
                                  cwd=repo_root, capture_output=True, text=True, check=True).stdout.splitlines()
            current = "v" + argv[1].removeprefix("v")
            previous = next((t for t in tags if t != current and
                             tuple(map(int, t[1:].split("."))) < tuple(map(int, current[1:].split(".")))), None)
            errors = check(Path(repo_root), value, previous_ref=previous)
            if errors:
                code, message = 1, "; ".join(errors)
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
            code, message = 1, "RELEASE_ATTESTATION_INVALID: " + str(exc)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
