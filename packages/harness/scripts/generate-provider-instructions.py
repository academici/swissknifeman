#!/usr/bin/env python3
"""Write or verify the generated provider-instructions reference."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "harness" / "lib"))

from harness.instructions import operator_reference  # noqa: E402


OUTPUT = ROOT / "packages" / "harness" / "docs" / "reference" / "provider-instructions.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = operator_reference()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print("provider instructions reference: stale", file=sys.stderr)
            return 1
        print("provider instructions reference: OK")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"provider instructions reference: written {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
