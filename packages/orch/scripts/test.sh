#!/usr/bin/env bash
set -euo pipefail
# Tests run in parallel worker processes when the foundation (aicore) is importable; plain unittest otherwise.
# SKM_TEST_JOBS=1 gives the old sequential run.
_unittest() {
  if python3 -c "import aicore.util.par_unittest" 2>/dev/null; then python3 -m aicore.util.par_unittest "$@"; else python3 -m unittest "$@"; fi
}
ORCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$ORCH_ROOT"

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
# Runners change directory: keep the foundation path absolute for the interpreter and the children.
AICORE_ROOT="$(cd "$AICORE_ROOT" && pwd)"
AICORE_LIB="$AICORE_ROOT/lib"
export AICORE_ROOT

cd "$ORCH_ROOT"
# The tests never touch the developer's HOME, state or event delivery.
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
export HOME="$TEST_HOME" SKM_HOME="$TEST_HOME/skm" SKM_AICORE_EVENTS__DELIVERY=off
unset XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME
PYTHONPATH="lib:$AICORE_LIB" _unittest discover -s tests -t . "$@"
