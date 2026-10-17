#!/usr/bin/env bash
# Runs the tests of the modules that read a partner module's output (harness; the tools analyst and maind with
# --with-tools) with every partner wired from the hub layout: the variables a module reads to find its partners point at
# packages/<id> of this checkout, so tests that need a partner run instead of being skipped. analyst and maind are
# auxiliary tools outside the core verification (standalone.tools): they join only with --with-tools. The end-to-end
# checks of planning in the portable workspace (scripts/e2e-workspace-plans.sh) and of the migration of plans into it
# (scripts/e2e-workspace-migrate.sh) run after the modules.
set -uo pipefail
HUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export AICORE_ROOT="$HUB/packages/aicore"
for module in maind analyst harness skiller brain orch; do
  upper="$(printf '%s' "$module" | tr '[:lower:]' '[:upper:]')"
  export "SKM_${upper}_ROOT=$HUB/packages/$module"
done
export PLANNER_ROOT="$HUB/packages/planner"
export PLANNER_PLAN_PY="$PLANNER_ROOT/scripts/plan.py"
export SKM_AICORE_EVENTS__DELIVERY=off
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
export HOME="$TEST_HOME" SKM_HOME="$TEST_HOME/skm"
unset XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME
unset SKM_ANALYST_BIN SKM_MAIND_BIN SKM_HARNESS_BIN SKM_SKILLER_BIN SKM_BRAIN_BIN SKM_ORCH_BIN MAIND_ANALYST_BIN

modules=(harness)
[[ "${1:-}" == "--with-tools" ]] && modules+=(analyst maind)
failed=()
count=0
for module in "${modules[@]}"; do
  count=$((count + 1))
  echo "== $module: bash packages/$module/scripts/test.sh"
  bash "$HUB/packages/$module/scripts/test.sh" || failed+=("$module")
done

count=$((count + 1))
echo "== workspace plans: bash scripts/e2e-workspace-plans.sh"
bash "$HUB/scripts/e2e-workspace-plans.sh" || failed+=("e2e-workspace-plans")

count=$((count + 1))
echo "== workspace migrate: bash scripts/e2e-workspace-migrate.sh"
bash "$HUB/scripts/e2e-workspace-migrate.sh" || failed+=("e2e-workspace-migrate")

if [[ "${#failed[@]}" -gt 0 ]]; then
  echo "integration: FAILURE (${failed[*]})" >&2
  exit 1
fi
echo "integration: OK ($count)"
