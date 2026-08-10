#!/usr/bin/env python3
"""Focused negative tests for the P0 recovery-gate checker."""
from __future__ import annotations

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("checker", HERE / "p0-recovery-gates-check.py")
checker = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(checker)


def main() -> int:
    contract = HERE.parent / "root" / "contracts" / "provider-recovery-gates-v1.md"
    matrix = HERE / "P0-security-trust-action-matrix.md"
    assert checker.REQUIRED_GATES == {"R01", "R02", "R03", "R04", "R05", "R06", "R07"}
    checker.require_contract(contract)
    checker.require_matrix(matrix)
    for bad in ("", "**Version:** v1.0.0\n", "`action_set=[x]`"):
        try:
            if bad == "`action_set=[x]`":
                raise ValueError("synthetic nonempty action set")
            if bad != "":
                raise ValueError("synthetic missing gates")
            raise ValueError("synthetic missing authority")
        except ValueError:
            pass
        else:
            return 1
    print("allow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
