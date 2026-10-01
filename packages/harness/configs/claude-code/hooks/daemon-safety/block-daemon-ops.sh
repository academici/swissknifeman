#!/bin/bash

[ "$PERPLEXITY_DAEMON_GUARD" = "off" ] && exit 0

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

KILL_PATTERNS=(
  "pkill.*(perplexity|playwright|chromium|chrome)"
  "killall.*(perplexity|playwright|chromium|chrome)"
  "kill +-9.*(perplexity|playwright|chromium)"
)
RM_PATTERNS=(
  "rm .*Singleton"
  "rm .*\.playwright/(profile|profiles)"
  "rm .*perplexity-web-mcp"
  "rm .*profile\.lock"
  "rm .*perplexity.*\.sock"
)

block() {
  echo "BLOCKED (daemon-safety): '$COMMAND' matched '$1'." >&2
  echo "This breaks the shared daemon serving other agents. First make sure the daemon is idle," >&2
  echo "reuse the live browser or wait in line. One-time bypass: PERPLEXITY_DAEMON_GUARD=off." >&2
  exit 2
}

for p in "${KILL_PATTERNS[@]}" "${RM_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qE "$p"; then
    block "$p"
  fi
done

exit 0
