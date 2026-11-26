#!/usr/bin/env python3
"""Mirror orch's run-options schema into this bridge, which supplies it to the planner's ``orchestration.options`` slot.

    sync-schema.py [--check]

orch owns the contract (``schemas/conductor/v1/run-options.schema.json`` of ``SKM_ORCH_ROOT`` or the ``orch`` on PATH);
the planner reads a slot schema only from a file inside the bridge, so this file is a generated mirror, never edited by
hand. ``--check`` exits 1 when the mirror differs (the bridge tests run the same comparison).
"""
from __future__ import annotations

import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BRIDGE))

import partners  # noqa: E402

MIRROR = BRIDGE / "schemas" / "run-options.schema.json"


def main(argv=None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    source = partners.require_orch() / "schemas" / "conductor" / "v1" / "run-options.schema.json"
    wanted = source.read_bytes()
    if MIRROR.is_file() and MIRROR.read_bytes() == wanted:
        return 0
    if check:
        print(f"SCHEMA_DRIFT: {MIRROR.relative_to(BRIDGE)} differs from {source}; run scripts/sync-schema.py", file=sys.stderr)
        return 1
    MIRROR.write_bytes(wanted)
    print(f"mirrored {source} -> {MIRROR.relative_to(BRIDGE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
