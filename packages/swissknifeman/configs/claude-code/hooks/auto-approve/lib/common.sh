#!/usr/bin/env bash
# Общая библиотека auto-approve хуков. Источать (source), не запускать.
# Любая неожиданность => fallthrough (exit 0) => обычный permission-флоу.

fallthrough() { exit 0; }

# require <bin>...: нет бинарника => fallthrough.
require() {
  local b
  for b in "$@"; do command -v "$b" >/dev/null 2>&1 || fallthrough; done
}

# read_input: stdin (JSON события) => HOOK_INPUT; вытаскивает tool_name/cwd.
read_input() {
  HOOK_INPUT="$(cat 2>/dev/null)" || fallthrough
  [ -n "$HOOK_INPUT" ] || fallthrough
  HOOK_TOOL="$(hook_field '.tool_name')"
  HOOK_CWD="$(hook_field '.cwd')"
}

# hook_field <jq-path>: значение из HOOK_INPUT (пусто если нет).
hook_field() {
  printf '%s' "$HOOK_INPUT" | jq -r "$1 // empty" 2>/dev/null
}

# read_mode <hookdir>: текущий режим из env.ini (strict|permissive|bypass|off).
# Приоритет: $CLAUDE_PROJECT_DIR/.claude/auto-approve.env.ini, затем <hookdir>/env.ini.
read_mode() {
  local dir="$1" f m
  for f in "${CLAUDE_PROJECT_DIR:+$CLAUDE_PROJECT_DIR/.claude/auto-approve.env.ini}" "$dir/env.ini"; do
    [ -n "$f" ] && [ -f "$f" ] || continue
    m="$(grep -E '^[[:space:]]*MODE[[:space:]]*=' "$f" | head -1 \
         | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]#].*$//' | tr -d "\"'")"
    [ -n "$m" ] && { printf '%s' "$m"; return 0; }
  done
  printf 'off'
}

# log_decision <decision> <command> <reason>: дозапись решения в JSONL (для разбора).
log_decision() {
  local dir="$HOME/.claude/logs"
  mkdir -p "$dir" 2>/dev/null || return 0
  jq -cn \
    --arg hook "${HOOK_NAME:-}" --arg cwd "${HOOK_CWD:-}" \
    --arg decision "${1:-}" --arg command "${2:-}" --arg reason "${3:-}" \
    '{ts:(now|todate), hook:$hook, cwd:$cwd, decision:$decision, command:$command, reason:$reason}' \
    >> "$dir/auto-approve-decisions.jsonl" 2>/dev/null || true
}

# emit_allow <reason>: одобрить tool-call без промпта (+лог) и выйти.
emit_allow() {
  log_decision allow "${HOOK_CMD:-}" "${1:-}"
  jq -cn --arg r "${1:-}" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",permissionDecisionReason:$r}}'
  exit 0
}

# emit_deny <reason>: заблокировать tool-call с сообщением (+лог) и выйти.
emit_deny() {
  log_decision deny "${HOOK_CMD:-}" "${1:-}"
  jq -cn --arg r "${1:-}" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r},systemMessage:$r}'
  exit 0
}

# fallthrough_logged <reason>: залогировать «ask» и отдать обычному флоу.
fallthrough_logged() {
  log_decision ask "${HOOK_CMD:-}" "${1:-}"
  exit 0
}
