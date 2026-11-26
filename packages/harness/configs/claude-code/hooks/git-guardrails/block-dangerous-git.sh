#!/bin/bash

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

# Argv-level check (git_guard.py next to this script): `git -C . push`, `git  push`, `git clean -df`,
# `git branch --delete --force`, `bash -c "git push"`, aliases... The patterns below stay as a safety net.
GUARD="$(dirname "${BASH_SOURCE[0]}")/git_guard.py"
if command -v python3 >/dev/null 2>&1 && [ -f "$GUARD" ]; then
  printf '%s' "$INPUT" | python3 "$GUARD"
  [ $? -eq 2 ] && exit 2
fi
COMMAND=$(echo "$COMMAND" | tr -s '[:space:]' ' ')

DANGEROUS_PATTERNS=(
  "git push"
  "git reset --hard"
  "git clean -fd"
  "git clean -f"
  "git branch -D"
  "git checkout \."
  "git restore \."
  "push --force"
  "push --force-with-lease"
  "reset --hard"
  "rebase --onto"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qE "$pattern"; then
    echo "BLOCKED: '$COMMAND' coincided with a dangerous pattern '$pattern'. User has disabled this command." >&2
    exit 2
  fi
done

exit 0
