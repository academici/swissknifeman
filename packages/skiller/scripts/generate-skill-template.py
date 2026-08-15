#!/usr/bin/env python3
"""Render the generated generate-skill template from the EN canonical template."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = PACKAGE_ROOT / "SKILL_TEMPLATE.md"
GENERATED = PACKAGE_ROOT / "generate-skill" / "generate-skill" / "snippets" / "SKILL_TEMPLATE.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="refuse generated-template drift")
    args = parser.parse_args()

    canonical = CANONICAL.read_bytes()
    if args.check:
        if not GENERATED.is_file() or GENERATED.read_bytes() != canonical:
            print("SKILL_TEMPLATE_GENERATED_DRIFT: regenerate with scripts/generate-skill-template.py", file=sys.stderr)
            return 1
        print("skill template: generated copy is byte-stable")
        return 0

    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_bytes(canonical)
    print(f"skill template: generated {GENERATED.relative_to(PACKAGE_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
