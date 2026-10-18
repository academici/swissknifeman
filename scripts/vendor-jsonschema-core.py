#!/usr/bin/env python3
"""Keep the planner copy of the schema validator core equal to the one of aicore.

`packages/aicore/lib/aicore/util/jsonschema_core.py` is the one implementation of the closed-profile JSON Schema
check; planner runs without aicore, so it carries a byte-for-byte copy at
`packages/planner/lib/planner/plan/_jsonschema_core.py`. Edit the aicore file, then run `--write`.

  --check   exit 1 and print a unified diff when the copy differs (the golden generator `jsonschema-core-planner` runs it)
  --write   replace the copy
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/aicore/lib/aicore/util/jsonschema_core.py"
COPY = ROOT / "packages/planner/lib/planner/plan/_jsonschema_core.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    parser.add_argument("--root", default=str(ROOT), help="repository root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    source, copy = root / SOURCE.relative_to(ROOT), root / COPY.relative_to(ROOT)
    want = source.read_text(encoding="utf-8")
    have = copy.read_text(encoding="utf-8") if copy.is_file() else ""
    if want == have:
        print("vendor-jsonschema-core: ok")
        return 0
    if args.write:
        copy.write_text(want, encoding="utf-8")
        print(f"wrote: {copy.relative_to(root)}")
        return 0
    sys.stderr.writelines(difflib.unified_diff(have.splitlines(True), want.splitlines(True),
                                               str(copy.relative_to(root)), str(source.relative_to(root))))
    print("vendor-jsonschema-core: the planner copy drifted; run --write", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
