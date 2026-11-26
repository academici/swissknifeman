#!/usr/bin/env bash
#
#
#
#            first-party («Can block?» → «Prevents the subagent from
#
#   { "check_command": "! git -C \"$PWD\" diff --name-only | grep -q ..." }

set -uo pipefail
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

input=$(cat)
cwd=""
session_id=""
agent_id=""
agent_type=""
if command -v jq >/dev/null 2>&1; then
  cwd=$(printf '%s' "$input" | jq -r '.cwd // ""' 2>/dev/null)
  session_id=$(printf '%s' "$input" | jq -r '.session_id // ""' 2>/dev/null)
  agent_id=$(printf '%s' "$input" | jq -r '.agent_id // ""' 2>/dev/null)
  agent_type=$(printf '%s' "$input" | jq -r '.agent_type // ""' 2>/dev/null)
fi
[ -n "$cwd" ] || cwd="$PWD"

read_ini() { # file key
  [ -f "$1" ] || return 1
  grep -E "^[[:space:]]*$2[[:space:]]*=" "$1" | head -1 \
    | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]#].*$//' | tr -d "\"'"
}

# Value of KEY from the committed carrier <project>/.swissknifeman/hooks.env (provider key first).
read_hooks_env() {
  local key="$1" dir="${2:-}" f v
  f="$dir/.swissknifeman/hooks.env"
  [ -n "$dir" ] && [ -f "$f" ] || return 1
  v="$(grep -E "^${key}__CLAUDE_CODE=" "$f" | head -1 | cut -d= -f2- | tr -d ' \r')"
  [ -n "$v" ] || v="$(grep -E "^${key}=" "$f" | head -1 | cut -d= -f2- | tr -d ' \r')"
  [ -n "$v" ] || return 1
  printf '%s' "$v"
}

# MODE: carrier → per-project override → hookdir
MODE="$(read_hooks_env REVIEW_GATE_MODE "$cwd" 2>/dev/null || true)"
for f in "$cwd/.claude/review-gate.env.ini" "$HOOK_DIR/env.ini"; do
  [ -n "$MODE" ] && break
  m="$(read_ini "$f" MODE 2>/dev/null || true)"
  [ -n "$m" ] && { MODE="$m"; break; }
done
case "$MODE" in off|warn|strict) ;; *) MODE=warn ;; esac
[ "$MODE" = off ] && exit 0

allow_project="$(read_ini "$HOOK_DIR/env.ini" ALLOW_PROJECT_CONFIG 2>/dev/null || true)"
config_files=("$HOOK_DIR/config.json")
[ "$allow_project" = "1" ] && config_files=("$cwd/.claude/review-gate.config.json" "$HOOK_DIR/config.json")
CHECK=""
if command -v jq >/dev/null 2>&1; then
  for f in "${config_files[@]}"; do
    [ -f "$f" ] && { CHECK="$(jq -r '.check_command // empty' "$f" 2>/dev/null)"; [ -n "$CHECK" ] && break; }
  done
fi
[ -n "$CHECK" ] || exit 0   # Missing check is a safe no-op.

export REVIEW_GATE_DIR="$HOOK_DIR"
export REVIEW_GATE_MODE="$MODE"
export REVIEW_GATE_AGENT_TYPE="$agent_type"
export REVIEW_GATE_SESSION="${session_id:-nosession}"
export REVIEW_GATE_AGENT_ID="${agent_id:-noagent}"

out="$(cd "$cwd" && bash -c "$CHECK" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && exit 0   # Passed.

is_dispatcher=0
case "$CHECK" in *run-checks.sh*) is_dispatcher=1 ;; esac
if [ "$is_dispatcher" -eq 1 ]; then
  [ "$rc" -eq 2 ] && strict=1 || strict=0
else
  [ "$MODE" = strict ] && strict=1 || strict=0
fi

downgrade_line="$(printf '%s\n' "$out" | grep '^\[DOWNGRADE\]' | head -1 || true)"
body="$(printf '%s\n' "$out" | grep -v '^\[DOWNGRADE\]' || true)"

reason="review-gate: architecture check failed after subagent (mode=$MODE).
${body}"

if [ "$strict" -eq 1 ]; then
  printf '%s\n' "$reason" >&2
  exit 2   # Require the subagent to continue without interrupting it.
fi

if command -v jq >/dev/null 2>&1; then
  if [ -n "$downgrade_line" ]; then
    jq -cn --arg r "$reason" --arg s "$downgrade_line" \
      '{hookSpecificOutput:{hookEventName:"SubagentStop",additionalContext:$r},systemMessage:$s}'
  else
    jq -cn --arg r "$reason" \
      '{hookSpecificOutput:{hookEventName:"SubagentStop",additionalContext:$r}}'
  fi
else
  printf '%s\n' "$reason" >&2
fi
exit 0
