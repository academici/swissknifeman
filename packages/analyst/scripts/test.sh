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

# --- aicore locator ---
# Finds the aicore foundation: $AICORE_ROOT, then <module>/_vendor/aicore, then the sibling <module>/../aicore.
# Canonical copy: packages/aicore/scripts/aicore-locator.sh; copies must stay identical.
_aicore_ok() { [ -f "$1/unit.json" ] && grep -q '"id": *"aicore"' "$1/unit.json"; }
if [ -n "${AICORE_ROOT:-}" ]; then
  _aicore_ok "$AICORE_ROOT" || { echo "AICORE_NOT_FOUND: AICORE_ROOT=$AICORE_ROOT is not an aicore checkout" >&2; exit 2; }
elif _aicore_ok "$REPO_ROOT/_vendor/aicore"; then
  AICORE_ROOT="$REPO_ROOT/_vendor/aicore"
elif _aicore_ok "$REPO_ROOT/../aicore"; then
  AICORE_ROOT="$(cd "$REPO_ROOT/../aicore" && pwd)"
else
  echo "AICORE_NOT_FOUND: no aicore in \$AICORE_ROOT, $REPO_ROOT/_vendor/aicore or $REPO_ROOT/../aicore; set AICORE_ROOT" >&2
  exit 2
fi
export AICORE_ROOT
AICORE_LIB="$AICORE_ROOT/lib"
unset -f _aicore_ok
# --- end aicore locator ---

# lib/ — package analyst; REPO_ROOT — to be imported tests.*.
export PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Tests run against a throwaway HOME; the configuration and state locations must not come from the
# developer machine.
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
export HOME="$TEST_HOME"
unset SKM_HOME XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME SKM_UNITS_PATH

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
