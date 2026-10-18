#!/usr/bin/env bash

fallthrough() { exit 0; }

require() {
  local b
  for b in "$@"; do command -v "$b" >/dev/null 2>&1 || fallthrough; done
}

read_input() {
  HOOK_INPUT="$(cat 2>/dev/null)" || fallthrough
  [ -n "$HOOK_INPUT" ] || fallthrough
  HOOK_TOOL="$(hook_field '.tool_name')"
  HOOK_CWD="$(hook_field '.cwd')"
}

hook_field() {
  printf '%s' "$HOOK_INPUT" | jq -r "$1 // empty" 2>/dev/null
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

# MODE value of one env.ini file (empty when absent).
_ini_mode() {
  [ -f "$1" ] || return 0
  grep -E '^[[:space:]]*MODE[[:space:]]*=' "$1" | head -1 \
    | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]#].*$//' | tr -d "\"'"
}

# 1 when the machine env.ini lets project files widen the hook (raise the mode, replace the lists).
allow_project_config() {
  local v
  v="$(grep -E '^[[:space:]]*ALLOW_PROJECT_CONFIG[[:space:]]*=' "$1/env.ini" 2>/dev/null | head -1 \
       | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]#].*$//' | tr -d "\"'")"
  [ "$v" = "1" ]
}

_mode_rank() {
  case "$1" in strict) echo 1;; permissive) echo 2;; bypass) echo 3;; *) echo 0;; esac
}

# The machine env.ini sets the mode. A project (hooks.env carrier, .claude/auto-approve.env.ini)
# may only lower it; it replaces it only when the machine sets ALLOW_PROJECT_CONFIG=1.
read_mode() {
  local dir="$1" f m pm="" gm
  gm="$(_ini_mode "$dir/env.ini")"
  pm="$(read_hooks_env AUTO_APPROVE_MODE "${CLAUDE_PROJECT_DIR:-${HOOK_CWD:-}}")" || pm=""
  if [ -z "$pm" ] && [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
    pm="$(_ini_mode "$CLAUDE_PROJECT_DIR/.claude/auto-approve.env.ini")"
  fi
  if [ -z "$pm" ]; then printf '%s' "${gm:-off}"; return 0; fi
  if allow_project_config "$dir"; then printf '%s' "$pm"; return 0; fi
  if [ "$(_mode_rank "$pm")" -lt "$(_mode_rank "${gm:-off}")" ]; then printf '%s' "$pm"; else printf '%s' "${gm:-off}"; fi
}

# Masks the token formats of aicore.util.redact (same patterns as hooks/log-bash-command.sh).
_JQ_REDACT='def redact: gsub("sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|Bearer\\s+\\S{20,}"; "‹redacted›")
  | gsub("(?<k>(api[_-]?key|token|secret|password)[\"\u0027]?\\s*[=:]\\s*[\"\u0027]?)[^\\s\"\u0027,;]{8,}"; "\(.k)‹redacted›"; "i");'

log_decision() {
  local dir="$HOME/.claude/logs" file max="${CLAUDE_LOG_MAX_BYTES:-5242880}"
  file="$dir/auto-approve-decisions.jsonl"
  ( umask 077; mkdir -p "$dir" ) 2>/dev/null || return 0
  if [ -f "$file" ] && [ "$(wc -c < "$file" 2>/dev/null || echo 0)" -gt "$max" ]; then
    mv -f "$file" "$file.1" 2>/dev/null
  fi
  (
    umask 077
    jq -cn \
      --arg hook "${HOOK_NAME:-}" --arg cwd "${HOOK_CWD:-}" \
      --arg decision "${1:-}" --arg command "${2:-}" --arg reason "${3:-}" \
      "$_JQ_REDACT"'{ts:(now|todate), hook:$hook, cwd:$cwd, decision:$decision, command:($command|redact), reason:($reason|redact)}' \
      >> "$file" 2>/dev/null
  ) || true
}

emit_allow() {
  log_decision allow "${HOOK_CMD:-}" "${1:-}"
  jq -cn --arg r "${1:-}" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",permissionDecisionReason:$r}}'
  exit 0
}

emit_deny() {
  log_decision deny "${HOOK_CMD:-}" "${1:-}"
  jq -cn --arg r "${1:-}" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r},systemMessage:$r}'
  exit 0
}

fallthrough_logged() {
  log_decision ask "${HOOK_CMD:-}" "${1:-}"
  exit 0
}
