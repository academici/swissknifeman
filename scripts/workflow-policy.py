#!/usr/bin/env python3
"""Supply-chain policy of the GitHub workflows (.github/workflows/*.yml).

  workflow-policy.py [--root DIR]     # exit 1 and one line per violation

- every `uses:` of an outside action names a full commit SHA, with the readable version in a comment
  (`owner/action@<40 hex>  # vX.Y.Z`): a tag can be moved under the same name, a commit cannot;
- every workflow declares its top-level `permissions:` (the token is narrowed first, a job widens it);
- no command ends in `|| true`: a failing step must not turn green.
"""
import argparse
import re
import sys
from pathlib import Path

USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"#\s*v\d")
FAIL_OPEN = re.compile(r"\|\|\s*true\b")
TOP_PERMISSIONS = re.compile(r"^permissions:", re.MULTILINE)


def check_text(name: str, text: str) -> list:
    errors = [] if TOP_PERMISSIONS.search(text) else [f"{name}: WORKFLOW_PERMISSIONS_MISSING: no top-level permissions"]
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        used = USES.match(line)
        if used and not used.group(1).startswith("./"):
            if not PINNED.match(used.group(1)):
                errors.append(f"{name}:{number}: ACTION_UNPINNED: {used.group(1)} (pin a full commit SHA)")
            elif not VERSION_COMMENT.search(used.group(2)):
                errors.append(f"{name}:{number}: ACTION_VERSION_COMMENT_MISSING: {used.group(1)}")
        if FAIL_OPEN.search(line.split(" #")[0]):
            errors.append(f"{name}:{number}: STEP_FAIL_OPEN: `|| true` hides a failure")
    return errors


def check(root: Path) -> list:
    errors = []
    for path in sorted((root / ".github/workflows").glob("*.y*ml")):
        errors.extend(check_text(path.name, path.read_text(encoding="utf-8")))
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    errors = check(Path(parser.parse_args(argv).root))
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
