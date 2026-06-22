#!/usr/bin/env bash
# PreToolUse hook: логирует каждую Bash-команду Claude Code в JSONL.
# Никогда не блокирует выполнение — всегда exit 0.

LOG_DIR="$HOME/.claude/logs"
LOG_FILE="$LOG_DIR/bash-commands.jsonl"

input=$(cat)
mkdir -p "$LOG_DIR"

echo "$input" | jq -c '{
  ts: (now | todate),
  cwd: .cwd,
  session: .session_id,
  command: .tool_input.command,
  description: .tool_input.description
}' >> "$LOG_FILE" 2>/dev/null

exit 0
