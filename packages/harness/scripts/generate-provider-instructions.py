#!/usr/bin/env python3
"""Write or verify the generated provider-instructions reference."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "harness" / "lib"))

from harness.instructions import operator_reference  # noqa: E402


OUTPUT = ROOT / "packages" / "harness" / "docs" / "reference" / "provider-instructions.md"
COVERAGE = ROOT / "packages/harness/tests/fixtures_data/instruction-literal-coverage-v1.json"
COMPATIBILITY = ROOT / "packages/harness/tests/fixtures_data/instruction-compatibility-v1.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = operator_reference()
    source = json.loads(COMPATIBILITY.read_text(encoding="utf-8"))
    literals = [{"semantic_id": row["id"], "literal": assertion}
                for row in source["records"] for assertion in row["assertions"]]
    coverage = json.dumps({
        "contract_version": source["contract_version"], "fixture_version": "1.4.0",
        "provenance": {"source": str(COMPATIBILITY.relative_to(ROOT)),
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
    print(f"provider instructions reference: written {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
