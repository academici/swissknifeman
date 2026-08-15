#!/usr/bin/env bash
set -uo pipefail

changed="$( { git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u | grep -v '^$')"
[ -n "$changed" ] || exit 0

plan_ids="$(printf '%s\n' "$changed" | grep -oE '^plans/[^/]+/' | sed -E 's#^plans/##; s#/$##' | sort -u)"
[ -n "$plan_ids" ] || exit 0

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
vc_py="$repo_root/packages/task/scripts/verify-plan-citations.py"
[ -f "$vc_py" ] || exit 0   # No citation gate in this tree.

violations=0
while IFS= read -r pid; do
  [ -n "$pid" ] || continue
  [ -d "$repo_root/plans/$pid" ] || continue
  out="$(python3 "$vc_py" "$repo_root/plans/$pid" --strict 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then
    while IFS= read -r line; do
      case "$line" in
        *"→"*)
          after="${line#*→ }"
          echo "plans/$pid: ${after}"
          ;;
      esac
    done <<< "$out"
    violations=1
  fi
done <<< "$plan_ids"

exit "$violations"
