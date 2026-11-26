#!/usr/bin/env bash
# Appends every Bash command to ~/.claude/logs/bash-commands.jsonl: secrets masked with the token formats of
# aicore.util.redact, file mode 0600, one rotation (.1) past CLAUDE_LOG_MAX_BYTES (default 5 MiB).

LOG_DIR="$HOME/.claude/logs"
LOG_FILE="$LOG_DIR/bash-commands.jsonl"
LOG_MAX_BYTES="${CLAUDE_LOG_MAX_BYTES:-5242880}"

input=$(cat)
umask 077
mkdir -p "$LOG_DIR"
if [ -f "$LOG_FILE" ] && [ "$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$LOG_MAX_BYTES" ]; then
  mv -f "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null
fi

echo "$input" | jq -c 'def redact: gsub("sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|Bearer\\s+\\S{20,}"; "‹redacted›")
  | gsub("(?<k>(api[_-]?key|token|secret|password)[\"\u0027]?\\s*[=:]\\s*[\"\u0027]?)[^\\s\"\u0027,;]{8,}"; "\(.k)‹redacted›"; "i");
  {
  ts: (now | todate),
  cwd: .cwd,
  session: .session_id,
  command: (.tool_input.command | if type == "string" then redact else . end),
  description: (.tool_input.description | if type == "string" then redact else . end)
}' >> "$LOG_FILE" 2>/dev/null

exit 0
