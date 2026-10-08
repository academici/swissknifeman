#!/usr/bin/env python3
"""Tag vX.Y.Z must have a top RELEASED header `## [X.Y.Z] - YYYY-MM-DD` in CHANGELOG.md.

Umbrella version media - root CHANGELOG.md, not package.json (no root); P8.6, transfer
raytsystem verify_tag.py.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(REPO_ROOT, "packages/aicore/lib")]

from aicore.release.attestation import check  # noqa: E402
from aicore.release.changelog import parse_released  # noqa: E402

MALFORMED_MSG = (
    "released view header not found `## [X.Y.Z] - YYYY-MM-DD` in CHANGELOG.md"
)


def verify(tag, changelog_path):
    if tag.startswith("v"):
        version = tag[1:]
    else:
        version = tag
    if not os.path.isfile(changelog_path):
        return 2, MALFORMED_MSG
    with open(changelog_path, encoding="utf-8") as f:
        text = f.read()
    released, malformed = parse_released(text)
    if malformed and not released:
        return 2, MALFORMED_MSG
    if not released:
        return 1, f"tag {tag}: in CHANGELOG.md no title released (only [Unreleased])"
    if released[0] == version:
        return 0, f"tag {tag}: top released header matches ({version})"
    if version in released:
        return 1, f"tag {tag}: not the top released header (top - {released[0]})"
    return 1, f"tag {tag}: released header «{version}» not found in CHANGELOG.md"


def main(argv):
    if len(argv) != 2:
        print("usage: verify-tag.py <vX.Y.Z>", file=sys.stderr)
        return 2
    repo_root = REPO_ROOT
    code, message = verify(argv[1], os.path.join(repo_root, "CHANGELOG.md"))
    if not code and os.path.isfile(os.path.join(repo_root, ".agents/plugins/marketplace.json")):
        from pathlib import Path
        import json
        import subprocess
        try:
            path = Path(repo_root) / "releases" / ("v" + argv[1].removeprefix("v") + ".json")
            value = json.loads(path.read_text())
            tags = subprocess.run(["git", "tag", "--list", "v[0-9]*", "--sort=-version:refname"],
                                  cwd=repo_root, capture_output=True, text=True, check=True).stdout.splitlines()
            current = "v" + argv[1].removeprefix("v")
            previous = next((t for t in tags if t != current and
                             tuple(map(int, t[1:].split("."))) < tuple(map(int, current[1:].split(".")))), None)
            errors = check(Path(repo_root), value, previous_ref=previous,
                           package_root=Path(repo_root) / "packages/skiller")
            if errors:
                code, message = 1, "; ".join(errors)
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
            code, message = 1, "RELEASE_ATTESTATION_INVALID: " + str(exc)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
