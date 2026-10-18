#!/usr/bin/env bash
# test.sh — the tests of planner (tests/ and the plan engine tests/engine) in a throwaway home; the quick check of a
# change. scripts/validate.sh runs them too, with the structural checks and the plan checks.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
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

# Tests read the layered configuration: give them an empty machine home instead of the real one; planner.* events
# stay undelivered (test_events enables delivery itself).
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
hermetic() { env -u SKM_WORKSPACES -u SKM_WORKSPACES_ROOT -u SKM_WORKSPACE HOME="$TEST_HOME" SKM_HOME="$TEST_HOME" SKM_AICORE_EVENTS__DELIVERY=off "$@"; }
# Tests run in parallel worker processes when the foundation (aicore) is importable; plain unittest otherwise.
# SKM_TEST_JOBS=1 gives the sequential run.
UT=(python3 -m unittest)
if PYTHONPATH="$AICORE_LIB" python3 -c "import aicore.util.par_unittest" 2>/dev/null; then UT=(python3 -m aicore.util.par_unittest); fi
# the two suites are independent and run side by side; each prints its own result when it ends
fail=0
pids=()
for start in tests tests/engine; do
  ( hermetic PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB${PYTHONPATH:+:$PYTHONPATH}" \
      "${UT[@]}" discover -s "$start" -p "test_*.py" >"$TEST_HOME/${start//\//-}.log" 2>&1 && status=0 || status=$?
    echo "== $start"; tail -n 40 "$TEST_HOME/${start//\//-}.log"; exit "$status" ) &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || fail=1; done
[ "$fail" = 0 ] || echo "FAIL: planner unittest" >&2
exit "$fail"
