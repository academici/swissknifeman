#!/usr/bin/env bash
# Run `plan.py check` for every changed plan directory that has a plan.json; other directories are skipped.
set -uo pipefail

changed="$( { git -c core.quotepath=false diff --name-only 2>/dev/null; git -c core.quotepath=false diff --cached --name-only 2>/dev/null; git -c core.quotepath=false ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -v '^$')"
[ -n "$changed" ] || exit 0

plan_dirs="$(printf '%s\n' "$changed" | grep -oE '^plans/[^/]+/' | sed -E 's#/$##' | sort -u)"
[ -n "$plan_dirs" ] || exit 0

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
plan_py="$repo_root/packages/task/scripts/plan.py"
[ -f "$plan_py" ] || exit 0   # No plan CLI in this tree.

violations=0
while IFS= read -r dir; do
  [ -n "$dir" ] || continue
  [ -f "$repo_root/$dir/plan.json" ] || continue
  out="$(python3 "$plan_py" check "$repo_root/$dir" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    first_error="$(printf '%s\n' "$out" | grep -i 'error' | head -1)"
    echo "$dir: plan.py check failed — ${first_error:-run plan.py check $dir}"
    violations=1
  fi
done <<< "$plan_dirs"

exit "$violations"
