#!/usr/bin/env bash
# Run the dependency-free lib/skiller unittest suite.
# Usage: scripts/test.sh [-v] (`-v` enables detailed unittest output).
# Tests use the synthetic tmpdir registry from tests/fixtures.py and never alter
# the real registry. This runner is also called by validate.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: тесты требуют python3" >&2
  exit 1
fi

# lib/ contains skiller; REPO_ROOT makes tests.fixtures importable.
# MONOREPO_ROOT makes core importable when this package is in the monorepo;
# standalone layouts do not add a nonexistent core directory.
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""
export PYTHONPATH="$REPO_ROOT/lib:$REPO_ROOT${MONOREPO_ROOT:+:$MONOREPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

verbose=""
[[ "${1:-}" == "-v" ]] && verbose="-v"

# Tests exercise the real CLI, including expected reports and WARN/ERROR output.
# Capture that output by default and print it only when a test fails; `-v` keeps
# the raw output for focused debugging.
cd "$REPO_ROOT"
if [[ -n "$verbose" ]]; then
  python3 -m unittest discover -s tests -p "test_*.py" -v
else
  out="$(python3 -m unittest discover -s tests -p "test_*.py" 2>&1)" || {
    echo "$out" >&2
    echo "ERROR: тесты упали" >&2
    exit 1
  }
  echo "tests: OK ($(echo "$out" | grep -oE 'Ran [0-9]+ tests' | head -1))"
fi
