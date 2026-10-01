#!/usr/bin/env python3
"""Render the committed `.cursor/rules/*.mdc` from canonical sources.

Catalog-backed root.cursor sections, observe policy bindings, and command-routing
selectors are projected into static Cursor rules. These files enter the context of
every Cursor session, so drift here is more expensive than usual.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages/harness/lib"))
sys.path.insert(0, str(REPO_ROOT))

from harness.cursor_render import check_cursor_rules, write_cursor_rules  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true",
                       help="fail when a committed rule drifted from the catalog")
    group.add_argument("--write", action="store_true", help="regenerate the committed rules")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.check:
        drift = check_cursor_rules(root)
        for path in drift:
            print(f"drift: {path}", file=sys.stderr)
        if drift:
            print("render-cursor-rules: run --write, rules are edited by the generator",
                  file=sys.stderr)
            return 1
        print("render-cursor-rules: check OK (no-op)")
        return 0

    written = write_cursor_rules(root)
    for path in written:
        print(f"wrote: {path}")
    print(f"render-cursor-rules: {len(written)} rule(s) changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
