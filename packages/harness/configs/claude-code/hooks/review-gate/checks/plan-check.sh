#!/usr/bin/env bash
# Run `plan.py check` for every changed plan directory that has a plan.json; other directories are skipped.
set -uo pipefail

changed="$( { git -c core.quotepath=false diff --name-only 2>/dev/null; git -c core.quotepath=false diff --cached --name-only 2>/dev/null; git -c core.quotepath=false ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -v '^$')"
[ -n "$changed" ] || exit 0

plan_dirs="$(printf '%s\n' "$changed" | grep -oE '^plans/[^/]+/' | sed -E 's#/$##' | sort -u)"
[ -n "$plan_dirs" ] || exit 0

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# Planner lookup (the order of aicore.util.partners): PLANNER_PLAN_PY -> PLANNER_ROOT/scripts/plan.py -> `planner`
# or `plan.py` (the link install.sh makes) on PATH. Not found: skip the check.
plan_cmd=()
if [ -n "${PLANNER_PLAN_PY:-}" ] && [ -f "$PLANNER_PLAN_PY" ]; then
  plan_cmd=(python3 "$PLANNER_PLAN_PY")
elif [ -n "${PLANNER_ROOT:-}" ] && [ -f "$PLANNER_ROOT/scripts/plan.py" ]; then
  plan_cmd=(python3 "$PLANNER_ROOT/scripts/plan.py")
elif command -v planner >/dev/null 2>&1; then
  plan_cmd=(planner)
elif command -v plan.py >/dev/null 2>&1; then
  plan_cmd=(plan.py)
fi
if [ "${#plan_cmd[@]}" -eq 0 ]; then
  echo "plan-check: planner not found (set PLANNER_ROOT)" >&2
  exit 0
fi

violations=0
while IFS= read -r dir; do
  [ -n "$dir" ] || continue
  [ -f "$repo_root/$dir/plan.json" ] || continue
  out="$("${plan_cmd[@]}" check "$repo_root/$dir" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    first_error="$(printf '%s\n' "$out" | grep -i 'error' | head -1)"
    echo "$dir: plan.py check failed — ${first_error:-run plan.py check $dir}"
    violations=1
  fi
done <<< "$plan_dirs"

exit "$violations"
