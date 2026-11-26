#!/usr/bin/env bash
# Runs the gui tests (stdlib unittest; the locked backend packages are installed once by `gui deps ensure`).
# Usage: scripts/test.sh [-v]   (-v: verbose unittest output)
# The tests run against a throwaway HOME; they never touch the developer machine.
set -euo pipefail
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

# lib/ is the package gui; REPO_ROOT makes tests.* importable.
export PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# The locked third-party packages (requirements.lock) are installed into the real cache once, before HOME is replaced,
# and the tests find them through GUI_PYDEPS_DIR. Offline without a filled cache this fails instead of skipping tests.
GUI_PYDEPS_DIR="$(python3 -m gui.cli deps path)" || { echo "GUI_DEPS_UNAVAILABLE: cannot name the install folder" >&2; exit 1; }
python3 -m gui.cli deps ensure >/dev/null || { echo "GUI_DEPS_UNAVAILABLE: gui deps ensure failed" >&2; exit 1; }
export GUI_PYDEPS_DIR

# The configuration and state locations must not come from the developer machine.
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
export HOME="$TEST_HOME"
export SKM_CONTRACTS_STRICT=1  # an event or progress line that breaks its schema fails the test instead of being reported
unset SKM_HOME SKM_WORKSPACES SKM_WORKSPACES_ROOT SKM_WORKSPACE XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME SKM_UNITS_PATH

verbose=""
[[ "${1:-}" == "-v" ]] && verbose="-v"

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
