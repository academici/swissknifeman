#!/usr/bin/env bash
# SubagentStop hook: детерминированный гейт соблюдения архитектуры.
#
# Прогоняет настроенную ПРОЕКТОМ проверку (check_command) после завершения
# субагента. Это L5-рубеж надёжности: skills:-preload (skiller) даёт скиллы
# агенту, а этот хук детерминированно ловит нарушения, на которые модель
# могла забить — то, чего проза «следуй скиллу» не гарантирует.
#
# MODE (env.ini или .claude/review-gate.env.ini проекта), дефолт warn:
#   off    — ничего (база A/B).
#   warn   — проверка не прошла → подсказка в контекст (additionalContext), НЕ блок.
#   strict — проверка не прошла → блок субагента (exit 2 + причина в stderr).
#
# Безопасно по умолчанию: без check_command хук — no-op. Проект включает гейт,
# задав проверку в .claude/review-gate.config.json (или config.json хука):
#   { "check_command": "! git -C \"$PWD\" diff --name-only | grep -q ..." }
# Проверка обязана возвращать 0 = чисто, ≠0 = нарушение; stdout идёт в подсказку.

set -uo pipefail
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

input=$(cat)
cwd=""
command -v jq >/dev/null 2>&1 && cwd=$(printf '%s' "$input" | jq -r '.cwd // ""' 2>/dev/null)
[ -n "$cwd" ] || cwd="$PWD"

read_ini() { # file key
  [ -f "$1" ] || return 1
  grep -E "^[[:space:]]*$2[[:space:]]*=" "$1" | head -1 \
    | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]#].*$//' | tr -d "\"'"
}

# MODE: per-project override → hookdir
MODE=""
for f in "$cwd/.claude/review-gate.env.ini" "$HOOK_DIR/env.ini"; do
  m="$(read_ini "$f" MODE 2>/dev/null || true)"
  [ -n "$m" ] && { MODE="$m"; break; }
done
case "$MODE" in off|warn|strict) ;; *) MODE=warn ;; esac
[ "$MODE" = off ] && exit 0

# check_command: per-project config → hookdir config
CHECK=""
if command -v jq >/dev/null 2>&1; then
  for f in "$cwd/.claude/review-gate.config.json" "$HOOK_DIR/config.json"; do
    [ -f "$f" ] && { CHECK="$(jq -r '.check_command // empty' "$f" 2>/dev/null)"; [ -n "$CHECK" ] && break; }
  done
fi
[ -n "$CHECK" ] || exit 0   # проверка не задана — no-op (безопасный дефолт)

out="$(cd "$cwd" && bash -c "$CHECK" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && exit 0   # чисто

reason="review-gate: проверка архитектуры не пройдена после субагента (mode=$MODE).
${out}"

if [ "$MODE" = strict ]; then
  printf '%s\n' "$reason" >&2
  exit 2   # блок субагента
fi

# warn: вернуть подсказку в контекст, не блокируя
if command -v jq >/dev/null 2>&1; then
  jq -cn --arg r "$reason" \
    '{hookSpecificOutput:{hookEventName:"SubagentStop",additionalContext:$r}}'
else
  printf '%s\n' "$reason" >&2
fi
exit 0
