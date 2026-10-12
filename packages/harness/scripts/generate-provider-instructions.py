#!/usr/bin/env python3
"""Write or verify the generated provider-instructions reference."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "lib"))

from harness.instructions import operator_reference  # noqa: E402


OUTPUT = PACKAGE / "docs" / "reference" / "provider-instructions.md"
COVERAGE = PACKAGE / "tests/fixtures_data/instruction-literal-coverage-v1.json"
COMPATIBILITY = PACKAGE / "tests/fixtures_data/instruction-compatibility-v1.json"
# hub-relative identifier recorded in the generated fixture, whatever the layout of this checkout
COMPATIBILITY_ID = "packages/harness/tests/fixtures_data/instruction-compatibility-v1.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = operator_reference()
    source = json.loads(COMPATIBILITY.read_text(encoding="utf-8"))
    literals = [{"semantic_id": row["id"], "literal": assertion}
                for row in source["records"] for assertion in row["assertions"]]
    coverage = json.dumps({
        "contract_version": source["contract_version"], "fixture_version": "1.7.0",
        "provenance": {"source": COMPATIBILITY_ID,
                       "source_hash_scope": "file",
                       "source_sha256": hashlib.sha256(COMPATIBILITY.read_bytes()).hexdigest(),
                       "generator": "packages/harness/scripts/generate-provider-instructions.py",
                       "literal_count": len(literals)},
        "literals": literals,
    }, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if (not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected
                or not COVERAGE.is_file() or COVERAGE.read_text(encoding="utf-8") != coverage):
            print("provider instructions reference: stale", file=sys.stderr)
            return 1
        print("provider instructions reference: OK")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    COVERAGE.write_text(coverage, encoding="utf-8")
    print(f"provider instructions reference: written packages/harness/{OUTPUT.relative_to(PACKAGE).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
