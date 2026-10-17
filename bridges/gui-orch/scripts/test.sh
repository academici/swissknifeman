#!/usr/bin/env bash
# Tests of the gui-orch bridge. Partners come from the environment (AICORE_ROOT, SKM_GUI_ROOT; `bash
# scripts/test-bridges.sh` at the hub root wires them), else from the hub registry (`swissknifeman units list --json`):
# the bridge never looks at a neighbouring folder.
set -euo pipefail
BRIDGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BRIDGE_ROOT"

_unit_root() {  # the root of hub unit $1 from the registry, or nothing
  command -v swissknifeman >/dev/null 2>&1 || return 0
  swissknifeman units list --json 2>/dev/null | python3 -c '
import json, os, sys
doc = json.load(sys.stdin)
for unit in doc.get("units", []):
    if unit.get("id") == sys.argv[1]:
        print(os.path.join(doc.get("hub_root", ""), unit["root"]))
' "$1" || true
}
AICORE_ROOT="${AICORE_ROOT:-$(_unit_root aicore)}"
SKM_GUI_ROOT="${SKM_GUI_ROOT:-$(_unit_root gui)}"
for pair in "AICORE_ROOT:$AICORE_ROOT" "SKM_GUI_ROOT:$SKM_GUI_ROOT"; do
  if [ -z "${pair#*:}" ] || [ ! -d "${pair#*:}/lib" ]; then
    echo "BRIDGE_PARTNER_UNAVAILABLE: ${pair%%:*} not found (set ${pair%%:*} or install swissknifeman)" >&2
    exit 3
  fi
done
export AICORE_ROOT SKM_GUI_ROOT
export PYTHONPATH="$AICORE_ROOT/lib:$SKM_GUI_ROOT/lib:$BRIDGE_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# The tests never touch the developer's HOME, state or event delivery.
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
export HOME="$TEST_HOME" SKM_HOME="$TEST_HOME/skm" SKM_AICORE_EVENTS__DELIVERY=off
unset XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME SKM_UMBRELLA

out="$(python3 -m unittest discover -s tests -t . -p "test_*.py" "$@" 2>&1)" || { echo "$out" >&2; echo "ERROR: tests failed" >&2; exit 1; }
echo "tests: OK ($(echo "$out" | grep -oE 'Ran [0-9]+ tests' | head -1))"
