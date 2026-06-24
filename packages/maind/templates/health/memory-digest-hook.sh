#!/usr/bin/env bash
# managed by maind — SessionStart: инжект ДАЙДЖЕСТА памяти проекта в контекст Claude Code
# через additionalContext. Заменяет нативную авто-загрузку MEMORY.md, когда MODE=maind
# (native выключается autoMemoryEnabled:false). Демон лёг / пусто → тихий no-op.
# Источник: <maind>/templates/health/memory-digest-hook.sh — правьте ТАМ и
# `maind sync --only memory-hook --all --mode update`, не в копии проекта.
# Лаунчер maind: env MAIND_BIN → PATH (command -v). Без машинно-специфичного пути
# в артефакте — генерируемый хук одинаков на любой машине. Не нашли → тихий no-op.
MAIND="${MAIND_BIN:-}"
[ -n "$MAIND" ] || MAIND="$(command -v maind 2>/dev/null)"
[ -n "$MAIND" ] && [ -x "$MAIND" ] || exit 0
digest="$("$MAIND" memory digest 2>/dev/null)"
[ -n "$digest" ] || exit 0
if command -v jq >/dev/null 2>&1; then
  jq -cn --arg c "$digest" \
    '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}'
else
  printf '%s\n' "$digest"          # fallback: плоский stdout тоже попадает в контекст
fi
exit 0
