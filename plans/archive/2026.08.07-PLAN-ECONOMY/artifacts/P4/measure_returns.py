#!/usr/bin/env python3
"""Read-only historic Return Fingerprint v1 measurement."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "packages/task/lib"))

from task import plan_returns  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = plan_returns.measure_repository(ROOT)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(f"{result['journals']} journals; {result['entries']} entries; {result['return_events']} return events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
