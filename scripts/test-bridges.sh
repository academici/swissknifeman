#!/usr/bin/env bash
# Runs the tests of every bridge of the hub (bridges/<id>/unit.json, dev.test) with the partners wired from the hub
# layout: the environment variables a bridge reads to find its partners point at packages/<id> of this checkout.
set -uo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PLANNER_ROOT="$HUB/packages/planner"
export PLANNER_PLAN_PY="$PLANNER_ROOT/scripts/plan.py"
export SKM_ORCH_ROOT="$HUB/packages/orch"
export SKM_SKILLER_ROOT="$HUB/packages/skiller"
export SKM_HARNESS_ROOT="$HUB/packages/harness"
export AICORE_ROOT="$HUB/packages/aicore"
export SKM_AICORE_EVENTS__DELIVERY=off
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
export HOME="$TEST_HOME" SKM_HOME="$TEST_HOME/skm"
unset XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME

failed=()
count=0
for unit in "$HUB"/bridges/*/unit.json; do
  [[ -f "$unit" ]] || continue
  dir="$(dirname "$unit")"
  name="$(basename "$dir")"
  mapfile -t argv < <(python3 -c 'import json, sys; print("\n".join(json.load(open(sys.argv[1]))["dev"]["test"]))' "$unit") \
    || { echo "bridges: $name: no dev.test in unit.json" >&2; failed+=("$name"); continue; }
  count=$((count + 1))
  echo "== $name: ${argv[*]}"
  (cd "$dir" && "${argv[@]}") || failed+=("$name")
done

if [[ "$count" -eq 0 ]]; then
  echo "bridges: FAILURE (no bridge with dev.test found)" >&2
  exit 1
fi
if [[ "${#failed[@]}" -gt 0 ]]; then
  echo "bridges: FAILURE (${failed[*]})" >&2
  exit 1
fi
echo "bridges: OK ($count)"
