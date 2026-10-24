#!/usr/bin/env bash
# test.sh [-p PATTERN] — discover tests/ once, including tests/engine, in a throwaway home.
# scripts/validate.sh also runs this suite unless its caller has already run the full set.
set -euo pipefail
PATTERN='test_*.py'
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p)
      [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || { echo "usage: test.sh [-p PATTERN]" >&2; exit 2; }
      PATTERN="$2"; shift 2 ;;
    *) echo "usage: test.sh [-p PATTERN]" >&2; exit 2 ;;
  esac
done
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
export SKM_CONTRACTS_STRICT=1  # an event that breaks its schema fails the test instead of being reported
hermetic() { env -u SKM_WORKSPACES -u SKM_WORKSPACES_ROOT -u SKM_WORKSPACE HOME="$TEST_HOME" SKM_HOME="$TEST_HOME" SKM_AICORE_EVENTS__DELIVERY=off "$@"; }
# Tests run in parallel worker processes when the foundation (aicore) is importable; plain unittest otherwise.
# SKM_TEST_JOBS=1 gives the sequential run.
UT=(python3 -m unittest)
if PYTHONPATH="$AICORE_LIB" python3 -c "import aicore.util.par_unittest" 2>/dev/null; then UT=(python3 -m aicore.util.par_unittest); fi
# Recursive discovery already includes engine; a second start directory would run it twice.
hermetic PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB${PYTHONPATH:+:$PYTHONPATH}" \
  "${UT[@]}" discover -s tests -p "$PATTERN" >"$TEST_HOME/tests.log" 2>&1 && status=0 || status=$?
echo "== tests"
if [[ "$status" = 0 ]]; then
  tail -n 40 "$TEST_HOME/tests.log"
else
  cat "$TEST_HOME/tests.log"
fi
[[ "$status" = 0 ]] || echo "FAIL: planner unittest" >&2
exit "$status"
