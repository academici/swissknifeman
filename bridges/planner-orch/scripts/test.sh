#!/usr/bin/env bash
# Tests of this bridge. Partners come from the environment (PLANNER_ROOT, SKM_ORCH_ROOT, SKM_SKILLER_ROOT,
# SKM_HARNESS_ROOT, AICORE_ROOT); `bash scripts/test-bridges.sh` at the hub root wires them from the hub layout.
set -euo pipefail
BRIDGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BRIDGE_ROOT"
# The tests never touch the developer's HOME, state or event delivery.
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
unset SKM_WORKSPACES SKM_WORKSPACES_ROOT SKM_WORKSPACE
export HOME="$TEST_HOME" SKM_HOME="$TEST_HOME/skm" SKM_AICORE_EVENTS__DELIVERY=off
export SKM_CONTRACTS_STRICT=1  # an event or progress line that breaks its schema fails the test instead of being reported
unset XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME
# Parallel worker processes when aicore is importable (its locator: AICORE_ROOT); SKM_TEST_JOBS=1 runs them one by one.
if [ -n "${AICORE_ROOT:-}" ] && PYTHONPATH="$AICORE_ROOT/lib" python3 -c "import aicore.util.par_unittest" 2>/dev/null; then
  PYTHONPATH="$AICORE_ROOT/lib${PYTHONPATH:+:$PYTHONPATH}" python3 -m aicore.util.par_unittest discover -s tests -t tests -p "test_*.py" "$@"
else
  python3 -m unittest discover -s tests -t tests -p "test_*.py" "$@"
fi
