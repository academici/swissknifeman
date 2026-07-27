#!/usr/bin/env bash
# SubagentStop hook: детерминированный гейт соблюдения архитектуры.
#
# Прогоняет настроенную ПРОЕКТОМ проверку (check_command) после завершения
# субагента. Это L5-рубеж надёжности: skills:-preload (skiller) даёт скиллы
# агенту, а этот хук детерминированно ловит нарушения, на которые модель
# могла забить — то, чего проза «следуй скиллу» не гарантирует.
#
# Содержание проверки — `checks/` (диспетчер `run-checks.sh` + по файлу на
# класс проверки), которые везёт harness; `check_command` в config.json —
# ОДНА стабильная строка-вызов диспетчера. Машина владеет РЕЖИМОМ и НАБОРОМ
# (config.json:checks[]), репозиторий — содержанием проверок.
#
# MODE (env.ini или .claude/review-gate.env.ini проекта), дефолт warn:
#   off    — ничего (база A/B).
#   warn   — проверка не прошла → подсказка в контекст (additionalContext), НЕ блок.
#   strict — проверка не прошла → `exit 2` на SubagentStop. Семантика ВАЖНА:
#            first-party («Can block?» → «Prevents the subagent from
#            stopping») — это НЕ прерывание субагента, а ПРИНУЖДЕНИЕ его
#            продолжать с фидбеком в stderr («it continues working»), петля
#            «нашли нарушение → субагент чинит → снова проверка». Защита от
#            бесконечной петли — счётчик диспетчера (см. checks/run-checks.sh):
#            `stop_hook_active` в первоисточнике не документирован, полагаться
#            на рантайм нельзя.
#
# Безопасно по умолчанию: без check_command хук — no-op. check_command берётся
# ТОЛЬКО из machine-owned config хука ($HOOK_DIR/config.json):
#   { "check_command": "! git -C \"$PWD\" diff --name-only | grep -q ..." }
# Проверка обязана возвращать 0 = чисто, ≠0 = нарушение; stdout идёт в подсказку.
# Project-local .claude/review-gate.config.json НЕ исполняется (RCE при открытии чужого
# репо), пока машина-владелец явно не выставит ALLOW_PROJECT_CONFIG=1 в $HOOK_DIR/env.ini.

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

# MODE: per-project override → hookdir
MODE=""
for f in "$cwd/.claude/review-gate.env.ini" "$HOOK_DIR/env.ini"; do
  m="$(read_ini "$f" MODE 2>/dev/null || true)"
  [ -n "$m" ] && { MODE="$m"; break; }
done
case "$MODE" in off|warn|strict) ;; *) MODE=warn ;; esac
[ "$MODE" = off ] && exit 0

# check_command: ТОЛЬКО machine-owned config ($HOOK_DIR/config.json) по умолчанию.
# Хук стоит глобально на SubagentStop → исполнять команду из project-local
# .claude/review-gate.config.json чужого репо = произвольное исполнение кода (RCE)
# при открытии любого репозитория. Per-project config честно исполняем ТОЛЬКО если
# машина-владелец явно разрешил это в machine-owned env.ini (ALLOW_PROJECT_CONFIG=1).
allow_project="$(read_ini "$HOOK_DIR/env.ini" ALLOW_PROJECT_CONFIG 2>/dev/null || true)"
config_files=("$HOOK_DIR/config.json")
[ "$allow_project" = "1" ] && config_files=("$cwd/.claude/review-gate.config.json" "$HOOK_DIR/config.json")
CHECK=""
if command -v jq >/dev/null 2>&1; then
  for f in "${config_files[@]}"; do
    [ -f "$f" ] && { CHECK="$(jq -r '.check_command // empty' "$f" 2>/dev/null)"; [ -n "$CHECK" ] && break; }
  done
fi
[ -n "$CHECK" ] || exit 0   # проверка не задана — no-op (безопасный дефолт)

# Экспорт для диспетчера checks/run-checks.sh (и для любой project-local
# команды, которая захочет прочитать контекст события) — bash -c ниже
# наследует окружение процесса.
export REVIEW_GATE_DIR="$HOOK_DIR"
export REVIEW_GATE_MODE="$MODE"
export REVIEW_GATE_AGENT_TYPE="$agent_type"
export REVIEW_GATE_SESSION="${session_id:-nosession}"
export REVIEW_GATE_AGENT_ID="${agent_id:-noagent}"

out="$(cd "$cwd" && bash -c "$CHECK" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && exit 0   # чисто

# Наш диспетчер (checks/run-checks.sh) уже применил per-check strict/warn,
# глобальный downgrade и защиту от петли — его exit-код 1=warn/2=strict
# читается напрямую. Любой ДРУГОЙ check_command (custom project-local,
# ALLOW_PROJECT_CONFIG=1, или старый однострочный) не несёт этого контракта —
# для него решает только глобальный $MODE, как раньше (back-compat).
is_dispatcher=0
case "$CHECK" in *run-checks.sh*) is_dispatcher=1 ;; esac
if [ "$is_dispatcher" -eq 1 ]; then
  [ "$rc" -eq 2 ] && strict=1 || strict=0
else
  [ "$MODE" = strict ] && strict=1 || strict=0
fi

downgrade_line="$(printf '%s\n' "$out" | grep '^\[DOWNGRADE\]' | head -1 || true)"
body="$(printf '%s\n' "$out" | grep -v '^\[DOWNGRADE\]' || true)"

reason="review-gate: проверка архитектуры не пройдена после субагента (mode=$MODE).
${body}"

if [ "$strict" -eq 1 ]; then
  printf '%s\n' "$reason" >&2
  exit 2   # принуждает субагента продолжать (НЕ прерывает — см. комментарий выше)
fi

# warn: вернуть подсказку в контекст, не блокируя
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
