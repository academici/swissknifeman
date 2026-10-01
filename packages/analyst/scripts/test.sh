#!/usr/bin/env bash
# Running package tests lib/analyst (stdlib unittest, without dependencies and network).
# Launch: scripts/test.sh [-v]   (-v — verbose output unittest)
# Tests race logic against synthetic data in tmpdir (without demons/networks).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: tests require python3" >&2
  exit 1
fi

# lib/ — package analyst; REPO_ROOT — to be imported tests.*.
# MONOREPO_ROOT (two levels above the package) — to import the package `core`;
# optional: in standalone-directory layout core no, the path is not added.
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""
export PYTHONPATH="$REPO_ROOT/lib:$REPO_ROOT${MONOREPO_ROOT:+:$MONOREPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

verbose=""
[[ "${1:-}" == "-v" ]] && verbose="-v"

cd "$REPO_ROOT"
if [[ -n "$verbose" ]]; then
  python3 -m unittest discover -s tests -p "test_*.py" -v
else
  out="$(python3 -m unittest discover -s tests -p "test_*.py" 2>&1)" || {
    echo "$out" >&2
    echo "ERROR: tests failed" >&2
    exit 1
  }
  echo "tests: OK ($(echo "$out" | grep -oE 'Ran [0-9]+ tests' | head -1))"
fi
