#!/usr/bin/env bash
# Run the dependency-free lib/skiller unittest suite.
# Usage: scripts/test.sh [-v] (`-v` enables detailed unittest output).
# Tests use the synthetic tmpdir registry from tests/fixtures.py and never alter
# the real registry. This runner is also called by validate.sh.
set -euo pipefail
if [[ $# -gt 1 || ( $# -eq 1 && "${1:-}" != "-v" ) ]]; then
  echo "ERROR: unsupported test runner arguments; usage: scripts/test.sh [-v]" >&2
  exit 2
fi
# Tests run in parallel worker processes when the foundation (aicore) is importable; plain unittest otherwise.
# SKM_TEST_JOBS=1 gives the old sequential run.
_unittest() {
  if python3 -c "import aicore.util.par_unittest" 2>/dev/null; then python3 -m aicore.util.par_unittest "$@"; else python3 -m unittest "$@"; fi
}

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

# lib/ contains skiller; REPO_ROOT makes tests.fixtures importable.
export PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Dev clone (PLAN3 D13): tests run against a throwaway HOME, never the real one; the entry-point
# guard refuses CLI runs that reach the real HOME.
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
export HOME="$TEST_HOME"
export SKM_CONTRACTS_STRICT=1  # an event or progress line that breaks its schema fails the test instead of being reported

verbose=""
[[ "${1:-}" == "-v" ]] && verbose="-v"

# Tests exercise the real CLI, including expected reports and WARN/ERROR output.
# Capture that output by default and print it only when a test fails; `-v` keeps
# the raw output for focused debugging.
cd "$REPO_ROOT"
if [[ -n "$verbose" ]]; then
  _unittest discover -s tests -p "test_*.py" -v
else
  out="$(_unittest discover -s tests -p "test_*.py" 2>&1)" || {
    echo "$out" >&2
    echo "ERROR: tests failed" >&2
    exit 1
  }
  echo "tests: OK ($(echo "$out" | grep -oE 'Ran [0-9]+ tests' | head -1))"
fi
