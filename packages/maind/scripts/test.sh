#!/usr/bin/env bash
# Run lib/maind tests with stdlib unittest and no external dependencies.
# Usage: scripts/test.sh [-v] (`-v` enables verbose unittest output).
# Tests use a synthetic tmpdir hub and FakeMemoryServer; no live daemon is needed.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: тесты требуют python3" >&2
  exit 1
fi

# lib/ contains maind and REPO_ROOT exposes tests.fixtures.
# MONOREPO_ROOT exposes core when this package runs inside the monorepo; standalone
# layouts do not add a nonexistent core path.
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
    echo "ERROR: тесты упали" >&2
    exit 1
  }
  echo "tests: OK ($(echo "$out" | grep -oE 'Ran [0-9]+ tests' | head -1))"
fi
