#!/usr/bin/env python3
"""Validate valid/invalid fixture verdicts in one interpreter, using the public CLI entry point."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys

# scripts/orch.py would otherwise shadow the package when this file is launched directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from orch import cli  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    args = parser.parse_args(argv)
    checked, mismatched = 0, 0
    for directory in args.directories:
        for category, expected in (("valid", 0), ("invalid", 1)):
            for path in sorted((directory / category).glob("*/*.json")):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    try:
                        code = cli.main(["validate", path.parent.name, str(path), "--quiet"])
                    except SystemExit as error:
                        code = error.code if isinstance(error.code, int) else 0 if error.code is None else 1
                checked += 1
                if code != expected:
                    mismatched += 1
                    print(f"{path}: exit {code}, expected {expected}")
    print(f"fixtures: {checked} checked, {mismatched} mismatched")
    return 1 if mismatched else 0


if __name__ == "__main__":
    sys.exit(main())
