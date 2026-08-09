#!/usr/bin/env python3
"""Emit the current normalized plan-session identity."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "lib"))

from task import session_context  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Показать provider-neutral session context")
    subparsers = parser.add_subparsers(dest="command", required=True)
    current = subparsers.add_parser("current")
    output = current.add_mutually_exclusive_group(required=True)
    output.add_argument("--json", action="store_true")
    output.add_argument("--id", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(session_context.current_json() if args.json else session_context.current_id())
    except session_context.SessionContextError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
